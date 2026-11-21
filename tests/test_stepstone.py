"""StepStone listings API paging and parsing tests."""

import asyncio
import json

import pytest
from fakes import DEEP_JSON, PagedFetcher, StubFetcher, ok

from jobrake import Stopped
from jobrake.fetchkit import FetchResult
from jobrake.sites import stepstone

# Two cards from naps-facade/v4/listings/search, trimmed to the fields jobrake reads plus a few it
# leaves out. The first is a single-city posting with coordinates, the second a multi-city posting
# whose 0, 0 stands for no coordinate (fetched 2026-11-15).
CARDS: list[dict[str, object]] = [
    {
        "id": "14660809",
        "title": "Data Scientist (w/m/d)",
        "companyName": "KBV",
        "companyLogoURL": "https://www.stepstone.de/logo/kbv.gif",
        "location": "Brühl",
        "country": "de",
        "latitude": 49.4026985168457,
        "longitude": 8.538100242614746,
        "language": "de",
        "datePosted": 1793509515882,
        "dateOriginal": 1793509515882,
        "dateExpire": 1796115626107,
        "section": "main",
        "listingLabels": ["BLAD", "REMOTE"],
        "url": "https://developer.stepstone.com/fakeListingUrlPleaseIgnore",
        "salaryDetails": {"min": None, "max": None},
        "employmentType": None,
    },
    {
        "id": "14569042",
        "title": "Volkswirt im Transfer Pricing (m/w/d)",
        "companyName": "Deloitte",
        "location": "Berlin, Düsseldorf, München",
        "country": "de",
        "latitude": 0.0,
        "longitude": 0.0,
        "language": "de",
        "datePosted": 1793509515882,
        "dateExpire": 1796115626107,
        "section": "regionalExtended",
        "listingLabels": ["BLAD"],
    },
]

# A posting page: an unrelated JSON-LD block, then the JobPosting block the site serves, and the
# JobAdContent literal that names the offer language and the card's location label. jobLocation
# carries a street and one city.
POSTING = (
    '<html><head><script type="application/ld+json">'
    '{"@type": "WebSite", "name": "StepStone"}</script>'
    '<script type="application/ld+json">{"@type": "JobPosting", "title": "Data Scientist",'
    ' "employmentType": "FULL_TIME", "datePosted": "2026-11-14T14:03:07.607Z",'
    ' "validThrough": "2026-11-29T13:50:48.89Z",'
    ' "hiringOrganization": {"name": "KBV", "url": "https://www.stepstone.de/cmp/kbv"},'
    ' "jobLocation": {"address": {"streetAddress": "Leipziger Stra\\u00dfe 35",'
    ' "addressLocality": "Wiesbaden", "addressCountry": "DE"},'
    ' "geo": {"latitude": 50.09116, "longitude": 8.28064}},'
    ' "description": "<p>Join us <b>today</b></p>"}</script>'
    '<script>window.JobAdContent = { props: {"offerLanguage":"de",'
    ' "metaData":{"workType":"Full Time","location":"Wiesbaden"}} }</script>'
    "</head><body></body></html>"
)


def _page(cards: list[dict[str, object]], total: int) -> str:
    return json.dumps({"data": {"items": cards, "totalItems": total, "limit": 50, "offset": 0}})


def test_search_parses_a_card_with_its_coordinates_and_dates() -> None:
    fetcher = PagedFetcher([_page(CARDS, 2)])
    [city, _] = asyncio.run(stepstone.search(fetcher, query="data", location="Brühl"))

    assert city["id"] == "14660809"
    assert city["url"] == "https://www.stepstone.de/job/14660809"
    assert city["company"] == "KBV"
    assert city["locations"] == [
        {
            "name": "Brühl",
            "country_code": "DE",
            "latitude": 49.4026985168457,
            "longitude": 8.538100242614746,
        }
    ]
    assert city["date"] == "2026-11-01"
    assert city["posted_at"] == "2026-11-01T05:05:15.882000+00:00"
    assert city["expires_at"] == "2026-12-01T09:00:26.107000+00:00"
    assert city["site_data"] == {"section": "main", "labels": ["BLAD", "REMOTE"]}


def test_a_multi_city_card_keeps_its_label_and_drops_the_zero_coordinate() -> None:
    fetcher = PagedFetcher([_page(CARDS, 2)])
    [_, deloitte] = asyncio.run(stepstone.search(fetcher, query="data"))

    assert deloitte["locations"] == [{"name": "Berlin, Düsseldorf, München", "country_code": "DE"}]


def test_a_card_on_the_prime_meridian_keeps_its_coordinates() -> None:
    greenwich = {**CARDS[0], "location": "Greenwich", "latitude": 51.48, "longitude": 0.0}
    [job] = asyncio.run(stepstone.search(PagedFetcher([_page([greenwich], 1)]), query="data"))

    assert job["locations"][0]["latitude"] == 51.48
    assert job["locations"][0]["longitude"] == 0.0


def test_search_pages_until_the_reported_total_with_its_filters_on_every_page() -> None:
    fetcher = PagedFetcher([_page(CARDS, 3), _page(CARDS[:1], 3)])
    jobs = asyncio.run(stepstone.search(fetcher, query="data", remote=True))

    assert [job["id"] for job in jobs] == ["14660809", "14569042"]
    assert len(fetcher.requests) == 2
    assert fetcher.headers[0]["ApiKey"] == stepstone.APP_KEY
    assert "workFromHome=1" in fetcher.requests[1]


