"""The ``JobDict`` record every site returns, the helpers that build it, and ``Stopped``."""

import logging
import re
import reprlib  # repr refuses an integer past 4,300 digits, and reprlib shortens it
from typing import Any, Literal, NotRequired, TypedDict, cast, get_args

from jobrake.countries import alpha2
from jobrake.utils import as_int, as_str, finite, iso_date, well_formed

logger = logging.getLogger(__name__)

WorkplaceType = Literal["remote", "hybrid", "on_site"]
WORKPLACE_TYPES: tuple[WorkplaceType, ...] = get_args(WorkplaceType)


class Place(TypedDict, closed=True):
    """
    One place a posting names, with the parts the site gives for it.

    ``name`` is the site's label for the place, or its city, region, and country code joined when
    the site gives no label. ``country_code`` is an ISO 3166-1 alpha-2 code in upper case.
    Nothing is parsed out of a label.
    """

    name: str
    city: NotRequired[str]
    region: NotRequired[str]
    country_code: NotRequired[str]
    latitude: NotRequired[float]
    longitude: NotRequired[float]


class JobDict(TypedDict, closed=True):
    """
    A posting from any site, under shared field names.

    Identity and summary keys are always present. A summary value the site lacks is ``None``,
    and ``locations`` is ``[]`` when no place was extracted, which says nothing about whether the
    posting has one. A detail key appears only when it has a value. ``id`` is the site's own
    identifier, so ``(site, id)`` is unique. ``locations`` keeps the site's order.
    ``date`` is a calendar date. ``workplace_type`` appears only when the site states it,
    so its absence leaves the workplace unknown. ``site_data`` holds fields only the site named in
    ``site`` carries, under that site's own names, as JSON values.
    """

    site: str
    id: str
    url: str
    title: str | None
    company: str | None
    locations: list[Place]
    date: str | None
    description: NotRequired[str]
    language: NotRequired[str]
    company_url: NotRequired[str]
    company_logo: NotRequired[str]
    department: NotRequired[str]
    team: NotRequired[str]
    employment_type: NotRequired[str]
    workplace_type: NotRequired[WorkplaceType]
    salary_min: NotRequired[float]
    salary_max: NotRequired[float]
    salary_currency: NotRequired[str]
    salary_period: NotRequired[str]
    posted_at: NotRequired[str]
    expires_at: NotRequired[str]
    apply_url: NotRequired[str]
    apply_type: NotRequired[str]
    applicants: NotRequired[int]
    experience_months: NotRequired[int]
    education: NotRequired[str]
    keywords: NotRequired[list[str]]
    site_data: NotRequired[dict[str, Any]]


# The CSV writer uses JOB_FIELDS for its columns, in this order.
JOB_FIELDS = tuple(JobDict.__annotations__)
IDENTITY_FIELDS = ("site", "id", "url")
DETAIL_FIELDS = tuple(name for name in JOB_FIELDS if name in JobDict.__optional_keys__)
SUMMARY_FIELDS = tuple(name for name in JOB_FIELDS if name not in IDENTITY_FIELDS + DETAIL_FIELDS)
# What a scalar detail of each type must be, and the check of it.
_SCALARS = {
    str: ("a string", lambda value: isinstance(value, str)),
    float: ("a finite number", lambda value: finite(value) is not None),
    # An integer past float range is no usable field value, and past 4,300 digits Python cannot
    # write it as JSON, so the cache could not store the record.
    int: ("an integer in float range", lambda value: finite(as_int(value)) is not None),
}
# The details with a rule of their own: a menu, a structure, or a date _readable_date checks.
_OWN_RULES = ("workplace_type", "site_data", "keywords", "posted_at", "expires_at")
# Built at import, so a scalar detail of a type without a check fails as the module loads.
_SCALAR_CHECKS = {
    name: _SCALARS[get_args(JobDict.__annotations__[name])[0]]
    for name in DETAIL_FIELDS
    if name not in _OWN_RULES
}
_PLACE_TEXT = ("city", "region", "country_code")


