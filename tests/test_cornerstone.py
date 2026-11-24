"""Cornerstone career site bootstrap, parsing, filtering, and paging tests."""

import asyncio
import json

import pytest
from fakes import PagedFetcher, StubFetcher, network_down, not_found, ok

from jobrake import Stopped, check
from jobrake.fetchkit import FetchResult
from jobrake.sites import cornerstone

WB_BOARD = "https://worldbankgroup.csod.com/ux/ats/careersite/1/home?c=worldbankgroup"
WB_API = "https://us.api.csod.com/rec-job-search/external/jobs"
HENKEL_BOARD = "https://henkel.csod.com/ux/ats/careersite/1/home?c=henkel"
HENKEL_API = "https://eu-fra.api.csod.com/rec-job-search/external/jobs"


def board_html(
    *,
    corp: str = "worldbankgroup",
    cloud: str = "https://us.api.csod.com/",
    token: str = "anon-token-1",
    culture_id: int = 1,
    culture_name: str = "en-US",
) -> str:
    context = {
        "corp": corp,
        "user": -100,
        "cultureID": culture_id,
        "cultureName": culture_name,
        "endpoints": {"cloud": cloud, "api": "/"},
        "token": token,
    }
    return (
        "<!DOCTYPE html><html><body>"
        f"<script>if(!csod.context || !csod.context.token) csod.context={json.dumps(context)};</script>"
        "</body></html>"
    )


# Two requisitions from World Bank Group (fetched 2026-11-23/24), with descriptions trimmed.
WB_REQUISITIONS = [
    {
        "requisitionId": 39579,
        "postingEffectiveDate": "11/23/2026",
        "postingExpirationDate": "12/8/2026",
        "displayJobTitle": "Regional Industry Director, FIG- West, Central and North Africa",
        "locations": [{"city": "Abidjan", "country": "CI"}, {"city": "Dakar", "country": "SN"}],
        "externalDescription": " At the International Finance Corporation (IFC), you will lead FIG. ",
    },
    {
        "requisitionId": 39580,
        "postingEffectiveDate": "11/23/2026",
        "postingExpirationDate": "12/9/2026",
        "displayJobTitle": "Senior Economist",
        "locations": [{"city": "Washington, DC", "state": "DC", "country": "US"}],
        "externalDescription": " Conduct macroeconomic analysis for country programs. ",
    },
]

# One requisition from Henkel's EU board (fetched 2026-11-24), with en-GB date and "-" expiration.
HENKEL_REQUISITION = {
    "requisitionId": 90427,
    "postingEffectiveDate": "24/11/2026",
    "postingExpirationDate": "-",
    "displayJobTitle": "IT Service Engineer (Digital Solutions)",
    "locations": [
        {"city": "Makati City", "country": "PH"},
        {"city": "Makati", "state": "NATIONAL CAPITAL REGION", "country": "PH"},
    ],
    "externalDescription": " About this Position Build reliable IT services. ",
}


def page(requisitions, total=None):
    total = len(requisitions) if total is None else total
    return json.dumps(
        {
            "status": "Success",
            "data": {"totalCount": total, "requisitions": requisitions, "filters": []},
        }
    )


def numbered(count, start=1):
    return [{**WB_REQUISITIONS[0], "requisitionId": n} for n in range(start, start + count)]


def test_a_search_reads_the_boards_token_and_parses_requisitions(caplog):
    # A JSON true is an int to isinstance, and str() of it would invent a bogus ID.
    malformed = [{"displayJobTitle": "no id"}, {"requisitionId": True}, "not an object"]
    fetcher = StubFetcher(
        {
            "worldbankgroup.csod.com": ok(board_html()),
            WB_API: ok(page([*WB_REQUISITIONS, *malformed], total=5)),
        }
    )
    jobs = asyncio.run(cornerstone.search(fetcher, board=WB_BOARD))
    assert jobs == [
        {
            "site": "cornerstone",
            "id": "worldbankgroup:39579",
            "url": "https://worldbankgroup.csod.com/ux/ats/careersite/1/home/requisition/39579?c=worldbankgroup",
            "title": "Regional Industry Director, FIG- West, Central and North Africa",
            "company": None,
            "locations": [
                {"name": "Abidjan, CI", "city": "Abidjan", "country_code": "CI"},
                {"name": "Dakar, SN", "city": "Dakar", "country_code": "SN"},
            ],
            "date": "2026-11-23",
            "description": "At the International Finance Corporation (IFC), you will lead FIG.",
            "posted_at": "2026-11-23",
            "expires_at": "2026-12-08",
        },
        {
            "site": "cornerstone",
            "id": "worldbankgroup:39580",
            "url": "https://worldbankgroup.csod.com/ux/ats/careersite/1/home/requisition/39580?c=worldbankgroup",
            "title": "Senior Economist",
            "company": None,
            "locations": [
                {
                    "name": "Washington, DC, DC, US",
                    "city": "Washington, DC",
                    "region": "DC",
                    "country_code": "US",
                }
            ],
            "date": "2026-11-23",
            "description": "Conduct macroeconomic analysis for country programs.",
            "posted_at": "2026-11-23",
            "expires_at": "2026-12-09",
        },
    ]
    assert fetcher.requests == [WB_BOARD, WB_API]
    assert fetcher.headers[1] == {
        "Authorization": "Bearer anon-token-1",
        "CSOD-Accept-Language": "en-US",
    }
    assert caplog.text.count("skipping malformed Cornerstone posting") == 3


