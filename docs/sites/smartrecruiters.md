# SmartRecruiters (`smartrecruiters`)

jobrake reads employer boards on [SmartRecruiters](https://www.smartrecruiters.com) through
SmartRecruiters' public Posting API, which supports server-side search and filtering.

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

`--board` is the company slug from the board URL, such as `BoschGroup` in
`jobs.smartrecruiters.com/BoschGroup` (case-insensitive).

Watch out for typos: SmartRecruiters responds to an unknown company slug the exact same way as an
empty board, returning zero results without an error.

`--query` searches job titles and locations. `--remote` filters to SmartRecruiters' remote flag,
which can also include `hybrid` roles. Large employers can have thousands of openings, so raise
`--results` above the default 100 when pulling a full board.

## Fields

Search results return title, company, location, release timestamp, employment type, language, and
(when set) department and workplace type. Add `--details` for the full description and application
link; SmartRecruiters' public API does not publish salaries.

- `description` stitches together SmartRecruiters' sections under their headings: company
  description, job description, qualifications, and additional information.
- `workplace_type` is `remote` or `hybrid` when tagged; SmartRecruiters has no explicit on-site
  flag, so everything else leaves it unset.
- `language` is a language/locale code like `en` or `zh-CN`.

See [Fields by site](../reference.md#fields-by-site) for the complete comparison.

### Reading individual postings

`jobrake smartrecruiters postings` accepts either the short posting URL
(`https://jobs.smartrecruiters.com/BoschGroup/744000158197889`) or the longer URL with a title
slug. Because it reads only the posting endpoint without search results, it returns the same fields
as a `--details` search except `department`.
