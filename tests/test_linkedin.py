"""LinkedIn guest-search parsing and pagination tests."""

import asyncio
import heapq
import importlib
import itertools
import json
import logging
from urllib.parse import parse_qs, urlsplit

import pytest
from fakes import PagedFetcher, StubFetcher, network_down, not_found, ok, rate_limited

from jobrake import Stopped, cache
from jobrake.fetchkit import FetchResult
from jobrake.models import IDENTITY_FIELDS, SUMMARY_FIELDS, JobDict
from jobrake.sites import linkedin
from jobrake.sites.linkedin import client


@pytest.fixture
def unlimited(monkeypatch):
    """Age every fabric and every turn, so no request waits."""
    # Each read of the clock moves it PACE, so no fabric or turn is too recent to send on.
    monkeypatch.setattr(client, "monotonic", itertools.count(0.0, client.PACE).__next__)


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


def test_linkedin_parses_cards_and_dedups_by_posting_id(unlimited):
    html = (
        linkedin_card("role-111")
        + linkedin_card("222")
        + linkedin_card("other-111")
        + linkedin_card("search")
    )
    fetcher = StubFetcher({"seeMoreJobPostings": ok(html)})
    jobs = asyncio.run(linkedin.search(fetcher, query="economist", location="Seattle", results=3))
    assert [j["url"] for j in jobs] == [
        "https://www.linkedin.com/jobs/view/role-111",
        "https://www.linkedin.com/jobs/view/222",
    ]
    assert jobs[0]["id"] == "111"
    assert jobs[0]["title"] == "Economist"
    assert jobs[0]["company"] == "Acme"
    assert jobs[0]["location"] == "Seattle, WA"
    assert jobs[0]["date"] == "2026-08-01"
    # search cards carry no detail fields
    assert set(jobs[0]) == {*IDENTITY_FIELDS, *SUMMARY_FIELDS}


def test_pagination_advances_by_raw_page_size(unlimited):
    fetcher = PagedFetcher(
        [
            linkedin_card("111") + linkedin_card("222"),
            linkedin_card("222") + linkedin_card("333"),
            linkedin_card("444"),
        ]
    )
    jobs = asyncio.run(linkedin.search(fetcher, query="x", location="Seattle", results=4))

    assert [job["id"] for job in jobs] == ["111", "222", "333", "444"]
    assert all("keywords=x" in url for url in fetcher.requests)
    assert "start=4" in fetcher.requests[2]


def test_pagination_survives_a_duplicate_only_page(unlimited):
    fetcher = PagedFetcher(
        [
            linkedin_card("111") + linkedin_card("222"),
            linkedin_card("111") + linkedin_card("222"),
            linkedin_card("333"),
            "",
        ]
    )
    jobs = asyncio.run(linkedin.search(fetcher, query="x", location="Seattle", results=10))

    assert [job["id"] for job in jobs] == ["111", "222", "333"]
    assert "start=4" in fetcher.requests[2]  # overlapped offsets still advance


def test_pagination_counts_unparsable_cards_toward_the_offset(unlimited):
    unparsable = '<div class="base-search-card"><span>no link</span></div>'
    fetcher = PagedFetcher([linkedin_card("111") + unparsable, ""])
    jobs = asyncio.run(linkedin.search(fetcher, query="x", location="Seattle", results=10))

    assert [job["id"] for job in jobs] == ["111"]
    assert "start=2" in fetcher.requests[1]


def test_linkedin_persistent_429_stops_the_search(unlimited, monkeypatch):
    monkeypatch.setattr(client, "RETRY_DELAY", 0)
    fetcher = StubFetcher({"seeMoreJobPostings": rate_limited()})
    with pytest.raises(Stopped, match="HTTP 429") as stop:
        asyncio.run(linkedin.search(fetcher, query="x", location="Seattle"))
    assert stop.value.partial == []
    assert len(fetcher.requests) == 1 + client.RETRIES  # the retries, then give up


def paced(fetcher, name="x"):
    """Send one paced request through the company lookup, which reads ``[]`` as no match."""
    return linkedin.companies(fetcher, name)


class Routing(StubFetcher):
    """Answer an unpinned request from the next fabric in ``fabrics``, a pinned one from its own."""

    def __init__(self, fabrics):
        super().__init__({"linkedin.com": ok("[]")})
        self.fabrics = fabrics

    async def fetch(self, url, *, headers=None, json=None):
        cookie = (headers or {})["cookie"]
        fabric = cookie[6:-1] if cookie != "lidc=" else self.fabrics.pop(0)
        result = await super().fetch(url, headers=headers)
        result.headers = {
            "x-li-fabric": fabric,
            "set-cookie": f'bcookie="x"; Path=/, lidc="{fabric}"; Path=/',
        }
        return result


def test_pacing_pins_each_request_to_a_fabric_in_turn(unlimited):
    # A new process starts pinned to the fabrics in FABRICS.
    fetcher = StubFetcher({"linkedin.com": ok("[]")})
    for _ in range(3):
        asyncio.run(paced(fetcher))
    assert [h["cookie"] for h in fetcher.headers] == [f"lidc={c}" for c in client.FABRICS.values()]

    client.POOL.known = {}
    fetcher = Routing(["prod-a", "prod-b", "prod-a", "prod-c"])
    for _ in range(8):
        assert asyncio.run(paced(fetcher)) == []

    cookies = [h["cookie"] for h in fetcher.headers]
    # Unpinned until three fabrics are known, then each fabric in turn, least
    # recently used first: prod-a answered the third request, after prod-b.
    assert cookies[:4] == ["lidc="] * 4
    assert cookies[4:] == ['lidc="prod-b"', 'lidc="prod-a"', 'lidc="prod-c"', 'lidc="prod-b"']


def test_turns_open_a_pace_apart_unpinned_and_shared_once_pinned(monkeypatch):
    monkeypatch.setattr(client, "monotonic", lambda: 0.0)
    pool = client.Fabrics()
    pool.known = {}  # discovery: every request goes out unpinned
    assert pool.pick(set()) == (None, 0.0)
    assert pool.pick(set()) == (None, client.PACE)
    pool = client.Fabrics()  # three fabrics known: they share the pace
    assert pool.pick(set()) == ("prod-lor1", 0.0)
    assert pool.pick(set()) == ("prod-ltx1", pytest.approx(client.PACE / 3))


