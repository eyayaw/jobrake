"""LinkedIn posting details from schema.org data and page markup."""

import contextlib
import functools
import logging
import re
from html import unescape
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit, urlunsplit

lazy from bs4 import BeautifulSoup

from jobrake.fetchkit import Fetcher, FetchResult
from jobrake.models import JobDict, Place, Stopped, employment_type, make_job, make_places
from jobrake.sites.postings import Halt, postings_of
from jobrake.sites.responses import json_ld
from jobrake.utils import as_dict, finite, html_text

from .client import (
    EN_US_QUERY,
    FABRICS_WANTED,
    FRAGMENT_URL,
    job_id,
    numeric,
    on_linkedin,
    paced_fetch,
)

logger = logging.getLogger(__name__)


# schema.org fields may be a scalar, a list, or a value in the wrong shape. For list-valued fields,
# LinkedIn's first item is the one we use.
def _first(value: object) -> object:
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _obj(value: object) -> dict[str, Any]:
    return as_dict(_first(value))


def _text_value(value: object) -> str | None:
    """Read a schema.org string, decoding the entities its script block escaped."""
    # LinkedIn HTML-escapes the JSON it embeds in the page, and entities inside a script element
    # reach the parser undecoded. A logo URL arrives with "&amp;" between its query parameters and
    # description markup as "&lt;p&gt;".
    text = _first(value)
    return unescape(text) if isinstance(text, str) else None


def _number_value(value: object) -> float | None:
    return finite(_first(value))


def _tag_text(soup: BeautifulSoup, selector: str) -> str | None:
    """Read the text of the first element matching a selector."""
    node = soup.select_one(selector)
    return node.get_text(strip=True) if node else None


def _description(soup: BeautifulSoup) -> str:
    div = soup.find("div", class_=lambda c: bool(c and "show-more-less-html__markup" in c))
    return html_text(div.decode_contents()) if div else ""


def _criteria(soup: BeautifulSoup) -> dict[str, str]:
    """Index LinkedIn criteria rows by their displayed labels."""
    pairs = {}
    for item in soup.select(".description__job-criteria-item"):
        label = item.select_one(".description__job-criteria-subheader")
        value = item.select_one(".description__job-criteria-text")
        if label and value:
            pairs[label.get_text(strip=True)] = value.get_text(strip=True)
    return pairs


_SALARY_BOUND = re.compile(r"([A-Z]{3})\s?(\d[\d,]*(?:\.\d+)?)/(yr|mo|wk|day|hr)")
_SALARY_PERIODS = {"yr": "YEAR", "mo": "MONTH", "wk": "WEEK", "day": "DAY", "hr": "HOUR"}


def _salary(soup: BeautifulSoup) -> dict[str, Any]:
    """
    Parse a two-bound en-US salary range from topcard markup.

    Both bounds must use the same currency code and supported period. Currency symbols,
    localized formats, single bounds, and unreadable numbers yield ``{}``.
    """
    node = soup.select_one(".compensation__salary")
    bounds = _SALARY_BOUND.findall(node.get_text()) if node else []
    if len(bounds) != 2:
        return {}
    (currency, low, period), (currency_2, high, period_2) = bounds
    if (currency, period) != (currency_2, period_2):
        return {}
    # A digit run past float range converts to infinity rather than raising.
    salary_min = finite(float(low.replace(",", "")))
    salary_max = finite(float(high.replace(",", "")))
    if salary_min is None or salary_max is None:
        return {}
    return {
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_currency": currency,
        "salary_period": _SALARY_PERIODS[period],
    }


def _company(soup: BeautifulSoup) -> dict[str, Any]:
    """Extract company URL and logo fields from topcard markup."""
    link = soup.select_one("a.topcard__org-name-link")
    logo = soup.select_one("img.artdeco-entity-image")
    return {
        "company_url": str(link["href"]).partition("?")[0] if link and link.get("href") else None,
        "company_logo": logo.get("data-delayed-url") if logo else None,
    }


def _apply_type(soup: BeautifulSoup) -> str | None:
    """
    Return the apply kind the page's apply link names.

    LinkedIn names its own form ``onsite`` and an employer's ``offsite``.
    """
    for element in soup.select("[data-tracking-control-name*='apply-link-']"):
        if found := re.search(r"apply-link-([a-z]+)", str(element["data-tracking-control-name"])):
            return found.group(1)
    return None


def _applicants(soup: BeautifulSoup) -> int | None:
    # The prose around it is localized, but the number is not.
    # LinkedIn displays counts above 200 as "Over 200", so no thousands separator appears.
    caption = soup.select_one(".num-applicants__caption")
    found = re.search(r"\d+", caption.get_text()) if caption else None
    try:
        return int(found.group()) if found else None
    except ValueError:
        # Past Python's limit of 4,300 digits, which no count of applicants reaches.
        return None


