"""LinkedIn posting details from schema.org data and page markup."""

import json
import logging
import math
import re
from collections.abc import Iterable
from gettext import ngettext
from html import unescape

from bs4 import BeautifulSoup

from jobrake import defaults
from jobrake.cache import POSTINGS
from jobrake.fetchkit import Fetcher
from jobrake.models import JOB_FIELDS, employment_type
from jobrake.utils import html_text

from . import client
from .client import job_id, paced_fetch, rate_limited

logger = logging.getLogger(__name__)

# The guest fragment has the same topcard and criteria markup as the job page
# at about a tenth of the size. The canonical page sets a locale cookie from
# the posting country's subdomain. Request ``_l=en_US`` so the fragment uses
# the labels and number format understood by the markup parsers.
FRAGMENT_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting"


# schema.org fields may be a scalar, a list, or a value in the wrong shape.
# For list-valued fields, LinkedIn's first item is the one we use.
def _obj(value) -> dict:
    if isinstance(value, list):
        value = value[0] if value else None
    return value if isinstance(value, dict) else {}


def _text_value(value) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    return value if isinstance(value, str) else None


def _number_value(value) -> float | None:
    if isinstance(value, list):
        value = value[0] if value else None
    # json.loads admits NaN and the infinities, which strict JSON output
    # forbids. Only finite numbers become fields.
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        return value if math.isfinite(value) else None
    except OverflowError:
        # An integer beyond float range is no usable field value.
        return None


def _url(value) -> str | None:
    """Unwrap a bare schema.org URL or an object's ``url`` field."""
    obj = _obj(value)
    return _text_value(obj.get("url")) if obj else _text_value(value)


def _job_posting(soup: BeautifulSoup) -> dict:
    """Find the first ``JobPosting`` in page JSON-LD or an ``@graph``."""
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


_SALARY_BOUND = re.compile(r"([A-Z]{3})\s?([\d,]+(?:\.\d+)?)/(yr|mo|wk|day|hr)")
_SALARY_PERIODS = {"yr": "YEAR", "mo": "MONTH", "wk": "WEEK", "day": "DAY", "hr": "HOUR"}


def _salary(soup: BeautifulSoup) -> dict:
    """
    Parse a two-bound en-US salary range from topcard markup.

    Both bounds must use the same currency code and supported period. Currency
    symbols, localized formats, single bounds, and unreadable numbers yield ``{}``.
    """
    node = soup.select_one(".compensation__salary")
    bounds = _SALARY_BOUND.findall(node.get_text()) if node else []
    if len(bounds) != 2:
        return {}
    (currency, low, period), (currency_2, high, period_2) = bounds
    if (currency, period) != (currency_2, period_2):
        return {}
    try:
        salary_min = float(low.replace(",", ""))
        salary_max = float(high.replace(",", ""))
    except ValueError:
        # The regex admits comma-only bounds, which float() rejects.
        return {}
    # A digit run past float range converts to infinity rather than raising.
    if not (math.isfinite(salary_min) and math.isfinite(salary_max)):
        return {}
    return {
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_currency": currency,
        "salary_period": _SALARY_PERIODS[period],
    }


def _company(soup: BeautifulSoup) -> dict:
    """Extract company URL and logo fields from topcard markup."""
    link = soup.select_one("a.topcard__org-name-link")
    logo = soup.select_one("img.artdeco-entity-image")
    # Drop tracking params
    return {
        "company_url": str(link["href"]).partition("?")[0] if link and link.get("href") else None,
        "company_logo": logo.get("data-delayed-url") if logo else None,
    }


def _apply_type(soup: BeautifulSoup) -> str | None:
    """Use ``onsite`` for LinkedIn forms and ``offsite`` for employer forms."""
    for element in soup.select("[data-tracking-control-name*='apply-link-']"):
        if found := re.search(r"apply-link-([a-z]+)", str(element["data-tracking-control-name"])):
            return found.group(1)
    return None


def _applicants(soup: BeautifulSoup) -> int | None:
    # The prose around it is localized, but the number is not.
    # LinkedIn displays counts above 200 as "Over 200", so no thousands
    # separator appears.
    caption = soup.select_one(".num-applicants__caption")
    found = re.search(r"\d+", caption.get_text()) if caption else None
    return int(found.group()) if found else None


def parse_posting(html: str) -> dict:
    """
    Extract model fields from a canonical posting page.

    A posting page carries the summary fields alongside the details, so one
    page is enough to build a job without a search card. Page markup fills
    fields absent from the schema.org block. Structured values win when both
    sources provide a field. A page with nothing extractable yields ``{}``.
    Unsupported or malformed values are omitted.
    """
    # LinkedIn omits the structured block for country-level postings on every
    # subdomain.
    fields, _ = _parse_posting(BeautifulSoup(html, "html.parser"))
    return fields


def _parse_posting(soup: BeautifulSoup) -> tuple[dict, bool]:
    """Extract posting fields and report whether structured data was present."""
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
        "title": _text_value(posting.get("title")),
        "company": _text_value(org.get("name")),
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
        "title": _tag_text(soup, ".topcard__title"),
        "company": _tag_text(soup, "a.topcard__org-name-link"),
        # The topcard bullets hold the place, the posting age, and the
        # applicant count. Age and count also carry the metadata class, so the
        # plain bullet is the place.
        "location": _tag_text(soup, ".topcard__flavor--bullet:not(.topcard__flavor--metadata)"),
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
    """Remove the trailing slash that suppresses LinkedIn's structured block."""
    # A trailing slash returns the same full page without its schema.org script.
    path, sep, query = url.partition("?")
    return path.rstrip("/") + sep + query


