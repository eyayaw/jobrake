"""SmartRecruiters Posting API paging and parsing tests."""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from fakes import StubFetcher, network_down, ok

from jobrake import Stopped
from jobrake.sites import smartrecruiters

# Two cards from api.smartrecruiters.com/v1/companies/BoschGroup/postings, the
# second with locationType=REMOTE, fetched 2026-10-28, trimmed to the fields
# jobrake reads plus a few it leaves out.
CARDS = [
    {
        "id": "744000158197889",
        "name": "Product Industrialization Expert_PS_RBCW      ",
        "uuid": "b0c659eb-1383-4fdd-a03c-24711d941217",
        "refNumber": "REF299568F",
        "company": {"identifier": "BoschGroup", "name": "Bosch Group"},
        "releasedDate": "2026-10-28T02:14:12.200Z",
        "location": {
            "city": "Wuxi",
            "region": "Jiangsu",
            "country": "cn",
            "remote": False,
            "hybrid": False,
            "latitude": "31.4912",
            "longitude": "120.3119",
            "fullLocation": "Wuxi, Jiangsu, China",
        },
        "typeOfEmployment": {"id": "permanent", "label": "Full-time"},
        "language": {"code": "en", "label": "English"},
    },
    {
        "id": "744000158108729",
        "name": "Roadside Assistance Territory Manager, Southwest region",
        "uuid": "e992ef56-d16e-47bb-a0d0-0cf05b843f58",
        "refNumber": "REF299550L",
        "company": {"identifier": "BoschGroup", "name": "Bosch Group"},
        "releasedDate": "2026-10-27T17:07:18.526Z",
        "location": {
            "city": "Itasca",
            "region": "IL",
            "country": "us",
            "remote": True,
            "hybrid": False,
            "fullLocation": "Itasca, IL, United States",
        },
        "typeOfEmployment": {"id": "permanent", "label": "Full-time"},
        "language": {"code": "en", "label": "English"},
    },
]

URL = "https://api.smartrecruiters.com/v1/companies/BoschGroup/postings"


def page(cards, total):
    return ok(json.dumps({"offset": 0, "limit": 100, "totalFound": total, "content": cards}))


def test_a_board_parses_into_records():
    fetcher = StubFetcher({"BoschGroup/postings": page(CARDS, 2)})
    assert asyncio.run(smartrecruiters.search(fetcher, board="BoschGroup")) == [
        {
            "site": "smartrecruiters",
            "id": "744000158197889",
            "url": "https://jobs.smartrecruiters.com/BoschGroup/744000158197889",
            "title": "Product Industrialization Expert_PS_RBCW",
            "company": "Bosch Group",
            "locations": [
                {
                    "name": "Wuxi, Jiangsu, China",
                    "city": "Wuxi",
                    "region": "Jiangsu",
                    "country_code": "CN",
                    "latitude": 31.4912,
                    "longitude": 120.3119,
                }
            ],
            "date": "2026-10-28",
            "language": "en",
            "employment_type": "full_time",
            "posted_at": "2026-10-28T02:14:12.200Z",
        },
        {
            "site": "smartrecruiters",
            "id": "744000158108729",
            "url": "https://jobs.smartrecruiters.com/BoschGroup/744000158108729",
            "title": "Roadside Assistance Territory Manager, Southwest region",
            "company": "Bosch Group",
            "locations": [
                {
                    "name": "Itasca, IL, United States",
                    "city": "Itasca",
                    "region": "IL",
                    "country_code": "US",
                }
            ],
            "date": "2026-10-27",
            "language": "en",
            "employment_type": "full_time",
            "workplace_type": "remote",
            "posted_at": "2026-10-27T17:07:18.526Z",
        },
    ]
    assert fetcher.requests == [f"{URL}?limit=100&offset=0"]
    hybrid = {**CARDS[0], "location": {"fullLocation": "Wuxi, Jiangsu, China", "hybrid": True}}
    fetcher = StubFetcher({"BoschGroup/postings": page([hybrid], 1)})
    assert (
        asyncio.run(smartrecruiters.search(fetcher, board="BoschGroup"))[0]["workplace_type"]
        == "hybrid"
    )
    # A card without fullLocation names its place from the place fields.
    location = {"city": "San Francisco", "region": "CA", "country": "us"}
    fetcher = StubFetcher({"BoschGroup/postings": page([{**CARDS[0], "location": location}], 1)})
    (job,) = asyncio.run(smartrecruiters.search(fetcher, board="BoschGroup"))
    assert job["locations"] == [
        {
            "name": "San Francisco, CA, US",
            "city": "San Francisco",
            "region": "CA",
            "country_code": "US",
        }
    ]


