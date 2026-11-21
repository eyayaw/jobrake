# Indeed (`indeed`)

[Indeed](https://www.indeed.com) is a general job board with a separate edition for each country it
serves. jobrake searches one edition at a time.

```sh
jobrake indeed search -q "data scientist" -c nl -l Amsterdam -n 2
jobrake indeed search -q "data analyst" -c gb -l London -n 5 -a 24 -o jobs.jsonl
jobrake indeed search -q econometrics -c nl --language en --remote
jobrake indeed places amsterdam -c nl
jobrake indeed companies "Booking" -c nl
jobrake indeed attributes "data scientist" -c us
```

`search` requires `--country` and returns postings newest first, by the date each reached Indeed.
Indeed returns the details it has with the search itself, so an Indeed search needs nothing further:
it takes no `--details`, and the site has no `postings` command.
In Python the options are keyword arguments:
`scrape("indeed", query="economist", country="us", attributes=["CF3CP"])`.

## Options

| Option                  | Value                                                    | Default           |
| ----------------------- | -------------------------------------------------------- | ----------------- |
| `--query`, `-q`         | a job title or keywords                                  | none              |
| `--country`, `-c`       | an ISO 3166-1 alpha-2 code, such as `de`, `gb`, or `us`  | required          |
| `--location`, `-l`      | a city or another place within that country              | the whole edition |
| `--radius`, `-r`        | kilometers around the location, 0 or more                | 40                |
| `--results`, `-n`       | a positive integer                                       | 10                |
| `--max-age-hours`, `-a` | a positive integer                                       | no age limit      |
| `--company-ids`         | one Indeed employer key                                  | every employer    |
| `--language`            | a two-letter language code, such as `en`                 | every language    |
| `--attributes`          | attribute codes, all of which a posting must carry       | none              |
| `--remote`              | only postings Indeed tags Remote                         | off               |

A posting must match every option given.
The [reference](../reference.md#options) has the rules every site shares.

### Country and location

Indeed searches one country edition at a time, so `--country` is required.
Set it to the country's ISO 3166-1 alpha-2 code in either case, such as `de`, `gb`, or `us`.
A code with no Indeed edition is an error that lists the codes Indeed serves.

`--location` narrows that edition to a city or another place within it,
and [`jobrake indeed places`](#lookups) suggests the names Indeed knows.
Without `--radius`, jobrake searches 40 km around the location.
`--radius` counts only with `--location`: without one, the search covers the whole edition and
ignores the radius.

### Query

jobrake sends the query unchanged.
Indeed matches loosely, so a returned posting need not contain every word you typed.
Where that matters, run several narrow queries and filter the results yourself.
Leave out `-q` to search without keywords.

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
other indexed content, so `data OR research` may return postings with neither word in the title.
You may be tempted to try `description:<term>`, but it does not reliably restrict
results to descriptions. `AND`, `OR`, and `NOT` act as Indeed search hints on their own.
Their results can differ from Boolean union, intersection, and exclusion.
Use the location and posting-age options to restrict geography and age.
Keep those restrictions out of query text such as `"data science jobs in England last 24 hours"`.

### Posting age

`--max-age-hours` measures a posting's age from the date it reached Indeed, the date the results
are ordered by. A posting inside your age window can still carry an older `posted_at`,
the publication timestamp the search returns.
A reposted posting counts as new, so a 24-hour window can include postings published weeks earlier.

### Employers

`--company-ids` takes an Indeed employer key, which [`jobrake indeed companies`](#lookups) finds
from the company's name:

```sh
jobrake indeed search -c nl -q "data scientist" --company-ids 8e8f030e53ea29e4
jobrake indeed search -c nl --company-ids 8e8f030e53ea29e4
```

This key selects _Booking.com_. Without `-q`, the search covers its postings without keywords.
Indeed intersects the keys it receives, so a search takes one employer key and rejects more.
Search one employer at a time and combine the results.

### Language

`--language` selects Indeed postings in one language, in either case. Indeed decides each posting's language.
The option accepts two-letter language codes such as `en` and `nl`.
Indeed's [language-code reference](https://docs.indeed.com/api/common/objects/LanguageCode)
describes ISO 639-1.
A well-formed code can still match nothing.

### Attributes and remote work

`--attributes` takes the codes that [`jobrake indeed attributes`](#lookups) finds:

```sh
jobrake indeed search -q "data scientist" -c us --attributes X62BT
jobrake indeed search -q economist -c us --attributes CF3CP 6QC5F
```

`X62BT` selects Python.
The second search requires both Full-time (`CF3CP`) and Doctoral degree (`6QC5F`),
because codes intersect: every returned posting carries every code you list.
To match any of several codes, run separate searches and combine the results.
A posting can hold codes that look mutually exclusive,
so a Full-time match may carry Part-time as well when the employer offers either arrangement.
The filter has no way to exclude a code.

`--remote` is shorthand for `--attributes DSQF7`, so a posting must carry the Remote tag
and every other code you pass.
The tag reflects Indeed's classification.
Check the posting for residency and workplace requirements.

## Lookups

Each lookup requires `--country` and prints a JSON list of `{"id", "name"}` entries in Indeed's
order. The `id` is the value a search takes.

| Command              | Lists                                                   | `id` goes to    |
| -------------------- | ------------------------------------------------------- | --------------- |
| `places <name>`      | the edition's location suggestions, best match first    | `--location`    |
| `companies <name>`   | employer keys with their company names                  | `--company-ids` |
| `attributes <query>` | the attribute codes on the first 100 matching postings  | `--attributes`  |

`places` lists up to ten suggestions.
`companies` may include related companies, so choose the employer whose postings you want.

`attributes` reads postings that match a job title or keywords and applies no posting-age
restriction. Those postings carry several (hundred) attributes between them.
Search the list by label:

```sh
jobrake indeed attributes -c us "data scientist" \
  | jq -r '.[] | select(.name | test("python"; "i")) | [.id, .name] | @tsv'
# X62BT Python
```

Each run samples the postings afresh, so a code can be missing from one lookup
and present in the next.
Try the lookup again, or a related query, when a code you expect does not appear.
Labels can differ by country edition. A label can also belong to several codes,
and the lookup keeps each code separately.

In Python the lookups are `places(fetcher, name, country=...)`,
`companies(fetcher, name, country=...)`, and `attributes(fetcher, query, country=...)`
in `jobrake.sites.indeed`.

## Fields

An Indeed record carries `title`, `company`, `locations`, and `date`,
and, when Indeed supplies them, `description` and the details below.
[The record](../reference.md#the-record) describes every key.

| Key                                | Holds                                                           |
| ---------------------------------- | --------------------------------------------------------------- |
| `id`                               | Indeed's job key                                                |
| `url`                              | the posting on the country edition searched                     |
| `locations`                        | one place, named from the parts Indeed gives                    |
| `posted_at`, `date`                | the time the posting was published, and its calendar date       |
| `expires_at`                       | the expiration time Indeed gives                                |
| `language`                         | Indeed's two-letter code, such as `en`                          |
| `employment_type`                  | a slug of one of the posting's attribute labels                 |
| `workplace_type`                   | `remote` or `hybrid`, from Indeed's tags                        |
| `salary_min`, `salary_max`         | the range Indeed gives                                          |
| `salary_currency`, `salary_period` | the range's currency and period, as Indeed sends them           |
| `apply_url`                        | the application link Indeed gives                               |
| `company_url`, `company_logo`      | the employer's page on Indeed, and its logo                     |

The place carries the `city`, `region`, `country_code`, `latitude`, and `longitude` Indeed gives.
`language` also carries the legacy codes `iw` for Hebrew and `in` for Indonesian.
`employment_type` is `full_time`, `part_time`, `contract`, `temporary`, `internship`, or `per_diem`.
A posting with one exact salary figure carries it as both bounds,
and a posting with only a minimum or only a maximum carries that bound alone.

`workplace_type` is `remote` for a posting tagged Remote
and `hybrid` for one tagged Hybrid work.
Indeed tags some postings both, and such a posting has no `workplace_type`.

A record has no `site_data`, and no `department`, `team`, `education`, `experience_months`,
`apply_type`, `applicants`, or `keywords`.

`jobrake.identify` reads an Indeed link that carries the posting's key in `jk`,
or in `vjk` on a search page, and returns `("indeed", <key>)`,
as the [Python API](../reference.md#python-api) describes.

## Limits

A search reads Indeed's results a page at a time.
Pages follow one another without delay, and each request gets a single attempt.
One search reaches at most 1,000 results, and jobrake warns when that cap cuts a search short.
Narrow the search to reach more of Indeed's postings.

A failed request, an error from Indeed, or an answer jobrake cannot read raises `Stopped` with the
postings of the pages before it. So does an answer that sends the search back to a page it already
read, with the postings read so far, its own included. Rerun the search to start again.

Each lookup is one request with a single attempt.
jobrake caches nothing it reads from Indeed.

## Measured

Indeed documents its language codes and none of the search behavior on this page.
The query syntax, the result order, the date behind `--max-age-hours`, and the 1,000-result cap
are what we observed on the mobile endpoint jobrake uses.
The editions are the country sites Indeed listed at <https://www.indeed.com/worldwide> on
2026-10-29, and its API answered HTTP 400 for the unlisted countries we tried.
On 2026-10-28, 1 of 100 hybrid postings was tagged Remote as well.
