"""Shared fixtures: every test runs against an isolated posting cache."""

import pytest

from jobrake.cache import PostingCache
from jobrake.sites.linkedin import client


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Point the shared cache at a per-test file so tests never touch the user's."""
    cache = PostingCache(tmp_path / "postings.sqlite3")
    monkeypatch.setattr(client, "CACHE", cache)
    return cache
