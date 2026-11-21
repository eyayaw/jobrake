# EconJobMarket (`econjobmarket`)

[EconJobMarket](https://econjobmarket.org) (EJM) is the job market site for economists:
academic positions, postdocs, pre-docs, and research jobs at central banks and consultancies.
jobrake reads EJM's public ad feed. A search returns every open ad:

```sh
jobrake econjobmarket search
jobrake econjobmarket search -o ejm.jsonl
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("econjobmarket"))
```

A search is one request. A failed request raises [`Stopped`](../reference.md#stopped) with an
empty `partial`.

## Options

A search takes no query, result limit, or filters, because EJM applies none.
To narrow the ads, pipe the results through `jq` or load them into another tool:

```sh
jobrake econjobmarket search \
  | jq -r '.[] | select(any(.locations[]; .country_code == "DE")) | [.expires_at, .company, .title] | @tsv'
```

## Fields

An EconJobMarket [record](../reference.md#the-record) carries `title`, `company`, `locations`,
`date`, and `description`, and the details `posted_at`, `expires_at`, `company_logo`, `site_data`,
and, when present, `department`.

- `company` is the hiring institution, such as `University of Zurich`.
  `company_logo` links to its logo on EJM.
- `posted_at` is the ad's start date on EJM, and `date` is the same day.
  Both are calendar dates without a time.
- `expires_at` is the application deadline.
  In our read of the feed's 319 ads on 2026-10-28, 7 were still open after their deadline.
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

## Terms

EJM offers the feed "for personal use and for academic research projects".
To redisplay EJM ads on your own website, you must notify EJM and get EJM's approval first.
Any use of the feed must follow EJM's Terms of Use, Privacy Policy, and Research Data Usage Policy.
See [Accessing the EJM Ad Feed](https://backend.econjobmarket.org/docs/ad-redisplay/Ad-Redisplay.0.md).
