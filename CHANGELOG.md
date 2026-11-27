# Changelog

## [Unreleased](https://github.com/eyayaw/jobrake/compare/v0.37.0...HEAD)

### Added

- `adzuna`: search Adzuna's 19 country editions by keyword, location, and age, with `--details`
  for full descriptions and advertised salaries.
- `cornerstone`: search Cornerstone OnDemand employer career sites by keyword, country, and age,
  with descriptions included.
- `xing`: search XING's job market (Germany, Austria, and Switzerland) by keyword, location, age,
  and remote work, with `--details` and `postings` for descriptions.
- `reliefweb`: search ReliefWeb's humanitarian and development postings via its v2 API using an
  approved appname in `JOBRAKE_RELIEFWEB_APPNAME`.

### Changed

- **Breaking:** `country_code` on places is always an assigned ISO 3166-1 alpha-2 code (alpha-3
  codes are converted, `UK` becomes `GB`, and unassigned codes like `ZZ` are dropped).
- `--country` / `country` now accepts ISO 3166-1 alpha-3 codes (such as `deu`) and `uk` in
  addition to alpha-2 codes, validated before any request across all sites.
- Errors, warnings, and logs use human-readable site names (like `LinkedIn` and `AEA JOE`) instead
  of raw module keys, and Indeed's `--company-ids` help and errors refer to "employer key".
- The warning at Indeed's and LinkedIn's result cap now advises splitting the search by place or by
  posting age.

### Fixed

- AcademicTransfer now skips vacancies with non-integer string `external_id` values instead of
  accepting them.
- When no home directory can be resolved, the default cache is disabled with a warning instead of
  crashing.
- Extracted `description` text no longer leaks hidden inline-styled content (including inherited
  `visibility` and `font-size` rules, hidden descendants, and split overrides).
- Missing positional arguments on `postings` / lookup functions no longer append `"It takes no
  options"` to the `TypeError` message.

## [0.37.0](https://github.com/eyayaw/jobrake/releases/tag/v0.37.0) - 2026-11-22

### Changed

- **Breaking:** Non-200 responses (including 204, unfollowed redirects, and `FetchResult` objects
  with `status=None`) are no longer parsed as data; searches and lookups raise `Stopped` and
  posting fetches skip them.
- **Breaking:** `identify` now rejects Indeed URLs with credentials or non-443 ports (matching
  LinkedIn), and rejects LinkedIn and Indeed URLs with invalid DNS hostnames; `linkedin.postings`
  raises `ValueError` for invalid hostnames.
- Split per-site documentation into dedicated pages under `docs/sites/<site>.md`.
- Unparseable `date`, `posted_at`, and `expires_at` warnings now include the field name and
  posting URL; unparseable `date` values fall back to `posted_at`.

### Fixed

- Fixed broken-pipe handling (`jobrake -h | true`, `--version`, usage errors, and crashes) so
  stdout/stderr pipe closures no longer turn exit status into 120.
- Fixed cache lock recovery: if another process holds the SQLite file locked, caching pauses for
  60 seconds and resumes instead of staying disabled for the rest of the process.
- Fixed `.check()` on Indeed lookups and on site `postings` functions so they validate country
  editions and posting references without sending requests.
- Fixed StepStone coordinate parsing so postings on the equator or prime meridian (`lat=0` or
  `lon=0`, but not both `0, 0`) keep their coordinates.
- Fixed Indeed URL parsing when a job key contains `&`.
- Skipped search cards whose URL cannot be read back by the site's `postings` command (StepStone,
  SmartRecruiters, Workday, LinkedIn) and cards with JSON boolean IDs (StepStone, UN Careers,
  AcademicTransfer); AcademicTransfer now omits JSON boolean contract type or education level codes
  instead of reading them as code `1`.
- Invalid cached records whose field types no longer match `JobDict` are treated as cache misses.
- Hardened URL validation, `make_job`, and option checks against malformed URLs (e.g., invalid
  IPv6 brackets) and out-of-range integers.

## [0.36.0](https://github.com/eyayaw/jobrake/releases/tag/v0.36.0) - 2026-11-20

### Changed

- **Breaking:** On INOMICS with `--details`, a posting page that gives a city and region without a
  country code now replaces the search result's location (e.g., `Umeå, Västerbotten` instead of
  `Umeå, Sweden`); `inomics postings` now returns a location for these pages too.

