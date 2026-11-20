"""AcademicTransfer search answer parsing and paging tests."""

import asyncio
import json
from urllib.parse import parse_qs, urlsplit

import pytest
from fakes import PagedFetcher

from jobrake import Stopped
from jobrake.sites import academictransfer

# A jobs page's Nuxt payload, trimmed to the entry that holds the public token, here a stand-in.
TOKEN_PAGE = (
    '<script type="application/json" id="__NUXT_DATA__">'
    '[["ShallowReactive",1],{"state":2},{"$satDataApiPublicAccessToken":3},"public-token"]'
    "</script>"
)
JOBS = "https://www.academictransfer.com/en/jobs/"

# Three vacancies as the list API served them on 2026-11-17, with fields left out, each text cut to
# its first block, and keywords to the first two. RSM's sends 0 for the salary and the weekly hours
# it leaves out, and no organization or keywords.
ERASMUS = {
    "external_id": 365285,
    "absolute_url": JOBS + "365285/tenure-track-assistant-professor-in-applied-economics-10-fte/",
    "application_url": "https://www.mmimir.nu/track/c32ba0d1-197e-4ddf-b49a-853a8be7c20c",
    "title": "Tenure Track Assistant Professor in Applied Economics (1.0 fte)",
    "organisation_name": "Erasmus University Rotterdam",
    "department_name": "",
    "city": "Rotterdam",
    "country_code": "NL",
    "language_code": "en",
    "contract_type": 2,
    "education_level": 1,
    "min_salary": 4925,
    "max_salary": 6682,
    "start_date": "2026-11-04T09:00:10.440304+01:00",
    "end_date": "2026-12-01T23:59:59+01:00",
    "keywords": ["Applied Economics", "Health Economics"],
    "min_weekly_hours": 38.0,
    "max_weekly_hours": 38.0,
    "description": "The Department of Applied Economics at Erasmus School of Economics (ESE), "
    "Erasmus University Rotterdam, the Netherlands, invites applications for a tenure-track "
    "Assistant Professor position, starting on 1 September 2027.",
    "requirements": "<strong>What you bring</strong><br>",
    "contract_terms": "We offer you an internationally oriented and varied job in an enthusiastic "
    "team, with excellent working conditions in accordance with the Collective Labour Agreement "
    "for Dutch Universities (CAO-NU).<br><br>",
    "additional_info": "",
    "extra_info": "<strong>Interested?</strong><br><br>",
}
GRONINGEN = {
    "external_id": 365603,
    "absolute_url": JOBS + "365603/phd-position-in-the-field-of-economic-behaviour-and-"
    "organization/",
    "title": "PhD position in the field of Economic Behaviour and Organization",
    "organisation_name": "University of Groningen",
    "department_name": "Faculty of Economics and Business",
    "city": "Groningen",
    "country_code": "NL",
    "start_date": "2026-11-16T09:30:21.823667+01:00",
}
RSM = {
    "external_id": 365360,
    "absolute_url": JOBS + "365360/fully-funded-phd-positions-in-organisational-behaviour-human-"
    "resource-management-and-sustainability-and-management-at-rotterdam-school-of-management-"
    "erasmus-university-rsm/",
    "title": "Fully funded PhD Positions in Organisational Behaviour, Human Resource Management "
    "and Sustainability and Management at Rotterdam School of Management, Erasmus University (RSM)",
    "organisation_name": "",
    "city": "Rotterdam",
    "country_code": "NL",
    "min_salary": 0,
    "max_salary": 0,
    "start_date": "2026-11-05T17:11:23.565240+01:00",
    "keywords": [],
    "min_weekly_hours": 0.0,
    "max_weekly_hours": 0.0,
    "additional_info": "<p><strong>How to apply</strong></p>",
}


def _answer(*vacancies: object, count: int) -> str:
    return json.dumps({"count": count, "next": None, "previous": None, "results": list(vacancies)})


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    async def sleep(seconds: float) -> None:
        pass

    monkeypatch.setattr(academictransfer.asyncio, "sleep", sleep)


