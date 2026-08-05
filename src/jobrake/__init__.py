"""
Minimal async job-board scrapers on fetchkit transport.

    from jobrake import scrape

    jobs = await scrape("indeed", search_term="economist", location="United States")

Each job is a plain dict: title, company, url, location, description, date
(YYYY-MM-DD or ""), site. Inject any fetchkit fetcher via ``fetcher=`` to swap
transports (e.g. CffiFetcher for TLS impersonation); Indeed needs one with a
``post`` method, which the default :class:`HttpxPostFetcher` provides.
"""

from jobrake.core import HttpxPostFetcher, scrape

__all__ = ["HttpxPostFetcher", "scrape"]
