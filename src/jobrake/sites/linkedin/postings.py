"""Full posting detail from the schema.org block on a job's canonical page."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from html import unescape

from bs4 import BeautifulSoup

from jobrake.fetchkit import Fetcher
from jobrake.models import JOB_FIELDS, employment_type
from jobrake.utils import html_text

from . import client
from .client import job_id, paced_fetch

# The guest fragment: the same topcard and criteria markup as the job page,
# ~10x smaller. Requested with ``_l=en_US`` because the canonical page,
# fetched just before on the posting country's subdomain, plants its locale
# as a cookie that would localize the fragment too—and en-US is the one
# locale whose labels and number format the markup parsers understand.
FRAGMENT_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting"


def _obj(value) -> dict:
    """One schema.org object, or ``{}``."""
    # A field can arrive as an object, a list of them, or a bare string.
    if isinstance(value, list):
        value = value[0] if value else None
    return value if isinstance(value, dict) else {}


def _job_posting(soup: BeautifulSoup) -> dict:
    """The page's schema.org ``JobPosting`` block; ``{}`` when the page carries none."""
    for block in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(block.string or "")
        except json.JSONDecodeError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                return item
    return {}


def _description(soup: BeautifulSoup) -> str:
    """Description text from the page markup; ``""`` when the markup is absent."""
    div = soup.find("div", class_=lambda c: bool(c and "show-more-less-html__markup" in c))
    return html_text(div.decode_contents()) if div else ""


def _criteria(soup: BeautifulSoup) -> dict[str, str]:
    """Label -> value from the criteria list (Seniority level, Employment type, ...)."""
    pairs = {}
    for item in soup.select(".description__job-criteria-item"):
        label = item.select_one(".description__job-criteria-subheader")
        value = item.select_one(".description__job-criteria-text")
        if label and value:
            pairs[label.get_text(strip=True)] = value.get_text(strip=True)
    return pairs


_SALARY_BOUND = re.compile(r"([A-Z]{3})\s?([\d,]+(?:\.\d+)?)/(yr|mo|wk|day|hr)")
_SALARY_PERIODS = {"yr": "YEAR", "mo": "MONTH", "wk": "WEEK", "day": "DAY", "hr": "HOUR"}


def _salary(soup: BeautifulSoup) -> dict:
    """
    Salary fields from the topcard text: ``AED 756,000.00/yr - AED 924,000.00/yr``.

    Only the en-US rendering with a currency code parses: two bounds
    sharing one currency and period. Anything else (a localized format, a
    symbol currency, a single bound) yields ``{}``. A wrong number is
    worse than none.
    """
    node = soup.select_one(".compensation__salary")
    bounds = _SALARY_BOUND.findall(node.get_text()) if node else []
    if len(bounds) != 2:
        return {}
    (currency, low, period), (currency_2, high, period_2) = bounds
    if (currency, period) != (currency_2, period_2):
        return {}
    return {
        "salary_min": float(low.replace(",", "")),
        "salary_max": float(high.replace(",", "")),
        "salary_currency": currency,
        "salary_period": _SALARY_PERIODS[period],
    }


def _company(soup: BeautifulSoup) -> dict:
    """Company link and logo from the topcard."""
    link = soup.select_one("a.topcard__org-name-link")
    logo = soup.select_one("img.artdeco-entity-image")
    # Drop tracking params
    return {
        "company_url": str(link["href"]).partition("?")[0] if link and link.get("href") else None,
        "company_logo": logo.get("data-delayed-url") if logo else None,
    }


def _apply_type(soup: BeautifulSoup) -> str | None:
    """
    Where the apply button leads.

    ``"onsite"`` is LinkedIn's own form, ``"offsite"`` the employer's site.
    """
    for element in soup.select("[data-tracking-control-name*='apply-link-']"):
        if found := re.search(r"apply-link-([a-z]+)", str(element["data-tracking-control-name"])):
            return found.group(1)
    return None


def _applicants(soup: BeautifulSoup) -> int | None:
    """The applicant count quoted on the page."""
    # The prose around it is localized, but the number is not.
    # LinkedIn buckets >200 applicants into "Over 200", so it won't grow a thousands separator.
    caption = soup.select_one(".num-applicants__caption")
    found = re.search(r"\d+", caption.get_text()) if caption else None
    return int(found.group()) if found else None