def _block_places(posting: dict[str, Any]) -> list[dict[str, Any]]:
    """Read the parts of each schema.org ``jobLocation``, one place per entry."""
    entries = posting.get("jobLocation")
    places = []
    for place in entries if isinstance(entries, list) else [entries]:
        if not isinstance(place, dict):
            continue
        address = _obj(place.get("address"))
        # addressCountry is Text or a Country object carrying its name.
        country = address.get("addressCountry")
        places.append(
            {
                "city": _text_value(address.get("addressLocality")),
                "region": _text_value(address.get("addressRegion")),
                "country_code": _text_value(country) or _text_value(_obj(country).get("name")),
                "latitude": _number_value(place.get("latitude")),
                "longitude": _number_value(place.get("longitude")),
            }
        )
    return places


def _parse_posting(soup: BeautifulSoup) -> dict[str, Any]:
    """
    Extract model fields from a posting page.

    A posting page carries the summary fields alongside the details, so one page is enough to build
    a record without a search card. Page markup fills fields absent from the schema.org block,
    which LinkedIn omits for country-level postings on every subdomain. Structured values win when
    both sources provide a field. Unsupported or malformed values are omitted.
    """
    posting = next(iter(json_ld(soup, {"JobPosting"})), {})
    org = _obj(posting.get("hiringOrganization"))
    pay = _obj(posting.get("baseSalary"))
    amount = _obj(pay.get("value"))
    # The topcard bullets hold the place, the posting age, and the applicant count.
    # Age and count also carry the metadata class, so the plain bullet is the place.
    label = _tag_text(soup, ".topcard__flavor--bullet:not(.topcard__flavor--metadata)")
    # Places count once normalized, so a block of empty entries holds none.
    places = make_places(_block_places(posting))
    # A lone block place is the place the bullet names when the bullet holds its city.
    # A bullet that names another city stands as a place of its own, and several block places keep
    # the names of their parts.
    city = places[0].get("city", "") if len(places) == 1 else ""
    if len(places) == 1 and label and city.casefold() in label.casefold():
        places = [{**places[0], "name": label}]
    elif len(places) < 2 and label:
        places = [Place(name=label), *places]
    # JobDict counts whole months.
    months = _number_value(_obj(posting.get("experienceRequirements")).get("monthsOfExperience"))
    from_block = {
        "title": _text_value(posting.get("title")),
        "company": _text_value(org.get("name")),
        "description": html_text(_text_value(posting.get("description")) or ""),
        "employment_type": employment_type(_text_value(posting.get("employmentType"))),
        "posted_at": _text_value(posting.get("datePosted")),
        "expires_at": _text_value(posting.get("validThrough")),
        "company_url": _text_value(org.get("sameAs")),
        "company_logo": _text_value(_obj(org.get("logo")).get("url") or org.get("logo")),
        "locations": places,
        "salary_min": _number_value(amount.get("minValue")),
        "salary_max": _number_value(amount.get("maxValue")),
        "salary_currency": _text_value(pay.get("currency")),
        "salary_period": _text_value(amount.get("unitText")),
        "experience_months": months if isinstance(months, int) else None,
        "education": _text_value(
            _obj(posting.get("educationRequirements")).get("credentialCategory")
        ),
    }
    # Only markup supplies apply_type and applicants, or any field when the page lacks
    # schema.org data.
    from_markup = {
        "title": _tag_text(soup, ".topcard__title"),
        "company": _tag_text(soup, "a.topcard__org-name-link"),
        "description": _description(soup),
        "employment_type": employment_type(_criteria(soup).get("Employment type")),
        **_company(soup),
        **_salary(soup),
        "apply_type": _apply_type(soup),
        "applicants": _applicants(soup),
        # LinkedIn keeps serving a posting that stopped taking applications and marks its top card
        # with this figure (measured 2026-10-21 on two postings).
        "site_data": {"closed": True} if soup.select_one("figure.closed-job") else None,
    }
    return {
        name: value
        for source in (from_markup, from_block)
        for name, value in source.items()
        if value not in (None, "", [])
    }


def _canonical(url: str) -> str:
    """Reduce a posting URL to its page address, without a query, a fragment, or a trailing slash."""
    # A trailing slash returns the same full page without its schema.org script.
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=parts.path.rstrip("/"), query="", fragment=""))


