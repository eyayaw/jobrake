"""The site contract, and how ``scrape`` routes to a site and checks its options."""

import asyncio
import inspect
from typing import Annotated

import pytest
from fakes import StubFetcher, ok
from hypothesis import given
from hypothesis import strategies as st

from jobrake import Stopped, check, cli, identify, scrape, sites
from jobrake.sites import SITES
from jobrake.utils import checked, site_options


@pytest.mark.parametrize("site", SITES)
def test_a_site_meets_the_site_contract(site):
    module = SITES[site]
    assert (module.__doc__ or "").splitlines()[0]  # the CLI help
    assert "search" in module.__all__
    assert set(module.__all__) <= set(cli.COMMANDS)  # the functions the CLI knows how to run
    if "postings" in module.__all__:
        assert callable(getattr(module, "card", None))  # postings' link reader, for identify
    for name in module.__all__:
        function = getattr(module, name)
        assert inspect.getdoc(function), name  # its command's CLI help
        assert inspect.iscoroutinefunction(function), name
        options = site_options(function)
        positional = [option for option, spec in options.items() if spec.positional]
        assert len(positional) == (name != "search"), name
        # Every exported function checks its arguments before any request, and takes its fetcher by
        # name as well as by position.
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
        ("linkedin", {"location": "Seattle", "country": "us"}, TypeError, "argument 'country'"),
        ("indeed", {"country": 5}, TypeError, "country must be a string, got 5"),
        ("indeed", {"country": "us", "remote": "false"}, TypeError, "remote must be a boolean"),
        ("linkedin", {"location": 5}, TypeError, "location must be a string or None"),
        ("linkedin", {"location": "Seattle", "results": True}, TypeError, "results must be an"),
        ("linkedin", {"location": "Seattle", "results": 2.5}, TypeError, "results must be an"),
        ("linkedin", {"location": "Seattle", "company_ids": "1173"}, TypeError, "list of strings"),
        ("linkedin", {"location": "Seattle", "company_ids": [1173]}, TypeError, "list of strings"),
        ("linkedin", {"location": "Seattle", "results": 0}, ValueError, r"results \(0\) must be"),
        ("indeed", {"country": "us", "radius": -1}, ValueError, "radius"),
        ("indeed", {"country": "us", "max_age_hours": 0}, ValueError, "max_age_hours"),
        (
            "indeed",
            {"country": " "},
            ValueError,
            "country is blank. Pass the ISO 3166-1 alpha-2 code",
        ),
        # The site validators raise the rows below, except the blank list entry, which
        # @checked rejects on every site.
        ("indeed", {"country": "atlantis"}, ValueError, "unknown Indeed country"),
        (
            "indeed",
            {"country": "us", "company_ids": [" "]},
            ValueError,
            "company_ids holds a blank entry",
        ),
        ("indeed", {"country": "us", "company_ids": ["a", "b"]}, ValueError, "one company ID"),
        ("linkedin", {}, ValueError, "location is required"),
        ("linkedin", {"location": "   "}, ValueError, "location is required"),
        ("linkedin", {"geoid": ""}, ValueError, "must use digits"),
        ("linkedin", {"location": "Seattle", "company_ids": ["Acme"]}, ValueError, "company ID"),
        ("linkedin", {"location": "Seattle", "company_ids": ["１２３"]}, ValueError, "company ID"),  # noqa: RUF001  fullwidth digits are the input under test
        ("workday", {"board": "https://example.com/jobs"}, ValueError, "not a Workday career site"),
        (
            "workday",
            {"board": "https://[/x"},
            ValueError,
            "not a Workday career site",
        ),  # urlsplit refuses
        (
            "academictransfer",
            {"vacancy_type": "phd"},
            ValueError,
            "unknown AcademicTransfer vacancy type 'phd'. "
            "Use one of scientific, non_scientific, all",
        ),
        (
            "aea",
            {"jel": ["Labor"]},
            ValueError,
            "unknown JOE JEL field 'Labor'. Use one of 00, A, B",
        ),
        ("inomics", {"category": ["Dean"]}, ValueError, "unknown INOMICS category 'Dean'"),
        ("inomics", {"jel": ["Y"]}, ValueError, "unknown INOMICS JEL field 'Y'. Use one of A, B"),
        # The slug INOMICS's search takes for a JEL field is not a value --jel accepts.
        ("inomics", {"jel": ["laweconomics"]}, ValueError, "unknown INOMICS JEL field"),
        ("inomics", {"country": "deu"}, ValueError, "not an ISO 3166-1 alpha-2 code"),
    ],
)
def test_check_and_scrape_reject_bad_options_before_any_request(site, kwargs, error, match):
    with pytest.raises(error, match=match):
        check(site, query="x", **kwargs)
    fetcher = StubFetcher({})
    with pytest.raises(error, match=match):
        asyncio.run(scrape(site, query="x", fetcher=fetcher, **kwargs))
    assert fetcher.requests == []


