# Workable (`workable`)

[Workable](https://www.workable.com) is an applicant tracking system. An employer that uses it
publishes its openings on a board Workable hosts, and jobrake reads one employer's board through
Workable's public widget API.

```sh
jobrake workable search -b huggingface
jobrake workable search -b huggingface -o huggingface.jsonl
jobrake workable search --board huggingface --format csv
jobrake workable search -b huggingface | jq '[.[] | select(.workplace_type == "remote")]'
```

`search` returns every posting on the board, descriptions included, in Workable's order.
`--board` is required. In Python the option is a keyword argument:
`scrape("workable", board="huggingface")`.

## Options

| Option          | Value                                    | Default  |
| --------------- | ---------------------------------------- | -------- |
| `--board`, `-b` | the board's token, such as `huggingface` | required |

The board token is the part of the board's address that names the employer:
`huggingface` in `apply.workable.com/huggingface`.
A token Workable does not know stops the search with an error that says so.

The search takes no query, result limit, or filters, and Workable applies none.
To narrow the postings, filter the records yourself,
as the last command above does on `workplace_type`.
The [README](../../README.md#cli) describes the output options every site shares.

## Fields

A Workable record carries `title`, `company`, `locations`, `date`, and `description`,
and the details `posted_at` and `employment_type`,
and, when present, `department`, `apply_url`, `workplace_type`, and `education`.
[The record](../reference.md#the-record) describes every key.

| Key                 | Value                                                    |
| ------------------- | -------------------------------------------------------- |
| `url`               | the posting on `apply.workable.com`                      |
| `apply_url`         | the posting's application form                           |
| `locations`         | every place the posting is open in                       |
| `date`, `posted_at` | the date the posting was published, with no time of day  |
| `employment_type`   | a slug such as `full_time`                               |
| `workplace_type`    | `remote` when the employer marked the posting as remote  |
| `education`         | the degree the employer chose, such as `Master's Degree` |

Each place carries the `city`, `region`, and `country_code` the employer entered
and is named with the city, region, and country name, such as `Paris, Île-de-France, France`.
Workable lists a posting open in several places once per place.
jobrake returns it once, with each of its places.
A posting's top-level city, state, and country add a place of their own
when no listed place matches all three.

Workable flags only remote postings, so a hybrid or on-site posting has no `workplace_type`.
`education` is absent when the employer chose none.
A Workable record has no salary or language, because the board does not publish them.

## Limits

A search is one request, which returns the whole board.
A failed request raises `Stopped` with no postings.

## Measured

In our test on one board of six postings,
every posting carried a country and an employment type, and three named no city.
On that board, a posting's top-level city, state, and country repeated its first place.
