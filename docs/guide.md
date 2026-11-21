# jobrake guide

This guide shows how to do common tasks with jobrake, across sites.
The [README](../README.md) covers installation and the options every site shares.
Each site's page under [sites](sites/) gives its own options, fields, and limits,
and the [reference](reference.md) describes the record, the commands, and the Python API.

- [Search by keyword and place](#search-by-keyword-and-place)
- [Filter by employer](#filter-by-employer)
- [Read an employer's board](#read-an-employers-board)
- [Collect postings from several sites](#collect-postings-from-several-sites)
- [Pipe results](#pipe-results)
- [Fetch posting details](#fetch-posting-details)
- [Recover from a stopped search](#recover-from-a-stopped-search)
- [Use jobrake from Python](#use-jobrake-from-python)
- [Refresh the cache](#refresh-the-cache)

## Search by keyword and place

Indeed, LinkedIn, and StepStone search a whole job market by keywords and place.
Choose a site and supply a job title or keywords:

```sh
jobrake indeed search -q "data scientist" -c nl -l Amsterdam -n 2
jobrake linkedin search -q "data scientist" -l "Amsterdam, North Holland, Netherlands" -n 2
jobrake stepstone search -q "data scientist" -l Berlin -n 2
```

The commands ask for two postings near Amsterdam, Netherlands, or Berlin,
but each site names a place its own way.
Indeed searches one country edition at a time, so `--country` is required,
and `--location` narrows that edition to a city or area within it.
LinkedIn has no editions: pass the place as text to `--location`, or its ID to `--geoid`,
and leave `--country` out.
StepStone searches Germany only, so `--location` is a German city or postal code.
When a site does not recognize a place, its `places` lookup turns a name into one it does:

```sh
jobrake linkedin places "amsterdam"
jobrake indeed places "amsterdam" -c nl
```

Each site's page, [Indeed](sites/indeed.md), [LinkedIn](sites/linkedin.md), and
[StepStone](sites/stepstone.md), gives its query syntax, how it reads a place, and its radius.

## Filter by employer

Indeed and LinkedIn filter by employer identifier, and both need a lookup to turn a name into
one. Look up the company name, then pass the `id` of the employer you want to `--company-ids`:

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

```sh
jobrake indeed search -c nl -q "data scientist" --company-ids 8e8f030e53ea29e4
jobrake linkedin search -l "Netherlands" --company-ids 11348 215713
```

The Indeed key selects _Booking.com_, and the LinkedIn IDs select _Booking.com_ and
_ING Nederland_.
An Indeed search takes one employer and a LinkedIn search several, as the
[Indeed](sites/indeed.md#employers) and [LinkedIn](sites/linkedin.md#employers) pages explain.

> [!TIP]
> Leave out `-q` to search without keywords, on any site that takes a query.
> One good use case is searching for openings from a certain company.

## Read an employer's board

Many employers publish their openings on a board that their applicant tracking system (ATS) hosts.
jobrake reads Ashby, Greenhouse, Lever, Personio, SmartRecruiters, Workable, and Workday boards.
A search names one employer's board with `--board | -b`.
An Ashby, Greenhouse, Lever, Personio, or Workable search returns every posting on the board:

```sh
jobrake greenhouse search -b airbnb
jobrake ashby search -b openai -o openai.csv
jobrake lever search -b spotify
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("greenhouse", board="airbnb"))
```

The board token is the part of the board's address that names the employer,
such as `airbnb` in `boards.greenhouse.io/airbnb`, and each site's page shows where to find it.
Workday has no token: pass the address of the employer's job search page instead.
These five searches take no query, result limit, or filters.
To narrow the postings, [pipe the results](#pipe-results) through `jq`
or load them into another tool.
SmartRecruiters and Workday search on the server, with a query and a result limit.

A token the site does not know stops the search with an error that says so, except on
SmartRecruiters, which answers it as a board with no postings: check the token against the board's
address, as its [page](sites/smartrecruiters.md) explains.

## Collect postings from several sites

A CSV has the same columns whichever site wrote it, so the files of several searches combine into
one. This run collects the economics postings of four sites:

```sh
mkdir -p runs
jobrake aea search --max-age-hours 168 -o runs/aea.csv
jobrake econjobmarket search -o runs/econjobmarket.csv
jobrake inomics search -n 500 -o runs/inomics.csv
jobrake academictransfer search -q economics -o runs/academictransfer.csv
awk 'FNR > 1 || NR == 1' runs/*.csv > economics.csv
```

The `awk` line keeps the header of the first file and drops the others.
A site's own fields stay in the `site_data` column as JSON, and a column a site does not fill stays
empty. Each site's page lists the fields it fills, and INOMICS adds the description only with `-d`.
`site` and `id` together name one posting, so use them to drop a posting that two runs share.

> [!TIP]
> JSONL suits a run you repeat, a daily one for instance.
> Combine the files with `cat`, or read the whole directory into DuckDB.
>
> ```sh
> jobrake inomics search -n 500 -o runs/2026-08-10.jsonl
> jobrake inomics search -n 500 -o runs/2026-08-11.jsonl
> cat runs/*.jsonl > jobs.jsonl
>
> duckdb -c "select * from read_json('runs/*.jsonl', union_by_name=true)"
> ```

`--output` refuses a file that exists, so give each run its own name, such as the date.

## Pipe results

Pipe stdout into another program to reshape the jobs.
[`jq`](https://github.com/jqlang/jq) picks out fields:

```sh
jobrake indeed search -q "data scientist" -c us -n 2 \
  | jq -r '.[] | [.date, .title, .company, .url] | @tsv'
```

A site without a date filter can be filtered on `date` afterwards:

```sh
jobrake inomics search -n 500 | jq '[.[] | select(.date != null and .date >= "2026-11-14")]'
```

## Fetch posting details

Some sites send search cards without the description and other details. On LinkedIn, Workday,
SmartRecruiters, StepStone, and INOMICS, add `--details | -d` (`details=True`) to fetch each
posting's page during the search, and the other sites return the details with the search itself.
If some pages could not be fetched, the CLI still writes every card, exits 1, and prints the
`postings` command that retries the rest.

### Fetch known postings

Fetch postings you already know without repeating a search:

```sh
jobrake linkedin postings 4449382178
jobrake stepstone postings https://www.stepstone.de/job/14569042
```

Sites take postings down over time, so the examples above may be gone.
Use references from a recent search, and name as many as you like.
The [reference](reference.md#postings) describes the result, and each site's page lists the
references it takes.
To match a link someone sends you to a posting you already stored, without a request, use
[`jobrake.identify`](reference.md#python-api).

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

The two calls share one fetcher, and so one connection pool. A posting `postings` could not fetch
is left out of its result, so calling it again on the missing URLs retries them.

## Recover from a stopped search

A search that cannot finish raises [`Stopped`](reference.md#stopped), whose `partial` holds the
jobs it collected. Keep them, and rerun later for the rest:

```python
from jobrake import Stopped, scrape


async def main():
    try:
        return await scrape("indeed", query="economist", country="us", results=500)
    except Stopped as stop:
        print(stop)  # what failed
        return stop.partial  # the jobs collected before it
```

The CLI writes those jobs and exits 1, so a script can tell a partial run from a complete one.
After a details search, `stop.failed` holds the URLs to pass to the site's `postings`.

## Use jobrake from Python

To check a batch of planned searches before any of them runs, such as searches read from a config
file, call `jobrake.check` on each. It raises what the search would, without a request:

```python
import jobrake

jobrake.check("indeed", query="economist", country="zz")  # ValueError: unknown Indeed country 'zz'
```

The [reference](reference.md#python-api) lists every function, the `.check` of each site function,
and the `Fetcher` protocol for another HTTP client.

### Show progress

The CLI draws its progress line from the `progress` attribute of jobrake's INFO log records,
and a handler of your own can do the same:

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

## Refresh the cache

jobrake serves a posting it fetched in the last seven days from its cache.
To refetch every posting at once, move `jobrake.sqlite3` out of the cache directory, or delete it.
To bypass the cache for one run, point `JOBRAKE_CACHE_PATH` at a new file:

```sh
JOBRAKE_CACHE_PATH="$(mktemp -d)/jobrake.sqlite3" jobrake linkedin postings 4449382178
```

The [reference](reference.md#configuration) gives the cache directory on each platform and the
variable that sets the lifetime.
