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


def test_retention_purges_fields_but_keeps_tombstones(tmp_path):
    cache = make_cache(tmp_path)
    cache.put("linkedin", {"111": POSTING, "222": None})
    age_rows(cache, RETENTION + 1)
    reopened = make_cache(tmp_path)
    assert reopened.get("linkedin", ["111", "222"]) == {"222": None}
    assert reopened._conn.execute("SELECT count(*) FROM postings").fetchone() == (1,)


def test_corrupt_json_disables_cache_instead_of_escaping(tmp_path, caplog):
    cache = make_cache(tmp_path)
    cache.put("linkedin", {"111": POSTING})
    cache._conn.execute("UPDATE postings SET fields = 'not json'")
    cache._conn.commit()

    assert cache.get("linkedin", ["111"]) == {}
    assert cache._broken
    assert "disabled" in caplog.text


def test_unserializable_fields_disable_cache(tmp_path):
    cache = make_cache(tmp_path)

    cache.put("linkedin", {"111": {"bad": object()}})

    assert cache._broken


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
