"""Indeed GraphQL parsing and pagination tests."""

import asyncio
import importlib
import json
import logging
import math
from urllib.parse import parse_qs, urlparse

import pytest
from fakes import PagedFetcher, StubFetcher, ok, rate_limited

from jobrake import Stopped
from jobrake.models import IDENTITY_FIELDS, SUMMARY_FIELDS
from jobrake.sites import indeed


def test_query_escapes_graphql_strings_as_json():
    tricky = 'key\\"quoted'
    first = indeed_payload(["a"], cursor='next\\"')
    fetcher = PagedFetcher([json.dumps(first), json.dumps(indeed_payload([]))])
    asyncio.run(
        indeed.search(
            fetcher,
            query='C:\\jobs "quoted"',
            country="usa",
            location='Brussels "center"',
            radius=0,
            company_ids=[tricky],
            attributes=[tricky],
        )
    )
    query, next_query = (body["query"] for body in fetcher.bodies)
    assert 'what: "C:\\\\jobs \\"quoted\\""' in query
    assert 'where: "Brussels \\"center\\"", radius: 0' in query
    assert 'field: "indeedEmployerKey", keys: ["key\\\\\\"quoted"]' in query
    assert 'field: "attributes", keys: ["key\\\\\\"quoted"]' in query
    assert 'cursor: "next\\\\\\""' in next_query
    assert "dateOnIndeed" not in query  # no age limit by default


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


def test_company_lookup_keeps_usable_keys_in_indeed_order():
    hits = [
        {"employerKey": " fe219df7f711aa73 ", "suggestion": " ABN AMRO "},
        {},
        {"employerKey": 123, "suggestion": "Invalid key"},
        {"employerKey": " ", "suggestion": "Blank key"},
        {"employerKey": "6495c5a19835b81b", "suggestion": None},
        {"employerKey": "6495c5a19835b81b", "suggestion": "Abn amro, bouwfonds"},
    ]
    fetcher = StubFetcher({"suggestions/company": ok(json.dumps(hits))})
    assert asyncio.run(indeed.companies(fetcher, " ABN & AMRO ", country="netherlands")) == [
        {"id": "fe219df7f711aa73", "name": "ABN AMRO"},
        {"id": "6495c5a19835b81b", "name": "Abn amro, bouwfonds"},
    ]
    params = parse_qs(urlparse(fetcher.requests[0]).query)
    assert params["query"] == ["ABN & AMRO"]
    assert params["country"] == ["NL"]
    for name, country, message in [
        (" ", "usa", "is blank"),
        ("ABN", "atlantis", "unknown Indeed country"),
    ]:
        with pytest.raises(ValueError, match=message):
            asyncio.run(indeed.companies(fetcher, name, country=country))
    assert len(fetcher.requests) == 1


def test_company_lookup_distinguishes_no_matches_from_failure():
    fetcher = StubFetcher({"suggestions/company": ok("[]")})
    assert asyncio.run(indeed.companies(fetcher, "ABN", country="netherlands")) == []
    for response in (ok("[{}]"), ok("{}"), ok("not JSON"), rate_limited()):
        fetcher = StubFetcher({"suggestions/company": response})
        with pytest.raises(Stopped, match="company"):
            asyncio.run(indeed.companies(fetcher, "ABN", country="netherlands"))


def test_places_lists_edition_suggestions():
    hits = [
        {"suggestion": "Boston, MA", "payload": {"locationType": "CITY", "population": 589141}},
        {},  # a malformed candidate is omitted, keeping its siblings
        {"suggestion": "   ", "payload": {"locationType": "CITY"}},
        {"suggestion": "Boston Common, MA", "payload": {"locationType": {"bad": 1}}},
        {"suggestion": "Boston Massacre Marker, MA", "payload": {"locationType": "MISC"}},
    ]
    fetcher = StubFetcher({"suggestions/location": ok(json.dumps(hits))})
    assert asyncio.run(indeed.places(fetcher, "boston", country="usa")) == [
        {"id": "Boston, MA", "name": "Boston, MA"},
        {"id": "Boston Common, MA", "name": "Boston Common, MA"},
        {"id": "Boston Massacre Marker, MA", "name": "Boston Massacre Marker, MA"},
    ]
    assert "country=US" in fetcher.requests[0]
    with pytest.raises(ValueError, match="country"):
        asyncio.run(indeed.places(fetcher, "boston", country="atlantis"))
    with pytest.raises(ValueError, match="blank"):
        asyncio.run(indeed.places(fetcher, "", country="usa"))
    assert len(fetcher.requests) == 1


