# AEA JOE (`aea`)

[JOE](https://www.aeaweb.org/joe/listings), Job Openings for Economists, is the American Economic
Association's listing of academic, government, and private-sector openings for economists.

```sh
jobrake aea search -o joe.jsonl
jobrake aea search --jel J --jel H --max-age-hours 168
jobrake aea search -q "labor economics" --section "Full-Time Nonacademic"
jobrake aea search --section 1 3 --jel J -f csv
```

A search returns the listings JOE shows as active, newest first, each with its full text.
No option is required. In [Python](../reference.md#python-api) the options are keyword arguments:
`scrape("aea", section=["1", "3"], jel=["J"])`.

## Options

| Option                  | Value                                         | Default       |
| ----------------------- | --------------------------------------------- | ------------- |
| `--query`, `-q`         | keywords                                      | none          |
| `--max-age-hours`, `-a` | a positive integer                            | no age limit  |
| `--section`             | codes or names from the table below           | every section |
| `--jel`                 | `00`, or a JEL letter, `A` to `R`, `Y`, or `Z` | every field   |

`--query | -q` is the site's keyword search.
A search takes no `--results` and reads every listing that matches.
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

JOE files each listing of section `2` or `4` under a subsection, so the heading `2` or `4` selects its subsections too.

`--jel` takes a JEL field by its letter, such as `J` for labor and demographic economics,
or `00` for listings open to any field.
JOE dates a listing by day, so `--max-age-hours` keeps the listings posted on or after the UTC date
that many hours ago.
`--section` and `--jel`, given more than once, keep the listings that match any of their values,
and different options all apply.
JOE answers a section or field it does not know with no listings, so jobrake refuses one instead,
before any request.
The [README](../../README.md#cli) describes the options every site shares, `--output` and `--format` among them.

## Fields

An AEA JOE record carries `title`, `company`, `locations`, `date`, and `description`,
and the details `posted_at`, `site_data`, and, when present, `department`, `expires_at`,
and `keywords`, one per line of the listing's keywords.
[The record](../reference.md#the-record) describes every key.

| Key                 | Value                                                                    |
| ------------------- | ------------------------------------------------------------------------ |
| `id`                | the JOE ID, such as `2026-02_111477855`                                  |
| `url`               | the listing on `aeaweb.org`                                              |
| `company`           | the institution, such as `Ahmedabad University`                          |
| `department`        | the unit that hires within it                                            |
| `locations`         | each place the listing names, with its `city` and `region`               |
| `date`, `posted_at` | the calendar date the listings page shows for the listing                |
| `expires_at`        | the application deadline, a calendar date                                |
| `description`       | the listing's full text as JOE stores it, with line breaks and no markup |
| `site_data`         | the five keys described below                                            |

The JOE ID is the year and issue that list the listing, and its number.
A place is named from its `city`, its `region`, and the country,
such as `Cergy, Ile de France, FRANCE`.
JOE names the country in words, so a place has no `country_code`.
JOE keeps a listing active past its deadline.

`site_data` holds the listing's `section`, such as `Full-Time Nonacademic`,
its `jel` codes, such as `J2` or `F`, and, when present, the `division` of the institution,
its `salary_range` as free text, such as `Competitive` or `$145,000/year`,
and a `status` such as `Position has been filled`, which JOE sets when the employer closes the
search.
A record has no salary keys, employment type, workplace type, or application link.

## Limits

A search is two requests.
The first reads the JOE listings page with the search's filters,
which shows every listing of the search with its posted date.
The second reads the XML export that the page links for the same listings,
which holds every other field, so jobrake makes no request per listing.
A search that matches nothing gets a page without listings and makes no second request.

A failed request raises [`Stopped`](../reference.md#stopped) with an empty `partial`,
and so does an export jobrake cannot read, an answer that is not a listings page,
or a page that dates its listings but links no export, or links an export but dates no listing.

## Terms

The JOE listings page states that its content is for personal use only and that you may not
scrape, collect, or otherwise use it without the American Economic Association's express written
permission. The page offers its own XML and Excel downloads of a search.

## Measured

The counts are from the 774 listings JOE showed as active on 2026-11-17:
232 were past their deadline, 18 gave no deadline, and 35 named more than one place.
