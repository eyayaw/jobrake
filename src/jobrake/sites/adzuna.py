"""Search Adzuna's country editions through its mobile app API."""

import functools
import hashlib
import itertools
import logging
import re
import uuid
from collections.abc import AsyncGenerator
from typing import Annotated, Any, NamedTuple
from urllib.parse import parse_qs, urlencode

lazy from bs4 import BeautifulSoup

from jobrake.countries import alpha2
from jobrake.fetchkit import Fetcher, FetchResult
from jobrake.models import JobDict, Stopped, employment_type, make_job
from jobrake.sites.postings import Reader, fill_details
from jobrake.sites.responses import collect, json_ld, json_page, offset_pages, read_html, read_json
from jobrake.utils import as_dict, as_int, as_list, as_str, checked, finite, html_text, split_url

logger = logging.getLogger(__name__)

# The Android app (com.adzuna 1.7.0) reads https://app.adzuna.com/app/<context>/ and signs every
# request with com.adzuna.api.VParamGenerator (checked 2026-11-23).
API_BASE = "https://app.adzuna.com/app"
APP_VERSION = "1.7.0"
_SIGN_KEY1 = "Z5lc58S@cc"
_SIGN_KEY2 = "Z6lv56K@ec"
_SIGN_PREFIX = "020104"
_SIGN_HEX = "0123456789ABCDEF"
_SIGN_SHIFT = 18

# Measured 2026-11-24: pp=50 returns 50 postings, and pp=100 is capped to 50 by the server.
PAGE_SIZE = 50
# Measured 2026-11-24 on q="manager" (318,281 matches): page 20 returned 50 postings, and pages 21
# and 22 clamped current_page back to 20 with entries_per_page=10.
MAX_PAGES = 20

_SESSION_COOKIE = re.compile(r"(?:^|[,\s])session=([^;,\s]+)")
_POSTING_PATH = re.compile(r"(?:/jobs)?/(?:land/ad|details)/([0-9]+)/?", re.ASCII)
_DIGITS = re.compile(r"[0-9]+", re.ASCII)
_VHASH = re.compile(r"[0-9A-Fa-f]{40}", re.ASCII)


class _Edition(NamedTuple):
    country: str
    context: str
    host: str
    jobs_base: str
    currency: str
    miles: bool


# The 19 country editions returned live in start_session's domain["CONTROL"]["CONTEXT.ALLOW"], with
# their hosts and distance units from domain["BASES"] and domain["REGIONAL"] (checked 2026-11-24).
# Only UK prefixes /jobs on its web paths, and only UK and US take search radius d in miles.
_EDITIONS: dict[str, _Edition] = {
    country: _Edition(
        country,
        context="jobs" if country == "GB" else f"jobs_{country}",
        host=f"https://www.{domain}",
        jobs_base=f"https://www.{domain}/jobs" if country == "GB" else f"https://www.{domain}",
        currency=currency,
        miles=country in {"GB", "US"},
    )
    for country, domain, currency in (
        ("AT", "adzuna.at", "EUR"),
        ("AU", "adzuna.com.au", "AUD"),
        ("BE", "adzuna.be", "EUR"),
        ("BR", "adzuna.com.br", "BRL"),
        ("CA", "adzuna.ca", "CAD"),
        ("CH", "adzuna.ch", "CHF"),
        ("DE", "adzuna.de", "EUR"),
        ("ES", "adzuna.es", "EUR"),
        ("FR", "adzuna.fr", "EUR"),
        ("GB", "adzuna.co.uk", "GBP"),
        ("IN", "adzuna.in", "INR"),
        ("IT", "adzuna.it", "EUR"),
        ("MX", "adzuna.com.mx", "MXN"),
        ("NL", "adzuna.nl", "EUR"),
        ("NZ", "adzuna.co.nz", "NZD"),
        ("PL", "adzuna.pl", "PLN"),
        ("SG", "adzuna.sg", "SGD"),
        ("US", "adzuna.com", "USD"),
        ("ZA", "adzuna.co.za", "ZAR"),
    )
}

_HOSTS: dict[str, _Edition] = {
    host: edition
    for edition in _EDITIONS.values()
    for host in (edition.host.removeprefix("https://"), edition.host.removeprefix("https://www."))
}


def _text(value: object) -> str | None:
    """Return a nonblank stripped string from a JSON value, or None."""
    return (as_str(value) or "").strip() or None


