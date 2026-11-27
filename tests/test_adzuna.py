"""Adzuna mobile app API signing, paging, parsing, and details tests."""

import asyncio
import json
from collections.abc import Sequence
from urllib.parse import parse_qs, urlsplit

import pytest
from fakes import PagedFetcher, StubFetcher, ok

from jobrake import Stopped, check, identify
from jobrake.fetchkit import FetchResult
from jobrake.sites import adzuna

SESSION_BODY = json.dumps({"sid": "224409-test-sid", "domain": {}})
SESSION_OK = FetchResult(
    url="stub",
    status=200,
    text=SESSION_BODY,
    headers={
        "Set-Cookie": "session=jwt-session-token; domain=.adzuna.com; path=/; secure, "
        "dcid2=abc; domain=.adzuna.co.uk; path=/"
    },
)

# Three cards trimmed from app.adzuna.com/app/jobs/search (fetched 2026-11-23 / 2026-11-24):
# 1. tracker_hash + predicted salary
# 2. direct_link details page (no tracker_hash) + advertised monthly salary
# 3. tracker_hash + advertised monthly salary, which get_ad annualizes
CARDS: list[dict[str, object]] = [
    {
        "id": "5575618204",
        "numeric_id": "5575618204",
        "title": "Commodities Macro Analyst",
        "company": "DRW",
        "location_raw": "London",
        "modified": "2026-10-07T09:22:56Z",
        "salary_raw": "48218.167969",
        "salary_is_predicted": True,
        "tracker_hash": "34A96E34FD9080B4AABE2D69D455929946AE75F2",
        "source_logo": "images/logo/jobs/partners/partner.png",
    },
    {
        "id": "5960371925",
        "numeric_id": "5960371925",
        "title": "Economist",
        "company": "Cameron Clarke Associates",
        "location_raw": "London, UK, WC1X 8HB",
        "modified": "2026-11-23T14:36:40Z",
        "salary_raw": "£3,500-£4,000 Gross per Month",
        "salary_is_predicted": False,
        "contract_time": "full_time",
        "contract_type": "permanent",
        "direct_link": "/jobs/details/5960371925?utm_medium=mobile-app&utm_source=android-app",
    },
    {
        "id": "5960462755",
        "numeric_id": "5960462755",
        "title": "Economist",
        "company": "International Coffee Organisation",
        "location_raw": "London",
        "modified": "2026-11-20T06:28:33Z",
        "salary_raw": "£3500 - £4000/month",
        "salary_is_predicted": False,
        "contract_time": "full_time",
        "tracker_hash": "75CAB68752888CCC8A51DCC9052E14E1C74AC988",
    },
]

# Trimmed from app.adzuna.com/app/jobs/get_ad for 5575618204 (predicted salary, fetched 2026-11-23).
AD_PREDICTED = {
    "ad": {
        "id": "5575618204",
        "title": "Commodities Macro Analyst",
        "company": "DRW",
        "location_raw": "London",
        "locations": [
            {"id": 86384, "level": 2, "name": "London", "lat": "51.503378", "lng": "-0.139134"},
            {"id": 86383, "level": 1, "name": "UK", "lat": None, "lng": None},
        ],
        "description": "<p><strong>DRW</strong> is a trading firm.</p>",
        "salary_min": None,
        "salary_max": None,
        "salary_predicted": "48218",
        "salary_is_predicted": 1,
        "created": "2026-01-09T09:31:41",
        "valid_through": "2026-12-07T09:56:49",
        "contract_time": None,
        "contract_type": None,
        "url": "https://www.adzuna.co.uk/jobs/land/ad/5575618204?utm_medium=mobile-app",
        "url_with_ga": "https://boards.greenhouse.io/drweng/jobs/7518800?utm_source=adzuna",
        "source": {"site": "SourceStack", "currency_code": "GBP"},
        "category": {"label": "Accounting & Finance Jobs"},
        "is_deleted": 0,
    }
}

