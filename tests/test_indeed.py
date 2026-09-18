"""Indeed GraphQL parsing and pagination tests."""

import asyncio
import json
import logging
import math
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from fakes import StubFetcher, ok, rate_limited

from jobrake.models import IDENTITY_FIELDS, SUMMARY_FIELDS
from jobrake.sites import indeed


def test_query_escapes_graphql_strings_as_json():
    query = indeed.build_query('C:\\jobs "quoted"', 'Brussels "center"', 0, None, 'next\\"')

    assert 'what: "C:\\\\jobs \\"quoted\\""' in query
    assert 'where: "Brussels \\"center\\""' in query
    assert "radius: 0" in query
    company = 'key\\"quoted'
    with_company = indeed.build_query("", None, None, None, None, company)
    assert f'field: "indeedEmployerKey", keys: [{json.dumps(company)}]' in with_company
    with_attributes = indeed.build_query("", None, None, None, None, attributes=[company])
    assert f'field: "attributes", keys: [{json.dumps(company)}]' in with_attributes
    assert 'cursor: "next\\\\\\""' in query


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


def test_company_lookup_keeps_usable_keys_in_provider_order():
    hits = [
        {"employerKey": " fe219df7f711aa73 ", "suggestion": " ABN AMRO "},
        {},
        {"employerKey": 123, "suggestion": "Invalid key"},
        {"employerKey": " ", "suggestion": "Blank key"},
        {"employerKey": "6495c5a19835b81b", "suggestion": None},
        {"employerKey": "6495c5a19835b81b", "suggestion": "Abn amro, bouwfonds"},
    ]
    fetcher = StubFetcher({"suggestions/company": ok(json.dumps(hits))})
    assert asyncio.run(indeed.companies(fetcher, " ABN & AMRO ", "netherlands")) == [
        {"employerKey": "fe219df7f711aa73", "suggestion": "ABN AMRO"},
        {"employerKey": "6495c5a19835b81b", "suggestion": "Abn amro, bouwfonds"},
    ]
    params = parse_qs(urlparse(fetcher.requests[0]).query)
    assert params["query"] == ["ABN & AMRO"]
    assert params["country"] == ["NL"]
    for name, country in [(" ", "usa"), ("ABN", "atlantis")]:
        with pytest.raises(ValueError):
            asyncio.run(indeed.companies(fetcher, name, country))
    assert len(fetcher.requests) == 1


def test_company_lookup_distinguishes_no_matches_from_failure(caplog):
    for response, expected in [
        (ok("[]"), []),
        (ok("[{}]"), None),
        (ok("{}"), None),
        (ok("not JSON"), None),
        (rate_limited(), None),
    ]:
        caplog.clear()
        fetcher = StubFetcher({"suggestions/company": response})
        assert asyncio.run(indeed.companies(fetcher, "ABN", "netherlands")) == expected
        assert bool(caplog.records) == (expected is None)


def test_indeed_rejects_invalid_company_arguments_before_searching():
    cases: list[tuple[Any, type[Exception]]] = [
        ("fe219df7f711aa73", TypeError),
        ([123], TypeError),
        ([" "], ValueError),
        (["fe219df7f711aa73", "8e8f030e53ea29e4"], ValueError),
    ]
    fetcher = StubFetcher({})
    for companies, error in cases:
        with pytest.raises(error):
            asyncio.run(
                indeed.search(fetcher, query="", country="netherlands", companies=companies)
            )
    assert fetcher.requests == []