def _place(entry: object) -> dict[str, Any]:
    """
    Normalize one place, leaving out a blank or malformed part.

    A place without a name is named from its city, region, and country code. An alpha-3
    ``country_code`` is converted to alpha-2, and anything that is not an assigned ISO 3166-1 code,
    such as a country name or ``ZZ``, is dropped. The result has no ``name`` when the place
    has neither a name nor a text part.

    Raises:
        TypeError: ``entry`` is not an object or has a key that is not a ``Place`` field.
    """
    if not isinstance(entry, dict):
        raise TypeError(f"a place must be an object, got {reprlib.repr(entry)}")
    if unknown := entry.keys() - Place.__annotations__.keys():
        raise TypeError(f"not a place field: {', '.join(sorted(unknown))}")
    parts: dict[str, Any] = {}
    for key in _PLACE_TEXT:
        text = (as_str(entry.get(key)) or "").strip()
        if key == "country_code":
            text = alpha2(text) or ""
        if text:
            parts[key] = text
    for key in ("latitude", "longitude"):
        if (number := finite(entry.get(key))) is not None:
            parts[key] = number
    name = (as_str(entry.get("name")) or "").strip()
    name = name or ", ".join(parts[key] for key in _PLACE_TEXT if key in parts)
    return {"name": name, **parts} if name else {}


def make_places(value: object) -> list[Place]:
    """
    Normalize a site's or a cache row's places, so that normalizing the result changes nothing.

    A place with neither a name nor a text part is left out, and a place equal to an earlier one
    once normalized appears once. Places that differ in any part stay separate,
    because a shared name alone does not make them one.

    Raises:
        TypeError: ``value`` is not a list, or a place is not an object or has a key that is not a
            ``Place`` field.
    """
    if value is None:
        return []
    if not isinstance(value, list):
        raise TypeError(f"job field locations must be a list, got {reprlib.repr(value)}")
    places: list[Place] = []
    for place in filter(None, map(_place, value)):
        if place not in places:
            places.append(cast(Place, place))
    return places


def _strict_json(value: object) -> object:
    """
    Replace each NaN, infinity, or integer past float range inside value with None.

    Strict JSON has no NaN or infinity, and Python cannot write an integer past 4,300 digits as
    JSON.
    """
    if isinstance(value, int | float) and not isinstance(value, bool) and finite(value) is None:
        return None
    if isinstance(value, dict):
        return {key: _strict_json(entry) for key, entry in value.items()}
    if isinstance(value, list):
        return [_strict_json(entry) for entry in value]
    return value


def _site_data(value: object) -> dict[str, Any] | None:
    """
    Return the site's own fields that have a value, or None if no field has one.

    A number that strict JSON cannot write becomes None and leaves the rest of its field in place.
    One example is the infinity that ``json.loads`` makes of ``1e400``.

    Raises:
        TypeError: ``value`` is not an object with text keys, so a cache row of another
            shape is a miss.
    """
    if value is None:
        return None
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise TypeError(
            f"job field site_data must be an object with text keys, got {reprlib.repr(value)}"
        )
    fields = {key: _strict_json(entry) for key, entry in value.items()}
    return {key: entry for key, entry in fields.items() if entry not in (None, "", [])} or None


def _keywords(value: object) -> list[str] | None:
    """
    Return the nonblank keywords, stripped, in the site's order, or None if there are none.

    Raises:
        TypeError: ``value`` is not a list of strings, so a cache row of another shape is a miss.
    """
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(entry, str) for entry in value):
        raise TypeError(f"job field keywords must be a list of strings, got {reprlib.repr(value)}")
    return [entry.strip() for entry in value if entry.strip()] or None


def _detail(name: str, value: object) -> object:
    """
    Normalize one detail value, or return None to leave its key out.

    A ``workplace_type`` text outside ``WORKPLACE_TYPES`` is left out.

    Raises:
        TypeError: A detail other than a date is not of its ``JobDict`` type, or ``site_data`` or
            ``keywords`` is malformed.
    """
    if isinstance(value, str):
        value = value.strip() or None
    if name == "workplace_type":
        if value is not None and not isinstance(value, str):
            raise TypeError(f"job field workplace_type must be a string, got {reprlib.repr(value)}")
        return value if value in WORKPLACE_TYPES else None
    if name == "site_data":
        return _site_data(value)
    if name == "keywords":
        return _keywords(value)
    if value is None or name not in _SCALAR_CHECKS:
        return value
    kind, fits = _SCALAR_CHECKS[name]
    if not fits(value):
        raise TypeError(f"job field {name} must be {kind}, got {reprlib.repr(value)}")
    return value


def _readable_date(name: str, value: object, url: str) -> object:
    """Return a date or timestamp ``iso_date`` reads as given, or None after a warning naming it."""
    if value is None or iso_date(value):
        return value
    logger.warning(
        "%s %r of %s is not an ISO 8601 date or timestamp jobrake reads", name, value, url
    )
    return None


