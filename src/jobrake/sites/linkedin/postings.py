"""Full posting detail from the schema.org block on a job's canonical page."""

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

# The guest fragment has the same topcard and criteria markup as the job page
# at about a tenth of the size. The canonical page sets a locale cookie from
# the posting country's subdomain. Request ``_l=en_US`` so the fragment uses
# the labels and number format understood by the markup parsers.
FRAGMENT_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting"


def _obj(value) -> dict:
    """Return the first schema.org object, or ``{}``."""
    # A field can arrive as an object, a list of them, or a bare string.
    if isinstance(value, list):
        value = value[0] if value else None
    return value if isinstance(value, dict) else {}


def _text_value(value) -> str | None:
    """Return the first schema.org text value, or ``None``."""
    if isinstance(value, list):
        value = value[0] if value else None
    return value if isinstance(value, str) else None


def _number_value(value) -> float | None:
    """Return the first schema.org numeric value, or ``None``."""
    if isinstance(value, list):
        value = value[0] if value else None
    return value if isinstance(value, int | float) and not isinstance(value, bool) else None


def _url(value) -> str | None:
    """Return one schema.org URL, either bare or wrapped in an object's ``url``."""
    obj = _obj(value)
    return _text_value(obj.get("url")) if obj else _text_value(value)


def _job_posting(soup: BeautifulSoup) -> dict:
    """Return the page's schema.org ``JobPosting`` block or ``{}``."""
    for block in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(block.string or "")
        except json.JSONDecodeError:
            continue
        queue = data if isinstance(data, list) else [data]
        for item in queue:
            if not isinstance(item, dict):
                continue
            kind = item.get("@type")
            if kind == "JobPosting" or (isinstance(kind, list) and "JobPosting" in kind):
                return item
            graph = item.get("@graph")
            queue.extend(graph if isinstance(graph, list) else [graph] if graph else [])
    return {}


def _description(soup: BeautifulSoup) -> str:
    """Return description text from the page markup or ``""``."""
    div = soup.find("div", class_=lambda c: bool(c and "show-more-less-html__markup" in c))
    return html_text(div.decode_contents()) if div else ""


def _criteria(soup: BeautifulSoup) -> dict[str, str]:
    """Map each criteria label to its value."""
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

    Only the en-US rendering with a currency code parses. It must contain two
    bounds with the same currency and period. Localized formats, currency
    symbols, and single bounds yield ``{}``. A wrong number is worse than none.
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
    """Return the company link and logo from the topcard."""
    link = soup.select_one("a.topcard__org-name-link")
    logo = soup.select_one("img.artdeco-entity-image")
    # Drop tracking params
    return {
        "company_url": str(link["href"]).partition("?")[0] if link and link.get("href") else None,
        "company_logo": logo.get("data-delayed-url") if logo else None,
    }


def _apply_type(soup: BeautifulSoup) -> str | None:
    """
    Return where the apply button leads.

    ``"onsite"`` is LinkedIn's form. ``"offsite"`` is the employer's site.
    """
    for element in soup.select("[data-tracking-control-name*='apply-link-']"):
        if found := re.search(r"apply-link-([a-z]+)", str(element["data-tracking-control-name"])):
            return found.group(1)
    return None


def _applicants(soup: BeautifulSoup) -> int | None:
    """Return the applicant count quoted on the page."""
    # The prose around it is localized, but the number is not.
    # LinkedIn displays counts above 200 as "Over 200", so no thousands
    # separator appears.
    caption = soup.select_one(".num-applicants__caption")
    found = re.search(r"\d+", caption.get_text()) if caption else None
    return int(found.group()) if found else None


def parse_posting(html: str) -> dict:
    """
    Extract a posting's fields from its canonical page.

    Page markup fills fields absent from the schema.org block. Structured
    values win when both sources provide a field. A page with nothing
    extractable yields ``{}``.
    """
    # LinkedIn omits the structured block for country-level postings on every
    # subdomain.
    fields, _ = _parse_posting(BeautifulSoup(html, "html.parser"))
    return fields


