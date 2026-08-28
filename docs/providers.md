# Provider behavior

Indeed and LinkedIn share one search interface, but they interpret geography and fetch posting details differently.

| Site | Required geography | Posting details |
| --- | --- | --- |
| Indeed | `country` chooses the country edition. `location` narrows the search. | Included in search results |
| LinkedIn | `location` is required. Library calls ignore `country`. | Fetched with `--details` or `details=True` |

## Search filters

Every search entry point defaults to postings from the last seven days.
Searches return 10 jobs by default.
Indeed defaults to a 40 km radius. LinkedIn omits its undocumented distance parameter.

`max_age_hours=None` omits the age filter.
Positive values limit results to jobs posted within that many hours.
For library calls, `radius=None` uses Indeed's standard radius and omits LinkedIn's distance parameter.
`radius` accepts zero. `max_age_hours` and `results` must be positive.

## Indeed

### Locations

Set `country` to a name such as `germany` or `netherlands`.
Accepted shortcuts are `usa`, `us`, and `uk`.
`location` may contain a city or another place within that country.

### Search requests

jobrake asks Indeed for 100 results on every page and keeps the API's relevance order.
`results` accepts any positive count.
If that count is not a multiple of 100, jobrake returns only the needed jobs from the last page.

jobrake adds no delay between Indeed pages. Each request gets one attempt.
A transport failure, provider error without usable data, or unreadable response logs a warning and returns the jobs already collected.
Indeed parses each result independently and keeps every valid job on the page.
Invalid fields are omitted from an otherwise valid job.

## LinkedIn

LinkedIn's guest search returns summary cards.
Use `--details | -d` or `details=True` to fetch each posting page and add its detail fields.

### Locations

LinkedIn requires a location. Its guest geocoder may return no jobs for an ambiguous place name.
Include the region and country whenever possible.

```text
Amsterdam, North Holland, Netherlands
```

### Search limit

The guest search returns about ten cards per page and no cards at offsets of 1,000 or more.
jobrake stops before requesting offset 1,000, so one search can return roughly 1,000 postings.
It warns when this limit prevents it from returning the requested count.

### Request rate and retries

LinkedIn limits traffic by IP. jobrake sends a short initial burst, then waits about three seconds between requests.

Each process keeps its own token bucket.
LinkedIn combines traffic from every process on the same IP, so concurrent runs can reach the limit sooner.

After a 429, jobrake waits for the number of seconds in a numeric `Retry-After` header.
A missing or invalid header gives a ten-second wait.
It then retries once. A value over one minute skips the retry.

If the 429 remains, search returns the jobs already collected.
Detail fetching returns postings already fetched or found in the cache.

### Posting details and cache

For URLs with numeric posting IDs, cached detail fields are reused for one week.
Older fields are fetched again. URLs without an ID are fetched on every call.
jobrake records HTTP 404 and 410 responses and skips those postings on later cached runs.
Pass `--no-cache` or `cache=False` to bypass the cache.

Fetching an uncached posting costs at least one paced request.
A page without its structured data may require a second request for an English fragment.
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

jobrake does not intend to support Glassdoor, in the presence of Indeed.
Glassdoor became [part of Indeed](https://web.archive.org/web/20260704043638/https://www.glassdoor.com/about/) on July 1, 2026, and is not a priority.
If there is a huge interest, contributions for Glassdoor, or another major job board are welcome.