def test_pacing_drops_a_pin_whose_request_lands_elsewhere(unlimited, monkeypatch):
    monkeypatch.setattr(client, "DISCOVERY", 1)
    client.POOL.known = {name: f'"{name}"' for name in ("prod-a", "prod-b", "prod-c")}
    client.POOL.unpinned = 1  # discovery is spent

    class Rerouting(Routing):
        async def fetch(self, url, *, headers=None, json=None):
            result = await super().fetch(url, headers=headers)
            if (headers or {})["cookie"] == 'lidc="prod-b"':
                result.headers = {"x-li-fabric": "prod-a"}
            return result

    fetcher = Rerouting(["prod-d"])
    for _ in range(5):
        asyncio.run(paced(fetcher))
    # prod-b took the second turn and never another. Its drop restarted
    # discovery, which found prod-d; the rest go on least recently used first.
    assert sorted(client.POOL.known) == ["prod-a", "prod-c", "prod-d"]
    cookies = [h["cookie"] for h in fetcher.headers]
    assert cookies == ['lidc="prod-a"', 'lidc="prod-b"', "lidc=", 'lidc="prod-c"', 'lidc="prod-a"']


def test_a_concurrent_request_waits_for_the_next_turn(monkeypatch):
    monkeypatch.setattr(client, "DISCOVERY", 1)
    client.POOL.known = {name: f'"{name}"' for name in ("prod-a", "prod-b")}
    now, sleeps, real_sleep = [0.0], [], asyncio.sleep

    async def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds
        await real_sleep(0)

    monkeypatch.setattr(client, "monotonic", lambda: now[0])
    monkeypatch.setattr(client.asyncio, "sleep", sleep)
    fetcher = Routing(["prod-c"])

    async def two_callers():
        await asyncio.gather(paced(fetcher), paced(fetcher))

    asyncio.run(two_callers())
    # The first caller's unpinned request takes the turn and finds prod-c. It
    # may land on any fabric, so the second waits a full PACE and then chooses
    # among three.
    assert [h["cookie"] for h in fetcher.headers] == ["lidc=", 'lidc="prod-a"']
    assert sleeps == [client.PACE]


class QueuedOnOneFabric:
    """Requests that wait on prod-a, the one fabric known, under a clock the test moves."""

    def __init__(self, monkeypatch):
        monkeypatch.setattr(client, "DISCOVERY", 0)  # no unpinned requests to find more fabrics
        client.POOL.known = {"prod-a": '"prod-a"'}
        self.now = 0.0
        self.parked: list[asyncio.Future[None]] = []  # sleepers, woken only by wake_all
        self.sends: list[float] = []
        self.yield_ = asyncio.sleep
        monkeypatch.setattr(client, "monotonic", lambda: self.now)
        monkeypatch.setattr(client.asyncio, "sleep", self.sleep)

    async def sleep(self, seconds):
        waiter = asyncio.get_running_loop().create_future()
        self.parked.append(waiter)
        await waiter

    async def fetch(self, url, *, headers=None, json=None):
        self.sends.append(self.now)
        return FetchResult(url=url, status=200, text="[]", headers={"x-li-fabric": "prod-a"})

    async def close(self):
        pass

    def request(self):
        return asyncio.ensure_future(paced(self))

    async def wake_all(self):
        waiters, self.parked = self.parked, []
        for waiter in waiters:
            waiter.set_result(None)
        await self.yield_(0)


def test_waiters_on_a_fabric_stay_paced_after_an_event_loop_stall(monkeypatch):
    queue = QueuedOnOneFabric(monkeypatch)

    async def run():
        requests = [queue.request() for _ in range(7)]
        await queue.yield_(0)  # one sends at once, six wait
        queue.now = 10 * client.PACE  # a stall: every wait ran out while the loop was blocked
        while queue.parked:
            await queue.wake_all()
            queue.now += client.PACE
        await asyncio.gather(*requests)

    asyncio.run(run())
    assert len(queue.sends) == 7
    assert all(b - a >= client.PACE for a, b in itertools.pairwise(queue.sends))


def test_waiters_take_a_new_turn_when_discovery_starts(monkeypatch):
    queue = QueuedOnOneFabric(monkeypatch)

    async def run():
        requests = [queue.request() for _ in range(4)]
        await queue.yield_(0)  # one sends at once, three wait
        # With one fabric known and requests to spare, discovery starts.
        monkeypatch.setattr(client, "DISCOVERY", 12)
        while queue.parked:
            queue.now += client.PACE
            await queue.wake_all()
        await asyncio.gather(*requests)

    asyncio.run(run())
    assert len(queue.sends) == 4
    # each send has a turn of its own
    assert all(b - a >= client.PACE for a, b in itertools.pairwise(queue.sends))


def test_an_unpinned_request_waits_until_every_fabric_is_paced(monkeypatch):
    now = [1.5]
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    monkeypatch.setattr(client, "monotonic", lambda: now[0])
    monkeypatch.setattr(client.asyncio, "sleep", sleep)
    # A reroute left one fabric known, so discovery runs. prod-b took a
    # request 0.5 s ago, and the unpinned request might land there.
    client.POOL.known = {"prod-a": '"prod-a"'}
    client.POOL.sent = {"prod-a": 0.0, "prod-b": 1.0}
    fetcher = StubFetcher({"linkedin.com": ok("[]")})
    asyncio.run(paced(fetcher))
    assert [h["cookie"] for h in fetcher.headers] == ["lidc="]
    assert sleeps == [pytest.approx(client.PACE - 0.5)]


def test_a_retry_skips_the_fabric_that_refused_an_unpinned_attempt(unlimited):
    # Two fabrics are known, so discovery runs. The unpinned attempt lands on
    # prod-b, which refuses it without a new cookie, so discovery goes on.
    client.POOL.known = {name: f'"{name}"' for name in ("prod-a", "prod-b")}

    class Refusing(StubFetcher):
        async def fetch(self, url, *, headers=None, json=None):
            cookie = (headers or {})["cookie"]
            fabric = cookie[6:-1] if cookie != "lidc=" else "prod-b"
            result = rate_limited() if fabric == "prod-b" else ok("[]")
            result.headers = {"x-li-fabric": fabric}
            self.headers.append(headers or {})
            return result

    fetcher = Refusing({})
    assert asyncio.run(paced(fetcher)) == []
    assert [h["cookie"] for h in fetcher.headers] == ["lidc=", 'lidc="prod-a"']


def test_a_canceled_wait_leaves_the_fabric_free(monkeypatch):
    queue = QueuedOnOneFabric(monkeypatch)

    async def run():
        requests = [queue.request() for _ in range(3)]
        await queue.yield_(0)  # one sends at once, two wait
        for request in requests:
            request.cancel()
        await asyncio.gather(*requests, return_exceptions=True)
        queue.now = client.PACE
        late = queue.request()
        await queue.yield_(0)
        return late.done()

    assert asyncio.run(run())  # the next request sends PACE after the last real send
    assert queue.sends == [0.0, client.PACE]


