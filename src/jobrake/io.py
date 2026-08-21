"""One renderer for each scraped-job output format."""

import csv
import io
import json

from .models import JOB_FIELDS


def to_json(obj: list, **kwargs):
    if "ensure_ascii" not in kwargs:
        kwargs["ensure_ascii"] = False
    return json.dumps(obj, **kwargs)


def to_jsonl(jobs: list[dict]) -> str:
    """Render one job object per line."""
    return "".join(json.dumps(job, ensure_ascii=False) + "\n" for job in jobs)


def to_csv(jobs: list[dict]) -> str:
    """Render every model field, with empty cells for unavailable values."""
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
