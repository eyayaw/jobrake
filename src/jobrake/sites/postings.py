"""The posting loop of the sites that fill a card with one request per posting."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from jobrake.models import JobDict, Stopped, make_job

logger = logging.getLogger(__name__)

# A site's reader of one card's posting: the fields the posting adds, {} when
# the site reports the posting gone, or None when the request failed or the
# response is unreadable, which the reader logs.
type Reader = Callable[[JobDict], Awaitable[dict[str, Any] | None]]


def _merge(card: JobDict, fields: dict[str, Any]) -> JobDict:
    # A None, blank, or empty field leaves the card's value in place.
    kept = {
        name: value
        for name, value in fields.items()
        if value not in (None, []) and not (isinstance(value, str) and not value.strip())
    }
    return make_job(**(card | kept))


async def _read_each(site: str, cards: list[JobDict], read: Reader) -> list[dict[str, Any] | None]:
    fields = []
    for position, card in enumerate(cards, start=1):
        # The CLI renders progress-flagged records as one self-updating stderr line.
        logger.info(
            "%s details %d/%d",
            site,
            position,
            len(cards),
            extra={"progress": (position, len(cards))},
        )
        fields.append(await read(card))
    return fields


async def fill_details(site: str, cards: list[JobDict], read: Reader) -> list[JobDict]:
    """
    Fill each card with its posting's fields, one request after another.

    A posting the site reports gone keeps its card.

    Raises:
        Stopped: A posting's fields could not be read. ``partial`` holds every
            card, filled where its read succeeded.
    """
    fields = await _read_each(site, cards, read)
    filled = [_merge(card, found or {}) for card, found in zip(cards, fields, strict=True)]
    if missing := fields.count(None):
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
    unique = list({found["id"]: found for found in cards.values()}.values())
    fields = await _read_each(site, unique, read)
    records = {
        posting["id"]: _merge(posting, found) if found else None
        for posting, found in zip(unique, fields, strict=True)
        if found is not None
    }
    return {reference: records[c["id"]] for reference, c in cards.items() if c["id"] in records}