def _edition(country: str) -> _Edition:
    """
    Resolve an upper-case ISO 3166-1 alpha-2 code to its Adzuna edition.

    Raises:
        ValueError: Adzuna has no app edition for the country.
    """
    if edition := _EDITIONS.get(country):
        return edition
    codes = " ".join(sorted(code.lower() for code in _EDITIONS))
    raise ValueError(f"Adzuna has no edition for {country!r}. Pass the code of one: {codes}")


def _validate(*, country: str, **_: object) -> None:
    _edition(country)


def _sign(context: str, path: str, sid: str | None, counter: int) -> str:
    """Compute the ``v`` signature parameter from com.adzuna.api.VParamGenerator (v1.7.0)."""
    payload = f"{_SIGN_KEY1}|{sid or ''}|{counter}|{context}{path}|{_SIGN_KEY2}"
    digest = (
        _SIGN_PREFIX + hashlib.sha1(payload.encode(), usedforsecurity=False).hexdigest().upper()
    )
    checksum = _SIGN_HEX[sum(map(ord, digest)) % 16]
    return "".join(chr(ord(char) + _SIGN_SHIFT) for char in digest + checksum)


class _Session:
    """One anonymous Adzuna app session, carrying its ``sid``, cookie, and request counter."""

    def __init__(self, context: str) -> None:
        self.context = context
        self.sid: str | None = None
        self.cookie: str | None = None
        self.counter = 0

    async def start(self, fetcher: Fetcher) -> None:
        """
        Bootstrap the session with ``start_session`` and retain its ``sid`` and session cookie.

        Raises:
            Stopped: The request failed or the response lacked a usable ``sid``.
        """
        result = await self.get(
            fetcher,
            "/start_session",
            {
                "device_type": "Android",
                "device_uuid": str(uuid.uuid4()),
                "app_id": "jobs",
                "app_version": APP_VERSION,
            },
        )

        def read_sid(body: Any) -> str:  # noqa: ANN401  decoded JSON validated here
            if not (sid := _text(body["sid"])):
                raise TypeError(f"sid {body['sid']!r} is not a nonblank string")
            return sid

        self.sid = read_json(result, read_sid, site="adzuna")
        if match := _SESSION_COOKIE.search(result.headers.get("set-cookie", "")):
            self.cookie = f"session={match.group(1)}"

    async def get(self, fetcher: Fetcher, path: str, params: dict[str, Any]) -> FetchResult:
        """Send one signed GET request within this session."""
        self.counter += 1
        signed = params | {
            "counter": self.counter,
            "v": _sign(self.context, path, self.sid, self.counter),
        }
        url = f"{API_BASE}/{self.context}{path}?{urlencode(signed)}"
        headers = {"Cookie": self.cookie} if self.cookie else None
        return await fetcher.fetch(url, headers=headers)


def _number(value: object) -> float | None:
    """Parse a JSON number or numeric string into a finite float, or return None."""
    if (number := finite(value)) is not None:
        return number
    if isinstance(value, str):
        try:
            return finite(float(value.strip()))
        except ValueError:
            return None
    return None


def _ad_salary(ad: dict[str, Any], edition: _Edition) -> dict[str, Any]:
    """Read the advertised salary of a ``get_ad`` posting, leaving Adzuna's estimate out."""
    if ad.get("salary_is_predicted"):
        return {}
    # get_ad annualizes an advertised salary: "£3500 - £4000/month" arrived as 42000 and 48000
    # (measured 2026-11-24). A search card carries only the employer's text, salary_raw, which
    # mixes periods, units, and other numbers too freely to parse.
    low, high = (
        value if (value := _number(ad.get(key))) is not None and value > 0 else None
        for key in ("salary_min", "salary_max")
    )
    if low is None and high is None:
        return {}
    return {
        "salary_min": low,
        "salary_max": high,
        "salary_currency": _text(as_dict(ad.get("source")).get("currency_code"))
        or edition.currency,
        "salary_period": "YEAR",
    }


def _card_id(raw: object) -> str:
    """Return a card's numeric ``id``, a string or an integer, or raise TypeError."""
    posting_id = raw.strip() if isinstance(raw, str) else str(as_int(raw))
    if _DIGITS.fullmatch(posting_id):
        return posting_id
    raise TypeError(f"id {raw!r} is not a posting number")


def _vhash(listing: dict[str, Any]) -> str | None:
    """Return the hash ``get_ad`` needs, from ``tracker_hash`` or the ``v`` of ``direct_link``."""
    query = parse_qs(split_url(_text(listing.get("direct_link")) or "").query)
    for value in (listing.get("tracker_hash"), *query.get("v", [])):
        if (vhash := _text(value)) and _VHASH.fullmatch(vhash):
            return vhash
    return None


