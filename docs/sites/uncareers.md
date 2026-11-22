# UN Careers (`uncareers`)

[UN Careers](https://careers.un.org) is the recruitment site of the United Nations Secretariat.
It lists professional, general service, field service, consultant, and internship openings
across the UN's departments, offices, and missions.
A search returns the openings newest first, by job ID, each with its description:

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

jobrake reads the endpoints behind the site's search page. UN Careers does not
document them, so what we say here about their behavior comes from our own tests.

## Options

`--query` is the site's keyword search. It matches whole words and their other forms.
In our tests, `economics` also found openings through their job family, Economic Affairs.
Raise `--results` to read past the first 100 openings.

`--max-age-hours` sends the site's own age filter, which counts in whole days, so jobrake rounds your hours up.
Use a multiple of 24 to get exactly the age you ask for. In our tests, the filter also took day counts
beyond the 1, 7, and 30 its menu offers.

The other filters take a name as the site's [search page](https://careers.un.org/jobopening?language=en)
shows it, in any letter case, or the site's own code:

| Option               | Example values                                    |
| -------------------- | ------------------------------------------------- |
| `--category`         | `INT` (`Affiliate Personnel – Internships`), `PD` |
| `--duty-station`     | `Geneva`, `New York`, `Addis Ababa`               |
| `--level`            | `P-3`, `G-5`, `D-1`, `NO-B`                       |
| `--department`       | `Economic Commission for Africa`                  |
| `--job-network`      | `DEVNET` (`Economic, Social and Development`)     |
| `--job-family`       | `Statistics`, `ECO`, `Human Rights Affairs`       |
| `--recruitment-type` | `Consultant`, `Intern`, `Temporary Opportunities` |

Give an option several times to match any of its values. Each further option narrows the search.
UN Careers ignores a value it does not know and returns every opening, so jobrake first reads the
site's list of values and stops on one it cannot find, naming the closest matches or the command that lists them all.
The site drops the keyword when a category is set, so jobrake refuses the two together.
Search by one and filter the results on the other.

## Lookups

`jobrake uncareers filters <option>` lists every value an option takes.
For example, `jobrake uncareers filters duty-station` lists the duty stations.
Each value is an `id` and a `name`, and a search takes either.
Two names can share a code: level `300` is both `NO-2` and `NO-B`.
The lookup is also a function, `jobrake.sites.uncareers.filters(fetcher, option)`.

## Fields

An opening's description holds every section of it under its title. The record also names the UN
entity that hires, the duty stations, and the dates the opening opens and closes
([every key](../reference.md#fields-by-site)). Candidates apply on `careers.un.org`, at the opening's `url`.

- A staff post's `title` ends in its grade, such as `HUMANITARIAN AFFAIRS OFFICER (PROGRAMME), P3`.
- `locations` holds one place per duty station, named by the site's label as it is, such as
  `NEW YORK`, `Juba`, or `FO West Bank`, with no country.
- `posted_at` and `expires_at` are UTC timestamps that fall at the start and the end of a day in
  New York, such as `2026-11-13T05:00:00.000Z` and `2026-11-20T04:59:59.000Z`.
- A record has no salary, employment type, or `workplace_type`. A remote opening says so in its
  description, in a section such as `Work Location`.
- `site_data` holds the opening's `category` code, such as `PD` or `INT`, its `level`, such as
  `P-3` or `CON`, its `recruitment_type`, and its `job_family` and `job_network` when it has them.
  A `category` can be a code that `--category` does not take, such as `RLG`.

## Requests

An opening that closes or appears during a long search shifts the later pages, so the search can miss one.

## Terms

UN Careers links to the UN's [terms of use](https://www.un.org/en/about-us/terms-of-use).
They permit copying the site's material for personal, non-commercial use,
and they give no right to redistribute it or to compile works from it.
