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

Identity and summary keys are always present, with `None` for an unavailable summary value
and `[]` when jobrake found no place.
An empty `locations` says only that jobrake extracted no place.
It does not say the posting has no place, nor that it is remote.

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
| `site_data` | object | Fields only this site carries, under the site's own names |

The keys from `description` down are the detail keys.
A detail key is absent when the site omits or does not publish the value,
or when jobrake did not fetch the posting page.
`employment_type` is a slug of the label the site sends,
with `contractor` and `intern` read as `contract` and `internship`.
Indeed sends one of six labels, and elsewhere the values form no fixed list:
Spotify's board on Lever labels its postings `permanent`.
Ashby gives `salary_period` as `HOUR`, `DAY`, `WEEK`, `MONTH`, or `YEAR`,
and so does LinkedIn's page markup.
Indeed's value and the one in LinkedIn's structured data pass through as sent.
`workplace_type` appears only when the site states it,
so an absent one leaves the workplace unknown and does not mean on-site.

`site_data` holds, for example, EconJobMarket's `position_types`.
Its keys depend on `site`, and each site's page lists them.
A key that a second site comes to share with the same meaning moves into the record.

### Places

Each place in `locations` has a `name`, the site's label for it or its parts joined
when the site gives no label,
and carries `city`, `region`, `country_code`, `latitude`, and `longitude` only
when the site gives them for that place.
`country_code` is an ISO 3166-1 alpha-2 code, such as `US`. jobrake converts a site's alpha-3 code
to alpha-2, and leaves the key out when the site gives no code or something else, such as a
country name.
jobrake parses nothing out of a place's name, so a place named `Seattle, WA` carries no `city`
unless the site sent one. A place the site lists twice with the same parts appears once.
Places that share a name but differ in any part, such as `Remote` in two countries, each appear.

### Dates

A posting can carry two dates. `date` holds the calendar date, such as `2026-09-19`,
and `posted_at` holds the full timestamp when the site gives one,
such as `2026-09-19T05:00:00+00:00`, and the calendar date otherwise.
jobrake prefers the date a search result states and falls back to the calendar portion
of `posted_at`.
The exceptions are LinkedIn, Workday, StepStone, and INOMICS with `--details`, where `date` is the
calendar date of the `posted_at` that the posting page gives.
A page without one leaves the search result's date.
Compare on `date`, and read `posted_at` for a time of day.
jobrake converts a site's own form, such as Lever's epoch milliseconds or INOMICS's day-first
dates, to ISO 8601. Any other value is dropped with a warning:
`date` falls back to `posted_at` or becomes `None`, and `posted_at` or `expires_at` is left out.

## Fields by site

Which sites fill each detail key, and whether a search fills it or only `--details` does:

