"""Full posting detail from the schema.org block on a job's canonical page."""

from __future__ import annotations

import json
import re
from html import unescape

from bs4 import BeautifulSoup

from jobrake.models import employment_type
from jobrake.utils import html_text


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
