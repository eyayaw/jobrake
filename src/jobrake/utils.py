"""Shared parsing and search-argument helpers."""

import logging
import re
from collections.abc import Callable
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


def check_flag(name: str, value: object, *, site: str) -> None:
    """Require a Boolean for one search flag."""
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a boolean, got {value!r}")


def check_attributes(name: str, value: object, *, site: str) -> None:
    """Require a list of nonblank attribute codes when supplied."""
    if value is None:
        return
    if not isinstance(value, list):
        raise TypeError(f"{name} must be a list of code strings")
    for code in value:
        if not isinstance(code, str):
            raise TypeError(f"attribute code {code!r} must be a string")
        if not code.strip():
            raise ValueError(
                "attribute code is blank. Find codes with "
                "'jobrake attributes indeed -c EDITION QUERY'"
            )


def check_language(name: str, value: object, *, site: str) -> None:
    """Validate an optional two-letter language code."""
    if value is None:
        return
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string or None, got {value!r}")
    if re.fullmatch(r"[A-Za-z]{2}", value) is None:
        raise ValueError(f"{name} {value!r} must contain exactly two ASCII letters, such as 'en'")


def check_companies(name: str, value: object, *, site: str) -> None:
    """Validate LinkedIn company IDs or one Indeed employer key."""
    if value is None:
        return
    if not isinstance(value, list):
        raise TypeError(f"{name} must be a list of company ID strings")
    if site == "indeed" and len(value) > 1:
        raise ValueError("jobrake supports one Indeed employer key per search. Supply a single key")
    for company in value:
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


class _Filter(NamedTuple):
    """How one search filter is checked and which providers apply it."""

    check: Callable[..., None]
    providers: tuple[str, ...]


# Any provider outside a filter's row accepts the argument and runs anyway.
_FILTERS = {
    "companies": _Filter(check_companies, ("indeed", "linkedin")),
    "remote": _Filter(check_flag, ("indeed",)),
    "language": _Filter(check_language, ("indeed",)),
    "attributes": _Filter(check_attributes, ("indeed",)),
    "easy_apply": _Filter(check_flag, ("linkedin",)),
    "early_applicant": _Filter(check_flag, ("linkedin",)),
}

_SITES = frozenset(site for entry in _FILTERS.values() for site in entry.providers)


def check_filters(site: str, **filters: object) -> None:
    """
    Validate each filter the provider applies and warn for each one it ignores.

    An ignored filter goes unchecked, and its warning is the only sign that the
    restriction took no effect. A falsy value asks for no restriction and
    passes in silence. Warnings follow the last check, so a rejected search
    logs none.

    Raises:
        KeyError: No provider applies the filter.
        TypeError: An applied filter has the wrong type.
        ValueError: The site is unknown, or an applied filter has an unusable value.
    """
    if site not in _SITES:
        # An unknown site matches no row, which would leave every filter unchecked.
        raise ValueError(f"unknown site {site!r}. Expected one of {sorted(_SITES)}")
    ignored = []
    for name, value in filters.items():
        entry = _FILTERS[name]
        if site in entry.providers:
            entry.check(name, value, site=site)
        elif value:
            ignored.append(name)
    for name in ignored:
        logger.warning(
            "%s ignores %s and searches without it. Run the search on %s to apply it",
            site,
            name,
            " or ".join(_FILTERS[name].providers),
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
