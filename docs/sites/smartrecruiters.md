# SmartRecruiters (`smartrecruiters`)

[SmartRecruiters](https://www.smartrecruiters.com) is an applicant tracking system. An employer
that uses it publishes its openings on a board SmartRecruiters hosts, and jobrake reads one
employer's board through SmartRecruiters' public Posting API.

```sh
jobrake smartrecruiters search -b BoschGroup -q engineer
jobrake smartrecruiters search -b BoschGroup --remote --max-age-hours 72 -n 500 -o bosch.csv
jobrake smartrecruiters search -b BoschGroup -q engineer -n 20 --details
jobrake smartrecruiters postings https://jobs.smartrecruiters.com/BoschGroup/744000158197889
```

`search` returns the board's postings in SmartRecruiters' order, and `--board` is required.
`postings` fetches the postings you name, each by a record's `url` or by the posting's address
with its title slug. Any other reference is an error, and nothing is fetched.
Employers take postings down over time, so the example above may be gone.
Use references from a recent search.
In Python the options are keyword arguments:
`scrape("smartrecruiters", board="BoschGroup", query="engineer")`.

## Options

| Option                  | Value                                   | Default      |
| ----------------------- | --------------------------------------- | ------------ |
| `--board`, `-b`         | the board's token, such as `BoschGroup` | required     |
| `--query`, `-q`         | keywords                                | none         |
| `--results`, `-n`       | a positive integer                      | 100          |
| `--max-age-hours`, `-a` | a positive integer                      | no age limit |
| `--remote`              | keep only remote postings               | off          |
| `--details`, `-d`       | fetch each posting                      | off          |

A SmartRecruiters search applies a query and filters on the server.
`--query | -q` searches posting titles and locations.
`--max-age-hours | -a` keeps postings released within that many hours,
and `--remote` keeps the postings SmartRecruiters marks remote.
Raise `--results` to read a large board.
The [reference](../reference.md#options) has the rules every site shares.

The board token is the part of the board's address that names the employer:
`BoschGroup` in `jobs.smartrecruiters.com/BoschGroup`.
SmartRecruiters answers a token it does not know as it answers a board with no postings,
so jobrake cannot tell the two apart.
Either way the search returns no postings, and without a query or filter it logs that the token may be
misspelled.
Check the token against the board's address before you conclude that the employer has no openings.

## Fields

SmartRecruiters serves a description only with each posting, so a search result has none.
`--details | -d` fetches each posting and adds `description` and, when present, `apply_url`.
[The record](../reference.md#the-record) describes every key.

| Key                 | From a search                                    | With `--details`        |
| ------------------- | ------------------------------------------------ | ----------------------- |
| `url`               | the posting on `jobs.smartrecruiters.com`        | the same                |
| `company`           | the employer's name                              | the same                |
| `locations`         | one place, named as SmartRecruiters writes it    | the same                |
| `date`, `posted_at` | the time the posting was released                | the same                |
| `employment_type`   | a slug such as `full_time`                       | the same                |
| `language`          | a code such as `en` or `zh-CN`                   | the same                |
| `department`        | the hiring unit, when present                    | the same                |
| `workplace_type`    | `remote` or `hybrid`, when the employer marks it | the same                |
| `description`       | absent                                           | every section of the ad |
| `apply_url`         | absent                                           | the application link    |

The one place is named as in `Wuxi, Jiangsu, China`,
with its `city`, `country_code`, and, when present, `region`, `latitude`, and `longitude`.
`workplace_type` is absent for any other posting, because SmartRecruiters does not mark on-site.
`--remote` keeps the postings SmartRecruiters files as remote,
which can include ones whose `workplace_type` is `hybrid`.

`description` holds every section of the ad under its title, in SmartRecruiters' order:
the company description, the job description, the qualifications, and additional information.
`postings` builds the record `--details` would, from a search result's `url` in a later run,
without the `department`, which only the search result carries.
A record has no salary, because SmartRecruiters does not publish one.

## Limits

A search pages through the board one request after another, without pacing.
It stops at `--results`, at the board's last matching posting, or at an empty page.
A failed request raises `Stopped` with the postings of the pages before it.
So does an empty page that comes before the number of matches SmartRecruiters reported,
as when postings close during the search, so a rerun may find the rest.

`--details` and `postings` send one request per posting, one at a time,
and none for a posting in the [cache](../reference.md#configuration).
A posting SmartRecruiters no longer serves, or serves as inactive, is gone:
a search keeps its card, and `postings` reports it and leaves it out.
A posting that could not be fetched also keeps its card, and the search raises
[`Stopped`](../reference.md#stopped) with the URLs to retry through `postings`.

## Measured

SmartRecruiters documents its Posting API.
In our tests, capitals in the board token did not matter,
and Bosch Group's board held more than 5,000 postings.
In five postings read on 2026-11-18,
`apply_url` was the posting page's address with `?oga=true`.