### Fixed

- LinkedIn searches now raise `Stopped` on non-200 or redirected non-search responses (such as
  sign-in walls) instead of ending silently, and Indeed raises `Stopped` if a cursor repeats.
- LinkedIn skips search cards with malformed URLs instead of aborting the search; AEA JOE raises
  `Stopped` on malformed export links.
- Improved JSON-LD parsing on INOMICS and StepStone to handle `@graph`, top-level arrays, list
  `@type` values, and broken sibling `<script>` blocks.
- AcademicTransfer now raises `Stopped` when the jobs page Nuxt payload is malformed or missing
  its API token.
- `HttpxFetcher(headers=...)` now replaces default headers case-insensitively.
- CLI `--output` removes partially written files on write error or Ctrl-C; stdout write failures
  (e.g., full disk or incompatible `PYTHONIOENCODING`) log an error and exit 1 instead of
  printing a traceback; closed stderr pipes preserve the command's exit code.
- Fixed large cache lookups exceeding SQLite's parameter limit (which previously disabled the
  cache).
- Non-ISO `posted_at` and `expires_at` values are now omitted with a warning instead of kept raw.
- Hardened response parsing and integer option handling against deeply nested JSON and extreme
  integer values.
- CLI `--help` now uses `VALUE` instead of `ID` as the metavar for multi-value flags.

## [0.35.0](https://github.com/eyayaw/jobrake/releases/tag/v0.35.0) - 2026-11-19

### Added

- SmartRecruiters `--details` and `postings` now populate `apply_url`.

### Changed

- **Breaking:** LinkedIn searches with `--details` now take `date` from the posting page (matching
  Workday, StepStone, and INOMICS) instead of keeping the search card's date.
- `postings` consistently reads the first reference when duplicates are passed, and SmartRecruiters
  and Workday `postings` return the canonical posting URL.
- Unified progress reporting, help text, and logger hierarchy (`jobrake.sites.<site>`) across
  detail-fetching sites.

### Fixed

- LinkedIn `--details` now produces identical results whether a posting comes from cache or a
  fresh fetch when a page has a blank title.
- SmartRecruiters no longer logs a "misspelled board?" hint when filters return zero matches (only
  when an unfiltered search is empty).
- Unparseable `date` values now become `None` (and unparseable AEA `expires_at` values are
  omitted) with a warning instead of slicing the first 10 characters.

## [0.34.0](https://github.com/eyayaw/jobrake/releases/tag/v0.34.0) - 2026-11-18

### Changed

- `uncareers search --max-age-hours` now accepts any positive number of hours (rounded up to whole
  days) instead of only 24, 168, or 720.

## [0.33.0](https://github.com/eyayaw/jobrake/releases/tag/v0.33.0) - 2026-11-17

### Added

- `academictransfer`: search Dutch academic and research vacancies on AcademicTransfer with
  `--query` and `--vacancy-type`, descriptions included.

## [0.32.0](https://github.com/eyayaw/jobrake/releases/tag/v0.32.0) - 2026-11-17

### Added

- `keywords` field on `JobDict` (list of strings), populated on Personio and AEA JOE.
- `aea`: search active listings on AEA JOE (Job Openings for Economists) with `--query`,
  `--section`, `--jel`, and `--max-age-hours`.
- `inomics`: search economist jobs on INOMICS (`--query`, `--country`, `--category`, `--jel`,
  `--details`) and fetch known postings by URL with `inomics postings`.

### Changed

- **Breaking:** Personio now stores keywords in the top-level `keywords` list instead of a
  comma-separated string in `site_data["keywords"]`.

## [0.31.0](https://github.com/eyayaw/jobrake/releases/tag/v0.31.0) - 2026-11-17

### Added

- `jobrake uncareers filters <option>` and `jobrake.sites.uncareers.filters()` to list valid
  values for UN Careers filters (duty stations, levels, departments, etc.).

## [0.30.0](https://github.com/eyayaw/jobrake/releases/tag/v0.30.0) - 2026-11-16

### Added

- `uncareers`: search United Nations Secretariat openings with `--query`, `--category`,
  `--duty-station`, `--level`, `--department`, `--job-network`, `--job-family`,
  `--recruitment-type`, and `--max-age-hours`.

## [0.29.0](https://github.com/eyayaw/jobrake/releases/tag/v0.29.0) - 2026-11-16

