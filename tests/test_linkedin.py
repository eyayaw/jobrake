"""LinkedIn guest-search parsing and pagination tests."""

import asyncio

from fakes import StubFetcher, ok, rate_limited

from jobrake import linkedin


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


def test_linkedin_parses_cards_and_dedups(monkeypatch):
    monkeypatch.setattr(linkedin, "PAGE_DELAY", 0)
    html = linkedin_card("111") + linkedin_card("222") + linkedin_card("111")
    fetcher = StubFetcher({"seeMoreJobPostings": ok(html)})
    jobs = asyncio.run(linkedin.search(fetcher, search_term="economist", results_wanted=2))
    assert [j["url"] for j in jobs] == [
        "https://www.linkedin.com/jobs/view/111",
        "https://www.linkedin.com/jobs/view/222",
    ]
    assert jobs[0]["title"] == "Economist"
    assert jobs[0]["company"] == "Acme"
    assert jobs[0]["location"] == "Seattle, WA"
    assert jobs[0]["date"] == "2026-08-01"


def test_linkedin_429_returns_partial(monkeypatch):
    monkeypatch.setattr(linkedin, "PAGE_DELAY", 0)
    fetcher = StubFetcher({"seeMoreJobPostings": rate_limited()})
    assert asyncio.run(linkedin.search(fetcher, search_term="x")) == []


def test_linkedin_fetch_description(monkeypatch):
    monkeypatch.setattr(linkedin, "PAGE_DELAY", 0)
    detail = '<div class="show-more-less-html__markup"><p>Great &amp; big role</p></div>'
    fetcher = StubFetcher(
        {"seeMoreJobPostings": ok(linkedin_card("111")), "/jobs/view/": ok(detail)}
    )
    jobs = asyncio.run(
        linkedin.search(fetcher, search_term="x", results_wanted=1, fetch_description=True)
    )
    assert jobs[0]["description"] == "Great & big role"
