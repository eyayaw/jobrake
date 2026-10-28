# Changelog

## Unreleased

## [0.21.0](https://github.com/eyayaw/jobrake/releases/tag/v0.21.0) - 2026-10-28

This release adds seven sites: employers' boards on six applicant tracking systems, and EconJobMarket's ad feed. When a site lists a posting's places one by one, its record names each of them in `location`.

### Added

- `greenhouse`, `ashby`, `lever`, and `workable` sites: `jobrake <site> search -b <token>` and `scrape(site, board=...)` return every posting on one employer's board.
- `smartrecruiters` site: `jobrake smartrecruiters search -b <token>` pages through one employer's board, with `query`, `results`, `max_age_hours`, and `remote` applied by SmartRecruiters.
- `workday` site: `jobrake workday search -b <career site URL>` searches one employer's Workday career site, with `query`, `results`, and `details`.
- `econjobmarket` site: `jobrake econjobmarket search` and `scrape("econjobmarket")` return every open ad from EconJobMarket's public feed.

### Changed

- A blank Indeed `country` raises `ValueError` saying the option is blank, instead of calling it an unknown country.
- `Stopped` also ends a SmartRecruiters or Workday search whose page comes back empty before the total the site reported.
- `employment_type()` slugs camelCase labels, so `FullTime` becomes `full_time`.
- `make_job` uppercases `country_code`.

### Fixed

- An Indeed response holding an integer longer than Python reads raises `Stopped` instead of `ValueError`. A LinkedIn posting page holding one in a JSON-LD block skips that block instead of raising.

## [0.20.0](https://github.com/eyayaw/jobrake/releases/tag/v0.20.0) - 2026-10-28

This release rebuilds jobrake around one contract. Every site returns the same `JobDict` record, and each site declares only the options its server applies. A failed request raises `Stopped`, so a caller can tell a cut-short result from a complete one.

### Added

- `jobrake.sites.SITES` maps each site name to its package, and `scrape()` and the CLI read it.
- `jobrake` exports `Stopped` and `JobDict`.
- An Indeed search warns when Indeed's 1,000-result cap cuts it short, as a LinkedIn search does at offset 1,000.
- `query` defaults to an empty string on both sites, so a search by company ID or place needs no `-q ""`.

### Changed

- **Breaking:** jobrake requires Python 3.15.
- **Breaking:** `scrape(site, *, fetcher=None, **options)` takes the options of the site's own `search()`. Every function a site exports checks its arguments before any request. An option the site does not apply raises `TypeError`, where it used to be ignored.
- **Breaking:** A failed request raises `Stopped`, whose `partial` holds the jobs collected before it. A search used to return them as a normal result, and a lookup returned `None`. A `details=True` search also raises it when a posting's details could not be fetched. The CLI writes a stopped search's jobs and exits 1.
- **Breaking:** Every lookup returns `{"id", "name"}` dicts, where `id` is the value a search takes. `id` replaces `geoId`, `companyId`, `employerKey`, and `key`, and `name` replaces `displayName`, `label`, and an Indeed company's `suggestion`. An Indeed place carries its `suggestion` in both keys and drops `locationType`. Indeed's `places()`, `companies()`, and `attributes()` take `country` by keyword.
- **Breaking:** `company_ids` filters employers on Indeed as on LinkedIn, replacing `employer_key`, and an Indeed search takes one ID.
- **Breaking:** Indeed's `radius` takes an integer, 40 by default, and `radius=None` raises `TypeError`. It used to mean 40.
- **Breaking:** `geoid` takes a LinkedIn place ID of digits 0-9 only, so `geoid=True`, `--geoid` without an ID, and the cached place resolutions are gone. Find an ID with `jobrake linkedin places NAME`.
- **Breaking:** `linkedin.postings(fetcher, references)` takes a list of posting IDs or URLs, returns their records keyed by the references given, and replaces `fetch_postings()` and `fetch_details()`. A posting LinkedIn reports gone maps to `None`, and a failed reference has no key. `postings()` raises no `Stopped`.
- **Breaking:** `jobrake linkedin postings REF...` replaces `jobrake details linkedin`. It exits 1 when a reference failed, and a run whose postings are all gone writes `[]` and exits 0.
- **Breaking:** Every CLI command names its site first: `jobrake linkedin search` replaces `jobrake linkedin`, and `jobrake indeed places NAME` replaces `jobrake places indeed NAME`. Each site's commands are the functions it exports, and `jobrake <site> -h` lists them.
- **Breaking:** CLI flags take the names of their options: `--max-age-hours` replaces `--max-age`, `--company-ids` replaces `--company`, and `--attributes` replaces `--attribute`. A list flag takes several values after one flag.
- **Breaking:** A `Fetcher` has one `fetch(url, *, headers=None, json=None)` that sends a POST when `json` is given, so an Indeed search runs on any fetcher. `FetchResult.status` replaces `status_code`, and `FetchResult.error` is a message string.
- **Breaking:** `JobDict` is a `TypedDict`.
- **Breaking:** `max_age_hours` defaults to `None` on both sites, so a search without `--max-age-hours` covers postings of any age. It used to keep the past 168 hours.
- **Breaking:** The cache stores each fetched LinkedIn posting as a whole `JobDict` under its site and posting ID, so it starts empty after this upgrade. The 0.19.0 tables stay in the cache file, so delete the file to reclaim their space. The shared instance is `jobrake.cache.CACHE`, and `Cache.get(site, ids)` and `Cache.put(jobs)` read and write its records.
- Concurrent LinkedIn requests in one process no longer leave in the order they arrived. Each data center still gets one request per pacing interval.