def make_job(**fields: Any) -> JobDict:
    """
    Build a ``JobDict`` from a site's fields, normalizing their text.

    Identity strings are stripped. A blank or missing summary value becomes ``None``,
    a missing ``locations`` becomes ``[]``, and a blank or ``None`` detail value is left out.
    ``date`` keeps the calendar date of the given ``date``, falling back to ``posted_at`` when
    ``date`` is missing, not text, or unreadable, and is ``None`` when neither gives one.
    Text in ``date``, or any ``posted_at`` or ``expires_at``, that ``iso_date`` cannot read logs a
    warning that names the field and the posting's URL, and such a ``posted_at`` or ``expires_at``
    is left out.
    A lone surrogate, which JSON can carry as an escape and UTF-8 cannot encode, becomes U+FFFD.

    Raises:
        TypeError: An identity field is missing, blank, or not a string, a field is not a
            ``JobDict`` key, a detail other than a date is not of its ``JobDict`` type, such as
            ``applicants`` given as text or ``salary_min`` as NaN, or ``locations``,
            ``site_data``, or ``keywords`` is malformed.
    """
    if unknown := fields.keys() - set(JOB_FIELDS):
        raise TypeError(f"not a job field: {', '.join(sorted(unknown))}")
    fields = well_formed(fields)
    job: dict[str, Any] = {}
    for name in IDENTITY_FIELDS:
        value = fields.get(name)
        if not isinstance(value, str) or not value.strip():
            raise TypeError(
                f"job field {name} must be a nonblank string, got {reprlib.repr(value)}"
            )
        job[name] = value.strip()
    for name in SUMMARY_FIELDS:
        value = fields.get(name)
        if name == "locations":
            job[name] = make_places(value)
        else:
            job[name] = (value.strip() or None) if isinstance(value, str) else None
    job["date"] = _readable_date("date", job["date"], job["url"])
    for name in DETAIL_FIELDS:
        value = _detail(name, fields.get(name))
        if name in ("posted_at", "expires_at"):
            value = _readable_date(name, value, job["url"])
        if value is not None:
            job[name] = value
    job["date"] = iso_date(job["date"]) or iso_date(job.get("posted_at"))
    return cast(JobDict, job)


class Stopped(Exception):
    """
    A search or lookup that could not finish.

    A request failed, the site reported an error or has no such board, its response could not be
    read, a page ended a search short of the total the site reported, or a posting's details could
    not be fetched. ``partial`` holds the records the call collected, ``[]`` when there are none.
    After a failed details fetch it holds every card, filled where its posting was read, and
    ``failed`` holds the URLs of the unread postings, for the site's ``postings`` to retry.
    ``failed`` is ``[]`` after any other stop.
    """

    def __init__(
        self, message: str, *, partial: list[JobDict] | None = None, failed: list[str] | None = None
    ) -> None:
        super().__init__(message)
        self.partial = partial or []
        self.failed = failed or []


# schema.org says CONTRACTOR and INTERN, and Ashby says Intern, where the other boards say Contract
# and Internship.
_EMPLOYMENT_ALIASES = {"contractor": "contract", "intern": "internship"}


def _slug(label: str | None) -> str | None:
    """Return a site's label as a snake_case slug such as ``full_time``, or None for no label."""
    if not label:
        return None
    # A camelCase label, such as Ashby's FullTime, splits before a capital that follows a lowercase
    # letter or digit.
    words = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", label)
    return re.sub(r"[^a-z0-9]+", "_", words.lower()).strip("_") or None


def employment_type(label: str | None) -> str | None:
    """Return a site's employment label as a snake_case slug such as ``full_time``, or None."""
    slug = _slug(label)
    return _EMPLOYMENT_ALIASES.get(slug, slug) if slug else None


# Lever's API sends onsite, where https://github.com/lever/postings-api lists on-site (Spotify's
# board, 2026-11-14).
_WORKPLACE_ALIASES = {"onsite": "on_site"}


def workplace_type(label: str | None) -> WorkplaceType | None:
    """
    Return a site's workplace label as ``remote``, ``hybrid``, or ``on_site``.

    Ashby's ``OnSite`` and Lever's ``onsite`` both read as ``on_site``. Any other label gives None.
    """
    slug = _slug(label)
    slug = _WORKPLACE_ALIASES.get(slug, slug)
    return next((kind for kind in WORKPLACE_TYPES if kind == slug), None)
