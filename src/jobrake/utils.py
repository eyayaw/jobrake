"""Shared parsing and search-argument helpers."""

import logging
from datetime import UTC, datetime

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_BLOCK_TAGS = ("p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "table", "tr", "br", )  # fmt: skip


def html_text(html: str) -> str:
    """
    Extract readable text from an HTML fragment.

    Block tags become line breaks. Inline tags join without spaces. Style and
    script bodies and empty lines are omitted.
    """
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(("style", "script")):
        tag.decompose()
    for tag in soup.find_all(_BLOCK_TAGS):
        tag.insert_before("\n")
        tag.insert_after("\n")
    for cell in soup.find_all(("td", "th")):
        cell.insert_after(" ")
    lines = (" ".join(line.split()) for line in soup.get_text().split("\n"))
    return "\n".join(line for line in lines if line)


def _check_integer(name: str, value: object) -> None:
    """Require an integer for a numeric search argument."""
    # Page slicing and Indeed's query text need real integers. Booleans satisfy
    # isinstance(value, int) on their own, and ``radius=False`` would search a
    # 0 km radius where ``None`` omits it.
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer, got {value!r}")


def check_max_age_hours(max_age_hours: int | None) -> None:
    """Require a positive posting-age bound when one is supplied."""
    if max_age_hours is None:
        return
    _check_integer("max_age_hours", max_age_hours)
    if max_age_hours <= 0:
        raise ValueError(f"max_age_hours ({max_age_hours}) must be positive")


def check_results(results: int) -> None:
    """Require at least one requested result."""
    _check_integer("results", results)
    if results <= 0:
        raise ValueError(f"results ({results}) must be positive")


def check_radius(radius: int | None) -> None:
    """Accept an omitted or nonnegative search radius."""
    if radius is None:
        return
    _check_integer("radius", radius)
    if radius < 0:
        raise ValueError(f"radius ({radius}) must be zero or more")


def iso_date(value: str | None) -> str | None:
    """
    Reduce an ISO 8601 date or timestamp to its calendar date.

    Empty input returns ``None``. Unparseable text logs a warning and remains
    visible as its first ten characters.
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date().isoformat()
    except ValueError:
        # Non-ISO input stays visible in the value rather than vanishing.
        logger.warning("not an ISO 8601 date: %r", value)
        return value[:10]


def epoch_ms_to_iso(ms: float | str) -> str:
    """
    Convert epoch milliseconds to an ISO 8601 UTC timestamp.

    Values resolving before the year 2000 are treated as likely epoch seconds.

    Raises:
        ValueError: The value is invalid, out of range, or likely expressed in seconds.
    """
    try:
        stamp = datetime.fromtimestamp(float(ms) / 1000.0, tz=UTC)
    except (TypeError, ValueError, OSError, OverflowError) as e:
        raise ValueError(f"not epoch milliseconds: {ms!r}") from e
    if stamp.year < 2000:
        raise ValueError(
            f"{ms!r} resolves before 2000, so it looks like epoch seconds rather than milliseconds"
        )
    return stamp.isoformat()
