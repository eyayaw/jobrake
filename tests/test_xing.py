"""XING GraphQL API paging, filtering, posting details, and parsing tests."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fakes import PagedFetcher, StubFetcher

from jobrake import Stopped, identify
from jobrake.fetchkit import FetchResult
from jobrake.sites import xing

# Trimmed real cards from api.xing.com/vendor/xing-one/api (fetched 2026-11-24).
# The first carries XING's own estimate, which the query selects nothing of, the second an
# employer-advertised SalaryRange. Fields are in the shape the query's aliases give them.
CARDS: list[dict[str, dict[str, Any]]] = [
    {
        "jobDetail": {
            "__typename": "VisibleJob",
            "id": "158291337_dbef63",
            "title": "Volkswirt / Betriebswirt als Consultant Transfer Pricing (w/m/d)",
            "url": "https://www.xing.com/jobs/berlin-volkswirt-transfer-pricing-158291337",
            "language": "de",
            "refreshedAt": "2026-11-23T01:37:59Z",
            "activeUntil": "2027-10-02T11:19:06Z",
            "remoteOptions": ["PARTLY_REMOTE"],
            "employmentType": {"id": "FULL_TIME_b0ed28", "localizationValue": "Full-time"},
            "careerLevel": {"localizationValue": "Entry level"},
            "discipline": {"localizationValue": "Consulting"},
            "industry": {"localizationValue": "Auditing, tax, law"},
            "locations": [
                {"city": "Berlin", "region": "Land Berlin", "country": {"countryCode": "DE"}}
            ],
            "companyInfo": {
                "companyNameOverride": "KPMG",
                "company": {
                    "companyName": "KPMG AG",
                    "logos": {"logo256px": "https://www.xing.com/imagecache/kpmg.png"},
                    "links": {"public": "https://www.xing.com/pages/kpmg"},
                },
            },
            "salary": {},
            "application": {
                "url": "https://apply.example.com/kpmg/158291337",
            },
        }
    },
    {
        "jobDetail": {
            "__typename": "VisibleJob",
            "id": "158433297_053628",
            "title": "Consultant *in Healthcare/Gesundheitsökonomie",
            "url": "https://www.xing.com/jobs/berlin-consultant-healthcare-158433297",
            "language": "de",
            "refreshedAt": "2026-11-22T08:21:23Z",
            "activeUntil": "2026-12-07T08:34:06Z",
            "remoteOptions": ["FULL_REMOTE"],
            "employmentType": {"id": "CONTRACTOR_d4c528", "localizationValue": "Self-employed"},
            "careerLevel": {"localizationValue": "Professional/Experienced"},
            "discipline": {"localizationValue": "Consulting"},
            "industry": {"localizationValue": "Health and social"},
            "locations": [
                {"city": "Berlin", "region": "Land Berlin", "country": {"countryCode": "DE"}},
                {"city": "Zürich", "region": None, "country": {"countryCode": "CH"}},
            ],
            "companyInfo": {
                "companyNameOverride": None,
                "company": {
                    "companyName": "Johannesstift Diakonie Services GmbH",
                    "logos": {"logo256px": None},
                    "links": {"public": None},
                },
            },
            "salary": {
                "__typename": "SalaryRange",
                "minimum": 50000,
                "maximum": 70000,
                "currency": "EUR",
            },
            "application": {
                "url": "https://www.xing.com/jobs/custom-apply/berlin-consultant-158433297",
            },
        }
    },
]

# Trimmed TemplateData posting with structured sections (from posting 158433297, 2026-11-24).
STRUCTURED_POSTING = {
    **CARDS[1]["jobDetail"],
    "description": {
        "__typename": "TemplateData",
        "genericDescription": None,
        "companyDescriptionTitle": "Ihr neues Team",
        "companyDescriptionContent": "<p>Unser Team verantwortet das Einkaufsmanagement.</p>",
        "responsibilityTitle": "Aufgaben",
        "responsibilityContent": "<p>Analyse von Sachkosten.</p>",
        "skillsTitle": "Ihr Profil",
        "skillsContent": "<ul><li>Studium der Gesundheitsökonomie</li></ul>",
        "weOfferTitle": "Vorteile",
        "weOfferContent": "<p>Mobiles Arbeiten</p>",
        "contactInfoTitle": "Bewerbung",
        "contactInfoContent": "<p>Bewerben Sie sich online.</p>",
    },
}


def _search_page(collection: list[dict[str, Any]], total: int, bound: int = 1000) -> str:
    return json.dumps(
        {
            "data": {
                "response": {
                    "boundedTotal": {"total": total, "bound": bound},
                    "collection": collection,
                }
            }
        }
    )


def _posting_body(job: dict[str, Any] | None) -> str:
    return json.dumps({"data": {"job": job}})


def _numbered(count: int, start: int = 1) -> list[dict[str, Any]]:
    base = CARDS[0]["jobDetail"]
    return [
        {
            "jobDetail": {
                **base,
                "id": f"{n}_abcdef",
                "url": f"https://www.xing.com/jobs/berlin-role-{n}",
            }
        }
        for n in range(start, start + count)
    ]


def test_search_parses_cards_advertised_salary_and_leaves_estimate_out() -> None:
    single_salary = {
        "jobDetail": {
            **CARDS[0]["jobDetail"],
            "id": "159022558_9abaea",
            "url": "https://www.xing.com/jobs/berlin-duales-studium-159022558",
            "remoteOptions": ["NON_REMOTE"],
            "employmentType": {"id": "INTERN_99cfb1", "localizationValue": "Student"},
            "salary": {"minimum": 65000, "maximum": 65000, "currency": "EUR"},
            "application": {},
        }
    }
    ambiguous_remote = {
        "jobDetail": {
            **CARDS[0]["jobDetail"],
            "id": "159022559_111111",
            "url": "https://www.xing.com/jobs/berlin-mixed-159022559",
            "remoteOptions": ["FULL_REMOTE", "PARTLY_REMOTE"],
            "employmentType": {"id": None, "localizationValue": "Full-time"},
            "salary": None,
        }
    }
    fetcher = PagedFetcher([_search_page([*CARDS, single_salary, ambiguous_remote], 4)])
    kpmg, jsd, intern, mixed = asyncio.run(xing.search(fetcher, query="economist"))

    assert kpmg == {
        "site": "xing",
        "id": "158291337",
        "url": "https://www.xing.com/jobs/berlin-volkswirt-transfer-pricing-158291337",
        "title": "Volkswirt / Betriebswirt als Consultant Transfer Pricing (w/m/d)",
        "company": "KPMG",
        "company_url": "https://www.xing.com/pages/kpmg",
        "company_logo": "https://www.xing.com/imagecache/kpmg.png",
        "locations": [
            {
                "name": "Berlin, Land Berlin, DE",
                "city": "Berlin",
                "region": "Land Berlin",
                "country_code": "DE",
            }
        ],
        "date": "2026-11-23",
        "language": "de",
        "employment_type": "full_time",
        "workplace_type": "hybrid",
        "posted_at": "2026-11-23T01:37:59Z",
        "expires_at": "2027-10-02T11:19:06Z",
        "apply_url": "https://apply.example.com/kpmg/158291337",
        "site_data": {
            "careerLevel": "Entry level",
            "discipline": "Consulting",
            "industry": "Auditing, tax, law",
        },
    }
    # Advertised SalaryRange fills all four salary keys; company falls back to company.companyName.
    assert jsd["company"] == "Johannesstift Diakonie Services GmbH"
    assert jsd["employment_type"] == "contract"
    assert jsd["workplace_type"] == "remote"
    assert jsd["salary_min"] == 50000
    assert jsd["salary_max"] == 70000
    assert jsd["salary_currency"] == "EUR"
    assert jsd["salary_period"] == "YEAR"
    assert jsd["apply_url"] == "https://www.xing.com/jobs/custom-apply/berlin-consultant-158433297"
    assert jsd["locations"] == [
        {
            "name": "Berlin, Land Berlin, DE",
            "city": "Berlin",
            "region": "Land Berlin",
            "country_code": "DE",
        },
        {"name": "Zürich, CH", "city": "Zürich", "country_code": "CH"},
    ]
    assert "company_url" not in jsd
    assert "company_logo" not in jsd
    # Single Salary sets both bounds; EmailApplication is not a URL so apply_url stays absent.
    assert (intern["salary_min"], intern["salary_max"]) == (65000, 65000)
    assert intern["salary_currency"] == "EUR"
    assert intern["salary_period"] == "YEAR"
    assert intern["employment_type"] == "internship"
    assert intern["workplace_type"] == "on_site"
    assert "apply_url" not in intern
    # Conflicting remoteOptions leave workplace_type unset, and a type without its code falls
    # back to its English label.
    assert "workplace_type" not in mixed
    assert mixed["employment_type"] == "full_time"


def test_search_sends_headers_and_filters_to_the_graphql_api() -> None:
    fetcher = PagedFetcher([_search_page([], 0)])
    before = datetime.now(UTC)
    asyncio.run(
        xing.search(
            fetcher,
            query=" economist ",
            location=" Berlin ",
            radius=50,
            results=5,
            max_age_hours=24,
            remote=True,
        )
    )
    assert fetcher.requests == [xing.API_URL]
    assert fetcher.headers[0] == xing.API_HEADERS
    variables = fetcher.bodies[0]["variables"]
    assert variables["query"] == {
        "keywords": "economist",
        "location": {"text": "Berlin", "radius": 50},
        "filter": {"remote": True},
    }
    assert variables["limit"] == 5
    assert variables["offset"] == 0
    since = datetime.fromisoformat(variables["since"])
    assert timedelta(hours=24, seconds=1) >= before - since >= timedelta(hours=24, seconds=-5)
    # An unfiltered search sends an empty query object and no since variable.
    empty = PagedFetcher([_search_page([], 0)])
    asyncio.run(xing.search(empty))
    assert empty.bodies[0]["variables"]["query"] == {}
    assert "since" not in empty.bodies[0]["variables"]


def test_search_pages_deduplicates_warns_at_window_cap_and_stops_when_cut_short(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # A posting repeated across page 0 and page 1 is kept once.
    fetcher = PagedFetcher(
        [_search_page(_numbered(20, 1), 30), _search_page(_numbered(10, 20), 30)]
    )
    jobs = asyncio.run(xing.search(fetcher, results=30))
    assert [job["id"] for job in jobs] == [str(n) for n in range(1, 30)]
    assert [body["variables"]["offset"] for body in fetcher.bodies] == [0, 20]
    assert [body["variables"]["limit"] for body in fetcher.bodies] == [20, 20]

    # Reaching XING's 1,000-posting window short of results warns, clamps limit so limit + offset
    # never exceeds 1,000, and never sends offset 1,000.
    pages: list[str | FetchResult | Exception] = [
        _search_page(_numbered(15, 1), 537119),
        *(_search_page(_numbered(20, 16 + i * 20), 537119) for i in range(49)),
        _search_page(_numbered(5, 996), 537119),
    ]
    capped = PagedFetcher(pages)
    with caplog.at_level("WARNING", logger="jobrake.sites.xing"):
        found = asyncio.run(xing.search(capped, results=1050))
    assert len(found) == 1000
    assert len(capped.bodies) == 51
    assert capped.bodies[-1]["variables"]["offset"] == 995
    assert capped.bodies[-1]["variables"]["limit"] == 5
    assert "at most 1000 postings per search" in caplog.text

    # An empty page before the reachable total stops with the postings collected so far.
    short = PagedFetcher([_search_page(CARDS, 10), _search_page([], 10)])
    with pytest.raises(Stopped, match="XING reported 10 postings") as caught:
        asyncio.run(xing.search(short))
    assert len(caught.value.partial) == 2


def test_malformed_cards_are_skipped_and_graphql_errors_stop_the_search(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bad: list[dict[str, Any]] = [
        {"jobDetail": None},
        {"jobDetail": {"__typename": "UnauthorizedJob", "reason": "PRIVATE"}},
        {
            "jobDetail": {
                "__typename": "VisibleJob",
                "id": "not-an-id",
                "url": "https://www.xing.com/jobs/a-1",
            }
        },
        {
            "jobDetail": {
                **CARDS[0]["jobDetail"],
                "id": "999_abcdef",  # disagrees with URL's 158291337
            }
        },
    ]
    fetcher = PagedFetcher([_search_page([*bad, CARDS[0]], 5)])
    jobs = asyncio.run(xing.search(fetcher))
    assert [job["id"] for job in jobs] == ["158291337"]
    assert caplog.text.count("skipping malformed XING posting") == 4

    error_page = json.dumps(
        {
            "data": {"response": None},
            "errors": [
                {
                    "message": "Could not resolve fields",
                    "details": {"description": "Window size (limit + offset) cannot be > 1000"},
                }
            ],
        }
    )
    failing = PagedFetcher([_search_page(CARDS, 40), error_page])
    with pytest.raises(Stopped, match="Window size") as caught:
        asyncio.run(xing.search(failing))
    assert [job["id"] for job in caught.value.partial] == ["158291337", "158433297"]

    # A GraphQL error alongside partial collection data also stops the search.
    partial_search_error = json.dumps(
        {
            "data": {
                "response": {"boundedTotal": {"total": 2, "bound": 1000}, "collection": CARDS[:1]}
            },
            "errors": [{"message": "card resolver failed"}],
        }
    )
    with pytest.raises(Stopped, match="card resolver failed"):
        asyncio.run(xing.search(PagedFetcher([partial_search_error])))


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        (
            {"__typename": "TemplateData", "genericDescription": "<p>Lead <b>analysis</b>.</p>"},
            "Lead analysis.",
        ),
        (
            STRUCTURED_POSTING["description"],
            "Ihr neues Team\nUnser Team verantwortet das Einkaufsmanagement.\nAufgaben\n"
            "Analyse von Sachkosten.\nIhr Profil\nStudium der Gesundheitsökonomie\n"
            "Vorteile\nMobiles Arbeiten\nBewerbung\nBewerben Sie sich online.",
        ),
        (
            {"__typename": "HtmlDescription", "content": "<p>Plain <em>HTML</em> ad.</p>"},
            "Plain HTML ad.",
        ),
        (
            {"__typename": "ExternalUrlDescription", "htmlContent": "<p>External body.</p>"},
            "External body.",
        ),
    ],
)
def test_postings_reads_every_description_variant_from_a_url_alone(
    description: dict[str, Any], expected: str
) -> None:
    posting = {**CARDS[1]["jobDetail"], "description": description}
    fetcher = PagedFetcher([_posting_body(posting)])
    stale = "https://www.xing.com/jobs/old-slug-158433297?utm_source=email"
    found = asyncio.run(xing.postings(fetcher, [stale]))
    job = found[stale]

    assert job is not None
    assert fetcher.bodies[0]["variables"] == {"slug": "158433297"}
    assert job["url"] == "https://www.xing.com/jobs/berlin-consultant-healthcare-158433297"
    assert job["description"] == expected
    assert job["site_data"]["industry"] == "Health and social"


def test_details_fill_description_and_cache_the_posting() -> None:
    fetcher = PagedFetcher([_search_page(CARDS[1:], 1), _posting_body(STRUCTURED_POSTING)])
    [job] = asyncio.run(xing.search(fetcher, query="economist", details=True))
    assert "Analyse von Sachkosten." in job["description"]
    assert job["id"] == "158433297"
    assert len(fetcher.requests) == 2

    # A second details search for the same posting reads the cache and makes no detail request.
    cached = PagedFetcher([_search_page(CARDS[1:], 1)])
    [again] = asyncio.run(xing.search(cached, query="economist", details=True))
    assert again["description"] == job["description"]
    assert len(cached.requests) == 1


def test_gone_postings_map_to_none_and_keep_their_card() -> None:
    url = "https://www.xing.com/jobs/berlin-volkswirt-transfer-pricing-158291337"
    gone_null = PagedFetcher([_search_page(CARDS[:1], 1), _posting_body(None)])
    [kept] = asyncio.run(xing.search(gone_null, details=True))
    assert "description" not in kept
    assert kept["company"] == "KPMG"

    gone_unauth = PagedFetcher([_posting_body({"__typename": "UnauthorizedJob", "reason": "GONE"})])
    assert asyncio.run(xing.postings(gone_unauth, [url])) == {url: None}


def test_refused_and_non_200_postings_count_as_unread() -> None:
    url = "https://www.xing.com/jobs/berlin-volkswirt-transfer-pricing-158291337"
    refused = PagedFetcher(
        [
            _search_page(CARDS[:1], 1),
            _posting_body({"__typename": "UnauthorizedJob", "reason": "PROJOBS"}),
        ]
    )
    with pytest.raises(Stopped) as caught:
        asyncio.run(xing.search(refused, details=True))
    assert caught.value.failed == [url]
    assert len(caught.value.partial) == 1

    posting = {
        **CARDS[0]["jobDetail"],
        "description": {"__typename": "HtmlDescription", "content": "<p>Transfer pricing.</p>"},
    }
    non_200 = StubFetcher({xing.API_URL: FetchResult("stub", 203, _posting_body(posting))})
    assert asyncio.run(xing.postings(non_200, [url])) == {}

    # A GraphQL error without a message still fails instead of reporting the posting gone.
    unexplained = json.dumps({"data": {"job": None}, "errors": [{"extensions": {"code": "X"}}]})
    assert asyncio.run(xing.postings(PagedFetcher([unexplained]), [url])) == {}

    # A job without its type is unreadable, so it is not cached as an empty posting.
    untyped = PagedFetcher([_posting_body({})])
    assert asyncio.run(xing.postings(untyped, [url])) == {}

    # A GraphQL error alongside partial data fails instead of caching an incomplete posting.
    partial_error = json.dumps(
        {
            "data": {"job": {**CARDS[0]["jobDetail"], "description": None}},
            "errors": [{"message": "description resolver unavailable"}],
        }
    )
    retrying = PagedFetcher([partial_error, _posting_body(posting)])
    assert asyncio.run(xing.postings(retrying, [url])) == {}
    retried = asyncio.run(xing.postings(retrying, [url]))
    job = retried[url]
    assert job is not None
    assert job["description"] == "Transfer pricing."
    assert len(retrying.requests) == 2


def test_card_and_identify_read_xing_posting_urls_and_reject_other_links() -> None:
    url = "https://www.xing.com/jobs/berlin-referent-strategische-datenanalyse-158824212"
    assert xing.card(url)["id"] == "158824212"
    assert xing.card("http://xing.com/jobs/berlin-role-158824212/?utm_source=x") == {
        "site": "xing",
        "id": "158824212",
        "url": "https://www.xing.com/jobs/berlin-role-158824212",
        "title": None,
        "company": None,
        "locations": [],
        "date": None,
    }
    assert identify(url) == ("xing", "158824212")

    for bad in (
        "https://www.xing.com/jobs/158824212",  # search page, not a posting page
        "https://www.xing.com/jobs/search?keywords=economist",
        "https://www.xing.com/jobs/-158824212",
        "https://www.xing.com/jobs/berlin-role-１５８８２４２１２",  # noqa: RUF001  fullwidth digits under test
        "https://user@www.xing.com/jobs/berlin-role-158824212",
        "https://www.xing.com:8443/jobs/berlin-role-158824212",
        "https://example.com/jobs/berlin-role-158824212",
    ):
        with pytest.raises(ValueError, match="not a XING posting URL"):
            xing.card(bad)
        assert identify(bad) is None
