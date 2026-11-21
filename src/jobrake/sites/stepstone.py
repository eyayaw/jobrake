"""Search StepStone's German job board through its mobile app's listings API."""

import json
import logging
import re
import uuid
from collections.abc import AsyncGenerator
from typing import Annotated, Any
from urllib.parse import urlencode, urlsplit

lazy from bs4 import BeautifulSoup

from jobrake.fetchkit import Fetcher
from jobrake.models import JobDict, Stopped, employment_type, make_job
from jobrake.sites.postings import fill_details, postings_of, readable_url
from jobrake.sites.responses import collect, json_ld, json_page, offset_pages, read_json
from jobrake.utils import (
    as_dict,
    as_int,
    as_str,
    checked,
    cutoff,
    epoch_ms_to_iso,
    finite,
    html_text,
)

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.stepstone.de/naps-facade/v4/listings/search"
# The list card's url is a placeholder, so a record points at the posting's own page, /job/<id>,
# whose schema.org JobPosting block carries the description.
POSTING_URL = "https://www.stepstone.de/job/{id}"
# The public key StepStone's mobile apps send in the ApiKey header (checked 2026-11-15).
# Without it the API answers HTTP 500.
APP_KEY = "bda9uI7EitLIAo37P+3UssK_0bQT5H"
API_HEADERS = {"ApiKey": APP_KEY, "accept": "application/json"}
PAGE_SIZE = 50  # the page size the app requests

# A record's url, /job/<id>, and the slug URL that StepStone's web search or an old link may carry.
# StepStone resets a plain client's request for a slug URL, so card() maps it to /job/<id>.
_JOB_PATH = re.compile(r"/job/([0-9]+)/?")
_SLUG_PATH = re.compile(r"/(?:stellenangebote|jobs)--.*--([0-9]+)-inline\.html")
_HOSTS = {"stepstone.de", "www.stepstone.de"}


def _place(card: dict[str, Any]) -> dict[str, Any]:
    """Read the card's one place: its location label, country, and any coordinates it gives."""
    name = as_str(card.get("location"))
    if not name:
        return {}
    place = {"name": name, "country_code": as_str(card.get("country"))}
    latitude, longitude = finite(card.get("latitude")), finite(card.get("longitude"))
    # StepStone sends 0, 0 for a posting without a point, single-city ones included. A single zero
    # is a real coordinate, as for a city on the prime meridian or the equator.
    if latitude is not None and longitude is not None and (latitude, longitude) != (0, 0):
        place["latitude"], place["longitude"] = latitude, longitude
    return place


def _parse_card(listing: dict[str, Any]) -> JobDict:
    """
    Build a record from one card of a search response's ``items`` list.

    Raises:
        TypeError: The card's ``id`` is not a posting number, as a string or an integer.
        AttributeError: The card is not an object.
    """
    raw = listing.get("id")
    posting_id = str(number) if (number := as_int(raw)) is not None else raw
    url = readable_url(card, posting_id, POSTING_URL.format(id=posting_id))
    return make_job(
        site="stepstone",
        id=posting_id,
        url=url,
        title=listing.get("title"),
        company=listing.get("companyName"),
        locations=[_place(listing)],
        date=epoch_ms_to_iso(listing.get("datePosted")),
        company_logo=as_str(listing.get("companyLogoURL")),
        language=as_str(listing.get("language")),
        posted_at=epoch_ms_to_iso(listing.get("dateOriginal") or listing.get("datePosted")),
        expires_at=epoch_ms_to_iso(listing.get("dateExpire")),
        site_data={
            "section": listing.get("section"),
            "labels": listing.get("listingLabels") or None,
        },
    )


# JobAdContent, a JS literal elsewhere on the page, carries what the schema.org block omits: the
# posting's own language, and in its first metaData object the location label of the posting's
# search card (the card's label on 16 of 16 pages compared, 2026-11-15).
_OFFER_LANGUAGE = re.compile(r'"offerLanguage":"(\w+)"')
_META_DATA = '"metaData":'


