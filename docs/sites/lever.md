# Lever (`lever`)

jobrake reads one employer's board on [Lever](https://www.lever.co) through Lever's public
Postings API. A search returns every posting on the board with its description:

```sh
jobrake lever search -b spotify
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("lever", board="spotify"))
```

## Options

`--board | -b` takes the board token, the part of the board's address that names the employer:
`spotify` in `jobs.lever.co/spotify`.
A board on Lever's EU host, `jobs.eu.lever.co/<token>`, works the same way.
A token Lever knows on neither host stops the search with an error that says so.

A search takes no query, result limit, or filters.
Lever filters only on the employer's own labels for location, team, department, and commitment,
which must match exactly, so jobrake offers none of them.
To narrow the postings, pipe the results through `jq` or load them into another tool:

```sh
jobrake lever search -b spotify | jq '[.[] | select(.date != null and .date >= "2026-11-14")]'
```

## Fields

A Lever [record](../reference.md#the-record) carries `title`, `locations`, `date`, and
`description`, and, when present, the details `posted_at`, `apply_url`, `team`,
`employment_type`, `workplace_type`, and `department`.

- `company` is always `None`, because Lever's response never names the employer.
- `posted_at` is the time the posting was created, and `date` is its calendar date.
- `description` joins the posting's description, its lists such as requirements and benefits,
  each under its own heading, its salary text, and its closing text.
- `locations` holds the posting's primary location first and then its other places,
  named as the employer entered them, such as `London, United Kingdom`.
  The primary place carries the posting's `country_code`.
- `employment_type` is the employer's commitment label as a slug,
  such as `full_time` for `Full-time`.
  The labels form no fixed list: Spotify's board labels its postings `permanent`.
- `workplace_type` is `remote`, `hybrid`, or `on_site`, as the employer set it,
  and is absent for a posting the employer left unspecified.
- `url` is the posting on `jobs.lever.co` or `jobs.eu.lever.co`,
  and `apply_url` is its application form.
- Lever can send a salary range, but its documentation does not list the pay intervals it uses,
  so jobrake leaves salary out. Salary text in the description stays in `description`.
- `team` is the posting's team, such as `Administrative`.
- In our tests on one board, every one of five postings carried a location, a country, a commitment,
  and a workplace type, and none had a salary range.

## Requests

A search is one request to Lever's global host, which returns the whole board.
When the global host does not know the token, jobrake asks the EU host with a second request.
Any other failure on the global host stops the search without asking the EU host.
A failed request raises [`Stopped`](../reference.md#stopped) with an empty `partial`.
