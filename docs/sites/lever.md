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

`--board` takes the board token, the part of the board's address that names the employer:
`spotify` in `jobs.lever.co/spotify`.
A board on Lever's EU host, `jobs.eu.lever.co/<token>`, works the same way.

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

## Requests

One request to Lever's global host returns the whole board.
When the global host does not know the token, jobrake asks the EU host instead.
Any other failure stops the search with nothing, and `scrape` raises [`Stopped`](../reference.md#stopped).
