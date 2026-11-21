# Greenhouse (`greenhouse`)

jobrake reads one employer's board on [Greenhouse](https://www.greenhouse.com) through
Greenhouse's public Job Board API. A search returns every posting on the board with its
description:

```sh
jobrake greenhouse search -b airbnb
jobrake greenhouse search -b anthropic -o anthropic.jsonl
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("greenhouse", board="airbnb"))
```

A search is one request. A failed request raises [`Stopped`](../reference.md#stopped) with an
empty `partial`.

## Options

`--board | -b` takes the board token, the part of the board's address that names the employer:
`airbnb` in `boards.greenhouse.io/airbnb`, or `anthropic` in `job-boards.greenhouse.io/anthropic`.
A token Greenhouse does not know stops the search with an error that says so.

A search takes no query, result limit, or filters, because Greenhouse applies none.
To narrow the postings, pipe the results through `jq` or load them into another tool:

```sh
jobrake greenhouse search -b airbnb | jq '[.[] | select(.date != null and .date >= "2026-11-14")]'
```

## Fields

A Greenhouse [record](../reference.md#the-record) carries `title`, `locations`, and `description`.
It also carries `company`, `date`, and the details `posted_at`, `language`, `department`,
and `expires_at` when Greenhouse supplies them, which its documented list response does not promise.

- `posted_at` is the time the posting was first published, and `date` is its calendar date.
  `expires_at` is the application deadline.
- `department` is the posting's department when Greenhouse lists exactly one,
  as it did for all 195 postings on Airbnb's board on 2026-10-28.
- `locations` holds one place, named with the text the employer entered,
  such as `Remote, Canada; Remote, United States`.
- `url` is the posting on the employer's own careers site when the board lives there,
  as Airbnb's does, and on `job-boards.greenhouse.io` otherwise.
- In our tests on two boards, every posting carried a company, a location, a first-published time,
  and a language, and one posting in 430 had a deadline.
- Employers can add facts such as a workplace type as custom fields,
  which differ from board to board.
  jobrake leaves those out, so a Greenhouse record has no salary, employment type,
  or workplace type.
