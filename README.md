# jobrake

The job boards shed new postings every day. Bring a rake. 🍂

jobrake (read as "job-rake") is a minimal python package and CLI tool for scraping job postings from LinkedIn and Indeed.
Repeat searches are cheap: fetched LinkedIn descriptions are cached on disk, so a sweep that took 24 minutes reruns in 2.

> If your name happens to be Jo, read it again: **Jo-brake**—the brake on the job-board doomscroll.

<table>
<tr>
<td valign="top" width="50%">

```sh
jobrake --site linkedin \
  --search-term "data scientist" \
  --location "amsterdam, netherlands" \
  --radius 100 \
  --hours-old 48 \
  --results-wanted 5 \
  --fetch-description
```

</td>
<td valign="top" width="50%">

```sh
jobrake -s indeed \
  -q "data scientist" \
  -l amsterdam -c netherlands \
  -r 100 \
  -a 48 \
  -n 5 \
  -d # always on for indeed
```

</td>
</tr>
</table>

## Installation

Install from GitHub (not on PyPI) with [`uv`](https://github.com/astral-sh/uv):

```sh
uv add git+https://github.com/eyayaw/jobrake
# or, for the CLI alone:
uv tool install git+https://github.com/eyayaw/jobrake
```

## Usage

### CLI

```sh
jobrake --help
```

> [!TIP]
> Pipe it to [`jq`](https://github.com/jqlang/jq) to filter fields:
>
> ```sh
> jobrake -s indeed -q "data scientist" -c usa -n 2 | jq '.[] | [.date, .title, .company, .url] | @tsv'
>
> "2026-08-09\tMachine Learning Engineer\tComponentWise Solutions, Inc.\thttps://www.indeed.com/viewjob?jk=024b6af7590a3553"
> "2026-03-10\tMachine Learning Engineer - Special Projects\tApple\thttps://www.indeed.com/viewjob?jk=d82828ae66c7adf9"
> ```

### As a library

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
print(jobs)
# [{"id", "title", "company", "url", "location", "description", "date", "site"}, ...]
```

## Locations and countries

Each site has one **required geographic argument**.

- Indeed needs `country` to pick the edition it queries: a name like `germany`, not an ISO code like `de`.

- LinkedIn needs `location` and ignores `country`. Always make your place names unambiguous, e.g., "Amsterdam, North Holland, Netherlands". A location LinkedIn cannot resolve returns an empty result, with a warning.

The search radius (`--radius` in the cli) is in **kilometers** and defaults to 50.

## Supported job boards

| Site       | Mechanism                     | Notes                                                                                                      |
| ---------- | ----------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `indeed`   | Mobile-app GraphQL API (POST) | most reliable; full descriptions                                                                           |
| `linkedin` | Guest search API (HTML cards) | token-bucket pacing (short burst, then ~one request per 3s); optional per-job description fetch, cached on disk, see below |

<details>
<summary>Glassdoor</summary>
Unlike jobspy, jobrake does not support Glassdoor. At the time of writing, it was acquired by Indeed and largely serves the same inventory. If it is ever wanted, we could inject a TLS-impersonating fetcher (e.g. one wrapping curl_cffi) for its Cloudflare frontend, but it is not a priority. Raising a PR is welcome, including any other major job board.
</details>

### LinkedIn: Rate limiting and job descriptions

LinkedIn rate-limits each visitor (per IP): a few requests are allowed immediately, then roughly one every couple of seconds.
Search pages are limited more strictly than job-detail pages.

jobrake tracks this limit with its own token bucket and waits before every request until the next one is allowed.
This makes it as fast as the limit permits without triggering rate limiting. If a 429 slips through anyway, the request is retried once after the limit clears.

Full job descriptions are not included in search results; each one costs an extra request against the same limit. 
Use `--fetch-description | -d` in the CLI to include them.

Fetched descriptions are cached on disk for a week (in your user cache directory), so repeated runs only pay for postings they have not seen; a posting that is gone (404) is remembered and never refetched. Pass `--no-cache` (or `cache=False`) to bypass the cache.

Be gentle with the guest API. The cache makes repeats cheap, but the first fetch still costs one request per job: if you only want some of the jobs, list without `-d` and hydrate just the interesting ids with `linkedin.fetch_descriptions(fetcher, ids)`. It maps each id to its text, or to `None` when the posting is gone (404); an id that failed transiently is absent and safe to retry.

## Bring your own fetcher

Every scraper takes any `jobrake.fetchkit.Fetcher` via `fetcher=`; failures are returned as results, and no exceptions are thrown. A fetcher you pass in stays yours to close. Indeed needs the `PostFetcher` variant (JSON `post` on top of the GET-only protocol), which the default `HttpxFetcher` implements. Subclass `jobrake.fetchkit.BaseFetcher` to wrap another HTTP client or a browser.

## Credits

jobrake owes a lot to [python-jobspy](https://pypi.org/project/python-jobspy/): the Indeed mobile-app GraphQL endpoint, its public app key, and the LinkedIn guest-search approach were all adapted from it. Thanks.

## Disclaimer

> [!WARNING]
> Scraping these sites may violate their terms of service. This package is not affiliated with any site it scrapes; check their terms and decide for yourself whether your use complies.