def test_places_lists_edition_suggestions():
    hits = [
        {"suggestion": "Boston, MA", "payload": {"locationType": "CITY", "population": 589141}},
        {},  # a malformed candidate is omitted, keeping its siblings
        {"suggestion": "   ", "payload": {"locationType": "CITY"}},
        {"suggestion": "Boston Common, MA", "payload": {"locationType": {"bad": 1}}},
        {"suggestion": "Boston Massacre Marker, MA", "payload": {"locationType": "MISC"}},
    ]
    fetcher = StubFetcher({"suggestions/location": ok(json.dumps(hits))})
    assert asyncio.run(indeed.places(fetcher, "boston", "usa")) == [
        {"suggestion": "Boston, MA", "locationType": "CITY"},
        {"suggestion": "Boston Common, MA", "locationType": None},
        {"suggestion": "Boston Massacre Marker, MA", "locationType": "MISC"},
    ]
    assert "country=US" in fetcher.requests[0]
    with pytest.raises(ValueError, match="country"):
        asyncio.run(indeed.places(fetcher, "boston", "atlantis"))
    with pytest.raises(ValueError, match="blank"):
        asyncio.run(indeed.places(fetcher, "", "usa"))
    assert len(fetcher.requests) == 1


def test_indeed_parses_and_paginates():
    pages = [indeed_payload(["a", "b"], cursor="next"), indeed_payload(["b", "c"])]

    class Paged(StubFetcher):
        async def post(self, url, json_body, headers=None):
            self.requests.append(url)
            return ok(json.dumps(pages[len(self.requests) - 1]))

    fetcher = Paged({})
    jobs = asyncio.run(indeed.search(fetcher, query="economist", country="usa", results=10))
    assert [j["title"] for j in jobs] == ["Job a", "Job b", "Job c"]
    assert jobs[0]["id"] == "a"
    assert jobs[0]["url"] == "https://www.indeed.com/viewjob?jk=a"
    assert jobs[0]["location"] == "NYC, NY, US"
    assert jobs[0]["description"] == "Economist & analyst"
    assert jobs[0]["date"] == "2024-06-01"
    assert "language" not in jobs[0]
    assert len(fetcher.requests) == 2  # stopped when cursor ran out


def test_indeed_stops_a_repeated_cursor_without_repeating_jobs():
    page = ok(json.dumps(indeed_payload(["a"], cursor="same")))
    fetcher = StubFetcher({"apis.indeed.com": page})

    jobs = asyncio.run(indeed.search(fetcher, query="x", country="usa", results=10))

    assert [job["id"] for job in jobs] == ["a"]
    assert len(fetcher.requests) == 2


def test_indeed_keeps_a_job_whose_date_is_not_milliseconds(caplog):
    payload = indeed_payload(["a"])
    payload["data"]["jobSearch"]["results"][0]["job"]["datePublished"] = 1717200000  # seconds
    fetcher = StubFetcher({"apis.indeed.com": ok(json.dumps(payload))})
    with caplog.at_level(logging.WARNING, logger="jobrake.sites.indeed"):
        jobs = asyncio.run(indeed.search(fetcher, query="x", country="usa"))
    assert jobs[0]["title"] == "Job a"  # the posting survives
    assert "posted_at" not in jobs[0]  # only its timestamp is lost
    assert jobs[0]["date"] is None
    assert any("milliseconds" in record.message for record in caplog.records)


