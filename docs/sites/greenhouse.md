# Greenhouse (`greenhouse`)

An employer on [Greenhouse](https://www.greenhouse.com) keeps its job board on Greenhouse or on its
own careers site, as Airbnb does. jobrake reads either through Greenhouse's public Job Board API,
and a search returns every posting on the board with its description:

```sh
jobrake greenhouse search -b airbnb
jobrake greenhouse search -b anthropic -o anthropic.jsonl
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("greenhouse", board="airbnb"))
```

## Options

`--board` takes the board token, the part of the board's address that names the employer:
`airbnb` in `boards.greenhouse.io/airbnb`, or `anthropic` in `job-boards.greenhouse.io/anthropic`.

Greenhouse filters nothing on its side, so a search returns the whole board.
Narrow it yourself, for example by title:

```sh
jobrake greenhouse search -b airbnb | jq '[.[] | select(.title | test("data"; "i"))]'
```

## Fields

A posting carries its title, its place, and its description, and usually the company, the
first-published date, the department, and the language ([every key](../reference.md#fields-by-site)).

- `locations` holds one place whose name is the employer's own text, which can list several
  places, such as `Remote, Canada; Remote, United States`.
- `department` is set only when Greenhouse lists exactly one department for the posting.
- `expires_at` is the application deadline, which few postings had in our tests.
- `url` is the posting on the employer's own careers site when the board lives there,
  as Airbnb's does, and on `job-boards.greenhouse.io` otherwise.
- Employers add facts such as a workplace type as custom fields, which differ from
  board to board. jobrake leaves those out, so a Greenhouse record has no salary, employment type, or workplace type.

## Requests

One request reads the whole board. If it fails, you get nothing, and `scrape` raises
[`Stopped`](../reference.md#stopped).
