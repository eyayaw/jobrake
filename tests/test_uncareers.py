"""UN Careers list paging and parsing tests."""

import asyncio
import json

import pytest
from fakes import PagedFetcher

from jobrake import Stopped, check
from jobrake.sites import uncareers

# An opening from careers.un.org/api/public/opening/jo/list/filteredV2/en, fetched 2026-11-16,
# with its description cut short.
OPENING = {
    "_id": "6af6f1d0dca68d4334019107",
    "jobId": 287773,
    "language": "EN",
    "categoryCode": "PD",
    "jobTitle": "HUMANITARIAN AFFAIRS OFFICER (PROGRAMME)",
    "postingTitle": "HUMANITARIAN AFFAIRS OFFICER (PROGRAMME), P3",
    "jobCodeTitle": "HUMANITARIAN AFFAIRS OFFICER",
    "jobDescription": (
        "<div class='jobPostingDetail'>\n\r<div class='jobPostingItem'>"
        "<div class='jobPostingItemTitle'>Org. Setting and Reporting</div>"
        "<div class='jobPostingItemContent'>These positions are located in the Crisis Response "
        "Division (CRD).</div></div></div>"
    ),
    "jobFamilyCode": "HRA",
    "jobLevel": "P-3",
    "dutyStation": [
        {"code": "2400", "description": "NAIROBI", "_id": "6afa3f67e114ae07bffbc489"},
        {"code": "4380", "description": "KAMPALA", "_id": "6afa3f67e114ae07bffbc48a"},
    ],
    "recruitmentType": "J",
    "startDate": "2026-11-13T05:00:00.000Z",
    "endDate": "2026-11-20T04:59:59.000Z",
    "jn": {"code": "POLNET", "name": "Political, Peace and Humanitarian"},
    "jf": {"Code": "HRA", "Name": "Humanitarian Affairs"},
    "jc": {"code": "PD", "name": "Professional and Higher Categories"},
    "jl": {"code": "100", "name": "P-3"},
    "recrttype": {"code": "T", "name": "Temporary Opportunities"},
    "dept": {"code": "39843984", "name": "Office for the Coordination of Humanitarian Affairs"},
    "totalCount": 448,
}


# Filters of careers.un.org/api/public/opening/jo-filter/list/en, fetched 2026-11-16, trimmed to a
# few entries and the fields jobrake reads. The site lists job families under each job network and
# none under the job family filter.
CATALOG = json.dumps(
    {
        "status": 1,
        "message": "Success.",
        "data": [
            {
                "name": "Category",
                "shortname": "jc",
                "values": [
                    {"code": "PD", "name": "Professional and Higher Categories"},
                    {"code": "INT", "name": "Affiliate Personnel – Internships"},  # noqa: RUF001  the site's own en dash
                ],
            },
            {
                "name": "Job Network",
                "shortname": "jn",
                "values": [
                    {
                        "code": "DEVNET",
                        "name": "Economic, Social and Development",
                        "jobFamilies": [
                            {"Code": "STT", "Name": "Statistics"},
                            {
                                "Code": "ECO",
                                "Name": "Economic Affairs (and Sustainable Development)",
                            },
                        ],
                    }
                ],
            },
            {"name": "Job Family", "shortname": "jf", "values": []},
            {
                "name": "Level",
                "shortname": "jle",
                "values": [{"code": "90", "name": "P-4"}, {"code": "100", "name": "P-3"}],
            },
            {
                "name": "Duty Station",
                "shortname": "ds",
                "values": [
                    {"code": "Geneva", "name": "Geneva", "countryName": "Switzerland"},
                    {
                        "code": "NEWYORK",
                        "name": "New York",
                        "countryName": "United States of America",
                    },
                    {"code": "1470", "name": "Paris", "countryName": "France"},
                ],
            },
        ],
    }
)


def page(openings, total):
    return json.dumps({"status": 1, "message": "", "data": {"count": total, "list": openings}})


def numbered(count, start=0):
    return [OPENING | {"jobId": n} for n in range(start, start + count)]


