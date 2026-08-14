"""Tests for the job data model."""

from jobrake.models import employment_type, make_job


def test_employment_type_is_unified_across_sites():
    # LinkedIn uses schema.org enums, Indeed uses labels
    assert employment_type("FULL_TIME") == employment_type("Full-time") == "full_time"
    assert employment_type("CONTRACTOR") == employment_type("Contract") == "contract"
    assert employment_type("INTERN") == employment_type("Internship") == "internship"
    assert employment_type(None) is None


def test_date_falls_back_to_the_posting_timestamp():
    job = make_job(
        site="indeed",
        id="1",
        title="t",
        company="c",
        url="u",
        location="l",
        posted_at="2026-08-05T08:04:27.000Z",
    )
    assert job["date"] == "2026-08-05"
    assert job["posted_at"] == "2026-08-05T08:04:27.000Z"  # kept whole
