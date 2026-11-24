# Cornerstone (`cornerstone`)

Employers such as the World Bank Group host their career sites on
[Cornerstone OnDemand](https://www.cornerstoneondemand.com), and jobrake searches one employer's
site through the undocumented API its pages call. We tested the career sites of the World Bank Group,
Henkel, and Project HOPE, which Cornerstone serves from its US and European data centers.

```sh
jobrake cornerstone search -b "https://worldbankgroup.csod.com/ux/ats/careersite/1/home?c=worldbankgroup" -n 200
jobrake cornerstone search -b "https://worldbankgroup.csod.com/ux/ats/careersite/1/home?c=worldbankgroup" -q economist -c us
jobrake cornerstone search -b "https://henkel.csod.com/ux/ats/careersite/1/home?c=henkel" -c de -a 72 -o henkel.jsonl
```

```python
import asyncio

from jobrake import scrape

board = "https://worldbankgroup.csod.com/ux/ats/careersite/1/home?c=worldbankgroup"
jobs = asyncio.run(scrape("cornerstone", board=board, query="economist", results=200))
```

## Options

Cornerstone has no board token. Pass `--board` the address of the employer's career site, copied
from the browser, which has the form `https://<tenant>.csod.com/ux/ats/careersite/<id>/home?c=<corp>`.
A posting's address on the same site works too, and a `lang` in the address,
such as `lang=de-DE`, carries over to the search.

`--query` searches the description as well as the title. `--country` keeps the requisitions with a
location in that country, and a requisition with several locations is found by any of them.
`--max-age-hours` rounds up to whole days, the unit of Cornerstone's age filter.

## Fields

A search result carries the requisition's title, places, description, posting date, and closing
date when the employer set one ([every key](../reference.md#fields-by-site)).

- `company` is always `None`, because one career site can post for several organizations, as the
  World Bank Group's does for IBRD, IDA, IFC, and MIGA.
- `id` joins the employer's Cornerstone name and the requisition ID, as in `worldbankgroup:39579`.
- When Cornerstone gives a place only as a country, its name is the country code, such as `PS`.
- `description` is the text the search returns. Some employers' posting pages add more around it,
  such as a summary table or selection criteria, which the record lacks.
- `posted_at` and `expires_at` are dates without a time.
- A record has no salary, employment type, workplace type, or application link.