def test_a_country_alias_selects_its_edition():
    for country, code, host in (
        ("usa", "US", "www"),
        ("United States", "US", "www"),
        ("uk", "GB", "uk"),
        ("netherlands", "NL", "nl"),
    ):
        fetcher = StubFetcher({"apis.indeed.com": ok(json.dumps(indeed_payload(["a"])))})
        (job,) = asyncio.run(indeed.search(fetcher, query="x", country=country))
        assert fetcher.headers[0]["indeed-co"] == code
        assert job["url"] == f"https://{host}.indeed.com/viewjob?jk=a"


def test_indeed_parses_and_paginates():
    pages = [indeed_payload(["a", "b"], cursor="next"), indeed_payload(["b", "c"])]

    fetcher = PagedFetcher([json.dumps(page) for page in pages])
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


def test_indeed_warns_when_its_result_cap_cuts_a_search_short(monkeypatch, caplog):
    search_module = importlib.import_module("jobrake.sites.indeed.search")
    page = ok(json.dumps(indeed_payload(["a", "b"])))
    for cap, warned in ((2, True), (3, False)):
        monkeypatch.setattr(search_module, "MAX_RESULTS", cap)
        caplog.clear()
        fetcher = StubFetcher({"apis.indeed.com": page})
        with caplog.at_level(logging.WARNING, logger="jobrake.sites.indeed"):
            jobs = asyncio.run(indeed.search(fetcher, query="x", country="usa", results=5))
        assert [job["id"] for job in jobs] == ["a", "b"]
        assert ("at most 2 results" in caplog.text) is warned


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
    ("company_ids", "age", "remote", "language", "attributes", "expected_keys"),
    [
        (None, 168, False, None, None, []),
        (None, None, False, None, [], []),
        ([" fe219df7f711aa73\n"], None, False, None, [" 3CQB7 "], ["3CQB7"]),
        (["fe219df7f711aa73"], 168, False, None, ["CF3CP", "6QC5F"], ["CF3CP", "6QC5F"]),
        (None, 168, True, "Iw", None, ["DSQF7"]),
        (None, None, True, None, [" DSQF7 "], ["DSQF7"]),
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
    company_ids, age, remote, language, attributes, expected_keys
):
    # Indeed binds the page size to its cursor and rejects a changed limit
    # with BAD_USER_INPUT, so every request in a chain asks for a full page.
    pages = [indeed_payload(["a", "b"], cursor="next"), indeed_payload(["b", "c", "d"])]

    fetcher = PagedFetcher([json.dumps(page) for page in pages])
    original_attributes = attributes.copy() if attributes is not None else None
    jobs = asyncio.run(
        indeed.search(
            fetcher,
            query="x",
            country="usa",
            results=3,
            company_ids=company_ids,
            max_age_hours=age,
            remote=remote,
            language=language,
            attributes=attributes,
            location="Seattle",
        )
    )
    queries = [body["query"] for body in fetcher.bodies]
    # The second page overlaps the first, the limit stays at 100, and the
    # final slice returns three unique jobs.
    assert [job["id"] for job in jobs] == ["a", "b", "c"]
    assert all('what: "x"' in query for query in queries)
    assert all("limit: 100" in query for query in queries)
    assert all("language" in query.split() for query in queries)
    for query in queries:
        assert ('field: "indeedEmployerKey"' in query) == bool(company_ids)
        assert ('keys: ["fe219df7f711aa73"]' in query) == bool(company_ids)
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
        if (company_ids or expected_keys or language) and age:
            assert "} }, { keyword:" in query
        if not company_ids and not expected_keys and language is None and age is None:
            assert "filters:" not in query
    assert len(queries) == 2
    assert attributes == original_attributes


def test_indeed_graphql_error_reports_the_indeed_message():
    rejected = {
        "data": None,
        "errors": [{"message": "BAD_USER_INPUT: Requested limit modified during pagination"}],
    }
    pages = [indeed_payload(["a"], cursor="next"), rejected]
    fetcher = PagedFetcher([json.dumps(page) for page in pages])
    with pytest.raises(Stopped, match=r"BAD_USER_INPUT.*Kept the 1 job collected") as stop:
        asyncio.run(indeed.search(fetcher, query="x", country="usa", results=10))
    assert [job["id"] for job in stop.value.partial] == ["a"]  # earlier pages survive


def test_indeed_returns_the_requested_number_of_results():
    fetcher = StubFetcher({"apis.indeed.com": ok(json.dumps(indeed_payload(["a", "b", "c"])))})
    jobs = asyncio.run(indeed.search(fetcher, query="x", country="usa", results=2))
    assert len(jobs) == 2


