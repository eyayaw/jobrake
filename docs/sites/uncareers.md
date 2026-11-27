# UN Careers (`uncareers`)

[UN Careers](https://careers.un.org) is the United Nations Secretariat's recruitment portal,
covering professional, general service, field service, consultant, and internship openings across
UN departments, offices, and missions. Searches return openings newest first (by job ID) with full
descriptions:

```sh
jobrake uncareers search -n 500 -o un.jsonl
jobrake uncareers search -q economist --max-age-hours 168
jobrake uncareers search --duty-station Geneva --duty-station "New York" --level P-3 --level P-4
jobrake uncareers search --category INT
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("uncareers", duty_station=["Geneva"], level=["P-3", "P-4"]))
```

jobrake calls the undocumented JSON endpoints powering the portal's search page.

## Options

`--query` runs the site's keyword search, matching whole words and their other forms (for example,
`economics` also picks up roles in the Economic Affairs job family). Increase `--results` if you
want more than the default 100 openings.

`--max-age-hours` rounds up to whole days to match UN Careers' age filter. Use a multiple of 24 for
an exact day count; the backend accepts arbitrary day counts beyond the 1, 7, and 30 options shown
in the web dropdown.

The remaining filters accept either the display label from the
[search page](https://careers.un.org/jobopening?language=en) (case-insensitive) or the internal
code:

| Option               | Example values                                    |
| -------------------- | ------------------------------------------------- |
| `--category`         | `INT` (`Affiliate Personnel – Internships`), `PD` |
| `--duty-station`     | `Geneva`, `New York`, `Addis Ababa`               |
| `--level`            | `P-3`, `G-5`, `D-1`, `NO-B`                       |
| `--department`       | `Economic Commission for Africa`                  |
| `--job-network`      | `DEVNET` (`Economic, Social and Development`)     |
| `--job-family`       | `Statistics`, `ECO`, `Human Rights Affairs`       |
| `--recruitment-type` | `Consultant`, `Intern`, `Temporary Opportunities` |

Repeat any filter to match multiple values (OR); different filters combine with AND. Because UN
Careers silently ignores unknown filter values and dumps the entire board, jobrake fetches the live
filter catalog first and rejects typos with suggested matches. Also, UN Careers ignores `--query`
whenever `--category` is passed, so jobrake refuses both together. Search by one and filter locally
on the other.

## Lookups

Run `jobrake uncareers filters <option>` (e.g., `jobrake uncareers filters duty-station`) to list
every valid `id` and `name` for a filter. A search accepts either value. Note that multiple labels
can share one code: for instance, `300` maps to both `NO-2` and `NO-B`.

From Python, call `jobrake.sites.uncareers.filters(fetcher, option)`.

## Fields

Descriptions preserve each section under its heading, alongside the hiring UN entity, duty
stations, and opening/closing timestamps. Candidates apply on `careers.un.org` via `url`; salary,
employment type, and `workplace_type` aren't exposed as structured fields (remote arrangements
appear inside the description, usually under `Work Location`). Check the
[fields-by-site table](../reference.md#fields-by-site) for the full list.

- Staff post titles include the grade at the end, e.g., `HUMANITARIAN AFFAIRS OFFICER (PROGRAMME), P3`.
- `locations` creates one entry per duty station using UN Careers' exact label (`NEW YORK`, `Juba`,
  `FO West Bank`), without country codes.
- `posted_at` and `expires_at` are UTC timestamps aligned to midnight in New York
  (`2026-11-13T05:00:00.000Z` / `2026-11-20T04:59:59.000Z`).
- `site_data` stores `category` (`PD`, `INT`, and occasionally internal codes like `RLG` that
  `--category` doesn't accept), `level` (`P-3`, `CON`), `recruitment_type`, and (when present)
  `job_family` and `job_network`.

## Requests

Openings added or closed during a multi-page fetch can shift page boundaries, so long searches may
occasionally miss an opening.

## Terms

UN Careers links to the UN [terms of use](https://www.un.org/en/about-us/terms-of-use), which
allow copying material for personal, non-commercial use without rights to redistribute or compile
derivative works.
