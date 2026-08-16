"""Indeed GraphQL parsing and pagination tests."""

import asyncio
import json
import logging

import pytest
from fakes import StubFetcher, ok, rate_limited

from jobrake.sites import indeed
from jobrake.sites.indeed.countries import indeed_domain


def test_query_escapes_graphql_strings_as_json():
    query = indeed.build_query('C:\\jobs "quoted"', 'Brussels "center"', 0, None, 'next\\"')

    assert 'what: "C:\\\\jobs \\"quoted\\""' in query
    assert 'where: "Brussels \\"center\\""' in query
    assert "radius: 0" in query
    assert 'cursor: "next\\\\\\""' in query


def test_indeed_country_aliases_and_api_codes():
    assert indeed_domain("usa") == indeed_domain("United States") == ("www", "US")
    assert indeed_domain("uk") == ("uk", "GB")
    assert indeed_domain("netherlands") == ("nl", "NL")


def test_indeed_rejects_an_unknown_country():
    with pytest.raises(ValueError, match="Atlantis"):
        indeed_domain("Atlantis")


def indeed_payload(keys, cursor=None):
    return {
        "data": {
            "jobSearch": {
                "pageInfo": {"nextCursor": cursor},
                "results": [
                    {
                        "job": {
                            "key": k,
                            "title": f"Job {k}",
                            "datePublished": 1717200000000,
                            "description": {"html": "<p>Economist &amp; analyst</p>"},
                            "location": {"city": "NYC", "admin1Code": "NY", "countryCode": "US"},
                            "employer": {"name": "Acme"},
                        }
                    }
                    for k in keys
                ],
            }
        }
    }


def test_indeed_parses_and_paginates():
    pages = [indeed_payload(["a", "b"], cursor="next"), indeed_payload(["c"])]

    class Paged(StubFetcher):
        async def post(self, url, json_body, headers=None):
            self.requests.append(url)
            return ok(json.dumps(pages[len(self.requests) - 1]))

    fetcher = Paged({})
    jobs = asyncio.run(
        indeed.search(fetcher, search_term="economist", country="usa", results_wanted=10)
    )
    assert [j["title"] for j in jobs] == ["Job a", "Job b", "Job c"]
    assert jobs[0]["id"] == "a"
    assert jobs[0]["url"] == "https://www.indeed.com/viewjob?jk=a"
    assert jobs[0]["location"] == "NYC, NY, US"
    assert jobs[0]["description"] == "Economist & analyst"
    assert jobs[0]["date"] == "2024-06-01"
    assert len(fetcher.requests) == 2  # stopped when cursor ran out


def test_indeed_keeps_a_job_whose_date_is_not_milliseconds(caplog):
    payload = indeed_payload(["a"])
    payload["data"]["jobSearch"]["results"][0]["job"]["datePublished"] = 1717200000  # seconds
    fetcher = StubFetcher({"apis.indeed.com": ok(json.dumps(payload))})
    with caplog.at_level(logging.WARNING, logger="jobrake.sites.indeed"):
        jobs = asyncio.run(indeed.search(fetcher, search_term="x", country="usa"))
    assert jobs[0]["title"] == "Job a"  # the posting survives
    assert jobs[0]["posted_at"] is None  # only its timestamp is lost
    assert jobs[0]["date"] == ""
    assert any("milliseconds" in record.message for record in caplog.records)


def test_indeed_stops_at_results_wanted():
    fetcher = StubFetcher({"apis.indeed.com": ok(json.dumps(indeed_payload(["a", "b", "c"])))})
    jobs = asyncio.run(indeed.search(fetcher, search_term="x", country="usa", results_wanted=2))
    assert len(jobs) == 2


def test_indeed_error_result_yields_empty():
    fetcher = StubFetcher({"apis.indeed.com": rate_limited()})
    assert asyncio.run(indeed.search(fetcher, search_term="x", country="usa")) == []


def rich_job(**overrides):
    return {
        "key": "a",
        "title": "Nurse",
        "datePublished": 1717200000000,
        "expirationDate": 1719792000000,
        "description": {"html": "<p>Role</p>"},
        "location": {
            "city": "Boston",
            "admin1Code": "MA",
            "countryCode": "US",
            "latitude": 42.36,
            "longitude": -71.06,
        },
        "employer": {
            "name": "Acme Health",
            "relativeCompanyPageUrl": "/cmp/Acme-Health",
            "dossier": {"images": {"squareLogoUrl": "https://img/logo.png"}},
        },
        "recruit": {"viewJobUrl": "https://acme.example/careers/1"},
        "compensation": {
            "baseSalary": {"unitOfWork": "HOUR", "range": {"min": 38.2, "max": 77.4}},
            "currencyCode": "USD",
        },
        "attributes": [{"label": "Full-time"}, {"label": "401(k)"}, {"label": "Remote"}],
    } | overrides


def parse_one(job):
    payload = {"data": {"jobSearch": {"pageInfo": {}, "results": [{"job": job}]}}}
    return indeed.parse_jobs(payload, "https://www.indeed.com")[0][0]


def test_indeed_maps_detail_onto_the_model():
    job = parse_one(rich_job())
    assert job["posted_at"] == "2024-06-01T00:00:00+00:00"
    assert job["expires_at"] == "2024-07-01T00:00:00+00:00"
    assert job["date"] == "2024-06-01"  # derived, not restated
    assert job["company_url"] == "https://www.indeed.com/cmp/Acme-Health"
    assert job["company_logo"] == "https://img/logo.png"
    assert job["apply_url"] == "https://acme.example/careers/1"
    assert job["employment_type"] == "full_time"  # the unified form
    assert job["is_remote"] is True
    assert (job["salary_min"], job["salary_max"]) == (38.2, 77.4)
    assert (job["salary_currency"], job["salary_period"]) == ("USD", "HOUR")
    assert (job["city"], job["region"], job["country_code"]) == ("Boston", "MA", "US")
    assert (job["latitude"], job["longitude"]) == (42.36, -71.06)


def test_indeed_absent_detail_stays_none():
    job = parse_one(rich_job(compensation=None, recruit=None, attributes=[], employer=None))
    assert job["salary_min"] is None
    assert job["apply_url"] is None
    assert job["employment_type"] is None
    assert job["is_remote"] is None  # untagged is not evidence of on-site


def test_indeed_single_bound_salaries():
    at_least = rich_job(
        compensation={"baseSalary": {"unitOfWork": "YEAR", "range": {"min": 90000.0}}}
    )
    exactly = rich_job(
        compensation={"baseSalary": {"unitOfWork": "YEAR", "range": {"value": 120000.0}}}
    )
    assert (parse_one(at_least)["salary_min"], parse_one(at_least)["salary_max"]) == (90000.0, None)
    assert (parse_one(exactly)["salary_min"], parse_one(exactly)["salary_max"]) == (
        120000.0,
        120000.0,
    )


def test_description_scrubs_flattened_stylesheets():
    # Some ATS pages arrive with their css flattened into the description text.
    css = ".jobdescription td { padding: 0 5px; } /* sidebar */ h1 { font-size: 14px !important; }"
    job = parse_one(
        rich_job(description={"html": css + "<p>Great role.</p><p>Salary range: 40k.</p>"})
    )
    assert job["description"] == "Great role.\nSalary range: 40k."


def test_indeed_remote_label_matches_exactly():
    # "Remote sensing observations" is a skill, not a workplace
    job = parse_one(rich_job(attributes=[{"label": "Remote sensing observations"}]))
    assert job["is_remote"] is None