# Trimmed from app.adzuna.com/app/jobs/get_ad for 5960462755 (advertised salary, fetched 2026-11-24).
AD_ADVERTISED = {
    "ad": {
        "id": "5960462755",
        "title": "Economist",
        "company": "International Coffee Organisation",
        "location_raw": "London",
        "locations": [
            {"id": 86384, "level": 2, "name": "London", "lat": "51.503378", "lng": "-0.139134"},
            {"id": 86383, "level": 1, "name": "UK", "lat": None, "lng": None},
        ],
        "description": "<p>Research and statistics on the coffee economy.</p>",
        "salary_min": "42000",
        "salary_max": "48000",
        "salary_raw": "£3500 - £4000/month",
        "salary_is_predicted": 0,
        "created": "2026-11-10T15:40:23",
        "valid_through": "2026-12-08T00:43:59",
        "contract_time": "full_time",
        "contract_type": None,
        "url": "https://www.adzuna.co.uk/jobs/land/ad/5960462755?utm_medium=mobile-app",
        "url_with_ga": "https://click.appcast.io/t/example?utm_source=adzuna",
        "source": {"site": "CV-Library", "currency_code": "GBP"},
        "category": {"label": "Scientific & QA Jobs"},
        "is_deleted": 0,
    }
}

# Trimmed from www.adzuna.co.uk/jobs/details/5960371925?utm_medium=mobile-app&utm_source=android-app
# (fetched 2026-11-24). Notice baseSalary mislabels £3,500-£4,000/month as YEAR, so jobrake ignores it.
# The country is a name here, as on Australia's pages, where GB's give its code.
DIRECT_HTML = (
    '<html><head><script type="application/ld+json">'
    '{"@type": "JobPosting", "title": "Economist", "employmentType": ["FULL_TIME"],'
    ' "datePosted": "2026-11-10T10:12:00", "validThrough": "2026-12-07T20:48:12",'
    ' "industry": "Scientific & QA",'
    ' "hiringOrganization": {"@type": "Organization", "name": "Cameron Clarke Associates"},'
    ' "jobLocation": {"@type": "Place", "address": {"addressLocality": "Finsbury",'
    ' "addressRegion": "Central London", "addressCountry": "United Kingdom"},'
    ' "geo": {"latitude": "51.523729", "longitude": "-0.114816"}},'
    ' "baseSalary": {"currency": "GBP", "value": {"minValue": "3500", "maxValue": "4000",'
    ' "unitText": "YEAR"}},'
    ' "description": "<p>Support the global coffee sector.</p>"}'
    "</script></head><body></body></html>"
)


def _search_page(
    docs: Sequence[object], total: int, current_page: int = 1, per_page: int = 50
) -> str:
    return json.dumps(
        {
            "contract": {
                "results": {
                    "docs": docs,
                    "pager": {
                        "current_page": current_page,
                        "entries_per_page": str(per_page),
                        "total_entries": total,
                    },
                }
            }
        }
    )


def _numbered(count: int, start: int = 1) -> list[dict[str, object]]:
    return [
        {**CARDS[0], "id": str(5000000000 + index), "numeric_id": str(5000000000 + index)}
        for index in range(start, start + count)
    ]


def test_signature_matches_android_app_vparamgenerator() -> None:
    # Pinned against com.adzuna.api.VParamGenerator (v1.7.0).
    assert (
        adzuna._sign("jobs", "/start_session", None, 1)  # noqa: SLF001  signer contract test
        == "BDBCBFBTUDUWKJXGSGHJVGVKUJJVDVVHSTXBUSFHFUFGJBD"
    )
    assert (
        adzuna._sign("jobs", "/search", "224409-test-sid", 2)  # noqa: SLF001
        == "BDBCBFFKJCXGVJSCISDGIVCBVSFWHDEWXGUESKJSWTEGUEJ"
    )
    assert (
        adzuna._sign("jobs_DE", "/start_session", None, 1)  # noqa: SLF001
        == "BDBCBFBGUSUGWIVTEUTBGHCWGUTGHCVCJTFDVCGWFVTDVSW"
    )


