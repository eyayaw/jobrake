"""Read job openings from UN Careers, the United Nations Secretariat's recruitment site."""

import difflib
import logging
from collections.abc import AsyncGenerator
from typing import Annotated, Any

from jobrake.fetchkit import Fetcher
from jobrake.models import JobDict, Stopped, make_job
from jobrake.sites.responses import (
    collect,
    cut_short,
    json_list,
    json_page,
    parse_postings,
    read_json,
)
from jobrake.utils import as_dict, as_str, checked, html_text

logger = logging.getLogger(__name__)

# The endpoints the careers.un.org search page calls, as Chrome showed on 2026-11-16. They are
# undocumented and answer without authentication.
SEARCH_URL = "https://careers.un.org/api/public/opening/jo/list/filteredV2/en"
CATALOG_URL = "https://careers.un.org/api/public/opening/jo-filter/list/en"
OPENING_URL = "https://careers.un.org/jobSearchDescription/{id}?language=en"
PAGE_SIZE = 100  # the page size the web app requests
# Each filter option and its key in the catalog and in the search's filterConfig. The API ignores
# a code it does not know and then returns every opening, so a value is checked against the catalog.
FILTERS = {
    "category": "jc",
    "duty_station": "ds",
    "level": "jle",
    "department": "dept",
    "job_network": "jn",
    "job_family": "jf",
    "recruitment_type": "recrtype",
}
# The posting ages the site filters on, in hours, and its span code in days.
SPANS = {24: "1", 168: "7", 720: "30"}
*_FIRST_AGES, _LAST_AGE = SPANS
_AGES = f"{', '.join(map(str, _FIRST_AGES))}, or {_LAST_AGE}"


def _parse_opening(opening: dict[str, Any]) -> JobDict:
    """
    Build a record from one opening of the list.

    Raises:
        TypeError: The opening lacks an integer ``jobId``.
        AttributeError: The opening is not an object.
    """
    job_id = opening.get("jobId")
    if not isinstance(job_id, int):
        raise TypeError(f"jobId {job_id!r} is not an integer")
    stations = opening.get("dutyStation")
    return make_job(
        site="uncareers",
        id=str(job_id),
        url=OPENING_URL.format(id=job_id),
        title=opening.get("postingTitle"),
        # The UN entity that hires, such as the United Nations Environment Programme.
        company=as_dict(opening.get("dept")).get("name"),
        # A duty station is a label such as NEW YORK or FO West Bank, with no country.
        locations=[
            {"name": as_dict(station).get("description")}
            for station in (stations if isinstance(stations, list) else [])
        ],
        description=html_text(as_str(opening.get("jobDescription")) or ""),
        posted_at=as_str(opening.get("startDate")),
        expires_at=as_str(opening.get("endDate")),
        site_data={
            "category": as_str(opening.get("categoryCode")),
            "level": as_str(opening.get("jobLevel")),
            "job_family": as_str(as_dict(opening.get("jf")).get("Name")),
            "job_network": as_str(as_dict(opening.get("jn")).get("name")),
            "recruitment_type": as_str(as_dict(opening.get("recrttype")).get("name")),
        },
    )


async def _pages(
    fetcher: Fetcher, filters: dict[str, object], size: int
) -> AsyncGenerator[tuple[list[JobDict], int]]:
    page = offset = total = 0
    while True:
        body = {
            "filterConfig": filters,
            "pagination": {
                "page": page,
                "itemPerPage": size,
                # Many openings share a start date, and the site orders them differently from one
                # request to the next, so pages sorted by date repeated 11 openings of 448 and
                # skipped 11 others (measured 2026-11-16). Job IDs are unique.
                "sortBy": "jobId",
                "sortDirection": -1,
            },
        }
        result = await fetcher.fetch(SEARCH_URL, json=body)
        openings, total = read_json(
            result, lambda payload: json_page(payload["data"], "list", "count"), site="uncareers"
        )
        if not openings:
            break
        page += 1
        offset += len(openings)
        # An opening posted between two requests shifts the list, so a page can repeat one.
        yield parse_postings(openings, _parse_opening, site="uncareers"), total
        if offset >= total:
            return
    if offset < total:
        raise cut_short("uncareers", total, offset)


def _entries(items: object, code: str, name: str) -> list[tuple[str, str]]:
    """Return the ``(code, name)`` pairs of catalog entries, skipping an incomplete one."""
    return [
        (key, label)
        for entry in map(as_dict, items if isinstance(items, list) else [])
        if (key := as_str(entry.get(code))) and (label := as_str(entry.get(name)))
    ]


