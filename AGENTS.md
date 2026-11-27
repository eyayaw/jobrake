# jobrake agent instructions

Use the code and docs in this repo as evidence of past decisions, not as a prose template.
Judge changes by whether the code and docs read and work well, not just by ticking rules. Preserve
useful facts, concrete examples, citations, and the author's voice across docs and comments.

## Purpose

jobrake is an async Python package and CLI that reads job postings without sign-in from multiple
boards (public APIs, feeds, and web/mobile app endpoints) and returns them in one shared record
format. The design follows from this purpose; no caller's needs shape it. Runtime dependencies stay
minimal: `httpx` and `beautifulsoup4`.

## Architecture map

- `src/jobrake/models.py`: `JobDict`, `Place`, `make_job`, `make_places`, and `Stopped`.
- `src/jobrake/countries.py`: ISO 3166-1 table and `alpha2` (shared by `@checked` and
  `make_places`).
- `src/jobrake/fetchkit.py`: `Fetcher` protocol, `FetchResult`, and `HttpxFetcher`.
- `src/jobrake/cache.py`: SQLite cache of `JobDict` rows keyed by `(site, id)` and shared `CACHE`.
- `src/jobrake/utils.py`: `SITE_NAMES`, `site_options`, `@checked`/`Checked`, `menu_codes`,
  `report_progress`, HTML/JSON/date/URL helpers.
- `src/jobrake/cli.py` & `io.py`: builds `jobrake <site> <command>` dynamically from `SITES` and
  renders JSON, JSONL, and CSV.
- `src/jobrake/sites/__init__.py`: `SITES` registry plus public `scrape`, `check`, and `identify`.
- `src/jobrake/sites/responses.py`: shared response readers (`read_json`, `read_xml`, `read_html`,
  `json_ld`), pagination (`collect`, `offset_pages`), `parse_postings`, `failure`, `UNREADABLE`.
- `src/jobrake/sites/postings.py`: shared detail-fetching loop (`fill_details`), `postings_of`,
  `Halt`, and `readable_url`.
- `src/jobrake/sites/<site>`: one module per site (packages for `linkedin/` and `indeed/`). Exports
  `search` and optionally `postings` or lookups (`places`, `companies`, `attributes`, `filters`).
  Sites supporting `postings` or `identify` also define `card(reference)` (outside `__all__`),
  which parses one posting URL or raises `ValueError`. LinkedIn's `postings` also accepts bare
  numeric posting IDs.
- `tests/`: fully offline suite using `tests/fakes.py` and `tests/fakesite.py`.

**Adding a new site:** add `src/jobrake/sites/<site>.py`, register it in `SITES`
(`sites/__init__.py`) and `SITE_NAMES` (`utils.py`), and add `docs/sites/<site>.md`.
`scrape`, the CLI, and the contract tests in `tests/test_scrape.py` pick it up automatically.

## Non-goals

- Local filtering or sorting of results, or translating options between sites. Return what the site
  serves.
- Generic retries or rate limiting in `fetchkit`. Only add pacing where a site requires it.
- Browser-based scraping or optional transport backends.
- Backwards-compatibility shims or deprecation aliases. Remove old names on rename.

## Core contracts

- **Naming:** Use `site` (never "provider"). ATS boards declare a required `board: str` (`-b`):
  employer slug, or career site URL for Cornerstone and Workday. `country` accepts ISO 3166-1
  alpha-2 or alpha-3 (case-insensitive); `@checked` passes upper-case alpha-2 to sites.
