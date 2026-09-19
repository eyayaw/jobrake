"""Site-routing and fetcher-lifecycle tests for ``scrape``."""

import asyncio
import logging

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
        ("indeed", {"country": "usa", "attributes": [" "]}, "attribute code"),
        ("indeed", {"country": "usa", "language": " "}, "language"),
        ("indeed", {"country": "usa", "language": "eng"}, "language"),
        ("indeed", {"country": "netherlands", "companies": [" "]}, "blank"),
        ("indeed", {"country": "netherlands", "companies": ["a", "b"]}, "one Indeed employer key"),
        ("linkedin", {}, "location"),
        ("linkedin", {"location": "   "}, "location"),
        ("linkedin", {"geoid": ""}, "geoid"),
        ("linkedin", {"location": "Seattle", "companies": ["Acme"]}, "company ID"),
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


@pytest.mark.parametrize(
    ("site", "kwargs", "ignored", "applied_by"),
    [
        ("linkedin", {"location": "Seattle", "remote": True}, "remote", "indeed"),
        ("linkedin", {"location": "Seattle", "attributes": ["3CQB7"]}, "attributes", "indeed"),
        ("indeed", {"country": "usa", "easy_apply": True}, "easy_apply", "linkedin"),
        ("indeed", {"country": "usa", "early_applicant": True}, "early_applicant", "linkedin"),
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
    assert f"{site} ignores {ignored}" in caplog.text
    assert f"Run the search on {applied_by}" in caplog.text


@pytest.mark.parametrize(
    ("site", "kwargs", "match"),
    [
        ("indeed", {"remote": "false"}, "remote"),
        ("indeed", {"language": ["en"]}, "language"),
        ("indeed", {"attributes": "3CQB7"}, "attributes"),
        ("linkedin", {"remote": 1}, "remote"),
        ("linkedin", {"easy_apply": "false"}, "easy_apply"),
        ("indeed", {"early_applicant": 1}, "early_applicant"),
        ("indeed", {"companies": "fe219df7f711aa73"}, "companies"),
        ("indeed", {"companies": [123]}, "company ID"),
        ("linkedin", {"companies": "1173"}, "companies"),
        ("linkedin", {"companies": [1173]}, "company ID"),
        ("linkedin", {"results": float("nan")}, "results"),
        ("linkedin", {"results": 2.5}, "results"),
        ("linkedin", {"results": True}, "results"),
        ("linkedin", {"radius": float("inf")}, "radius"),
        ("linkedin", {"radius": False}, "radius"),
        ("linkedin", {"max_age_hours": 1.5}, "max_age_hours"),
        ("linkedin", {"max_age_hours": True}, "max_age_hours"),
    ],
)
def test_scrape_rejects_invalid_argument_types(kwargs, match, monkeypatch, site):
    def must_not_open():
        raise AssertionError("opened transport before validating arguments")

    monkeypatch.setattr(sites, "HttpxFetcher", must_not_open)
    with pytest.raises(TypeError, match=match):
        asyncio.run(scrape(site, query="x", location="Seattle", country="usa", **kwargs))


def test_scrape_accepts_an_explicit_zero_radius(monkeypatch):
    monkeypatch.setattr(client, "LIMITER", TokenBucket(capacity=10**9, refill_interval=1.0))
    fetcher = StubFetcher({"seeMoreJobPostings": ok("")})
    asyncio.run(scrape("linkedin", query="x", location="Seattle", radius=0, fetcher=fetcher))
    assert len(fetcher.requests) == 1


@pytest.mark.parametrize(
    ("site", "companies", "remote", "easy_apply", "early_applicant", "language"),
    [
        ("linkedin", None, False, False, True, "not a code"),
        ("linkedin", ["1173", "2220078"], False, True, False, None),
        ("indeed", None, True, False, False, "EN"),
    ],
)
def test_scrape_passes_search_options(
    monkeypatch, site, companies, remote, easy_apply, early_applicant, language
):
    options = {}

    async def capture(fetcher, **kwargs):
        options.update(kwargs)
        return []

    monkeypatch.setattr(sites, "site_searchers", lambda: {site: capture})
    asyncio.run(
        scrape(
            site,
            query="x",
            country="usa",
            geoid="12345",
            companies=companies,
            remote=remote,
            language=language,
            attributes=["3CQB7", "6QC5F"],
            easy_apply=easy_apply,
            early_applicant=early_applicant,
            fetcher=StubFetcher({}),
        )
    )

    assert options["radius"] is None
    assert options["results"] == defaults.RESULTS
    assert options["max_age_hours"] == defaults.MAX_AGE_HOURS
    assert options["details"] is defaults.DETAILS
    assert options["cache"] is defaults.CACHE
    assert options["location"] is None
    assert options["geoid"] == "12345"
    assert options["companies"] == companies
    assert options["remote"] is remote
    assert options["language"] == language
    assert options["attributes"] == ["3CQB7", "6QC5F"]
    assert options["easy_apply"] is easy_apply
    assert options["early_applicant"] is early_applicant


def test_provider_searches_require_boolean_filters():
    fetcher = StubFetcher({})
    for search in sites.site_searchers().values():
        for name in ("remote", "easy_apply", "early_applicant"):
            for value in (None, 0, "false"):
                with pytest.raises(TypeError, match=f"{name} must be a boolean"):
                    asyncio.run(
                        search(
                            fetcher, query="x", location="Seattle", country="usa", **{name: value}
                        )
                    )
    assert fetcher.requests == []


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
