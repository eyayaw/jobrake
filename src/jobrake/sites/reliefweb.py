"""Read humanitarian and development postings from ReliefWeb, UN OCHA's information service."""

import logging
import os
from collections.abc import AsyncGenerator
from typing import Annotated, Any
from urllib.parse import urlencode

from jobrake.countries import ALPHA3
from jobrake.fetchkit import Fetcher
from jobrake.models import JobDict, Stopped, employment_type, make_job
from jobrake.sites.responses import collect, json_page, offset_pages, read_json
from jobrake.utils import as_dict, as_int, as_list, as_str, checked, cutoff, html_text

logger = logging.getLogger(__name__)

# ReliefWeb's v2 API, documented at https://apidoc.reliefweb.int (read 2026-11-24). Every request
# must name an application ReliefWeb approved in appname. The API returns 400 without one and 403
# for one it has not approved.
JOBS_URL = "https://api.reliefweb.int/v2/jobs"
APPNAME = "JOBRAKE_RELIEFWEB_APPNAME"
# The most a call returns, per https://apidoc.reliefweb.int/read/response/ (read 2026-11-24). A page
# of 1,000 postings took 2 s, against 0.8 s for 100 (2026-11-24).
PAGE_SIZE = 1000


def _appname() -> str:
    """
    Return the user's approved appname from the environment.

    Raises:
        ValueError: ``JOBRAKE_RELIEFWEB_APPNAME`` is unset or blank.
    """
    if name := os.environ.get(APPNAME, "").strip():
        return name
    raise ValueError(
        f"{APPNAME} is unset or blank, and ReliefWeb's API requires an approved appname. "
        "Request one at https://apidoc.reliefweb.int/#appname and set the variable to it"
    )


def _validate(**_: object) -> None:
    _appname()


def _names(terms: object) -> list[str]:
    """Return the names of a field's taxonomy terms, such as its themes, in the API's order."""
    names = ((as_str(as_dict(term).get("name")) or "").strip() for term in as_list(terms))
    return [name for name in names if name]


def _parse_posting(posting: dict[str, Any]) -> JobDict:
    """
    Build a record from one posting of the list.

    Raises:
        TypeError: The posting lacks an integer ``id``.
        AttributeError: The posting is not an object.
    """
    fields = as_dict(posting.get("fields"))
    if (posting_id := as_int(fields.get("id"))) is None:
        raise TypeError(f"id {fields.get('id')!r} is not an integer")
    source = as_dict(next(iter(as_list(fields.get("source"))), None))
    dates = as_dict(fields.get("date"))
    kind = next(iter(_names(fields.get("type"))), None)
    return make_job(
        site="reliefweb",
        id=str(posting_id),
        url=(as_str(fields.get("url_alias")) or "").strip()
        or f"https://reliefweb.int/job/{posting_id}",
        title=fields.get("title"),
        # The first organization listed. Only 1 of the 1,000 newest postings listed a second
        # (2026-11-24).
        company=source.get("name"),
        company_url=as_str(source.get("homepage")),
        # The API's location for a country is its center, not where the job is, so it is left out.
        locations=[
            {"name": as_dict(country).get("name"), "country_code": as_dict(country).get("iso3")}
            for country in as_list(fields.get("country"))
        ],
        description=html_text(as_str(fields.get("body-html")) or ""),
        # Job, Consultancy, Internship, Volunteer Opportunity, or a call for tenders.
        employment_type=employment_type(kind),
        posted_at=as_str(dates.get("created")),
        expires_at=as_str(dates.get("closing")),
        site_data={
            "experience": next(iter(_names(fields.get("experience"))), None),
            "career_categories": _names(fields.get("career_categories")),
            "themes": _names(fields.get("theme")),
            "how_to_apply": html_text(as_str(fields.get("how_to_apply-html")) or ""),
        },
    )


def _filters(country: str | None, max_age_hours: int | None) -> list[dict[str, object]]:
    """Return the API's filter conditions for an alpha-2 country code and a maximum posting age."""
    conditions: list[dict[str, object]] = []
    if country:
        conditions.append({"field": "country.iso3", "value": ALPHA3[country].lower()})
    if since := cutoff(max_age_hours):
        # The API returns 400 for a timestamp with fractional seconds (2026-11-24).
        start = since.isoformat(timespec="seconds")
        conditions.append({"field": "date.created", "value": {"from": start}})
    return conditions


def _pages(
    fetcher: Fetcher, body: dict[str, object], size: int, appname: str
) -> AsyncGenerator[tuple[list[JobDict], int]]:
    url = f"{JOBS_URL}?{urlencode({'appname': appname})}"

    async def read(offset: int) -> tuple[list[Any], int]:
        result = await fetcher.fetch(url, json=body | {"offset": offset, "limit": size})
        if result.status == 403:
            raise Stopped(
                f"ReliefWeb rejected the appname {appname!r} in {APPNAME} with HTTP 403. Check "
                "that it matches the name ReliefWeb approved"
            )
        return read_json(
            result, lambda payload: json_page(payload, "data", "totalCount"), site="reliefweb"
        )

    return offset_pages(read, _parse_posting, site="reliefweb")


@checked(validator=_validate)
async def search(
    fetcher: Fetcher,
    *,
    query: Annotated[str, "job title or keywords"] = "",
    country: Annotated[str | None, "ISO 3166-1 country code, e.g., ke"] = None,
    # The newest 100 postings ran from 2026-11-20 to 2026-11-23 when read on 2026-11-24.
    results: Annotated[int, "maximum number of postings"] = 100,
    max_age_hours: Annotated[int | None, "maximum posting age in hours"] = None,
) -> list[JobDict]:
    """
    List the postings on ReliefWeb, newest first, each with its description.

    ``query`` runs ReliefWeb's keyword search as its site does. ``country`` keeps the postings that
    name the country, and ``max_age_hours`` those ReliefWeb published within that many hours.
    Pages of up to 1,000 postings follow one another without pacing or retries until ``results``,
    the last posting, or an empty page. A posting that a later page repeats is kept once.

    Every request carries the appname set in ``JOBRAKE_RELIEFWEB_APPNAME``.

    Raises:
        Stopped: A request failed, ReliefWeb refused the appname or sent an unreadable response,
            or an empty page came before the reported total.
            ``partial`` holds the postings of the pages before it.
        ValueError: ``JOBRAKE_RELIEFWEB_APPNAME`` is unset or blank, ``country`` is not an ISO
            3166-1 code, or ``results`` or ``max_age_hours`` is below 1.
    """
    body: dict[str, object] = {
        "profile": "full",
        # Markdown copies of the HTML fields parsed here. 1,000 postings were 3.6 MB gzipped without
        # them and 4.7 MB with them (2026-11-24).
        "fields": {"exclude": ["body", "how_to_apply"]},
        # The preset ReliefWeb's own search uses, which makes a keyword match what the website
        # matches: finance found 386 postings with it, as on reliefweb.int, and 46 without
        # (2026-11-24).
        "preset": "latest",
        # The ID breaks ties between postings created in the same second, so pages stay in order.
        "sort": ["date.created:desc", "id:desc"],
    }
    if keyword := query.strip():
        body["query"] = {"value": keyword, "operator": "AND"}
    # checked has already converted country to alpha-2.
    if conditions := _filters(country, max_age_hours):
        body["filter"] = {"operator": "AND", "conditions": conditions}
    logger.info("reading ReliefWeb postings%s", f" for {keyword!r}" if keyword else "")
    pages = _pages(fetcher, body, min(PAGE_SIZE, results), _appname())
    return await collect("reliefweb", pages, results)


__all__ = ["search"]
