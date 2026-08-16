"""LinkedIn guest-search parsing and pagination tests."""

import asyncio
import json
import logging

import pytest
from fakes import StubFetcher, not_found, ok, rate_limited

from jobrake.cache import PostingCache
from jobrake.fetchkit import TokenBucket
from jobrake.models import JOB_FIELDS
from jobrake.sites import linkedin
from jobrake.sites.linkedin import client
from jobrake.sites.linkedin.postings import FRAGMENT_URL


@pytest.fixture
def unlimited(monkeypatch):
    """Replace the module limiter with one whose burst no test can exhaust."""
    monkeypatch.setattr(client, "LIMITER", TokenBucket(capacity=10**9, refill_interval=1.0))


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


def test_linkedin_parses_cards_and_dedups_by_posting_id(unlimited):
    html = (
        linkedin_card("role-111")
        + linkedin_card("222")
        + linkedin_card("other-111")
        + linkedin_card("search")
    )
    fetcher = StubFetcher({"seeMoreJobPostings": ok(html)})
    jobs = asyncio.run(
        linkedin.search(fetcher, search_term="economist", location="Seattle", results_wanted=3)
    )
    assert [j["url"] for j in jobs] == [
        "https://www.linkedin.com/jobs/view/role-111",
        "https://www.linkedin.com/jobs/view/222",
    ]
    assert jobs[0]["id"] == "111"
    assert jobs[0]["title"] == "Economist"
    assert jobs[0]["company"] == "Acme"
    assert jobs[0]["location"] == "Seattle, WA"
    assert jobs[0]["date"] == "2026-08-01"


def test_pagination_advances_by_raw_page_size(unlimited):
    pages = [
        linkedin_card("111") + linkedin_card("222"),
        linkedin_card("222") + linkedin_card("333"),
        linkedin_card("444"),
    ]

    class Paged(StubFetcher):
        async def fetch(self, url, headers=None):
            self.requests.append(url)
            return ok(pages[len(self.requests) - 1])

    fetcher = Paged({})
    jobs = asyncio.run(
        linkedin.search(fetcher, search_term="x", location="Seattle", results_wanted=4)
    )

    assert [job["id"] for job in jobs] == ["111", "222", "333", "444"]
    assert "start=4" in fetcher.requests[2]


def test_linkedin_429_retries_once_then_recovers(unlimited, monkeypatch):
    monkeypatch.setattr(client, "RETRY_DELAY", 0)

    class FlakyOnce(StubFetcher):
        async def fetch(self, url, headers=None):
            if not self.requests:
                self.requests.append(url)
                return rate_limited()
            return await super().fetch(url, headers)

    fetcher = FlakyOnce({"seeMoreJobPostings": ok(linkedin_card("111"))})
    jobs = asyncio.run(
        linkedin.search(fetcher, search_term="x", location="Seattle", results_wanted=1)
    )
    assert [j["id"] for j in jobs] == ["111"]
    assert len(fetcher.requests) == 2


def test_linkedin_persistent_429_returns_partial(unlimited, monkeypatch):
    monkeypatch.setattr(client, "RETRY_DELAY", 0)
    fetcher = StubFetcher({"seeMoreJobPostings": rate_limited()})
    assert asyncio.run(linkedin.search(fetcher, search_term="x", location="Seattle")) == []
    assert len(fetcher.requests) == 2  # the one retry, then give up


def test_warns_on_empty_first_page(unlimited, caplog):
    fetcher = StubFetcher({"seeMoreJobPostings": ok("<!DOCTYPE html>\n<!---->")})
    with caplog.at_level(logging.WARNING, logger="jobrake.sites.linkedin"):
        jobs = asyncio.run(linkedin.search(fetcher, search_term="x", location="Amsterdam"))
    assert jobs == []
    assert any("location" in record.message for record in caplog.records)


def test_no_warning_when_pagination_simply_ends(unlimited, caplog):
    fetcher = StubFetcher({"seeMoreJobPostings": ok(linkedin_card("111"))})
    with caplog.at_level(logging.WARNING, logger="jobrake.sites.linkedin"):
        jobs = asyncio.run(
            linkedin.search(fetcher, search_term="x", location="Seattle", results_wanted=5)
        )
    assert [j["id"] for j in jobs] == ["111"]  # second page dedups to empty: normal end
    assert caplog.records == []


def test_every_request_takes_a_token(monkeypatch):
    acquired = []

    class Counting(TokenBucket):
        async def acquire(self):
            acquired.append(1)

    monkeypatch.setattr(client, "LIMITER", Counting(capacity=10**9, refill_interval=1.0))
    fetcher = StubFetcher(
        {"seeMoreJobPostings": ok(linkedin_card("111")), "jobs/view/111": ok(job_page())}
    )
    asyncio.run(
        linkedin.search(fetcher, search_term="x", location="Seattle", results_wanted=1, detail=True)
    )
    assert len(acquired) == len(fetcher.requests) == 2