### Removed

- **Breaking:** `jobrake.defaults`, `jobrake.sites.site_searchers()`, `jobrake.models.Job`, `jobrake.utils.check_filters()` and the other `check_*` helpers, and `jobrake.io.to_json()`, `to_jsonl()`, and `to_csv()`. Render records with `jobrake.io.RENDERERS`.
- **Breaking:** The modules `jobrake.fetchkit.base` and `limiter`, `jobrake.sites.linkedin.geo`, `companies`, and `postings`, and `jobrake.sites.indeed.geo`, `companies`, and `attributes`. Each site's lookups live in its `lookups` module, and LinkedIn's posting pages in `pages`.
- **Breaking:** `BaseFetcher`, `PostFetcher`, `ErrorCategory`, `FetchError`, `TokenBucket`, and `build_result` from `jobrake.fetchkit`, and the `cookies`, `follow_redirects`, and `jitter` options of `HttpxFetcher`.
- **Breaking:** `resolve_geoid`, `parse_cards`, `parse_posting`, `job_id`, `CACHE`, `BASE_URL`, `HEADERS`, `SEARCH_URL`, `TYPEAHEAD_URL`, `FRAGMENT_URL`, and `MAX_START` from `jobrake.sites.linkedin`.
- **Breaking:** `API_HEADERS`, `API_URL`, `AUTOCOMPLETE_URL`, `INDEED_APP_KEY`, `QUERY`, `build_query`, and `parse_jobs` from `jobrake.sites.indeed`.
- **Breaking:** LinkedIn's `country`, `employer_key`, `remote`, `language`, and `attributes` options, and Indeed's `details`, `cache`, `geoid`, `easy_apply`, and `early_applicant` options, which each site accepted without applying.
- **Breaking:** `JOBRAKE_CACHE_RETENTION`, the `retention` and `ttl` arguments of `Cache`, and `POSTINGS`, `ADDRESSES`, `GEOIDS`, and `RETENTION` from `jobrake.cache`, with the posting-address cache and the gone-posting markers.
- **Breaking:** `cache=False` and `--no-cache`, with no per-call replacement. To bypass the cache, point `JOBRAKE_CACHE_PATH` at a new file.

### Fixed

