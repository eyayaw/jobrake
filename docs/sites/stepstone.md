# StepStone (`stepstone`)

[StepStone](https://www.stepstone.de) is a German job board, and jobrake searches its postings in
Germany.

```sh
jobrake stepstone search -q "data scientist" -l Mannheim -n 20
jobrake stepstone search -q volkswirt -l 68159 -r 50 -a 168 -o stepstone.jsonl
jobrake stepstone search -q "data engineer" --remote --details
jobrake stepstone postings https://www.stepstone.de/job/14569042
```

`search` requires no option and returns postings in the order StepStone serves them.
`postings` fetches the postings you name, each by a record's `url`,
`https://www.stepstone.de/job/<id>`, or by the posting's longer address that ends in
`--<id>-inline.html`. Any other reference is an error, and nothing is fetched.
StepStone takes postings down over time, so the example above may be gone.
Use references from a recent search.
In [Python](../reference.md#python-api) the options are keyword arguments:
`scrape("stepstone", query="data scientist", location="Mannheim", details=True)`.

## Options

| Option                  | Value                                                       | Default        |
| ----------------------- | ----------------------------------------------------------- | -------------- |
| `--query`, `-q`         | a job title or keywords                                     | none           |
| `--location`, `-l`      | a German city or postal code, such as `Mannheim` or `68159` | all of Germany |
| `--radius`, `-r`        | kilometers around the location, 0 or more                   | 30             |
| `--results`, `-n`       | a positive integer                                          | 100            |
| `--max-age-hours`, `-a` | a positive integer                                          | no age limit   |
| `--remote`              | only postings StepStone lists as fully remote               | off            |
| `--details`, `-d`       | fetch each posting's page                                   | off            |

A posting must match every option given, except that StepStone mixes in postings outside the
radius, as below.
The [reference](../reference.md#options) has the rules every site shares.

`--radius` widens the search around `--location`. Without a location the search covers the whole
country.

StepStone mixes in postings outside the radius, so the results can exceed the radius's own matches.
Each record names its `section` in `site_data`: `main`, or `regionalExtended` for a match outside
the radius. To keep the radius's own matches, filter on it:

```sh
jobrake stepstone search -q "data scientist" -l Mannheim -r 10 \
  | jq '[.[] | select(.site_data.section == "main")]'
```

`--remote` keeps the postings StepStone lists as fully remote. With a location, it still
returns such postings from the rest of the country, marked `regionalExtended` in `site_data`.

## Fields

A search card carries `title`, `company`, `locations`, and `date`, and the details in the second
column. `--details` fetches each posting's page for the third.
[The record](../reference.md#the-record) describes every key.

| Key                 | From a search                                | With `--details`                      |
| ------------------- | -------------------------------------------- | ------------------------------------- |
| `url`               | `https://www.stepstone.de/job/<id>`          | the same                              |
| `locations`         | one place, named as StepStone writes it      | adds `city` and `region` for one city |
| `date`, `posted_at` | the day and time StepStone first dated it    | the day and time it went online       |
| `expires_at`        | the time StepStone expects to remove it      | the same, as the page gives it        |
| `language`          | a code such as `de`                          | the same                              |
| `company_logo`      | the logo's address, when StepStone gives one | the same                              |
| `site_data`         | `section` and `labels`                       | the same                              |
| `description`       | absent                                       | the ad text                           |
| `employment_type`   | absent                                       | a slug such as `full_time`            |
| `company_url`       | absent                                       | the employer's page, when given       |

The place's name holds every city of a posting open in several. The place adds `country_code`,
and `latitude` and `longitude` when StepStone gives them.
The page dates a posting to when it went online, which can be later than the card's `posted_at`,
so `--details` can move `posted_at` and `date`.

`site_data` carries the card's `section`, either `main` or `regionalExtended` for a match
outside the radius, and its `labels`, such as `REMOTE`, `EASY_APPLY`, and `NO_COVER_LETTER`.
`REMOTE` marks a posting that allows home office, though not every such posting carries it.

In a later run, `jobrake stepstone postings` takes a card's `url` and returns the record a search
with `--details` would, without `site_data`, which only a search card carries.

A record has no salary, because the range StepStone sends is its own estimate rather than the
employer's, and no application link.
It has no workplace type either, because a posting says only whether home office is possible, in
the same words for fully and partly remote roles.
`--remote` applies StepStone's own filter for fully remote postings, whose records also lack a
workplace type.

## Limits

A search reads StepStone's mobile listings API and pages through the results one request after
another, without pacing, and each request gets a single attempt.
A search stops at `--results`, at the last match, or at an empty page.
A failed request raises `Stopped` with the postings of the pages before it.
So does an empty page that comes before the number of matches StepStone reported,
because postings may have closed during the search and a rerun may find more.

`--details` and `jobrake stepstone postings` fetch each posting's page, one request per posting,
one at a time, which a cached posting skips.
jobrake [caches](../reference.md#configuration) each posting it fetched, for seven days by default.
A posting whose page answers 404 or 410 is gone: a search keeps its card, and `postings` reports it.
A posting whose page could not be fetched also keeps its card, and the search raises
[`Stopped`](../reference.md#stopped) with the URLs to retry through `postings`.

## Measured

StepStone does not document its mobile listings API.
`--remote` sends the filter behind the website's "Nur Home-Office" switch,
which the listings API applied as well on 2026-11-15.
On 11 postings compared, the page dated a posting up to 15 hours after its card.