def test_search_detail_hydrates_from_the_canonical_page(unlimited):
    fetcher = StubFetcher(
        {"seeMoreJobPostings": ok(linkedin_card("111")), "jobs/view/111": ok(job_page())}
    )
    jobs = asyncio.run(
        linkedin.search(fetcher, search_term="x", location="Seattle", results_wanted=1, detail=True)
    )
    assert jobs[0]["description"] == "Great & big role"
    assert jobs[0]["employment_type"] == "full_time"
    assert jobs[0]["applicants"] == 200
    assert jobs[0]["title"] == "Economist"  # summary fields survive the merge


def test_search_keeps_the_summary_when_the_posting_is_gone(unlimited):
    fetcher = StubFetcher(
        {"seeMoreJobPostings": ok(linkedin_card("111")), "jobs/view/111": not_found()}
    )
    jobs = asyncio.run(
        linkedin.search(fetcher, search_term="x", location="Seattle", results_wanted=1, detail=True)
    )
    assert jobs[0]["title"] == "Economist"
    assert jobs[0]["description"] == ""


def test_search_reruns_only_fetch_unseen_postings(unlimited):
    responses = {"seeMoreJobPostings": ok(linkedin_card("111")), "jobs/view/111": ok(job_page())}
    jobs = asyncio.run(
        linkedin.search(
            StubFetcher(responses),
            search_term="x",
            location="Seattle",
            results_wanted=1,
            detail=True,
        )
    )
    rerun_fetcher = StubFetcher(responses)
    rerun = asyncio.run(
        linkedin.search(
            rerun_fetcher,
            search_term="x",
            location="Seattle",
            results_wanted=1,
            detail=True,
        )
    )
    assert jobs[0]["description"] == rerun[0]["description"] == "Great & big role"
    assert [url for url in rerun_fetcher.requests if "seeMoreJobPostings" not in url] == []


CANONICAL = "https://nl.linkedin.com/jobs/view/economist-at-acme-111"


def job_page(apply="offsite", applicants="Over 200 applicants", **overrides):
    posting = {
        "@type": "JobPosting",
        "description": "&lt;p&gt;Great &amp;amp; big role&lt;/p&gt;",
        "employmentType": "FULL_TIME",
        "datePosted": "2026-08-05T08:04:27.000Z",
        "validThrough": "2026-09-04T08:04:27.000Z",
        "hiringOrganization": {"sameAs": "https://nl.linkedin.com/company/acme"},
        "jobLocation": {"address": {"addressCountry": "NL"}, "latitude": 52.37},
    } | overrides
    button = (
        f'<button data-tracking-control-name="public_jobs_apply-link-{apply}"></button>'
        if apply
        else ""
    )
    return f"""
    <html><script type="application/ld+json">{json.dumps(posting)}</script>
    {button}
    <figcaption class="num-applicants__caption">{applicants}</figcaption></html>"""


def test_parse_posting_omits_what_it_cannot_extract():
    fields = linkedin.parse_posting(job_page())
    assert fields["description"] == "Great & big role"  # unescaped, then de-tagged
    assert fields["employment_type"] == "full_time"  # unified across sites
    assert fields["posted_at"] == "2026-08-05T08:04:27.000Z"  # timestamps kept whole
    assert fields["expires_at"] == "2026-09-04T08:04:27.000Z"
    assert fields["country_code"] == "NL"
    assert fields["applicants"] == 200
    # the posting has no salary and no experience: the keys are absent
    assert "salary_min" not in fields
    assert "experience_months" not in fields


def test_parse_posting_speaks_the_model_vocabulary():
    page = job_page(
        baseSalary={
            "currency": "USD",
            "value": {"minValue": 105000, "maxValue": 135000, "unitText": "YEAR"},
        },
        experienceRequirements={"monthsOfExperience": 36},
        educationRequirements={"credentialCategory": "bachelor degree"},
        jobLocation={
            "address": {"addressLocality": "Delft", "addressRegion": "ZH", "addressCountry": "NL"}
        },
    )
    fields = linkedin.parse_posting(page)
    # every key a parser can emit is a model field, so merging can never raise
    assert set(fields) <= set(JOB_FIELDS)
    assert (fields["salary_min"], fields["salary_max"]) == (105000, 135000)
    assert (fields["salary_currency"], fields["salary_period"]) == ("USD", "YEAR")
    assert (fields["city"], fields["region"], fields["country_code"]) == ("Delft", "ZH", "NL")
    assert fields["experience_months"] == 36


