"""Read the listings on JOE, the American Economic Association's Job Openings for Economists."""

import html
import logging
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from functools import partial
from string import ascii_lowercase
from typing import Annotated
from urllib.parse import urlencode, urljoin

lazy from bs4 import BeautifulSoup

from jobrake.fetchkit import Fetcher
from jobrake.models import JobDict, make_job
from jobrake.sites.responses import parse_postings, read_html, read_xml
from jobrake.utils import checked, cutoff, iso_date, menu_codes

logger = logging.getLogger(__name__)

# The listings page and the export it links, as the JOE site served them on 2026-11-17. A plain GET
# of the page applies the form's fields given in its query, and its export link carries a token for
# that result. An export token built without the page got HTTP 500.
SEARCH_URL = "https://www.aeaweb.org/joe/listings"
LISTING_URL = "https://www.aeaweb.org/joe/listing.php?JOE_ID={id}"
# One page holds every listing of a search, so it shows each listing's posted date, which the export
# lacks. The cycle of 2026-11-17 listed 774.
PAGE_SIZE = 5000
# The page's Section/Type menu, as it listed the sections on 2026-11-17.
SECTIONS = {
    "1": "US: Full-Time Academic (Permanent, Tenure Track or Tenured)",
    "2": "US: Other Academic (Temporary, Adjunct, Visiting, Part-Time)",
    "2a": "US: Other Academic (Visiting or Temporary)",
    "2b": "US: Other Academic (Part-time or Adjunct)",
    "3": "International: Full-Time Academic (Permanent, Tenure Track or Tenured)",
    "4": "International: Other Academic (Temporary, Adjunct, Visiting, Part-Time)",
    "4a": "International: Other Academic (Visiting or Temporary)",
    "4b": "International: Other Academic (Part-time or Adjunct)",
    "5": "Full-Time Nonacademic",
    "6": "Other Nonacademic (Temporary, Part-Time, Non-Salaried, Consulting, Etc.)",
}
# The JEL Classifications menu takes 00 for a listing open to any field, and the JEL letters.
JEL_FIELDS = ("00", *"ABCDEFGHIJKLMNOPQRYZ")
# JOE answers an unknown code with no listings, so a search refuses one before its request.
_codes = partial(menu_codes, "AEA JOE")


def _validate(*, section: list[str] | None, jel: list[str] | None, **_: object) -> None:
    _codes("section", SECTIONS, section)
    _codes("JEL field", JEL_FIELDS, jel)


def _listings(page: BeautifulSoup) -> tuple[str | None, dict[str, str]]:
    """
    Return a listings page's absolute export link and each listing's posted date, newest first.

    Raises:
        TypeError: The page is not a listings page, or it shows postings without both their dates
            and an export link.
        ValueError: The export link is not an address urlsplit can read.
    """
    if page.select_one("form#ListingsForm") is None:
        raise TypeError("the page holds no listings form")
    dates = {}
    for header in page.select("h6.listing-item-header-title"):
        link = header.select_one("a[href*='JOE_ID=']")
        posted = header.find_next_sibling("div", class_="listing-item-header-date-posted")
        if link is None or posted is None:
            continue
        joe_id = str(link["href"]).partition("JOE_ID=")[2].partition("&")[0]
        day = posted.get_text().removeprefix("Date Posted:").strip()
        try:
            dates[joe_id] = datetime.strptime(day, "%m/%d/%Y").date().isoformat()
        except ValueError as error:
            raise TypeError(f"posted date {day!r} is not MM/DD/YYYY") from error
    export = page.select_one("a[href*='resultset_output.php?mode=full_xml']")
    if export is None and dates:
        raise TypeError("the page lists postings but links no export")
    if export is not None and not dates:
        raise TypeError("the page links an export but shows no posted dates")
    return (urljoin(SEARCH_URL, str(export["href"])) if export else None), dates


def _positions(root: ET.Element) -> list[tuple[str, ET.Element]]:
    """
    Return each position of the export with the ID of the JOE issue that lists it.

    Raises:
        TypeError: The document is not a JOE export.
    """
    if root.tag != "JOE_EXPORT":
        raise TypeError(f"the document's root is {root.tag}, not JOE_EXPORT")
    return [
        (f"{year.get('joe_year_ID')}-{(issue.get('joe_issue_ID') or '').zfill(2)}", position)
        for year in root.iter("year")
        for issue in year.iter("issue")
        for position in issue.iter("position")
    ]


def _text(element: ET.Element, tag: str) -> str | None:
    # The export escapes the text's entities twice, so &amp;amp; parses to &amp;.
    return html.unescape(element.findtext(tag) or "").strip() or None