async def fetch_postings(
    fetcher: Fetcher, urls: Iterable[str], *, cache: bool = defaults.CACHE
) -> dict[str, dict | None]:
    """
    Fetch LinkedIn detail fields for a collection of posting URLs.

    URLs sharing a numeric posting ID share one hydration attempt and result.
    A page with fields but no structured block costs one en-US fragment request
    for the remaining fields when the URL has a numeric ID. A persistent 429
    stops further requests while retaining cached and completed results. Other
    transient failures leave that URL absent so a later call can retry it.
    Fetcher exceptions and cancellation propagate. Empty and duplicate URLs
    are ignored. The cache stores only numeric identities. URLs without one are
    fetched on every call. INFO records report the start, progress, and
    resolved count on completion. A persistent rate limit reports where
    fetching stopped at WARNING. The supplied transport remains open.

    Returns:
        Results keyed by the supplied URLs. A field dictionary may be partial.
        ``None`` records a confirmed 404 or 410. Missing keys represent
        retryable failures or pages with nothing parseable.
    """
    wanted = list(dict.fromkeys(u for u in urls if u))
    if not wanted:
        return {}

    total = len(wanted)
    wanted_count = ngettext("%d job", "%d jobs", total) % total
    logger.info("fetching linkedin details for %s", wanted_count)
    ids = {url: job_id(url) for url in wanted}
    # Keep one value per posting identity for the whole call. Seed it from the
    # cache and extend it as fetches finish so aliases reuse the same result.
    resolved = (
        client.CACHE.get(POSTINGS, "linkedin", [i for i in ids.values() if i]) if cache else {}
    )
    for posting_id, posting in resolved.items():
        # Cached rows may predate the current field set.
        # Ignore unknown keys before merging a row into a Job.
        if posting is not None:
            resolved[posting_id] = {
                name: value for name, value in posting.items() if name in JOB_FIELDS
            }

    attempted: set[str] = set()
    stopped = False
    for position, url in enumerate(wanted, start=1):
        # The CLI renders progress-flagged records as one self-updating
        # stderr line; other logging configurations show them as plain lines.
        logger.info(
            "linkedin details %d/%d", position, total, extra={"progress": (position, total)}
        )
        # A posting's identity is its ID when the URL carries one, else the
        # URL itself. IDs are digit strings and ID-less URLs never are, so the
        # two kinds of key cannot collide. Only real IDs reach the disk cache.
        posting_id = ids[url]
        identity = posting_id or url
        # Spend at most one request per identity during this call.
        # After a transient miss, aliases remain absent for a later retry.
        if identity in resolved or identity in attempted:
            continue
        attempted.add(identity)
        result = await paced_fetch(fetcher, _canonical(url))
        if rate_limited(result):
            # The retry inside paced_fetch already waited and failed. The
            # limit belongs to the IP, so the next posting would fare no
            # better; spending a wait per posting turns one block into a
            # stall over the whole list.
            stopped = True
            break
        if result.error and result.error.http_status in (404, 410):
            resolved[identity] = None
            if cache and posting_id:
                client.CACHE.put(POSTINGS, "linkedin", {posting_id: None})
            continue
        if result.error:
            logger.warning("posting %s: %s; skipped, a rerun retries it", url, result.error.message)
            continue
        posting, structured = _parse_posting(BeautifulSoup(result.text, "html.parser"))
        if not posting:
            logger.warning(
                "posting %s: the page yielded no fields, possibly a signup "
                "wall or changed markup; a rerun retries it",
                url,
            )
            continue
        if not structured and posting_id:
            # A blockless page arrives localized, so its employment and
            # salary labels may not parse. Fetch the en-US fragment once
            # for those fields, then cache the combined result.
            fragment = await paced_fetch(fetcher, f"{FRAGMENT_URL}/{posting_id}?_l=en_US")
            if rate_limited(fragment):
                # Keep and cache the canonical fields before ending hydration.
                stopped = True
            elif fragment.error:
                logger.warning(
                    "posting %s: fragment fetch failed (%s); keeping the partial canonical fields",
                    posting_id,
                    fragment.error.message,
                )
            else:
                posting = parse_posting(fragment.text) | posting
        resolved[identity] = posting
        if cache and posting_id:
            client.CACHE.put(POSTINGS, "linkedin", {posting_id: posting})
        if stopped:
            break

    # Assemble results in input order. After a rate-limit stop, URLs never
    # visited still take cached and already resolved values.
    postings: dict[str, dict | None] = {}
    for url in wanted:
        identity = ids[url] or url
        if identity in resolved:
            postings[url] = resolved[identity]
    if stopped:
        logger.warning(
            "linkedin is rate limiting this IP; stopping detail hydration "
            "with %d of %d postings resolved. Wait a while, then rerun to "
            "fill in the rest",
            len(postings),
            total,
        )
    elif len(postings) == total:
        logger.info("linkedin detail fetch finished with %s resolved", wanted_count)
    else:
        logger.info(
            "linkedin detail fetch finished with %d of %s resolved", len(postings), wanted_count
        )
    return postings