### Added

- `stepstone`: search StepStone Germany via its mobile API (`--location`, `--radius`, `--remote`,
  `--details`) and fetch postings by URL via `stepstone postings`.
- `personio`: read employer career feeds from Personio's public XML API, backfilling blank
  descriptions from alternate language feeds.

### Fixed

- `identify` and `postings` reject non-ASCII digits (such as fullwidth digits) in SmartRecruiters
  and Workday IDs.

## [0.28.0](https://github.com/eyayaw/jobrake/releases/tag/v0.28.0) - 2026-11-15

### Added

- Support for shared-host Workday URLs (`https://wd<n>.myworkdaysite.com/recruiting/<tenant>/<site>`).
- LinkedIn postings no longer accepting applications set `site_data["closed"] = True`.
- `Stopped.failed` lists unread posting URLs after a partial `--details` failure, and the CLI logs
  the exact `postings` retry command.
- `jobrake.check(site, **options)` for offline option validation without an event loop.
- `jobrake.identify(link)` to map posting URLs (LinkedIn, Indeed, Workday, SmartRecruiters) to
  `(site, id)`.

### Changed

- Enabled local SQLite caching for Workday and SmartRecruiters detail fetches (matching LinkedIn).
- Workday detail fetches without a primary location no longer prepend the search card's location.
- LinkedIn postings without JSON-LD now cost one request instead of two.

### Fixed

- When an API returns an HTML maintenance page instead of JSON (such as Workday), jobrake reports
  possible maintenance instead of blaming an API change.
- LinkedIn detail pages are now requested in English (`?_l=en_US`) and replace search-card places
  whole, preventing mixed-language city/region pairs and mismatched multi-city locations.

## [0.27.0](https://github.com/eyayaw/jobrake/releases/tag/v0.27.0) - 2026-11-14

### Changed

- **Breaking:** LinkedIn posting references must use HTTPS on the default port without embedded
  credentials; `http://`, custom ports, or `user:pass@` raise `ValueError`.
- Expanded `docs/reference.md` with every record field's type and meaning, and corrected
  optionality notes for Ashby and Lever fields.

### Fixed

- Lever's `onsite` label now maps to `workplace_type="on_site"`.
- Fixed Indeed's CSS-scrubbing regex so prose containing braces (like `{"id": 1}`) is preserved
  without backtracking stalls.
- Replaced lone UTF-16 surrogates in scraped text with U+FFFD so they cannot crash CLI output or
  disable caching.
- LinkedIn skips search cards linking off `linkedin.com` so `--details` never fetches external
  hosts.
- Ctrl-C exits cleanly with a single warning line instead of a traceback; post-parse CLI errors
  now reference the subcommand's `-h` help.
- Indeed `attributes` surfaces GraphQL error messages properly, and cache-disable warnings include
  recovery instructions.

## [0.26.0](https://github.com/eyayaw/jobrake/releases/tag/v0.26.0) - 2026-11-13

Consolidated response parsing, pagination, `fetchkit`, and single-file site modules.

### Changed

- **Breaking:** Removed `FetchResult.ok` (check `error is None` instead).
- **Breaking:** Flattened `jobrake.fetchkit` into a single module (`jobrake.fetchkit.httpx` and
  `jobrake.fetchkit.types` removed; import `Fetcher`, `FetchResult`, and `HttpxFetcher` from
  `jobrake.fetchkit`).
- **Breaking:** Flattened Ashby, EconJobMarket, Greenhouse, Lever, SmartRecruiters, Workable, and
  Workday into single modules (`jobrake.sites.<site>.search` is now the function itself).
- **Breaking:** When a CLI search or `postings` run fails with zero results collected, jobrake now
  writes nothing instead of an empty `[]` / CSV header (still logging the error and exiting 1).
- Custom `Fetcher` implementations only need `fetch()` (jobrake never closes caller-supplied
  fetchers).
- Standardized failed-request error messages, result-count logging, page sizes on
  SmartRecruiters/Workday, and optional `partial` on `Stopped`.
- Moved field and request reference material from `docs/guide.md` into `docs/reference.md`.

## [0.25.0](https://github.com/eyayaw/jobrake/releases/tag/v0.25.0) - 2026-11-11

### Added

- Page-by-page progress reporting for LinkedIn, Indeed, Workday, and SmartRecruiters searches.

