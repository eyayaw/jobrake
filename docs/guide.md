# jobrake guide

jobrake provides one interface for Indeed, LinkedIn, EconJobMarket, and employers' boards on six applicant tracking systems, but the sites differ in how they interpret geography, apply search filters, and fetch posting details.
Run `jobrake -h` for the sites, `jobrake <site> -h` for a site's commands, and `jobrake <site> <command> -h` for their options.

- [Search for jobs](#search-for-jobs)
- [Narrow the results](#narrow-the-results)
- [Fetch posting details](#fetch-posting-details)
- [Employer boards](#employer-boards)
- [EconJobMarket](#econjobmarket)
- [Read and save results](#read-and-save-results)
- [Use the Python API](#use-the-python-api)
- [Request limits and partial results](#request-limits-and-partial-results)
- [Cache location and lifetimes](#cache-location-and-lifetimes)
- [Other job boards](#other-job-boards)

## Search for jobs

Choose a site and supply a job title or keywords:

```sh
jobrake indeed search -q "data scientist" -c Netherlands -l Amsterdam -n 2
jobrake linkedin search -q "data scientist" -l "Amsterdam, North Holland, Netherlands" -n 2
```

Both commands ask for two recent postings near Amsterdam, Netherlands, but each names that place its own way.
Indeed searches one country edition at a time, so `--country` is required, and `--location` narrows that edition to a city or area within it.
LinkedIn has no editions: pass the place as text to `--location`, or its ID to `--geoid`, and leave `--country` out.

Three more options shape the result set rather than its content. By default, they return **10 jobs** with **no age limit**.

| Option               | CLI                     | Library         | Accepted values                                  |
| -------------------- | ----------------------- | --------------- | ------------------------------------------------ |
| Result limit         | `--results`, `-n`       | `results`       | a positive integer                               |
| Posting age in hours | `--max-age-hours`, `-a` | `max_age_hours` | a positive integer, or unset for no age limit    |
| Search radius in km  | `--radius`, `-r`        | `radius`        | $\ge 0$, or `None` on LinkedIn to send no radius |

> [!NOTE]
> Indeed measures posting age against `dateOnIndeed`, so a job inside your age window can still carry an older `posted_at`, the publication timestamp the search returns.
>
> Indeed's default radius covers 40 km around the location. LinkedIn has no default.
> LinkedIn's guest endpoint takes the distance in miles through an undocumented parameter, so jobrake sends your kilometers rounded to whole miles.
> The radius reliably widens or narrows a LinkedIn search by `--location`. A search by geoId ignores it for some places, such as Amsterdam and Utrecht.

### Write a query

Search for a job title or keywords. jobrake sends the query unchanged to Indeed's `what` or LinkedIn's `keywords` field.

Both sites match loosely, so a returned job need not contain every word you typed.
Where that matters, run several narrow queries and filter the results yourself.

#### Indeed query syntax

Indeed's mobile endpoint treats `title:` and `company:` as field restrictions.
Inside `title:`, parentheses for grouping terms and `OR` work.
Quotation marks narrow phrase searches, and a leading minus can exclude a term.
Note that these operations can be combined.

```text
title:(data OR research)
company:"Booking.com"
title:analyst company:Booking.com
title:analyst -senior
```

However, plain terms behave differently. They can match posting descriptions or
other indexed content, so `data OR research` may return jobs with neither word in the title.
You may be tempted to try `description:<term>`, but it does not reliably restrict
results to descriptions. `AND`, `OR`, and `NOT` act as Indeed search hints on their own.
Their results can differ from Boolean union, intersection, and exclusion.
Importantly, we do not advise mixing geography and posting age with search queries
(e.g., `"data science jobs in England last 24 hours"`), rather use their own arguments.

#### LinkedIn query syntax

LinkedIn documents [Boolean search operators](https://www.linkedin.com/help/linkedin/answer/a524335/using-boolean-search-on-linkedin?lang=en) for its own search interface.
However, they do not behave as expected on the guest endpoint jobrake uses,
so write plain keywords for LinkedIn queries.

### Choose a location

#### Indeed locations

Set `country` to a name such as `Germany` or `Netherlands`. Accepted shortcuts
are `USA`, `US`, and `UK`. `location` may contain a city or another place within
that country.

`jobrake indeed places <name> --country <edition>` prints the edition's location
suggestions as JSON, best match first. Each `id` can be passed directly
to `--location`. For library calls use `jobrake.sites.indeed.places`.

#### LinkedIn locations

LinkedIn accepts a location or a geoId. Its guest geocoder may return no
jobs for an **ambiguous place name**. Include the region and country whenever possible.

```sh
-l Amsterdam # Bad
-l "Amsterdam, Netherlands" # Good
-l "Amsterdam, North Holland, Netherlands" # Good
```

`--geoid | -g` takes a geoid, such as `--geoid 102011674`.
This sends that ID straight to LinkedIn and `location` becomes optional.
The library call equivalent is `geoid="102011674"`.
Note that leaving the geoid option out is fine, jobrake just searches by location text.

If you want to know the geoid of a place name, you can use `jobrake linkedin places <name>`,
which prints LinkedIn's candidates as JSON, best match first.

```sh
jobrake linkedin places Birmingham

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

Choose the candidate you want, then search with its display name or geoid:

```sh
jobrake linkedin search -q "data scientist" -l "Birmingham, England, United Kingdom"
jobrake linkedin search -q "data scientist" -g 100356971
```

Library callers use `jobrake.sites.linkedin.places`.

### Lookup commands

The `places`, `companies`, and `attributes` commands print JSON lists of `{"id", "name"}` entries, and their
library functions return the same lists. Each `id` is the value a search takes. An empty list means the lookup
found no matches. A failed request or unreadable response raises `Stopped` in a library call. The CLI exits nonzero on failure.

## Narrow the results

Search filters apply on every page, alongside keywords and geography, **before the result limit is applied**.
Each one has a CLI option and a library argument of the same name.
Pass the library argument to `scrape()` or the site's `search()` function.

| Filter           | CLI                 | Library                | Site                    | Unset   |
| ---------------- | ------------------- | ---------------------- | ----------------------- | ------- |
| Employers        | `--company-ids`     | `company_ids=[...]`    | LinkedIn, Indeed        | `None`  |
| Posting language | `--language`        | `language="en"`        | Indeed                  | `None`  |
| Job attributes   | `--attributes`      | `attributes=[...]`     | Indeed                  | `None`  |
| Remote           | `--remote`          | `remote=True`          | Indeed, SmartRecruiters | `False` |
| Easy Apply       | `--easy-apply`      | `easy_apply=True`      | LinkedIn                | `False` |
| Early applicant  | `--early-applicant` | `early_applicant=True` | LinkedIn                | `False` |

An option left at its **unset** value (or an empty list) stays out of the search.
A list option takes several values after one flag, `--attributes CF3CP 6QC5F`, or across repeats.

> [!NOTE]
> Each site takes only the filters it applies.
> `scrape("linkedin", remote=True)` raises `TypeError` before any request and lists LinkedIn's options,
> and `jobrake linkedin search --remote` fails as an unrecognized argument.

### Companies

Both sites filter by **employer identifier**, and both need a lookup to turn a name into one.
The identifiers differ in form, and so does the number of companies a single search accepts.

#### Indeed employers

Find an Indeed employer key by looking up the company name in a country edition:

```sh
jobrake indeed companies "Booking" -c Netherlands
```
```json
[
  {
    "id": "8e8f030e53ea29e4",
    "name": "Booking.com"
  },
  {
    "id": "aee0b02548b689e2",
    "name": "Booking Experts"
  },
  {
    "id": "542f63b11393c5a9",
    "name": "BookingGo"
  }
]
```

Each JSON entry pairs an employer key in `id` with a company name in `name`.
Results follow Indeed's suggestion order and may include related companies.
Choose the employer whose jobs you want.
Library callers use `jobrake.sites.indeed.companies(fetcher, name, country=...)`.

Use the selected key to restrict job results to that employer:

```sh
jobrake indeed search -c Netherlands -q "data scientist" --company-ids 8e8f030e53ea29e4
jobrake indeed search -c Netherlands --company-ids 8e8f030e53ea29e4
```

This key selects _Booking.com_. Without `-q`, the search covers its postings without keywords.
For a library search, pass `company_ids=["8e8f030e53ea29e4"]` to `scrape()`.

> [!TIP]
> Leave out `-q` to search without keywords, works for both Indeed and LinkedIn.
> One good use case is searching for openings from a certain company.

Indeed intersects the keys it receives, so a search takes one employer key and rejects more.
Search one employer at a time and combine the results.

#### LinkedIn employers

Look up an employer's name to find its LinkedIn company ID:

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
  },
  {
    "id": "92790319",
    "name": "Booking Express"
  },
  {
    "id": "5268984",
    "name": "bookingkit"
  },
  {
    "id": "7795107",
    "name": "BookingJini"
  },
  {
    "id": "99898831",
    "name": "BooKing"
  },
  {
    "id": "34581028",
    "name": "Booking Shake"
  },
  {
    "id": "6793622",
    "name": "Booking Health GmbH"
  },
  {
    "id": "109254975",
    "name": "Booking Hub"
  }
]
```

The command lists suggested companies as JSON, with `id` and `name` for each entry.
LinkedIn determines the order. Subsidiaries and regional branches can have separate IDs, so choose
the intended employer or try a more specific name.
Library callers use `jobrake.sites.linkedin.companies(fetcher, name)`.

Pass an employer's numeric (a string of digits `0-9`) ID to `--company-ids` to find
job postings at that company. Unlike with Indeed, here we can provide several employers.

```sh
jobrake linkedin search -l "Netherlands" -q "data scientist" --company-ids 11348
jobrake linkedin search -l "Netherlands" --company-ids 11348 215713
```

These IDs select _Booking.com_ and _ING Nederland_. For a library search, pass
`company_ids=["11348", "215713"]` to `scrape()`.

### Job posting language

Use `--language CODE` to select Indeed postings in one language:

```sh
jobrake indeed search -q econometrics -c Netherlands --language en
```

Indeed decides each posting's language. The option accepts two-letter language codes
such as `EN` and `NL`. Indeed's [language-code reference](https://docs.indeed.com/api/common/objects/LanguageCode) describes
ISO 639-1. Search results also carry the legacy codes `iw` for Hebrew and `in` for Indonesian, which jobrake preserves.
An Indeed search rejects a malformed value before any request, though a well-formed code can still match nothing.

LinkedIn does not have language support.

### Job attributes

The `attributes` command helps you find codes on postings matching a job title or keywords.

```sh
jobrake indeed attributes -c usa "data scientist"
```

The command reads the first 100 matching postings and prints a JSON list of code and label pairs, as `id` and `name`.
It applies no posting-age restriction. Those postings carry several (hundred) attributes between them.
Search the list by label:

```sh
jobrake indeed attributes -c usa "data scientist" \
  | jq -r '.[] | select(.name | test("python"; "i")) | [.id, .name] | @tsv'
# X62BT	Python
```

Each run samples the postings afresh, so a code can be missing from one lookup and present in the next.
Try the lookup again, or a related query, when a code you expect does not appear.
Labels can differ by country edition. A label can also belong to several codes, and the lookup keeps each code separately.
jobrake reads the codes live from Indeed. Library callers use `jobrake.sites.indeed.attributes(fetcher, query, country=...)`.

Once you find the codes you want, then use those codes to filter jobs:

```sh
jobrake indeed search -q "data scientist" -c usa --attributes X62BT
jobrake indeed search -q economist -c usa --attributes CF3CP 6QC5F
```

`X62BT` selects Python. The second search requires both Full-time (`CF3CP`) and Doctoral degree (`6QC5F`),
because codes intersect: every returned posting carries every code you list. To match any of several codes,
run separate searches and combine the results. A posting can hold codes that look mutually exclusive,
so a Full-time match may carry Part-time as well when the employer offers either arrangement.
The filter has no way to exclude a code.

For a library search, pass the codes as a list of strings, such as `attributes=["CF3CP", "6QC5F"]`.

### Remote jobs

Pass `--remote` to search postings that Indeed tags Remote:

```sh
jobrake indeed search -q "econometrics" -c usa --remote
```

`--remote` is shorthand for `--attributes DSQF7`, so a posting must carry the Remote tag and every other code you pass.
The tag reflects Indeed's classification. Check the posting for residency and workplace requirements.
An Indeed record's `workplace_type` is `remote` for a posting tagged Remote and `hybrid` for one tagged Hybrid work, whose code is `PAXZC`. Indeed tags some postings both, and such a posting has no `workplace_type`.

### Easy Apply and early applicants

Use `--easy-apply` to find jobs with LinkedIn's Easy Apply form. `--early-applicant` requests LinkedIn's "under 10 applicants" filter.

```sh
jobrake linkedin search -q "data scientist" -l Netherlands --easy-apply --early-applicant
```

With both set, a job must match both. Neither needs `--details`.

LinkedIn's posting pages show a broader count than the filter's threshold. "Be among the first 25 applicants" becomes `applicants=25` in jobrake, so an early-applicant result can carry that value.

### Unsupported LinkedIn filters

The guest endpoint ignores filters for workplace type (remote, hybrid, and on-site), employment type, experience level, verified postings, and salary, so jobrake offers none of them.
Employment type is still available as a posting detail with `--details`.

## Fetch posting details

Indeed returns the details it has with the search itself, so an Indeed search needs nothing further.
LinkedIn's guest search returns summary cards only. Add `--details | -d` (`details=True`) to fetch each posting page and fill in the rest.
That costs one paced request per uncached posting, and sometimes a second.
Workday and SmartRecruiters searches also return cards without descriptions, and `--details` fetches each posting with one more request, as [Workday fields](#workday-fields) and [SmartRecruiters fields](#smartrecruiters-fields) describe.
See [request limits](#request-limits-and-partial-results) for pacing and retries, and [cache settings](#cache-location-and-lifetimes) for reuse.

### Fetch known postings

Fetch postings you already know on LinkedIn, Workday, or SmartRecruiters without repeating a search:

```sh
jobrake linkedin postings 4449382178
jobrake linkedin postings https://nl.linkedin.com/jobs/view/data-scientist-at-acme-4449382178
jobrake workday postings https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/US-CA-Santa-Clara/Networking-Architect_JR1996377
jobrake smartrecruiters postings https://jobs.smartrecruiters.com/BoschGroup/744000158197889
```

Sites take postings down over time, so the examples above may be gone. Use references from a recent search.
Name as many postings as you like. Results follow the order given and have the fields of a search with `--details`, except a field only the search result carries, such as SmartRecruiters' `department`. Several references to one posting return one job.
The command accepts the same `--output | -o` and `--format | -f` options as a search.
A posting that is gone or unreachable is reported on stderr and left out. When one was unreachable, the command writes the others and exits nonzero.
A LinkedIn reference is a numeric ID or a posting URL. A Workday or SmartRecruiters reference is a search result's `url`, and SmartRecruiters also takes the posting's address with its title slug. Any other reference is an error, and nothing is fetched.

LinkedIn serves a posting's dates, coordinates, and requirements only at its canonical URL: the title slug on the host of the posting's country.
That host is `www.linkedin.com` for the United States and a country subdomain, such as `nl.linkedin.com`, elsewhere.
A posting placed in a whole country, such as "United States" or "Netherlands", comes without those fields at any address.

jobrake fetches a country-subdomain URL with a slug as given. Any other reference costs one lookup first to find the canonical URL.
A cached posting holds its URL, so it costs no request.

Library callers use the `postings` function of `jobrake.sites.linkedin`, `jobrake.sites.workday`, or `jobrake.sites.smartrecruiters`.

### Fetch selected results

For a large search, omit `-d` and fetch only the postings you want:

```python
import asyncio

from jobrake import HttpxFetcher, scrape
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
        return await linkedin.postings(fetcher, urls)


postings = asyncio.run(main())
```

`postings()` maps each ID or URL to its whole job, or to `None` when LinkedIn reports the posting gone.
A reference whose request failed is absent from the result, and calling the function again retries it.

## Employer boards

Many employers publish their openings on a board that their applicant tracking system (ATS) hosts.
jobrake reads Ashby, Greenhouse, Lever, SmartRecruiters, Workable, and Workday boards. A search names one employer's board with `--board | -b`.
An Ashby, Greenhouse, Lever, or Workable search returns every posting on the board:

```sh
jobrake greenhouse search -b airbnb
jobrake greenhouse search -b gitlab -o gitlab.jsonl
jobrake ashby search -b ramp -o ramp.csv
jobrake lever search -b palantir
jobrake workable search -b huggingface
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("greenhouse", board="airbnb"))
```

These searches take no query, result limit, or filters. Ashby, Greenhouse, and Workable apply none.
Lever filters only on the employer's own labels for location, team, department, and commitment, which must match exactly, so jobrake offers none of them.
To narrow the postings, [pipe the results](#pipe-results) through `jq` or load them into another tool.
SmartRecruiters and Workday search on the server, as [Search a board](#search-a-board) describes.

### Find a board

The board token is the last part of the board's address:

- Greenhouse: `airbnb` in `boards.greenhouse.io/airbnb`, or `gitlab` in `job-boards.greenhouse.io/gitlab`.
- Ashby: `ramp` in `jobs.ashbyhq.com/ramp`.
- Lever: `palantir` in `jobs.lever.co/palantir`. A board on Lever's EU host, `jobs.eu.lever.co/<token>`, works the same way.
- Workable: `huggingface` in `apply.workable.com/huggingface`.
- SmartRecruiters: `BoschGroup` in `jobs.smartrecruiters.com/BoschGroup`. In our tests, capitals did not matter.

A token the site does not know stops the search with an error that says so, except on SmartRecruiters.
SmartRecruiters answers a token it does not know as it answers a board with no postings, so jobrake cannot tell the two apart.
Either way the search returns no postings and logs that the token may be misspelled. Check the token against the board's address before you conclude that the employer has no openings.

Workday has no board token. Pass the address of the employer's job search page instead, copied from the browser, such as `https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite`.
The address has the form `https://<tenant>.wd<n>.myworkdayjobs.com/<site>`, with or without a language part such as `en-US` before the site name. A posting's address on the same site works too.
Addresses on `myworkdaysite.com` are not supported. An address jobrake cannot read stops before any request with an error that shows the expected form, and a site name Workday does not know stops the search with an error that says so.

### Search a board

A SmartRecruiters search applies a query and filters on the server:

```sh
jobrake smartrecruiters search -b BoschGroup -q engineer
jobrake smartrecruiters search -b BoschGroup --remote --max-age-hours 72 -n 500 -o bosch.csv
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("smartrecruiters", board="BoschGroup", query="engineer"))
```

`--query | -q` searches posting titles and locations. `--max-age-hours | -a` keeps postings released within that many hours, and `--remote` keeps postings the employer marks remote.
`--results | -n` defaults to 100 here, not 10, because an employer board is usually read whole. Raise it to read a large board: Bosch Group's board held more than 5,000 postings in our tests.

A Workday search applies a query on the server:

```sh
jobrake workday search -b https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite -q architect
jobrake workday search -b https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite -n 100 -d -o nvidia.jsonl
```

```python
import asyncio

from jobrake import scrape

board = "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"
jobs = asyncio.run(scrape("workday", board=board, query="architect", details=True))
```

`--query | -q` is Workday's keyword search, and `--results | -n` caps the postings returned, 20 by default.
Each employer defines its own Workday filters, such as job category or country, so jobrake offers no location, remote, or age filter for Workday.
Workday publishes no documentation for this API. The behavior described here was measured on NVIDIA's career site in October 2026, and another employer's site may differ.

### Greenhouse fields

A Greenhouse record carries `title`, `locations`, and `description`.
It also carries `company`, `date`, and the details `posted_at`, `language`, `department`, and `expires_at` when Greenhouse supplies them, which its documented list response does not promise.
`posted_at` is the time the posting was first published, and `date` is its calendar date. `expires_at` is the application deadline.
`department` is the job's department when Greenhouse lists exactly one, as it did for all 195 postings on Airbnb's board on 2026-10-28.
`locations` holds one place, named with the text the employer entered, such as `Remote, Canada; Remote, United States`.
`url` is the posting on the employer's own careers site when the board lives there, as Airbnb's does, and on `job-boards.greenhouse.io` otherwise.
In our tests on two boards, every posting carried a company, a location, a first-published time, and a language, and one posting in 430 had a deadline.
Employers can add facts such as a workplace type as custom fields, which differ from board to board. jobrake leaves those out, so a Greenhouse record has no salary, employment type, or workplace type.

### Ashby fields

An Ashby record carries `title`, `locations`, `date`, and `description`, and the details `posted_at`, `employment_type`, `department`, `team`, `apply_url`, `workplace_type`, and, when present, `salary_min`, `salary_max`, `salary_currency`, and `salary_period`.
`company` is always `None`, because Ashby's response never names the employer. The board token tells you whose board it is.
`posted_at` is the time the posting was published, and `date` is its calendar date.
`locations` holds the posting's primary location first and then its other places, named as the employer entered them, such as `Remote (US)` and `Remote (Canada)`. Each place carries the `city` and `region` of its address as Ashby spells them, and `region` can be a code or a name, such as `NY` or `Ontario`.
Ashby gives the country as a name, such as `USA` or `United Kingdom`, so an Ashby place has no `country_code`.
`workplace_type` is `remote`, `hybrid`, or `on_site`, as the employer set it.
The salary fields come from the posting's first salary range.
`team` is the posting's team, such as `Solutions Consulting`. `site_data` holds its `summaryComponents` as Ashby sends them, so equity, commission, and bonus appear there beside the salary range. In our test on one board, 124 of 172 postings listed an equity value and 40 a commission.
`url` and `apply_url` point to the posting on `jobs.ashbyhq.com`.
A search also returns postings the employer marked unlisted, which Ashby intends for direct links only.
In our test on one board of 172 postings, every posting carried a location, a publish time, and an employment type, 165 carried a salary range, 162 a city, and 16 were remote.

### Lever fields

A Lever record carries `title`, `locations`, `date`, and `description`, and the details `posted_at`, `employment_type`, `workplace_type`, `apply_url`, `team`, and, when present, `department`.
`company` is always `None`, because Lever's response never names the employer.
`posted_at` is the time the posting was created, and `date` is its calendar date.
`description` joins the posting's description, its lists such as requirements and benefits, each under its own heading, and its closing text.
`locations` holds the posting's primary location first and then its other places, named as the employer entered them, such as `London, United Kingdom`. The primary place carries the posting's `country_code`.
`employment_type` is the employer's commitment label as a slug, such as `full_time` for `Full-time`.
`workplace_type` is `remote`, `hybrid`, or `on_site`, as the employer set it, and is absent for a posting the employer left unspecified.
`url` is the posting on `jobs.lever.co` or `jobs.eu.lever.co`, and `apply_url` is its application form.
Lever can send a salary range, but its documentation does not list the pay intervals it uses, so jobrake leaves salary out. Salary text in the description stays in `description`.
`team` is the posting's team, such as `Administrative`.
In our tests on one board, every one of five postings carried a location, a country, a commitment, and a workplace type, and none had a salary range.

### Workable fields

A Workable record carries `title`, `company`, `locations`, `date`, and `description`, and the details `posted_at`, `employment_type`, `department`, `apply_url`, and, when present, `workplace_type` and `education`.
`posted_at` is the date the posting was published, with no time of day, so it equals `date`.
Each place carries the `city`, `region`, and `country_code` the employer entered and is named with the city, region, and country name, such as `Paris, Île-de-France, France`.
Workable lists a posting open in several places once per place. jobrake returns it once, with each of its places.
A posting's top-level city, state, and country add a place of their own when no listed place has all three, such as `Paris, Île-de-France, France`. On the board we measured, they repeated the first place.
`workplace_type` is `remote` when the employer marked the posting as remote. The board flags remote alone, so another posting has no `workplace_type`. `employment_type` is a slug such as `full_time`.
`education` is the degree the employer chose, such as `Master's Degree`, and is absent when the employer chose none.
`url` is the posting on `apply.workable.com`, and `apply_url` is its application form.
In our test on one board of six postings, every posting carried a country and an employment type, and three named no city.
A Workable record has no salary or language, because the board does not publish them.

### SmartRecruiters fields

A SmartRecruiters record carries `title`, `company`, `locations`, and `date`, and the details `posted_at`, `employment_type`, `language`, and, when present, `department` and `workplace_type`.
`locations` holds one place, named as SmartRecruiters writes it, such as `Wuxi, Jiangsu, China`, with its `city`, `country_code`, and, when present, `region`, `latitude`, and `longitude`.
`posted_at` is the time the posting was released, and `date` is its calendar date. `language` is a code such as `en` or `zh-CN`.
`url` opens the posting on `jobs.smartrecruiters.com`.
`workplace_type` is `remote` or `hybrid` for a posting the employer marks so, and absent otherwise, because SmartRecruiters does not mark on-site. `--remote` keeps the postings SmartRecruiters files as remote, which can include ones whose `workplace_type` is `hybrid`.
A search result has no description, which SmartRecruiters serves only one posting at a time. `--details | -d` fetches each posting and adds `description`, every section of the ad under its title, in SmartRecruiters' order: the company description, the job description, the qualifications, and additional information.
[`jobrake smartrecruiters postings`](#fetch-known-postings) builds the same record from a search result's `url` in a later run, without the `department`, which only the search result carries.
A record has no apply link, and no salary, which SmartRecruiters does not publish.

### Workday fields

A Workday search result carries `title`, `locations`, and `date`, but no description.
`--details | -d` fetches each posting and adds `description`, `posted_at`, and `employment_type`, and gives the primary place its `country_code`.
[`jobrake workday postings`](#fetch-known-postings) builds the same record from a search result's `url` in a later run.

- `company` is always `None`. Workday names only the employer's legal entity, such as `2100 NVIDIA USA`.
- `locations` is empty for a posting with several locations, because a search result shows only their count, such as `2 Locations`. With `--details`, it holds the primary location and then the others, by name.
- Without `--details`, `date` comes from Workday's label: "Posted Today", "Posted Yesterday", or "Posted 3 Days Ago", counted back from today in UTC. Workday counts from its own day, so this `date` can be a day late. On one posting we fetched at 02:22 UTC, Workday said "Posted Today" and the posting's start date was the previous day. Workday stops counting at "Posted 30+ Days Ago", so an older posting has no `date`.
- `posted_at` is a calendar date, Workday's start date for the posting. With `--details`, `date` is `posted_at`.
- `id` joins the employer's Workday name and the requisition ID, as in `nvidia:JR1996377`.

A Workday record has no salary, workplace type, or application link.

## EconJobMarket

[EconJobMarket](https://econjobmarket.org) (EJM) is the job market site for economists: academic positions, postdocs, pre-docs, and research jobs at central banks and consultancies.
jobrake reads EJM's public ad feed. A search returns every open ad:

```sh
jobrake econjobmarket search
jobrake econjobmarket search -o ejm.jsonl
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("econjobmarket"))
```

A search takes no query, result limit, or filters, because EJM applies none.
To narrow the ads, [pipe the results](#pipe-results) through `jq` or load them into another tool:

```sh
jobrake econjobmarket search \
  | jq -r '.[] | select(any(.locations[]; .country_code == "DE")) | [.expires_at, .company, .title] | @tsv'
```

### EconJobMarket terms

EJM offers the feed "for personal use and for academic research projects".
To redisplay EJM ads on your own website, you must notify EJM and get EJM's approval first.
Any use of the feed must follow EJM's Terms of Use, Privacy Policy, and Research Data Usage Policy.
See [Accessing the EJM Ad Feed](https://backend.econjobmarket.org/docs/ad-redisplay/Ad-Redisplay.0.md).

### EconJobMarket fields

An EconJobMarket record carries `title`, `company`, `locations`, `date`, and `description`, and the details `posted_at`, `expires_at`, `company_logo`, and, when present, `department`.
`company` is the hiring institution, such as `University of Zurich`. `company_logo` links to its logo on EJM.
`posted_at` is the ad's start date on EJM, and `date` is the same day. Both are calendar dates without a time.
`expires_at` is the application deadline. In our read of the feed, 7 ads in 319 were still open after their deadline.
`locations` holds each location the ad lists, with its `city`, `region`, `country_code`, and coordinates when present, named from them, such as `Boston, Massachusetts, US`.
Two ads in 319 listed no location, and their `locations` is empty.
`url` is the ad on `econjobmarket.org`, and candidates apply there, so a record has no separate `apply_url`.
`department` is the hiring unit, such as `Department of Economics`. An ad that says `All departments`, as 61 of 319 did, has no `department`.
`site_data` holds the ad's `position_types`, ranks such as `Assistant Professor`, and its `categories`, fields of economics such as `Econometrics`, each as a list of names. Every one of the 319 ads listed both.
The feed carries no salary, employment type, or workplace type.

## Read and save results

### Returned fields

Every job is a dictionary, with three groups of keys.

- **Identity keys:** `site`, `id`, and `url`.
- **Summary keys:** `title`, `company`, `locations`, and `date`.
- **Detail keys:** included when a value is available.

Identity and summary keys are always present, with `None` for an unavailable summary value and `[]` when jobrake found no place.
An empty `locations` says only that jobrake extracted no place. It does not say the posting has no place, nor that it is remote.

`locations` lists the posting's places in the site's order. Each place has a `name`, the site's label for it or its parts joined when the site gives no label, and carries `city`, `region`, `country_code`, `latitude`, and `longitude` only when the site gives them for that place.
`country_code` has the form of an ISO 3166-1 alpha-2 code, such as `US`, and jobrake checks the form only. jobrake parses nothing out of a place's name, so a place named `Seattle, WA` carries no `city` unless the site sent one.
A place the site lists twice with the same parts appears once. Places that share a name but differ in any part, such as `Remote` in two countries, each appear.

`workplace_type` is `remote`, `hybrid`, or `on_site`, and appears only when the site states it. An absent `workplace_type` leaves the workplace unknown and does not mean on-site.
`department` is the hiring unit within the employer, as the site names it, such as `Engineering`, and `team` the posting's team within it, on Ashby and Lever.

`site_data` holds fields that only one site carries, under that site's own names, such as EconJobMarket's `position_types`. Its keys depend on `site`, and each site's fields section lists them. A key that a second site comes to share with the same meaning moves into the record.
A detail key is absent when the site omits or does not publish the value, or when jobrake did not fetch the posting page.

The sites use the same names for the details they share. A fields subsection under [Employer boards](#employer-boards) or [EconJobMarket](#econjobmarket) lists the details its site carries.
`apply_type`, `applicants`, and `experience_months` come from LinkedIn only, and LinkedIn carries no `workplace_type`, `apply_url`, or `language`.

A posting can carry two dates. `date` holds the calendar date, such as `2026-09-19`, and `posted_at` holds the full timestamp when the site gives one, such as `2026-09-19T05:00:00+00:00`, and the calendar date otherwise.
jobrake prefers the date a search result states and falls back to the calendar portion of `posted_at`. Compare on `date`, and read `posted_at` for a time of day.

### Output formats

The CLI writes compact JSON to stdout. `--output | -o` writes a new file instead and refuses to overwrite an existing one.
`--format | -f` chooses `json`, `jsonl`, or `csv`, and defaults to the extension of `--output`.
A search that returns no jobs writes no file, and the output directory must already exist.

```sh
jobrake ... -o jobs.csv
jobrake ... -o jobs.txt -f jsonl
```

The formats represent unavailable fields differently.

- JSON writes one array, using `null` for unavailable summary values.
- JSONL writes one job per line with the same keys as JSON.
- CSV writes every field as a column and leaves unavailable cells empty. Its `locations` column holds the place names, separated by `; `, without their parts, and its `site_data` column holds the site's fields as JSON. A place name can itself contain `; `, such as Greenhouse's `Remote, Canada; Remote, United States`, so read JSON or JSONL to count places.

> [!TIP]
> JSONL suits a run you repeat, a daily one for instance. Combine the files with `cat`, or read the whole directory into DuckDB.
>
> ```sh
> jobrake ... -o runs/2026-08-10.jsonl
> jobrake ... -o runs/2026-08-11.jsonl
> cat runs/*.jsonl > jobs.jsonl
>
> duckdb -c "select * from read_json('runs/*.jsonl', union_by_name=true)"
> ```

### Pipe results

Pipe stdout into another program to reshape the jobs. [`jq`](https://github.com/jqlang/jq) picks out fields:

```sh
jobrake indeed search -q "data scientist" -c usa -n 2 \
  | jq -r '.[] | [.date, .title, .company, .url] | @tsv'
```

## Use the Python API

`scrape()` creates and closes an HTTP client when `fetcher` is omitted.
Library calls log under the `jobrake` logger, and your application sets its level and handlers.

```python
import asyncio

from jobrake import scrape


async def main():
    jobs = await scrape(
        "indeed",
        query="economist",
        country="United States",
        results=2,
    )
    for job in jobs:
        print(job["title"], job["url"])


asyncio.run(main())
```

A fetcher you supply is yours to close.
Use its context manager when several searches should share one connection pool:

```python
import asyncio

from jobrake import HttpxFetcher, scrape


async def main():
    query = "economist"
    site = "indeed"
    async with HttpxFetcher(timeout=30) as fetcher:
        nl = await scrape(
            site,
            query=query,
            location="Amsterdam",
            country="Netherlands",
            fetcher=fetcher,
        )
        us = await scrape(
            site,
            query=query,
            location="New York",
            country="USA",
            fetcher=fetcher,
        )
    return nl, us


nl, us = asyncio.run(main())
```

To use another HTTP client or a browser, implement the `Fetcher` protocol from `jobrake.fetchkit`: an async `fetch(url, *, headers=None, json=None)` that sends a POST when `json` is given, and an async `close()`.
`fetch` returns a `FetchResult` and reports a failed request in its `error`. A status of 400 or more sets `error` on its own.
An exception your own `Fetcher` raises propagates out of `scrape()`.

## Request limits and partial results

A failed request ends a search with `Stopped`, and so does a page that ends it short of the total the site reported. Its `partial` holds the jobs collected before the search stopped:

```python
from jobrake import Stopped, scrape


async def main():
    try:
        return await scrape("indeed", query="economist", country="usa", results=500)
    except Stopped as stop:
        print(stop)  # what failed
        return stop.partial  # the jobs collected before it
```

The CLI writes those jobs and exits 1. Reaching a site's own result cap is not a failure. jobrake warns on stderr and returns what the site served.

### Ashby requests

A board search is one request, which returns the whole board, descriptions and salaries included. It gets a single attempt and no pacing.
A failed request raises `Stopped` with an empty `partial`, and the CLI exits 1.
jobrake skips a posting it cannot read and leaves out a field it cannot read.

### EconJobMarket requests

A search is one request, which returns every open ad. It gets a single attempt and no pacing.
A failed request raises `Stopped` with an empty `partial`, and the CLI exits 1.
jobrake skips an ad it cannot read and leaves out a field it cannot read.

### Greenhouse requests

A board search is one request, which returns the whole board. It gets a single attempt and no pacing.
A failed request raises `Stopped` with an empty `partial`, and the CLI exits 1.
jobrake skips a posting it cannot read and leaves out a field it cannot read.

### Indeed requests

One search reaches at most 1,000 results, and jobrake warns when that cap cuts a search short.

Indeed returns jobs newest first by the date the posting reached Indeed, the same date `--max-age-hours` filters on.
A reposted job counts as new, so a 24-hour window can include postings published weeks earlier.
Repeating a search returns the same jobs in the same order.

Pages follow one another without delay, and each request gets a single attempt.
jobrake skips a posting it cannot read and leaves out a field it cannot read.

### Lever requests

A board search is one request, which returns the whole board, or two when the board lives on Lever's EU host. Each gets a single attempt and no pacing.
A failed request raises `Stopped` with an empty `partial`, and the CLI exits 1. A failure on the global host other than "not found" stops the search without asking the EU host.
jobrake skips a posting it cannot read and leaves out a field it cannot read.

### LinkedIn requests

The guest search returns about 10 cards per page and stops at offset 1,000, so one search returns roughly 1,000 postings at most.
jobrake warns when that limit cuts a search short.

jobrake asks LinkedIn for the newest postings first, but the guest endpoint ignores the request and ranks by relevance.
The order can also change between two runs of the same search.
To collect only new postings, repeat the search with `--max-age-hours` covering the time since the last run.

LinkedIn limits guest traffic per IP and per data center, and pins a client to one data center with a cookie.
jobrake spreads its requests over the three data centers that answered in our tests and sends about one request per second.
If LinkedIn stops routing requests to a data center that jobrake names, jobrake looks for another with requests 2.5 seconds apart.
Within one process, jobrake keeps each data center under the limit we measured, unless LinkedIn moves a request to another data center, which can cost one retry.
Each process paces only its own requests, so concurrent runs on the same IP can reach the limit sooner.
LinkedIn requests carry only the data-center cookie, so a custom fetcher's own cookies reach LinkedIn only when it redirects a request.

LinkedIn refuses some requests whatever the pace, up to a quarter of them in our tests.
jobrake retries a 429 up to three times, first on the other data centers and then after a 12-second wait.
If the 429 remains, the search raises `Stopped` with what it has collected so far.
A `--details` search that could not fetch every posting's details raises `Stopped` too, holding every posting it found.

On a data center IP, such as a VPS, LinkedIn refuses posting pages with [HTTP 999](https://http.dev/999). Searches and lookups keep working, but every detail fetch fails.

### SmartRecruiters requests

A search reads the board in pages of up to 100 postings, which follow one another without pacing, and each request gets a single attempt.
It stops at `--results`, at the board's last matching posting, or at an empty page.
A failed request raises `Stopped` with the postings of the pages before it, and the CLI exits 1. So does an empty page that comes before the number of matches SmartRecruiters reported, because postings may have closed during the search and a rerun may find more.
`--details` and `postings` add one request per posting, one after another, and treat a failed one as Workday's do.
A posting SmartRecruiters marks inactive, or an ID the board does not hold, counts as gone.
jobrake skips a posting it cannot read and leaves out a field it cannot read.

### Workable requests

A board search is one request, which returns the whole board. It gets a single attempt and no pacing.
A failed request raises `Stopped` with an empty `partial`, and the CLI exits 1.
jobrake skips a posting it cannot read and leaves out a field it cannot read.

### Workday requests

A search pages through the results one request after another, without pacing, and each request gets a single attempt.
Workday reports at most 2,000 postings per search, and jobrake warns when that cap cuts a search short. Narrow the search with `--query` to reach the rest.
A failed request raises `Stopped` with the postings collected before it, and the CLI exits 1. So does an empty page that comes before the number of postings Workday reported, because postings may have closed during the search and a rerun may find more.
`--details` adds one request per posting, also one after another. A posting removed since the search keeps its search result.
A posting whose details cannot be fetched also keeps its search result, and once the rest are fetched the search raises `Stopped` with every posting in `partial`. A rerun retries them.
`postings` sends the same one request per posting and never raises `Stopped`. It leaves out a posting whose request failed or whose response it cannot read.
jobrake skips a posting it cannot read and leaves out a field it cannot read.

## Cache location and lifetimes

jobrake keeps the LinkedIn postings it fetched in one SQLite file under your user cache directory: `~/Library/Caches/jobrake/` on macOS, `$XDG_CACHE_HOME/jobrake/` on Linux, `%LOCALAPPDATA%\jobrake\` on Windows.
No other site is cached.

A cached posting stays fresh for seven days and is fetched again after that. A posting that LinkedIn reports gone is not cached.
An upgrade keeps the cache, and a posting whose cached copy no longer fits the job fields is fetched again.
A release that reads posting pages better reaches a cached posting when it expires.

To refetch every posting at once, move `jobrake.sqlite3` out of the cache directory, or delete it.
To bypass the cache for one run, point `JOBRAKE_CACHE_PATH` at a new file:

```sh
JOBRAKE_CACHE_PATH="$(mktemp -d)/jobrake.sqlite3" jobrake linkedin postings 4449382178
```

Two environment variables configure the cache:

| Variable             | Default             | Effect                                                 |
| -------------------- | ------------------- | ------------------------------------------------------ |
| `JOBRAKE_CACHE_PATH` | platform user cache | Path to the SQLite file, with home-directory expansion |
| `JOBRAKE_CACHE_TTL`  | 604800              | Seconds a cached posting is served before a refetch    |

The lifetime must be a positive number of seconds. An invalid value draws a warning and falls back to the default.

A storage failure disables the cache with a warning, and scraping carries on without it.

## Other job boards

Glassdoor is not planned because it is now [part of Indeed](https://web.archive.org/web/20260704043638/https://www.glassdoor.com/about/).
AEA JOE is not planned because its [listings](https://www.aeaweb.org/joe/listings) forbid scraping or collecting them without the American Economic Association's written permission. Its listings page offers its own XML and Excel downloads.
Wellfound is not planned because it has no public API, and its job data sits behind a Cloudflare challenge that only a browser passes.
