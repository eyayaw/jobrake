# Ashby (`ashby`)

[Ashby](https://www.ashbyhq.com) hosts employer job boards at `jobs.ashbyhq.com/<employer>`.
jobrake reads a board via Ashby's public Job Posting API and returns every posting with its full
description, including unlisted postings:

```sh
jobrake ashby search -b openai
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("ashby", board="openai"))
```

## Options

Pass the employer slug from the board URL to `--board` (e.g., `openai` from `jobs.ashbyhq.com/openai`).

Ashby's public endpoint doesn't support server-side filtering, so pipe to `jq` if you only want a
subset (such as remote roles):

```sh
jobrake ashby search -b openai | jq '[.[] | select(.workplace_type == "remote")]'
```

## Fields

Results include the title, locations, publish timestamp, and full description, along with
employment type, department, team, workplace type, application URL, and salary range whenever the
employer fills them in. See the [reference](../reference.md#fields-by-site) for the complete field
table.

- `company` is always `None` because Ashby's API response doesn't include the employer's name.
- Ashby returns country names (`USA`, `United Kingdom`) rather than ISO codes, so `country_code` is
  left out. `region` may be either an abbreviation (`NY`) or a full name (`Ontario`).
- Structured salary fields are taken from the first salary range, with `salary_period` set to
  `HOUR`, `DAY`, `WEEK`, `MONTH`, or `YEAR`.
- `site_data` stores Ashby's raw `summaryComponents`, which is where equity, bonus, or commission
  details appear alongside salary.
- Unlisted postings (intended for direct links) are also returned by Ashby's API.
