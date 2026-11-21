# StepStone (`stepstone`)

jobrake searches [StepStone](https://www.stepstone.de)'s German site through StepStone's mobile
listings API, which StepStone does not document.

```sh
jobrake stepstone search -q "data scientist" -l Mannheim -n 20
jobrake stepstone search -q volkswirt -l 68159 -r 50 -a 168 -o stepstone.jsonl
jobrake stepstone search -q "data engineer" --remote --details
jobrake stepstone postings https://www.stepstone.de/job/14569042
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("stepstone", query="data scientist", location="Mannheim", details=True))
```

## Options

| Option                  | Value                                                  | Default        |
| ----------------------- | ------------------------------------------------------ | -------------- |
| `--query`, `-q`         | a job title or keywords                                | none           |
| `--location`, `-l`      | a German city or postal code, such as `Mannheim`       | all of Germany |
| `--radius`, `-r`        | kilometers around the location                         | 30             |
| `--results`, `-n`       | the number of postings to return                       | 100            |
| `--max-age-hours`, `-a` | the oldest posting to keep, in hours                   | no age limit   |
| `--remote`              | keep only the postings StepStone lists as fully remote | off            |
| `--details`, `-d`       | fetch each posting's page                              | off            |

`--location` also takes a postal code, such as `68159`, and `--radius` widens the search
around it.

StepStone mixes in postings outside the radius, so the results can exceed the radius's own matches.
`site_data.section` is `main` for a match inside the radius and `regionalExtended` for one outside
it. Filter on it to keep the matches inside:

```sh
jobrake stepstone search -q "data scientist" -l Mannheim -r 10 \
  | jq '[.[] | select(.site_data.section == "main")]'
```

`--remote` applies the filter behind the website's "Nur Home-Office" switch.
On 2026-11-15, the listings API honored it.
With a location, it still returns fully remote postings from the rest of the country,
marked `regionalExtended`.

## Fields

A StepStone search result carries `title`, `company`, `locations`, and `date`, and the
[details](../reference.md#the-record) `language`, `company_logo`, `posted_at`, `expires_at`, and
`site_data`. `--details | -d` fetches each posting's page and adds `description`,
`employment_type`, and `company_url`.

- `locations` holds one place, named as StepStone writes it, with every city of a posting open in
  several. It adds `country_code`, and `latitude` and `longitude` when StepStone gives them.
  With `--details`, a posting that names one city adds its `city` and `region`.
- `date` is the posting's calendar date, `posted_at` the time StepStone dates it, and `expires_at`
  the time StepStone expects to remove it. `language` is a code such as `de`.
  The page dates a posting to when it went online, up to 15 hours after the search result's
  `posted_at` on 11 postings compared, so `--details` can move `posted_at` and `date`.
- `url` opens the posting at `stepstone.de/job/<id>`.
- `site_data` carries the result's `section` and its `labels`, such as `REMOTE`, `EASY_APPLY`, and
  `NO_COVER_LETTER`. `REMOTE` marks a posting that allows home office, though not every such
  posting carries it.
- A record has no salary, because the range StepStone sends is its own estimate rather than the
  employer's figure, and no application link. It has no workplace type, because a posting states
  only whether home office is possible, in the same words for a fully and a partly remote role.

`jobrake stepstone postings` fetches postings you already know.
A reference is a search result's `url`, its `stepstone.de/job/<id>` page, or the posting's longer
address that ends in `--<id>-inline.html`.
It returns the record a `--details` search would, without `site_data`, which only a search
result carries.

## Requests

A search pages through the results one request after another, without pacing,
and each request gets a single attempt.
It stops at `--results`, at the last match, or at an empty page.
A failed request raises [`Stopped`](../reference.md#stopped) with the postings of the pages before
it. So does an empty page that comes before the number of matches StepStone reported,
because postings may have closed during the search and a rerun may find more.

`--details` and `jobrake stepstone postings` fetch each posting's page for its description,
one request per posting, which a [cached](../reference.md#configuration) posting skips.
A page that answers 404 or 410 counts as a posting gone.