def test_parse_posting_reads_the_apply_kind():
    assert linkedin.parse_posting(job_page())["apply_type"] == "offsite"
    assert linkedin.parse_posting(job_page(apply="onsite"))["apply_type"] == "onsite"
    # any value the page uses, not only the two we have seen
    assert linkedin.parse_posting(job_page(apply="whatevernext"))["apply_type"] == "whatevernext"
    assert "apply_type" not in linkedin.parse_posting(job_page(apply=None))


def test_applicant_count_ignores_the_prose_around_it():
    for caption, expected in (  # every form seen across seven locales
        ("Be among the first 25 applicants", 25),
        ("Over 200 applicants", 200),
        ("114 applicants", 114),
        ("Wees een van de eerste 25 sollicitanten", 25),  # the prose is localized
        ("applicants", None),
    ):
        fields = linkedin.parse_posting(job_page(applicants=caption))
        assert fields.get("applicants") == expected


def test_parse_posting_survives_schema_variants():
    # schema.org allows a bare string or a list where an object is typical
    page = job_page(
        experienceRequirements="3 years", jobLocation=[{"address": {"addressCountry": "DE"}}]
    )
    fields = linkedin.parse_posting(page)
    assert fields["country_code"] == "DE"
    assert "experience_months" not in fields
    assert linkedin.parse_posting("<html><body>signup wall</body></html>") == {}


def blockless_page():
    # A country-level posting: a real job page, localized, no schema.org block.
    return """
    <html><div class="show-more-less-html__markup">Great &amp; big role</div>
    <button data-tracking-control-name="public_jobs_apply-link-offsite"></button>
    <li class="description__job-criteria-item">
      <h3 class="description__job-criteria-subheader">Tipo de empleo</h3>
      <span class="description__job-criteria-text">Jornada completa</span>
    </li>
    <div class="salary compensation__salary">756.000,00 AED/año - 924.000,00 AED/año</div>
    <figcaption class="num-applicants__caption">Over 200 applicants</figcaption></html>"""


def en_fragment():
    # The same posting's www fragment: identical markup in en-US.
    return """
    <html><a class="topcard__org-name-link"
      href="https://uk.linkedin.com/company/acme?trk=public_jobs_topcard-org-name"></a>
    <img class="artdeco-entity-image" data-delayed-url="https://media.licdn.com/acme-logo.png"/>
    <div class="show-more-less-html__markup">Great &amp; big role</div>
    <li class="description__job-criteria-item">
      <h3 class="description__job-criteria-subheader">Employment type</h3>
      <span class="description__job-criteria-text">Full-time</span>
    </li>
    <div class="salary compensation__salary">AED 756,000.00/yr - AED 924,000.00/yr</div>
    <figcaption class="num-applicants__caption">109 applicants</figcaption></html>"""


def test_parse_posting_falls_back_to_the_markup_without_the_block():
    fields = linkedin.parse_posting(blockless_page())
    assert fields["description"] == "Great & big role"
    assert fields["apply_type"] == "offsite"
    assert fields["applicants"] == 200
    assert "posted_at" not in fields  # the structured fields stay absent
    # localized labels and number formats must not half-parse into wrong values
    assert "employment_type" not in fields
    assert "salary_min" not in fields


def test_parse_posting_reads_the_en_us_markup_labels():
    fields = linkedin.parse_posting(en_fragment())
    assert fields["employment_type"] == "full_time"
    assert (fields["salary_min"], fields["salary_max"]) == (756000.0, 924000.0)
    assert (fields["salary_currency"], fields["salary_period"]) == ("AED", "YEAR")
    assert fields["company_url"] == "https://uk.linkedin.com/company/acme"
    assert fields["company_logo"] == "https://media.licdn.com/acme-logo.png"


def hydrated(postings, url) -> dict:
    """The posting's fields; a gone or unfetched posting fails the test."""
    posting = postings.get(url)
    assert posting is not None
    return posting


def test_fetch_postings_block_less_page_pulls_the_fragment(unlimited):
    other = "https://nl.linkedin.com/jobs/view/other-at-acme-444"
    fetcher = StubFetcher(
        {
            "economist-at-acme-111": ok(blockless_page()),
            "jobPosting/111": ok(en_fragment()),
            "other-at-acme-444": ok(blockless_page()),  # its fragment errors: no stub
        }
    )
    got = asyncio.run(linkedin.fetch_postings(fetcher, [CANONICAL, other]))
    assert hydrated(got, CANONICAL)["employment_type"] == "full_time"  # the fragment's contribution
    assert hydrated(got, CANONICAL)["applicants"] == 200  # the page wins where both speak
    # page fields survive a failed fragment
    assert hydrated(got, other)["description"] == "Great & big role"
    assert "employment_type" not in hydrated(got, other)
    assert fetcher.requests == [
        CANONICAL,
        f"{FRAGMENT_URL}/111?_l=en_US",  # forced locale: the labels must parse
        other,
        f"{FRAGMENT_URL}/444?_l=en_US",
    ]
    # the rerun serves both from the cache, partial or not
    fetcher.requests.clear()
    assert asyncio.run(linkedin.fetch_postings(fetcher, [CANONICAL, other])) == got
    assert fetcher.requests == []


