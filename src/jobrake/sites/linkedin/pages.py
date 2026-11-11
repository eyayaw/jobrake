"""LinkedIn posting details from schema.org data and page markup."""

import asyncio
import json
import logging
import math
import re
from gettext import ngettext
from html import unescape
from typing import Annotated, Any
from urllib.parse import parse_qs, unquote, urlsplit, urlunsplit

lazy from bs4 import BeautifulSoup

from jobrake import cache
from jobrake.fetchkit import Fetcher, FetchResult
from jobrake.models import JobDict, Place, employment_type, make_job, make_places
from jobrake.utils import checked, finite, html_text, report_progress

from .client import FABRICS_WANTED, FRAGMENT_URL, job_id, numeric, paced_fetch

logger = logging.getLogger(__name__)


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
    return finite(value)


def _url(value: object) -> str | None:
    """Unwrap a bare schema.org URL or an object's ``url`` field."""
    obj = _obj(value)
    return _text_value(obj.get("url")) if obj else _text_value(value)


def _job_posting(soup: BeautifulSoup) -> dict[str, Any]:
    """Find the first ``JobPosting`` in page JSON-LD or an ``@graph``."""
    for block in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(block.string or "")
        except ValueError:
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


def _block_places(posting: dict[str, Any]) -> list[dict[str, Any]]:
    """Read the parts of each schema.org ``jobLocation``, one place per entry."""
    entries = posting.get("jobLocation")
    places = []
    for place in entries if isinstance(entries, list) else [entries]:
        if not isinstance(place, dict):
            continue
        address = _obj(place.get("address"))
        # addressCountry is Text or a Country object carrying its name.
        country = address.get("addressCountry")
        places.append(
            {
                "city": _text_value(address.get("addressLocality")),
                "region": _text_value(address.get("addressRegion")),
                "country_code": _text_value(country) or _text_value(_obj(country).get("name")),
                "latitude": _number_value(place.get("latitude")),
                "longitude": _number_value(place.get("longitude")),
            }
        )
    return places


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
    pay = _obj(posting.get("baseSalary"))
    amount = _obj(pay.get("value"))
    # The topcard bullets hold the place, the posting age, and the applicant
    # count. Age and count also carry the metadata class, so the plain bullet
    # is the place.
    label = _tag_text(soup, ".topcard__flavor--bullet:not(.topcard__flavor--metadata)")
    # Places count once normalized, so a block of empty entries holds none.
    places = make_places(_block_places(posting))
    # A lone block place is the place the bullet names. Several keep the names of their parts.
    if len(places) == 1 and label:
        places = [{**places[0], "name": label}]
    elif not places and label:
        places = [Place(name=label)]
    # JobDict counts whole months.
    months = _number_value(_obj(posting.get("experienceRequirements")).get("monthsOfExperience"))
    from_block = {
        "title": _text_value(posting.get("title")),
        "company": _text_value(org.get("name")),
        "description": html_text(_text_value(posting.get("description")) or ""),
        "employment_type": employment_type(_text_value(posting.get("employmentType"))),
        "posted_at": _text_value(posting.get("datePosted")),
        "expires_at": _text_value(posting.get("validThrough")),
        "company_url": _text_value(org.get("sameAs")),
        "company_logo": _url(org.get("logo")),
        "locations": places,
        "salary_min": _number_value(amount.get("minValue")),
        "salary_max": _number_value(amount.get("maxValue")),
        "salary_currency": _text_value(pay.get("currency")),
        "salary_period": _text_value(amount.get("unitText")),
        "experience_months": months if isinstance(months, int) else None,
        "education": _text_value(
            _obj(posting.get("educationRequirements")).get("credentialCategory")
        ),
    }
    # Only markup supplies apply_type and applicants, or any field when the
    # page lacks schema.org data.
    from_markup = {
        "title": _tag_text(soup, ".topcard__title"),
        "company": _tag_text(soup, "a.topcard__org-name-link"),
        "description": _description(soup),
        "employment_type": employment_type(_criteria(soup).get("Employment type")),
        **_company(soup),
        **_salary(soup),
        "apply_type": _apply_type(soup),
        "applicants": _applicants(soup),
    }
    fields = {
        name: value
        for source in (from_markup, from_block)
        for name, value in source.items()
        if value not in (None, "", [])
    }
    return fields, bool(posting)


def _canonical(url: str) -> str:
    """Reduce a posting URL to its page address, without a query, a fragment, or a trailing slash."""
    # A trailing slash returns the same full page without its schema.org script.
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=parts.path.rstrip("/"), query="", fragment=""))


