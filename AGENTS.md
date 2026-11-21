# jobrake agent instructions

## Purpose

jobrake reads the postings a job board publishes and returns each one as a record with the same
fields, whichever board it came from. It is an async Python package and CLI that reads LinkedIn's
guest API, Indeed's GraphQL API, the AcademicTransfer jobs page's list API, the AEA JOE listings
page and its XML export, EconJobMarket's ad feed, the INOMICS search page's results endpoint and job
pages, StepStone's mobile listings API, the UN Careers web app's list API, and the board APIs of
applicant tracking systems, and it depends on `httpx` and `bs4`.

## Map

- `sites/__init__.py`: `SITES`, the registry with one entry per site, `scrape`,
  which routes a search to its site, `check`, which runs a search's option checks alone,
  and `identify`, which asks each site's `card` whose posting a link names.
- `sites/<site>`: one module per site, or a package for LinkedIn and Indeed,
  which split into several modules. It exports `search` and any of `places`, `companies`,
  `attributes`, `filters`, and `postings`, and the first line of its docstring is the site's CLI help.
  A site that exports `postings` defines `card(reference)`, outside `__all__`, and a site may
  define one for `identify` alone, as Indeed does. `card` reads one posting URL as the card it
  names and raises `ValueError` for any other reference. `postings_of` builds a site's `postings`
  from its `card` and its reader, and that `postings` reads every reference with `card` before the
  first request.
  LinkedIn's `postings` reads references as its `card` does and also takes a bare posting ID.
  In the two packages, `search.py` builds requests and parses results, `client.py` holds the URLs
  and headers, plus LinkedIn's pacing, and `lookups.py` holds the lookups. Of the other sites,
  only AcademicTransfer paces its requests, waiting the crawl delay its robots.txt asks for before
  each request to its list API, and only it, StepStone, and INOMICS send headers of their own.
  LinkedIn's `pages.py` holds its reader of posting pages, which the posting loop runs with a
  fixed pool of workers, and Indeed's `countries.py` maps ISO country codes to editions.
- `sites/responses.py`: the response reading the sites share. `read_json`, `read_xml`, and
  `read_html` raise `Stopped` for a failed request or an unreadable response, and the first two for
  an unknown board. `failure` says why a response holds no data: its `error`, no status, or a
  status other than HTTP 200. `UNREADABLE` holds the exceptions a parser raises for data it cannot
  read, which those readers and `parse_postings` catch, and `json_ld` reads a page's schema.org
  nodes.
  `json_list` checks the posting list, `json_page` checks a page's list and its total, `cut_short`
  builds the `Stopped` of an empty page before that total, and `parse_postings` skips a malformed
  posting with a warning.
  `collect` gathers the pages a paged search yields: it drops a repeated posting, logs progress,
  stops at `results`, and keeps the pages before a failure. A paged site yields its pages from a
  generator and leaves the rest to `collect`. `offset_pages` builds that generator from a site's
  reader of one page and its card parser.
- `sites/postings.py`: the posting loop of the sites that fetch each posting on its own,
  LinkedIn among them. `fill_details` serves `details=True` and `postings_of` builds `postings`,
  and each site supplies only the reader of the posting at a URL, which raises `Stopped` for a
  posting it could not read and `Halt` when no posting can be read for now. Each posting read
  becomes a record of its own, with the posting's own `url` when the reader gives one. The cache
  stores it, `postings` returns it, and a details search merges it into each card of the posting:
  the record wins wherever it has a value, and the card keeps its `site`, `id`, and `url`.
  A cached posting costs no request. `readable_url` keeps a search card's URL only when the site's
  `card` reads it back unchanged, so `postings` can fetch the card's posting.
- `utils.py`: `site_options`, which reads the `Annotated` arguments of a site function, `checked`,
  which wraps it in a `Checked` that runs those checks and the site's validator on every call,
  or alone through `check`, `menu_codes`, which maps filter values to codes of a site's fixed menu,
  `report_progress`, which `collect` and the posting loop call to log their progress records,
  and the JSON value, text, number, date, and URL helpers.
- `models.py`: `JobDict`, its `Place`, `make_job`, `make_places`, and `Stopped`.
- `fetchkit.py`: the `Fetcher` protocol, `FetchResult`, and `HttpxFetcher`.
- `cache.py`: one SQLite table of `JobDict` records keyed by site and ID, and the shared `CACHE`.
- `cli.py` builds `jobrake <site> <command>` from `SITES`, one command per function a site exports,
  and `io.py` renders JSON, JSONL, and CSV.