| Key | From a search | Only with `--details` |
| --- | --- | --- |
| `description` | [AcademicTransfer](sites/academictransfer.md), [AEA JOE](sites/aea.md), [Ashby](sites/ashby.md), [EconJobMarket](sites/econjobmarket.md), [Greenhouse](sites/greenhouse.md), [Indeed](sites/indeed.md), [Lever](sites/lever.md), [Personio](sites/personio.md), [ReliefWeb](sites/reliefweb.md), [UN Careers](sites/uncareers.md), [Workable](sites/workable.md) | [INOMICS](sites/inomics.md), [LinkedIn](sites/linkedin.md), [SmartRecruiters](sites/smartrecruiters.md), [StepStone](sites/stepstone.md), [Workday](sites/workday.md) |
| `language` | [AcademicTransfer](sites/academictransfer.md), [Greenhouse](sites/greenhouse.md), [Indeed](sites/indeed.md), [SmartRecruiters](sites/smartrecruiters.md), [StepStone](sites/stepstone.md) | — |
| `company_url` | [Indeed](sites/indeed.md), [ReliefWeb](sites/reliefweb.md) | [LinkedIn](sites/linkedin.md), [StepStone](sites/stepstone.md) |
| `company_logo` | [EconJobMarket](sites/econjobmarket.md), [Indeed](sites/indeed.md), [StepStone](sites/stepstone.md) | [LinkedIn](sites/linkedin.md) |
| `department` | [AcademicTransfer](sites/academictransfer.md), [AEA JOE](sites/aea.md), [Ashby](sites/ashby.md), [EconJobMarket](sites/econjobmarket.md), [Greenhouse](sites/greenhouse.md), [Lever](sites/lever.md), [Personio](sites/personio.md), [SmartRecruiters](sites/smartrecruiters.md), [Workable](sites/workable.md) | — |
| `team` | [Ashby](sites/ashby.md), [Lever](sites/lever.md) | — |
| `employment_type` | [AcademicTransfer](sites/academictransfer.md), [Ashby](sites/ashby.md), [Indeed](sites/indeed.md), [Lever](sites/lever.md), [Personio](sites/personio.md), [ReliefWeb](sites/reliefweb.md), [SmartRecruiters](sites/smartrecruiters.md), [Workable](sites/workable.md) | [LinkedIn](sites/linkedin.md), [StepStone](sites/stepstone.md), [Workday](sites/workday.md) |
| `workplace_type` | [Ashby](sites/ashby.md), [Indeed](sites/indeed.md), [INOMICS](sites/inomics.md), [Lever](sites/lever.md), [SmartRecruiters](sites/smartrecruiters.md), [Workable](sites/workable.md) | — |
| `salary_min`, `salary_max`, `salary_currency`, `salary_period` | [AcademicTransfer](sites/academictransfer.md), [Ashby](sites/ashby.md), [Indeed](sites/indeed.md), [Personio](sites/personio.md) | [LinkedIn](sites/linkedin.md) |
| `posted_at` | [AcademicTransfer](sites/academictransfer.md), [AEA JOE](sites/aea.md), [Ashby](sites/ashby.md), [EconJobMarket](sites/econjobmarket.md), [Greenhouse](sites/greenhouse.md), [Indeed](sites/indeed.md), [INOMICS](sites/inomics.md), [Lever](sites/lever.md), [Personio](sites/personio.md), [ReliefWeb](sites/reliefweb.md), [SmartRecruiters](sites/smartrecruiters.md), [StepStone](sites/stepstone.md), [UN Careers](sites/uncareers.md), [Workable](sites/workable.md) | [LinkedIn](sites/linkedin.md), [Workday](sites/workday.md) |
| `expires_at` | [AcademicTransfer](sites/academictransfer.md), [AEA JOE](sites/aea.md), [EconJobMarket](sites/econjobmarket.md), [Greenhouse](sites/greenhouse.md), [Indeed](sites/indeed.md), [ReliefWeb](sites/reliefweb.md), [StepStone](sites/stepstone.md), [UN Careers](sites/uncareers.md) | [INOMICS](sites/inomics.md), [LinkedIn](sites/linkedin.md) |
| `apply_url` | [AcademicTransfer](sites/academictransfer.md), [Ashby](sites/ashby.md), [Indeed](sites/indeed.md), [Lever](sites/lever.md), [Workable](sites/workable.md) | [SmartRecruiters](sites/smartrecruiters.md) |
| `apply_type`, `applicants`, `experience_months` | — | [LinkedIn](sites/linkedin.md) |
| `education` | [AcademicTransfer](sites/academictransfer.md), [Workable](sites/workable.md) | [LinkedIn](sites/linkedin.md) |
| `keywords` | [AcademicTransfer](sites/academictransfer.md), [AEA JOE](sites/aea.md), [Personio](sites/personio.md) | — |
| `site_data` | [AcademicTransfer](sites/academictransfer.md), [AEA JOE](sites/aea.md), [Ashby](sites/ashby.md), [EconJobMarket](sites/econjobmarket.md), [INOMICS](sites/inomics.md), [Personio](sites/personio.md), [ReliefWeb](sites/reliefweb.md), [StepStone](sites/stepstone.md), [UN Careers](sites/uncareers.md) | [LinkedIn](sites/linkedin.md) |

## Command line

