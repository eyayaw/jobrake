# StepStone (`stepstone`)

jobrake searches [StepStone](https://www.stepstone.de)'s German job board through the listings API
of StepStone's mobile app. StepStone does not document that API, so what we say here about its
behavior comes from our own tests.

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

StepStone's search results leave out the description, so add `--details` when you want it.

## Options

| Option                  | Value                                                       | Default        |
| ----------------------- | ----------------------------------------------------------- | -------------- |
| `--query`, `-q`         | a job title or keywords                                     | none           |
| `--location`, `-l`      | a German city or postal code, such as `Mannheim` or `68159` | all of Germany |
| `--radius`, `-r`        | kilometers around the location                              | 30             |
| `--results`, `-n`       | the number of postings to return                            | 100            |
| `--max-age-hours`, `-a` | the oldest posting to keep, in hours                        | no age limit   |
| `--remote`              | keep only the postings StepStone lists as fully remote      | off            |
| `--details`, `-d`       | fetch each posting's page                                   | off            |

### Place and radius

StepStone mixes in postings from outside the radius, so a search can return more than the radius holds.
It marks them in `site_data.section`: `main` for a match inside the radius and `regionalExtended` for one outside it.
To keep only the matches inside, filter on it:

```sh
jobrake stepstone search -q "data scientist" -l Mannheim -r 10 \
  | jq '[.[] | select(.site_data.section == "main")]'
```

### Remote

`--remote` applies the filter behind the website's "Nur Home-Office" switch,
which the listings API honored in our tests on 2026-11-15. With a location,
it also brings fully remote postings from the rest of the country, marked `regionalExtended`.

## Fields

A search gives you each posting's `title`, `company`, `locations`, and dates, its language
(a code such as `de`), the company logo, and StepStone's labels.
`--details` adds the description, the employment type, and the company's link from each
posting's page ([every key](../reference.md#fields-by-site)).

- `--details` can move `posted_at` and `date`. The page dates a posting to when it went online,
  which in our tests was up to 15 hours after the search result's `posted_at`.
- `locations` holds one place, named as StepStone writes it. For a posting open in several
  cities, that name lists them all. With `--details`, a posting in one city also gets its `city` and `region`.
- `site_data.labels` holds StepStone's labels, such as `REMOTE`, `EASY_APPLY`, and
  `NO_COVER_LETTER`. `REMOTE` marks a posting that allows home office, but not every such posting carries it.
- StepStone sends a salary range, but the range is StepStone's own estimate, not the employer's figure, so jobrake leaves it out.
- A record has no application link and no workplace type. A posting only says whether home office
  is possible, in the same words for a fully and a partly remote role.
- `expires_at` is when StepStone expects to take the posting down.

### Postings you already know

`jobrake stepstone postings` fetches postings by URL: a search result's `url`, such as
`https://www.stepstone.de/job/14569042`, or the longer address that ends in `--<id>-inline.html`.
You get what a `--details` search would give, except `site_data`, which only a search result carries.

## Requests

If a search page fails, the search stops with the postings it has, and `scrape`
raises [`Stopped`](../reference.md#stopped) with them in `partial`.
It also stops when StepStone sends an empty page before the number of matches it reported.
Postings may have closed during the search and shifted the pages, so a rerun may find the ones it skipped.

With `--details`, a posting that StepStone has taken down (HTTP 404 or 410), or that jobrake could
not fetch, keeps what its search result had.
