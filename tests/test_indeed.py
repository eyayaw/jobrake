"""Indeed GraphQL parsing and pagination tests."""

import asyncio
import json
import logging
import math

import pytest
from fakes import StubFetcher, ok, rate_limited

from jobrake.models import IDENTITY_FIELDS, SUMMARY_FIELDS
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
    pages = [indeed_payload(["a", "b"], cursor="next"), indeed_payload(["b", "c"])]

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


def test_indeed_stops_a_repeated_cursor_without_repeating_jobs():
    page = ok(json.dumps(indeed_payload(["a"], cursor="same")))
    fetcher = StubFetcher({"apis.indeed.com": page})

    jobs = asyncio.run(indeed.search(fetcher, search_term="x", country="usa", results_wanted=10))

    assert [job["id"] for job in jobs] == ["a"]
    assert len(fetcher.requests) == 2


def test_indeed_keeps_a_job_whose_date_is_not_milliseconds(caplog):
    payload = indeed_payload(["a"])
    payload["data"]["jobSearch"]["results"][0]["job"]["datePublished"] = 1717200000  # seconds
    fetcher = StubFetcher({"apis.indeed.com": ok(json.dumps(payload))})
    with caplog.at_level(logging.WARNING, logger="jobrake.sites.indeed"):
        jobs = asyncio.run(indeed.search(fetcher, search_term="x", country="usa"))
    assert jobs[0]["title"] == "Job a"  # the posting survives
    assert "posted_at" not in jobs[0]  # only its timestamp is lost
    assert jobs[0]["date"] is None
    assert any("milliseconds" in record.message for record in caplog.records)


def test_indeed_stops_at_results_wanted():
    fetcher = StubFetcher({"apis.indeed.com": ok(json.dumps(indeed_payload(["a", "b", "c"])))})
    jobs = asyncio.run(indeed.search(fetcher, search_term="x", country="usa", results_wanted=2))
    assert len(jobs) == 2


def test_indeed_error_result_yields_empty():
    fetcher = StubFetcher({"apis.indeed.com": rate_limited()})
    assert asyncio.run(indeed.search(fetcher, search_term="x", country="usa")) == []


def test_indeed_skips_malformed_results_and_keeps_valid_siblings(caplog):
    payload = indeed_payload(["a", "b"])
    results = payload["data"]["jobSearch"]["results"]
    results[1:1] = [
        {"job": None},  # the provider sent a null job
        {"job": {"key": None, "title": "Job null-key"}},  # would become id "" and jk=None
        {"job": {"key": "", "title": "Job empty-key"}},
        {"job": {"key": "   ", "title": "Job blank-key"}},
        {"no-job-key": True},
    ]
    fetcher = StubFetcher({"apis.indeed.com": ok(json.dumps(payload))})
    with caplog.at_level(logging.WARNING, logger="jobrake.sites.indeed"):
        jobs = asyncio.run(indeed.search(fetcher, search_term="x", country="usa"))
    assert [job["id"] for job in jobs] == ["a", "b"]
    assert sum("malformed" in record.message for record in caplog.records) == 5


def test_indeed_malformed_later_page_keeps_collected_jobs():
    pages = [indeed_payload(["a"], cursor="next"), {"data": {"jobSearch": None}}]

    class Paged(StubFetcher):
        async def post(self, url, json_body, headers=None):
            self.requests.append(url)
            return ok(json.dumps(pages[len(self.requests) - 1]))

    fetcher = Paged({})
    jobs = asyncio.run(indeed.search(fetcher, search_term="x", country="usa", results_wanted=10))
    assert [job["id"] for job in jobs] == ["a"]


@pytest.mark.parametrize(
    "damage",
    [
        lambda job_search: job_search.update(pageInfo="malformed"),
        lambda job_search: job_search.pop("pageInfo"),
        lambda job_search: job_search.update(pageInfo=None),
        lambda job_search: job_search.update(pageInfo={"nextCursor": ["malformed"]}),
    ],
    ids=["string", "absent", "null", "list-cursor"],
)
def test_indeed_damaged_page_info_ends_the_search_with_the_page_kept(damage):
    last = indeed_payload(["b"])
    damage(last["data"]["jobSearch"])
    pages = [indeed_payload(["a"], cursor="next"), last]

    class Paged(StubFetcher):
        async def post(self, url, json_body, headers=None):
            self.requests.append(url)
            return ok(json.dumps(pages[len(self.requests) - 1]))

    fetcher = Paged({})
    jobs = asyncio.run(indeed.search(fetcher, search_term="x", country="usa", results_wanted=10))
    assert [job["id"] for job in jobs] == ["a", "b"]  # both pages parsed; no cursor, so done


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


def test_indeed_omits_the_detail_a_posting_lacks():
    job = parse_one(rich_job(compensation=None, recruit=None, attributes=[], employer=None))
    # untagged is not evidence of on-site
    assert {"salary_min", "apply_url", "employment_type", "is_remote"}.isdisjoint(job)


def test_indeed_single_bound_salaries():
    at_least = rich_job(
        compensation={"baseSalary": {"unitOfWork": "YEAR", "range": {"min": 90000.0}}}
    )
    exactly = rich_job(
        compensation={"baseSalary": {"unitOfWork": "YEAR", "range": {"value": 120000.0}}}
    )
    one_bound = parse_one(at_least)
    assert one_bound["salary_min"] == 90000.0
    assert "salary_max" not in one_bound  # AtLeast carries no upper bound
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
    assert "is_remote" not in job


def test_indeed_omits_invalid_detail_values():
    job = parse_one(
        rich_job(
            title={"t": 1},
            location="Boston",  # a leaf where an object belongs loses the object's fields
            description="a bare string",
            employer={"name": ["Acme"], "relativeCompanyPageUrl": {"u": 1}, "dossier": "flat"},
            recruit=["x"],
            attributes=7,  # a non-list bag loses the employment fields
            compensation={
                "baseSalary": {"unitOfWork": 7, "range": {"min": "38.2", "max": math.nan}},
                "currencyCode": {"code": "USD"},
            },
        )
    )
    assert (job["id"], job["url"]) == ("a", "https://www.indeed.com/viewjob?jk=a")
    assert (job["title"], job["company"], job["location"]) == (None, None, None)
    # a numeric string is not a number and nan is not finite
    assert set(job) == {*IDENTITY_FIELDS, *SUMMARY_FIELDS, "posted_at", "expires_at"}


def test_indeed_strips_the_job_key():
    job = parse_one(rich_job(key=" padded "))
    assert job["id"] == "padded"
    assert job["url"].endswith("jk=padded")


def test_indeed_ignores_malformed_attribute_entries():
    job = parse_one(rich_job(attributes=[{}, {"label": 3}, "Remote", {"label": "Full-time"}]))
    assert job["employment_type"] == "full_time"
    assert "is_remote" not in job  # the bare string is not a Remote tag
