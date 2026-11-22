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

`--board` takes the company identifier, the first path segment of the board's URL:
`BoschGroup` in `jobs.smartrecruiters.com/BoschGroup`. Capitalization did not matter in our tests.

SmartRecruiters answers a token it does not know as it answers a board with no postings,
so a misspelled token returns nothing, with no error. Check the token against the board's address before you conclude
that the employer has no openings.

`--query` searches posting titles and locations.
`--remote` keeps the postings SmartRecruiters files as remote, which can include ones whose
`workplace_type` is `hybrid`.
For a large board, raise `--results` above its default of 100:
Bosch Group's board held thousands of postings in our tests.

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
title slug. You get what a `--details` search would give, except a field only the search result had.
