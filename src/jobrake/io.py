"""Writers for scraped jobs: one function per output format."""

import csv
import json
from pathlib import Path

from .models import JOB_FIELDS


def to_json(obj: list, **kwargs):
    if len(obj) < 50 and "indent" not in kwargs:
        kwargs["indent"] = 2

    if "ensure_ascii" not in kwargs:
        kwargs["ensure_ascii"] = False
    return json.dumps(obj, **kwargs)


def write_json(jobs: list[dict], path: Path) -> None:
    path.write_text(to_json(jobs) + "\n", encoding="utf-8")


def write_jsonl(jobs: list[dict], path: Path) -> None:
    """Write one job object per line."""
    with path.open("w", encoding="utf-8") as f:
        for job in jobs:
            f.write(json.dumps(job, ensure_ascii=False) + "\n")


def write_csv(jobs: list[dict], path: Path) -> None:
    """Write every model field, with empty cells for unavailable values."""
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=JOB_FIELDS, restval="")
        writer.writeheader()
        writer.writerows(jobs)


WRITERS = {".json": write_json, ".jsonl": write_jsonl, ".csv": write_csv}
