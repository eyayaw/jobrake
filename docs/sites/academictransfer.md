# AcademicTransfer (`academictransfer`)

[AcademicTransfer](https://www.academictransfer.com) lists academic and research vacancies at
universities, medical centers, and research institutes, mostly in the Netherlands.
Searches return active vacancies newest first, with full descriptions included:

```sh
jobrake academictransfer search -n 1000 -o academictransfer.jsonl
jobrake academictransfer search -q economics --vacancy-type scientific
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("academictransfer", query="economics", vacancy_type="scientific"))
```

## Options

`--vacancy-type` matches the tabs on AcademicTransfer's jobs page: `scientific` for academic roles,
`non_scientific` for support and administrative roles, or `all` (the default).
If you want the entire active board, bump `--results` up (for example `-n 1000`).

## Fields

Alongside the title, institution, location, publication timestamp, and language, AcademicTransfer
often provides the contract type, department, required education, deadline, salary range,
application URL, keywords, and weekly hours. See the [reference](../reference.md#fields-by-site)
for the full field breakdown.

- `description` combines the description, requirements, terms of employment, additional
  information, and application instructions, skipping boilerplate about the employer or department.
- The API omits currency and pay period, so jobrake records salary ranges as monthly EUR (the
  convention used by most Dutch academic listings we inspected). Double-check the posting text
  if a figure looks unusual. Postings without a salary range omit all salary fields.
- `employment_type` is `permanent` or `temporary`; `language` is `en` or `nl`.
- `locations` contains a single entry with `city` and `country_code` (such as `Rotterdam, NL`).
- `site_data` includes `min_weekly_hours` and `max_weekly_hours` when provided.

## Requests

jobrake fetches a public token from the jobs page first, then honors the
[10-second crawl delay](https://www.academictransfer.com/robots.txt) before each API request, so
fetching 500 vacancies takes roughly 100 seconds.

We haven't measured how long a token stays valid; our longest run took 22 seconds.

## Terms

`www.academictransfer.com/robots.txt` allows public pages with a crawl delay, while
`api.academictransfer.com/robots.txt` disallows all paths. jobrake calls that list API the same way
the website's own frontend does in a browser and honors that delay.