def test_search_bootstraps_session_forwards_cookie_and_parses_cards(caplog) -> None:
    malformed: list[object] = [{"title": "No ID"}, {"id": True}, {"id": "abc"}, "not an object"]
    numeric = {**CARDS[2], "id": 5960462755}
    fetcher = PagedFetcher([SESSION_OK, _search_page([*CARDS[:2], numeric, *malformed], total=7)])
    jobs = asyncio.run(adzuna.search(fetcher, country="gb", query="economist", location="London"))

    # First request is start_session (counter=1); second is search (counter=2) with Cookie header.
    start_query = parse_qs(urlsplit(fetcher.requests[0]).query)
    search_query = parse_qs(urlsplit(fetcher.requests[1]).query)
    assert "/app/jobs/start_session?" in fetcher.requests[0]
    assert start_query["counter"] == ["1"]
    assert start_query["app_version"] == ["1.7.0"]
    assert start_query["v"] == ["BDBCBFBTUDUWKJXGSGHJVGVKUJJVDVVHSTXBUSFHFUFGJBD"]
    assert "/app/jobs/search?" in fetcher.requests[1]
    assert search_query["counter"] == ["2"]
    assert search_query["q"] == ["economist"]
    assert search_query["w"] == ["London"]
    assert search_query["p"] == ["1"]
    assert search_query["pp"] == ["50"]
    assert search_query["v"] == ["BDBCBFFKJCXGVJSCISDGIVCBVSFWHDEWXGUESKJSWTEGUEJ"]
    assert fetcher.headers[1] == {"Cookie": "session=jwt-session-token"}

    assert jobs == [
        {
            "site": "adzuna",
            "id": "5575618204",
            "url": "https://www.adzuna.co.uk/jobs/land/ad/5575618204",
            "title": "Commodities Macro Analyst",
            "company": "DRW",
            "locations": [{"name": "London", "country_code": "GB"}],
            "date": "2026-10-07",
        },
        {
            "site": "adzuna",
            "id": "5960371925",
            "url": "https://www.adzuna.co.uk/jobs/details/5960371925",
            "title": "Economist",
            "company": "Cameron Clarke Associates",
            "locations": [{"name": "London, UK, WC1X 8HB", "country_code": "GB"}],
            "date": "2026-11-23",
            "employment_type": "full_time",
            "site_data": {"contract_type": "permanent"},
        },
        {
            "site": "adzuna",
            "id": "5960462755",
            "url": "https://www.adzuna.co.uk/jobs/land/ad/5960462755",
            "title": "Economist",
            "company": "International Coffee Organisation",
            "locations": [{"name": "London", "country_code": "GB"}],
            "date": "2026-11-20",
            "employment_type": "full_time",
        },
    ]
    assert caplog.text.count("skipping malformed Adzuna posting") == 4


def test_search_routes_country_editions_converts_radius_and_rounds_age() -> None:
    # GB uses context "jobs" and converts kilometers to miles.
    fetcher_gb = PagedFetcher([SESSION_OK, _search_page([], total=0)])
    asyncio.run(
        adzuna.search(
            fetcher_gb, country="uk", location="London", radius=16, max_age_hours=25, results=5
        )
    )
    query_gb = parse_qs(urlsplit(fetcher_gb.requests[1]).query)
    assert "/app/jobs/search?" in fetcher_gb.requests[1]
    assert query_gb["d"] == ["10"]  # 16 km -> 10 miles
    assert query_gb["f"] == ["2"]  # 25 hours -> 2 days
    assert query_gb["pp"] == ["5"]

    # DE uses context "jobs_DE" and keeps radius in kilometers.
    fetcher_de = PagedFetcher([SESSION_OK, _search_page([], total=0)])
    asyncio.run(
        adzuna.search(
            fetcher_de, country="DEU", location="Berlin", radius=16, max_age_hours=24, results=10
        )
    )
    query_de = parse_qs(urlsplit(fetcher_de.requests[1]).query)
    assert "/app/jobs_DE/start_session?" in fetcher_de.requests[0]
    assert "/app/jobs_DE/search?" in fetcher_de.requests[1]
    assert query_de["d"] == ["16"]
    assert query_de["f"] == ["1"]

    with pytest.raises(ValueError, match="Adzuna has no edition for 'JP'"):
        check("adzuna", country="jp")


def test_search_pages_deduplicates_stops_on_early_empty_page_and_warns_at_cap(caplog) -> None:
    # Two pages with one repeated card across the page boundary.
    page1 = _search_page(_numbered(50, start=1), total=80, current_page=1)
    page2 = _search_page(_numbered(30, start=50), total=80, current_page=2)
    fetcher = PagedFetcher([SESSION_OK, page1, page2])
    jobs = asyncio.run(adzuna.search(fetcher, country="gb", results=100))
    assert len(jobs) == 79
    assert parse_qs(urlsplit(fetcher.requests[2]).query)["p"] == ["2"]

    # Empty page before total raises Stopped with partial.
    fetcher = PagedFetcher([SESSION_OK, _search_page(CARDS, total=10), _search_page([], total=10)])
    with pytest.raises(Stopped, match="Adzuna reported 10 postings") as caught:
        asyncio.run(adzuna.search(fetcher, country="gb", results=10))
    assert len(caught.value.partial) == 3

    # Hitting Adzuna's 20-page cap warns and returns cleanly without Stopped.
    cap_pages = [
        _search_page(_numbered(50, start=1 + 50 * index), total=5000, current_page=index + 1)
        for index in range(adzuna.MAX_PAGES)
    ]
    fetcher = PagedFetcher([SESSION_OK, *cap_pages])
    capped = asyncio.run(adzuna.search(fetcher, country="gb", results=1500))
    assert len(capped) == 1000
    assert "Adzuna serves at most 20 pages per search" in caplog.text

    # Short pages still stop at the 20th page, because Adzuna answers a later page with that one,
    # and warn though the reported total is within 20 full pages.
    caplog.clear()
    short_pages = [
        _search_page(_numbered(10, start=1 + 10 * index), total=800, current_page=index + 1)
        for index in range(adzuna.MAX_PAGES)
    ]
    fetcher = PagedFetcher([SESSION_OK, *short_pages, *short_pages[-1:] * 5])
    short = asyncio.run(adzuna.search(fetcher, country="gb", results=1500))
    assert len(short) == 200
    assert len(fetcher.requests) == 1 + adzuna.MAX_PAGES
    assert "Adzuna serves at most 20 pages per search" in caplog.text


