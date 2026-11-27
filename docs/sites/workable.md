# Workable (`workable`)

jobrake reads employer boards on [Workable](https://www.workable.com) through the public API behind
Workable's embeddable jobs widget. Searches return the entire board with full descriptions,
deduplicating multi-location postings automatically:

```sh
jobrake workable search -b huggingface
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("workable", board="huggingface"))
```

## Options

Pass the employer slug from the board URL to `--board`, such as `huggingface` from
`apply.workable.com/huggingface`.

Workable's widget endpoint doesn't filter server-side, so slice results with `jq` (for example, roles
in France):

```sh
jobrake workable search -b huggingface | jq '[.[] | select(any(.locations[]; .country_code == "FR"))]'
```

## Fields

Openings include title, company, locations, date, and description, plus employment type,
department, application URL, and education (like `Master's Degree`) when provided. Salary and
language are not published by the widget API. See the [reference](../reference.md#fields-by-site)
for every key.

- `posted_at` is date-only and matches `date`.
- Workable emits one entry per location for multi-site roles; jobrake collapses those into a single
  posting with all locations preserved (formatted like `Paris, Île-de-France, France`).
- If a posting's top-level city/state/country isn't already in its locations list, jobrake appends
  it as an extra location.
- `workplace_type` is only ever `remote`, since Workable exposes a boolean remote flag and no
  hybrid or on-site marker.
