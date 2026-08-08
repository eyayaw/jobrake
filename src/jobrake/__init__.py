"""
Minimal async job-board scrapers on a vendored fetch layer (``jobrake.fetchkit``).

    from jobrake import scrape

    jobs = await scrape("linkedin", search_term="economist", location="United States")

Each job is a plain dict: title, company, url, location, description, date
(YYYY-MM-DD or ""), site. Inject any ``jobrake.fetchkit.Fetcher`` via ``fetcher=``
to swap transports. Indeed uses a custom fetcher with a ``post`` method, which
the default :class:`HttpxPostFetcher` provides.
"""

from jobrake.core import HttpxPostFetcher, scrape

__all__ = ["HttpxPostFetcher", "scrape"]
