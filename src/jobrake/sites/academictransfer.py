"""Search AcademicTransfer, a Dutch board for academic and research vacancies."""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from functools import partial
from typing import Annotated, Any
from urllib.parse import urlencode

lazy from bs4 import BeautifulSoup

from jobrake.fetchkit import Fetcher
from jobrake.models import JobDict, employment_type, make_job
from jobrake.sites.responses import collect, json_page, offset_pages, read_html, read_json
from jobrake.utils import as_int, as_str, checked, finite, html_text, menu_codes

logger = logging.getLogger(__name__)

# The jobs page embeds the public token its search script sends to the API, as an entry of its
# Nuxt payload (2026-11-17).
TOKEN_PAGE = "https://www.academictransfer.com/en/jobs/"
_TOKEN_KEY = "$satDataApiPublicAccessToken"
# The list API the jobs page reads, as AcademicTransfer served it on 2026-11-17. It answers 401
# without the token and at most 50 vacancies a page, whatever limit asks. Its robots.txt disallows
# every path, and the www site's allows every public one with Crawl-delay: 10.
SEARCH_URL = "https://api.academictransfer.com/vacancies/"
PAGE_SIZE = 50
# The Crawl-delay of the www site's robots.txt, in seconds, waited before each request to the API.
DELAY = 10
# The jobs page's tabs: academic, non-academic, and all vacancies.
VACANCY_TYPES = ("scientific", "non_scientific", "all")
# The labels the site's script gives the API's codes (2026-11-17).
_CONTRACT_TYPES = {1: "Permanent", 2: "Temporary"}
_EDUCATION_LEVELS = {
    1: "Doctorate",
    2: "University graduate",
    3: "Higher professional education +",
    4: "Higher professional education",
    5: "Secondary vocational higher level +",
    6: "Secondary vocational higher level",
    7: "Secondary vocational lower level +",
    8: "Secondary vocational lower level",
}
# The text fields about the position, in the order the API sends them. extra_info holds how to
# apply. The organization's and the department's descriptions are about the employer.
_SECTIONS = ("description", "requirements", "contract_terms", "additional_info", "extra_info")
_codes = partial(menu_codes, "AcademicTransfer")


def _validate(*, vacancy_type: str, **_: object) -> None:
    _codes("vacancy type", VACANCY_TYPES, [vacancy_type])


def _token(page: BeautifulSoup) -> str:
    """
    Return the public token a jobs page embeds.

    Raises:
        TypeError: The page holds no Nuxt payload or no token in it.
        ValueError: The payload is not JSON.
    """
    script = page.find("script", id="__NUXT_DATA__")
    if script is None:
        raise TypeError("the jobs page holds no Nuxt payload")
    # The Nuxt payload is a flat array whose objects reference values by index; negative indices
    # represent special devalue sentinels such as undefined.
    data = json.loads(script.get_text())
    holder = next((o for o in data if isinstance(o, dict) and _TOKEN_KEY in o), {})
    index = holder.get(_TOKEN_KEY)
    if not (type(index) is int and 0 <= index < len(data) and (token := as_str(data[index]))):
        raise TypeError("the jobs page holds no public API token")
    return token


def _given(value: object) -> float | None:
    # The API sends 0 for a salary or weekly hours a vacancy leaves out: 10 of the 53 academic
    # economics vacancies of 2026-11-17 had a salary of 0 to 0, and none named an amount in its
    # text.
    return finite(value) or None


