"""LinkedIn guest-search parsing and pagination tests."""

import asyncio
import heapq
import importlib
import itertools
import json
import logging
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fakes import PagedFetcher, StubFetcher, network_down, not_found, ok, rate_limited
from hypothesis import given
from hypothesis import strategies as st

from jobrake import Stopped, cache
from jobrake.fetchkit import FetchResult, HttpxFetcher
from jobrake.models import IDENTITY_FIELDS, SUMMARY_FIELDS, JobDict
from jobrake.sites import linkedin
from jobrake.sites.linkedin import client


@pytest.fixture
def unlimited(monkeypatch):
    """Expire every fabric's window, so no request waits."""
    monkeypatch.setattr(client, "monotonic", itertools.count(0.0, client.RETRY_DELAY).__next__)


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
    assert jobs[0]["locations"] == [{"name": "Seattle, WA"}]
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

    async def fetch(self, url, *, headers=None, json=None, follow_redirects=True):
        cookie = (headers or {})["cookie"]
        fabric = cookie[6:-1] if cookie != "lidc=" else self.fabrics.pop(0)
        result = await super().fetch(url, headers=headers, follow_redirects=follow_redirects)
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


def test_redirect_hops_keep_their_pin_and_share_the_request_budget(monkeypatch):
    now = 0.0
    sends = []
    sleeps = []

    async def sleep(seconds):
        nonlocal now
        now += seconds
        sleeps.append(seconds)

    monkeypatch.setattr(client, "monotonic", lambda: now)
    monkeypatch.setattr(client.asyncio, "sleep", sleep)

    def respond(request):
        sends.append((now, request.headers.get("cookie")))
        if len(sends) == 16:
            return httpx.Response(200, text="[]")
        return httpx.Response(302, headers={"location": f"/hop/{len(sends)}"})

    async def run():
        async with HttpxFetcher(
            headers={"cookie": "session=private"}, transport=httpx.MockTransport(respond)
        ) as fetcher:
            return await paced(fetcher)

    assert asyncio.run(run()) == []
    cookies = ['lidc="b=OGST02"', 'lidc="b=TGST02"', 'lidc="b=VGST02"']
    assert [stamp for stamp, _ in sends] == [0.0] * 15 + [11.6]
    assert sorted(cookie for _, cookie in sends[:15]) == sorted(cookies * 5)
    assert sends[-1][1] in cookies
    assert sleeps == [11.6]


def test_redirects_resolve_locations_learn_cookies_and_retry_only_the_current_hop(unlimited):
    sends = []
    responses = iter(
        [
            httpx.Response(
                301,
                headers={
                    "location": "/one",
                    "x-li-fabric": "prod-lor1",
                    "set-cookie": 'lidc="b=Olearned"',
                },
            ),
            httpx.Response(302, headers={"location": "//nl.linkedin.com/two"}),
            httpx.Response(303, headers={"location": "https://de.linkedin.com/three"}),
            httpx.Response(307, headers={"location": "../four"}),
            httpx.Response(308, headers={"location": "/five"}),
            httpx.Response(429),
            httpx.Response(200, text="[]"),
        ]
    )

    def respond(request):
        sends.append((str(request.url), request.headers["cookie"]))
        return next(responses)

    async def run():
        async with HttpxFetcher(transport=httpx.MockTransport(respond)) as fetcher:
            return await paced(fetcher)

    assert asyncio.run(run()) == []
    assert sends == [
        (
            "https://www.linkedin.com/jobs-guest/api/typeaheadHits?query=x&typeaheadType=COMPANY",
            'lidc="b=OGST02"',
        ),
        ("https://www.linkedin.com/one", 'lidc="b=TGST02"'),
        ("https://nl.linkedin.com/two", 'lidc="b=VGST02"'),
        ("https://de.linkedin.com/three", 'lidc="b=Olearned"'),
        ("https://de.linkedin.com/four", 'lidc="b=TGST02"'),
        ("https://de.linkedin.com/five", 'lidc="b=VGST02"'),
        ("https://de.linkedin.com/five", 'lidc="b=Olearned"'),
    ]


