"""LinkedIn posting details from schema.org data and page markup."""

import json
import logging
import math
import re
from collections.abc import Iterable
from gettext import ngettext
from html import unescape
from typing import Annotated, Any, NamedTuple
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from jobrake import cache
from jobrake.fetchkit import Fetcher
from jobrake.models import JobDict, employment_type, make_job
from jobrake.utils import checked, html_text

from .client import job_id, paced_fetch

logger = logging.getLogger(__name__)

# The guest fragment has the same topcard and criteria markup as the posting page
# at about a tenth of the size. The canonical page sets a locale cookie from
# the posting country's subdomain. Request ``_l=en_US`` so the fragment uses
# the labels and number format understood by the markup parsers.
FRAGMENT_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting"


# schema.org fields may be a scalar, a list, or a value in the wrong shape.
# For list-valued fields, LinkedIn's first item is the one we use.
def _obj(value: object) -> dict[str, Any]:
    if isinstance(value, list):
        value = value[0] if value else None
    return value if isinstance(value, dict) else {}


def _text_value(value: object) -> str | None:
    """Read a schema.org string, decoding the entities its script block escaped."""
    # LinkedIn HTML-escapes the JSON it embeds in the page, and entities inside
    # a script element reach the parser undecoded. A logo URL arrives with
    # "&amp;" between its query parameters and description markup as "&lt;p&gt;".
    if isinstance(value, list):
        value = value[0] if value else None
    return unescape(value) if isinstance(value, str) else None


def _number_value(value: object) -> float | None:
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


def _url(value: object) -> str | None:
    """Unwrap a bare schema.org URL or an object's ``url`` field."""
    obj = _obj(value)
    return _text_value(obj.get("url")) if obj else _text_value(value)


def _job_posting(soup: BeautifulSoup) -> dict[str, Any]:
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
            if isinstance(graph, list):
                queue.extend(graph)
            elif graph:
                queue.append(graph)
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


def _salary(soup: BeautifulSoup) -> dict[str, Any]:
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


def _company(soup: BeautifulSoup) -> dict[str, Any]:
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


def _parse_posting(soup: BeautifulSoup) -> tuple[dict[str, Any], bool]:
    """
    Extract model fields from a posting page, and report whether its schema.org block was present.

    A posting page carries the summary fields alongside the details, so one
    page is enough to build a record without a search card. Page markup fills
    fields absent from the schema.org block, which LinkedIn omits for
    country-level postings on every subdomain. Structured values win when both
    sources provide a field. Unsupported or malformed values are omitted.
    """
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
        "description": html_text(_text_value(posting.get("description")) or ""),
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


_PAGE_PATH = "/jobs/view/"
# The addresses a caller may name a posting by: its page, or the same posting
# under the guest API's own path.
_REFERENCE_PATHS = (_PAGE_PATH, f"{urlsplit(FRAGMENT_URL).path}/")


def _posting_url(url: str, posting_id: str, paths: tuple[str, ...]) -> bool:
    """Check that a URL is one of LinkedIn's addresses for one posting."""
    parts = urlsplit(url)
    return (
        parts.scheme in ("http", "https")
        and parts.netloc.lower().endswith(".linkedin.com")
        and parts.path.startswith(paths)
        and job_id(url) == posting_id
    )


def _country_canonical(url: str) -> bool:
    """
    Check for a canonical posting URL on a country subdomain.

    LinkedIn serves the schema.org block only from a posting's canonical URL,
    the title slug on the host of the posting's country. That host is ``www``
    for a US posting and a country subdomain elsewhere. A ``www`` URL looks
    the same for a posting from any country, so only a country subdomain
    passes.
    """
    parts = urlsplit(url)
    host = parts.netloc.lower()
    if host.startswith("www.") or not host.endswith(".linkedin.com"):
        return False
    if not parts.path.startswith(_PAGE_PATH):
        return False
    slug = parts.path.rstrip("/").rsplit("/", 1)[-1]
    # The canonical address carries a title slug ahead of the ID.
    return slug != job_id(url)


def _fragment_url(html: str, posting_id: str) -> str | None:
    """
    Read the posting URL a guest fragment names.

    LinkedIn writes the canonical URL here, on ``www`` for a US posting. A
    missing link, or one to another posting, yields None and a warning.
    """
    link = BeautifulSoup(html, "html.parser").select_one("a.topcard__link[href]")
    if link is None:
        logger.warning(
            "skipping posting %s. Its guest fragment names no posting URL, so LinkedIn's "
            "markup may have changed. Pass the posting URL instead",
            posting_id,
        )
        return None
    # Drop tracking params
    url = str(link["href"]).partition("?")[0]
    if not _posting_url(url, posting_id, (_PAGE_PATH,)):
        logger.warning(
            "skipping posting %s. Its guest fragment points at %s, which is not that "
            "posting's page",
            posting_id,
            url,
        )
        return None
    return url


