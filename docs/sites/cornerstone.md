# Cornerstone (`cornerstone`)

Organizations such as the World Bank Group, Henkel, and Project HOPE host their career sites on
[Cornerstone OnDemand](https://www.cornerstoneondemand.com). jobrake queries the undocumented search
API behind those career pages (tested across both US and European Cornerstone data centers).

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

Instead of a short board token, `--board` takes the career site URL copied from your browser:
`https://<tenant>.csod.com/ux/ats/careersite/<id>/home?c=<corp>`. Any individual posting URL from
the same site works too, and a `lang` query parameter (like `lang=de-DE`) sets the search language.

`--query` matches both titles and descriptions. `--country` filters to requisitions with at least
one location in that country. `--max-age-hours` rounds up to whole days to match Cornerstone's API.

## Fields

Each requisition includes its title, locations, description, posting date, and (when set) closing
date; see the [fields by site table](../reference.md#fields-by-site) for a summary. Salary,
employment type, workplace type, and separate application URLs aren't available from this endpoint.

- `company` is always `None` because a single Cornerstone site can cover multiple entities (for
  example, the World Bank Group site posts for IBRD, IDA, IFC, and MIGA).
- `id` combines the tenant name and requisition ID, like `worldbankgroup:39579`.
- Country-only locations use the ISO country code as their `name` (such as `PS`).
- `description` comes directly from the search payload; extra blocks that some employers render on
  individual pages (like summary tables or selection criteria) aren't included.
- `posted_at` and `expires_at` are calendar dates with no time component.
