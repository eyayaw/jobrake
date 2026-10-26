"""Cache tests for stored records, expiry, rows that no longer fit, and corrupt data."""

import contextlib
import json
import logging
import math
import os
import sqlite3
import subprocess
import sys
from unittest import mock

import pytest
from hypothesis import given
from hypothesis import strategies as st

from jobrake.cache import TTL, Cache
from jobrake.models import make_job

JOB = make_job(
    site="linkedin", id="111", url="https://nl.linkedin.com/jobs/view/111", applicants=25
)
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


def test_a_record_comes_back_under_its_own_site(make_cache):
    cache = make_cache()
    cache.put([JOB])
    assert cache.get("linkedin", ["111", "999"]) == {"111": JOB}
    assert cache.get("indeed", ["111"]) == {}


def test_expired_rows_miss_and_are_deleted_when_the_cache_opens(make_cache):
    cache = make_cache()
    cache.put([JOB])
    run_sql(cache, "UPDATE jobs SET stored_at = stored_at - ?", (TTL + 1,))
    assert cache.get("linkedin", ["111"]) == {}
    reopened = make_cache()
    reopened.get("linkedin", ["111"])
    assert run_sql(reopened, "SELECT count(*) FROM jobs") == [(0,)]


def test_a_row_that_no_longer_fits_job_dict_is_a_miss(make_cache, caplog):
    # A row from an older field set passes through make_job, which rejects it.
    # Its neighbors keep coming back, and the next fetch replaces it.
    cache = make_cache()
    other = make_job(site="linkedin", id="222", url="https://nl.linkedin.com/jobs/view/222")
    cache.put([JOB, other])
    moved_on = json.dumps({**JOB, "headcount": 4})
    run_sql(cache, "UPDATE jobs SET job = ? WHERE id = '111'", (moved_on,))
    with caplog.at_level(logging.DEBUG, logger="jobrake.cache"):
        assert cache.get("linkedin", ["111", "222"]) == {"222": other}
    assert "1 row for linkedin did not fit JobDict" in caplog.text
    cache.put([JOB])
    assert cache.get("linkedin", ["111"]) == {"111": JOB}


@pytest.mark.parametrize(
    ("column", "value"), [("job", "not json"), ("stored_at", "bad")], ids=["json", "stored_at"]
)
def test_corrupt_data_disables_the_cache_with_one_warning(make_cache, caplog, column, value):
    cache = make_cache()
    cache.put([JOB])
    run_sql(cache, f"UPDATE jobs SET {column} = ?", (value,))
    assert cache.get("linkedin", ["111"]) == {}
    assert cache.get("linkedin", ["111"]) == {}  # later lookups miss quietly
    (warning,) = caplog.records
    assert warning.message.startswith(f"cache disabled ({cache.path})")


def test_an_unserializable_record_disables_the_cache(make_cache, caplog):
    cache = make_cache()
    cache.put([JOB])
    cache.put([{**JOB, "id": "222", "description": object()}])
    # The stored row would hit on a cache that stayed enabled.
    assert cache.get("linkedin", ["111"]) == {}
    assert "disabled" in caplog.text


@given(ttl=st.floats(max_value=0) | NOT_FINITE)
def test_a_ttl_that_is_not_finite_and_positive_is_rejected(ttl):
    with pytest.raises(ValueError, match=r"^ttl "):
        Cache("unused.sqlite3", ttl=ttl)


def test_environment_supplies_path_and_ttl(tmp_path, monkeypatch):
    path = tmp_path / "elsewhere" / "jobrake.sqlite3"
    monkeypatch.setenv("JOBRAKE_CACHE_PATH", str(path))
    monkeypatch.setenv("JOBRAKE_CACHE_TTL", "5400")

    cache = Cache()

    assert (cache.path, cache.ttl) == (path, 5400)
    # An argument beats the variable.
    assert Cache(tmp_path / "given.sqlite3", ttl=60).ttl == 60


@given(seconds=st.floats(max_value=0).map(str) | st.sampled_from(["", "weekly", "inf", "nan"]))
def test_an_unusable_environment_ttl_falls_back(seconds):
    with mock.patch.dict(os.environ, {"JOBRAKE_CACHE_TTL": seconds}):
        assert Cache().ttl == TTL


def test_the_shared_cache_reads_the_environment_on_first_use(tmp_path):
    # A fresh interpreter, because the suite's fixture replaces the shared cache.
    code = """
import os
import jobrake
from jobrake import cache

assert "CACHE" not in vars(cache), "importing jobrake built the shared cache"
os.environ["JOBRAKE_CACHE_TTL"] = "5400"
assert cache.CACHE.ttl == 5400
"""
    env = {k: v for k, v in os.environ.items() if not k.startswith("JOBRAKE_CACHE_")}
    env["JOBRAKE_CACHE_PATH"] = str(tmp_path / "jobrake.sqlite3")
    subprocess.run([sys.executable, "-c", code], env=env, check=True)
