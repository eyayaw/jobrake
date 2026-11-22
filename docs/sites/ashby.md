# Ashby (`ashby`)

[Ashby](https://www.ashbyhq.com) hosts employers' job boards at `jobs.ashbyhq.com/<employer>`,
and jobrake reads one of them through Ashby's public Job Posting API.
A search returns every posting on the board with its description, unlisted ones included:

```sh
jobrake ashby search -b openai
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("ashby", board="openai"))
```

## Options

`--board` takes the board token, the part of the board's address that names the employer:
`openai` in `jobs.ashbyhq.com/openai`.

Ashby filters nothing on its side, so narrow the postings yourself, for example to the remote ones:

```sh
jobrake ashby search -b openai | jq '[.[] | select(.workplace_type == "remote")]'
```

## Fields

A posting carries its title, its places, its publish time, and its description, and, when the
employer set them, the employment type, the department, the team, the workplace type, the
application link, and the salary range ([every key](../reference.md#fields-by-site)).

- `company` is always `None`, because Ashby's response never names the employer.
- Ashby gives the country as a name, such as `USA` or `United Kingdom`, so a place has no
  `country_code`. Its `region` can be a code or a name, such as `NY` or `Ontario`.
- The salary fields come from the posting's first salary range,
  and `salary_period` is `HOUR`, `DAY`, `WEEK`, `MONTH`, or `YEAR`.
- `site_data` holds the posting's `summaryComponents` as Ashby sends them,
  which is where equity, commission, and bonus appear beside the salary range.
- A search also returns postings the employer marked unlisted, which Ashby intends for direct links only.

## Requests

A single request returns the whole board. If it fails, you get nothing, and `scrape` raises
[`Stopped`](../reference.md#stopped).