def test_pacing_retries_a_refusal_on_an_untried_fabric(unlimited, monkeypatch):
    monkeypatch.setattr(client, "DISCOVERY", 0)  # discovery stops once a fabric is known
    sleeps = []

    async def recording_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(client.asyncio, "sleep", recording_sleep)
    client.POOL.known = {name: f'"{name}"' for name in ("prod-a", "prod-b")}

    class Refusing(StubFetcher):
        """prod-a refuses every request; prod-b answers unless ``answering`` is off."""

        answering = True

        async def fetch(self, url, *, headers=None, json=None):
            fabric = (headers or {})["cookie"][6:-1]
            result = ok("[]") if fabric == "prod-b" and self.answering else rate_limited()
            self.requests.append(url)
            self.headers.append(headers or {})
            result.headers = {**result.headers, "x-li-fabric": fabric}
            return result

    fetcher = Refusing({})
    assert asyncio.run(paced(fetcher)) == []
    assert [h["cookie"] for h in fetcher.headers] == ['lidc="prod-a"', 'lidc="prod-b"']
    assert sleeps == []  # the other fabric has its own budget

    # When both fabrics refuse, a retry that returns to one waits for the window.
    fetcher = Refusing({})
    fetcher.answering = False
    with pytest.raises(Stopped):
        asyncio.run(paced(fetcher))
    assert [h["cookie"][6:-1] for h in fetcher.headers] == ["prod-a", "prod-b"] * 2
    assert sleeps == [client.RETRY_DELAY] * 2

    # With no other fabric known, every retry waits for the window.
    sleeps.clear()
    client.POOL.known = {"prod-a": '"prod-a"'}
    fetcher = Refusing({})
    with pytest.raises(Stopped):
        asyncio.run(paced(fetcher))
    assert sleeps == [client.RETRY_DELAY] * client.RETRIES

    # While no fabric is known, every retry goes out unpinned without waiting.
    sleeps.clear()
    client.POOL.known = {}
    fetcher = Refusing({})
    with pytest.raises(Stopped):
        asyncio.run(paced(fetcher))
    assert [h["cookie"] for h in fetcher.headers] == ["lidc="] * (1 + client.RETRIES)
    assert sleeps == []


def test_concurrent_retries_try_each_fabric_once_and_keep_each_fabric_paced(monkeypatch):
    # Three callers share the pacer. Every fabric refuses the target request,
    # and the other two callers take the turns between its retries. Time is
    # virtual, so a sleep parks its caller until the driver moves the clock.
    monkeypatch.setattr(client, "DISCOVERY", 0)
    fabrics = ("prod-a", "prod-b", "prod-c")
    client.POOL.known = {name: f'"{name}"' for name in fabrics}
    clock, parked, order, real_sleep = 0.0, [], itertools.count(), asyncio.sleep

    async def sleep(seconds):
        waiter = asyncio.get_running_loop().create_future()
        heapq.heappush(parked, (clock + seconds, next(order), waiter))
        await waiter

    monkeypatch.setattr(client, "monotonic", lambda: clock)
    monkeypatch.setattr(asyncio, "sleep", sleep)
    sends: dict[str, list[float]] = {}  # send times per fabric
    target: list[str] = []  # the fabrics the target request went to

    class Refusing(StubFetcher):
        async def fetch(self, url, *, headers=None, json=None):
            fabric = (headers or {})["cookie"][6:-1]
            sends.setdefault(fabric, []).append(clock)
            if "query=target" in url:
                target.append(fabric)
            result = rate_limited() if "query=target" in url else ok("[]")
            result.headers = {**result.headers, "x-li-fabric": fabric}
            return result

    fetcher = Refusing({})

    async def caller(name):
        for i in range(6):
            await paced(fetcher, f"{name}{i}")

    async def drive():
        nonlocal clock
        tasks = [
            asyncio.ensure_future(paced(fetcher, "target")),
            asyncio.ensure_future(caller("b")),
            asyncio.ensure_future(caller("c")),
        ]
        await real_sleep(0)  # every caller runs until it sleeps or finishes
        while parked:
            wake, _, waiter = heapq.heappop(parked)
            clock = max(clock, wake)
            waiter.set_result(None)
            await real_sleep(0)
        return await asyncio.gather(*tasks, return_exceptions=True)

    refused, *_ = asyncio.run(drive())
    assert isinstance(refused, Stopped)
    assert len(target) == 1 + client.RETRIES
    assert sorted(target[:3]) == list(fabrics)  # all three before any again
    for fabric, times in sends.items():
        assert all(b - a >= client.PACE for a, b in itertools.pairwise(times)), fabric


def test_linkedin_keeps_collected_jobs_after_a_later_page_failure(unlimited):
    class DownAfterFirst(StubFetcher):
        async def fetch(self, url, *, headers=None, json=None):
            if self.requests:
                self.requests.append(url)
                return network_down()
            return await super().fetch(url, headers=headers)

    fetcher = DownAfterFirst(
        {"seeMoreJobPostings": ok(linkedin_card("111") + linkedin_card("222"))}
    )
    with pytest.raises(Stopped, match=r"connection reset\. Kept the 2 postings") as stop:
        asyncio.run(linkedin.search(fetcher, query="x", location="Seattle", results=5))
    assert [j["id"] for j in stop.value.partial] == ["111", "222"]  # the first page survives


def test_warns_on_empty_first_page(unlimited, caplog):
    fetcher = StubFetcher({"seeMoreJobPostings": ok("<!DOCTYPE html>\n<!---->")})
    with caplog.at_level(logging.WARNING, logger="jobrake.sites.linkedin"):
        jobs = asyncio.run(linkedin.search(fetcher, query="x", location="Amsterdam"))
    assert jobs == []
    assert any("location" in record.message for record in caplog.records)


def test_warns_when_the_offset_cap_cuts_a_search_short(unlimited, caplog, monkeypatch):
    # linkedin.search is the exported function, so import its module directly
    search_module = importlib.import_module("jobrake.sites.linkedin.search")
    monkeypatch.setattr(search_module, "MAX_START", 2)
    fetcher = PagedFetcher([linkedin_card("111"), linkedin_card("222")])
    with caplog.at_level(logging.WARNING, logger="jobrake.sites.linkedin"):
        jobs = asyncio.run(linkedin.search(fetcher, query="x", location="Seattle", results=5))
    assert [j["id"] for j in jobs] == ["111", "222"]
    assert any("offset" in record.message for record in caplog.records)


def test_no_warning_when_pagination_simply_ends(unlimited, caplog):
    fetcher = PagedFetcher([linkedin_card("111"), ""])
    with caplog.at_level(logging.WARNING, logger="jobrake.sites.linkedin"):
        jobs = asyncio.run(linkedin.search(fetcher, query="x", location="Seattle", results=5))
    assert [j["id"] for j in jobs] == ["111"]  # a card-less page: normal end
    assert caplog.records == []


