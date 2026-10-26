"""Cache tests for stored fields, expiry, and corrupt data."""

import contextlib
import json
import math
import os
import sqlite3
import subprocess
import sys
import time
from unittest import mock

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from jobrake.cache import _VERSIONS, ADDRESSES, POSTINGS, RETENTION, TTL, Cache

POSTING = {"description": "Role", "applicants": 25}
NOT_FINITE = st.sampled_from([math.nan, math.inf])


@pytest.fixture
def make_cache(tmp_path):
    caches = []

    def make():
        cache = Cache(tmp_path / "jobrake.sqlite3")
        caches.append(cache)
        return cache

    yield make
    for cache in caches:
        cache.close()


def run_sql(cache, sql, params=()):
    with contextlib.closing(sqlite3.connect(cache.path)) as conn, conn:
        return conn.execute(sql, params).fetchall()


def age_rows(cache, seconds):
    """Backdate every row, as if it were written ``seconds`` ago."""
    run_sql(cache, "UPDATE postings SET stored_at = stored_at - ?", (seconds,))


def test_roundtrip_including_tombstones(make_cache):
    cache = make_cache()
    cache.put(POSTINGS, "linkedin", {"111": POSTING, "222": None})
    assert cache.get(POSTINGS, "linkedin", ["111", "222", "999"]) == {
        "111": POSTING,
        "222": None,
    }


def test_sites_do_not_collide(make_cache):
    cache = make_cache()
    cache.put(POSTINGS, "linkedin", {"111": POSTING})
    assert cache.get(POSTINGS, "indeed", ["111"]) == {}


def test_tombstones_and_addresses_outlive_the_freshness_period(make_cache):
    cache = make_cache()
    cache.put(POSTINGS, "linkedin", {"111": POSTING, "222": None})
    address = {"url": "https://nl.linkedin.com/jobs/view/economist-at-acme-111"}
    cache.put(ADDRESSES, "linkedin", {"111": address})
    age_rows(cache, TTL + 1)
    run_sql(cache, "UPDATE addresses SET stored_at = stored_at - ?", (TTL + 1,))
    assert cache.get(POSTINGS, "linkedin", ["111", "222"]) == {"222": None}
    assert cache.get(ADDRESSES, "linkedin", ["111"]) == {"111": address}


def test_retention_ends_tombstones_and_purges_posting_rows(make_cache):
    cache = make_cache()
    cache.put(POSTINGS, "linkedin", {"111": POSTING, "222": None})
    age_rows(cache, RETENTION + 1)
    # The open cache stops honoring the tombstone, and the next startup deletes both rows.
    assert cache.get(POSTINGS, "linkedin", ["111", "222"]) == {}
    reopened = make_cache()
    assert reopened.get(POSTINGS, "linkedin", ["111", "222"]) == {}
    assert run_sql(reopened, "SELECT count(*) FROM postings") == [(0,)]


def test_nonfinite_row_is_a_miss_without_disabling_the_cache(make_cache):
    # json.dumps writes NaN by default, so rows predating the finite-number
    # rule can carry it. Such a row must miss, and only that row.
    cache = make_cache()
    cache.put(POSTINGS, "linkedin", {"111": {"salary_min": float("nan")}, "222": POSTING})
    assert cache.get(POSTINGS, "linkedin", ["111", "222"]) == {"222": POSTING}
    assert cache.get(POSTINGS, "linkedin", ["222"]) == {"222": POSTING}  # still enabled


def test_corrupt_json_disables_cache_instead_of_escaping(make_cache, caplog):
    cache = make_cache()
    cache.put(POSTINGS, "linkedin", {"111": POSTING})
    run_sql(cache, "UPDATE postings SET fields = 'not json'")

    assert cache.get(POSTINGS, "linkedin", ["111"]) == {}
    assert "disabled" in caplog.text


def test_corrupt_timestamp_disables_cache_instead_of_escaping(make_cache, caplog):
    cache = make_cache()
    cache.put(POSTINGS, "linkedin", {"111": POSTING})
    run_sql(cache, "UPDATE postings SET stored_at = 'bad'")

    assert cache.get(POSTINGS, "linkedin", ["111"]) == {}
    assert "disabled" in caplog.text
    assert cache.get(POSTINGS, "linkedin", ["111"]) == {}  # later lookups miss quietly


def test_unserializable_fields_disable_cache(make_cache, caplog):
    cache = make_cache()
    cache.put(POSTINGS, "linkedin", {"111": POSTING})

    cache.put(POSTINGS, "linkedin", {"222": {"bad": object()}})

    # The stored row would hit on a cache that stayed enabled.
    assert cache.get(POSTINGS, "linkedin", ["111"]) == {}
    assert "disabled" in caplog.text


@given(ttl=st.floats(max_value=0) | NOT_FINITE)
def test_a_ttl_that_is_not_finite_and_positive_is_rejected(ttl):
    with pytest.raises(ValueError, match=r"^ttl "):
        Cache("unused.sqlite3", ttl=ttl)


