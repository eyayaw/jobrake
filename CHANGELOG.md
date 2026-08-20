# Changelog

## [0.10.0](https://github.com/eyayaw/jobrake/releases/tag/v0.10.0) (2026-08-18)

### Fixed

- `scrape` validates the site and required geographic arguments before creating
  its default fetcher. Caller-supplied fetchers remain caller-owned even when
  they define a falsy value.
- The posting cache preserves gone-posting tombstones during retention cleanup.
  Invalid stored posting fields and storage failures disable the cache and make
  subsequent lookups cache misses.
- Canceled token-bucket waits leave later requests on their expected schedule.
- `HttpxFetcher` rejects zero, negative, NaN, and infinite timeout values before
  opening its client.
- Indeed safely encodes GraphQL search, location, and cursor values and
  preserves an explicit radius of zero.
- Indeed deduplicates jobs across pages and terminates pagination when a cursor
  repeats.
- LinkedIn deduplicates cards by posting ID and advances pagination by the
  parsed card count.
- LinkedIn recognizes `JobPosting` data in JSON-LD graphs and list-valued
  `@type` fields. Unrelated JSON-LD blocks still allow the blockless-posting
  fallback.
- Punctuation-only employment labels resolve to `None`, and invalid
  epoch-millisecond values receive a consistent `ValueError`.

## [0.9.0](https://github.com/eyayaw/jobrake/releases/tag/v0.9.0) (2026-08-15)

Jobs now share a single cross-site data model: a field means the same thing
whichever site a row came from. `site`, `id`, and `url` address the posting;
`title`, `company`, `location`, and `date` are part of every search result;
the rest—`description`, salary, employment type, structured location, and
more—we extract from the posting, null when it was missing from what we
fetched.

### Added

- LinkedIn `--detail | -d` fetches each job's posting page and extracts additional attributes:
  description, salary, employment type, posted and expiry timestamps, location (geo) info, applicant count, apply type, etc.
- Country-level LinkedIn postings (e.g., "Spain", "EMEA"), whose pages don't carry
  the structured block, fill from the page markup plus one extra request for the en-US guest fragment.
- Indeed fills the same fields from the search response it already
  receives—salary, the employer's own apply URL, company page and logo,
  employment type, remote, coordinates, and expiry—at the same single
  request.
- `linkedin.fetch_postings(fetcher, urls)` fetches postings by their URLs, through the same cache.
- `employment_type` labels are unified across sites: LinkedIn's `FULL_TIME` and Indeed's `Full-time` both read back `full_time`.
- `--version` prints the installed version; `jobrake.__version__` carries it for the library.

### Changed

- **Breaking:** `--fetch-description` (`fetch_description`) is now `--detail` (same `-d`); the kwarg is `detail`. The flag fills more than `description`, unlike the old flag.
- **Breaking:** `site` is required when constructing a `Job`; `(site, id)` identifies a posting globally.
- The cache stores whole postings (`postings.sqlite3`, keyed by site and posting id).
  The old `descriptions.sqlite3` is abandoned in place, delete it at will.
- Field order, and with it the CSV header, reads identity, summary, detail:
  `site`, `id`, `url`, `title`, `company`, `location`, `date`, `description`, then the rest.
- `date` derives from the posting timestamp when the search result offers none.

### Removed

- **Breaking:** `linkedin.fetch_descriptions` and `parse_description`. The
  fragment they read costs one request, the same as the whole posting, and carries only the description.

## [0.8.0](https://github.com/eyayaw/jobrake/releases/tag/v0.8.0) (2026-08-13)

Each site scraper is a package now: `jobrake.linkedin` and `jobrake.indeed`
split into `client` and `search` modules (LinkedIn also `descriptions`), with
the public names unchanged.

### Added

- `site_searches()` maps every supported site to its `search`; `scrape` and
  the CLI's `--site` choices both draw from it, so a new site registers in
  one place.

### Changed

- LinkedIn's request pacing is public API: `linkedin.client.paced_fetch`
  (the former `_paced_fetch`).

## [0.7.0](https://github.com/eyayaw/jobrake/releases/tag/v0.7.0) (2026-08-11)

Results now land wherever your tools want them: `--output` writes JSON, JSONL,
or CSV, resolved from the file extension.

### Added

- `--output | -o PATH` writes results to a file instead of stdout. A bad extension fails before the scrape spends a single request; with `-o`, stdout stays silent and a summary line goes to stderr.
- JSONL output holds one job per line, so files from separate runs merge with a plain `cat runs/*.jsonl`.
- The writers are library API too: `jobrake.io.write_json`, `write_jsonl`, and `write_csv` save a job list exactly as the CLI does, with the CSV header derived from the job dict itself.

## [0.6.0](https://github.com/eyayaw/jobrake/releases/tag/v0.6.0) (2026-08-10)

Fetched descriptions now persist in an on-disk cache, so repeat searches only
pay for postings they have not seen: a ~430-job sweep that took ~24 minutes
reruns in ~2.

### Added

- Descriptions are cached in a SQLite file in the user cache directory for a
  week; gone postings are remembered and skipped on later cached runs. Each
  result is written as it arrives, so an interrupted sweep keeps what it paid
  for. `--no-cache` (or `cache=False`) bypasses it; a broken cache costs extra
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
- README: the cache promoted up top, the hand-rolled store recipe replaced by
  it, sections reordered around the reader; this changelog added.

## [0.5.0](https://github.com/eyayaw/jobrake/releases/tag/v0.5.0) (2026-08-10)

The LinkedIn scraper was rebuilt around the site's measured request budget, and
fetched descriptions now persist in an on-disk cache. A 25-job search with
descriptions dropped from ~100s and ~8MB to ~80s and ~0.9MB, and repeating a
~430-job sweep dropped from ~24 minutes to ~2.

### Added

- Every job dict carries an `id`: LinkedIn's numeric posting ID, Indeed's job key.
- `linkedin.fetch_descriptions(fetcher, ids)` fetches descriptions by posting ID
  via the ~30KB guest fragment (the full job page is ~300KB). Per ID: the text,
  `None` when the posting is gone, or absent when the fetch failed and a retry
  is safe.
- Descriptions are cached in a SQLite file in the user cache directory for a week;
  gone postings are remembered and skipped on later cached runs. Each result is
  written as it arrives, so an interrupted sweep keeps what it paid for. `--no-cache` (or
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
- README reworked: CLI-first usage, the cache moved up top, and all site details
  in one place. 🍂

### Fixed

- Pagination no longer stops silently at a mid-run rate limit (the stuck-at-50
  bug); long runs now finish slower instead of truncated.
- An empty first page now warns that the location likely failed to resolve;
  qualify place names ("Amsterdam, North Holland, Netherlands").
- `TokenBucket` and `DescriptionCache` validate their parameters instead of
  accepting values that would misbehave; a canceled wait refunds its token.

## [0.4.0](https://github.com/eyayaw/jobrake/releases/tag/v0.4.0) (2026-08-08)

### Changed

- **Breaking:** `HttpxFetcher` provides JSON `post` itself; `HttpxPostFetcher`
  dropped.

## [0.3.0](https://github.com/eyayaw/jobrake/releases/tag/v0.3.0) (2026-08-08)

### Added

- The `PostFetcher` protocol names what the Indeed scraper requires; no
  dependency on the private fetchkit package.

## [0.2.0](https://github.com/eyayaw/jobrake/releases/tag/v0.2.0) (2026-08-07)

### Added

- The fetchkit transport subset vendored as `jobrake.fetchkit`.
