# Greenhouse (`greenhouse`)

[Greenhouse](https://www.greenhouse.com) is an applicant tracking system. An employer that uses it
publishes its openings on a board Greenhouse hosts, and jobrake reads one employer's board through
Greenhouse's public Job Board API.

```sh
jobrake greenhouse search -b airbnb
jobrake greenhouse search -b anthropic -o anthropic.jsonl
jobrake greenhouse search --board airbnb --output airbnb.csv
jobrake greenhouse search -b airbnb | jq '[.[] | select(.date != null and .date >= "2026-11-14")]'
```

`search` returns every posting on the board, descriptions included, in Greenhouse's order.
`--board` is required. In Python the option is a keyword argument:
`scrape("greenhouse", board="airbnb")`.

## Options

| Option          | Value                               | Default  |
| --------------- | ----------------------------------- | -------- |
| `--board`, `-b` | the board's token, such as `airbnb` | required |

The board token is the part of the board's address that names the employer:
`airbnb` in `boards.greenhouse.io/airbnb`, or `anthropic` in `job-boards.greenhouse.io/anthropic`.
A token Greenhouse does not know stops the search with an error that says so.

The search takes no query, result limit, or filters, and Greenhouse applies none.
To narrow the postings, filter the records yourself, as the last command above does on `date`.
The [README](../../README.md#cli) describes the output options every site shares.

## Fields

A Greenhouse record carries `title`, `locations`, and `description`.
When Greenhouse omits them, `company` and `date` are `None`, and `posted_at`, `language`,
`department`, and `expires_at` are absent. Its documented list response promises none of them.
[The record](../reference.md#the-record) describes every key.

| Key                 | Value                                                   |
| ------------------- | ------------------------------------------------------- |
| `locations`         | one place, named with the text the employer entered     |
| `date`, `posted_at` | the time the posting was first published                |
| `expires_at`        | the application deadline                                |
| `department`        | the posting's department, when Greenhouse lists exactly one |

`url` is the posting on the employer's own careers site when the board lives there,
as Airbnb's does, and on `job-boards.greenhouse.io` otherwise.
The one place keeps the employer's text whole, such as `Remote, Canada; Remote, United States`.

Employers can add facts such as a workplace type as custom fields,
which differ from board to board.
jobrake leaves those out, so a Greenhouse record has no salary, employment type,
or workplace type.

## Limits

A search is one request, which returns the whole board.
A failed request raises `Stopped` with no postings.

## Measured

Greenhouse documents its Job Board API.
In our tests on two boards, every posting carried a company, a location, a first-published time,
and a language, and one posting in 430 had a deadline.
All 195 postings on Airbnb's board on 2026-10-28 listed exactly one department.
