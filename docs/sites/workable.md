# Workable (`workable`)

jobrake reads an employer's [Workable](https://www.workable.com) board through the public API
behind Workable's jobs widget. A search returns every posting on the board with its description,
and a posting Workable lists once per place comes back once:

```sh
jobrake workable search -b huggingface
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("workable", board="huggingface"))
```

## Options

The first path segment of the board's URL is what `--board` takes: `huggingface` in
`apply.workable.com/huggingface`.

Workable's widget returns the whole board and filters nothing, so narrow it yourself, for example
to the postings in France:

```sh
jobrake workable search -b huggingface | jq '[.[] | select(any(.locations[]; .country_code == "FR"))]'
```

## Fields

A posting carries its title, the company, its places, its date, and its description, and, when
the employer set them, the employment type, the department, the application link, and the
education, such as `Master's Degree` ([every key](../reference.md#fields-by-site)).

- `posted_at` is a date without a time of day, so it equals `date`.
- Workable lists a posting open in several places once per place,
  and jobrake returns it once, with each of its places.
  A place is named with the city, region, and country, such as `Paris, Île-de-France, France`.
- When the posting's own city, state, and country match none of its listed places, they become one more place.
- `workplace_type` is only ever `remote`, because Workable flags only remote postings.
- A record has no salary or language, because the board does not publish them.
