# jobrake guide

A site's own options and quirks are on its page under [sites](sites/).

- [Search by keyword and place](#search-by-keyword-and-place)
- [Filter by employer](#filter-by-employer)
- [Read an employer's board](#read-an-employers-board)
- [Collect postings from several sites](#collect-postings-from-several-sites)
- [Pipe results](#pipe-results)
- [Fetch posting details](#fetch-posting-details)
- [Recover from a stopped search](#recover-from-a-stopped-search)
- [Check searches before they run](#check-searches-before-they-run)
- [Show progress](#show-progress)
- [Refresh the cache](#refresh-the-cache)

## Search by keyword and place

Adzuna, Indeed, LinkedIn, StepStone, and XING search by keyword and place.
Choose one and supply a job title or keywords:

```sh
jobrake adzuna search -q "data scientist" -c nl -l Amsterdam -n 2
jobrake indeed search -q "data scientist" -c nl -l Amsterdam -n 2
jobrake linkedin search -q "data scientist" -l "Amsterdam, North Holland, Netherlands" -n 2
jobrake stepstone search -q "data scientist" -l Berlin -n 2
```

Location handling varies by site:
- **Adzuna and Indeed** search one country edition at a time, so `--country` is required and
  `--location` narrows the search to a city or region inside it.
- **LinkedIn** has no country editions. Pass a place name to `--location` or its ID to `--geoid`
  (no `--country`).
- **StepStone** covers Germany only, so `--location` takes a German city or postal code.
- **XING** covers Germany, Austria, and Switzerland together, accepting a city or postal code in
  any of the three.

When Indeed or LinkedIn does not recognize a place, look it up with `places` and search with a name or ID it returns:

```sh
jobrake linkedin places "amsterdam"
jobrake indeed places "amsterdam" -c nl
```

For each site's query syntax, see the [Indeed](sites/indeed.md#query) and [LinkedIn](sites/linkedin.md#query) pages.

## Filter by employer

Indeed and LinkedIn filter by employer, and both need a lookup to turn a company name into the ID a search takes:

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

Pass the `id` of the employer you want to `--company-ids`:

```sh
jobrake indeed search -c nl -q "data scientist" --company-ids 8e8f030e53ea29e4
jobrake linkedin search -l "Netherlands" --company-ids 11348 215713
```

The Indeed search returns Booking.com postings; the LinkedIn search returns postings from both
Booking.com and ING Nederland (ID `215713`).
Indeed allows one employer per search, while LinkedIn accepts several.

> [!TIP]
> Leave out `--query` to search without keywords, on any site that takes a query.
> One good use case is searching for openings from a certain company.

## Read an employer's board

Many employers publish their openings on a board that their applicant tracking system (ATS) hosts.
jobrake reads boards on Ashby, Cornerstone, Greenhouse, Lever, Personio, SmartRecruiters, Workable,
and Workday.
A search names one employer's board with `--board`.
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

These five boards don't support server-side filtering, so [pipe the results](#pipe-results) to
narrow them down.
Cornerstone, SmartRecruiters, and Workday accept a query and a result limit; Cornerstone also
filters by country and age, and SmartRecruiters by age and remote work.

The board token is the employer slug in the board's URL, like `airbnb` in
`boards.greenhouse.io/airbnb`.
Cornerstone and Workday don't use tokens; pass the employer's career site or job search URL instead.

On [SmartRecruiters](sites/smartrecruiters.md#options), a misspelled token returns an empty list
instead of an error, so double-check the token before assuming an employer has no openings.

## Collect postings from several sites

Every site writes the same CSV columns, so you can concatenate files from different boards into one
table. For example, to gather economics listings from four sites:

```sh
mkdir -p runs
jobrake aea search --max-age-hours 168 -o runs/aea.csv
jobrake econjobmarket search -o runs/econjobmarket.csv
jobrake inomics search -n 500 -o runs/inomics.csv
jobrake academictransfer search -q economics -o runs/academictransfer.csv
awk 'FNR > 1 || NR == 1' runs/*.csv > economics.csv
```

The `awk` command drops the header row from every file after the first.
Site-specific fields stay in `site_data`, and INOMICS rows won't include descriptions unless you
pass `--details`.
Together, `site` and `id` uniquely identify a posting if you need to deduplicate across runs.

> [!TIP]
> JSONL works well for recurring runs (for instance, a daily cron job).
> Since `--output` refuses to overwrite existing files, name each file by date and combine them
> with `cat` or load the whole directory into DuckDB:
>
> ```sh
> jobrake inomics search -n 500 -o runs/2026-08-10.jsonl
> jobrake inomics search -n 500 -o runs/2026-08-11.jsonl
> cat runs/*.jsonl > jobs.jsonl
>
> duckdb -c "select * from read_json('runs/*.jsonl', union_by_name=true)"
> ```

## Pipe results

Pipe stdout into another program to reshape the postings.
[`jq`](https://github.com/jqlang/jq) picks out fields:

```sh
jobrake indeed search -q "data scientist" -c us -n 2 \
  | jq -r '.[] | [.date, .title, .company, .url] | @tsv'
```

Where a site has no date filter, filter on `date` yourself:

```sh
jobrake inomics search -n 500 | jq '[.[] | select(.date != null and .date >= "2026-11-14")]'
```

## Fetch posting details

Searches on Adzuna, INOMICS, LinkedIn, SmartRecruiters, StepStone, Workday, and XING don't return
full descriptions by default. Pass `--details` (`details=True`) to fetch each posting's page during
the search. All other sites already include descriptions in search results.

If some detail fetches fail, jobrake keeps the original search summary for those postings and ends
with [`Stopped`](#recover-from-a-stopped-search), listing the missed URLs in `.failed` so you can
retry them with `<site> postings`. Adzuna doesn't have a `postings` command and leaves `.failed`
empty. Just rerun the search, and cached postings will be reused without refetching.

### Fetch known postings

Fetch postings you already know without repeating a search:

```sh
jobrake linkedin postings 4449382178
jobrake stepstone postings https://www.stepstone.de/job/14569042
```

Sites take postings down over time, so the examples above may be gone.
Use references from a recent search, and name as many as you like.
A reference is a search result's `url` or another address of the posting, such as a bare LinkedIn
posting ID ([every form](reference.md#postings)).

To match a link someone sends you to a posting you already stored, `jobrake.identify` returns the
`site` and `id` a search gives that posting:

```python
import jobrake

jobrake.identify("https://nl.indeed.com/viewjob?jk=1a2b3c4d5e6f7a8b")
# ('indeed', '1a2b3c4d5e6f7a8b')
```

### Fetch selected results

For a large search, omit `--details` and fetch only the postings you want:

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

Both calls share one fetcher and connection pool.
`postings` omits any URL it couldn't fetch. Call it again with the missing URLs to retry.

## Recover from a stopped search

If a search cannot finish, it raises [`Stopped`](reference.md#stopped) with the postings collected
so far in `.partial`:

```python
from jobrake import Stopped, scrape


async def main():
    try:
        return await scrape("indeed", query="economist", country="us", results=500)
    except Stopped as stop:
        print(stop)  # what failed
        return stop.partial  # the postings collected before it
```

After a details search, `stop.failed` holds the URLs to pass to the site's `postings`.

## Check searches before they run

To check a batch of planned searches before any of them runs, such as searches read from a config
file, call `jobrake.check` on each. It raises what the search would, without a request:

```python
import jobrake

# ValueError: Indeed has no edition for 'SI'
jobrake.check("indeed", query="economist", country="si")
```

## Show progress

The CLI renders its progress line from the `progress` attribute on jobrake's `INFO` log records,
and your own logging handler can do the same:

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

Cached postings expire after seven days.
To force a fresh fetch for everything, delete or move `jobrake.sqlite3` from your
[cache directory](reference.md#configuration).
To bypass the cache for a single run, point `JOBRAKE_CACHE_PATH` at a temporary file:

```sh
JOBRAKE_CACHE_PATH="$(mktemp -d)/jobrake.sqlite3" jobrake linkedin postings 4449382178
```
