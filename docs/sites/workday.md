# Workday (`workday`)

jobrake searches one employer's career site on [Workday](https://www.workday.com) through the JSON
API behind it. Workday publishes no documentation for this API. The behavior described here was
measured on NVIDIA's career site in October 2026 and on two career sites in different Workday data
centers on 2026-11-14, and another employer's site may differ.

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

Workday has no board token. Pass `--board | -b` the address of the employer's job search page,
copied from the browser, such as `https://zillow.wd5.myworkdayjobs.com/Zillow_Group_External`.
The address has the form `https://<tenant>.wd<n>.myworkdayjobs.com/<site>`, with or without a
language part such as `en-US` before the site name. A posting's address on the same site works too.
Some employers' sites live at `https://wd<n>.myworkdaysite.com/recruiting/<tenant>/<site>`,
which works the same way.
An address jobrake cannot read stops before any request with an error that shows the expected form,
and a site name Workday does not know stops the search with an error that says so.

`--query | -q` is Workday's keyword search,
and `--results | -n` caps the postings returned, 20 by default.
Each employer defines its own Workday filters, such as job category or country,
so jobrake offers no location, remote, or age filter for Workday.

## Fields

A Workday [record](../reference.md#the-record) from a search carries `title`, `locations`, and
`date`, but no description.
`--details | -d` fetches each posting and adds `description`, `posted_at`, and `employment_type`,
and gives the primary place its `country_code`.

- `company` is always `None`. Workday names only the employer's legal entity,
  such as `ZINC Zillow, Inc.`.
- `locations` is empty for a posting with several locations,
  because a search result shows only their count, such as `2 Locations`.
  With `--details`, it holds the primary location and then the others, by name.
- Without `--details`, `date` comes from Workday's label:
  "Posted Today", "Posted Yesterday", or "Posted 3 Days Ago", counted back from today in UTC.
  Workday counts from its own day, so this `date` can be a day late.
  On one posting we fetched at 02:22 UTC, Workday said "Posted Today"
  and the posting's start date was the previous day.
  Workday stops counting at "Posted 30+ Days Ago", so an older posting has no `date`.
- `posted_at` is a calendar date, Workday's start date for the posting.
  With `--details`, `date` is `posted_at`.
- `id` joins the employer's Workday name and the requisition ID, as in `zillow:P751481-1`.

A Workday record has no salary, workplace type, or application link.

`jobrake workday postings` fetches postings you already know.
A reference is a search result's `url` or the posting's address copied from the browser,
and the result is the record a `--details` search would build.

## Requests

A search pages through the results one request after another, without pacing,
and each request gets a single attempt.
Workday reports at most 2,000 postings per search, and jobrake warns
when that cap cuts a search short.
Narrow the search with `--query` to reach the rest.
A failed request raises [`Stopped`](../reference.md#stopped) with the postings collected before it.
So does an empty page that comes before the number of postings Workday reported,
because postings may have closed during the search and a rerun may find more.

`--details` and `jobrake workday postings` fetch each posting with one request,
which a [cached](../reference.md#configuration) posting skips.
A posting removed or withdrawn since the search counts as gone.
