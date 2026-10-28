"""EconJobMarket ad feed parsing tests."""

import asyncio
import json

from fakes import StubFetcher, ok

from jobrake.sites import econjobmarket

# Three ads from backend.econjobmarket.org/data/zz_public/json/Ads, fetched
# 2026-10-28, trimmed to the fields jobrake reads plus enddate, with each ad
# text cut to a sentence or two and the first two of its locations kept.
ADS = [
    {
        "adtitle": "Senior Associate (North America)",
        "adtext": "<p><strong>About Charles River Associates</strong></p>\n<p>Charles River "
        "Associates is a leading global consulting firm.</p>",
        "startdate": "2026-09-03",
        "enddate": "2026-12-01",
        "deadline_date": "2026-11-06",
        "name": "Charles River Associates",
        "latitude": 42.3493011,
        "longitude": -71.0752547,
        "locations": [
            {
                "city": "Boston",
                "state": "Massachusetts",
                "country_code": "US",
                "latitude": 42.34915593041873,
                "longitude": -71.07513728955853,
            },
            {
                "city": "Chicago",
                "state": "Illinois",
                "country_code": "US",
                "latitude": None,
                "longitude": None,
            },
        ],
        "url": "https://econjobmarket.org/positions/12622",
        "logo_url": "https://backend.econjobmarket.org/data/zz_public/json/Logo/470",
    },
    {
        "adtitle": "Senior Associate/Antitrust & Competition Economics (Europe)",
        "adtext": '<p><strong><a href="http://www.crai.com/">Charles River Associates</a>'
        "</strong> is a leading global consulting firm.</p>",
        "startdate": "2026-09-30",
        "enddate": "2026-12-01",
        "deadline_date": "2026-11-06",
        "name": "Charles River Associates",
        "latitude": 42.3493011,
        "longitude": -71.0752547,
        "locations": [
            {
                "city": "London",
                "state": None,
                "country_code": "GB",
                "latitude": 51.518512067411244,
                "longitude": -0.08701994054260755,
            },
            {
                "city": "Brussels",
                "state": None,
                "country_code": "BE",
                "latitude": None,
                "longitude": None,
            },
        ],
        "url": "https://econjobmarket.org/positions/12723",
        "logo_url": "https://backend.econjobmarket.org/data/zz_public/json/Logo/470",
    },
    {
        "adtitle": "Postdoctoral position - Causal inference in electronic health record data",
        "adtext": "<p>We are looking for a talented researcher to help the Geldsetzer lab.</p>",
        "startdate": "2026-08-03",
        "enddate": "2027-02-03",
        "deadline_date": "2027-02-03",
        "name": "Heidelberg University",
        "latitude": 49.41260787196709,
        "longitude": 8.67098002533317,
        "locations": [],
        "url": "https://econjobmarket.org/positions/12558",
        "logo_url": "https://backend.econjobmarket.org/data/zz_public/json/Logo/10426",
    },
]


def test_the_feed_parses_into_records():
    fetcher = StubFetcher({"json/Ads": ok(json.dumps(ADS))})
    assert asyncio.run(econjobmarket.search(fetcher)) == [
        {
            "site": "econjobmarket",
            "id": "12622",
            "url": "https://econjobmarket.org/positions/12622",
            "title": "Senior Associate (North America)",
            "company": "Charles River Associates",
            "locations": [
                {
                    "name": "Boston, Massachusetts, US",
                    "city": "Boston",
                    "region": "Massachusetts",
                    "country_code": "US",
                    "latitude": 42.34915593041873,
                    "longitude": -71.07513728955853,
                },
                {
                    "name": "Chicago, Illinois, US",
                    "city": "Chicago",
                    "region": "Illinois",
                    "country_code": "US",
                },
            ],
            "date": "2026-09-03",
            "description": "About Charles River Associates\n"
            "Charles River Associates is a leading global consulting firm.",
            "company_logo": "https://backend.econjobmarket.org/data/zz_public/json/Logo/470",
            "posted_at": "2026-09-03",
            "expires_at": "2026-11-06",
        },
        {
            "site": "econjobmarket",
            "id": "12723",
            "url": "https://econjobmarket.org/positions/12723",
            "title": "Senior Associate/Antitrust & Competition Economics (Europe)",
            "company": "Charles River Associates",
            "locations": [
                {
                    "name": "London, GB",
                    "city": "London",
                    "country_code": "GB",
                    "latitude": 51.518512067411244,
                    "longitude": -0.08701994054260755,
                },
                {"name": "Brussels, BE", "city": "Brussels", "country_code": "BE"},
            ],
            "date": "2026-09-30",
            "description": "Charles River Associates is a leading global consulting firm.",
            "company_logo": "https://backend.econjobmarket.org/data/zz_public/json/Logo/470",
            "posted_at": "2026-09-30",
            "expires_at": "2026-11-06",
        },
        {
            "site": "econjobmarket",
            "id": "12558",
            "url": "https://econjobmarket.org/positions/12558",
            "title": "Postdoctoral position - Causal inference in electronic health record data",
            "company": "Heidelberg University",
            "locations": [],
            "date": "2026-08-03",
            "description": "We are looking for a talented researcher to help the Geldsetzer lab.",
            "company_logo": "https://backend.econjobmarket.org/data/zz_public/json/Logo/10426",
            "posted_at": "2026-08-03",
            "expires_at": "2027-02-03",
        },
    ]
    assert fetcher.requests == ["https://backend.econjobmarket.org/data/zz_public/json/Ads"]


def test_an_ad_whose_url_holds_no_number_is_skipped(caplog):
    malformed = [{**ADS[0], "url": "https://econjobmarket.org/"}, ADS[2]]
    fetcher = StubFetcher({"json/Ads": ok(json.dumps(malformed))})
    jobs = asyncio.run(econjobmarket.search(fetcher))
    assert [job["id"] for job in jobs] == ["12558"]
    assert "skipping malformed econjobmarket posting" in caplog.text
