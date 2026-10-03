# jobrake agent instructions

jobrake is an async Python package and CLI that fetches job postings from
LinkedIn's guest API and Indeed's GraphQL API. It depends on `httpx` and `bs4`.

## Architecture

### Public API

- `jobrake.scrape(site, *, query, ...)` runs one search and returns a list of
  job dictionaries. `jobrake.sites.<provider>.search(fetcher, ...)` is the same
  search with a fetcher the caller supplies.
- The lookups turn names into provider IDs: `places` and `companies` on both
  providers and `attributes` on Indeed. Each returns a list, `[]` for no match,
  and `None` after a failed request. `linkedin.resolve_geoid` returns one geoId
  or `None`.
- `linkedin.fetch_postings(fetcher, urls)` maps URLs to detail fields, and
  `linkedin.fetch_details(fetcher, references)` builds whole jobs from IDs or
  URLs.
- The CLI mirrors the library: `jobrake linkedin` and `jobrake indeed` search,
  `jobrake details linkedin` fetches known postings, and `jobrake places`,
  `companies`, and `attributes` run the lookups.

### Design

- A job is a flat dictionary. The identity keys `site`, `id`, and `url` and the
  summary keys `title`, `company`, `location`, and `date` are always present.
  A detail key appears only when it has a value.
- Each provider parses its own responses into the shared `Job` fields.
- `scrape` only routes. It checks the site name, creates and closes the default
  `HttpxFetcher`, and forwards every option. Each provider's `search` validates
  the arguments it applies and warns for a filter it ignores.
- Invalid arguments raise `TypeError` or `ValueError` before any request.
- A failed request logs a warning, and the search returns the jobs collected
  so far. A short result is normal.
- The transport is injected. Code takes a `Fetcher` and leaves it open, and
  the caller that created it closes it. Indeed needs `PostFetcher` for `post()`.
- LinkedIn requests go through `paced_fetch`, which shares one token bucket
  per process and retries a 429 once. Posting fields, posting addresses, and
  place resolutions are cached in one SQLite file, configured by the
  `JOBRAKE_CACHE_*` environment variables. Indeed is neither paced nor cached.
- Library code logs under the `jobrake` logger and prints nothing. The CLI
  sends logs to stderr and data to stdout. It exits 2 for a bad argument, and
  1 when a lookup fails, no named posting could be fetched, or the output
  cannot be written.

### Layout

- `sites/__init__.py`: `scrape` and `site_searchers()`.
- `sites/<provider>/`: `search.py` builds requests and parses results,
  `client.py` holds URLs, headers, and pacing, and `geo.py`, `companies.py`,
  and Indeed's `attributes.py` hold the lookups. LinkedIn's `postings.py`
  fetches posting details.
- `utils.py`: the argument checks and `_FILTERS`, the table that maps each
  search filter to the provider that applies it.
- `models.py`: `Job` and `make_job`, which builds the public job dictionary.
- `defaults.py`: the defaults shared by the library and the CLI.
- `fetchkit/`: the `Fetcher` protocols, `HttpxFetcher`, and the token bucket.
- `cache.py`: one separately versioned table per kind of value. Bump a table's
  version when its fields or parsing change.
- `cli.py` builds the subcommands, and `io.py` renders JSON, JSONL, and CSV.
- `tests/`: offline, built on the stub fetcher in `tests/fakes.py`.

A new provider touches `site_searchers()` in `sites/__init__.py`, `_FILTERS`
in `utils.py`, and `_SITE_ARGS` and `_SITE_LABELS` in `cli.py`.

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
- Keep the README as a short landing page. Put detailed usage, output, and
  provider-specific behavior in `docs/guide.md`.
- Keep CLI help terse. Caveats and provider quirks go in the guide.
- The guide tells readers what they need to use jobrake. Leave out input
  normalization, request sizes, and other internals.

## Providers

- Keep the providers symmetric, with the same options, names, and units, so
  shared code stays shared.
- Live requests to LinkedIn or Indeed spend the rate budget of my IP. Ask
  before sending any, and keep them few and paced. The test suite is offline.
- State provider behavior that we measured as measured, and say in the guide
  when it is unreliable.

## Checks

- A change passes when these exit 0: `uv run -m pytest tests/ -q`,
  `uv run ruff check`, `uv run ruff format --check`, and `uv run ty check`.

## Changelog

- Use `[version] (date)`, an `Unreleased` section, and the standard change
  categories. Treat released entries as historical records; correct errors
  without broadly restyling their prose.
- Keep `Unreleased` changelog edits uncommitted until release.
- Write release notes for people. Lead with what changed and why it matters.
  Include only the details needed to understand the release.
- Prefix an entry that breaks existing callers with `**Breaking:**` and list
  it first under Changed.
- A release is one commit, `chore: bump version to X.Y.Z`, with `CHANGELOG.md`,
  the version in `pyproject.toml`, and `uv.lock`, plus an annotated tag
  `vX.Y.Z`. Dependency bumps get their own `chore` commit before it.
