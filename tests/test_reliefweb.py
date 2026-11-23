"""ReliefWeb paging, filtering, and parsing tests."""

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from fakes import PagedFetcher

from jobrake import Stopped, check
from jobrake.fetchkit import FetchResult
from jobrake.sites import reliefweb

# A posting from api.reliefweb.int/v2/jobs with profile=full, fetched 2026-11-23, with its texts cut
# short. The second country is ReliefWeb's own World, which has no ISO code.
FIELDS = {
    "id": 4076200,
    "title": "Dublin Regulation Expert - Germany",
    "status": "published",
    "body": "The **European Union Agency for Asylum (EUAA)** has issued a call.",
    "country": [
        {
            "id": 101,
            "name": "Germany",
            "shortname": "Germany",
            "iso3": "deu",
            "location": {"lat": 51.13, "lon": 10.02},
        },
        {"id": 254, "name": "World", "shortname": "World", "iso3": "wld"},
    ],
    "source": [
        {
            "id": 50873,
            "name": "European Union Agency for Asylum",
            "shortname": "EUAA",
            "homepage": "https://euaa.europa.eu/",
        },
        {"id": 1503, "name": "European Commission", "shortname": "EC"},
    ],
    "theme": [{"id": 4600, "name": "Protection and Human Rights"}],
    "type": [{"id": 264, "name": "Consultancy"}],
    "experience": [{"id": 259, "name": "3-4 years"}],
    "career_categories": [{"id": 20971, "name": "Information Management"}],
    "url": "https://reliefweb.int/node/4076200",
    "url_alias": "https://reliefweb.int/job/4076200/dublin-regulation-expert-germany",
    "body-html": "<p>The <strong>European Union Agency for Asylum (EUAA)</strong> has issued "
    "a call.</p>",
    "how_to_apply-html": "<p>Apply on the <strong>EUAA</strong> site.</p>",
    "date": {
        "closing": "2027-03-28T00:00:00+00:00",
        "changed": "2024-07-09T09:25:34+00:00",
        "created": "2024-07-09T09:25:34+00:00",
    },
}
POSTING = {"id": "4076200", "score": 1, "fields": FIELDS}


def page(postings, total):
    return json.dumps({"totalCount": total, "count": len(postings), "data": postings})


def numbered(count, start=0):
    return [{"fields": FIELDS | {"id": n}} for n in range(start, start + count)]


def test_a_posting_becomes_a_record_with_a_place_per_country(caplog):
    # A JSON true is an int to isinstance, and str() of it would invent the ID "True".
    malformed = [{"fields": {"title": "no id"}}, {"fields": {"id": True}}, "not an object"]
    jobs = asyncio.run(reliefweb.search(PagedFetcher([page([POSTING, *malformed], total=4)])))
    assert jobs == [
        {
            "site": "reliefweb",
            "id": "4076200",
            "url": "https://reliefweb.int/job/4076200/dublin-regulation-expert-germany",
            "title": "Dublin Regulation Expert - Germany",
            "company": "European Union Agency for Asylum",
            "company_url": "https://euaa.europa.eu/",
            # The alpha-3 code becomes the alpha-2 code, and World keeps its name alone.
            "locations": [{"name": "Germany", "country_code": "DE"}, {"name": "World"}],
            "date": "2024-07-09",
            "description": "The European Union Agency for Asylum (EUAA) has issued a call.",
            "employment_type": "consultancy",
            "posted_at": "2024-07-09T09:25:34+00:00",
            "expires_at": "2027-03-28T00:00:00+00:00",
            "site_data": {
                "experience": "3-4 years",
                "career_categories": ["Information Management"],
                "themes": ["Protection and Human Rights"],
                "how_to_apply": "Apply on the EUAA site.",
            },
        }
    ]
    assert caplog.text.count("skipping malformed ReliefWeb posting") == 3


def test_a_blank_url_or_term_name_counts_as_absent():
    blank = {
        "id": 42,
        "url_alias": "  ",
        "type": [{"name": " "}, {"name": "Consultancy"}],
        "experience": [{"name": " "}, {"name": "3-4 years"}],
        "career_categories": [{"name": " "}],
        "theme": [{"name": " Health "}],
    }
    (job,) = asyncio.run(reliefweb.search(PagedFetcher([page([{"fields": blank}], total=1)])))
    assert job["url"] == "https://reliefweb.int/job/42"
    assert job["employment_type"] == "consultancy"
    assert job["site_data"] == {"experience": "3-4 years", "themes": ["Health"]}


