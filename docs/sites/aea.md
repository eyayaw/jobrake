# AEA JOE (`aea`)

[JOE](https://www.aeaweb.org/joe/listings) (Job Openings for Economists) is the American Economic
Association's board for academic, government, and private-sector economist positions. Searches
return all matching active listings, newest first, with full descriptions:

```sh
jobrake aea search -o joe.jsonl
jobrake aea search --jel J --jel H --max-age-hours 168
jobrake aea search -q "labor economics" --section "Full-Time Nonacademic"
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("aea", section=["1", "3"], jel=["J"]))
```

## Options

`--query` passes keywords to JOE's search box.
`--section` filters by JOE's Section/Type menu using either the code or the full label:

| Code | Section                                                                   |
| ---- | ------------------------------------------------------------------------- |
| `1`  | US: Full-Time Academic (Permanent, Tenure Track or Tenured)               |
| `2`  | US: Other Academic (Temporary, Adjunct, Visiting, Part-Time)              |
| `2a` | US: Other Academic (Visiting or Temporary)                                |
| `2b` | US: Other Academic (Part-time or Adjunct)                                 |
| `3`  | International: Full-Time Academic (Permanent, Tenure Track or Tenured)    |
| `4`  | International: Other Academic (Temporary, Adjunct, Visiting, Part-Time)   |
| `4a` | International: Other Academic (Visiting or Temporary)                     |
| `4b` | International: Other Academic (Part-time or Adjunct)                      |
| `5`  | Full-Time Nonacademic                                                     |
| `6`  | Other Nonacademic (Temporary, Part-Time, Non-Salaried, Consulting, Etc.)  |

Because JOE files listings in sections 2 and 4 under their subsections (`2a`/`2b`, `4a`/`4b`),
passing `2` or `4` automatically includes both subsections.

`--jel` filters by JEL classification letter (such as `J` for labor and demographic economics), or
`00` for listings open to any field. Repeat `--section` or `--jel` to match any of several values;
combining different flags narrows the results. Unknown codes are rejected locally before sending a
request, since JOE would silently return zero listings.

Because JOE dates listings by calendar day, `--max-age-hours 168` returns everything posted on or
after the date seven days ago. There is no `--results` flag; every matching listing is returned.

## Fields

Each listing includes the full text, title, institution, locations, and posted date, plus the
deadline, department, and keywords when provided. The
[reference](../reference.md#fields-by-site) lists every populated field.

A few JOE quirks to keep in mind:

- Expired listings can remain active on JOE past their deadline, so check `expires_at`.
- Closed searches set `site_data.status` (e.g., `Position has been filled`).
- Salary is free text (like `Competitive` or `$145,000/year`) and lives in `site_data.salary_range`
  rather than the structured salary fields.
- `site_data` also includes `section`, `jel` codes (such as `J2` or `F`), and `division` when present.
- `locations` lists every location in the posting (e.g., `Cergy, Ile de France, FRANCE`). JOE spells
  out country names instead of ISO codes, so `country_code` is omitted.
- `posted_at`, `date`, and `expires_at` are calendar dates only (no time of day).
- `id` combines the JOE issue and listing number, e.g., `2026-02_111477855`.

## Terms

The JOE listings page states that content is for personal use only and forbids scraping or
collecting it without express written permission from the American Economic Association. Note that
the site also provides its own XML and Excel export buttons.
