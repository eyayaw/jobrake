"""Normalized job fields shared by the site adapters, and ``Stopped``."""

import functools
import re
from typing import Any, Literal, NotRequired, TypedDict, cast, get_args

from jobrake.utils import as_str, finite, iso_date

WorkplaceType = Literal["remote", "hybrid", "on_site"]
WORKPLACE_TYPES: tuple[WorkplaceType, ...] = get_args(WorkplaceType)


class Place(TypedDict, closed=True):
    """
    One place a posting names, with the parts the site gives for it.

    ``name`` is the site's label for the place, or its city, region, and
    country code joined when the site gives no label. ``country_code`` is two
    uppercase letters in the form of an ISO 3166-1 alpha-2 code. ``make_places``
    checks the form only, so an unassigned code such as ``ZZ`` stays. Nothing
    is parsed out of a label.
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

    Identity and summary keys are always present. A summary value the site
    lacks is ``None``, and ``locations`` is ``[]`` when no place was
    extracted, which says nothing about whether the posting has one. A
    detail key appears only when it has a value. ``id`` is the site's own
    identifier, so ``(site, id)`` is unique. ``locations`` keeps the site's
    order. ``date`` is a calendar date. ``workplace_type`` appears only
    when the site states it, so its absence leaves the workplace unknown.
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


# The CSV writer uses JOB_FIELDS for its columns, in this order.
JOB_FIELDS = tuple(JobDict.__annotations__)
IDENTITY_FIELDS = ("site", "id", "url")
DETAIL_FIELDS = tuple(name for name in JOB_FIELDS if name in JobDict.__optional_keys__)
SUMMARY_FIELDS = tuple(name for name in JOB_FIELDS if name not in IDENTITY_FIELDS + DETAIL_FIELDS)
_PLACE_TEXT = ("city", "region", "country_code")
_ALPHA2 = re.compile(r"[A-Za-z]{2}")


def _place(entry: object) -> dict[str, Any]:
    """
    Normalize one place, leaving out a blank or malformed part and naming it from its parts when it has no name.

    A ``country_code`` that is not two letters, such as a country name, is
    left out. The result has no ``name`` when the place has neither a name
    nor a text part.

    Raises:
        TypeError: ``entry`` is not an object or has a key that is not a ``Place`` field.
    """
    if not isinstance(entry, dict):
        raise TypeError(f"a place must be an object, got {entry!r}")
    if unknown := entry.keys() - Place.__annotations__.keys():
        raise TypeError(f"not a place field: {', '.join(sorted(unknown))}")
    parts: dict[str, Any] = {}
    for key in _PLACE_TEXT:
        text = (as_str(entry.get(key)) or "").strip()
        if key == "country_code":
            text = text.upper() if _ALPHA2.fullmatch(text) else ""
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

    A place with neither a name nor a text part is left out, and a place equal
    to an earlier one once normalized appears once. Places that differ in any
    part stay separate, because a shared name alone does not make them one.

    Raises:
        TypeError: ``value`` is not a list, or a place is not an object or
            has a key that is not a ``Place`` field.
    """
    if value is None:
        return []
    if not isinstance(value, list):
        raise TypeError(f"job field locations must be a list, got {value!r}")
    places: list[Place] = []
    for place in filter(None, map(_place, value)):
        if place not in places:
            places.append(cast(Place, place))
    return places


def make_job(**fields: Any) -> JobDict:
    """
    Build a ``JobDict`` from a site's fields, normalizing their text.

    Identity strings are stripped. A blank or missing summary value becomes
    ``None``, a missing ``locations`` becomes ``[]``, and a blank or ``None``
    detail value is left out. ``date`` keeps the calendar date of the given
    ``date``, falling back to ``posted_at``.

    Raises:
        TypeError: An identity field is missing, blank, or not a string, a
            field is not a ``JobDict`` key, or ``locations`` is malformed.
    """
    if unknown := fields.keys() - set(JOB_FIELDS):
        raise TypeError(f"not a job field: {', '.join(sorted(unknown))}")
    job: dict[str, Any] = {}
    for name in IDENTITY_FIELDS:
        value = fields.get(name)
        if not isinstance(value, str) or not value.strip():
            raise TypeError(f"job field {name} must be a nonblank string, got {value!r}")
        job[name] = value.strip()
    for name in SUMMARY_FIELDS:
        value = fields.get(name)
        if name == "locations":
            job[name] = make_places(value)
        else:
            job[name] = (value.strip() or None) if isinstance(value, str) else None
    for name in DETAIL_FIELDS:
        value = fields.get(name)
        if isinstance(value, str):
            value = value.strip() or None
        if name == "workplace_type" and value not in WORKPLACE_TYPES:
            value = None
        if value is not None:
            job[name] = value
    # Prefer the search date. Fall back to the posting timestamp.
    job["date"] = iso_date(job["date"] or job.get("posted_at"))
    return cast(JobDict, job)


class Stopped(Exception):
    """
    A failed request, or a page that ended a search short of the total the site reported, cut it short.

    ``partial`` holds the records collected before the failure, ``[]`` for a lookup.
    """

    def __init__(self, message: str, *, partial: list[JobDict]) -> None:
        super().__init__(message)
        self.partial = partial

    def __reduce__(self) -> tuple[Any, ...]:
        # Unpickling calls the class with args alone, which lack partial, so a
        # Stopped raised in a process-pool worker would break the pool.
        return functools.partial(type(self), partial=self.partial), self.args, self.__dict__


# schema.org says CONTRACTOR and INTERN, and Ashby says Intern, where the
# other boards say Contract and Internship.
_EMPLOYMENT_ALIASES = {"contractor": "contract", "intern": "internship"}


def _slug(label: str | None) -> str | None:
    """Return a site's label as a snake_case slug such as ``full_time``, or None for no label."""
    if not label:
        return None
    # A camelCase label, such as Ashby's FullTime, splits before a capital that follows a lowercase letter or digit.
    words = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", label)
    return re.sub(r"[^a-z0-9]+", "_", words.lower()).strip("_") or None


def employment_type(label: str | None) -> str | None:
    """Return a site's employment label as a snake_case slug such as ``full_time``, or None."""
    slug = _slug(label)
    return _EMPLOYMENT_ALIASES.get(slug, slug) if slug else None


def workplace_type(label: str | None) -> WorkplaceType | None:
    """Return a site's workplace label, such as Ashby's ``OnSite`` or Lever's ``on-site``, as ``remote``, ``hybrid``, or ``on_site``, or None for any other label."""
    slug = _slug(label)
    return next((kind for kind in WORKPLACE_TYPES if kind == slug), None)
