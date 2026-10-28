"""Read job boards' postings and return each one as the same record."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _get_version

from jobrake.fetchkit import HttpxFetcher
from jobrake.models import JobDict, Place, Stopped
from jobrake.sites import scrape

try:
    __version__ = _get_version("jobrake")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["HttpxFetcher", "JobDict", "Place", "Stopped", "__version__", "scrape"]
