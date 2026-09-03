<div align="center">
  <picture>
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/eyayaw/jobrake/refs/heads/main/docs/assets/logo/jobrake-icon.svg">
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/eyayaw/jobrake/refs/heads/main/docs/assets/logo/jobrake-icon-dark.svg">
    <img alt="Jobrake logo—Rake" src="https://raw.githubusercontent.com/eyayaw/jobrake/refs/heads/main/docs/assets/logo/jobrake-icon.svg" height="100">
</picture>
</div>

# jobrake

___Scrape job postings together and heap them up.___

> Read it as "**job-rake**".
>
> Say it quick, you hear "**job break**"—a break from the search doomscroll. (^_~)
>
> _Did **Jo** show up? **Jo** hit the **brake**, too._

jobrake is a Python package and CLI tool for fetching job postings from LinkedIn and Indeed.

<table>
<tr>
<td valign="top" width="50%">

```sh
jobrake linkedin \
  --query "data scientist" \
  --location "amsterdam, netherlands" \
  --max-age 48 \
  --results 5 \
  --details
```

</td>
<td valign="top" width="50%">

```sh
jobrake indeed \
  -q "data scientist" \
  -l amsterdam -c netherlands \
  -r 100 \
  -a 48 \
  -n 5
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
```

The CLI writes JSON to stdout by default.
`--format | -f` selects JSON, JSONL, or CSV, and `--output | -o` writes to a file.
See [usage and output](https://github.com/eyayaw/jobrake/blob/main/docs/usage.md) for file formats, returned fields, custom fetchers, and piping.

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
| `indeed` | Mobile-app GraphQL API | Included in search results |
| `linkedin` | Login-free guest API | Optional, paced, and cached |

Indeed requires `country`. LinkedIn accepts either `location` or a geoId.
See [provider behavior](https://github.com/eyayaw/jobrake/blob/main/docs/providers.md) for geography, filters, pagination, rate limits, retries, and LinkedIn detail fetching.

## Credits

jobrake's Indeed GraphQL endpoint and LinkedIn guest-search approach are based on [python-jobspy](https://pypi.org/project/python-jobspy/). Huge thanks.

## Disclaimer

> [!WARNING]
> jobrake has no affiliation with LinkedIn or Indeed. Use it to find jobs, not to build datasets by scraping regularly.
Scraping may violate their terms of service, and either site may rate-limit or block your IP address.
You are responsible for checking and complying with their terms.
