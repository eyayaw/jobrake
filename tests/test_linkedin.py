"""LinkedIn guest-search parsing and pagination tests."""

import asyncio

import pytest
from fakes import StubFetcher, ok, rate_limited

from jobrake import linkedin
from jobrake.fetchkit import TokenBucket


@pytest.fixture
def unlimited(monkeypatch):
    """Replace the module limiter with one whose burst no test can exhaust."""
    monkeypatch.setattr(linkedin, "LIMITER", TokenBucket(capacity=10**9, refill_interval=1.0))


def linkedin_card(job_id, title="Economist", company="Acme"):
    return f"""
    <div class="base-search-card">
      <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/{job_id}?trk=x"></a>
      <span class="sr-only">{title}</span>
      <h4 class="base-search-card__subtitle"><a>{company}</a></h4>
      <div class="base-search-card__metadata">
        <span class="job-search-card__location">Seattle, WA</span>
        <time datetime="2026-08-01"></time>
      </div>
    </div>"""


def test_job_id_from_url():
    assert (
        linkedin.job_id("https://nl.linkedin.com/jobs/view/economist-at-acme-4433303524")
        == "4433303524"
    )
    assert linkedin.job_id("https://www.linkedin.com/jobs/view/4433303524/?trk=x") == "4433303524"
    assert linkedin.job_id("https://www.linkedin.com/jobs/view/111") == "111"
    assert linkedin.job_id("https://www.linkedin.com/jobs/search") == ""


def test_linkedin_parses_cards_and_dedups(unlimited):
    html = linkedin_card("111") + linkedin_card("222") + linkedin_card("111")
    fetcher = StubFetcher({"seeMoreJobPostings": ok(html)})
    jobs = asyncio.run(
        linkedin.search(fetcher, search_term="economist", location="Seattle", results_wanted=2)
    )
    assert [j["url"] for j in jobs] == [
        "https://www.linkedin.com/jobs/view/111",
        "https://www.linkedin.com/jobs/view/222",
    ]
    assert jobs[0]["id"] == "111"
    assert jobs[0]["title"] == "Economist"
    assert jobs[0]["company"] == "Acme"
    assert jobs[0]["location"] == "Seattle, WA"
    assert jobs[0]["date"] == "2026-08-01"


def test_linkedin_429_returns_partial(unlimited):
    fetcher = StubFetcher({"seeMoreJobPostings": rate_limited()})
    assert asyncio.run(linkedin.search(fetcher, search_term="x", location="Seattle")) == []


def test_every_request_takes_a_token(monkeypatch):
    acquired = []

    class Counting(TokenBucket):
        async def acquire(self):
            acquired.append(1)

    monkeypatch.setattr(linkedin, "LIMITER", Counting(capacity=10**9, refill_interval=1.0))
    detail = '<div class="show-more-less-html__markup"><p>x</p></div>'
    fetcher = StubFetcher(
        {"seeMoreJobPostings": ok(linkedin_card("111")), "/jobs/view/": ok(detail)}
    )
    asyncio.run(
        linkedin.search(
            fetcher, search_term="x", location="Seattle", results_wanted=1, fetch_description=True
        )
    )
    assert len(acquired) == len(fetcher.requests) == 2


def test_linkedin_fetch_description(unlimited):
    detail = '<div class="show-more-less-html__markup"><p>Great &amp; big role</p></div>'
    fetcher = StubFetcher(
        {"seeMoreJobPostings": ok(linkedin_card("111")), "/jobs/view/": ok(detail)}
    )
    jobs = asyncio.run(
        linkedin.search(
            fetcher, search_term="x", location="Seattle", results_wanted=1, fetch_description=True
        )
    )
    assert jobs[0]["description"] == "Great & big role"
