# Changelog

## [0.7.0] — 2026-08-11

Results now land wherever your tools want them: `--output` writes json, jsonl,
or csv, resolved from the file extension.

### New

- `--output | -o PATH` writes results to a file instead of stdout. A bad extension fails before the scrape spends a single request; with `-o`, stdout stays silent and a summary line goes to stderr.
- jsonl output holds one job per line, so files from separate runs merge with a plain `cat runs/*.jsonl`.
- The writers are library API too: `jobrake.io.write_json`, `write_jsonl`, and `write_csv` save a job list exactly as the CLI does, with the csv header derived from the job dict itself.

## [0.6.0] — 2026-08-10

Fetched descriptions now persist in an on-disk cache, so repeat searches only
pay for postings they have not seen: a ~430-job sweep that took ~24 minutes
reruns in ~2.

### New

- Descriptions are cached in a sqlite file in the user cache directory for a
  week; gone postings are remembered and never refetched. Each result is
  written as it arrives, so an interrupted sweep keeps what it paid for.
  `--no-cache` (or `cache=False`) bypasses it; a broken cache costs extra
  requests, never the scrape.
- The CLI logs progress and warnings to stderr and keeps chatty dependency
  loggers quiet; stdout stays pure JSON for piping.

### Changed

- `scrape`'s `linkedin_fetch_description` is now `fetch_description`; every
  search accepts the same keywords.
- `linkedin.search` accepts `country` and ignores it (LinkedIn resolves places
  from `location` alone); one set of arguments works for every site.
- `indeed.search` likewise accepts `fetch_description` and `cache` as no-ops:
  descriptions always arrive in the search response, so there is nothing to
  fetch or cache.

### Docs

- README: the cache promoted up top, the hand-rolled store recipe replaced by
  it, sections reordered around the reader; this changelog added.

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

[0.7.0]: https://github.com/eyayaw/jobrake/releases/tag/v0.7.0
[0.6.0]: https://github.com/eyayaw/jobrake/releases/tag/v0.6.0
[0.5.0]: https://github.com/eyayaw/jobrake/releases/tag/v0.5.0
[0.4.0]: https://github.com/eyayaw/jobrake/releases/tag/v0.4.0
[0.3.0]: https://github.com/eyayaw/jobrake/releases/tag/v0.3.0
[0.2.0]: https://github.com/eyayaw/jobrake/releases/tag/v0.2.0