- **Records & places:** Identity (`site`, `id`, `url`) and summary (`title`, `company`, `locations`,
  `date`) keys are always present; detail keys are omitted when absent or empty (`None`, blank
  strings, empty lists/dicts; `0` is preserved). `locations` is a list of `Place` in the site's
  order (`[]` when none was extracted). Each `Place` has `name` (site label or joined parts) plus
  only the parts the site gave, with `country_code` normalized to upper-case alpha-2 by
  `make_places`. Never parse structured parts out of a label; deduplicate two places only when
  equal after normalization, and merge two entries into one place only when the site's response
  says so. Empty `locations` never overrides a non-empty one during merges. Site-only fields live
  in `site_data` (documented on that site's page) and move to `JobDict` once a second site shares
  the same meaning.
- **Options:** `search` exposes only server-supported filters as keyword-only
  `Annotated[T, "help"]` (`T` in `str`, `int`, `bool`, `list[str]`, or `| None`), with defaults in
  the signature (`False` for booleans); lookups and `postings` take one positional argument after
  `fetcher`. Shared option names keep one type, meaning, and unit across sites. Every exported site
  function uses `@checked` (with `validator=` for site-specific rules) so both calls and `.check()`
  fail before the first request: `TypeError` for unknown, missing, or wrong-type args, and
  `ValueError` for out-of-range values, blank required strings, blank list entries, or
  site-rejected values (except live-catalog checks like UN Careers duty stations).
- **Failures, `details`, & `postings`:** Failed requests, non-200 responses, unreadable payloads,
  and empty pages before the reported total raise `Stopped(partial=...)`. Hitting a site's result
  cap warns and returns normally because a rerun meets it again. Add `details` on `search` when
  search cards lack fields the posting endpoint serves, and export `postings(fetcher, references)`
  when a posting URL alone can be read back. `postings_of` validates every reference with `card`
  before the first request. `postings` never raises `Stopped`: it keys results by the input
  references, maps gone postings to `None`, and omits failed references. Details searches put unread
  URLs in `Stopped.failed` when the site exports `postings`, so `postings` can retry them even if a
  later search drops them.
- **Detail merging:** When `--details` merges a fetched posting into a search card, the posting
  wins for every field with a value (not `None` or `[]`; `site_data` merges key-by-key) while the
  card keeps its `site`, `id`, and `url`. `readable_url` rejects a search card whose URL `card` does
  not read back unchanged.
- **Transport & pacing:** Callers own and close any `Fetcher` they pass in. Only two sites are
  paced:
  - LinkedIn: `paced_fetch` pins fabrics, paces process-wide, retries 429s up to 5 times, and
    handles HTTPS-only LinkedIn redirects hop-by-hop (so custom `Fetcher`s must honor
    `follow_redirects=False`). Posting-page reads use 2 workers per fabric, with each concurrent
    call running its own pool.
  - AcademicTransfer: waits the 10s `robots.txt` crawl delay before each API page request.
- **Caching:** Only the posting loop (`sites/postings.py`) uses `cache.CACHE`, transparently,
  configured via `JOBRAKE_CACHE_PATH` and `JOBRAKE_CACHE_TTL` (no per-call cache flags). Cached
  rows carry no version and pass through `make_job` on read; rows rejected by the current schema
  count as cache misses, while parser fixes reach cached postings only when their rows expire.
- **CLI & logging:** Library code logs under `jobrake` and never prints. The CLI writes logs and
  progress to stderr and data to stdout. Exit codes: `0` complete, `1` stopped/failed/write error,
  `2` bad arguments, `130`/SIGINT on Ctrl-C (removing any newly created `--output` file on write
  errors or Ctrl-C). Stopped searches and `postings` runs with failed references still write
  collected records, or write nothing when none were collected, so an empty document comes only
  from a command that completed. An unwritable stderr (closed pipe), or closed stdout under
  `-h`/`--version`, keeps the exit status unchanged.

## Docs and style

- Always write `jobrake` in lowercase. The authors are "we". Wrap Markdown prose near 100 columns.
- Keep module docstrings to one line; put rationale and contracts on the symbol that owns them.
  User-facing errors and warnings state what happened, the likely cause when known, and a concrete
  next action.
- Inside `sites/`, use site terminology (`postings`, `cards`, `fields`; Indeed uses `job`). Use
  "job" and "job dict" only where the package promises them (`models`, `scrape`, and the README).
  Describe detail fields as what we extract when present (avoid "the posting states"). Keep
  "hydrate" in code docstrings; README says "fetch" or "fill".
- Tagline at the top of `README.md`: `"The job boards shed new postings every day. Bring a rake."`
- Doc layout:
  - `README.md`: install, real runnable example + output, shared options, formats, sites table,
    pacing/caching overview.
  - `docs/guide.md`: cross-site workflows.
  - `docs/reference.md`: record schema, field matrix, CLI, Python API, configuration.
  - `docs/sites/<site>.md`: standalone guide per site. Standard `##` sections (`Options`, `Lookups`,
    `Fields`, `Requests`, `Terms`) keep that relative order when present; extra `##` sections are
    allowed when helpful.
- Keep CLI `--help` terse (first docstring line + `Annotated` help); put quirks on the site page.
- Write docs in plain, direct English for job seekers and developers. Avoid stiff telegraphic
  wording (`carries`, `holds`, `gives no`, `A record has no...`), internal jargon (`card`, `record`)
  in site pages, em-dash overuse, and copy-pasted sentence templates across pages.
- Skip documenting internals, input normalization, request page sizes, and what `--help` or logs
  already say. State empirically observed site behavior plainly (and note when it is unreliable)
  without repeating `"in our tests"`. Put sample sizes/dates in inline comments only for live-site
  quirks (never on RFCs, stdlib, SQLite docs, or library defaults, and never inside signatures or
  docstrings).
- Keep `CHANGELOG.md` entries concise and user-facing: group edge-case hardening instead of listing
  every fuzzer counterexample or warning-wording tweak separately.

## Live requests and verification

- The test suite is offline. Ask before making live requests to external boards, and keep any live
  probes small (especially on LinkedIn, where concurrent runs from the same IP share rate limits).
- A change is ready when `prek run --all-files` exits 0 (`ruff check`, `ruff format`, `ty`, and
  `pytest`).
