# SmartRecruiters (`smartrecruiters`)

jobrake reads one employer's board on [SmartRecruiters](https://www.smartrecruiters.com) through
SmartRecruiters' public Posting API, which applies a query and filters on the server.

```sh
jobrake smartrecruiters search -b BoschGroup -q engineer
jobrake smartrecruiters search -b BoschGroup --remote --max-age-hours 72 -n 500 -o bosch.csv
jobrake smartrecruiters postings https://jobs.smartrecruiters.com/BoschGroup/744000158197889
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("smartrecruiters", board="BoschGroup", query="engineer"))
```

## Options

`--board | -b` takes the board token, the part of the board's address that names the employer:
`BoschGroup` in `jobs.smartrecruiters.com/BoschGroup`. In our tests, capitals did not matter.

SmartRecruiters answers a token it does not know as it answers a board with no postings,
so jobrake cannot tell the two apart.
Either way the search returns no postings, and without a query or filter it logs that the token
may be misspelled.
Check the token against the board's address before you conclude that the employer has no openings.

`--query | -q` searches posting titles and locations.
`--max-age-hours | -a` keeps postings released within that many hours,
and `--remote` keeps the postings SmartRecruiters files as remote,
which can include ones whose `workplace_type` is `hybrid`.
`--results | -n` defaults to 100, because an employer board is usually read whole.
Raise it to read a large board: Bosch Group's board held more than 5,000 postings in our tests.

## Fields

A SmartRecruiters search result carries `title`, `company`, `locations`, and `date`,
and the [details](../reference.md#the-record) `posted_at`, `employment_type`, `language`, and,
when present, `department` and `workplace_type`.

- `locations` holds one place, named as SmartRecruiters writes it, such as `Wuxi, Jiangsu, China`,
  with its `city`, `country_code`, and, when present, `region`, `latitude`, and `longitude`.
- `posted_at` is the time the posting was released, and `date` is its calendar date.
  `language` is a code such as `en` or `zh-CN`.
- `url` opens the posting on `jobs.smartrecruiters.com`.
- `workplace_type` is `remote` or `hybrid` for a posting the employer marks so,
  and absent otherwise, because SmartRecruiters does not mark on-site.
- SmartRecruiters serves a description only with each posting, so a search result has none.
  `--details | -d` fetches each posting and adds `description` and, when present, `apply_url`.
  `description` holds every section of the ad under its title, in SmartRecruiters' order:
  the company description, the job description, the qualifications, and additional information.
- `apply_url` is the application link the posting gives. In five postings read on 2026-11-18,
  it was the posting page's address with `?oga=true`.
- A record has no salary, because SmartRecruiters does not publish one.

`jobrake smartrecruiters postings` fetches postings you already know.
A reference is a search result's `url` or the posting's address with its title slug.
It returns the record a `--details` search would, without the `department`,
which only the search result carries.

## Requests

A search pages through the board one request after another, without pacing,
and each request gets a single attempt.
It stops at `--results`, at the board's last matching posting, or at an empty page.
A failed request raises [`Stopped`](../reference.md#stopped) with the postings of the pages before
it. So does an empty page that comes before the number of matches SmartRecruiters reported,
because postings may have closed during the search and a rerun may find more.

`--details` and `jobrake smartrecruiters postings` fetch each posting with one request,
which a [cached](../reference.md#configuration) posting skips.
SmartRecruiters reports a posting gone with HTTP 404, or by marking a posting it still serves
inactive.