def test_the_options_become_query_parameters():
    fetcher = StubFetcher({"BoschGroup/postings": page([], 0)})
    search = smartrecruiters.search(
        fetcher, board="BoschGroup", query="data", results=5, max_age_hours=24, remote=True
    )
    asyncio.run(search)
    (request,) = fetcher.requests
    params = {name: value for name, (value,) in parse_qs(urlsplit(request).query).items()}
    released_after = datetime.fromisoformat(params.pop("releasedAfter"))
    assert abs(released_after - (datetime.now(UTC) - timedelta(hours=24))) < timedelta(minutes=1)
    assert params == {"limit": "5", "offset": "0", "q": "data", "locationType": "REMOTE"}
    asyncio.run(smartrecruiters.search(fetcher, board="BoschGroup", max_age_hours=10**20))
    assert "releasedAfter" not in fetcher.requests[-1]


def cards(count, start=0):
    return [{**CARDS[0], "id": str(n)} for n in range(start, start + count)]


def test_paging_stops_at_results_and_at_the_last_page():
    # A posting released between two requests repeats a card on the next page.
    fetcher = StubFetcher(
        {
            "offset=0": page(cards(100), 250),
            "offset=100": page(cards(50, 99), 250),
            "offset=150": page(cards(1, 149), 250),
        }
    )
    jobs = asyncio.run(smartrecruiters.search(fetcher, board="BoschGroup", results=150))
    assert [job["id"] for job in jobs] == [str(n) for n in range(150)]
    assert fetcher.requests == [
        f"{URL}?limit=100&offset=0",
        f"{URL}?limit=50&offset=100",
        f"{URL}?limit=1&offset=150",
    ]
    fetcher = StubFetcher(
        {"offset=0": page(cards(100), 150), "offset=100": page(cards(50, 100), 150)}
    )
    asyncio.run(smartrecruiters.search(fetcher, board="BoschGroup", results=1000))
    assert len(fetcher.requests) == 2


def test_an_empty_board_returns_nothing_and_names_a_misspelling(caplog):
    caplog.set_level(logging.INFO, logger="jobrake")
    fetcher = StubFetcher({"companies/BoshGroup/postings": page([], 0)})
    assert asyncio.run(smartrecruiters.search(fetcher, board="BoshGroup")) == []
    assert "board 'BoshGroup' returned no postings" in caplog.text
    assert "check the identifier" in caplog.text


def test_a_failed_or_early_empty_page_stops_with_the_pages_before_it():
    # An empty page before the reported total may have skipped postings.
    for last, message in (
        (network_down(), "smartrecruiters"),
        (page([], 250), "may be incomplete"),
    ):
        fetcher = StubFetcher({"offset=0": page(cards(100), 250), "offset=100": last})
        with pytest.raises(Stopped, match=message) as stop:
            asyncio.run(smartrecruiters.search(fetcher, board="BoschGroup", results=200))
        assert len(stop.value.partial) == 100


def test_a_malformed_card_costs_only_itself(caplog):
    bad_place = {"latitude": "north", "longitude": "1e999"}
    malformed = [{**CARDS[0], "id": None}, "not a card", {**CARDS[1], "location": bad_place}]
    fetcher = StubFetcher({"BoschGroup/postings": page(malformed, 3)})
    (job,) = asyncio.run(smartrecruiters.search(fetcher, board="BoschGroup"))
    assert job["id"] == "744000158108729"
    assert "latitude" not in job
    assert "longitude" not in job
    assert caplog.text.count("skipping malformed smartrecruiters posting") == 2