def _parse_position(item: tuple[str, ET.Element], dates: dict[str, str]) -> JobDict:
    """
    Build a record from one position of the export.

    Raises:
        TypeError: The position lacks a numeric ``jp_id``.
    """
    issue, position = item
    number = position.get("jp_id") or ""
    if not number.isdigit():
        raise TypeError(f"jp_id {number!r} is not a number")
    joe_id = f"{issue}_{number}"
    places = []
    for location in position.iter("location"):
        city, region, country = (_text(location, tag) for tag in ("city", "state", "country"))
        # The export names the country in words, such as GERMANY, so it has no ISO code.
        name = ", ".join(part for part in (city, region, country) if part)
        places.append({"name": name, "city": city, "region": region})
    # The export writes a deadline with a midnight time, as in 2027-07-31 00:00:00, so expires_at
    # keeps the date alone. One that does not parse passes as written for make_job to warn and drop.
    deadline = _text(position, "jp_application_deadline")
    return make_job(
        site="aea",
        id=joe_id,
        url=LISTING_URL.format(id=joe_id),
        title=_text(position, "jp_title"),
        company=_text(position, "jp_institution"),
        locations=places,
        description=_text(position, "jp_full_text"),
        department=_text(position, "jp_department"),
        keywords=(_text(position, "jp_keywords") or "").splitlines(),
        posted_at=dates.get(joe_id),
        expires_at=iso_date(deadline) or deadline,
        site_data={
            "section": _text(position, "jp_section"),
            "division": _text(position, "jp_division"),
            "jel": [code for jel in position.iter("jel_class") if (code := _text(jel, "jc_code"))],
            # Free text, such as "Competitive" or a range in some currency.
            "salary_range": _text(position, "jp_salary_range"),
            # Set once the employer closes the search, such as "Position has been filled".
            "status": _text(position, "jp_status"),
        },
    )


@checked(validator=_validate)
async def search(
    fetcher: Fetcher,
    *,
    query: Annotated[str, "job title or keywords"] = "",
    max_age_hours: Annotated[int | None, "maximum posting age in hours, by posting day"] = None,
    section: Annotated[list[str] | None, "section, e.g., 1 or 'Full-Time Nonacademic'"] = None,
    jel: Annotated[list[str] | None, "JEL field, e.g., J or Q"] = None,
) -> list[JobDict]:
    """
    List the active listings on JOE, newest first, each with its full text.

    ``section`` takes a code or a name of the site's Section/Type menu, where the heading 2 or 4
    also selects its subsections, and ``jel`` a JEL field code, in any case. Each keeps the
    listings that match any of its values, and different filters all apply. JOE dates a listing by
    day, so ``max_age_hours`` keeps those posted on or after the UTC date that many hours ago, and
    JOE compares it with its own calendar.
    One request reads the listings page with the search's filters, for each listing's posted date
    and the link to the page's export, and a second reads that export. Neither is paced or retried.

    Raises:
        Stopped: A request failed or JOE sent a page or export that cannot be read.
            ``partial`` is empty.
        ValueError: A ``section`` or ``jel`` value names no entry of the site's menus.
    """
    fields = {"ListingsForm[lpp]": PAGE_SIZE, "ListingsForm[listings_order_by]": "date_posted_a"}
    if keyword := query.strip():
        fields["ListingsForm[keyword_search]"] = keyword
    # JOE files each listing under a subsection such as 2a and answers the heading 2 alone with no
    # listings (measured 2026-11-17), so a heading also sends its subsections.
    sections = [
        sub
        for code in _codes("section", SECTIONS, section)
        for sub in SECTIONS
        if code in (sub, sub.rstrip(ascii_lowercase))
    ]
    for name, codes in (("section", sections), ("jel", _codes("JEL field", JEL_FIELDS, jel))):
        fields |= {
            f"ListingsForm[{name}][{i}]": code for i, code in enumerate(dict.fromkeys(codes))
        }
    if since := cutoff(max_age_hours):
        fields |= {
            "ListingsForm[recent_only][0][option]": "date_range",
            "ListingsForm[recent_only][0][from]": f"{since:%m/%d/%Y}",
            "ListingsForm[recent_only][0][to]": f"{datetime.now(UTC):%m/%d/%Y}",
        }
    logger.info("reading the AEA JOE listings page")
    page = await fetcher.fetch(f"{SEARCH_URL}?{urlencode(fields)}")
    export, dates = read_html(page, _listings, site="aea")
    if export is None:
        return []
    logger.info("reading the AEA JOE export of %d listings", len(dates))
    positions = read_xml(await fetcher.fetch(export), _positions, site="aea")
    jobs = parse_postings(positions, partial(_parse_position, dates=dates), site="aea")
    if undated := sum(job["date"] is None for job in jobs):
        logger.warning(
            "%d AEA JOE listings of the export are missing from the listings page", undated
        )
    order = {joe_id: rank for rank, joe_id in enumerate(dates)}
    return sorted(jobs, key=lambda job: order.get(job["id"], len(order)))


__all__ = ["search"]
