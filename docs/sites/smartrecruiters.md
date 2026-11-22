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

`--board` takes the board token, the part of the board's address that names the employer:
`BoschGroup` in `jobs.smartrecruiters.com/BoschGroup`. Capitalization did not matter in our tests.

SmartRecruiters answers a token it does not know as it answers a board with no postings,
so a misspelled token returns nothing, with no error. Check the token against the board's address before you conclude
that the employer has no openings.

`--query` searches posting titles and locations.
`--remote` keeps the postings SmartRecruiters files as remote, which can include ones whose
`workplace_type` is `hybrid`.
For a large board, raise `--results` above its default of 100:
Bosch Group's board held more than 5,000 postings in our tests.

## Fields

A search result carries the posting's title, company, place, release time, employment type, and
language. The department and the workplace type come when the employer set them.
`--details` adds the description and the application link ([every key](../reference.md#fields-by-site)).

- `description` holds every section of the ad under its title, in SmartRecruiters' order:
  the company description, the job description, the qualifications, and additional information.
- `workplace_type` is `remote` or `hybrid` when the employer says so. SmartRecruiters has no
  on-site mark, so other postings have none.
- `language` is a code such as `en` or `zh-CN`.
- A record has no salary, because SmartRecruiters does not publish one.

### Postings you already know

`jobrake smartrecruiters postings` fetches postings by URL: a search result's `url`, such as
`https://jobs.smartrecruiters.com/BoschGroup/744000158197889`, or the posting's address with its
title slug. You get what a `--details` search would give, except the `department`, which only a search result carries.

## Requests

jobrake reads the board page after page until it has `--results` postings or the board runs out
of matches. If a page fails, the search stops with the postings it has, and `scrape`
raises [`Stopped`](../reference.md#stopped) with them in `partial`.
An empty page before the number of matches SmartRecruiters reported stops it too: postings that
closed mid-search may have shifted the pages, so a rerun may find what it skipped.

With `--details`, a posting that SmartRecruiters reports gone, with HTTP 404 or by marking it
inactive, keeps what its search result had, and so does one jobrake could not fetch.