def _employment(entry: dict[str, Any]) -> tuple[str | None, str | None]:
    """
    Return the ``employment_type`` of a card or ad and the ``contract_type`` left for ``site_data``.

    The work schedule, ``contract_time`` such as ``full_time``, fills ``employment_type`` when
    Adzuna gives one, and the contract kind, ``permanent`` or ``contract``, fills it otherwise.
    """
    schedule = employment_type(as_str(entry.get("contract_time")))
    contract = employment_type(as_str(entry.get("contract_type")))
    return (schedule, contract) if schedule else (contract, None)


class _CardMeta(NamedTuple):
    posting_id: str
    vhash: str | None
    direct_link: str | None


def _parse_card(listing: dict[str, Any], edition: _Edition, meta: dict[str, _CardMeta]) -> JobDict:
    """
    Build a record from one search card, noting in ``meta`` how its posting can be read.

    Raises:
        TypeError: The card lacks a numeric ``id``.
        AttributeError: The card is not an object.
    """
    posting_id = _card_id(listing.get("id"))
    direct = _text(listing.get("direct_link"))
    link = split_url(direct or "")
    # A relative link to a details page names a posting Adzuna hosts. A land/ad link clicks out.
    hosted = not (link.scheme or link.netloc) and link.path.startswith(
        ("/details/", "/jobs/details/")
    )
    url = f"{edition.jobs_base}/{'details' if hosted else 'land/ad'}/{posting_id}"
    employment, contract_type = _employment(listing)
    place = _text(listing.get("location_raw"))
    job = make_job(
        site="adzuna",
        id=posting_id,
        url=url,
        title=listing.get("title"),
        company=listing.get("company"),
        locations=[{"name": place, "country_code": edition.country}] if place else [],
        date=as_str(listing.get("modified")),
        employment_type=employment,
        site_data={"contract_type": contract_type},
    )
    # collect keeps a posting's first card, so details read the posting with that card's hash.
    meta.setdefault(url, _CardMeta(posting_id, _vhash(listing), direct if hosted else None))
    return job


def _ad_place(ad: dict[str, Any], edition: _Edition) -> list[dict[str, Any]]:
    """
    Read the posting's one place from ``location_raw`` and the most specific ``locations`` entry.

    ``ad["locations"]`` is a geographic hierarchy for one place (level 1 country up to level 3
    district), not separate job locations.
    """
    entries = sorted(
        map(as_dict, as_list(ad.get("locations"))),
        key=lambda entry: as_int(entry.get("level")) or 0,
        reverse=True,
    )
    names = (ad.get("location_raw"), *(entry.get("name") for entry in entries))
    if not (name := next(filter(None, map(_text, names)), None)):
        return []
    points = ((_number(entry.get("lat")), _number(entry.get("lng"))) for entry in entries)
    lat, lng = next((point for point in points if None not in point), (None, None))
    return [{"name": name, "country_code": edition.country, "latitude": lat, "longitude": lng}]


def _apply_url(ad: dict[str, Any]) -> str | None:
    link = _text(ad.get("url_with_ga"))
    if link and split_url(link).scheme in ("http", "https"):
        return link
    return None


def _parse_ad(ad: dict[str, Any], edition: _Edition) -> dict[str, Any]:
    """Read a ``get_ad`` posting object into detail fields."""
    kind, contract_type = _employment(ad)
    source = as_dict(ad.get("source"))
    category = as_dict(ad.get("category"))
    return {
        "title": as_str(ad.get("title")),
        "company": as_str(ad.get("company")),
        "locations": _ad_place(ad, edition),
        "description": html_text(as_str(ad.get("description")) or ""),
        "employment_type": kind,
        **_ad_salary(ad, edition),
        "posted_at": as_str(ad.get("created")),
        "expires_at": as_str(ad.get("valid_through")),
        "apply_url": _apply_url(ad),
        "site_data": {
            "category": as_str(category.get("label")),
            "source": as_str(source.get("site")),
            "contract_type": contract_type,
        },
    }


def _direct_place(posting: dict[str, Any], edition: _Edition) -> list[dict[str, Any]]:
    """Read the schema.org ``jobLocation``, or ``[]`` when it names no city or region."""
    loc = posting.get("jobLocation")
    loc = as_dict(loc[0] if isinstance(loc, list) and loc else loc)
    address, geo = as_dict(loc.get("address")), as_dict(loc.get("geo"))
    city, region = _text(address.get("addressLocality")), _text(address.get("addressRegion"))
    if not (city or region):
        # A country alone would replace the card's more specific label.
        return []
    # On 2026-11-24, GB's pages gave the country's code and Australia's its name ("Australia").
    country = alpha2(_text(address.get("addressCountry")) or "")
    return [
        {
            "city": city,
            "region": region,
            "country_code": country or edition.country,
            "latitude": _number(geo.get("latitude")),
            "longitude": _number(geo.get("longitude")),
        }
    ]


