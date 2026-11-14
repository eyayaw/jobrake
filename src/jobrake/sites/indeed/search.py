"""Indeed GraphQL query construction, parsing, and pagination."""

import functools
import json
import logging
import re
from collections.abc import AsyncGenerator, Callable
from typing import Annotated, Any

from jobrake.fetchkit import Fetcher
from jobrake.models import JobDict, Stopped, WorkplaceType, employment_type, make_job
from jobrake.sites.responses import collect, json_list, parse_postings, read_json
from jobrake.utils import as_dict, as_str, checked, epoch_ms_to_iso, finite, html_text

from .client import API_HEADERS, API_URL
from .countries import Country, indeed_domain

logger = logging.getLogger(__name__)

# The query of JobSpy (https://github.com/speedyapply/JobSpy), trimmed to the
# fields we keep. `limit: 100` sets the API page size and must stay identical
# on every request of a cursor chain: Indeed binds the size to its cursor and
# rejects a changed value with BAD_USER_INPUT. Pagination continues through
# pageInfo.nextCursor. The salary range is a union. Range carries both bounds,
# AtLeast and AtMost carry one, and Exactly carries one value.
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
# text, where html_text keeps them as text. A rule is a selector followed by a
# {block} of `property: value;` declarations. Only the last declaration may
# drop its semicolon, so prose such as {"id": 1} or {negotiable: yes} is not a
# rule. Neither is an empty block, or a value that holds a semicolon, such as
# a data URI: those stay in the text. The selector stops at a line break or a
# sentence period.
_CSS_BLOCK = r"\{(?:\s*[-\w]+\s*:[^{};]+;)+(?:\s*[-\w]+\s*:[^{};]+)?\s*\}"
_CSS_RULE = re.compile(r"(?:[^{}\n.]|\.(?!\s)){0,200}?" + _CSS_BLOCK)
# An at-rule such as @media, once the rules inside it are gone.
_CSS_EMPTY_AT_RULE = re.compile(r"@[^{};\n]{0,200}\{\s*\}")
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _scrub_css(text: str) -> str:
    """Remove CSS rules flattened into some posting descriptions."""
    if "{" not in text:
        return text
    # A comment inside a block would hide its rule, so the search runs without
    # comments. They go only from a text that holds a rule, because a file glob
    # in prose holds /* too.
    uncommented = _CSS_COMMENT.sub(" ", text)
    if not _CSS_RULE.search(uncommented):
        return text
    text = uncommented
    while True:
        # Innermost rules first, so nested @media blocks collapse over the passes.
        scrubbed = _CSS_EMPTY_AT_RULE.sub(" ", _CSS_RULE.sub(" ", text))
        if scrubbed == text:
            break
        text = scrubbed
    lines = (" ".join(line.split()) for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def _workplace_type(labels: list[str]) -> WorkplaceType | None:
    """
    Read the workplace from Indeed's Remote and Hybrid work tags.

    Return None when both tags are present or both are absent, because a
    missing tag proves nothing. Indeed tagged 1 of 100 hybrid postings Remote
    as well on 2026-10-28.
    """
    remote, hybrid = "Remote" in labels, "Hybrid work" in labels
    if remote == hybrid:
        return None
    return "remote" if remote else "hybrid"


def _parse_job(job: dict[str, Any], base_url: str) -> JobDict:
    """Normalize one Indeed result into the shared job model."""
    # Indeed's job key becomes both the job ID and the URL's ``jk`` parameter.
    key = (as_str(job.get("key")) or "").strip()
    loc = as_dict(job.get("location"))
    employer = as_dict(job.get("employer"))
    compensation = as_dict(job.get("compensation"))
    salary = as_dict(compensation.get("baseSalary"))
    amount = as_dict(salary.get("range"))
    exactly = finite(amount.get("value"))
    # Employment types share the attributes bag with skills and benefits.
    # Malformed entries, or a bag that is not a list, are ignored.
    attributes = job.get("attributes")
    labels = [
        attribute.get("label")
        for attribute in (attributes if isinstance(attributes, list) else [])
        if isinstance(attribute, dict) and isinstance(attribute.get("label"), str)
    ]
    company_page = as_str(employer.get("relativeCompanyPageUrl"))
    dossier = as_dict(employer.get("dossier"))
    images = as_dict(dossier.get("images"))
    return make_job(
        site="indeed",
        id=key,
        url=f"{base_url}/viewjob?jk={key}",
        title=as_str(job.get("title")),
        language=as_str(job.get("language")),
        company=as_str(employer.get("name")),
        locations=[
            {
                "city": loc.get("city"),
                "region": loc.get("admin1Code"),
                "country_code": loc.get("countryCode"),
                "latitude": loc.get("latitude"),
                "longitude": loc.get("longitude"),
            }
        ],
        description=_scrub_css(
            html_text(as_str(as_dict(job.get("description")).get("html")) or "")
        ),
        posted_at=epoch_ms_to_iso(job.get("datePublished")),
        expires_at=epoch_ms_to_iso(job.get("expirationDate")),
        company_url=base_url + company_page if company_page else None,
        company_logo=as_str(images.get("squareLogoUrl")),
        employment_type=next(
            (employment_type(label) for label in labels if label in EMPLOYMENT_TYPES),
            None,
        ),
        workplace_type=_workplace_type(labels),
        salary_min=finite(amount.get("min", exactly)),
        salary_max=finite(amount.get("max", exactly)),
        salary_currency=as_str(compensation.get("currencyCode")),
        salary_period=as_str(salary.get("unitOfWork")),
        apply_url=as_str(as_dict(job.get("recruit")).get("viewJobUrl")),
    )


def _graphql_error_message(payload: object) -> str | None:
    """Read the first string message from a GraphQL error envelope."""
    errors = payload.get("errors") if isinstance(payload, dict) else None
    for error in errors if isinstance(errors, list) else []:
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"]
    return None


def search_results(data: Any) -> tuple[Any, list[Any]]:  # noqa: ANN401  any decoded JSON
    """
    Return the ``jobSearch`` object of a GraphQL response and its list of results.

    Raises:
        Stopped: Indeed answered with a GraphQL error in place of the search data.
        KeyError: The response lacks required search data.
        TypeError: The response envelope has an unreadable shape.
    """
    try:
        search = data["data"]["jobSearch"]
        return search, json_list(search, "results")
    except KeyError, TypeError:
        # A GraphQL error arrives as HTTP 200 with null data. Usable data
        # alongside errors parses and is kept.
        if message := _graphql_error_message(data):
            raise Stopped(f"Indeed reported {message!r}") from None
        raise


def _parse_jobs(data: dict[str, Any], base_url: str) -> tuple[list[JobDict], str | None, int]:
    """
    Parse one GraphQL page while isolating malformed results.

    ``base_url`` supplies the origin for posting and company links.

    Returns:
        Parsed jobs, a usable next cursor, and the count of results Indeed sent.
        The raw count includes malformed results so pagination still advances.

    Raises:
        Stopped, KeyError, TypeError: Whatever ``search_results`` raises for ``data``.
    """
    search, results = search_results(data)
    jobs = parse_postings(
        results, lambda result: _parse_job(result.get("job"), base_url), site="indeed"
    )
    # Missing or invalid pagination metadata ends the search after this page.
    # Keep the jobs already parsed from it.
    cursor = as_str(as_dict(search.get("pageInfo")).get("nextCursor"))
    return jobs, cursor, len(results)


async def _pages(
    fetcher: Fetcher, headers: dict[str, str], base_url: str, query: Callable[[str | None], str]
) -> AsyncGenerator[tuple[list[JobDict], int]]:
    """
    Yield each page of a cursor chain until Indeed ends it, warning when it ends at ``MAX_RESULTS``.

    ``query`` builds the GraphQL query for a cursor.

    Raises:
        Stopped: A request failed, or Indeed answered with an error or an unreadable response.
    """
    cursor: str | None = None
    cursors: set[str] = set()
    served = 0  # results Indeed has sent, malformed ones included
    while True:
        result = await fetcher.fetch(API_URL, headers=headers, json={"query": query(cursor)})
        page, cursor, raw = read_json(
            result, lambda payload: _parse_jobs(payload, base_url), site="indeed"
        )
        # A page without results ends the search. A page whose results all
        # failed to parse yields none, and its cursor still advances.
        if not raw:
            break
        served += raw
        yield page, MAX_RESULTS
        if not cursor or cursor in cursors:
            break
        cursors.add(cursor)
    if served >= MAX_RESULTS:
        logger.warning(
            "indeed serves at most %d results per search, fewer than requested. "
            "Narrow the search to reach more of its inventory",
            MAX_RESULTS,
        )


def _check_filters(company_ids: list[str] | None, language: str | None) -> None:
    # Indeed intersects the employer keys it receives, so a search takes one.
    if len(company_ids or []) > 1:
        raise ValueError(
            "indeed takes one company ID per search. "
            "Search each company on its own and combine the results"
        )
    if language is not None and re.fullmatch(r"[A-Za-z]{2}", language) is None:
        raise ValueError(
            f"language {language!r} must contain exactly two ASCII letters, such as 'en'"
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
    The supplied filters combine on every page.
    Age uses Indeed's ``dateOnIndeed`` field, which can differ from the publication timestamp returned as ``posted_at``.

    Each request asks for 100 jobs, newest first. The returned list keeps
    that order and stops at ``results``. Indeed serves at most
    ``MAX_RESULTS`` results per search, and a search that reaches that cap
    short of ``results`` warns. Requests are neither paced nor retried.

    Raises:
        Stopped: A request failed, or Indeed answered with an error or an
            unreadable response. ``partial`` holds the jobs collected before it.
        ValueError: The country is unknown, ``company_ids`` holds more than
            one ID, a list holds a blank entry, or ``language`` is not two
            ASCII letters.
    """
    subdomain, api_code = indeed_domain(country)
    _check_filters(company_ids, language)
    base_url = f"https://{subdomain}.indeed.com"
    headers = {**API_HEADERS, "indeed-co": api_code}
    logger.info(
        "searching indeed for %r in %r", query, f"{location}, {country}" if location else country
    )
    build = functools.partial(
        _build_query,
        query,
        location,
        radius,
        max_age_hours,
        company_ids=company_ids,
        remote=remote,
        language=language,
        attributes=attributes,
    )
    return await collect("indeed", _pages(fetcher, headers, base_url, build), results)