def test_details_fill_get_ad_and_direct_link_and_cache_skips_repeat_fetches() -> None:
    # Card 1 -> get_ad (predicted salary omitted, apply_url + coordinates + description added)
    # Card 2 -> direct_link HTML (no salary, adds description + city/region/coords)
    # Card 3 -> get_ad (annualized salary)
    fetcher = StubFetcher(
        {
            "start_session": SESSION_OK,
            "/app/jobs/search": ok(_search_page(CARDS, total=3)),
            "id=5575618204": ok(json.dumps(AD_PREDICTED)),
            "id=5960462755": ok(json.dumps(AD_ADVERTISED)),
            "/jobs/details/5960371925": ok(DIRECT_HTML),
        }
    )
    jobs = asyncio.run(adzuna.search(fetcher, country="gb", query="economist", details=True))
    [drw, cameron, ico] = jobs

    assert drw["description"] == "DRW is a trading firm."
    assert drw["apply_url"] == "https://boards.greenhouse.io/drweng/jobs/7518800?utm_source=adzuna"
    assert drw["date"] == "2026-01-09"
    assert drw["posted_at"] == "2026-01-09T09:31:41"
    assert drw["expires_at"] == "2026-12-07T09:56:49"
    assert drw["locations"] == [
        {"name": "London", "country_code": "GB", "latitude": 51.503378, "longitude": -0.139134}
    ]
    assert drw["site_data"] == {"category": "Accounting & Finance Jobs", "source": "SourceStack"}
    assert "salary_min" not in drw

    assert cameron["description"] == "Support the global coffee sector."
    assert "salary_min" not in cameron
    assert cameron["date"] == "2026-11-10"
    assert cameron["site_data"] == {"category": "Scientific & QA", "contract_type": "permanent"}
    assert cameron["locations"] == [
        {
            "name": "Finsbury, Central London, GB",
            "city": "Finsbury",
            "region": "Central London",
            "country_code": "GB",
            "latitude": 51.523729,
            "longitude": -0.114816,
        }
    ]

    assert ico["description"] == "Research and statistics on the coffee economy."
    assert ico["salary_min"] == 42000.0
    assert ico["salary_max"] == 48000.0
    assert ico["salary_currency"] == "GBP"
    assert ico["salary_period"] == "YEAR"
    assert ico["apply_url"] == "https://click.appcast.io/t/example?utm_source=adzuna"
    assert ico["site_data"] == {"category": "Scientific & QA Jobs", "source": "CV-Library"}

    # Repeat search hits the cache for all 3 postings and makes only start_session + search.
    cached_fetcher = StubFetcher(
        {"start_session": SESSION_OK, "/app/jobs/search": ok(_search_page(CARDS, total=3))}
    )
    again = asyncio.run(
        adzuna.search(cached_fetcher, country="gb", query="economist", details=True)
    )
    assert again == jobs
    assert len(cached_fetcher.requests) == 2


