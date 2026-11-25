<div align="center">
  <picture>
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/eyayaw/jobrake/refs/heads/main/docs/assets/logo/svg/jobrake-stacked-color.svg">
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/eyayaw/jobrake/refs/heads/main/docs/assets/logo/svg/jobrake-stacked-dark.svg">
    <img alt="jobrake" src="https://raw.githubusercontent.com/eyayaw/jobrake/refs/heads/main/docs/assets/logo/svg/jobrake-stacked-color.svg" width="240">
  </picture>
</div>

___The job boards shed new postings every day. Bring a rake.___

jobrake is a Python package and CLI tool for fetching job postings from LinkedIn, Indeed, StepStone,
and [many more boards](#supported-job-boards), including academic and UN listings and employers' own
boards on major ATSs.
It returns each posting with the [same fields](https://github.com/eyayaw/jobrake/blob/main/docs/reference.md#the-record),
whichever site it came from.

> Read it as "**job-rake**".
>
> Say it quickly and you hear "**job break**"—a break from the search doomscroll. (^_~)
>
> _Did **Jo** show up? **Jo** hit the **brake**, too._

<table>
<tr>
<td valign="top" width="50%">

```sh
jobrake linkedin search \
  --query economist \
  --location Germany \
  --results 1 \
  --details
```

</td>
<td valign="top" width="50%">

```sh
jobrake greenhouse search \
  --board anthropic
```
</td>
</tr>
</table>

The LinkedIn search above returns something like this, with its description and logo URL shortened:

```json
[
  {
    "site": "linkedin",
    "id": "4491606986",
    "url": "https://de.linkedin.com/jobs/view/senior-researcher-f-m-x-health-economics-at-wifor-institute-4491606986",
    "title": "Senior Researcher (f/m/x) Health Economics",
    "company": "WifOR Institute",
    "locations": [
      {
        "name": "Darmstadt, Hesse, Germany",
        "city": "Darmstadt",
        "country_code": "DE",
        "latitude": 49.87245,
        "longitude": 8.6510105
      }
    ],
    "date": "2026-11-19",
    "description": "Dein zukünftiger Job?\nUnsere Business Unit Health Economics erforscht ...",
    "company_url": "https://de.linkedin.com/company/wifor",
    "company_logo": "https://media.licdn.com/dms/image/v2/C4D0BAQHzEHqMu92Yew/company-logo_200_200/...",
    "employment_type": "full_time",
    "posted_at": "2026-11-19T14:10:11.000Z",
    "expires_at": "2027-11-19T14:10:11.000Z",
    "apply_type": "offsite",
    "applicants": 25,
    "education": "bachelor degree"
  }
]
```

Every key is in the [reference](https://github.com/eyayaw/jobrake/blob/main/docs/reference.md#the-record).

## Installation

jobrake is not on PyPI, so install it from GitHub with [`uv`](https://github.com/astral-sh/uv):

```sh
# Try it without installing
uvx --from git+https://github.com/eyayaw/jobrake jobrake -h
# Install as a CLI tool
uv tool install git+https://github.com/eyayaw/jobrake
# Add it to a project as a library
uv add git+https://github.com/eyayaw/jobrake
```

Releases before 1.0 can break the API, so please pin a tag in a project:
`uv add git+https://github.com/eyayaw/jobrake --tag <tag>`.
The [changelog](https://github.com/eyayaw/jobrake/blob/main/CHANGELOG.md) marks each breaking change.

## Usage

### CLI

Every command has the form `jobrake <site> <command>`, and `--help` at any level lists what comes next.
Each site has `search`. Some add `postings`, which fetches postings by URL or ID,
and lookups, which turn a name into the ID a search takes.

```sh
# LinkedIn ----
## Search, with details
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
# Use the geoId of the place directly (instead of location)
jobrake linkedin search -q "data scientist" -g 102011674 -n 2 # Amsterdam, Netherlands

# Indeed ----
## Search, details included
jobrake indeed search \
        -q "data analyst" \
        -c gb \
        -l "London" \
        -n 5 \
        -a 24 \
        -o jobs.jsonl
# Resolve place names
jobrake indeed places -c nl "amsterdam"

# StepStone ----
## Engineering jobs within 50 km of Munich
jobrake stepstone search -q Ingenieur -l München -r 50 -n 20 -d

# Greenhouse ----
## Every posting on one employer's board
jobrake greenhouse search -b airbnb -o airbnb.csv

# EconJobMarket ----
## Every open ad
jobrake econjobmarket search -o ejm.csv

# AEA JOE ----
## Labor economics listings posted this week
jobrake aea search --jel J --max-age-hours 168

# INOMICS ----
## Postdocs in Germany
jobrake inomics search -c de --category postdoc -d

# AcademicTransfer ----
## Scientific vacancies in economics, newest first
jobrake academictransfer search -q economics --vacancy-type scientific
```

Each site has its own options, which `--help` lists.
These options mean the same on every site that takes them:

| Option                  | Effect                                                                         |
| ----------------------- | ------------------------------------------------------------------------------ |
| `--query`, `-q`         | Job title or keywords                                                          |
| `--country`, `-c`       | A country's ISO 3166-1 code, alpha-2 or alpha-3, such as `de` or `deu`         |
| `--results`, `-n`       | The number of postings to return. The default is 10 on Indeed and LinkedIn, 20 on Workday, and 100 elsewhere |
| `--max-age-hours`, `-a` | Only postings this many hours old or newer. No age limit by default            |
| `--radius`, `-r`        | The search radius around `--location`, in kilometers                           |
| `--details`, `-d`       | Fetch each posting for the fields a search result lacks, such as the description |
| `--output`, `-o`        | Write a new file instead of stdout. An existing file is an error               |
| `--format`, `-f`        | `json`, `jsonl`, or `csv`. Defaults to the extension of `--output`, else JSON  |

A site without `--results` returns every posting that matches.

The default output is JSON, one array of records.
JSONL writes one record per line with the same keys.
CSV has the same columns for every site and leaves an absent value empty.
In CSV, `locations` joins the place names with `; ` and drops their parts, `keywords` joins the
keywords the same way, and `site_data` holds JSON.
A place name can itself contain `; `, such as Greenhouse's `Remote, Canada; Remote, United States`,
so read JSON or JSONL to count places.

### As a library

```python
import asyncio

from jobrake import scrape


async def main():
    return await scrape(
        "indeed",
        query="economist",
        country="de",
        results=3,
    )


for job in asyncio.run(main()):
    print(job["date"], job["title"], "|", job["company"])
```

```text
2026-11-11 Senior Economist - Research | The European Central Bank
2026-09-15 Economist (m/w/d) – Economic Consulting | Oxford Economics
2026-11-02 Economist (ESCB/IO) - EU Institutions and Fora | The European Central Bank
```

`scrape` takes the same options as the CLI, as keyword arguments with underscores, and checks
them before any request. A failed request raises `jobrake.Stopped`, whose `partial` holds the
postings collected until then.
To [recover from `Stopped`](https://github.com/eyayaw/jobrake/blob/main/docs/guide.md#recover-from-a-stopped-search)
or [fetch details later](https://github.com/eyayaw/jobrake/blob/main/docs/guide.md#fetch-known-postings), see the guide.
See the [reference](https://github.com/eyayaw/jobrake/blob/main/docs/reference.md#python-api) for every function.

## Supported job boards

| Site | Search | Posting details | Requires |
| --- | --- | --- | --- |
| <a href="https://www.academictransfer.com"><img src="https://www.academictransfer.com/favicon.ico" alt="" height="16"></a> <a href="https://github.com/eyayaw/jobrake/blob/main/docs/sites/academictransfer.md">`academictransfer`</a> | The jobs page's list API, Dutch academic and research vacancies | Included in search results | — |
| <a href="https://www.aeaweb.org/joe/listings"><img src="https://www.aeaweb.org/favicon.ico" alt="" height="16"></a> <a href="https://github.com/eyayaw/jobrake/blob/main/docs/sites/aea.md">`aea`</a> | JOE listings page and its XML export, every active listing | Included in search results | — |
| <a href="https://www.ashbyhq.com"><img src="https://www.ashbyhq.com/favicon.png" alt="" height="16"></a> <a href="https://github.com/eyayaw/jobrake/blob/main/docs/sites/ashby.md">`ashby`</a> | Public Job Posting API, one employer's board | Included in search results | `--board` |
| <a href="https://www.cornerstoneondemand.com"><img src="https://www.cornerstoneondemand.com/favicon.ico" alt="" height="16"></a> <a href="https://github.com/eyayaw/jobrake/blob/main/docs/sites/cornerstone.md">`cornerstone`</a> | Career site search API, one employer's career site | Included in search results | `--board`, the career site URL |
| <a href="https://econjobmarket.org"><img src="https://econjobmarket.org/images/ejm_logo.png" alt="" height="16"></a> <a href="https://github.com/eyayaw/jobrake/blob/main/docs/sites/econjobmarket.md">`econjobmarket`</a> | Public ad feed, every open ad | Included in search results | — |
| <a href="https://www.greenhouse.com"><img src="https://cdn.simpleicons.org/greenhouse" alt="" height="16"></a> <a href="https://github.com/eyayaw/jobrake/blob/main/docs/sites/greenhouse.md">`greenhouse`</a> | Public Job Board API, one employer's board | Included in search results | `--board` |
| <a href="https://www.indeed.com"><picture><source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/eyayaw/jobrake/refs/heads/main/docs/assets/sites/indeed-light.svg"><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/eyayaw/jobrake/refs/heads/main/docs/assets/sites/indeed-dark.svg"><img src="https://raw.githubusercontent.com/eyayaw/jobrake/refs/heads/main/docs/assets/sites/indeed-light.svg" alt="" height="16"></picture></a> <a href="https://github.com/eyayaw/jobrake/blob/main/docs/sites/indeed.md">`indeed`</a> | Mobile-app GraphQL API | Included in search results | `--country` |
| <a href="https://inomics.com"><img src="https://inomics.com/themes/custom/venice/images/favicons/inomics_favicon.ico" alt="" height="16"></a> <a href="https://github.com/eyayaw/jobrake/blob/main/docs/sites/inomics.md">`inomics`</a> | The search page's results endpoint, jobs for economists | Optional and cached, one request per posting | — |
| <a href="https://www.lever.co"><img src="https://www.lever.co/images/favicon-lever.png" alt="" height="16"></a> <a href="https://github.com/eyayaw/jobrake/blob/main/docs/sites/lever.md">`lever`</a> | Public Postings API, one employer's board | Included in search results | `--board` |
| <a href="https://www.linkedin.com/jobs"><picture><source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/eyayaw/jobrake/refs/heads/main/docs/assets/sites/linkedin-light.svg"><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/eyayaw/jobrake/refs/heads/main/docs/assets/sites/linkedin-dark.svg"><img src="https://raw.githubusercontent.com/eyayaw/jobrake/refs/heads/main/docs/assets/sites/linkedin-light.svg" alt="" height="16"></picture></a> <a href="https://github.com/eyayaw/jobrake/blob/main/docs/sites/linkedin.md">`linkedin`</a> | Login-free guest API | Optional, paced, and cached | `--location` or `--geoid` |
| <a href="https://www.personio.com"><img src="https://assets.cdn.personio.de/rebrand/favicon.svg" alt="" height="16"></a> <a href="https://github.com/eyayaw/jobrake/blob/main/docs/sites/personio.md">`personio`</a> | Public XML feed, one employer's career site | Included in search results | `--board` |
| <a href="https://reliefweb.int/jobs"><img src="https://reliefweb.int/themes/custom/common_design_subtheme/favicon.ico" alt="" height="16"></a> <a href="https://github.com/eyayaw/jobrake/blob/main/docs/sites/reliefweb.md">`reliefweb`</a> | Documented API, humanitarian and development postings | Included in search results | `JOBRAKE_RELIEFWEB_APPNAME` |
| <a href="https://www.smartrecruiters.com"><img src="https://www.smartrecruiters.com/wp-content/uploads/cropped-web-app-manifest-192x192-1-192x192.png" alt="" height="16"></a> <a href="https://github.com/eyayaw/jobrake/blob/main/docs/sites/smartrecruiters.md">`smartrecruiters`</a> | Public Posting API, one employer's board | Optional and cached, one request per posting | `--board` |
| <a href="https://www.stepstone.de"><img src="https://www.stepstone.de/favicon.ico" alt="" height="16"></a> <a href="https://github.com/eyayaw/jobrake/blob/main/docs/sites/stepstone.md">`stepstone`</a> | Mobile-app listings API, German job board | Optional and cached, one request per posting | — |
| <a href="https://careers.un.org"><img src="https://www.un.org/sites/un2.un.org/themes/bootstrap_un2/favicon.ico" alt="" height="16"></a> <a href="https://github.com/eyayaw/jobrake/blob/main/docs/sites/uncareers.md">`uncareers`</a> | Web app's list API, every UN Secretariat opening | Included in search results | — |
| <a href="https://www.workable.com"><img src="https://www.workable.com/static/apple-touch-icon.png" alt="" height="16"></a> <a href="https://github.com/eyayaw/jobrake/blob/main/docs/sites/workable.md">`workable`</a> | Public widget API, one employer's board | Included in search results | `--board` |
| <a href="https://www.workday.com"><img src="https://www.workday.com/favicon.ico" alt="" height="16"></a> <a href="https://github.com/eyayaw/jobrake/blob/main/docs/sites/workday.md">`workday`</a> | Career site JSON API, one employer's career site | Optional and cached, one request per posting | `--board`, the career site URL |
| <a href="https://www.xing.com"><img src="https://www.xing.com/favicon.ico" alt="" height="16"></a> <a href="https://github.com/eyayaw/jobrake/blob/main/docs/sites/xing.md">`xing`</a> | Mobile-app GraphQL API, German-speaking job market | Optional and cached, one request per posting | — |

On an employer-board site, `--board` takes the employer's token from the board's address,
such as `airbnb` in `boards.greenhouse.io/airbnb`, while Cornerstone and Workday take the career
site's address.

Glassdoor is not planned, as it is
[part of Indeed](https://web.archive.org/web/20260704043638/https://www.glassdoor.com/about/).
Neither is Wellfound, which has no public API and sits behind a Cloudflare challenge that only a browser passes.

## Requests and caching

jobrake paces its requests to two sites. It spaces out LinkedIn requests and retries one that
LinkedIn refuses with HTTP 429, and it waits 10 seconds before each request to AcademicTransfer's API.
It sends every other request without a pause and tries it once, so a failed request ends the
search with the postings collected so far.

jobrake caches the postings it fetches for **seven days**,
so a repeat run costs no request for them.
`JOBRAKE_CACHE_PATH` moves the cache and `JOBRAKE_CACHE_TTL` sets its lifetime
([configuration](https://github.com/eyayaw/jobrake/blob/main/docs/reference.md#configuration)).

> [!WARNING]
> LinkedIn answers posting pages with [HTTP 999](https://http.dev/999) from data center IPs, such as a Hetzner VPS.
> Searches still work there, but `--details` and `jobrake linkedin postings` return no details and exit 1.
> So use jobrake from the comfort of your home. :D

## Contributing

Issues and pull requests are welcome.
The layout and design rules are in [`AGENTS.md`](https://github.com/eyayaw/jobrake/blob/main/AGENTS.md).
Before a pull request, run `uvx prek run --all-files`, as CI does.

## Disclaimer

> [!WARNING]
> jobrake has no affiliation with any of the supported sites,
> and its authors are not liable for how you use it.
> We do not recommend using it to collect postings at scale or to republish them.
> Scraping may violate their ToS, and any of them may rate-limit or block your IP address.
> You are responsible for checking and complying with their terms:
> [AcademicTransfer](https://www.academictransfer.com/en/terms-conditions-privacy/),
> [AEA JOE](https://www.aeaweb.org/joe/listings),
> [Ashby](https://www.ashbyhq.com/resources/terms-and-policies),
> [Cornerstone](https://www.cornerstoneondemand.com/terms-of-use/),
> [EconJobMarket](https://backend.econjobmarket.org/docs/ad-redisplay/Ad-Redisplay.0.md),
> [Greenhouse](https://www.greenhouse.com/legal),
> [Indeed](https://www.indeed.com/legal),
> [INOMICS](https://inomics.com/terms-and-conditions),
> [Lever](https://www.lever.co/legal),
> [LinkedIn](https://www.linkedin.com/legal/user-agreement),
> [Personio](https://www.personio.com/terms/),
> [ReliefWeb](https://reliefweb.int/terms-conditions),
> [SmartRecruiters](https://www.smartrecruiters.com/legal/terms-of-use/),
> [StepStone](https://www.stepstone.de/ueber-stepstone/general-terms-of-use-from-april-27th-2022/),
> [UN Careers](https://www.un.org/en/about-us/terms-of-use),
> [Workable](https://www.workable.com/terms),
> [Workday](https://www.workday.com/en-us/legal/site-terms.html), and
> [XING](https://www.xing.com/terms).

---

jobrake's Indeed and LinkedIn searches were inspired by
[python-jobspy](https://pypi.org/project/python-jobspy/). Huge thanks.
