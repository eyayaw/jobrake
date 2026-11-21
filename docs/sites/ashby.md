# Ashby (`ashby`)

jobrake reads one employer's board on [Ashby](https://www.ashbyhq.com) through Ashby's public
Job Posting API. A search returns every posting on the board with its description:

```sh
jobrake ashby search -b openai
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("ashby", board="openai"))
```

A search is one request. A failed request raises [`Stopped`](../reference.md#stopped) with an
empty `partial`.

## Options

`--board | -b` takes the board token, the part of the board's address that names the employer:
`openai` in `jobs.ashbyhq.com/openai`.
A token Ashby does not know stops the search with an error that says so.

A search takes no query, result limit, or filters, because Ashby applies none.
To narrow the postings, pipe the results through `jq` or load them into another tool:

```sh
jobrake ashby search -b openai | jq '[.[] | select(.workplace_type == "remote")]'
```

## Fields

An Ashby [record](../reference.md#the-record) carries `title`, `locations`, `date`, and
`description`, and, when present, the details `posted_at`, `employment_type`, `department`, `team`,
`apply_url`, `workplace_type`, `salary_min`, `salary_max`, `salary_currency`, `salary_period`, and
`site_data`.

- `company` is always `None`, because Ashby's response never names the employer.
  The board token tells you whose board it is.
- `posted_at` is the time the posting was published, and `date` is its calendar date.
- `locations` holds the posting's primary location first and then its other places,
  named as the employer entered them, such as `Remote (US)` and `Remote (Canada)`.
  Each place carries the `city` and `region` of its address as Ashby spells them,
  and `region` can be a code or a name, such as `NY` or `Ontario`.
- Ashby gives the country as a name, such as `USA` or `United Kingdom`,
  so an Ashby place has no `country_code`.
- `workplace_type` is `remote`, `hybrid`, or `on_site`, as the employer set it,
  and is absent when the employer set none.
- The salary fields come from the posting's first salary range,
  and `salary_period` is `HOUR`, `DAY`, `WEEK`, `MONTH`, or `YEAR`.
- `team` is the posting's team, such as `Solutions Consulting`.
  `site_data` holds its `summaryComponents` as Ashby sends them,
  so equity, commission, and bonus appear there beside the salary range.
  In our test on one board, 124 of 172 postings listed an equity value and 40 a commission.
- `url` and `apply_url` point to the posting on `jobs.ashbyhq.com`.
- A search also returns postings the employer marked unlisted,
  which Ashby intends for direct links only.
- In our test on one board of 172 postings, every posting carried a location, a publish time,
  and an employment type, 165 carried a salary range, 162 a city, and 16 were remote.