def test_search_uses_the_boards_regional_api_host_and_culture_dates(caplog):
    # Henkel uses the Frankfurt cloud and en-GB (day/month/year) dates with "-" for no expiry.
    fetcher = StubFetcher(
        {
            "henkel.csod.com": ok(
                board_html(
                    corp="henkel",
                    cloud="https://eu-fra.api.csod.com/",
                    token="eu-tok",
                    culture_id=2,
                    culture_name="en-GB",
                )
            ),
            HENKEL_API: ok(page([HENKEL_REQUISITION], total=1)),
        }
    )
    (job,) = asyncio.run(cornerstone.search(fetcher, board=HENKEL_BOARD))
    assert fetcher.requests == [HENKEL_BOARD, HENKEL_API]
    assert fetcher.headers[1] == {
        "Authorization": "Bearer eu-tok",
        "CSOD-Accept-Language": "en-GB",
    }
    assert fetcher.bodies[1]["cultureId"] == 2
    assert fetcher.bodies[1]["cultureName"] == "en-GB"
    assert job == {
        "site": "cornerstone",
        "id": "henkel:90427",
        "url": "https://henkel.csod.com/ux/ats/careersite/1/home/requisition/90427?c=henkel",
        "title": "IT Service Engineer (Digital Solutions)",
        "company": None,
        "locations": [
            {"name": "Makati City, PH", "city": "Makati City", "country_code": "PH"},
            {
                "name": "Makati, NATIONAL CAPITAL REGION, PH",
                "city": "Makati",
                "region": "NATIONAL CAPITAL REGION",
                "country_code": "PH",
            },
        ],
        "date": "2026-11-24",
        "description": "About this Position Build reliable IT services.",
        "posted_at": "2026-11-24",
    }
    # German and Czech dot-separated dates, Hungarian/Korean YMD with spaces, ISO dates,
    # country-only places, and an unreadable date.
    de_board = f"{HENKEL_BOARD}&lang=de-DE"
    mixed = [
        {
            **HENKEL_REQUISITION,
            "requisitionId": 1,
            "postingEffectiveDate": "24.11.2026",
            "postingExpirationDate": "2026-12-31",
            "locations": [{"country": "PS"}],
        },
        {
            **HENKEL_REQUISITION,
            "requisitionId": 2,
            "postingEffectiveDate": "2026. 11. 24.",
            "postingExpirationDate": "24. 12. 2026.",
        },
        {
            **HENKEL_REQUISITION,
            "requisitionId": 3,
            "postingEffectiveDate": "32/13/2026",
            "postingExpirationDate": "soon",
        },
    ]
    fetcher = StubFetcher(
        {
            "henkel.csod.com": ok(
                board_html(
                    corp="henkel",
                    cloud="https://eu-fra.api.csod.com/",
                    culture_id=4,
                    culture_name="de-DE",
                )
            ),
            HENKEL_API: ok(page(mixed, total=3)),
        }
    )
    first, second, third = asyncio.run(cornerstone.search(fetcher, board=de_board))
    assert fetcher.requests[0] == de_board
    assert (first["date"], first["expires_at"]) == ("2026-11-24", "2026-12-31")
    assert first["locations"] == [{"name": "PS", "country_code": "PS"}]
    assert (second["date"], second["expires_at"]) == ("2026-11-24", "2026-12-24")
    assert third["date"] is None
    assert "posted_at" not in third
    assert "expires_at" not in third
    assert "is not an ISO 8601 date" in caplog.text


