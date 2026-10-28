"""EconJobMarket ad feed requests and parsing."""

import logging
import re
from gettext import ngettext
from typing import Any

from jobrake.fetchkit import Fetcher
from jobrake.models import JobDict, make_job
from jobrake.sites.responses import json_list, parse_postings, read_json
from jobrake.utils import as_str, checked, finite, html_text

logger = logging.getLogger(__name__)

API_URL = "https://backend.econjobmarket.org/data/zz_public/json/Ads"

# An ad carries no ID field. Its page URL ends in the ad's number.
_AD_ID = re.compile(r"/positions/(\d+)")


def _parse_ad(ad: dict[str, Any]) -> JobDict:
    """
    Build a record from one ad of the feed, placed at the first of its locations.

    Raises:
        TypeError: The ad's ``url`` holds no ``/positions/<number>``.
        AttributeError: The ad or its first location is not an object.
    """
    url = ad.get("url")
    match = _AD_ID.search(url) if isinstance(url, str) else None
    if match is None:
        raise TypeError(f"ad url {url!r} holds no /positions/<number>")
    locations = ad.get("locations")
    # The top-level coordinates are the institution's, which can lie on
    # another continent, so every place field comes from the first location.
    place = locations[0] if isinstance(locations, list) and locations else {}
    city = as_str(place.get("city"))
    region = as_str(place.get("state"))
    country_code = as_str(place.get("country_code"))
    parts = (city, region, country_code)
    return make_job(
        site="econjobmarket",
        id=match[1],
        url=url,
        title=ad.get("adtitle"),
        company=ad.get("name"),
        location=", ".join(part.strip() for part in parts if part and part.strip()) or None,
        description=html_text(as_str(ad.get("adtext")) or ""),
        company_logo=as_str(ad.get("logo_url")),
        city=city,
        region=region,
        country_code=country_code,
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
