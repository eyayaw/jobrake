# Workday (`workday`)

jobrake searches employer career sites hosted on [Workday](https://www.workday.com) through the
undocumented JSON API behind their job pages. We tested against three Workday career sites
(including Zillow and NVIDIA) across different data centers; individual employer setups can still
vary.

```sh
jobrake workday search -b https://zillow.wd5.myworkdayjobs.com/Zillow_Group_External -q analyst
jobrake workday search -b https://zillow.wd5.myworkdayjobs.com/Zillow_Group_External -n 100 -d -o zillow.jsonl
jobrake workday postings https://zillow.wd5.myworkdayjobs.com/Zillow_Group_External/job/Remote-USA/Applied-Scientist_P751481-1
```

```python
import asyncio

from jobrake import scrape

board = "https://zillow.wd5.myworkdayjobs.com/Zillow_Group_External"
jobs = asyncio.run(scrape("workday", board=board, query="analyst", details=True))
```

## Options

Rather than a short board token, `--board` takes the career site URL copied straight from your
browser, such as `https://zillow.wd5.myworkdayjobs.com/Zillow_Group_External`. Both standard
Workday URL patterns work:
- `https://<tenant>.wd<n>.myworkdayjobs.com/<site>` (with or without a locale prefix like `en-US`)
- `https://wd<n>.myworkdaysite.com/recruiting/<tenant>/<site>`

Individual posting URLs on the same site work too.

Searches return 20 postings by default; pass `--results` for more. Because every Workday tenant
configures its own custom facets, jobrake exposes `--query` only (no location, remote, or age
filters).

## Fields

Search results return title, location, and an approximate date. Pass `--details` to fetch the full
description, `employment_type`, and exact `posted_at` start date. Salary, workplace type, and
application URLs aren't included; see [Fields by site](../reference.md#fields-by-site) for
the full summary.

- `company` is always `None`, since Workday exposes internal legal entity names (like
  `ZINC Zillow, Inc.`) rather than a clean employer name.
- Multi-location postings return an empty `locations` list during search because search results
  only say `"2 Locations"`. `--details` fills in the primary location (with `country_code`)
  followed by additional locations.
- Without `--details`, `date` is computed backwards from Workday's relative label
  (`"Posted 3 Days Ago"`) in UTC, so it can be off by a day, and `"Posted 30+ Days Ago"` yields
  `None`. With `--details`, `date` uses Workday's exact `startDate`.
- `id` combines the tenant and requisition ID, e.g., `zillow:P751481-1`.

### Fetching by posting URL

`jobrake workday postings` takes any Workday posting URL copied from search output or a browser and
returns the same fields as a `--details` search.

## Requests

Workday caps search results at 2,000 postings per query. Add `--query` terms to break larger boards
into smaller slices.