def _parse_direct_page(page: BeautifulSoup, edition: _Edition) -> dict[str, Any]:
    """
    Read a ``direct_link`` details page for cards that carry no ``tracker_hash``.

    Adzuna's schema.org ``JobPosting`` omits ``salary_is_predicted`` and mislabeled monthly pay as
    ``YEAR`` in our 2026-11-24 check, so this reader leaves the salary out. Editions that omit
    ``JobPosting`` JSON-LD, or a block without a description, fall back to ``.adp-body``.

    Raises:
        TypeError: The page carries neither a ``JobPosting`` block nor a description body.
    """
    posting = next(iter(json_ld(page, {"JobPosting"})), None)
    body = page.select_one("section.adp-body, div.adp-body")
    description = html_text(as_str(as_dict(posting).get("description")) or "") or (
        html_text(str(body)) if body is not None else ""
    )
    if posting is None:
        if not description:
            raise TypeError("the details page holds no JobPosting block or description body")
        return {"description": description}
    org = as_dict(posting.get("hiringOrganization"))
    raw_emp = posting.get("employmentType")
    emp_label = as_str(raw_emp[0] if isinstance(raw_emp, list) and raw_emp else raw_emp)
    return {
        "title": as_str(posting.get("title")),
        "company": as_str(org.get("name")),
        "locations": _direct_place(posting, edition),
        "description": description,
        "employment_type": employment_type(emp_label),
        "posted_at": as_str(posting.get("datePosted")),
        "expires_at": as_str(posting.get("validThrough")),
        "site_data": {"category": as_str(posting.get("industry"))},
    }


def _read_search_page(payload: Any) -> tuple[list[Any], int]:  # noqa: ANN401  decoded JSON checked here
    """Return the ``docs`` and ``pager.total_entries`` of a ``/search`` response."""
    results = payload["contract"]["results"]
    return json_page(results["pager"] | results, "docs", "total_entries")


async def _pages(
    fetcher: Fetcher,
    session: _Session,
    edition: _Edition,
    shared: dict[str, Any],
    *,
    limit: int,
    meta: dict[str, _CardMeta],
) -> AsyncGenerator[tuple[list[JobDict], int]]:
    """
    Yield each page's cards with the count of matches Adzuna reports, for ``collect``.

    Raises:
        Stopped: A request failed, Adzuna sent an unreadable response, or an empty page came
            before the reported count.
    """
    numbers, capped = itertools.count(1), False

    async def read(offset: int) -> tuple[list[Any], int]:
        nonlocal capped
        if (number := next(numbers)) > MAX_PAGES:
            # Adzuna answers a later page with its last one again, so the search ends here.
            capped = True
            return [], offset
        result = await session.get(fetcher, "/search", shared | {"p": number, "pp": limit})
        return read_json(result, _read_search_page, site="adzuna")

    parse = functools.partial(_parse_card, edition=edition, meta=meta)
    async for page in offset_pages(read, parse, site="adzuna"):
        yield page
    if capped:
        logger.warning(
            "Adzuna serves at most %d pages per search, fewer than requested. "
            "Split the search by place or narrow the query to reach the rest",
            MAX_PAGES,
        )


async def _read_ad(
    fetcher: Fetcher, session: _Session, edition: _Edition, posting_id: str, vhash: str
) -> dict[str, Any] | None:
    """Fetch one posting through ``get_ad``, returning None when Adzuna reports it gone."""
    result = await session.get(fetcher, "/get_ad", {"id": posting_id, "vhash": vhash})
    if result.status in (404, 410):
        return None

    def unpack(body: Any) -> dict[str, Any] | None:  # noqa: ANN401  decoded JSON validated here
        ad = body["ad"]
        # get_ad sends is_deleted and salary_is_predicted as 0 or 1 (41 postings in 6 editions,
        # 2026-11-24).
        return None if ad is None or ad.get("is_deleted") else _parse_ad(ad, edition)

    return read_json(result, unpack, site="adzuna")


async def _read_direct_page(
    fetcher: Fetcher, edition: _Edition, direct_link: str
) -> dict[str, Any] | None:
    """Fetch an Adzuna-hosted posting's details page, returning None for 404 or 410."""
    result = await fetcher.fetch(f"{edition.host}{direct_link}")
    if result.status in (404, 410):
        return None
    return read_html(result, lambda page: _parse_direct_page(page, edition), site="adzuna")


