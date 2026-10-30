"""SmartRecruiters Posting API paging and parsing tests."""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from fakes import StubFetcher, network_down, not_found, ok

from jobrake import Stopped
from jobrake.fetchkit import FetchResult
from jobrake.sites import smartrecruiters

# Two cards from api.smartrecruiters.com/v1/companies/BoschGroup/postings, the
# second with locationType=REMOTE, fetched 2026-10-28, trimmed to the fields
# jobrake reads plus a few it leaves out. The first card gains a department in
# SmartRecruiters' documented shape, which BoschGroup leaves out.
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
        "department": {"id": "8193", "label": "Manufacturing"},
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

PRODUCT_EXPERT_URL = "https://jobs.smartrecruiters.com/BoschGroup/744000158197889"
# The record CARDS[0] parses into.
PRODUCT_EXPERT = {
    "site": "smartrecruiters",
    "id": "744000158197889",
    "url": PRODUCT_EXPERT_URL,
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
    "department": "Manufacturing",
    "posted_at": "2026-10-28T02:14:12.200Z",
}


def page(cards, total):
    return ok(json.dumps({"offset": 0, "limit": 100, "totalFound": total, "content": cards}))


def test_a_board_parses_into_records():
    fetcher = StubFetcher({"BoschGroup/postings": page(CARDS, 2)})
    assert asyncio.run(smartrecruiters.search(fetcher, board="BoschGroup")) == [
        PRODUCT_EXPERT,
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


# GET {API}/BoschGroup/postings/744000158197889 on 2026-10-29, the posting
# behind CARDS[0], trimmed to the fields jobrake reads, with each section cut
# to its opening and additionalInformation emptied, as another BoschGroup
# posting serves it.
POSTING = {
    "id": "744000158197889",
    "name": "Product Industrialization Expert_PS_RBCW      ",
    "company": {"name": "Bosch Group", "identifier": "BoschGroup"},
    "releasedDate": "2026-10-28T02:14:12.200Z",
    "location": CARDS[0]["location"],
    "typeOfEmployment": {"id": "permanent", "label": "Full-time"},
    "language": {"code": "en", "label": "English", "labelNative": "English (US)"},
    "department": None,
    "jobAd": {
        "sections": {
            "companyDescription": {
                "title": "Company Description",
                "text": "<p>To better support the fast development of automotive industry and "
                "technology of China, Bosch set up its wholly owned company, Bosch Automotive "
                "Systems (Wuxi) Co., Ltd., in Wuxi (RBCW).</p>",
            },
            "jobDescription": {
                "title": "Job Description",
                "text": "<p><strong>Job Summary: </strong>&#xa0;</p><p>Responsible for new "
                "production line realization, line upgradation and modification for KPI "
                "improvement, Production Planning/management.</p>",
            },
            "qualifications": {
                "title": "Qualifications",
                "text": "<p>- Bachelor/master&#xa0;degree.</p>"
                "<p>-&#xa0;&gt;5 years working in production planning</p>",
            },
            "additionalInformation": {"title": "Additional Information", "text": ""},
        }
    },
}
DESCRIPTION = (
    "Company Description\n"
    "To better support the fast development of automotive industry and technology of China, "
    "Bosch set up its wholly owned company, Bosch Automotive Systems (Wuxi) Co., Ltd., in "
    "Wuxi (RBCW).\n"
    "Job Description\n"
    "Job Summary:\n"
    "Responsible for new production line realization, line upgradation and modification for "
    "KPI improvement, Production Planning/management.\n"
    "Qualifications\n"
    "- Bachelor/master degree.\n"
    "- >5 years working in production planning"
)
POSTINGS = "https://api.smartrecruiters.com/v1/companies/BoschGroup/postings/"


def test_details_fill_each_card_and_stop_when_one_fails(caplog):
    fetcher = StubFetcher(
        {
            "postings?": page(CARDS, 2),
            "postings/744000158197889": ok(json.dumps(POSTING)),
            "postings/744000158108729": not_found(),  # closed since the search
        }
    )
    filled, gone = asyncio.run(smartrecruiters.search(fetcher, board="BoschGroup", details=True))
    # The posting names no department, so the card's stays.
    assert filled == {**PRODUCT_EXPERT, "description": DESCRIPTION}
    assert gone["id"] == "744000158108729"
    assert "description" not in gone
    assert fetcher.requests[1:] == [f"{POSTINGS}744000158197889", f"{POSTINGS}744000158108729"]
    # A field the posting leaves empty keeps the card's value.
    bare = {**POSTING, "name": None, "location": {}}
    fetcher.responses["postings/744000158197889"] = ok(json.dumps(bare))
    filled_again, _ = asyncio.run(smartrecruiters.search(fetcher, board="BoschGroup", details=True))
    assert filled_again == filled
    fetcher.responses["postings/744000158108729"] = network_down()
    with pytest.raises(Stopped, match="details of 1 of 2 postings") as stop:
        asyncio.run(smartrecruiters.search(fetcher, board="BoschGroup", details=True))
    assert stop.value.partial[0] == filled
    assert "skipping posting" in caplog.text


def test_postings_fetch_each_posting_once_and_key_it_by_reference():
    url = PRODUCT_EXPERT_URL
    slugged = f"{url}-product-industrialization-expert-ps-rbcw?trk=x"  # the posting's postingUrl
    shouted = "https://JOBS.SMARTRECRUITERS.COM/BoschGroup/744000158197889"
    board = "https://jobs.smartrecruiters.com/BoschGroup/"
    gone, malformed, closed, failed = (f"{board}{n}" for n in (1, 2, 3, 4))
    # SmartRecruiters answered a malformed request this way on 2026-10-30.
    # A 400 says nothing about the posting.
    bad_request = FetchResult("stub", 400, "Bad Request", error="client error (HTTP 400)")
    fetcher = StubFetcher(
        {
            "postings/744000158197889": ok(json.dumps(POSTING)),
            "postings/1": not_found(),
            "postings/2": bad_request,
            "postings/3": ok(json.dumps({**POSTING, "id": "3", "active": False})),
            "postings/4": network_down(),
        }
    )
    references = [url, slugged, shouted, gone, malformed, closed, failed]
    got = asyncio.run(smartrecruiters.postings(fetcher, references))
    # Without a card, the record is the posting's alone, which names no department. A 400
    # fails like a dropped connection, so its reference has no key.
    record = {**PRODUCT_EXPERT, "description": DESCRIPTION}
    del record["department"]
    assert got == {
        url: record,
        slugged: record,
        shouted: record,
        gone: None,
        closed: None,
    }
    assert len(fetcher.requests) == 5


@pytest.mark.parametrize(
    "reference",
    [
        "https://jobs.smartrecruiters.com/BoschGroup",  # the board, not one of its postings
        f"{POSTINGS}744000158197889",  # the API's address
        "https://careers.smartrecruiters.com/BoschGroup/744000158197889",
        "https://jobs.smartrecruiters.com/BoschGroup/product-expert",  # no posting ID
    ],
)
def test_postings_reject_a_reference_that_is_not_a_smartrecruiters_posting(reference):
    fetcher = StubFetcher({})
    with pytest.raises(ValueError, match="not a SmartRecruiters posting URL"):
        asyncio.run(smartrecruiters.postings(fetcher, [PRODUCT_EXPERT_URL, reference]))
    assert fetcher.requests == []
