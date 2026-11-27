# Lever (`lever`)

[Lever](https://www.lever.co) hosts employer job boards on either its global (`jobs.lever.co`) or EU
(`jobs.eu.lever.co`) domain. Through Lever's public Postings API, jobrake tries the global host
first and falls back to the EU host on a 404, returning all open postings with full descriptions:

```sh
jobrake lever search -b spotify
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("lever", board="spotify"))
```

## Options

Set `--board` to the employer slug from the URL, such as `spotify` from `jobs.lever.co/spotify` or
`jobs.eu.lever.co/spotify`.

Lever only supports exact-match server filters on each employer's custom team/location/commitment
strings, so jobrake fetches the full board and lets you filter locally:

```sh
jobrake lever search -b spotify | jq '[.[] | select(.date != null and .date >= "2026-11-14")]'
```

## Fields

Every posting includes title, locations, creation timestamp, and a combined description (main text,
section lists like requirements and benefits under their headings, salary notes, and closing text),
plus team, department, employment type, workplace type, and application URL when set.

- `company` is always `None` because Lever's API omits the employer name. Track the board slug
  yourself if you're combining multiple boards.
- `employment_type` slugifies whatever commitment label the employer uses, so values vary across
  boards (e.g., `full_time` vs. Spotify's `permanent`).
- `workplace_type` is `remote`, `hybrid`, or `on_site` when specified, and omitted otherwise.
- Structured salary fields are omitted because Lever's API doesn't document its pay-interval enum;
  any salary prose stays in `description`.
- `locations` puts the primary location first (with `country_code`), followed by any secondary
  locations as entered by the employer (such as `London, United Kingdom`).

See the [reference](../reference.md#fields-by-site) for how Lever compares with other boards.
