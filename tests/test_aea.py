"""JOE listings page and export tests."""

import asyncio
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

import pytest
from fakes import PagedFetcher

from jobrake import Stopped
from jobrake.sites import aea

# The listings page of www.aeaweb.org/joe/listings, fetched 2026-11-17, trimmed to two listings and
# the markup jobrake reads. The site lists the newer one first when asked for recent postings.
PAGE = """<html><body>
<form id="ListingsForm" action="/joe/listings/" method="get"></form>
<a href="/joe/resultset_output.php?mode=full_xml&amp;q=eNplj0EKwkAM">XML</a>
<h5 class="date-group-header-title spacer">Date Posted: November 16, 2026</h5>
<h6 class="listing-item-header-title">
    <a href="/joe/listing.php?JOE_ID=2026-02_111478520&amp;q=eNpl">Post-Doctoral Position</a>
</h6>
<div class="listing-item-header-date-posted">Date Posted: 11/16/2026</div>
<h6 class="listing-item-header-title">
    <a href="/joe/listing.php?JOE_ID=2026-02_111477855&amp;q=eNpl">Assistant Professor</a>
</h6>
<div class="listing-item-header-date-posted">Date Posted: 10/02/2026</div>
</body></html>"""

# The export that page linked, trimmed to the same listings in the export's own order, plus one
# without an ID. The export escapes entities twice, as the site sends it.
EXPORT = """<JOE_EXPORT>
<year joe_year_ID="2026">
<issue joe_issue_ID="2">
    <position jp_id="111477855">
        <jp_section>International: Full-Time Academic (Permanent, Tenure Track or Tenured)</jp_section>
        <jp_title>Assistant Professor/ Associate/ Full Professor - Economics</jp_title>
        <jp_institution>Ahmedabad University</jp_institution>
        <jp_division>Economics and Public Policy</jp_division>
        <jp_department>Amrut Mody School of Management</jp_department>
        <jp_salary_range></jp_salary_range>
        <jp_application_deadline>2027-07-31 00:00:00</jp_application_deadline>
        <jp_full_text>Interdisciplinary &amp;amp; project-based learning.</jp_full_text>
        <jp_keywords>Microeconomics
Energy &amp;amp; Environment Economics
</jp_keywords>
        <jp_status></jp_status>
        <locations>
            <location id="35770"><country>INDIA</country><state>Gujarat</state><city>AHMEDABAD</city></location>
        </locations>
        <JEL_Classifications>
            <jel_class id="59548"><jc_code>A1</jc_code><jc_description>General Economics</jc_description></jel_class>
            <jel_class id="59556"><jc_code>F</jc_code><jc_description>International Economics</jc_description></jel_class>
        </JEL_Classifications>
    </position>
    <position jp_id="111478520">
        <jp_section>International: Other Academic (Part-time or Adjunct)</jp_section>
        <jp_title>Post-Doctoral Position</jp_title>
        <jp_institution>ESSEC Business School</jp_institution>
        <jp_salary_range>Competitive</jp_salary_range>
        <jp_full_text>ESSEC is offering a postdoctoral position in Economics</jp_full_text>
        <jp_status>Position has been filled</jp_status>
        <locations>
            <location id="1"><country>FRANCE</country><state>Ile de France</state><city>Cergy</city></location>
            <location id="2"><country>FRANCE</country><state></state><city>Paris</city></location>
        </locations>
    </position>
    <position><jp_title>no jp_id</jp_title></position>
</issue>
</year>
</JOE_EXPORT>"""


