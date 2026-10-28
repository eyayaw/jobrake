"""Greenhouse Job Board API parsing tests."""

import asyncio
import json

from fakes import StubFetcher, ok

from jobrake.sites import greenhouse

# Two postings from boards-api.greenhouse.io/v1/boards/airbnb/jobs?content=true,
# fetched 2026-10-28, trimmed to the fields jobrake reads plus updated_at and
# internal_job_id, with each description cut to a block or two.
POSTINGS = [
    {
        "id": 8285171,
        "internal_job_id": 3583414,
        "title": "Strategic Finance & Analytics Intern (MBA)",
        "company_name": "Airbnb",
        "location": {"name": "United States"},
        "absolute_url": "https://careers.airbnb.com/positions/8285171?gh_jid=8285171",
        "language": "en",
        "first_published": "2026-10-15T11:14:03-04:00",
        "updated_at": "2026-10-16T02:02:58-04:00",
        "application_deadline": "2026-11-01T23:45:00-05:00",
        "content": "&lt;p&gt;&lt;strong&gt;The Community You Will Join:&lt;/strong&gt;&lt;/p&gt;\n"
        "&lt;p&gt;Airbnb is seeking MBA students to join the Finance organization as "
        "Strategic Finance &amp;amp; Analytics Interns for our &lt;strong&gt;2027 Summer "
        "Intern&lt;/strong&gt; &lt;strong&gt;Program&lt;/strong&gt; from "
        "&lt;strong&gt;May 24, 2027 - August 13, 2027&lt;/strong&gt;.&lt;/p&gt;",
    },
    {
        "id": 8264827,
        "internal_job_id": 3576058,
        "title": "Gestionnaire, Excellence de la prestation de services",
        "company_name": "Airbnb",
        "location": {"name": "Ontario, Canada, Quebec, Canada"},
        "absolute_url": "https://careers.airbnb.com/positions/8264827?gh_jid=8264827",
        "language": "fr",
        "first_published": "2026-10-14T16:45:33-04:00",
        "updated_at": "2026-10-14T16:45:33-04:00",
        "application_deadline": None,
        "content": "&lt;p&gt;&lt;strong&gt;La différence que vous ferez :&lt;/strong&gt;&lt;/p&gt;",
    },
]


def board(postings):
    return ok(json.dumps({"jobs": postings, "meta": {"total": len(postings)}}))


def test_a_board_parses_into_records():
    fetcher = StubFetcher({"boards/airbnb/jobs": board(POSTINGS)})
    assert asyncio.run(greenhouse.search(fetcher, board="airbnb")) == [
        {
            "site": "greenhouse",
            "id": "8285171",
            "url": "https://careers.airbnb.com/positions/8285171?gh_jid=8285171",
            "title": "Strategic Finance & Analytics Intern (MBA)",
            "company": "Airbnb",
            "location": "United States",
            "date": "2026-10-15",
            "description": "The Community You Will Join:\nAirbnb is seeking MBA students to "
            "join the Finance organization as Strategic Finance & Analytics Interns for our "
            "2027 Summer Intern Program from May 24, 2027 - August 13, 2027.",
            "language": "en",
            "posted_at": "2026-10-15T11:14:03-04:00",
            "expires_at": "2026-11-01T23:45:00-05:00",
        },
        {
            "site": "greenhouse",
            "id": "8264827",
            "url": "https://careers.airbnb.com/positions/8264827?gh_jid=8264827",
            "title": "Gestionnaire, Excellence de la prestation de services",
            "company": "Airbnb",
            "location": "Ontario, Canada, Quebec, Canada",
            "date": "2026-10-14",
            "description": "La différence que vous ferez :",
            "language": "fr",
            "posted_at": "2026-10-14T16:45:33-04:00",
        },
    ]
    assert fetcher.requests == [
        "https://boards-api.greenhouse.io/v1/boards/airbnb/jobs?content=true"
    ]


def test_a_posting_without_an_integer_id_is_skipped(caplog):
    malformed = [{**POSTINGS[0], "id": None}, POSTINGS[1]]
    fetcher = StubFetcher({"boards/airbnb/jobs": board(malformed)})
    jobs = asyncio.run(greenhouse.search(fetcher, board="airbnb"))
    assert [job["id"] for job in jobs] == ["8264827"]
    assert "skipping malformed greenhouse posting" in caplog.text
