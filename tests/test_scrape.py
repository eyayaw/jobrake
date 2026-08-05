"""Dispatcher tests: site routing and fetcher lifecycle."""

import asyncio

from fakes import StubFetcher, ok

from jobrake import scrape


def test_scrape_rejects_unknown_site():
    try:
        asyncio.run(scrape("glassdoor", search_term="x"))
    except ValueError as e:
        assert "glassdoor" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_scrape_does_not_close_injected_fetcher():
    closed = []

    class Recording(StubFetcher):
        async def close(self):
            closed.append(True)

    fetcher = Recording({"seeMoreJobPostings": ok("")})
    asyncio.run(scrape("linkedin", search_term="x", fetcher=fetcher))
    assert closed == []