def test_fetch_postings_three_outcomes_and_what_each_costs_again(unlimited, monkeypatch):
    monkeypatch.setattr(client, "RETRY_DELAY", 0)
    gone = "https://nl.linkedin.com/jobs/view/gone-at-acme-222"
    flaky = "https://nl.linkedin.com/jobs/view/flaky-at-acme-333"
    fetcher = StubFetcher(
        {
            "economist-at-acme-111": ok(job_page()),
            "gone-at": not_found(),
            "flaky-at": rate_limited(),
        }
    )
    postings = asyncio.run(
        linkedin.fetch_postings(fetcher, [CANONICAL, "", CANONICAL, gone, flaky])
    )
    assert hydrated(postings, CANONICAL)["employment_type"] == "full_time"
    assert postings[gone] is None  # gone: stop asking
    assert flaky not in postings  # transient: safe to retry
    assert sum(1 for u in fetcher.requests if u == CANONICAL) == 1  # deduped

    # A retry: hydrated and gone come from the cache, only the transient is re-asked.
    fetcher.responses["flaky-at"] = ok(job_page())
    fetcher.requests.clear()
    again = asyncio.run(linkedin.fetch_postings(fetcher, [CANONICAL, gone, flaky]))
    assert hydrated(again, flaky)["employment_type"] == "full_time"
    assert (again[CANONICAL], again[gone]) == (postings[CANONICAL], None)
    assert fetcher.requests == [flaky]


def test_fetch_postings_drops_a_trailing_slash(unlimited):
    fetcher = StubFetcher({"economist-at-acme-111": ok(job_page())})
    got = asyncio.run(linkedin.fetch_postings(fetcher, [CANONICAL + "/"]))
    assert hydrated(got, CANONICAL + "/")["employment_type"] == "full_time"  # keyed as passed
    assert fetcher.requests == [CANONICAL]  # fetched without it, or the page omits the block


def test_fetch_postings_cache_false_refetches(unlimited):
    fetcher = StubFetcher({"economist-at-acme-111": ok(job_page())})
    asyncio.run(linkedin.fetch_postings(fetcher, [CANONICAL], cache=False))
    asyncio.run(linkedin.fetch_postings(fetcher, [CANONICAL], cache=False))
    assert len(fetcher.requests) == 2


def test_fetch_postings_caches_by_id_not_url(unlimited):
    # The subdomain and slug vary under one posting; the id does not.
    fetcher = StubFetcher({"economist-at-acme-111": ok(job_page())})
    asyncio.run(linkedin.fetch_postings(fetcher, [CANONICAL]))
    moved = "https://www.linkedin.com/jobs/view/senior-economist-at-acme-111"
    got = asyncio.run(linkedin.fetch_postings(StubFetcher({}), [moved]))
    assert hydrated(got, moved)["employment_type"] == "full_time"


def test_fetch_postings_drops_unknown_cached_keys(unlimited, isolated_cache):
    # A cached row from an older schema must not crash the run it is served to.
    isolated_cache.put("linkedin", {"111": {"description": "Role", "months_of_experience": 36}})
    got = asyncio.run(linkedin.fetch_postings(StubFetcher({}), [CANONICAL]))
    assert got[CANONICAL] == {"description": "Role"}


def test_interrupted_sweep_keeps_paid_results(unlimited, isolated_cache):
    class DiesOnSecond(StubFetcher):
        async def fetch(self, url, headers=None):
            if len(self.requests) == 1:
                raise RuntimeError("interrupted")
            return await super().fetch(url, headers)

    other = "https://nl.linkedin.com/jobs/view/other-at-acme-222"
    fetcher = DiesOnSecond({"economist-at-acme-111": ok(job_page())})
    with pytest.raises(RuntimeError):
        asyncio.run(linkedin.fetch_postings(fetcher, [CANONICAL, other]))
    assert isolated_cache.get("linkedin", ["111"])["111"]["applicants"] == 200


def test_broken_cache_still_fetches_and_warns_once(unlimited, tmp_path, monkeypatch, caplog):
    (tmp_path / "blocker").write_text("")
    monkeypatch.setattr(client, "CACHE", PostingCache(tmp_path / "blocker" / "x.sqlite3"))
    fetcher = StubFetcher({"economist-at-acme-111": ok(job_page())})
    with caplog.at_level(logging.WARNING, logger="jobrake.cache"):
        postings = asyncio.run(linkedin.fetch_postings(fetcher, [CANONICAL]))
    assert hydrated(postings, CANONICAL)["applicants"] == 200
    assert len([r for r in caplog.records if "disabled" in r.message]) == 1
