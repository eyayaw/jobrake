"""Text and date helpers"""

from datetime import UTC, datetime

from bs4 import BeautifulSoup


def html_text(html: str) -> str:
    """Plain text from an HTML fragment (descriptions arrive as HTML)."""
    if not html:
        return ""
    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)


def epoch_ms_to_date(ms: float | str) -> str:
    """
    ``YYYY-MM-DD`` (UTC) from epoch milliseconds.

    Raises ``ValueError`` for anything that cannot be epoch milliseconds,
    seconds included: those land in the 1970s, a plausible date and a wrong one.
    """
    try:
        date = datetime.fromtimestamp(float(ms) / 1000.0, tz=UTC)
    except (OSError, OverflowError) as e:
        raise ValueError(f"not epoch milliseconds: {ms!r}") from e
    if date.year < 2000:
        raise ValueError(f"not epoch milliseconds, seconds rather than ms?: {ms!r}")
    return date.strftime("%Y-%m-%d")
