# StepStone (`stepstone`)

jobrake queries [StepStone](https://www.stepstone.de)'s German job board through the undocumented
listings API used by its mobile app.

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

Search results omit job descriptions, so pass `--details` when you need full text.

## Options

StepStone covers Germany only: pass a German city or postal code to `--location` (defaulting to all
of Germany) and an optional `--radius` in kilometers (default 30 km). `--results` defaults to 100;
`--max-age-hours` filters by posting age. Run `jobrake stepstone search -h` for the full flag list.

### Place and radius

StepStone pads search results with listings outside your chosen radius and tags them in
`site_data.section` (`main` for matches inside the radius, `regionalExtended` for matches outside).
Filter on `site_data.section` if you want a strict radius:

```sh
jobrake stepstone search -q "data scientist" -l Mannheim -r 10 \
  | jq '[.[] | select(.site_data.section == "main")]'
```

### Remote

`--remote` maps to StepStone's "Nur Home-Office" filter for fully remote roles. When combined with
`--location`, StepStone still mixes in nationwide remote roles under `regionalExtended`.

## Fields

Search results include `title`, `company`, `locations`, dates, `language` (such as `de`),
`company_logo`, and StepStone's tags. Adding `--details` fetches each posting page for the
description, `employment_type`, and `company_url`. Every supported key is listed in the
[reference](../reference.md#fields-by-site).

- `--details` can shift `posted_at` and `date` slightly: the posting page timestamps when the ad
  went online, which can be hours after the search listing's timestamp.
- `locations` contains a single entry with StepStone's location text (for multi-city postings, all
  cities appear in that string). With `--details`, single-city postings also populate `city` and
  `region`.
- `site_data.labels` keeps StepStone's badges (`REMOTE`, `EASY_APPLY`, `NO_COVER_LETTER`, etc.).
  `REMOTE` indicates home-office eligibility, though not every eligible role includes the badge.
- Salary fields are omitted because StepStone's API only returns its own salary estimates.
- `apply_url` is omitted. `workplace_type` is also omitted because StepStone's home-office wording
  doesn't reliably distinguish hybrid from fully remote roles.
- `expires_at` is when StepStone expects to take the ad offline.

### Looking up known URLs

`jobrake stepstone postings` accepts short URLs (`https://www.stepstone.de/job/14569042`) or the
longer `--<id>-inline.html` form. Because it reads only the posting page, `site_data` (which only
comes from search results) is absent.
