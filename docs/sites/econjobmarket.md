# EconJobMarket (`econjobmarket`)

[EconJobMarket](https://econjobmarket.org) (EJM) is the job market site for economists:
academic positions, postdocs, pre-docs, and research jobs at central banks and consultancies.

```sh
jobrake econjobmarket search
jobrake econjobmarket search -o ejm.jsonl
jobrake econjobmarket search -o ejm.csv
```

jobrake reads EJM's public ad feed. A search returns every open ad, in the feed's order.
In [Python](../reference.md#python-api) it is `scrape("econjobmarket")`.

## Options

A search takes no query, result limit, or filters, because EJM applies none.
To narrow the ads, pipe the results through `jq` or load them into another tool:

```sh
jobrake econjobmarket search \
  | jq -r '.[] | select(any(.locations[]; .country_code == "DE")) | [.expires_at, .company, .title] | @tsv'
```

The [README](../../README.md#cli) describes `--output` and `--format`,
which every site shares.

## Fields

An EconJobMarket record carries `title`, `company`, `locations`, `date`, and `description`,
and the details `posted_at`, `expires_at`, `company_logo`, `site_data`, and, when present,
`department`.
[The record](../reference.md#the-record) describes every key.

| Key                 | Value                                                                      |
| ------------------- | -------------------------------------------------------------------------- |
| `id`                | the ad's number, which ends its `url`                                      |
| `url`               | the ad on `econjobmarket.org`, where candidates apply                      |
| `company`           | the hiring institution, such as `University of Zurich`                     |
| `company_logo`      | a link to its logo on EJM                                                  |
| `department`        | the hiring unit, such as `Department of Economics`                         |
| `locations`         | each location the ad lists, such as `Boston, Massachusetts, US`            |
| `date`, `posted_at` | the ad's start date on EJM, a calendar date without a time                 |
| `expires_at`        | the application deadline                                                   |
| `site_data`         | `position_types` and `categories`, each as a list of names                 |

A location carries its `city`, `region`, `country_code`, and coordinates when present,
and its name joins the city, region, and country code. An ad that lists no location has an empty `locations`.
An ad that says `All departments` has no `department`.
An ad can still be open after its deadline.

`position_types` are ranks such as `Assistant Professor`,
and `categories` are fields of economics such as `Econometrics`.
Candidates apply on the ad's page, so a record has no separate `apply_url`.
The feed carries no salary, employment type, or workplace type.

## Limits

A search is one request, which returns every open ad.
A failed request raises [`Stopped`](../reference.md#stopped) with an empty `partial`.

## Terms

EJM offers the feed "for personal use and for academic research projects".
To redisplay EJM ads on your own website, you must notify EJM and get EJM's approval first.
Any use of the feed must follow EJM's Terms of Use, Privacy Policy, and Research Data Usage Policy.
See [Accessing the EJM Ad Feed](https://backend.econjobmarket.org/docs/ad-redisplay/Ad-Redisplay.0.md).

## Measured

EJM documents the feed on the page linked under Terms.
The counts are from our read of the feed's 319 ads on 2026-10-28:
7 were still open after their deadline, 2 listed no location,
and every one listed both `position_types` and `categories`.
