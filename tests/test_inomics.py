"""INOMICS search answer and job page parsing tests."""

import asyncio
import json
from urllib.parse import parse_qs, urlsplit

import pytest
from fakes import DEEP_JSON, StubFetcher, ok

from jobrake import Stopped
from jobrake.fetchkit import FetchResult
from jobrake.sites import inomics


def _card(href: str, badge: str, info: str, attendance: str = "") -> str:
    return (
        f'<li><a class="post-link" href="{href}"><ul class="psh"><li><span class="type-badge">'
        f"{badge}</span></li>{attendance}<li class='since'>Posted 1 week ago</li></ul>"
        f"<h2> Title of {href[-7:]} </h2>"
        f'<span class="informations">{info}</span></a></li>'
    )


# Cards as /ajax/filter served them on 2026-11-17, trimmed: a hybrid job in one city, and a job
# with two employers and a country alone.
CARDS = [
    _card(
        "/job/postdoctoral-researcher-in-political-economy-1555720",
        " Postdoc Job, PhD Candidate Job ",
        '<span content="Postdoctoral Researcher"></span><span content="05-11-2026"></span> At'
        ' <span class="location">Saarland University</span> <span> in <span class="location'
        ' bold"> <span>Saarbrücken</span>, <span>Germany</span> </span></span>',
        '<li class="attendance"> (Hybrid) </li>',
    ),
    _card(
        "/job/tenure-track-faculty-economics-1555749",
        "Professor Job",
        '<span content="13-11-2026"></span> At <span class="location">Villanova University</span>'
        ' and <span class="location">Villanova School of Business</span> <span> in'
        ' <span class="location bold"> <span>United States</span> </span></span>',
    ),
]


def _answer(*blocks: str, total: int) -> str:
    """Return a search answer whose content arrives in ``blocks``, as trendingPage sends it."""
    content = [
        {
            "command": "insert",
            "method": "html" if i == 0 else "append",
            "selector": "#block-venice-content",
            "data": f'<ul class="posts">{block}</ul>',
        }
        for i, block in enumerate(blocks)
    ]
    count = f'<span id="filter-count-number">{total}</span>'
    count_command = {"command": "insert", "selector": "#filter-count-number", "data": count}
    return json.dumps([{"command": "settings", "settings": {}}, *content, count_command])


_LD = '<script type="application/ld+json">'
# A job page with both of its schema.org blocks, in the order the site serves them: the ISO block
# with the day the job was entered and its city, then the block with the day the cards show and the
# country code (job 1555182, 2026-11-17), and the page's own description.
PAGE = (
    f'{_LD}{{"@type": "RegisterAction"}}</script>'
    f'{_LD}{{"@type": "JobPosting", "title": "Assistant Professor",'
    ' "datePosted": "2026-09-21T11:23:44Z", "validThrough": "2026-11-29T22:59:59Z",'
    ' "hiringOrganization": {"name": "IWH"}, "description": "An excerpt", "jobLocation":'
    ' {"address": {"addressLocality": "Magdeburg", "addressRegion": "Saxony-Anhalt"}}}</script>'
    f'{_LD}{{"@type": "JobPosting", "title": "Assistant Professor", "datePosted": "2026/10/22",'
    ' "validThrough": "2026/11/29", "hiringOrganization": {"name": null}, "jobLocation":'
    ' {"address": {"addressLocality": "Magdeburg, Germany", "addressCountry": "DE"}}}</script>'
    '<div class="post-description"><p>The faculty seeks</p><ul><li>a labor economist</li></ul>'
    "</div>"
)
# The page of a job INOMICS also lists as a scholarship: one block, which names the city and region
# and no country (job 1555359, 2026-11-18).
SCHOLARSHIP = (
    f'{_LD}{{"@type": "EducationalOccupationalProgram", "title": "Postdoctoral scholarship",'
    ' "datePosted": "2026-10-02T07:30:06Z", "jobLocation": {"address": {"addressLocality":'
    ' "Umeå", "addressRegion": "Västerbotten"}}}</script>'
    '<div class="post-description"><p>Umeå University offers</p></div>'
)


