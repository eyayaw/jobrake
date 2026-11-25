"""Search XING's job market through its mobile app's GraphQL API."""

import logging
import re
from collections.abc import AsyncGenerator
from html import escape
from typing import Annotated, Any

from jobrake.fetchkit import Fetcher
from jobrake.models import JobDict, Stopped, WorkplaceType, employment_type, make_job
from jobrake.sites.postings import fill_details, postings_of, readable_url
from jobrake.sites.responses import collect, json_page, offset_pages, read_json
from jobrake.utils import as_dict, as_list, as_str, checked, cutoff, finite, html_text, split_url

logger = logging.getLogger(__name__)

# XING's GraphQL endpoint and the logged-out API key of its Android app, com.xing.android 26.52.0p
# (checked 2026-11-24). Without the Authorization header the API returns HTTP 401. English labels
# keep careerLevel, discipline, and industry the same whatever the posting's language.
API_URL = "https://api.xing.com/vendor/xing-one/api"
APP_KEY = "37cade477746b5cba99e4529cf0fa6fb13697938"  # gitleaks:allow  public Android app key
API_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "en",
    "Authorization": f'APIKEY api_key="{APP_KEY}"',
}
CONSUMER = "jobs_search_android"
# XING rejects limit > 20 ("Limit cannot be > 20") and limit + offset > 1000
# ("Window size (limit + offset) cannot be > 1000"), measured 2026-11-24.
PAGE_SIZE = 20
MAX_RESULTS = 1000

_HOSTS = {"xing.com", "www.xing.com"}
# A posting's web URL ends in -<id>. /jobs/<id> without a slug opens a search page on xing.com.
_JOB_PATH = re.compile(r"/jobs/([^/\s]+-([0-9]+))/?")
# Search cards carry a client-specific scrambled suffix such as 158291337_dbef63; the numeric
# prefix is the public posting ID that appears in the URL and that job(slug:) accepts directly.
_POSTING_ID = re.compile(r"([0-9]+)(?:_[0-9a-fA-F]+)?")
# Employment type IDs carry the same scrambled suffix, such as FULL_TIME_b0ed28 or INTERN_99cfb1.
_SCRAMBLED_SUFFIX = re.compile(r"_[0-9a-fA-F]+$")

_WORKPLACE_MAP: dict[str, WorkplaceType] = {
    "FULL_REMOTE": "remote",
    "PARTLY_REMOTE": "hybrid",
    "NON_REMOTE": "on_site",
}

# The titled HTML sections of a TemplateData description, in reading order.
_TEMPLATE_SECTIONS = ("companyDescription", "responsibility", "skills", "weOffer", "contactInfo")

# Aliases give the variants of salary and application one shape. The query leaves out XING's
# SalaryEstimate, so an estimated salary arrives as an empty object.
_VISIBLE_JOB_FIELDS = """
  __typename id title url language refreshedAt activeUntil remoteOptions
  employmentType { id localizationValue }
  careerLevel { localizationValue }
  discipline { localizationValue }
  industry { localizationValue }
  locations { city region country { countryCode } }
  companyInfo { companyNameOverride company { companyName logos { logo256px } links { public } } }
  salary {
    ... on Salary { minimum: amount maximum: amount currency }
    ... on SalaryRange { minimum maximum currency }
  }
  application {
    ... on UrlApplication { url: applyUrl }
    ... on JobXingCustomApplication { url: fallbackUrl }
  }
"""

_SEARCH_QUERY = f"""
query JobSearch($query: JobSearchQueryInput!, $consumer: String!, $limit: Int!, $offset: Int!,
    $since: Date) {{
  response: jobSearchByQuery(query: $query, consumer: $consumer, limit: $limit, offset: $offset,
      trackRecent: false, since: $since, returnAggregations: false, searchMode: SEMANTIC) {{
    boundedTotal {{ total }}
    collection {{ jobDetail {{ ... on VisibleJob {{ {_VISIBLE_JOB_FIELDS} }} }} }}
  }}
}}
"""

