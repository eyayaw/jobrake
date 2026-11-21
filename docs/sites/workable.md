# Workable (`workable`)

jobrake reads one employer's board on [Workable](https://www.workable.com) through Workable's
public widget API. A search returns every posting on the board with its description:

```sh
jobrake workable search -b huggingface
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("workable", board="huggingface"))
```

A search is one request. A failed request raises [`Stopped`](../reference.md#stopped) with an
empty `partial`.

## Options

`--board | -b` takes the board token, the part of the board's address that names the employer:
`huggingface` in `apply.workable.com/huggingface`.
A token Workable does not know stops the search with an error that says so.

A search takes no query, result limit, or filters, because Workable applies none.
To narrow the postings, pipe the results through `jq` or load them into another tool:

```sh
jobrake workable search -b huggingface | jq '[.[] | select(.workplace_type == "remote")]'
```

## Fields

A Workable [record](../reference.md#the-record) carries `title`, `company`, `locations`, `date`,
and `description`, and, when present, the details `posted_at`, `employment_type`, `department`,
`apply_url`, `workplace_type`, and `education`.

- `posted_at` is the date the posting was published, with no time of day, so it equals `date`.
- Each place carries the `city`, `region`, and `country_code` the employer entered
  and is named with the city, region, and country name, such as `Paris, Île-de-France, France`.
- Workable lists a posting open in several places once per place.
  jobrake returns it once, with each of its places.
- A posting's top-level city, state, and country add a place of their own
  when no listed place matches all three.
  On the board we measured, they repeated the first place.
- `workplace_type` is `remote` when the employer marked the posting as remote.
  The board flags remote alone, so another posting has no `workplace_type`.
  `employment_type` is a slug such as `full_time`.
- `education` is the degree the employer chose, such as `Master's Degree`, and is absent
  when the employer chose none.
- `url` is the posting on `apply.workable.com`, and `apply_url` is its application form.
- In our test on one board of six postings,
  every posting carried a country and an employment type, and three named no city.
- A Workable record has no salary or language, because the board does not publish them.
