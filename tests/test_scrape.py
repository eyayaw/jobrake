"""The site contract, and how ``scrape`` routes to a site and checks its options."""

import asyncio
import inspect
from collections.abc import Iterable
from types import NoneType
from typing import Annotated, get_args, get_origin

import pytest
from fakes import StubFetcher, ok

from jobrake import scrape, sites
from jobrake.fetchkit import TokenBucket
from jobrake.sites import SITES
from jobrake.sites.linkedin import client

OPTION_TYPES = [str, int, bool, list[str], str | None, int | None, bool | None, list[str] | None]


def options_of(function, *positional):
    """
    Map each keyword option of a site function to the type inside its Annotated.

    The function takes the fetcher, then one annotated argument of each type
    in ``positional``, then only keyword options.
    """
    fetcher, *parameters = inspect.signature(function).parameters.values()
    assert fetcher.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    options = {}
    for index, parameter in enumerate(parameters):
        assert get_origin(parameter.annotation) is Annotated, parameter.name
        kind, help_text = get_args(parameter.annotation)
        assert help_text.strip(), parameter.name
        if index < len(positional):
            assert parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD, parameter.name
            assert kind == positional[index], parameter.name
            continue
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY, parameter.name
        assert kind in OPTION_TYPES, parameter.name
        # The CLI turns a boolean option into a flag that sets it.
        assert kind is not bool or parameter.default is False, parameter.name
        options[parameter.name] = kind
    return options


def search_options(module):
    return options_of(module.search)


def without_none(kind):
    members = get_args(kind)
    return (
        next(member for member in members if member is not NoneType)
        if NoneType in members
        else kind
    )


@pytest.mark.parametrize("site", SITES)
def test_a_site_meets_the_site_contract(site):
    module = SITES[site]
    assert (module.__doc__ or "").splitlines()[0]  # the CLI help
    for lookup in ("places", "companies", "attributes"):
        if hasattr(module, lookup):
            options_of(getattr(module, lookup), str)
    if hasattr(module, "postings"):
        options_of(module.postings, Iterable[str])
    options = search_options(module)
    # A name two sites share keeps one type, apart from accepting None.
    for other in SITES.values():
        for name, kind in search_options(other).items():
            if name in options:
                assert without_none(kind) == without_none(options[name]), name


@pytest.mark.parametrize(
    ("site", "kwargs", "error", "match"),
    [
        ("glassdoor", {}, ValueError, "glassdoor"),
        ("indeed", {}, TypeError, "indeed requires country. Its options are query, country"),
        ("indeed", {"country": "usa", "geoid": "1"}, TypeError, "indeed has no option geoid"),
        ("linkedin", {"location": "Seattle", "country": "usa"}, TypeError, "no option country"),
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
    with pytest.raises(TypeError, match="fakesite has no option location"):
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