def test_a_search_reads_every_block_of_cards_and_sends_its_filters():
    fetcher = StubFetcher({"ajax/filter": ok(_answer(*CARDS, total=2))})
    jobs = asyncio.run(
        inomics.search(
            fetcher,
            query=" labor ",
            country="deu",  # an alpha-3 code reaches INOMICS as its alpha-2 code
            category=["Postdoc", "PROFESSOR", " postdoc "],
            jel=["j", "E", "J"],
            results=21,
        )
    )
    assert jobs == [
        {
            "site": "inomics",
            "id": "1555720",
            "url": "https://inomics.com/job/1555720",
            "title": "Title of 1555720",
            "company": "Saarland University",
            "locations": [{"name": "Saarbrücken, Germany", "city": "Saarbrücken"}],
            "date": "2026-11-05",
            "workplace_type": "hybrid",
            "posted_at": "2026-11-05",
            "site_data": {"types": ["Postdoc Job", "PhD Candidate Job"]},
        },
        {
            "site": "inomics",
            "id": "1555749",
            "url": "https://inomics.com/job/1555749",
            "title": "Title of 1555749",
            "company": "Villanova University",
            "locations": [{"name": "United States"}],
            "date": "2026-11-13",
            "posted_at": "2026-11-13",
            "site_data": {"types": ["Professor Job"]},
        },
    ]
    [request] = fetcher.requests
    # A repeated value goes once, and 21 results need two blocks of 20 cards.
    assert parse_qs(urlsplit(request).query) == {
        "job": ["job-postdoc,job-professor"],
        "orderBy": ["relevance"],
        "trendingPage": ["2"],
        "textsearch": ["labor"],
        "country": ["DE"],
        "economics": ["labordemographiceconomics,macroeconomicsmonetary"],
    }
    assert fetcher.headers[0] == {"Accept": "application/json"}


def test_a_search_keeps_the_first_results_and_stops_when_the_site_sends_fewer_than_it_counts():
    fetcher = StubFetcher({"ajax/filter": ok(_answer("".join(CARDS[:2]), total=40))})
    jobs = asyncio.run(inomics.search(fetcher, results=1))
    assert [job["id"] for job in jobs] == ["1555720"]
    assert "job=job&" in fetcher.requests[0]
    with pytest.raises(Stopped, match="counted 40 postings but sent 2") as caught:
        asyncio.run(inomics.search(fetcher, results=30))
    assert [job["id"] for job in caught.value.partial] == ["1555720", "1555749"]


def test_an_answer_without_its_count_stops_the_search():
    answer = [{"command": "insert", "selector": "#block-venice-content", "data": ""}]
    fetcher = StubFetcher({"ajax/filter": ok(json.dumps(answer))})
    with pytest.raises(Stopped) as caught:
        asyncio.run(inomics.search(fetcher))
    assert caught.value.partial == []


def test_details_date_a_posting_by_its_slash_dated_block_and_fill_the_card_from_the_page():
    card = _card(
        "/job/assistant-professor-w1-financial-economics-1555182",
        "Assistant Professor / Lecturer Job",
        '<span content="22-10-2026"></span> At <span class="location">Halle Institute for Economic'
        ' Research</span> <span> in <span class="location bold"> <span>Magdeburg</span>,'
        " <span>Germany</span> </span></span>",
    )
    fetcher = StubFetcher({"ajax/filter": ok(_answer(card, total=1)), "/job/1555182": ok(PAGE)})
    [job] = asyncio.run(inomics.search(fetcher, details=True))
    assert job["date"] == job["posted_at"] == "2026-10-22"
    assert job["expires_at"] == "2026-11-29"
    assert job["company"] == "IWH"
    assert job["description"] == "The faculty seeks\na labor economist"
    assert job["locations"] == [
        {
            "name": "Magdeburg, Germany",
            "city": "Magdeburg",
            "region": "Saxony-Anhalt",
            "country_code": "DE",
        }
    ]


def test_postings_reads_both_page_types_and_leaves_out_a_page_it_cannot_read():
    # JSON-LD allows a block to be an array and a type to be a list, as this page's RegisterAction
    # has here. A script that does not parse, or that nests deeper than json.loads reads, leaves the
    # page's posting blocks readable.
    arrayed = f"{_LD}{{</script>{_LD}{DEEP_JSON}</script>" + PAGE.replace(
        '{"@type": "RegisterAction"}', '[{"@type": ["RegisterAction", "Thing"]}]'
    )
    fetcher = StubFetcher(
        {
            "/job/1555182": ok(arrayed),
            "/job/1555359": ok(SCHOLARSHIP),
            "/job/1000000": FetchResult(url="stub", status=410),
            # A page whose markup changed: its block remains, its description element is gone.
            "/job/1555749": ok(PAGE.partition('<div class="post-description">')[0]),
        }
    )
    found = asyncio.run(
        inomics.postings(
            fetcher,
            [
                "https://inomics.com/job/assistant-professor-w1-financial-economics-1555182",
                "https://inomics.com/job/1555359",
                "https://www.inomics.com/job/1000000",
                "https://inomics.com/job/1555749",
            ],
        )
    )
    assert "https://inomics.com/job/1555749" not in found
    job, scholarship, gone = found.values()
    assert job is not None
    assert (job["id"], job["url"], job["title"], job["company"]) == (
        "1555182",
        "https://inomics.com/job/1555182",
        "Assistant Professor",
        "IWH",
    )
    assert scholarship is not None
    assert (scholarship["date"], scholarship["locations"]) == (
        "2026-10-02",
        [{"name": "Umeå, Västerbotten", "city": "Umeå", "region": "Västerbotten"}],
    )
    assert gone is None
