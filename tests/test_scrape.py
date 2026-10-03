"""Site-routing and fetcher-lifecycle tests for ``scrape``."""

import asyncio
import inspect
import logging

import pytest
from fakes import StubFetcher, ok

from jobrake import scrape, sites, utils
from jobrake.fetchkit import TokenBucket
from jobrake.sites.linkedin import client


@pytest.mark.parametrize(
    ("site", "kwargs", "error", "match"),
    [
        ("glassdoor", {}, ValueError, "glassdoor"),
        # Each provider's search owns its own argument checks. These are the
        # ones scrape's defaults reach, plus one applied filter per provider.
        ("indeed", {}, ValueError, "country is required"),
        ("indeed", {"country": 5}, TypeError, "country"),
        ("indeed", {"country": "usa", "employer_key": " "}, ValueError, "employer key is blank"),
        ("indeed", {"country": "usa", "remote": "false"}, TypeError, "remote must be a boolean"),
        ("linkedin", {}, ValueError, "location is required"),
        ("linkedin", {"geoid": True}, ValueError, "location is required"),
        ("linkedin", {"location": 5}, TypeError, "location"),
        ("linkedin", {"geoid": 102011674}, TypeError, "geoid"),
        ("linkedin", {"geoid": " "}, ValueError, "geoid is blank"),
        ("linkedin", {"location": "Seattle", "company_ids": ["Acme"]}, ValueError, "company ID"),
        ("linkedin", {"location": "Seattle", "easy_apply": "false"}, TypeError, "easy_apply must"),
        ("linkedin", {"location": "Seattle", "early_applicant": 1}, TypeError, "early_applicant"),
    ],
)
def test_scrape_rejects_bad_arguments_before_any_request(site, kwargs, error, match):
    fetcher = StubFetcher({})
    with pytest.raises(error, match=match):
        asyncio.run(scrape(site, query="x", fetcher=fetcher, **kwargs))
    assert fetcher.requests == []


@pytest.mark.parametrize(
    ("site", "kwargs", "ignored", "applied_by"),
    [
        # One case per filter. The wrong-typed values show an ignored filter goes unchecked.
        ("linkedin", {"location": "Seattle", "remote": "yes"}, "remote", "indeed"),
        ("linkedin", {"location": "Seattle", "language": "not a code"}, "language", "indeed"),
        ("linkedin", {"location": "Seattle", "attributes": ["3CQB7"]}, "attributes", "indeed"),
        ("linkedin", {"location": "Seattle", "employer_key": "fe21"}, "employer_key", "indeed"),
        ("indeed", {"country": "usa", "company_ids": ["1173"]}, "company_ids", "linkedin"),
        ("indeed", {"country": "usa", "geoid": "102011674"}, "geoid", "linkedin"),
        ("indeed", {"country": "usa", "easy_apply": True}, "easy_apply", "linkedin"),
        ("indeed", {"country": "usa", "early_applicant": 1}, "early_applicant", "linkedin"),
    ],
)
def test_a_filter_the_provider_cannot_apply_is_ignored_with_a_warning(
    site, kwargs, ignored, applied_by, caplog
):
    fetcher = StubFetcher({})
    with caplog.at_level(logging.WARNING, logger="jobrake.utils"):
        jobs = asyncio.run(scrape(site, query="x", fetcher=fetcher, **kwargs))

    assert jobs == []
    assert fetcher.requests, "an unsupported filter stopped the search"
    assert caplog.text.count(f"{site} ignores {ignored}") == 1
    assert f"Run the search on {applied_by}" in caplog.text


def test_the_filter_checks_reject_an_unknown_filter_or_site():
    with pytest.raises(KeyError, match="salary"):
        utils.check_filters("indeed", salary=True)
    # An unknown site matches no row, which would pass every filter unchecked.
    with pytest.raises(ValueError, match="glassdoor"):
        utils.check_filters("glassdoor", remote="nonsense")


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("results", float("nan")),
        ("results", 2.5),
        ("results", True),
        ("radius", float("inf")),
        ("radius", False),
        ("max_age_hours", 1.5),
        ("max_age_hours", True),
    ],
)
def test_numeric_options_reject_non_integers(name, value):
    with pytest.raises(TypeError, match=name):
        utils.check_bounds(**{name: value})


def test_scrape_accepts_an_explicit_zero_radius(monkeypatch):
    monkeypatch.setattr(client, "LIMITER", TokenBucket(capacity=10**9, refill_interval=1.0))
    fetcher = StubFetcher({"seeMoreJobPostings": ok("")})
    asyncio.run(scrape("linkedin", query="x", location="Seattle", radius=0, fetcher=fetcher))
    assert len(fetcher.requests) == 1


def test_scrape_forwards_every_search_option(monkeypatch):
    received = {}

    async def capture(fetcher, **options):
        received.update(options)
        return []

    monkeypatch.setattr(sites, "site_searchers", lambda: {"stub": capture})
    given = {
        "query": "x",
        "location": "Seattle",
        "country": "usa",
        "radius": 5,
        "results": 3,
        "max_age_hours": 24,
        "details": True,
        "cache": False,
        "geoid": "12345",
        "company_ids": ["1173"],
        "employer_key": "fe219df7f711aa73",
        "remote": True,
        "language": "en",
        "attributes": ["3CQB7"],
        "easy_apply": True,
        "early_applicant": True,
    }
    # A new scrape parameter must join this dict, which then proves it is forwarded.
    assert given.keys() == inspect.signature(scrape).parameters.keys() - {"site", "fetcher"}
    asyncio.run(scrape("stub", fetcher=StubFetcher({}), **given))
    assert received == given


def test_scrape_does_not_close_injected_fetcher():
    closed = []

    class Recording(StubFetcher):
        def __bool__(self):
            return False

        async def close(self):
            closed.append(True)

    fetcher = Recording({"seeMoreJobPostings": ok("")})
    asyncio.run(scrape("linkedin", query="x", location="Seattle", fetcher=fetcher))
    assert closed == []


def test_scrape_closes_its_default_fetcher(monkeypatch):
    closed = []

    class Recording(StubFetcher):
        async def close(self):
            closed.append(True)

    fetcher = Recording({"seeMoreJobPostings": ok("")})
    monkeypatch.setattr(sites, "HttpxFetcher", lambda: fetcher)

    asyncio.run(scrape("linkedin", query="x", location="Seattle"))

    assert closed == [True]


def test_scrape_closes_its_default_fetcher_after_a_search_failure(monkeypatch):
    closed = []

    class Dying(StubFetcher):
        async def fetch(self, url, headers=None):
            raise RuntimeError("interrupted")

        async def close(self):
            closed.append(True)

    monkeypatch.setattr(sites, "HttpxFetcher", lambda: Dying({}))
    monkeypatch.setattr(client, "LIMITER", TokenBucket(capacity=10**9, refill_interval=1.0))
    with pytest.raises(RuntimeError):
        asyncio.run(scrape("linkedin", query="x", location="Seattle"))
    assert closed == [True]