The options several sites share and the output formats are in the [README](../README.md#cli).

| Site                                                     | Commands                                          |
| -------------------------------------------------------- | ------------------------------------------------- |
| [`indeed`](sites/indeed.md)                              | `search`, `places`, `companies`, `attributes`     |
| [`linkedin`](sites/linkedin.md)                          | `search`, `postings`, `places`, `companies`       |
| [`inomics`](sites/inomics.md), [`smartrecruiters`](sites/smartrecruiters.md), [`stepstone`](sites/stepstone.md), [`workday`](sites/workday.md) | `search`, `postings` |
| [`uncareers`](sites/uncareers.md)                        | `search`, `filters`                               |
| every other site                                         | `search`                                          |

### Options

Each site takes only the filters it applies.
An option left at its unset value, or an empty list, stays out of the search.
A list option takes several values after one flag, `--attributes CF3CP 6QC5F`, or across repeats.
A posting must match every option given. Within one list option, a posting needs to match only
one value, except for Indeed's `--attributes`, where it must carry every code.
An option with a fixed list of values, such as AEA JOE's `--section`, rejects any other value
before any request.
Filters apply alongside keywords and geography, before the result limit.

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

Any other reference is an error, and nothing is fetched.
Results follow the order given and have the fields of a search with `--details`, except a field only
the search result carries, such as StepStone's `site_data`.
Several references to one posting return one record.
The command takes the same `--output` and `--format` as a search.
A posting that is gone or unreachable is reported on stderr and left out, and when one was
unreachable, the command writes the others and exits 1.
In a search with `--details`, a gone posting keeps its search result instead, without details,
and does not count as a failure.

### Exit statuses

| Exit status | When                                                                                      |
| ----------- | ----------------------------------------------------------------------------------------- |
| 0           | The command completed, including a search that found nothing                              |
| 1           | A request failed or a search ended short, a named posting could not be fetched, or the output could not be written |
| 2           | An argument is wrong, a site refuses its value, or the `--output` path cannot be used     |
| 130         | Ctrl-C ended the command                                                                  |

A search or `postings` command that exits 1 still writes the postings it got, and stderr says
what failed. With none it writes nothing, so empty output always comes from a command that
completed. Logs and progress go to stderr, and the records to stdout.

A search that finds nothing writes no file, and on stdout it writes `[]` in JSON, the header row
in CSV, and nothing in JSONL.
A write that fails or is interrupted partway removes the file it started, so a rerun can write it.

## Python API

```text
import jobrake

await jobrake.scrape(site, *, fetcher=None, **options)  # -> list[JobDict]
jobrake.check(site, **options)  # -> None, or the TypeError or ValueError scrape would raise
jobrake.identify(link)  # -> (site, id) or None
```

`jobrake.JobDict` and `jobrake.Place` are the `TypedDict`s of a record and a place.

`scrape` takes a site's `search` options as keyword arguments, named as the CLI's long options
with underscores, such as `max_age_hours`.
It checks them before any request. An unknown, missing, or wrongly typed option raises
`TypeError`, and an unknown site, a value out of range, a blank required string, or a value the
site refuses raises `ValueError`.
Without `fetcher`, it creates and closes an `HttpxFetcher` of its own.

`check` takes the same arguments as `scrape` without `fetcher` and sends no request.
A value that only the site's live list can confirm, such as a UN Careers duty station,
passes `check`, and the search refuses it after reading that list:

```python
jobrake.check("uncareers", duty_station=["Genva"])  # passes, and the search raises ValueError
```

`identify` reads a posting's link and returns the `site` and `id` a search gives that posting.
It sends no request. It reads the posting URLs that `postings` takes, and Indeed links that carry
the key in `jk`, or in `vjk` on a search page.
Any other link, including a bare LinkedIn ID or a Greenhouse posting, gives `None`.

```python
jobrake.identify("https://nl.indeed.com/viewjob?jk=1a2b3c4d5e6f7a8b")
# ('indeed', '1a2b3c4d5e6f7a8b')
```

### Site functions

`jobrake.sites.SITES` maps each site name to its module.
Each site module exports `search` and the functions behind its other commands,
and each takes a `Fetcher` first: `search(fetcher, **options)`,
`postings(fetcher, references)`, and the lookups listed under [Lookups](#lookups).
Each also has a `.check(**options)` that raises what the call would and sends no request,
as in `stepstone.postings.check(references=urls)`.

`postings` never raises `Stopped`. It maps each reference to its whole record,
or to `None` when the site reports the posting gone.
A reference whose request failed, or whose response jobrake cannot read, is absent from the result,
and calling the function again retries it.

### Stopped

A failed request, an answer other than HTTP 200, or a page that ends a search short of the total
the site reported raises `jobrake.Stopped`.
Its `partial`, a list of `JobDict`, holds the postings collected before the search stopped,
and is `[]` when there are none.
A search can end short when postings close while it pages through the results,
so a rerun may find the ones it skipped.

A details search that could not fetch every posting fetches the others first, then raises
`Stopped`. `partial` holds every search result, with details where the fetch succeeded,
and `failed` holds the URLs of the rest. Pass them to the site's `postings` to retry.
LinkedIn stops fetching early after a rate limit that outlasts its retries,
and the postings it never tried are in `failed` too.

Reaching a site's own result cap is not a failure. jobrake warns and returns what the site served.
On every site, jobrake skips a posting it cannot read and leaves out a field it cannot read.

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

jobrake keeps the LinkedIn, Workday, SmartRecruiters, StepStone, and INOMICS postings it fetched
in one SQLite file, `jobrake.sqlite3`, under your user cache directory:
`~/Library/Caches/jobrake/` on macOS, `$XDG_CACHE_HOME/jobrake/` on Linux
(`~/.cache/jobrake/` when that variable is unset), and `%LOCALAPPDATA%\jobrake\` on Windows.
No other site is cached.

| Variable             | Default             | Effect                                                 |
| -------------------- | ------------------- | ------------------------------------------------------ |
| `JOBRAKE_CACHE_PATH` | platform user cache | Path to the SQLite file, with home-directory expansion |
| `JOBRAKE_CACHE_TTL`  | 604800              | Seconds a cached posting is served before a refetch    |

The lifetime must be a positive number of seconds.
An invalid value draws a warning and falls back to the default.

A posting that its site reports gone is not cached.
An upgrade keeps the cache.
A cached posting keeps the fields the older version extracted until it expires,
and is fetched again earlier only if its cached copy no longer fits the record's fields.

A storage failure disables the cache with a warning, and scraping carries on without it.
When another connection holds the cache locked, jobrake skips the cache for a minute with a warning, then uses it again.

`JOBRAKE_RELIEFWEB_APPNAME` holds the appname ReliefWeb approved for you. Every `reliefweb` search
needs it, and it has no default ([how to request one](sites/reliefweb.md)).