def test_companies_lists_usable_candidates_in_linkedin_order(unlimited):
    hits = [
        {"id": " 1173 ", "displayName": " ABN AMRO Bank N.V. ", "trackingId": "unused"},
        {"id": "2948083", "displayName": "ABN AMRO MeesPierson"},
        {"id": "company-slug", "displayName": "Acme"},
        {"id": "１２３", "displayName": "Acme"},  # noqa: RUF001  fullwidth digits are the input under test
        {"id": "456", "displayName": "   "},
        {"id": 789, "displayName": "Acme"},
        None,
    ]
    fetcher = StubFetcher({"typeaheadHits": ok(json.dumps(hits))})
    assert asyncio.run(linkedin.companies(fetcher, " ABN & AMRO ")) == [
        {"id": "1173", "name": "ABN AMRO Bank N.V."},
        {"id": "2948083", "name": "ABN AMRO MeesPierson"},
    ]
    assert len(fetcher.requests) == 1
    assert parse_qs(urlsplit(fetcher.requests[0]).query) == {
        "query": ["ABN & AMRO"],
        "typeaheadType": ["COMPANY"],
    }
    with pytest.raises(ValueError, match="Pass a company name"):
        asyncio.run(linkedin.companies(fetcher, "   "))
    assert len(fetcher.requests) == 1


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (ok("[]"), []),
        (network_down(), None),
        (ok("<html>Sign in</html>"), None),
        (ok("{}"), None),
        (ok('[{"id": "bad", "displayName": "Acme"}]'), None),
    ],
)
def test_company_lookup_distinguishes_no_matches_from_failure(unlimited, response, expected):
    fetcher = StubFetcher({"typeaheadHits": response})
    if expected is None:
        with pytest.raises(Stopped, match="company"):
            asyncio.run(linkedin.companies(fetcher, "Acme"))
    else:
        assert asyncio.run(linkedin.companies(fetcher, "Acme")) == expected


def test_places_lists_usable_candidates_in_order(unlimited):
    hits = [
        {"id": "1", "displayName": "Amsterdam, North Holland, Netherlands", "type": "GEO"},
        {"id": "   ", "displayName": "Amsterdam Area"},
        {"id": "3", "displayName": "   "},
        {"id": "2", "displayName": "Amsterdam, New York, United States", "type": "GEO"},
        {"id": "4", "displayName": "Amsterdam North Holland Netherlands"},
    ]
    fetcher = StubFetcher({"typeaheadHits": ok(json.dumps(hits))})
    assert asyncio.run(linkedin.places(fetcher, "amsterdam, ")) == [
        {"id": "1", "name": "Amsterdam, North Holland, Netherlands"},
        {"id": "2", "name": "Amsterdam, New York, United States"},
        {"id": "4", "name": "Amsterdam North Holland Netherlands"},
    ]
    assert "query=amsterdam%2C&" in fetcher.requests[0]
    with pytest.raises(ValueError, match="blank"):
        asyncio.run(linkedin.places(fetcher, "   "))
    assert len(fetcher.requests) == 1


@pytest.mark.parametrize(
    ("company_ids", "query", "easy_apply", "early_applicant"),
    [
        (None, "data", False, False),
        ([], "", True, False),
        (["1173"], "", False, True),
        (["1173", "2220078"], "data", True, True),
    ],
)
def test_paginated_search_preserves_filters(
    unlimited, company_ids, query, easy_apply, early_applicant
):
    fetcher = PagedFetcher([linkedin_card("111"), linkedin_card("222")])
    jobs = asyncio.run(
        linkedin.search(
            fetcher,
            query=query,
            geoid="102890719",
            company_ids=company_ids,
            easy_apply=easy_apply,
            early_applicant=early_applicant,
            max_age_hours=48,
            radius=40,
            results=2,
        )
    )
    assert [job["id"] for job in jobs] == ["111", "222"]
    assert len(fetcher.requests) == 2
    for start, url in enumerate(fetcher.requests):
        params = parse_qs(urlsplit(url).query, keep_blank_values=True)
        assert params == {
            "keywords": [query],
            "geoId": ["102890719"],
            # Kilometers go out as whole miles, here with a geoId and no location.
            "distance": ["25"],
            "start": [str(start)],
            "f_TPR": ["r172800"],
            "sortBy": ["DD"],
            **({"f_C": [",".join(company_ids)]} if company_ids else {}),
            **({"f_AL": ["true"]} if easy_apply else {}),
            **({"f_EA": ["true"]} if early_applicant else {}),
        }


def test_search_by_geoid_needs_no_location_or_query(unlimited):
    fetcher = StubFetcher({"seeMoreJobPostings": ok(linkedin_card("111"))})
    asyncio.run(linkedin.search(fetcher, results=1, geoid="12345"))
    assert "geoId=12345" in fetcher.requests[0]
    assert "location=" not in fetcher.requests[0]
    assert "f_TPR" not in fetcher.requests[0]  # no age limit by default


def test_every_request_waits_for_its_turn_before_it_sends(unlimited, monkeypatch):
    events = []
    pick = client.POOL.pick

    def turn(tried):
        events.append("turn")
        return pick(tried)

    class Sending(StubFetcher):
        async def fetch(self, url, *, headers=None, json=None):
            events.append("send")
            return await super().fetch(url, headers=headers)

    monkeypatch.setattr(client.POOL, "pick", turn)
    fetcher = Sending(
        {"seeMoreJobPostings": ok(linkedin_card("111")), "jobs/view/111": ok(job_page())}
    )
    asyncio.run(linkedin.search(fetcher, query="x", location="Seattle", results=1, details=True))
    assert events == ["turn", "send"] * 2


def test_search_details_hydrate_from_the_canonical_page(unlimited):
    fetcher = StubFetcher(
        {"seeMoreJobPostings": ok(linkedin_card("111")), "jobs/view/111": ok(job_page())}
    )
    jobs = asyncio.run(
        linkedin.search(fetcher, query="x", location="Seattle", results=1, details=True)
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
        linkedin.search(fetcher, query="x", location="Seattle", results=1, details=True)
    )
    assert jobs[0]["title"] == "Economist"
    assert "description" not in jobs[0]


def test_search_stops_when_a_posting_cannot_be_fetched(unlimited, monkeypatch):
    monkeypatch.setattr(client, "RETRY_DELAY", 0)
    fetcher = StubFetcher(
        {"seeMoreJobPostings": ok(linkedin_card("111")), "jobs/view/111": rate_limited()}
    )
    with pytest.raises(Stopped, match="details of 1 of 1 postings") as stop:
        asyncio.run(
            linkedin.search(fetcher, query="x", location="Seattle", results=1, details=True)
        )
    assert [job["title"] for job in stop.value.partial] == ["Economist"]


