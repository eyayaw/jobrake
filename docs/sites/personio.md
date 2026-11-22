# Personio (`personio`)

jobrake reads one employer's board on [Personio](https://www.personio.com), which Personio calls
a career site, through its public XML feed. A search returns every posting on the board:

```sh
jobrake personio search -b tado
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("personio", board="tado"))
```

## Options

`--board` takes the subdomain of the board's address alone: `tado` for
`tado.jobs.personio.de` or `tado.jobs.personio.com`.

Personio's feed takes no query or filters, so narrow the postings yourself, for example to the
working-student positions:

```sh
jobrake personio search -b tado | jq '[.[] | select(.employment_type == "working_student")]'
```

## Fields

A posting carries its title, its offices, the time it was created, and its contract type, and,
when present, its description, subcompany, department, keywords, and salary ([every key](../reference.md#fields-by-site)).

- Personio writes each description in one language, and its feed in any other language lists
  the posting bare. jobrake reads the default language first, then fills each bare posting,
  title included, from the first of English, German, French, Spanish, Dutch, Italian, and
  Portuguese that describes it. In our tests on 2026-11-15, the other languages described every posting the
  default feed left bare.
- `company` is the posting's subcompany, such as `tado GmbH`,
  which Personio names when the employer has set up subcompanies.
- `employment_type` is Personio's contract type as a slug,
  such as `permanent`, `internship`, `fixed_term`, or `working_student`.
- `salary_period` is `YEAR`, `MONTH`, or `HOUR`, and a salary without a maximum carries `salary_min` alone.
- `keywords` splits the feed's comma-separated keywords, such as `Werkstudent:in,Accounting`.
- `site_data` holds `seniority`, `schedule`, `occupation`, `occupationCategory`, and,
  when present, `recruitingCategory` and `yearsOfExperience`, as the feed names them.
- A record has no workplace type or application link.

## Requests

A search reads the board's feed in its default language, then the next language in the order
above while a posting still lacks a description, so it takes one to eight requests.
Most boards in our tests on 2026-11-15 took one or two.
If the first request fails, the search stops with nothing. If a later one fails, it keeps the
postings already read, and `scrape` raises [`Stopped`](../reference.md#stopped) with them in `partial`.