@pytest.mark.parametrize(
    ("link", "named"),
    [
        (
            "https://nl.linkedin.com/jobs/view/economist-at-acme-4449382178?trk=x",
            ("linkedin", "4449382178"),
        ),
        ("https://www.linkedin.com/comm/jobs/view/4449382178?trk=eml", ("linkedin", "4449382178")),
        (
            "https://www.linkedin.com/jobs/search/?currentJobId=4449382178",
            ("linkedin", "4449382178"),
        ),
        (
            "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/4449382178",
            ("linkedin", "4449382178"),
        ),
        (
            "https://nl.indeed.com/viewjob?jk=1a2b3c4d5e6f7a8b&from=serp",
            ("indeed", "1a2b3c4d5e6f7a8b"),
        ),
        (
            "https://www.indeed.com/jobs?q=economist&vjk=1a2b3c4d5e6f7a8b",
            ("indeed", "1a2b3c4d5e6f7a8b"),
        ),
        (
            "https://NVIDIA.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite"
            "/job/US-CA-Santa-Clara/Networking-Architect_JR1996377/?source=email",
            ("workday", "nvidia:JR1996377"),
        ),
        (
            "https://jobs.smartrecruiters.com/BoschGroup/744000158197889-product-expert?trk=x",
            ("smartrecruiters", "744000158197889"),
        ),
        (
            "https://jobs.smartrecruiters.com/Bosch Group/744000158197889",
            ("smartrecruiters", "744000158197889"),
        ),
    ],
)
def test_identify_names_the_site_and_id_a_search_gives(link, named):
    assert identify(link) == named


@pytest.mark.parametrize(
    "link",
    [
        "4449382178",  # a LinkedIn ID, but not a link
        "https://boards.greenhouse.io/airbnb/jobs/7649441",
        "https://www.indeed.com/viewjob",
        # A posting link carries neither credentials nor a port.
        "https://acme@www.indeed.com/viewjob?jk=1a2b3c4d5e6f7a8b",
        "https://www.indeed.com:8443/viewjob?jk=1a2b3c4d5e6f7a8b",
        "https://example.com/jobs/view/4449382178",
        "https://inomics.com/scholarship/postdoctoral-scholarship-1555359",
        # A posting ID holds digits 0-9, and \d also matches other scripts' digits.
        "https://www.stepstone.de/job/１４５６９０４２",  # noqa: RUF001  fullwidth digits are the input under test
        "https://jobs.smartrecruiters.com/BoschGroup/７４４０００１５８１９７８８９",  # noqa: RUF001  fullwidth digits are the input under test
    ],
)
def test_identify_gives_none_for_a_link_no_site_reads(link):
    assert identify(link) is None


@pytest.mark.parametrize(
    "site", [site for site, module in SITES.items() if hasattr(module, "card")]
)
def test_card_names_a_link_urlsplit_refuses_in_its_own_message(site):
    # urlsplit raises its own ValueError, "Invalid IPv6 URL", for an unbalanced bracket.
    with pytest.raises(ValueError, match=r"^'https://\[/job/1' is (not|neither) "):
        SITES[site].card("https://[/job/1")


@given(st.one_of(st.text(), st.text().map("https://".__add__)))
def test_identify_never_raises(text):
    identify(text)


@pytest.mark.parametrize("site", SITES)
def test_an_integer_option_beyond_float_range_reaches_the_first_request(site):
    # check accepts an integer beyond float range, so a search's own arithmetic must accept it too.
    options = site_options(SITES[site].search)
    board = "https://acme.wd1.myworkdayjobs.com/External" if site == "workday" else "acme"
    required = {"board": board, "country": "us", "location": "Seattle"}
    needed = {name: value for name, value in required.items() if name in options}
    for name in (name for name, option in options.items() if option.kind is int):
        fetcher = StubFetcher({})  # every request fails
        with pytest.raises(Stopped):
            asyncio.run(SITES[site].search(fetcher, **needed, **{name: 10**400}))
        assert fetcher.requests, name


def test_check_rejects_an_integer_too_long_for_a_request_to_carry():
    with pytest.raises(ValueError, match="radius has too many digits to send"):
        check("linkedin", query="x", location="Seattle", radius=-(10**5000))


def test_check_and_scrape_accept_an_explicit_zero_radius():
    check("linkedin", query="x", location="Seattle", radius=0)
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
    # An explicit None passes for an option that may be None.
    asyncio.run(scrape("fakesite", query="x", tags=None, fetcher=StubFetcher({})))
    assert fake_site.calls[-1]["tags"] is None


def test_scrape_closes_only_the_fetcher_it_created(fake_site, monkeypatch):
    given = StubFetcher({})
    asyncio.run(scrape("fakesite", query="x", fetcher=given))
    created = StubFetcher({})
    monkeypatch.setattr(sites, "HttpxFetcher", lambda: created)
    asyncio.run(scrape("fakesite", query="x"))
    assert (given.closed, created.closed) == (0, 1)


def test_scrape_closes_its_fetcher_after_a_search_failure(fake_site, monkeypatch):
    async def failing(fetcher, *, query: Annotated[str, "job title or keywords"]):
        raise RuntimeError("interrupted")

    created = StubFetcher({})
    monkeypatch.setattr(sites, "HttpxFetcher", lambda: created)
    monkeypatch.setattr(fake_site, "search", failing)
    with pytest.raises(RuntimeError):
        asyncio.run(scrape("fakesite", query="x"))
    assert created.closed == 1