@pytest.mark.parametrize(
    ("raw", "culture", "expected"),
    [
        # Short dates Cornerstone sent on 2026-11-24 in Thai, Arabic, and Bulgarian.
        ("24/11/2569", "th-TH", "2026-11-24"),
        ("24\u200f\u200f/11\u200f\u200f/2026", "ar-AE", "2026-11-24"),
        ("24.11.2026\u202f\u0433.", "bg-BG", "2026-11-24"),
        ("11/24/2026", "en-US", "2026-11-24"),
        # A two-digit year names no century, so the date is left out.
        ("24/11/26", "en-GB", None),
    ],
)
def test_short_dates_read_in_every_culture(raw, culture, expected):
    requisition = {**HENKEL_REQUISITION, "postingEffectiveDate": raw}
    fetcher = StubFetcher(
        {
            "henkel.csod.com": ok(
                board_html(
                    corp="henkel", cloud="https://eu-fra.api.csod.com/", culture_name=culture
                )
            ),
            HENKEL_API: ok(page([requisition], total=1)),
        }
    )
    (job,) = asyncio.run(cornerstone.search(fetcher, board=HENKEL_BOARD))
    assert job["date"] == expected


def test_search_sends_keywords_country_and_age_rounded_up_to_days():
    fetcher = StubFetcher(
        {"worldbankgroup.csod.com": ok(board_html()), WB_API: ok(page([], total=0))}
    )
    asyncio.run(
        cornerstone.search(
            fetcher, board=WB_BOARD, query=" economist ", country="in", max_age_hours=25, results=50
        )
    )
    assert fetcher.bodies[1] == {
        "careerSiteId": 1,
        "careerSitePageId": 1,
        "pageNumber": 1,
        "pageSize": 50,
        "cultureId": 1,
        "cultureName": "en-US",
        "searchText": "economist",
        "states": [],
        "countryCodes": ["IN"],
        "cities": [],
        "placeID": "",
        "radius": None,
        "postingsWithinDays": 2,
        "customFieldCheckboxKeys": [],
        "customFieldDropdowns": [],
        "customFieldRadios": [],
    }
    # Alpha-3 codes resolve to alpha-2, and an unfiltered search sends null radius and age.
    fetcher = StubFetcher(
        {"worldbankgroup.csod.com": ok(board_html()), WB_API: ok(page([], total=0))}
    )
    asyncio.run(cornerstone.search(fetcher, board=WB_BOARD, country="IND", max_age_hours=24))
    assert fetcher.bodies[1]["countryCodes"] == ["IN"]
    assert fetcher.bodies[1]["postingsWithinDays"] == 1
    # An age beyond float range rounds up in integer arithmetic.
    fetcher = StubFetcher(
        {"worldbankgroup.csod.com": ok(board_html()), WB_API: ok(page([], total=0))}
    )
    asyncio.run(cornerstone.search(fetcher, board=WB_BOARD, max_age_hours=10**400))
    assert fetcher.bodies[1]["postingsWithinDays"] == 10**400 // 24 + 1
    fetcher = StubFetcher(
        {"worldbankgroup.csod.com": ok(board_html()), WB_API: ok(page([], total=0))}
    )
    asyncio.run(cornerstone.search(fetcher, board=WB_BOARD))
    assert fetcher.bodies[1]["countryCodes"] == []
    assert fetcher.bodies[1]["radius"] is None
    assert fetcher.bodies[1]["postingsWithinDays"] is None
    with pytest.raises(ValueError, match="'India' is not an ISO 3166-1 code"):
        check("cornerstone", board=WB_BOARD, country="India")


def test_search_pages_by_page_number_dedupes_and_stops_on_an_early_empty_page():
    # A requisition added between pages repeats an ID on the next page.
    pages = [
        board_html(),
        page(numbered(1000, 1), total=2500),
        page(numbered(1000, 1000), total=2500),
        page(numbered(1000, 1999), total=2500),
    ]
    fetcher = PagedFetcher(pages)
    jobs = asyncio.run(cornerstone.search(fetcher, board=WB_BOARD, results=2500))
    assert [job["id"] for job in jobs] == [f"worldbankgroup:{n}" for n in range(1, 2501)]
    assert [(body["pageNumber"], body["pageSize"]) for body in fetcher.bodies[1:]] == [
        (1, 1000),
        (2, 1000),
        (3, 1000),
    ]
    # An empty page before totalCount stops with the postings collected so far.
    fetcher = PagedFetcher([board_html(), page(numbered(2, 1), total=10), page([], total=10)])
    with pytest.raises(Stopped, match="reported 10 postings") as stop:
        asyncio.run(cornerstone.search(fetcher, board=WB_BOARD, results=10))
    assert len(stop.value.partial) == 2
    # A network failure on page 2 keeps page 1 in partial.
    fetcher = PagedFetcher([board_html(), page(numbered(2, 1), total=10), network_down()])
    with pytest.raises(Stopped, match=r"Kept the 2 postings collected") as stop:
        asyncio.run(cornerstone.search(fetcher, board=WB_BOARD, results=10))
    assert len(stop.value.partial) == 2