### Changed

- Replaced the terminal progress bar with concise status lines (e.g., `workday search 20/60`,
  `linkedin details 5/10`).
- Increased LinkedIn HTTP 429 retries from 3 to 5.

## [0.24.0](https://github.com/eyayaw/jobrake/releases/tag/v0.24.0) - 2026-11-10

### Changed

- **Breaking:** `Fetcher.fetch()` must accept `follow_redirects: bool = True` and return the first
  response (with `Location`) when `False`. LinkedIn requests pass `follow_redirects=False`.
- Concurrency for LinkedIn posting pages increased to up to 6 in flight across data centers,
  sending short bursts within each data center's window.
- `linkedin postings` reads `www.linkedin.com` title-slug URLs directly and follows the canonical
  link, saving a lookup request for US postings; mismatched canonical links are skipped with a
  warning.

### Fixed

- Preserved dates, coordinates, and requirements when a renamed LinkedIn posting redirects via its
  canonical link.
- Malformed links in a LinkedIn guest fragment now skip just that posting instead of aborting the
  whole `postings` batch.
- Postings redirecting to a search page fall back cleanly to the guest fragment instead of scraping
  the search page.
- LinkedIn redirect hops are now followed manually (HTTPS `linkedin.com` only) so every hop is
  paced and pinned to a data center.

## [0.23.0](https://github.com/eyayaw/jobrake/releases/tag/v0.23.0) - 2026-10-30

### Added

- `workday postings` and `smartrecruiters postings` (plus `--details` on SmartRecruiters) for
  fetching full job descriptions on demand.
- `linkedin postings` now accepts job alert email URLs (`/comm/jobs/view/ID`) and search URLs with
  `currentJobId=`.

### Changed

- **Breaking:** Workday requisition IDs containing underscores stay intact (e.g., `guidewire:JR_15332`
  instead of `guidewire:15332`), and paths ending in non-ID title words like `/Data_Scientist` are
  skipped.
- **Breaking:** Indeed `--country` / `country` now uses ISO 3166-1 alpha-2 codes (`de`, `gb`, `us`)
  instead of country names.
- `html_text` now strips hidden inline-styled elements (`display:none`, etc.) and invisible
  zero-width / bidi characters from descriptions.

### Fixed

- Workday HTTP 403 responses with `errorCode: "S22"` are now treated as withdrawn/gone postings
  instead of raising `Stopped`.
- Removed 10 countries rejected by Indeed's API (Bangladesh, Bulgaria, Croatia, Cyprus, Estonia,
  Latvia, Lithuania, Malta, Slovakia, Slovenia) so they fail locally with `ValueError`.

## [0.22.0](https://github.com/eyayaw/jobrake/releases/tag/v0.22.0) - 2026-10-29

### Added

- `department`, `team`, and `site_data` fields on `JobDict`.
- `jobrake.Place`, `jobrake.models.make_places()`, and `jobrake.models.workplace_type()`.

### Changed

- **Breaking:** Replaced `location`, `city`, `region`, `country_code`, `latitude`, and `longitude`
  with `locations` (a list of `Place` dicts). Cached LinkedIn postings refetch once under the new
  schema.
- **Breaking:** Replaced `is_remote` with `workplace_type` (`"remote"`, `"hybrid"`, or
  `"on_site"`), included only when stated by the site.
- CSV output joins `locations` with `; ` and serializes `site_data` as JSON.

### Removed

- **Breaking:** `jobrake.utils.join_places()`.

## [0.21.0](https://github.com/eyayaw/jobrake/releases/tag/v0.21.0) - 2026-10-28

### Added

- Seven new sites: `greenhouse`, `ashby`, `lever`, `workable`, `smartrecruiters`, `workday`, and
  `econjobmarket`.

### Changed

- Blank Indeed `country` reports a blank-option `ValueError`; SmartRecruiters and Workday raise
  `Stopped` on premature empty pages; `employment_type()` handles camelCase labels (`FullTime` ->
  `full_time`); `make_job` uppercases `country_code`.

### Fixed

- Oversized integers in Indeed responses raise `Stopped` instead of `ValueError`, and in LinkedIn
  JSON-LD blocks skip the block instead of crashing.

## [0.20.0](https://github.com/eyayaw/jobrake/releases/tag/v0.20.0) - 2026-10-28

