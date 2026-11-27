# XING (`xing`)

[XING](https://www.xing.com) is a professional network with a job board focused on Germany, Austria,
and Switzerland. jobrake queries the undocumented GraphQL API behind XING's Android app.

```sh
jobrake xing search -q economist -l Berlin -n 20
jobrake xing search -q "data scientist" -l Zürich -r 50 -a 168 -o xing.jsonl
jobrake xing search -q "data engineer" --remote --details
jobrake xing postings https://www.xing.com/jobs/berlin-referent-strategische-datenanalyse-158824212
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("xing", query="economist", location="Berlin", details=True))
```

## Options

Pass a city or postal code in Germany, Austria, or Switzerland to `--location` (such as `Berlin`,
`Wien`, or `Zürich`), or omit it to search everywhere. There is no `--country` flag because XING
filters countries only by internal IDs. `--radius` is in kilometers and defaults to `0` (matching
the given city alone, as XING's app does). `--remote` restricts results to fully remote roles,
`--results` defaults to 100, and `--details` fetches full job descriptions. Run
`jobrake xing search -h` for every option.

## Fields

Search results already return most metadata: title, company (plus page URL and logo), locations,
dates, `language`, `employment_type`, `workplace_type`, `apply_url`, advertised salary, and XING's
career level, discipline, and industry. Adding `--details` fetches the full description. All
populated keys are listed in the [reference](../reference.md#fields-by-site).

- `posted_at` and `date` reflect when XING last published or refreshed the listing (the same
  timestamp `--max-age-hours` filters on), so reposted roles can appear recent. `expires_at` is the
  scheduled end date.
- Salary fields include employer-advertised salaries only; XING's salary estimates are excluded.
  Because XING's API omits the pay period and displays salaries annually in the app,
  `salary_period` is set to `YEAR`.
- `apply_url` points either to the employer's form or XING's apply page; email-only postings omit it.
- `site_data` stores `careerLevel`, `discipline`, and `industry` (always requested in English).

You can also fetch individual postings directly with `jobrake xing postings <url>` (for example,
`https://www.xing.com/jobs/berlin-referent-strategische-datenanalyse-158824212`), which returns the
same fields as a `--details` search.

## Requests

XING caps results at 1,000 postings per search. Split broad queries by city or keywords to retrieve
more.