def test_search_reruns_only_fetch_unseen_postings(unlimited):
    responses = {"seeMoreJobPostings": ok(linkedin_card("111")), "jobs/view/111": ok(job_page())}
    jobs = asyncio.run(
        linkedin.search(
            StubFetcher(responses),
            query="x",
            location="Seattle",
            results=1,
            details=True,
        )
    )
    rerun_fetcher = StubFetcher(responses)
    rerun = asyncio.run(
        linkedin.search(
            rerun_fetcher,
            query="x",
            location="Seattle",
            results=1,
            details=True,
        )
    )
    assert jobs[0]["description"] == rerun[0]["description"] == "Great & big role"
    assert [url for url in rerun_fetcher.requests if "seeMoreJobPostings" not in url] == []
    # refresh reaches the detail fetch, so the same search refetches the posting.
    refetch_fetcher = StubFetcher(responses)
    asyncio.run(
        linkedin.search(
            refetch_fetcher,
            query="x",
            location="Seattle",
            results=1,
            details=True,
            refresh=True,
        )
    )
    assert len([url for url in refetch_fetcher.requests if "jobs/view/111" in url]) == 1


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


def blockless_page():
    # A country-level posting: a real posting page, localized, no schema.org block.
    return """
    <html><script type="application/ld+json">{"@type": "Organization"}</script>
    <div class="show-more-less-html__markup">Great &amp; big role</div>
    <button data-tracking-control-name="public_jobs_apply-link-offsite"></button>
    <li class="description__job-criteria-item">
      <h3 class="description__job-criteria-subheader">Tipo de empleo</h3>
      <span class="description__job-criteria-text">Jornada completa</span>
    </li>
    <div class="salary compensation__salary">756.000,00 AED/año - 924.000,00 AED/año</div>
    <figcaption class="num-applicants__caption">Over 200 applicants</figcaption></html>"""


def en_fragment(url=CANONICAL):
    # The same posting's guest fragment: identical markup in en-US, and the
    # cheapest place LinkedIn writes down the canonical URL.
    return f"""
    <html><a class="topcard__link" href="{url}?trk=public_jobs_topcard-title">
      <h2 class="top-card-layout__title topcard__title">Economist</h2></a>
    <a class="topcard__org-name-link"
      href="https://uk.linkedin.com/company/acme?trk=public_jobs_topcard-org-name">Acme</a>
    <span class="topcard__flavor topcard__flavor--bullet">Seattle, WA</span>
    <span class="num-applicants__caption topcard__flavor--metadata topcard__flavor--bullet">
      109 applicants</span>
    <img class="artdeco-entity-image" data-delayed-url="https://media.licdn.com/acme-logo.png"/>
    <div class="show-more-less-html__markup">Great &amp; big role</div>
    <li class="description__job-criteria-item">
      <h3 class="description__job-criteria-subheader">Employment type</h3>
      <span class="description__job-criteria-text">Full-time</span>
    </li>
    <div class="salary compensation__salary">AED 756,000.00/yr - AED 924,000.00/yr</div></html>"""


FRAGMENT = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting"
OTHER = "https://nl.linkedin.com/jobs/view/other-at-acme-222"


def fetched(found, reference) -> JobDict:
    """Return the record postings() fetched for a reference, failing for a gone or unfetched one."""
    job = found.get(reference)
    assert job is not None
    return job


def parse(page) -> JobDict | None:
    """Return the record postings() builds from ``page`` served as CANONICAL, or None for no fields."""
    # An empty fragment answers a blockless page, so the record holds the page's fields alone.
    fetcher = StubFetcher({"economist-at-acme-111": ok(page), "jobPosting/111": ok("")})
    return asyncio.run(linkedin.postings(fetcher, [CANONICAL], refresh=True)).get(CANONICAL)


def parsed(page) -> JobDict:
    job = parse(page)
    assert job is not None
    return job


def test_a_posting_page_omits_what_it_cannot_extract(unlimited):
    job = parsed(job_page())
    assert job["description"] == "Great & big role"  # unescaped, then de-tagged
    assert job["employment_type"] == "full_time"  # unified across sites
    assert job["posted_at"] == "2026-08-05T08:04:27.000Z"  # timestamps kept whole
    assert job["expires_at"] == "2026-09-04T08:04:27.000Z"
    assert job["country_code"] == "NL"
    assert job["applicants"] == 200
    # the posting has no salary and no experience: the keys are absent
    assert "salary_min" not in job
    assert "experience_months" not in job


def test_a_posting_page_maps_schema_org_onto_the_record(unlimited):
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
    job = parsed(page)
    assert (job["salary_min"], job["salary_max"]) == (105000, 135000)
    assert (job["salary_currency"], job["salary_period"]) == ("USD", "YEAR")
    assert (job["city"], job["region"], job["country_code"]) == ("Delft", "ZH", "NL")
    assert job["experience_months"] == 36
    fractional = job_page(experienceRequirements={"monthsOfExperience": 24.5})
    assert "experience_months" not in parsed(fractional)  # JobDict holds whole months


def test_a_posting_page_drops_nonfinite_numbers(unlimited):
    # json.loads admits these constants, and json.dumps would write them back
    # out as invalid JSON
    page = job_page(
        jobLocation={"latitude": float("nan"), "longitude": float("inf")},
        baseSalary={"currency": "USD", "value": {"minValue": float("-inf"), "maxValue": 135000}},
        # an integer beyond float range costs only its field
        experienceRequirements={"monthsOfExperience": 10**1000},
    )
    job = parsed(page)
    assert not {"latitude", "longitude", "salary_min", "experience_months"} & set(job)
    assert job["salary_max"] == 135000
    # a markup salary with enough digits converts to infinity, and comma-only
    # bounds match the salary pattern but hold no number: neither yields a field
    huge = "9" * 400
    assert parse(f'<div class="compensation__salary">USD {huge}/yr - USD {huge}/yr</div>') is None
    assert parse('<div class="compensation__salary">USD ,/yr - USD ,/yr</div>') is None


def test_a_posting_page_reads_the_apply_kind(unlimited):
    for apply in ("offsite", "onsite", "whatevernext"):  # any value the page uses
        assert parsed(job_page(apply=apply))["apply_type"] == apply
    assert "apply_type" not in parsed(job_page(apply=None))


def test_applicant_count_ignores_the_prose_around_it(unlimited):
    for caption, expected in (  # every form seen across seven locales
        ("Be among the first 25 applicants", 25),
        ("Over 200 applicants", 200),
        ("114 applicants", 114),
        ("Wees een van de eerste 25 sollicitanten", 25),  # the prose is localized
        ("applicants", None),
    ):
        job = parsed(job_page(applicants=caption))
        assert job.get("applicants") == expected


