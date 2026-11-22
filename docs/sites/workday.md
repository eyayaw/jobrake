# Workday (`workday`)

jobrake searches one employer's career site on [Workday](https://www.workday.com) through the JSON
API behind it. Workday does not document that API, so what we say here comes from our tests on
NVIDIA's career site in October 2026 and on two more career sites, in different Workday data
centers, on 2026-11-14. Another employer's site may behave differently.

```sh
jobrake workday search -b https://zillow.wd5.myworkdayjobs.com/Zillow_Group_External -q analyst
jobrake workday search -b https://zillow.wd5.myworkdayjobs.com/Zillow_Group_External -n 100 -d -o zillow.jsonl
jobrake workday postings https://zillow.wd5.myworkdayjobs.com/Zillow_Group_External/job/Remote-USA/Applied-Scientist_P751481-1
```

```python
import asyncio

from jobrake import scrape

board = "https://zillow.wd5.myworkdayjobs.com/Zillow_Group_External"
jobs = asyncio.run(scrape("workday", board=board, query="analyst", details=True))
```

## Options

Workday has no board token. Pass `--board` the address of the employer's job search page,
copied from the browser, such as `https://zillow.wd5.myworkdayjobs.com/Zillow_Group_External`.
The address has the form `https://<tenant>.wd<n>.myworkdayjobs.com/<site>`, with or without a
language part such as `en-US` before the site name. A posting's address on the same site works too.
Some employers' sites live at `https://wd<n>.myworkdaysite.com/recruiting/<tenant>/<site>`, which works the same way.

A search returns 20 postings unless you raise `--results`.
Each employer defines its own Workday filters, such as job category or country,
so jobrake offers no location, remote, or age filter for Workday.

## Fields

A search result carries the posting's title, place, and date. `--details` adds the
description, the employment type, and `posted_at`, Workday's start date for the posting
([every key](../reference.md#fields-by-site)).

- `company` is always `None`, because Workday names only the employer's legal entity, such as `ZINC Zillow, Inc.`.
- A posting with several locations has an empty `locations` in a search, because the search result
  shows only their count, such as `2 Locations`. With `--details`, it holds the primary location
  and then the others, and the primary one gets its `country_code`.
- Without `--details`, `date` comes from Workday's label, such as "Posted 3 Days Ago", counted back
  from today in UTC. Workday counts from its own day, so this `date` can be a day late, and a
  posting labeled "Posted 30+ Days Ago" has none. With `--details`, `date` is Workday's start date.
- `id` joins the employer's Workday name and the requisition ID, as in `zillow:P751481-1`.
- A record has no salary, workplace type, or application link.

### Postings you already know

`jobrake workday postings` fetches postings by URL: a search result's `url` or the posting's
address copied from the browser. You get what a `--details` search would give.

## Requests

Workday reports at most 2,000 postings per search, and jobrake warns you when a search reaches
that. Narrow the search with `--query` to reach the rest.

If a page fails, the search stops with the postings it has, and `scrape`
raises [`Stopped`](../reference.md#stopped) with them in `partial`.
An empty page before the number Workday reported stops it as well: postings may have closed during
the search, so a rerun may find more.

With `--details`, a posting removed or withdrawn since the search, or one jobrake could not fetch,
keeps what its search result had.
