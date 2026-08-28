"""Fixtures that give every test an isolated cache."""

import pytest

from jobrake.cache import Cache
from jobrake.sites.linkedin import client


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Point the shared cache at a per-test database."""
    cache = Cache(tmp_path / "jobrake.sqlite3")
    monkeypatch.setattr(client, "CACHE", cache)
    return cache
