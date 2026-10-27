"""The site contract, and how ``scrape`` routes to a site and checks its options."""

import asyncio
from typing import Annotated

import pytest
from fakes import StubFetcher, ok

from jobrake import scrape, sites
from jobrake.fetchkit import TokenBucket
from jobrake.sites import SITES
from jobrake.sites.linkedin import client
from jobrake.utils import checked, site_options

EXPORTS = {"search", "places", "companies", "attributes", "postings"}


@pytest.mark.parametrize("site", SITES)
def test_a_site_meets_the_site_contract(site):
    module = SITES[site]
    assert (module.__doc__ or "").splitlines()[0]  # the CLI help
    assert "search" in module.__all__
    assert set(module.__all__) <= EXPORTS  # the functions the CLI knows how to run
    for name in module.__all__:
        function = getattr(module, name)
        options = site_options(function)
        positional = [option for option, spec in options.items() if spec.positional]
        assert len(positional) == (name != "search"), name
        # Every exported function checks its arguments before any request, and
        # takes its fetcher by name as well as by position.
        fetcher = StubFetcher({})
        text = {option: ["x"] if name == "postings" else "x" for option in positional}
        with pytest.raises(TypeError, match=f"^{site}: "):
            asyncio.run(function(fetcher=fetcher, **text, bogus=1))
        assert fetcher.requests == []
    # A name two sites share keeps one type, apart from accepting None.
    kinds = {name: option.kind for name, option in site_options(module.search).items()}
    for other in SITES.values():
        for name, option in site_options(other.search).items():
            assert kinds.get(name, option.kind) == option.kind, name


async def unannotated(fetcher, *, query: str): ...


async def floating(fetcher, *, ratio: Annotated[float, "a ratio"]): ...


async def flag_on(fetcher, *, strict: Annotated[bool, "strict parsing"] = True): ...


async def either(fetcher, *, key: Annotated[str | int | None, "a key"] = None): ...


@pytest.mark.parametrize(
    ("function", "match"),
    [
        (unannotated, "annotate query as Annotated"),
        (floating, "ratio is <class 'float'>. Use str, int, bool, or list"),
        (flag_on, "the boolean option strict must default to False"),
        (either, r"key is str \| int \| None. Use str, int, bool, or list"),
    ],
)
def test_a_site_function_the_cli_cannot_build_fails_when_decorated(function, match):
    with pytest.raises(TypeError, match=f"test_scrape.{function.__name__}: {match}"):
        checked(function)


@pytest.mark.parametrize(
    ("site", "kwargs", "error", "match"),
    [
        ("glassdoor", {}, ValueError, "glassdoor"),
        ("indeed", {}, TypeError, r"indeed: missing .* 'country'. Its options are query, country"),
        ("indeed", {"country": "usa", "geoid": "1"}, TypeError, r"indeed: .* argument 'geoid'"),
        ("linkedin", {"location": "Seattle", "country": "usa"}, TypeError, "argument 'country'"),
        ("indeed", {"country": 5}, TypeError, "country must be a string, got 5"),
        ("indeed", {"country": "usa", "remote": "false"}, TypeError, "remote must be a boolean"),
        ("linkedin", {"location": 5}, TypeError, "location must be a string or None"),
        ("linkedin", {"location": "Seattle", "results": True}, TypeError, "results must be an"),
        ("linkedin", {"location": "Seattle", "results": 2.5}, TypeError, "results must be an"),
        ("linkedin", {"location": "Seattle", "company_ids": "1173"}, TypeError, "list of strings"),
        ("linkedin", {"location": "Seattle", "company_ids": [1173]}, TypeError, "list of strings"),
        ("linkedin", {"location": "Seattle", "results": 0}, ValueError, r"results \(0\) must be"),
        ("indeed", {"country": "usa", "radius": -1}, ValueError, "radius"),
        ("indeed", {"country": "usa", "max_age_hours": 0}, ValueError, "max_age_hours"),
        # The checks each site makes of the values it accepts.
        ("indeed", {"country": "atlantis"}, ValueError, "unknown Indeed country"),
        ("indeed", {"country": "usa", "company_ids": [" "]}, ValueError, "company ID is blank"),
        ("indeed", {"country": "usa", "company_ids": ["a", "b"]}, ValueError, "one company ID"),
        ("linkedin", {}, ValueError, "location is required"),
        ("linkedin", {"geoid": "Amsterdam"}, ValueError, "must use digits"),
        ("linkedin", {"location": "Seattle", "company_ids": ["Acme"]}, ValueError, "company ID"),
    ],
)
def test_scrape_rejects_bad_options_before_any_request(site, kwargs, error, match):
    fetcher = StubFetcher({})
    with pytest.raises(error, match=match):
        asyncio.run(scrape(site, query="x", fetcher=fetcher, **kwargs))
    assert fetcher.requests == []


def test_scrape_accepts_an_explicit_zero_radius(monkeypatch):
    monkeypatch.setattr(client, "LIMITER", TokenBucket(capacity=10**9, refill_interval=1.0))
    fetcher = StubFetcher({"seeMoreJobPostings": ok("")})
    asyncio.run(scrape("linkedin", query="x", location="Seattle", radius=0, fetcher=fetcher))
    assert len(fetcher.requests) == 1
    assert "distance=0" in fetcher.requests[0]


def test_a_registered_site_needs_no_change_to_scrape(fake_site):
    jobs = asyncio.run(
        scrape("fakesite", query="x", board="acme", tags=["a"], results=2, fetcher=StubFetcher({}))
    )
    assert [job["site"] for job in jobs] == ["fakesite", "fakesite"]
    # Options the caller leaves out keep the site's own defaults.
    assert fake_site.calls == [
        {"query": "x", "board": "acme", "results": 2, "remote": False, "tags": ["a"]}
    ]
    with pytest.raises(TypeError, match=r"fakesite: .* argument 'location'"):
        asyncio.run(scrape("fakesite", query="x", location="Seattle"))
    with pytest.raises(TypeError, match="tags must be a list of strings or None"):
        asyncio.run(scrape("fakesite", query="x", tags="a"))
    assert len(fake_site.calls) == 1


class Recording(StubFetcher):
    closed = 0

    async def close(self):
        self.closed += 1


def test_scrape_closes_only_the_fetcher_it_created(fake_site, monkeypatch):
    given = Recording({})
    asyncio.run(scrape("fakesite", query="x", fetcher=given))
    created = Recording({})
    monkeypatch.setattr(sites, "HttpxFetcher", lambda: created)
    asyncio.run(scrape("fakesite", query="x"))
    assert (given.closed, created.closed) == (0, 1)


def test_scrape_closes_its_fetcher_after_a_search_failure(fake_site, monkeypatch):
    async def failing(fetcher, *, query: Annotated[str, "job title or keywords"]):
        raise RuntimeError("interrupted")

    created = Recording({})
    monkeypatch.setattr(sites, "HttpxFetcher", lambda: created)
    monkeypatch.setattr(fake_site, "search", failing)
    with pytest.raises(RuntimeError):
        asyncio.run(scrape("fakesite", query="x"))
    assert created.closed == 1
