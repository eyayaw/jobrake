"""Dispatcher tests: site routing and fetcher lifecycle."""

import asyncio

import pytest
from fakes import StubFetcher, ok

from jobrake import scrape, sites
from jobrake.fetchkit import TokenBucket
from jobrake.sites.linkedin import client


@pytest.mark.parametrize(
    ("site", "missing"),
    [("glassdoor", "glassdoor"), ("indeed", "country"), ("linkedin", "location")],
)
def test_scrape_rejects_invalid_scope_before_opening_a_fetcher(site, missing, monkeypatch):
    def must_not_open():
        raise AssertionError("opened transport before validating arguments")

    monkeypatch.setattr(sites, "HttpxFetcher", must_not_open)
    with pytest.raises(ValueError, match=missing):
        asyncio.run(scrape(site, search_term="x"))


@pytest.mark.parametrize("hours_old", [0, -24])
def test_scrape_rejects_a_nonpositive_age_before_opening_a_fetcher(hours_old, monkeypatch):
    def must_not_open():
        raise AssertionError("opened transport before validating arguments")

    monkeypatch.setattr(sites, "HttpxFetcher", must_not_open)
    with pytest.raises(ValueError, match="hours_old"):
        asyncio.run(scrape("linkedin", search_term="x", location="Seattle", hours_old=hours_old))


def test_scrape_does_not_close_injected_fetcher():
    closed = []

    class Recording(StubFetcher):
        def __bool__(self):
            return False

        async def close(self):
            closed.append(True)

    fetcher = Recording({"seeMoreJobPostings": ok("")})
    asyncio.run(scrape("linkedin", search_term="x", location="Seattle", fetcher=fetcher))
    assert closed == []


def test_scrape_closes_its_default_fetcher(monkeypatch):
    closed = []

    class Recording(StubFetcher):
        async def close(self):
            closed.append(True)

    fetcher = Recording({"seeMoreJobPostings": ok("")})
    monkeypatch.setattr(sites, "HttpxFetcher", lambda: fetcher)

    asyncio.run(scrape("linkedin", search_term="x", location="Seattle"))

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
        asyncio.run(scrape("linkedin", search_term="x", location="Seattle"))
    assert closed == [True]
