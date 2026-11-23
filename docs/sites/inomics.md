# INOMICS (`inomics`)

[INOMICS](https://inomics.com) lists jobs for economists in academia, research,
and industry, from PhD positions to professorships.
A search returns the postings in INOMICS's order of relevance, 100 by default:

```sh
jobrake inomics search -n 500 -o inomics.jsonl
jobrake inomics search -q labor -c de
jobrake inomics search --category postdoc --category professor --jel J --jel E -d
jobrake inomics postings https://inomics.com/job/1555749
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("inomics", country="de", category=["postdoc"], details=True))
```

## Options

`--country` keeps the postings in one country, given by its ISO 3166-1 code, such as `de` or `deu`.
`--category` takes a category of the site's Job Type menu, by its name or its code:

| Code                 | Category                             |
| -------------------- | ------------------------------------ |
| `administration`     | Administration                       |
| `asst-prof-lecturer` | Assistant Professor / Lecturer       |
| `graduate`           | Graduate / Traineeship               |
| `internship`         | Internship                           |
| `junior-industry`    | Junior Industry Position             |
| `mid-level-industry` | Mid-Level Industry Position          |
| `other`              | Other Jobs                           |
| `phd-candidate`      | PhD Candidate                        |
| `postdoc`            | Postdoc                              |
| `practicioner`       | Practitioner / Consultant            |
| `professor`          | Professor                            |
| `research-assistant` | Research Assistant / Technician      |
| `researcher`         | Researcher / Analyst                 |
| `senior-industry`    | Executive / Senior Industry Position |
| `senior-reasercher`  | Senior Researcher / Group Leader     |

The codes keep INOMICS's own spelling, typos included: `practicioner` and `senior-reasercher`.
`--jel` takes a JEL field of the site's Disciplines menu by its letter, from `A` to `R` or `Z`,
such as `J` for labor and demographic economics. Repeat `--category` or `--jel` to match any of several values.
Different options must all match. jobrake refuses a category or field INOMICS does not know, because INOMICS would quietly return nothing.

Pass `--results 500` to read more jobs than the default.

INOMICS has no date filter, so a search takes no `--max-age-hours`.
To keep the recent postings, pipe the results through `jq` on `date`:

```sh
jobrake inomics search -n 500 | jq '[.[] | select(.date != null and .date >= "2026-11-14")]'
```

## Fields

INOMICS shows each search result as a card with the title, the employer, the place, the posting
date, its types, such as `Postdoc Job`, and sometimes whether the job is `remote` or `hybrid`.
`--details` adds the description and the application deadline from each posting's page,
and, when the page names them, the place's region and country code ([every key](../reference.md#fields-by-site)).

- `date` is the day INOMICS shows as posted, and INOMICS moves it to the day it reposts a posting.
  A posting INOMICS also lists as a scholarship is dated on its page by the day it was entered,
  so `--details` can move that posting's `date`.
- `company` is the first employer the card names, and a few cards name none or several.
  With `--details`, it is the hiring organization the page names.
- `locations` is the place as the card writes it, such as `Saarbrücken, Germany`, and sometimes
  only a country. With `--details`, the page's place replaces it when the page names one.
  Often that is the same place, but a page without a city drops the card's city, and a page
  without a country code names the place by city and region, such as `Umeå, Västerbotten` for the
  card's `Umeå, Sweden`.
- `expires_at` is the application deadline, which many postings leave out.
- `site_data.types` holds the card's types, such as `Assistant Professor / Lecturer Job`.
  A posting can also carry the type of a program, scholarship, or course, such as `PhD Program`.
- A record has no salary, employment type, or application link.

### Postings you already know

`jobrake inomics postings` fetches postings by URL: a search result's `url`, such as
`https://inomics.com/job/1555749`, or the posting's address with its title slug.
It reads only the page, so its records lack `workplace_type` and `site_data`, which only a card carries.

## Terms

The INOMICS [terms and conditions](https://inomics.com/terms-and-conditions), in section C.3.b,
forbid collecting users' content or information, or otherwise accessing the INOMICS sites,
"using automated means (such as harvesting bots, robots, spiders, or scrapers) without our permission".