Major architecture overhaul around a shared `JobDict` schema, per-site option validation, and
`Stopped` partial-result exceptions.

### Added

- `jobrake.sites.SITES` registry; top-level `Stopped` and `JobDict` exports; Indeed 1,000-result
  cap warning; default `query=""` on LinkedIn and Indeed.

### Changed

- **Breaking:** Requires Python 3.15.
- **Breaking:** `scrape()` and all site functions validate options strictly before making requests;
  unsupported options raise `TypeError` instead of being ignored.
- **Breaking:** Failed requests raise `Stopped` (carrying `.partial`) instead of returning partial
  lists or `None`; CLI writes partial results and exits 1.
- **Breaking:** Standardized all lookup outputs to `{"id", "name"}` dicts and made `country`
  keyword-only on Indeed lookups.
- **Breaking:** Unified employer filtering under `company_ids` (replacing Indeed's `employer_key`);
  Indeed `radius` no longer accepts `None`; LinkedIn `geoid` accepts numeric ID strings only
  (dropping `geoid=True` and cached geoId lookups); `max_age_hours` defaults to `None` (no age
  limit) instead of 168.
- **Breaking:** Replaced `fetch_postings` / `fetch_details` and `jobrake details linkedin` with
  `linkedin.postings(fetcher, references)` and `jobrake linkedin postings REF...`.
- **Breaking:** CLI subcommands are now site-first (`jobrake <site> search` replaces `jobrake <site>`,
  and `jobrake <site> <lookup>` replaces `jobrake <lookup> <site>`), and flags match Python option
  names (`--max-age` -> `--max-age-hours`, `--company` -> `--company-ids`, `--attribute` ->
  `--attributes`).
- **Breaking:** Unified `Fetcher.fetch(url, *, headers=None, json=None)`, renamed `status_code` to
  `status`, made `error` a string, and converted `JobDict` to a `TypedDict`.
- **Breaking:** Rebuilt the SQLite cache around whole `JobDict` rows keyed by `(site, id)` via
  `jobrake.cache.CACHE` (previous tables in `jobrake.sqlite3` are unused and can be deleted).

### Removed

- **Breaking:** Removed `jobrake.defaults`, `site_searchers()`, `models.Job`, `check_*` helpers,
  `io.to_*` writers (use `RENDERERS`), old per-lookup submodules, legacy `fetchkit` classes
  (`BaseFetcher`, `PostFetcher`, `ErrorCategory`, `FetchError`, `TokenBucket`, `build_result`),
  `HttpxFetcher`'s `cookies`/`follow_redirects`/`jitter` options, unused per-site cross-options,
  `JOBRAKE_CACHE_RETENTION`, and `--no-cache` / `cache=False`.

### Fixed

- Normalized LinkedIn posting URLs (stripping tracking queries and trailing slashes), validated
  ASCII-only IDs before requesting, avoided caching incomplete fallback pages, accepted uppercase
  `--output` extensions, validated Indeed `results` list types, and dropped non-integer
  `experience_months`.

## [0.19.0](https://github.com/eyayaw/jobrake/releases/tag/v0.19.0) - 2026-10-26

### Added

- `HttpxFetcher(transport=...)` for custom transports such as `httpx.MockTransport`.
- `Cache.close()` and `models.JobDict`.

### Changed

- **Breaking:** Requires Python 3.14; keyword-only options on `HttpxFetcher` (after `timeout`) and
  `indeed.build_query`; `ErrorCategory` is now a `StrEnum`.

## [0.18.0](https://github.com/eyayaw/jobrake/releases/tag/v0.18.0) - 2026-10-18

### Changed

- **Breaking:** Removed `linkedin.LIMITER` and `linkedin.RETRY_DELAY`, and switched LinkedIn
  requests to send only the data-center pinning cookie.
- Sped up LinkedIn scraping ~3× by distributing requests across LinkedIn's three data centers and
  retrying 429s up to three times.

### Removed

- Stopped parsing `Retry-After` on LinkedIn 429 responses (which the guest API does not send).

## [0.17.0](https://github.com/eyayaw/jobrake/releases/tag/v0.17.0) - 2026-10-04

### Added

- Indeed filters and lookups: `--attribute` / `attributes`, `--language`, `--remote`, company
  filtering (`--company` / `employer_key`) and lookup (`jobrake companies indeed`), and `language`
  in returned records/CSV.
- LinkedIn filters and lookups: `--easy-apply`, `--early-applicant`, `--radius` (km), and company
  filtering (`--company` / `company_ids`) and lookup (`jobrake companies linkedin`).
- Cache configuration via `JOBRAKE_CACHE_PATH`, `JOBRAKE_CACHE_TTL`, and `JOBRAKE_CACHE_RETENTION`.

### Changed

- **Breaking:** `--output` refuses to overwrite existing files and checks directory permissions
  before searching.
- **Breaking:** LinkedIn `radius` now uses kilometers (matching Indeed) and converts to whole miles
  internally.
- Cached canonical URLs and gone-posting markers (expiring after `JOBRAKE_CACHE_RETENTION`);
  `--geoid` prefers exact name matches; `--no-cache` refreshes cached entries instead of bypassing
  writes.

### Fixed

- Stopped warning on US `www.linkedin.com` canonical URLs and added upfront `TypeError` validation
  for non-string search arguments.

## [0.16.0](https://github.com/eyayaw/jobrake/releases/tag/v0.16.0) - 2026-09-05

### Added

- `jobrake details linkedin <ID|URL>...` and `linkedin.fetch_details()` for fetching known
  postings directly.
- Shipped `py.typed` marker for downstream type checkers.

### Changed

- Added CLI descriptions, separated `LICENSE` and `THIRD_PARTY_NOTICES` for GitHub license
  detection, added versioned cache tables, and extracted `title`/`company`/`location` directly from
  LinkedIn posting pages.

### Fixed

- HTML-decoded LinkedIn JSON-LD strings (fixing `&amp;` in `company_logo` URLs), clarified
  transport and epoch-timestamp warnings, and rejected non-integer numeric search options with
  `TypeError`.

## [0.15.0](https://github.com/eyayaw/jobrake/releases/tag/v0.15.0) - 2026-09-02

### Added

- LinkedIn `--geoid` support and `jobrake places linkedin|indeed <name>` location lookups (with
  `linkedin.places`, `indeed.places`, and `linkedin.resolve_geoid`).

### Changed

- **Breaking:** Replaced `--site` with `jobrake indeed` and `jobrake linkedin` subcommands, updated
  search defaults (10 results, 7-day age limit, 40 km Indeed radius), and renamed search options
  (`search_term` -> `query`, `results_wanted` -> `results`, `hours_old` -> `max_age_hours`,
  `distance` -> `radius`, `detail` -> `details`; CLI `--search-term` -> `--query`,
  `--results-wanted` -> `--results`, `--hours-old` -> `--max-age`, `--detail` -> `--details`).

## [0.14.0](https://github.com/eyayaw/jobrake/releases/tag/v0.14.0) - 2026-08-25

### Added

- Progress logging and terminal progress bar for LinkedIn detail fetches.

### Changed

- Empty searches leave `--output` untouched with a warning instead of writing an empty file.

### Fixed

- Validated `--output` paths upfront and reported write errors cleanly without tracebacks.

## [0.13.0](https://github.com/eyayaw/jobrake/releases/tag/v0.13.0) - 2026-08-24

### Added

- Warnings for search failures, LinkedIn's 1,000-card cap, and failed detail pages.

### Changed

- LinkedIn stops detail fetching cleanly on persistent 429s, honors numeric `Retry-After` up to 60s,
  and validates `results_wanted`, `distance`, and `location` before requesting.

### Fixed

- Fixed Indeed cursor page-size consistency (keeping 100 across pages), continued pagination on
  all-malformed pages, and stripped non-finite/overflowing numeric values across LinkedIn, Indeed,
  and cache reads.

## [0.12.0](https://github.com/eyayaw/jobrake/releases/tag/v0.12.0) - 2026-08-21

### Added

- `--format` (`json`, `jsonl`, `csv`) and string renderers `jobrake.io.to_jsonl` / `to_csv`.

### Changed

- Compact JSON output regardless of result count.

### Removed

- **Breaking:** Removed `jobrake.io.write_json`, `write_jsonl`, and `write_csv`.

### Fixed

- Handled broken stdout pipes (`jobrake ... | head`) quietly with exit code 1 instead of a
  traceback.

## [0.11.0](https://github.com/eyayaw/jobrake/releases/tag/v0.11.0) - 2026-08-20

### Changed

- **Breaking:** Records always contain the seven identity and summary keys (`None` when absent) and
  include detail keys only when populated.

### Fixed

- Isolated malformed Indeed items, advanced LinkedIn pagination by raw card count, supported more
  LinkedIn schema.org shapes, handled corrupt cache timestamps gracefully, rejected non-positive
  age filters, improved `HttpxFetcher` error classification, and deduplicated LinkedIn detail
  fetches per posting ID.

## [0.10.0](https://github.com/eyayaw/jobrake/releases/tag/v0.10.0) - 2026-08-18

### Fixed

- Validated arguments before opening default fetchers, preserved caller-owned fetchers, hardened
  cache retention/failure handling and `TokenBucket` cancellation, rejected invalid `HttpxFetcher`
  timeouts, fixed Indeed GraphQL escaping and `radius=0`, deduplicated Indeed/LinkedIn pages, and
  improved JSON-LD `@graph` / list `@type` handling.

## [0.9.0](https://github.com/eyayaw/jobrake/releases/tag/v0.9.0) - 2026-08-16

Unified job data model across LinkedIn and Indeed.

### Added

- LinkedIn `--detail` fetches full posting pages (description, salary, employment type, timestamps,
  locations, applicants, apply type) with guest-fragment fallback for country-level postings.
- Indeed extracts the same extended fields from search responses; added `linkedin.fetch_postings()`,
  normalized `employment_type`, `--version`, and `jobrake.__version__`.

### Changed

- **Breaking:** Renamed `--fetch-description` / `fetch_description` to `--detail` / `detail`,
  required `site` on `Job`, switched caching to whole postings (`postings.sqlite3`), standardized
  field/CSV order, and derived `date` from `posted_at` when missing.

### Removed

- **Breaking:** Removed `linkedin.fetch_descriptions` and `parse_description`.

## [0.8.0](https://github.com/eyayaw/jobrake/releases/tag/v0.8.0) - 2026-08-13

### Added

- `site_searches()` registry powering both `scrape()` and CLI dispatch.

### Changed

- Split `jobrake.linkedin` and `jobrake.indeed` into subpackages (`client`, `search`, etc.) and
  exposed `linkedin.client.paced_fetch`.

## [0.7.0](https://github.com/eyayaw/jobrake/releases/tag/v0.7.0) - 2026-08-11

### Added

- `--output PATH` for JSON, JSONL, and CSV export chosen by file extension, along with
  `jobrake.io.write_json`, `write_jsonl`, and `write_csv`.

## [0.6.0](https://github.com/eyayaw/jobrake/releases/tag/v0.6.0) - 2026-08-10

### Added

- On-disk SQLite cache for fetched LinkedIn descriptions (7-day TTL, gone-posting tracking,
  `--no-cache` / `cache=False` bypass).
- Sent CLI logs and warnings to stderr while muting noisy dependency loggers so stdout stays pure
  JSON.

### Changed

- Renamed `linkedin_fetch_description` to `fetch_description` and aligned search keyword arguments
  across LinkedIn and Indeed.
- Added this changelog and reorganized the README.

## [0.5.0](https://github.com/eyayaw/jobrake/releases/tag/v0.5.0) - 2026-08-10

### Added

- `id` field on job dicts (LinkedIn posting ID / Indeed job key), `linkedin.fetch_descriptions()`
  via the guest fragment, and `fetchkit.TokenBucket`.

### Changed

- Switched LinkedIn pacing from fixed sleeps to a token bucket with a single retry on HTTP 429,
  and read descriptions from the lightweight guest fragment.

### Fixed

- Handled mid-run LinkedIn rate limits during pagination, warned on empty first pages (likely
  ambiguous location), and validated `TokenBucket` parameters and wait cancellation.

## [0.4.0](https://github.com/eyayaw/jobrake/releases/tag/v0.4.0) - 2026-08-08

### Changed

- **Breaking:** Merged `HttpxPostFetcher` into `HttpxFetcher`.

## [0.3.0](https://github.com/eyayaw/jobrake/releases/tag/v0.3.0) - 2026-08-08

### Added

- Defined the `PostFetcher` protocol locally, dropping the private `fetchkit` dependency.

## [0.2.0](https://github.com/eyayaw/jobrake/releases/tag/v0.2.0) - 2026-08-07

### Added

- Vendored the `jobrake.fetchkit` transport layer.
