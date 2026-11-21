# Workday (`workday`)

[Workday](https://www.workday.com) hosts the career sites of the employers that use it.
jobrake searches one employer's career site through the JSON API behind it.

```sh
jobrake workday search -b https://zillow.wd5.myworkdayjobs.com/Zillow_Group_External -q analyst
jobrake workday search -b https://zillow.wd5.myworkdayjobs.com/Zillow_Group_External -n 100 -d -o zillow.jsonl
jobrake workday postings https://zillow.wd5.myworkdayjobs.com/Zillow_Group_External/job/Remote-USA/Applied-Scientist_P751481-1
```

`search` returns the career site's postings in Workday's order, and `--board` is required.
`postings` fetches the postings you name, each by a record's `url` or by the posting's address
copied from the browser. Any other reference is an error, and nothing is fetched.
Employers take postings down over time, so the example above may be gone.
Use references from a recent search.
In Python the options are keyword arguments:
`scrape("workday", board="https://zillow.wd5.myworkdayjobs.com/Zillow_Group_External", query="analyst")`.

## Options

| Option            | Value                                     | Default  |
| ----------------- | ----------------------------------------- | -------- |
| `--board`, `-b`   | the address of the employer's career site | required |
| `--query`, `-q`   | keywords                                  | none     |
| `--results`, `-n` | a positive integer                        | 20       |
| `--details`, `-d` | fetch each posting                        | off      |

A Workday search applies a query on the server.
`--query | -q` is Workday's keyword search, and `--results | -n` caps the postings returned.
Each employer defines its own Workday filters, such as job category or country,
so jobrake offers no location, remote, or age filter for Workday.
The [reference](../reference.md#options) has the rules every site shares.

Workday has no board token. Pass the address of the employer's job search page instead,
copied from the browser, such as `https://zillow.wd5.myworkdayjobs.com/Zillow_Group_External`.
The address has the form `https://<tenant>.wd<n>.myworkdayjobs.com/<site>`, with or without a
language part such as `en-US` before the site name. A posting's address on the same site works too.
Some employers' sites live at `https://wd<n>.myworkdaysite.com/recruiting/<tenant>/<site>`,
which works the same way.
An address jobrake cannot read stops before any request with an error that shows the expected form,
and a site name Workday does not know stops the search with an error that says so.

## Fields

A Workday search result carries `title`, `locations`, and `date`, but no description.
`--details | -d` fetches each posting and adds `description`, `posted_at`, and `employment_type`,
and gives the primary place its `country_code`.
[The record](../reference.md#the-record) describes every key.

| Key               | From a search                          | With `--details`                     |
| ----------------- | -------------------------------------- | ------------------------------------ |
| `id`              | such as `zillow:P751481-1`             | the same                             |
| `company`         | always `None`                          | the same                             |
| `locations`       | one place by name, or none for several | the primary place, then the others   |
| `date`            | counted back from Workday's label      | `posted_at`                          |
| `posted_at`       | absent                                 | Workday's start date for the posting |
| `employment_type` | absent                                 | a slug such as `full_time`           |
| `description`     | absent                                 | the posting's text                   |

`id` joins the employer's Workday name and the requisition ID.
`company` is always `None`. Workday names only the employer's legal entity,
such as `ZINC Zillow, Inc.`.

`locations` is empty for a posting with several locations,
because a search result shows only their count, such as `2 Locations`.
With `--details`, it holds the primary location and then the others, by name.

Without `--details`, `date` comes from Workday's label:
"Posted Today", "Posted Yesterday", or "Posted 3 Days Ago", counted back from today in UTC.
Workday counts from its own day, so this `date` can be a day late.
Workday stops counting at "Posted 30+ Days Ago", so an older posting has no `date`.
`posted_at` is a calendar date, with no time of day.

`postings` builds the record `--details` would, from a search result's `url` in a later run.
A Workday record has no salary, workplace type, or application link.

## Limits

A search pages through the results one request after another, without pacing.
Workday reports at most 2,000 postings per search, and jobrake warns
when that cap cuts a search short.
Narrow the search with `--query` to reach the rest.
A failed request raises `Stopped` with the postings collected before it.
So does an empty page that comes before the number of postings Workday reported,
as when postings close during the search, so a rerun may find the rest.

`--details` and `postings` send one request per posting, one at a time,
and none for a posting in the [cache](../reference.md#configuration).
A posting removed or withdrawn since the search is gone:
a search keeps its card, and `postings` reports it and leaves it out.
A posting that could not be fetched also keeps its card, and the search raises
[`Stopped`](../reference.md#stopped) with the URLs to retry through `postings`.

## Measured

Workday publishes no documentation for this API.
The behavior described here was measured on NVIDIA's career site in October 2026
and on two career sites in different Workday data centers on 2026-11-14,
and another employer's site may differ.
