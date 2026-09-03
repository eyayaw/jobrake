# Provider behavior

Indeed and LinkedIn share one search interface, but they interpret geography and fetch posting details differently.

| Site | Required geography | Posting details |
| --- | --- | --- |
| Indeed | `country` chooses the country edition. `location` narrows the search. | Included in search results |
| LinkedIn | Pass `location` or a geoId. Library calls ignore `country`. | Fetched with `--details` or `details=True` |

## Search filters

Every search entry point defaults to postings from the last seven days. Searches return 10 jobs by default.
Indeed defaults to a 40 km radius. LinkedIn omits its undocumented distance parameter.

`max_age_hours=None` omits the age filter. Positive values limit results to jobs posted within that many hours.
For library calls, `radius=None` uses Indeed's standard radius and omits LinkedIn's distance parameter.
`results` and `max_age_hours` must be positive integers. `radius` must be a nonnegative integer, so zero is accepted.

## Indeed

### Locations

Set `country` to a name such as `germany` or `netherlands`. Accepted shortcuts are `usa`, `us`, and `uk`.
`location` may contain a city or another place within that country.

`jobrake places indeed <name> --country <edition>` prints the edition's location suggestions as JSON, best match first.
Each `suggestion` can be passed directly to `location`.
`locationType` helps distinguish cities, states or provinces, postal areas, and landmarks with similar names.
Library callers use `jobrake.sites.indeed.places`.

### Search requests

jobrake asks Indeed for 100 results on every page and keeps the API's relevance order. `results` accepts any positive integer.
If that count is not a multiple of 100, jobrake returns only the needed jobs from the last page.

jobrake adds no delay between Indeed pages. Each request gets one attempt.
A transport failure, provider error without usable data, or unreadable response logs a warning and returns the jobs already collected.
Indeed parses each result independently and keeps every valid job on the page.
Invalid fields are omitted from an otherwise valid job.

## LinkedIn

LinkedIn's guest search returns summary cards.
Use `--details | -d` or `details=True` to fetch each posting page and add its detail fields.

### Locations

LinkedIn accepts a location or a geoId. Its guest geocoder may return no jobs for an ambiguous place name.
Include the region and country whenever possible.

```text
Amsterdam, North Holland, Netherlands
```

Pass `--geoid | -g` (or `geoid=True`) to resolve `location` through LinkedIn's place lookup.
jobrake reports the selected place and caches it for later runs.
If resolution fails, it returns no jobs. Omit the flag to search by location text.

`--geoid 102011674` (or `geoid="102011674"`) sends a known ID directly, with `location` optional.

`jobrake places linkedin <name>` prints LinkedIn's candidates as JSON, best match first, and caches them.
Cache matching ignores case, commas, surrounding punctuation, and repeated spaces.

```sh
$ jobrake places linkedin birmingham
[
  {
    "geoId": "100356971",
    "displayName": "Birmingham, England, United Kingdom"
  },
  {
    "geoId": "102905961",
    "displayName": "Birmingham, Alabama, United States"
  },
  ...
]
```

Choose the candidate you want, then search with its display name or geoid:

```sh
jobrake linkedin -q "data scientist" -l "Birmingham, England, United Kingdom"
jobrake linkedin -q "data scientist" -g 100356971
```

Library callers use `jobrake.sites.linkedin.places` and `resolve_geoid`.

### Search limit

The guest search returns about 10 cards per page and stops before offset 1,000.
One search can therefore return roughly 1,000 postings. jobrake warns if the limit prevents the requested count.

### Request rate and retries

LinkedIn limits traffic per IP. jobrake permits a short burst, then waits about 3 seconds between requests.
Each process has its own limiter, so concurrent runs on the same IP can reach the limit sooner.

After a 429, jobrake waits for a numeric `Retry-After` value or ten seconds, then retries once.
A value over one minute skips the retry. If the 429 remains, jobrake returns the search results or detail postings resolved so far.

### Posting details and cache

For URLs with numeric posting IDs, cached detail fields are reused for one week.
Older fields are fetched again. URLs without an ID are fetched on every call.
jobrake records HTTP 404 and 410 responses and skips those postings on later cached runs.
Pass `--no-cache` or `cache=False` to bypass the cache.

Every stored value records the cache format that produced it, and jobrake reads only the format it writes. A release whose job fields or parsers have moved on therefore starts from an empty cache and fills it again as you search.

Fetching an uncached posting costs at least one paced request.
A page without its structured data may require a second request for an English fragment.

### Fetching known postings

`jobrake details linkedin <ID|URL> ...` fetches postings you already know, in the order given.

LinkedIn serves the schema.org block only from a posting's canonical URL, the one carrying both its country subdomain and its title slug.
A slugless `/jobs/view/<id>`, a `www` address, and the guest fragment all return the posting without that block, and so without the dates, coordinates, and requirements only it carries. A salary still comes through when the page markup states one in English.
jobrake therefore fetches a canonical URL as given and resolves every other reference first, reading the canonical URL from the guest fragment, which transfers about a tenth as many bytes as the page.

The URL a search prints is canonical, so it costs the fewest requests: a posting already in the cache needs none at all.
Anything else spends that one lookup.

The posting ID is the identity throughout, so several references to one posting return one job, and the cache stores that posting once.
A reference that is neither a numeric ID nor a LinkedIn posting address is an error, and nothing is fetched.
A posting that is gone or unreachable is reported and left out. A persistent 429 ends the lookups, and jobrake answers from the cache for the postings whose addresses it already had.
Library callers use `jobrake.sites.linkedin.fetch_details`.

For a large search, omit `-d` and fetch only the postings you want:

```python
import asyncio

from jobrake import scrape
from jobrake.fetchkit import HttpxFetcher
from jobrake.sites import linkedin


async def main():
    async with HttpxFetcher() as fetcher:
        jobs = await scrape(
            "linkedin",
            query="data scientist",
            location="Amsterdam, North Holland, Netherlands",
            results=10,
            fetcher=fetcher,
        )
        urls = [job["url"] for job in jobs if "senior" not in (job["title"] or "").lower()]
        return await linkedin.fetch_postings(fetcher, urls)


postings = asyncio.run(main())
```

`fetch_postings()` maps each URL to its detail fields or to `None` after HTTP 404 or 410.
A URL is absent from the result after a retryable failure. Calling the function again retries it.

## Unsupported boards

Glassdoor is not planned because it is now [part of Indeed](https://web.archive.org/web/20260704043638/https://www.glassdoor.com/about/).
