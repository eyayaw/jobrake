"""The posting loop of the sites that fill a card with one request per posting."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from jobrake.models import JobDict, Stopped, make_job
from jobrake.utils import report_progress

logger = logging.getLogger(__name__)

# A site's reader of one card's posting: the fields the posting adds, or None
# when the site reports the posting gone. It raises Stopped for a failed
# request or an unreadable response.
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
    """Map each card's ID to what ``read`` returns for it, logging and leaving out a failed read."""
    found = {}
    for position, card in enumerate(cards, start=1):
        report_progress(logger, f"{site} details", position, len(cards))
        try:
            found[card["id"]] = await read(card)
        except Stopped as stopped:
            logger.warning("skipping posting %s: %s. A rerun retries it", card["url"], stopped)
    return found


async def fill_details(site: str, cards: list[JobDict], read: Reader) -> list[JobDict]:
    """
    Fill each card with its posting's fields, one request after another.

    A posting the site reports gone keeps its card.

    Raises:
        Stopped: A posting's fields could not be read. ``partial`` holds every
            card, filled where its read succeeded.
    """
    found = await _read_each(site, cards, read)
    filled = [_merge(card, found.get(card["id"]) or {}) for card in cards]
    if missing := len(cards) - len(found):
        raise Stopped(
            f"{site} could not fetch the details of {missing} of {len(cards)} postings. "
            "A rerun retries them",
            partial=filled,
        )
    return filled


async def fetch_postings(
    site: str, references: list[str], card: Callable[[str], JobDict], read: Reader
) -> dict[str, JobDict | None]:
    """
    Fetch the posting each reference names, keyed by the references given.

    ``card`` reads a reference as the card it names, so every reference is
    checked before the first request. References naming one posting share
    one request. A posting the site reports gone maps to None, and a
    reference whose read failed has no key.

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
