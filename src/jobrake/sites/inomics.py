"""Search the economics postings on INOMICS."""

import functools
import logging
import re
from typing import Annotated, Any
from urllib.parse import urlencode, urlsplit

lazy from bs4 import BeautifulSoup, Tag

from jobrake.fetchkit import Fetcher
from jobrake.models import JobDict, Stopped, make_job, workplace_type
from jobrake.sites.postings import fill_details, postings_of
from jobrake.sites.responses import json_ld, parse_postings, read_html, read_json
from jobrake.utils import as_dict, as_str, checked, html_text, menu_codes

logger = logging.getLogger(__name__)

# The endpoint the search page's script reads its results from, as INOMICS served it on 2026-11-17.
# It answers with Drupal AJAX commands. With orderBy=relevance, trendingPage=N holds the first
# 20 * N cards, which is how the page's "load more" button pages. In the afternoon of 2026-11-17
# its page=N parameter served the first page for every N when sorted by date, and unsorted it
# repeated page 0 at page 1, so pages 0 to 5 reached 92 of 112 postings.
SEARCH_URL = "https://inomics.com/ajax/filter"
# Drupal wraps its AJAX answer in a <textarea> for a client whose Accept header puts HTML first.
API_HEADERS = {"Accept": "application/json"}
CARDS_PER_PAGE = 20
# A posting page answers at its ID alone, without the slug of the search card's link.
POSTING_URL = "https://inomics.com/job/{id}"
# The Job Type menu of the search page, as it listed the categories on 2026-11-17. The site's slug
# of each is its code after job-, spelled as the site spells it.
CATEGORIES = {
    "administration": "Administration",
    "asst-prof-lecturer": "Assistant Professor / Lecturer",
    "graduate": "Graduate / Traineeship",
    "internship": "Internship",
    "junior-industry": "Junior Industry Position",
    "mid-level-industry": "Mid-Level Industry Position",
    "other": "Other Jobs",
    "phd-candidate": "PhD Candidate",
    "postdoc": "Postdoc",
    "practicioner": "Practitioner / Consultant",
    "professor": "Professor",
    "research-assistant": "Research Assistant / Technician",
    "researcher": "Researcher / Analyst",
    "senior-industry": "Executive / Senior Industry Position",
    "senior-reasercher": "Senior Researcher / Group Leader",
}
# The Disciplines menu's economics fields, each labeled with its JEL letter, such as
# "Labor and Demographic Economics (JEL J)" (2026-11-17).
JEL_FIELDS = {
    "A": "generaleconomics",
    "B": "economicthoughtmethodology",
    "C": "econometricsstatisticsquantitative",
    "D": "microeconomics",
    "E": "macroeconomicsmonetary",
    "F": "internationaleconomics",
    "G": "financialeconomics",
    "H": "publiceconomicspolicy",
    "I": "healtheducationwelfareeconomics",
    "J": "labordemographiceconomics",
    "K": "laweconomics",
    "L": "industrialorganization",
    "M": "businesseconomics",
    "N": "economichistory",
    "O": "economicdevelopmentgrowth",
    "P": "economicsystems",
    "Q": "agriculturalenvironmentaleconomics",
    "R": "urbanruraltransportationeconomics",
    "Z": "othereconomics",
}
# A posting page's schema.org blocks: JobPosting, or EducationalOccupationalProgram for a posting
# INOMICS also lists as a scholarship.
_POSTING_TYPES = {"JobPosting", "EducationalOccupationalProgram"}
_JOB_PATH = re.compile(r"/job/(?:[^/]*-)?([0-9]+)/?")
_DAY = re.compile(r"^\d\d-\d\d-\d{4}$")  # a card's posted day, such as 16-11-2026
_HOSTS = {"inomics.com", "www.inomics.com"}
# INOMICS answers an unknown value with no results, so a search refuses one before its request.
# JEL_FIELDS maps each letter to the site's slug, so its keys alone are the spellings to match.
_codes = functools.partial(menu_codes, "INOMICS")


def _validate(
    *, country: str | None, category: list[str] | None, jel: list[str] | None, **_: object
) -> None:
    if country is not None and not re.fullmatch(r"[A-Za-z]{2}", country.strip()):
        raise ValueError(
            f"country {country!r} is not an ISO 3166-1 alpha-2 code. Pass one such as de"
        )
    _codes("category", CATEGORIES, category)
    _codes("JEL field", JEL_FIELDS.keys(), jel)


