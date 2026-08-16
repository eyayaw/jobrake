"""Paging the GraphQL job search."""

import json
import logging
import re

from jobrake import defaults
from jobrake.fetchkit import PostFetcher
from jobrake.models import employment_type, make_job
from jobrake.utils import epoch_ms_to_iso, html_text

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


def parse_jobs(data: dict, base_url: str) -> tuple[list[dict], str | None]:
    """(jobs, next cursor) from one GraphQL response."""
    search = data["data"]["jobSearch"]
    jobs = []
    for result in search["results"]:
        job = result["job"]
        loc = job.get("location") or {}
        location = ", ".join(
            part
            for part in (loc.get("city"), loc.get("admin1Code"), loc.get("countryCode"))
            if part
        )
        employer = job.get("employer") or {}
        compensation = job.get("compensation") or {}
        salary = compensation.get("baseSalary") or {}
        amount = salary.get("range") or {}
        exactly = amount.get("value")
        labels = [attribute["label"] for attribute in job.get("attributes") or []]
        company_page = employer.get("relativeCompanyPageUrl")
        jobs.append(
            make_job(
                site="indeed",
                id=job["key"],
                url=f"{base_url}/viewjob?jk={job['key']}",
                title=job.get("title", ""),
                company=employer.get("name") or "",
                location=location,
                description=_scrub_css(html_text((job.get("description") or {}).get("html", ""))),
                posted_at=_timestamp(job, "datePublished"),
                expires_at=_timestamp(job, "expirationDate"),
                company_url=base_url + company_page if company_page else None,
                company_logo=((employer.get("dossier") or {}).get("images") or {}).get(
                    "squareLogoUrl"
                ),
                employment_type=next(
                    (employment_type(label) for label in labels if label in EMPLOYMENT_TYPES),
                    None,
                ),
                # A Remote tag proves remote; absence proves nothing, so the field stays None.
                is_remote=True if "Remote" in labels else None,
                salary_min=amount.get("min", exactly),
                salary_max=amount.get("max", exactly),
                salary_currency=compensation.get("currencyCode"),
                salary_period=salary.get("unitOfWork"),
                city=loc.get("city"),
                region=loc.get("admin1Code"),
                country_code=loc.get("countryCode"),
                latitude=loc.get("latitude"),
                longitude=loc.get("longitude"),
                apply_url=(job.get("recruit") or {}).get("viewJobUrl"),
            )
        )
    return jobs, search["pageInfo"].get("nextCursor")


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

    This API answers POST alone, hence the ``PostFetcher``. An error result
    or a malformed page ends the search with whatever was collected.

    ``detail`` and ``cache`` are accepted and ignored: every field arrives
    in the search response, and nothing costs an extra request.
    """
    subdomain, api_code = indeed_domain(country)
    base_url = f"https://{subdomain}.indeed.com"
    headers = {**API_HEADERS, "indeed-co": api_code}

    jobs: list[dict] = []
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
        jobs.extend(page)
        if not cursor:
            break
    return jobs[:results_wanted]