@pytest.mark.parametrize(
    ("companies", "age", "remote", "language", "attributes", "expected_keys"),
    [
        (None, 168, False, None, None, []),
        ([], None, False, None, [], []),
        (["fe219df7f711aa73"], None, False, None, [" 3CQB7 "], ["3CQB7"]),
        (["fe219df7f711aa73"], 168, False, None, ["CF3CP", "6QC5F"], ["CF3CP", "6QC5F"]),
        (None, 168, True, "Iw", None, ["DSQF7"]),
        ([], None, True, None, [" DSQF7 "], ["DSQF7"]),
        (["fe219df7f711aa73"], None, True, "in", ["3CQB7"], ["3CQB7", "DSQF7"]),
        (
            ["fe219df7f711aa73"],
            168,
            True,
            "EN",
            ["CF3CP", "\t6QC5F\n", " CF3CP "],
            ["CF3CP", "6QC5F", "DSQF7"],
        ),
        (None, None, False, "NL", None, []),
    ],
)
def test_indeed_requests_full_pages_throughout_a_cursor_chain(
    companies, age, remote, language, attributes, expected_keys
):
    # Indeed binds the page size to its cursor and rejects a changed limit
    # with BAD_USER_INPUT, so every request in a chain asks for a full page.
    pages = [indeed_payload(["a", "b"], cursor="next"), indeed_payload(["b", "c", "d"])]

    class Paged(StubFetcher):
        def __init__(self):
            super().__init__({})
            self.queries = []

        async def post(self, url, json_body, headers=None):
            self.requests.append(url)
            self.queries.append(json_body["query"])
            return ok(json.dumps(pages[len(self.requests) - 1]))

    fetcher = Paged()
    original_attributes = attributes.copy() if attributes is not None else None
    jobs = asyncio.run(
        indeed.search(
            fetcher,
            query="x",
            country="usa",
            results=3,
            companies=companies,
            max_age_hours=age,
            remote=remote,
            language=language,
            attributes=attributes,
            location="Seattle",
        )
    )
    # The second page overlaps the first, the limit stays at 100, and the
    # final slice returns three unique jobs.
    assert [job["id"] for job in jobs] == ["a", "b", "c"]
    assert all('what: "x"' in query for query in fetcher.queries)
    assert all("limit: 100" in query for query in fetcher.queries)
    assert all("language" in query.split() for query in fetcher.queries)
    for query in fetcher.queries:
        assert ('field: "indeedEmployerKey"' in query) == bool(companies)
        assert ('keys: ["fe219df7f711aa73"]' in query) == bool(companies)
        assert ('date: { field: "dateOnIndeed", start: "168h" }' in query) == bool(age)
        if expected_keys:
            assert f'keyword: {{ field: "attributes", keys: {json.dumps(expected_keys)} }}' in query
            assert query.count('field: "attributes"') == 1
        else:
            assert 'field: "attributes"' not in query
        assert 'where: "Seattle"' in query
        if language is None:
            assert 'field: "language"' not in query
        else:
            assert '{ keyword: { field: "language", keys: ["' + language.lower() + '"] } }' in query
        if (companies or expected_keys or language) and age:
            assert "} }, { keyword:" in query
        if not companies and not expected_keys and language is None and age is None:
            assert "filters:" not in query
    assert len(fetcher.queries) == 2
    assert attributes == original_attributes


def test_indeed_graphql_error_reports_the_provider_message(caplog):
    rejected = {
        "data": None,
        "errors": [{"message": "BAD_USER_INPUT: Requested limit modified during pagination"}],
    }
    pages = [indeed_payload(["a"], cursor="next"), rejected]

    class Paged(StubFetcher):
        async def post(self, url, json_body, headers=None):
            self.requests.append(url)
            return ok(json.dumps(pages[len(self.requests) - 1]))

    fetcher = Paged({})
    with caplog.at_level(logging.WARNING, logger="jobrake.sites.indeed"):
        jobs = asyncio.run(indeed.search(fetcher, query="x", country="usa", results=10))
    assert [job["id"] for job in jobs] == ["a"]  # earlier pages survive
    # The warning carries the provider's message and the retained-job count.
    assert any(
        "BAD_USER_INPUT" in record.message and "the 1 job already" in record.message
        for record in caplog.records
    )


def test_indeed_returns_the_requested_number_of_results():
    fetcher = StubFetcher({"apis.indeed.com": ok(json.dumps(indeed_payload(["a", "b", "c"])))})
    jobs = asyncio.run(indeed.search(fetcher, query="x", country="usa", results=2))
    assert len(jobs) == 2


