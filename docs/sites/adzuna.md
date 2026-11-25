# Adzuna (`adzuna`)

[Adzuna](https://www.adzuna.com) collects postings from employers, agencies, and other job boards
into one search per country. jobrake reads it through the undocumented API of Adzuna's Android app.

```sh
jobrake adzuna search -c gb -q economist -l London -n 20
jobrake adzuna search -c de -q "data scientist" -l Berlin -r 25 -a 72 --details
jobrake adzuna search -c us -q "health economist" -l "New York" -o adzuna.jsonl
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(
    scrape("adzuna", country="gb", query="economist", location="London", details=True)
)
```

## Options

`--country` is required and names one of Adzuna's editions: `at`, `au`, `be`, `br`, `ca`, `ch`,
`de`, `es`, `fr`, `gb`, `in`, `it`, `mx`, `nl`, `nz`, `pl`, `sg`, `us`, or `za`.

In our tests, a `--location` search without `--radius` returned the same postings as `-r 0`.
Some of them name a nearby town, such as Villeurbanne for Lyon.

Adzuna filters by whole days, so `--max-age-hours` rounds up: `-a 25` reaches back two days.

## Fields

Search results carry the title, company, place, date, and employment type. `--details` adds the
description, the salary, `posted_at`, `expires_at`, and coordinates
([every key](../reference.md#fields-by-site)). A posting Adzuna collected from another board also
gets that board's name and the application link.

- A salary comes only with `--details`. It is the salary the employer advertised, which Adzuna
  converts to a yearly figure. We leave out Adzuna's own estimates, and the salary of a posting
  Adzuna hosts itself, because its page labeled monthly pay as yearly in our tests.
- `--details` moves `date` to the day Adzuna created the posting, which can be months before
  the date a search shows.
- `url` is the posting on Adzuna, and `apply_url` is the posting at its source.
- `employment_type` holds the work schedule, such as `full_time`, and `site_data.contract_type`
  says whether the job is `permanent` or a `contract`. When a posting has no schedule,
  `employment_type` holds the contract type instead. With `--details`, `site_data` also holds
  Adzuna's `category` and the `source` board.

Adzuna has no `postings` command, because reading a posting from another board takes a hash that
only its search result carries. To retry the postings a `--details` search could not read, run
the search again: the postings it already read come from the cache.

## Requests

In our tests, Adzuna stopped at 1,000 postings per search. Search by city or with a narrower query
to reach more.
