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
# [{"title", "company", "url", "location", "description", "date", "site"}, ...]
```

Each site has one required geographic argument: Indeed needs `country`—a name like `germany` or the alias `usa`, not an ISO code like `de`—to pick the edition it queries. LinkedIn needs `location` and ignores `country`. The search radius (`distance=`, `--radius` in the CLI) is in **kilometers** and defaults to 50.

jobrake also has a CLI:

```sh
jobrake --site indeed --search-term "Data Scientist" --location "Amsterdam" --country "Netherlands" --results-wanted 5 --hours-old 48
```
> [!TIP]
> Pipe it to [`jq`](https://github.com/jqlang/jq) to filter fields:
> ```sh
> jobrake -s indeed -q "data scientist" -c usa -n 2 | jq '.[] | {title, company, url, date}'
> ```

Unlike indeed, the scraper for linkedin does not return full descriptions by default, but you can enable this with `linkedin_fetch_description=True` or the `--fetch-description` flag in the CLI. The scraper may appear slow, as it makes an additional request for each job to fetch the description, which is slower and may lead to rate limits.


## Sites

| Site | Mechanism | Notes |
|---|---|---|
| `indeed` | Mobile-app GraphQL API (POST) | most reliable; full descriptions |
| `linkedin` | Guest search API (HTML cards) | ~5-request burst bucket; pages paced 3s apart; optional per-job description fetch (`linkedin_fetch_description=True`) |

Unlike jobspy, jobrake does not support Glassdoor. At the time of writing, it was acquired by Indeed and largely serves the same inventory. If it is ever wanted, we could inject a TLS-impersonating fetcher (e.g. one wrapping curl_cffi) for its Cloudflare frontend, but it is not a priority. Raising a PR is welcome.

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
