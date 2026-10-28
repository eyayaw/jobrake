"""Shared parsing and search-argument helpers."""

import functools
import inspect
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from types import NoneType
from typing import Annotated, Any, NamedTuple, Union, get_args, get_origin

lazy from bs4 import BeautifulSoup

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
    """One argument a site function declares after the fetcher, as ``Annotated[kind, help]``."""

    kind: object  # str, int, bool, or list[str]
    optional: bool  # whether the annotation adds ``| None``
    help: str
    default: object  # inspect.Parameter.empty for a required argument
    positional: bool  # whether it is the text a lookup or postings() takes before its options


# Each type a site function may declare, with its description and its check.
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


def site_options(function: Callable[..., object]) -> dict[str, Option]:
    """
    Map each argument after the fetcher to its ``Annotated`` kind, help, and default, keeping signature order.

    Raises:
        TypeError: An argument is not ``Annotated[kind, help]`` with a
            supported kind and nonblank help, or a boolean option has a
            default other than ``False``.
    """
    where = f"{function.__module__}.{getattr(function, '__qualname__', function)}"
    _, *params = inspect.signature(function).parameters.values()
    options = {}
    for param in params:
        if param.kind not in (param.POSITIONAL_OR_KEYWORD, param.KEYWORD_ONLY):
            raise TypeError(f"{where}: declare {param.name} as a named argument")
        if get_origin(param.annotation) is not Annotated:
            raise TypeError(f"{where}: annotate {param.name} as Annotated[kind, help]")
        kind, help_text, *_ = get_args(param.annotation)
        if not isinstance(help_text, str) or not help_text.strip():
            raise TypeError(f"{where}: give {param.name} a help string in its Annotated")
        members = get_args(kind) if get_origin(kind) is Union else ()
        optional = NoneType in members and len(members) == 2
        if optional:
            (kind,) = (member for member in members if member is not NoneType)
        if kind not in _TYPES:
            raise TypeError(
                f"{where}: {param.name} is {kind!r}. Use str, int, bool, or list[str], "
                "each optionally | None"
            )
        positional = param.kind is param.POSITIONAL_OR_KEYWORD
        # The CLI turns a boolean option into a flag that sets it.
        if kind is bool and not positional and param.default is not False:
            raise TypeError(f"{where}: the boolean option {param.name} must default to False")
        options[param.name] = Option(kind, optional, help_text, param.default, positional)
    return options


def _check(options: dict[str, Option], given: dict[str, object]) -> None:
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
        # A required text, such as a lookup's name or a board, names what to
        # read, so a blank one asks for nothing.
        required = option.default is inspect.Parameter.empty
        if required and isinstance(value, str) and not value.strip():
            raise ValueError(f"{name} is blank. Pass the {option.help}")
        # A blank list entry names nothing either.
        if isinstance(value, list) and not all(item.strip() for item in value):
            raise ValueError(f"{name} holds a blank entry. Pass the {option.help}")


def checked[**P, R](function: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """
    Check every call of a site function against its annotations before the function runs.

    The signature is read once, here, so a site function that breaks the
    rules of ``site_options`` fails when its module is imported. Error
    messages name the site after the package below ``jobrake.sites``.

    Raises:
        TypeError: At decoration, the signature breaks a rule of
            ``site_options``. At a call, an argument is unknown, missing, or of
            the wrong type.
        ValueError: At a call, ``results``, ``radius``, or ``max_age_hours``
            is below its minimum, or a required string or a list entry is blank.
    """
    signature = inspect.signature(function)
    options = site_options(function)
    site = function.__module__.removeprefix("jobrake.sites.").partition(".")[0]
    keywords = ", ".join(name for name, option in options.items() if not option.positional)
    listing = f"Its options are {keywords}" if keywords else "It takes no options"

    @functools.wraps(function)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            _, *given = signature.bind(*args, **kwargs).arguments.items()
        except TypeError as error:
            raise TypeError(f"{site}: {error}. {listing}") from None
        _check(options, dict(given))
        return await function(*args, **kwargs)

    return wrapper


def as_str(value: object) -> str | None:
    """Return a JSON value when it is a string, or None for anything else."""
    return value if isinstance(value, str) else None


def as_dict(value: object) -> dict[str, Any]:
    """Return a JSON value unchanged when it is an object, or ``{}`` for anything else, so a ``.get`` can follow."""
    return value if isinstance(value, dict) else {}


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