_PAGE_PATH = "/jobs/view/"
_WWW_HOSTS = ("linkedin.com", "www.linkedin.com")
# The addresses a caller may name a posting by: its page, or the same posting
# under the guest API's own path.
_REFERENCE_PATHS = (_PAGE_PATH, f"{urlsplit(FRAGMENT_URL).path}/")


def _posting_url(url: str, posting_id: str, paths: tuple[str, ...]) -> bool:
    """Check that a URL is one of LinkedIn's addresses for one posting."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return (
        parts.scheme in ("http", "https")
        and f".{parts.hostname}".endswith(".linkedin.com")
        and parts.path.startswith(paths)
        and job_id(url) == posting_id
    )


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


class _Skip(Exception):
    """
    A posting failed, so it gets no result and a rerun retries it.

    ``stop`` marks a persistent 429, which ends the fetch. Otherwise the message
    is the reason ``_read`` logs, and an empty message means the raiser already
    logged it.
    """

    def __init__(self, message: str = "", *, stop: bool = False) -> None:
        super().__init__(message)
        self.stop = stop


async def _request(fetcher: Fetcher, url: str) -> FetchResult | None:
    """
    Return the response, or None when LinkedIn reports the posting gone with HTTP 404 or 410.

    Raises:
        _Skip: The request failed, or paced_fetch spent its retries on a 429.
    """
    result = await paced_fetch(fetcher, url)
    if result.status == 429:
        # paced_fetch has spent its retries, so the next posting would likely be
        # refused too. Stop instead of repeating them for every remaining posting.
        raise _Skip(stop=True)
    if result.status in (404, 410):
        return None
    if result.error:
        raise _Skip(result.error)
    return result


async def _page(
    fetcher: Fetcher, posting_id: str, url: str, *, candidate: bool = False
) -> tuple[str, dict[str, Any] | None, bool] | None:
    """
    Read a posting page, following its canonical link to another address once, and parse its fields.

    Return None for a gone posting, or missing fields for an unrelated redirect.
    An empty field mapping means the posting page yielded no usable data.
    """
    for _ in range(2):
        result = await _request(fetcher, url)
        if result is None:
            return None
        if not _posting_url(result.url, posting_id, (_PAGE_PATH,)):
            return url, None, False
        url = _canonical(result.url)
        soup = BeautifulSoup(result.text, "html.parser")
        # Measured 2026-11-07: www pages name the posting country's canonical
        # URL here even when they omit its schema.org fields.
        link = soup.select_one('link[rel="canonical"][href]')
        if link is not None:
            canonical = str(link["href"])
            if not _posting_url(canonical, posting_id, (_PAGE_PATH,)):
                raise _Skip(
                    f"its page names {canonical} as canonical, which is not that posting's "
                    "page, so LinkedIn may have replaced the posting or changed its markup"
                )
            # Measured 2026-11-10: a renamed posting still answers at its old
            # slug, without its schema.org fields, and names the new slug here.
            # Decoded, two spellings of one address are equal, such as a raw
            # "ö" and "%C3%B6".
            canonical = _canonical(canonical)
            if unquote(canonical) != unquote(url):
                url, candidate = canonical, False
                continue
        elif candidate and urlsplit(url).hostname in _WWW_HOSTS:
            raise _Skip(f"its page at {url} names no canonical address")
        return url, *_parse_posting(soup)
    raise _Skip(
        f"its canonical page names another canonical address, {url}, so LinkedIn's pages "
        "for it may point at each other"
    )


async def _resolve_page(
    fetcher: Fetcher, posting_id: str, url: str | None, *, candidate: bool = False
) -> tuple[str, dict[str, Any] | None, bool, FetchResult | None] | None:
    """Find the canonical page and retain any guest fragment fetched to locate it."""
    fragment_url = f"{FRAGMENT_URL}/{posting_id}?_l=en_US"
    fragment = None
    if candidate and url is not None:
        try:
            page = await _page(fetcher, posting_id, url, candidate=True)
        except _Skip as skip:
            if skip.stop:
                raise
        else:
            if page is not None and page[1]:
                return *page, None
        url = None
    if url is None:
        if (fragment := await _request(fetcher, fragment_url)) is None:
            return None
        if (url := _fragment_url(fragment.text, posting_id)) is None:
            raise _Skip
    if (page := await _page(fetcher, posting_id, _canonical(url))) is None:
        return None
    return *page, fragment


async def _fetch_posting(
    fetcher: Fetcher, posting_id: str, url: str | None, *, candidate: bool = False
) -> dict[str, Any] | None:
    """Read posting fields, using only its guest fragment when the page redirects elsewhere."""
    page = await _resolve_page(fetcher, posting_id, url, candidate=candidate)
    if page is None:
        return None
    url, fields, structured, fragment = page
    redirected = fields is None
    if redirected:
        fields = {}
        logger.warning(
            "posting %s redirected away from its page; using only its guest fragment", posting_id
        )
    elif not fields:
        logger.warning(
            "skipping posting %s. Its page yielded no fields, so it may be a signup "
            "wall or changed markup. A rerun retries it",
            url,
        )
        raise _Skip
    if not structured:
        # Localized markup may use employment and salary labels the parsers do
        # not recognize. Without schema.org data, the en-US fragment supplies
        # those fields. Reuse it if the canonical URL lookup already fetched it.
        if fragment is None:
            fragment = await _request(fetcher, f"{FRAGMENT_URL}/{posting_id}?_l=en_US")
        if fragment is None:
            logger.warning(
                "skipping posting %s: its en-US fragment is gone. A rerun retries it",
                posting_id,
            )
            raise _Skip
        if redirected and _fragment_url(fragment.text, posting_id) is None:
            raise _Skip
        fields = _parse_posting(BeautifulSoup(fragment.text, "html.parser"))[0] | fields
        if not fields:
            logger.warning(
                "skipping posting %s: its guest fragment yielded no fields. A rerun retries it",
                posting_id,
            )
            raise _Skip
    return fields | {"url": url}


def _reference(reference: str) -> tuple[str, str | None]:
    """
    Extract the posting ID and, for a title-slug URL, its page address.

    A posting URL is its page, its guest API address, the link in a job alert
    email, or a search page that names it in ``currentJobId``.

    Raises:
        ValueError: The reference is neither a numeric posting ID nor a
            LinkedIn posting URL.
    """
    ref = reference.strip()
    if numeric(ref):
        return ref, None
    parts = urlsplit(ref)
    shown = parse_qs(parts.query).get("currentJobId", [""])[0]
    # The /comm/ link redirects to the page, and a search page carries only the
    # ID, so each is rewritten to the page address of its ID. A path that names a
    # posting keeps it over any currentJobId.
    if parts.path.startswith(f"/comm{_PAGE_PATH}"):
        ref = urlunsplit(parts._replace(path=parts.path.removeprefix("/comm")))
    elif numeric(shown) and not job_id(ref):
        ref = urlunsplit(parts._replace(path=f"{_PAGE_PATH}{shown}"))
    posting_id = job_id(ref)
    if not (posting_id and _posting_url(ref, posting_id, _REFERENCE_PATHS)):
        raise ValueError(
            f"{reference!r} is neither a numeric posting ID nor a LinkedIn posting URL. "
            "Try 4449382178 or the posting's https://www.linkedin.com/jobs/view/... address"
        )
    parts = urlsplit(ref)
    # The canonical address carries a title slug ahead of the ID.
    slug = parts.path.rstrip("/").rsplit("/", 1)[-1]
    page = parts.path.startswith(_PAGE_PATH) and slug != posting_id
    return posting_id, _canonical(ref) if page else None


def _job(posting_id: str, known: dict[str, Any], fields: dict[str, Any]) -> JobDict:
    """
    Build a posting's record from the fields known for it, overridden by its page's fields.

    A known ``url`` and ``date``, such as a search card's, stay when set, and a
    ``None`` or empty page value leaves the known one in place. When the page
    and the known fields each have one place, the page's place takes the known
    place's name, so a record read from the cache names its place as a fresh
    read does.
    """
    page = {name: value for name, value in fields.items() if value not in (None, [])}
    places, known_places = page.get("locations"), known.get("locations") or []
    if places and len(places) == 1 and len(known_places) == 1:
        page["locations"] = [{**places[0], "name": known_places[0]["name"]}]
    kept = {name: known[name] for name in ("url", "date") if known.get(name)}
    return make_job(**(known | page | kept | {"site": "linkedin", "id": posting_id}))


async def _read(
    fetcher: Fetcher, posting_id: str, known: dict[str, Any], url: str | None
) -> dict[str, JobDict | None]:
    """
    Read one posting and cache its page fields, mapping it to its record or to ``None`` if gone.

    A failed posting yields ``{}`` and a warning. A persistent 429 propagates
    as ``_Skip`` with ``stop`` set.
    """
    try:
        fields = await _fetch_posting(
            fetcher,
            posting_id,
            url or known.get("url"),
            candidate=urlsplit(url or "").hostname in _WWW_HOSTS,
        )
    except _Skip as skip:
        if skip.stop:
            raise
        if str(skip):
            logger.warning("skipping posting %s: %s. A rerun retries it", posting_id, skip)
        return {}
    if fields is None:
        return {posting_id: None}
    # Cache page fields only, so a later caller's record keeps its own card values.
    cache.CACHE.put([_job(posting_id, {}, fields)])
    return {posting_id: _job(posting_id, known, fields)}


# Two workers per fabric. Measured live on 2026-11-09, six workers held the
# pacer's sustained rate and three did not, because a worker waits out its own
# retries and second requests. The count also bounds the requests sent after a
# persistent 429 before the call stops.
_WORKERS = 2 * FABRICS_WANTED


async def fetch_pages(
    fetcher: Fetcher,
    wanted: dict[str, dict[str, Any]],
    *,
    urls: dict[str, str] | None = None,
) -> dict[str, JobDict | None]:
    """
    Build a ``JobDict`` per wanted posting ID from its page, over the fields known for it.

    ``wanted`` maps each posting ID to the fields known so far, such as a
    search card. ``urls`` supplies page addresses for individual IDs. A cached
    record costs no request. Without an address in ``urls`` or the known fields,
    a guest-fragment request locates the canonical page. A page without
    schema.org data needs that fragment for additional fields; the lookup's
    response is reused when available.
    A fixed pool of workers, two per fabric, takes the postings in order and
    leaves request pacing to ``paced_fetch``. A persistent 429 stops this
    call, cancels the reads in progress, and keeps cached and completed
    results. INFO records report progress and the count of pages read.

    Returns:
        A ``JobDict`` per fetched posting and ``None`` per posting LinkedIn
        reports gone. A posting that failed has no key, so a rerun retries it.
    """
    if not wanted:
        return {}
    total = len(wanted)
    logger.info("reading %s", ngettext("%d linkedin page", "%d linkedin pages", total) % total)
    # Cached postings come back even when a 429 stops the requests below.
    cached = cache.CACHE.get("linkedin", wanted)
    found: dict[str, JobDict | None] = {
        posting_id: _job(posting_id, wanted[posting_id], dict(job))
        for posting_id, job in cached.items()
    }
    done = len(cached)
    report_progress(logger, "linkedin pages", done, total)
    # Every worker takes from one iterator, so each posting is read once.
    pending = iter([item for item in wanted.items() if item[0] not in cached])

    async def work() -> None:
        nonlocal done
        for posting_id, known in pending:
            found.update(await _read(fetcher, posting_id, known, (urls or {}).get(posting_id)))
            done += 1
            report_progress(logger, "linkedin pages", done, total)

    stopped = False
    try:
        # The group cancels the other workers on the first error and awaits them all,
        # through a repeated cancellation, so none outlives the caller's transport.
        async with asyncio.TaskGroup() as group:
            for _ in range(_WORKERS):
                group.create_task(work())
    except ExceptionGroup as errors:
        # A fetcher's own exception leaves as itself and outranks a persistent 429.
        for error in errors.exceptions:
            if not isinstance(error, _Skip):
                raise error from None
        stopped = True
    if stopped:
        logger.warning(
            "linkedin is rate limiting this IP, so reading pages stopped at %d of %d. "
            "Wait a while, then rerun to fill in the rest",
            len(found),
            total,
        )
    else:
        logger.info(
            ngettext("read %d of %d linkedin page", "read %d of %d linkedin pages", total),
            len(found),
            total,
        )
    return found


@checked
async def postings(
    fetcher: Fetcher,
    references: Annotated[list[str], "LinkedIn posting IDs or URLs"],
) -> dict[str, JobDict | None]:
    """
    Fetch known LinkedIn postings by ID or URL.

    The result is keyed by the references given. A reference is a posting
    URL or a numeric posting ID. References naming one posting share a read
    and one ``JobDict``. Cached postings need no request. Otherwise, title-slug
    URLs are tried directly; an uncertain ``www`` address falls back to a
    guest-fragment lookup. Other references need that lookup first.
    A reference maps to ``None`` when LinkedIn reports its posting gone.
    A failed request or persistent 429 is logged and leaves out the affected
    references, so a rerun retries them. The caller owns ``fetcher``.

    Raises:
        ValueError: A reference is neither a numeric posting ID nor a LinkedIn
            posting URL. Nothing is fetched in that case.
    """
    ids: dict[str, str] = {}
    wanted: dict[str, dict[str, Any]] = {}
    urls: dict[str, str] = {}
    for ref in references:
        posting_id, url = _reference(ref)
        ids[ref] = posting_id
        wanted.setdefault(posting_id, {})
        if url:
            previous = urls.setdefault(posting_id, url)
            if (
                urlsplit(previous).hostname in _WWW_HOSTS
                and urlsplit(url).hostname not in _WWW_HOSTS
            ):
                urls[posting_id] = url
    found = await fetch_pages(fetcher, wanted, urls=urls)
    return {ref: found[posting_id] for ref, posting_id in ids.items() if posting_id in found}
