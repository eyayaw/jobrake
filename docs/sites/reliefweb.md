# ReliefWeb (`reliefweb`)

[ReliefWeb](https://reliefweb.int/jobs), run by UN OCHA, lists humanitarian and development
postings from UN agencies, NGOs, and other organizations: staff jobs, consultancies, internships,
and volunteer roles.

jobrake reads ReliefWeb's [API](https://apidoc.reliefweb.int), which serves only applications
ReliefWeb has approved, so a search needs an appname of your own. Request one with the
[form in the API's documentation](https://apidoc.reliefweb.int/#appname). Then set it in your
shell profile:

```sh
export JOBRAKE_RELIEFWEB_APPNAME="the-name-reliefweb-approved"
```

A search returns the postings newest first, each with its description:

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

`--query` runs the keyword search of ReliefWeb's own job page, so it finds what that page finds.
It matches more than titles: in our tests, `finance` in Colombia also found postings titled
`Oficial de Finanzas` and `Asistente Administrativo/a`.

`--country` keeps the postings that name the country, given by its ISO 3166-1 code, such as `ke`
or `ken`. A posting can name several countries, and a search for any one of them finds it.

`--max-age-hours` keeps the postings ReliefWeb published within that many hours.
In our tests, the default 100 postings went back about three days, so raise `--results` to reach
further.

## Fields

A record carries the full description, the organization that posts it, the countries it names,
the date ReliefWeb published it, and its closing date ([every key](../reference.md#fields-by-site)).

- `company` is the first organization a posting names, and `company_url` its homepage when
  ReliefWeb has one. A posting rarely names a second organization, which the record leaves out.
- `locations` holds one place per country, named as ReliefWeb names it, such as
  `United Kingdom of Great Britain and Northern Ireland`, with its `country_code`. ReliefWeb gives
  no city. A region it lists as a country, such as `World`, carries no code.
- `employment_type` is ReliefWeb's posting type: `job`, `consultancy`, `internship`,
  `volunteer_opportunity`, or `tender_rfps_eois`, a call for tenders or proposals that the job list
  carries too.
- `posted_at` is when the posting appeared on ReliefWeb, and `expires_at` its closing date.
- A record has no salary or `workplace_type`. A posting that pays or allows remote work says so
  in its description.
- `site_data` holds the `experience` ReliefWeb asks for, such as `3-4 years`, the
  `career_categories` and `themes` it files the posting under, and `how_to_apply`, the posting's
  own instructions.

## Terms

ReliefWeb's [terms and conditions](https://reliefweb.int/terms-conditions) permit downloading and
copying its material for personal, non-commercial use, and they give no right to redistribute it
or to compile works from it.
