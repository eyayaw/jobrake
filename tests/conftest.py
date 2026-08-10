"""Shared fixtures: every test runs against an isolated description cache."""

import pytest

from jobrake import linkedin
from jobrake.cache import DescriptionCache


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Point the module cache at a per-test file so tests never touch the user's."""
    cache = DescriptionCache(tmp_path / "descriptions.sqlite3")
    monkeypatch.setattr(linkedin, "CACHE", cache)
    return cache