@given(
    ttl=st.none() | st.just(TTL),
    retention=st.floats(max_value=TTL, exclude_max=True) | NOT_FINITE,
)
@example(ttl=None, retention=math.nextafter(TTL, 0))
def test_a_stated_retention_below_ttl_or_not_finite_is_rejected(ttl, retention):
    # Rows would purge before going stale, and a retention the caller stated is never repaired.
    with pytest.raises(ValueError, match=r"^retention "):
        Cache("unused.sqlite3", ttl=ttl, retention=retention)


def test_environment_supplies_path_and_lifetimes(tmp_path, monkeypatch):
    path = tmp_path / "elsewhere" / "jobrake.sqlite3"
    monkeypatch.setenv("JOBRAKE_CACHE_PATH", str(path))
    monkeypatch.setenv("JOBRAKE_CACHE_TTL", "5400")
    monkeypatch.setenv("JOBRAKE_CACHE_RETENTION", "172800")

    cache = Cache()

    assert cache.path == path
    assert cache.ttl == 5400
    assert cache.retention == 172800
    # An argument beats the variable.
    assert Cache(tmp_path / "given.sqlite3", ttl=60).ttl == 60


@given(seconds=st.floats(max_value=0).map(str) | st.sampled_from(["", "weekly", "inf", "nan"]))
def test_an_unusable_environment_lifetime_falls_back(seconds):
    with mock.patch.dict(os.environ, {"JOBRAKE_CACHE_TTL": seconds}):
        assert Cache().ttl == TTL


def test_environment_ttl_lifts_retention(monkeypatch):
    # The shared cache is built inside the first cached fetch, so this pair must not raise.
    monkeypatch.setenv("JOBRAKE_CACHE_TTL", str(RETENTION * 2))

    cache = Cache()

    assert cache.retention == cache.ttl


def test_the_shared_cache_reads_the_environment_on_first_use(tmp_path):
    # A fresh interpreter, because the suite's fixture replaces the shared cache.
    code = """
import os
import jobrake
from jobrake.sites import linkedin
from jobrake.sites.linkedin import client

assert "CACHE" not in vars(client), "importing jobrake built the shared cache"
os.environ["JOBRAKE_CACHE_TTL"] = "5400"
assert linkedin.CACHE.ttl == 5400
assert linkedin.CACHE is client.CACHE
"""
    env = {k: v for k, v in os.environ.items() if not k.startswith("JOBRAKE_CACHE_")}
    env["JOBRAKE_CACHE_PATH"] = str(tmp_path / "jobrake.sqlite3")
    subprocess.run([sys.executable, "-c", code], env=env, check=True)


def test_rows_of_another_format_are_invisible(make_cache):
    # Stored values belong to the code that wrote them, so a jobrake whose
    # fields or parsers have moved on neither serves another format's rows nor
    # loses its own to them.
    cache = make_cache()
    cache.put(POSTINGS, "linkedin", {"111": POSTING})
    moved_on = json.dumps({"description": "Role", "headcount": 4})
    for key in ("111", "222"):
        run_sql(
            cache,
            f"INSERT OR REPLACE INTO {POSTINGS} VALUES (?, ?, ?, ?, ?)",
            (_VERSIONS[POSTINGS] + 1, "linkedin", key, moved_on, time.time()),
        )
    assert cache.get(POSTINGS, "linkedin", ["111", "222"]) == {"111": POSTING}


def test_table_versions_are_independent(make_cache, monkeypatch):
    # Addresses cost paced requests, so a reworked posting parser leaves them in place.
    address = {"url": "https://nl.linkedin.com/jobs/view/economist-at-acme-111"}
    cache = make_cache()
    cache.put(POSTINGS, "linkedin", {"111": POSTING})
    cache.put(ADDRESSES, "linkedin", {"111": address})

    monkeypatch.setitem(_VERSIONS, POSTINGS, _VERSIONS[POSTINGS] + 1)
    moved_on = make_cache()
    assert moved_on.get(POSTINGS, "linkedin", ["111"]) == {}
    assert moved_on.get(ADDRESSES, "linkedin", ["111"]) == {"111": address}


def test_a_table_from_an_older_jobrake_is_rebuilt(make_cache):
    # A shape from before the current columns cannot take today's rows, so
    # opening the database replaces the table and starts collecting again.
    cache = make_cache()
    run_sql(cache, f"CREATE TABLE {POSTINGS} (scope TEXT, key TEXT, value TEXT, stored_at REAL)")
    run_sql(
        cache,
        f"INSERT INTO {POSTINGS} VALUES (?, ?, ?, ?)",
        ("linkedin", "111", json.dumps(POSTING), time.time()),
    )
    assert cache.get(POSTINGS, "linkedin", ["111"]) == {}
    cache.put(POSTINGS, "linkedin", {"111": POSTING})
    assert cache.get(POSTINGS, "linkedin", ["111"]) == {"111": POSTING}
