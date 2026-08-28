# jobrake

The job boards _shed new postings_ 🍂 every day. Bring a rake!

<table>
<tr>
<td valign="top" width="55%">
<blockquote>
Read it as "<b>job-rake</b>".
<br>
Say it fast and you hear "<b>job break</b>"—a break from the job-board doomscroll. (^_~)
<br><br>
Did <b>Jo</b> show up here? <b>Jo</b> hit the <b>brake</b>, too!
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

jobrake is a minimal Python package and CLI tool for scraping job postings from LinkedIn and Indeed.

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

jobrake is not on PyPI, install it from GitHub with [`uv`](https://github.com/astral-sh/uv):

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
See [usage and output](docs/usage.md) for file formats, returned fields, custom fetchers, and piping.

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

Indeed requires `country`. LinkedIn requires `location`.
See [provider behavior](docs/providers.md) for geography, filters, pagination, rate limits, retries, and LinkedIn detail fetching.

## Credits

jobrake is grateful for [python-jobspy](https://pypi.org/project/python-jobspy/). 
The Indeed mobile-app GraphQL endpoint, and the LinkedIn guest-search approach are taken from it. Thanks.

## Disclaimer

> [!WARNING]
> jobrake has no affiliation with LinkedIn or Indeed. Use it to find jobs, not to build datasets by scraping regularly. 
Scraping may violate their terms of service, and either site may rate-limit or block your IP address. 
You are responsible for checking and complying with their terms.
