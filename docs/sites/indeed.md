# Indeed (`indeed`)

jobrake searches [Indeed](https://www.indeed.com) through Indeed's mobile GraphQL API.
Indeed does not document that API, so what we say here about its behavior comes from our own tests,
save for its [language codes](https://docs.indeed.com/api/common/objects/LanguageCode).

```sh
jobrake indeed search -q "data scientist" -c nl -l Amsterdam -n 2
jobrake indeed search -q "data analyst" -c gb -l London -n 5 -a 24 -o jobs.jsonl
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("indeed", query="economist", country="us", attributes=["CF3CP"]))
```

Indeed sends the details it has with the search results, so there is no need for a `--details` flag.

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
Set it to the country's ISO 3166-1 alpha-2 code, such as `de`, `gb`, or `us`, case insensitive.
A code with no Indeed edition gives an error that lists the codes Indeed serves,
so `--country zz` is a quick way to see them.

`--location` narrows that edition to a city or another place within it,
and [`jobrake indeed places`](#lookups) suggests the names Indeed knows.
Leave `--location` out to search the whole country; `--radius` then has no effect.

### Query

jobrake sends the query unchanged to Indeed's `what` field.
Indeed matches loosely, so a returned posting may not contain every word you typed.
Where that matters, run several narrow queries and filter the results yourself.

Indeed's mobile API treats `title:` and `company:` as field restrictions.
Inside `title:`, parentheses for grouping terms and `OR` work.
Quotation marks narrow phrase searches, and a leading minus can exclude a term.
Note that these operators can be combined.

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

Indeed sorts postings by the date they reached Indeed, newest first,
and `--max-age-hours` counts from that date too.
A reposted posting counts as new, so a 24-hour search can return postings first published weeks
ago, and their `posted_at` shows that older date.
To keep only recently published postings, filter on `posted_at` yourself:

```sh
jobrake indeed search -q economist -c us -a 24 | jq '[.[] | select(.posted_at >= "2026-11-21")]'
```

### Employers

Find an Indeed employer key by looking up the company name with
[`jobrake indeed companies`](#lookups), then pass it to `--company-ids`:

```sh
jobrake indeed search -c nl -q "data scientist" --company-ids 8e8f030e53ea29e4
jobrake indeed search -c nl --company-ids 8e8f030e53ea29e4
```

This key selects _Booking.com_. Without `--query`, the search covers its postings without keywords.
Indeed intersects the keys it receives, so a search takes one employer key and rejects more.
Search one employer at a time and combine the results.

### Language

Use `--language CODE` to select Indeed postings in one language:

```sh
jobrake indeed search -q econometrics -c nl --language en
```

Indeed decides each posting's language. The option accepts two-letter language codes such as `EN` and `NL`.
The codes follow ISO 639-1, as Indeed's
[language-code reference](https://docs.indeed.com/api/common/objects/LanguageCode) lists them. A well-formed code can still match nothing.

### Attributes and remote work

`--attributes` takes the codes that [`jobrake indeed attributes`](#lookups) finds:

```sh
jobrake indeed search -q "data scientist" -c us --attributes X62BT
jobrake indeed search -q economist -c us --attributes CF3CP 6QC5F
```

`X62BT` selects Python. The second search requires both Full-time (`CF3CP`) and
Doctoral degree (`6QC5F`), because codes intersect: every returned posting carries every code you list.
To match any of several codes, run separate searches and combine the results.
A posting can hold codes that look mutually exclusive, so a Full-time match may carry
Part-time as well when the employer offers either arrangement. The filter has no way to exclude a code.

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
keywords and prints their attribute codes, as `id` and `name`. It applies no posting-age restriction.
Those postings carry several (hundred) attributes between them.
Search the list by label:

```sh
jobrake indeed attributes -c us "data scientist" \
  | jq -r '.[] | select(.name | test("python"; "i")) | [.id, .name] | @tsv'
# X62BT	Python
```

Each run samples the postings afresh, so a code can be missing from one lookup
and present in the next. Try the lookup again, or a related query, when a code you
expect does not appear. Labels can differ by country edition.
A label can also belong to several codes, and the lookup keeps each code separately.

The lookups are also functions, `places(fetcher, name, country=...)`,
`companies(fetcher, name, country=...)`, and `attributes(fetcher, query, country=...)` in `jobrake.sites.indeed`.

## Fields

Each search result comes with what Indeed has on the posting: the title, the company, the place
with its city, region, country code, and coordinates, the dates, and the description when Indeed has one.
You may also get the language, the employment and workplace type, the salary range, the
application link, and the employer's Indeed page and logo.
Every key is in the [reference](../reference.md#fields-by-site).

A few things about these fields may surprise you:

- `posted_at` is the posting's publication time, which can be weeks before the date
  Indeed sorts and filters by. See [Posting age](#posting-age).
- `employment_type` comes from the posting's attribute labels, as one of `full_time`,
  `part_time`, `contract`, `temporary`, `internship`, or `per_diem`.
- `workplace_type` is `remote` or `hybrid`, from Indeed's Remote and Hybrid work tags,
  whose codes are `DSQF7` and `PAXZC`.
  In our tests, Indeed rarely tagged a posting both, and such a posting has no `workplace_type`.
- A salary given as one figure fills both `salary_min` and `salary_max`,
  and a range open at one end fills only that end.
- `language` is Indeed's two-letter code. Indeed still uses the old codes `iw` for Hebrew
  and `in` for Indonesian, and jobrake keeps them.
- `id` is Indeed's job key, the `jk` in the posting's URL.

## Requests

Indeed gives one search 1,000 results at most, and jobrake warns you when a search reaches that.
Split a bigger search by place or by `--max-age-hours`.

If a request fails, or Indeed starts sending pages it already sent, the search stops with what it
has found: the CLI writes it and exits 1, and `scrape` raises [`Stopped`](../reference.md#stopped)
with it in `partial`. Wait a while and run the search again.
