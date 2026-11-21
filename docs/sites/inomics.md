# INOMICS (`inomics`)

[INOMICS](https://inomics.com) lists jobs for economists in academia, research, and industry,
from PhD positions to professorships.

```sh
jobrake inomics search -n 500 -o inomics.jsonl
jobrake inomics search -q labor -c de
jobrake inomics search -c de --category postdoc -d
jobrake inomics search --category postdoc --category professor --jel J --jel E -d
jobrake inomics postings https://inomics.com/job/1555749
```

A search returns the postings in INOMICS's order of relevance, 100 by default.
`postings` fetches the postings you name, each by a record's `url` or by the posting's address
with its title slug. Any other reference is an error, and nothing is fetched.
INOMICS takes postings down over time, so the example above may be gone.
Use references from a recent search.
No option is required. In [Python](../reference.md#python-api) the options are keyword arguments:
`scrape("inomics", country="de", category=["postdoc"], details=True)`.

## Options

| Option            | Value                                    | Default        |
| ----------------- | ---------------------------------------- | -------------- |
| `--query`, `-q`   | keywords                                 | none           |
| `--country`, `-c` | an ISO 3166-1 alpha-2 code, such as `de` | every country  |
| `--category`      | codes or names from the table below      | every category |
| `--jel`           | JEL letters, `A` to `R` or `Z`           | every field    |
| `--results`, `-n` | a positive integer                       | 100            |
| `--details`, `-d` | fetch each posting's page                | off            |

`--query | -q` is the site's keyword search, and `--country | -c` keeps the postings in one country.
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
instead, before any request.
The [README](../../README.md#cli) describes the options every site shares, `--output` and `--format` among them.

INOMICS has no date filter, so a search takes no `--max-age-hours`.
To keep the recent postings, filter on `date` yourself:

```sh
jobrake inomics search -n 500 | jq '[.[] | select(.date != null and .date >= "2026-11-14")]'
```

## Fields

A card lacks the description and the deadline,
and `--details | -d` fetches each posting's page for them.
[The record](../reference.md#the-record) describes every key.

| Key                 | From a search                          | With `--details`                       |
| ------------------- | -------------------------------------- | -------------------------------------- |
| `url`               | `https://inomics.com/job/<id>`         | the same                               |
| `company`           | the first employer the card names      | the hiring organization the page names |
| `locations`         | one place: its `name` and `city`       | adds `region` and `country_code`       |
| `date`, `posted_at` | the day the card shows as posted       | the same day, with one exception       |
| `workplace_type`    | `hybrid` or `remote`, if the card says | the same                               |
| `site_data`         | `types`, such as `["Postdoc Job"]`     | the same                               |
| `description`       | absent                                 | the description on the posting's page  |
| `expires_at`        | absent                                 | the deadline, if the page has it       |

A card that names no employer leaves `company` as `None`.
A place is named as the card writes it, such as `Saarbrücken, Germany`, with its `city`,
or by the country alone. The card names the country in words.
INOMICS moves the day a card shows as posted to the day it reposts the posting.
`site_data` holds the card's `types`, such as `Postdoc Job` or `Assistant Professor / Lecturer Job`.
A posting can also carry the type of a program, scholarship, or course, such as `PhD Program`.
A record has no salary, employment type, or application link.

`--details` takes the place from the posting's page when the page names one.
When the page gives the country's code, the place takes the page's label,
which matched the card's on the pages we read, and adds its `region` and `country_code`.
A page without the country's code gives its city and region and no country, named from both,
such as `Umeå, Västerbotten` where the card named `Umeå, Sweden`.
A page that names no city drops the city the card gave.
The posting's page dates a posting the same way as its card.
A posting INOMICS also lists as a scholarship dates it by the day it was entered instead,
so `--details` can move that posting's `date`.

`postings` reads the page alone, so its records have the fields of the last column
without `workplace_type` and `site_data`, which only a card carries.

## Limits

A search is one request and returns the first `--results` postings.
The default of 100 can fall short of the whole board, which held 112 postings on 2026-11-17,
so raise `--results` to read all of it.
A failed request, or an answer jobrake cannot read, such as one without the count,
raises [`Stopped`](../reference.md#stopped)
with no postings.
An answer with fewer cards than both `--results` and its count raises `Stopped` with the postings
it holds.

`--details` and `jobrake inomics postings` fetch each posting's page, one request per posting,
one at a time, which a [cached](../reference.md#configuration) posting skips.
A page answering 404 or 410 counts as a posting gone:
a search keeps its card, and `postings` reports it and leaves it out.
A posting whose page could not be fetched also keeps its card,
and the search raises `Stopped` with the URLs to retry through `postings`.

## Terms

The INOMICS [terms and conditions](https://inomics.com/terms-and-conditions), in section C.3.b,
forbid collecting users' content or information, or otherwise accessing the INOMICS sites,
"using automated means (such as harvesting bots, robots, spiders, or scrapers) without our
permission".

## Measured

jobrake reads the endpoint that INOMICS's search page reads its results from.
The counts are from the 112 postings it listed on 2026-11-17, the pages of 17 of them read that
day, and 20 posting pages read on 2026-11-18.
Of the 112 cards, 2 named no employer, 2 named more than one, 7 named a country alone,
and 1 named no place. All 17 pages read on 2026-11-17 with a block dated like 2026/11/13 gave the card's day.
Of the 15 postings in Germany, every page gave the country's code and 9 gave no deadline.
Of the 20 pages, 2 gave no country code: a scholarship and a program.
