"""Indeed GraphQL query construction, parsing, and pagination."""

import json
import logging
import math
import re
from gettext import ngettext

from jobrake import defaults
from jobrake.fetchkit import PostFetcher
from jobrake.models import employment_type, make_job
from jobrake.utils import (
    check_distance,
    check_hours_old,
    check_results_wanted,
    epoch_ms_to_iso,
    html_text,
)

from .client import API_HEADERS, API_URL
from .countries import indeed_domain

logger = logging.getLogger(__name__)

# jobspy's query, trimmed to the fields we keep. `limit: 100` sets the API
# page size and must stay identical on every request of a cursor chain:
# Indeed binds the size to its cursor and rejects a changed value with
# BAD_USER_INPUT. Pagination continues through pageInfo.nextCursor. The salary
# range is a union. Range carries both bounds, AtLeast and AtMost carry one,
# and Exactly carries one value.
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
# benefits. These labels pick them out. The headers pin the en-US locale.
EMPLOYMENT_TYPES = ("Full-time", "Part-time", "Contract", "Temporary", "Internship", "Per diem")


def build_query(
    search_term: str,
    location: str | None,
    distance: int | None,
    hours_old: int | None,
    cursor: str | None,
) -> str:
    """Build an Indeed query with a cursor-bound page size of 100."""
    filters = ""
    if hours_old:
        filters = f'filters: {{ date: {{ field: "dateOnIndeed", start: "{hours_old}h" }} }}'
    return QUERY.format(
        what=f"what: {json.dumps(search_term)}" if search_term else "",
        location=(
            f"location: {{ where: {json.dumps(location)}, "
            f"radius: {defaults.INDEED_RADIUS if distance is None else distance}, "
            f"radiusUnit: {defaults.INDEED_RADIUS_UNIT} }}"
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
    """Remove CSS rules flattened into some posting descriptions."""
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
    """Read an epoch-millisecond field, logging and dropping invalid values."""
    if (ms := job.get(field)) is None:
        return None
    try:
        return epoch_ms_to_iso(ms)
    except ValueError as e:
        # One posting's bad timestamp costs that field, not the page.
        logger.warning("job %s: %s", job["key"], e)
        return None


def _dict_value(value) -> dict:
    return value if isinstance(value, dict) else {}


def _string_value(value) -> str | None:
    return value if isinstance(value, str) else None


def _finite_value(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        return value if math.isfinite(value) else None
    except OverflowError:
        # An integer beyond float range is no usable field value.
        return None


def _parse_job(job: dict, base_url: str) -> dict:
    """Normalize one Indeed result into the shared job model."""
    key = job["key"].strip() if isinstance(job["key"], str) else ""
    # The provider key becomes both the job ID and the URL's ``jk`` parameter.
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


def _graphql_error_message(payload: object) -> str | None:
    """Read the first string message from a GraphQL error envelope."""
    errors = payload.get("errors") if isinstance(payload, dict) else None
    for error in errors if isinstance(errors, list) else []:
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"]
    return None


def parse_jobs(data: dict, base_url: str) -> tuple[list[dict], str | None, int]:
    """
    Parse one GraphQL page while isolating malformed results.

    ``base_url`` supplies the origin for posting and company links.

    Returns:
        Parsed jobs, a usable next cursor, and the provider's raw result count.
        The raw count includes malformed results so pagination still advances.

    Raises:
        KeyError: The response lacks required search data.
        TypeError: The response envelope has an unreadable shape.
    """
    search = data["data"]["jobSearch"]
    results = search["results"]
    jobs = []
    for result in results:
        try:
            jobs.append(_parse_job(result["job"], base_url))
        except (KeyError, TypeError, AttributeError) as error:
            # Skip the malformed result and keep parsing its siblings.
            logger.warning("skipping malformed indeed result: %r", error)
    page_info = search.get("pageInfo")
    # Missing or invalid pagination metadata ends the search after this page.
    # Keep the jobs already parsed from it.
    cursor = page_info.get("nextCursor") if isinstance(page_info, dict) else None
    return jobs, cursor if isinstance(cursor, str) else None, len(results)


async def search(
    fetcher: PostFetcher,
    *,
    search_term: str,
    location: str | None = None,
    country: str,
    distance: int | None = defaults.INDEED_RADIUS,
    results_wanted: int = defaults.RESULTS_WANTED,
    hours_old: int | None = defaults.HOURS_OLD,
    detail: bool = defaults.DETAIL,
    cache: bool = defaults.CACHE,
) -> list[dict]:
    """
    Search one Indeed country edition through its GraphQL API.

    ``country`` selects the edition. Distance is measured in kilometers.
    ``None`` uses the standard radius. ``detail`` and ``cache`` are accepted
    for the common provider call but do not change Indeed searches. The caller
    retains ownership of ``fetcher``.

    Each request asks for 100 jobs in relevance order. The returned list keeps
    that order and trims the final page to ``results_wanted``. Requests are
    neither paced nor retried. A transport failure, provider error without
    usable data, or unreadable response ends the search with a warning and the
    jobs already collected. A malformed result costs only that result. An
    invalid field costs only that field.

    Raises:
        ValueError: The country is unknown or a numeric search argument is outside its valid range.
    """
    check_results_wanted(results_wanted)
    check_distance(distance)
    check_hours_old(hours_old)
    subdomain, api_code = indeed_domain(country)
    base_url = f"https://{subdomain}.indeed.com"
    headers = {**API_HEADERS, "indeed-co": api_code}
    logger.info("searching indeed for %r in %r", search_term, location or country)

    jobs: list[dict] = []
    seen: set[str] = set()
    cursors: set[str] = set()
    cursor: str | None = None
    while len(jobs) < results_wanted:
        query = build_query(search_term, location, distance, hours_old, cursor)
        result = await fetcher.post(API_URL, {"query": query}, headers=headers)
        if result.error:
            logger.warning(
                "indeed search stopped by %s; keeping the %s already collected",
                result.error.message,
                ngettext("%d job", "%d jobs", len(jobs)) % len(jobs),
            )
            break
        payload = None
        try:
            payload = json.loads(result.text)
            page, cursor, raw = parse_jobs(payload, base_url)
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            # A GraphQL error arrives as HTTP 200 with null data. Usable data
            # alongside errors parses above and is kept.
            if message := _graphql_error_message(payload):
                logger.warning(
                    "indeed search stopped by provider error (%s); keeping the %s "
                    "already collected",
                    message,
                    ngettext("%d job", "%d jobs", len(jobs)) % len(jobs),
                )
            else:
                logger.warning(
                    "indeed sent a response this version cannot read (%r), likely an "
                    "API change; keeping the %s already collected",
                    error,
                    ngettext("%d job", "%d jobs", len(jobs)) % len(jobs),
                )
            break
        # A page without results ends the search. A page whose results all
        # failed to parse costs only those results; its cursor still advances.
        if not raw:
            break
        for job in page:
            if job["id"] in seen:
                continue
            seen.add(job["id"])
            jobs.append(job)
        if not cursor or cursor in cursors:
            break
        cursors.add(cursor)
    jobs = jobs[:results_wanted]
    logger.info(
        "indeed search finished with %s", ngettext("%d job", "%d jobs", len(jobs)) % len(jobs)
    )
    return jobs
