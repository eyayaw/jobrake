# LinkedIn (`linkedin`)

[LinkedIn](https://www.linkedin.com/jobs) is a professional network with a job board that employers
around the world post to. jobrake reads it through LinkedIn's login-free guest API, without an
account.

```sh
jobrake linkedin search -q "data scientist" -l "Amsterdam, North Holland, Netherlands" -n 2
jobrake linkedin search -q "research economist" -l "London, England" -n 5 -a 24 -d -o jobs.csv
jobrake linkedin places Birmingham
jobrake linkedin search -q "data scientist" -g 100356971
jobrake linkedin companies "Booking"
jobrake linkedin postings 4449382178
```

`search` requires `--location` or `--geoid` and returns postings in LinkedIn's order of relevance.
In Python the options are keyword arguments:
`scrape("linkedin", query="data scientist", geoid="102011674", details=True)`.

`postings` fetches the postings you name.
A LinkedIn reference is a numeric ID or an HTTPS posting URL,
including the link in a LinkedIn job alert email and a search page address with `currentJobId=`.
Any other reference is an error, and nothing is fetched.
`jobrake.identify` reads the same URLs, and a bare LinkedIn ID gives `None`.

## Options

| Option                  | Value                                           | Default                    |
| ----------------------- | ----------------------------------------------- | -------------------------- |
| `--query`, `-q`         | a job title or keywords                         | none                       |
| `--location`, `-l`      | a place, preferably with its region and country | required without `--geoid` |
| `--geoid`, `-g`         | a LinkedIn place ID, digits only                | none                       |
| `--radius`, `-r`        | kilometers, 0 or more                           | none sent                  |
| `--results`, `-n`       | a positive integer                              | 10                         |
| `--max-age-hours`, `-a` | a positive integer                              | no age limit               |
| `--company-ids`         | LinkedIn company IDs, digits only               | every employer             |
| `--easy-apply`          | only postings with LinkedIn's Easy Apply form   | off                        |
| `--early-applicant`     | only postings with fewer than 10 applicants     | off                        |
| `--details`, `-d`       | fetch each posting's page                       | off                        |

A posting must match every option given.
LinkedIn has no country editions, so `search` takes no `--country`.
Pass the place as text to `--location`, or its ID to `--geoid`.

### Query

jobrake sends the query unchanged.
LinkedIn matches loosely, so a returned posting need not contain every word you typed.
Where that matters, run several narrow queries and filter the results yourself.
Leave out `-q` to search without keywords.

LinkedIn documents [Boolean search operators](https://www.linkedin.com/help/linkedin/answer/a524335/using-boolean-search-on-linkedin?lang=en)
for its own search interface.
However, they do not behave as expected on the guest endpoint jobrake uses,
so write plain keywords for LinkedIn queries.

### Place

LinkedIn accepts a location or a geoId. Its guest geocoder may return no
postings for an **ambiguous place name**. Include the region and country whenever possible.

```sh
-l Amsterdam # Bad
-l "Amsterdam, Netherlands" # Good
-l "Amsterdam, North Holland, Netherlands" # Good
```

LinkedIn answers a place it cannot resolve as it answers a search that matches nothing,
so either way the search returns no postings and jobrake warns.

`--geoid | -g` takes a geoId, such as `--geoid 102011674`. This sends that ID straight to LinkedIn
and `--location` becomes optional. Without a geoId, jobrake searches by the location text.
[`jobrake linkedin places`](#lookups) finds a place's geoId and its full name.

`--radius` is in kilometers. Without it, jobrake sends no radius and leaves the distance to LinkedIn.
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
Each `id` is a geoId. A name can belong to several places: `Birmingham` lists
`Birmingham, England, United Kingdom`, whose `id` is `100356971`, ahead of
`Birmingham, Alabama, United States`.
Choose the candidate you want, then search with its `name` or its `id`.

`jobrake linkedin companies <name>` lists suggested companies as JSON,
with `id` and `name` for each entry. LinkedIn determines the order.
Subsidiaries and regional branches can have separate IDs, so choose
the intended employer or try a more specific name.

In Python they are `jobrake.sites.linkedin.places(fetcher, name)` and
`jobrake.sites.linkedin.companies(fetcher, name)`.

## Fields

A LinkedIn card carries `title`, `company`, `locations`, and `date`, and no details.
`--details | -d` fetches each posting page, and a value the page has replaces the card's.
[The record](../reference.md#the-record) says what each key means.

| Key                              | From a search                         | With `--details`                                               |
| -------------------------------- | ------------------------------------- | -------------------------------------------------------------- |
| `id`                             | LinkedIn's numeric posting ID         | the same                                                       |
| `url`                            | the posting page the card links to    | the same                                                       |
| `title`, `company`               | as the card shows them                | the page's                                                     |
| `locations`                      | one place, named as the card shows it | the page's places                                              |
| `date`                           | the card's date                       | the calendar date of the page's `posted_at`                    |
| `description`                    | absent                                | the posting's text                                             |
| `posted_at`, `expires_at`        | absent                                | when the page has them                                         |
| `employment_type`                | absent                                | when the page has it                                           |
| `salary_min`, `salary_max`       | absent                                | the posting's salary range, when the page gives one            |
| `company_url`, `company_logo`    | absent                                | when the page has them                                         |
| `apply_type`                     | absent                                | `onsite` for LinkedIn's own form, `offsite` for the employer's |
| `applicants`                     | absent                                | the count the page shows                                       |
| `experience_months`, `education` | absent                                | the experience, in whole months, and the credential asked for  |
| `site_data`                      | absent                                | `closed`, when the page marks the posting closed               |

A card's `url` comes without its query string.
A salary range comes with the `salary_currency` and `salary_period` the page gives for it.
A range read from the page markup has `salary_period` `HOUR`, `DAY`, `WEEK`, `MONTH`, or `YEAR`,
and the value in its structured data passes through as sent.

With `--details`, the places come from the page, read in English, and a place carries the
`city`, `region`, `country_code`, `latitude`, and `longitude` the page gives.
A posting the page places in several locations lists each.
A posting open in several cities can show one of them on its card and another on its page.
A page without a place leaves the card's, and a page without a `posted_at` leaves the card's date.

A posting placed in a whole country, such as "United States" or "Netherlands",
comes without `posted_at`, `expires_at`, coordinates, `experience_months`, and `education`.

LinkedIn shows a count above 200 as "Over 200", so `applicants` stops at 200.

`site_data` holds `closed`, which is `true` when the page says the posting no longer
accepts applications.
LinkedIn keeps serving such a posting, and a posting without the mark may still be closed.

A record has no `workplace_type`, `apply_url`, `language`, `department`, `team`, or `keywords`.

`jobrake linkedin postings` builds the record from the posting page alone, in a later run.
Its `url` is the page's own address, and a field only the card gave, such as a `date` when the page
has no `posted_at`, or the card's `title`, `company`, or `locations`, is absent or `None`.

## Limits

A search sends one request for about every ten postings.
LinkedIn limits guest traffic per IP, and jobrake allows short bursts
at a sustained pace of about 1.3 requests per second.
Lookups and posting pages share that pace.
Each process paces only its own requests, so concurrent runs on the same IP can reach
the limit sooner.
jobrake follows LinkedIn's redirects itself to pace each hop, so a
[`Fetcher`](../reference.md#python-api) of your own must honor `follow_redirects=False`.

The guest search stops at offset 1,000, so one search returns roughly 1,000 postings at most.
jobrake warns when that limit cuts a search short. Narrow the search to reach more.
The order can change between two runs of the same search.
To collect only new postings, repeat the search with `--max-age-hours` covering the time
since the last run.

LinkedIn refuses some requests whatever the pace.
jobrake retries a 429 up to five times.
If the 429 remains, the search raises `Stopped` with what it has collected so far.
So does an answer to a results request other than the search endpoint's HTTP 200, such as a
sign-in page.

`--details` costs one paced request for most uncached postings and up to three for the rest,
plus one for each redirect hop and each retry after a 429.
A [cached](../reference.md#configuration) posting costs none.
`postings` spends at least two requests on a bare ID and up to five on a `www.linkedin.com` address.
A `--details` search that could not fetch every posting's details raises `Stopped` too,
holding every posting it found and, in `failed`, the URLs of the postings it could not fetch.
When a posting page still answers 429 after its retries, jobrake stops fetching the rest.
Wait a while, then rerun, and the postings already fetched come from the cache.
A posting whose page answers 404 or 410 is gone:
a `--details` search keeps its card, and `postings` maps its reference to `None`, which the
CLI reports as gone.

> [!WARNING]
> LinkedIn answers posting pages with [HTTP 999](https://http.dev/999) from data center IPs,
> such as a Hetzner VPS.
> Searches and lookups keep working there, but every detail fetch fails.
> A `--details` search writes only its cards, `jobrake linkedin postings` writes nothing,
> and both exit 1.
> So use jobrake from the comfort of your home. :D

## Measured

LinkedIn documents its Boolean operators for its own search interface and nothing about the guest
endpoint. Everything this page says about that endpoint is measured.
In October 2026 the endpoint ignored a request for the newest postings first and ranked by relevance.
On 2026-11-11 it refused a retry about as often as a first attempt,
and it refused up to a quarter of requests in our tests.
No search in our tests got an answer other than a results page.
On 2026-11-14, on 144 postings in 18 countries, a page read in English named its place as its
card did. We saw the closed mark on two postings on 2026-10-21.
Four more are measurements without a recorded date or sample: the radius a search by geoId ignores,
the details a whole-country posting lacks, a card and a page that name different cities,
and HTTP 999 on a data center IP.
