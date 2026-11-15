"""The posting loop of the sites that fill a card with one request per posting."""

import logging
from collections.abc import Awaitable, Callable, Container
from typing import Any

from jobrake import cache
from jobrake.models import JobDict, Stopped, make_job
from jobrake.utils import report_progress

logger = logging.getLogger(__name__)

# A site's reader of one card's posting: the fields the posting adds, or None when the site reports
# the posting gone. It raises Stopped for a failed request or an unreadable response.
type Reader = Callable[[JobDict], Awaitable[dict[str, Any] | None]]


def _merge(card: JobDict, fields: dict[str, Any]) -> JobDict:
    # A None, blank, or empty field leaves the card's value in place.
    kept = {
        name: value
        for name, value in fields.items()
        if value not in (None, []) and not (isinstance(value, str) and not value.strip())
    }
    return make_job(**(card | kept))


async def _read_each(
    site: str, cards: list[JobDict], read: Reader
) -> dict[str, dict[str, Any] | None]:
    """
    Map each card's ID to what ``read`` returns for it, logging and leaving out a failed read.

    A cached posting costs no request. Each read's fields go to the cache as a record of their own,
    so a later card merges with them as with a fresh read. A gone posting stays out of the cache.
    """
    cached = cache.CACHE.get(site, [card["id"] for card in cards])
    found: dict[str, dict[str, Any] | None] = {
        posting: dict(job) for posting, job in cached.items()
    }
    for position, card in enumerate(cards, start=1):
        report_progress(logger, f"{site} details", position, len(cards))
        if card["id"] in found:
            continue
        try:
            fields = await read(card)
        except Stopped as stopped:
            logger.warning("skipping posting %s: %s", card["url"], stopped)
            continue
        found[card["id"]] = fields
        if fields is not None:
            cache.CACHE.put([_merge(make_job(site=site, id=card["id"], url=card["url"]), fields)])
    return found


def stop_if_unread(site: str, jobs: list[JobDict], found: Container[str]) -> None:
    """
    End a details search unless every posting in ``jobs`` was read or reported gone.

    Raises:
        Stopped: A posting's ID is not in ``found``. ``partial`` holds ``jobs``, and ``failed`` the
            URLs of the postings whose ID is missing.
    """
    if failed := [job["url"] for job in jobs if job["id"] not in found]:
        raise Stopped(
            f"{site} could not fetch the details of {len(failed)} of {len(jobs)} postings. "
            "Pass their URLs to postings to retry them",
            partial=jobs,
            failed=failed,
        )


async def fill_details(site: str, cards: list[JobDict], read: Reader) -> list[JobDict]:
    """
    Fill each card with its posting's fields, one request after another.

    A posting the site reports gone keeps its card.

    Raises:
        Stopped: A posting's fields could not be read. ``partial`` holds every card,
            filled where its read succeeded, and ``failed`` the URLs of the cards whose read failed.
    """
    found = await _read_each(site, cards, read)
    filled = [_merge(card, found.get(card["id"]) or {}) for card in cards]
    stop_if_unread(site, filled, found)
    return filled


async def fetch_postings(
    site: str, references: list[str], card: Callable[[str], JobDict], read: Reader
) -> dict[str, JobDict | None]:
    """
    Fetch the posting each reference names, keyed by the references given.

    ``card`` reads a reference as the card it names, so every reference is checked before the first
    request. References naming one posting share one request. A posting the site reports gone maps
    to None, and a reference whose read failed has no key.

    Raises:
        ValueError: ``card`` rejected a reference.
    """
    cards = {reference: card(reference) for reference in references}
    unique = {named["id"]: named for named in cards.values()}
    found = await _read_each(site, list(unique.values()), read)
    records = {
        posting: None if fields is None else _merge(unique[posting], fields)
        for posting, fields in found.items()
    }
    return {
        reference: records[named["id"]]
        for reference, named in cards.items()
        if named["id"] in records
    }