def test_a_posting_page_survives_schema_variants(unlimited):
    # schema.org allows a bare string or a list where an object is typical
    page = job_page(
        experienceRequirements="3 years", jobLocation=[{"address": {"addressCountry": "DE"}}]
    )
    job = parsed(page)
    assert job["country_code"] == "DE"
    assert "experience_months" not in job
    assert parse("<html><body>signup wall</body></html>") is None

    graph = {
        "@graph": [
            {"@type": "Organization"},
            {"@type": ["Thing", "JobPosting"], "description": "Role"},
        ]
    }
    page = f'<script type="application/ld+json">{json.dumps(graph)}</script>'
    assert parsed(page)["description"] == "Role"


def test_a_posting_page_decodes_the_entities_the_block_arrives_with(unlimited):
    # Entities inside a script element reach the parser undecoded, so every
    # string the block holds needs decoding, not just the description markup.
    page = job_page(
        title="Data &amp; Analytics Lead",
        hiringOrganization={
            "name": "Johnson &amp; Johnson",
            "logo": "https://media.licdn.com/logo?e=1&amp;v=beta",
        },
    )
    job = parsed(page)
    assert job["title"] == "Data & Analytics Lead"
    assert job["company"] == "Johnson & Johnson"
    assert job["company_logo"] == "https://media.licdn.com/logo?e=1&v=beta"


def test_a_posting_page_normalizes_union_valued_fields(unlimited):
    page = job_page(
        description={"@type": "Thing"},
        employmentType=["FULL_TIME", "CONTRACTOR"],
        hiringOrganization={
            "sameAs": ["https://nl.linkedin.com/company/acme"],
            "logo": {"@type": "ImageObject", "url": "https://media.licdn.com/acme.png"},
        },
        jobLocation={
            "address": {"addressCountry": {"@type": "Country", "name": "US"}},
            "latitude": "52.37",
        },
    )
    job = parsed(page)
    assert "description" not in job  # an object is not a description
    assert job["employment_type"] == "full_time"  # the first of a list
    assert job["company_url"] == "https://nl.linkedin.com/company/acme"
    assert job["company_logo"] == "https://media.licdn.com/acme.png"  # unwrapped ImageObject
    assert job["country_code"] == "US"  # a Country object's name
    assert "latitude" not in job  # only numbers reach the model


def test_a_posting_page_falls_back_to_the_markup_without_the_block(unlimited):
    job = parsed(blockless_page())
    assert job["description"] == "Great & big role"
    assert job["apply_type"] == "offsite"
    assert job["applicants"] == 200
    assert "posted_at" not in job  # the structured fields stay absent
    # localized labels and number formats must not half-parse into wrong values
    assert "employment_type" not in job
    assert "salary_min" not in job


def test_a_posting_page_reads_the_summary_fields(unlimited):
    # A posting page has to yield a whole job, card or no card.
    markup = parsed(en_fragment())
    assert (markup["title"], markup["company"]) == ("Economist", "Acme")
    # the place bullet, not the applicant count sitting in the bullet beside it
    assert markup["location"] == "Seattle, WA"
    page = job_page(title="Senior Economist", hiringOrganization={"name": "Acme BV"})
    block = parsed(page)
    assert (block["title"], block["company"]) == ("Senior Economist", "Acme BV")


def test_a_posting_page_reads_the_en_us_markup_labels(unlimited):
    job = parsed(en_fragment())
    assert job["employment_type"] == "full_time"
    assert (job["salary_min"], job["salary_max"]) == (756000.0, 924000.0)
    assert (job["salary_currency"], job["salary_period"]) == ("AED", "YEAR")
    assert job["company_url"] == "https://uk.linkedin.com/company/acme"
    assert job["company_logo"] == "https://media.licdn.com/acme-logo.png"


@pytest.mark.parametrize("failure", [network_down(), rate_limited()])
def test_a_blockless_page_pulls_the_en_us_fragment(unlimited, monkeypatch, failure):
    monkeypatch.setattr(client, "RETRY_DELAY", 0)
    other = "https://nl.linkedin.com/jobs/view/other-at-acme-444"
    fetcher = StubFetcher(
        {
            "economist-at-acme-111": ok(blockless_page()),
            "jobPosting/111": ok(en_fragment()),
            "other-at-acme-444": ok(blockless_page()),
            "jobPosting/444": failure,
        }
    )
    got = asyncio.run(linkedin.postings(fetcher, ["111", other]))
    assert fetched(got, "111")["employment_type"] == "full_time"  # the fragment's part
    assert fetched(got, "111")["applicants"] == 200  # the page wins where both speak
    assert fetcher.requests[:4] == [
        f"{FRAGMENT}/111?_l=en_US",  # names the URL, and serves the labels too
        CANONICAL,
        other,
        f"{FRAGMENT}/444?_l=en_US",  # forced locale: the labels must parse
    ]
    # a posting whose fragment failed is left out and not cached, so a rerun fetches it again
    assert other not in got
    fetcher.requests.clear()
    assert asyncio.run(linkedin.postings(fetcher, ["111", other])) == got
    assert fetcher.requests[0] == other
    assert CANONICAL not in fetcher.requests


def test_postings_three_outcomes_and_what_each_costs_again(unlimited, monkeypatch):
    monkeypatch.setattr(client, "RETRY_DELAY", 0)
    gone = "https://nl.linkedin.com/jobs/view/gone-at-acme-222"
    gone_alias = "https://www.linkedin.com/jobs/view/gone-at-acme-222"
    flaky = "https://nl.linkedin.com/jobs/view/flaky-at-acme-333"
    fetcher = StubFetcher(
        {
            "economist-at-acme-111": ok(job_page()),
            "gone-at": not_found(),
            "flaky-at": rate_limited(),
        }
    )
    references = [CANONICAL, CANONICAL, gone, gone_alias, flaky]
    got = asyncio.run(linkedin.postings(fetcher, references))
    assert fetched(got, CANONICAL)["employment_type"] == "full_time"
    assert (got[gone], got[gone_alias]) == (None, None)  # gone, and the alias shares it
    assert flaky not in got  # transient: safe to retry
    assert sum(1 for u in fetcher.requests if u == CANONICAL) == 1  # deduped
    assert sum(1 for u in fetcher.requests if "gone-at" in u) == 1  # so is the alias

    # A retry: the fetched posting comes from the cache. A gone posting is not
    # cached, so it is asked again with the transient one.
    fetcher.responses["flaky-at"] = ok(job_page())
    fetcher.requests.clear()
    again = asyncio.run(linkedin.postings(fetcher, [CANONICAL, gone, flaky]))
    assert fetched(again, flaky)["employment_type"] == "full_time"
    assert (again[CANONICAL], again[gone]) == (got[CANONICAL], None)
    assert fetcher.requests == [gone, flaky]


