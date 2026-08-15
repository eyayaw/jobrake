"""Text and date helpers."""

import logging
from datetime import UTC, datetime

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def html_text(html: str) -> str:
    """Plain text from an HTML fragment."""
    if not html:
        return ""
    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)


def iso_date(value: str | None) -> str:
    """``YYYY-MM-DD`` from an ISO 8601 date or timestamp; ``""`` if empty."""
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).date().isoformat()
    except ValueError:
        # Non-ISO input stays visible in the value rather than vanishing.
        logger.warning("not an ISO 8601 date: %r", value)
        return value[:10]


def epoch_ms_to_iso(ms: float | str) -> str:
    """
    ISO 8601 UTC timestamp from epoch milliseconds.

    Raises ``ValueError`` for anything that cannot be epoch milliseconds,
    seconds included: those land in the 1970s, a plausible date and a wrong one.
    """
    try:
        stamp = datetime.fromtimestamp(float(ms) / 1000.0, tz=UTC)
    except (OSError, OverflowError) as e:
        raise ValueError(f"not epoch milliseconds: {ms!r}") from e
    if stamp.year < 2000:
        raise ValueError(f"not epoch milliseconds, seconds rather than ms?: {ms!r}")
    return stamp.isoformat()
