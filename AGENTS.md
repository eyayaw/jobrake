# jobrake agent instructions

## Purpose

jobrake reads the postings a job board publishes and returns each one as a
record with the same fields, whichever board it came from. It is an async
Python package and CLI that reads LinkedIn's guest API, Indeed's GraphQL API,
EconJobMarket's ad feed, and the board APIs of six applicant tracking
systems, and it depends on `httpx` and `bs4`.

## Map

- `sites/__init__.py`: `SITES`, the registry with one entry per site, and
  `scrape`, which routes a search to its site.
- `sites/<site>/`: one package per site. `__init__` exports `search` and any
  of `places`, `companies`, `attributes`, and `postings`, and the first line
  of its docstring is the site's CLI help. `search.py` builds requests and
  parses results. LinkedIn's and Indeed's `client.py` hold their URLs,
  headers, and pacing, and their `lookups.py` hold the lookups. The other
  sites need no headers or pacing and have no `client.py`. LinkedIn's
  `pages.py` fetches posting pages for `postings` and `details=True`, and
  Indeed's `countries.py` maps country names to editions.
- `sites/responses.py`: the response reading the JSON sites share, for one
  request or each page. `read_json` raises `Stopped` for an unknown board, a
  failed request, or an unreadable response, `json_list` checks the posting
  list, `json_page` checks a page's list and its total, and `parse_postings`
  skips a malformed posting with a warning. A new site of this kind writes
  no error handling of its own.
- `utils.py`: `site_options`, which reads the `Annotated` arguments of a
  site function, `checked`, which checks every call against them, and the
  JSON value, text, number, and date helpers.
- `models.py`: `JobDict`, its `Place`, `make_job`, `make_places`, and `Stopped`.
- `fetchkit/`: the `Fetcher` protocol, `FetchResult`, and `HttpxFetcher`.
- `cache.py`: one SQLite table of `JobDict` records keyed by site and ID, and
  the shared `CACHE`.
- `cli.py` builds `jobrake <site> <command>` from `SITES`, one command per
  function a site exports, and `io.py` renders JSON, JSONL, and CSV.
- `tests/`: offline, built on the stub fetcher in `tests/fakes.py`.
  `tests/fakesite.py` is a fake site the tests register.

A new site is a package under `sites/` and one entry in `SITES`. `scrape`,
the CLI, and the contract test in `tests/test_scrape.py` need no edit.

## Non-goals

- Filtering or choosing results locally, or translating an option from one
  site to another. jobrake returns what the site serves.
- Generic pacing or retries in `fetchkit`. A site adds only the pacing its
  server demands.
- A browser fetcher or any optional transport.
- Compatibility shims and deprecation aliases. A rename removes the old name.

## Decisions

- The design follows from the purpose. No caller's needs shape it.
- `site`: the unit jobrake reads, such as `linkedin` or `indeed`. It replaces
  "provider".
- `board`: the token, or for Workday the career site URL, that names one
  employer's board on an ATS site, such as `airbnb` on Greenhouse. Every ATS
  site declares it as a required `str` named `board`, with the short flag
  `-b`.
- One record. Every site returns `JobDict` records with the same keys, types,
  and units. The identity keys `site`, `id`, and `url` and the summary keys
  `title`, `company`, `locations`, and `date` are always present. A detail
  key appears only when it has a value. Each site parses its own responses.
- A posting's places are `locations`, a list of `Place` in the site's order,
  `[]` when none was extracted. A `Place` has a `name`, the site's label or
  its parts joined, and only the parts the site gives for that place.
  `make_job` normalizes places with `make_places`, for every site and every
  cache read, and nothing is parsed out of a label. Two places are one only
  when they are equal once normalized. A site treats two of its entries as
  one place only when its response says so. Where one source's fields
  override another's, an empty `locations` overrides nothing.
