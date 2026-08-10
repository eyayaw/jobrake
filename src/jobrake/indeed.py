"""Indeed via its mobile-app GraphQL API (the same one jobspy uses)."""

from __future__ import annotations

import json

from jobrake.core import epoch_ms_to_date, html_text, make_job
from jobrake.countries import indeed_domain
from jobrake.constants import JobrakeConstants as JBC
from jobrake.fetchkit import PostFetcher

API_URL = "https://apis.indeed.com/graphql"

# The public API key baked into Indeed's iOS app—shared by every client of
# this endpoint (jobspy ships the same one), so it is not a secret. If Indeed
# rotates it, requests start failing with 401/403; lift the fresh key from the
# app or jobspy and update this one line.
INDEED_APP_KEY = "161092c2017b5bbab13edb12461a62d5a833871e7cad6d9d475304573de67ac8"

API_HEADERS = {
    "Host": "apis.indeed.com",
    "content-type": "application/json",
    "indeed-api-key": INDEED_APP_KEY,
    "accept": "application/json",
    "indeed-locale": "en-US",
    "user-agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6_1 like Mac OS X) AppleWebKit/605.1.15"
        " (KHTML, like Gecko) Mobile/15E148 Indeed App 193.1"
    ),
    "indeed-app-info": "appv=193.1; appid=com.indeed.jobsearch; osv=16.6.1; os=ios; dtype=phone",
}

# jobspy's query, trimmed to the fields we keep. `limit: 100` is the API's page
# size; pagination continues via pageInfo.nextCursor.
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
        description {{ html }}
        location {{ city admin1Code countryCode }}
        employer {{ name }}
      }}
    }}
  }}
}}
"""


def build_query(
    search_term: str,
    location: str,
    distance: int | None,
    hours_old: int | None,
    cursor: str | None,
) -> str:
    escaped = search_term.replace('"', '\\"')
    filters = ""
    if hours_old:
        filters = f'filters: {{ date: {{ field: "dateOnIndeed", start: "{hours_old}h" }} }}'
    return QUERY.format(
        what=f'what: "{escaped}"' if escaped else "",
        location=(
            f'location: {{ where: "{location}", radius: {distance or JBC.radius}, radiusUnit: {JBC.radius_unit} }}'
            if location
            else ""
        ),
        cursor=f'cursor: "{cursor}"' if cursor else "",
        filters=filters,
    )


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
        jobs.append(
            make_job(
                id=job["key"],
                title=job.get("title", ""),
                company=employer.get("name") or "",
                url=f"{base_url}/viewjob?jk={job['key']}",
                location=location,
                description=html_text((job.get("description") or {}).get("html", "")),
                date=epoch_ms_to_date(job.get("datePublished")),
                site="indeed",
            )
        )
    return jobs, search["pageInfo"].get("nextCursor")


async def search(
    fetcher: PostFetcher,
    *,
    search_term: str,
    location: str | None = None,
    country: str,
    distance: int | None = JBC.radius,
    results_wanted: int = JBC.results_wanted,
    hours_old: int | None = None,
    fetch_description: bool = True,  # no-op: always included in the GraphQL response
) -> list[dict]:
    """
    Page through the GraphQL API into job dicts.

    This API answers POST alone, hence the ``PostFetcher``. An error result
    or a malformed page ends the search with whatever was collected.
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
