"""On-disk cache for hydrated postings."""

from __future__ import annotations

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

TTL = 7 * 24 * 3600  # seconds before cached fields go stale (live postings can be edited)
# Rows older than RETENTION are purged on open, keeping the file from growing forever.
RETENTION = 30 * 24 * 3600

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS postings (
    site       TEXT NOT NULL,
    id         TEXT NOT NULL,
    fields     TEXT, -- JSON of the extracted fields; NULL means the posting is gone (tombstone)
    fetched_at REAL NOT NULL,
    PRIMARY KEY (site, id)
)"""


def _default_path() -> Path:
    """The platform user-cache location for the posting database."""
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
    Best-effort ``(site, id) -> posting fields`` cache backed by sqlite.

    Persists the ``fetch_postings`` contract between runs: a dict holds the
    fields parsed from the posting, NULL is a tombstone (the posting is
    gone), and an absent row means not fetched yet. Fields older than ``ttl`` are treated as
    absent, so employer edits are eventually picked up; tombstones never
    expire, since a removed posting does not come back. Rows older than
    ``retention`` are deleted when the file is opened.

    Never raises: the first sqlite/OS failure logs a warning and disables
    the cache for the rest of the process. The worst a broken cache may
    cost is extra requests.
    """

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        ttl: float = TTL,
        retention: float = RETENTION,
    ):
        if not math.isfinite(ttl) or ttl <= 0:
            raise ValueError(f"ttl ({ttl}) must be finite and positive")
        if not math.isfinite(retention) or retention < ttl:
            raise ValueError(
                f"retention ({retention}) must be finite and at least ttl ({ttl}),"
                " or rows would be purged before they go stale"
            )
        self.path = Path(path) if path else _default_path()
        self.ttl = ttl
        self.retention = retention
        self._conn: sqlite3.Connection | None = None
        self._broken = False

    def _connect(self) -> sqlite3.Connection | None:
        if self._broken:
            return None
        if self._conn is None:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(self.path)
                conn.execute(_SCHEMA)
                conn.execute(
                    "DELETE FROM postings WHERE fetched_at < ?",
                    (time.time() - self.retention,),
                )
                conn.commit()
            except (sqlite3.Error, OSError) as error:
                self._give_up(error)
                return None
            self._conn = conn
        return self._conn

    def _give_up(self, error: Exception) -> None:
        self._broken = True
        self._conn = None
        logger.warning("posting cache disabled (%s): %s", self.path, error)

    def get(self, site: str, ids: Iterable[str]) -> dict[str, dict | None]:
        """Cached entries among ``ids``: fresh fields, or ``None`` for gone postings."""
        ids = list(ids)
        conn = self._connect()
        if conn is None or not ids:
            return {}
        try:
            rows = conn.execute(
                "SELECT id, fields, fetched_at FROM postings"
                f" WHERE site = ? AND id IN ({','.join('?' * len(ids))})",
                [site, *ids],
            ).fetchall()
        except (sqlite3.Error, OSError) as error:
            self._give_up(error)
            return {}
        stale = time.time() - self.ttl
        return {
            pid: None if fields is None else json.loads(fields)
            for pid, fields, at in rows
            if fields is None or at >= stale
        }

    def put(self, site: str, postings: dict[str, dict | None]) -> None:
        """Upsert entries; values follow the ``get`` contract."""
        conn = self._connect()
        if conn is None or not postings:
            return
        now = time.time()
        try:
            conn.executemany(
                "INSERT OR REPLACE INTO postings (site, id, fields, fetched_at)"
                " VALUES (?, ?, ?, ?)",
                [
                    (
                        site,
                        pid,
                        None if fields is None else json.dumps(fields, ensure_ascii=False),
                        now,
                    )
                    for pid, fields in postings.items()
                ],
            )
            conn.commit()
        except (sqlite3.Error, OSError) as error:
            self._give_up(error)
