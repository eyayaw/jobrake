"""The posting loop of the sites that fetch each posting on its own, and ``postings_of``."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from jobrake import cache
from jobrake.fetchkit import Fetcher
from jobrake.models import IDENTITY_FIELDS, JobDict, Stopped, make_job
from jobrake.sites.responses import UNREADABLE
from jobrake.utils import Checked, checked, report_progress

# A site's reader of the posting at a card's URL: the posting's fields, or None when the site
# reports the posting gone. It raises Stopped for a posting it could not read, and Halt when no
# posting can be read for now. It sees only the URL, so its fields are the same for every card of
# the posting and can be cached. A url among them is the posting's own address, and a field it
# gives as None is one the posting lacks.
type Reader = Callable[[Fetcher, str], Awaitable[dict[str, Any] | None]]


class Halt(Exception):
    """
    Raised by a reader when no posting can be read for now, as after a persistent HTTP 429.

    The message says why and what to do next. The loop ends, and the postings read by then stay.
    """


def _merge(card: JobDict, record: JobDict) -> JobDict:
    # The card keeps its identity, and the posting's record wins wherever it has a value.
    # make_job left a field the posting lacks as None or [], or out of the record.
    kept = {
        name: value
        for name, value in record.items()
        if name not in IDENTITY_FIELDS and value not in (None, [])
    }
    return make_job(**(card | kept))


async def _posting(fetcher: Fetcher, card: JobDict, read: Reader) -> JobDict | None:
    """
    Read a card's posting as a record of its own and cache it, or return None for a gone posting.

    The card gives the record its ``site`` and ``id``, and its ``url`` when the reader gives none.
    Every other field is the posting's, so a cached record and a fresh one are the same.
    """
    fields = await read(fetcher, card["url"])
    if fields is None:
        return None
    given = {name: value for name, value in fields.items() if value is not None}
    identity = {"site": card["site"], "id": card["id"]}
    try:
        record = make_job(**({"url": card["url"]} | given | identity))
    except UNREADABLE as error:
        # A field can hold a value nested deeper than make_job recurses, though json.loads read it.
        raise Stopped(f"the posting's fields are malformed: {error!r}") from None
    cache.CACHE.put([record])
    return record


async def _read_each(
    fetcher: Fetcher, cards: list[JobDict], read: Reader, workers: int
) -> dict[str, JobDict | None]:
    """
    Map each card's ID to its posting's record, or to None for a gone posting.

    The cards are one site's. Cards of one posting share the read of the first, and a cached
    posting costs no request. A failed read is logged and left out, and a ``Halt`` ends the reads
    with a warning.
    ``workers`` postings are read at a time, in the cards' order.
    """
    if not cards:
        return {}
    site = cards[0]["site"]
    logger = logging.getLogger(f"jobrake.sites.{site}")
    unique: dict[str, JobDict] = {}
    for card in cards:
        unique.setdefault(card["id"], card)
    found: dict[str, JobDict | None] = dict(cache.CACHE.get(site, unique))
    done = len(found)
    report_progress(logger, f"{site} details", done, len(unique))
    # Every worker takes from one iterator, so each posting is read once.
    pending = iter([card for posting, card in unique.items() if posting not in found])

    async def work() -> None:
        nonlocal done
        for card in pending:
            try:
                found[card["id"]] = await _posting(fetcher, card, read)
            except Stopped as stopped:
                logger.warning("skipping posting %s: %s", card["url"], stopped)
            done += 1
            report_progress(logger, f"{site} details", done, len(unique))

    try:
        # The group cancels the other workers on the first error and awaits them all,
        # through a repeated cancellation, so none outlives the caller's transport.
        async with asyncio.TaskGroup() as group:
            for _ in range(workers):
                group.create_task(work())
    except ExceptionGroup as errors:
        # A fetcher's own exception leaves as itself and outranks a Halt.
        for error in errors.exceptions:
            if not isinstance(error, Halt):
                raise error from None
        logger.warning(
            "reading %s postings stopped at %d of %d: %s",
            site,
            len(found),
            len(unique),
            errors.exceptions[0],
        )
    return found


async def fill_details(
    fetcher: Fetcher, cards: list[JobDict], read: Reader, *, workers: int = 1
) -> list[JobDict]:
    """
    Fill each card with its posting's record, reading ``workers`` postings at a time.

    The record wins wherever it has a value, and the card keeps its ``site``, ``id``, and ``url``.
    A posting the site reports gone keeps its card.

    Raises:
        Stopped: A posting could not be read. ``partial`` holds every card, filled where its read
            succeeded, and ``failed`` the URLs of the cards whose read failed.
    """
    found = await _read_each(fetcher, cards, read, workers)
    filled = [_merge(card, record) if (record := found.get(card["id"])) else card for card in cards]
    if failed := [card["url"] for card in cards if card["id"] not in found]:
        raise Stopped(
            f"{cards[0]['site']} could not fetch the details of {len(failed)} of {len(cards)} "
            "postings. Pass their URLs to postings to retry them",
            partial=filled,
            failed=failed,
        )
    return filled


def readable_url(card: Callable[[str], JobDict], posting_id: object, url: str) -> str:
    """
    Return a search card's URL when the site's ``card`` reads it back unchanged, as that posting.

    ``postings`` and a details search fetch a posting from its URL, so a URL that ``card`` refuses
    or reads as another posting would leave the card unfillable. The URL must also come back
    unchanged, as ``urlsplit`` drops a tab or newline the record would keep.

    Raises:
        TypeError: ``card`` refuses the URL, or reads another posting ID or URL from it.
    """
    try:
        named = card(url)
    except ValueError:
        same = False
    else:
        same = named["id"] == posting_id and named["url"] == url
    if not same:
        raise TypeError(f"{url!r} does not read back as posting {posting_id!r}")
    return url


def postings_of(
    card: Callable[[str], JobDict],
    read: Reader,
    *,
    workers: int = 1,
    help_text: str = "posting URLs",
) -> Checked[[Fetcher, list[str]], dict[str, JobDict | None]]:
    """
    Build a site's ``postings`` from its ``card`` and its reader.

    ``workers`` postings are read at a time, and ``help_text`` names the references in the CLI
    help.
    """

    async def postings(
        fetcher: Fetcher, references: Annotated[list[str], help_text]
    ) -> dict[str, JobDict | None]:
        """
        Fetch known postings, with no request for a cached posting.

        The result is keyed by the references given, and references naming one posting share one
        record, read from the first of them. The site's ``card`` reads each reference as the card
        it names, before the first request. A reference maps to ``None`` when the site reports its
        posting gone. A posting that was not read has no key, and a warning says why.

        Raises:
            ValueError: ``card`` refused a reference. Nothing is fetched in that case.
        """
        cards = {reference: card(reference) for reference in references}
        found = await _read_each(fetcher, list(cards.values()), read, workers)
        return {
            reference: found[named["id"]]
            for reference, named in cards.items()
            if named["id"] in found
        }

    def _readable(*, references: list[str]) -> None:
        # So postings.check refuses every reference the call would.
        for reference in references:
            card(reference)

    # Checked names a function's site after its module.
    postings.__module__ = card.__module__
    return checked(validator=_readable)(postings)