- A LinkedIn posting URL keeps no tracking query or trailing slash in its record, and a URL with a `#` fragment, a port, or no `www` is accepted.
- A LinkedIn posting URL whose ID uses digits outside 0-9 raises `ValueError` before any request. It used to spend a request.
- A LinkedIn posting page without the schema.org block, whose en-US fragment then fails, gets no record and no cache row. It used to be cached without its employment type and salary.
- A LinkedIn posting fetched by ID whose page lacks the schema.org block costs two requests, not three.
- `--output` accepts an uppercase extension, such as `jobs.JSON`.
- An Indeed response whose `results` is not a list stops the search as unreadable. It used to read as an empty or all-malformed page.
- A LinkedIn posting whose `monthsOfExperience` is not an integer, such as `6.5`, gets no `experience_months`. It used to hold the float.

## [0.19.0](https://github.com/eyayaw/jobrake/releases/tag/v0.19.0) - 2026-10-26

### Added

- `HttpxFetcher(transport=...)` replaces the network with an httpx transport, as `httpx.MockTransport` does in tests.
- `Cache.close()` closes the SQLite connection. A working cache reopens it on the next read or write.
- `models.JobDict` types the job dictionaries that `make_job` builds and searches return.

### Changed

- **Breaking:** jobrake requires Python 3.14.
- **Breaking:** `HttpxFetcher` takes every option after `timeout` by keyword, and `indeed.build_query` takes its filters by keyword.
- **Breaking:** `ErrorCategory` is a `StrEnum`, so `str(ErrorCategory.NETWORK)` is `"network"` instead of `"ErrorCategory.NETWORK"`.

## [0.18.0](https://github.com/eyayaw/jobrake/releases/tag/v0.18.0) - 2026-10-18

### Changed

- **Breaking:** `linkedin.LIMITER` is removed. jobrake sets the LinkedIn pace from the number of data centers it knows, so a caller's own setting would be overwritten.
- **Breaking:** `linkedin.RETRY_DELAY` is removed. Assigning it never changed the retry delay, because jobrake reads its own copy.
- **Breaking:** LinkedIn requests carry only the data-center cookie, so cookies seeded on the fetcher reach LinkedIn only when it redirects a request.
- LinkedIn requests go out about three times as fast. jobrake spreads them over LinkedIn's three data centers, each with its own limit. jobrake retries a 429 up to three times instead of once.

### Removed

- Reading `Retry-After` on LinkedIn 429 responses, which the guest API does not send.

## [0.17.0](https://github.com/eyayaw/jobrake/releases/tag/v0.17.0) - 2026-10-04

### Added

- Filter Indeed jobs by attribute codes with repeatable `--attribute CODE` options or `attributes=[...]`. Discover codes and labels from matching postings with `jobrake attributes indeed -c EDITION QUERY` or `jobrake.sites.indeed.attributes()`. Surrounding whitespace in codes is ignored.
- Filter Indeed searches by posting language with `--language CODE` or `language="en"`. Two-letter codes accept either case, and the result limit counts postings in the selected language.
- Find LinkedIn jobs with Easy Apply or fewer than 10 applicants. Use `--easy-apply` and `--early-applicant` separately or together, with matching library options.
- Limit Indeed searches to postings tagged Remote with `--remote` or `remote=True`, alongside company, location, and age filters.
- Find Indeed employer keys with `jobrake companies indeed NAME --country EDITION` or `jobrake.sites.indeed.companies()`, then search for jobs at one company using `--company KEY` or `employer_key=KEY`. Surrounding whitespace in the key is ignored.
- Find company IDs with `jobrake companies linkedin NAME` or `jobrake.sites.linkedin.companies()`, then search their postings with repeatable `--company ID` options or `company_ids=[...]`.
- Indeed results include a language code when available, so callers can keep postings in languages they read. CSV output gains a `language` column after `description`.
- Configure the cache location, freshness and retention period through `JOBRAKE_CACHE_PATH`, `JOBRAKE_CACHE_TTL` and `JOBRAKE_CACHE_RETENTION`.
- `jobrake linkedin` takes `--radius`, `-r`, in kilometers.
- Every filter belongs to the shared search signature, so one set of options can go to both providers. A provider checks only the filters it applies and warns for each one it ignores.

