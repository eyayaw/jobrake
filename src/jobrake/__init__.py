"""Minimal async LinkedIn and Indeed scrapers into a unified job posting data."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _get_version

from jobrake.fetchkit import HttpxFetcher
from jobrake.sites import scrape

try:
    __version__ = _get_version("jobrake")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["__version__", "HttpxFetcher", "scrape"]