@pytest.mark.parametrize(
    ("bad", "error", "match"),
    [
        ({"attributes": "3CQB7"}, TypeError, "attributes"),
        ({"attributes": [1]}, TypeError, "attribute code"),
        ({"attributes": [" "]}, ValueError, "attribute code is blank"),
        ({"max_age_hours": 0}, ValueError, "max_age_hours"),
        ({"results": 0}, ValueError, "results"),
        ({"radius": -1}, ValueError, "radius"),
        ({"easy_apply": True}, ValueError, "easy_apply"),
        ({"early_applicant": True}, ValueError, "early_applicant"),
        *[
            ({"language": value}, ValueError, "two ASCII letters")
            for value in ("", " ", " en ", "e", "eng", "en-US", "en_US", "e1", "éñ", "en\n")
        ],
        *[({"language": value}, TypeError, "language") for value in (False, 1, ["en"])],
    ],
)
def test_indeed_rejects_bad_arguments_before_any_request(bad, error, match):
    fetcher = StubFetcher({})
    with pytest.raises(error, match=match):
        asyncio.run(indeed.search(fetcher, query="x", country="usa", **bad))
    assert fetcher.requests == []


def test_indeed_error_result_yields_empty_with_a_warning(caplog):
    fetcher = StubFetcher({"apis.indeed.com": rate_limited()})
    with caplog.at_level(logging.WARNING, logger="jobrake.sites.indeed"):
        assert asyncio.run(indeed.search(fetcher, query="x", country="usa")) == []
    assert any("429" in record.message for record in caplog.records)


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
        jobs = asyncio.run(indeed.search(fetcher, query="x", country="usa"))
    assert [job["id"] for job in jobs] == ["a", "b"]
    assert sum("malformed" in record.message for record in caplog.records) == 5


def test_indeed_all_malformed_page_keeps_paginating():
    bad = indeed_payload(["a"], cursor="next")
    bad["data"]["jobSearch"]["results"] = [{"job": None}]
    pages = [bad, indeed_payload(["b"])]

    class Paged(StubFetcher):
        async def post(self, url, json_body, headers=None):
            self.requests.append(url)
            return ok(json.dumps(pages[len(self.requests) - 1]))

    fetcher = Paged({})
    jobs = asyncio.run(indeed.search(fetcher, query="x", country="usa", results=10))
    assert [job["id"] for job in jobs] == ["b"]  # the cursor survives the bad page


def test_indeed_malformed_later_page_keeps_collected_jobs(caplog):
    pages = [indeed_payload(["a"], cursor="next"), {"data": {"jobSearch": None}}]

    class Paged(StubFetcher):
        async def post(self, url, json_body, headers=None):
            self.requests.append(url)
            return ok(json.dumps(pages[len(self.requests) - 1]))

    fetcher = Paged({})
    with caplog.at_level(logging.WARNING, logger="jobrake.sites.indeed"):
        jobs = asyncio.run(indeed.search(fetcher, query="x", country="usa", results=10))
    assert [job["id"] for job in jobs] == ["a"]
    # the warning names the caught error
    assert any("TypeError" in record.message for record in caplog.records)


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
    jobs = asyncio.run(indeed.search(fetcher, query="x", country="usa", results=10))
    assert [job["id"] for job in jobs] == ["a", "b"]  # Both pages survive the bad cursor.


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


@pytest.mark.parametrize("language", ["en", "nl"])
def test_indeed_maps_detail_onto_the_model(language):
    job = parse_one(rich_job(language=language))
    assert job["language"] == language
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


