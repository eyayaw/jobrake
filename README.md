# jobrake

Rakes job postings off the boards into plain dicts.

jobrake is a minimal job posting scraper off of Indeed and LinkedIn, and it uses [fetchkit](https://github.com/eyayaw/fetchkit) for the transport and is async natively (httpx underneath).

jobrake returns plain python dicts, and is stripped down keeping only relevant posting attributes: no salary parsing, job types, and company metadata. Inspired by [python-jobspy](https://pypi.org/project/python-jobspy/), but does not depend on pandas, pydantic, tls-client, and requests.

```python
from jobrake import scrape

jobs = await scrape(
    "indeed",
    search_term="economist",
    location="United States",
    country="usa",
    results_wanted=25,
    hours_old=168,
)
# [{"title", "company", "url", "location", "description", "date", "site"}, ...]
```

## Sites

| Site | Mechanism | Notes |
|---|---|---|
| `indeed` | Mobile-app GraphQL API (POST) | most reliable; full descriptions |
| `linkedin` | Guest search API (HTML cards) | ~5-request burst bucket; pages paced 3s apart; optional per-job description fetch (`linkedin_fetch_description=True`) |

Unlike jobspy, jobrake does not support Glassdoor. At the time of writing, Indeed acquired it and largely serves the same inventory. If it is ever wanted, we could use fetchkit's `CffiFetcher` (TLS impersonation) for its Cloudflare frontend, but it is not a priority. Raising a PR is welcome.

## Transport injection

Every scraper takes any fetchkit fetcher via `fetcher=`; failures are returned as results, and no exceptions are thrown. An injected fetcher's lifecycle stays with the caller. Indeed requires a fetcher with a `post` method. At the moment, fetchkit's protocol is GET-only, so this package's `HttpxPostFetcher` (the default) adds one.

```python
from fetchkit import CffiFetcher
jobs = await scrape(
    "linkedin",
    search_term="economist",
    location="Amsterdam, Netherlands",
    fetcher=CffiFetcher()
)
```

## Disclaimer

> [!WARNING]
> Scraping these sites may violate their terms of service. This package is not affiliated with any site it scrapes; check their terms and decide for yourself whether your use complies.
