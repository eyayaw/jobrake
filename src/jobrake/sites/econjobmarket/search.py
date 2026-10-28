"""EconJobMarket ad feed requests and parsing."""

import logging
import re
from gettext import ngettext
from typing import Any

from jobrake.fetchkit import Fetcher
from jobrake.models import JobDict, make_job
from jobrake.sites.responses import json_list, parse_postings, read_json
from jobrake.utils import as_dict, as_str, checked, finite, html_text, join_places

logger = logging.getLogger(__name__)

API_URL = "https://backend.econjobmarket.org/data/zz_public/json/Ads"

# An ad carries no ID field. Its page URL ends in the ad's number.
_AD_ID = re.compile(r"/positions/(\d+)")


def _place(location: dict[str, Any]) -> str:
    """Join one location's city, state, and country code, such as ``London, GB``."""
    parts = (as_str(location.get(key)) for key in ("city", "state", "country_code"))
    return ", ".join(part.strip() for part in parts if part and part.strip())


def _parse_ad(ad: dict[str, Any]) -> JobDict:
    """
    Build a record from one ad of the feed, named for each of its locations and placed at the first.

    Raises:
        TypeError: The ad's ``url`` holds no ``/positions/<number>``.
        AttributeError: The ad is not an object.
    """
    url = ad.get("url")
    match = _AD_ID.search(url) if isinstance(url, str) else None
    if match is None:
        raise TypeError(f"ad url {url!r} holds no /positions/<number>")
    locations = ad.get("locations")
    places = [as_dict(entry) for entry in locations] if isinstance(locations, list) else []
    # The top-level coordinates are the institution's, which can lie on
    # another continent, so every place field comes from the first location.
    place = places[0] if places else {}
    return make_job(
        site="econjobmarket",
        id=match[1],
        url=url,
        title=ad.get("adtitle"),
        company=ad.get("name"),
        location=join_places(_place(entry) for entry in places),
        description=html_text(as_str(ad.get("adtext")) or ""),
        company_logo=as_str(ad.get("logo_url")),
        city=as_str(place.get("city")),
        region=as_str(place.get("state")),
        country_code=as_str(place.get("country_code")),
        latitude=finite(place.get("latitude")),
        longitude=finite(place.get("longitude")),
        posted_at=as_str(ad.get("startdate")),
        expires_at=as_str(ad.get("deadline_date")),
    )


@checked
async def search(fetcher: Fetcher) -> list[JobDict]:
    """
    List every open ad on EconJobMarket.

    One request returns the whole feed, descriptions included, in EJM's
    order. EJM applies no filter, so the search takes no options. It is
    neither paced nor retried. A malformed ad costs only that ad. The caller
    owns ``fetcher``.

    Raises:
        Stopped: The request failed or EJM sent an unreadable response.
            ``partial`` is empty.
    """
    logger.info("reading the econjobmarket ad feed")
    result = await fetcher.fetch(API_URL)
    ads = read_json(result, json_list, site="econjobmarket")
    jobs = parse_postings(ads, _parse_ad, site="econjobmarket")
    logger.info(
        "econjobmarket has %s", ngettext("%d open ad", "%d open ads", len(jobs)) % len(jobs)
    )
    return jobs
