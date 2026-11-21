# Personio (`personio`)

[Personio](https://www.personio.com) is an applicant tracking system. An employer that uses it
publishes its openings on a career site Personio hosts, and jobrake reads one employer's
career site through its public XML feed.

```sh
jobrake personio search -b tado
jobrake personio search -b tado -o tado.jsonl
jobrake personio search --board tado --format csv
jobrake personio search -b tado | jq '[.[] | select(.date != null and .date >= "2026-11-14")]'
```

`search` returns every posting on the career site,
in the order of its feed in the board's default language.
`--board` is required. In Python the option is a keyword argument:
`scrape("personio", board="tado")`.

## Options

| Option          | Value                                       | Default  |
| --------------- | ------------------------------------------- | -------- |
| `--board`, `-b` | the career site's subdomain, such as `tado` | required |

The board token is `tado` in `tado.jobs.personio.de`, the subdomain of the career site.
A career site at `<token>.jobs.personio.com` takes the same token.
A value that is not one subdomain, such as the whole address, is an error before any request.
An employer can switch off the feed jobrake reads, and Personio then answers as it does for a
token it does not know, so the error names both causes.

The search takes no query, result limit, or filters, and Personio applies none.
To narrow the postings, filter the records yourself, as the last command above does on `date`.
The [README](../../README.md#cli) describes the output options every site shares.

## Fields

A Personio record carries `title`, `locations`, and `date`, and the details `posted_at`,
`employment_type`, `site_data`, and, when present, `company`, `description`, `department`,
`keywords`, and the salary fields.
[The record](../reference.md#the-record) describes every key.

| Key                 | Value                                                 |
| ------------------- | ----------------------------------------------------- |
| `url`               | the posting on `<board>.jobs.personio.de`             |
| `company`           | the posting's subcompany, such as `tado GmbH`         |
| `locations`         | the posting's office, then its additional offices     |
| `date`, `posted_at` | the time the posting was created                      |
| `description`       | the posting's description blocks, each under its name |
| `employment_type`   | Personio's contract type as a slug                    |
| `salary_period`     | `YEAR`, `MONTH`, or `HOUR`                            |
| `keywords`          | the feed's comma-separated keywords, split            |

`site_data` holds, when present, `seniority`, `schedule`, `occupation`, `occupationCategory`,
`recruitingCategory`, and `yearsOfExperience`, as the feed names them.

Personio names a subcompany when the employer has set up subcompanies.
A place is named as the employer entered it, such as `Mannheim` and `Köln`.
`employment_type` is a slug such as `permanent`, `internship`, `fixed_term`, or `working_student`.
A salary without a maximum carries `salary_min` alone.
`keywords` splits a value such as `Werkstudent:in,Accounting` in two.

Personio serves each posting's description in one language,
and its feed in any other language lists the posting without one.
jobrake first reads the feed in the board's default language.
A posting that feed leaves without a description comes whole, title included,
from the first of English, German, French, Spanish, Dutch, Italian, and Portuguese
that describes it.

A Personio record has no workplace type or application link.

## Limits

A search reads the board's feed in its default language.
While a posting still lacks a description, the search reads the feed in the next language,
in the order above, so a search takes one to eight requests.
A failed first request raises `Stopped` with no postings,
and a failed later one keeps the postings already read in `partial`.

## Measured

Personio's recruiting API spec lists the feed's languages.
On 2026-11-15 we measured the feeds of 71 boards, each with German or English as its default
language.
The default-language feeds left 161 of 742 postings without a description,
and the other languages described all of them.
Of the 71 boards, 69 took one or two requests, and of the 742 postings, 62 published a salary.
