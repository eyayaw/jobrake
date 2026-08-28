"""Cache tests for stored fields, expiry, and corrupt data."""

import math

import pytest

from jobrake.cache import GEOIDS, POSTINGS, RETENTION, TTL, Cache

POSTING = {"description": "Role", "applicants": 25}


def make_cache(tmp_path, **kwargs):
    return Cache(tmp_path / "jobrake.sqlite3", **kwargs)


def age_rows(cache, seconds):
    """Backdate every row, as if it were written ``seconds`` ago."""
    cache._conn.execute("UPDATE postings SET stored_at = stored_at - ?", (seconds,))
    cache._conn.commit()


def test_roundtrip_including_tombstones(tmp_path):
    cache = make_cache(tmp_path)
    cache.put(POSTINGS, "linkedin", {"111": POSTING, "222": None})
    assert cache.get(POSTINGS, "linkedin", ["111", "222", "999"]) == {
        "111": POSTING,
        "222": None,
    }


def test_sites_do_not_collide(tmp_path):
    cache = make_cache(tmp_path)
    cache.put(POSTINGS, "linkedin", {"111": POSTING})
    assert cache.get(POSTINGS, "indeed", ["111"]) == {}


def test_expiry_applies_to_postings_but_not_tombstones_or_geoids(tmp_path):
    cache = make_cache(tmp_path)
    cache.put(POSTINGS, "linkedin", {"111": POSTING, "222": None})
    place = {"geoId": "7", "displayName": "Enschede, Overijssel, Netherlands"}
    cache.put(GEOIDS, "linkedin", {"enschede": place})
    age_rows(cache, TTL + 1)
    cache._conn.execute("UPDATE geoids SET stored_at = stored_at - ?", (TTL + 1,))
    cache._conn.commit()
    assert cache.get(POSTINGS, "linkedin", ["111", "222"]) == {"222": None}
    assert cache.get(GEOIDS, "linkedin", ["enschede"]) == {"enschede": place}


def test_retention_purges_fields_but_keeps_tombstones(tmp_path):
    cache = make_cache(tmp_path)
    cache.put(POSTINGS, "linkedin", {"111": POSTING, "222": None})
    age_rows(cache, RETENTION + 1)
    reopened = make_cache(tmp_path)
    assert reopened.get(POSTINGS, "linkedin", ["111", "222"]) == {"222": None}
    assert reopened._conn.execute("SELECT count(*) FROM postings").fetchone() == (1,)


def test_nonfinite_row_is_a_miss_without_disabling_the_cache(tmp_path):
    # json.dumps writes NaN by default, so rows predating the finite-number
    # rule can carry it. Such a row must miss, and only that row.
    cache = make_cache(tmp_path)
    cache.put(POSTINGS, "linkedin", {"111": {"salary_min": float("nan")}, "222": POSTING})
    assert cache.get(POSTINGS, "linkedin", ["111", "222"]) == {"222": POSTING}
    assert not cache._broken


def test_corrupt_json_disables_cache_instead_of_escaping(tmp_path, caplog):
    cache = make_cache(tmp_path)
    cache.put(POSTINGS, "linkedin", {"111": POSTING})
    cache._conn.execute("UPDATE postings SET value = 'not json'")
    cache._conn.commit()

    assert cache.get(POSTINGS, "linkedin", ["111"]) == {}
    assert cache._broken
    assert "disabled" in caplog.text


def test_corrupt_timestamp_disables_cache_instead_of_escaping(tmp_path, caplog):
    cache = make_cache(tmp_path)
    cache.put(POSTINGS, "linkedin", {"111": POSTING})
    cache._conn.execute("UPDATE postings SET stored_at = 'bad'")
    cache._conn.commit()

    assert cache.get(POSTINGS, "linkedin", ["111"]) == {}
    assert cache._broken
    assert "disabled" in caplog.text
    assert cache.get(POSTINGS, "linkedin", ["111"]) == {}  # later lookups miss quietly


def test_unserializable_fields_disable_cache(tmp_path):
    cache = make_cache(tmp_path)

    cache.put(POSTINGS, "linkedin", {"111": {"bad": object()}})

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
        Cache(tmp_path / "jobrake.sqlite3", ttl=ttl, retention=retention)
