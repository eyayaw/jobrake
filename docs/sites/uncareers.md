# UN Careers (`uncareers`)

[UN Careers](https://careers.un.org) is the recruitment site of the United Nations Secretariat.
It lists professional, general service, field service, consultant, and internship openings
across the UN's departments, offices, and missions.
A search returns the openings with the highest job IDs first, which the site created most recently,
each with its description:

```sh
jobrake uncareers search -n 500 -o un.jsonl
jobrake uncareers search -q economist --max-age-hours 168
jobrake uncareers search --duty-station Geneva --duty-station "New York" --level P-3 --level P-4
jobrake uncareers search --category INT
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("uncareers", duty_station=["Geneva"], level=["P-3", "P-4"]))
```

jobrake reads the endpoints behind the site's search page, which UN Careers does not document,
so what this page says about them is what we measured.

## Options

`--query | -q` is the site's keyword search. It matches words, not parts of words,
and other forms of a word as well: in our tests, `economics` matched 27 openings,
three of them only through their job family, Economic Affairs.
`--results | -n` caps the openings returned, 100 by default, which falls short of the 448
openings the site listed on 2026-11-16.

`--max-age-hours | -a` sends the site's posting age filter, which keeps the openings whose start
date lies within a whole number of days, with the hours rounded up to days.
A multiple of 24 bounds the age exactly.
The site's menu offers 1, 7, and 30 days, and on 2026-11-17 the filter applied 2, 3, 14, 45,
and 365 days as well.

The other filters take the names that the filters on the site's
[search page](https://careers.un.org/jobopening?language=en) show, in any case,
or the site's own codes:

| Option               | Example values                                         |
| -------------------- | ------------------------------------------------------ |
| `--category`         | `INT` or `Affiliate Personnel – Internships`, `PD`     |
| `--duty-station`     | `Geneva`, `New York`, `Addis Ababa`                    |
| `--level`            | `P-3`, `G-5`, `D-1`, `NO-B`                            |
| `--department`       | `Economic Commission for Africa`                       |
| `--job-network`      | `DEVNET` or `Economic, Social and Development`         |
| `--job-family`       | `Statistics`, `ECO`, `Human Rights Affairs`            |
| `--recruitment-type` | `Consultant`, `Intern`, `Temporary Opportunities`      |

Each option in the table, given more than once, keeps the openings that match any of its values,
and different options all apply.
A search that takes one of these options first reads the site's list of filter values,
because UN Careers ignores a value it does not know and then returns every opening.
jobrake stops instead and names the closest values, or the command that lists them all.
A category makes the site drop the keyword, so a search takes `--query` or `--category`.
To narrow the openings further, pipe the results through `jq`.

## Lookups

`jobrake uncareers filters <option>` lists every value an option takes.
For example, `jobrake uncareers filters duty-station` lists the duty stations.
Each value is an `id` and a `name`, and a search takes either.
Two names can share a code: level `300` is both `NO-2` and `NO-B`.
In Python the lookup is `jobrake.sites.uncareers.filters(fetcher, option)`.

## Fields

A UN Careers [record](../reference.md#the-record) carries `title`, `company`, `locations`, `date`,
and `description`, and the details `posted_at`, `expires_at`, and `site_data`.

- `title` is the opening's posting title, which for a staff post ends in its grade,
  such as `HUMANITARIAN AFFAIRS OFFICER (PROGRAMME), P3`.
- `company` is the UN entity that hires,
  such as `Office for the Coordination of Humanitarian Affairs`.
- `locations` holds one place per duty station, named by the site's label,
  such as `NEW YORK`, `Juba`, or `FO West Bank`, with no other part.
  In our read of 448 openings on 2026-11-16, 8 listed more than one duty station.
- `posted_at` is the opening's start and `expires_at` its deadline, as UTC timestamps such as
  `2026-11-13T05:00:00.000Z` and `2026-11-20T04:59:59.000Z`, which fall at the start and the end of
  a day in New York. `date` is the calendar date of `posted_at`.
- `description` holds every section of the opening under its title, in the site's order.
  A section such as `Work Location` can say the work is remote,
  and the record carries no `workplace_type`.
- `url` opens the opening on `careers.un.org`, where candidates apply,
  so a record has no separate `apply_url`.
- `site_data` holds the opening's `category` code, such as `PD` or `INT`, its `level`,
  such as `P-3`, `I-1`, or `CON`, its `recruitment_type`, such as `Temporary Opportunities`,
  and, when present, its `job_family` and `job_network`.
  A `category` can be a code that `--category` does not take,
  such as `RLG`, which 25 of the 448 openings carried.
- The list carries no salary or employment type.

## Requests

A search pages through the openings 100 at a time, highest job ID first, one request after another,
without pacing, and each request gets a single attempt.
The list carries each opening whole, so jobrake makes no request per opening.

Many openings share a start date, and the site orders those differently from one request to the
next, so pages sorted by date repeated 11 of 448 openings and skipped 11 others in our test.
Job IDs are unique, and in our test, pages sorted by them gave each of the 448 openings once.
An opening that closes during a search still shifts the later pages, so one can be skipped,
and an opening that appears repeats one, which jobrake keeps once.
Job IDs follow the order the site created openings in: on 2026-11-16 the 20 highest IDs had start
dates over five days.

A search stops at `--results`, at the last opening, or at an empty page.
A failed request, or an answer jobrake cannot read, raises [`Stopped`](../reference.md#stopped)
with the openings of the pages before it.
So does an empty page that comes before the number of openings UN Careers reported,
because openings may have closed during the search and a rerun may find more.
A failed read of the filter list stops the search before its first page.

## Terms

UN Careers links to the UN's [terms of use](https://www.un.org/en/about-us/terms-of-use).
They permit copying the site's material for personal, non-commercial use,
and they give no right to redistribute it or to compile works from it.