def test_a_search_maps_each_vacancy_and_waits_before_each_api_request(monkeypatch):
    fetcher = PagedFetcher(
        [TOKEN_PAGE, _answer(ERASMUS, GRONINGEN, count=3), _answer(RSM, count=3)]
    )
    waits = []

    async def sleep(seconds: float) -> None:
        waits.append((seconds, len(fetcher.requests)))

    monkeypatch.setattr(academictransfer.asyncio, "sleep", sleep)
    jobs = asyncio.run(
        academictransfer.search(fetcher, query=" economics ", vacancy_type="Scientific", results=3)
    )
    assert jobs == [
        {
            "site": "academictransfer",
            "id": "365285",
            "url": ERASMUS["absolute_url"],
            "title": "Tenure Track Assistant Professor in Applied Economics (1.0 fte)",
            "company": "Erasmus University Rotterdam",
            "locations": [{"name": "Rotterdam, NL", "city": "Rotterdam", "country_code": "NL"}],
            "date": "2026-11-04",
            "description": f"{ERASMUS['description']}\n\nWhat you bring\n\n"
            "We offer you an internationally oriented and varied job in an enthusiastic team, with "
            "excellent working conditions in accordance with the Collective Labour Agreement for "
            "Dutch Universities (CAO-NU).\n\nInterested?",
            "language": "en",
            "employment_type": "temporary",
            "salary_min": 4925.0,
            "salary_max": 6682.0,
            "salary_currency": "EUR",
            "salary_period": "MONTH",
            "posted_at": "2026-11-04T09:00:10.440304+01:00",
            "expires_at": "2026-12-01T23:59:59+01:00",
            "apply_url": "https://www.mmimir.nu/track/c32ba0d1-197e-4ddf-b49a-853a8be7c20c",
            "education": "Doctorate",
            "keywords": ["Applied Economics", "Health Economics"],
            "site_data": {"min_weekly_hours": 38.0, "max_weekly_hours": 38.0},
        },
        {
            "site": "academictransfer",
            "id": "365603",
            "url": GRONINGEN["absolute_url"],
            "title": "PhD position in the field of Economic Behaviour and Organization",
            "company": "University of Groningen",
            "locations": [{"name": "Groningen, NL", "city": "Groningen", "country_code": "NL"}],
            "date": "2026-11-16",
            "department": "Faculty of Economics and Business",
            "posted_at": "2026-11-16T09:30:21.823667+01:00",
        },
        {
            "site": "academictransfer",
            "id": "365360",
            "url": RSM["absolute_url"],
            "title": RSM["title"],
            "company": None,
            "locations": [{"name": "Rotterdam, NL", "city": "Rotterdam", "country_code": "NL"}],
            "date": "2026-11-05",
            "description": "How to apply",
            "posted_at": "2026-11-05T17:11:23.565240+01:00",
        },
    ]
    token_page, *pages = fetcher.requests
    assert token_page == JOBS
    assert [parse_qs(urlsplit(page).query) for page in pages] == [
        {
            "vacancy_type": ["scientific"],
            "is_active": ["true"],
            "ordering": ["-start_date"],
            "search": ["economics"],
            "offset": [str(offset)],
            "limit": ["3"],
        }
        for offset in (0, 2)
    ]
    assert (
        fetcher.headers[1:]
        == [{"Authorization": "Bearer public-token", "Accept": "application/json; version=2"}] * 2
    )
    # Each wait comes after the request before it and before the next.
    assert waits == [(academictransfer.DELAY, 1), (academictransfer.DELAY, 2)]


def test_an_empty_page_before_the_count_stops_the_search_with_the_pages_before_it():
    fetcher = PagedFetcher([TOKEN_PAGE, _answer(ERASMUS, count=5), _answer(count=5)])
    stop = "reported 5 postings but sent an empty page after 1"
    with pytest.raises(Stopped, match=stop) as caught:
        asyncio.run(academictransfer.search(fetcher))
    assert [job["id"] for job in caught.value.partial] == ["365285"]
    query = parse_qs(urlsplit(fetcher.requests[1]).query, keep_blank_values=True)
    assert "search" not in query
    assert query["limit"] == ["50"]


@pytest.mark.parametrize(
    "payload",
    [
        "[{}]",
        "{",  # not JSON
        '[{"$satDataApiPublicAccessToken": 5}]',  # an index past the payload's end
        '[{"$satDataApiPublicAccessToken": -1}, "en-GB"]',  # devalue's index of undefined
    ],
)
def test_a_jobs_page_without_a_readable_token_stops_the_search_before_the_api(payload):
    page = f'<script type="application/json" id="__NUXT_DATA__">{payload}</script>'
    fetcher = PagedFetcher([page])
    with pytest.raises(Stopped, match="academictransfer sent a response this version cannot read"):
        asyncio.run(academictransfer.search(fetcher))
    assert len(fetcher.requests) == 1
