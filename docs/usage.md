# Usage

## Command line

Run `jobrake -h` to see the commands, then `jobrake <command> -h` for its options. The default output is compact JSON on stdout.

```sh
jobrake indeed -q "data scientist" -c usa -n 2
```

Stdout can be piped into another program.
For example, you can select fields with [`jq`](https://github.com/jqlang/jq):

```sh
jobrake indeed -q "data scientist" -c usa -n 2 \
  | jq -r '.[] | [.date, .title, .company, .url] | @tsv'
```

### Output formats

`--format | -f` accepts `json`, `jsonl`, or `csv`.
`--output | -o` writes jobs to a new file instead of stdout.
If the search returns no jobs, jobrake does not create the file. The output directory must already exist.

When `--format` is absent, jobrake uses the file extension from `--output`.
Note that an explicit format takes precedence over the extension.

```sh
jobrake ... -o jobs.csv
jobrake ... -o jobs.txt -f jsonl
```

The formats represent unavailable fields differently.

- JSON writes one array. Identity and summary keys are always present; unavailable detail keys are omitted.
- JSONL writes one job per line with the same keys as JSON.
- CSV writes every model field as a column and fills unavailable cells with an empty string.

> [!tip]
> JSONL is suitable for incremental fetching, say, daily.
> You can combine the files with `cat` or load them into DuckDB.
>
> ```sh
> jobrake ... -o runs/2026-08-10.jsonl
> jobrake ... -o runs/2026-08-11.jsonl
> cat runs/*.jsonl > jobs.jsonl
>
> duckdb -c "select * from read_json('runs/*.jsonl', union_by_name=true)"
> ```

### Fetching a posting you already have

A search result tells you enough to spot a posting worth reading. Fetch that one by ID or URL instead of searching again:

```sh
jobrake details linkedin 4449382178
jobrake details linkedin https://nl.linkedin.com/jobs/view/data-scientist-at-acme-4449382178
```

Name as many postings as you like. The command takes the same `--output | -o` and `--format | -f` options as a search, and `--no-cache` to refetch a posting jobrake already stored.
Each job reads like a search result with `--details`: the identity and summary keys, plus whichever detail keys the posting publishes.
A posting that is gone or unreachable is reported on stderr and left out. If none resolve, the command exits nonzero and writes nothing.

The URL a search prints is the cheapest reference. [Provider behavior](providers.md) explains what the others cost.

## The Job data model

Every job is a flat dictionary, with three groups of keys.

1) The **identity keys** are `site`, `id`, and `url`.
2) The **summary keys** are `title`, `company`, `location`, and `date`.
All seven keys are present, with `None` for an unavailable summary value.

3) **Detail keys** appear only when their value is available.
Their absence can mean that the provider omitted the value, does not publish it, or that jobrake did not fetch the posting page.

Shared details use the same field names, and a few fields come from one provider only.
LinkedIn postings can supply `apply_type`, `applicants`, `experience_months`, and `education`.
Indeed returns available details with search results, including `is_remote`, `apply_url`, and `language`.
Use `--details | -d` or `details=True` to fetch each LinkedIn posting page and add its detail fields.

For Indeed postings, `language` holds the provider's language code when available, such as `"en"` or `"nl"`.
To keep English postings:

```python
english = [job for job in jobs if job.get("language") == "en"]
```

LinkedIn job dictionaries omit `language`. CSV includes the column, with an empty cell when the value is unavailable.

## Library use

`scrape()` creates and closes an HTTP client when `fetcher` is omitted.
Library calls emit records through loggers under `jobrake`. The application controls their levels and handlers.

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

The caller owns any fetcher it supplies and must close it when the fetcher holds resources.
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
Indeed needs the JSON `post()` operation from `PostFetcher`.
`BaseFetcher` records ordinary request exceptions in `FetchResult.error`, and cancellation propagates.
If another `Fetcher` implementation raises, `scrape()` lets the exception propagate.

## Partial results

Fetch errors may leave partial results.
[Provider behavior](providers.md) explains when fetching stops and which results are retained.

## Cache location and lifetimes

jobrake keeps posting fields and LinkedIn place resolutions in one SQLite file under your user cache directory (`~/Library/Caches/jobrake/` on macOS, `$XDG_CACHE_HOME/jobrake/` on Linux, `%LOCALAPPDATA%\jobrake\` on Windows). Posting fields remain fresh for seven days and are eligible for deletion after 30 days. Place resolutions and gone-posting markers are kept indefinitely. Three environment variables configure the cache:

| Variable | Default | Effect |
| --- | --- | --- |
| `JOBRAKE_CACHE_PATH` | platform user cache | Path to the SQLite file, with home-directory expansion |
| `JOBRAKE_CACHE_TTL` | 604800 | Seconds a stored field is served before a refetch |
| `JOBRAKE_CACHE_RETENTION` | 2592000 | Seconds a field stays on disk, counted from when it was stored |

Opening the database deletes posting fields older than the retention period. If the configured retention is shorter than the freshness period, jobrake raises retention to match.

Unset or empty lifetime variables use the defaults. Other values must be finite, positive numbers of seconds. Invalid values produce a warning and fall back to the defaults. If home-directory expansion fails, jobrake warns and uses the default cache path. A storage failure logs a warning and disables that cache instance while scraping continues.

When constructing `jobrake.cache.Cache`, library callers can supply explicit lifetimes with `Cache(path, ttl=..., retention=...)`. Each supplied argument overrides its environment variable. An explicit retention must be finite and at least as long as the resolved freshness period. Invalid explicit lifetimes raise `ValueError`.
