# jobrake reference

This page describes a jobrake record, the commands and options every site shares, the Python API,
and configuration. Each site's own options, fields, and limits are on its page under
[sites](sites/), and the [guide](guide.md) shows how to do common tasks.

- [The record](#the-record)
- [Fields by site](#fields-by-site)
- [Command line](#command-line)
- [Python API](#python-api)
- [Configuration](#configuration)

## The record

Every job is a dictionary, with three groups of keys.

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
and so does jobrake's reading of LinkedIn's page markup.
Indeed's value and the one in LinkedIn's structured data pass through as sent.
`workplace_type` appears only when the site states it,
so an absent one leaves the workplace unknown and does not mean on-site.

`site_data` holds fields that only one site carries, under that site's own names,
such as EconJobMarket's `position_types`.
Its keys depend on `site`, and each site's page lists them.
A key that a second site comes to share with the same meaning moves into the record.

### Places

Each place in `locations` has a `name`, the site's label for it or its parts joined
when the site gives no label,
and carries `city`, `region`, `country_code`, `latitude`, and `longitude` only
when the site gives them for that place.
`country_code` has the form of an ISO 3166-1 alpha-2 code, such as `US`,
and jobrake checks the form only.
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
Some sites send another form, such as Lever's epoch milliseconds or INOMICS's day-first dates,
which jobrake converts to ISO 8601. A value jobrake cannot read logs a warning that names the field
and the posting: `date` falls back to `posted_at` or becomes `None`, and `posted_at` or
`expires_at` is left out.

## Fields by site

Each detail key comes from the sites below, from a search or only once `--details` fetches the
posting's page. A site that fills a key fills it when the posting has a value, and each site's page
says what the value holds.

| Key | From a search | Only with `--details` |
| --- | --- | --- |
| `description` | [AcademicTransfer](sites/academictransfer.md), [AEA JOE](sites/aea.md), [Ashby](sites/ashby.md), [EconJobMarket](sites/econjobmarket.md), [Greenhouse](sites/greenhouse.md), [Indeed](sites/indeed.md), [Lever](sites/lever.md), [Personio](sites/personio.md), [UN Careers](sites/uncareers.md), [Workable](sites/workable.md) | [INOMICS](sites/inomics.md), [LinkedIn](sites/linkedin.md), [SmartRecruiters](sites/smartrecruiters.md), [StepStone](sites/stepstone.md), [Workday](sites/workday.md) |
| `language` | [AcademicTransfer](sites/academictransfer.md), [Greenhouse](sites/greenhouse.md), [Indeed](sites/indeed.md), [SmartRecruiters](sites/smartrecruiters.md), [StepStone](sites/stepstone.md) | — |
| `company_url` | [Indeed](sites/indeed.md) | [LinkedIn](sites/linkedin.md), [StepStone](sites/stepstone.md) |
| `company_logo` | [EconJobMarket](sites/econjobmarket.md), [Indeed](sites/indeed.md), [StepStone](sites/stepstone.md) | [LinkedIn](sites/linkedin.md) |
| `department` | [AcademicTransfer](sites/academictransfer.md), [AEA JOE](sites/aea.md), [Ashby](sites/ashby.md), [EconJobMarket](sites/econjobmarket.md), [Greenhouse](sites/greenhouse.md), [Lever](sites/lever.md), [Personio](sites/personio.md), [SmartRecruiters](sites/smartrecruiters.md), [Workable](sites/workable.md) | — |
| `team` | [Ashby](sites/ashby.md), [Lever](sites/lever.md) | — |
| `employment_type` | [AcademicTransfer](sites/academictransfer.md), [Ashby](sites/ashby.md), [Indeed](sites/indeed.md), [Lever](sites/lever.md), [Personio](sites/personio.md), [SmartRecruiters](sites/smartrecruiters.md), [Workable](sites/workable.md) | [LinkedIn](sites/linkedin.md), [StepStone](sites/stepstone.md), [Workday](sites/workday.md) |
| `workplace_type` | [Ashby](sites/ashby.md), [Indeed](sites/indeed.md), [INOMICS](sites/inomics.md), [Lever](sites/lever.md), [SmartRecruiters](sites/smartrecruiters.md), [Workable](sites/workable.md) | — |
| `salary_min` | [AcademicTransfer](sites/academictransfer.md), [Ashby](sites/ashby.md), [Indeed](sites/indeed.md), [Personio](sites/personio.md) | [LinkedIn](sites/linkedin.md) |
| `salary_max` | [AcademicTransfer](sites/academictransfer.md), [Ashby](sites/ashby.md), [Indeed](sites/indeed.md), [Personio](sites/personio.md) | [LinkedIn](sites/linkedin.md) |
| `salary_currency` | [AcademicTransfer](sites/academictransfer.md), [Ashby](sites/ashby.md), [Indeed](sites/indeed.md), [Personio](sites/personio.md) | [LinkedIn](sites/linkedin.md) |
| `salary_period` | [AcademicTransfer](sites/academictransfer.md), [Ashby](sites/ashby.md), [Indeed](sites/indeed.md), [Personio](sites/personio.md) | [LinkedIn](sites/linkedin.md) |
| `posted_at` | [AcademicTransfer](sites/academictransfer.md), [AEA JOE](sites/aea.md), [Ashby](sites/ashby.md), [EconJobMarket](sites/econjobmarket.md), [Greenhouse](sites/greenhouse.md), [Indeed](sites/indeed.md), [INOMICS](sites/inomics.md), [Lever](sites/lever.md), [Personio](sites/personio.md), [SmartRecruiters](sites/smartrecruiters.md), [StepStone](sites/stepstone.md), [UN Careers](sites/uncareers.md), [Workable](sites/workable.md) | [LinkedIn](sites/linkedin.md), [Workday](sites/workday.md) |
| `expires_at` | [AcademicTransfer](sites/academictransfer.md), [AEA JOE](sites/aea.md), [EconJobMarket](sites/econjobmarket.md), [Greenhouse](sites/greenhouse.md), [Indeed](sites/indeed.md), [StepStone](sites/stepstone.md), [UN Careers](sites/uncareers.md) | [INOMICS](sites/inomics.md), [LinkedIn](sites/linkedin.md) |
| `apply_url` | [AcademicTransfer](sites/academictransfer.md), [Ashby](sites/ashby.md), [Indeed](sites/indeed.md), [Lever](sites/lever.md), [Workable](sites/workable.md) | [SmartRecruiters](sites/smartrecruiters.md) |
| `apply_type` | — | [LinkedIn](sites/linkedin.md) |
| `applicants` | — | [LinkedIn](sites/linkedin.md) |
| `experience_months` | — | [LinkedIn](sites/linkedin.md) |
| `education` | [AcademicTransfer](sites/academictransfer.md), [Workable](sites/workable.md) | [LinkedIn](sites/linkedin.md) |
| `keywords` | [AcademicTransfer](sites/academictransfer.md), [AEA JOE](sites/aea.md), [Personio](sites/personio.md) | — |
| `site_data` | [AcademicTransfer](sites/academictransfer.md), [AEA JOE](sites/aea.md), [Ashby](sites/ashby.md), [EconJobMarket](sites/econjobmarket.md), [INOMICS](sites/inomics.md), [Personio](sites/personio.md), [StepStone](sites/stepstone.md), [UN Careers](sites/uncareers.md) | [LinkedIn](sites/linkedin.md) |

## Command line

Every command has the form `jobrake <site> <command>`, and `-h` at each level lists what comes next.
The [README](../README.md#cli) lists the options several sites share, the output formats, and the
exit statuses.

| Site                                                     | Commands                                          |
| -------------------------------------------------------- | ------------------------------------------------- |
| [`indeed`](sites/indeed.md)                              | `search`, `places`, `companies`, `attributes`     |
| [`linkedin`](sites/linkedin.md)                          | `search`, `postings`, `places`, `companies`       |
| [`inomics`](sites/inomics.md), [`smartrecruiters`](sites/smartrecruiters.md), [`stepstone`](sites/stepstone.md), [`workday`](sites/workday.md) | `search`, `postings` |
| [`uncareers`](sites/uncareers.md)                        | `search`, `filters`                               |
| every other site                                         | `search`                                          |

### Options

A site takes only the options its server applies.
`jobrake linkedin search --remote` fails as an unrecognized argument and exits 2,
and `scrape("linkedin", remote=True)` raises `TypeError` before any request and lists LinkedIn's
options.
An option left at its unset value, or an empty list, stays out of the search.
A list option takes several values after one flag, `--attributes CF3CP 6QC5F`, or across repeats.
A posting must match every option given. How several values of one option combine differs by
site, and each site's page says so.
A value outside a site's fixed menu is an error before any request.
Filters apply on every page, alongside keywords and geography, before the result limit.

| Filter           | CLI                 | Library                | Sites                              |
| ---------------- | ------------------- | ---------------------- | ---------------------------------- |
| Employers        | `--company-ids`     | `company_ids=[...]`    | LinkedIn, Indeed                   |
| Posting language | `--language`        | `language="en"`        | Indeed                             |
| Job attributes   | `--attributes`      | `attributes=[...]`     | Indeed                             |
| Remote           | `--remote`          | `remote=True`          | Indeed, SmartRecruiters, StepStone |
| Easy Apply       | `--easy-apply`      | `easy_apply=True`      | LinkedIn                           |
| Early applicant  | `--early-applicant` | `early_applicant=True` | LinkedIn                           |

### Lookups

The `places`, `companies`, `attributes`, and `filters` commands print an indented JSON list of
`{"id", "name"}` entries, and their library functions return the same list.
Each `id` is the value a search takes. An empty list means the lookup found no matches.
A lookup takes no `--output` or `--format`, so redirect it to save it.
A failed request or unreadable response raises `Stopped` in a library call,
and the CLI exits 1.

| Command                                       | Library function                                               |
| --------------------------------------------- | -------------------------------------------------------------- |
| `jobrake indeed places <name> -c <code>`      | `jobrake.sites.indeed.places(fetcher, name, country=...)`      |
| `jobrake indeed companies <name> -c <code>`   | `jobrake.sites.indeed.companies(fetcher, name, country=...)`   |
| `jobrake indeed attributes <query> -c <code>` | `jobrake.sites.indeed.attributes(fetcher, query, country=...)` |
| `jobrake linkedin places <name>`              | `jobrake.sites.linkedin.places(fetcher, name)`                 |
| `jobrake linkedin companies <name>`           | `jobrake.sites.linkedin.companies(fetcher, name)`              |
| `jobrake uncareers filters <option>`          | `jobrake.sites.uncareers.filters(fetcher, option)`             |

### Postings

`jobrake <site> postings <reference>...` fetches postings you already know, on LinkedIn, Workday,
SmartRecruiters, StepStone, and INOMICS, with no request for a cached posting.
A reference is at least a search result's `url`, and each site's page lists the other forms it
takes. Any other reference is an error, and nothing is fetched.
Results follow the order given and have the fields of the posting's page,
so a field only the search card carries is absent.
Several references to one posting return one job.
The command takes the same `--output` and `--format` as a search.
A posting that is gone or unreachable is reported on stderr and left out.
When one was unreachable, the command writes the others and exits 1.

## Python API

```python
import jobrake

await jobrake.scrape(site, *, fetcher=None, **options)  # -> list[JobDict]
jobrake.check(site, **options)  # -> None, or the TypeError or ValueError scrape would raise
jobrake.identify(link)  # -> (site, id) or None
```

`scrape` takes a site's `search` options as keyword arguments, named as the CLI's long options
with underscores, such as `max_age_hours`.
It checks them before any request. An unknown, missing, or wrongly typed option raises
`TypeError`, and an unknown site, a value out of range, a blank required string, or a value the
site refuses raises `ValueError`.
Without `fetcher`, it creates and closes an `HttpxFetcher` of its own.
`jobrake.sites.SITES` maps each site name to its module.

`check` takes the same arguments as `scrape` without `fetcher` and sends no request,
so a caller can check every planned search, such as searches read from a config file,
before the first one runs.
A value that only the site's live list can confirm, such as a UN Careers duty station,
passes `check`, and the search refuses it after reading that list:

```python
jobrake.check("indeed", query="economist", country="zz")  # ValueError: unknown Indeed country 'zz'
jobrake.check("uncareers", duty_station=["Genva"])  # passes, and the search raises ValueError
```

`identify` returns the `site` and `id` that a search gives the posting a link names, and sends no
request. It reads the posting URLs of LinkedIn, Indeed, INOMICS, SmartRecruiters, StepStone, and
Workday: those that `postings` takes, and Indeed links that carry the key in `jk`, or in `vjk` on a
search page. Any other link, including a bare LinkedIn ID or a Greenhouse posting, gives `None`.

```python
jobrake.identify("https://nl.indeed.com/viewjob?jk=1a2b3c4d5e6f7a8b")  # ('indeed', '1a2b3c4d5e6f7a8b')
```

### Site functions

Each site module in `jobrake.sites` exports `search` and the functions behind its other commands,
and each takes a `Fetcher` first: `search(fetcher, **options)`,
`postings(fetcher, references)`, and the lookups listed under [Lookups](#lookups).
Every one has a `.check(**options)` that raises what the call would, without a request,
such as `stepstone.postings.check(references=urls)`.

`postings` never raises `Stopped`. It maps each reference to its whole job,
or to `None` when the site reports the posting gone.
A reference whose request failed, or whose response jobrake cannot read, is absent from the result,
and calling the function again retries it.

### Stopped

A failed request, an answer other than HTTP 200, or a page that ends a search short of the total
the site reported raises `jobrake.Stopped`.
Its `partial` holds the jobs collected before the search stopped, and is `[]` when there are none.
A details search that could not fetch every posting raises it at the end, with every posting in
`partial`, filled where its posting was read, and the URLs of the unfetched ones in `failed`, for
the site's `postings` to retry. LinkedIn stops fetching early after a rate limit that outlasts its
retries, and the postings it never tried are in `failed` too.
`partial` is a list of `JobDict` and `failed` a list of URL strings, each `[]` when empty.
Reaching a site's own result cap is not a failure: jobrake warns and returns what the site served.
On every site, jobrake skips a posting it cannot read and leaves out a field it cannot read.

### Fetchers

`jobrake.HttpxFetcher(timeout=30.0, *, headers=None)` is the HTTP client jobrake uses by default.
`timeout` applies to each network operation, in seconds, and must be finite and positive, or it
raises `ValueError`. `headers` override its browser-like default headers, whatever the case of their
names.
Use it as an async context manager to share one connection pool across calls.
A fetcher you supply is yours to close.

To use another HTTP client, implement the `Fetcher` protocol from `jobrake.fetchkit`:
an async `fetch(url, *, headers=None, json=None, follow_redirects=True)`
that sends a POST when `json` is given.
With `follow_redirects=False`, return the first response,
including its `Location` header. LinkedIn uses this to pace each redirect hop.
`fetch` returns a `FetchResult(url, status, text, headers, error)`: the final URL, the HTTP status
or `None` when no response arrived, the body, the response headers, which it stores with lowercased
names, and a failure message or `None`. It reports a failed request in `error`.
A status of 400 or more sets `error` on its own,
and jobrake reads a response as data only when its `status` is 200.
An exception your own `Fetcher` raises propagates out of `scrape()`.

### Types and logging

`jobrake.JobDict` and `jobrake.Place` are the `TypedDict`s of a record and a place, for type hints.
Library calls log under the `jobrake` logger and print nothing, and your application sets its level
and handlers. While a paged search reads its pages, and while it fetches posting details,
jobrake logs INFO records whose `progress` attribute holds `(done, total)`.
The [guide](guide.md#show-progress) shows a handler that draws them.

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
and is fetched again earlier only if its cached copy no longer fits the job fields.
A storage failure disables the cache with a warning, and scraping carries on without it.
When another connection holds the cache locked, jobrake skips the cache for a minute with a
warning, then uses it again.
jobrake has no switch to turn the cache off. To run without the cached postings, point
`JOBRAKE_CACHE_PATH` at a new file, as the [guide](guide.md#refresh-the-cache) shows.
