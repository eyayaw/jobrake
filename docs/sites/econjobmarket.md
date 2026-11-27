# EconJobMarket (`econjobmarket`)

[EconJobMarket](https://econjobmarket.org) (EJM) lists academic positions, postdocs, pre-docs, and
research jobs for economists at universities, central banks, and consultancies. jobrake reads EJM's
public ad feed and returns every open ad:

```sh
jobrake econjobmarket search
jobrake econjobmarket search -o ejm.jsonl
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("econjobmarket"))
```

## Options

EJM's feed is a single unfiltered dump, so there are no search flags. Filter locally with `jq`, for
example to pull ads in Germany:

```sh
jobrake econjobmarket search \
  | jq -r '.[] | select(any(.locations[]; .country_code == "DE")) | [.expires_at, .company, .title] | @tsv'
```

## Fields

Every ad comes with its full text, institution name and logo, locations, opening date, deadline,
and department when listed (see [Fields by site](../reference.md#fields-by-site)). Applications go
through EJM at `url`, so `apply_url` isn't set; the feed also omits salary, employment type, and
workplace type.

- Ads occasionally stay in the feed past their closing date, so filter on `expires_at` if needed.
- `posted_at` and `date` give the day the ad opened on EJM (date only, no time).
- Ads marked `All departments` omit `department`.
- `site_data` includes `position_types` (e.g., `Assistant Professor`) and `categories` (e.g.,
  `Econometrics`) as lists.
- Locations include city, region, country code, and coordinates when provided (e.g.,
  `Boston, Massachusetts, US`); ads without a location have an empty `locations` list.

## Terms

EJM provides the feed "for personal use and for academic research projects." Redisplaying EJM ads on
your own site requires notifying EJM and getting approval first, and any use must comply with EJM's
Terms of Use, Privacy Policy, and Research Data Usage Policy. See
[Accessing the EJM Ad Feed](https://backend.econjobmarket.org/docs/ad-redisplay/Ad-Redisplay.0.md).
