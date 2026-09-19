"""Shared parsing and search-argument helpers."""

import logging
import re
from datetime import UTC, datetime
from typing import NamedTuple

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


class _Bound(NamedTuple):
    """What one numeric search option accepts."""

    minimum: int
    requirement: str
    optional: bool = False


_BOUNDS = {
    "results": _Bound(1, "positive"),
    "radius": _Bound(0, "zero or more", optional=True),
    "max_age_hours": _Bound(1, "positive", optional=True),
}


def check_bounds(**values: int | None) -> None:
    """Require each numeric search option to be an integer within its bound."""
    for name, value in values.items():
        bound = _BOUNDS[name]
        if value is None and bound.optional:
            continue
        # Page slicing and Indeed's query text need real integers. Booleans
        # satisfy isinstance(value, int) on their own, and ``radius=False``
        # would search a 0 km radius where ``None`` omits it.
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer, got {value!r}")
        if value < bound.minimum:
            raise ValueError(f"{name} ({value}) must be {bound.requirement}")


def check_flags(**flags: bool) -> None:
    """Require a Boolean for each search flag."""
    for name, value in flags.items():
        if not isinstance(value, bool):
            raise TypeError(f"{name} must be a boolean, got {value!r}")


def check_attributes(attributes: list[str] | None) -> None:
    """Require a list of nonblank attribute codes when supplied."""
    if attributes is None:
        return
    if not isinstance(attributes, list):
        raise TypeError("attributes must be a list of code strings")
    for code in attributes:
        if not isinstance(code, str):
            raise TypeError(f"attribute code {code!r} must be a string")
        if not code.strip():
            raise ValueError(
                "attribute code is blank. Find codes with "
                "'jobrake attributes indeed -c EDITION QUERY'"
            )


def check_language(language: str | None) -> None:
    """Validate an optional two-letter language code."""
    if language is None:
        return
    if not isinstance(language, str):
        raise TypeError(f"language must be a string or None, got {language!r}")
    if re.fullmatch(r"[A-Za-z]{2}", language) is None:
        raise ValueError(
            f"language {language!r} must contain exactly two ASCII letters, such as 'en'"
        )


# Which provider applies each search filter. The other one accepts the
# argument and leaves it unused.
_FILTER_PROVIDER = {
    "remote": "indeed",
    "language": "indeed",
    "attributes": "indeed",
    "easy_apply": "linkedin",
    "early_applicant": "linkedin",
}


def warn_ignored_filters(site: str, **filters: object) -> None:
    """
    Report each supplied filter the selected provider cannot apply.

    The search still runs, so the warning is the only sign that a restriction
    took no effect.
    """
    for name, value in filters.items():
        if value and _FILTER_PROVIDER[name] != site:
            logger.warning(
                "%s ignores %s and searches without it. Run the search on %s to apply it",
                site,
                name,
                _FILTER_PROVIDER[name],
            )


def check_companies(companies: list[str] | None, *, site: str) -> None:
    """Validate LinkedIn company IDs or one Indeed employer key."""
    if companies is None:
        return
    if not isinstance(companies, list):
        raise TypeError("companies must be a list of company ID strings")
    if site == "indeed" and len(companies) > 1:
        raise ValueError("jobrake supports one Indeed employer key per search. Supply a single key")
    for company in companies:
        if not isinstance(company, str):
            raise TypeError(f"company ID {company!r} must be a string")
        if site == "linkedin":
            if not (company.isascii() and company.isdigit()):
                raise ValueError(f"company ID {company!r} must use digits 0-9, such as '1173'")
        elif not company.strip():
            raise ValueError(
                "Indeed employer key is blank. Find a key with "
                "'jobrake companies indeed NAME --country EDITION'"
            )


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
