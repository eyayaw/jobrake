# XING (`xing`)

[XING](https://www.xing.com) is a professional network with a job market for Germany, Austria, and
Switzerland. jobrake reads it through the undocumented API of XING's Android app.

```sh
jobrake xing search -q economist -l Berlin -n 20
jobrake xing search -q "data scientist" -l Zürich -r 50 -a 168 -o xing.jsonl
jobrake xing search -q "data engineer" --remote --details
jobrake xing postings https://www.xing.com/jobs/berlin-referent-strategische-datenanalyse-158824212
```

```python
import asyncio

from jobrake import scrape

jobs = asyncio.run(scrape("xing", query="economist", location="Berlin", details=True))
```

## Options

| Option                  | Value                                               | Default               |
| ----------------------- | --------------------------------------------------- | --------------------- |
| `--query`, `-q`         | a job title or keywords                             | none                  |
| `--location`, `-l`      | a city or postal code, such as `Berlin` or `Zürich` | everywhere            |
| `--radius`, `-r`        | kilometers around the location                      | 0, the location alone |
| `--results`, `-n`       | the number of postings to return                    | 100                   |
| `--max-age-hours`, `-a` | the oldest posting to keep, in hours                | no age limit          |
| `--remote`              | keep only the postings XING lists as fully remote   | off                   |
| `--details`, `-d`       | fetch each posting                                  | off                   |

`xing` has no `--country`, because XING filters countries only by IDs of its own. To search Austria
or Switzerland, pass a place there to `--location`, such as `Wien`.

## Fields

Where XING has them, search results carry the company's page and logo, the employment and
workplace type, the application link, an advertised salary, and XING's career level, discipline,
and industry. `--details` adds the description ([every key](../reference.md#fields-by-site)).

- `posted_at` and `date` are when XING last published or refreshed the posting, so an older posting
  can carry a recent date. `--max-age-hours` counts from the same date. `expires_at` is when the
  posting is set to end.
- The salary fields hold only a salary the employer advertised, never XING's own estimate.
  XING gives no period, and its app shows salaries per year, so `salary_period` is `YEAR`.
- `apply_url` is the employer's application page or XING's own apply link. A posting that takes
  applications by email has none.
- `site_data` holds `career_level`, `discipline`, and `industry`, in English.

### Postings you already know

`jobrake xing postings` takes the URLs of postings, such as
`https://www.xing.com/jobs/berlin-referent-strategische-datenanalyse-158824212`, and returns what a
`--details` search would.

## Requests

XING serves at most 1,000 postings per search. Split a broader search by place, or narrow the
query, to reach the rest.
