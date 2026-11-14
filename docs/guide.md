# jobrake guide

jobrake provides one interface for Indeed, LinkedIn, EconJobMarket, and employers' boards on applicant tracking systems, but the sites differ in how they interpret geography, apply search filters, and fetch posting details.
Run `jobrake -h` for the sites, `jobrake <site> -h` for a site's commands, and `jobrake <site> <command> -h` for their options.
The [reference](reference.md) lists the fields each site returns and how each site's requests behave.

- [Search for jobs](#search-for-jobs)
- [Narrow the results](#narrow-the-results)
- [Fetch posting details](#fetch-posting-details)
- [Employer boards](#employer-boards)
- [EconJobMarket](#econjobmarket)
- [Read and save results](#read-and-save-results)
- [Use the Python API](#use-the-python-api)
- [Request limits and partial results](#request-limits-and-partial-results)
- [Cache location and lifetimes](#cache-location-and-lifetimes)
- [Other job boards](#other-job-boards)

## Search for jobs

The searches in this section run on Indeed and LinkedIn. To read one employer's board or EconJobMarket, go to [Employer boards](#employer-boards) or [EconJobMarket](#econjobmarket).

Choose a site and supply a job title or keywords:

```sh
jobrake indeed search -q "data scientist" -c nl -l Amsterdam -n 2
jobrake linkedin search -q "data scientist" -l "Amsterdam, North Holland, Netherlands" -n 2
```

Both commands ask for two postings near Amsterdam, Netherlands, but each names that place its own way.
Indeed searches one country edition at a time, so `--country` is required, and `--location` narrows that edition to a city or area within it.
LinkedIn has no editions: pass the place as text to `--location`, or its ID to `--geoid`, and leave `--country` out.

Three more options shape the result set rather than its content. By default, a search returns **10 jobs** with **no age limit**.

| Option               | CLI                     | Library         | Accepted values                                  |
| -------------------- | ----------------------- | --------------- | ------------------------------------------------ |
| Result limit         | `--results`, `-n`       | `results`       | a positive integer                               |
| Posting age in hours | `--max-age-hours`, `-a` | `max_age_hours` | a positive integer, or unset for no age limit    |
| Search radius in km  | `--radius`, `-r`        | `radius`        | $\ge 0$, or `None` on LinkedIn to send no radius |

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
results to descriptions. `AND`, `OR`, and `NOT` act as Indeed search hints on their own.
Their results can differ from Boolean union, intersection, and exclusion.
Use the location and posting-age options to restrict geography and age.
Keep those restrictions out of query text such as `"data science jobs in England last 24 hours"`.

#### LinkedIn query syntax

LinkedIn documents [Boolean search operators](https://www.linkedin.com/help/linkedin/answer/a524335/using-boolean-search-on-linkedin?lang=en) for its own search interface.
However, they do not behave as expected on the guest endpoint jobrake uses,
so write plain keywords for LinkedIn queries.

### Choose a location

#### Indeed locations

Set `country` to the country's ISO 3166-1 alpha-2 code in either case, such as `de`, `gb`, or `us`.
A code with no Indeed edition is an error that lists the codes Indeed serves.
`location` may contain a city or another place within that country.

`jobrake indeed places <name> --country <code>` prints the edition's location
suggestions as JSON, best match first. Each `id` can be passed directly
to `--location`.

#### LinkedIn locations

LinkedIn accepts a location or a geoId. Its guest geocoder may return no
jobs for an **ambiguous place name**. Include the region and country whenever possible.

```sh
-l Amsterdam # Bad
-l "Amsterdam, Netherlands" # Good
-l "Amsterdam, North Holland, Netherlands" # Good
```

`--geoid | -g` takes a geoId, such as `--geoid 102011674`.
This sends that ID straight to LinkedIn and `location` becomes optional.
The library call equivalent is `geoid="102011674"`.
Note that leaving the geoid option out is fine, jobrake just searches by location text.

If you want to know the geoId of a place name, you can use `jobrake linkedin places <name>`,
which prints LinkedIn's candidates as JSON, best match first.

```sh
jobrake linkedin places Birmingham

[
  {
    "id": "100356971",
    "name": "Birmingham, England, United Kingdom"
  },
  {
    "id": "102905961",
    "name": "Birmingham, Alabama, United States"
  },
  ...
]
```

Choose the candidate you want, then search with its display name or geoId:

```sh
jobrake linkedin search -q "data scientist" -l "Birmingham, England, United Kingdom"
jobrake linkedin search -q "data scientist" -g 100356971
```

### Lookup commands

The `places`, `companies`, and `attributes` commands print JSON lists of `{"id", "name"}` entries, and their
library functions return the same lists. Each `id` is the value a search takes. An empty list means the lookup
found no matches. A failed request or unreadable response raises `Stopped` in a library call. The CLI exits nonzero on failure.

| Command                                       | Library function                                               |
| --------------------------------------------- | -------------------------------------------------------------- |
| `jobrake indeed places <name> -c <code>`      | `jobrake.sites.indeed.places(fetcher, name, country=...)`      |
| `jobrake indeed companies <name> -c <code>`   | `jobrake.sites.indeed.companies(fetcher, name, country=...)`   |
| `jobrake indeed attributes <query> -c <code>` | `jobrake.sites.indeed.attributes(fetcher, query, country=...)` |
| `jobrake linkedin places <name>`              | `jobrake.sites.linkedin.places(fetcher, name)`                 |
| `jobrake linkedin companies <name>`           | `jobrake.sites.linkedin.companies(fetcher, name)`              |

## Narrow the results

Search filters apply on every page, alongside keywords and geography, **before the result limit is applied**.
Each one has a CLI option and a library argument of the same name.
Pass the library argument to `scrape()` or the site's `search()` function.

| Filter           | CLI                 | Library                | Site                    | Unset   |
| ---------------- | ------------------- | ---------------------- | ----------------------- | ------- |
| Employers        | `--company-ids`     | `company_ids=[...]`    | LinkedIn, Indeed        | `None`  |
| Posting language | `--language`        | `language="en"`        | Indeed                  | `None`  |
| Job attributes   | `--attributes`      | `attributes=[...]`     | Indeed                  | `None`  |
| Remote           | `--remote`          | `remote=True`          | Indeed, SmartRecruiters | `False` |
| Easy Apply       | `--easy-apply`      | `easy_apply=True`      | LinkedIn                | `False` |
| Early applicant  | `--early-applicant` | `early_applicant=True` | LinkedIn                | `False` |

An option left at its **unset** value (or an empty list) stays out of the search.
A list option takes several values after one flag, `--attributes CF3CP 6QC5F`, or across repeats.

> [!NOTE]
> Each site takes only the filters it applies.
> `scrape("linkedin", remote=True)` raises `TypeError` before any request and lists LinkedIn's options,
> and `jobrake linkedin search --remote` fails as an unrecognized argument.

### Companies

Both sites filter by **employer identifier**, and both need a lookup to turn a name into one.
The identifiers differ in form, and so does the number of companies a single search accepts.

#### Indeed employers

Find an Indeed employer key by looking up the company name in a country edition:

```sh
jobrake indeed companies "Booking" -c nl
```
```json
[
  {
    "id": "8e8f030e53ea29e4",
    "name": "Booking.com"
  },
  {
    "id": "aee0b02548b689e2",
    "name": "Booking Experts"
  },
  {
    "id": "542f63b11393c5a9",
    "name": "BookingGo"
  }
]
```

Each JSON entry pairs an employer key in `id` with a company name in `name`.
Results follow Indeed's suggestion order and may include related companies.
Choose the employer whose jobs you want.

Use the selected key to restrict job results to that employer:

```sh
jobrake indeed search -c nl -q "data scientist" --company-ids 8e8f030e53ea29e4
jobrake indeed search -c nl --company-ids 8e8f030e53ea29e4
```

This key selects _Booking.com_. Without `-q`, the search covers its postings without keywords.

> [!TIP]
> Leave out `-q` to search without keywords, works for both Indeed and LinkedIn.
> One good use case is searching for openings from a certain company.

Indeed intersects the keys it receives, so a search takes one employer key and rejects more.
Search one employer at a time and combine the results.

#### LinkedIn employers

Look up an employer's name to find its LinkedIn company ID:

```sh
jobrake linkedin companies "Booking"
```
```json
[
  {
    "id": "11348",
    "name": "Booking.com"
  },
  {
    "id": "10198247",
    "name": "Booking Holdings (NASDAQ: BKNG)"
  },
  {
    "id": "17896204",
    "name": "Booking Experts B.V."
  }
]
```

The command lists suggested companies as JSON, with `id` and `name` for each entry.
LinkedIn determines the order. Subsidiaries and regional branches can have separate IDs, so choose
the intended employer or try a more specific name.

Pass an employer's numeric (a string of digits `0-9`) ID to `--company-ids` to find
job postings at that company. Unlike with Indeed, here we can provide several employers.

```sh
jobrake linkedin search -l "Netherlands" -q "data scientist" --company-ids 11348
jobrake linkedin search -l "Netherlands" --company-ids 11348 215713
```

These IDs select _Booking.com_ and _ING Nederland_.

### Job posting language

Use `--language CODE` to select Indeed postings in one language:

```sh
jobrake indeed search -q econometrics -c nl --language en
```

Indeed decides each posting's language. The option accepts two-letter language codes
such as `EN` and `NL`. Indeed's [language-code reference](https://docs.indeed.com/api/common/objects/LanguageCode) describes
ISO 639-1. Search results also carry the legacy codes `iw` for Hebrew and `in` for Indonesian, which jobrake preserves.
An Indeed search rejects a malformed value before any request, though a well-formed code can still match nothing.

jobrake's LinkedIn search has no language filter.

### Job attributes

The `attributes` command helps you find codes on postings matching a job title or keywords.

```sh
jobrake indeed attributes -c us "data scientist"
```

The command reads the first 100 matching postings and prints a JSON list of code and label pairs, as `id` and `name`.
It applies no posting-age restriction. Those postings carry several (hundred) attributes between them.
Search the list by label:

```sh
jobrake indeed attributes -c us "data scientist" \
  | jq -r '.[] | select(.name | test("python"; "i")) | [.id, .name] | @tsv'
# X62BT	Python
```

Each run samples the postings afresh, so a code can be missing from one lookup and present in the next.
Try the lookup again, or a related query, when a code you expect does not appear.
Labels can differ by country edition. A label can also belong to several codes, and the lookup keeps each code separately.
jobrake reads the codes live from Indeed.

Once you find the codes you want, then use those codes to filter jobs:

```sh
jobrake indeed search -q "data scientist" -c us --attributes X62BT
jobrake indeed search -q economist -c us --attributes CF3CP 6QC5F
```

`X62BT` selects Python. The second search requires both Full-time (`CF3CP`) and Doctoral degree (`6QC5F`),
because codes intersect: every returned posting carries every code you list. To match any of several codes,
run separate searches and combine the results. A posting can hold codes that look mutually exclusive,
so a Full-time match may carry Part-time as well when the employer offers either arrangement.
The filter has no way to exclude a code.

### Remote jobs

Pass `--remote` to search postings that Indeed tags Remote:

```sh
jobrake indeed search -q "econometrics" -c us --remote
```

`--remote` is shorthand for `--attributes DSQF7`, so a posting must carry the Remote tag and every other code you pass.
The tag reflects Indeed's classification. Check the posting for residency and workplace requirements.
An Indeed record's `workplace_type` is `remote` for a posting tagged Remote and `hybrid` for one tagged Hybrid work, whose code is `PAXZC`. Indeed tags some postings both, and such a posting has no `workplace_type`.

### Easy Apply and early applicants

Use `--easy-apply` to find jobs with LinkedIn's Easy Apply form. `--early-applicant` requests LinkedIn's "under 10 applicants" filter.

```sh
jobrake linkedin search -q "data scientist" -l Netherlands --easy-apply --early-applicant
```

With both set, a job must match both. Neither needs `--details`.

LinkedIn's posting pages show a broader count than the filter's threshold. "Be among the first 25 applicants" becomes `applicants=25` in jobrake, so an early-applicant result can carry that value.

### Unsupported LinkedIn filters

The guest endpoint ignores filters for workplace type (remote, hybrid, and on-site), employment type, experience level, verified postings, and salary, so jobrake offers none of them.
Employment type is still available as a posting detail with `--details`.

## Fetch posting details

Indeed returns the details it has with the search itself, so an Indeed search needs nothing further.
LinkedIn's guest search returns summary cards only. Add `--details | -d` (`details=True`) to fetch each posting page and fill in the rest.
That costs one paced request for most uncached postings and up to three for the rest.
In our measurements, a LinkedIn posting placed in a whole country, such as "United States" or "Netherlands", comes without its dates, coordinates, and requirements.

Workday and SmartRecruiters searches also return cards without descriptions, and `--details` fetches each posting with one more request, one after another, as [Workday fields](reference.md#workday-fields) and [SmartRecruiters fields](reference.md#smartrecruiters-fields) describe.
On these two sites, a posting removed or withdrawn since the search keeps its search result.
A posting SmartRecruiters reports missing or marks inactive counts as gone, and jobrake reads a Workday 403 that names error `S22` as withdrawn, as [career-ops](https://github.com/career-ops-hq/career-ops)' liveness checks do.

A posting whose details cannot be fetched also keeps its search result, and once the rest are fetched the search raises `Stopped` with every posting in `partial`. A rerun retries them.
See [LinkedIn requests](reference.md#linkedin-requests) for pacing and retries, and [cache settings](#cache-location-and-lifetimes) for reuse.

### Fetch known postings

Fetch postings you already know on LinkedIn, Workday, or SmartRecruiters without repeating a search:

```sh
jobrake linkedin postings 4449382178
jobrake linkedin postings https://nl.linkedin.com/jobs/view/data-scientist-at-acme-4449382178
jobrake workday postings https://zillow.wd5.myworkdayjobs.com/Zillow_Group_External/job/Remote-USA/Applied-Scientist_P751481-1
jobrake smartrecruiters postings https://jobs.smartrecruiters.com/BoschGroup/744000158197889
```

Sites take postings down over time, so the examples above may be gone. Use references from a recent search.
Name as many postings as you like. Results follow the order given and have the fields of a search with `--details`, except a field only the search result carries, such as SmartRecruiters' `department`. Several references to one posting return one job.
The command accepts the same `--output | -o` and `--format | -f` options as a search.
A posting that is gone or unreachable is reported on stderr and left out. When one was unreachable, the command writes the others and exits nonzero.
A LinkedIn reference is a numeric ID or an HTTPS posting URL, including the link in a LinkedIn job alert email and a search page address with `currentJobId=`. A Workday or SmartRecruiters reference is a search result's `url`, and SmartRecruiters also takes the posting's address with its title slug. Any other reference is an error, and nothing is fetched.

Library callers use the `postings` function of `jobrake.sites.linkedin`, `jobrake.sites.workday`, or `jobrake.sites.smartrecruiters`, which never raises `Stopped`.
It maps each ID or URL to its whole job, or to `None` when the site reports the posting gone.
A reference whose request failed, or whose response jobrake cannot read, is absent from the result, and calling the function again retries it.

### Fetch selected results

For a large search, omit `-d` and fetch only the postings you want:

```python
import asyncio

from jobrake import HttpxFetcher, scrape
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
        return await linkedin.postings(fetcher, urls)


postings = asyncio.run(main())
```

## Employer boards

Many employers publish their openings on a board that their applicant tracking system (ATS) hosts.
jobrake reads Ashby, Greenhouse, Lever, SmartRecruiters, Workable, and Workday boards. A search names one employer's board with `--board | -b`.
An Ashby, Greenhouse, Lever, or Workable search returns every posting on the board:

```sh
jobrake greenhouse search -b airbnb
jobrake greenhouse search -b anthropic -o anthropic.jsonl
jobrake ashby search -b openai -o openai.csv
jobrake lever search -b spotify
jobrake workable search -b huggingface
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("greenhouse", board="airbnb"))
```

These searches take no query, result limit, or filters. Ashby, Greenhouse, and Workable apply none.
Lever filters only on the employer's own labels for location, team, department, and commitment, which must match exactly, so jobrake offers none of them.
To narrow the postings, [pipe the results](#pipe-results) through `jq` or load them into another tool.
SmartRecruiters and Workday search on the server, as [Search a board](#search-a-board) describes.

### Find a board

The board token is the last part of the board's address:

- Greenhouse: `airbnb` in `boards.greenhouse.io/airbnb`, or `anthropic` in `job-boards.greenhouse.io/anthropic`.
- Ashby: `openai` in `jobs.ashbyhq.com/openai`.
- Lever: `spotify` in `jobs.lever.co/spotify`. A board on Lever's EU host, `jobs.eu.lever.co/<token>`, works the same way.
- Workable: `huggingface` in `apply.workable.com/huggingface`.
- SmartRecruiters: `BoschGroup` in `jobs.smartrecruiters.com/BoschGroup`. In our tests, capitals did not matter.

A token the site does not know stops the search with an error that says so, except on SmartRecruiters.
SmartRecruiters answers a token it does not know as it answers a board with no postings, so jobrake cannot tell the two apart.
Either way the search returns no postings and logs that the token may be misspelled. Check the token against the board's address before you conclude that the employer has no openings.

Workday has no board token. Pass the address of the employer's job search page instead, copied from the browser, such as `https://zillow.wd5.myworkdayjobs.com/Zillow_Group_External`.
The address has the form `https://<tenant>.wd<n>.myworkdayjobs.com/<site>`, with or without a language part such as `en-US` before the site name. A posting's address on the same site works too.
Addresses on `myworkdaysite.com` are not supported. An address jobrake cannot read stops before any request with an error that shows the expected form, and a site name Workday does not know stops the search with an error that says so.

### Search a board

A SmartRecruiters search applies a query and filters on the server:

```sh
jobrake smartrecruiters search -b BoschGroup -q engineer
jobrake smartrecruiters search -b BoschGroup --remote --max-age-hours 72 -n 500 -o bosch.csv
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("smartrecruiters", board="BoschGroup", query="engineer"))
```

`--query | -q` searches posting titles and locations. `--max-age-hours | -a` keeps postings released within that many hours, and `--remote` keeps postings the employer marks remote.
`--results | -n` defaults to 100 here, not 10, because an employer board is usually read whole. Raise it to read a large board: Bosch Group's board held more than 5,000 postings in our tests.

A Workday search applies a query on the server:

```sh
jobrake workday search -b https://zillow.wd5.myworkdayjobs.com/Zillow_Group_External -q analyst
jobrake workday search -b https://zillow.wd5.myworkdayjobs.com/Zillow_Group_External -n 100 -d -o zillow.jsonl
```

```python
import asyncio

from jobrake import scrape

board = "https://zillow.wd5.myworkdayjobs.com/Zillow_Group_External"
jobs = asyncio.run(scrape("workday", board=board, query="analyst", details=True))
```

`--query | -q` is Workday's keyword search, and `--results | -n` caps the postings returned, 20 by default.
Each employer defines its own Workday filters, such as job category or country, so jobrake offers no location, remote, or age filter for Workday.
Workday publishes no documentation for this API. The behavior described here was measured on NVIDIA's career site in October 2026, and another employer's site may differ.

[Fields by site](reference.md#fields-by-site) lists what a record from each board carries.

## EconJobMarket

[EconJobMarket](https://econjobmarket.org) (EJM) is the job market site for economists: academic positions, postdocs, pre-docs, and research jobs at central banks and consultancies.
jobrake reads EJM's public ad feed. A search returns every open ad:

```sh
jobrake econjobmarket search
jobrake econjobmarket search -o ejm.jsonl
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("econjobmarket"))
```

A search takes no query, result limit, or filters, because EJM applies none.
To narrow the ads, [pipe the results](#pipe-results) through `jq` or load them into another tool:

```sh
jobrake econjobmarket search \
  | jq -r '.[] | select(any(.locations[]; .country_code == "DE")) | [.expires_at, .company, .title] | @tsv'
```

[EconJobMarket fields](reference.md#econjobmarket-fields) lists what a record carries.

### EconJobMarket terms

EJM offers the feed "for personal use and for academic research projects".
To redisplay EJM ads on your own website, you must notify EJM and get EJM's approval first.
Any use of the feed must follow EJM's Terms of Use, Privacy Policy, and Research Data Usage Policy.
See [Accessing the EJM Ad Feed](https://backend.econjobmarket.org/docs/ad-redisplay/Ad-Redisplay.0.md).

## Read and save results

Every job is a dictionary. [Returned fields](reference.md#returned-fields) describes its keys, and [Fields by site](reference.md#fields-by-site) lists the details each site fills.

### Output formats

A search or a `postings` command writes compact JSON to stdout. `--output | -o` writes a new file instead and refuses to overwrite an existing one.
`--format | -f` chooses `json`, `jsonl`, or `csv`, and defaults to the extension of `--output`.
A search that returns no jobs writes no file, and the output directory must already exist.

```sh
jobrake ... -o jobs.csv
jobrake ... -o jobs.txt -f jsonl
```

The formats represent unavailable fields differently.

- JSON writes one array, using `null` for unavailable summary values.
- JSONL writes one job per line with the same keys as JSON.
- CSV writes every field as a column and leaves unavailable cells empty. Its `locations` column holds the place names, separated by `; `, without their parts, and its `site_data` column holds the site's fields as JSON. A place name can itself contain `; `, such as Greenhouse's `Remote, Canada; Remote, United States`, so read JSON or JSONL to count places.

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
jobrake indeed search -q "data scientist" -c us -n 2 \
  | jq -r '.[] | [.date, .title, .company, .url] | @tsv'
```

## Use the Python API

`scrape()` creates and closes an HTTP client when `fetcher` is omitted.
Library calls log under the `jobrake` logger, and your application sets its level and handlers.
jobrake logs INFO records whose `progress` attribute holds `(done, total)` while a LinkedIn, Indeed, Workday, or SmartRecruiters search reads its pages, and while LinkedIn, Workday, or SmartRecruiters fetches posting details.
A search counts its postings toward `results`, or toward the site's own limit when that is smaller, and stops below `total` when the site runs out first.
While it fetches details, LinkedIn reads several posting pages concurrently, counts cached pages at the start, and advances progress as each read finishes.
The CLI draws its progress line from these records, and a handler of your own can do the same:

```python
import logging
import sys


class Progress(logging.Handler):
    def emit(self, record):
        if progress := getattr(record, "progress", None):
            print("\r%d/%d" % progress, end="", file=sys.stderr)


logger = logging.getLogger("jobrake")
logger.setLevel(logging.INFO)
logger.addHandler(Progress())
```

A fetcher you supply is yours to close.
Use its context manager when several calls should share one connection pool, as the example under [Fetch selected results](#fetch-selected-results) does.

To use another HTTP client or a browser, implement the `Fetcher` protocol from `jobrake.fetchkit`: an async `fetch(url, *, headers=None, json=None, follow_redirects=True)` that sends a POST when `json` is given.
With `follow_redirects=False`, return the first response, including its `Location` header. LinkedIn uses this to pace each redirect hop.
`fetch` returns a `FetchResult` and reports a failed request in its `error`. A status of 400 or more sets `error` on its own.
An exception your own `Fetcher` raises propagates out of `scrape()`.

## Request limits and partial results

A failed request ends a search with `Stopped`, and so does a page that ends it short of the total the site reported. Its `partial` holds the jobs collected before the search stopped:

```python
from jobrake import Stopped, scrape


async def main():
    try:
        return await scrape("indeed", query="economist", country="us", results=500)
    except Stopped as stop:
        print(stop)  # what failed
        return stop.partial  # the jobs collected before it
```

The CLI writes those jobs and exits 1. When there are none it writes nothing, so empty output such as `[]` always comes from a search that completed. Reaching a site's own result cap is not a failure. jobrake warns on stderr and returns what the site served.
On Indeed, EconJobMarket, and the employer boards, jobrake skips a posting it cannot read and leaves out a field it cannot read.

[Requests by site](reference.md#requests-by-site) gives each site's result cap, pacing, and retries.

## Cache location and lifetimes

jobrake keeps the LinkedIn postings it fetched in one SQLite file under your user cache directory: `~/Library/Caches/jobrake/` on macOS, `$XDG_CACHE_HOME/jobrake/` on Linux, or `~/.cache/jobrake/` when that variable is unset, and `%LOCALAPPDATA%\jobrake\` on Windows.
No other site is cached.

A cached posting stays fresh for seven days and is fetched again after that. A posting that LinkedIn reports gone is not cached.
An upgrade keeps the cache, and a posting whose cached copy no longer fits the job fields is fetched again.
After an upgrade that reads posting pages better, a cached posting keeps the fields the earlier version read until it expires.

To refetch every posting at once, move `jobrake.sqlite3` out of the cache directory, or delete it.
To bypass the cache for one run, point `JOBRAKE_CACHE_PATH` at a new file:

```sh
JOBRAKE_CACHE_PATH="$(mktemp -d)/jobrake.sqlite3" jobrake linkedin postings 4449382178
```

Two environment variables configure the cache:

| Variable             | Default             | Effect                                                 |
| -------------------- | ------------------- | ------------------------------------------------------ |
| `JOBRAKE_CACHE_PATH` | platform user cache | Path to the SQLite file, with home-directory expansion |
| `JOBRAKE_CACHE_TTL`  | 604800              | Seconds a cached posting is served before a refetch    |

The lifetime must be a positive number of seconds. An invalid value draws a warning and falls back to the default.

A storage failure disables the cache with a warning, and scraping carries on without it.

## Other job boards

Glassdoor is not planned because it is now [part of Indeed](https://web.archive.org/web/20260704043638/https://www.glassdoor.com/about/).
AEA JOE is not planned because its [listings](https://www.aeaweb.org/joe/listings) forbid scraping or collecting them without the American Economic Association's written permission. Its listings page offers its own XML and Excel downloads.
Wellfound is not planned because it has no public API, and its job data sits behind a Cloudflare challenge that only a browser passes.