def _card_label(html: str) -> str | None:
    """Return the location label of the posting's search card, or None when the page lacks it."""
    start = html.find(_META_DATA)
    if start < 0:
        return None
    try:
        meta, _ = json.JSONDecoder().raw_decode(html, start + len(_META_DATA))
    except ValueError, RecursionError:
        return None
    return as_str(as_dict(meta).get("location"))


def _block_place(posting: dict[str, Any], label: str | None) -> dict[str, Any]:
    """Read the schema.org ``jobLocation`` as a place named by the card's ``label``."""
    location = posting.get("jobLocation")
    location = as_dict(location[0] if isinstance(location, list) and location else location)
    address, geo = as_dict(location.get("address")), as_dict(location.get("geo"))
    city = as_str(address.get("addressLocality"))
    name = label or city
    if not name:
        return {}
    # A label lists a posting's cities with commas, and jobLocation then holds the first city's
    # address, or the list itself in addressLocality (29 pages, 2026-11-15). Only a label without
    # a comma names one city, so one named with its region, such as "Eberbach, Baden", gets none.
    one_city = {"city": city, "region": as_str(address.get("addressRegion"))}
    return {
        "name": name,
        **(one_city if "," not in name else {}),
        "country_code": as_str(address.get("addressCountry")),
        "latitude": finite(geo.get("latitude")),
        "longitude": finite(geo.get("longitude")),
    }


def _parse_posting(posting: dict[str, Any], html: str) -> dict[str, Any]:
    """
    Read a posting page's schema.org block and JobAdContent into a whole record's fields.

    A search card lacks the description, the employment type, and the company URL. The page
    carries the rest too, so ``postings`` can build a record from a URL alone, where there is no
    card, and a search card's fields give way to the page's.
    """
    organization = as_dict(posting.get("hiringOrganization"))
    language = _OFFER_LANGUAGE.search(html)
    return {
        "title": as_str(posting.get("title")),
        "company": as_str(organization.get("name")),
        "company_url": as_str(organization.get("url")),
        "company_logo": as_str(organization.get("logo")),
        "locations": [_block_place(posting, _card_label(html))],
        "description": html_text(as_str(posting.get("description")) or ""),
        "employment_type": employment_type(as_str(posting.get("employmentType"))),
        "language": language[1] if language else None,
        "posted_at": as_str(posting.get("datePosted")),
        "expires_at": as_str(posting.get("validThrough")),
    }


async def _posting_fields(fetcher: Fetcher, url: str) -> dict[str, Any] | None:
    """
    Fetch the posting at a URL and read its page, or None when StepStone reports it gone.

    A closed posting answers 410 and an unknown ID 404. The page carries a whole record, so a search
    result gains the fields its card lacks and a ``postings`` call needs only the URL.

    Raises:
        Stopped: The request failed, or the page carries no posting data.
    """
    result = await fetcher.fetch(url)
    if result.status in (404, 410):
        return None
    # A posting page comes with HTTP 200, as the shared readers require of every site's data.
    if result.error or result.status != 200:
        failure = result.error or f"HTTP {result.status}"
        raise Stopped(f"stepstone request for {url} failed: {failure}")
    page = BeautifulSoup(result.text, "html.parser")
    posting = next(iter(json_ld(page, {"JobPosting"})), None)
    if posting is None:
        raise Stopped(
            f"stepstone served {url} without its posting data, so the site may be under "
            "maintenance or its markup changed. Try again later"
        )
    return _parse_posting(posting, result.text)


def _params(
    query: str,
    location: str | None,
    radius: int,
    max_age_hours: int | None,
    install_id: str,
    *,
    remote: bool,
) -> dict[str, Any]:
    """Return the query parameters every page of a search shares, all but its offset and limit."""
    params: dict[str, Any] = {
        "itemsSection": "main",
        "radius": radius,
        "appname": "STST",
        "client": "ANDROID",
        "installId": install_id,
        "country": "de",
        "language": "de",
    }
    if query:
        params["what"] = query
    if location:
        params["where"] = location
    if since := cutoff(max_age_hours):
        params["sinceDate"] = int(since.timestamp() * 1000)
    if remote:
        # The web search's "Nur Home-Office" filter, applied by the API too (measured 2026-11-15).
        params["workFromHome"] = 1
    return params


