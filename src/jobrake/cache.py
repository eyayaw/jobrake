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
# Startup applies retention only to rows with posting fields. Tombstones stay.
RETENTION = 30 * 24 * 3600
_SCHEMA = """
CREATE TABLE IF NOT EXISTS postings (
    site TEXT NOT NULL,
    id TEXT NOT NULL,
    fields TEXT,
    fetched_at REAL NOT NULL,
    PRIMARY KEY (site, id)
)"""


class _NonstandardConstant(Exception):
    """A nonstandard JSON number treated as a row-level cache miss."""


def _reject_constant(name: str):
    raise _NonstandardConstant(name)


def _default_path() -> Path:
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
    A best-effort cache for posting fields and gone-posting tombstones.

    Entries are keyed by ``(site, id)``. Field rows expire after ``ttl`` seconds
    and are deleted after ``retention`` seconds. Tombstones remain until the
    database is deleted. A storage or decoding failure logs once and disables
    this instance. Callers receive misses and continue scraping.

    Attributes:
        path: SQLite database path. The cache opens it on first access.
        ttl: Seconds a field row remains fresh.
        retention: Seconds a field row remains on disk.
    """

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        ttl: float = TTL,
        retention: float = RETENTION,
    ) -> None:
        """
        Configure lazy storage and field-row lifetimes.

        ``None`` selects the platform user-cache directory for ``path``.

        Raises:
            ValueError: A lifetime is non-finite, ``ttl`` is not positive, or ``retention`` is lt ``ttl``.
        """
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
        """
        Read fresh fields and tombstones for the requested IDs.

        A ``None`` value is a gone-posting tombstone. Missing keys are stale,
        absent, or malformed rows. Storage and decoding failures disable the
        cache and return an empty mapping.
        """
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
                    try:
                        value = json.loads(fields, parse_constant=_reject_constant)
                    except _NonstandardConstant:
                        # Treat nonstandard numeric constants as a cache miss. A successful refetch replaces the row.
                        continue
                    if not isinstance(value, dict):
                        raise ValueError("posting fields are not a JSON object")
                    found[posting_id] = value
            return found
        except (json.JSONDecodeError, OSError, sqlite3.Error, TypeError, ValueError) as error:
            self._give_up(error)
            return {}

    def put(self, site: str, postings: dict[str, dict | None]) -> None:
        """
        Store field dictionaries and gone-posting tombstones.

        ``None`` records a confirmed 404 or 410. Storage or serialization
        failures log once and disable this cache instance.
        """
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
