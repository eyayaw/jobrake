# Ashby (`ashby`)

[Ashby](https://www.ashbyhq.com) is an applicant tracking system. An employer that uses it
publishes its openings on a board Ashby hosts, and jobrake reads one employer's board through
Ashby's public Job Posting API.

```sh
jobrake ashby search -b openai
jobrake ashby search -b openai -o openai.csv
jobrake ashby search --board openai --format jsonl
jobrake ashby search -b openai | jq '[.[] | select(.workplace_type == "remote")]'
```

`search` returns every posting on the board, descriptions and compensation included,
in Ashby's order.
A search also returns postings the employer marked unlisted,
which Ashby intends for direct links only.
`--board` is required. In Python the option is a keyword argument:
`scrape("ashby", board="openai")`.

## Options

| Option          | Value                               | Default  |
| --------------- | ----------------------------------- | -------- |
| `--board`, `-b` | the board's token, such as `openai` | required |

The board token is the part of the board's address that names the employer:
`openai` in `jobs.ashbyhq.com/openai`.
A token Ashby does not know stops the search with an error that says so.

The search takes no query, result limit, or filters, and Ashby applies none.
To narrow the postings, filter the records yourself,
as the last command above does on `workplace_type`.
The [README](../../README.md#cli) describes the output options every site shares.

## Fields

An Ashby record carries `title`, `locations`, `date`, and `description`,
and the details `posted_at` and `employment_type`, and, when present, `department`, `team`,
`apply_url`, `workplace_type`, `salary_min`, `salary_max`, `salary_currency`, `salary_period`,
and `site_data`.
[The record](../reference.md#the-record) describes every key.

| Key                 | Value                                                    |
| ------------------- | -------------------------------------------------------- |
| `url`               | the posting on `jobs.ashbyhq.com`                        |
| `apply_url`         | the posting's application form                           |
| `company`           | always `None`                                            |
| `locations`         | the posting's primary location, then its other places    |
| `date`, `posted_at` | the time the posting was published                       |
| `team`              | the posting's team, such as `Solutions Consulting`       |
| `workplace_type`    | `remote`, `hybrid`, or `on_site`, as the employer set it |
| `salary_period`     | `HOUR`, `DAY`, `WEEK`, `MONTH`, or `YEAR`                |
| `site_data`         | `summaryComponents`                                      |

Ashby's response never names the employer, so the board token tells you whose board it is.

A place is named as the employer entered it, such as `Remote (US)` and `Remote (Canada)`.
Each place carries the `city` and `region` of its address as Ashby spells them,
and `region` can be a code or a name, such as `NY` or `Ontario`.
Ashby gives the country as a name, such as `USA` or `United Kingdom`,
so an Ashby place has no `country_code`.

`workplace_type` is absent when the employer set none.
The salary fields come from the posting's first salary range.
`site_data` holds the posting's `summaryComponents` as Ashby sends them,
so equity, commission, and bonus appear there beside the salary range.

## Limits

A search is one request, which returns the whole board.
A failed request raises `Stopped` with no postings.

## Measured

Ashby documents its Job Posting API.
In our test on one board of 172 postings, every posting carried a location, a publish time,
and an employment type, 165 carried a salary range, 162 a city, and 16 were remote.
Of the 172, 124 listed an equity value and 40 a commission.
