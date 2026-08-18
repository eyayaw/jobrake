"""Best-effort SQLite cache for hydrated postings."""

import json
import logging
import math
import os
import sqlite3
import sys
import time
from collections.abc import Iterable
from pathlib import Path

logger = logging.getLogger(__name__)

PACKAGE_NAME = "jobrake"
CACHE_DB_NAME = "postings.sqlite3"
TTL = 7 * 24 * 3600  # seconds
RETENTION = 30 * 24 * 3600  # older will be deleted on startup
_SCHEMA = """
CREATE TABLE IF NOT EXISTS postings (
    site TEXT NOT NULL,
    id TEXT NOT NULL,
    fields TEXT,
    fetched_at REAL NOT NULL,
    PRIMARY KEY (site, id)
)"""


def _default_path() -> Path:
    """Return the platform user-cache location."""
    match sys.platform:
        case "darwin":
            base = Path.home() / "Library" / "Caches"
        case "win32":
            base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        case _:
            base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / PACKAGE_NAME / CACHE_DB_NAME


class PostingCache:
    """
    Store posting fields or gone-posting tombstones under ``(site, id)``.

    Fields expire after ``ttl`` and leave the cache after ``retention``.
    Tombstones stay until the cache is deleted because a removed posting does not return.
    A storage or decoding failure logs once and disables the cache, so cache
    damage can cost requests but cannot stop a scrape.
    """

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        ttl: float = TTL,
        retention: float = RETENTION,
    ):
        self.ttl = float(ttl)
        self.retention = float(retention)
        if not math.isfinite(self.ttl) or self.ttl <= 0:
            raise ValueError(f"ttl ({ttl}) must be finite and positive")
        if not math.isfinite(self.retention) or self.retention < self.ttl:
            raise ValueError(f"retention ({retention}) must be finite and at least ttl ({ttl})")
        self.path = Path(path) if path else _default_path()
        self._conn: sqlite3.Connection | None = None
        self._broken = False

    def _connect(self) -> sqlite3.Connection | None:
        if self._broken:
            return None
        if self._conn is None:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._conn = sqlite3.connect(self.path)
                self._conn.execute(_SCHEMA)
                self._conn.execute(
                    "DELETE FROM postings WHERE fields IS NOT NULL AND fetched_at < ?",
                    (time.time() - self.retention,),
                )
                self._conn.commit()
            except (sqlite3.Error, OSError) as error:
                self._give_up(error)
        return self._conn

    def _give_up(self, error: Exception) -> None:
        if self._broken:
            return
        self._broken = True
        if self._conn is not None:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass
            self._conn = None
        logger.warning("posting cache disabled (%s): %s", self.path, error)

    def get(self, site: str, ids: Iterable[str]) -> dict[str, dict | None]:
        """Return fresh cached entries among ``ids``."""
        ids = list(dict.fromkeys(ids))
        conn = self._connect()
        if conn is None or not ids:
            return {}
        try:
            rows = conn.execute(
                "SELECT id, fields, fetched_at FROM postings"
                f" WHERE site = ? AND id IN ({','.join('?' * len(ids))})",
                [site, *ids],
            )
            stale = time.time() - self.ttl
            found = {}
            for posting_id, fields, fetched_at in rows:
                if fields is None:
                    found[posting_id] = None
                    continue
                # SQLite's flexible typing lets any value sit in the REAL column.
                if not isinstance(fetched_at, int | float) or not math.isfinite(fetched_at):
                    raise ValueError(f"posting fetched_at is not a finite number: {fetched_at!r}")
                if fetched_at >= stale:
                    value = json.loads(fields)
                    if not isinstance(value, dict):
                        raise ValueError("posting fields are not a JSON object")
                    found[posting_id] = value
            return found
        except (json.JSONDecodeError, OSError, sqlite3.Error, TypeError, ValueError) as error:
            self._give_up(error)
            return {}

    def put(self, site: str, postings: dict[str, dict | None]) -> None:
        """Upsert posting fields or tombstones."""
        conn = self._connect()
        if conn is None or not postings:
            return
        try:
            now = time.time()
            conn.executemany(
                "INSERT OR REPLACE INTO postings (site, id, fields, fetched_at) VALUES (?, ?, ?, ?)",
                (
                    (
                        site,
                        posting_id,
                        None if fields is None else json.dumps(fields, ensure_ascii=False),
                        now,
                    )
                    for posting_id, fields in postings.items()
                ),
            )
            conn.commit()
        except (OSError, sqlite3.Error, TypeError, ValueError) as error:
            self._give_up(error)