@pytest.mark.parametrize("finishes", [True, False])
def test_redirect_limit_allows_twenty_hops_and_stops_a_loop(unlimited, finishes):
    requests = []

    def respond(request):
        requests.append(str(request.url))
        if finishes and len(requests) == 21:
            return httpx.Response(200, text="[]")
        return httpx.Response(302, headers={"location": "/loop"})

    async def run():
        async with HttpxFetcher(transport=httpx.MockTransport(respond)) as fetcher:
            return await paced(fetcher)

    if finishes:
        assert asyncio.run(run()) == []
    else:
        with pytest.raises(Stopped, match="exceeded 20 redirects") as stop:
            asyncio.run(run())
        assert stop.value.partial == []
    assert len(requests) == 21


def test_invalid_redirects_fail_before_another_request(unlimited):
    async def run():
        for location in (
            "http://www.linkedin.com/page",
            "https://linkedin.com.evil.test/page",
            "https://[bad",
        ):
            fetcher = StubFetcher(
                {
                    "linkedin.com": FetchResult(
                        "https://www.linkedin.com/start", 302, headers={"location": location}
                    )
                }
            )
            with pytest.raises(Stopped, match="invalid LinkedIn redirect") as stop:
                await paced(fetcher)
            assert stop.value.partial == []
            assert len(fetcher.requests) == 1

    asyncio.run(run())


def test_redirect_wait_can_be_cancelled_without_sending_another_request(monkeypatch):
    requests = []

    async def run():
        waiting = asyncio.Event()

        async def sleep(seconds):
            assert seconds == 11.6
            waiting.set()
            await asyncio.Future()

        def respond(request):
            requests.append(str(request.url))
            return httpx.Response(302, headers={"location": "/loop"})

        monkeypatch.setattr(client, "monotonic", lambda: 0.0)
        monkeypatch.setattr(client.asyncio, "sleep", sleep)
        async with HttpxFetcher(transport=httpx.MockTransport(respond)) as fetcher:
            task = asyncio.create_task(paced(fetcher))
            try:
                await asyncio.wait_for(waiting.wait(), timeout=1)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            with pytest.raises(asyncio.CancelledError):
                await task
            assert len(requests) == 15
            assert not [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]

    asyncio.run(run())


def test_pacing_allows_a_burst_then_waits_for_window_capacity(monkeypatch):
    monkeypatch.setattr(client, "monotonic", lambda: 0.0)
    pool = client.Fabrics()
    pool.known = {}  # discovery: every request goes out unpinned
    assert pool.pick(set()) == (None, 0.0)
    assert pool.pick(set()) == (None, 2.32)
    pool = client.Fabrics()
    assert sorted(pool.pick(set()) for _ in range(15)) == sorted(
        [("prod-lor1", 0.0), ("prod-ltx1", 0.0), ("prod-lva1", 0.0)] * 5
    )
    assert pool.pick(set()) == ("prod-lor1", 11.6)


def test_pacing_charges_unanswered_and_rerouted_requests_to_possible_fabrics(monkeypatch):
    monkeypatch.setattr(client, "monotonic", itertools.count(0.0, 0.001).__next__)
    client.POOL.known = {}
    assert asyncio.run(paced(Routing(["prod-a"]))) == []
    assert client.POOL.history.get(None) == []

    now = [0.0]
    monkeypatch.setattr(client, "monotonic", lambda: now[0])
    pool = client.Fabrics()
    pool.known = {name: f'"{name}"' for name in ("prod-a", "prod-b")}
    assert pool.pick(set()) == (None, 0.0)
    pool.unpinned = client.DISCOVERY
    now[0] = 2.5
    assert (
        sorted(pool.pick(set()) for _ in range(8)) == [("prod-a", 0.0)] * 4 + [("prod-b", 0.0)] * 4
    )
    assert pool.pick(set()) == ("prod-a", 9.1)

    result = FetchResult(url="stub", status=200, headers={"x-li-fabric": "prod-a"})
    pool.learn(None, result, 0.0)
    assert pool.pick(set()) == ("prod-b", 0.0)  # its reserved slot is free again
    assert pool.pick(set()) == ("prod-a", 9.1)

    pool.learn("prod-b", result, 2.5)
    pool.unpinned = client.DISCOVERY
    now[0] = 11.6
    assert pool.pick(set()) == ("prod-a", 2.5)  # the reroute filled its window


