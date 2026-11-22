# AcademicTransfer (`academictransfer`)

[AcademicTransfer](https://www.academictransfer.com) lists academic and research vacancies at
universities, medical centers, and research institutes, most of them in the Netherlands.
A search returns the active vacancies, newest first, each with its description:

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

`--vacancy-type` picks a tab of the site's jobs page: `scientific` for academic vacancies,
`non_scientific` for the others, or `all`, the default.
The site held 728 active vacancies on 2026-11-17, and `--results` defaults to 100,
so pass `--results 1000` to read them all.

## Fields

A vacancy also carries its language and the time it was published, and, when it gives them, the
contract type, the department, the education asked for, the deadline, the salary range, the
application link, the keywords, and the weekly hours ([every key](../reference.md#fields-by-site)).

- `description` joins the vacancy's description, requirements, terms of employment, additional
  information, and how to apply, and leaves out the organization's and the department's own descriptions.
- The site names no currency or period for a salary, so jobrake records every range as euros a
  month. In our tests on 2026-11-17, most academic economics vacancies with a range named an
  amount in euros a month in their text, and all of them were in the Netherlands.
  A vacancy without a range has no salary keys.
- `employment_type` is `permanent` or `temporary`, and `language` is `en` or `nl`, the language
  the vacancy is written in.
- `locations` holds one place with its `city` and `country_code`, such as `Rotterdam, NL`.
- `site_data` holds the vacancy's `min_weekly_hours` and `max_weekly_hours` when it gives them.

## Requests

A search first reads the site's jobs page once, for the public token its search script sends,
then pages through the list API that page reads, newest first.
jobrake waits 10 seconds before each request to the API, the crawl delay the robots.txt of
`www.academictransfer.com` asks for, so a search of 500 vacancies waits 100 seconds in all.
We have not measured how long the token stays valid: our longest test, two pages, took 22 seconds.

If a request fails, or jobrake finds no token on the jobs page, the search stops with the
vacancies read so far, and `scrape` raises [`Stopped`](../reference.md#stopped) with them in `partial`.
It also stops when the API sends an empty page before the count it reported.

## Terms

The robots.txt of `www.academictransfer.com` allows its public pages.
The robots.txt of `api.academictransfer.com`, which serves the list the jobs page shows,
disallows every path.
jobrake reads that API as the site's own jobs page does in your browser, and it waits the crawl
delay that the robots.txt of `www.academictransfer.com` asks for.
