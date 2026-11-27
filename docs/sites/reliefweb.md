# ReliefWeb (`reliefweb`)

[ReliefWeb](https://reliefweb.int/jobs), run by UN OCHA, publishes humanitarian and development
openings from UN agencies, NGOs, and partner organizations, covering staff roles, consultancies,
internships, and volunteer positions.

ReliefWeb's [v2 API](https://apidoc.reliefweb.int) requires an approved `appname`. Request one
through [ReliefWeb's registration form](https://apidoc.reliefweb.int/#appname) and export it in
your shell:

```sh
export JOBRAKE_RELIEFWEB_APPNAME="the-name-reliefweb-approved"
```

Searches return postings newest first with full descriptions:

```sh
jobrake reliefweb search -n 500 -o reliefweb.jsonl
jobrake reliefweb search -q "monitoring evaluation" -c ke
jobrake reliefweb search -q economist --max-age-hours 72
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("reliefweb", query="nutrition", country="so"))
```

## Options

`--query` runs ReliefWeb's website keyword search, matching beyond job titles (searching `finance`
in Colombia, for instance, also surfaces `Oficial de Finanzas` and `Asistente Administrativo/a`).

`--country` filters by ISO 3166-1 code (such as `ke` or `ken`) and matches any posting listing that
country, even when multiple countries are attached.

`--max-age-hours` filters by when ReliefWeb published the posting. Because the default `-n 100`
typically spans only a few days of listings, increase `--results` when looking further back.

## Fields

Each posting includes its full description, hiring organization, listed countries, publication
timestamp, and closing date. Salary and `workplace_type` are not structured fields on ReliefWeb, so
check the description for pay or remote eligibility. See the
[reference](../reference.md#fields-by-site) for all fields.

- `company` is the first listed organization, and `company_url` is its homepage when present
  (postings rarely list a second organization, which is ignored).
- `locations` has one entry per country using ReliefWeb's label (e.g.,
  `United Kingdom of Great Britain and Northern Ireland`) and `country_code`, with no city.
  Non-country entries like `World` omit `country_code`.
- `employment_type` maps ReliefWeb's posting type: `job`, `consultancy`, `internship`,
  `volunteer_opportunity`, or `tender_rfps_eois` (calls for tenders/proposals that appear in the
  job feed).
- `posted_at` is when the posting went live on ReliefWeb; `expires_at` is the closing date.
- `site_data` contains `experience` (e.g., `3-4 years`), `career_categories`, `themes`, and
  `how_to_apply`.

## Terms

ReliefWeb's [terms and conditions](https://reliefweb.int/terms-conditions) allow downloading and
copying content for personal, non-commercial use only, without rights to redistribute or build
derivative compilations.