def test_pacing_drops_a_pin_whose_request_lands_elsewhere(unlimited, monkeypatch):
    monkeypatch.setattr(client, "DISCOVERY", 1)
    client.POOL.known = {name: f'"{name}"' for name in ("prod-a", "prod-b", "prod-c")}
    client.POOL.unpinned = 1  # discovery is spent

    class Rerouting(Routing):
        async def fetch(self, url, *, headers=None, json=None, follow_redirects=True):
            result = await super().fetch(url, headers=headers, follow_redirects=follow_redirects)
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
    # may land on any fabric, so the second waits for discovery's spacing, then chooses
    # among three.
    assert [h["cookie"] for h in fetcher.headers] == ["lidc=", 'lidc="prod-a"']
    assert sleeps == [2.32]


class QueuedOnOneFabric:
    """Requests that wait on prod-a, the one fabric known, under a clock the test moves."""

    def __init__(self, monkeypatch):
        monkeypatch.setattr(client, "DISCOVERY", 0)  # no unpinned requests to find more fabrics
        client.POOL.known = {"prod-a": '"prod-a"'}
        client.POOL.history = {"prod-a": [0.0] * 4}
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

    async def fetch(self, url, *, headers=None, json=None, follow_redirects=True):
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
        await queue.yield_(0)  # one fills the window, six wait
        queue.now = 10 * client.WINDOW  # every wait ran out while the loop was blocked
        while queue.parked:
            await queue.wake_all()
            queue.now += client.WINDOW
        await asyncio.gather(*requests)

    asyncio.run(run())
    assert len(queue.sends) == 7
    assert all(b >= a + 11.6 for a, b in zip(queue.sends, queue.sends[5:], strict=False))


def test_waiters_take_a_new_turn_when_discovery_starts(monkeypatch):
    queue = QueuedOnOneFabric(monkeypatch)

    async def run():
        requests = [queue.request() for _ in range(4)]
        await queue.yield_(0)  # one sends at once, three wait
        # With one fabric known and requests to spare, discovery starts.
        monkeypatch.setattr(client, "DISCOVERY", 12)
        while queue.parked:
            queue.now += 2.5
            await queue.wake_all()
        await asyncio.gather(*requests)

    asyncio.run(run())
    assert len(queue.sends) == 4
    assert all(b - a >= 2.5 for a, b in itertools.pairwise(queue.sends))


def test_an_unpinned_request_waits_until_every_fabric_is_paced(monkeypatch):
    now = [1.5]
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    monkeypatch.setattr(client, "monotonic", lambda: now[0])
    monkeypatch.setattr(client.asyncio, "sleep", sleep)
    # A reroute left one fabric known, so discovery runs. prod-b took a
    # full window 0.5 s ago, and the unpinned request might land there.
    client.POOL.known = {"prod-a": '"prod-a"'}
    client.POOL.sent = {"prod-a": 0.0, "prod-b": 1.0}
    client.POOL.history = {"prod-b": [1.0] * 5}
    fetcher = StubFetcher({"linkedin.com": ok("[]")})
    asyncio.run(paced(fetcher))
    assert [h["cookie"] for h in fetcher.headers] == ["lidc="]
    assert sleeps == [11.1]


def test_a_retry_skips_the_fabric_that_refused_an_unpinned_attempt(unlimited):
    # Two fabrics are known, so discovery runs. The unpinned attempt lands on
    # prod-b, which refuses it without a new cookie, so discovery goes on.
    client.POOL.known = {name: f'"{name}"' for name in ("prod-a", "prod-b")}

    class Refusing(StubFetcher):
        async def fetch(self, url, *, headers=None, json=None, follow_redirects=True):
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
        queue.now = client.WINDOW
        late = queue.request()
        await queue.yield_(0)
        return late.done()

    assert asyncio.run(run())  # canceled waiters spent no capacity in the next window
    assert queue.sends == [0.0, 11.6]


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

        async def fetch(self, url, *, headers=None, json=None, follow_redirects=True):
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
        async def fetch(self, url, *, headers=None, json=None, follow_redirects=True):
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
        assert all(b >= a + 11.6 for a, b in zip(times, times[5:], strict=False)), fabric


