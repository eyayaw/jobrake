"""The data model for job postings: the same fields from every site."""

import re
from dataclasses import asdict, dataclass, fields

from jobrake.utils import iso_date

IDENTITY_FIELDS = ("site", "id", "url")
SUMMARY_FIELDS = ("title", "company", "location", "date")


@dataclass(kw_only=True, slots=True)
class Job:
    """
    Fields from a job posting, normalized across sites:
    a field means the same thing regardless of which site it came from.

    Three groups, by what is guaranteed.

    1. Identity: ``site``, ``id``, and ``url`` identify the job posting.
       ``id`` is the site's own identifier, stable but unique only within
       its site; ``(site, id)`` is unique globally.

    2. Summary: ``title``, ``company``, ``location``, and ``date`` are present
       in every job dict. Each value is ``None`` when unavailable.

    3. Detail: everything from ``description`` on—attributes a posting
       may contain, extracted when present. ``None`` means no value was
       found: the posting omitted it, the site never provides it, or the
       page was not fetched. The job dict omits those fields.
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
        # The search result's date wins; posted_at fills in when the site gave none.
        self.date = iso_date(self.date or self.posted_at)


def make_job(**scraped) -> dict:
    """
    Normalize scraped fields into the job dict.

    Identity and summary keys are always present. An unavailable summary value
    is ``None``. A detail key whose value is ``None`` is omitted.
    """
    job = asdict(Job(**scraped))
    return {
        name: value for name, value in job.items() if name not in DETAIL_FIELDS or value is not None
    }


# Derived, not declared, so the field lists can never drift from ``Job``.
# ``JOB_FIELDS`` lists every model field. The CSV writer uses it for columns.
JOB_FIELDS = tuple(f.name for f in fields(Job))
DETAIL_FIELDS = tuple(n for n in JOB_FIELDS if n not in IDENTITY_FIELDS + SUMMARY_FIELDS)

# schema.org says CONTRACTOR and INTERN where the boards say Contract and Internship.
_EMPLOYMENT_ALIASES = {"contractor": "contract", "intern": "internship"}


def employment_type(label: str | None) -> str | None:
    """A site's employment-type label in the unified form (``FULL_TIME`` -> ``full_time``)."""
    if not label:
        return None
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return _EMPLOYMENT_ALIASES.get(slug, slug or None)