def test_board_url_accepts_variants_and_refuses_other_addresses():
    # A posting URL, a second careerSiteId, uppercase host, and omitted ?c= all work.
    posting_url = "https://PROJECTHOPE.csod.com/ux/ats/careersite/2/home/requisition/2001"
    fetcher = StubFetcher(
        {
            "projecthope.csod.com": ok(board_html(corp="projecthope")),
            WB_API: ok(page([{**WB_REQUISITIONS[0], "requisitionId": 2001}], total=1)),
        }
    )
    (job,) = asyncio.run(cornerstone.search(fetcher, board=posting_url))
    assert (
        fetcher.requests[0] == "https://projecthope.csod.com/ux/ats/careersite/2/home?c=projecthope"
    )
    assert fetcher.bodies[1]["careerSiteId"] == 2
    assert fetcher.bodies[1]["careerSitePageId"] == 2
    assert job["id"] == "projecthope:2001"
    assert (
        job["url"]
        == "https://projecthope.csod.com/ux/ats/careersite/2/home/requisition/2001?c=projecthope"
    )
    # A distinct c query parameter stays as given.
    fetcher = StubFetcher(
        {"acme.csod.com": ok(board_html(corp="acme_corp")), WB_API: ok(page([], total=0))}
    )
    asyncio.run(
        cornerstone.search(
            fetcher, board="https://acme.csod.com/ux/ats/careersite/3/home?c=acme_corp"
        )
    )
    assert fetcher.requests[0] == "https://acme.csod.com/ux/ats/careersite/3/home?c=acme_corp"
    for bad in (
        "https://example.com/ux/ats/careersite/1/home?c=example",
        "https://us.api.csod.com/ux/ats/careersite/1/home?c=us",
        "https://csod.com/ux/ats/careersite/1/home?c=csod",
        "https://-.csod.com/ux/ats/careersite/1/home?c=x",
        "https://worldbankgroup.csod.com:8443/ux/ats/careersite/1/home?c=worldbankgroup",
        "https://user@worldbankgroup.csod.com/ux/ats/careersite/1/home?c=worldbankgroup",
        "worldbankgroup.csod.com/ux/ats/careersite/1/home?c=worldbankgroup",
        "https://worldbankgroup.csod.com/ux/ats/careersite/0/home?c=worldbankgroup",
        "https://worldbankgroup.csod.com/ux/ats/careersite/abc/home?c=worldbankgroup",
        "https://worldbankgroup.csod.com/ux/ats/careersite/1/other?c=worldbankgroup",
        "https://worldbankgroup.csod.com/ux/ats/careersite/1/home/extra",
        "https://[/ux/ats/careersite/1/home",
    ):
        fetcher = StubFetcher({})
        with pytest.raises(ValueError, match="not a Cornerstone career site URL"):
            asyncio.run(cornerstone.search(fetcher, board=bad))
        assert fetcher.requests == []


def test_unknown_career_site_and_unreadable_bootstrap_stop_cleanly():
    # A 404 or redirect to /error.aspx names the unknown career site.
    with pytest.raises(Stopped, match="Cornerstone has no career site at"):
        asyncio.run(
            cornerstone.search(
                StubFetcher({"worldbankgroup.csod.com": not_found()}), board=WB_BOARD
            )
        )
    error_page = FetchResult(
        url="https://worldbankgroup.csod.com/error.aspx", status=200, text="<title>Error</title>"
    )
    with pytest.raises(Stopped, match="Cornerstone has no career site at"):
        asyncio.run(
            cornerstone.search(StubFetcher({"worldbankgroup.csod.com": error_page}), board=WB_BOARD)
        )
    # A server error on that page is a failed request, not an unknown career site.
    broken = FetchResult(url=error_page.url, status=500, text="Internal Server Error")
    with pytest.raises(Stopped, match=r"Cornerstone request for board .* failed: HTTP 500"):
        asyncio.run(
            cornerstone.search(StubFetcher({"worldbankgroup.csod.com": broken}), board=WB_BOARD)
        )
    # Missing context, blank token, or a cloud URL off csod.com stops as unreadable.
    for html in (
        "<html><body>no context</body></html>",
        board_html(token=" "),
        board_html(cloud="https://evil.example/"),
        board_html(cloud="http://us.api.csod.com/"),
    ):
        with pytest.raises(Stopped, match="cannot read"):
            asyncio.run(
                cornerstone.search(
                    StubFetcher({"worldbankgroup.csod.com": ok(html)}), board=WB_BOARD
                )
            )
    # A network failure on the board page names the board.
    with pytest.raises(Stopped, match=r"Cornerstone request for board .* failed: connection reset"):
        asyncio.run(
            cornerstone.search(
                StubFetcher({"worldbankgroup.csod.com": network_down()}), board=WB_BOARD
            )
        )