def test_linkedin_keeps_collected_jobs_after_a_later_page_failure(unlimited):
    class DownAfterFirst(StubFetcher):
        async def fetch(self, url, *, headers=None, json=None, follow_redirects=True):
            if self.requests:
                self.requests.append(url)
                return network_down()
            return await super().fetch(url, headers=headers, follow_redirects=follow_redirects)

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
    with pytest.raises(ValueError, match="Pass the company name"):
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
        async def fetch(self, url, *, headers=None, json=None, follow_redirects=True):
            events.append("send")
            return await super().fetch(url, headers=headers, follow_redirects=follow_redirects)

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
    # The page's lone place takes the card's label.
    assert jobs[0]["locations"] == [
        {"name": "Seattle, WA", "country_code": "NL", "latitude": 52.37}
    ]
    fetcher = StubFetcher(
        {
            "seeMoreJobPostings": ok(linkedin_card("222")),
            "jobs/view/222": ok(job_page(jobLocation=[{}, {}])),  # entries without a part
        }
    )
    jobs = asyncio.run(
        linkedin.search(fetcher, query="x", location="Seattle", results=1, details=True)
    )
    assert jobs[0]["locations"] == [
        {"name": "Seattle, WA"}
    ]  # a page without a place keeps the card's
    cards = StubFetcher({"seeMoreJobPostings": ok(linkedin_card("222"))})
    again = asyncio.run(
        linkedin.search(cards, query="x", location="Seattle", results=1, details=True)
    )
    assert again[0]["locations"] == [{"name": "Seattle, WA"}]  # and so does its cached record


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
    # An earlier parse in the same test must not answer from the cache.
    cache.CACHE.close()
    cache.CACHE.path.unlink(missing_ok=True)
    return asyncio.run(linkedin.postings(fetcher, [CANONICAL])).get(CANONICAL)


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
    assert job["locations"] == [{"name": "NL", "country_code": "NL", "latitude": 52.37}]
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
    assert job["locations"] == [
        {"name": "Delft, ZH, NL", "city": "Delft", "region": "ZH", "country_code": "NL"}
    ]
    # Each of several jobLocation entries is a place, named from its parts.
    delft, tokyo = {"addressLocality": "Delft", "addressCountry": "NL"}, {"addressCountry": "JP"}
    several = job_page(jobLocation=[{"address": delft}, {"address": tokyo}])
    assert parsed(several)["locations"] == [
        {"name": "Delft, NL", "city": "Delft", "country_code": "NL"},
        {"name": "JP", "country_code": "JP"},
    ]
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
    assert job["locations"] == [{"name": "DE", "country_code": "DE"}]
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
    # a Country object's name, and only numbers reach the model
    assert job["locations"] == [{"name": "US", "country_code": "US"}]


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
    assert markup["locations"] == [{"name": "Seattle, WA"}]
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


def test_postings_have_three_outcomes(unlimited, monkeypatch):
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


def test_postings_overlap_page_reads_and_keep_reference_order(unlimited, caplog):
    references = [f"https://nl.linkedin.com/jobs/view/role-{n}" for n in range(111, 119)]

    class Overlapping(StubFetcher):
        active = 0
        peak = 0

        async def fetch(self, url, *, headers=None, json=None, follow_redirects=True):
            self.active += 1
            self.peak = max(self.peak, self.active)
            # Every read yields so that each worker starts one, and the first posting ends last.
            for _ in range(10 if url == references[0] else 1):
                await asyncio.sleep(0)
            self.active -= 1
            return await super().fetch(
                url, headers=headers, json=json, follow_redirects=follow_redirects
            )

    fetcher = Overlapping({"linkedin.com": ok(job_page())})
    with caplog.at_level(logging.INFO, logger="jobrake.sites.linkedin"):
        got = asyncio.run(linkedin.postings(fetcher, references))
    assert fetcher.peak == 6
    assert fetcher.requests[-1] == references[0]
    assert list(got) == references
    assert all(fetched(got, ref)["applicants"] == 200 for ref in references)
    progress = [record.progress for record in caplog.records if hasattr(record, "progress")]
    assert progress == [(n, 8) for n in range(9)]
    assert asyncio.run(linkedin.postings(StubFetcher({}), references)) == got