# job(slug:) accepts both a posting's slug and its bare numeric ID, unlike jobById which requires
# the scrambled ID (measured 2026-11-24 on three postings and one unknown ID). HtmlDescription and
# ExternalUrlDescription keep their own field names, because XING refuses one alias for a String
# and a String!.
_POSTING_QUERY = f"""
query JobPosting($slug: String!) {{
  job(slug: $slug, enableTemplateData: true, templateDataFormat: HTML,
      enableXingCustomApplication: true) {{
    __typename
    ... on UnauthorizedJob {{ reason }}
    ... on VisibleJob {{
      {_VISIBLE_JOB_FIELDS}
      description {{
        ... on HtmlDescription {{ content }}
        ... on ExternalUrlDescription {{ htmlContent }}
        ... on TemplateData {{
          genericDescription {" ".join(f"{name}Title {name}Content" for name in _TEMPLATE_SECTIONS)}
        }}
      }}
    }}
  }}
}}
"""


def _data(payload: Any) -> Any:  # noqa: ANN401  decoded JSON checked by its caller
    """
    Return a response's ``data``.

    Raises:
        Stopped: XING reported a GraphQL error. The message names the first one.
    """
    if errors := as_list(as_dict(payload).get("errors")):
        error = as_dict(errors[0])
        detail = as_str(as_dict(error.get("details")).get("description"))
        raise Stopped(f"XING reported {detail or as_str(error.get('message')) or errors[0]!r}")
    return payload["data"]


def _posting_id(raw: object) -> str:
    """
    Return the numeric posting ID of XING's scrambled ``id``.

    Raises:
        TypeError: ``raw`` is not a numeric ID with an optional scrambled suffix.
    """
    if isinstance(raw, str) and (match := _POSTING_ID.fullmatch(raw.strip())):
        return match[1]
    raise TypeError(f"id {raw!r} is not a XING posting ID")


def _workplace(options: object) -> WorkplaceType | None:
    """Map XING's ``remoteOptions`` when they agree on one workplace type."""
    modes = {
        _WORKPLACE_MAP[code]
        for code in as_list(options)
        if isinstance(code, str) and code in _WORKPLACE_MAP
    }
    return modes.pop() if len(modes) == 1 else None


def _description(raw: object) -> str:
    """Read a posting's HTML description, joining the titled sections of XING's template."""
    entry = as_dict(raw)
    blocks = [entry.get("content"), entry.get("htmlContent"), entry.get("genericDescription")]
    for name in _TEMPLATE_SECTIONS:
        if content := as_str(entry.get(f"{name}Content")):
            if title := as_str(entry.get(f"{name}Title")):
                blocks.append(f"<h3>{escape(title)}</h3>")
            blocks.append(content)
    return html_text("".join(f"<div>{block}</div>" for block in blocks if isinstance(block, str)))


def _visible_fields(posting: dict[str, Any]) -> dict[str, Any]:
    """Read the fields shared by search cards and ``job(slug:)`` postings."""
    info = as_dict(posting.get("companyInfo"))
    company = as_dict(info.get("company"))
    salary = as_dict(posting.get("salary"))
    low, high = finite(salary.get("minimum")), finite(salary.get("maximum"))
    employment = as_dict(posting.get("employmentType"))
    code = as_str(employment.get("id"))
    return {
        "title": posting.get("title"),
        "company": as_str(info.get("companyNameOverride")) or as_str(company.get("companyName")),
        "company_url": as_str(as_dict(company.get("links")).get("public")),
        "company_logo": as_str(as_dict(company.get("logos")).get("logo256px")),
        "locations": [
            {
                "city": place.get("city"),
                "region": place.get("region"),
                "country_code": as_dict(place.get("country")).get("countryCode"),
            }
            for place in map(as_dict, as_list(posting.get("locations")))
        ],
        "language": as_str(posting.get("language")),
        "employment_type": employment_type(
            _SCRAMBLED_SUFFIX.sub("", code) if code else as_str(employment.get("localizationValue"))
        ),
        "workplace_type": _workplace(posting.get("remoteOptions")),
        # XING's app shows advertised salaries as yearly gross amounts (Android app strings
        # JOBS_SEARCH_AI_EARN_MORE_DIALOG_SALARY_RANGE / JOB_PREFERENCES_*, checked 2026-11-24).
        **(
            {
                "salary_min": low,
                "salary_max": high,
                "salary_currency": as_str(salary.get("currency")),
                "salary_period": "YEAR",
            }
            if low is not None or high is not None
            else {}
        ),
        "posted_at": as_str(posting.get("refreshedAt")),
        "expires_at": as_str(posting.get("activeUntil")),
        "apply_url": as_str(as_dict(posting.get("application")).get("url")),
        "site_data": {
            field: as_str(as_dict(posting.get(field)).get("localizationValue"))
            for field in ("careerLevel", "discipline", "industry")
        },
    }


