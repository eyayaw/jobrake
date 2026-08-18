"""Paging the GraphQL job search."""

import json
import logging
import math
import re

from jobrake import defaults
from jobrake.fetchkit import PostFetcher
from jobrake.models import employment_type, make_job
from jobrake.utils import check_hours_old, epoch_ms_to_iso, html_text

from .client import API_HEADERS, API_URL
from .countries import indeed_domain

logger = logging.getLogger(__name__)

# jobspy's query, trimmed to the fields we keep. `limit: 100` is the API's
# page size; pagination continues via pageInfo.nextCursor. The salary range
# is a union type, hence the inline fragments: Range carries both bounds,
# AtLeast/AtMost one, Exactly a value.
QUERY = """
query GetJobData {{
  jobSearch(
    {what}
    {location}
    limit: 100
    {cursor}
    sort: RELEVANCE
    {filters}
  ) {{
    pageInfo {{ nextCursor }}
    results {{
      job {{
        key
        title
        datePublished
        expirationDate
        description {{ html }}
        location {{ city admin1Code countryCode latitude longitude }}
        employer {{
          name
          relativeCompanyPageUrl
          dossier {{ images {{ squareLogoUrl }} }}
        }}
        recruit {{ viewJobUrl }}
        compensation {{
          baseSalary {{
            unitOfWork
            range {{
              ... on Range {{ min max }}
              ... on AtLeast {{ min }}
              ... on AtMost {{ max }}
              ... on Exactly {{ value }}
            }}
          }}
          currencyCode
        }}
        attributes {{ label }}
      }}
    }}
  }}
}}
"""

# Indeed mixes employment types into the attributes bag with skills and
# benefits; these exact labels pick them out. Stable, since the headers pin
# the en-US locale.
EMPLOYMENT_TYPES = ("Full-time", "Part-time", "Contract", "Temporary", "Internship", "Per diem")


def build_query(
    search_term: str,
    location: str | None,
    distance: int | None,
    hours_old: int | None,
    cursor: str | None,
) -> str:
    filters = ""
    if hours_old:
        filters = f'filters: {{ date: {{ field: "dateOnIndeed", start: "{hours_old}h" }} }}'
    return QUERY.format(
        what=f"what: {json.dumps(search_term)}" if search_term else "",
        location=(
            f"location: {{ where: {json.dumps(location)}, "
            f"radius: {defaults.RADIUS if distance is None else distance}, "
            f"radiusUnit: {defaults.RADIUS_UNIT} }}"
            if location
            else ""
        ),
        cursor=f"cursor: {json.dumps(cursor)}" if cursor else "",
        filters=filters,
    )


# Indeed's ingestion flattens some ATS pages' stylesheets into the description
# text, beyond the reach of tag-level cleanup. These match CSS rule syntax: a
# selector, then a {block} holding `property: value` (or nothing, once inner
# rules are gone). The selector may not cross a line break or a sentence
# period, keeping prose out of reach.
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_CSS_RULE = re.compile(r"(?:[^{}\n.]|\.(?!\s)){0,200}?\{(?:[^{}]*:[^{}]*|\s*)\}")


