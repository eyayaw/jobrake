"""Lever Postings API parsing tests."""

import asyncio
import json

import pytest
from fakes import StubFetcher, network_down, not_found, ok

from jobrake import Stopped
from jobrake.sites import lever

GLOBAL = "https://api.lever.co/v0/postings"
EU = "https://api.eu.lever.co/v0/postings"

# Two postings from api.lever.co/v0/postings/palantir?mode=json, fetched
# 2026-10-28, trimmed to the fields jobrake reads plus categories.team and
# opening, with each HTML field and list cut to a block or two. The second
# posting's workplaceType is changed from hybrid to remote to cover the flag.
POSTINGS = [
    {
        "id": "6ed76ce8-4156-4b60-b120-403538bd66cd",
        "text": "Administrative Business Partner",
        "hostedUrl": "https://jobs.lever.co/palantir/6ed76ce8-4156-4b60-b120-403538bd66cd",
        "applyUrl": "https://jobs.lever.co/palantir/6ed76ce8-4156-4b60-b120-403538bd66cd/apply",
        "createdAt": 1786469891368,
        "country": "SG",
        "workplaceType": "hybrid",
        "categories": {
            "commitment": "Full-time",
            "location": "Singapore, Singapore",
            "team": "Administrative",
        },
        "opening": '<div><strong><span style="font-size: 18px;">A World-Changing Company'
        "</span></strong></div>",
        "description": '<div><strong><span style="font-size: 18px;">A World-Changing Company'
        "</span></strong></div>\n<div>&nbsp;</div>\n"
        "<div>Palantir builds the world’s leading "  # noqa: RUF001  the posting's own apostrophe
        "software for data-driven decisions and operations.</div>",
        "lists": [
            {
                "text": "What We Value",
                "content": "\n<li>Ability to adjust quickly, anticipate needs, and implement "
                "autonomously, with strong attention to detail.</li>\n<li>High level of "
                "integrity, confidentiality, and discretion in both internal and external "
                "interactions.</li>\n",
            }
        ],
        "additional": "<div>Palantir is particularly interested in applicants who have a "
        "current right to work in Singapore, and we encourage Singapore citizens to "
        "apply.</div><div><br></div>",
    },
    {
        "id": "a237973c-cb29-41fe-9c80-416e6f42e087",
        "text": "Administrative Business Partner - ShipOS",
        "hostedUrl": "https://jobs.lever.co/palantir/a237973c-cb29-41fe-9c80-416e6f42e087",
        "applyUrl": "https://jobs.lever.co/palantir/a237973c-cb29-41fe-9c80-416e6f42e087/apply",
        "createdAt": 1781771660468,
        "country": "US",
        "workplaceType": "remote",
        "categories": {
            "commitment": "Full-time",
            "location": "Washington, D.C.",
            "team": "Administrative",
        },
        "opening": '<div><strong><span style="font-size: 18px;">A World-Changing Company'
        "</span></strong></div>",
        "description": '<div><strong><span style="font-size: 18px;">A World-Changing Company'
        "</span></strong></div>",
        "lists": [
            {
                "text": "What We Value",
                "content": "\n<li>You move fast and close loops — you don't let things "
                "fall through the cracks.</li>\n",
            }
        ],
        "additional": "<h3><strong>Salary</strong></h3>\n<div>The estimated salary range "
        "for this position is estimated to be $60,000 - $97,000/year.</div>",
    },
]