def test_postings_stop_when_the_429_retries_also_fail(unlimited, caplog, monkeypatch):
    monkeypatch.setattr(client, "RETRY_DELAY", 0)
    fetcher = StubFetcher({"linkedin.com": rate_limited()})
    with caplog.at_level(logging.WARNING, logger="jobrake.sites.linkedin"):
        got = asyncio.run(linkedin.postings(fetcher, [CANONICAL, OTHER]))
    assert got == {}  # nothing fetched, everything retryable later
    assert len(fetcher.requests) == 1 + client.RETRIES  # one posting's tries; the rest spared
    assert "rate limiting" in caplog.text

    # a persistently limited fragment stops too, sparing the postings after it
    fetcher = StubFetcher(
        {"economist-at-acme-111": ok(blockless_page()), "jobPosting/111": rate_limited()}
    )
    assert asyncio.run(linkedin.postings(fetcher, [CANONICAL, OTHER])) == {}
    fragment = f"{FRAGMENT}/111?_l=en_US"
    assert fetcher.requests == [CANONICAL] + [fragment] * (1 + client.RETRIES)

    # a stop still serves the postings it never reached from the cache
    first = "https://nl.linkedin.com/jobs/view/first-at-acme-333"
    cached = "https://nl.linkedin.com/jobs/view/cached-at-acme-444"
    asyncio.run(linkedin.postings(StubFetcher({"cached-at": ok(job_page())}), [cached]))
    fetcher = StubFetcher({"linkedin.com": rate_limited()})
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="jobrake.sites.linkedin"):
        got = asyncio.run(linkedin.postings(fetcher, [first, cached]))
    assert list(got) == [cached]
    assert len(fetcher.requests) == 1 + client.RETRIES  # only the first posting was attempted
    assert "1 of 2" in caplog.text


def test_postings_contain_a_malformed_block_per_posting(unlimited):
    fetcher = StubFetcher(
        {
            "economist-at-acme-111": ok(
                job_page(description={"@type": "Thing"}, employmentType=["FULL_TIME"])
            ),
            "other-at-acme-222": ok(job_page()),
        }
    )
    got = asyncio.run(linkedin.postings(fetcher, [CANONICAL, OTHER]))
    assert fetched(got, CANONICAL)["employment_type"] == "full_time"
    assert "description" not in fetched(got, CANONICAL)
    assert fetched(got, OTHER)["description"] == "Great & big role"  # fetching went on


@pytest.mark.parametrize("suffix", ["/", "?trk=public_jobs", "/?trk=public_jobs", "#apply"])
def test_postings_reduce_a_url_to_its_page(unlimited, suffix):
    fetcher = StubFetcher({"economist-at-acme-111": ok(job_page())})
    got = asyncio.run(linkedin.postings(fetcher, [CANONICAL + suffix]))
    assert fetched(got, CANONICAL + suffix)["url"] == CANONICAL  # keyed as passed
    # fetched without a trailing slash, or the page omits the block
    assert fetcher.requests == [CANONICAL]


def test_postings_without_the_cache_refetch_and_refresh(unlimited):
    fetcher = StubFetcher({"economist-at-acme-111": ok(job_page())})
    asyncio.run(linkedin.postings(fetcher, [CANONICAL], refresh=True))
    asyncio.run(linkedin.postings(fetcher, [CANONICAL], refresh=True))
    assert len(fetcher.requests) == 2
    # the refetches stored what they found, so a cached call needs no request
    asyncio.run(linkedin.postings(fetcher, [CANONICAL]))
    assert len(fetcher.requests) == 2


def test_a_refreshed_posting_replaces_its_cached_copy(unlimited):
    complete = StubFetcher({"economist-at-acme-111": ok(job_page(description="Old role"))})
    asyncio.run(linkedin.postings(complete, [CANONICAL]))
    blockless = StubFetcher(
        {"economist-at-acme-111": ok(blockless_page()), "jobPosting/111": ok(en_fragment())}
    )
    got = asyncio.run(linkedin.postings(blockless, [CANONICAL], refresh=True))
    cached = asyncio.run(linkedin.postings(StubFetcher({}), [CANONICAL]))
    assert cached == got  # the cache returns what the last fetch returned
    assert "posted_at" not in fetched(cached, CANONICAL)


def test_postings_are_cached_by_id_not_url(unlimited):
    # One posting may change subdomain or slug while keeping its ID.
    fetcher = StubFetcher({"economist-at-acme-111": ok(job_page())})
    asyncio.run(linkedin.postings(fetcher, [CANONICAL]))
    moved = "https://uk.linkedin.com/jobs/view/senior-economist-at-acme-111"
    got = asyncio.run(linkedin.postings(StubFetcher({}), [moved]))
    assert fetched(got, moved)["employment_type"] == "full_time"


def test_a_details_search_caches_the_page_without_its_card(unlimited):
    responses = {"seeMoreJobPostings": ok(linkedin_card("111")), "jobs/view/111": ok(job_page())}
    jobs = asyncio.run(
        linkedin.search(
            StubFetcher(responses), query="x", location="Seattle", results=1, details=True
        )
    )
    assert jobs[0]["date"] == "2026-08-01"  # the search keeps its card's date
    got = asyncio.run(linkedin.postings(StubFetcher({}), ["111"]))
    assert fetched(got, "111")["date"] == "2026-08-05"  # the page's, as a cold fetch reads it


def test_postings_attempt_each_posting_once(unlimited, caplog):
    moved = "https://uk.linkedin.com/jobs/view/senior-economist-at-acme-111"
    fetcher = StubFetcher({"-111": ok("<html><body>signup wall</body></html>")})
    with caplog.at_level(logging.WARNING, logger="jobrake.sites.linkedin"):
        got = asyncio.run(linkedin.postings(fetcher, [CANONICAL, moved]))
    assert got == {}  # nothing parsed: absent, safe to retry later
    assert len(fetcher.requests) == 1  # but the alias spends no second request now
    assert "no fields" in caplog.text


def test_an_interrupted_fetch_keeps_paid_results(unlimited):
    class DiesOnSecond(StubFetcher):
        async def fetch(self, url, *, headers=None, json=None):
            if len(self.requests) == 1:
                raise RuntimeError("interrupted")
            return await super().fetch(url, headers=headers)

    fetcher = DiesOnSecond({"economist-at-acme-111": ok(job_page())})
    with pytest.raises(RuntimeError):
        asyncio.run(linkedin.postings(fetcher, [CANONICAL, OTHER]))
    got = asyncio.run(linkedin.postings(StubFetcher({}), [CANONICAL]))
    assert fetched(got, CANONICAL)["applicants"] == 200


def test_a_broken_cache_still_fetches_and_warns_once(unlimited, tmp_path, monkeypatch, caplog):
    (tmp_path / "blocker").write_text("")
    monkeypatch.setattr(cache, "CACHE", cache.Cache(tmp_path / "blocker" / "jobrake.sqlite3"))
    fetcher = StubFetcher({"economist-at-acme-111": ok(job_page())})
    with caplog.at_level(logging.WARNING, logger="jobrake.cache"):
        got = asyncio.run(linkedin.postings(fetcher, [CANONICAL]))
    assert fetched(got, CANONICAL)["applicants"] == 200
    assert len([r for r in caplog.records if "disabled" in r.message]) == 1


