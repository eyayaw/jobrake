"""Workday career site parsing and paging tests."""

import asyncio
import importlib
import json
from datetime import date

import pytest
from fakes import PagedFetcher, StubFetcher, network_down, not_found, ok

from jobrake import Stopped
from jobrake.sites import workday

BOARD = "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"
API = "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite"
# workday.search is the exported function, so import its module directly.
SEARCH = importlib.import_module("jobrake.sites.workday.search")

# Three cards, as served, from POST {API}/jobs on 2026-10-28: two from a search
# without keywords and one from a search for part-time "engineer" postings.
CARDS = [
    {
        "title": "Networking Architect",
        "externalPath": "/job/US-CA-Santa-Clara/Networking-Architect_JR1996377",
        "locationsText": "US, CA, Santa Clara",
        "postedOn": "Posted Today",
        "bulletFields": ["JR1996377"],
    },
    {
        "title": "Principal Architect, System Software - Orbital Data Center",
        "externalPath": "/job/US-CA-Santa-Clara/"
        "Principal-Architect--System-Software---Orbital-Data-Center_JR2019010",
        "locationsText": "2 Locations",
        "postedOn": "Posted Today",
        "bulletFields": ["JR2019010"],
    },
    {
        "title": "AI Research Scientist",
        "externalPath": "/job/Singapore-Singapore-Suntec-Tower/AI-Research-Scientist_JR2018673",
        "locationsText": "2 Locations",
        "postedOn": "Posted 30+ Days Ago",
        "bulletFields": ["JR2018673"],
    },
]


def page(cards, total=None):
    total = len(cards) if total is None else total
    return json.dumps(
        {"total": total, "jobPostings": cards, "facets": [], "userAuthenticated": False}
    )


def numbered(count, start=0):
    return [
        {**CARDS[0], "externalPath": f"/job/Remote/Engineer_JR{n}"}
        for n in range(start, start + count)
    ]


@pytest.fixture
def today(monkeypatch):
    monkeypatch.setattr(SEARCH, "_today", lambda: date(2026, 10, 28))


def test_a_search_page_parses_into_records(today):
    fetcher = StubFetcher({"/jobs": ok(page(CARDS))})
    jobs = asyncio.run(workday.search(fetcher, board=BOARD, query="architect"))
    assert jobs == [
        {
            "site": "workday",
            "id": "nvidia:JR1996377",
            "url": f"{BOARD}/job/US-CA-Santa-Clara/Networking-Architect_JR1996377",
            "title": "Networking Architect",
            "company": None,
            "location": "US, CA, Santa Clara",
            "date": "2026-10-28",
        },
        {
            "site": "workday",
            "id": "nvidia:JR2019010",
            "url": f"{BOARD}/job/US-CA-Santa-Clara/"
            "Principal-Architect--System-Software---Orbital-Data-Center_JR2019010",
            "title": "Principal Architect, System Software - Orbital Data Center",
            "company": None,
            "location": None,
            "date": "2026-10-28",
        },
        {
            "site": "workday",
            "id": "nvidia:JR2018673",
            "url": f"{BOARD}/job/Singapore-Singapore-Suntec-Tower/AI-Research-Scientist_JR2018673",
            "title": "AI Research Scientist",
            "company": None,
            "location": None,
            "date": None,
        },
    ]
    assert fetcher.requests == [f"{API}/jobs"]
    assert fetcher.bodies == [
        {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "architect"}
    ]


# GET {API}/job/US-CA-Santa-Clara/Networking-Architect_JR1996377 on 2026-10-28,
# trimmed to jobPostingInfo and hiringOrganization, with the description cut
# to its first two paragraphs.
DETAIL = {
    "jobPostingInfo": {
        "id": "9683fb87cfe610016c0dba112fad0000",
        "title": "Networking Architect",
        "jobDescription": "<p>NVIDIA Networking has been a leader in high performance "
        "networking infrastructure for many years.</p><p>What you’ll be doing:</p>",  # noqa: RUF001  the posting's own apostrophe
        "location": "US, CA, Santa Clara",
        "postedOn": "Posted Today",
        "startDate": "2026-10-27",
        "timeType": "Full time",
        "jobReqId": "JR1996377",
        "jobPostingId": "Networking-Architect_JR1996377",
        "jobRequisitionLocation": {
            "descriptor": "US, CA, Santa Clara",
            "country": {
                "descriptor": "United States of America",
                "id": "bc33aa3152ec42d4995f4791a106ed09",
                "alpha2Code": "US",
            },
        },
        "externalUrl": f"{BOARD}/job/US-CA-Santa-Clara/Networking-Architect_JR1996377",
    },
    "hiringOrganization": {"name": "2100 NVIDIA USA", "url": ""},
}