def _catalog(payload: Any) -> dict[str, list[tuple[str, str]]]:  # noqa: ANN401  any decoded JSON, which _catalog checks
    """
    Return the ``(code, name)`` entries of each filter in the site's filter catalog.

    Raises:
        KeyError: The payload lacks ``data``.
        TypeError: ``data`` is not a list.
        AttributeError: A filter is not an object.
    """
    catalog = {}
    families = []
    for group in json_list(payload, "data"):
        values = group.get("values")
        catalog[group.get("shortname")] = _entries(values, "code", "name")
        # The job family filter comes with no values, and each job network lists its families.
        if group.get("shortname") == "jn":
            families += [
                family
                for network in map(as_dict, values if isinstance(values, list) else [])
                for family in _entries(network.get("jobFamilies"), "Code", "Name")
            ]
    catalog["jf"] = families
    return catalog


def _codes(option: str, entries: list[tuple[str, str]], values: list[str]) -> list[str]:
    """
    Return the codes of the catalog entries whose code or name is one of ``values``, in any case.

    Raises:
        Stopped: The catalog lists no entries for the filter.
        ValueError: A value names no entry. The message lists close names.
    """
    if not entries:
        raise Stopped(
            f"UN Careers sent a filter catalog without {option.replace('_', ' ')} values, "
            f"likely an API change. Search without the {option} filter"
        )
    codes = set()
    for value in values:
        wanted = value.strip().casefold()
        found = {code for code, name in entries if wanted in (code.casefold(), name.casefold())}
        if not found:
            names = {name.casefold(): name for _, name in entries}
            close = [names[match] for match in difflib.get_close_matches(wanted, names, n=3)]
            hint = (
                f"Did you mean {', '.join(map(repr, close))}?"
                if close
                else "Use a name from the filters of the site's search page"
            )
            raise ValueError(f"unknown UN Careers {option.replace('_', ' ')} {value!r}. {hint}")
        codes |= found
    return sorted(codes)


def _validate(
    *, query: str, category: list[str] | None, max_age_hours: int | None, **_: object
) -> None:
    # A category makes the site drop the keyword, though every other filter combines with it
    # (measured 2026-11-16).
    if query.strip() and category:
        raise ValueError(
            "UN Careers ignores query when category is given, so pass one of them and filter the "
            "results on the other"
        )
    if max_age_hours is not None and max_age_hours not in SPANS:
        raise ValueError(
            f"UN Careers filters posting age by {_AGES} hours only, not {max_age_hours}"
        )


@checked(validator=_validate)
async def search(
    fetcher: Fetcher,
    *,
    query: Annotated[str, "job title or keywords"] = "",
    results: Annotated[int, "maximum number of postings"] = 100,
    max_age_hours: Annotated[int | None, f"maximum posting age in hours: {_AGES}"] = None,
    category: Annotated[list[str] | None, "job category, e.g., PD or INT"] = None,
    duty_station: Annotated[list[str] | None, "duty station, e.g., Geneva"] = None,
    level: Annotated[list[str] | None, "grade, e.g., P-3"] = None,
    department: Annotated[
        list[str] | None, "UN entity, e.g., Economic Commission for Africa"
    ] = None,
    job_network: Annotated[list[str] | None, "job network, e.g., DEVNET"] = None,
    job_family: Annotated[list[str] | None, "job family, e.g., Statistics"] = None,
    recruitment_type: Annotated[list[str] | None, "recruitment type, e.g., Consultant"] = None,
) -> list[JobDict]:
    """
    List the openings on UN Careers, highest job ID first, each with its description.

    ``query`` keeps openings that UN Careers matches to its words. Each list filter keeps openings
    that match any of its values, given by the name or the code the site's search page uses,
    in any case, and different filters all apply. A search with a list filter first reads the
    site's filter catalog, to turn names into codes, so ``check`` confirms those values' types
    only. ``query`` cannot be combined with ``category``.
    Pages of up to 100 openings follow one another without pacing or retries until ``results``,
    the last opening, or an empty page. An opening that a later page repeats is kept once.

    Raises:
        Stopped: A request failed, UN Careers sent an unreadable response,
            or an empty page came before the reported total.
            ``partial`` holds the postings of the pages before it.
        ValueError: ``query`` and ``category`` are both given, ``max_age_hours`` is not one of the
            ages the site filters on, a filter value is not in the catalog,
            or ``results`` is below 1.
    """
    chosen = {
        option: values
        for option, values in {
            "category": category,
            "duty_station": duty_station,
            "level": level,
            "department": department,
            "job_network": job_network,
            "job_family": job_family,
            "recruitment_type": recruitment_type,
        }.items()
        if values
    }
    filters: dict[str, object] = {}
    if chosen:
        catalog = read_json(await fetcher.fetch(CATALOG_URL), _catalog, site="uncareers")
        filters |= {
            FILTERS[option]: _codes(option, catalog.get(FILTERS[option], []), values)
            for option, values in chosen.items()
        }
    if keyword := query.strip():
        filters["keyword"] = keyword
    if max_age_hours is not None:
        filters["span"] = [SPANS[max_age_hours]]
    logger.info("reading uncareers openings%s", f" with {filters}" if filters else "")
    return await collect("uncareers", _pages(fetcher, filters, min(PAGE_SIZE, results)), results)


__all__ = ["search"]
