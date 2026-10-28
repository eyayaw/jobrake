"""Tests for the job data model."""

import pickle

import pytest

from jobrake.models import IDENTITY_FIELDS, SUMMARY_FIELDS, Stopped, employment_type, make_job


def test_employment_type_is_unified_across_sites():
    # LinkedIn uses schema.org enums, Indeed uses labels, and Ashby uses camelCase enums
    assert employment_type("FULL_TIME") == employment_type("Full-time") == "full_time"
    assert employment_type("CONTRACTOR") == employment_type("Contract") == "contract"
    assert employment_type("INTERN") == employment_type("Internship") == "internship"
    assert [employment_type(label) for label in ("FullTime", "PartTime", "Intern")] == [
        "full_time",
        "part_time",
        "internship",
    ]
    assert employment_type(None) is None
    assert employment_type("---") is None


def test_job_dict_keeps_summary_keys_and_omits_unavailable_detail():
    job = make_job(
        site="linkedin",
        id=" 1 ",
        url="u",
        title="t",
        company="c",
        location="   ",
        description="   ",
        company_url="   ",
        salary_min=None,
    )
    assert set(job) == {*IDENTITY_FIELDS, *SUMMARY_FIELDS}
    assert job["id"] == "1"
    assert job["location"] is None
    assert job["date"] is None


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


def test_make_job_rejects_a_record_outside_job_dict():
    # A cached row from an older field set must fail here rather than reach callers.
    with pytest.raises(TypeError, match="headcount"):
        make_job(site="linkedin", id="1", url="u", headcount=4)
    for identity in ({"id": "1"}, {"id": 1, "url": "u"}, {"id": " ", "url": "u"}):
        with pytest.raises(TypeError, match="must be a nonblank string"):
            make_job(site="linkedin", **identity)


def test_stopped_keeps_its_partial_across_processes():
    # A process pool pickles a worker's exception to hand it back.
    job = make_job(site="linkedin", id="1", url="u")
    stop = pickle.loads(pickle.dumps(Stopped("HTTP 429", partial=[job])))
    assert (str(stop), stop.partial) == ("HTTP 429", [job])