def test_a_persistent_429_cancels_unfinished_reads_and_keeps_completed_pages(
    unlimited, monkeypatch
):
    monkeypatch.setattr(client, "RETRY_DELAY", 0)
    references = [f"https://nl.linkedin.com/jobs/view/role-{n}" for n in range(111, 135)]
    cancelled = []

    class Refusing(StubFetcher):
        async def fetch(self, url, *, headers=None, json=None, follow_redirects=True):
            if url == references[0]:
                return await super().fetch(
                    url, headers=headers, json=json, follow_redirects=follow_redirects
                )
            if url == references[1]:
                await asyncio.sleep(0)
                self.requests.append(url)
                return rate_limited()
            self.requests.append(url)
            try:
                # The refusals take far fewer turns, so a read the stop never cancels fails here.
                for _ in range(1000):
                    await asyncio.sleep(0)
            except asyncio.CancelledError:
                cancelled.append(url)
                raise
            raise AssertionError(f"{url} was still being read after the 429 stop")

    fetcher = Refusing({"linkedin.com": ok(job_page())})

    async def run():
        got = await linkedin.postings(fetcher, references)
        assert cancelled  # readers finish before the caller can close its transport
        return got

    got = asyncio.run(run())
    assert list(got) == references[:1]
    assert set(fetcher.requests) == set(references[:7])
    assert set(cancelled) == set(references[2:7])
    assert fetcher.requests.count(references[1]) == 4
    assert asyncio.run(linkedin.postings(StubFetcher({}), references[:1])) == got


def test_a_429_stop_propagates_a_completed_fetcher_exception_after_cleanup(unlimited, monkeypatch):
    monkeypatch.setattr(client, "RETRY_DELAY", 0)
    entered, released, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()
    blocked = "https://nl.linkedin.com/jobs/view/blocked-333"
    attempts = 0

    class Refusing(StubFetcher):
        async def fetch(self, url, *, headers=None, json=None, follow_redirects=True):
            nonlocal attempts
            if url == CANONICAL:
                await entered.wait()
                attempts += 1
                if attempts == 4:
                    released.set()
                return rate_limited()
            if url == OTHER:
                await released.wait()
                raise RuntimeError("fetcher failed")
            entered.set()
            try:
                await asyncio.Future()
            finally:
                cancelled.set()

    async def run():
        with pytest.raises(RuntimeError, match="fetcher failed"):
            await linkedin.postings(Refusing({}), [CANONICAL, OTHER, blocked])
        assert cancelled.is_set()

    asyncio.run(asyncio.wait_for(run(), timeout=1))


def test_postings_stop_when_the_429_retries_also_fail(unlimited, caplog, monkeypatch):
    monkeypatch.setattr(client, "RETRY_DELAY", 0)
    fetcher = StubFetcher({"linkedin.com": rate_limited()})
    with caplog.at_level(logging.WARNING, logger="jobrake.sites.linkedin"):
        got = asyncio.run(linkedin.postings(fetcher, [CANONICAL]))
    assert got == {}  # nothing fetched, everything retryable later
    assert len(fetcher.requests) == 1 + client.RETRIES
    assert "rate limiting" in caplog.text

    # A persistently limited fragment fails the whole posting too.
    fetcher = StubFetcher(
        {"economist-at-acme-111": ok(blockless_page()), "jobPosting/111": rate_limited()}
    )
    assert asyncio.run(linkedin.postings(fetcher, [CANONICAL])) == {}
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


@given(
    origin=st.sampled_from(["canonical", "fragment", "response"]),
    malformed=st.sampled_from(["https://[bad", "https://linkedin.com\uff0fjobs/view/role-111"]),
)
def test_malformed_response_urls_do_not_abort_other_postings(origin, malformed):
    class Malformed(StubFetcher):
        async def fetch(self, url, *, headers=None, json=None, follow_redirects=True):
            result = await super().fetch(
                url, headers=headers, json=json, follow_redirects=follow_redirects
            )
            if "111" in url and origin == "response":
                result.url = malformed
            return result

    body = job_page() + f'<link rel="canonical" href="{malformed}">'
    first = "111" if origin == "fragment" else CANONICAL
    fetcher = Malformed(
        {
            CANONICAL: ok(body if origin == "canonical" else job_page()),
            "jobPosting/111": ok(f'<a class="topcard__link" href="{malformed}"></a>'),
            OTHER: ok(job_page(title="Healthy")),
        }
    )
    isolated = cache.Cache(":memory:")
    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(cache, "CACHE", isolated)
            patch.setattr(client, "POOL", client.Fabrics())
            patch.setattr(client, "monotonic", itertools.count(0.0, 100.0).__next__)
            got = asyncio.run(linkedin.postings(fetcher, [first, OTHER]))
        assert list(got) == [OTHER]
        assert fetched(got, OTHER)["title"] == "Healthy"
        assert OTHER in fetcher.requests
    finally:
        isolated.close()


