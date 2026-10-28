"""Serialize scraped jobs as JSON, JSON Lines, or CSV."""

import csv
import io
import json

from .models import JOB_FIELDS, JobDict


def _csv(jobs: list[JobDict]) -> str:
    """Serialize jobs with a header and one column per model field, in model order, with places by name and site data as JSON."""
    buf = io.StringIO()
    # A missing detail field leaves its cell empty.
    writer = csv.DictWriter(buf, fieldnames=JOB_FIELDS, restval="", lineterminator="\n")
    writer.writeheader()
    writer.writerows(
        {
            **job,
            "locations": "; ".join(place["name"] for place in job["locations"]),
            **(
                {"site_data": json.dumps(job["site_data"], ensure_ascii=False)}
                if "site_data" in job
                else {}
            ),
        }
        for job in jobs
    )
    return buf.getvalue()


RENDERERS = {
    "json": lambda jobs: json.dumps(jobs, ensure_ascii=False) + "\n",
    "jsonl": lambda jobs: "".join(json.dumps(job, ensure_ascii=False) + "\n" for job in jobs),
    "csv": _csv,
}
