"""EconJobMarket ad feed requests and parsing."""

import logging
import re
from gettext import ngettext
from typing import Any

from jobrake.fetchkit import Fetcher
from jobrake.models import JobDict, make_job
from jobrake.sites.responses import json_list, parse_postings, read_json
from jobrake.utils import as_dict, as_str, checked, html_text

logger = logging.getLogger(__name__)

API_URL = "https://backend.econjobmarket.org/data/zz_public/json/Ads"

# An ad carries no ID field. Its page URL ends in the ad's number.
_AD_ID = re.compile(r"/positions/(\d+)")


def _names(entries: object) -> list[str]:
    """Read the names of a list of ``{"name": ...}`` entries, as the feed sends position types and categories."""
    return [
        name
        for entry in (entries if isinstance(entries, list) else [])
        if (name := as_str(as_dict(entry).get("name")))
    ]


def _parse_ad(ad: dict[str, Any]) -> JobDict:
    """
    Build a record from one ad of the feed, with each of its locations.

    Raises:
        TypeError: The ad's ``url`` holds no ``/positions/<number>``.
        AttributeError: The ad is not an object.
    """
    url = ad.get("url")
    match = _AD_ID.search(url) if isinstance(url, str) else None
    if match is None:
        raise TypeError(f"ad url {url!r} holds no /positions/<number>")
    # "All departments" stands for no unit in particular, in 61 of 319 ads on 2026-10-28.
    department = as_str(ad.get("department"))
    locations = ad.get("locations")
    # The top-level coordinates are the institution's, which can lie on
    # another continent, so each place takes its own.
    places = [
        {
            "city": place.get("city"),
            "region": place.get("state"),
            "country_code": place.get("country_code"),
            "latitude": place.get("latitude"),
            "longitude": place.get("longitude"),
        }
        for place in map(as_dict, locations if isinstance(locations, list) else [])
    ]
    return make_job(
        site="econjobmarket",
        id=match[1],
        url=url,
        title=ad.get("adtitle"),
        company=ad.get("name"),
        locations=places,
        description=html_text(as_str(ad.get("adtext")) or ""),
        company_logo=as_str(ad.get("logo_url")),
        department=department if department != "All departments" else None,
        posted_at=as_str(ad.get("startdate")),
        expires_at=as_str(ad.get("deadline_date")),
        # Ranks such as Assistant Professor, and fields of economics such as Econometrics.
        site_data={
            "position_types": _names(ad.get("position_types")),
            "categories": _names(ad.get("categories")),
        },
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
