"""Fixtures that give every test an isolated cache and fabric pool."""

import pytest

from jobrake.cache import Cache
from jobrake.sites.linkedin import client


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Point the shared cache at a per-test database."""
    # A developer's own cache settings must not reach the suite.
    for name in ("JOBRAKE_CACHE_PATH", "JOBRAKE_CACHE_TTL", "JOBRAKE_CACHE_RETENTION"):
        monkeypatch.delenv(name, raising=False)
    cache = Cache(tmp_path / "jobrake.sqlite3")
    monkeypatch.setattr(client, "CACHE", cache)
    yield cache
    cache.close()


@pytest.fixture(autouse=True)
def fresh_fabrics(monkeypatch):
    """Start every test with a new fabric pool, as a new process does."""
    monkeypatch.setattr(client, "POOL", client.Fabrics())
