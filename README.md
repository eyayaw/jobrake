# jobrake

Rakes job postings off the boards into plain dicts.

jobrake is a minimal job posting scraper off of Indeed and LinkedIn. It ships its own small fetch layer (`jobrake.fetchkit`) for the transport and is async natively (httpx underneath).

jobrake returns plain python dicts, and is stripped down keeping only relevant posting attributes: no salary parsing, job types, and company metadata. Inspired by [python-jobspy](https://pypi.org/project/python-jobspy/), but does not depend on pandas, pydantic, tls-client, and requests.

Install from GitHub (not on PyPI):

```sh
uv add git+https://github.com/eyayaw/jobrake
# or, for the CLI alone:
uv tool install git+https://github.com/eyayaw/jobrake
```

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
# [{"id", "title", "company", "url", "location", "description", "date", "site"}, ...]
```

Each site has one required geographic argument: Indeed needs `country`—a name like `germany` or the alias `usa`, not an ISO code like `de`—to pick the edition it queries. LinkedIn needs `location` and ignores `country`. Qualify ambiguous places ("Amsterdam, North Holland, Netherlands"): a location LinkedIn cannot resolve returns an empty result, with a warning. The search radius (`distance=`, `--radius` in the CLI) is in **kilometers** and defaults to 50.

jobrake also has a CLI:

```sh
jobrake --site indeed --search-term "Data Scientist" --location "Amsterdam" --country "Netherlands" --results-wanted 5 --hours-old 48
```
> [!TIP]
> Pipe it to [`jq`](https://github.com/jqlang/jq) to filter fields:
> ```sh
> jobrake -s indeed -q "data scientist" -c usa -n 2 | jq '.[] | {title, company, url, date}'
> ```

## Sites

| Site | Mechanism | Notes |
|---|---|---|
| `indeed` | Mobile-app GraphQL API (POST) | most reliable; full descriptions |
| `linkedin` | Guest search API (HTML cards) | token-bucket pacing (short burst, then ~one request per 2s); optional per-job description fetch, see below |

Unlike jobspy, jobrake does not support Glassdoor. At the time of writing, it was acquired by Indeed and largely serves the same inventory. If it is ever wanted, we could inject a TLS-impersonating fetcher (e.g. one wrapping curl_cffi) for its Cloudflare frontend, but it is not a priority. Raising a PR is welcome.

## LinkedIn pacing and descriptions

LinkedIn budgets each visitor's requests: a small burst, then a steady drip, with search pages metered more strictly than job-detail fragments. jobrake keeps its own copy of that budget (a token bucket, tuned to the strictest lane) and waits its turn before every request, so it goes as fast as the budget allows without getting rate-limited; a 429 that slips through anyway is retried once after the limit clears.

Descriptions are not in the search results—each one is an extra request against that budget. `linkedin_fetch_description=True` (`--fetch-description` in the CLI) fetches them for every job returned, every time. For repeated searches, list first and hydrate only what you haven't stored:

```python
from jobrake import HttpxFetcher, linkedin, scrape

fetcher = HttpxFetcher()
jobs = await scrape(
    "linkedin",
    search_term="economist",
    location="Berlin, Germany",
    fetcher=fetcher,
)
wanted = [j["id"] for j in jobs if j["id"] not in store]  # your store, your policy
descriptions = await linkedin.fetch_descriptions(fetcher, wanted)
```

`fetch_descriptions` maps each id to its text, to `None` when the posting is gone (404—prune it, stop asking), or omits it when the fetch failed transiently (retry whenever suits you). Descriptions never change after posting, so anything you store never goes stale.

## Transport injection

Every scraper takes any `jobrake.fetchkit.Fetcher` via `fetcher=`; failures are returned as results, and no exceptions are thrown. An injected fetcher's lifecycle stays with the caller. Indeed needs the `PostFetcher` variant (JSON `post` on top of the GET-only protocol), which the default `HttpxFetcher` implements. Subclass `jobrake.fetchkit.BaseFetcher` to wrap another HTTP client or a browser.

```python
from jobrake import HttpxFetcher
jobs = await scrape(
    "linkedin",
    search_term="economist",
    location="Amsterdam, Netherlands",
    fetcher=HttpxFetcher(headers={"Accept-Language": "en-US"}),
)
```

## Disclaimer

> [!WARNING]
> Scraping these sites may violate their terms of service. This package is not affiliated with any site it scrapes; check their terms and decide for yourself whether your use complies.
