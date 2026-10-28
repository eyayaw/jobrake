"""The JSON response reading the sites share, and how each board site names an unknown board."""

import asyncio

import pytest
from fakes import StubFetcher, network_down, not_found, ok

from jobrake import Stopped
from jobrake.models import make_job
from jobrake.sites import SITES
from jobrake.sites.responses import json_list, parse_postings, read_json

UNKNOWN = "acme has no board 'x'"
UNREADABLE = r"^acme sent a response this version cannot read \("


@pytest.mark.parametrize(
    ("response", "options", "message"),
    [
        (not_found(), {"board": "x", "unknown": UNKNOWN}, f"^{UNKNOWN}$"),
        (not_found(), {"board": "x"}, r"^acme search of board 'x' stopped: HTTP 404$"),
        (network_down(), {}, "^acme search stopped: connection reset$"),
        (ok("not JSON"), {}, UNREADABLE + "JSONDecodeError"),
        (ok("[]"), {}, UNREADABLE + "TypeError"),
        (ok("{}"), {}, UNREADABLE + r"KeyError\('jobs'\)"),
        (ok('{"jobs": {}}'), {}, UNREADABLE + r"TypeError\('jobs is a dict, not a list'\)"),
    ],
)
def test_a_failed_or_unreadable_response_stops_with_nothing(response, options, message):
    with pytest.raises(Stopped, match=message) as stop:
        read_json(response, lambda page: json_list(page, "jobs"), site="acme", **options)
    assert stop.value.partial == []


def test_a_failed_page_keeps_and_counts_the_postings_before_it():
    collected = [make_job(site="acme", id="1", url="https://acme.test/1")]
    for response in (network_down(), ok("not JSON")):
        with pytest.raises(Stopped, match=r"\. Kept the 1 posting collected$") as stop:
            read_json(response, json_list, site="acme", partial=collected)
        assert stop.value.partial == collected


def test_a_malformed_posting_costs_only_itself(caplog):
    def parse(posting):
        return make_job(site="acme", id=posting.get("id"), url=posting.get("url"))

    items = [{"id": None}, "not a posting", {"id": "1", "url": "https://acme.test/1"}]
    assert [job["id"] for job in parse_postings(items, parse, site="acme")] == ["1"]
    skipped = [r.name for r in caplog.records if "malformed acme posting" in r.getMessage()]
    assert skipped == ["jobrake.sites.acme"] * 2


@pytest.mark.parametrize("site", ["ashby", "greenhouse", "lever", "workable"])
def test_a_board_site_names_an_unknown_board(site):
    fetcher = StubFetcher({"": not_found()})
    with pytest.raises(Stopped, match=rf"^{site} has no board 'acme/x'.*\. Pass the token") as stop:
        asyncio.run(SITES[site].search(fetcher, board="acme/x"))
    assert stop.value.partial == []
    assert fetcher.requests
    assert all("/acme%2Fx" in url for url in fetcher.requests)
