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

`--board | -b` takes the board token, the subdomain of the board's address: `tado` in
`tado.jobs.personio.de`.
A board at `<token>.jobs.personio.com` takes the same token.
Pass the subdomain alone, since jobrake refuses a whole address.
An employer can switch off the feed jobrake reads, and Personio then answers as it does for a
token it does not know, so the error names both causes.

A search takes no query, result limit, or filters, because Personio applies none.
To narrow the postings, pipe the results through `jq` or load them into another tool:

```sh
jobrake personio search -b tado | jq '[.[] | select(.date != null and .date >= "2026-11-14")]'
```

## Fields

A Personio [record](../reference.md#the-record) carries `title`, `locations`, and `date`, and the
details `posted_at`, `employment_type`, `site_data`, and, when present, `company`, `description`,
`department`, `keywords`, and the salary fields.

- `company` is the posting's subcompany, such as `tado GmbH`,
  which Personio names when the employer has set up subcompanies.
- `posted_at` is the time the posting was created, and `date` is its calendar date.
- `locations` holds the posting's office and then its additional offices,
  named as the employer entered them, such as `Mannheim` and `Köln`.
- `description` joins the posting's description blocks, each under its name when it has one.
  Personio serves each posting's description in one language,
  and its feed in any other language lists the posting without one.
  jobrake first reads the feed in the board's default language,
  German or English on the boards we tested.
  A posting that feed leaves without a description comes whole, title included,
  from the first of English, German, French, Spanish, Dutch, Italian, and Portuguese
  that describes it.
  In our test on 71 boards on 2026-11-15, the default-language feeds left 161 of 742 postings
  without a description, and the other languages described all of them.
- `employment_type` is Personio's contract type as a slug,
  such as `permanent`, `internship`, `fixed_term`, or `working_student`.
- `salary_period` is `YEAR`, `MONTH`, or `HOUR`, and a salary without a maximum carries
  `salary_min` alone. In the same test, 62 of 742 postings published a salary.
- `keywords` splits the feed's comma-separated keywords, such as `Werkstudent:in,Accounting`.
- `site_data` holds `seniority`, `schedule`, `occupation`, `occupationCategory`, and,
  when present, `recruitingCategory` and `yearsOfExperience`, as the feed names them.
- `url` is the posting on `<board>.jobs.personio.de`.

A Personio record has no workplace type or application link.

## Requests

A search reads the board's feed in its default language.
While a posting still lacks a description, the search reads the feed in the next language,
in the order above, so a search takes one to eight requests.
In our test, 69 of 71 boards took one or two requests.
Each request gets a single attempt and no pacing.
A failed first request raises [`Stopped`](../reference.md#stopped) with an empty `partial`,
and a failed later one keeps the postings already read in `partial`.
