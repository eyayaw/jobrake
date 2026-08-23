"""Serialize scraped jobs as JSON, JSON Lines, or CSV."""

import csv
import io
import json

from .models import JOB_FIELDS


def to_json(obj: list, **kwargs) -> str:
    """
    Serialize a list as JSON without escaping non-ASCII text.

    Explicit ``json.dumps`` options take precedence over the Unicode default.
    """
    if "ensure_ascii" not in kwargs:
        kwargs["ensure_ascii"] = False
    return json.dumps(obj, **kwargs)


def to_jsonl(jobs: list[dict]) -> str:
    """Serialize one job per line, including a final newline."""
    return "".join(json.dumps(job, ensure_ascii=False) + "\n" for job in jobs)


def to_csv(jobs: list[dict]) -> str:
    """
    Serialize jobs with a header and one column for every model field.

    Columns follow model order. Missing detail fields produce empty cells.
    """
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=JOB_FIELDS, restval="", lineterminator="\n")
    writer.writeheader()
    writer.writerows(jobs)
    return buf.getvalue()


RENDERERS = {
    "json": lambda jobs: to_json(jobs) + "\n",
    "jsonl": to_jsonl,
    "csv": to_csv,
}