def test_postings_resolve_an_id_before_fetching_the_page(unlimited):
    fetcher = StubFetcher(
        {
            "jobPosting/111": ok(en_fragment()),
            "economist-at-acme-111": ok(job_page(title="Economist")),
        }
    )
    got = asyncio.run(linkedin.postings(fetcher, ["111"]))
    # /jobs/view/111 answers without the schema.org block, so the id buys the
    # canonical URL from the fragment first
    assert fetcher.requests == [f"{FRAGMENT}/111?_l=en_US", CANONICAL]
    job = fetched(got, "111")
    assert (job["id"], job["url"], job["title"]) == ("111", CANONICAL, "Economist")
    assert job["posted_at"] == "2026-08-05T08:04:27.000Z"  # what the block adds
    others = (
        f"{FRAGMENT}/111",
        "https://www.linkedin.com/jobs/view/economist-at-acme-111",
        "https://nl.linkedin.com/jobs/view/111",
        "https://linkedin.com/jobs/view/economist-at-acme-111",
        "https://www.linkedin.com:443/jobs/view/111",
    )
    # the cache holds the address and the posting, so no reference costs a request
    for address in ("111", CANONICAL, *others):
        fetcher.requests.clear()
        assert asyncio.run(linkedin.postings(fetcher, [address])) == {address: job}
        assert fetcher.requests == []
    # without the cache, every other address is resolved like an id, so none
    # of them can leave a record holding a page without the block
    for address in others:
        fetcher.requests.clear()
        assert asyncio.run(linkedin.postings(fetcher, [address], refresh=True)) == {address: job}
        assert fetcher.requests == [f"{FRAGMENT}/111?_l=en_US", CANONICAL]


@pytest.mark.parametrize(
    "reference",
    [
        "https://www.linkedin.com/jobs/search",  # no posting id anywhere
        "https://example.test/private-123",  # another site's page ending in digits
        "https://nl.linkedin.com/company/acme-111",  # linkedin, but not a posting
        "ftp://nl.linkedin.com/jobs/view/economist-at-acme-111",  # not a web address
        "   ",  # a blank argument, which names nothing at all
    ],
)
def test_postings_reject_a_reference_that_is_not_a_linkedin_posting(unlimited, reference):
    # A wrong address must fail rather than quietly become whichever linkedin
    # posting shares its trailing digits, or vanish and leave a short result.
    fetcher = StubFetcher({})
    with pytest.raises(ValueError, match="posting ID"):
        asyncio.run(linkedin.postings(fetcher, [CANONICAL, reference]))
    assert fetcher.requests == []


def test_postings_distrust_a_lookup_that_names_another_page(unlimited):
    elsewhere = en_fragment(url="https://nl.linkedin.com/jobs/view/other-at-acme-222")
    for fragment in (elsewhere, "<html>no topcard</html>"):
        fetcher = StubFetcher({"jobPosting/111": ok(fragment)})
        assert asyncio.run(linkedin.postings(fetcher, ["111"])) == {}
        # nothing is fetched on a link jobrake cannot tie back to posting 111
        assert fetcher.requests == [f"{FRAGMENT}/111?_l=en_US"]


def test_postings_collapse_the_addresses_of_one_posting(unlimited):
    fetcher = StubFetcher({"economist-at-acme-111": ok(job_page(title="Economist"))})
    references = [CANONICAL, "https://uk.linkedin.com/jobs/view/economist-at-acme-111", "111"]
    got = asyncio.run(linkedin.postings(fetcher, references, refresh=True))
    # one posting, fetched once from the first canonical address
    assert fetcher.requests == [CANONICAL]
    assert list(got) == references
    assert all(job == got[CANONICAL] for job in got.values())
    assert fetched(got, "111")["url"] == CANONICAL


def test_postings_stop_looking_up_ids_once_rate_limited(unlimited, monkeypatch, caplog):
    monkeypatch.setattr(client, "RETRY_DELAY", 0)
    fetcher = StubFetcher({"jobPosting": rate_limited()})
    with caplog.at_level(logging.WARNING, logger="jobrake.sites.linkedin"):
        assert asyncio.run(linkedin.postings(fetcher, ["111", "222", "333"])) == {}
    # the retries inside paced_fetch, then give up
    assert fetcher.requests == [f"{FRAGMENT}/111?_l=en_US"] * (1 + client.RETRIES)
    assert "rate limiting" in caplog.text


def test_postings_keep_what_they_resolved_in_reference_order(unlimited, caplog):
    other = "https://nl.linkedin.com/jobs/view/other-at-acme-444"
    fetcher = StubFetcher(
        {
            "jobPosting/111": ok(en_fragment()),
            "economist-at-acme-111": ok(job_page(title="Economist")),
            "jobPosting/444": ok(en_fragment(url=other)),
            "other-at-acme-444": ok(job_page(title="Other")),
            "jobPosting/222": not_found(),  # gone
            "jobPosting/333": network_down(),  # retryable
        }
    )
    references = ["333", "444", "222", "111"]
    with caplog.at_level(logging.WARNING, logger="jobrake.sites.linkedin"):
        got = asyncio.run(linkedin.postings(fetcher, references))
    assert list(got) == ["444", "222", "111"]  # reference order, the failure left out
    assert got["222"] is None
    assert [fetched(got, ref)["title"] for ref in ("444", "111")] == ["Other", "Economist"]
    assert [record.message.split(".")[0] for record in caplog.records] == [
        "skipping posting 333: connection reset",
    ]
    # a rerun asks only about the postings it did not fetch: 444 and 111 come
    # from the cache with their URLs
    fetcher.requests.clear()
    assert asyncio.run(linkedin.postings(fetcher, references)) == got
    assert fetcher.requests == [f"{FRAGMENT}/333?_l=en_US", f"{FRAGMENT}/222?_l=en_US"]


def test_postings_fetch_a_us_posting_on_www(unlimited, caplog):
    # A US posting has no country subdomain, so the fragment names its www page,
    # and that page carries the schema.org block.
    www = "https://www.linkedin.com/jobs/view/economist-at-acme-111"
    fetcher = StubFetcher(
        {"jobPosting/111": ok(en_fragment(url=www)), www: ok(job_page(title="Economist"))}
    )
    with caplog.at_level(logging.WARNING, logger="jobrake.sites.linkedin"):
        job = fetched(asyncio.run(linkedin.postings(fetcher, ["111"])), "111")
    assert (job["id"], job["url"], job["title"]) == ("111", www, "Economist")
    assert job["posted_at"] == "2026-08-05T08:04:27.000Z"
    assert caplog.records == []
