# Indeed (`indeed`)

jobrake searches [Indeed](https://www.indeed.com) through Indeed's mobile GraphQL API.
Indeed does not document this API, so the search behavior on this page is what we measured.
Only its language codes have an Indeed reference.

```sh
jobrake indeed search -q "data scientist" -c nl -l Amsterdam -n 2
jobrake indeed search -q "data analyst" -c gb -l London -n 5 -a 24 -o jobs.jsonl
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("indeed", query="economist", country="us", attributes=["CF3CP"]))
```

Indeed returns the details it has with the search itself, so an Indeed search takes no `--details`,
and the site has no `postings` command.

## Options

| Option                  | Value                                                 | Default           |
| ----------------------- | ----------------------------------------------------- | ----------------- |
| `--query`, `-q`         | a job title or keywords                               | none              |
| `--country`, `-c`       | a country code                                        | required          |
| `--location`, `-l`      | a city or another place within that country           | the whole edition |
| `--radius`, `-r`        | kilometers around the location                        | 40                |
| `--results`, `-n`       | the number of postings to return                      | 10                |
| `--max-age-hours`, `-a` | the oldest posting to keep, in hours                  | no age limit      |
| `--company-ids`         | one Indeed employer key                               | every employer    |
| `--language`            | a language code                                       | every language    |
| `--attributes`          | attribute codes, all of which a posting must carry    | none              |
| `--remote`              | keep only postings Indeed tags Remote                 | off               |

### Country and location

Indeed searches one country edition at a time, so `--country` is required.
Set it to the country's ISO 3166-1 alpha-2 code in either case, such as `de`, `gb`, or `us`.
A code with no Indeed edition is an error that lists the codes Indeed serves.
The editions are the country sites Indeed listed at <https://www.indeed.com/worldwide> on
2026-10-29, and its API answered HTTP 400 for the unlisted countries we tried.

`--location` narrows that edition to a city or another place within it,
and [`jobrake indeed places`](#lookups) suggests the names Indeed knows.
Without `--location`, the search covers the whole edition and sends no radius.

### Query

jobrake sends the query unchanged to Indeed's `what` field.
Indeed matches loosely, so a returned posting need not contain every word you typed.
Where that matters, run several narrow queries and filter the results yourself.

Indeed's mobile API treats `title:` and `company:` as field restrictions.
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

Indeed returns postings newest first by the date the posting reached Indeed,
the same date `--max-age-hours` filters on.
A posting inside your age window can still carry an older `posted_at`,
the publication timestamp the search returns.
A reposted posting counts as new, so a 24-hour window can include postings published weeks earlier.

### Employers

Find an Indeed employer key by looking up the company name with
[`jobrake indeed companies`](#lookups), then pass it to `--company-ids`:

```sh
jobrake indeed search -c nl -q "data scientist" --company-ids 8e8f030e53ea29e4
jobrake indeed search -c nl --company-ids 8e8f030e53ea29e4
```

This key selects _Booking.com_. Without `-q`, the search covers its postings without keywords.
Indeed intersects the keys it receives, so a search takes one employer key and rejects more.
Search one employer at a time and combine the results.

### Language

Use `--language CODE` to select Indeed postings in one language:

```sh
jobrake indeed search -q econometrics -c nl --language en
```

Indeed decides each posting's language.
The option accepts two-letter language codes such as `EN` and `NL`.
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

Pass `--remote` to search postings that Indeed tags Remote:

```sh
jobrake indeed search -q "econometrics" -c us --remote
```

`--remote` is shorthand for `--attributes DSQF7`, so a posting must carry the Remote tag
and every other code you pass.
The tag reflects Indeed's classification.
Check the posting for residency and workplace requirements.

## Lookups

Each lookup requires `--country` and prints a JSON list of `{"id", "name"}` entries.
The `id` is the value a search takes.

`jobrake indeed places <name>` prints the edition's location suggestions, best match first.
Each `id` can be passed directly to `--location`.

`jobrake indeed companies <name>` pairs an employer key in `id` with a company name in `name`:

```sh
jobrake indeed companies "Booking" -c nl
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

Results follow Indeed's suggestion order and may include related companies.
Choose the employer whose postings you want.

`jobrake indeed attributes <query>` reads the first 100 postings that match a job title or
keywords and prints their attribute codes, as `id` and `name`.
It applies no posting-age restriction.
Those postings carry several (hundred) attributes between them.
Search the list by label:

```sh
jobrake indeed attributes -c us "data scientist" \
  | jq -r '.[] | select(.name | test("python"; "i")) | [.id, .name] | @tsv'
# X62BT	Python
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

An Indeed [record](../reference.md#the-record) carries `title`, `company`, `locations`, and
`date`, and, when Indeed supplies them, `description` and the details `posted_at`, `expires_at`,
`language`, `employment_type`, `workplace_type`, `apply_url`, `company_url`, `company_logo`,
`salary_min`, `salary_max`, `salary_currency`, and `salary_period`.

- `id` is Indeed's job key, and `url` opens the posting on the country edition searched.
- `locations` holds one place with the `city`, `region`, `country_code`, `latitude`,
  and `longitude` Indeed gives, named from those parts.
- `posted_at` is the time the posting was published, and `date` is its calendar date.
  `--max-age-hours` filters on another date, as [Posting age](#posting-age) says.
- `language` is Indeed's two-letter code, and Indeed also sends the legacy codes `iw` for Hebrew
  and `in` for Indonesian, which jobrake preserves.
- `employment_type` comes from the posting's attribute labels, as a slug such as `full_time`.
  It is one of `full_time`, `part_time`, `contract`, `temporary`, `internship`, or `per_diem`.
- `workplace_type` is `remote` for a posting tagged Remote
  and `hybrid` for one tagged Hybrid work, whose code is `PAXZC`.
  Indeed tags some postings both, and such a posting has no `workplace_type`.
  On 2026-10-28, 1 of 100 hybrid postings carried both tags.
- The salary fields hold the range Indeed gives with its currency and period.
  A posting with one exact figure carries it as both bounds,
  and a posting with only a minimum or only a maximum carries that bound alone.
- `apply_url` is the application link Indeed gives,
  and `company_url` is the employer's page on Indeed.

## Requests

One search reaches at most 1,000 results, and jobrake warns when that cap cuts a search short.

Pages follow one another without delay, and each request gets a single attempt.
A failed request raises [`Stopped`](../reference.md#stopped) with the postings of the pages before
it, and a page that repeats an earlier page's cursor raises it with the postings read so far, its
own included.
Each lookup is one request.