def _detail_reader(session: _Session, edition: _Edition, meta: dict[str, _CardMeta]) -> Reader:
    """Build the per-posting reader for ``fill_details`` bound to the active search session."""

    async def read(fetcher: Fetcher, url: str) -> dict[str, Any] | None:
        info = meta[url]
        if info.vhash:
            return await _read_ad(fetcher, session, edition, info.posting_id, info.vhash)
        if info.direct_link:
            return await _read_direct_page(fetcher, edition, info.direct_link)
        raise Stopped(f"Adzuna's search result for {url} names no way to read the posting")

    return read


def card(reference: str) -> JobDict:
    """
    Read an Adzuna posting URL as the card it names, for ``identify``.

    Raises:
        ValueError: The reference is not an Adzuna posting URL on a supported edition.
    """
    parts = split_url(reference)
    # An edition's host alone: a port or credentials fail the lookup.
    edition = _HOSTS.get(parts.netloc.lower())
    if not (
        edition
        and parts.scheme in ("http", "https")
        and (match := _POSTING_PATH.fullmatch(parts.path))
    ):
        raise ValueError(
            f"{reference!r} is not an Adzuna posting URL. Pass one on an Adzuna edition, "
            "such as https://www.adzuna.co.uk/jobs/land/ad/5575618204"
        )
    posting_id = match[1]
    kind = "details" if "/details/" in parts.path else "land/ad"
    return make_job(site="adzuna", id=posting_id, url=f"{edition.jobs_base}/{kind}/{posting_id}")


@checked(validator=_validate)
async def search(
    fetcher: Fetcher,
    *,
    query: Annotated[str, "job title or keywords"] = "",
    country: Annotated[str, "ISO 3166-1 code of an Adzuna edition, e.g., de, gb, or us"],
    location: Annotated[str | None, "city or area within the country"] = None,
    radius: Annotated[int | None, "search radius in kilometers"] = None,
    results: Annotated[int, "maximum number of postings"] = 100,
    max_age_hours: Annotated[int | None, "maximum posting age in hours, rounded up to days"] = None,
    details: Annotated[bool, "fetch each posting for its description and other details"] = False,
) -> list[JobDict]:
    """
    Search one Adzuna country edition and list the postings it returns.

    ``radius`` is in kilometers, which the GB and US editions receive as miles, and
    ``max_age_hours`` rounds up to whole days. Adzuna serves at most ``MAX_PAGES`` pages per
    search, and a search that reaches that cap short of ``results`` warns and returns them.
    ``details`` fetches each posting for its description, salary, and application link with one
    more request, which a cached posting skips. Reading most postings takes a hash only their search
    cards carry, so ``failed`` stays empty, and a rerun of the search retries the unread postings.

    Raises:
        Stopped: A request failed, Adzuna sent an unreadable response, or an empty page came before
            the reported total. ``partial`` holds the postings of the pages before it. With
            ``details``, a posting could not be fetched, and ``partial`` holds every posting,
            filled where its fetch succeeded.
        ValueError: ``country`` is blank, not an ISO 3166-1 code, or not an Adzuna edition,
            ``results`` or ``max_age_hours`` is below 1, or ``radius`` is below 0.
    """
    edition = _edition(country)
    place = _text(location)
    logger.info("searching Adzuna for %r in %r", query, ", ".join(filter(None, (place, country))))
    session = _Session(edition.context)
    await session.start(fetcher)
    shared: dict[str, Any] = {
        key: text for key, text in (("q", query.strip()), ("w", place)) if text
    }
    # With w and without d, five searches in the DE, GB, and FR editions reported the same total as
    # d=0, and Leipzig, Leeds, and Lyon returned the same postings (2026-11-25). At d=0, 3 of 293
    # Leipzig postings, 32 of 1,000 for Leeds, and 263 of 1,000 for Lyon named a place other than
    # the city.
    if radius is not None:
        # Integer arithmetic keeps radii beyond float range from overflowing.
        shared["d"] = (radius * 1_000_000 + 804_672) // 1_609_344 if edition.miles else radius
    if max_age_hours is not None:
        # Adzuna's f filter counts whole days (NOW/DAY-fDAYS), so hours round up.
        shared["f"] = -(-max_age_hours // 24)
    meta: dict[str, _CardMeta] = {}
    pages = _pages(fetcher, session, edition, shared, limit=min(PAGE_SIZE, results), meta=meta)
    jobs = await collect("adzuna", pages, results)
    reader = _detail_reader(session, edition, meta)
    return await fill_details(fetcher, jobs, reader, retryable=False) if details else jobs


__all__ = ["search"]
