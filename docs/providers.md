# Provider behavior

Indeed and LinkedIn share one search interface, but they interpret geography and fetch posting details differently.

| Site | Required geography | Posting details |
| --- | --- | --- |
| Indeed | `country` chooses the country edition. `location` narrows the search. | Included in search results |
| LinkedIn | Pass `location` or a geoId. Library calls ignore `country`. | Fetched with `--details` or `details=True` |

## Search queries

Search for a job title or keywords. jobrake sends the query unchanged to Indeed's `what` or LinkedIn's `keywords` field.

Each provider determines how operators, quotation marks, and parentheses affect results.
Those rules can differ between providers and change independently of jobrake.
Applications that need deterministic matching can expand a search into several provider queries, then filter and rank the returned jobs.

## Search filters

By default, searches ask the provider for jobs from the past seven days. Searches return 10 jobs by default.
Indeed defaults to a 40 km radius. LinkedIn omits its undocumented distance parameter.

`max_age_hours=None` omits the age filter. Positive values set the provider's age limit in hours.
For library calls, `radius=None` uses Indeed's standard radius and omits LinkedIn's distance parameter.
`results` and `max_age_hours` must be positive integers. `radius` must be a nonnegative integer, so zero is accepted.

## Indeed

### Query behavior

Indeed's mobile endpoint treats `title:` and `company:` as field restrictions.
Inside `title:`, parentheses group terms.
Quotation marks narrow phrase searches, and a leading minus can exclude a term.
These constructs can be combined:

```text
title:(data OR research)
company:"Booking.com"
title:analyst company:Booking.com
title:analyst -senior
```

Plain terms can match posting descriptions or other indexed content, and `description:<term>` does not reliably restrict results to descriptions.
`AND`, `OR`, and `NOT` act as provider search hints. Their results can differ from Boolean union, intersection, and exclusion.
Use jobrake's dedicated arguments for geography and posting age.

### Posting language

Use `--language CODE` to select postings in one language:

```sh
jobrake indeed -q econometrics -c netherlands --language en
```

Library searches accept `language="en"` through `scrape("indeed", ...)` or `indeed.search()`.
Omitting the option, or passing `None`, leaves language unrestricted.
Use the code from a posting's `language` field, such as `en` or `nl`. The input accepts two ASCII letters in either case, so `EN` and `Nl` work too. jobrake sends the code in lowercase. Indeed determines each posting's language.
Indeed's [language-code reference](https://docs.indeed.com/api/common/objects/LanguageCode) describes ISO 639-1. Search results also use the legacy codes `iw` for Hebrew and `in` for Indonesian, which jobrake preserves.
Values with the wrong type or format raise an error before any request. A correctly formatted code can still return no matches.

Indeed applies the restriction on every page together with company, remote, location, and age filters. The requested result count therefore applies to postings matching the language filter.
The CLI offers `--language` only for Indeed. A LinkedIn library search accepts `language`, warns, and runs without it.

### Job attributes

Find codes on postings matching a job title or keywords:

```sh
jobrake attributes indeed -c usa "data scientist"
```

The command reads the first 100 matching postings and prints a JSON list of `key` and `label` pairs. It applies no posting-age restriction. The list covers the sampled jobs, so another query can reveal additional codes.
Labels can differ by country edition. A label can also belong to several codes, and the lookup keeps each code separately. jobrake reads the codes live from Indeed.
Library callers use `jobrake.sites.indeed.attributes(fetcher, query, country)`. A lookup that finds no attributes returns `[]`. A failed request or unreadable response returns `None` and logs a warning. The CLI exits nonzero on failure.

Use those codes to filter jobs:

```sh
jobrake indeed -q "data scientist" -c usa --attribute 3CQB7
jobrake indeed -q economist -c usa --attribute CF3CP --attribute 6QC5F
```

`3CQB7` selects Spatial analysis. The second search requires both Full-time (`CF3CP`) and Doctoral degree (`6QC5F`). Several codes intersect: every returned posting must carry every selected code. To find jobs matching any of several codes, run separate searches and combine the results.
A code selects postings carrying that attribute. A Full-time match can also carry Part-time when the employer offers either arrangement. Attribute filters provide no exclusion option.

Pass `attributes=["3CQB7"]` to `scrape("indeed", ...)` or `indeed.search()`. Supply codes as nonblank strings in a list. jobrake removes surrounding whitespace before sending them to Indeed. `None` or `[]` leaves attributes unrestricted.
Attribute filters combine with company, language, location, and posting age on every page, before the requested result limit is applied.
The CLI exposes `--attribute` only for Indeed. LinkedIn library searches ignore `attributes`.

### Remote jobs

Pass `--remote` to search postings that Indeed tags Remote:

```sh
jobrake indeed -q "econometrics" -c usa --remote
```

Library callers pass `remote=True` to `scrape("indeed", ...)` or `indeed.search()`. The default, `False`, leaves remote status unrestricted.
`--remote` is shorthand for `--attribute DSQF7`. When combined with other attributes, a posting must carry the Remote tag and every other selected code.
Indeed applies this filter together with keywords, location, company, and posting age before returning each page.
The tag reflects Indeed's classification. Check the posting for residency and workplace requirements.

The age filter uses Indeed's `dateOnIndeed` field. A matching posting can have an older publication timestamp in `posted_at`.
LinkedIn's guest endpoint does not support remote filtering. jobrake offers `--remote` only for Indeed, and a LinkedIn library search with `remote=True` warns and runs without it.

### Companies

Find an Indeed employer key by looking up the company name in a country edition:

```sh
jobrake companies indeed "ABN AMRO" -c netherlands
```

Each JSON entry pairs an `employerKey` with a company name in `suggestion`. Results follow Indeed's suggestion order and may include related companies. Choose the employer whose jobs you want.
Library callers can use `jobrake.sites.indeed.companies(fetcher, name, country)`. A lookup with no matches returns `[]`. A failed request or unreadable response returns `None` and logs a warning. The command exits nonzero on failure.

Use the selected key to restrict job results to that employer:

```sh
jobrake indeed -q "data" -c netherlands --company fe219df7f711aa73
jobrake indeed -q "" -c netherlands --company fe219df7f711aa73
```

This key selects ABN AMRO. An empty query searches its postings without keywords. Location and posting-age options apply alongside the company filter.
For a library search, pass `companies=["fe219df7f711aa73"]` to `scrape()`. jobrake supports one Indeed employer key per search, supplied as a nonblank string. A list with multiple keys raises an error before any request. Use `None` or `[]` to omit this filter.

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

### Query behavior

The [Boolean search operators](https://www.linkedin.com/help/linkedin/answer/a524335/using-boolean-search-on-linkedin?lang=en) LinkedIn documents for its supported search interface do not work as documented on the guest endpoint used by jobrake.

### Easy Apply and early applicants

Use `--easy-apply` to find jobs with LinkedIn's Easy Apply form. `--early-applicant` requests LinkedIn's "under 10 applicants" filter.
Both can be combined with keywords, location or geoId, company IDs, and posting age:

```sh
jobrake linkedin -q "data scientist" -l Netherlands --easy-apply --early-applicant
```

Library callers pass `easy_apply=True` or `early_applicant=True` to `scrape("linkedin", ...)` or `linkedin.search()`.
Both default to `False`, which omits those restrictions. When both are enabled, results must match both filters.
LinkedIn applies them on every search page, including searches with `details=False`.

LinkedIn fixes the early-applicant threshold at fewer than 10 applicants. Its posting pages can show a broader count: "Be among the first 25 applicants" becomes `applicants=25` in jobrake.
An early-applicant result can therefore carry that value in its details.
Indeed applies neither option. Enabling either on an Indeed search draws a warning, and the search runs without it.

The guest endpoint ignores filters for workplace type, employment type, experience level, verified postings, and salary. jobrake leaves these out of its LinkedIn search options.
Employment type is available as a posting detail when `details=True`.

### Companies

Pass an employer's numeric ID to `--company ID` to find job postings at that company.
Repeat the option to include several employers.
Company filtering combines with keywords, geography, and the posting-age limit.
Look up an employer's name to find its LinkedIn company ID:

```sh
jobrake companies linkedin "ABN AMRO"
```

The command lists suggested companies as JSON, with `companyId` and `displayName` for each entry.
LinkedIn determines the order.
Subsidiaries and regional branches can have separate IDs, so choose the intended employer or try a more specific name.
Library callers use `jobrake.sites.linkedin.companies(fetcher, name)`.
It returns `[]` when LinkedIn supplies no suggestions and `None` if the request fails or the response cannot be read.
The CLI exits nonzero on failure.

Pass an employer's numeric ID to `--company ID` to find job postings at that company.
Repeat the option to include several employers.
Company filtering combines with keywords, geography, and the posting-age limit.

```sh
jobrake linkedin -q "data" -l "Netherlands" --company 1173
jobrake linkedin -q "" -l "Netherlands" --company 1173 --company 2220078
```

These IDs select ABN AMRO and PwC Nederland. Use `-q ""` to search without keywords.
Within Python, pass `companies=["1173", "2220078"]` to `scrape()`. Each ID must be a string of digits `0-9`.
Use `None` or `[]` to search without a company filter. Indeed reads the same argument as a single employer key.

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

For URLs with numeric posting IDs, cached detail fields remain fresh for one week by default.
[`JOBRAKE_CACHE_TTL`](usage.md#cache-location-and-lifetimes) sets this period in seconds.
Older fields are fetched again. URLs without an ID are fetched on every call.
jobrake records HTTP 404 and 410 responses and skips those postings on later cached runs.
Pass `--no-cache` or `cache=False` to bypass the cache.

Every stored value records the cache format that produced it, and jobrake reads only the format it writes. A release whose job fields or parsers have moved on therefore starts from an empty table and fills it again as you search. Posting fields, posting addresses, and place resolutions each carry their own format version, so a change to one leaves the others' cached values in place.

Fetching an uncached posting costs at least one paced request.
A page without its structured data may require a second request for an English fragment.

### Fetching known postings

`jobrake details linkedin <ID|URL> ...` fetches postings you already know, in the order given.

LinkedIn serves the schema.org block only from a posting's canonical URL, the title slug on the host of the posting's country.
That host is `www.linkedin.com` for the United States and a country subdomain, such as `nl.linkedin.com`, elsewhere.
Another country's host, a slugless `/jobs/view/<id>`, and the guest fragment all return the posting without that block, and so without the dates, coordinates, and requirements only it carries. A salary still comes through when the page markup states one in English.
A posting placed in a whole country, such as "United States" or "Netherlands", has no block at any address.

A `www` URL looks the same for a posting from any country, so jobrake fetches only a country-subdomain URL with a slug as given.
Every other reference, US `www` URLs included, costs one lookup the first time. jobrake reads the canonical URL from the guest fragment, which transfers about a tenth as many bytes as the page.
The cache keeps that URL, so a cached posting costs no request, whichever reference names it.

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
