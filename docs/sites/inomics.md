# INOMICS (`inomics`)

[INOMICS](https://inomics.com) lists jobs for economists in academia, research, and industry,
from PhD positions to professorships.
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

`--query | -q` is the site's keyword search, and `--country | -c` keeps the postings in one
country, given by its ISO 3166-1 alpha-2 code, such as `de`.
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

The codes keep the site's spelling, so `practicioner` and `senior-reasercher` stay as INOMICS
writes them.
`--jel` takes a JEL field of the site's Disciplines menu by its letter, from `A` to `R` or `Z`,
such as `J` for labor and demographic economics.
`--category` and `--jel`, given more than once, keep the postings that match any of their values,
and different options all apply.
INOMICS answers a category or field it does not know with no postings, so jobrake refuses one
instead.
`--results | -n` defaults to 100, which can fall short of the site's postings, 112 on 2026-11-17,
so raise it to read them all.

INOMICS has no date filter, so a search takes no `--max-age-hours`.
To keep the recent postings, pipe the results through `jq` on `date`:

```sh
jobrake inomics search -n 500 | jq '[.[] | select(.date != null and .date >= "2026-11-14")]'
```

## Fields

INOMICS shows a search result as a card, which carries `title`, `company`, `locations`, and `date`,
and the [details](../reference.md#the-record) `posted_at`, `site_data`, and `workplace_type` when
the card states one.
`--details | -d` fetches each posting's page and adds `description` and, when the page gives them,
`expires_at` and the place's `region` and `country_code`.

- `url` opens the posting at `inomics.com/job/<id>`.
- `company` is the first employer the card names. 2 of the 112 postings of 2026-11-17 named none,
  and 2 named more than one. `--details` takes the hiring organization the posting's page names.
- `locations` holds one place, named as the card writes it, such as `Saarbrücken, Germany`, with
  its `city`, or the country alone, as 7 of the 112 gave. One of the 112 named no place.
  The card names the country in words. `--details` takes the place from the posting's page when
  the page names one.
  When the page gives the country's code, as all 15 postings in Germany did, the place takes the
  page's label, which matched the card's, and adds its `region` and `country_code`.
  A page that names no city drops the city the card gave, as the page of posting 1555182 did.
  A page without the country's code gives its city and region and no country, named from both,
  such as `Umeå, Västerbotten` where the card named `Umeå, Sweden`.
  Of 20 pages read on 2026-11-18, the 2 such pages were a scholarship and a program.
- `date` and `posted_at` are the day the card shows as posted, which INOMICS moves to the day it
  reposts a posting. The posting's page dates it the same way: on 2026-11-17, 17 of 17 pages that
  carried that date matched their card. A posting INOMICS also lists as a scholarship dates it by
  the day it was entered instead, so `--details` can move that posting's `date`.
- `expires_at` is the application deadline, which 9 of the 15 postings in Germany lacked.
- `workplace_type` is `hybrid` or `remote` when the card says so, as 9 and 6 of the 112 did.
- `description` is the text of the posting's page.
- `site_data` holds the card's `types`, such as `Postdoc Job` or `Assistant Professor / Lecturer
  Job`. A posting can also carry the type of a program, scholarship, or course, such as
  `PhD Program`.
- A record has no salary, employment type, or application link.

`jobrake inomics postings` fetches postings you already know.
A reference is a search result's `url` or the posting's address with its title slug.
`postings` reads the page alone, so its records lack `workplace_type` and `site_data`,
which only a card carries.

## Requests

A search is one request, without pacing and with a single attempt, to the endpoint INOMICS's
search page reads its results from. It asks for the first `--results` postings.
A failed request, or an answer without the count, raises [`Stopped`](../reference.md#stopped)
with no postings.
An answer that stops short of both `--results` and its count raises `Stopped` with the postings
it holds.

`--details` and `jobrake inomics postings` fetch each posting's page, one request per posting,
which a [cached](../reference.md#configuration) posting skips.
A page answering 404 or 410 counts as a posting gone.

## Terms

The INOMICS [terms and conditions](https://inomics.com/terms-and-conditions), in section C.3.b,
forbid collecting users' content or information, or otherwise accessing the INOMICS sites,
"using automated means (such as harvesting bots, robots, spiders, or scrapers) without our
permission".