def test_a_search_reads_the_page_for_dates_and_the_export_for_the_rest(caplog):
    fetcher = PagedFetcher([PAGE, EXPORT])
    jobs = asyncio.run(
        aea.search(
            fetcher, query=" labor ", section=["full-time nonacademic", "2A", "4", "4b", " 5 "]
        )
    )
    assert jobs == [
        {
            "site": "aea",
            "id": "2026-02_111478520",
            "url": "https://www.aeaweb.org/joe/listing.php?JOE_ID=2026-02_111478520",
            "title": "Post-Doctoral Position",
            "company": "ESSEC Business School",
            "locations": [
                {
                    "name": "Cergy, Ile de France, FRANCE",
                    "city": "Cergy",
                    "region": "Ile de France",
                },
                {"name": "Paris, FRANCE", "city": "Paris"},
            ],
            "date": "2026-11-16",
            "description": "ESSEC is offering a postdoctoral position in Economics",
            "posted_at": "2026-11-16",
            "site_data": {
                "section": "International: Other Academic (Part-time or Adjunct)",
                "salary_range": "Competitive",
                "status": "Position has been filled",
            },
        },
        {
            "site": "aea",
            "id": "2026-02_111477855",
            "url": "https://www.aeaweb.org/joe/listing.php?JOE_ID=2026-02_111477855",
            "title": "Assistant Professor/ Associate/ Full Professor - Economics",
            "company": "Ahmedabad University",
            "locations": [
                {"name": "AHMEDABAD, Gujarat, INDIA", "city": "AHMEDABAD", "region": "Gujarat"}
            ],
            "date": "2026-10-02",
            "description": "Interdisciplinary & project-based learning.",
            "department": "Amrut Mody School of Management",
            "posted_at": "2026-10-02",
            "expires_at": "2027-07-31",
            "keywords": ["Microeconomics", "Energy & Environment Economics"],
            "site_data": {
                "section": "International: Full-Time Academic (Permanent, Tenure Track or Tenured)",
                "division": "Economics and Public Policy",
                "jel": ["A1", "F"],
            },
        },
    ]
    assert "skipping malformed aea posting" in caplog.text
    page, export = fetcher.requests
    assert parse_qs(urlsplit(page).query) == {
        "ListingsForm[lpp]": ["5000"],
        "ListingsForm[listings_order_by]": ["date_posted_a"],
        "ListingsForm[keyword_search]": ["labor"],
        "ListingsForm[section][0]": ["5"],
        "ListingsForm[section][1]": ["2a"],
        # The heading 4 brings its subsections and 2a only itself, and 4b and 5, each selected
        # twice, go once.
        "ListingsForm[section][2]": ["4"],
        "ListingsForm[section][3]": ["4a"],
        "ListingsForm[section][4]": ["4b"],
    }
    assert export == "https://www.aeaweb.org/joe/resultset_output.php?mode=full_xml&q=eNplj0EKwkAM"


def test_a_search_sends_jel_codes_and_a_date_range():
    fetcher = PagedFetcher([PAGE, EXPORT])
    asyncio.run(aea.search(fetcher, jel=["j", "h"], max_age_hours=48))
    sent = parse_qs(urlsplit(fetcher.requests[0]).query)
    assert sent["ListingsForm[jel][0]"] == ["J"]
    assert sent["ListingsForm[jel][1]"] == ["H"]
    assert sent["ListingsForm[recent_only][0][option]"] == ["date_range"]
    since, until = (
        datetime.strptime(sent[f"ListingsForm[recent_only][0][{end}]"][0], "%m/%d/%Y")
        for end in ("from", "to")
    )
    assert since < until


def test_a_search_returns_nothing_for_no_match_and_stops_on_a_changed_page():
    # A search that matches nothing gets a page without listings or an export: one request.
    empty = PAGE.partition('<a href="/joe/resultset')[0] + "</body></html>"
    fetcher = PagedFetcher([empty])
    assert asyncio.run(aea.search(fetcher, query="nothing")) == []
    assert len(fetcher.requests) == 1
    # A page JOE changed, or one it serves in place of the listings, would otherwise lose listings,
    # their dates, or all of them without a word.
    for page, reason in (
        (PAGE.replace("resultset_output.php?mode=full_xml", "elsewhere.php"), "links no export"),
        (PAGE.replace("listing-item-header-title", "renamed"), "shows no posted dates"),
        (PAGE.replace('id="ListingsForm"', 'id="Maintenance"'), "holds no listings form"),
        (PAGE.replace("11/16/2026", "November 16"), "is not MM/DD/YYYY"),
        (
            PAGE.replace('href="/joe/resultset', 'href="https://[broken/joe/resultset'),
            "Invalid IPv6",
        ),
    ):
        with pytest.raises(Stopped, match=reason):
            asyncio.run(aea.search(PagedFetcher([page])))
