# INOMICS (`inomics`)

[INOMICS](https://inomics.com) lists jobs for economists across academia, research, and industry,
from PhD positions to professorships. Searches return postings in INOMICS's relevance order (100 by
default):

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

`--country` filters to one country by ISO 3166-1 code (such as `de` or `deu`).
`--category` matches INOMICS's Job Type menu by either code or label:

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

The codes preserve INOMICS's exact URL spellings, typos and all (`practicioner`,
`senior-reasercher`).

`--jel` filters by JEL discipline letter (`A`–`R` or `Z`, e.g., `J` for labor and demographic
economics). Repeat `--category` or `--jel` to match any of several values; combining different
options intersects them. Invalid values fail fast locally because INOMICS would otherwise return an
empty list silently.

Pass a larger `--results` (such as `-n 500`) to fetch beyond the default 100 postings. INOMICS has
no date filter, so filter recent postings locally with `jq`:

```sh
jobrake inomics search -n 500 | jq '[.[] | select(.date != null and .date >= "2026-11-14")]'
```

## Fields

Search results return the title, employer, location, posted date, posting types (like `Postdoc Job`),
and sometimes `workplace_type` (`remote` or `hybrid`). Adding `--details` fetches each posting's
page for the full description, application deadline, and structured location parts (region and
country code) when available. Salary, employment type, and separate application links are not
provided; see the [reference](../reference.md#fields-by-site) for the full field breakdown.

- `date` reflects the posted date shown on INOMICS, which updates if a posting is reposted. For
  listings cross-listed as scholarships, the detail page uses the original entry date, so
  `--details` can shift `date` earlier.
- `company` uses the first listed employer in search results (a few listings show none or multiple);
  with `--details`, it uses the hiring organization from the posting page.
- Search results give `locations` as a plain label like `Saarbrücken, Germany` (or just a country).
  With `--details`, the posting page's structured location replaces it when present: if a page omits
  the city, the city is dropped; if it omits the country code, the label uses city and region
  (e.g., `Umeå, Västerbotten` replacing `Umeå, Sweden`).
- `expires_at` is the application deadline when listed.
- `site_data.types` lists the INOMICS posting types (such as `Assistant Professor / Lecturer Job`
  or `PhD Program`).

### Reading individual postings

`jobrake inomics postings` accepts either a short URL like `https://inomics.com/job/1555749` or a
full slugged posting URL. Because it skips search results and reads only the posting page,
`workplace_type` and `site_data` won't be populated.

## Terms

Section C.3.b of INOMICS's [terms and conditions](https://inomics.com/terms-and-conditions)
prohibits accessing the site or collecting content "using automated means (such as harvesting bots,
robots, spiders, or scrapers) without our permission".
