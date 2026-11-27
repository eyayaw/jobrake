# jobrake reference

Each site's own options and fields are on its page under [sites](sites/).

- [The record](#the-record)
- [Fields by site](#fields-by-site)
- [Command line](#command-line)
- [Python API](#python-api)
- [Configuration](#configuration)

## The record

Every record is a dictionary, with three groups of keys.

- **Identity keys:** `site`, `id`, and `url`.
- **Summary keys:** `title`, `company`, `locations`, and `date`.
- **Detail keys:** included when a value is available.

Identity and summary keys are always present, using `None` when a summary value is unavailable and
`[]` when no locations were extracted. An empty `locations` list only means no place was extracted;
it does not imply the role is remote or has no location.

| Key | Type | Meaning |
| --- | --- | --- |
| `site` | string | The site's name, such as `linkedin` |
| `id` | string | The posting's ID on the site, unique together with `site` |
| `url` | string | The posting's page |
| `title` | string or `None` | The job title |
| `company` | string or `None` | The employer's name |
| `locations` | list of places | The posting's places, in the site's order |
| `date` | string or `None` | The calendar date the site gives the posting, as `YYYY-MM-DD` |
| `description` | string | The posting's text without its HTML, one line per block |
| `language` | string | The posting's language as the site codes it, such as `en` or `zh-CN` |
| `company_url` | string | The employer's page on the site |
| `company_logo` | string | The address of the employer's logo |
| `department` | string | The hiring unit within the employer, as the site names it |
| `team` | string | The posting's team within that unit |
| `employment_type` | string | The site's label as a snake_case slug, such as `full_time`, `part_time`, `contract`, or `internship` |
| `workplace_type` | string | `remote`, `hybrid`, or `on_site` |
| `salary_min`, `salary_max` | number | The bounds of the salary range, in `salary_currency` per `salary_period` |
| `salary_currency` | string | The currency code the site gives, such as `USD` |
| `salary_period` | string | The time unit the amounts cover, such as `YEAR` or `HOUR` |
| `posted_at` | string | When the posting was published or created, as an ISO 8601 timestamp, or as a calendar date where the site gives no time |
| `expires_at` | string | The posting's closing time or application deadline, in the same two forms |
| `apply_url` | string | The application form or link |
| `apply_type` | string | LinkedIn's apply kind as its page names it: `onsite` for its own application form, `offsite` for the employer's |
| `applicants` | integer | The applicant count LinkedIn's page shows |
| `experience_months` | integer | The experience the posting asks for, in whole months |
| `education` | string | The credential the posting asks for, as the site words it |
| `keywords` | list of strings | The terms the employer tagged the posting with, in the site's order |
| `site_data` | object | Site-specific fields under the site's own names |

The keys from `description` down are detail keys. They are omitted when the site doesn't publish a
value, or on `--details` sites when the posting page wasn't fetched.
`employment_type` slugifies the site's label, normalizing `contractor` to `contract` and `intern`
to `internship`. Indeed uses a fixed set of six labels, while other boards are free-form (for
example, Spotify's Lever board labels roles `permanent`).
Ashby and LinkedIn's page markup report `salary_period` as `HOUR`, `DAY`, `WEEK`, `MONTH`, or
`YEAR`; Indeed and LinkedIn's structured data pass through as sent.
`workplace_type` is only set when explicitly stated by the site, so omitting it means unknown rather
than on-site.

`site_data` stores fields unique to one site (such as EconJobMarket's `position_types`), listed on
each site's page. Whenever a second site shares the same concept, that field gets promoted to a
top-level key.

### Places

Each entry in `locations` has a `name` (the site's label, or its parts joined if there is no label)
and includes `city`, `region`, `country_code`, `latitude`, and `longitude` only when the site
provides them.
`country_code` is an ISO 3166-1 alpha-2 code (such as `US`); alpha-3 codes are converted to
alpha-2, and non-codes like country names are omitted.
jobrake never guesses structured fields from free text, so a label like `Seattle, WA` won't set
`city` unless the site supplied it separately. Exact duplicate places are deduplicated, while
places sharing a name with different fields (like `Remote` in two countries) stay separate.

### Dates

Postings can have two date fields: `date` for the calendar date (`2026-09-19`) and `posted_at` for
the full timestamp when available (`2026-09-19T05:00:00+00:00`), or the calendar date otherwise.
Usually `date` comes from the search result, falling back to the calendar part of `posted_at`.
On Adzuna, LinkedIn, Workday, StepStone, and INOMICS with `--details`, `date` is updated to the
calendar date of the posting page's `posted_at` (keeping the search result's date if the page has
none).
Use `date` for day-level filtering and `posted_at` when you need a time of day.
Site-specific date formats (like Lever's epoch milliseconds or INOMICS's day-first dates) are
converted to ISO 8601; unparseable values are dropped with a warning (`date` falls back to
`posted_at` or `None`, and `posted_at`/`expires_at` are omitted).

## Fields by site

Which sites fill each detail key, and whether a search fills it or only `--details` does:

| Key | From a search | Only with `--details` |
| --- | --- | --- |
| `description` | [AcademicTransfer](sites/academictransfer.md), [AEA JOE](sites/aea.md), [Ashby](sites/ashby.md), [Cornerstone](sites/cornerstone.md), [EconJobMarket](sites/econjobmarket.md), [Greenhouse](sites/greenhouse.md), [Indeed](sites/indeed.md), [Lever](sites/lever.md), [Personio](sites/personio.md), [ReliefWeb](sites/reliefweb.md), [UN Careers](sites/uncareers.md), [Workable](sites/workable.md) | [Adzuna](sites/adzuna.md), [INOMICS](sites/inomics.md), [LinkedIn](sites/linkedin.md), [SmartRecruiters](sites/smartrecruiters.md), [StepStone](sites/stepstone.md), [Workday](sites/workday.md), [XING](sites/xing.md) |
| `language` | [AcademicTransfer](sites/academictransfer.md), [Greenhouse](sites/greenhouse.md), [Indeed](sites/indeed.md), [SmartRecruiters](sites/smartrecruiters.md), [StepStone](sites/stepstone.md), [XING](sites/xing.md) | — |
| `company_url` | [Indeed](sites/indeed.md), [ReliefWeb](sites/reliefweb.md), [XING](sites/xing.md) | [LinkedIn](sites/linkedin.md), [StepStone](sites/stepstone.md) |
| `company_logo` | [EconJobMarket](sites/econjobmarket.md), [Indeed](sites/indeed.md), [StepStone](sites/stepstone.md), [XING](sites/xing.md) | [LinkedIn](sites/linkedin.md) |
| `department` | [AcademicTransfer](sites/academictransfer.md), [AEA JOE](sites/aea.md), [Ashby](sites/ashby.md), [EconJobMarket](sites/econjobmarket.md), [Greenhouse](sites/greenhouse.md), [Lever](sites/lever.md), [Personio](sites/personio.md), [SmartRecruiters](sites/smartrecruiters.md), [Workable](sites/workable.md) | — |
| `team` | [Ashby](sites/ashby.md), [Lever](sites/lever.md) | — |
| `employment_type` | [AcademicTransfer](sites/academictransfer.md), [Adzuna](sites/adzuna.md), [Ashby](sites/ashby.md), [Indeed](sites/indeed.md), [Lever](sites/lever.md), [Personio](sites/personio.md), [ReliefWeb](sites/reliefweb.md), [SmartRecruiters](sites/smartrecruiters.md), [Workable](sites/workable.md), [XING](sites/xing.md) | [LinkedIn](sites/linkedin.md), [StepStone](sites/stepstone.md), [Workday](sites/workday.md) |
| `workplace_type` | [Ashby](sites/ashby.md), [Indeed](sites/indeed.md), [INOMICS](sites/inomics.md), [Lever](sites/lever.md), [SmartRecruiters](sites/smartrecruiters.md), [Workable](sites/workable.md), [XING](sites/xing.md) | — |
| `salary_min`, `salary_max`, `salary_currency`, `salary_period` | [AcademicTransfer](sites/academictransfer.md), [Ashby](sites/ashby.md), [Indeed](sites/indeed.md), [Personio](sites/personio.md), [XING](sites/xing.md) | [Adzuna](sites/adzuna.md), [LinkedIn](sites/linkedin.md) |
| `posted_at` | [AcademicTransfer](sites/academictransfer.md), [AEA JOE](sites/aea.md), [Ashby](sites/ashby.md), [Cornerstone](sites/cornerstone.md), [EconJobMarket](sites/econjobmarket.md), [Greenhouse](sites/greenhouse.md), [Indeed](sites/indeed.md), [INOMICS](sites/inomics.md), [Lever](sites/lever.md), [Personio](sites/personio.md), [ReliefWeb](sites/reliefweb.md), [SmartRecruiters](sites/smartrecruiters.md), [StepStone](sites/stepstone.md), [UN Careers](sites/uncareers.md), [Workable](sites/workable.md), [XING](sites/xing.md) | [Adzuna](sites/adzuna.md), [LinkedIn](sites/linkedin.md), [Workday](sites/workday.md) |
| `expires_at` | [AcademicTransfer](sites/academictransfer.md), [AEA JOE](sites/aea.md), [Cornerstone](sites/cornerstone.md), [EconJobMarket](sites/econjobmarket.md), [Greenhouse](sites/greenhouse.md), [Indeed](sites/indeed.md), [ReliefWeb](sites/reliefweb.md), [StepStone](sites/stepstone.md), [UN Careers](sites/uncareers.md), [XING](sites/xing.md) | [Adzuna](sites/adzuna.md), [INOMICS](sites/inomics.md), [LinkedIn](sites/linkedin.md) |
| `apply_url` | [AcademicTransfer](sites/academictransfer.md), [Ashby](sites/ashby.md), [Indeed](sites/indeed.md), [Lever](sites/lever.md), [Workable](sites/workable.md), [XING](sites/xing.md) | [Adzuna](sites/adzuna.md), [SmartRecruiters](sites/smartrecruiters.md) |
| `apply_type`, `applicants`, `experience_months` | — | [LinkedIn](sites/linkedin.md) |
| `education` | [AcademicTransfer](sites/academictransfer.md), [Workable](sites/workable.md) | [LinkedIn](sites/linkedin.md) |
| `keywords` | [AcademicTransfer](sites/academictransfer.md), [AEA JOE](sites/aea.md), [Personio](sites/personio.md) | — |
| `site_data` | [AcademicTransfer](sites/academictransfer.md), [Adzuna](sites/adzuna.md), [AEA JOE](sites/aea.md), [Ashby](sites/ashby.md), [EconJobMarket](sites/econjobmarket.md), [INOMICS](sites/inomics.md), [Personio](sites/personio.md), [ReliefWeb](sites/reliefweb.md), [StepStone](sites/stepstone.md), [UN Careers](sites/uncareers.md), [XING](sites/xing.md) | [LinkedIn](sites/linkedin.md) |

## Command line

The options several sites share and the output formats are in the [README](../README.md#cli).

| Site                                                     | Commands                                          |
| -------------------------------------------------------- | ------------------------------------------------- |
| [`indeed`](sites/indeed.md)                              | `search`, `places`, `companies`, `attributes`     |
| [`linkedin`](sites/linkedin.md)                          | `search`, `postings`, `places`, `companies`       |
| [`inomics`](sites/inomics.md), [`smartrecruiters`](sites/smartrecruiters.md), [`stepstone`](sites/stepstone.md), [`workday`](sites/workday.md), [`xing`](sites/xing.md) | `search`, `postings` |
| [`uncareers`](sites/uncareers.md)                        | `search`, `filters`                               |
| every other site                                         | `search`                                          |

### Options

Each site exposes only the filters its backend actually supports. Unset options and empty lists are
omitted from requests. List options accept multiple values after a single flag
(`--attributes CF3CP 6QC5F`) or repeated flags.
Multiple options combine with AND. Within a single list option, values combine with OR, except on
Indeed's `--attributes`, where a posting must match every code listed.
Options with a fixed set of allowed values (like AEA JOE's `--section`) are validated locally before
sending any request. Filters apply server-side alongside query and location, before `--results`
limits the count.

### Lookups

The `places`, `companies`, `attributes`, and `filters` commands print an indented JSON list of
`{"id", "name"}` entries, and their library functions return the same list.
Each `id` is the value a search takes.
A lookup takes no `--output` or `--format`, so redirect stdout to save one.
A failed request or unreadable response raises `Stopped` in a library call, and the CLI exits 1.

| Command                                       | Library function                                               |
| --------------------------------------------- | -------------------------------------------------------------- |
| `jobrake indeed places <name> -c <code>`      | `jobrake.sites.indeed.places(fetcher, name, country=...)`      |
| `jobrake indeed companies <name> -c <code>`   | `jobrake.sites.indeed.companies(fetcher, name, country=...)`   |
| `jobrake indeed attributes <query> -c <code>` | `jobrake.sites.indeed.attributes(fetcher, query, country=...)` |
| `jobrake linkedin places <name>`              | `jobrake.sites.linkedin.places(fetcher, name)`                 |
| `jobrake linkedin companies <name>`           | `jobrake.sites.linkedin.companies(fetcher, name)`              |
| `jobrake uncareers filters <option>`          | `jobrake.sites.uncareers.filters(fetcher, option)`             |

### Postings

`jobrake <site> postings <reference>...` fetches the postings you name.
A reference is a search result's `url` or another address of the posting:

| Site                     | Other references                                                                  |
| ------------------------ | --------------------------------------------------------------------------------- |
| LinkedIn                 | a numeric posting ID, an HTTPS posting URL such as a job alert email's link, or a search page address with `currentJobId=` |
| StepStone                | `stepstone.de/job/<id>`, or the longer address that ends in `--<id>-inline.html`  |
| SmartRecruiters, INOMICS | the posting's address with its title slug                                         |
| Workday                  | the posting's address copied from the browser                                     |
| XING                     | the posting's address under `xing.com/jobs/<slug>-<id>`                           |

Any unrecognized reference raises an error before any request is sent.
Results keep the input order and include the same fields as `--details`, except for fields that
exist only on search results (such as StepStone's `site_data`). Duplicate references to the same
posting return one record, and `--output`/`--format` work the same as in `search`.
Gone or unreachable postings are logged to stderr and omitted from output; if any posting was
unreachable, the command writes the rest and exits 1.
During a `--details` search, a gone posting simply keeps its search summary and does not count as
a failure.

### Exit statuses

| Exit status | When                                                                                      |
| ----------- | ----------------------------------------------------------------------------------------- |
| 0           | The command completed, including a search that found nothing                              |
| 1           | A request failed or a search ended short, a named posting could not be fetched, or the output could not be written |
| 2           | An argument is wrong, a site refuses its value, or the `--output` path cannot be used     |
| 130         | Ctrl-C ended the command                                                                  |

When a `search` or `postings` command exits 1, it still writes whatever postings it collected and
logs the failure to stderr. If it collected nothing, it writes nothing. An empty JSON array (`[]`)
or CSV header therefore always means the command completed normally (for JSONL, check the exit
status). Logs and progress go to stderr; data goes to stdout.

A completed search with zero matches writes no `--output` file; on stdout it writes `[]` for JSON,
just the header row for CSV, and nothing for JSONL. If writing a file fails or is interrupted
midway, jobrake removes the partial file so you can safely rerun the command.

## Python API

```text
import jobrake

await jobrake.scrape(site, *, fetcher=None, **options)  # -> list[JobDict]
jobrake.check(site, **options)  # -> None, or the TypeError or ValueError scrape would raise
jobrake.identify(link)  # -> (site, id) or None
```

`jobrake.JobDict` and `jobrake.Place` are the `TypedDict`s of a record and a place.

`scrape` accepts a site's `search` options as keyword arguments (using underscores instead of CLI
hyphens, like `max_age_hours`) and validates them before making any requests. Unknown, missing, or
mistyped options raise `TypeError`; unknown sites, out-of-range numbers, blank required strings, or
values rejected by the site raise `ValueError`. If you omit `fetcher`, `scrape` creates and closes
its own `HttpxFetcher`.

`check` validates the same arguments offline (without `fetcher` or an event loop). Values that can
only be checked against a site's live filter list, such as a UN Careers duty station, pass `check`
and fail during the search instead:

```python
jobrake.check("uncareers", duty_station=["Genva"])  # passes, and the search raises ValueError
```

`identify` parses a posting URL offline and returns the `(site, id)` pair that a search would
produce. It recognizes the URLs accepted by `postings`, Adzuna posting links, and Indeed links with
a `jk` or `vjk` parameter. Everything else (including bare LinkedIn IDs and Greenhouse URLs)
returns `None`.

```python
jobrake.identify("https://nl.indeed.com/viewjob?jk=1a2b3c4d5e6f7a8b")
# ('indeed', '1a2b3c4d5e6f7a8b')
```

### Site functions

`jobrake.sites.SITES` maps each site name to its module. Each module exports `search` plus any
additional command functions (`postings` or [lookups](#lookups)), all taking a `Fetcher` first:
`search(fetcher, **options)` and `postings(fetcher, references)`. Every exported function also
exposes `.check(**options)` for offline validation, e.g. `stepstone.postings.check(references=urls)`.

`postings` never raises `Stopped`. It maps each reference to its record, or `None` if the site
reports the posting gone. Any reference that failed to fetch or parse is omitted from the returned
dict, so calling `postings` again retries it.

### Stopped

`jobrake.Stopped` is raised when a request fails, a site returns a non-200 status, or pagination
returns an empty page before reaching the reported total. `stop.partial` contains the `JobDict`
records collected so far (`[]` if none). Pagination can come up short if postings close mid-search,
so rerunning may recover skipped listings.

In a `--details` search, jobrake still tries to fetch all remaining postings before raising
`Stopped`: `stop.partial` contains every search result (filled where fetches succeeded), and
`stop.failed` lists the URLs that couldn't be read so you can pass them to `<site>.postings`.
Adzuna has no `postings` command and leaves `stop.failed` empty; rerun the search instead.
On LinkedIn, a rate limit that outlasts retries stops fetching early and puts all remaining unread
URLs in `stop.failed`.

Hitting a site's own result cap is not an error; jobrake logs a warning and returns what the site
served. Across all sites, unreadable individual postings are skipped and unreadable fields are
omitted.

### Fetchers

`jobrake.HttpxFetcher(timeout=30.0, *, headers=None)` is the HTTP client jobrake uses by default.
`timeout` is the limit on each network operation, in seconds. `headers` override its browser-like
defaults.
Use it as an async context manager to share one connection pool across calls.
A fetcher you supply is yours to close.

To use another HTTP client, implement the `Fetcher` protocol from `jobrake.fetchkit`:
an async `fetch(url, *, headers=None, json=None, follow_redirects=True)`
that sends a POST when `json` is given.
With `follow_redirects=False`, return the first response,
including its `Location` header. LinkedIn uses this to pace each redirect hop.
`fetch` returns a `FetchResult`:

| Field     | Value                                                   |
| --------- | ------------------------------------------------------- |
| `url`     | the final URL                                           |
| `status`  | the HTTP status, or `None` when no response arrived     |
| `text`    | the body                                                |
| `headers` | the response headers, with lowercased names             |
| `error`   | a message for a failed request, or `None`               |

A status of 400 or more sets `error` on its own,
and jobrake reads a response as data only when its `status` is 200.
An exception your own `Fetcher` raises propagates out of `scrape()`.

### Logging

Library calls log under the `jobrake` logger and print nothing, and your application sets its level
and handlers. While a paged search reads its pages, and while it fetches posting details,
jobrake logs INFO records whose `progress` attribute holds `(done, total)`.
For a handler that draws them, see the [guide](guide.md#show-progress).

## Configuration

jobrake keeps the Adzuna, LinkedIn, Workday, SmartRecruiters, StepStone, INOMICS, and XING
postings it fetched in one SQLite file, `jobrake.sqlite3`, under your user cache directory:
`~/Library/Caches/jobrake/` on macOS, `$XDG_CACHE_HOME/jobrake/` on Linux
(`~/.cache/jobrake/` when that variable is unset), and `%LOCALAPPDATA%\jobrake\` on Windows.
No other site is cached.

| Variable             | Default             | Effect                                                 |
| -------------------- | ------------------- | ------------------------------------------------------ |
| `JOBRAKE_CACHE_PATH` | platform user cache | Path to the SQLite file, with home-directory expansion |
| `JOBRAKE_CACHE_TTL`  | 604800              | Seconds a cached posting is served before a refetch    |

The lifetime must be a positive number of seconds; invalid values log a warning and fall back to
the default.

Postings reported as gone are not cached. Upgrading jobrake preserves the existing cache: cached
entries keep the fields extracted by the older version until they expire, unless a cached entry no
longer matches the current schema (in which case it is treated as a miss and refetched).

If the cache file fails to open or write, jobrake disables caching with a warning and continues
normally. If another process holds the SQLite file locked, jobrake pauses cache use for a minute
with a warning before trying again.

`JOBRAKE_RELIEFWEB_APPNAME` holds the appname approved for you by ReliefWeb. Every `reliefweb`
search requires it and there is no default ([how to request one](sites/reliefweb.md)).
