"""PostingCache unit tests: contract, expiry, and the never-raise posture."""

import math

import pytest

from jobrake.cache import RETENTION, TTL, PostingCache

POSTING = {"description": "Role", "applicants": 25}


def make_cache(tmp_path, **kwargs):
    return PostingCache(tmp_path / "cache.sqlite3", **kwargs)


def age_rows(cache, seconds):
    """Backdate every row, as if it were written ``seconds`` ago."""
    cache._conn.execute("UPDATE postings SET fetched_at = fetched_at - ?", (seconds,))
    cache._conn.commit()


def test_roundtrip_including_tombstones(tmp_path):
    cache = make_cache(tmp_path)
    cache.put("linkedin", {"111": POSTING, "222": None})
    assert cache.get("linkedin", ["111", "222", "999"]) == {"111": POSTING, "222": None}


def test_sites_do_not_collide(tmp_path):
    cache = make_cache(tmp_path)
    cache.put("linkedin", {"111": POSTING})
    assert cache.get("indeed", ["111"]) == {}


def test_stale_fields_are_absent_but_tombstones_never_expire(tmp_path):
    cache = make_cache(tmp_path)
    cache.put("linkedin", {"111": POSTING, "222": None})
    age_rows(cache, TTL + 1)
    assert cache.get("linkedin", ["111", "222"]) == {"222": None}


def test_retention_purges_old_rows_on_open(tmp_path):
    cache = make_cache(tmp_path)
    cache.put("linkedin", {"111": None})  # even tombstones leave eventually
    age_rows(cache, RETENTION + 1)
    reopened = make_cache(tmp_path)
    assert reopened.get("linkedin", ["111"]) == {}
    assert reopened._conn.execute("SELECT count(*) FROM postings").fetchone() == (0,)


@pytest.mark.parametrize(
    ("ttl", "retention"),
    [
        (math.nan, RETENTION),
        (TTL, TTL - 1),  # rows would purge before going stale
    ],
)
def test_invalid_policy_rejected(tmp_path, ttl, retention):
    with pytest.raises(ValueError):
        PostingCache(tmp_path / "cache.sqlite3", ttl=ttl, retention=retention)
