"""Fixtures that isolate each test's cache and fabric pool, and a fake third site."""

import fakesite
import pytest

from jobrake import cache, sites
from jobrake.sites.linkedin import client


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Point the shared cache at a per-test database."""
    # A developer's own cache settings must not reach the suite.
    for name in ("JOBRAKE_CACHE_PATH", "JOBRAKE_CACHE_TTL"):
        monkeypatch.delenv(name, raising=False)
    isolated = cache.Cache(tmp_path / "jobrake.sqlite3")
    monkeypatch.setattr(cache, "CACHE", isolated)
    yield isolated
    isolated.close()


@pytest.fixture(autouse=True)
def fresh_fabrics(monkeypatch):
    """Start every test with a new fabric pool, as a new process does."""
    monkeypatch.setattr(client, "POOL", client.Fabrics())


@pytest.fixture
def fake_site(monkeypatch):
    """Register the fake job board in tests/fakesite.py as a third site."""
    monkeypatch.setitem(sites.SITES, "fakesite", fakesite)
    monkeypatch.setattr(fakesite, "calls", [])
    return fakesite
