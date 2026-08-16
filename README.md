# jobrake

The job boards shed new postings every day. Bring a rake. 🍂

<table>
<tr>
<td valign="top" width="55%">
<blockquote>
Read it as "<b>job-rake</b>". Say it fast and it is "<b>job break</b>". (^_~)
<br><br>
And if your name happens to be Jo, read it again: <b>Jo-brake</b>—the brake on the job-board doomscroll.
</blockquote>
</td>
<td valign="top">
<pre>
⠀⠀⠀⠀⠀⢠⣤⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⢻⣿⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⢻⣷⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⢿⣷⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠈⢿⣷⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⣿⣇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⣿⡆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢹⡿⠄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢠⣶⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠻⠿⠀⠀⠀⠀⠀⢀⣀⣀⣀⣤⣤⣤⡀⠀⠀
⠀⠀⠀⠀⠀⠀⣀⣀⣀⣠⣤⣤⣤⣶⣶⣶⣾⣿⣿⠿⣿⣿⠛⢻⣿⡋⢻⣷⠀⠀
⠀⢰⣾⣿⣿⣿⡿⠿⣿⣿⠛⢻⣯⠉⢻⣿⠀⠘⣿⠀⠘⣿⡄⠀⢿⡇⠀⢿⡇⠀
⠀⠈⢻⣇⠀⢹⣿⠀⠘⣿⡀⠘⣿⠀⠀⢿⡄⠀⢹⠀⠀⢹⡇⠀⠘⠇⠀⠘⠃⠀
⠀⠀⠀⢿⠀⠀⢿⠀⠀⠹⠇⠀⠙⠀⠀⠈⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠈⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
</pre>
</td>
</tr>
</table>

jobrake is a minimal python package and CLI tool for scraping job postings from LinkedIn and Indeed.

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
  --detail
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
> "2026-08-15\tApplied AI/Machine Learning Engineer\tOddball\thttps://www.indeed.com/viewjob?jk=c674b457443cf940"
> "2026-08-15\tSenior Data Scientist - Machine Learning\tGeneral Dynamics Information Technology\thttps://www.indeed.com/viewjob?jk=e422bd4de2737ee7"
> ```

Or write directly to a file with `--output | -o`; the extension determines the format: use `-o jobs.csv` for CSV, and `-o jobs.json` or `-o jobs.jsonl` for JSON.

> [!TIP]
> `-o` replaces the file, so give each run its own; jsonl files then merge with a plain `cat`:
>
> ```sh
> jobrake ... -o runs/2026-08-10.jsonl   # Monday's run
> jobrake ... -o runs/2026-08-11.jsonl   # Tuesday's run
> cat runs/*.jsonl | jq ...              # merge them
> ```

### As a library

```python
from jobrake import scrape

jobs = await scrape(
    "indeed",
    search_term="economist",
    country="usa",
    results_wanted=25,
    hours_old=168,
)
print(jobs)
# [{"site", "id", "url", "title", "company", "location", "date", "description", ...}, ...]
```

Every job posting uses the same flat dict structure, regardless of the site or selected flags.
The `site`, `id`, and `url` fields uniquely identify the posting.
The `title`, `company`, `location`, and `date` fields are extracted from every search result. Missing values are represented by `""`.
The rest of the fields, `description` and detail fields such as `salary_min`, `employment_type`, and `applicants`, are retrieved from the posting itself. Missing attributes get `None`.
All fields have the same meaning across sites. Indeed includes the detail fields in the search response, whereas LinkedIn requires the `--detail | -d` flag.

`scrape` creates and closes its own fetcher on every call. Pass your own to reuse one session across searches, or to set timeouts, headers, or cookies.

```python
from jobrake.fetchkit import HttpxFetcher

fetcher = HttpxFetcher(timeout=30)
nl = await scrape("linkedin", ..., fetcher=fetcher)
us = await scrape("indeed", ..., fetcher=fetcher)
await fetcher.close() # you own the fetcher
```

To create a custom fetcher, e.g., around another HTTP client or a browser, subclass `jobrake.fetchkit.BaseFetcher`. Note that failures always come back as results: a failed request costs that page, and the run continues.

## Locations and countries

Each site has one **required geographic argument**.

- Indeed needs `country` to pick the edition it queries: a name like `germany`, not an ISO code like `de`.

- LinkedIn needs `location` and ignores `country`. Always make your place names unambiguous, e.g., "Amsterdam, North Holland, Netherlands". A location LinkedIn cannot resolve returns an empty result, with a warning.

The search radius (`--radius` in the cli) is in **kilometers** and defaults to 50. `--hours-old` defaults to 24: postings older than a day are filtered unless you widen it (e.g., `-a 168` for a week). See other defaults in [defaults.py](src/jobrake/defaults.py).

## Supported job boards

| Site       | Mechanism                     | Notes                                                                                                      |
| ---------- | ----------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `indeed`   | Mobile-app GraphQL API (POST) | fast and reliable; full descriptions and detail in the search response                                     |
| `linkedin` | Guest search API (HTML cards) | token-bucket pacing (short burst, then ~one request per 3s); optional per-job detail fetch, cached on disk |

<details>
<summary>Glassdoor</summary>
Unlike jobspy, jobrake does not support Glassdoor. Since July 1, 2026, it is <a href="https://web.archive.org/web/20260704043638/https://www.glassdoor.com/about/">part of Indeed</a> and likely serves the same inventory. It is not a priority, but a PR is welcome—for Glassdoor or any other major job board.
</details>

### LinkedIn: Rate limiting and posting detail

LinkedIn rate-limits each visitor, per IP. A few requests may burst immediately, then roughly one every couple of seconds. Search pages are limited more strictly than job-detail pages.

jobrake tracks this budget with its own token bucket and waits before every request until the next one is allowed.
This makes it as fast as the server permits without triggering 429s. If a request is limited anyway, it is retried once after the limit clears.

We extract summary fields from the search results. The description and the rest of attributes live on the job's posting page, so this requires an extra request per job against the same rate limit. Use `--detail | -d` in the CLI to fetch these attributes.

Fetched postings are cached on disk for a week (see [`TTL`](src/jobrake/cache.py)) in your user cache directory, so repeated runs only pay for postings that have not been seen. A posting that is gone (404/410) is remembered and never refetched. Pass `--no-cache` (or `cache=False`) to bypass the cache.

I advise being gentle with the guest API. Detail fetches cost one paced request per job, so a long list takes its time by design. The cache makes repeats cheap. If you only want some of the jobs, list without `-d` and fetch just the interesting ones with `linkedin.fetch_postings(fetcher, urls)`. It maps each url to the posting's fields, or to `None` when the posting is gone (404/410); a url that failed transiently is absent and safe to retry.

## Credits

jobrake owes a lot to [python-jobspy](https://pypi.org/project/python-jobspy/): the Indeed mobile-app GraphQL endpoint, its public app key, and the LinkedIn guest-search approach were all adapted from it. Thanks.

## Disclaimer

> [!WARNING]
> Scraping these sites may violate their terms of service. This package is not affiliated with any site it scrapes; check their terms and decide for yourself whether your use complies.