@pytest.mark.parametrize("suffix", ["/", "?trk=public_jobs", "/?trk=public_jobs", "#apply"])
def test_postings_reduce_a_url_to_its_page(unlimited, suffix):
    fetcher = StubFetcher({"economist-at-acme-111": ok(job_page())})
    got = asyncio.run(linkedin.postings(fetcher, [CANONICAL + suffix]))
    assert fetched(got, CANONICAL + suffix)["url"] == CANONICAL  # keyed as passed
    # fetched without a trailing slash, or the page omits the block
    assert fetcher.requests == [CANONICAL]


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
    cards = StubFetcher({"seeMoreJobPostings": ok(linkedin_card("111"))})
    again = asyncio.run(
        linkedin.search(cards, query="x", location="Seattle", results=1, details=True)
    )
    assert again[0]["date"] == "2026-08-01"  # a cached page keeps the card's date too
    assert again[0]["locations"] == jobs[0]["locations"]  # and names its place as the card does


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
        async def fetch(self, url, *, headers=None, json=None, follow_redirects=True):
            if len(self.requests) == 1:
                raise RuntimeError("interrupted")
            return await super().fetch(url, headers=headers, follow_redirects=follow_redirects)

    fetcher = DiesOnSecond({"economist-at-acme-111": ok(job_page())})
    with pytest.raises(RuntimeError):
        asyncio.run(linkedin.postings(fetcher, [CANONICAL, OTHER]))
    got = asyncio.run(linkedin.postings(StubFetcher({}), [CANONICAL]))
    assert fetched(got, CANONICAL)["applicants"] == 200


@pytest.mark.parametrize("cancel", [False, True])
def test_interrupted_postings_finish_their_readers_before_returning(unlimited, cancel):
    entered = asyncio.Event()
    started, cancelled = [], []
    references = [CANONICAL] + [
        f"https://nl.linkedin.com/jobs/view/role-{n}" for n in range(112, 135)
    ]

    class Interrupted(StubFetcher):
        async def fetch(self, url, *, headers=None, json=None, follow_redirects=True):
            if url == CANONICAL:
                await entered.wait()
                if not cancel:
                    raise RuntimeError("interrupted")
                await asyncio.Future()
            started.append(url)
            if len(started) == 5:
                entered.set()
            try:
                await asyncio.Future()
            finally:
                cancelled.append(url)

    async def run():
        task = asyncio.create_task(linkedin.postings(Interrupted({}), references))
        await entered.wait()
        if cancel:
            task.cancel()
        with pytest.raises(asyncio.CancelledError if cancel else RuntimeError):
            await task
        assert started == references[1:6]
        assert set(cancelled) == set(started)

    asyncio.run(asyncio.wait_for(run(), timeout=1))


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
        "https://nl.linkedin.com/jobs/view/111",
        "https://www.linkedin.com:443/jobs/view/111",
        "https://www.linkedin.com/comm/jobs/view/111?trk=eml",  # a job alert email's link
        "https://nl.linkedin.com/jobs/search/?currentJobId=111&keywords=economist",
        "https://nl.linkedin.com/jobs/view/111?currentJobId=222",  # the path names the posting
    )
    # the cache holds the address and the posting, so no reference costs a request
    for address in (
        "111",
        CANONICAL,
        "https://www.linkedin.com/jobs/view/economist-at-acme-111",
        "https://linkedin.com/jobs/view/economist-at-acme-111",
        *others,
    ):
        fetcher.requests.clear()
        assert asyncio.run(linkedin.postings(fetcher, [address])) == {address: job}
        assert fetcher.requests == []
    # Slugless references need the guest resolver even when they name a country.
    for address in others:
        fetcher.requests.clear()
        cache.CACHE.close()
        cache.CACHE.path.unlink(missing_ok=True)
        assert asyncio.run(linkedin.postings(fetcher, [address])) == {address: job}
        assert fetcher.requests == [f"{FRAGMENT}/111?_l=en_US", CANONICAL]


