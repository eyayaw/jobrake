# jobrake reference

This page describes a jobrake record, the fields each site fills, and how each site's requests behave.
The [guide](guide.md) shows how to search, narrow, and save.

- [Returned fields](#returned-fields)
- [Fields by site](#fields-by-site)
- [Requests by site](#requests-by-site)

## Returned fields

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

The sites use the same names for the details they share. Each site's section under [Fields by site](#fields-by-site) lists the details it carries.
`apply_type`, `applicants`, and `experience_months` come from LinkedIn only, and LinkedIn carries no `workplace_type`, `apply_url`, or `language`.

A posting can carry two dates. `date` holds the calendar date, such as `2026-09-19`, and `posted_at` holds the full timestamp when the site gives one, such as `2026-09-19T05:00:00+00:00`, and the calendar date otherwise.
jobrake prefers the date a search result states and falls back to the calendar portion of `posted_at`. Compare on `date`, and read `posted_at` for a time of day.

## Fields by site

### LinkedIn fields

A LinkedIn search result carries `title`, `company`, `locations`, and `date`, and no details.
`--details | -d` fetches each posting page and adds `description` and, when the page has them, `posted_at`, `expires_at`, `employment_type`, `education`, `experience_months`, `apply_type`, `applicants`, `company_url`, `company_logo`, `salary_min`, `salary_max`, `salary_currency`, and `salary_period`.
[`jobrake linkedin postings`](guide.md#fetch-known-postings) builds the same record from an ID or a URL in a later run.

- `id` is LinkedIn's numeric posting ID, and `url` is the posting page the search result links to, without its query string.
- `locations` holds one place, named as the search result shows it. With `--details`, a place carries the `city`, `region`, `country_code`, `latitude`, and `longitude` the page gives, and a posting the page places in several locations lists each.
- `apply_type` is `onsite` for LinkedIn's own application form and `offsite` for the employer's.
- `applicants` is the count the page shows. LinkedIn shows a count above 200 as "Over 200", so `applicants` stops at 200.
- `experience_months` and `education` are the experience, in whole months, and the credential the posting asks for.
- The salary fields hold the posting's salary range when the page gives one.
- A posting placed in a whole country comes with fewer details, as [Fetch posting details](guide.md#fetch-posting-details) says.

### Indeed fields

An Indeed record carries `title`, `company`, `locations`, `date`, and `description`, and, when Indeed supplies them, the details `posted_at`, `expires_at`, `language`, `employment_type`, `workplace_type`, `apply_url`, `company_url`, `company_logo`, `salary_min`, `salary_max`, `salary_currency`, and `salary_period`.
A search returns them all, so Indeed takes no `--details`.

- `id` is Indeed's job key, and `url` opens the posting on the country edition searched.
- `locations` holds one place with the `city`, `region`, `country_code`, `latitude`, and `longitude` Indeed gives, named from those parts.
- `posted_at` is the time the posting was published, and `date` is its calendar date. `--max-age-hours` filters on another date, as the note under [Search for jobs](guide.md#search-for-jobs) says.
- `employment_type` comes from the posting's attribute labels, as a slug such as `full_time`.
- `workplace_type` follows Indeed's Remote and Hybrid work tags, as [Remote jobs](guide.md#remote-jobs) describes.
- The salary fields hold the range Indeed gives with its currency and period. A posting with one figure carries it as both bounds.
- `apply_url` is the application link Indeed gives, and `company_url` is the employer's page on Indeed.

### Greenhouse fields

A Greenhouse record carries `title`, `locations`, and `description`.
It also carries `company`, `date`, and the details `posted_at`, `language`, `department`, and `expires_at` when Greenhouse supplies them, which its documented list response does not promise.

- `posted_at` is the time the posting was first published, and `date` is its calendar date. `expires_at` is the application deadline.
- `department` is the job's department when Greenhouse lists exactly one, as it did for all 195 postings on Airbnb's board on 2026-10-28.
- `locations` holds one place, named with the text the employer entered, such as `Remote, Canada; Remote, United States`.
- `url` is the posting on the employer's own careers site when the board lives there, as Airbnb's does, and on `job-boards.greenhouse.io` otherwise.
- In our tests on two boards, every posting carried a company, a location, a first-published time, and a language, and one posting in 430 had a deadline.
- Employers can add facts such as a workplace type as custom fields, which differ from board to board. jobrake leaves those out, so a Greenhouse record has no salary, employment type, or workplace type.

### Ashby fields

An Ashby record carries `title`, `locations`, `date`, and `description`, and the details `posted_at`, `employment_type`, `department`, `team`, `apply_url`, `workplace_type`, and, when present, `salary_min`, `salary_max`, `salary_currency`, and `salary_period`.

- `company` is always `None`, because Ashby's response never names the employer. The board token tells you whose board it is.
- `posted_at` is the time the posting was published, and `date` is its calendar date.
- `locations` holds the posting's primary location first and then its other places, named as the employer entered them, such as `Remote (US)` and `Remote (Canada)`. Each place carries the `city` and `region` of its address as Ashby spells them, and `region` can be a code or a name, such as `NY` or `Ontario`.
- Ashby gives the country as a name, such as `USA` or `United Kingdom`, so an Ashby place has no `country_code`.
- `workplace_type` is `remote`, `hybrid`, or `on_site`, as the employer set it.
- The salary fields come from the posting's first salary range.
- `team` is the posting's team, such as `Solutions Consulting`. `site_data` holds its `summaryComponents` as Ashby sends them, so equity, commission, and bonus appear there beside the salary range. In our test on one board, 124 of 172 postings listed an equity value and 40 a commission.
- `url` and `apply_url` point to the posting on `jobs.ashbyhq.com`.
- A search also returns postings the employer marked unlisted, which Ashby intends for direct links only.
- In our test on one board of 172 postings, every posting carried a location, a publish time, and an employment type, 165 carried a salary range, 162 a city, and 16 were remote.

### Lever fields

A Lever record carries `title`, `locations`, `date`, and `description`, and the details `posted_at`, `employment_type`, `workplace_type`, `apply_url`, `team`, and, when present, `department`.

- `company` is always `None`, because Lever's response never names the employer.
- `posted_at` is the time the posting was created, and `date` is its calendar date.
- `description` joins the posting's description, its lists such as requirements and benefits, each under its own heading, and its closing text.
- `locations` holds the posting's primary location first and then its other places, named as the employer entered them, such as `London, United Kingdom`. The primary place carries the posting's `country_code`.
- `employment_type` is the employer's commitment label as a slug, such as `full_time` for `Full-time`.
- `workplace_type` is `remote`, `hybrid`, or `on_site`, as the employer set it, and is absent for a posting the employer left unspecified.
- `url` is the posting on `jobs.lever.co` or `jobs.eu.lever.co`, and `apply_url` is its application form.
- Lever can send a salary range, but its documentation does not list the pay intervals it uses, so jobrake leaves salary out. Salary text in the description stays in `description`.
- `team` is the posting's team, such as `Administrative`.
- In our tests on one board, every one of five postings carried a location, a country, a commitment, and a workplace type, and none had a salary range.

### Workable fields

A Workable record carries `title`, `company`, `locations`, `date`, and `description`, and the details `posted_at`, `employment_type`, `department`, `apply_url`, and, when present, `workplace_type` and `education`.

- `posted_at` is the date the posting was published, with no time of day, so it equals `date`.
- Each place carries the `city`, `region`, and `country_code` the employer entered and is named with the city, region, and country name, such as `Paris, Île-de-France, France`.
- Workable lists a posting open in several places once per place. jobrake returns it once, with each of its places.
- A posting's top-level city, state, and country add a place of their own when no listed place has all three, such as `Paris, Île-de-France, France`. On the board we measured, they repeated the first place.
- `workplace_type` is `remote` when the employer marked the posting as remote. The board flags remote alone, so another posting has no `workplace_type`. `employment_type` is a slug such as `full_time`.
- `education` is the degree the employer chose, such as `Master's Degree`, and is absent when the employer chose none.
- `url` is the posting on `apply.workable.com`, and `apply_url` is its application form.
- In our test on one board of six postings, every posting carried a country and an employment type, and three named no city.
- A Workable record has no salary or language, because the board does not publish them.

### SmartRecruiters fields

A SmartRecruiters record carries `title`, `company`, `locations`, and `date`, and the details `posted_at`, `employment_type`, `language`, and, when present, `department` and `workplace_type`.

- `locations` holds one place, named as SmartRecruiters writes it, such as `Wuxi, Jiangsu, China`, with its `city`, `country_code`, and, when present, `region`, `latitude`, and `longitude`.
- `posted_at` is the time the posting was released, and `date` is its calendar date. `language` is a code such as `en` or `zh-CN`.
- `url` opens the posting on `jobs.smartrecruiters.com`.
- `workplace_type` is `remote` or `hybrid` for a posting the employer marks so, and absent otherwise, because SmartRecruiters does not mark on-site. `--remote` keeps the postings SmartRecruiters files as remote, which can include ones whose `workplace_type` is `hybrid`.
- SmartRecruiters serves a description only with each posting, so a search result has none. `--details | -d` fetches each posting and adds `description`. It holds every section of the ad under its title, in SmartRecruiters' order: the company description, the job description, the qualifications, and additional information.
- [`jobrake smartrecruiters postings`](guide.md#fetch-known-postings) builds the same record from a search result's `url` in a later run, without the `department`, which only the search result carries.
- A record has no apply link. It has no salary either, because SmartRecruiters does not publish one.

### Workday fields

A Workday search result carries `title`, `locations`, and `date`, but no description.
`--details | -d` fetches each posting and adds `description`, `posted_at`, and `employment_type`, and gives the primary place its `country_code`.
[`jobrake workday postings`](guide.md#fetch-known-postings) builds the same record from a search result's `url` in a later run.

- `company` is always `None`. Workday names only the employer's legal entity, such as `ZINC Zillow, Inc.`.
- `locations` is empty for a posting with several locations, because a search result shows only their count, such as `2 Locations`. With `--details`, it holds the primary location and then the others, by name.
- Without `--details`, `date` comes from Workday's label: "Posted Today", "Posted Yesterday", or "Posted 3 Days Ago", counted back from today in UTC. Workday counts from its own day, so this `date` can be a day late. On one posting we fetched at 02:22 UTC, Workday said "Posted Today" and the posting's start date was the previous day. Workday stops counting at "Posted 30+ Days Ago", so an older posting has no `date`.
- `posted_at` is a calendar date, Workday's start date for the posting. With `--details`, `date` is `posted_at`.
- `id` joins the employer's Workday name and the requisition ID, as in `zillow:P751481-1`.

A Workday record has no salary, workplace type, or application link.

### EconJobMarket fields

An EconJobMarket record carries `title`, `company`, `locations`, `date`, and `description`, and the details `posted_at`, `expires_at`, `company_logo`, and, when present, `department`.

- `company` is the hiring institution, such as `University of Zurich`. `company_logo` links to its logo on EJM.
- `posted_at` is the ad's start date on EJM, and `date` is the same day. Both are calendar dates without a time.
- `expires_at` is the application deadline. In our read of the feed, 7 ads in 319 were still open after their deadline.
- `locations` holds each location the ad lists, with its `city`, `region`, `country_code`, and coordinates when present, named from them, such as `Boston, Massachusetts, US`.
- Two ads in 319 listed no location, and their `locations` is empty.
- `url` is the ad on `econjobmarket.org`, and candidates apply there, so a record has no separate `apply_url`.
- `department` is the hiring unit, such as `Department of Economics`. An ad that says `All departments`, as 61 of 319 did, has no `department`.
- `site_data` holds the ad's `position_types`, ranks such as `Assistant Professor`, and its `categories`, fields of economics such as `Econometrics`, each as a list of names. Every one of the 319 ads listed both.
- The feed carries no salary, employment type, or workplace type.

## Requests by site

### Ashby, EconJobMarket, Greenhouse, Lever, and Workable requests

An Ashby, Greenhouse, Lever, or Workable board search is one request, which returns the whole board, and an EconJobMarket search is one request, which returns every open ad.
A board on Lever's EU host takes a second request, and a failure on Lever's global host other than "not found" stops the search without asking the EU host.
Each request gets a single attempt and no pacing. A failed request raises `Stopped` with an empty `partial`.

### Indeed requests

One search reaches at most 1,000 results, and jobrake warns when that cap cuts a search short.

Indeed returns jobs newest first by the date the posting reached Indeed, the same date `--max-age-hours` filters on.
A reposted job counts as new, so a 24-hour window can include postings published weeks earlier.

Pages follow one another without delay, and each request gets a single attempt.

### LinkedIn requests

The guest search stops at offset 1,000, so one search returns roughly 1,000 postings at most.
jobrake warns when that limit cuts a search short.

jobrake asks LinkedIn for the newest postings first, but the guest endpoint ignores the request and ranks by relevance.
The order can also change between two runs of the same search.
To collect only new postings, repeat the search with `--max-age-hours` covering the time since the last run.

LinkedIn limits guest traffic per IP, and jobrake allows short bursts at a sustained pace of about 1.3 requests per second.
Each process paces only its own requests, so concurrent runs on the same IP can reach the limit sooner.

LinkedIn refuses some requests whatever the pace, up to a quarter of them in our tests.
jobrake retries a 429 up to five times.
If the 429 remains, the search raises `Stopped` with what it has collected so far.
A `--details` search that could not fetch every posting's details raises `Stopped` too, holding every posting it found.

On a data center IP, such as a VPS, LinkedIn refuses posting pages with [HTTP 999](https://http.dev/999). Searches and lookups keep working, but every detail fetch fails.

### SmartRecruiters requests

A search pages through the board one request after another, without pacing, and each request gets a single attempt.
It stops at `--results`, at the board's last matching posting, or at an empty page.
A failed request raises `Stopped` with the postings of the pages before it. So does an empty page that comes before the number of matches SmartRecruiters reported, because postings may have closed during the search and a rerun may find more.

### Workday requests

A search pages through the results one request after another, without pacing, and each request gets a single attempt.
Workday reports at most 2,000 postings per search, and jobrake warns when that cap cuts a search short. Narrow the search with `--query` to reach the rest.
A failed request raises `Stopped` with the postings collected before it. So does an empty page that comes before the number of postings Workday reported, because postings may have closed during the search and a rerun may find more.
