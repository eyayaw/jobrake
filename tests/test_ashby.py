"""Ashby Job Posting API parsing tests."""

import asyncio
import json

from fakes import StubFetcher, ok

from jobrake.sites import ashby

# Two postings from api.ashbyhq.com/posting-api/job-board/ramp?includeCompensation=true,
# fetched 2026-10-28, trimmed to the fields jobrake reads plus isListed and isRemote,
# with each description cut to its role heading and a sentence or two, with
# compensation cut to its summaryComponents.
POSTINGS = [
    {
        "id": "c63ba7d7-5290-4d9b-b002-40b2873b66f6",
        "title": "Partner Consultant, Accounting",
        "employmentType": "FullTime",
        "location": "Remote (US)",
        "secondaryLocations": [
            {
                "location": "Remote (Canada)",
                "address": {"postalAddress": {"addressCountry": "Canada"}},
            },
            {
                "location": "San Francisco, CA",
                "address": {
                    "postalAddress": {
                        "addressRegion": "California ",
                        "addressCountry": "USA",
                        "addressLocality": "San Fransisco",
                    }
                },
            },
            {
                "location": "New York, NY (HQ)",
                "address": {
                    "postalAddress": {
                        "addressRegion": "NY",
                        "addressCountry": "USA",
                        "addressLocality": "New York City",
                    }
                },
            },
        ],
        "publishedAt": "2026-09-02T17:17:20.841+00:00",
        "isListed": True,
        "isRemote": True,
        "workplaceType": "Remote",
        "address": {"postalAddress": {"addressCountry": "United States"}},
        "jobUrl": "https://jobs.ashbyhq.com/ramp/c63ba7d7-5290-4d9b-b002-40b2873b66f6",
        "applyUrl": "https://jobs.ashbyhq.com/ramp/c63ba7d7-5290-4d9b-b002-40b2873b66f6/application",
        "descriptionHtml": '<h1><strong>About the Role</strong></h1><p style="min-height:1.5em">'
        "The Solutions Team are technical experts that work directly with customers and "
        "partners to provide world-class product, sales, industry, and domain expertise.</p>",
        "compensation": {
            "summaryComponents": [
                {
                    "minValue": 151000,
                    "maxValue": 231000,
                    "currencyCode": "USD",
                    "interval": "1 YEAR",
                    "compensationType": "Salary",
                },
                {
                    "compensationType": "EquityCashValue",
                    "minValue": None,
                    "maxValue": None,
                    "interval": "1 YEAR",
                },
            ]
        },
    },
    {
        "id": "b39ceb08-a0a7-4f8b-a760-2fb88e209956",
        "title": "Applied Scientist Intern",
        "employmentType": "Intern",
        "location": "New York, NY (HQ)",
        "publishedAt": "2026-09-15T01:44:04.643+00:00",
        "isListed": True,
        "isRemote": True,
        "workplaceType": "Hybrid",
        "address": {
            "postalAddress": {
                "addressRegion": "NY",
                "addressCountry": "USA",
                "addressLocality": "New York City",
            }
        },
        "jobUrl": "https://jobs.ashbyhq.com/ramp/b39ceb08-a0a7-4f8b-a760-2fb88e209956",
        "applyUrl": "https://jobs.ashbyhq.com/ramp/b39ceb08-a0a7-4f8b-a760-2fb88e209956/application",
        "descriptionHtml": '<h1><strong>About the Role</strong></h1><p style="min-height:1.5em">'
        "The Applied Science team builds models and tools that solve Ramp’s most critical "  # noqa: RUF001  the posting's own apostrophe
        "problems: from underwriting businesses to combatting fraud to making spend "
        "management smarter.</p>",
        "compensation": {
            "summaryComponents": [
                {
                    "compensationType": "Salary",
                    "interval": "1 MONTH",
                    "currencyCode": "USD",
                    "minValue": 12500,
                    "maxValue": 12500,
                }
            ]
        },
    },
]


def board(postings):
    return ok(json.dumps({"jobs": postings, "apiVersion": "1"}))