def test_a_board_parses_into_records():
    fetcher = StubFetcher({"api.lever.co": ok(json.dumps(POSTINGS))})
    assert asyncio.run(lever.search(fetcher, board="palantir")) == [
        {
            "site": "lever",
            "id": "6ed76ce8-4156-4b60-b120-403538bd66cd",
            "url": "https://jobs.lever.co/palantir/6ed76ce8-4156-4b60-b120-403538bd66cd",
            "title": "Administrative Business Partner",
            "company": None,
            "location": "Singapore, Singapore",
            "date": "2026-08-11",
            "description": "A World-Changing Company\n"
            "Palantir builds the world’s leading "  # noqa: RUF001  the posting's own apostrophe
            "software for data-driven decisions and operations.\nWhat We Value\nAbility to "
            "adjust quickly, anticipate needs, and implement autonomously, with strong "
            "attention to detail.\nHigh level of integrity, confidentiality, and discretion "
            "in both internal and external interactions.\nPalantir is particularly interested "
            "in applicants who have a current right to work in Singapore, and we encourage "
            "Singapore citizens to apply.",
            "employment_type": "full_time",
            "country_code": "SG",
            "posted_at": "2026-08-11T17:38:11.368000+00:00",
            "apply_url": "https://jobs.lever.co/palantir/6ed76ce8-4156-4b60-b120-403538bd66cd/apply",
        },
        {
            "site": "lever",
            "id": "a237973c-cb29-41fe-9c80-416e6f42e087",
            "url": "https://jobs.lever.co/palantir/a237973c-cb29-41fe-9c80-416e6f42e087",
            "title": "Administrative Business Partner - ShipOS",
            "company": None,
            "location": "Washington, D.C.",
            "date": "2026-06-18",
            "description": "A World-Changing Company\nWhat We Value\nYou move fast and close "
            "loops — you don't let things fall through the cracks.\nSalary\nThe estimated "
            "salary range for this position is estimated to be $60,000 - $97,000/year.",
            "employment_type": "full_time",
            "is_remote": True,
            "country_code": "US",
            "posted_at": "2026-06-18T08:34:20.468000+00:00",
            "apply_url": "https://jobs.lever.co/palantir/a237973c-cb29-41fe-9c80-416e6f42e087/apply",
        },
    ]
    assert fetcher.requests == [f"{GLOBAL}/palantir?mode=json"]


def test_a_creation_time_in_seconds_costs_only_its_field(caplog):
    posting = {**POSTINGS[0], "createdAt": 1786469891}
    fetcher = StubFetcher({"api.lever.co": ok(json.dumps([posting]))})
    (job,) = asyncio.run(lever.search(fetcher, board="palantir"))
    assert job["date"] is None
    assert "posted_at" not in job
    assert "looks like epoch seconds" in caplog.text


def test_the_description_keeps_every_section_on_its_own_line():
    posting = {
        **POSTINGS[0],
        "description": "Build software",
        "lists": [{"text": "Requirements", "content": "<li>Python</li>"}],
        "salaryDescription": "Plus commission",
        "additional": "Benefits included",
    }
    fetcher = StubFetcher({"api.lever.co": ok(json.dumps([posting]))})
    (job,) = asyncio.run(lever.search(fetcher, board="palantir"))
    assert job["description"] == (
        "Build software\nRequirements\nPython\nPlus commission\nBenefits included"
    )
    # An unreadable lists field costs only its own sections.
    fetcher = StubFetcher({"api.lever.co": ok(json.dumps([{**posting, "lists": 1}]))})
    (job,) = asyncio.run(lever.search(fetcher, board="palantir"))
    assert job["description"] == "Build software\nPlus commission\nBenefits included"


def test_only_a_404_from_the_global_host_sends_the_board_to_the_eu_host():
    fetcher = StubFetcher(
        {"api.lever.co": not_found(), "api.eu.lever.co": ok(json.dumps(POSTINGS[1:]))}
    )
    jobs = asyncio.run(lever.search(fetcher, board="palantir"))
    assert [job["id"] for job in jobs] == ["a237973c-cb29-41fe-9c80-416e6f42e087"]
    assert fetcher.requests == [f"{GLOBAL}/palantir?mode=json", f"{EU}/palantir?mode=json"]
    # A failure other than a 404 says nothing about the EU host, so it is not asked.
    fetcher = StubFetcher({"api.lever.co": network_down(), "api.eu.lever.co": ok("[]")})
    with pytest.raises(Stopped, match="connection reset"):
        asyncio.run(lever.search(fetcher, board="palantir"))
    assert fetcher.requests == [f"{GLOBAL}/palantir?mode=json"]
