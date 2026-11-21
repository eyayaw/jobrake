# AcademicTransfer (`academictransfer`)

[AcademicTransfer](https://www.academictransfer.com) lists academic and research vacancies at
universities, medical centers, and research institutes, most of them in the Netherlands.

```sh
jobrake academictransfer search -n 1000 -o academictransfer.jsonl
jobrake academictransfer search -q economics --vacancy-type scientific
jobrake academictransfer search --vacancy-type non_scientific -n 20 -f csv
```

A search returns the active vacancies, newest first, each with its description.
No option is required. In [Python](../reference.md#python-api) the options are keyword arguments:
`scrape("academictransfer", query="economics", vacancy_type="scientific")`.

## Options

| Option            | Value                                    | Default |
| ----------------- | ---------------------------------------- | ------- |
| `--query`, `-q`   | keywords                                 | none    |
| `--vacancy-type`  | `scientific`, `non_scientific`, or `all` | `all`   |
| `--results`, `-n` | a positive integer                       | 100     |

`--query | -q` is the site's keyword search. `--vacancy-type` takes a tab of the site's jobs page:
`scientific` for academic vacancies, `non_scientific` for the others, or `all`, the default.
The [README](../../README.md#cli) describes the options several sites share,
`--output` and `--format` among them.

## Fields

An AcademicTransfer record carries `title`, `locations`, `date`, and `description`,
and the details `posted_at`, `language`, `employment_type`, and, when present, `company`, `department`,
`education`, `expires_at`, `salary_min`, `salary_max`, `salary_currency`, `salary_period`,
`apply_url`, `keywords`, and `site_data`.
[The record](../reference.md#the-record) describes every key.

| Key                        | Value                                                                  |
| -------------------------- | ---------------------------------------------------------------------- |
| `id`                       | the vacancy's number on the site, such as `365285`                     |
| `url`                      | the vacancy's page on `academictransfer.com`                           |
| `company`                  | the organization, such as `Erasmus University Rotterdam`               |
| `department`               | the unit that hires within it                                          |
| `locations`                | one place with its `city` and `country_code`, such as `Rotterdam, NL`  |
| `date`, `posted_at`        | when the vacancy was published, `posted_at` as a timestamp             |
| `expires_at`               | its application deadline, also a timestamp                             |
| `language`                 | `en` or `nl`, the language the vacancy is written in                   |
| `employment_type`          | `permanent` or `temporary`                                             |
| `education`                | the level of education the vacancy asks for, such as `Doctorate`       |
| `salary_min`, `salary_max` | the salary range                                                       |
| `apply_url`                | the employer's application link                                        |
| `site_data`                | `min_weekly_hours` and `max_weekly_hours`, when the vacancy gives them |

`description` joins the vacancy's description, requirements, terms of employment,
additional information, and how to apply. It leaves out the organization's and the department's
own descriptions.

The site names no currency or period. Its vacancies' texts state euros a month, so jobrake sets
`salary_currency` to `EUR` and `salary_period` to `MONTH`.
A vacancy without a salary range has none of the four salary keys.
A record has no workplace type.

## Limits

A search reads the site's jobs page once, then pages through the list API that page reads.
jobrake waits 10 seconds before each request to the site's API, as the robots.txt of `www.academictransfer.com` asks,
so a search of 500 vacancies waits 100 seconds in all.
The default of 100 falls short of the whole board, which held 728 active vacancies on 2026-11-17,
so raise `--results` to read all of it.

A failed request, a jobs page or an answer jobrake cannot read, or an empty page before the count the API
reported raises [`Stopped`](../reference.md#stopped), and its `partial` holds the vacancies of
the pages before it.

## Terms

The robots.txt of `www.academictransfer.com` allows its public pages with a crawl delay of
10 seconds. The robots.txt of `api.academictransfer.com`, which serves the list the jobs page shows,
disallows every path.

## Measured

The counts are from the list API's answers of 2026-11-17.
Of the 53 academic economics vacancies of that day, 2 were in Germany and the rest
in the Netherlands, and 43 gave a salary range. Of those 43, 36 named an amount in euros a month in
their text, and all 43 were in the Netherlands. The longest search tested read two pages and took
22 seconds. A search reads the jobs page's access to the API once, at its start, and how long that
access stays valid was not measured, so a much longer search may stop partway.