@pytest.mark.parametrize("language", [None, "", "   "])
def test_indeed_omits_the_detail_a_posting_lacks(language):
    job = parse_one(
        rich_job(compensation=None, recruit=None, attributes=[], employer=None, language=language)
    )
    # untagged is not evidence of on-site
    assert {"salary_min", "apply_url", "employment_type", "is_remote", "language"}.isdisjoint(job)


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
            language={"code": "en"},
            location="Boston",  # a leaf where an object belongs loses the object's fields
            description="a bare string",
            employer={"name": ["Acme"], "relativeCompanyPageUrl": {"u": 1}, "dossier": "flat"},
            recruit=["x"],
            attributes=7,  # a non-list bag loses the employment fields
            compensation={
                "baseSalary": {
                    "unitOfWork": 7,
                    "range": {"min": "38.2", "max": math.nan, "value": 10**1000},
                },
                "currencyCode": {"code": "USD"},
            },
        )
    )
    assert (job["id"], job["url"]) == ("a", "https://www.indeed.com/viewjob?jk=a")
    assert (job["title"], job["company"], job["location"]) == (None, None, None)
    # a numeric string, nan, and an integer beyond float range each cost
    # only their field
    assert set(job) == {*IDENTITY_FIELDS, *SUMMARY_FIELDS, "posted_at", "expires_at"}


def test_indeed_strips_the_job_key():
    job = parse_one(rich_job(key=" padded "))
    assert job["id"] == "padded"
    assert job["url"].endswith("jk=padded")


def test_indeed_ignores_malformed_attribute_entries():
    job = parse_one(rich_job(attributes=[{}, {"label": 3}, "Remote", {"label": "Full-time"}]))
    assert job["employment_type"] == "full_time"
    assert "is_remote" not in job  # the bare string is not a Remote tag


def test_attribute_lookup_preserves_distinct_codes_and_skips_malformed_entries():
    entries = [
        {"key": " 4N39D ", "label": " Economics "},
        {"key": "5DH8C", "label": "Economics"},
        {"key": "4N39D", "label": "Economics"},
        {"key": "", "label": "Missing code"},
        {"key": "INVALID", "label": None},
        None,
    ]
    payload = {
        "data": {
            "jobSearch": {
                "results": [
                    {"job": {"attributes": entries}},
                    None,
                    {"job": {"attributes": []}},
                ]
            }
        }
    }

    class Recording(StubFetcher):
        async def post(self, url, json_body, headers=None):
            assert headers is not None
            assert headers["indeed-co"] == "NL"
            assert "attributes { key label }" in json_body["query"]
            assert "limit: 100" in json_body["query"]
            assert json.dumps('data "scientist"') in json_body["query"]
            assert "filters:" not in json_body["query"]
            return await super().post(url, json_body, headers)

    fetcher = Recording({"apis.indeed.com": ok(json.dumps(payload))})
    assert asyncio.run(indeed.attributes(fetcher, 'data "scientist"', "netherlands")) == [
        {"key": "4N39D", "label": "Economics"},
        {"key": "5DH8C", "label": "Economics"},
    ]
    assert len(fetcher.requests) == 1
    for query, country in ((" ", "usa"), ("data", "unknown")):
        with pytest.raises(ValueError):
            asyncio.run(indeed.attributes(fetcher, query, country))
    assert len(fetcher.requests) == 1


def test_attribute_lookup_distinguishes_empty_results_from_failure(caplog):
    for payload, expected in (
        ({"data": {"jobSearch": {"results": []}}}, []),
        ({"data": {"jobSearch": {"results": [{"job": {"attributes": []}}]}}}, []),
        ({"data": None, "errors": [{"message": "unavailable"}]}, None),
        ({"data": {"jobSearch": {"results": {}}}}, None),
        ({"data": {"jobSearch": {"results": [{"job": {"attributes": [None]}}]}}}, None),
        (None, None),
    ):
        caplog.clear()
        fetcher = StubFetcher({"apis.indeed.com": ok(json.dumps(payload))})
        assert asyncio.run(indeed.attributes(fetcher, "data", "usa")) == expected
        assert bool(caplog.records) == (expected is None)
    for response in (ok("not json"), rate_limited()):
        fetcher = StubFetcher({"apis.indeed.com": response})
        assert asyncio.run(indeed.attributes(fetcher, "data", "usa")) is None