class _Fetched(NamedTuple):
    fields: dict[str, Any] | None  # None with resolved=True records a posting that is gone
    resolved: bool  # False after a 429, another failed request, or a page without fields, so a rerun retries the URL
    stopped: bool  # True once paced_fetch has spent its retries on a 429


async def _with_fragment(fetcher: Fetcher, posting_id: str, posting: dict[str, Any]) -> _Fetched:
    # A blockless page arrives localized, so its employment and salary labels
    # may not parse. Fetch the en-US fragment once for those fields.
    fragment = await paced_fetch(fetcher, f"{FRAGMENT_URL}/{posting_id}?_l=en_US")
    # Without its fragment, the posting lacks fields a fetch would give, so it fails
    # as a whole: nothing is cached, and a rerun fetches it again.
    if fragment.status == 429:
        return _Fetched(None, resolved=False, stopped=True)
    if fragment.error:
        logger.warning(
            "skipping posting %s: its en-US fragment failed (%s). A rerun retries it",
            posting_id,
            fragment.error,
        )
        return _Fetched(None, resolved=False, stopped=False)
    fields, _ = _parse_posting(BeautifulSoup(fragment.text, "html.parser"))
    return _Fetched(fields | posting, resolved=True, stopped=False)


async def _fetch_fields(fetcher: Fetcher, url: str, posting_id: str) -> _Fetched:
    result = await paced_fetch(fetcher, _canonical(url))
    if result.status == 429:
        # paced_fetch has spent its retries, so the next posting would likely be
        # refused too. Stop instead of repeating them for every remaining posting.
        return _Fetched(None, resolved=False, stopped=True)
    if result.status in (404, 410):
        return _Fetched(None, resolved=True, stopped=False)
    if result.error:
        logger.warning("skipping posting %s: %s. A rerun retries it", url, result.error)
        return _Fetched(None, resolved=False, stopped=False)
    posting, structured = _parse_posting(BeautifulSoup(result.text, "html.parser"))
    if not posting:
        logger.warning(
            "skipping posting %s. Its page yielded no fields, so it may be a signup "
            "wall or changed markup. A rerun retries it",
            url,
        )
        return _Fetched(None, resolved=False, stopped=False)
    if structured:
        return _Fetched(posting, resolved=True, stopped=False)
    return await _with_fragment(fetcher, posting_id, posting)


def _is_posting_id(reference: str) -> bool:
    """Check for a bare numeric posting ID."""
    return reference.isascii() and reference.isdigit()


def _reference_ids(references: Iterable[str]) -> dict[str, str]:
    """Map each reference to its posting ID, raising ValueError for one that names no posting."""
    ids: dict[str, str] = {}
    for reference in references:
        ref = reference.strip()
        posting_id = ref if _is_posting_id(ref) else job_id(ref)
        if not posting_id or not (
            _is_posting_id(ref) or _posting_url(ref, posting_id, _REFERENCE_PATHS)
        ):
            raise ValueError(
                f"{reference!r} is neither a numeric posting ID nor a LinkedIn posting URL. "
                "Try 4449382178 or the posting's linkedin.com/jobs/view/... address"
            )
        ids[reference] = posting_id
    return ids


async def _lookup_address(fetcher: Fetcher, posting_id: str) -> _Fetched:
    """Learn a posting's canonical URL, as ``{"url"}``, from its guest fragment."""
    result = await paced_fetch(fetcher, f"{FRAGMENT_URL}/{posting_id}?_l=en_US")
    if result.status == 429:
        # paced_fetch has spent its retries, so later postings would likely be
        # refused too. Stop rather than retry each of them.
        return _Fetched(None, resolved=False, stopped=True)
    if result.status in (404, 410):
        return _Fetched(None, resolved=True, stopped=False)
    if result.error:
        logger.warning(
            "skipping posting %s: %s. Pass its URL to fetch the posting without this lookup",
            posting_id,
            result.error,
        )
        return _Fetched(None, resolved=False, stopped=False)
    url = _fragment_url(result.text, posting_id)
    if url is None:
        return _Fetched(None, resolved=False, stopped=False)
    return _Fetched({"url": url}, resolved=True, stopped=False)


async def _fetch_posting(fetcher: Fetcher, posting_id: str, url: str | None) -> _Fetched:
    """Fetch one posting's fields, with its ``url``, looking the URL up when none is known."""
    if url is None:
        looked = await _lookup_address(fetcher, posting_id)
        if looked.fields is None:
            return looked
        url = looked.fields["url"]
    fetched = await _fetch_fields(fetcher, url, posting_id)
    if fetched.fields is None:
        return fetched
    return fetched._replace(fields=fetched.fields | {"url": url})