def parse_posting(html: str) -> dict:
    """
    Extract a posting's fields from its canonical page.

    Returns a dict of ``Job`` fields, holding only what we could
    extract. A page with nothing extractable yields ``{}``.

    Two sources feed the dict. The page's schema.org JobPosting block
    carries the structured fields, renamed to the model's names. The
    page markup fills what the block omits.

    The block is not always there. LinkedIn serves it only when the
    posting names a city and the request hits the posting country's
    subdomain. A country-level posting never carries it, on any
    subdomain. A block-less page yields the markup fields alone.
    """
    soup = BeautifulSoup(html, "html.parser")
    posting = _job_posting(soup)
    org = _obj(posting.get("hiringOrganization"))
    place = _obj(posting.get("jobLocation"))
    address = _obj(place.get("address"))
    pay = _obj(posting.get("baseSalary"))
    amount = _obj(pay.get("value"))
    from_block = {
        "description": html_text(unescape(posting.get("description") or "")),
        "employment_type": employment_type(posting.get("employmentType")),
        "posted_at": posting.get("datePosted"),
        "expires_at": posting.get("validThrough"),
        "company_url": org.get("sameAs"),
        "company_logo": org.get("logo"),
        "city": address.get("addressLocality"),
        "region": address.get("addressRegion"),
        "country_code": address.get("addressCountry"),
        "latitude": place.get("latitude"),
        "longitude": place.get("longitude"),
        "salary_min": amount.get("minValue"),
        "salary_max": amount.get("maxValue"),
        "salary_currency": pay.get("currency"),
        "salary_period": amount.get("unitText"),
        "experience_months": _obj(posting.get("experienceRequirements")).get("monthsOfExperience"),
        "education": _obj(posting.get("educationRequirements")).get("credentialCategory"),
    }
    # The markup is the only source of apply_type and applicants, and the
    # only source of anything on a block-less page.
    # Its selectors are the first to break if (when) LinkedIn restyles.
    from_markup = {
        "description": _description(soup),
        "employment_type": employment_type(_criteria(soup).get("Employment type")),
        **_company(soup),
        **_salary(soup),
        "apply_type": _apply_type(soup),
        "applicants": _applicants(soup),
    }
    # The block wins wherever both speak.
    return {
        name: value
        for source in (from_markup, from_block)
        for name, value in source.items()
        if value not in (None, "")
    }


def _canonical(url: str) -> str:
    """The URL form that carries the structured block."""
    # A trailing slash suppresses it: same page, 200 and full size, no schema.org script.
    path, sep, query = url.partition("?")
    return path.rstrip("/") + sep + query


async def fetch_postings(
    fetcher: Fetcher, urls: Iterable[str], *, cache: bool = True
) -> dict[str, dict | None]:
    """
    Full detail per job, from the canonical page at each job's own URL.

    Takes each job's own URL (``/jobs/view/<slug>-<id>``), the one the
    search cards carry. An id alone reaches a page without the structured
    block. Duplicate and empty urls are skipped. Never raises.

    Three outcomes per url. A dict of fields means hydrated, partial when
    the page omits the structured block. ``None`` means the posting is
    gone (404 or 410): stop asking. Absent from the result means a
    transient miss (rate-limited past the retry, a network failure, or a
    page with nothing to parse): safe to try again later. A page without
    the block costs a second request for the en-US fragment, which
    renders the labeled markup fields parseable.

    With ``cache`` (the default), postings still fresh on disk are served
    from it and only the rest cost requests. Cached under the posting id,
    not the url: the subdomain and slug vary under one posting, the id
    does not. Each result is saved as it arrives, so an interrupted sweep
    keeps everything it already paid for.
    """
    postings: dict[str, dict | None] = {}
    wanted = list(dict.fromkeys(u for u in urls if u))
    ids = {url: job_id(url) for url in wanted}
    cached = client.CACHE.get("linkedin", [i for i in ids.values() if i]) if cache else {}
    for url in wanted:
        if (posting_id := ids[url]) in cached:
            posting = cached[posting_id]
            # A cached row may predate the current field set; serve only the
            # keys the model has so the merge in search cannot raise.
            if posting is not None:
                posting = {name: value for name, value in posting.items() if name in JOB_FIELDS}
            postings[url] = posting
            continue
        result = await paced_fetch(fetcher, _canonical(url))
        if result.ok:
            if not (posting := parse_posting(result.text)):
                continue
            if "application/ld+json" not in result.text and posting_id:
                # A block-less page arrives localized, hiding the labeled
                # fields (employment type, salary) from the markup parsers;
                # the en-US fragment repeats it parseably. One extra request,
                # only for these postings, then cached like any other.
                fragment = await paced_fetch(fetcher, f"{FRAGMENT_URL}/{posting_id}?_l=en_US")
                if fragment.ok:
                    posting = parse_posting(fragment.text) | posting
            value = posting
        elif result.error and result.error.http_status in (404, 410):
            value = None
        else:
            continue
        postings[url] = value
        if cache and posting_id:
            client.CACHE.put("linkedin", {posting_id: value})
    return postings