### Changed

- **Breaking:** `--output` refuses an existing path, protecting earlier results from accidental replacement. An unwritable output directory is refused before the search starts.
- **Breaking:** `radius` on a LinkedIn search is kilometers, as on Indeed. LinkedIn reads its distance in miles, so `radius=25` used to reach about 40 km. jobrake now sends the value rounded to whole miles.
- Searches ask for newest postings first. Indeed already returned that order and LinkedIn's guest endpoint ignores the request, so results are unchanged for now. The guide describes each site's order and how to collect only new postings with `--max-age`.
- Search query documentation now explains that jobrake forwards text unchanged.
  - Indeed recognizes field restrictions, such as `title:` and `company:`.
  - LinkedIn's documented Boolean operators do not work on its guest endpoint.
- `jobrake details` and `fetch_details()` cache each posting's canonical URL and remember postings whose lookup found them gone. A rerun over the same IDs or `www` URLs sends no lookups, where 100 IDs used to spend about five minutes on them. `--no-cache` still sends every lookup.
- `--geoid` and `resolve_geoid()` pick the candidate whose name equals the requested one. LinkedIn lists a region ahead of the city that shares its name, so `Utrecht, Utrecht, Netherlands` used to search the province. A name with no exact candidate still takes the first one. This release clears cached place resolutions, so each name resolves again on first use.
- Gone-posting markers expire after `JOBRAKE_CACHE_RETENTION`, 30 days by default. A posting that once returned 404 or 410 used to be skipped on every later cached run.
- Indeed warns when a search passes it a `geoid`, which only LinkedIn applies.
- `--no-cache` and `cache=False` refresh the posting cache instead of bypassing it, so later cached runs see what a refetch found. A refetched page without the schema.org block leaves a fresh cached copy that has the block in place, with its dates, coordinates, and requirements.

### Fixed

- `jobrake details` and `fetch_details()` stop warning that a US posting's `www` URL serves no schema.org block. That URL is the posting's canonical address, and its dates and coordinates come through.
- An Indeed search raises `TypeError` for a non-string `query`, `location`, or `country`. A LinkedIn search does so for `query` and `location`, and for a `geoid` that is neither a string nor a Boolean. These used to surface as `AttributeError` or as a missing-location error.

## [0.16.0](https://github.com/eyayaw/jobrake/releases/tag/v0.16.0) - 2026-09-05

### Added

- `jobrake details linkedin <ID|URL> ...` fetches known postings without repeating a search, with the same `--output`, `--format`, and `--no-cache` options. Several references to one posting return one job. Library callers can use `jobrake.sites.linkedin.fetch_details`. URLs from search results need the fewest requests; other accepted references require a lookup first.
- jobrake ships a `py.typed` marker, so downstream type checkers use its inline annotations. Without it mypy reports jobrake as missing stubs and falls back to `Any`.

### Changed

- `jobrake --help` describes the program and each subcommand instead of listing bare names.
- The MIT text stands alone in `LICENSE`, and the JobSpy attribution moved to `THIRD_PARTY_NOTICES`, which ships with the package. GitHub had read the concatenated file as "Other" rather than MIT.
- This release rebuilds both cache tables, clearing existing entries, including the escaped logo URLs described below. Posting fields and place resolutions now have separate format versions. Releases bump the affected version when fields or parsing change, so jobrake refetches those values while preserving the other table's entries.
- LinkedIn posting pages yield `title`, `company`, and `location`, so one page is enough to build a whole job. A hydrated search result takes these from the posting page wherever it names them.

### Fixed

- Strings from a LinkedIn posting's schema.org block are HTML-decoded. `company_logo` had carried `&amp;` between its query parameters, which made the image URL answer 403.
- A warning carrying a transport failure reads as one sentence, with a lowercase label and the status attached, as in `server error (HTTP 500)`.
- Rejecting a timestamp says why. A value that resolves before the year 2000 is reported as epoch seconds rather than milliseconds.
- A numeric search argument that is not an integer now raises `TypeError` naming the argument. Previously `results=2.5` failed at page slicing, a non-finite `radius` or `max_age_hours` reached Indeed inside a malformed query, and `radius=False` searched a 0 km radius instead of omitting it.