def _parse_card(entry: dict[str, Any]) -> JobDict:
    """
    Build a record from one entry of a search response's ``collection`` list.

    Raises:
        TypeError, LookupError, AttributeError: The entry carries no readable ``VisibleJob``.
    """
    posting = entry["jobDetail"]
    if posting.get("__typename") != "VisibleJob":
        raise TypeError("search entry carries no VisibleJob")
    posting_id = _posting_id(posting.get("id"))
    url = readable_url(card, posting_id, as_str(posting.get("url")) or "")
    return make_job(site="xing", id=posting_id, url=url, **_visible_fields(posting))


def _unpack_page(payload: Any) -> tuple[list[Any], int]:  # noqa: ANN401  decoded JSON checked here
    """
    Return the ``collection`` list and ``boundedTotal.total`` of a search response.

    Raises:
        Stopped: XING reported a GraphQL error.
        TypeError, LookupError: The response is unreadable.
    """
    response = _data(payload)["response"]
    return json_page(response | response["boundedTotal"], "collection", "total")


def _unpack_posting(payload: Any, url: str) -> dict[str, Any] | None:  # noqa: ANN401  decoded JSON checked here
    """
    Read a ``job(slug:)`` response into a whole record's fields, or None when the posting is gone.

    Raises:
        Stopped: XING reported a GraphQL error or refused access to the posting.
        TypeError, LookupError, AttributeError: The response is unreadable.
    """
    posting = _data(payload)["job"]
    if posting is None:
        return None
    kind, reason = posting.get("__typename"), posting.get("reason")
    if kind == "UnauthorizedJob" and reason == "GONE":
        return None
    if kind == "UnauthorizedJob":
        raise Stopped(f"XING refused {url} ({reason})")
    if kind != "VisibleJob":
        raise TypeError(f"job is a {kind!r}, not a VisibleJob")
    fields = _visible_fields(posting) | {"description": _description(posting.get("description"))}
    if canonical := as_str(posting.get("url")):
        fields["url"] = canonical
    return fields


async def _posting_fields(fetcher: Fetcher, url: str) -> dict[str, Any] | None:
    """
    Fetch the posting at a URL through ``job(slug:)``, or None when XING reports it gone.

    Raises:
        Stopped: The request failed, XING refused the posting, or the response is unreadable.
    """
    posting_id = card(url)["id"]
    body = {
        "operationName": "JobPosting",
        "query": _POSTING_QUERY,
        "variables": {"slug": posting_id},
    }
    result = await fetcher.fetch(API_URL, headers=API_HEADERS, json=body)
    return read_json(result, lambda payload: _unpack_posting(payload, url), site="xing")


def _query_input(query: str, location: str | None, radius: int, *, remote: bool) -> dict[str, Any]:
    """Build ``JobSearchQueryInput`` from the search options that XING applies."""
    body: dict[str, Any] = {}
    if keyword := query.strip():
        body["keywords"] = keyword
    if where := (location or "").strip():
        body["location"] = {"text": where, "radius": radius}
    if remote:
        # Matches filter.remoteOption = FULL_REMOTE (both returned the same 285 postings, all
        # FULL_REMOTE, on 2026-11-24).
        body["filter"] = {"remote": True}
    return body