- A site owns its options. `search` declares only the options its server
  applies, keyword-only, as `Annotated[T, "help"]` with `T` one of `str`,
  `int`, `bool`, `list[str]`, or `T | None`, and with defaults in the
  signature. A boolean option defaults to `False`. A name two sites share
  keeps one meaning and unit. Every function a site exports carries
  `@checked`, which raises `TypeError` for an unknown, missing, or wrongly
  typed argument and `ValueError` for a value out of range, a blank required
  string, or a blank list entry, all before the first request. `site_options`
  rejects an annotation or a boolean default that breaks these rules when the
  module is imported, and `test_a_site_meets_the_site_contract` checks that
  `search` takes no positional option and that a shared name keeps its type.
- A caller can tell a cut-short result from a complete one. A failed
  request, or a page that ends a search short of the total the site
  reported, raises `Stopped`, whose `partial` holds what was collected. A
  site's own result cap warns and returns, because a rerun meets it again. `postings` never raises `Stopped`
  and leaves a failed reference out of its result.
- The transport is the caller's. Code takes a `Fetcher` and leaves it open,
  and the caller that created it closes it. LinkedIn requests go through
  `paced_fetch`, which pins requests to LinkedIn's data centers in turn,
  paces them once per process, and retries a 429 up to three times.
- The cache is transparent. It stores the whole `JobDict` of each fetched
  LinkedIn posting, rows carry no version, and each row read passes through
  `make_job`, so a row whose keys no longer fit `JobDict` or `Place` is a
  miss. `make_job` normalizes a row as it does a site's fields and cannot
  redo a parser's work, so a parser fix reaches a cached posting when its row
  expires. `JOBRAKE_CACHE_PATH` and `JOBRAKE_CACHE_TTL` configure it, and no
  site function takes a cache option. Only LinkedIn is paced and cached.
- Library code logs under the `jobrake` logger and prints nothing. The CLI
  sends logs to stderr and data to stdout. It exits 2 for a bad argument, and
  1 when a search or lookup raises `Stopped`, a named posting could not be
  fetched, or the output cannot be written. A stopped search and a postings
  fetch with a failed reference still write what they got.

## Style

- Keep module docstrings to one-line orientation. Keep short docstrings on one
  line; longer ones open with a bare `"""` and put the summary on the next line.
  Put rationale and contracts on the symbol that owns them.
- Comments explain non-obvious mechanisms or reasons. User-facing messages
  state what happened, name the likely cause when known, and give a concrete
  next action.
- Treat style checks as heuristics, not bans. Preserve useful facts, concrete
  examples, and the author's voice. Use punctuation where it improves clarity.
- Wrap only genuinely long passages, tables, and code. Keep short prose
  sentences on one line even when they cross the usual line length.
- Always write `jobrake` in lowercase.
- Inside `sites/`, prose uses each site's nouns: postings, cards, and fields.
  "Job" and "job dict" appear only where the package promises them, in `models`, `scrape`,
  and the README. Indeed's API says "job", so the word stays in its code.
- Describe detail fields as what we extract, when present, and avoid "the
  posting states". "Hydrate" stays in code docstrings, and the README says "fetch" or "fill".
- The tagline is one image with no feature list: "The job boards shed new
  postings every day. Bring a rake."
- Keep the README as a short landing page. Put detailed usage, output, and
  site-specific behavior in `docs/guide.md`.
- Keep CLI help terse. It comes from the `Annotated` help of each option and
  the first docstring line of each site package and site function. Caveats
  and site quirks go in the guide.
- The guide tells readers what they need to use jobrake. Leave out input
  normalization, request sizes, and other internals.

## Sites

- Keep the sites symmetric, with the same names and units for the options
  they share, so shared code stays shared.
- Live requests to LinkedIn or Indeed spend the rate budget of my IP. Ask
  before sending any, and keep them few and paced. The test suite is offline.
- State site behavior that we measured as measured, and say in the guide
  when it is unreliable.

## Verify

- A change passes when `prek run --all-files` exits 0. It runs ruff check,
  ruff format, ty, and pytest from the locked environment. CI runs the same
  hooks, and so does every commit once `prek install` has run in the clone.