_PAGE_PATH = "/jobs/view/"
_WWW_HOSTS = ("linkedin.com", "www.linkedin.com")
# The addresses a caller may name a posting by: its page, or the same posting under the guest
# API's own path.
_REFERENCE_PATHS = (_PAGE_PATH, f"{urlsplit(FRAGMENT_URL).path}/")


def _posting_url(url: str, posting_id: str, paths: tuple[str, ...]) -> bool:
    """Check that a URL is one of LinkedIn's addresses for one posting."""
    return on_linkedin(url) and urlsplit(url).path.startswith(paths) and job_id(url) == posting_id


def _fragment_url(html: str, posting_id: str) -> str:
    """
    Read the posting URL a guest fragment names.

    LinkedIn writes the canonical URL here, on ``www`` for a US posting.

    Raises:
        Stopped: The link is missing or points at another posting.
    """
    link = BeautifulSoup(html, "html.parser").select_one("a.topcard__link[href]")
    if link is None:
        raise Stopped(
            "its guest fragment names no posting URL, so LinkedIn's markup may have changed. "
            "Its posting URL may still work"
        )
    url = str(link["href"]).partition("?")[0]
    if not _posting_url(url, posting_id, (_PAGE_PATH,)):
        raise Stopped(f"its guest fragment points at {url}, which is not that posting's page")
    return url


async def _request(fetcher: Fetcher, url: str) -> FetchResult | None:
    """
    Return the response, or None when LinkedIn reports the posting gone with HTTP 404 or 410.

    Raises:
        Stopped: The request failed.
        Halt: paced_fetch spent its retries on a 429.
    """
    result = await paced_fetch(fetcher, url)
    if result.status == 429:
        # paced_fetch has spent its retries, so the next posting would likely be refused too.
        # Stop instead of repeating them for every remaining posting.
        raise Halt(
            "linkedin is rate limiting this IP. Wait a while, then rerun to fill in the rest"
        )
    if result.status in (404, 410):
        return None
    # A posting page comes with HTTP 200, as the shared readers require of every site's data.
    if result.error or result.status != 200:
        raise Stopped(result.error or f"HTTP {result.status}")
    return result


async def _page(
    fetcher: Fetcher, posting_id: str, url: str, *, candidate: bool = False
) -> tuple[str, dict[str, Any]] | None:
    """
    Read a posting page, following its canonical link to another address once, and parse its fields.

    Return None for a gone posting, and no fields for an unrelated redirect.

    Raises:
        Stopped: The page's canonical link rules it out, or the page yields no fields.
    """
    for _ in range(2):
        result = await _request(fetcher, f"{url}{EN_US_QUERY}")
        if result is None:
            return None
        if not _posting_url(result.url, posting_id, (_PAGE_PATH,)):
            return url, {}
        url = _canonical(result.url)
        soup = BeautifulSoup(result.text, "html.parser")
        # Measured 2026-11-07: www pages name the posting country's canonical URL here even when
        # they omit its schema.org fields.
        link = soup.select_one('link[rel="canonical"][href]')
        if link is not None:
            canonical = str(link["href"])
            if not _posting_url(canonical, posting_id, (_PAGE_PATH,)):
                raise Stopped(
                    f"its page names {canonical} as canonical, which is not that posting's "
                    "page, so LinkedIn may have replaced the posting or changed its markup"
                )
            # Measured 2026-11-10: a renamed posting still answers at its old slug,
            # without its schema.org fields, and names the new slug here. Decoded,
            # two spellings of one address are equal, such as a raw "ö" and "%C3%B6".
            canonical = _canonical(canonical)
            if unquote(canonical) != unquote(url):
                url, candidate = canonical, False
                continue
        elif candidate and urlsplit(url).hostname in _WWW_HOSTS:
            raise Stopped(f"its page at {url} names no canonical address")
        if not (fields := _parse_posting(soup)):
            raise Stopped(
                f"its page at {url} yielded no fields, so it may be a signup wall or changed markup"
            )
        return url, fields
    raise Stopped(
        f"its canonical page names another canonical address, {url}, so LinkedIn's pages "
        "for it may point at each other"
    )


async def _resolve_page(
    fetcher: Fetcher, posting_id: str, url: str | None, *, candidate: bool = False
) -> tuple[str, dict[str, Any], FetchResult | None] | None:
    """Find the canonical page and retain any guest fragment fetched to locate it."""
    fragment_url = f"{FRAGMENT_URL}/{posting_id}{EN_US_QUERY}"
    fragment = None
    if candidate and url is not None:
        with contextlib.suppress(Stopped):
            page = await _page(fetcher, posting_id, url, candidate=True)
            if page is not None and page[1]:
                return *page, None
        url = None
    if url is None:
        if (fragment := await _request(fetcher, fragment_url)) is None:
            return None
        url = _fragment_url(fragment.text, posting_id)
    if (page := await _page(fetcher, posting_id, _canonical(url))) is None:
        return None
    return *page, fragment