def _parse_vacancy(vacancy: dict[str, Any]) -> JobDict:
    """
    Build a record from one vacancy of a search answer's ``results`` list.

    Raises:
        TypeError: The vacancy lacks an integer ``external_id``.
        AttributeError: The vacancy is not an object.
    """
    if (whole := as_int(vacancy.get("external_id"))) is None:
        raise TypeError(f"external_id {vacancy.get('external_id')!r} is not an integer")
    low, high = _given(vacancy.get("min_salary")), _given(vacancy.get("max_salary"))
    paid = low is not None or high is not None
    sections = (as_str(vacancy.get(name)) for name in _SECTIONS)
    return make_job(
        site="academictransfer",
        # The public number, which the vacancy's page URL carries.
        id=str(whole),
        url=vacancy.get("absolute_url"),
        title=vacancy.get("title"),
        company=vacancy.get("organisation_name"),
        locations=[{"city": vacancy.get("city"), "country_code": vacancy.get("country_code")}],
        department=as_str(vacancy.get("department_name")),
        description="\n\n".join(filter(None, (html_text(text) for text in sections if text))),
        language=as_str(vacancy.get("language_code")),
        employment_type=employment_type(_CONTRACT_TYPES.get(as_int(vacancy.get("contract_type")))),
        education=_EDUCATION_LEVELS.get(as_int(vacancy.get("education_level"))),
        # The API names no currency or period, so both are inferred from the vacancies' texts: of
        # the 43 academic economics vacancies of 2026-11-17 with a range, 36 named an amount in
        # euros a month in their text. None of them was outside the Netherlands.
        salary_min=low,
        salary_max=high,
        salary_currency="EUR" if paid else None,
        salary_period="MONTH" if paid else None,
        # The day the vacancy was published, which the site's "Published" order sorts by.
        posted_at=as_str(vacancy.get("start_date")),
        expires_at=as_str(vacancy.get("end_date")),
        apply_url=as_str(vacancy.get("application_url")),
        keywords=vacancy.get("keywords"),
        site_data={
            "min_weekly_hours": _given(vacancy.get("min_weekly_hours")),
            "max_weekly_hours": _given(vacancy.get("max_weekly_hours")),
        },
    )


def _pages(
    fetcher: Fetcher, params: dict[str, Any], token: str, limit: int
) -> AsyncGenerator[tuple[list[JobDict], int]]:
    """Yield each page's vacancies with the count AcademicTransfer reports, until its last match."""
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json; version=2"}

    async def read(offset: int) -> tuple[list[Any], int]:
        await asyncio.sleep(DELAY)
        page = urlencode(params | {"offset": offset, "limit": limit})
        result = await fetcher.fetch(f"{SEARCH_URL}?{page}", headers=headers)
        return read_json(
            result, lambda body: json_page(body, "results", "count"), site="academictransfer"
        )

    return offset_pages(read, _parse_vacancy, site="academictransfer")


@checked(validator=_validate)
async def search(
    fetcher: Fetcher,
    *,
    query: Annotated[str, "job title or keywords"] = "",
    vacancy_type: Annotated[str, "vacancy category: scientific, non_scientific, or all"] = "all",
    results: Annotated[int, "maximum number of postings"] = 100,
) -> list[JobDict]:
    """
    List the active vacancies on AcademicTransfer, newest first, each with its description.

    ``vacancy_type`` takes the jobs page's tab: ``scientific`` for academic vacancies,
    ``non_scientific`` for the others, or ``all``. A search reads the jobs page for the public token
    the site's search script sends, then pages through the list API up to 50 vacancies at a time,
    waiting ``DELAY`` seconds before each request to it, without retries.

    Raises:
        Stopped: A request failed, AcademicTransfer sent an unreadable page or answer, or an empty
            page came before the reported count. ``partial`` holds the postings of the pages before
            it.
        ValueError: ``vacancy_type`` is not one of the tabs, or ``results`` is below 1.
    """
    [kind] = _codes("vacancy type", VACANCY_TYPES, [vacancy_type])
    params: dict[str, Any] = {"vacancy_type": kind, "is_active": "true", "ordering": "-start_date"}
    if keyword := query.strip():
        params["search"] = keyword
    logger.info("searching AcademicTransfer for %r", query)
    token = read_html(await fetcher.fetch(TOKEN_PAGE), _token, site="academictransfer")
    pages = _pages(fetcher, params, token, min(PAGE_SIZE, results))
    return await collect("academictransfer", pages, results)


__all__ = ["search"]