def test_details_handles_vhash_in_direct_link_fallbacks_gone_and_malformed_answers() -> None:
    land_card = {
        **CARDS[0],
        "id": "5968091702",
        "tracker_hash": None,
        "direct_link": "/land/ad/5968091702?utm_medium=mobile-app&v="
        "1D4CE7104B58E54C5AD65BC5AD123BB3ECEDD44F",
    }
    gone_card = {**CARDS[0], "id": "5575618205"}
    de_body_card = {
        **CARDS[1],
        "id": "5954501613",
        "direct_link": "/details/5954501613?utm_medium=mobile-app&utm_source=android-app",
    }
    # JSON-LD with empty location and no description falls back to card's location + .adp-body.
    sparse_ld_card = {
        **CARDS[1],
        "id": "5954501614",
        "location_raw": "Munich",
        "direct_link": "/details/5954501614/?utm_medium=mobile-app",
    }
    sparse_html = (
        '<html><head><script type="application/ld+json">'
        '{"@type": "JobPosting", "title": "Economist"}</script></head>'
        '<body><section class="adp-body"><p>Munich role.</p></section></body></html>'
    )
    ad_blank_fields = {
        "ad": {
            **AD_ADVERTISED["ad"],
            "location_raw": "   ",
            "source": {"site": "CV-Library", "currency_code": "  "},
        }
    }
    fetcher = StubFetcher(
        {
            "start_session": SESSION_OK,
            "/app/jobs_DE/search": ok(
                # A repeat of a card without its hash leaves the first card's hash to read.
                _search_page(
                    [
                        land_card,
                        {**land_card, "direct_link": None},
                        gone_card,
                        de_body_card,
                        sparse_ld_card,
                    ],
                    total=5,
                )
            ),
            "id=5968091702": ok(json.dumps(ad_blank_fields)),
            "id=5575618205": ok(json.dumps({"ad": {**AD_PREDICTED["ad"], "is_deleted": 1}})),
            "/details/5954501613": ok(
                '<html><body><section class="adp-body"><p>Berlin role.</p></section></body></html>'
            ),
            "/details/5954501614": ok(sparse_html),
        }
    )
    [land, gone, body_only, sparse] = asyncio.run(
        adzuna.search(fetcher, country="de", details=True)
    )
    assert land["description"] == "Research and statistics on the coffee economy."
    assert land["salary_currency"] == "EUR"  # whitespace currency_code falls back to edition
    assert land["locations"][0]["name"] == "London"  # whitespace location_raw falls back to entries
    assert "vhash=1D4CE7104B58E54C5AD65BC5AD123BB3ECEDD44F" in fetcher.requests[2]
    assert "description" not in gone
    assert body_only["description"] == "Berlin role."
    assert sparse["description"] == "Munich role."
    assert sparse["locations"] == [{"name": "Munich", "country_code": "DE"}]

    # A 200 without an "ad" key (e.g., {"error": ...}) is a failure, not a gone posting.
    missing_ad = StubFetcher(
        {
            "start_session": SESSION_OK,
            "/app/jobs/search": ok(_search_page(CARDS[:1], total=1)),
            "id=5575618204": ok(json.dumps({"error": "rate limited"})),
        }
    )
    with pytest.raises(Stopped, match="Rerun the search to retry") as stop:
        asyncio.run(adzuna.search(missing_ad, country="gb", details=True))
    # Adzuna has no postings to retry a URL with, so the CLI names no retry command.
    assert stop.value.failed == []
    assert len(stop.value.partial) == 1

    # A link with /details/ only in its query clicks out, so it names no details page to read.
    click_out = {
        **CARDS[0],
        "tracker_hash": None,
        "direct_link": "/land/ad/5575618204?r=/details/1",
    }
    fetcher = StubFetcher(
        {"start_session": SESSION_OK, "/app/jobs/search": ok(_search_page([click_out], total=1))}
    )
    with pytest.raises(Stopped) as stop:
        asyncio.run(adzuna.search(fetcher, country="gb", details=True))
    assert stop.value.partial[0]["url"] == "https://www.adzuna.co.uk/jobs/land/ad/5575618204"
    assert len(fetcher.requests) == 2


def test_card_and_identify_read_adzuna_urls_and_reject_others() -> None:
    assert identify("https://www.adzuna.co.uk/jobs/land/ad/5575618204?v=ABC") == (
        "adzuna",
        "5575618204",
    )
    assert identify("https://www.adzuna.co.uk/jobs/details/5960371925") == ("adzuna", "5960371925")
    assert identify("https://www.adzuna.de/land/ad/5954501613") == ("adzuna", "5954501613")
    assert identify("https://adzuna.com/details/5794344677") == ("adzuna", "5794344677")
    assert identify("https://www.adzuna.co.uk/jobs/search?q=economist") is None
    assert identify("https://evil@www.adzuna.co.uk/jobs/land/ad/5575618204") is None
    assert identify("https://www.adzuna.co.uk:8443/jobs/land/ad/5575618204") is None
    with pytest.raises(ValueError, match="not an Adzuna posting URL"):
        adzuna.card("https://www.adzuna.co.uk/jobs/search")
