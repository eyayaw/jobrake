# Personio (`personio`)

[Personio](https://www.personio.com) publishes a public XML feed for each employer's career site.
jobrake reads that feed and returns every active opening on the board:

```sh
jobrake personio search -b tado
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("personio", board="tado"))
```

## Options

Pass just the employer's subdomain to `--board`, for example `tado` for `tado.jobs.personio.de` or
`tado.jobs.personio.com`.

Because the XML feed is unfiltered, pipe the output if you want a subset (like working-student
roles):

```sh
jobrake personio search -b tado | jq '[.[] | select(.employment_type == "working_student")]'
```

## Fields

Openings include title, office locations, creation timestamp, and contract type, plus description,
subcompany, department, keywords, and salary when present. Workplace type and separate application
links are not published in the feed. See the [reference](../reference.md#fields-by-site) for the
full column breakdown.

- Personio stores each job description in a single language and leaves it blank in other language
  feeds. jobrake fetches the default feed first, then backfills any blank postings (including
  titles) from the first of English, German, French, Spanish, Dutch, Italian, or Portuguese that
  contains text.
- `company` is populated from Personio's subcompany field (e.g., `tado GmbH`) when configured.
- `employment_type` slugifies Personio's contract type (`permanent`, `internship`, `fixed_term`,
  `working_student`, etc.).
- `salary_period` is `YEAR`, `MONTH`, or `HOUR`; salaries without an upper bound set only
  `salary_min`.
- `keywords` splits Personio's comma-separated tag list (e.g., `Werkstudent:in,Accounting`).
- `site_data` passes through `seniority`, `schedule`, `occupation`, `occupationCategory`, and
  (when set) `recruitingCategory` and `yearsOfExperience`.
