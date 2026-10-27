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

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    site TEXT NOT NULL,
    id TEXT NOT NULL,
    -- The JobDict as a JSON object.
    job TEXT NOT NULL,
    -- Unix time in seconds when the row was written.
    stored_at REAL NOT NULL,
    PRIMARY KEY (site, id)
)"""


def _env_seconds(name: str, default: float) -> float:
    """Read lifetime seconds from an environment variable, with a fallback."""
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


class Cache:
    """
    Store whole ``JobDict`` records in one SQLite table, keyed by site and posting ID.

    A row stays fresh for ``ttl`` seconds, and opening the cache deletes
    expired rows. Each row read passes through ``make_job``, so a row whose
    keys no longer fit ``JobDict`` is a miss, which the next fetch replaces. A
    storage or decoding failure logs one warning with the path and disables
    this instance, so callers see misses and keep fetching.

    Attributes:
        path: SQLite database path. The cache opens it on first access.
        ttl: Seconds a row remains fresh.
    """

    def __init__(self, path: str | Path | None = None, *, ttl: float | None = None) -> None:
        """
        Configure lazy storage and the row lifetime.

        An omitted ``path`` selects ``JOBRAKE_CACHE_PATH`` or the platform
        user-cache directory. An omitted ``ttl`` uses ``JOBRAKE_CACHE_TTL``,
        with ``TTL`` as the fallback.

        Raises:
            ValueError: ``ttl`` is not finite and positive.
        """
        self.ttl = float(ttl) if ttl is not None else _env_seconds("JOBRAKE_CACHE_TTL", TTL)
        if not math.isfinite(self.ttl) or self.ttl <= 0:
            raise ValueError(f"ttl ({self.ttl:.10g}) must be finite and positive")
        self.path = Path(path) if path else _default_path()
        self._conn: sqlite3.Connection | None = None
        self._broken = False

    def _connect(self) -> sqlite3.Connection | None:
        if self._broken:
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
            self._give_up(error)
        return self._conn

    def close(self) -> None:
        """Close the SQLite connection. A working cache reopens it on the next read or write."""
        if self._conn is not None:
            conn, self._conn = self._conn, None
            conn.close()

    def _give_up(self, error: Exception) -> None:
        if self._broken:
            return
        self._broken = True
        with contextlib.suppress(sqlite3.Error):
            self.close()
        logger.warning("cache disabled (%s): %s", self.path, error)

    def get(self, site: str, ids: Iterable[str]) -> dict[str, JobDict]:
        """
        Read the fresh records of one site for the requested posting IDs.

        A row ``make_job`` rejects is left out, and the count of rejected rows
        logs at DEBUG. A storage or decoding failure disables the cache and
        returns an empty dict.
        """
        ids = list(dict.fromkeys(ids))
        conn = self._connect()
        if conn is None or not ids:
            return {}
        try:
            placeholders = ", ".join("?" for _ in ids)
            rows = conn.execute(
                f"SELECT id, job, stored_at FROM jobs WHERE site = ? AND id IN ({placeholders})",
                [site, *ids],
            ).fetchall()
            fresh_after = time.time() - self.ttl
            found: dict[str, JobDict] = {}
            rejected = 0
            for posting_id, stored, stored_at in rows:
                # SQLite may return a nonnumeric value despite the REAL declaration.
                if not isinstance(stored_at, int | float) or not math.isfinite(stored_at):
                    raise ValueError(f"cache stored_at is not a finite number: {stored_at!r}")
                if stored_at < fresh_after:
                    continue
                try:
                    found[posting_id] = make_job(**json.loads(stored))
                except TypeError:
                    rejected += 1
        except (json.JSONDecodeError, OSError, sqlite3.Error, ValueError) as error:
            self._give_up(error)
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

        A storage or serialization failure disables the cache.
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
            self._give_up(error)


def __getattr__(name: str) -> Cache:
    # One cache per process, built when a fetch first reads ``CACHE``. Its
    # environment settings are read at that moment, so importing jobrake
    # neither reads them nor warns about them.
    if name == "CACHE":
        cache = globals()["CACHE"] = Cache()
        return cache
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
