"""Indeed GraphQL query construction, parsing, and pagination."""

import json
import logging
import math
import re
from gettext import ngettext
from typing import Annotated, Any

from jobrake.fetchkit import Fetcher
from jobrake.models import JobDict, Stopped, employment_type, make_job
from jobrake.utils import checked, epoch_ms_to_iso, html_text

from .client import API_HEADERS, API_URL
from .countries import Country, indeed_domain

logger = logging.getLogger(__name__)

# jobspy's query, trimmed to the fields we keep. `limit: 100` sets the API
# page size and must stay identical on every request of a cursor chain:
# Indeed binds the size to its cursor and rejects a changed value with
# BAD_USER_INPUT. Pagination continues through pageInfo.nextCursor. The salary
# range is a union. Range carries both bounds, AtLeast and AtMost carry one,
# and Exactly carries one value.
#
# The API returns results newest first by dateOnIndeed under both RELEVANCE
# and DATE. DATE names that order, so it holds if the two ever diverge.
QUERY = """
query GetJobData {{
  jobSearch(
    {what}
    {location}
    limit: 100
    {cursor}
    sort: DATE
    {filters}
  ) {{
    pageInfo {{ nextCursor }}
    results {{
      job {{
        key
        title
        language
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

# Indeed ends a cursor chain after this many results.
MAX_RESULTS = 1000

# Indeed mixes employment types into the attributes bag with skills and
# benefits. These labels pick them out. The headers pin the en-US locale.
EMPLOYMENT_TYPES = ("Full-time", "Part-time", "Contract", "Temporary", "Internship", "Per diem")


def _build_query(
    query: str,
    location: str | None,
    radius: int,
    max_age_hours: int | None,
    cursor: str | None,
    *,
    company_ids: list[str] | None = None,
    remote: bool = False,
    language: str | None = None,
    attributes: list[str] | None = None,
) -> str:
    """Build an Indeed query with a cursor-bound page size of 100."""
    filters = []
    if max_age_hours:
        filters.append(f'{{ date: {{ field: "dateOnIndeed", start: "{max_age_hours}h" }} }}')
    if company_ids:
        keys = [company.strip() for company in company_ids]
        filters.append(
            '{ keyword: { field: "indeedEmployerKey", keys: ' + json.dumps(keys) + " } }"
        )
    attribute_keys = list(dict.fromkeys(code.strip() for code in attributes or []))
    if remote and "DSQF7" not in attribute_keys:
        # DSQF7 identifies Indeed's Remote attribute.
        attribute_keys.append("DSQF7")
    if attribute_keys:
        filters.append(
            '{ keyword: { field: "attributes", keys: ' + json.dumps(attribute_keys) + " } }"
        )
    if language is not None:
        filters.append(
            '{ keyword: { field: "language", keys: [' + json.dumps(language.lower()) + "] } }"
        )
    # Indeed requires date and keyword filters in separate objects.
    # Jobs must satisfy every filter in the list.
    return QUERY.format(
        what=f"what: {json.dumps(query)}" if query else "",
        location=(
            f"location: {{ where: {json.dumps(location)}, "
            f"radius: {radius}, radiusUnit: KILOMETERS }}"
            if location
            else ""
        ),
        cursor=f"cursor: {json.dumps(cursor)}" if cursor else "",
        filters="filters: [" + ", ".join(filters) + "]" if filters else "",
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


def _timestamp(job: dict[str, Any], field: str) -> str | None:
    """Read an epoch-millisecond field, logging and dropping invalid values."""
    if (ms := job.get(field)) is None:
        return None
    try:
        return epoch_ms_to_iso(ms)
    except ValueError as e:
        # One posting's bad timestamp costs that field, not the page.
        logger.warning("job %s: %s", job["key"], e)
        return None


def _dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_value(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _finite_value(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        return value if math.isfinite(value) else None
    except OverflowError:
        # An integer beyond float range is no usable field value.
        return None


def _parse_job(job: dict[str, Any], base_url: str) -> JobDict:
    """Normalize one Indeed result into the shared job model."""
    # Indeed's job key becomes both the job ID and the URL's ``jk`` parameter.
    key = (_string_value(job["key"]) or "").strip()
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
        language=_string_value(job.get("language")),
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


def _parse_jobs(data: dict[str, Any], base_url: str) -> tuple[list[JobDict], str | None, int]:
    """
    Parse one GraphQL page while isolating malformed results.

    ``base_url`` supplies the origin for posting and company links.

    Returns:
        Parsed jobs, a usable next cursor, and the count of results Indeed sent.
        The raw count includes malformed results so pagination still advances.

    Raises:
        KeyError: The response lacks required search data.
        TypeError: The response envelope has an unreadable shape.
    """
    search = data["data"]["jobSearch"]
    results = search["results"]
    if not isinstance(results, list):
        raise TypeError(f"results is a {type(results).__name__}, not a list")
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


def _check_filters(
    company_ids: list[str] | None, language: str | None, attributes: list[str] | None
) -> None:
    # Indeed intersects the employer keys it receives, so a search takes one.
    if len(company_ids or []) > 1:
        raise ValueError(
            "indeed takes one company ID per search. "
            "Search each company on its own and combine the results"
        )
    if any(not company.strip() for company in company_ids or []):
        raise ValueError(
            "company ID is blank. Find IDs with 'jobrake indeed companies NAME --country EDITION'"
        )
    if language is not None and re.fullmatch(r"[A-Za-z]{2}", language) is None:
        raise ValueError(
            f"language {language!r} must contain exactly two ASCII letters, such as 'en'"
        )
    if any(not code.strip() for code in attributes or []):
        raise ValueError(
            "attribute code is blank. Find codes with 'jobrake indeed attributes -c EDITION QUERY'"
        )


@checked
async def search(
    fetcher: Fetcher,
    *,
    query: Annotated[str, "job title or keywords"] = "",
    country: Country,
    location: Annotated[str | None, "city or area within the country"] = None,
    radius: Annotated[int, "search radius in kilometers"] = 40,
    results: Annotated[int, "maximum number of postings"] = 10,
    max_age_hours: Annotated[int | None, "maximum posting age in hours"] = None,
    company_ids: Annotated[list[str] | None, "Indeed company ID, one per search"] = None,
    remote: Annotated[bool, "only postings Indeed tags Remote"] = False,
    language: Annotated[str | None, "two-letter posting language code, e.g., en"] = None,
    attributes: Annotated[list[str] | None, "attribute codes a posting must all carry"] = None,
) -> list[JobDict]:
    """
    Search one Indeed country edition through its GraphQL API.

    ``country`` selects the edition, and ``location`` narrows it to a place within that edition.
    ``company_ids`` takes one employer key and keeps jobs at that employer, and ``attributes`` keeps postings carrying every listed code.
    Whitespace around the key and the codes is removed.
    ``remote=True`` adds Indeed's Remote attribute, ``"DSQF7"``, to those codes.
    ``language`` takes Indeed's two-letter code in either case, such as ``"en"``, including the legacy codes ``"iw"`` and ``"in"``.
    A filter stays out of the search at its default and as ``[]``. The filters that remain combine on every page.
    Age uses Indeed's ``dateOnIndeed`` field, which can differ from the publication timestamp returned as ``posted_at``.
    The caller owns ``fetcher``.

    Each request asks for 100 jobs, newest first. The returned list keeps
    that order and trims the final page to ``results``, which Indeed caps at
    ``MAX_RESULTS`` with a warning. Requests are neither paced nor retried. A
    malformed result costs only that result. An invalid field costs only that
    field.

    Raises:
        Stopped: A request failed, or Indeed answered with an error or an
            unreadable response. ``partial`` holds the jobs collected before it.
        ValueError: The country is unknown, ``company_ids`` holds more than one
            ID or a blank one, an attribute code is blank, or ``language`` is
            not two ASCII letters.
    """
    subdomain, api_code = indeed_domain(country)
    _check_filters(company_ids, language, attributes)
    base_url = f"https://{subdomain}.indeed.com"
    headers = {**API_HEADERS, "indeed-co": api_code}
    logger.info(
        "searching indeed for %r in %r", query, f"{location}, {country}" if location else country
    )

    jobs: list[JobDict] = []
    seen: set[str] = set()
    cursors: set[str] = set()
    cursor: str | None = None
    served = 0  # results Indeed has sent, malformed ones included
    while len(jobs) < results:
        graphql = _build_query(
            query,
            location,
            radius,
            max_age_hours,
            cursor,
            company_ids=company_ids,
            remote=remote,
            language=language,
            attributes=attributes,
        )
        result = await fetcher.fetch(API_URL, headers=headers, json={"query": graphql})
        kept = ngettext("%d job", "%d jobs", len(jobs)) % len(jobs)
        if result.error:
            raise Stopped(
                f"indeed search stopped: {result.error}. Kept the {kept} collected", partial=jobs
            )
        payload = None
        try:
            payload = json.loads(result.text)
            page, cursor, raw = _parse_jobs(payload, base_url)
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            # A GraphQL error arrives as HTTP 200 with null data. Usable data
            # alongside errors parses above and is kept.
            message = _graphql_error_message(payload)
            cause = (
                f"Indeed reported {message!r}"
                if message
                else f"indeed sent a response this version cannot read ({error!r}), likely an API change"
            )
            raise Stopped(
                f"indeed search stopped: {cause}. Kept the {kept} collected", partial=jobs
            ) from error
        # A page without results ends the search. A page whose results all
        # failed to parse costs only those results; its cursor still advances.
        if not raw:
            break
        served += raw
        for job in page:
            if job["id"] in seen:
                continue
            seen.add(job["id"])
            jobs.append(job)
        if not cursor or cursor in cursors:
            break
        cursors.add(cursor)
    if len(jobs) < results and served >= MAX_RESULTS:
        logger.warning(
            "indeed serves at most %d results per search; returning %d of the %d jobs "
            "requested. Narrow the search to reach more of its inventory",
            MAX_RESULTS,
            len(jobs),
            results,
        )
    jobs = jobs[:results]
    logger.info(
        "indeed search finished with %s", ngettext("%d job", "%d jobs", len(jobs)) % len(jobs)
    )
    return jobs