def _job(posting_id: str, known: dict[str, Any], fields: dict[str, Any]) -> JobDict:
    """
    Build a posting's record from the fields known for it, overridden by its page's fields.

    A known ``url`` and ``date``, such as a search card's, stay, and a ``None``
    page value leaves the known one in place.
    """
    page = {name: value for name, value in fields.items() if value is not None}
    kept = {name: known[name] for name in ("url", "date") if name in known}
    return make_job(**(known | page | kept | {"site": "linkedin", "id": posting_id}))


async def fetch_pages(
    fetcher: Fetcher, wanted: dict[str, dict[str, Any]], *, refresh: bool
) -> dict[str, JobDict | None]:
    """
    Build a ``JobDict`` per wanted posting ID from its page, over the fields known for it.

    ``wanted`` maps each posting ID to the fields known so far, such as a
    search card. A cached record costs no request. A posting whose fields
    hold no ``url`` costs a guest-fragment request to learn its canonical
    URL. A page without the schema.org block costs one en-US fragment request
    for the remaining fields. ``refresh`` skips cache reads but still stores
    what it fetched. A persistent 429 stops further requests and keeps what
    the cache and the completed requests hold. INFO records report the
    start, progress, and resolved count.

    Returns:
        A ``JobDict`` per fetched posting and ``None`` per posting LinkedIn
        reports gone. A posting that failed has no key, so a rerun retries it.
    """
    if not wanted:
        return {}
    total = len(wanted)
    wanted_count = ngettext("%d posting", "%d postings", total) % total
    logger.info("fetching linkedin details for %s", wanted_count)
    # Cached postings come back even when a 429 stops the requests below.
    cached = {} if refresh else cache.CACHE.get("linkedin", wanted)
    found: dict[str, JobDict | None] = {
        posting_id: _job(posting_id, wanted[posting_id], dict(job))
        for posting_id, job in cached.items()
    }
    stopped = False
    for position, (posting_id, known) in enumerate(wanted.items(), start=1):
        # The CLI renders progress-flagged records as one self-updating
        # stderr line; other logging configurations show them as plain lines.
        logger.info(
            "linkedin details %d/%d", position, total, extra={"progress": (position, total)}
        )
        if posting_id in found:
            continue
        fetched = await _fetch_posting(fetcher, posting_id, known.get("url"))
        if fetched.resolved:
            job = None if fetched.fields is None else _job(posting_id, known, fetched.fields)
            found[posting_id] = job
            if job is not None:
                cache.CACHE.put([job])
        if fetched.stopped:
            stopped = True
            break
    if stopped:
        logger.warning(
            "linkedin is rate limiting this IP, so detail fetching stopped with %d of "
            "%d postings resolved. Wait a while, then rerun to fill in the rest",
            len(found),
            total,
        )
    else:
        logger.info(
            "linkedin detail fetch finished with %d of %s resolved", len(found), wanted_count
        )
    return found


@checked
async def postings(
    fetcher: Fetcher,
    references: Annotated[list[str], "LinkedIn posting IDs or URLs"],
    *,
    refresh: Annotated[bool, "refetch postings and refresh their cached copies"] = False,
) -> dict[str, JobDict | None]:
    """
    Fetch known LinkedIn postings by ID or URL.

    The result is keyed by the references given. A reference is a posting
    URL or a numeric posting ID, and references naming one posting share one
    fetch and one ``JobDict``. A canonical URL on a country subdomain is
    fetched as given. Any other reference, including an ID or a US posting's
    ``www`` URL, costs a guest-fragment request to learn the canonical URL,
    unless the cache holds the posting. A reference maps to ``None`` when
    LinkedIn reports its posting gone, and has no key after a failed request
    or a persistent 429, each logged, so a rerun retries it. The caller owns
    ``fetcher``.

    Raises:
        ValueError: A reference is neither a numeric posting ID nor a LinkedIn
            posting URL. Nothing is fetched in that case.
    """
    ids = _reference_ids(references)
    # A canonical reference is the posting's own address, so every posting
    # named by one is fetched from it.
    wanted: dict[str, dict[str, Any]] = {}
    for ref, posting_id in ids.items():
        known = wanted.setdefault(posting_id, {})
        if "url" not in known and _country_canonical(ref.strip()):
            known["url"] = ref.strip()
    found = await fetch_pages(fetcher, wanted, refresh=refresh)
    return {ref: found[posting_id] for ref, posting_id in ids.items() if posting_id in found}