async def posting_fields(
    fetcher: Fetcher, url: str, *, named: bool = False
) -> dict[str, Any] | None:
    """
    Read the fields of the posting at a card's URL, or None when LinkedIn reports it gone.

    A guest API address holds a fragment, which names the page to read. Any other address is
    read as the page. ``named`` marks an address a caller gave: on ``www`` it may be another
    country's alias, so a failed read of it falls back to the fragment. A page that redirects
    elsewhere leaves the fragment as the only source of fields. The fields carry the page's
    canonical ``url``.

    Raises:
        Stopped: The posting could not be read.
        Halt: paced_fetch spent its retries on a 429.
    """
    posting_id = job_id(url)
    page = await _resolve_page(
        fetcher,
        posting_id,
        None if url.startswith(f"{FRAGMENT_URL}/") else url,
        candidate=named and urlsplit(url).hostname in _WWW_HOSTS,
    )
    if page is None:
        return None
    url, fields, fragment = page
    if not fields:
        logger.warning(
            "posting %s redirected away from its page; using only its guest fragment", posting_id
        )
        # Reuse the fragment if the canonical URL lookup already fetched it.
        if fragment is None:
            fragment = await _request(fetcher, f"{FRAGMENT_URL}/{posting_id}{EN_US_QUERY}")
        if fragment is None:
            raise Stopped("its en-US fragment is gone")
        # The fragment is the only source left, so it must name this posting.
        _fragment_url(fragment.text, posting_id)
        if not (fields := _parse_posting(BeautifulSoup(fragment.text, "html.parser"))):
            raise Stopped("its guest fragment yielded no fields")
    return fields | {"url": url}


def _reference(reference: str) -> JobDict:
    """
    Read a posting ID or URL as the card it names.

    A posting URL is its page, its guest API address, the link in a job alert email,
    or a search page that names it in ``currentJobId``. A title-slug URL is the posting's page
    and becomes the card's ``url``. Any other reference gives the guest API address of its ID,
    whose fragment names the page.

    Raises:
        ValueError: The reference is neither a numeric posting ID nor a LinkedIn posting URL.
    """
    ref = reference.strip()
    if numeric(ref):
        ref = f"{FRAGMENT_URL}/{ref}"
    parts = urlsplit(ref)
    shown = parse_qs(parts.query).get("currentJobId", [""])[0]
    # The /comm/ link redirects to the page, and a search page carries only the ID,
    # so each is rewritten to the page address of its ID. A path that names a posting keeps it over
    # any currentJobId.
    if parts.path.startswith(f"/comm{_PAGE_PATH}"):
        ref = urlunsplit(parts._replace(path=parts.path.removeprefix("/comm")))
    elif numeric(shown) and not job_id(ref):
        ref = urlunsplit(parts._replace(path=f"{_PAGE_PATH}{shown}"))
    posting_id = job_id(ref)
    if not (posting_id and _posting_url(ref, posting_id, _REFERENCE_PATHS)):
        raise ValueError(
            f"{reference!r} is neither a numeric posting ID nor a LinkedIn posting URL. "
            "Try 4449382178 or the posting's https://www.linkedin.com/jobs/view/... address"
        )
    parts = urlsplit(ref)
    # The canonical address carries a title slug ahead of the ID.
    slug = parts.path.rstrip("/").rsplit("/", 1)[-1]
    page = parts.path.startswith(_PAGE_PATH) and slug != posting_id
    url = _canonical(ref) if page else f"{FRAGMENT_URL}/{posting_id}"
    return make_job(site="linkedin", id=posting_id, url=url)


def card(reference: str) -> JobDict:
    """
    Read a LinkedIn posting URL as the card it names, for ``identify``.

    Raises:
        ValueError: The reference is not a LinkedIn posting URL. A bare posting ID is refused too,
            because a number alone names no site.
    """
    if numeric(reference.strip()):
        raise ValueError(f"{reference!r} is a number, not a LinkedIn posting URL")
    return _reference(reference)


# Two workers per fabric. Measured live on 2026-11-09, six workers held the pacer's sustained rate
# and three did not, because a worker waits out its own retries and second requests.
# The count also bounds the requests sent after a persistent 429 before the call stops.
WORKERS = 2 * FABRICS_WANTED

postings = postings_of(
    _reference,
    functools.partial(posting_fields, named=True),
    workers=WORKERS,
    help_text="posting IDs or URLs",
)
