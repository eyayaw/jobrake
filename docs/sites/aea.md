# AEA JOE (`aea`)

[JOE](https://www.aeaweb.org/joe/listings), Job Openings for Economists, is the American Economic
Association's listing of academic, government, and private-sector openings for economists.
A search returns the listings JOE shows as active, newest first, each with its full text:

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

`--query` is the site's keyword search.
`--section` takes a section of JOE's Section/Type menu, by its name or its code:

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

JOE files the listings of sections 2 and 4 under subsections, such as `2a`, so `2` or `4` selects both of its subsections.

`--jel` takes a JEL field by its letter, such as `J` for labor and demographic economics, or `00` for listings open to any field.
Repeat `--section` or `--jel` to match any of several values. Each option you add narrows the search.
JOE would return nothing for a section or field it does not know, so jobrake stops you before the search.

JOE dates listings by the day, so `--max-age-hours 168` keeps the listings posted on or after the date seven days ago.
A search takes no `--results` and returns every listing that matches.

## Fields

Besides its full text, each listing carries the title, the institution, the places, and the posted
date, and, when JOE has them, the application deadline, the hiring department, and the keywords
([every key](../reference.md#fields-by-site)).

A few idiosyncrasies of these fields:

- JOE keeps a listing active past its deadline. On 2026-11-17, nearly a third of the active
  listings were past theirs, so check `expires_at`.
- `site_data.status` holds a status such as `Position has been filled` once the employer closes the search.
- The salary is free text in `site_data.salary_range`, such as `Competitive` or `$145,000/year`,
  so a record has no salary fields.
- `site_data` also holds the listing's `section`, its `jel` codes, such as `J2` or `F`, and the
  `division` of the institution when JOE names one.
- `locations` holds each place the listing names, such as `Cergy, Ile de France, FRANCE`.
  JOE writes the country in words, so a place has no `country_code`.
- `posted_at`, `date`, and `expires_at` are calendar dates without a time.
- `id` joins the JOE issue that carried the listing and the listing's number, such as `2026-02_111477855`.

## Requests

A search reads the JOE listings page with your filters, then the XML export that page links,
which holds the full text. So a search costs two requests whether it finds 5 listings or 500,
and one that finds nothing stops after the first. If either request fails, the search stops
with nothing, and `scrape` raises [`Stopped`](../reference.md#stopped).

## Terms

The JOE listings page states that its content is for personal use only and that you may not
scrape, collect, or otherwise use it without the American Economic Association's express written
permission. The page offers its own XML and Excel downloads of a search.