@pytest.mark.parametrize(
    "language", ["", " ", " en ", "e", "eng", "en-US", "en_US", "e1", "éñ", "en\n"]
)
def test_indeed_rejects_a_language_before_any_request(language):
    fetcher = StubFetcher({})
    with pytest.raises(ValueError, match="two ASCII letters"):
        asyncio.run(indeed.search(fetcher, query="x", country="usa", language=language))
    assert fetcher.requests == []


def test_indeed_failed_or_unreadable_response_stops_the_search():
    # An integer longer than Python reads raises ValueError, not JSONDecodeError.
    for response, message in ((rate_limited(), "HTTP 429"), (ok("9" * 5000), "cannot read")):
        fetcher = StubFetcher({"apis.indeed.com": response})
        with pytest.raises(Stopped, match=message) as stop:
            asyncio.run(indeed.search(fetcher, query="x", country="usa"))
        assert stop.value.partial == []


def test_indeed_skips_malformed_results_and_keeps_valid_siblings(caplog):
    payload = indeed_payload(["a", "b"])
    results = payload["data"]["jobSearch"]["results"]
    results[1:1] = [
        {"job": None},  # Indeed sent a null job
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

    fetcher = PagedFetcher([json.dumps(page) for page in pages])
    jobs = asyncio.run(indeed.search(fetcher, query="x", country="usa", results=10))
    assert [job["id"] for job in jobs] == ["b"]  # the cursor survives the bad page


@pytest.mark.parametrize(
    "job_search", [None, {"results": {}}, {"results": "x"}], ids=["null", "dict", "string"]
)
def test_indeed_malformed_later_page_keeps_collected_jobs(job_search):
    pages = [indeed_payload(["a"], cursor="next"), {"data": {"jobSearch": job_search}}]
    fetcher = PagedFetcher([json.dumps(page) for page in pages])
    # The message names the caught error.
    with pytest.raises(Stopped, match="TypeError") as stop:
        asyncio.run(indeed.search(fetcher, query="x", country="usa", results=10))
    assert [job["id"] for job in stop.value.partial] == ["a"]


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

    fetcher = PagedFetcher([json.dumps(page) for page in pages])
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
    fetcher = StubFetcher({"apis.indeed.com": ok(json.dumps(payload))})
    (parsed,) = asyncio.run(indeed.search(fetcher, query="x", country="usa"))
    return parsed


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

    fetcher = StubFetcher({"apis.indeed.com": ok(json.dumps(payload))})
    assert asyncio.run(indeed.attributes(fetcher, 'data "scientist"', country="netherlands")) == [
        {"id": "4N39D", "name": "Economics"},
        {"id": "5DH8C", "name": "Economics"},
    ]
    assert fetcher.headers[0]["indeed-co"] == "NL"
    graphql = fetcher.bodies[0]["query"]
    assert "attributes { key label }" in graphql
    assert "limit: 100" in graphql
    assert json.dumps('data "scientist"') in graphql
    assert "filters:" not in graphql
    assert len(fetcher.requests) == 1
    for query, country, message in (
        (" ", "usa", "is blank"),
        ("data", "unknown", "unknown Indeed country"),
    ):
        with pytest.raises(ValueError, match=message):
            asyncio.run(indeed.attributes(fetcher, query, country=country))
    assert len(fetcher.requests) == 1


def test_attribute_lookup_distinguishes_empty_results_from_failure():
    for payload, found in (
        ({"data": {"jobSearch": {"results": []}}}, True),
        ({"data": {"jobSearch": {"results": [{"job": {"attributes": []}}]}}}, True),
        ({"data": None, "errors": [{"message": "unavailable"}]}, False),
        ({"data": {"jobSearch": {"results": {}}}}, False),
        ({"data": {"jobSearch": {"results": [{"job": {"attributes": [None]}}]}}}, False),
        (None, False),
    ):
        fetcher = StubFetcher({"apis.indeed.com": ok(json.dumps(payload))})
        if found:
            assert asyncio.run(indeed.attributes(fetcher, "data", country="usa")) == []
        else:
            with pytest.raises(Stopped, match="attributes"):
                asyncio.run(indeed.attributes(fetcher, "data", country="usa"))
    for response in (ok("not json"), rate_limited()):
        fetcher = StubFetcher({"apis.indeed.com": response})
        with pytest.raises(Stopped, match="attribute"):
            asyncio.run(indeed.attributes(fetcher, "data", country="usa"))