def test_a_card_without_a_posting_number_is_skipped() -> None:
    # Each of these ids gives a posting URL that card rejects.
    malformed: list[dict[str, object]] = [{"title": "No ID"}, {"id": True}, {"id": "abc"}]
    malformed += [{"id": -5}, {"id": "1/"}]
    fetcher = PagedFetcher([_page([*malformed, CARDS[0]], 6)])
    jobs = asyncio.run(stepstone.search(fetcher, query="data"))

    assert [job["id"] for job in jobs] == ["14660809"]


def test_an_empty_page_before_the_total_stops_the_search_with_what_it_has() -> None:
    fetcher = PagedFetcher([_page(CARDS, 5), _page([], 5)])
    with pytest.raises(Stopped) as caught:
        asyncio.run(stepstone.search(fetcher, query="data"))

    assert len(caught.value.partial) == 2


def test_details_fill_the_description_and_employment_type() -> None:
    fetcher = StubFetcher({"offset=0": ok(_page(CARDS[:1], 1)), "/job/14660809": ok(POSTING)})
    [job] = asyncio.run(stepstone.search(fetcher, query="data", details=True))

    assert job["description"] == "Join us today"
    assert job["employment_type"] == "full_time"


def test_postings_builds_a_whole_record_from_a_url_with_no_card() -> None:
    fetcher = StubFetcher({"/job/14569042": ok(POSTING)})
    found = asyncio.run(stepstone.postings(fetcher, ["https://www.stepstone.de/job/14569042"]))
    job = found["https://www.stepstone.de/job/14569042"]

    assert job is not None
    assert job["company"] == "KBV"
    assert job["company_url"] == "https://www.stepstone.de/cmp/kbv"
    assert job["locations"] == [
        {
            "name": "Wiesbaden",
            "city": "Wiesbaden",
            "country_code": "DE",
            "latitude": 50.09116,
            "longitude": 8.28064,
        }
    ]
    assert job["language"] == "de"
    assert job["date"] == "2026-11-14"
    assert job["description"] == "Join us today"


@pytest.mark.parametrize(
    ("label", "street", "locality", "name"),
    [
        # The first city's address under the card's label, as on posting 14611747 (2026-11-15).
        ("Darmstadt, Bensheim ", "Rheinstr. 21", "Darmstadt", "Darmstadt, Bensheim"),
        # The label again in addressLocality, as on posting 10002139.
        ("Berlin, Bonn, Hamburg", "", "Berlin, Bonn, Hamburg", "Berlin, Bonn, Hamburg"),
        # A label the page escapes, here for its quotes.
        ('Hamburg "Hafen", Kiel', "Am Kai 1", "Hamburg", 'Hamburg "Hafen", Kiel'),
    ],
)
def test_a_page_keeps_the_label_of_a_posting_open_in_several_cities(label, street, locality, name):
    address = {"streetAddress": street, "addressLocality": locality, "addressCountry": "DE"}
    block = {"@type": "JobPosting", "jobLocation": {"address": address}}
    meta = json.dumps({"location": label}, separators=(",", ":"))  # as compact as the page's
    page = (
        f'<script type="application/ld+json">{json.dumps(block)}</script>'
        f'<script>window.JobAdContent = {{"metaData":{meta}}}</script>'
    )
    fetcher = StubFetcher({"/job/1": ok(page)})
    found = asyncio.run(stepstone.postings(fetcher, ["https://www.stepstone.de/job/1"]))
    job = found["https://www.stepstone.de/job/1"]

    assert job is not None
    assert job["locations"] == [{"name": name, "country_code": "DE"}]


@pytest.mark.parametrize("meta", ["{", DEEP_JSON])
def test_a_page_whose_card_label_does_not_parse_names_the_place_from_its_block(meta):
    address = {"addressLocality": "Wiesbaden", "addressCountry": "DE"}
    block = {"@type": "JobPosting", "jobLocation": {"address": address}}
    page = (
        f'<script>window.JobAdContent = {{"metaData":{meta}}}</script>'
        f'<script type="application/ld+json">{json.dumps(block)}</script>'
    )
    fetcher = StubFetcher({"/job/1": ok(page)})
    found = asyncio.run(stepstone.postings(fetcher, ["https://www.stepstone.de/job/1"]))
    job = found["https://www.stepstone.de/job/1"]

    assert job is not None
    assert job["locations"] == [{"name": "Wiesbaden", "city": "Wiesbaden", "country_code": "DE"}]


def test_a_posting_page_sent_without_http_200_is_left_out() -> None:
    fetcher = StubFetcher({"/job/1": FetchResult("stub", 203, POSTING)})
    assert asyncio.run(stepstone.postings(fetcher, ["https://www.stepstone.de/job/1"])) == {}


def test_a_gone_posting_keeps_its_card() -> None:
    gone = FetchResult(url="stub", status=410)
    fetcher = StubFetcher({"offset=0": ok(_page(CARDS[:1], 1)), "/job/14660809": gone})
    [job] = asyncio.run(stepstone.search(fetcher, query="data", details=True))

    assert "description" not in job
    assert job["company"] == "KBV"


def test_card_reads_a_job_url_and_a_slug_url() -> None:
    assert stepstone.card("https://www.stepstone.de/job/14569042")["id"] == "14569042"
    slug = (
        "https://www.stepstone.de/stellenangebote--Data-Scientist-Berlin-KBV--14569042-inline.html"
    )
    assert stepstone.card(slug)["id"] == "14569042"


def test_card_rejects_a_non_posting_url() -> None:
    with pytest.raises(ValueError, match="not a StepStone posting URL"):
        stepstone.card("https://www.stepstone.de/jobs/in-berlin")
