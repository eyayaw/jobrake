# Changelog

## [0.5.0] — 2026-08-10

The LinkedIn scraper was rebuilt around the site's measured request budget, and
fetched descriptions now persist in an on-disk cache. A 25-job search with
descriptions dropped from ~100s and ~8MB to ~80s and ~0.9MB, and repeating a
~430-job sweep dropped from ~24 minutes to ~2.

### New

- Every job dict carries an `id`: LinkedIn's numeric posting id, Indeed's job key.
- `linkedin.fetch_descriptions(fetcher, ids)` fetches descriptions by posting id
  via the ~30KB guest fragment (the full job page is ~300KB). Per id: the text,
  `None` when the posting is gone, or absent when the fetch failed and a retry
  is safe.
- Descriptions are cached in a sqlite file in the user cache directory for a week;
  gone postings are remembered and never refetched. Each result is written as it
  arrives, so an interrupted sweep keeps what it paid for. `--no-cache` (or
  `cache=False`) bypasses it; a broken cache costs extra requests, never the scrape.
- `fetchkit.TokenBucket`: allows `capacity` calls immediately, then one per
  `refill_interval` seconds; cancellation-safe.

### Changed

- LinkedIn requests are paced by a shared token bucket (a short burst, then about
  one request per 3s) instead of flat sleeps; a 429 is retried once after the
  limit clears.
- Description fetches use the guest fragment instead of the full job page: same
  text, a tenth of the bandwidth.
- `scrape`'s `linkedin_fetch_description` is now `fetch_description`; every search
  accepts the same keywords.

### Fixed

- Pagination no longer stops silently at a mid-run rate limit (the stuck-at-50
  bug); long runs now finish slower instead of truncated.
- An empty first page now warns that the location likely failed to resolve;
  qualify place names ("Amsterdam, North Holland, Netherlands").
- `TokenBucket` and `DescriptionCache` validate their parameters instead of
  accepting values that would misbehave; a canceled wait refunds its token.

### Docs

- README reworked: CLI-first usage, the cache moved up top, and all site details
  in one place. 🍂

## [0.4.0] — 2026-08-08

`HttpxFetcher` provides JSON `post` itself; `HttpxPostFetcher` dropped (breaking).

## [0.3.0] — 2026-08-08

The `PostFetcher` protocol names what the indeed scraper requires; no dependency
on the private fetchkit package.

## [0.2.0] — 2026-08-07

The fetchkit transport subset vendored as `jobrake.fetchkit`.

[0.5.0]: https://github.com/eyayaw/jobrake/releases/tag/v0.5.0
[0.4.0]: https://github.com/eyayaw/jobrake/releases/tag/v0.4.0
[0.3.0]: https://github.com/eyayaw/jobrake/releases/tag/v0.3.0
[0.2.0]: https://github.com/eyayaw/jobrake/releases/tag/v0.2.0