## [0.15.0](https://github.com/eyayaw/jobrake/releases/tag/v0.15.0) - 2026-09-02

### Added

- `jobrake linkedin --geoid | -g` searches by LinkedIn's own place ID. The bare flag resolves `--location` through the guest place lookup, reports the qualified place it picked, and saves the resolution in the SQLite cache. A location that fails to resolve returns no jobs. `--geoid 102011674` searches that area directly, with `--location` optional. Library calls take `geoid=True` or a geoId string.
- `jobrake places linkedin|indeed <name>` prints a provider's candidate places for a name as JSON, best match first: LinkedIn geoIds with their qualified names, or an Indeed edition's canonical location suggestions. LinkedIn candidates also seed normalized query and qualified-name keys in the geoId cache. `--country` picks the Indeed edition, as in search. The lookups are public as `jobrake.sites.linkedin.places` and `jobrake.sites.indeed.places`, and `jobrake.sites.linkedin.resolve_geoid` returns the single best LinkedIn ID.

### Changed

- **Breaking:** `jobrake indeed` and `jobrake linkedin` replace the `--site | -s` option.
- **Breaking:** Searches now default to 10 results, a seven-day age limit, a 40 km Indeed radius, and no LinkedIn distance parameter.
- **Breaking:** Search arguments are renamed: `search_term` to `query`, `results_wanted` to `results`, `hours_old` to `max_age_hours`, `distance` to `radius`, and `detail` to `details`. The CLI renames `--search-term` to `--query`, `--results-wanted` to `--results`, `--hours-old` to `--max-age`, and `--detail` to `--details`.
- jobrake stores posting details and LinkedIn geoId resolutions in separate tables within `jobrake.sqlite3`.

## [0.14.0](https://github.com/eyayaw/jobrake/releases/tag/v0.14.0) - 2026-08-25

### Added

- Provider searches log their start and result count. LinkedIn detail fetching also logs its progress and, on completion, the resolved count.
- On a terminal, the CLI renders LinkedIn detail progress as a self-updating bar with a `current/total` count on stderr.

### Changed

- When a search finds no jobs, `--output` leaves the file untouched and warns instead of replacing it with an empty document.

### Fixed

- `--output` rejects a directory path or a missing parent directory before any provider requests, and a failed write reports the error instead of a traceback.

## [0.13.0](https://github.com/eyayaw/jobrake/releases/tag/v0.13.0) - 2026-08-24

### Added

- Search failures warn with the error and number of jobs kept. LinkedIn also
  warns when its search reaches the ~1,000-card ceiling, a detail page yields
  no usable fields, or a detail request fails transiently.

### Changed

- LinkedIn ends detail hydration when a posting or en-US fragment request
  still returns 429 after applying the retry policy. It returns every posting
  already resolved. A limited fragment keeps and caches the canonical page's
  partial fields.
- The LinkedIn 429 retry honors a seconds-form `Retry-After` header. A delay
  above one minute skips the retry and returns the 429.
- A nonpositive `results_wanted`, a negative `distance`, and a blank LinkedIn
  `location` raise `ValueError` before any request, from `scrape()` and the
  site `search()` functions.

### Fixed

- Indeed keeps its page size at 100 throughout a cursor chain. Requested counts such as 202 no longer stop at the preceding full page.
- LinkedIn postings whose schema.org block carries `NaN` or an infinity no
  longer leak those constants into the output, which strict JSON parsers
  reject. Non-finite and beyond-float-range numbers are dropped like other
  malformed fields.
- An Indeed number too large for a float crashed the whole scrape with
  `OverflowError`; it now costs only that field.
- Indeed continues pagination when every result on a page is malformed but
  the response supplies a valid continuation cursor.
