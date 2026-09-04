"""SQLite cache for posting fields and LinkedIn place resolutions."""

import json
import logging
import math
import os
import sqlite3
import sys
import time
from collections.abc import Iterable, Mapping
from pathlib import Path

logger = logging.getLogger(__name__)

POSTINGS = "postings"
GEOIDS = "geoids"
TTL = 7 * 24 * 3600  # seconds
# Startup applies retention only to rows with posting fields, tombstones stay.
RETENTION = 30 * 24 * 3600

# Each table version identifies the field set and parsing of its rows.
# Bump the affected version when either changes. Reads select only that version,
# so a posting version change leaves the cached geoids intact.
# Fetching those again costs paced requests.
_VERSIONS = {
    POSTINGS: 0,
    GEOIDS: 0,
}
_TABLES = tuple(_VERSIONS)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS {table} (
    version INTEGER NOT NULL,
    scope TEXT NOT NULL,
    key TEXT NOT NULL,
    fields TEXT,
    stored_at REAL NOT NULL,
    PRIMARY KEY (version, scope, key)
)"""
_COLUMNS = ("version", "scope", "key", "fields", "stored_at")


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
    return base / "jobrake" / "jobrake.sqlite3"


def _table_name(table: str) -> str:
    if table not in _TABLES:
        raise ValueError(f"unknown cache table {table!r}")
    return table


class Cache:
    """
    Store postings and LinkedIn place resolutions in separate SQLite tables.

    Posting values expire after ``ttl`` seconds and are deleted after
    ``retention`` seconds. Posting tombstones and geoId resolutions do not
    expire. A storage or decoding failure logs once and disables this instance.
    Callers receive misses and continue scraping. A scope keeps provider keys
    separate within each table, and each table's stored format version keeps
    values apart from those an earlier field set or parser produced.

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
            ValueError: A lifetime is non-finite, ``ttl`` is not positive, or
                ``retention`` < ``ttl``.
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
                for table in _TABLES:
                    columns = tuple(
                        row[1] for row in self._conn.execute(f"PRAGMA table_info({table})")
                    )
                    if columns and columns != _COLUMNS:
                        # A table built by an older jobrake cannot take today's rows.
                        self._conn.execute(f"DROP TABLE {table}")
                    self._conn.execute(_SCHEMA.format(table=table))
                    # Rows of another format are already invisible to this one,
                    # so dropping them only reclaims the space they hold.
                    self._conn.execute(
                        f"DELETE FROM {table} WHERE version != ?", (_VERSIONS[table],)
                    )
                self._conn.execute(
                    f"DELETE FROM {POSTINGS} WHERE fields IS NOT NULL AND stored_at < ?",
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
        logger.warning("cache disabled (%s): %s", self.path, error)

    def get(self, table: str, scope: str, keys: Iterable[str]) -> dict[str, dict | None]:
        """
        Read values for the requested keys in one table and scope.

        Posting values honor ``ttl``, geoId values do not expire.
        A ``None`` posting value is a tombstone marking the posting as gone.
        Missing keys are stale, absent, or malformed rows.
        Storage and decoding failures disable the cache and return an empty dict.
        """
        table = _table_name(table)
        keys = list(dict.fromkeys(keys))
        conn = self._connect()
        if conn is None or not keys:
            return {}
        try:
            placeholders = ", ".join("?" for _ in keys)
            rows = conn.execute(
                f"SELECT key, fields, stored_at FROM {table}"
                f" WHERE version = ? AND scope = ? AND key IN ({placeholders})",
                [_VERSIONS[table], scope, *keys],
            )
            stale = time.time() - self.ttl if table == POSTINGS else None
            found = {}
            for key, stored, stored_at in rows:
                if stored is None:
                    if table == POSTINGS:
                        found[key] = None
                    continue
                # SQLite may return a nonnumeric value despite the REAL declaration.
                if not isinstance(stored_at, int | float) or not math.isfinite(stored_at):
                    raise ValueError(f"cache stored_at is not a finite number: {stored_at!r}")
                if stale is None or stored_at >= stale:
                    try:
                        decoded = json.loads(stored, parse_constant=_reject_constant)
                    except _NonstandardConstant:
                        # Treat nonstandard numeric constants as a cache miss. A successful refetch replaces the row.
                        continue
                    if not isinstance(decoded, dict):
                        raise ValueError("cached value is not a JSON object")
                    found[key] = decoded
            return found
        except (json.JSONDecodeError, OSError, sqlite3.Error, TypeError, ValueError) as error:
            self._give_up(error)
            return {}

    def put(self, table: str, scope: str, values: Mapping[str, dict | None]) -> None:
        """
        Store dicts in one table and scope.

        ``None`` records a posting confirmed gone with a 404 or 410.
        Storage or serialization failures log once and disable this cache instance.
        """
        table = _table_name(table)
        conn = self._connect()
        if conn is None or not values:
            return
        try:
            now = time.time()
            conn.executemany(
                f"INSERT OR REPLACE INTO {table} (version, scope, key, fields, stored_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    (
                        _VERSIONS[table],
                        scope,
                        key,
                        None if value is None else json.dumps(value, ensure_ascii=False),
                        now,
                    )
                    for key, value in values.items()
                ),
            )
            conn.commit()
        except (OSError, sqlite3.Error, TypeError, ValueError) as error:
            self._give_up(error)
