# Greenhouse (`greenhouse`)

Employers using [Greenhouse](https://www.greenhouse.com) host their openings either on Greenhouse's
own domain or embedded on their company careers page (as Airbnb does). jobrake reads both through
Greenhouse's public Job Board API and returns the entire board with full descriptions:

```sh
jobrake greenhouse search -b airbnb
jobrake greenhouse search -b anthropic -o anthropic.jsonl
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("greenhouse", board="airbnb"))
```

## Options

Pass the employer's URL token to `--board`, such as `airbnb` from `boards.greenhouse.io/airbnb`
or `anthropic` from `job-boards.greenhouse.io/anthropic`.

Greenhouse's public API returns all open roles without server-side filtering. Use `jq` or Python to
slice the output:

```sh
jobrake greenhouse search -b airbnb | jq '[.[] | select(.title | test("data"; "i"))]'
```

## Fields

Postings include title, location, and description, plus company name, first-published timestamp,
department, and language when available (listed in the [reference](../reference.md#fields-by-site)).
Because Greenhouse leaves salary, employment type, and workplace type to arbitrary per-employer
custom fields, jobrake omits them.

- `locations` has one entry using the employer's exact location string, which may bundle several
  places (like `Remote, Canada; Remote, United States`).
- `department` is populated only when a posting belongs to a single department.
- `expires_at` gives the application deadline when set, though few postings include it.
- `url` points to the employer's own careers page when hosted there (like Airbnb), or to
  `job-boards.greenhouse.io` otherwise.