def _parse_posting(soup: BeautifulSoup) -> tuple[dict, bool]:
    """Return fields and whether the page contained a schema.org posting block."""
    posting = _job_posting(soup)
    org = _obj(posting.get("hiringOrganization"))
    place = _obj(posting.get("jobLocation"))
    address = _obj(place.get("address"))
    pay = _obj(posting.get("baseSalary"))
    amount = _obj(pay.get("value"))
    # addressCountry is Text or a Country object carrying its name.
    country = address.get("addressCountry")
    # Normalize each schema.org union before adding it to the result. Omit
    # structured values in an unsupported shape.
    from_block = {
        "description": html_text(unescape(_text_value(posting.get("description")) or "")),
        "employment_type": employment_type(_text_value(posting.get("employmentType"))),
        "posted_at": _text_value(posting.get("datePosted")),
        "expires_at": _text_value(posting.get("validThrough")),
        "company_url": _text_value(org.get("sameAs")),
        "company_logo": _url(org.get("logo")),
        "city": _text_value(address.get("addressLocality")),
        "region": _text_value(address.get("addressRegion")),
        "country_code": _text_value(country) or _text_value(_obj(country).get("name")),
        "latitude": _number_value(place.get("latitude")),
        "longitude": _number_value(place.get("longitude")),
        "salary_min": _number_value(amount.get("minValue")),
        "salary_max": _number_value(amount.get("maxValue")),
        "salary_currency": _text_value(pay.get("currency")),
        "salary_period": _text_value(amount.get("unitText")),
        "experience_months": _number_value(
            _obj(posting.get("experienceRequirements")).get("monthsOfExperience")
        ),
        "education": _text_value(
            _obj(posting.get("educationRequirements")).get("credentialCategory")
        ),
    }
    # The markup is the only source of apply_type and applicants, and the
    # only source of anything on a block-less page.
    # These selectors depend on LinkedIn's page structure and are the first
    # parsing points to break when it changes.
    from_markup = {
        "description": _description(soup),
        "employment_type": employment_type(_criteria(soup).get("Employment type")),
        **_company(soup),
        **_salary(soup),
        "apply_type": _apply_type(soup),
        "applicants": _applicants(soup),
    }
    # The block wins wherever both speak.
    fields = {
        name: value
        for source in (from_markup, from_block)
        for name, value in source.items()
        if value not in (None, "")
    }
    return fields, bool(posting)


def _canonical(url: str) -> str:
    """Return the URL form that carries the structured block."""
    # A trailing slash returns the same full page without its schema.org script.
    path, sep, query = url.partition("?")
    return path.rstrip("/") + sep + query


async def fetch_postings(
    fetcher: Fetcher, urls: Iterable[str], *, cache: bool = True
) -> dict[str, dict | None]:
    """
    Fetch full detail from the canonical page at each job's own URL.

    Pass each job's own ``/jobs/view/<slug>-<id>`` URL from the search cards.
    An ID alone reaches a page without the structured block. Duplicate and
    empty URLs are skipped. URLs for the same posting ID share one fetch and
    reuse its result. A failure returned in ``FetchResult`` costs at most that
    posting. Exceptions raised by the fetcher propagate, including
    cancellation.

    Each URL has three possible outcomes. A field dict contains the parsed
    posting, which may be partial when the page omits the structured block.
    ``None`` means a 404 or 410 confirmed the posting is gone. A URL
    absent from the result had a transient failure or nothing parseable, so a
    later call may retry it. A page without the block costs a second request
    for the en-US fragment, whose labels and numbers the markup parser knows.

    With ``cache``, fresh postings come from disk. Only missing or stale IDs
    trigger requests. Cache keys use the posting ID because its subdomain and
    slug can change.
    Each result is saved as it arrives, so an interrupted sweep keeps every
    completed fetch.
    """
    postings: dict[str, dict | None] = {}
    wanted = list(dict.fromkeys(u for u in urls if u))
    ids = {url: job_id(url) for url in wanted}
    # Keep one value per posting ID for the whole call. Seed it from the cache
    # and extend it as fetches finish so aliases reuse the same result.
    resolved = client.CACHE.get("linkedin", [i for i in ids.values() if i]) if cache else {}
    for posting_id, posting in resolved.items():
        # Cached rows may predate the current field set. Ignore unknown keys
        # before merging a row into a Job.
        if posting is not None:
            resolved[posting_id] = {
                name: value for name, value in posting.items() if name in JOB_FIELDS
            }
    attempted: set[str] = set()
    for url in wanted:
        if (posting_id := ids[url]) in resolved:
            postings[url] = resolved[posting_id]
            continue
        if posting_id:
            # Spend at most one request per posting ID during this call. After a
            # transient miss, aliases remain absent for a later retry.
            if posting_id in attempted:
                continue
            attempted.add(posting_id)
        result = await paced_fetch(fetcher, _canonical(url))
        if result.ok:
            posting, structured = _parse_posting(BeautifulSoup(result.text, "html.parser"))
            if not posting:
                continue
            if not structured and posting_id:
                # A blockless page arrives localized, so its employment and
                # salary labels may not parse. Fetch the en-US fragment once
                # for those fields, then cache the combined result.
                fragment = await paced_fetch(fetcher, f"{FRAGMENT_URL}/{posting_id}?_l=en_US")
                if fragment.ok:
                    posting = parse_posting(fragment.text) | posting
            value = posting
        elif result.error and result.error.http_status in (404, 410):
            value = None
        else:
            continue
        postings[url] = value
        if posting_id:
            resolved[posting_id] = value
            if cache:
                client.CACHE.put("linkedin", {posting_id: value})
    return postings
