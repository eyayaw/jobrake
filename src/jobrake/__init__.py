"""
Minimal async job-board scrapers on a small built-in fetch layer (``jobrake.fetchkit``).

    from jobrake import scrape

    jobs = await scrape("linkedin", search_term="economist", location="United States")

Each job is a plain dict: id (site-local posting identifier), title, company,
url, location, description, date (YYYY-MM-DD or ""), site. Inject any ``jobrake.fetchkit.Fetcher`` via ``fetcher=``
to swap transports (indeed needs the ``PostFetcher`` variant).
"""

from jobrake.sites import scrape
from jobrake.fetchkit import HttpxFetcher

__all__ = ["HttpxFetcher", "scrape"]
