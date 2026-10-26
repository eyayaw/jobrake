"""Shared parsing and search-argument helpers."""

import inspect
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from types import NoneType
from typing import NamedTuple, Union, get_args, get_origin

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


class Option(NamedTuple):
    """One keyword option a site function declares as ``Annotated[kind, help]``."""

    kind: object  # str, int, bool, or list[str]
    optional: bool  # whether the annotation adds ``| None``
    help: str
    default: object  # inspect.Parameter.empty for a required option


def site_options(function: Callable[..., object]) -> dict[str, Option]:
    """Read the keyword-only options of a site function from its annotations, in order."""
    options = {}
    for param in inspect.signature(function).parameters.values():
        if param.kind is not param.KEYWORD_ONLY:
            continue
        kind, help_text = get_args(param.annotation)
        members = get_args(kind) if get_origin(kind) is Union else ()
        optional = NoneType in members
        if optional:
            (kind,) = (member for member in members if member is not NoneType)
        options[param.name] = Option(kind, optional, help_text, param.default)
    return options


# Each option type a site may declare, with its description and its check.
# bool is a subclass of int, so an int option rejects it.
_TYPES: dict[object, tuple[str, Callable[[object], bool]]] = {
    str: ("a string", lambda value: isinstance(value, str)),
    int: ("an integer", lambda value: isinstance(value, int) and not isinstance(value, bool)),
    bool: ("a boolean", lambda value: isinstance(value, bool)),
    list[str]: (
        "a list of strings",
        lambda value: isinstance(value, list) and all(isinstance(item, str) for item in value),
    ),
}

# Options that keep one meaning on every site that declares them, with their smallest value.
_MINIMUMS = {"results": 1, "radius": 0, "max_age_hours": 1}


def check_options(site: str, function: Callable[..., object], given: dict[str, object]) -> None:
    """
    Reject options a site function does not declare, or whose values do not fit its annotations.

    Raises:
        TypeError: An option is unknown, a required option is missing, or a
            value does not match its annotation.
        ValueError: ``results``, ``radius``, or ``max_age_hours`` is below its minimum.
    """
    options = site_options(function)
    listing = ", ".join(options)
    if unknown := [name for name in given if name not in options]:
        raise TypeError(f"{site} has no option {', '.join(unknown)}. Its options are {listing}")
    required = [
        name for name, option in options.items() if option.default is inspect.Parameter.empty
    ]
    if missing := [name for name in required if name not in given]:
        raise TypeError(f"{site} requires {', '.join(missing)}. Its options are {listing}")
    for name, value in given.items():
        option = options[name]
        if value is None and option.optional:
            continue
        description, accepts = _TYPES[option.kind]
        if not accepts(value):
            expected = description + (" or None" if option.optional else "")
            raise TypeError(f"{name} must be {expected}, got {value!r}")
        minimum = _MINIMUMS.get(name)
        if minimum is not None and isinstance(value, int) and value < minimum:
            raise ValueError(f"{name} ({value}) must be at least {minimum}")


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