async def _pages(
    fetcher: Fetcher, query_input: dict[str, Any], since: str | None, results: int
) -> AsyncGenerator[tuple[list[JobDict], int]]:
    """
    Yield each page's cards with the count of matches XING can serve, for ``collect``.

    Raises:
        Stopped: A request failed, XING reported an error or sent an unreadable response,
            or an empty page came before the reported total.
    """
    total = 0

    async def read(offset: int) -> tuple[list[Any], int]:
        nonlocal total
        variables = {
            "query": query_input,
            "consumer": CONSUMER,
            "limit": min(PAGE_SIZE, results, MAX_RESULTS - offset),
            "offset": offset,
        } | ({"since": since} if since else {})
        body = {"operationName": "JobSearch", "query": _SEARCH_QUERY, "variables": variables}
        result = await fetcher.fetch(API_URL, headers=API_HEADERS, json=body)
        cards, total = read_json(result, _unpack_page, site="xing")
        return cards, min(total, MAX_RESULTS)

    async for page in offset_pages(read, _parse_card, site="xing"):
        yield page
    # Keyword searches for 'data' and 'volkswirt' reported a total of exactly 1,000, XING's
    # bound, on 2026-11-24, while a search without keywords reported 536,204, so a total at the
    # cap may hide more matches.
    if total >= MAX_RESULTS:
        logger.warning(
            "XING serves at most %d postings per search, fewer than requested. "
            "Split the search by place or narrow the query to reach the rest",
            MAX_RESULTS,
        )


@checked
async def search(
    fetcher: Fetcher,
    *,
    query: Annotated[str, "job title or keywords"] = "",
    location: Annotated[str | None, "city or postal code"] = None,
    # XING's own search covers the location alone ("Nur in Leipzig", radius null), and an omitted
    # radius returned the 578 postings of radius 0 for 'ingenieur' in Leipzig (2026-11-25).
    radius: Annotated[int, "search radius in kilometers"] = 0,
    results: Annotated[int, "maximum number of postings"] = 100,
    max_age_hours: Annotated[int | None, "maximum posting age in hours"] = None,
    remote: Annotated[bool, "only postings XING lists as fully remote"] = False,
    details: Annotated[bool, "fetch each posting for its description"] = False,
) -> list[JobDict]:
    """
    Search XING's job market and list the postings it returns.

    ``max_age_hours`` counts from the time XING last refreshed a posting. XING serves at most
    ``MAX_RESULTS`` postings per search, and a search that reaches that cap short of ``results``
    warns and returns them. A card lacks the description, so ``details`` fetches each posting
    with one more request, which a cached posting skips.

    Raises:
        Stopped: A request failed, XING reported an error or sent an unreadable response, or an
            empty page came before the reported total. ``partial`` holds the postings of the pages
            before it. With ``details``, a posting could not be fetched, and ``partial`` holds
            every posting, filled where its fetch succeeded, and ``failed`` the URLs of the
            postings whose fetch failed.
        ValueError: ``results`` or ``max_age_hours`` is below 1, or ``radius`` is below 0.
    """
    logger.info("searching XING for %r in %r", query, location or "all locations")
    query_input = _query_input(query, location, radius, remote=remote)
    since = moment.strftime("%Y-%m-%dT%H:%M:%SZ") if (moment := cutoff(max_age_hours)) else None
    jobs = await collect("xing", _pages(fetcher, query_input, since, results), results)
    return await fill_details(fetcher, jobs, _posting_fields) if details else jobs


def card(reference: str) -> JobDict:
    """
    Read a XING posting URL as the card it names, for ``postings`` and ``identify``.

    Raises:
        ValueError: The reference is not a XING posting URL on xing.com.
    """
    parts = split_url(reference)
    hosted = parts.scheme in ("http", "https") and parts.netloc.lower() in _HOSTS
    if not (hosted and (match := _JOB_PATH.fullmatch(parts.path))):
        raise ValueError(
            f"{reference!r} is not a XING posting URL. Pass a record's url, such as "
            "https://www.xing.com/jobs/berlin-referent-strategische-datenanalyse-158824212"
        )
    slug, posting_id = match.groups()
    return make_job(site="xing", id=posting_id, url=f"https://www.xing.com/jobs/{slug}")


postings = postings_of(card, _posting_fields)


__all__ = ["postings", "search"]