- `tests/`: offline, built on the stub fetcher in `tests/fakes.py`.
  `tests/fakesite.py` is a fake site the tests register.

A new site is a module under `sites/`, one entry in `SITES`, and its page, `docs/sites/<site>.md`,
which `tests/test_docs.py` requires. `scrape`, the CLI, and the contract test in
`tests/test_scrape.py` need no edit.

## Non-goals

- Filtering or choosing results locally, or translating an option from one site to another.
  jobrake returns what the site serves.
- Generic pacing or retries in `fetchkit`. A site adds only the pacing its server demands.
- A browser fetcher or any optional transport.
- Compatibility shims and deprecation aliases. A rename removes the old name.

## Decisions

- The design follows from the purpose. No caller's needs shape it.
- `site`: the unit jobrake reads, such as `linkedin` or `indeed`. It replaces "provider".
- `board`: the token, or for Workday the career site URL, that names one employer's board on an ATS
  site, such as `airbnb` on Greenhouse. Every ATS site declares it as a required `str` named
  `board`, with the short flag `-b`.
- `country`: a country's ISO 3166-1 alpha-2 code, in either case, such as `de`.
  A site that searches one country edition at a time takes it and maps it to the site's own code.
  It replaces country names and Indeed's codes.
- One record. Every site returns `JobDict` records with the same keys, types, and units.
  The identity keys `site`, `id`, and `url` and the summary keys `title`, `company`, `locations`,
  and `date` are always present. A detail key appears only when it has a value.
  Each site parses its own responses.
- A posting's places are `locations`, a list of `Place` in the site's order,
  `[]` when none was extracted. A `Place` has a `name`, the site's label or its parts joined,
  and only the parts the site gives for that place.
  `make_job` normalizes places with `make_places`, for every site and every cache read,
  and nothing is parsed out of a label. Two places are one only when they are equal once normalized.
  A site treats two of its entries as one place only when its response says so.
  Where one source's fields override another's, an empty `locations` overrides nothing.
- `site_data` holds fields only one site carries, under that site's own names, as JSON values.
  Each site's page lists its keys, and a key moves into `JobDict` once a second site shares its
  meaning.
- A site owns its options. `search` declares only the options its server applies, keyword-only,
  as `Annotated[T, "help"]` with `T` one of `str`, `int`, `bool`, `list[str]`, or `T | None`,
  and with defaults in the signature. A boolean option defaults to `False`.
  A name two sites share keeps one meaning and unit. Every function a site exports carries
  `@checked`, which raises `TypeError` for an unknown, missing, or wrongly typed argument and
  `ValueError` for a value out of range, a blank required string, or a blank list entry,
  all before the first request. A rule of the site's own on an option, such as Indeed's country
  editions or a `postings` reference its `card` must read, goes in the validator the function
  passes as `@checked(validator=_validate)`, so `check` raises everything the call would, without
  a request. The exception is a value only the site's live catalog can confirm, such as a UN
  Careers duty station, which `search` checks after reading that catalog. `site_options` rejects
  an annotation or a boolean default that breaks these rules when the module is imported, and
  `test_a_site_meets_the_site_contract` checks that `search` takes no positional option and that a
  shared name keeps its type.
- A caller can tell a cut-short result from a complete one. A failed request, an answer other than
  HTTP 200 among them, or a page that ends a search short of the total the site reported, raises
  `Stopped`, whose `partial` holds what was collected. A site's own result cap warns and returns,
  because a rerun meets it again.
  A details search that could not read every posting also puts the URLs of the unread ones in
  `failed`, so the site's `postings` can retry them even when a later search drops them.
  `postings` never raises `Stopped` and leaves a failed reference out of its result.
- A site whose search cards lack fields its posting endpoint serves takes `details` on `search` and
  exports `postings(fetcher, references)`, so a caller can fill cards in the same run or a later
  one. A reference is at least a record's `url`. `postings` keys its result by the references given
  and maps a posting the site reports gone to `None`.
  The posting outranks its card: with `details`, every field the posting has a value for replaces
  the card's, `date` and `locations` among them, and only `site`, `id`, and `url` stay the card's.
