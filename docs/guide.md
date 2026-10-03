# jobrake guide

jobrake provides one interface for Indeed and LinkedIn, but they differ in how they interpret geography, apply search filters, and fetch posting details.
Run `jobrake -h`, and `jobrake <command> -h` for commands and options.

- [Search for jobs](#search-for-jobs)
- [Narrow the results](#narrow-the-results)
- [Fetch posting details](#fetch-posting-details)
- [Read and save results](#read-and-save-results)
- [Use the Python API](#use-the-python-api)
- [Request limits and partial results](#request-limits-and-partial-results)
- [Cache location and lifetimes](#cache-location-and-lifetimes)
- [Other job boards](#other-job-boards)

## Search for jobs

Choose a provider and supply a job title or keywords:

```sh
jobrake indeed -q "data scientist" -c Netherlands -l Amsterdam -n 2
jobrake linkedin -q "data scientist" -l "Amsterdam, North Holland, Netherlands" -n 2
```

Both commands ask for two recent postings near Amsterdam, Netherlands, but each names that place its own way.
Indeed searches one country edition at a time, so `--country` is required, and `--location` narrows that edition to a city or area within it.
LinkedIn has no editions: pass the place as text to `--location`, or its ID to `--geoid`, and leave `--country` out.

Three more options shape the result set rather than its content. By default, they return **10 jobs** from the **past seven days**.

| Option                  | CLI               | Library         | Accepted values                                     |
| ----------------------- | ----------------- | --------------- | --------------------------------------------------- |
| Result limit            | `--results`, `-n` | `results`       | a positive integer                                  |
| Posting age in hours    | `--max-age`, `-a` | `max_age_hours` | a positive integer, or `None` for no age limit      |
| Search radius in km     | `--radius`, `-r`  | `radius`        | $\ge 0$, or `None` for the provider's default  |

> [!NOTE]
> Indeed measures posting age against `dateOnIndeed`, so a job inside your age window can still carry an older `posted_at`, the publication timestamp the search returns.
>
> Indeed's default radius covers 40 km around the location. LinkedIn has no default.
> LinkedIn's guest endpoint takes the distance in miles through an undocumented parameter, so jobrake sends your kilometers rounded to whole miles.
> The radius reliably widens or narrows a LinkedIn search by `--location`. A search by geoId ignores it for some places, such as Amsterdam and Utrecht.

### Write a query

Search for a job title or keywords. jobrake sends the query unchanged to Indeed's `what` or LinkedIn's `keywords` field.

Both sites match loosely, so a returned job need not contain every word you typed.
Where that matters, run several narrow queries and filter the results yourself.

#### Indeed query syntax

Indeed's mobile endpoint treats `title:` and `company:` as field restrictions.
Inside `title:`, parentheses for grouping terms and `OR` work.
Quotation marks narrow phrase searches, and a leading minus can exclude a term.
Note that these operations can be combined.

```text
title:(data OR research)
company:"Booking.com"
title:analyst company:Booking.com
title:analyst -senior
```

However, plain terms behave differently. They can match posting descriptions or
other indexed content, so `data OR research` may return jobs with neither word in the title.
You may be tempted to try `description:<term>`, but it does not reliably restrict
results to descriptions. `AND`, `OR`, and `NOT` act as provider search hints on their own.
Their results can differ from Boolean union, intersection, and exclusion.
Importantly, we do not advise mixing geography and posting age with search queries
(e.g., `"data science jobs in England last 24 hours"`), rather use their own arguments.

#### LinkedIn query syntax

LinkedIn documents [Boolean search operators](https://www.linkedin.com/help/linkedin/answer/a524335/using-boolean-search-on-linkedin?lang=en) for its own search interface.
However, they do not behave as expected on the guest endpoint jobrake uses,
so write plain keywords for LinkedIn queries.

### Choose a location

#### Indeed locations

Set `country` to a name such as `Germany` or `Netherlands`. Accepted shortcuts
are `USA`, `US`, and `UK`. `location` may contain a city or another place within
that country.

`jobrake places indeed <name> --country <edition>` prints the edition's location
suggestions as JSON, best match first. Each `suggestion` can be passed directly
to `location`. For library calls use `jobrake.sites.indeed.places`.

#### LinkedIn locations

LinkedIn accepts a location or a geoId. Its guest geocoder may return no
jobs for an **ambiguous place name**. Include the region and country whenever possible.

```sh
-l Amsterdam # Bad
-l "Amsterdam, Netherlands" # Good
-l "Amsterdam, North Holland, Netherlands" # Good
```

`--geoid | -g` works two ways. On its own it resolves `location` through LinkedIn's
place lookup, reports the place it chose, and caches that answer for later runs.
It picks the candidate whose name equals yours, and LinkedIn's first candidate when none does.
jobrake takes care of that internally. Note that a resolution that fails returns no jobs.
Alternatively, you can also directly pass a geoid like `--geoid 102011674`.
This sends that ID straight to LinkedIn and `location` becomes optional.
Library call equivalents of the two forms are `geoid=True` and `geoid="102011674"`.
Note that leaving the geoid option out is fine, jobrake just searches by location text.

If you want to know the geoid of a place name, you can use `jobrake places linkedin <name>`,
which prints LinkedIn's candidates as JSON, best match first, and caches them.
Cache matching ignores case, commas, surrounding punctuation, and repeated spaces.

```sh
jobrake places linkedin Birmingham

[
  {
    "geoId": "100356971",
    "displayName": "Birmingham, England, United Kingdom"
  },
  {
    "geoId": "102905961",
    "displayName": "Birmingham, Alabama, United States"
  },
  ...
]
```

Choose the candidate you want, then search with its display name or geoid:

```sh
jobrake linkedin -q "data scientist" -l "Birmingham, England, United Kingdom"
jobrake linkedin -q "data scientist" -g 100356971
```

Library callers use `jobrake.sites.linkedin.places` and `resolve_geoid`.

### Lookup commands

The `places`, `companies`, and `attributes` commands print JSON lists, and their library functions return
lists of the same entries. An empty list means the lookup found no matches. A failed request or unreadable
response logs a warning and returns `None` to library callers. The CLI exits nonzero on failure.

## Narrow the results

Search filters apply on every page, alongside keywords and geography, **before the result limit is applied**.
Each one has a CLI option and a library argument of the same meaning.
Pass the library argument to `scrape()` or the provider's `search()` function.

| Filter           | CLI                 | Library                | Provider | Unset   |
| ---------------- | ------------------- | ---------------------- | -------- | ------- |
| Employers        | `--company`         | `company_ids=[...]`    | LinkedIn | `None`  |
| Employer         | `--company`         | `employer_key="..."`   | Indeed   | `None`  |
| Posting language | `--language`        | `language="en"`        | Indeed   | `None`  |
| Job attribute    | `--attribute`       | `attributes=[...]`     | Indeed   | `None`  |
| Remote           | `--remote`          | `remote=True`          | Indeed   | `False` |
| Easy Apply       | `--easy-apply`      | `easy_apply=True`      | LinkedIn | `False` |
| Early applicant  | `--early-applicant` | `early_applicant=True` | LinkedIn | `False` |

An option left at its **unset** value (or an empty list) stays out of the search.

> [!NOTE]
> The CLI offers each option under its own provider alone.
> A library search takes all of them but applies the ones relevant to a provider.
> The rest pass unchecked, so `scrape("linkedin", remote="yes")` returns LinkedIn
> jobs, and a warning names each one that carried a restriction.

### Companies

Both providers filter by **employer identifier**, and both need a lookup to turn a name into one.
The identifiers differ in form, and so does the number of companies a single search accepts.

#### Indeed employers

Find an Indeed employer key by looking up the company name in a country edition:

```sh
jobrake companies indeed "Booking" -c Netherlands
```
```json
[
  {
    "employerKey": "8e8f030e53ea29e4",
    "suggestion": "Booking.com"
  },
  {
    "employerKey": "aee0b02548b689e2",
    "suggestion": "Booking Experts"
  },
  {
    "employerKey": "542f63b11393c5a9",
    "suggestion": "BookingGo"
  }
]
```

Each JSON entry pairs an `employerKey` with a company name in `suggestion`.
Results follow Indeed's suggestion order and may include related companies.
Choose the employer whose jobs you want.
Library callers use `jobrake.sites.indeed.companies(fetcher, name, country)`.

Use the selected key to restrict job results to that employer:

```sh
jobrake indeed -c Netherlands -q "data scientist" --company 8e8f030e53ea29e4
jobrake indeed -c Netherlands -q "" --company 8e8f030e53ea29e4
```

This key selects _Booking.com_. An empty query searches its postings without keywords.
For a library search, pass `employer_key="8e8f030e53ea29e4"` to `scrape()`.

> [!TIP]
> Use `-q ""` to search without keywords, works for both Indeed and LinkedIn.
> One good use case is searching for openings from a certain company.

Indeed intersects the keys it receives, so a search takes one employer key. A repeated `--company` keeps the last key.
Search one employer at a time and combine the results.

#### LinkedIn employers

Look up an employer's name to find its LinkedIn company ID:

```sh
jobrake companies linkedin "Booking"
```
```json
[
  {
    "companyId": "11348",
    "displayName": "Booking.com"
  },
  {
    "companyId": "10198247",
    "displayName": "Booking Holdings (NASDAQ: BKNG)"
  },
  {
    "companyId": "17896204",
    "displayName": "Booking Experts B.V."
  },
  {
    "companyId": "92790319",
    "displayName": "Booking Express"
  },
  {
    "companyId": "5268984",
    "displayName": "bookingkit"
  },
  {
    "companyId": "7795107",
    "displayName": "BookingJini"
  },
  {
    "companyId": "99898831",
    "displayName": "BooKing"
  },
  {
    "companyId": "34581028",
    "displayName": "Booking Shake"
  },
  {
    "companyId": "6793622",
    "displayName": "Booking Health GmbH"
  },
  {
    "companyId": "109254975",
    "displayName": "Booking Hub"
  }
]
```

The command lists suggested companies as JSON, with `companyId` and `displayName` for each entry.
LinkedIn determines the order. Subsidiaries and regional branches can have separate IDs, so choose
the intended employer or try a more specific name.
Library callers use `jobrake.sites.linkedin.companies(fetcher, name)`.

Pass an employer's numeric (a string of digits `0-9`) ID to `--company ID` to find
job postings at that company. Unlike with Indeed, here we can provide several employers.

```sh
jobrake linkedin -l "Netherlands"  -q "data scientist" --company 11348
jobrake linkedin -l "Netherlands" -q "" --company 11348 --company 215713
```

These IDs select _Booking.com_ and _ING Nederland_. For a library search, pass
`company_ids=["11348", "215713"]` to `scrape()`.

### Job posting language

Use `--language CODE` to select Indeed postings in one language:

```sh
jobrake indeed -q econometrics -c Netherlands --language en
```

Indeed decides each posting's language. The option accepts two-letter language codes
such as `EN` and `NL`. Indeed's [language-code reference](https://docs.indeed.com/api/common/objects/LanguageCode) describes
ISO 639-1. Search results also carry the legacy codes `iw` for Hebrew and `in` for Indonesian, which jobrake preserves.
An Indeed search rejects a malformed value before any request, though a well-formed code can still match nothing.

LinkedIn does not have language support.

### Job attributes

The `attributes` command helps you find codes on postings matching a job title or keywords.

```sh
jobrake attributes indeed -c usa "data scientist"
```

The command reads the first 100 matching postings and prints a JSON list of `key` and `label` pairs.
It applies no posting-age restriction. Those postings carry several (hundred) attributes between them.
Search the list by label:

```sh
jobrake attributes indeed -c usa "data scientist" \
  | jq -r '.[] | select(.label | test("python"; "i")) | [.key, .label] | @tsv'
# X62BT	Python
```

Each run samples the postings afresh, so a code can be missing from one lookup and present in the next.
Try the lookup again, or a related query, when a code you expect does not appear.
Labels can differ by country edition. A label can also belong to several codes, and the lookup keeps each code separately.
jobrake reads the codes live from Indeed. Library callers use `jobrake.sites.indeed.attributes(fetcher, query, country)`.

Once you find the codes you want, then use those codes to filter jobs:

```sh
jobrake indeed -q "data scientist" -c usa --attribute X62BT
jobrake indeed -q economist -c usa --attribute CF3CP --attribute 6QC5F
```

`X62BT` selects Python. The second search requires both Full-time (`CF3CP`) and Doctoral degree (`6QC5F`),
because codes intersect: every returned posting carries every code you list. To match any of several codes,
run separate searches and combine the results. A posting can hold codes that look mutually exclusive,
so a Full-time match may carry Part-time as well when the employer offers either arrangement.
The filter has no way to exclude a code.

For a library search, pass the codes as a list of strings, such as `attributes=["CF3CP", "6QC5F"]`.

### Remote jobs

Pass `--remote` to search postings that Indeed tags Remote:

```sh
jobrake indeed -q "econometrics" -c usa --remote
```

`--remote` is shorthand for `--attribute DSQF7`, so a posting must carry the Remote tag and every other code you pass.
The tag reflects Indeed's classification. Check the posting for residency and workplace requirements.

### Easy Apply and early applicants

Use `--easy-apply` to find jobs with LinkedIn's Easy Apply form. `--early-applicant` requests LinkedIn's "under 10 applicants" filter.

```sh
jobrake linkedin -q "data scientist" -l Netherlands --easy-apply --early-applicant
```

With both set, a job must match both. Neither needs `--details`.

LinkedIn's posting pages show a broader count than the filter's threshold. "Be among the first 25 applicants" becomes `applicants=25` in jobrake, so an early-applicant result can carry that value.

### Unsupported LinkedIn filters

The guest endpoint ignores filters for workplace type (remote, hybrid, and on-site), employment type, experience level, verified postings, and salary, so jobrake offers none of them.
Employment type is still available as a posting detail with `--details`.

## Fetch posting details

Indeed returns the details it has with the search itself, so an Indeed search needs nothing further.
LinkedIn's guest search returns summary cards only. Add `--details | -d` (`details=True`) to fetch each posting page and fill in the rest.
That costs one paced request per uncached posting, and sometimes a second.
See [request limits](#request-limits-and-partial-results) for pacing and retries, and [cache settings](#cache-location-and-lifetimes) for reuse.

### Fetch known postings

Fetch a LinkedIn posting by ID or URL without repeating a search:

```sh
jobrake details linkedin 4449382178
jobrake details linkedin https://nl.linkedin.com/jobs/view/data-scientist-at-acme-4449382178
```

LinkedIn takes postings down over time, so the examples above may be gone. Use IDs and URLs from a recent search.
Name as many postings as you like. Results follow the order given and have the same fields as a search with `--details`. Several references to one posting return one job.
The command accepts the same `--output | -o`, `--format | -f`, and `--no-cache` options as a LinkedIn search.
A posting that is gone or unreachable is reported on stderr and left out. If none resolve, the command exits nonzero and writes nothing.
A reference that is neither a numeric ID nor a LinkedIn posting URL is an error, and nothing is fetched.

LinkedIn serves a posting's dates, coordinates, and requirements only at its canonical URL: the title slug on the host of the posting's country.
That host is `www.linkedin.com` for the United States and a country subdomain, such as `nl.linkedin.com`, elsewhere.
A posting placed in a whole country, such as "United States" or "Netherlands", comes without those fields at any address.

jobrake fetches a country-subdomain URL with a slug as given. Any other reference costs one lookup first to find the canonical URL.
The cache keeps that URL, so a cached posting costs no request.

Library callers use `jobrake.sites.linkedin.fetch_details`, which returns those jobs as a list.

### Fetch selected results

For a large search, omit `-d` and fetch only the postings you want:

```python
import asyncio

from jobrake import scrape
from jobrake.fetchkit import HttpxFetcher
from jobrake.sites import linkedin


async def main():
    async with HttpxFetcher() as fetcher:
        jobs = await scrape(
            "linkedin",
            query="data scientist",
            location="Amsterdam, North Holland, Netherlands",
            results=10,
            fetcher=fetcher,
        )
        urls = [job["url"] for job in jobs if "senior" not in (job["title"] or "").lower()]
        return await linkedin.fetch_postings(fetcher, urls)


postings = asyncio.run(main())
```

`fetch_postings()` maps each URL to its detail fields, or to `None` after HTTP 404 or 410.
A URL that failed for another reason is absent from the result, and calling the function again retries it.

| Function           | Takes       | Returns                        |
| ------------------ | ----------- | ------------------------------ |
| `fetch_postings()` | URLs        | detail fields keyed by URL     |
| `fetch_details()`  | IDs or URLs | whole jobs, in the order given |

Use `fetch_postings()` to add fields to jobs you already hold. Use `fetch_details()` when a posting reference is all you have.

## Read and save results

### Returned fields

Every job is a flat dictionary, with three groups of keys.

- **Identity keys:** `site`, `id`, and `url`.
- **Summary keys:** `title`, `company`, `location`, and `date`.
- **Detail keys:** included when a value is available.

Identity and summary keys are always present, with `None` for an unavailable summary value.
A detail key is absent when the provider omits or does not publish the value, or when jobrake did not fetch the posting page.

Both providers use the same names for the details they share. A few come from one provider only:
`apply_type`, `applicants`, `experience_months`, and `education` from LinkedIn, and `is_remote`, `apply_url`, and `language` from Indeed.

A posting can carry two dates. `date` holds the calendar date, such as `2026-09-19`, and `posted_at` holds the full timestamp, such as `2026-09-19T05:00:00+00:00`.
jobrake prefers the date a search result states and falls back to the calendar portion of `posted_at`. Compare on `date`, and read `posted_at` for a time of day.

### Output formats

The CLI writes compact JSON to stdout. `--output | -o` writes a new file instead and refuses to overwrite an existing one.
`--format | -f` chooses `json`, `jsonl`, or `csv`, and defaults to the extension of `--output`.
A search that returns no jobs writes no file, and the output directory must already exist.

```sh
jobrake ... -o jobs.csv
jobrake ... -o jobs.txt -f jsonl
```

The formats represent unavailable fields differently.

- JSON writes one array, using `null` for unavailable summary values.
- JSONL writes one job per line with the same keys as JSON.
- CSV writes every field as a column and leaves unavailable cells empty.

> [!TIP]
> JSONL suits a run you repeat, a daily one for instance. Combine the files with `cat`, or read the whole directory into DuckDB.
>
> ```sh
> jobrake ... -o runs/2026-08-10.jsonl
> jobrake ... -o runs/2026-08-11.jsonl
> cat runs/*.jsonl > jobs.jsonl
>
> duckdb -c "select * from read_json('runs/*.jsonl', union_by_name=true)"
> ```

### Pipe results

Pipe stdout into another program to reshape the jobs. [`jq`](https://github.com/jqlang/jq) picks out fields:

```sh
jobrake indeed -q "data scientist" -c usa -n 2 \
  | jq -r '.[] | [.date, .title, .company, .url] | @tsv'
```

## Use the Python API

`scrape()` creates and closes an HTTP client when `fetcher` is omitted.
Library calls log under the `jobrake` logger, and your application sets its level and handlers.

```python
import asyncio

from jobrake import scrape


async def main():
    jobs = await scrape(
        "indeed",
        query="economist",
        country="United States",
        results=2,
    )
    for job in jobs:
        print(job["title"], job["url"])


asyncio.run(main())
```

A fetcher you supply is yours to close.
Use its context manager when several searches should share one connection pool:

```python
import asyncio

from jobrake import scrape
from jobrake.fetchkit import HttpxFetcher


async def main():
    query = "economist"
    site = "indeed"
    async with HttpxFetcher(timeout=30) as fetcher:
        nl = await scrape(
            site,
            query=query,
            location="Amsterdam",
            country="Netherlands",
            fetcher=fetcher,
        )
        us = await scrape(
            site,
            query=query,
            location="New York",
            country="USA",
            fetcher=fetcher,
        )
    return nl, us


nl, us = asyncio.run(main())
```

To use another HTTP client or a browser, implement `Fetcher` or subclass `BaseFetcher`.
An Indeed search also needs `post()` from `PostFetcher`.
`BaseFetcher` records request exceptions in `FetchResult.error`. An exception your own `Fetcher` raises propagates out of `scrape()`.

## Request limits and partial results

Both providers return the jobs already collected when a request fails. A short result is normal, and the warning on stderr says what stopped.

### Indeed requests

One search reaches at most 1,000 results.

Indeed returns jobs newest first by the date the posting reached Indeed, the same date `--max-age` filters on.
A reposted job counts as new, so a 24-hour window can include postings published weeks earlier.
Repeating a search returns the same jobs in the same order.

Pages follow one another without delay, and each request gets a single attempt.
jobrake skips a posting it cannot read and leaves out a field it cannot read.

### LinkedIn requests

The guest search returns about 10 cards per page and stops at offset 1,000, so one search returns roughly 1,000 postings at most.
jobrake warns when that limit cuts a search short.

jobrake asks LinkedIn for the newest postings first, but the guest endpoint ignores the request and ranks by relevance.
The order can also change between two runs of the same search.
To collect only new postings, repeat the search with `--max-age` covering the time since the last run.

LinkedIn limits traffic per IP. jobrake permits a short burst, then waits about three seconds between requests.
Each process has its own limiter, so concurrent runs on the same IP can reach the limit sooner.

After a 429, jobrake waits for the `Retry-After` value or 10 seconds, then retries once.
A `Retry-After` over one minute skips the retry. If the 429 remains, jobrake returns what it has collected so far.

## Cache location and lifetimes

jobrake keeps posting fields, posting addresses, and LinkedIn place resolutions in one SQLite file under your user cache directory: `~/Library/Caches/jobrake/` on macOS, `$XDG_CACHE_HOME/jobrake/` on Linux, `%LOCALAPPDATA%\jobrake\` on Windows.

Posting fields stay fresh for seven days and are deleted after 30. Fields past their freshness period are fetched again.
jobrake also remembers a posting that returned HTTP 404 or 410 and skips it for those same 30 days.
Posting addresses and place resolutions stay indefinitely.

Pass `--no-cache` or `cache=False` to refetch every posting and refresh its cached copy.
A jobrake release that changes what the cache stores ignores the older values and fills the cache again as you search.

Three environment variables configure the cache:

| Variable                  | Default             | Effect                                                         |
| ------------------------- | ------------------- | -------------------------------------------------------------- |
| `JOBRAKE_CACHE_PATH`      | platform user cache | Path to the SQLite file, with home-directory expansion         |
| `JOBRAKE_CACHE_TTL`       | 604800              | Seconds a stored field is served before a refetch              |
| `JOBRAKE_CACHE_RETENTION` | 2592000             | Seconds a field stays on disk, counted from when it was stored |

A lifetime must be a positive number of seconds. An invalid value draws a warning and falls back to the default.
If the retention is shorter than the freshness period, jobrake raises it to match.

A storage failure disables the cache with a warning, and scraping carries on without it.

## Other job boards

Glassdoor is not planned because it is now [part of Indeed](https://web.archive.org/web/20260704043638/https://www.glassdoor.com/about/).
