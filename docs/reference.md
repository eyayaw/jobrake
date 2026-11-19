# jobrake reference

This page describes a jobrake record, the fields each site fills,
and how each site's requests behave.
The [guide](guide.md) shows how to search, narrow, and save.

- [Returned fields](#returned-fields)
- [Fields by site](#fields-by-site)
- [Requests by site](#requests-by-site)

## Returned fields

Every job is a dictionary, with three groups of keys.

- **Identity keys:** `site`, `id`, and `url`.
- **Summary keys:** `title`, `company`, `locations`, and `date`.
- **Detail keys:** included when a value is available.

Identity and summary keys are always present, with `None` for an unavailable summary value
and `[]` when jobrake found no place.
An empty `locations` says only that jobrake extracted no place.
It does not say the posting has no place, nor that it is remote.

| Key | Type | Meaning |
| --- | --- | --- |
| `site` | string | The site's name, such as `linkedin` |
| `id` | string | The posting's ID on the site, unique together with `site` |
| `url` | string | The posting's page |
| `title` | string or `None` | The job title |
| `company` | string or `None` | The employer's name |
| `locations` | list of places | The posting's places, in the site's order |
| `date` | string or `None` | The calendar date the site gives the posting, as `YYYY-MM-DD` |
| `description` | string | The posting's text without its HTML, one line per block |
| `language` | string | The posting's language as the site codes it, such as `en` or `zh-CN` |
| `company_url` | string | The employer's page on the site |
| `company_logo` | string | The address of the employer's logo |
| `department` | string | The hiring unit within the employer, as the site names it |
| `team` | string | The posting's team within that unit |
| `employment_type` | string | The site's label as a snake_case slug, such as `full_time`, `part_time`, `contract`, or `internship` |
| `workplace_type` | string | `remote`, `hybrid`, or `on_site` |
| `salary_min`, `salary_max` | number | The bounds of the salary range, in `salary_currency` per `salary_period` |
| `salary_currency` | string | The currency code the site gives, such as `USD` |
| `salary_period` | string | The time unit the amounts cover, such as `YEAR` or `HOUR` |
| `posted_at` | string | When the posting was published or created, as an ISO 8601 timestamp, or as a calendar date where the site gives no time |
| `expires_at` | string | The posting's closing time or application deadline, in the same two forms |
| `apply_url` | string | The application form or link |
| `apply_type` | string | LinkedIn's apply kind as its page names it: `onsite` for its own application form, `offsite` for the employer's |
| `applicants` | integer | The applicant count LinkedIn's page shows |
| `experience_months` | integer | The experience the posting asks for, in whole months |
| `education` | string | The credential the posting asks for, as the site words it |
| `keywords` | list of strings | The terms the employer tagged the posting with, in the site's order |
| `site_data` | object | Fields only this site carries, under the site's own names |

The keys from `description` down are the detail keys.
`employment_type` is a slug of the label the site sends,
with `contractor` and `intern` read as `contract` and `internship`.
Indeed sends one of six labels, and elsewhere the values form no fixed list:
Spotify's board on Lever labels its postings `permanent`.
Ashby gives `salary_period` as `HOUR`, `DAY`, `WEEK`, `MONTH`, or `YEAR`,
and so does LinkedIn's page markup.
Indeed's value and the one in LinkedIn's structured data pass through as sent.

Each place in `locations` has a `name`, the site's label for it or its parts joined
when the site gives no label,
and carries `city`, `region`, `country_code`, `latitude`, and `longitude` only
when the site gives them for that place.
`country_code` has the form of an ISO 3166-1 alpha-2 code, such as `US`,
and jobrake checks the form only.
jobrake parses nothing out of a place's name, so a place named `Seattle, WA` carries no `city`
unless the site sent one. A place the site lists twice with the same parts appears once.
Places that share a name but differ in any part, such as `Remote` in two countries, each appear.

`workplace_type` appears only when the site states it,
so an absent one leaves the workplace unknown and does not mean on-site.
`team` comes from Ashby and Lever only.

`site_data` holds fields that only one site carries, under that site's own names,
such as EconJobMarket's `position_types`.
Its keys depend on `site`, and each site's fields section lists them.
A key that a second site comes to share with the same meaning moves into the record.
A detail key is absent when the site omits or does not publish the value,
or when jobrake did not fetch the posting page.

The sites use the same names for the details they share.
Each site's section under [Fields by site](#fields-by-site) lists the details it carries.
`apply_type`, `applicants`, and `experience_months` come from LinkedIn only,
and LinkedIn carries no `workplace_type`, `apply_url`, or `language`.

A posting can carry two dates. `date` holds the calendar date, such as `2026-09-19`,
and `posted_at` holds the full timestamp when the site gives one,
such as `2026-09-19T05:00:00+00:00`, and the calendar date otherwise.
jobrake prefers the date a search result states and falls back to the calendar portion
of `posted_at`.
The exceptions are LinkedIn, Workday, StepStone, and INOMICS with `--details`, where `date` is the
calendar date of the `posted_at` that the posting page gives.
A page without one leaves the search result's date.
Compare on `date`, and read `posted_at` for a time of day.

## Fields by site

### LinkedIn fields

A LinkedIn search result carries `title`, `company`, `locations`, and `date`, and no details.
`--details | -d` fetches each posting page and adds `description` and, when the page has them,
`posted_at`, `expires_at`, `employment_type`, `education`, `experience_months`, `apply_type`,
`applicants`, `company_url`, `company_logo`, `salary_min`, `salary_max`, `salary_currency`,
and `salary_period`.
[`jobrake linkedin postings`](guide.md#fetch-known-postings) builds the same record
from an ID or a URL in a later run.

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
- A posting placed in a whole country comes with fewer details,
  as [Fetch posting details](guide.md#fetch-posting-details) says.

### Indeed fields

An Indeed record carries `title`, `company`, `locations`, `date`, and `description`,
and, when Indeed supplies them, the details `posted_at`, `expires_at`, `language`,
`employment_type`, `workplace_type`, `apply_url`, `company_url`, `company_logo`, `salary_min`,
`salary_max`, `salary_currency`, and `salary_period`.
A search returns them all, so Indeed takes no `--details`.

- `id` is Indeed's job key, and `url` opens the posting on the country edition searched.
- `locations` holds one place with the `city`, `region`, `country_code`, `latitude`,
  and `longitude` Indeed gives, named from those parts.
- `posted_at` is the time the posting was published, and `date` is its calendar date.
  `--max-age-hours` filters on another date, as the note under
  [Search for jobs](guide.md#search-for-jobs) says.
- `employment_type` comes from the posting's attribute labels, as a slug such as `full_time`.
- `workplace_type` follows Indeed's Remote and Hybrid work tags,
  as [Remote jobs](guide.md#remote-jobs) describes.
- The salary fields hold the range Indeed gives with its currency and period.
  A posting with one exact figure carries it as both bounds,
  and a posting with only a minimum or only a maximum carries that bound alone.
- `apply_url` is the application link Indeed gives,
  and `company_url` is the employer's page on Indeed.

### Greenhouse fields

A Greenhouse record carries `title`, `locations`, and `description`.
It also carries `company`, `date`, and the details `posted_at`, `language`, `department`,
and `expires_at` when Greenhouse supplies them, which its documented list response does not promise.

- `posted_at` is the time the posting was first published, and `date` is its calendar date.
  `expires_at` is the application deadline.
- `department` is the job's department when Greenhouse lists exactly one,
  as it did for all 195 postings on Airbnb's board on 2026-10-28.
- `locations` holds one place, named with the text the employer entered,
  such as `Remote, Canada; Remote, United States`.
- `url` is the posting on the employer's own careers site when the board lives there,
  as Airbnb's does, and on `job-boards.greenhouse.io` otherwise.
- In our tests on two boards, every posting carried a company, a location, a first-published time,
  and a language, and one posting in 430 had a deadline.
- Employers can add facts such as a workplace type as custom fields,
  which differ from board to board.
  jobrake leaves those out, so a Greenhouse record has no salary, employment type,
  or workplace type.

### Ashby fields

An Ashby record carries `title`, `locations`, `date`, and `description`,
and the details `posted_at`, `employment_type`, `department`, `team`, `apply_url`,
and, when present, `workplace_type`, `salary_min`, `salary_max`, `salary_currency`,
and `salary_period`.

- `company` is always `None`, because Ashby's response never names the employer.
  The board token tells you whose board it is.
- `posted_at` is the time the posting was published, and `date` is its calendar date.
- `locations` holds the posting's primary location first and then its other places,
  named as the employer entered them, such as `Remote (US)` and `Remote (Canada)`.
  Each place carries the `city` and `region` of its address as Ashby spells them,
  and `region` can be a code or a name, such as `NY` or `Ontario`.
- Ashby gives the country as a name, such as `USA` or `United Kingdom`,
  so an Ashby place has no `country_code`.
- `workplace_type` is `remote`, `hybrid`, or `on_site`, as the employer set it,
  and is absent when the employer set none.
- The salary fields come from the posting's first salary range.
- `team` is the posting's team, such as `Solutions Consulting`.
  `site_data` holds its `summaryComponents` as Ashby sends them,
  so equity, commission, and bonus appear there beside the salary range.
  In our test on one board, 124 of 172 postings listed an equity value and 40 a commission.
- `url` and `apply_url` point to the posting on `jobs.ashbyhq.com`.
- A search also returns postings the employer marked unlisted,
  which Ashby intends for direct links only.
- In our test on one board of 172 postings, every posting carried a location, a publish time,
  and an employment type, 165 carried a salary range, 162 a city, and 16 were remote.

### Lever fields

A Lever record carries `title`, `locations`, `date`, and `description`, and the details `posted_at`,
`apply_url`, `team`, and, when present, `employment_type`, `workplace_type`, and `department`.

- `company` is always `None`, because Lever's response never names the employer.
- `posted_at` is the time the posting was created, and `date` is its calendar date.
- `description` joins the posting's description, its lists such as requirements and benefits,
  each under its own heading, its salary text, and its closing text.
- `locations` holds the posting's primary location first and then its other places,
  named as the employer entered them, such as `London, United Kingdom`.
  The primary place carries the posting's `country_code`.
- `employment_type` is the employer's commitment label as a slug,
  such as `full_time` for `Full-time`.
- `workplace_type` is `remote`, `hybrid`, or `on_site`, as the employer set it,
  and is absent for a posting the employer left unspecified.
- `url` is the posting on `jobs.lever.co` or `jobs.eu.lever.co`,
  and `apply_url` is its application form.
- Lever can send a salary range, but its documentation does not list the pay intervals it uses,
  so jobrake leaves salary out. Salary text in the description stays in `description`.
- `team` is the posting's team, such as `Administrative`.
- In our tests on one board, every one of five postings carried a location, a country, a commitment,
  and a workplace type, and none had a salary range.

### Workable fields

A Workable record carries `title`, `company`, `locations`, `date`, and `description`,
and the details `posted_at`, `employment_type`, `department`, `apply_url`,
and, when present, `workplace_type` and `education`.

- `posted_at` is the date the posting was published, with no time of day, so it equals `date`.
- Each place carries the `city`, `region`, and `country_code` the employer entered
  and is named with the city, region, and country name, such as `Paris, Île-de-France, France`.
- Workable lists a posting open in several places once per place.
  jobrake returns it once, with each of its places.
- A posting's top-level city, state, and country add a place of their own
  when no listed place matches all three, such as `Paris, Île-de-France, France`.
  On the board we measured, they repeated the first place.
- `workplace_type` is `remote` when the employer marked the posting as remote.
  The board flags remote alone, so another posting has no `workplace_type`.
  `employment_type` is a slug such as `full_time`.
- `education` is the degree the employer chose, such as `Master's Degree`, and is absent
  when the employer chose none.
- `url` is the posting on `apply.workable.com`, and `apply_url` is its application form.
- In our test on one board of six postings,
  every posting carried a country and an employment type, and three named no city.
- A Workable record has no salary or language, because the board does not publish them.

### SmartRecruiters fields

A SmartRecruiters record carries `title`, `company`, `locations`, and `date`,
and the details `posted_at`, `employment_type`, `language`, and, when present, `department`
and `workplace_type`.

- `locations` holds one place, named as SmartRecruiters writes it, such as `Wuxi, Jiangsu, China`,
  with its `city`, `country_code`, and, when present, `region`, `latitude`, and `longitude`.
- `posted_at` is the time the posting was released, and `date` is its calendar date.
  `language` is a code such as `en` or `zh-CN`.
- `url` opens the posting on `jobs.smartrecruiters.com`.
- `workplace_type` is `remote` or `hybrid` for a posting the employer marks so,
  and absent otherwise, because SmartRecruiters does not mark on-site.
  `--remote` keeps the postings SmartRecruiters files as remote,
  which can include ones whose `workplace_type` is `hybrid`.
- SmartRecruiters serves a description only with each posting, so a search result has none.
  `--details | -d` fetches each posting and adds `description` and, when present, `apply_url`.
  It holds every section of the ad under its title, in SmartRecruiters' order:
  the company description, the job description, the qualifications, and additional information.
- [`jobrake smartrecruiters postings`](guide.md#fetch-known-postings) builds the same record
  from a search result's `url` in a later run, without the `department`,
  which only the search result carries.
- `apply_url` is the application link the posting gives. In five postings read on 2026-11-18,
  it was the posting page's address with `?oga=true`.
- A record has no salary, because SmartRecruiters does not publish one.

### Workday fields

A Workday search result carries `title`, `locations`, and `date`, but no description.
`--details | -d` fetches each posting and adds `description`, `posted_at`, and `employment_type`,
and gives the primary place its `country_code`.
[`jobrake workday postings`](guide.md#fetch-known-postings) builds the same record
from a search result's `url` in a later run.

- `company` is always `None`. Workday names only the employer's legal entity,
  such as `ZINC Zillow, Inc.`.
- `locations` is empty for a posting with several locations,
  because a search result shows only their count, such as `2 Locations`.
  With `--details`, it holds the primary location and then the others, by name.
- Without `--details`, `date` comes from Workday's label:
  "Posted Today", "Posted Yesterday", or "Posted 3 Days Ago", counted back from today in UTC.
  Workday counts from its own day, so this `date` can be a day late.
  On one posting we fetched at 02:22 UTC, Workday said "Posted Today"
  and the posting's start date was the previous day.
  Workday stops counting at "Posted 30+ Days Ago", so an older posting has no `date`.
- `posted_at` is a calendar date, Workday's start date for the posting.
  With `--details`, `date` is `posted_at`.
- `id` joins the employer's Workday name and the requisition ID, as in `zillow:P751481-1`.

A Workday record has no salary, workplace type, or application link.

### StepStone fields

A StepStone search result carries `title`, `company`, `locations`, and `date`, and the details
`language`, `company_logo`, `posted_at`, and `expires_at`. `--details | -d` adds `description`,
`employment_type`, and `company_url`.

- `locations` holds one place, named as StepStone writes it, with every city of a posting open in
  several. It adds `country_code`, and `latitude` and `longitude` when StepStone gives them.
- `date` is the posting's calendar date, `posted_at` the time StepStone dates it, and `expires_at`
  the time StepStone expects to remove it. `language` is a code such as `de`.
- `url` opens the posting at `stepstone.de/job/<id>`.
- `site_data` carries the result's `section`, either `main` or `regionalExtended` for a match
  outside the radius, and the card's `labels`, such as `REMOTE`, `EASY_APPLY`, and `NO_COVER_LETTER`.
  `REMOTE` marks a posting that allows home office, though not every such posting carries it.
- StepStone serves the ad text only on a posting's page, so a search result has no `description`.
  `--details | -d` fetches each posting, which a cached posting skips, and adds its `description`,
  `employment_type`, `company_url`, and the place's `city` when the posting names one city.
  The page dates a posting to when it went online, up to 15 hours after the search result's
  `posted_at` on 11 postings compared, so `--details` can move `posted_at` and `date`.
- [`jobrake stepstone postings`](guide.md#fetch-known-postings) builds the same record from a
  search result's `url` in a later run.
- A record has no salary, because the range StepStone sends is its own estimate rather than the
  employer's figure, and no application link. It has no workplace type, because a posting states
  only whether home office is possible, in the same words for a fully and a partly remote role.
  `--remote` applies StepStone's own filter for fully remote postings, whose records also lack a
  workplace type.

### Personio fields

A Personio record carries `title`, `locations`, and `date`, and the details `posted_at`,
`employment_type`, `site_data`, and, when present, `company`, `description`, `department`,
`keywords`, and the salary fields.

- `company` is the posting's subcompany, such as `tado GmbH`,
  which Personio names when the employer has set up subcompanies.
- `posted_at` is the time the posting was created, and `date` is its calendar date.
- `locations` holds the posting's office and then its additional offices,
  named as the employer entered them, such as `Mannheim` and `Köln`.
- `description` joins the posting's description blocks, each under its name when it has one.
  Personio serves each posting's description in one language,
  and its feed in any other language lists the posting without one.
  jobrake first reads the feed in the board's default language,
  German or English on the boards we tested.
  A posting that feed leaves without a description comes whole, title included,
  from the first of English, German, French, Spanish, Dutch, Italian, and Portuguese
  that describes it.
  In our test on 71 boards, the default-language feeds left 161 of 742 postings without a
  description, and the other languages described all of them.
- `employment_type` is Personio's contract type as a slug,
  such as `permanent`, `internship`, `fixed_term`, or `working_student`.
- `salary_period` is `YEAR`, `MONTH`, or `HOUR`, and a salary without a maximum carries
  `salary_min` alone. In the same test, 62 of 742 postings published a salary.
- `keywords` splits the feed's comma-separated keywords, such as `Werkstudent:in,Accounting`.
- `site_data` holds `seniority`, `schedule`, `occupation`, `occupationCategory`, and,
  when present, `recruitingCategory` and `yearsOfExperience`, as the feed names them.
- `url` is the posting on `<board>.jobs.personio.de`.

A Personio record has no workplace type or application link.

### AcademicTransfer fields

An AcademicTransfer record carries `title`, `company`, `locations`, `date`, and `description`,
and the details `posted_at`, `language`, `employment_type`, and, when present, `department`,
`education`, `expires_at`, `salary_min`, `salary_max`, `salary_currency`, `salary_period`,
`apply_url`, `keywords`, and `site_data`.

- `id` is the vacancy's number on the site, such as `365285`,
  and `url` opens its page on `academictransfer.com`.
- `company` is the organization, such as `Erasmus University Rotterdam`, and `department` the unit
  that hires within it, which 3 of the 53 academic economics vacancies of 2026-11-17 named.
- `locations` holds one place with its `city` and `country_code`, such as `Rotterdam, NL`.
  2 of the 53 academic economics vacancies of 2026-11-17 were in Germany, the rest in the
  Netherlands.
- `posted_at` is the timestamp the vacancy was published, and `expires_at` its application
  deadline, also a timestamp.
- `description` joins the vacancy's description, requirements, terms of employment,
  additional information, and how to apply. It leaves out the organization's and the department's
  own descriptions, which 24 and 14 of 50 academic economics vacancies carried.
- `language` is `en` or `nl`, the language the vacancy is written in.
- `employment_type` is `permanent` or `temporary`, and `education` the level of education the
  vacancy asks for, such as `Doctorate` or `University graduate`.
- `salary_min` and `salary_max` are the salary range. The site names no currency or period,
  so jobrake infers `salary_currency` `EUR` and `salary_period` `MONTH` from the vacancies' texts:
  36 of the 43 academic economics vacancies of 2026-11-17 with a range named an amount in euros a
  month, and all 43 were in the Netherlands. The site sends a range of 0 to 0 for a vacancy
  without one, as 10 of the 53 did, and jobrake leaves that range out.
- `apply_url` is the employer's application link.
- `site_data` holds the vacancy's `min_weekly_hours` and `max_weekly_hours` when it gives them.

### AEA JOE fields

An AEA JOE record carries `title`, `company`, `locations`, `date`, and `description`,
and the details `posted_at`, `site_data`, and, when present, `department`, `expires_at`,
and `keywords`, one per line of the listing's keywords, which 542 of the 774 listings gave.

- `id` is the JOE ID: the year and issue that list the listing, and its number,
  such as `2026-02_111477855`. `url` opens the listing on `aeaweb.org`.
- `company` is the institution, such as `Ahmedabad University`, and `department` the unit that
  hires within it, which 520 of the 774 listings of 2026-11-17 named.
- `locations` holds each place the listing names, with its `city` and `region`,
  named from them and the country, such as `Cergy, Ile de France, FRANCE`.
  JOE names the country in words, so a place has no `country_code`.
  35 of the 774 listings named more than one place.
- `posted_at` and `date` are the calendar date the listings page shows for the listing.
- `expires_at` is the application deadline, a calendar date, which 18 of the 774 listings lacked.
  JOE keeps a listing active past its deadline: 232 of the 774 were.
- `description` is the listing's full text as JOE stores it, with line breaks and no markup.
- `site_data` holds the listing's `section`, such as `Full-Time Nonacademic`,
  its `jel` codes, such as `J2` or `F`, and, when present, the `division` of the institution,
  its `salary_range` as free text, such as `Competitive` or
  `$145,000/year`, which 330 listings gave, and a `status` such as `Position has been filled`,
  which JOE sets when the employer closes the search.

### EconJobMarket fields

An EconJobMarket record carries `title`, `company`, `locations`, `date`, and `description`,
and the details `posted_at`, `expires_at`, `company_logo`, and, when present, `department`.

- `company` is the hiring institution, such as `University of Zurich`.
  `company_logo` links to its logo on EJM.
- `posted_at` is the ad's start date on EJM, and `date` is the same day.
  Both are calendar dates without a time.
- `expires_at` is the application deadline.
  In our read of the feed, 7 ads in 319 were still open after their deadline.
- `locations` holds each location the ad lists, with its `city`, `region`, `country_code`,
  and coordinates when present, named from them, such as `Boston, Massachusetts, US`.
- Two ads in 319 listed no location, and their `locations` is empty.
- `url` is the ad on `econjobmarket.org`, and candidates apply there,
  so a record has no separate `apply_url`.
- `department` is the hiring unit, such as `Department of Economics`.
  An ad that says `All departments`, as 61 of 319 did, has no `department`.
- `site_data` holds the ad's `position_types`, ranks such as `Assistant Professor`,
  and its `categories`, fields of economics such as `Econometrics`, each as a list of names.
  Every one of the 319 ads listed both.
- The feed carries no salary, employment type, or workplace type.

### INOMICS fields

An INOMICS search result carries `title`, `company`, `locations`, and `date`, and the details
`posted_at`, `site_data`, and `workplace_type` when the card states one.
`--details | -d` adds `description` and, when the job's page gives them, `expires_at` and the
place's `region` and `country_code`.

- `url` opens the job at `inomics.com/job/<id>`.
- `company` is the first employer the card names. 2 of the 112 jobs of 2026-11-17 named none,
  and 2 named more than one. `--details` takes the hiring organization the job's page names.
- `locations` holds one place, named as the card writes it, such as `Saarbrücken, Germany`, with
  its `city`, or the country alone, as 7 of the 112 gave. One of the 112 named no place.
  The card names the country in words. `--details` takes the place from the job's page when the
  page gives the country's code, with the same name and its `region` and `country_code`,
  as all 15 jobs in Germany did, and keeps the card's place otherwise.
  That place has a `city` only when the page's other schema.org block names it, so a page
  without that block drops the city the card gave, as job 1555182's did earlier that day.
- `date` and `posted_at` are the day the card shows as posted, which INOMICS moves to the day it
  reposts a job. The job's page dates a job the same way: on 2026-11-17, 17 of 17 pages that
  carried that date matched their card. A job INOMICS also lists as a scholarship dates it by the
  day it was entered instead, so `--details` can move that job's `date`.
- `expires_at` is the application deadline, which 9 of the 15 jobs in Germany lacked.
- `workplace_type` is `hybrid` or `remote` when the card says so, as 9 and 6 of the 112 did.
- `description` is the text of the job's page. The page's schema.org blocks carry an excerpt.
- `site_data` holds the card's `types`, such as `Postdoc Job` or `Assistant Professor / Lecturer
  Job`. A job can also carry the type of a program, scholarship, or course, such as `PhD Program`.
- A record has no salary, employment type, or application link.

### UN Careers fields

A UN Careers record carries `title`, `company`, `locations`, `date`, and `description`,
and the details `posted_at`, `expires_at`, and `site_data`.

- `title` is the opening's posting title, which for a staff post ends in its grade,
  such as `HUMANITARIAN AFFAIRS OFFICER (PROGRAMME), P3`.
- `company` is the UN entity that hires,
  such as `Office for the Coordination of Humanitarian Affairs`.
- `locations` holds one place per duty station, named by the site's label,
  such as `NEW YORK`, `Juba`, or `FO West Bank`, with no other part.
  In our read of 448 openings on 2026-11-16, 8 listed more than one duty station.
- `posted_at` is the opening's start and `expires_at` its deadline, as UTC timestamps such as
  `2026-11-13T05:00:00.000Z` and `2026-11-20T04:59:59.000Z`, which fall at the start and the end of
  a day in New York. `date` is the calendar date of `posted_at`.
- `description` holds every section of the opening under its title, in the site's order.
  A section such as `Work Location` can say the work is remote,
  and the record carries no `workplace_type`.
- `url` opens the opening on `careers.un.org`, where candidates apply,
  so a record has no separate `apply_url`.
- `site_data` holds the opening's `category` code, such as `PD` or `INT`, its `level`,
  such as `P-3`, `I-1`, or `CON`, its `recruitment_type`, such as `Temporary Opportunities`,
  and, when present, its `job_family` and `job_network`.
  A `category` can be a code that `--category` does not take,
  such as `RLG`, which 25 of the 448 openings carried.
- The list carries no salary or employment type.

## Requests by site

### Ashby, EconJobMarket, Greenhouse, Lever, and Workable requests

An Ashby, Greenhouse, Lever, or Workable board search is one request, which returns the whole board,
and an EconJobMarket search is one request, which returns every open ad.
A board on Lever's EU host takes a second request,
and a failure on Lever's global host other than "not found" stops the search without
asking the EU host.
Each request gets a single attempt and no pacing.
A failed request raises `Stopped` with an empty `partial`.

### AcademicTransfer requests

A search first reads the site's jobs page for the public token its search script sends,
then pages through the list API that page reads, newest first, 50 vacancies to a request,
each with a single attempt. jobrake waits 10 seconds before each request to the API,
the crawl delay the robots.txt of `www.academictransfer.com` asks for.
The robots.txt of `api.academictransfer.com` disallows every path.
On 2026-11-17 the API counted 728 active vacancies, and a page of 50 was about 580 KB.
A failed request, a jobs page without a readable token, or an empty page before the count the API
reported raises `Stopped`, and its `partial` holds the vacancies of the pages before it.
A search reads the token once, at its start. How long a token stays valid was not measured,
and the longest search tested, two pages, took 22 seconds.

### AEA JOE requests

A search is two requests, each with a single attempt and no pacing.
The first reads the JOE listings page with the search's filters and 5,000 listings to a page,
which shows every listing of the search with its posted date.
On 2026-11-17 the page of all 774 active listings was 2.4 MB.
The second reads the XML export that the page links for the same listings,
2.6 MB for all 774, which holds every other field, so jobrake makes no request per listing.
A failed request raises `Stopped` with an empty `partial`, and so does a page that shows listings
without both their posted dates and an export link.
A search that matches nothing gets a page without listings and makes no second request.
A section heading, `2` or `4`, is sent with its subsections, because JOE files each listing under a
subsection: on 2026-11-17, `2` alone matched no listing, while `2a` and `2b` held 115.

### Personio requests

A Personio search reads the board's feed in its default language.
While a posting still lacks a description, the search reads the feed in the next language,
in the order [Personio fields](#personio-fields) gives, so a search takes one to eight requests.
In our test, 69 of 71 boards took one or two requests.
Each request gets a single attempt and no pacing.
A failed first request raises `Stopped` with an empty `partial`,
and a failed later one keeps the postings already read in `partial`.

### Indeed requests

One search reaches at most 1,000 results, and jobrake warns when that cap cuts a search short.

Indeed returns jobs newest first by the date the posting reached Indeed,
the same date `--max-age-hours` filters on.
A reposted job counts as new, so a 24-hour window can include postings published weeks earlier.

Pages follow one another without delay, and each request gets a single attempt.
A failed request raises `Stopped` with the jobs of the pages before it, and a page that
repeats an earlier page's cursor raises it with the jobs read so far, its own included.

### LinkedIn requests

The guest search stops at offset 1,000, so one search returns roughly 1,000 postings at most.
jobrake warns when that limit cuts a search short.

jobrake asks LinkedIn for the newest postings first, but the guest endpoint ignores the request
and ranks by relevance. The order can also change between two runs of the same search.
To collect only new postings, repeat the search with `--max-age-hours` covering the time
since the last run.

LinkedIn limits guest traffic per IP, and jobrake allows short bursts
at a sustained pace of about 1.3 requests per second.
Each process paces only its own requests, so concurrent runs on the same IP can reach
the limit sooner.

LinkedIn refuses some requests whatever the pace, up to a quarter of them in our tests.
jobrake retries a 429 up to five times.
If the 429 remains, the search raises `Stopped` with what it has collected so far.
So does a results page from an address outside the search endpoint, such as a login page.
No search in our tests met one.
A `--details` search that could not fetch every posting's details raises `Stopped` too,
holding every posting it found and, in `failed`, the URLs of the postings it could not fetch.

On a data center IP, such as a VPS, LinkedIn refuses posting pages
with [HTTP 999](https://http.dev/999).
Searches and lookups keep working, but every detail fetch fails.

### SmartRecruiters requests

A search pages through the board one request after another, without pacing,
and each request gets a single attempt.
It stops at `--results`, at the board's last matching posting, or at an empty page.
A failed request raises `Stopped` with the postings of the pages before it.
So does an empty page that comes before the number of matches SmartRecruiters reported,
because postings may have closed during the search and a rerun may find more.

### Workday requests

A search pages through the results one request after another, without pacing,
and each request gets a single attempt.
Workday reports at most 2,000 postings per search, and jobrake warns
when that cap cuts a search short.
Narrow the search with `--query` to reach the rest.
A failed request raises `Stopped` with the postings collected before it.
So does an empty page that comes before the number of postings Workday reported,
because postings may have closed during the search and a rerun may find more.

### StepStone requests

A search reads StepStone's mobile listings API and pages through the results one request after
another, without pacing, and each request gets a single attempt.
StepStone mixes in postings outside the radius, so the results can exceed the radius's own matches.
A search stops at `--results`, at the last match, or at an empty page.
`--details` and `jobrake stepstone postings` fetch each posting's page for its description,
one request per posting, which a cached posting skips.
A failed request raises `Stopped` with the postings of the pages before it.
So does an empty page that comes before the number of matches StepStone reported,
because postings may have closed during the search and a rerun may find more.

### INOMICS requests

A search is one request, without pacing and with a single attempt, to the endpoint INOMICS's search
page reads its results from. It asks for the first `--results` jobs in the site's order of
relevance, rounded up to a multiple of 20, as the page's "load more" button does.
The site's numbered pages are unreliable: on the afternoon of 2026-11-17, pages sorted by date all
repeated the first, and unsorted pages reached 92 of the 112 jobs.
All 112 jobs of that day came in one answer of 391 KB.
A failed request, or an answer without the count, raises `Stopped` with no postings.
An answer with fewer jobs than it counts raises `Stopped` with the jobs it holds.
`--details` and `jobrake inomics postings` fetch each job's page, one request per job,
which a cached posting skips. A page answering 404 or 410 counts as a job gone.

### UN Careers requests

A search pages through the openings 100 at a time, highest job ID first, one request after another,
without pacing, and each request gets a single attempt.
Many openings share a start date, and the site orders those differently from one request to the
next, so pages sorted by date repeated 11 of 448 openings and skipped 11 others in our test.
Job IDs are unique, and in our test, pages sorted by them gave each of the 448 openings once.
An opening that closes during a search still shifts the later pages, so one can be skipped,
and an opening that appears repeats one, which jobrake keeps once.
Job IDs follow the order the site created openings in: on 2026-11-16 the 20 highest IDs had start
dates over five days.
`--max-age-hours` sends the site's posting age filter, which keeps the openings whose start date lies
within a whole number of days, with the hours rounded up to days. A multiple of 24 bounds the age
exactly. The site's menu offers 1, 7, and 30 days, and on 2026-11-17 the filter applied 2, 3, 14,
45, and 365 days as well, while it cut 6.9 days to 6.
The 448 openings of 2026-11-16 took five requests.
A search stops at `--results`, at the last opening, or at an empty page.
A failed request raises `Stopped` with the openings of the pages before it.
So does an empty page that comes before the number of openings UN Careers reported,
because openings may have closed during the search and a rerun may find more.
The list carries each opening whole, so jobrake makes no request per opening.
A search that takes `--category`, `--duty-station`, `--level`, `--department`, `--job-network`,
`--job-family`, or `--recruitment-type` first reads the site's list of filter values, about 330 KB,
to turn names into the site's codes.
