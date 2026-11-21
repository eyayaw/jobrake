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

`--query | -q` is the site's keyword search. `--vacancy-type` takes a tab of the site's jobs page:
`scientific` for academic vacancies, `non_scientific` for the others, or `all`, the default.
`--results | -n` caps the vacancies returned, 100 by default.
The site held 728 active vacancies on 2026-11-17, so raise it to read them all.

## Fields

An AcademicTransfer [record](../reference.md#the-record) carries `title`, `company`, `locations`,
`date`, and `description`, and the details `posted_at`, `language`, and, when present,
`employment_type`, `department`, `education`, `expires_at`, `salary_min`, `salary_max`,
`salary_currency`, `salary_period`, `apply_url`, `keywords`, and `site_data`.

- `id` is the vacancy's number on the site, such as `365285`,
  and `url` opens its page on `academictransfer.com`.
- `company` is the organization, such as `Erasmus University Rotterdam`, and `department` the unit
  that hires within it, which 3 of the 53 academic economics vacancies of 2026-11-17 named.
- `locations` holds one place with its `city` and `country_code`, such as `Rotterdam, NL`.
  2 of the 53 academic economics vacancies of 2026-11-17 were in Germany, the rest in the
  Netherlands.
- `posted_at` is the timestamp the vacancy was published, and `expires_at` its application
  deadline, also a timestamp.
- `description` joins the vacancy's description, requirements, terms of employment,
  additional information, and how to apply. It leaves out the organization's and the department's
  own descriptions.
- `language` is `en` or `nl`, the language the vacancy is written in.
- `employment_type` is `permanent` or `temporary`, and `education` the level of education the
  vacancy asks for, such as `Doctorate` or `University graduate`.
- `salary_min` and `salary_max` are the salary range. The site names no currency or period,
  so jobrake infers `salary_currency` `EUR` and `salary_period` `MONTH` from the vacancies' texts:
  36 of the 43 academic economics vacancies of 2026-11-17 with a range named an amount in euros a
  month, and all 43 were in the Netherlands. A vacancy without a range has no salary keys.
- `apply_url` is the employer's application link.
- `site_data` holds the vacancy's `min_weekly_hours` and `max_weekly_hours` when it gives them.

## Requests

A search first reads the site's jobs page for the public token its search script sends,
then pages through the list API that page reads, newest first, each request with a single attempt.
jobrake waits 10 seconds before each request to the API, the crawl delay the robots.txt of
`www.academictransfer.com` asks for, so a search of 500 vacancies waits 100 seconds in all.
A failed request, a jobs page without a readable token, or an empty page before the count the API
reported raises [`Stopped`](../reference.md#stopped), and its `partial` holds the vacancies of
the pages before it.
A search reads the token once, at its start. How long a token stays valid was not measured,
and the longest search tested, two pages, took 22 seconds.

## Terms

The robots.txt of `www.academictransfer.com` allows its public pages.
The robots.txt of `api.academictransfer.com`, which serves the list the jobs page shows,
disallows every path.