def _cards(commands: list[dict[str, Any]]) -> tuple[list[Tag], int]:
    """
    Return the cards of a search answer and the count of all its matches.

    Raises:
        TypeError: The answer lacks the count.
        KeyError: A command lacks its data.
        AttributeError: A command is not an object.
    """
    count = next((c["data"] for c in commands if c.get("selector") == "#filter-count-number"), None)
    total = BeautifulSoup(count or "", "html.parser").get_text(strip=True)
    if not total.isdigit():
        raise TypeError(f"the answer holds no result count, only {count!r}")
    # The first command sets the content, and each later one appends 20 more cards.
    content = "".join(
        command["data"]
        for command in commands
        if command.get("selector") == "#block-venice-content"
    )
    return BeautifulSoup(content, "html.parser").select("ul.posts > li"), int(total)


def _parse_card(card: Tag) -> JobDict:
    """
    Build a record from one card of a search answer.

    Raises:
        TypeError: The card links no posting page, or it lacks its title or its information line.
    """
    link = card.select_one("a.post-link[href]")
    match = _JOB_PATH.fullmatch(str(link["href"])) if link else None
    if match is None:
        raise TypeError("the card links no posting page")
    title, info = card.select_one("h2"), card.select_one("span.informations")
    if title is None or info is None:
        raise TypeError("the card lacks its title or its information line")
    # The employers come first, each in a span.location of its own, then the place, a
    # span.location.bold that holds a span for the city, when given, and one for the country.
    employers = info.find_all("span", class_="location", recursive=False)
    place = info.select_one("span.location.bold")
    parts = [span.get_text(strip=True) for span in place.find_all("span")] if place else []
    posted = info.find("span", attrs={"content": _DAY}, recursive=False)
    badge = card.select_one("span.type-badge")
    # A hybrid or remote posting's card says "(Hybrid)" or "(Remote)" there.
    attendance = card.select_one("li.attendance")
    mode = attendance.get_text(strip=True).strip("()") if attendance else None
    return make_job(
        site="inomics",
        id=match[1],
        url=POSTING_URL.format(id=match[1]),
        title=title.get_text(strip=True),
        company=employers[0].get_text(strip=True) if employers else None,
        locations=[{"name": ", ".join(parts), "city": parts[0] if len(parts) > 1 else None}],
        # 16-11-2026 becomes 2026-11-16.
        posted_at="-".join(reversed(str(posted["content"]).split("-"))) if posted else None,
        workplace_type=workplace_type(mode),
        site_data={"types": badge.get_text(strip=True).split(", ") if badge else None},
    )