def _scrub_css(text: str) -> str:
    """Drop the stylesheet text some postings carry in their description."""
    if "{" not in text:
        return text
    text = _CSS_COMMENT.sub(" ", text)
    while True:
        # Innermost rules first, so nested @media blocks collapse over the passes.
        scrubbed = _CSS_RULE.sub(" ", text)
        if scrubbed == text:
            break
        text = scrubbed
    lines = (" ".join(line.split()) for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def _timestamp(job: dict, field: str) -> str | None:
    """The job's epoch-milliseconds field as an ISO timestamp; ``None`` if absent or bad."""
    if (ms := job.get(field)) is None:
        return None
    try:
        return epoch_ms_to_iso(ms)
    except ValueError as e:
        # One posting's bad timestamp costs that field, not the page.
        logger.warning("job %s: %s", job["key"], e)
        return None


def _dict_value(value) -> dict:
    """The value if it is a dict, else ``{}``."""
    return value if isinstance(value, dict) else {}


def _string_value(value) -> str | None:
    """The value if it is a string, else ``None``."""
    return value if isinstance(value, str) else None


def _finite_value(value) -> float | None:
    """The value if it is a finite number, else ``None``."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return value if math.isfinite(value) else None


def _parse_job(job: dict, base_url: str) -> dict:
    """
    Convert an Indeed job object into a unified job dict.

    The provider key must be a string containing non-whitespace text. It is
    stripped before use. Other fields are normalized to their model types.
    A value in the wrong shape is omitted.
    """
    key = job["key"].strip() if isinstance(job["key"], str) else ""
    # Require a nonempty provider key; the model would silently empty a falsy one.
    if not key:
        raise TypeError(f"job key {job['key']!r} is blank or not a string")
    loc = _dict_value(job.get("location"))
    city = _string_value(loc.get("city"))
    region = _string_value(loc.get("admin1Code"))
    country_code = _string_value(loc.get("countryCode"))
    employer = _dict_value(job.get("employer"))
    compensation = _dict_value(job.get("compensation"))
    salary = _dict_value(compensation.get("baseSalary"))
    amount = _dict_value(salary.get("range"))
    exactly = _finite_value(amount.get("value"))
    # Employment types share the attributes bag with skills and benefits.
    # Malformed entries, or a bag that is not a list, are ignored.
    attributes = job.get("attributes")
    labels = [
        attribute.get("label")
        for attribute in (attributes if isinstance(attributes, list) else [])
        if isinstance(attribute, dict) and isinstance(attribute.get("label"), str)
    ]
    company_page = _string_value(employer.get("relativeCompanyPageUrl"))
    dossier = _dict_value(employer.get("dossier"))
    images = _dict_value(dossier.get("images"))
    return make_job(
        site="indeed",
        id=key,
        url=f"{base_url}/viewjob?jk={key}",
        title=_string_value(job.get("title")),
        company=_string_value(employer.get("name")),
        location=", ".join(part for part in (city, region, country_code) if part) or None,
        description=_scrub_css(
            html_text(_string_value(_dict_value(job.get("description")).get("html")) or "")
        ),
        posted_at=_timestamp(job, "datePublished"),
        expires_at=_timestamp(job, "expirationDate"),
        company_url=base_url + company_page if company_page else None,
        company_logo=_string_value(images.get("squareLogoUrl")),
        employment_type=next(
            (employment_type(label) for label in labels if label in EMPLOYMENT_TYPES),
            None,
        ),
        # A Remote tag proves remote; absence proves nothing, so the field stays None.
        is_remote=True if "Remote" in labels else None,
        salary_min=_finite_value(amount.get("min", exactly)),
        salary_max=_finite_value(amount.get("max", exactly)),
        salary_currency=_string_value(compensation.get("currencyCode")),
        salary_period=_string_value(salary.get("unitOfWork")),
        city=city,
        region=region,
        country_code=country_code,
        latitude=_finite_value(loc.get("latitude")),
        longitude=_finite_value(loc.get("longitude")),
        apply_url=_string_value(_dict_value(job.get("recruit")).get("viewJobUrl")),
    )


def parse_jobs(data: dict, base_url: str) -> tuple[list[dict], str | None]:
    """(jobs, next cursor) from one GraphQL response."""
    search = data["data"]["jobSearch"]
    jobs = []
    for result in search["results"]:
        try:
            jobs.append(_parse_job(result["job"], base_url))
        except (KeyError, TypeError, AttributeError) as error:
            # Skip the malformed result and keep parsing its siblings.
            logger.warning("skipping malformed indeed result: %r", error)
    page_info = search.get("pageInfo")
    # Missing or invalid pagination metadata ends the search after the
    # current page; its parsed jobs still count.
    cursor = page_info.get("nextCursor") if isinstance(page_info, dict) else None
    return jobs, cursor if isinstance(cursor, str) else None


async def search(
    fetcher: PostFetcher,
    *,
    search_term: str,
    location: str | None = None,
    country: str,
    distance: int | None = defaults.RADIUS,
    results_wanted: int = defaults.RESULTS_WANTED,
    hours_old: int | None = None,
    detail: bool = True,
    cache: bool = True,
) -> list[dict]:
    """
    Page through the GraphQL API.

    This API answers POST alone, via ``PostFetcher``. An error result
    or a malformed response envelope ends the search with whatever was
    collected; a job without a usable key is skipped alone, and invalid
    field values are omitted.

    ``detail`` and ``cache`` are accepted and ignored: every field this
    adapter supports arrives in the search response, and nothing costs an
    extra request. A job from here omits the unsupported fields
    (``apply_type``, ``applicants``, ``experience_months``, ``education``).
    """
    check_hours_old(hours_old)
    subdomain, api_code = indeed_domain(country)
    base_url = f"https://{subdomain}.indeed.com"
    headers = {**API_HEADERS, "indeed-co": api_code}

    jobs: list[dict] = []
    seen: set[str] = set()
    cursors: set[str] = set()
    cursor: str | None = None
    while len(jobs) < results_wanted:
        query = build_query(search_term, location, distance, hours_old, cursor)
        result = await fetcher.post(API_URL, {"query": query}, headers=headers)
        if not result.ok:
            break
        try:
            page, cursor = parse_jobs(json.loads(result.text), base_url)
        except (json.JSONDecodeError, KeyError, TypeError):
            break
        if not page:
            break
        for job in page:
            if job["id"] in seen:
                continue
            seen.add(job["id"])
            jobs.append(job)
        if not cursor or cursor in cursors:
            break
        cursors.add(cursor)
    return jobs[:results_wanted]