def test_details_fill_each_card_and_stop_when_one_fails(today, caplog):
    fetcher = StubFetcher(
        {
            "/jobs": ok(page([*CARDS, *numbered(1)])),
            "Networking-Architect_JR1996377": ok(json.dumps(DETAIL)),
            "Orbital-Data-Center_JR2019010": not_found(),  # removed since the search
            "AI-Research-Scientist_JR2018673": network_down(),
            "Engineer_JR0": ok("[]"),
        }
    )
    filled = {
        "site": "workday",
        "id": "nvidia:JR1996377",
        "url": f"{BOARD}/job/US-CA-Santa-Clara/Networking-Architect_JR1996377",
        "title": "Networking Architect",
        "company": None,
        "location": "US, CA, Santa Clara",
        "date": "2026-10-27",  # the start date, a day before the card's "Posted Today"
        "description": "NVIDIA Networking has been a leader in high performance networking "
        "infrastructure for many years.\nWhat you’ll be doing:",  # noqa: RUF001  the posting's own apostrophe
        "employment_type": "full_time",
        "country_code": "US",
        "posted_at": "2026-10-27",
    }
    assert asyncio.run(workday.search(fetcher, board=BOARD, results=1, details=True)) == [filled]
    assert fetcher.requests[1] == f"{API}/job/US-CA-Santa-Clara/Networking-Architect_JR1996377"
    with pytest.raises(Stopped, match="details of 2 of 4 postings") as stop:
        asyncio.run(workday.search(fetcher, board=BOARD, details=True))
    assert [job["id"] for job in stop.value.partial] == [
        "nvidia:JR1996377",
        "nvidia:JR2019010",
        "nvidia:JR2018673",
        "nvidia:JR0",
    ]
    assert stop.value.partial[0] == filled
    assert caplog.text.count("skipping the details of") == 2


def test_a_relative_posting_date_counts_back_from_today(today):
    labels = ["Posted Yesterday", "Posted 3 Days Ago", "Posted 30+ Days Ago", "Publié hier", None]
    cards = [{**card, "postedOn": label} for card, label in zip(numbered(5), labels, strict=True)]
    jobs = asyncio.run(workday.search(StubFetcher({"/jobs": ok(page(cards))}), board=BOARD))
    assert [job["date"] for job in jobs] == ["2026-10-27", "2026-10-25", None, None, None]


def test_a_board_url_names_its_career_site():
    copied = "https://NVIDIA.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/x?q=1#top"
    fetcher = StubFetcher({"/jobs": ok(page([]))})
    asyncio.run(workday.search(fetcher, board=copied))
    assert fetcher.requests == [f"{API}/jobs"]
    for board in (
        "https://nvidia.wd5.myworkdaysite.com/recruiting/nvidia/NVIDIAExternalCareerSite",
        "https://nvidia.wd5.myworkdayjobs.com/en-US",
        "nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite",
        "https://careers.nvidia.com/NVIDIAExternalCareerSite",
        "https://nvidia.wd5.myworkdayjobs.com:1234/NVIDIAExternalCareerSite",
        "https://nvidia.wd5.myworkdayjobs.com:garbage/NVIDIAExternalCareerSite",
        f"{API}/jobs",
    ):
        fetcher = StubFetcher({})
        with pytest.raises(ValueError, match="not a Workday career site URL"):
            asyncio.run(workday.search(fetcher, board=board))
        assert fetcher.requests == []


def test_only_a_404_on_the_first_page_means_an_unknown_site():
    board = "https://nvidia.wd5.myworkdayjobs.com/NoSuchSiteJrZz9"
    with pytest.raises(Stopped, match=f"no career site at '{board}'") as stop:
        asyncio.run(workday.search(StubFetcher({"/jobs": not_found()}), board=board))
    assert stop.value.partial == []
    fetcher = PagedFetcher([page(numbered(20), total=40), not_found()])
    with pytest.raises(Stopped, match=r"stopped: HTTP 404\. Kept the 20 postings") as stop:
        asyncio.run(workday.search(fetcher, board=BOARD, results=40))
    assert len(stop.value.partial) == 20


def test_a_card_without_a_requisition_id_is_skipped(caplog):
    malformed = [{**CARDS[0], "externalPath": "/job/no-requisition"}, CARDS[1]]
    jobs = asyncio.run(workday.search(StubFetcher({"/jobs": ok(page(malformed))}), board=BOARD))
    assert [job["id"] for job in jobs] == ["nvidia:JR2019010"]
    assert "skipping malformed workday posting" in caplog.text


def test_paging_stops_at_results_at_the_first_total_and_at_an_empty_page(caplog, monkeypatch):
    # A posting added between two requests repeats a card on the next page.
    pages = [numbered(20), numbered(5, 19), numbered(1, 24)]
    fetcher = PagedFetcher([page(cards, total=2000) for cards in pages])
    jobs = asyncio.run(workday.search(fetcher, board=BOARD, results=25))
    assert [job["id"] for job in jobs] == [f"nvidia:JR{n}" for n in range(25)]
    requested = [(body["offset"], body["limit"]) for body in fetcher.bodies]
    assert requested == [(0, 20), (20, 5), (25, 1)]
    fetcher = PagedFetcher([page(numbered(20), total=2000), page([], total=2000)])
    assert len(asyncio.run(workday.search(fetcher, board=BOARD, results=100))) == 20
    # A search that reaches a total below the cap is complete.
    fetcher = PagedFetcher([page(numbered(20), total=25), page(numbered(5, 20), total=25)])
    assert len(asyncio.run(workday.search(fetcher, board=BOARD, results=100))) == 25
    assert "at most" not in caplog.text
    # Later pages are reported to say total 0, so the first page's total stands.
    monkeypatch.setattr(SEARCH, "MAX_TOTAL", 43)
    pages = [page(numbered(20), total=43), page(numbered(20, 20), total=0)]
    fetcher = PagedFetcher([*pages, page(numbered(3, 40), total=0)])
    assert len(asyncio.run(workday.search(fetcher, board=BOARD, results=100))) == 43
    assert "workday reports at most 43 postings per search" in caplog.text
