"""Indeed GraphQL parsing and pagination tests."""

import asyncio
import json
import logging

from fakes import StubFetcher, ok, rate_limited

from jobrake.sites import indeed


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