def _pages(
    fetcher: Fetcher, shared: dict[str, Any], limit: int
) -> AsyncGenerator[tuple[list[JobDict], int]]:
    """Yield each page's cards with the count of matches StepStone reports, until its last match."""

    async def read(offset: int) -> tuple[list[Any], int]:
        page = urlencode(shared | {"offset": offset, "limit": limit})
        result = await fetcher.fetch(f"{SEARCH_URL}?{page}", headers=API_HEADERS)
        return read_json(
            result, lambda body: json_page(body["data"], "items", "totalItems"), site="stepstone"
        )

    return offset_pages(read, _parse_card, site="stepstone")


@checked
async def search(
    fetcher: Fetcher,
    *,
    query: Annotated[str, "job title or keywords"] = "",
    location: Annotated[str | None, "city or postal code in Germany"] = None,
    radius: Annotated[int, "search radius in kilometers"] = 30,
    results: Annotated[int, "maximum number of postings"] = 100,
    max_age_hours: Annotated[int | None, "maximum posting age in hours"] = None,
    remote: Annotated[bool, "only postings StepStone lists as fully remote"] = False,
    details: Annotated[bool, "fetch each posting for its description"] = False,
) -> list[JobDict]:
    """
    Search StepStone's German job board and list the postings it returns.

    StepStone applies every option: ``query`` searches titles and keywords, ``location`` is a German
    city or postal code, and ``radius`` widens the search around it. ``max_age_hours`` keeps
    postings posted within that many hours, and ``remote`` those StepStone lists as fully remote.
    Pages of up to 50 cards follow one another without pacing or retries until ``results``, the last
    match, or an empty page. StepStone mixes postings outside the radius into the results, each card
    naming its ``section`` in ``site_data``. A posting that a later page repeats is kept once.
    A card lacks the description, the employment type, and the company URL, so ``details`` fetches
    each posting's page with one more request, which a cached posting skips.

    Raises:
        Stopped: A request failed, StepStone sent an unreadable response, or an empty page came
            before the reported total. ``partial`` holds the postings of the pages before it.
            With ``details``, a posting could not be fetched, and ``partial`` holds every posting,
            filled where its fetch succeeded, and ``failed`` the URLs of the postings whose fetch
            failed.
        ValueError: ``results`` or ``max_age_hours`` is below 1, or ``radius`` is below 0.
    """
    logger.info("searching stepstone for %r in %r", query, location or "Germany")
    shared = _params(query, location, radius, max_age_hours, str(uuid.uuid4()), remote=remote)
    jobs = await collect("stepstone", _pages(fetcher, shared, min(PAGE_SIZE, results)), results)
    return await fill_details(fetcher, jobs, _posting_fields) if details else jobs


def card(reference: str) -> JobDict:
    """
    Read a StepStone posting URL as the card it names, for ``postings`` and ``identify``.

    Raises:
        ValueError: The reference is not a StepStone posting URL on stepstone.de.
    """
    parts = urlsplit(reference.strip())
    hosted = parts.scheme in ("http", "https") and parts.netloc.lower() in _HOSTS
    path = parts.path
    if not (hosted and (match := _JOB_PATH.fullmatch(path) or _SLUG_PATH.fullmatch(path))):
        raise ValueError(
            f"{reference!r} is not a StepStone posting URL. Pass a record's url, such as "
            "https://www.stepstone.de/job/14569042"
        )
    posting_id = match.group(1)
    return make_job(site="stepstone", id=posting_id, url=POSTING_URL.format(id=posting_id))


postings = postings_of(card, _posting_fields)


__all__ = ["postings", "search"]
