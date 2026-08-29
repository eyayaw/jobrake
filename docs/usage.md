# Usage

## Command line

Run `jobrake -h` to see the provider commands, then `jobrake PROVIDER -h` for that provider's options. The default output is compact JSON on stdout.

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
`--output | -o` writes jobs to a file instead of stdout and replaces an existing file.
If the search returns no jobs, the path remains untouched. The output directory must already exist.

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
> You can combine the files with `cat` or import them to `duckdb`.
>
> ```sh
> jobrake ... -o runs/2026-08-10.jsonl
> jobrake ... -o runs/2026-08-11.jsonl
> cat runs/*.jsonl > jobs.jsonl
>
> duckdb -c "select * from read_json('runs/*.jsonl', union_by_name=true)"
> ```

## The Job data model

Every job is a flat dictionary, with three groups of keys.

1) The **identity keys** are `site`, `id`, and `url`.
2) The **summary keys** are `title`, `company`, `location`, and `date`.
All seven keys are present, with `None` for an unavailable summary value.

3) **Detail keys** appear only when their value is available.
Their absence can mean that the provider omitted the value, does not publish it, or that jobrake did not fetch the posting page.

Shared details use the same field names. However, there are provider-specific fields.
`apply_type`, `applicants`, `experience_months`, and `education` are present only in LinkedIn,
and `is_remote` and `apply_url` on Indeed. Indeed includes detail fields in search results.
Use `--details | -d` or `details=True` to fetch each LinkedIn posting page and add its detail fields.

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

A custom fetcher passed belongs to the caller, i.e., it may need to be closed.
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
