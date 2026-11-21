# LinkedIn (`linkedin`)

jobrake reads [LinkedIn](https://www.linkedin.com/jobs)'s job search through its guest endpoint,
which needs no account. LinkedIn documents nothing about that endpoint, so what this page says
about it is what we measured.

```sh
jobrake linkedin search -q "data scientist" -l "Amsterdam, North Holland, Netherlands" -n 2
jobrake linkedin search -q "research economist" -l "London, England" -n 5 -a 24 -d -o jobs.csv
jobrake linkedin postings 4449382178
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("linkedin", query="data scientist", geoid="102011674", details=True))
```

jobrake asks LinkedIn for the newest postings first, but the guest endpoint ignores the request
and ranks by relevance. The order can also change between two runs of the same search.
To collect only new postings, repeat the search with `--max-age-hours` covering the time
since the last run.

## Options

| Option                  | Value                                           | Default                    |
| ----------------------- | ----------------------------------------------- | -------------------------- |
| `--query`, `-q`         | a job title or keywords                         | none                       |
| `--location`, `-l`      | a place, preferably with its region and country | required without `--geoid` |
| `--geoid`, `-g`         | a LinkedIn place ID                             | none                       |
| `--radius`, `-r`        | kilometers around the place                     | none sent                  |
| `--results`, `-n`       | the number of postings to return                | 10                         |
| `--max-age-hours`, `-a` | the oldest posting to keep, in hours            | no age limit               |
| `--company-ids`         | LinkedIn company IDs                            | every employer             |
| `--easy-apply`          | keep only postings with LinkedIn's Easy Apply   | off                        |
| `--early-applicant`     | keep only postings with under 10 applicants     | off                        |
| `--details`, `-d`       | fetch each posting's page                       | off                        |

### Query

jobrake sends the query unchanged to LinkedIn's `keywords` field.
LinkedIn matches loosely, so a returned posting need not contain every word you typed.
Where that matters, run several narrow queries and filter the results yourself.

LinkedIn documents [Boolean search operators](https://www.linkedin.com/help/linkedin/answer/a524335/using-boolean-search-on-linkedin?lang=en)
for its own search interface.
However, they do not behave as expected on the guest endpoint jobrake uses,
so write plain keywords for LinkedIn queries.

### Place

A LinkedIn search covers every country at once, so it takes no `--country`.
LinkedIn accepts a location or a geoId. Its guest geocoder may return no
postings for an **ambiguous place name**. Include the region and country whenever possible.

```sh
-l Amsterdam # Bad
-l "Amsterdam, Netherlands" # Good
-l "Amsterdam, North Holland, Netherlands" # Good
```

LinkedIn answers a place it cannot resolve as it answers a search that matches nothing,
and jobrake warns.

`--geoid | -g` takes a geoId, such as `--geoid 102011674`. This sends that ID straight to LinkedIn
and `--location` becomes optional. Without a geoId, jobrake searches by the location text.
[`jobrake linkedin places`](#lookups) finds a place's geoId.

LinkedIn has no default radius.
The guest endpoint takes the distance in miles through an undocumented parameter,
so jobrake sends your kilometers rounded to whole miles, and `-r 1` covers about 1.6 km.
The radius reliably widens or narrows a LinkedIn search by `--location`.
A search by geoId ignores it for some places, such as Amsterdam and Utrecht.

### Employers

Pass an employer's numeric ID to `--company-ids` to find job postings at that company.
Unlike with Indeed, here we can provide several employers.
[`jobrake linkedin companies`](#lookups) finds an employer's ID.

```sh
jobrake linkedin search -l "Netherlands" -q "data scientist" --company-ids 11348
jobrake linkedin search -l "Netherlands" --company-ids 11348 215713
```

These IDs select _Booking.com_ and _ING Nederland_.

### Easy Apply and early applicants

Use `--easy-apply` to find postings with LinkedIn's Easy Apply form.
`--early-applicant` requests LinkedIn's "under 10 applicants" filter.

```sh
jobrake linkedin search -q "data scientist" -l Netherlands --easy-apply --early-applicant
```

With both set, a posting must match both. Neither needs `--details`.

LinkedIn's posting pages show a broader count than the filter's threshold.
"Be among the first 25 applicants" becomes `applicants=25` in jobrake,
so an early-applicant result can carry that value.

### Unsupported filters

The guest endpoint ignores filters for workplace type (remote, hybrid, and on-site),
employment type, experience level, verified postings, and salary, so jobrake offers none of them.
Employment type is still available as a posting detail with `--details`.
jobrake's LinkedIn search has no language filter.

## Lookups

`jobrake linkedin places <name>` prints LinkedIn's candidates as JSON, best match first.

```sh
jobrake linkedin places Birmingham
```
```json
[
  {
    "id": "100356971",
    "name": "Birmingham, England, United Kingdom"
  },
  {
    "id": "102905961",
    "name": "Birmingham, Alabama, United States"
  },
  ...
]
```

Choose the candidate you want, then search with its display name or geoId:

```sh
jobrake linkedin search -q "data scientist" -l "Birmingham, England, United Kingdom"
jobrake linkedin search -q "data scientist" -g 100356971
```

`jobrake linkedin companies <name>` lists suggested companies:

```sh
jobrake linkedin companies "Booking"
```
```json
[
  {
    "id": "11348",
    "name": "Booking.com"
  },
  {
    "id": "10198247",
    "name": "Booking Holdings (NASDAQ: BKNG)"
  },
  {
    "id": "17896204",
    "name": "Booking Experts B.V."
  }
]
```

LinkedIn determines the order. Subsidiaries and regional branches can have separate IDs, so choose
the intended employer or try a more specific name.

In Python the lookups are `places(fetcher, name)` and `companies(fetcher, name)`
in `jobrake.sites.linkedin`.

## Fields

A LinkedIn search result carries `title`, `company`, `locations`, and `date`, and no
[details](../reference.md#the-record).
`--details | -d` fetches each posting page and adds `description` and, when the page has them,
`posted_at`, `expires_at`, `employment_type`, `education`, `experience_months`, `apply_type`,
`applicants`, `company_url`, `company_logo`, `salary_min`, `salary_max`, `salary_currency`,
`salary_period`, and `site_data`.

- `id` is LinkedIn's numeric posting ID,
  and `url` is the posting page the search result links to, without its query string.
- `locations` holds one place, named as the search result shows it.
  With `--details`, the places come from the page, read in English, and a place carries the
  `city`, `region`, `country_code`, `latitude`, and `longitude` the page gives.
  A posting the page places in several locations lists each.
  In our measurements, a posting open in several cities can show one of them in the search result
  and another on its page.
- `apply_type` is `onsite` for LinkedIn's own application form and `offsite` for the employer's.
- `applicants` is the count the page shows.
  LinkedIn shows a count above 200 as "Over 200", so `applicants` stops at 200.
- `experience_months` and `education` are the experience, in whole months,
  and the credential the posting asks for.
- The salary fields hold the posting's salary range when the page gives one.
- `site_data` holds `closed`, which is `true` when the page says the posting no longer
  accepts applications.
  LinkedIn keeps serving such a posting, and a posting without the mark may still be closed.
- In our measurements, a posting placed in a whole country, such as "United States" or
  "Netherlands", comes without its dates, coordinates, and requirements.
- A record has no `workplace_type`, `apply_url`, or `language`.

`jobrake linkedin postings` fetches postings you already know.
A reference is a numeric ID or an HTTPS posting URL,
including the link in a LinkedIn job alert email and a search page address with `currentJobId=`.
The command reads the posting page alone. Its `url` is the page's own address, and a field the
page lacks is absent or `None`, even when a search result had it.

## Requests

LinkedIn limits guest traffic per IP, and jobrake allows short bursts
at a sustained pace of about 1.3 requests per second.
Lookups and posting pages share that pace.
Each process paces only its own requests, so concurrent runs on the same IP can reach
the limit sooner.

The guest search stops at offset 1,000, so one search returns roughly 1,000 postings at most.
jobrake warns when that limit cuts a search short.

LinkedIn refuses some requests whatever the pace, up to a quarter of them in our tests.
jobrake retries a 429 up to five times.
If the 429 remains, the search raises [`Stopped`](../reference.md#stopped) with what it has
collected so far.
So does an answer to a results request other than the search endpoint's HTTP 200, such as a
sign-in page.
No search in our tests met one.

`--details` costs one paced request for most uncached postings and up to three for the rest.
A [cached](../reference.md#configuration) posting costs none.
When a posting page still answers 429 after its retries, jobrake stops fetching the rest.
Wait a while, then rerun, and the postings already fetched come from the cache.
A posting page that answers 404 or 410 counts as a posting gone.

On a data center IP, such as a VPS, LinkedIn refuses posting pages
with [HTTP 999](https://http.dev/999).
Searches and lookups keep working, but every detail fetch fails.
