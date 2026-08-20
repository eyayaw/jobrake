import logging
from datetime import UTC, datetime

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_BLOCK_TAGS = ("p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "table", "tr", "br", )  # fmt: skip


def html_text(html: str) -> str:
    """
    Plain text from an HTML fragment, with one line per block.

    Block tags become line breaks. Inline tags join without spaces. Style and
    script bodies are dropped.
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


def check_hours_old(hours_old: int | None) -> None:
    """Raise ``ValueError`` unless ``hours_old`` is ``None`` or positive."""
    if hours_old is not None and hours_old <= 0:
        raise ValueError(f"hours_old ({hours_old}) must be positive, or None for no age bound")


def iso_date(value: str | None) -> str | None:
    """``YYYY-MM-DD`` from an ISO 8601 date or timestamp, or ``None`` if absent."""
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
    ISO 8601 UTC timestamp from epoch milliseconds.

    Raises ``ValueError`` for values that cannot be epoch milliseconds. Epoch
    seconds land in the 1970s, so they are rejected too.
    """
    try:
        stamp = datetime.fromtimestamp(float(ms) / 1000.0, tz=UTC)
    except (TypeError, ValueError, OSError, OverflowError) as e:
        raise ValueError(f"not epoch milliseconds: {ms!r}") from e
    if stamp.year < 2000:
        raise ValueError(f"not epoch milliseconds, seconds rather than ms?: {ms!r}")
    return stamp.isoformat()
