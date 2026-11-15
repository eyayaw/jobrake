"""Personio XML feed tests: parsing, the language fallback, and the stops."""

import asyncio

import pytest
from fakes import StubFetcher, network_down, not_found, ok

from jobrake import Stopped, check, scrape
from jobrake.sites import personio

# Positions from the feeds of tado and gesis, fetched 2026-11-15, trimmed to one short block of
# description each. The GESIS block has a blank name, as all of that board's first blocks do. The
# GESIS position also gains an empty block, as some feeds carry, a trailing space in its recruiting
# category, as 117 of 2,369 measured positions had, and an everphone position's monthly salary,
# which has no maximum.
WERKSTUDENT = """<position>
    <id>2840027</id>
    <subcompany>tado GmbH</subcompany>
    <office>Germany - Munich</office>
    <department>Finance</department>
    <recruitingCategory>People &amp; Culture</recruitingCategory>
    <name>Werkstudent:in Accounting (m/w/d)</name>
    <jobDescriptions>
        <jobDescription>
            <name>Was erwartet dich bei uns</name>
            <value><![CDATA[<p><strong>Standort</strong>: München</p>]]></value>
        </jobDescription>
    </jobDescriptions>
    <employmentType>intern</employmentType>
    <seniority>student</seniority>
    <schedule>part-time</schedule>
    <keywords>Werkstudent:in,Accounting</keywords>
    <occupation>bookkeeping</occupation>
    <occupationCategory>accounting_and_finance</occupationCategory>
    <createdAt>2026-10-13T09:59:49+00:00</createdAt>
</position>"""

INITIATIVE = """<position>
    <id>1896153</id>
    <subcompany>GESIS &#8211; Leibniz-Institut für Sozialwissenschaften e.V.</subcompany>
    <office>Mannheim</office>
    <additionalOffices>
        <office>Köln</office>
    </additionalOffices>
    <department>Initiativbewerbung</department>
    <recruitingCategory>Initiativ </recruitingCategory>
    <name>Initiativbewerbung</name>
    <jobDescriptions>
        <jobDescription>
            <name>  </name>
            <value><![CDATA[Der perfekte Job ist noch nicht dabei?]]></value>
        </jobDescription>
        <jobDescription>
            <name>Kontakt</name>
            <value>
            </value>
        </jobDescription>
    </jobDescriptions>
    <employmentType>permanent</employmentType>
    <seniority>entry-level</seniority>
    <schedule>full-or-part-time</schedule>
    <occupation>other</occupation>
    <occupationCategory>other</occupationCategory>
    <createdAt>2025-01-07T11:43:43+00:00</createdAt>
    <salaryInformation>
        <min>2410.00</min>
        <currencySymbol>€</currencySymbol>
        <currencyCode>EUR</currencyCode>
        <type>monthly</type>
    </salaryInformation>
</position>"""


def minimal(posting_id: str, title: str, *blocks: str) -> str:
    return f"""<position>
    <id>{posting_id}</id>
    <office>Germany - Munich</office>
    <name>{title}</name>
    <jobDescriptions>{"".join(blocks)}</jobDescriptions>
    <createdAt>2026-01-22T09:48:25+00:00</createdAt>
</position>"""


def block(name: str, value: str) -> str:
    return f"<jobDescription><name>{name}</name><value><![CDATA[{value}]]></value></jobDescription>"


def feed(*positions: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<workzag-jobs>'
        + "".join(positions)
        + "</workzag-jobs>"
    )