def test_an_opening_becomes_a_record_with_a_place_per_duty_station(caplog):
    malformed = {"postingTitle": "no jobId"}
    jobs = asyncio.run(uncareers.search(PagedFetcher([page([OPENING, malformed], total=2)])))
    assert jobs == [
        {
            "site": "uncareers",
            "id": "287773",
            "url": "https://careers.un.org/jobSearchDescription/287773?language=en",
            "title": "HUMANITARIAN AFFAIRS OFFICER (PROGRAMME), P3",
            "company": "Office for the Coordination of Humanitarian Affairs",
            "locations": [{"name": "NAIROBI"}, {"name": "KAMPALA"}],
            "date": "2026-11-13",
            "description": "Org. Setting and Reporting\nThese positions are located in the Crisis "
            "Response Division (CRD).",
            "posted_at": "2026-11-13T05:00:00.000Z",
            "expires_at": "2026-11-20T04:59:59.000Z",
            "site_data": {
                "category": "PD",
                "level": "P-3",
                "job_family": "Humanitarian Affairs",
                "job_network": "Political, Peace and Humanitarian",
                "recruitment_type": "Temporary Opportunities",
            },
        }
    ]
    assert "skipping malformed uncareers posting" in caplog.text


def test_search_pages_by_job_id_until_results_or_the_total_and_stops_at_an_early_empty_page():
    # An opening posted between two requests repeats a card on the next page.
    pages = [numbered(100), numbered(100, 99), numbered(100, 199)]
    fetcher = PagedFetcher([page(openings, total=448) for openings in pages])
    jobs = asyncio.run(uncareers.search(fetcher, results=250))
    assert [job["id"] for job in jobs] == [str(n) for n in range(250)]
    assert fetcher.bodies[2] == {
        "filterConfig": {},
        "pagination": {"page": 2, "itemPerPage": 100, "sortBy": "jobId", "sortDirection": -1},
    }
    # A search for fewer openings than a page holds asks for only that many.
    fetcher = PagedFetcher([page(numbered(3), total=5)])
    assert len(asyncio.run(uncareers.search(fetcher, results=3))) == 3
    assert fetcher.bodies[0]["pagination"]["itemPerPage"] == 3
    # An empty page before the reported total may have skipped openings.
    fetcher = PagedFetcher([page(numbered(100), total=448), page([], total=448)])
    with pytest.raises(Stopped, match="may be incomplete") as stop:
        asyncio.run(uncareers.search(fetcher, results=448))
    assert len(stop.value.partial) == 100


def test_a_search_sends_the_codes_its_filter_names_stand_for_and_refuses_what_the_site_ignores():
    fetcher = PagedFetcher([CATALOG, page([], total=0)])
    asyncio.run(
        uncareers.search(
            fetcher,
            category=["int"],
            duty_station=["new york", " Geneva "],
            level=["P-3"],
            job_family=["statistics"],
            max_age_hours=168,
        )
    )
    assert fetcher.bodies[1]["filterConfig"] == {
        "jc": ["INT"],
        "ds": ["Geneva", "NEWYORK"],
        "jle": ["100"],
        "jf": ["STT"],
        "span": ["7"],
    }
    # A search without a list filter reads no catalog.
    fetcher = PagedFetcher([page([], total=0)])
    asyncio.run(uncareers.search(fetcher, query=" economist "))
    assert [body["filterConfig"] for body in fetcher.bodies] == [{"keyword": "economist"}]
    # The site ignores a code it does not know, a category drops the keyword, and the site has three
    # posting ages, so each of these would return openings the caller excluded.
    fetcher = PagedFetcher([CATALOG])
    with pytest.raises(
        ValueError, match=r"unknown UN Careers duty station 'Genva'\. Did you mean 'Geneva'"
    ):
        asyncio.run(uncareers.search(fetcher, duty_station=["Genva"]))
    assert len(fetcher.requests) == 1
    # A filter missing from the catalog is a site change, not a misspelled value.
    with pytest.raises(Stopped, match="without department values, likely an API change"):
        asyncio.run(uncareers.search(PagedFetcher([CATALOG]), department=["ECA"]))
    with pytest.raises(ValueError, match="ignores query when category is given"):
        check("uncareers", query="economist", category=["CON"])
    with pytest.raises(ValueError, match="24, 168, or 720 hours only, not 48"):
        check("uncareers", max_age_hours=48)
