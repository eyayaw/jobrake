# Adzuna (`adzuna`)

[Adzuna](https://www.adzuna.com) aggregates listings from employers, staffing agencies, and other
job boards into separate country editions. jobrake queries the undocumented API behind Adzuna's
Android app.

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

`--country` is required and accepts any of Adzuna's 19 editions: `at`, `au`, `be`, `br`, `ca`, `ch`,
`de`, `es`, `fr`, `gb`, `in`, `it`, `mx`, `nl`, `nz`, `pl`, `sg`, `us`, or `za`.

Searching with `--location` and no `--radius` behaves like `-r 0`, though results can still include
neighboring municipalities (for instance, Villeurbanne when searching Lyon).

`--max-age-hours` rounds up to whole days because Adzuna only filters by day (`-a 25` searches the
last two days).

## Fields

Search results return the title, company, location, date, and employment type. Adding `--details`
fetches the full description, advertised salary, `posted_at`, `expires_at`, coordinates, and (for
listings aggregated from another board) the source board name and application link. Check the
[fields-by-site reference](../reference.md#fields-by-site) for the full list.

- Salaries appear only with `--details` and reflect employer-advertised figures annualized by
  Adzuna. Adzuna's own salary predictions are dropped, as are salaries on Adzuna-hosted direct
  pages (where we observed monthly pay mislabeled as yearly).
- With `--details`, `date` switches to the day Adzuna originally created the listing, which can be
  months earlier than the modified date shown in search results.
- `url` points to Adzuna; `apply_url` points to the original source listing.
- `employment_type` uses the work schedule (`full_time`, `part_time`, etc.) when present, putting
  `permanent` or `contract` in `site_data.contract_type`. If no schedule is given, `employment_type`
  falls back to the contract type. With `--details`, `site_data` also includes `category` and
  `source`.

There is no `jobrake adzuna postings` command: fetching an aggregated ad requires a per-search hash
that only appears in search results. If a `--details` run fails partway through, rerun the same
search and already-fetched postings will come from the local cache.

## Requests

Adzuna caps searches at 1,000 results. Split large queries by city or narrower keywords to get
further.
