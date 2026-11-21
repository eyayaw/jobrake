"""Shared parsing and search-argument helpers."""

import functools
import inspect
import logging
import math
import re
from collections.abc import Awaitable, Callable, Collection, Mapping
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from types import NoneType
from typing import Annotated, Any, NamedTuple, Union, get_args, get_origin, overload
from urllib.parse import SplitResult, urlsplit

lazy from bs4 import BeautifulSoup
lazy from bs4.element import Tag

logger = logging.getLogger(__name__)

_BLOCK_TAGS = ("p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "table", "tr", "br", )  # fmt: skip
# Characters that render as nothing and can split a word or reverse a run of text. ZWJ, ZWNJ,
# and the LRM and RLM marks stay, because Persian, Arabic, and Indic text use them.
_INVISIBLE = re.compile("[\u00ad\u200b\u2060\ufeff\u202a-\u202e\u2066-\u2069]")


def _style(tag: Tag) -> dict[str, str]:
    """Read a tag's inline declarations, the last one winning for each property."""
    css = re.sub(r"/\*.*?\*/", "", str(tag.get("style", "")), flags=re.DOTALL)
    declarations = (part.partition(":") for part in css.split(";"))
    return {
        name.strip().lower(): value.strip().lower().removesuffix("!important").strip()
        for name, _, value in declarations
    }


def _zero(value: str | None) -> bool:
    """Tell whether a CSS number or length is zero, such as ``0``, ``.0``, or ``0px``."""
    number = re.fullmatch(r"(\d*\.?\d+)[a-z%]*", value or "")
    return number is not None and float(number[1]) == 0


def _hidden(tag: Tag) -> bool:
    if tag.has_attr("hidden"):
        return True
    style = _style(tag)
    if style.get("display") == "none" or _zero(style.get("opacity")):
        return True
    # Visibility and font size inherit, and a descendant that sets either one again can show its
    # text, so the element then stays.
    inherited = set()
    if style.get("visibility") in ("hidden", "collapse"):
        inherited.add("visibility")
    if _zero(style.get("font-size")):
        inherited.add("font-size")
    descendants = (_style(child) for child in tag.find_all(style=True))
    return bool(inherited) and not any(inherited & child.keys() for child in descendants)


def html_text(html: str) -> str:
    """
    Extract the text a reader sees from an HTML fragment.

    Block tags become line breaks. Inline tags join without spaces. Style and script bodies,
    elements hidden by the ``hidden`` attribute or an inline style, invisible characters, and empty
    lines are omitted. A stylesheet's classes are not resolved, so an element they hide stays.
    """
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(("style", "script")):
        tag.decompose()
    for tag in soup.find_all(_hidden):
        tag.decompose()
    for tag in soup.find_all(_BLOCK_TAGS):
        tag.insert_before("\n")
        tag.insert_after("\n")
    for cell in soup.find_all(("td", "th")):
        cell.insert_after(" ")
    text = _INVISIBLE.sub("", soup.get_text())
    lines = (" ".join(line.split()) for line in text.split("\n"))
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
    Map each argument after the fetcher to its ``Annotated`` kind, help, and default.

    The mapping keeps the signature's order.

    Raises:
        TypeError: An argument is not ``Annotated[kind, help]`` with a supported kind and nonblank
            help, or a boolean option has a default other than ``False``.
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
        # A request carries a number as text, which Python refuses past 4,300 digits by default.
        if isinstance(value, int):
            try:
                str(value)
            except ValueError:
                raise ValueError(f"{name} has too many digits to send in a request") from None
        minimum = _MINIMUMS.get(name)
        if minimum is not None and isinstance(value, int) and value < minimum:
            raise ValueError(f"{name} ({value}) must be at least {minimum}")
        # A required text, such as a lookup's name or a board, names what to read,
        # so a blank one asks for nothing.
        required = option.default is inspect.Parameter.empty
        if required and isinstance(value, str) and not value.strip():
            raise ValueError(f"{name} is blank. Pass the {option.help}")
        # A blank list entry names nothing either.
        if isinstance(value, list) and not all(item.strip() for item in value):
            raise ValueError(f"{name} holds a blank entry. Pass the {option.help}")


# A site's own rules for its options: it takes every option, defaults included, as a keyword and
# raises ValueError for a value the site cannot use.
type Validator = Callable[..., None]


class Checked[**P, R]:
    """
    A site function that checks every call against its annotations and its site's rules first.

    The signature is read once, at decoration, so a site function that breaks the rules of
    ``site_options`` fails when its module is imported. Error messages name the site after its
    module below ``jobrake.sites``.
    """

    def __init__(
        self, function: Callable[P, Awaitable[R]], validator: Validator | None = None
    ) -> None:
        functools.update_wrapper(self, function)
        # inspect reports a callable instance as sync, which misleads a caller dispatching on it.
        inspect.markcoroutinefunction(self)
        self._function = function
        self._validator = validator
        self._signature = inspect.signature(function)
        self._options = site_options(function)
        self._site = function.__module__.removeprefix("jobrake.sites.").partition(".")[0]

    async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        self._verify(*args, **kwargs)
        return await self._function(*args, **kwargs)

    def check(self, **options: object) -> None:
        """
        Raise what a call with these options would raise before its first request, without calling.

        Raises:
            TypeError: An option is unknown, missing, or of the wrong type.
            ValueError: ``results``, ``radius``, or ``max_age_hours`` is below its minimum,
                a required string or a list entry is blank, or the site's rules refuse a value.
        """
        self._verify(None, **options)

    def _verify(self, *args: object, **kwargs: object) -> None:
        try:
            bound = self._signature.bind(*args, **kwargs)
        except TypeError as error:
            names = [name for name, option in self._options.items() if not option.positional]
            listing = f"Its options are {', '.join(names)}" if names else "It takes no options"
            raise TypeError(f"{self._site}: {error}. {listing}") from None
        bound.apply_defaults()
        _, *given = bound.arguments.items()
        values = dict(given)
        _check(self._options, values)
        if self._validator is not None:
            self._validator(**values)


@overload
def checked[**P, R](function: Callable[P, Awaitable[R]], /) -> Checked[P, R]: ...
@overload
def checked[**P, R](
    *, validator: Validator
) -> Callable[[Callable[P, Awaitable[R]]], Checked[P, R]]: ...
def checked[**P, R](
    function: Callable[P, Awaitable[R]] | None = None, /, *, validator: Validator | None = None
) -> Checked[P, R] | Callable[[Callable[P, Awaitable[R]]], Checked[P, R]]:
    """Make a site function ``Checked``, as ``@checked`` or with its site's rules."""
    if function is None:
        return functools.partial(Checked, validator=validator)
    return Checked(function)


def menu_codes(
    site: str, option: str, menu: Mapping[str, str] | Collection[str], values: list[str] | None
) -> list[str]:
    """
    Return the code of each value in a site's menu, matched by its code or its label in any case.

    ``menu`` maps each code to its label, or holds the codes alone when only a code matches.
    Space around a value is ignored.

    Raises:
        ValueError: A value names no entry. The message lists the codes in the menu's order.
    """
    pairs = menu.items() if isinstance(menu, Mapping) else ((code, code) for code in menu)
    spellings = {key.casefold(): code for code, label in pairs for key in (code, label)}
    codes = []
    for value in values or []:
        if (code := spellings.get(value.strip().casefold())) is None:
            raise ValueError(f"unknown {site} {option} {value!r}. Use one of {', '.join(menu)}")
        codes.append(code)
    return codes


def report_progress(logger: logging.Logger, label: str, done: int, total: int) -> None:
    """Log ``label done/total`` as an INFO progress record, with ``done`` capped at ``total``."""
    # A search page can carry cards past the result limit.
    done = min(done, total)
    logger.info("%s %d/%d", label, done, total, extra={"progress": (done, total)})


def finite(value: object) -> float | None:
    """Return a JSON number that fits a record field, or None for anything else."""
    # json.loads admits NaN and the infinities, which strict JSON output forbids,
    # and bool is an int subclass.
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        return value if math.isfinite(value) else None
    except OverflowError:
        # An integer beyond float range is no usable field value.
        return None


def well_formed(value: Any) -> Any:  # noqa: ANN401  any JSON value
    """
    Return a JSON value with each lone surrogate in its text replaced by U+FFFD.

    JSON can carry half of a surrogate pair as an escape, and UTF-8 cannot encode it.
    """
    if isinstance(value, str):
        return value.encode("utf-16", "surrogatepass").decode("utf-16", "replace")
    if isinstance(value, list):
        return [well_formed(item) for item in value]
    if isinstance(value, dict):
        return {well_formed(key): well_formed(item) for key, item in value.items()}
    return value


def split_url(text: str) -> SplitResult:
    """
    Split stripped text as ``urlsplit`` does, or return an empty split for text it refuses.

    ``urlsplit`` raises ``ValueError`` for text such as an unbalanced bracket, so a caller that
    checks the parts raises its own message, which names a next step.
    """
    try:
        return urlsplit(text.strip())
    except ValueError:
        return SplitResult("", "", "", "", "")


# One label of a host name: RFC 1035, sections 2.3.1 and 2.3.4, as RFC 1123, section 2.1, lets it
# start with a digit (checked 2026-11-21).
HOST_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"


def on_domain(parts: SplitResult, domain: str) -> bool:
    """Tell whether a URL is on ``domain`` or a subdomain, with no credentials and no port but 443."""
    try:
        port = parts.port
    except ValueError:  # a port that is not a number in range
        return False
    host = re.compile(rf"(?:{HOST_LABEL}\.)*{re.escape(domain)}")
    return (
        "@" not in parts.netloc
        and port in (None, 443)
        and bool(host.fullmatch(parts.hostname or ""))
    )


def as_str(value: object) -> str | None:
    """Return a JSON value when it is a string, made well-formed, or None for anything else."""
    return well_formed(value) if isinstance(value, str) else None


def as_dict(value: object) -> dict[str, Any]:
    """Return a JSON object unchanged, or ``{}`` for any other value, so a ``.get`` can follow."""
    return value if isinstance(value, dict) else {}


def as_int(value: object) -> int | None:
    """Return a JSON integer, or None for anything else, ``true`` and ``false`` included."""
    # bool is an int subclass, so a bare isinstance check reads true as 1.
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def as_list(value: object) -> list[Any]:
    """Return a JSON array unchanged, or ``[]`` for any other value, so a loop can follow."""
    return value if isinstance(value, list) else []


def iso_date(value: object) -> str | None:
    """
    Reduce an ISO 8601 date or timestamp to its calendar date.

    Any value that ``datetime.fromisoformat`` cannot read, an ordinal date among them, gives
    ``None``.
    """
    if isinstance(value, str):
        with suppress(ValueError):
            return datetime.fromisoformat(value).date().isoformat()
    return None


def cutoff(max_age_hours: int | None) -> datetime | None:
    """
    Return the UTC moment ``max_age_hours`` before now, the earliest a posting may date from.

    Return ``None`` for no age, or for one that reaches back before the year 1, as neither
    excludes a posting.
    """
    if max_age_hours is None:
        return None
    try:
        return datetime.now(UTC) - timedelta(hours=max_age_hours)
    except OverflowError:
        return None


def epoch_ms_to_iso(ms: object) -> str | None:
    """
    Convert a site's epoch milliseconds to an ISO 8601 UTC timestamp.

    ``None`` returns ``None``. A value that is no number, is out of range, or resolves before the
    year 2000, as epoch seconds do, logs a warning and returns ``None``.
    """
    if ms is None:
        return None
    number = finite(ms)
    try:
        stamp = datetime.fromtimestamp(number / 1000.0, tz=UTC) if number is not None else None
    except ValueError, OSError, OverflowError:
        stamp = None
    if stamp is None:
        logger.warning("not epoch milliseconds: %r", ms)
        return None
    if stamp.year < 2000:
        logger.warning(
            "%r resolves before 2000, so it looks like epoch seconds rather than milliseconds", ms
        )
        return None
    return stamp.isoformat()
