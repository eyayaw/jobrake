# Lever (`lever`)

[Lever](https://www.lever.co) serves each employer's job board from its global host or its EU host.
jobrake reads one board through Lever's public Postings API, on whichever host knows it,
and a search returns every posting with its description:

```sh
jobrake lever search -b spotify
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("lever", board="spotify"))
```

## Options

Pass `--board` the first path segment of the board's URL, on the global or the EU host:
`spotify` in `jobs.lever.co/spotify` or `jobs.eu.lever.co/spotify`.

A search takes no query, result limit, or filters.
Lever filters only on the employer's own labels for location, team, department, and commitment,
which must match exactly, so jobrake offers none of them.
Filter the results yourself instead:

```sh
jobrake lever search -b spotify | jq '[.[] | select(.date != null and .date >= "2026-11-14")]'
```

## Fields

A posting carries its title, its places, the time it was created, and its description.
The description joins the posting's text, its lists, such as requirements and benefits, under their
headings, its salary text, and its closing text. When the employer set them, you also get the team,
the department, the commitment, the workplace type, and the application link ([every key](../reference.md#fields-by-site)).

- `company` is always `None`, because Lever's response never names the employer.
  Keep the board token with the results if you merge several boards.
- `employment_type` is the employer's own commitment label as a slug, so it varies by board:
  `full_time` for `Full-time`, but Spotify's board labels its postings `permanent`.
- `workplace_type` is `remote`, `hybrid`, or `on_site`, and is absent when the employer left it unspecified.
- Lever can send a salary range, but its documentation does not list the pay intervals it uses,
  so jobrake leaves salary out. Salary text in the description stays in `description`.
- `locations` holds the primary location first, with its `country_code`, and then the other places,
  named as the employer entered them, such as `London, United Kingdom`.