- The transport is the caller's. Code takes a `Fetcher` and leaves it open,
  and the caller that created it closes it. LinkedIn requests go through `paced_fetch`,
  which pins requests to LinkedIn's data centers in turn, paces them once per process,
  and retries a 429 up to five times. It follows redirects itself, to HTTPS LinkedIn addresses only,
  and paces each hop, so a caller's `Fetcher` must honor `follow_redirects=False`.
  Two workers per data center read posting pages, and concurrent calls each read their own.
- The cache is transparent. On LinkedIn, Workday, SmartRecruiters, StepStone, and INOMICS it
  stores the fields of each posting read as a `JobDict`. A reader sees only the posting's URL, so a
  later card merges with the cached fields as with a fresh read. Rows carry no version, and each
  row read passes through `make_job`, so a row it rejects is a miss, such as one whose keys no
  longer fit `JobDict` or `Place` or whose `applicants` is text.
  `make_job` normalizes a row as it does a site's fields and cannot redo a parser's work, so a
  parser fix reaches a cached posting when its row expires.
  `JOBRAKE_CACHE_PATH` and `JOBRAKE_CACHE_TTL` configure it, and no site function takes a cache
  option. Only LinkedIn and AcademicTransfer are paced.
- Library code logs under the `jobrake` logger and prints nothing. The CLI sends logs to stderr and
  data to stdout. It exits 2 for a bad argument, and 1 when a search or lookup raises `Stopped`,
  a named posting could not be fetched, or the output cannot be written. A stopped search and a
  postings fetch with a failed reference still write the postings they got.
  With none they write nothing, so an empty document comes only from a command that completed.
  A stderr that cannot be written, as when its reader closed the pipe, leaves the status as it was,
  and so does a closed stdout under `-h` or `--version`.
  Ctrl-C ends a command with one line and removes an output file the command started.
  The process then dies of SIGINT, so a shell reports 130 and stops a loop that ran it.

## Style

- Keep module docstrings to one-line orientation. Keep short docstrings on one line;
  longer ones open with a bare `"""` and put the summary on the next line.
  Put rationale and contracts on the symbol that owns them.
- Comments explain non-obvious mechanisms or reasons. User-facing messages state what happened,
  name the likely cause when known, and give a concrete next action.
- Treat style checks as heuristics, not bans. Preserve useful facts, concrete examples,
  and the author's voice. Use punctuation where it improves clarity.
- Wrap prose near 100 columns, at a sentence end or a clause boundary.
  A line may run to about 120 columns when that keeps a sentence whole or absorbs a short tail.
- Always write `jobrake` in lowercase.
- Inside `sites/`, prose uses each site's nouns: postings, cards, and fields.
  "Job" and "job dict" appear only where the package promises them, in `models`, `scrape`,
  and the README. Indeed's API says "job", so the word stays in its code.
- Describe detail fields as what we extract, when present, and avoid "the posting states".
  "Hydrate" stays in code docstrings, and the README says "fetch" or "fill".
- The tagline is one image with no feature list:
  "The job boards shed new postings every day. Bring a rake." It heads the README. The package and
  repository descriptions say what jobrake does.
- The README holds what a user needs to start: installation, a run with its real output, the
  options every site shares, the output formats and exit statuses, the sites, and the limits.
- `docs/guide.md` holds tasks that span sites, one section each. `docs/reference.md` holds the
  record, the fields by site, the commands, the Python API, and configuration, each stated once.
- `docs/sites/<site>.md` holds everything about one site, in the sections Options, Lookups,
  Fields, Limits, Terms, and Measured, in that order and only those it needs. A site's quirk lives
  on its page, and a rule every site shares lives in the reference, linked from the page.
- Keep CLI help terse. It comes from the `Annotated` help of each option and the first docstring
  line of each site and site function. Caveats and site quirks go on the site's page.
- The docs tell readers what they need to use jobrake. Leave out input normalization,
  request sizes, and other internals. A site's measured behavior goes in its page's Measured
  section, with when and on what it was measured.

## Sites

- Keep the sites symmetric, with the same names and units for the options they share,
  so shared code stays shared.
- Live requests to LinkedIn or Indeed spend the rate budget of my IP. Ask before sending any,
  and keep them few and paced. The test suite is offline.
- State site behavior that we measured as measured, and say in the docs when it is unreliable.

## Verify

- A change passes when `prek run --all-files` exits 0. It runs ruff check, ruff format, ty,
  and pytest from the locked environment. CI runs the same hooks, and so does every commit once
  `prek install` has run in the clone.
