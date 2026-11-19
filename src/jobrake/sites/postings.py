"""The posting loop of the sites that read one posting per request, and their ``postings``."""

import logging
from collections.abc import Awaitable, Callable, Container
from typing import Annotated, Any

from jobrake import cache
from jobrake.fetchkit import Fetcher
from jobrake.models import IDENTITY_FIELDS, JobDict, Stopped, make_job
from jobrake.utils import Checked, checked, report_progress

logger = logging.getLogger(__name__)

# A site's reader of the posting at a card's URL: the fields the posting adds, or None when the site
# reports the posting gone. It raises Stopped for a failed request or an unreadable response.
# It sees only the URL, so its fields are the same for every card of the posting and can be cached.
type Reader = Callable[[Fetcher, str], Awaitable[dict[str, Any] | None]]


def _merge(card: JobDict, fields: dict[str, Any]) -> JobDict:
    # The card keeps its identity. A None, blank, or empty field leaves the card's value in place.
    kept = {
        name: value
        for name, value in fields.items()
        if name not in IDENTITY_FIELDS
        and value not in (None, [])
        and not (isinstance(value, str) and not value.strip())
    }
    return make_job(**(card | kept))


async def _read_each(
    fetcher: Fetcher, cards: list[JobDict], read: Reader
) -> dict[str, dict[str, Any] | None]:
    """
    Map each card's ID to what ``read`` returns for it, logging and leaving out a failed read.

    A cached posting costs no request. Each read's fields become a normalized record of their own,
    which fills this card and goes to the cache, so a later card merges with the same record.
    A read sees only the URL, so that record suits any card of the posting. A gone posting stays
    out of the cache. The cards are one site's, and each names that site.
    """
    if not cards:
        return {}
    site = cards[0]["site"]
    cached = cache.CACHE.get(site, [card["id"] for card in cards])
    found: dict[str, dict[str, Any] | None] = {
        posting: dict(job) for posting, job in cached.items()
    }
    for position, card in enumerate(cards, start=1):
        report_progress(logger, f"{site} details", position, len(cards))
        if card["id"] in found:
            continue
        try:
            fields = await read(fetcher, card["url"])
        except Stopped as stopped:
            logger.warning("skipping posting %s: %s", card["url"], stopped)
            continue
        if fields is None:
            found[card["id"]] = None
            continue
        record = _merge(make_job(site=site, id=card["id"], url=card["url"]), fields)
        cache.CACHE.put([record])
        found[card["id"]] = dict(record)
    return found


def stop_if_unread(jobs: list[JobDict], found: Container[str]) -> None:
    """
    End a details search unless every posting in ``jobs`` was read or reported gone.

    Raises:
        Stopped: A posting's ID is not in ``found``. ``partial`` holds ``jobs``, and ``failed`` the
            URLs of the postings whose ID is missing.
    """
    if failed := [job["url"] for job in jobs if job["id"] not in found]:
        raise Stopped(
            f"{jobs[0]['site']} could not fetch the details of {len(failed)} of {len(jobs)} "
            "postings. Pass their URLs to postings to retry them",
            partial=jobs,
            failed=failed,
        )


async def fill_details(fetcher: Fetcher, cards: list[JobDict], read: Reader) -> list[JobDict]:
    """
    Fill each card with its posting's fields, one request after another.

    A posting the site reports gone keeps its card.

    Raises:
        Stopped: A posting's fields could not be read. ``partial`` holds every card,
            filled where its read succeeded, and ``failed`` the URLs of the cards whose read failed.
    """
    found = await _read_each(fetcher, cards, read)
    filled = [_merge(card, found.get(card["id"]) or {}) for card in cards]
    stop_if_unread(filled, found)
    return filled


def postings_of(
    card: Callable[[str], JobDict], read: Reader, *, help_text: str = "posting URLs"
) -> Checked[[Fetcher, list[str]], dict[str, JobDict | None]]:
    """
    Build a site's ``postings`` from its ``card`` and its reader.

    ``help_text`` names the references in the CLI help.
    """

    async def postings(
        fetcher: Fetcher, references: Annotated[list[str], help_text]
    ) -> dict[str, JobDict | None]:
        """
        Fetch known postings by reference, with no request for a cached posting.

        The result is keyed by the references given, and references naming one posting share one
        read. The site's ``card`` reads each reference as the card it names, before the first
        request. A reference maps to ``None`` when the site reports its posting gone. After a
        failed read it has no key, and a warning names its posting.

        Raises:
            ValueError: ``card`` refused a reference. Nothing is fetched in that case.
        """
        cards = {reference: card(reference) for reference in references}
        unique = {named["id"]: named for named in cards.values()}
        found = await _read_each(fetcher, list(unique.values()), read)
        records = {
            posting: None if fields is None else _merge(unique[posting], fields)
            for posting, fields in found.items()
        }
        return {
            reference: records[named["id"]]
            for reference, named in cards.items()
            if named["id"] in records
        }

    # Checked names a function's site after its module.
    postings.__module__ = card.__module__
    return checked(postings)