- Malformed LinkedIn salary bounds no longer stop detail hydration. The
  salary fields are omitted.
- Cached LinkedIn rows containing `NaN` or an infinity are treated as misses
  instead of being returned.

## [0.12.0](https://github.com/eyayaw/jobrake/releases/tag/v0.12.0) - 2026-08-21

### Added

- `--format | -f` selects the output format: `json`, `jsonl`, or `csv`. It
  replaces the default JSON on stdout and overrides the `--output` extension.
- `jobrake.io.to_jsonl` and `to_csv` render a job list to a string, alongside
  `to_json`.

### Changed

- JSON output is compact regardless of result count.

### Removed

- **Breaking:** the `jobrake.io` path writers `write_json`, `write_jsonl`, and
  `write_csv`. Render with a `to_*` function and write the returned string to
  a file or stream.

### Fixed

- A closed pipe detected while writing to stdout (`jobrake ... | head`) ends
  the run quietly with exit code 1 instead of a `BrokenPipeError` traceback.

## [0.11.0](https://github.com/eyayaw/jobrake/releases/tag/v0.11.0) - 2026-08-20

### Changed

- **Breaking:** Job dicts retain the seven identity and summary keys, using
  `None` for unavailable summary values. Detail fields appear only when a
  value is available.

### Fixed

- Indeed skips malformed results without discarding valid siblings, preserves
  parsed jobs when pagination metadata is damaged, and omits provider values
  that do not match the model type.
- LinkedIn advances pagination by the raw card count, so overlapping pages and
  unparseable cards do not truncate a search.
- LinkedIn accepts the structured forms used for employment type, company
  logos, country, and other schema.org fields; unsupported shapes are omitted.
- Malformed cache timestamps disable the cache and become misses instead of
  stopping a scrape.
- Search entry points reject zero and negative posting-age filters.
- `HttpxFetcher` classifies protocol and proxy failures as network errors while
  leaving malformed URLs in the unknown category.
- LinkedIn fetches each posting ID at most once per detail call, even when
  several URLs refer to it or its first request fails transiently.


## [0.10.0](https://github.com/eyayaw/jobrake/releases/tag/v0.10.0) - 2026-08-18

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

## [0.9.0](https://github.com/eyayaw/jobrake/releases/tag/v0.9.0) - 2026-08-16

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

## [0.8.0](https://github.com/eyayaw/jobrake/releases/tag/v0.8.0) - 2026-08-13

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

## [0.7.0](https://github.com/eyayaw/jobrake/releases/tag/v0.7.0) - 2026-08-11

Results now land wherever your tools want them: `--output` writes JSON, JSONL,
or CSV, resolved from the file extension.

### Added

- `--output | -o PATH` writes results to a file instead of stdout. A bad extension fails before the scrape spends a single request; with `-o`, stdout stays silent and a summary line goes to stderr.
- JSONL output holds one job per line, so files from separate runs merge with a plain `cat runs/*.jsonl`.
- The writers are library API too: `jobrake.io.write_json`, `write_jsonl`, and `write_csv` save a job list exactly as the CLI does, with the CSV header derived from the job dict itself.

## [0.6.0](https://github.com/eyayaw/jobrake/releases/tag/v0.6.0) - 2026-08-10

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

## [0.5.0](https://github.com/eyayaw/jobrake/releases/tag/v0.5.0) - 2026-08-10

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

## [0.4.0](https://github.com/eyayaw/jobrake/releases/tag/v0.4.0) - 2026-08-08

### Changed

- **Breaking:** `HttpxFetcher` provides JSON `post` itself; `HttpxPostFetcher`
  dropped.

## [0.3.0](https://github.com/eyayaw/jobrake/releases/tag/v0.3.0) - 2026-08-08

### Added

- The `PostFetcher` protocol names what the Indeed scraper requires; no
  dependency on the private fetchkit package.

## [0.2.0](https://github.com/eyayaw/jobrake/releases/tag/v0.2.0) - 2026-08-07

### Added

- The fetchkit transport subset vendored as `jobrake.fetchkit`.
