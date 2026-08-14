"""Description text from the guest jobPosting fragment, served from disk on repeats."""

from __future__ import annotations

from collections.abc import Iterable

from bs4 import BeautifulSoup

from jobrake.cache import DescriptionCache
from jobrake.core import html_text
from jobrake.fetchkit import Fetcher

from .client import DETAIL_URL, paced_fetch

# One cache per process, lazy, so no file is touched until the first cached fetch.
CACHE = DescriptionCache()


def parse_description(html: str) -> str:
    """
    Description text from a job page or guest fragment; ``""`` when the markup is absent.

    LinkedIn nondeterministically serves a signup page (interstitial) instead of the job page.
    """
    soup = BeautifulSoup(html, "html.parser")
    div = soup.find("div", class_=lambda c: c and "show-more-less-html__markup" in c)
    return html_text(div.decode_contents()) if div else ""


async def fetch_descriptions(
    fetcher: Fetcher, ids: Iterable[str], *, cache: bool = True
) -> dict[str, str | None]:
    """
    Full description per posting id, via the guest jobPosting fragment.

    The fragment (~30KB) carries the same description markup as the full
    job page (~300KB) at the same one-token price. Duplicate and empty ids
    are skipped. Three outcomes per id: description text (hydrated), ``None``
    (the posting is gone—404/410—stop asking), or absent from the result
    (transient: rate-limited past the retry, network failure, or markup
    absent) and safe to try again later. Never raises.

    With ``cache`` (the default), ids still fresh in the on-disk cache
    (``CACHE``; freshness window ``jobrake.cache.TTL``) are served from disk
    and only the rest cost requests. Each result is saved as it arrives, so
    an interrupted sweep keeps everything it already paid for.
    """
    wanted = list(dict.fromkeys(i for i in ids if i))
    cached = CACHE.get("linkedin", wanted) if cache else {}
    fetched: dict[str, str | None] = {}
    for posting_id in wanted:
        if posting_id in cached:
            continue
        result = await paced_fetch(fetcher, f"{DETAIL_URL}/{posting_id}")
        if result.ok:
            if not (description := parse_description(result.text)):
                continue
            value = description
        elif result.error.http_status in (404, 410):
            value = None
        else:
            continue
        fetched[posting_id] = value
        if cache:
            CACHE.put("linkedin", {posting_id: value})
    return cached | fetched
