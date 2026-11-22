"""Read job openings from UN Careers, the United Nations Secretariat's recruitment site."""

import difflib
import itertools
import logging
from collections.abc import AsyncGenerator
from typing import Annotated, Any

from jobrake.fetchkit import Fetcher
from jobrake.models import JobDict, Stopped, make_job
from jobrake.sites.responses import collect, json_list, json_page, offset_pages, read_json
from jobrake.utils import as_dict, as_int, as_list, as_str, checked, html_text

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


def _parse_opening(opening: dict[str, Any]) -> JobDict:
    """
    Build a record from one opening of the list.

    Raises:
        TypeError: The opening lacks an integer ``jobId``.
        AttributeError: The opening is not an object.
    """
    if (job_id := as_int(opening.get("jobId"))) is None:
        raise TypeError(f"jobId {opening.get('jobId')!r} is not an integer")
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
            for station in as_list(opening.get("dutyStation"))
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


def _pages(
    fetcher: Fetcher, config: dict[str, object], size: int
) -> AsyncGenerator[tuple[list[JobDict], int]]:
    numbers = itertools.count()  # the API pages by number, one per request

    async def read(_offset: int) -> tuple[list[Any], int]:
        body = {
            "filterConfig": config,
            "pagination": {
                "page": next(numbers),
                "itemPerPage": size,
                # Many openings share a start date, and the site orders them differently from one
                # request to the next, so pages sorted by date repeated 11 openings of 448 and
                # skipped 11 others (measured 2026-11-16). Job IDs are unique.
                "sortBy": "jobId",
                "sortDirection": -1,
            },
        }
        result = await fetcher.fetch(SEARCH_URL, json=body)
        return read_json(
            result, lambda payload: json_page(payload["data"], "list", "count"), site="uncareers"
        )

    return offset_pages(read, _parse_opening, site="uncareers")


def _entries(items: object, code: str, name: str) -> list[tuple[str, str]]:
    """Return the ``(code, name)`` pairs of catalog entries, skipping an incomplete one."""
    return [
        (key, label)
        for entry in map(as_dict, as_list(items))
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
                for network in map(as_dict, as_list(values))
                for family in _entries(network.get("jobFamilies"), "Code", "Name")
            ]
    catalog["jf"] = families
    return catalog


async def _read_catalog(fetcher: Fetcher) -> dict[str, list[tuple[str, str]]]:
    return read_json(await fetcher.fetch(CATALOG_URL), _catalog, site="uncareers")


def _cli_name(option: str) -> str:
    """Return a filter option as the CLI spells it, such as ``duty-station``."""
    return option.replace("_", "-")


def _values(catalog: dict[str, list[tuple[str, str]]], option: str) -> list[tuple[str, str]]:
    """
    Return the ``(code, name)`` entries the catalog lists for a filter option.

    Raises:
        Stopped: The catalog lists no entries for the filter.
    """
    if entries := catalog.get(FILTERS[option]):
        return entries
    raise Stopped(
        f"UN Careers sent a filter catalog without {option.replace('_', ' ')} values, "
        f"likely an API change, so jobrake cannot use the {_cli_name(option)} filter"
    )


def _codes(option: str, entries: list[tuple[str, str]], values: list[str]) -> list[str]:
    """
    Return the codes of the catalog entries whose code or name is one of ``values``, in any case.

    Raises:
        ValueError: A value names no entry. The message lists close names.
    """
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
                else f"List them with 'jobrake uncareers filters {_cli_name(option)}'"
            )
            raise ValueError(f"unknown UN Careers {option.replace('_', ' ')} {value!r}. {hint}")
        codes |= found
    return sorted(codes)


def _validate(*, query: str, category: list[str] | None, **_: object) -> None:
    # A category makes the site drop the keyword, though every other filter combines with it
    # (measured 2026-11-16).
    if query.strip() and category:
        raise ValueError(
            "UN Careers ignores query when category is given, so pass one of them and filter the "
            "results on the other"
        )


@checked(validator=_validate)
async def search(
    fetcher: Fetcher,
    *,
    query: Annotated[str, "job title or keywords"] = "",
    results: Annotated[int, "maximum number of postings"] = 100,
    max_age_hours: Annotated[int | None, "maximum posting age in hours, rounded up to days"] = None,
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
    only. ``query`` cannot be combined with ``category``. UN Careers filters posting age in whole
    days, so ``max_age_hours`` keeps the openings whose start date falls within that many hours
    rounded up to whole days.
    Pages of up to 100 openings follow one another without pacing or retries until ``results``,
    the last opening, or an empty page. An opening that a later page repeats is kept once.

    Raises:
        Stopped: A request failed, UN Careers sent an unreadable response,
            or an empty page came before the reported total.
            ``partial`` holds the postings of the pages before it.
        ValueError: ``query`` and ``category`` are both given, a filter value is not in the
            catalog, or ``results`` or ``max_age_hours`` is below 1.
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
    config: dict[str, object] = {}
    if chosen:
        catalog = await _read_catalog(fetcher)
        config |= {
            FILTERS[option]: _codes(option, _values(catalog, option), values)
            for option, values in chosen.items()
        }
    if keyword := query.strip():
        config["keyword"] = keyword
    if max_age_hours is not None:
        # The site's Date Posted filter keeps the openings whose startDate lies within span days of
        # now. Its menu offers 1, 7, and 30, but it takes any whole number and truncates a fraction
        # (measured 2026-11-17), so the hours round up to whole days in integer arithmetic.
        config["span"] = [str(-(-max_age_hours // 24))]
    logger.info("reading UN Careers openings%s", f" with {config}" if config else "")
    return await collect("uncareers", _pages(fetcher, config, min(PAGE_SIZE, results)), results)


def _filter_option(option: str) -> str:
    return option.strip().replace("-", "_")


def _validate_filters(*, option: str) -> None:
    if _filter_option(option) not in FILTERS:
        names = ", ".join(map(_cli_name, FILTERS))
        raise ValueError(f"UN Careers search has no {option!r} list filter. Use one of {names}")


@checked(validator=_validate_filters)
async def filters(
    fetcher: Fetcher, option: Annotated[str, "list filter, e.g., duty-station"]
) -> list[dict[str, str]]:
    """
    List the values a UN Careers list filter takes, in the order of the site's filter catalog.

    ``option`` is a list option of ``search``, with ``-`` or ``_``. Each value is an
    ``{"id", "name"}`` dict, and ``search`` takes either one. A code can carry two names,
    such as level 300, NO-2 and NO-B.

    Raises:
        Stopped: The request failed, UN Careers sent an unreadable catalog,
            or the catalog lists no values for the filter.
        ValueError: ``option`` names no list option of ``search``.
    """
    entries = _values(await _read_catalog(fetcher), _filter_option(option))
    return [{"id": code, "name": name} for code, name in entries]


__all__ = ["filters", "search"]
