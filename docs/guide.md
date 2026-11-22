# jobrake guide

Each section is one task that spans several sites.
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

The searches in this section run on Indeed, LinkedIn, and StepStone.
Choose a site and supply a job title or keywords:

```sh
jobrake indeed search -q "data scientist" -c nl -l Amsterdam -n 2
jobrake linkedin search -q "data scientist" -l "Amsterdam, North Holland, Netherlands" -n 2
jobrake stepstone search -q "data scientist" -l Berlin -n 2
```

Each site names a place its own way.
Indeed searches one country edition at a time, so `--country` is required,
and `--location` narrows that edition to a city or area within it.
LinkedIn has no editions: pass the place as text to `--location`, or its ID to `--geoid`,
and leave `--country` out.
StepStone searches Germany only, so `--location` is a German city or postal code.

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

The Indeed search keeps Booking.com's postings.
The LinkedIn search keeps those of Booking.com and of ING Nederland, whose ID is `215713`.
Indeed takes one employer per search, and LinkedIn several.

> [!TIP]
> Leave out `--query` to search without keywords, on any site that takes a query.
> One good use case is searching for openings from a certain company.

## Read an employer's board

Many employers publish their openings on a board that their applicant tracking system (ATS) hosts.
jobrake reads boards on Ashby, Greenhouse, Lever, Personio, SmartRecruiters, Workable, and Workday.
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

These sites filter nothing on their side, so [pipe the results](#pipe-results) to narrow a board
down.
SmartRecruiters and Workday take a query and a result limit, and SmartRecruiters also filters by age and by remote work.

The board token is the part of the board's address that names the employer,
such as `airbnb` in `boards.greenhouse.io/airbnb`.
Workday has no token. Pass the address of the employer's job search page instead.

On [SmartRecruiters](sites/smartrecruiters.md#options), a misspelled token returns an empty board
instead of an error, so check the token before you conclude that an employer has no openings.

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

The `awk` line drops the header row of every file but the first.
A site's own fields stay in the `site_data` column.
The INOMICS rows have no description unless you add `--details`.
`site` and `id` together name one posting, so use them to drop a posting that two runs share.

> [!TIP]
> JSONL suits a run you repeat, a daily one for instance.
> `--output` refuses a file that exists, so give each run its own name, such as the date.
> Combine the files with `cat`, or read the whole directory into DuckDB.
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

A LinkedIn, Workday, SmartRecruiters, StepStone, or INOMICS search returns each posting without
its description. Add `--details` (`details=True`) to fetch each posting during the search.
The other sites return the description with the search itself.
A posting that could not be fetched keeps its search result, so you still get every posting.
Fetch the missed ones later with the site's `postings`.

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

The two calls share one fetcher, and so one connection pool.
`postings` leaves out a posting it could not fetch. Call it again with the missing URLs to retry.

## Recover from a stopped search

A search that cannot finish raises [`Stopped`](reference.md#stopped).
Its `partial` holds the postings collected before the failure:

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

jobrake.check("indeed", query="economist", country="zz")  # ValueError: unknown Indeed country 'zz'
```

## Show progress

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

A cached posting stays fresh for seven days and is fetched again after that.
To refetch every posting at once, move `jobrake.sqlite3` out of the
[cache directory](reference.md#configuration), or delete it.
To bypass the cache for one run, point `JOBRAKE_CACHE_PATH` at a new file:

```sh
JOBRAKE_CACHE_PATH="$(mktemp -d)/jobrake.sqlite3" jobrake linkedin postings 4449382178
```