@pytest.mark.parametrize(
    "reference",
    [
        "https://www.linkedin.com/jobs/search",  # no posting id anywhere
        "https://www.linkedin.com/jobs/search/?currentJobId=111%2F222",  # not one id
        "https://example.test/private-123",  # another site's page ending in digits
        "https://nl.linkedin.com/company/acme-111",  # linkedin, but not a posting
        "ftp://nl.linkedin.com/jobs/view/economist-at-acme-111",  # not a web address
        "https://nl.linkedin.com/jobs/view/economist-at-acme-\uff11\uff11\uff11",  # fullwidth digits
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
    references = [
        "https://www.linkedin.com/jobs/view/economist-at-acme-111",
        CANONICAL,
        "https://uk.linkedin.com/jobs/view/economist-at-acme-111",
        "111",
    ]
    got = asyncio.run(linkedin.postings(fetcher, references))
    # one posting, fetched once from the first canonical address
    assert fetcher.requests == [CANONICAL]
    assert list(got) == references
    assert all(job == got[CANONICAL] for job in got.values())
    assert fetched(got, "111")["url"] == CANONICAL


def test_postings_stop_looking_up_ids_once_rate_limited(unlimited, monkeypatch, caplog):
    monkeypatch.setattr(client, "RETRY_DELAY", 0)
    fetcher = StubFetcher({"jobPosting": rate_limited()})
    with caplog.at_level(logging.WARNING, logger="jobrake.sites.linkedin"):
        assert asyncio.run(linkedin.postings(fetcher, [str(n) for n in range(111, 135)])) == {}
    # The six lookups in progress can retry; the remaining IDs never start.
    assert fetcher.requests.count(f"{FRAGMENT}/111?_l=en_US") == 4
    assert set(fetcher.requests) <= {f"{FRAGMENT}/{n}?_l=en_US" for n in range(111, 117)}
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


@pytest.mark.parametrize("by_id", [False, True])
def test_postings_fetch_a_us_posting_on_www(unlimited, caplog, by_id):
    www = "https://www.linkedin.com/jobs/view/economist-at-acme-111"
    reference = "111" if by_id else www
    fetcher = StubFetcher(
        {
            "jobPosting/111": ok(en_fragment(url=www)),
            www: ok(f'<link rel="canonical" href="{www}">' + job_page(title="Economist")),
        }
    )
    with caplog.at_level(logging.WARNING, logger="jobrake.sites.linkedin"):
        job = fetched(asyncio.run(linkedin.postings(fetcher, [reference])), reference)
    assert (job["id"], job["url"], job["title"]) == ("111", www, "Economist")
    assert job["posted_at"] == "2026-08-05T08:04:27.000Z"
    assert fetcher.requests == ([f"{FRAGMENT}/111?_l=en_US", www] if by_id else [www])
    assert caplog.records == []


def test_postings_follow_a_foreign_www_pages_canonical_link(unlimited):
    www = "https://www.linkedin.com/jobs/view/economist-at-acme-111"
    fetcher = StubFetcher(
        {
            www: ok(f'<link rel="canonical" href="{CANONICAL}">' + en_fragment(url=www)),
            CANONICAL: ok(job_page(title="Economist")),
        }
    )
    got = asyncio.run(linkedin.postings(fetcher, [www]))
    job = fetched(got, www)
    assert fetcher.requests == [www, CANONICAL]
    assert (job["url"], job["title"], job["description"]) == (
        CANONICAL,
        "Economist",
        "Great & big role",
    )
    assert job["posted_at"] == "2026-08-05T08:04:27.000Z"
    assert job["locations"] == [{"name": "NL", "country_code": "NL", "latitude": 52.37}]
    assert asyncio.run(linkedin.postings(StubFetcher({}), [www])) == got


@pytest.mark.parametrize(
    "candidate",
    [
        not_found(),
        network_down(),
        ok(
            '<link rel="canonical" href="https://www.linkedin.com/jobs/view/economist-at-acme-111">'
        ),
    ],
)
def test_postings_resolve_a_failed_candidate_with_the_guest_fragment(unlimited, candidate, caplog):
    www = "https://www.linkedin.com/jobs/view/economist-at-acme-111"
    fetcher = StubFetcher(
        {
            www: candidate,
            "jobPosting/111": ok(en_fragment()),
            CANONICAL: ok(job_page(title="Economist")),
        }
    )
    job = fetched(asyncio.run(linkedin.postings(fetcher, [www])), www)
    assert (job["url"], job["title"], job["posted_at"]) == (
        CANONICAL,
        "Economist",
        "2026-08-05T08:04:27.000Z",
    )
    assert fetcher.requests == [www, f"{FRAGMENT}/111?_l=en_US", CANONICAL]
    assert [record for record in caplog.records if record.levelno >= logging.WARNING] == []


def test_a_failed_page_does_not_repeat_the_guest_lookup_it_already_used(unlimited):
    www = "https://www.linkedin.com/jobs/view/economist-at-acme-111"
    fetcher = StubFetcher(
        {
            www: ok("<html>Sign in</html>"),
            "jobPosting/111": ok(en_fragment()),
            CANONICAL: ok("<html>Sign in</html>"),
        }
    )
    assert asyncio.run(linkedin.postings(fetcher, [www])) == {}
    assert fetcher.requests == [www, f"{FRAGMENT}/111?_l=en_US", CANONICAL]


@pytest.mark.parametrize("canonical", [None, OTHER])
def test_postings_resolve_a_page_without_its_own_canonical_metadata(unlimited, canonical):
    www = "https://www.linkedin.com/jobs/view/economist-at-acme-111"
    metadata = f'<link rel="canonical" href="{canonical}">' if canonical else ""
    fetcher = StubFetcher(
        {
            www: ok(metadata + job_page(title="Wrong")),
            "jobPosting/111": ok(en_fragment()),
            CANONICAL: ok(job_page(title="Economist")),
        }
    )
    job = fetched(asyncio.run(linkedin.postings(fetcher, [www])), www)
    assert (job["url"], job["title"]) == (CANONICAL, "Economist")
    assert fetcher.requests == [www, f"{FRAGMENT}/111?_l=en_US", CANONICAL]


@pytest.mark.parametrize("has_fields", [False, True])
def test_an_expired_page_cannot_replace_fields_from_its_surviving_fragment(unlimited, has_fields):
    search_page = '<img class="artdeco-entity-image" data-delayed-url="wrong-logo.png">'

    class Expired(StubFetcher):
        async def fetch(self, url, *, headers=None, json=None, follow_redirects=True):
            result = await super().fetch(
                url, headers=headers, json=json, follow_redirects=follow_redirects
            )
            if url == CANONICAL:
                result.url = "https://nl.linkedin.com/jobs/search?trk=expired_jd_redirect"
            return result

    fragment = en_fragment() if has_fields else f'<a class="topcard__link" href="{CANONICAL}"></a>'
    fetcher = Expired({CANONICAL: ok(search_page), "jobPosting/111": ok(fragment)})
    got = asyncio.run(linkedin.postings(fetcher, ["111"]))
    if not has_fields:
        assert got == {}
        assert cache.CACHE.get("linkedin", ["111"]) == {}
        return
    job = fetched(got, "111")
    assert (job["title"], job["company"], job["company_logo"]) == (
        "Economist",
        "Acme",
        "https://media.licdn.com/acme-logo.png",
    )
    assert job["url"] == CANONICAL
    assert fetcher.requests == [f"{FRAGMENT}/111?_l=en_US", CANONICAL]


@pytest.mark.parametrize("metadata", [False, True])
def test_postings_reuse_a_response_already_redirected_to_its_canonical_url(unlimited, metadata):
    www = "https://www.linkedin.com/jobs/view/economist-at-acme-111"

    class Redirected(StubFetcher):
        async def fetch(self, url, *, headers=None, json=None, follow_redirects=True):
            result = await super().fetch(
                url, headers=headers, json=json, follow_redirects=follow_redirects
            )
            result.url = CANONICAL
            return result

    link = f'<link rel="canonical" href="{CANONICAL}">' if metadata else ""
    fetcher = Redirected(
        {www: ok(link + job_page(title="Economist")), "jobPosting/111": not_found()}
    )
    job = fetched(asyncio.run(linkedin.postings(fetcher, [www])), www)
    assert (job["url"], job["title"]) == (CANONICAL, "Economist")
    assert fetcher.requests == [www]
