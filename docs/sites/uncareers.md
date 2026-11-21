# UN Careers (`uncareers`)

[UN Careers](https://careers.un.org) is the recruitment site of the United Nations Secretariat.
It lists professional, general service, field service, consultant, and internship openings
across the UN's departments, offices, and missions.

```sh
jobrake uncareers search -n 500 -o un.jsonl
jobrake uncareers search -q economist --max-age-hours 168
jobrake uncareers search --duty-station Geneva --duty-station "New York" --level P-3 --level P-4
jobrake uncareers search --category INT
jobrake uncareers filters duty-station
```

A search returns the openings with the highest job IDs first, which the site created most recently,
each with its description. No option is required.
In [Python](../reference.md#python-api) the options are keyword arguments:
`scrape("uncareers", duty_station=["Geneva"], level=["P-3", "P-4"])`.

## Options

| Option                  | Value                                                      | Default            |
| ----------------------- | ---------------------------------------------------------- | ------------------ |
| `--query`, `-q`         | keywords                                                   | none               |
| `--results`, `-n`       | a positive integer                                         | 100                |
| `--max-age-hours`, `-a` | a positive integer                                         | no age limit       |
| `--category`            | such as `INT` or `Affiliate Personnel – Internships`, `PD` | every category     |
| `--duty-station`        | such as `Geneva`, `New York`, `Addis Ababa`                | every duty station |
| `--level`               | such as `P-3`, `G-5`, `D-1`, `NO-B`                        | every level        |
| `--department`          | such as `Economic Commission for Africa`                   | every department   |
| `--job-network`         | such as `DEVNET` or `Economic, Social and Development`     | every job network  |
| `--job-family`          | such as `Statistics`, `ECO`, `Human Rights Affairs`        | every job family   |
| `--recruitment-type`    | such as `Consultant`, `Intern`, `Temporary Opportunities`  | every type         |

`--query | -q` is the site's keyword search. It matches words, not parts of words,
and other forms of a word as well.
The site filters posting age in whole days, so `--max-age-hours` rounds up to whole days.
A multiple of 24 bounds the age exactly.

The other filters take the names that the filters on the site's
[search page](https://careers.un.org/jobopening?language=en) show, in any case,
or the site's own codes.
A search that takes one of these options first reads the site's list of filter values,
because UN Careers ignores a value it does not know and then returns every opening.
jobrake stops instead and names the closest values, or the command that lists them all.
Only that list can confirm a value, so `jobrake.check("uncareers", duty_station=["Genva"])` passes,
and the search raises `ValueError`.
A category makes the site drop the keyword, so a search refuses `--query` and `--category` together.
Each list option in the table, given more than once, keeps the openings that match any of its values,
and different options all apply.
The [README](../../README.md#cli) describes the options every site shares, `--output` and `--format` among them.

## Lookups

`jobrake uncareers filters <option>` lists every value an option takes.
For example, `jobrake uncareers filters duty-station` lists the duty stations.
`<option>` names a filter as its flag does, without the leading dashes: `category`, `duty-station`,
`level`, `department`, `job-network`, `job-family`, or `recruitment-type`.
Each value is an `id` and a `name`, in the order of the site's list, and a search takes either one.
A code can carry two names, such as level `300`, `NO-2` and `NO-B`.
In Python it is `jobrake.sites.uncareers.filters(fetcher, option)`.

## Fields

A UN Careers record carries `title`, `company`, `locations`, `date`, and `description`,
and the details `posted_at`, `expires_at`, and `site_data`.
[The record](../reference.md#the-record) describes every key.

| Key           | Value                                                                                   |
| ------------- | --------------------------------------------------------------------------------------- |
| `id`          | the opening's job ID                                                                    |
| `url`         | the opening on `careers.un.org`, where candidates apply                                 |
| `title`       | the opening's posting title, such as `HUMANITARIAN AFFAIRS OFFICER (PROGRAMME), P3`     |
| `company`     | the UN entity that hires, such as `Office for the Coordination of Humanitarian Affairs` |
| `locations`   | one place per duty station, such as `NEW YORK`, `Juba`, or `FO West Bank`               |
| `posted_at`   | the opening's start, as a UTC timestamp                                                 |
| `expires_at`  | its deadline, as a UTC timestamp                                                        |
| `description` | every section of the opening under its title, in the site's order                       |
| `site_data`   | the five keys described below                                                           |

For a staff post the title ends in its grade.
A place is named by the site's label, with no other part.
The timestamps, such as `2026-11-13T05:00:00.000Z` and `2026-11-20T04:59:59.000Z`,
fall at the start and the end of a day in New York.

`site_data` holds the opening's `category` code, such as `PD` or `INT`, its `level`,
such as `P-3`, `I-1`, or `CON`, its `recruitment_type`, such as `Temporary Opportunities`,
and, when present, its `job_family` and `job_network`.
A `category` can be a code that `--category` does not take, such as `RLG`.

A section of the description such as `Work Location` can say the work is remote,
and the record carries no `workplace_type`.
Candidates apply on the opening's page, so a record has no separate `apply_url`.
The list carries no salary or employment type.

## Limits

A search pages through the openings, highest job ID first, one request after another.
The list carries each opening whole, so jobrake makes no request per opening.
The default of 100 falls short of the whole site, which listed 448 openings on 2026-11-16,
so raise `--results` to read all of it.
An opening that closes during a search shifts the later pages, so one can be skipped.
An opening added during a search makes one repeat, which jobrake keeps once.

A search stops at `--results`, at the last opening, or at an empty page.
A failed request or an answer jobrake cannot read, the filter list's included, raises
[`Stopped`](../reference.md#stopped) with the openings of the pages before it.
So does an empty page that comes before the number of openings UN Careers reported,
as when openings close during the search, so a rerun may find the rest.
To narrow the openings further, pipe the results through `jq`.

## Terms

UN Careers links to the UN's [terms of use](https://www.un.org/en/about-us/terms-of-use).
They permit copying the site's material for personal, non-commercial use,
and they give no right to redistribute it or to compile works from it.

## Measured

UN Careers does not document the endpoints its search page calls, which jobrake reads.
We measured them on the 448 openings of 2026-11-16 and on searches of the next day.
Pages sorted by job ID gave each of the 448 openings once.
We infer that job IDs follow the order the site created openings in, because the 20 highest IDs had start dates over
five days. In our tests, `economics` matched 27 openings, three of them only through their job
family, Economic Affairs. The site's menu offers a posting age of 1, 7, and 30 days,
and the filter applied 2, 3, 14, 45, and 365 days as well.
