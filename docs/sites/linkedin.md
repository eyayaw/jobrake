# LinkedIn (`linkedin`)

jobrake searches [LinkedIn](https://www.linkedin.com/jobs) through its guest endpoint,
the one LinkedIn serves to visitors who are not signed in, so you do not need an account.
LinkedIn does not document that endpoint, so what we say here about its behavior comes from our own tests.

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

> [!NOTE]
> jobrake asks LinkedIn for the newest postings first, but the guest endpoint ignores the request
> and ranks by relevance. The order can also change between two runs of the same search.
> To collect only new postings, repeat the search with `--max-age-hours` covering the time since the last run.

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

LinkedIn matches loosely, so a returned posting may not contain every word you typed.
Where that matters, run several narrow queries and filter the results yourself.

LinkedIn documents [Boolean search operators](https://www.linkedin.com/help/linkedin/answer/a524335/using-boolean-search-on-linkedin?lang=en)
for its own search interface. However, they do not behave as expected on
the guest endpoint jobrake uses, so write plain keywords for LinkedIn queries.

### Place

A LinkedIn search can cover every country at once, so it takes no `--country`.
LinkedIn accepts a location or a geoId. Its guest geocoder may return no postings
for an **ambiguous place name**, so include the region and country whenever possible.

```sh
-l Amsterdam # Bad
-l "Amsterdam, Netherlands" # Good
-l "Amsterdam, North Holland, Netherlands" # Good
```

If LinkedIn cannot make sense of the name, it returns nothing, as if no posting matched.
Try a fuller name (i.e., an unambiguous place name) or a geoId.

`--geoid` takes a geoId, such as `--geoid 102011674`. This sends that ID straight to LinkedIn
and `--location` becomes optional. Without a geoId, jobrake searches by the location text.
[`jobrake linkedin places`](#lookups) finds a place's geoId.

LinkedIn has no default radius. Its guest endpoint takes the distance in whole **miles**,
so jobrake rounds your kilometers, and `--radius 1` covers about 1.6 km.
According to our testing, the radius reliably widens or narrows a LinkedIn search by `--location`.
A search by geoId ignores the radius for some places, such as Amsterdam and Utrecht.

### Employers

Pass an employer's numeric ID to `--company-ids` to find job postings at that company.
You can pass several. Use [`jobrake linkedin companies`](#lookups) to find an employer's ID.

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

The lookups are also functions, `places(fetcher, name)` and `companies(fetcher, name)`, in `jobrake.sites.linkedin`.

## Fields

A search gives you each posting's `title`, `company`, `locations`, and `date`, because that is all
LinkedIn's search results show. For anything more, add `--details`.
jobrake then opens each posting's page and adds what it finds there: the description, when the
posting went up and when it closes, the employment type, the education and the experience (in
months) it asks for, the salary range, the applicant count, and whether you apply on LinkedIn
(`apply_type` is `onsite`) or on the employer's site (`offsite`).
Every key is in the [reference](../reference.md#fields-by-site).

Some of these fields hold less than their names promise:

- `applicants` stops at 200, because LinkedIn shows any larger count as "Over 200".
- LinkedIn keeps serving postings that no longer take applications.
  When the page says so, `site_data` holds `"closed": true`, but a posting without it may be closed too.
- In our tests, a posting placed in a whole country, such as "United States" or "Netherlands",
  came without its dates, coordinates, and requirements.
- With `--details`, `locations` comes from the page, with the city, region, country code, and
  coordinates. A posting open in several cities lists them all, and in our tests its search result sometimes showed a different one.
- LinkedIn gives jobrake no workplace type, application link, or language.

### Postings you already know

`jobrake linkedin postings` fetches postings by their ID or URL, so you can paste the link from a
LinkedIn job alert email, or a search page address with `currentJobId=`:

```sh
jobrake linkedin postings 4449382178
jobrake linkedin postings "https://nl.linkedin.com/jobs/view/data-scientist-at-acme-4449382178"
```

Since it reads only the posting page, you get what the page shows: a field the page lacks stays
empty, even if a search result had it.

## Requests

LinkedIn limits how much a visitor without an account may ask for, so jobrake goes slowly on
purpose, at about one request a second after a short burst.
Searches, lookups, and posting pages all count, so a `--details` search takes roughly a second per
posting, sometimes more.
Each run keeps its own pace, so we advise against running two at once from the same IP:
together they reach LinkedIn's limit sooner.

LinkedIn serves about 1,000 postings per search at most.
Split a bigger search by place or by `--max-age-hours`.

Even at this pace, LinkedIn turns some requests away.
jobrake retries each one up to five times. If LinkedIn keeps refusing, the search stops with what
it has found.
Wait a while, then run the search again.
The postings already fetched come from the [cache](../reference.md#configuration).

> [!WARNING]
> On a data center IP, such as a VPS, LinkedIn refuses posting pages with [HTTP 999](https://http.dev/999),
> so `--details` and `postings` fail there, while searches and lookups still work.
> Run `--details` and `postings` from a home connection.
