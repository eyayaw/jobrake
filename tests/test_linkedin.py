"""LinkedIn guest-search parsing and pagination tests."""

import asyncio
import json
import logging

import pytest
from fakes import StubFetcher, not_found, ok, rate_limited

from jobrake.cache import DescriptionCache
from jobrake.fetchkit import TokenBucket
from jobrake.models import JOB_FIELDS
from jobrake.sites import linkedin
from jobrake.sites.linkedin import client, descriptions


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
    detail = '<div class="show-more-less-html__markup"><p>x</p></div>'
    fetcher = StubFetcher(
        {"seeMoreJobPostings": ok(linkedin_card("111")), "jobPosting/111": ok(detail)}
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
        {"seeMoreJobPostings": ok(linkedin_card("111")), "jobPosting/111": ok(detail)}
    )
    jobs = asyncio.run(
        linkedin.search(
            fetcher, search_term="x", location="Seattle", results_wanted=1, fetch_description=True
        )
    )
    assert jobs[0]["description"] == "Great & big role"
    assert any("jobPosting/111" in url for url in fetcher.requests)


def test_fetch_descriptions_dedups_and_omits_unhydrated(unlimited):
    detail = '<div class="show-more-less-html__markup"><p>Role</p></div>'
    fetcher = StubFetcher(
        {
            "jobPosting/111": ok(detail),
            "jobPosting/222": ok("<div>signup wall</div>"),
            "jobPosting/333": not_found(),
        }
    )
    descriptions = asyncio.run(
        linkedin.fetch_descriptions(fetcher, ["111", "", "111", "222", "333"])
    )
    # 222 fetched but empty: absent, retryable; 333 gone: None, stop asking
    assert descriptions == {"111": "Role", "333": None}
    assert len(fetcher.requests) == 3  # duplicates and empty ids cost nothing


def test_search_keeps_empty_description_for_gone_posting(unlimited):
    fetcher = StubFetcher(
        {"seeMoreJobPostings": ok(linkedin_card("111")), "jobPosting/111": not_found()}
    )
    jobs = asyncio.run(
        linkedin.search(
            fetcher, search_term="x", location="Seattle", results_wanted=1, fetch_description=True
        )
    )
    assert jobs[0]["description"] == ""


def test_fetch_descriptions_skips_persistent_429(unlimited, monkeypatch):
    monkeypatch.setattr(client, "RETRY_DELAY", 0)
    fetcher = StubFetcher({"jobPosting/": rate_limited()})
    assert asyncio.run(linkedin.fetch_descriptions(fetcher, ["111"])) == {}
    assert len(fetcher.requests) == 2  # the one retry, then move on


DETAIL = '<div class="show-more-less-html__markup"><p>Role</p></div>'


def test_fetch_descriptions_serves_repeats_from_cache(unlimited):
    fetcher = StubFetcher({"jobPosting/111": ok(DETAIL)})
    first = asyncio.run(linkedin.fetch_descriptions(fetcher, ["111"]))
    again = asyncio.run(linkedin.fetch_descriptions(fetcher, ["111"]))
    assert first == again == {"111": "Role"}
    assert len(fetcher.requests) == 1  # the repeat cost nothing


def test_fetch_descriptions_caches_tombstones(unlimited):
    fetcher = StubFetcher({"jobPosting/111": not_found()})
    assert asyncio.run(linkedin.fetch_descriptions(fetcher, ["111"])) == {"111": None}
    assert asyncio.run(linkedin.fetch_descriptions(fetcher, ["111"])) == {"111": None}
    assert len(fetcher.requests) == 1  # gone is gone: never re-asked


def test_fetch_descriptions_cache_false_refetches(unlimited):
    fetcher = StubFetcher({"jobPosting/111": ok(DETAIL)})
    asyncio.run(linkedin.fetch_descriptions(fetcher, ["111"], cache=False))
    asyncio.run(linkedin.fetch_descriptions(fetcher, ["111"], cache=False))
    assert len(fetcher.requests) == 2


def test_fetch_descriptions_transient_miss_is_not_cached(unlimited, monkeypatch):
    monkeypatch.setattr(client, "RETRY_DELAY", 0)
    fetcher = StubFetcher({"jobPosting/111": rate_limited()})
    assert asyncio.run(linkedin.fetch_descriptions(fetcher, ["111"])) == {}
    fetcher.responses["jobPosting/111"] = ok(DETAIL)
    assert asyncio.run(linkedin.fetch_descriptions(fetcher, ["111"])) == {"111": "Role"}


def test_search_reruns_only_fetch_unseen_descriptions(unlimited):
    responses = {"seeMoreJobPostings": ok(linkedin_card("111")), "jobPosting/111": ok(DETAIL)}
    jobs = asyncio.run(
        linkedin.search(
            StubFetcher(responses),
            search_term="x",
            location="Seattle",
            results_wanted=1,
            fetch_description=True,
        )
    )
    rerun_fetcher = StubFetcher(responses)
    rerun = asyncio.run(
        linkedin.search(
            rerun_fetcher,
            search_term="x",
            location="Seattle",
            results_wanted=1,
            fetch_description=True,
        )
    )
    assert jobs[0]["description"] == rerun[0]["description"] == "Role"
    assert not any("jobPosting" in url for url in rerun_fetcher.requests)


def test_interrupted_sweep_keeps_paid_results(unlimited, isolated_cache):
    class DiesOnSecond(StubFetcher):
        async def fetch(self, url, headers=None):
            if len(self.requests) == 1:
                raise RuntimeError("interrupted")
            return await super().fetch(url, headers)

    fetcher = DiesOnSecond({"jobPosting/111": ok(DETAIL)})
    with pytest.raises(RuntimeError):
        asyncio.run(linkedin.fetch_descriptions(fetcher, ["111", "222"]))
    assert isolated_cache.get("linkedin", ["111"]) == {"111": "Role"}


def test_broken_cache_still_fetches_and_warns_once(unlimited, tmp_path, monkeypatch, caplog):
    (tmp_path / "blocker").write_text("")
    monkeypatch.setattr(descriptions, "CACHE", DescriptionCache(tmp_path / "blocker" / "x.sqlite3"))
    fetcher = StubFetcher({"jobPosting/111": ok(DETAIL)})
    with caplog.at_level(logging.WARNING, logger="jobrake.cache"):
        assert asyncio.run(linkedin.fetch_descriptions(fetcher, ["111"])) == {"111": "Role"}
    assert len([r for r in caplog.records if "disabled" in r.message]) == 1


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
    # no salary and no experience on this posting: absent, not blank
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
    assert "posted_at" not in fields  # the structured fields stay absent, not blank
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
