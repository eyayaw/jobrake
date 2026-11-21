# Lever (`lever`)

[Lever](https://www.lever.co) is an applicant tracking system. An employer that uses it
publishes its openings on a board Lever hosts, and jobrake reads one employer's board through
Lever's public Postings API.

```sh
jobrake lever search -b spotify
jobrake lever search -b spotify -o spotify.jsonl
jobrake lever search --board spotify --format csv
jobrake lever search -b spotify | jq '[.[] | select(.date != null and .date >= "2026-11-14")]'
```

`search` returns every posting on the board, descriptions included, in Lever's order.
`--board` is required. In Python the option is a keyword argument:
`scrape("lever", board="spotify")`.

## Options

| Option          | Value                                | Default  |
| --------------- | ------------------------------------ | -------- |
| `--board`, `-b` | the board's token, such as `spotify` | required |

The board token is the part of the board's address that names the employer:
`spotify` in `jobs.lever.co/spotify`.
A board on Lever's EU host, `jobs.eu.lever.co/<token>`, works the same way.
A token Lever does not know on either host stops the search with an error that says so.

The search takes no query, result limit, or filters.
Lever filters only on the employer's own labels for location, team, department, and commitment,
which must match exactly, so jobrake offers none of them.
To narrow the postings, filter the records yourself, as the last command above does on `date`.
The [README](../../README.md#cli) describes the output options every site shares.

## Fields

A Lever record carries `title`, `locations`, `date`, and `description`, and the details `posted_at`,
`apply_url`, and, when present, `team`, `employment_type`, `workplace_type`, and `department`.
[The record](../reference.md#the-record) describes every key.

| Key                 | Value                                                    |
| ------------------- | -------------------------------------------------------- |
| `url`               | the posting on `jobs.lever.co` or `jobs.eu.lever.co`     |
| `apply_url`         | the posting's application form                           |
| `company`           | always `None`                                            |
| `locations`         | the posting's primary location, then its other places    |
| `date`, `posted_at` | the time the posting was created                         |
| `team`              | the posting's team, such as `Administrative`             |
| `employment_type`   | the employer's commitment label as a slug                |
| `workplace_type`    | `remote`, `hybrid`, or `on_site`, as the employer set it |

Lever's response never names the employer, so the board token tells you whose board it is.
`description` joins the posting's description, its lists such as requirements and benefits,
each under its own heading, its salary text, and its closing text.

A place is named as the employer entered it, such as `London, United Kingdom`.
The primary place carries the posting's `country_code`.

`employment_type` is a slug such as `full_time` for `Full-time`, and the values form no fixed
list: Spotify's board labels its postings `permanent`.
`workplace_type` is absent for a posting the employer left unspecified.

A Lever record has no salary fields.
Lever can send a salary range, but its documentation does not list the pay intervals it uses,
so jobrake leaves salary out.

## Limits

A search is one request, which returns the whole board.
A board on Lever's EU host takes a second request, sent only when the global host does not
know the token, so any other failure there stops the search.
A failed request raises `Stopped` with no postings.

## Measured

Lever documents its Postings API.
In our tests on one board, every one of five postings carried a location, a country, a commitment,
and a workplace type, and none had a salary range.
