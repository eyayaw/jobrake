"""Normalized job fields shared by the provider adapters."""

import re
from dataclasses import asdict, dataclass, fields

from jobrake.utils import iso_date

IDENTITY_FIELDS = ("site", "id", "url")
SUMMARY_FIELDS = ("title", "company", "location", "date")


@dataclass(kw_only=True, slots=True)
class Job:
    """
    A provider posting normalized to shared field names.

    Identity strings are stripped. Blank summary and detail strings become
    ``None``. ``date`` prefers the search result's date and falls back to the
    calendar date in ``posted_at``.

    Attributes:
        id: Provider-owned identifier. The pair ``(site, id)`` is globally unique.
        date: Posting date without a time component.
        is_remote: ``True`` when confirmed remote and ``None`` when unknown.
    """

    # Identity ----
    site: str
    id: str
    url: str
    # Summary ----
    title: str | None
    company: str | None
    location: str | None
    date: str | None = None
    # Detail ----
    description: str | None = None
    company_url: str | None = None
    company_logo: str | None = None
    employment_type: str | None = None
    is_remote: bool | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    city: str | None = None
    region: str | None = None
    country_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    posted_at: str | None = None
    expires_at: str | None = None
    apply_url: str | None = None
    apply_type: str | None = None
    applicants: int | None = None
    experience_months: int | None = None
    education: str | None = None

    def __post_init__(self):
        """Normalize strings and derive the calendar date."""
        for name in IDENTITY_FIELDS:
            setattr(self, name, (getattr(self, name) or "").strip())
        for name in SUMMARY_FIELDS:
            value = getattr(self, name)
            value = value.strip() if isinstance(value, str) else None
            setattr(self, name, value or None)
        for name in DETAIL_FIELDS:
            value = getattr(self, name)
            if isinstance(value, str):
                setattr(self, name, value.strip() or None)
        # Prefer the search date. Fall back to the posting timestamp.
        self.date = iso_date(self.date or self.posted_at)


def make_job(**scraped) -> dict:
    """
    Build the public job dictionary from provider fields.

    Identity and summary keys are always present. An unavailable summary value
    is ``None``. A detail key whose value is ``None`` is omitted.

    Raises:
        TypeError: A required field is missing or an unknown field is supplied.
    """
    job = asdict(Job(**scraped))
    return {
        name: value for name, value in job.items() if name not in DETAIL_FIELDS or value is not None
    }


# Derive the field lists from ``Job`` so they stay in sync.
# The CSV writer uses ``JOB_FIELDS`` for its columns.
JOB_FIELDS = tuple(f.name for f in fields(Job))
DETAIL_FIELDS = tuple(n for n in JOB_FIELDS if n not in IDENTITY_FIELDS + SUMMARY_FIELDS)

# schema.org says CONTRACTOR and INTERN where the boards say Contract and Internship.
_EMPLOYMENT_ALIASES = {"contractor": "contract", "intern": "internship"}


def employment_type(label: str | None) -> str | None:
    """Normalize a provider's employment label for the shared model."""
    if not label:
        return None
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return _EMPLOYMENT_ALIASES.get(slug, slug or None)
