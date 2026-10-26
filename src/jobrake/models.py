"""Normalized job fields shared by the site adapters, and ``Stopped``."""

import re
from typing import Any, NotRequired, TypedDict, cast

from jobrake.utils import iso_date


class JobDict(TypedDict):
    """
    A posting from any site, under shared field names.

    Identity and summary keys are always present, and a summary value the
    site lacks is ``None``. A detail key appears only when it has a value.
    ``id`` is the site's own identifier, so ``(site, id)`` is unique. ``date``
    is a calendar date, and ``is_remote`` is ``True`` only when confirmed.
    """

    site: str
    id: str
    url: str
    title: str | None
    company: str | None
    location: str | None
    date: str | None
    description: NotRequired[str]
    language: NotRequired[str]
    company_url: NotRequired[str]
    company_logo: NotRequired[str]
    employment_type: NotRequired[str]
    is_remote: NotRequired[bool]
    salary_min: NotRequired[float]
    salary_max: NotRequired[float]
    salary_currency: NotRequired[str]
    salary_period: NotRequired[str]
    city: NotRequired[str]
    region: NotRequired[str]
    country_code: NotRequired[str]
    latitude: NotRequired[float]
    longitude: NotRequired[float]
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


def make_job(**fields: Any) -> JobDict:
    """
    Build a ``JobDict`` from a site's fields, normalizing their text.

    Identity strings are stripped. A blank or missing summary value becomes
    ``None``, and a blank or ``None`` detail value is left out. ``date`` keeps
    the calendar date of the given ``date``, falling back to ``posted_at``.

    Raises:
        TypeError: An identity field is missing, or a field is not a ``JobDict`` key.
    """
    if unknown := fields.keys() - set(JOB_FIELDS):
        raise TypeError(f"not a job field: {', '.join(sorted(unknown))}")
    if missing := [name for name in IDENTITY_FIELDS if name not in fields]:
        raise TypeError(f"missing job field: {', '.join(missing)}")
    job: dict[str, Any] = {name: (fields[name] or "").strip() for name in IDENTITY_FIELDS}
    for name in SUMMARY_FIELDS:
        value = fields.get(name)
        job[name] = (value.strip() or None) if isinstance(value, str) else None
    for name in DETAIL_FIELDS:
        value = fields.get(name)
        if isinstance(value, str):
            value = value.strip() or None
        if value is not None:
            job[name] = value
    # Prefer the search date. Fall back to the posting timestamp.
    job["date"] = iso_date(job["date"] or job.get("posted_at"))
    return cast(JobDict, job)


class Stopped(Exception):
    """
    A failed request ended a search or lookup early.

    ``partial`` holds the records collected before the failure, ``[]`` for a lookup.
    """

    def __init__(self, message: str, *, partial: list[JobDict]) -> None:
        super().__init__(message)
        self.partial = partial


# schema.org says CONTRACTOR and INTERN where the boards say Contract and Internship.
_EMPLOYMENT_ALIASES = {"contractor": "contract", "intern": "internship"}


def employment_type(label: str | None) -> str | None:
    """Normalize a site's employment label for the shared model."""
    if not label:
        return None
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return _EMPLOYMENT_ALIASES.get(slug, slug or None)
