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

## Options

EJM's feed takes no query or filters, so jobrake offers none. Narrow the ads yourself, for example to Germany:

```sh
jobrake econjobmarket search \
  | jq -r '.[] | select(any(.locations[]; .country_code == "DE")) | [.expires_at, .company, .title] | @tsv'
```

## Fields

Each ad carries its full text, the institution and its logo, the places, the day it opened on EJM,
the application deadline, and the hiring department when the ad names one ([every key](../reference.md#fields-by-site)).
Candidates apply on EJM, at the ad's `url`, so a record has no separate application link.

- In our read of 2026-10-28, a few ads stayed in the feed past their deadline, so check `expires_at`.
- `posted_at` and `date` are the day the ad opened on EJM, without a time.
- An ad open to `All departments` has no `department`.
- `site_data` holds the ad's `position_types`, such as `Assistant Professor`, and its
  `categories`, fields such as `Econometrics`, each as a list.
- A place carries the city, region, country code, and coordinates the ad gives, such as
  `Boston, Massachusetts, US`. A few ads list no place, and their `locations` is empty.
- The feed carries no salary, employment type, or workplace type.

## Requests

One request reads the whole feed. If it fails, you get nothing, and `scrape` raises
[`Stopped`](../reference.md#stopped).

## Terms

EJM offers the feed "for personal use and for academic research projects".
To redisplay EJM ads on your own website, you must notify EJM and get its approval first.
Any use of the feed must follow EJM's Terms of Use, Privacy Policy, and Research Data Usage Policy.
See [Accessing the EJM Ad Feed](https://backend.econjobmarket.org/docs/ad-redisplay/Ad-Redisplay.0.md).
