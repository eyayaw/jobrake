"""
Minimal async job-board scrapers on a small built-in fetch layer (``jobrake.fetchkit``).

    from jobrake import scrape

    jobs = await scrape("linkedin", search_term="economist", location="United States")

Each job is a dict with the fields of ``jobrake.models.Job``. ``site``,
``id``, and ``url`` address the posting; ``title``, ``company``,
``location``, and ``date`` accompany every search result, ``""`` where a
site shows nothing; the rest—``description`` and the detail fields—is
extracted from the posting, ``None`` where it was not in what we fetched.

Pass any ``jobrake.fetchkit.Fetcher`` as ``fetcher=`` to swap transports
(indeed needs the ``PostFetcher`` variant).
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _get_version

from jobrake.fetchkit import HttpxFetcher
from jobrake.sites import scrape

try:
    __version__ = _get_version("jobrake")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["__version__", "HttpxFetcher", "scrape"]
