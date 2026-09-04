"""Cache tests for stored fields, expiry, and corrupt data."""

import json
import math
import sqlite3
import time

import pytest

from jobrake.cache import _VERSIONS, GEOIDS, POSTINGS, RETENTION, TTL, Cache

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
    cache._conn.execute("UPDATE postings SET fields = 'not json'")
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


def test_rows_of_another_format_are_invisible(tmp_path):
    # Stored values belong to the code that wrote them, so a jobrake whose
    # fields or parsers have moved on neither serves another format's rows nor
    # loses its own to them.
    path = tmp_path / "jobrake.sqlite3"
    cache = Cache(path)
    cache.put(POSTINGS, "linkedin", {"111": POSTING})
    moved_on = json.dumps({"description": "Role", "headcount": 4})
    with sqlite3.connect(path) as other:
        other.executemany(
            f"INSERT OR REPLACE INTO {POSTINGS} VALUES (?, ?, ?, ?, ?)",
            [
                (_VERSIONS[POSTINGS] + 1, "linkedin", "111", moved_on, time.time()),
                (_VERSIONS[POSTINGS] + 1, "linkedin", "222", moved_on, time.time()),
            ],
        )
    assert cache.get(POSTINGS, "linkedin", ["111", "222"]) == {"111": POSTING}
    assert not cache._broken


def test_table_versions_are_independent(tmp_path, monkeypatch):
    # Place resolutions cost paced requests, so a reworked posting parser leaves
    # them in place.
    path = tmp_path / "jobrake.sqlite3"
    place = {"geoId": "102011674"}
    cache = Cache(path)
    cache.put(POSTINGS, "linkedin", {"111": POSTING})
    cache.put(GEOIDS, "linkedin", {"enschede": place})

    monkeypatch.setitem(_VERSIONS, POSTINGS, _VERSIONS[POSTINGS] + 1)
    moved_on = Cache(path)
    assert moved_on.get(POSTINGS, "linkedin", ["111"]) == {}
    assert moved_on.get(GEOIDS, "linkedin", ["enschede"]) == {"enschede": place}


def test_a_table_from_an_older_jobrake_is_rebuilt(tmp_path):
    # A shape from before the current columns cannot take today's rows, so
    # opening the database replaces the table and starts collecting again.
    path = tmp_path / "jobrake.sqlite3"
    with sqlite3.connect(path) as old:
        old.execute(f"CREATE TABLE {POSTINGS} (scope TEXT, key TEXT, value TEXT, stored_at REAL)")
        old.execute(
            f"INSERT INTO {POSTINGS} VALUES (?, ?, ?, ?)",
            ("linkedin", "111", json.dumps(POSTING), time.time()),
        )
    cache = Cache(path)
    assert cache.get(POSTINGS, "linkedin", ["111"]) == {}
    assert not cache._broken  # it starts over instead of giving up
    cache.put(POSTINGS, "linkedin", {"111": POSTING})
    assert cache.get(POSTINGS, "linkedin", ["111"]) == {"111": POSTING}