def _place(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Read the place a posting page's schema.org blocks give, which may have no part.

    The block dated 2026/11/13 names the place as "city, country" with the country's ISO code, and
    the other names the city and region. A page without the first gives the city and region of the
    second, and a page without the second gives a place without its city.
    """
    addresses = [as_dict(as_dict(block.get("jobLocation")).get("address")) for block in blocks]
    labeled = next((a for a in addresses if as_str(a.get("addressCountry"))), {})

    def part(key: str, among: list[dict[str, Any]]) -> str | None:
        return next((text for address in among if (text := as_str(address.get(key)))), None)

    city = part("addressLocality", [a for a in addresses if a is not labeled])
    return {
        "name": as_str(labeled.get("addressLocality")) or city,
        "city": city,
        "region": part("addressRegion", addresses),
        "country_code": as_str(labeled.get("addressCountry")),
    }


def _parse_page(page: BeautifulSoup) -> dict[str, Any]:
    """
    Read a posting page into a whole record's fields.

    The page carries one or two schema.org blocks, and the first non-empty value of a field wins.
    One block dates the posting as 2026/11/13, and the other dates it in ISO 8601.
    The blocks' descriptions are excerpts, so the description is the page's own text.

    Raises:
        TypeError: The page holds no posting block or no description.
    """
    blocks = json_ld(page, _POSTING_TYPES)
    description = page.select_one("div.post-description")
    if not blocks or description is None:
        raise TypeError("the page holds no posting block or no description")
    # The block dated 2026/11/13 goes first. Its datePosted was the day the search card shows, the
    # posting's last repost, on all 17 pages that carried it on 2026-11-17, and the other block's is
    # the day the posting was entered. A posting INOMICS also lists as a scholarship has only the
    # other block.
    blocks.sort(key=lambda block: "/" not in str(block.get("datePosted")))

    def first(*path: str) -> str | None:
        for block in blocks:
            value: Any = block
            for key in path:
                value = as_dict(value).get(key)
            if text := as_str(value):
                return text
        return None

    def day(name: str) -> str | None:
        # 2026/11/13 becomes ISO 8601, and an ISO timestamp stays as it is.
        return (first(name) or "").replace("/", "-") or None

    return {
        "title": first("title"),
        "company": first("hiringOrganization", "name"),
        "locations": [_place(blocks)],
        "description": html_text(str(description)),
        "posted_at": day("datePosted"),
        "expires_at": day("validThrough"),
    }


async def _posting_fields(fetcher: Fetcher, url: str) -> dict[str, Any] | None:
    """
    Fetch the posting page at a URL and read it, or None when INOMICS reports the posting gone.

    An unknown ID answers 404 and a removed posting 410.

    Raises:
        Stopped: The request failed, or the page cannot be read.
    """
    result = await fetcher.fetch(url)
    if result.status in (404, 410):
        return None
    return read_html(result, _parse_page, site="inomics")


@checked(validator=_validate)
async def search(
    fetcher: Fetcher,
    *,
    query: Annotated[str, "job title or keywords"] = "",
    country: Annotated[str | None, "ISO 3166-1 alpha-2 country code, e.g., de"] = None,
    category: Annotated[list[str] | None, "posting category, e.g., postdoc or Professor"] = None,
    jel: Annotated[list[str] | None, "JEL field, e.g., J or Q"] = None,
    results: Annotated[int, "maximum number of postings"] = 100,
    details: Annotated[bool, "fetch each posting for its description"] = False,
) -> list[JobDict]:
    """
    Search the postings on INOMICS and list them in the site's order of relevance.

    INOMICS applies every option. ``category`` takes a category of the site's Job Type menu by its
    name or its code, and ``jel`` the letter of a JEL field the site's Disciplines menu lists, in
    any case. Each keeps the postings that match any of its values, and different options all apply.
    One request reads the first ``results`` cards, without pacing or retries. A card lacks the
    description and the deadline, so ``details`` fetches each posting's page with one more request,
    which a cached posting skips.

    Raises:
        Stopped: The request failed or INOMICS sent an answer that cannot be read, and ``partial``
            is empty. INOMICS sent fewer cards than it counted, and ``partial`` holds them.
            With ``details``, a posting's page could not be fetched, and ``partial`` holds every
            posting, filled where its fetch succeeded, and ``failed`` the URLs of the others.
        ValueError: ``country`` is not an alpha-2 code, a ``category`` or ``jel`` value names no
            entry of the site's menus, or ``results`` is below 1.
    """
    categories = [f"job-{code}" for code in _codes("category", CATEGORIES, category)]
    fields = [JEL_FIELDS[letter] for letter in _codes("JEL field", JEL_FIELDS.keys(), jel)]
    params: dict[str, Any] = {
        # job=job asks for every category.
        "job": ",".join(dict.fromkeys(categories)) or "job",
        "orderBy": "relevance",
        # Ceiling division in integers, so a ``results`` beyond float range does not overflow.
        "trendingPage": -(-results // CARDS_PER_PAGE),
    }
    if keyword := query.strip():
        params["textsearch"] = keyword
    # INOMICS takes the code in upper case only: country=de matched no posting on 2026-11-17.
    if country:
        params["country"] = country.strip().upper()
    if fields:
        params["economics"] = ",".join(dict.fromkeys(fields))
    logger.info("searching inomics for %r", query)
    result = await fetcher.fetch(f"{SEARCH_URL}?{urlencode(params)}", headers=API_HEADERS)
    cards, total = read_json(result, _cards, site="inomics")
    jobs = parse_postings(cards, _parse_card, site="inomics")[:results]
    if len(cards) < min(results, total):
        raise Stopped(
            f"inomics counted {total} postings but sent {len(cards)}, so the result may be "
            "incomplete. A rerun reads the current list",
            partial=jobs,
        )
    return await fill_details(fetcher, jobs, _posting_fields) if details else jobs


def card(reference: str) -> JobDict:
    """
    Read an INOMICS posting URL as the card it names, for ``postings`` and ``identify``.

    Raises:
        ValueError: The reference is not a posting URL on inomics.com.
    """
    parts = urlsplit(reference.strip())
    hosted = parts.scheme in ("http", "https") and parts.netloc.lower() in _HOSTS
    if not (hosted and (match := _JOB_PATH.fullmatch(parts.path))):
        raise ValueError(
            f"{reference!r} is not an INOMICS posting URL. Pass a record's url, such as "
            "https://inomics.com/job/1555182"
        )
    return make_job(site="inomics", id=match[1], url=POSTING_URL.format(id=match[1]))


postings = postings_of(card, _posting_fields)


__all__ = ["postings", "search"]
