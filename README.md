<div align="center">
  <picture>
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/eyayaw/jobrake/refs/heads/main/docs/assets/logo/svg/jobrake-stacked-color.svg">
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/eyayaw/jobrake/refs/heads/main/docs/assets/logo/svg/jobrake-stacked-dark.svg">
    <img alt="jobrake" src="https://raw.githubusercontent.com/eyayaw/jobrake/refs/heads/main/docs/assets/logo/svg/jobrake-stacked-color.svg" width="240">
  </picture>
</div>

___Scrape job postings together and heap them up.___ Read the launch post [here](https://eyayaw.github.io/posts/jobrake-for-the-job/).

> Read it as "**job-rake**".
>
> Say it quickly and you hear "**job break**"—a break from the search doomscroll. (^_~)
>
> _Did **Jo** show up? **Jo** hit the **brake**, too._

jobrake is a Python package and CLI tool for fetching job postings from LinkedIn, Indeed, EconJobMarket, and employers' boards on six applicant tracking systems.

<table>
<tr>
<td valign="top" width="50%">

```sh
jobrake linkedin search \
  --query "data scientist" \
  --location "amsterdam, netherlands" \
  --max-age-hours 48 \
  --results 5 \
  --details
```

</td>
<td valign="top" width="50%">

```sh
jobrake indeed search \
  -q "data scientist" \
  -l amsterdam -c netherlands \
  -a 48 \
  -n 5 \
  --radius 100
```
</td>
</tr>
</table>

## Installation

jobrake is not on PyPI. Install it from GitHub with [`uv`](https://github.com/astral-sh/uv):

```sh
uv add git+https://github.com/eyayaw/jobrake
# Install as a CLI tool
uv tool install git+https://github.com/eyayaw/jobrake
```

## Usage

### CLI

```sh
jobrake -h

# LinkedIn ----
## Search
jobrake linkedin search \
        -q "research economist" \
        -l "London, England" \
        -n 5 \
        -a 24 \
        -d \
        -o jobs.csv

## Fetch details
# You can pass several urls/ids
jobrake linkedin postings \
        "https://uk.linkedin.com/jobs/view/senior-data-scientist-at-hm-treasury-4461975556"
        # or just 4461975556
## Resolve place names
jobrake linkedin places "amsterdam" # then use the display name in search
                                    # -l "Amsterdam, North Holland, Netherlands"
# Use the geoid of the place directly (instead of location)
jobrake linkedin search -q "data scientist" -g 102011674 -n 2 # Amsterdam, Netherlands

# Indeed ----
## Search and fetch details
jobrake indeed search \
        -q "data analyst" \
        -c "UK" \
        -l "London" \
        -n 5 \
        -a 24 \
        -o jobs.jsonl
# Resolve place names
jobrake indeed places -c netherlands "amsterdam"

# Greenhouse ----
## Every posting on one employer's board
jobrake greenhouse search -b airbnb -o airbnb.csv

# EconJobMarket ----
## Every open ad
jobrake econjobmarket search -o ejm.csv
```

The CLI writes JSON to stdout by default.
`--format | -f` selects JSON, JSONL, or CSV, and `--output | -o` writes to a file.
See the [guide](https://github.com/eyayaw/jobrake/blob/main/docs/guide.md#read-and-save-results) for file formats, returned fields, custom fetchers, and piping.

### As a library

```python
import asyncio

from jobrake import scrape


async def main():
    return await scrape(
        "indeed",
        query="economist",
        country="United States",
        results=2,
    )


jobs = asyncio.run(main())
```

## Supported job boards

| Site | Search | Posting details |
| --- | --- | --- |
| `ashby` | Public Job Posting API, one employer's board | Included in search results |
| `econjobmarket` | Public ad feed, every open ad | Included in search results |
| `greenhouse` | Public Job Board API, one employer's board | Included in search results |
| `indeed` | Mobile-app GraphQL API | Included in search results |
| `lever` | Public Postings API, one employer's board | Included in search results |
| `linkedin` | Login-free guest API | Optional, paced, and cached |
| `smartrecruiters` | Public Posting API, one employer's board | Search results only, without descriptions |
| `workable` | Public widget API, one employer's board | Included in search results |
| `workday` | Career site JSON API, one employer's career site | Search results only, without descriptions |

The sites that read one employer's board require `board`, the employer's board token, or for Workday the career site URL. Indeed requires `country`. LinkedIn accepts either `location` or a geoId.
See the [guide](https://github.com/eyayaw/jobrake/blob/main/docs/guide.md) for search queries, geography, filters, pagination, rate limits, retries, and LinkedIn detail fetching.

> [!WARNING]
> LinkedIn answers posting pages with [HTTP 999](https://http.dev/999) from data center IPs, such as a Hetzner VPS.
> Searches still work there, but `--details` and `jobrake linkedin postings` return no details. So use jobrake from the comfort of your home. :D

## Credits

jobrake's Indeed GraphQL endpoint and LinkedIn guest-search approach are based on [python-jobspy](https://pypi.org/project/python-jobspy/). Huge thanks.

## Disclaimer

> [!WARNING]
> jobrake has no affiliation with any of the [supported sites](#supported-job-boards). Use it to find jobs, not to build datasets by scraping regularly.
> Scraping may violate their terms of service, and any of them may rate-limit or block your IP address.
> EconJobMarket offers its ad feed for personal use and academic research, and redisplaying its ads on your own website needs EconJobMarket's approval.
> You are responsible for checking and complying with their terms.