def test_a_board_parses_into_records():
    # Ashby serves an unlisted posting for direct links, and jobrake returns it too.
    # It also lacks id, which Ashby does not document, so its ID comes from jobUrl.
    unlisted = {**POSTINGS[1], "isListed": False}
    del unlisted["id"]
    fetcher = StubFetcher({"job-board/ramp": board([POSTINGS[0], unlisted])})
    assert asyncio.run(ashby.search(fetcher, board="ramp")) == [
        {
            "site": "ashby",
            "id": "c63ba7d7-5290-4d9b-b002-40b2873b66f6",
            "url": "https://jobs.ashbyhq.com/ramp/c63ba7d7-5290-4d9b-b002-40b2873b66f6",
            "title": "Partner Consultant, Accounting",
            "company": None,
            "locations": [
                {"name": "Remote (US)"},
                {"name": "Remote (Canada)"},
                # Each secondary place keeps its own address, as Ashby spells it.
                {"name": "San Francisco, CA", "city": "San Fransisco", "region": "California"},
                {"name": "New York, NY (HQ)", "city": "New York City", "region": "NY"},
            ],
            "date": "2026-09-02",
            "description": "About the Role\nThe Solutions Team are technical experts that work "
            "directly with customers and partners to provide world-class product, sales, "
            "industry, and domain expertise.",
            "employment_type": "full_time",
            "workplace_type": "remote",
            "salary_min": 151000,
            "salary_max": 231000,
            "salary_currency": "USD",
            "salary_period": "YEAR",
            "posted_at": "2026-09-02T17:17:20.841+00:00",
            "apply_url": "https://jobs.ashbyhq.com/ramp/c63ba7d7-5290-4d9b-b002-40b2873b66f6/application",
        },
        {
            "site": "ashby",
            "id": "b39ceb08-a0a7-4f8b-a760-2fb88e209956",
            "url": "https://jobs.ashbyhq.com/ramp/b39ceb08-a0a7-4f8b-a760-2fb88e209956",
            "title": "Applied Scientist Intern",
            "company": None,
            "locations": [{"name": "New York, NY (HQ)", "city": "New York City", "region": "NY"}],
            "date": "2026-09-15",
            "description": "About the Role\nThe Applied Science team builds models and tools that "
            "solve Ramp’s most critical problems: from underwriting businesses to combatting "  # noqa: RUF001  the posting's own apostrophe
            "fraud to making spend management smarter.",
            "employment_type": "internship",
            "workplace_type": "hybrid",  # isRemote says true for it
            "salary_min": 12500,
            "salary_max": 12500,
            "salary_currency": "USD",
            "salary_period": "MONTH",
            "posted_at": "2026-09-15T01:44:04.643+00:00",
            "apply_url": "https://jobs.ashbyhq.com/ramp/b39ceb08-a0a7-4f8b-a760-2fb88e209956/application",
        },
    ]
    assert fetcher.requests == [
        "https://api.ashbyhq.com/posting-api/job-board/ramp?includeCompensation=true"
    ]
    # A malformed jobUrl stays as given and costs neither its posting nor the next.
    odd = {**POSTINGS[0], "jobUrl": "https://[invalid"}
    fetcher = StubFetcher({"job-board/ramp": board([odd, POSTINGS[1]])})
    jobs = asyncio.run(ashby.search(fetcher, board="ramp"))
    assert [job["url"] for job in jobs] == ["https://[invalid", POSTINGS[1]["jobUrl"]]
    # Ashby documents a secondary location's address without postalAddress.
    documented = {
        **POSTINGS[1],
        "secondaryLocations": [
            {
                "location": "San Francisco",
                "address": {"addressLocality": "San Francisco", "addressRegion": "California"},
            }
        ],
    }
    fetcher = StubFetcher({"job-board/ramp": board([documented])})
    (job,) = asyncio.run(ashby.search(fetcher, board="ramp"))
    assert job["locations"][1] == {
        "name": "San Francisco",
        "city": "San Francisco",
        "region": "California",
    }
