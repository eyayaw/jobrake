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

`--query | -q` is the site's keyword search.
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

JOE files each listing under a subsection, so the heading `2` or `4` selects its subsections too.
On 2026-11-17, `2` alone matched no listing, while `2a` and `2b` held 115.

`--jel` takes a JEL field by its letter, such as `J` for labor and demographic economics,
or `00` for listings open to any field.
`--section` and `--jel`, given more than once, keep the listings that match any of their values,
and different options all apply.
JOE answers a section or field it does not know with no listings, so jobrake refuses one instead.
JOE dates a listing by day, so `--max-age-hours` keeps the listings posted on or after the day that
many hours ago.
A search takes no `--results` and returns every listing that matches.

## Fields

An AEA JOE [record](../reference.md#the-record) carries `title`, `company`, `locations`, `date`,
and `description`, and the details `posted_at`, `site_data`, and, when present, `department`,
`expires_at`, and `keywords`, one per line of the listing's keywords, which 542 of the 774 listings
of 2026-11-17 gave.

- `id` is the JOE ID: the year and issue that list the listing, and its number,
  such as `2026-02_111477855`. `url` opens the listing on `aeaweb.org`.
- `company` is the institution, such as `Ahmedabad University`, and `department` the unit that
  hires within it, which 520 of the 774 listings named.
- `locations` holds each place the listing names, with its `city` and `region`,
  named from them and the country, such as `Cergy, Ile de France, FRANCE`.
  JOE names the country in words, so a place has no `country_code`.
  35 of the 774 listings named more than one place.
- `posted_at` and `date` are the calendar date the listings page shows for the listing.
- `expires_at` is the application deadline, a calendar date, which 18 of the 774 listings lacked.
  JOE keeps a listing active past its deadline: 232 of the 774 were.
- `description` is the listing's full text as JOE stores it, with line breaks and no markup.
- `site_data` holds the listing's `section`, such as `Full-Time Nonacademic`,
  its `jel` codes, such as `J2` or `F`, and, when present, the `division` of the institution,
  its `salary_range` as free text, such as `Competitive` or
  `$145,000/year`, which 330 listings gave, and a `status` such as `Position has been filled`,
  which JOE sets when the employer closes the search.

## Requests

A search is two requests, each with a single attempt and no pacing.
The first reads the JOE listings page with the search's filters,
which shows every listing of the search with its posted date.
The second reads the XML export that the page links for the same listings,
which holds every other field, so jobrake makes no request per listing.
A search that matches nothing gets a page without listings and makes no second request.
A failed request, or an answer jobrake cannot read, raises [`Stopped`](../reference.md#stopped)
with an empty `partial`.

## Terms

The JOE listings page states that its content is for personal use only and that you may not
scrape, collect, or otherwise use it without the American Economic Association's express written
permission. The page offers its own XML and Excel downloads of a search.