def test_a_feed_parses_into_records():
    fetcher = StubFetcher({"/xml": ok(feed(WERKSTUDENT, INITIATIVE))})
    assert asyncio.run(personio.search(fetcher, board=" Tado ")) == [
        {
            "site": "personio",
            "id": "2840027",
            "url": "https://tado.jobs.personio.de/job/2840027",
            "title": "Werkstudent:in Accounting (m/w/d)",
            "company": "tado GmbH",
            "locations": [{"name": "Germany - Munich"}],
            "date": "2026-10-13",
            "description": "Was erwartet dich bei uns\nStandort: München",
            "department": "Finance",
            "employment_type": "internship",
            "posted_at": "2026-10-13T09:59:49+00:00",
            "site_data": {
                "recruitingCategory": "People & Culture",
                "seniority": "student",
                "schedule": "part-time",
                "keywords": "Werkstudent:in,Accounting",
                "occupation": "bookkeeping",
                "occupationCategory": "accounting_and_finance",
            },
        },
        {
            "site": "personio",
            "id": "1896153",
            "url": "https://tado.jobs.personio.de/job/1896153",
            "title": "Initiativbewerbung",
            "company": "GESIS \N{EN DASH} Leibniz-Institut für Sozialwissenschaften e.V.",
            "locations": [{"name": "Mannheim"}, {"name": "Köln"}],
            "date": "2025-01-07",
            "description": "Der perfekte Job ist noch nicht dabei?",
            "department": "Initiativbewerbung",
            "employment_type": "permanent",
            "salary_min": 2410.0,
            "salary_currency": "EUR",
            "salary_period": "MONTH",
            "posted_at": "2025-01-07T11:43:43+00:00",
            "site_data": {
                "recruitingCategory": "Initiativ",
                "seniority": "entry-level",
                "schedule": "full-or-part-time",
                "occupation": "other",
                "occupationCategory": "other",
            },
        },
    ]
    # Every posting has a description, so no other language is read.
    assert fetcher.requests == ["https://tado.jobs.personio.de/xml"]


def test_a_posting_without_a_description_comes_from_the_first_language_that_has_one():
    lead = "Team Lead Accounting (m/f/d)"
    fetcher = StubFetcher(
        {
            "language=en": ok(
                feed(
                    WERKSTUDENT.replace("(m/w/d)", "(m/f/d)"),
                    minimal(
                        "2502124", lead, block("What you'll be up to", "<p>Close the books.</p>")
                    ),
                    minimal("1", "Accountant (m/f/d)"),
                )
            ),
            "language=de": ok(feed(minimal("1", "Buchhalter:in", block("Aufgaben", "Buchen.")))),
            "/xml": ok(feed(WERKSTUDENT, minimal("2502124", lead), minimal("1", "Buchhalter:in"))),
        }
    )
    jobs = asyncio.run(personio.search(fetcher, board="tado"))
    # A posting the default feed describes keeps its own title and description.
    assert [(job["id"], job["title"], job["description"]) for job in jobs] == [
        (
            "2840027",
            "Werkstudent:in Accounting (m/w/d)",
            "Was erwartet dich bei uns\nStandort: München",
        ),
        ("2502124", lead, "What you'll be up to\nClose the books."),
        ("1", "Buchhalter:in", "Aufgaben\nBuchen."),
    ]
    assert fetcher.requests == [
        "https://tado.jobs.personio.de/xml",
        "https://tado.jobs.personio.de/xml?language=en",
        "https://tado.jobs.personio.de/xml?language=de",
    ]


def test_a_failed_language_request_keeps_the_postings_read():
    fetcher = StubFetcher(
        {"language=en": network_down(), "/xml": ok(feed(WERKSTUDENT, minimal("2502124", "Lead")))}
    )
    with pytest.raises(
        Stopped, match=r"reset\. Kept the 2 postings read, 1 without a description$"
    ) as stop:
        asyncio.run(personio.search(fetcher, board="tado"))
    assert [job["id"] for job in stop.value.partial] == ["2840027", "2502124"]
    assert "description" not in stop.value.partial[1]


def test_a_board_without_a_feed_stops_with_nothing():
    fetcher = StubFetcher({"/xml": not_found()})
    with pytest.raises(
        Stopped, match=r"^personio serves no feed for board 'acme', so the board"
    ) as stop:
        asyncio.run(personio.search(fetcher, board="acme"))
    assert stop.value.partial == []


@pytest.mark.parametrize(
    ("body", "error"),
    [("<!DOCTYPE html><p>Wartung<br></p>", "ParseError"), ("<rss/>", "TypeError")],
)
def test_a_body_that_is_not_the_feed_is_unreadable(body, error):
    with pytest.raises(
        Stopped, match=rf"^personio sent a response this version cannot read \({error}"
    ):
        asyncio.run(personio.search(StubFetcher({"/xml": ok(body)}), board="tado"))


@pytest.mark.parametrize("board", ["tado.jobs.personio.de", "\N{LATIN SMALL LETTER LONG S}tado"])
def test_a_board_that_is_not_a_subdomain_is_refused_before_any_request(board):
    with pytest.raises(ValueError, match=r"is not a Personio subdomain"):
        check("personio", board=board)
    fetcher = StubFetcher({})
    with pytest.raises(ValueError, match=r"Pass the name before \.jobs\.personio\.de"):
        asyncio.run(scrape("personio", board=board, fetcher=fetcher))
    assert fetcher.requests == []
