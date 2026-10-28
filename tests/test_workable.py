"""Workable widget API parsing tests."""

import asyncio
import json

from fakes import StubFetcher, ok

from jobrake.sites import workable

# Two postings from apply.workable.com/api/v1/widget/accounts/huggingface?details=true,
# fetched 2026-10-28, trimmed to the fields jobrake reads and a few it drops,
# with each description cut to a block or two. The second posting's
# telecommuting is changed to false to cover an onsite posting.
POSTINGS = [
    {
        "title": "Senior Machine Learning Engineer, Voice Agents - EMEA Remote",
        "shortcode": "9E2A4C02C7",
        "employment_type": "Full-time",
        "telecommuting": True,
        "department": "Science",
        "url": "https://apply.workable.com/j/9E2A4C02C7",
        "shortlink": "https://apply.workable.com/j/9E2A4C02C7",
        "application_url": "https://apply.workable.com/j/9E2A4C02C7/apply",
        "published_on": "2026-09-02",
        "country": "France",
        "city": "Paris",
        "state": "Île-de-France",
        "education": "Master's Degree",
        "locations": [
            {
                "country": "France",
                "countryCode": "FR",
                "city": "Paris",
                "region": "Île-de-France",
                "hidden": True,
            }
        ],
        "description": "<p>At Hugging Face, we're on a journey to democratize good AI. "
        "Our open-source libraries have more than 600k+ stars on Github.</p><p></p>"
        "<p><strong>About the Role</strong></p>",
    },
    {
        "title": "Wild Card",
        "shortcode": "0BD8C06DB3",
        "employment_type": "Full-time",
        "telecommuting": False,
        "department": "Wild Card",
        "url": "https://apply.workable.com/j/0BD8C06DB3",
        "shortlink": "https://apply.workable.com/j/0BD8C06DB3",
        "application_url": "https://apply.workable.com/j/0BD8C06DB3/apply",
        "published_on": "2024-10-17",
        "country": "United States",
        "city": "",
        "state": "",
        "education": "Unspecified",
        "locations": [
            {
                "country": "United States",
                "countryCode": "US",
                "city": "",
                "region": None,
                "hidden": False,
            }
        ],
        "description": "<p>If you don't see the perfect job position, just apply to this one!"
        "<br></p><p></p><p><strong>Requirements</strong></p>",
    },
]


def board(postings):
    return ok(json.dumps({"name": "Hugging Face", "description": "", "jobs": postings}))


def test_a_board_parses_into_records():
    fetcher = StubFetcher({"accounts/huggingface": board(POSTINGS)})
    assert asyncio.run(workable.search(fetcher, board="huggingface")) == [
        {
            "site": "workable",
            "id": "9E2A4C02C7",
            "url": "https://apply.workable.com/j/9E2A4C02C7",
            "title": "Senior Machine Learning Engineer, Voice Agents - EMEA Remote",
            "company": "Hugging Face",
            "location": "Paris, Île-de-France, France",
            "date": "2026-09-02",
            "description": "At Hugging Face, we're on a journey to democratize good AI. "
            "Our open-source libraries have more than 600k+ stars on Github.\nAbout the Role",
            "employment_type": "full_time",
            "is_remote": True,
            "city": "Paris",
            "region": "Île-de-France",
            "country_code": "FR",
            "posted_at": "2026-09-02",
            "apply_url": "https://apply.workable.com/j/9E2A4C02C7/apply",
            "education": "Master's Degree",
        },
        {
            "site": "workable",
            "id": "0BD8C06DB3",
            "url": "https://apply.workable.com/j/0BD8C06DB3",
            "title": "Wild Card",
            "company": "Hugging Face",
            "location": "United States",
            "date": "2024-10-17",
            "description": "If you don't see the perfect job position, just apply to this "
            "one!\nRequirements",
            "employment_type": "full_time",
            "country_code": "US",
            "posted_at": "2024-10-17",
            "apply_url": "https://apply.workable.com/j/0BD8C06DB3/apply",
        },
    ]
    assert fetcher.requests == [
        "https://apply.workable.com/api/v1/widget/accounts/huggingface?details=true"
    ]
