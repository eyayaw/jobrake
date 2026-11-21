"""SQLite cache of fetched postings as whole ``JobDict`` records."""

import contextlib
import json
import logging
import math
import os
import sqlite3
import sys
import time
from collections.abc import Iterable
from gettext import ngettext
from pathlib import Path

from jobrake.models import JobDict, make_job

logger = logging.getLogger(__name__)

TTL = 7 * 24 * 3600  # seconds
# Seconds the cache is skipped after a lock that outlasted SQLite's busy timeout, so a lock that
# another process keeps costs that wait about once a minute, not once per posting.
LOCK_PAUSE = 60

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    site TEXT NOT NULL,
    id TEXT NOT NULL,
    -- The JobDict as a JSON object.
    job TEXT NOT NULL,
    -- Unix time in seconds when the row was written.
    stored_at REAL NOT NULL,
    PRIMARY KEY (site, id)
) STRICT"""


def _env_seconds(name: str, default: float) -> float:
    """
    Return an environment variable as seconds, or ``default`` when it is unset or empty.

    A value that is not a finite positive number logs a warning and gives ``default`` too.
    """
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        seconds = float(raw)
    except ValueError:
        seconds = 0.0
    # float() also accepts NaN and infinity.
    if not math.isfinite(seconds) or seconds <= 0:
        logger.warning("%s=%r is not a positive number of seconds; using %.0f", name, raw, default)
        return default
    return seconds


def _default_path() -> Path:
    if override := os.environ.get("JOBRAKE_CACHE_PATH"):
        try:
            return Path(override).expanduser()
        except RuntimeError:
            logger.warning(
                "JOBRAKE_CACHE_PATH=%r names no home directory; using the default", override
            )
    match sys.platform:
        case "darwin":
            base = Path.home() / "Library" / "Caches"
        case "win32":
            base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        case "linux" | _:
            base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "jobrake" / "jobrake.sqlite3"


def _locked(error: Exception) -> bool:
    """Tell whether SQLite refused a statement for a lock another connection held too long."""
    # An extended code, such as SQLITE_BUSY_SNAPSHOT, carries its primary code in its low byte
    # (https://sqlite.org/rescode.html, checked 2026-11-21).
    code = getattr(error, "sqlite_errorcode", 0) & 0xFF
    return code in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)


class Cache:
    """
    Store whole ``JobDict`` records in one SQLite table, keyed by site and posting ID.

    A row stays fresh for ``ttl`` seconds, and opening the cache deletes expired rows.
    Each row read passes through ``make_job``, so a row whose keys no longer fit ``JobDict`` is a
    miss, which the next fetch replaces. A storage or decoding failure logs one warning with the
    path and disables this instance, so callers see misses and keep fetching. A lock another
    process holds past SQLite's busy timeout skips the cache for ``LOCK_PAUSE`` seconds.

    Attributes:
        path: SQLite database path. The cache opens it on first access.
        ttl: Seconds a row remains fresh.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        """
        Take the row lifetime from ``JOBRAKE_CACHE_TTL``, falling back to ``TTL``.

        An omitted ``path`` selects ``JOBRAKE_CACHE_PATH`` or the platform user-cache directory.
        The database opens on first use.
        """
        self.ttl = _env_seconds("JOBRAKE_CACHE_TTL", TTL)
        self.path = Path(path) if path else _default_path()
        self._conn: sqlite3.Connection | None = None
        self._broken = False
        self._paused_until = -math.inf  # time.monotonic() before which a lock skips the cache

    def _connect(self) -> sqlite3.Connection | None:
        if self._broken or time.monotonic() < self._paused_until:
            return None
        if self._conn is not None:
            return self._conn
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self.path)
            self._conn.execute(_SCHEMA)
            self._conn.execute("DELETE FROM jobs WHERE stored_at < ?", (time.time() - self.ttl,))
            self._conn.commit()
        except (sqlite3.Error, OSError) as error:
            self._fail(error)
        return self._conn

    def close(self) -> None:
        """Close the SQLite connection. A working cache reopens it on the next read or write."""
        if self._conn is not None:
            conn, self._conn = self._conn, None
            conn.close()

    def _fail(self, error: Exception) -> None:
        if not _locked(error):
            self._give_up(error)
            return
        # Closing rolls back this call's transaction, and the first read or write after the pause
        # opens the database again.
        with contextlib.suppress(sqlite3.Error):
            self.close()
        self._paused_until = time.monotonic() + LOCK_PAUSE
        logger.warning(
            "cache %s is locked by another process, so jobrake skips it for %d seconds",
            self.path,
            LOCK_PAUSE,
        )

    def _give_up(self, error: Exception) -> None:
        self._broken = True
        with contextlib.suppress(sqlite3.Error):
            self.close()
        logger.warning(
            "cache disabled (%s): %s. Delete that file if it is damaged, or set "
            "JOBRAKE_CACHE_PATH to another path",
            self.path,
            error,
        )

    def get(self, site: str, ids: Iterable[str]) -> dict[str, JobDict]:
        """
        Read the fresh records of one site for the requested posting IDs.

        A row ``make_job`` rejects is left out, and the count of rejected rows logs at DEBUG.
        A lock another process holds returns an empty dict, as does a call in the pause after one.
        Any other storage or decoding failure also returns an empty dict and disables the cache.
        """
        ids = list(dict.fromkeys(ids))
        conn = self._connect()
        if conn is None or not ids:
            return {}
        try:
            # One JSON parameter holds every ID, so no call reaches SQLite's limit on parameters.
            # json_each is built in from SQLite 3.38.0, and the STRICT table needs 3.37.0
            # (https://sqlite.org/json1.html, checked 2026-11-20).
            rows = conn.execute(
                "SELECT id, job FROM jobs"
                " WHERE site = ? AND id IN (SELECT value FROM json_each(?)) AND stored_at >= ?",
                [site, json.dumps(ids), time.time() - self.ttl],
            ).fetchall()
            found: dict[str, JobDict] = {}
            rejected = 0
            for posting_id, stored in rows:
                try:
                    found[posting_id] = make_job(**json.loads(stored))
                except TypeError:
                    rejected += 1
        except (ValueError, OSError, sqlite3.Error) as error:
            self._fail(error)
            return {}
        if rejected:
            rows = ngettext("%d row", "%d rows", rejected) % rejected
            logger.debug(
                "cache: %s for %s did not fit JobDict and will be fetched again", rows, site
            )
        return found

    def put(self, jobs: Iterable[JobDict]) -> None:
        """
        Store records, each under its own site and ID, replacing an older row.

        A lock another process holds skips the write, as does the pause after one, and any other
        storage or serialization failure disables the cache.
        """
        conn = self._connect()
        if conn is None:
            return
        try:
            now = time.time()
            conn.executemany(
                "INSERT OR REPLACE INTO jobs (site, id, job, stored_at) VALUES (?, ?, ?, ?)",
                (
                    (job["site"], job["id"], json.dumps(job, ensure_ascii=False), now)
                    for job in jobs
                ),
            )
            conn.commit()
        except (OSError, sqlite3.Error, TypeError, ValueError) as error:
            self._fail(error)


def __getattr__(name: str) -> Cache:
    # One cache per process, built when a fetch first reads ``CACHE``. Its environment settings are
    # read at that moment, so importing jobrake neither reads them nor warns about them.
    if name == "CACHE":
        cache = globals()["CACHE"] = Cache()
        return cache
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