def test_search_pages_by_offset_until_results_or_the_total_and_stops_at_an_early_empty_page():
    # A posting published between two requests repeats a card on the next page.
    pages = [numbered(1000), numbered(1000, 999), numbered(1000, 1999)]
    fetcher = PagedFetcher([page(postings, total=4480) for postings in pages])
    jobs = asyncio.run(reliefweb.search(fetcher, results=2500))
    assert [job["id"] for job in jobs] == [str(n) for n in range(2500)]
    assert fetcher.bodies[2] == {
        "profile": "full",
        "fields": {"exclude": ["body", "how_to_apply"]},
        "preset": "latest",
        "sort": ["date.created:desc", "id:desc"],
        "offset": 2000,
        "limit": 1000,
    }
    # A search for fewer postings than a page holds asks for only that many.
    fetcher = PagedFetcher([page(numbered(3), total=5)])
    assert len(asyncio.run(reliefweb.search(fetcher, results=3))) == 3
    assert fetcher.bodies[0]["limit"] == 3
    # An empty page before the reported total may have skipped postings.
    fetcher = PagedFetcher([page(numbered(1000), total=4480), page([], total=4480)])
    with pytest.raises(Stopped, match="ReliefWeb reported 4480 postings") as stop:
        asyncio.run(reliefweb.search(fetcher, results=4480))
    assert len(stop.value.partial) == 1000


def test_a_search_sends_its_keywords_country_and_age_as_the_api_takes_them():
    fetcher = PagedFetcher([page([], total=0)])
    before = datetime.now(UTC)
    asyncio.run(reliefweb.search(fetcher, query=" data analyst ", country="Ke", max_age_hours=36))
    body = fetcher.bodies[0]
    assert body["query"] == {"value": "data analyst", "operator": "AND"}
    country, age = body["filter"]["conditions"]
    assert body["filter"]["operator"] == "AND"
    # The API filters on its lower-case alpha-3 codes.
    assert country == {"field": "country.iso3", "value": "ken"}
    # The API refuses a time with fractions of a second.
    start = datetime.fromisoformat(age["value"]["from"])
    assert age["field"] == "date.created"
    assert start.microsecond == 0
    assert timedelta(hours=36, seconds=1) >= before - start >= timedelta(hours=36, seconds=-5)
    # An alpha-3 code names the same country.
    fetcher = PagedFetcher([page([], total=0)])
    asyncio.run(reliefweb.search(fetcher, country="KEN"))
    assert fetcher.bodies[0]["filter"]["conditions"] == [country]
    # A search with no filter sends none.
    fetcher = PagedFetcher([page([], total=0)])
    asyncio.run(reliefweb.search(fetcher))
    assert "filter" not in fetcher.bodies[0]
    assert "query" not in fetcher.bodies[0]
    with pytest.raises(ValueError, match="'Kenya' is not an ISO 3166-1 code"):
        check("reliefweb", country="Kenya")


def test_every_request_names_the_users_appname(monkeypatch):
    monkeypatch.setenv("JOBRAKE_RELIEFWEB_APPNAME", " UN-Desk Q&A ")
    fetcher = PagedFetcher([page([], total=0)])
    asyncio.run(reliefweb.search(fetcher))
    assert fetcher.requests[0] == "https://api.reliefweb.int/v2/jobs?appname=UN-Desk+Q%26A"


def test_a_search_without_an_appname_fails_before_its_first_request(monkeypatch):
    for unset in ("", " "):
        monkeypatch.setenv("JOBRAKE_RELIEFWEB_APPNAME", unset)
        with pytest.raises(ValueError, match="JOBRAKE_RELIEFWEB_APPNAME is unset or blank"):
            check("reliefweb")
    monkeypatch.delenv("JOBRAKE_RELIEFWEB_APPNAME")
    fetcher = PagedFetcher([])
    with pytest.raises(ValueError, match="requires an approved appname"):
        asyncio.run(reliefweb.search(fetcher))
    assert fetcher.requests == []


def test_a_refused_appname_stops_the_search_with_the_name_to_check():
    fetcher = PagedFetcher([FetchResult(url="stub", status=403, text="{}")])
    with pytest.raises(Stopped, match="appname 'jobrake-tests' in JOBRAKE_RELIEFWEB_APPNAME"):
        asyncio.run(reliefweb.search(fetcher))
