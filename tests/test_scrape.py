"""Site-routing and fetcher-lifecycle tests for ``scrape``."""

import asyncio

import pytest
from fakes import StubFetcher, ok

from jobrake import defaults, scrape, sites
from jobrake.fetchkit import TokenBucket
from jobrake.sites.linkedin import client


@pytest.mark.parametrize(
    ("site", "kwargs", "match"),
    [
        ("glassdoor", {}, "glassdoor"),
        ("indeed", {}, "country"),
        ("linkedin", {}, "location"),
        ("linkedin", {"location": "   "}, "location"),
        ("linkedin", {"location": "Seattle", "results": 0}, "results"),
        ("linkedin", {"location": "Seattle", "radius": -1}, "radius"),
        ("linkedin", {"location": "Seattle", "max_age_hours": 0}, "max_age_hours"),
    ],
)
def test_scrape_rejects_bad_arguments_before_opening_a_fetcher(site, kwargs, match, monkeypatch):
    def must_not_open():
        raise AssertionError("opened transport before validating arguments")

    monkeypatch.setattr(sites, "HttpxFetcher", must_not_open)
    with pytest.raises(ValueError, match=match):
        asyncio.run(scrape(site, query="x", **kwargs))


def test_scrape_accepts_an_explicit_zero_radius(monkeypatch):
    monkeypatch.setattr(client, "LIMITER", TokenBucket(capacity=10**9, refill_interval=1.0))
    fetcher = StubFetcher({"seeMoreJobPostings": ok("")})
    asyncio.run(scrape("linkedin", query="x", location="Seattle", radius=0, fetcher=fetcher))
    assert len(fetcher.requests) == 1


def test_scrape_passes_shared_defaults(monkeypatch):
    options = {}

    async def capture(fetcher, **kwargs):
        options.update(kwargs)
        return []

    monkeypatch.setattr(sites, "site_searchers", lambda: {"linkedin": capture})
    asyncio.run(scrape("linkedin", query="x", location="Seattle", fetcher=StubFetcher({})))

    assert options["radius"] is defaults.LINKEDIN_RADIUS
    assert options["results"] == defaults.RESULTS
    assert options["max_age_hours"] == defaults.MAX_AGE_HOURS
    assert options["details"] is defaults.DETAILS
    assert options["cache"] is defaults.CACHE


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
