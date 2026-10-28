"""Tests for the job data model."""

import pickle
import re

import pytest
from hypothesis import given
from hypothesis import strategies as st

from jobrake.models import (
    IDENTITY_FIELDS,
    SUMMARY_FIELDS,
    Stopped,
    employment_type,
    make_job,
    workplace_type,
)

_TEXT = st.one_of(
    st.none(), st.integers(), st.text(max_size=6), st.sampled_from(["de", " NL ", "USA"])
)
_NUMBER = st.one_of(st.none(), st.text(max_size=4), st.integers(), st.floats())
_PLACE = st.fixed_dictionaries(
    {},
    optional=dict.fromkeys(("name", "city", "region", "country_code"), _TEXT)
    | dict.fromkeys(("latitude", "longitude"), _NUMBER),
)


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


def test_workplace_type_reads_the_sites_labels_and_nothing_else():
    labels = ("OnSite", "on-site", "Remote", "Hybrid")  # Ashby's and Lever's spellings
    assert [workplace_type(label) for label in labels] == ["on_site", "on_site", "remote", "hybrid"]
    # Lever's unspecified, and slugs of labels no site sends, are no workplace type.
    assert [workplace_type(label) for label in ("unspecified", "onsite", "Hybrid work", None)] == [
        None
    ] * 4
    assert "workplace_type" not in make_job(site="x", id="1", url="u", workplace_type="anywhere")


def test_site_data_keeps_the_fields_with_a_value_and_rejects_another_shape():
    fields = {
        "team": "Data",
        "levels": [],
        "note": "",
        "rank": None,
        "open": False,
        # Strict JSON has no infinity, so that number alone becomes None.
        "pay": [{"type": "Bonus", "min": 1000}, {"type": "Salary", "min": float("inf")}],
    }
    assert make_job(site="x", id="1", url="u", site_data=fields)["site_data"] == {
        "team": "Data",
        "open": False,
        "pay": [{"type": "Bonus", "min": 1000}, {"type": "Salary", "min": None}],
    }
    assert "site_data" not in make_job(site="x", id="1", url="u", site_data={"team": None})
    # A cache row of another shape must fail here, so the cache reads it as a miss.
    for malformed in (["Data"], {1: "Data"}):
        with pytest.raises(TypeError):
            make_job(site="x", id="1", url="u", site_data=malformed)


def test_job_dict_keeps_summary_keys_and_omits_unavailable_detail():
    job = make_job(
        site="linkedin",
        id=" 1 ",
        url="u",
        title="t",
        company="c",
        locations=[{"name": "   "}],
        description="   ",
        company_url="   ",
        salary_min=None,
    )
    assert set(job) == {*IDENTITY_FIELDS, *SUMMARY_FIELDS}
    assert job["id"] == "1"
    assert job["locations"] == []
    assert job["date"] is None


def test_date_falls_back_to_the_posting_timestamp():
    job = make_job(
        site="indeed",
        id="1",
        title="t",
        company="c",
        url="u",
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


@given(st.lists(_PLACE, max_size=5))
def test_places_come_out_named_distinct_and_unchanged_by_a_second_pass(places):
    # A cache row passes through make_job again, so a record must read back as it was written.
    job = make_job(site="x", id="1", url="u", locations=places)
    assert make_job(**job) == job
    names = [place["name"] for place in job["locations"]]
    assert all(name and name == name.strip() for name in names)
    assert all(
        place not in job["locations"][:index] for index, place in enumerate(job["locations"])
    )
    codes = [place["country_code"] for place in job["locations"] if "country_code" in place]
    assert all(re.fullmatch("[A-Z]{2}", code) for code in codes)


def test_a_place_keeps_what_the_site_gives_and_a_malformed_one_is_rejected():
    locations = [
        {"city": " Berlin ", "country_code": "de", "latitude": 52.5},
        {"name": "Berlin, DE", "city": "Berlin", "country_code": "DE", "latitude": 52.5},  # again
        {"name": "Boston", "country_code": "USA"},  # a country name, not a code
        {"latitude": 1.0},  # coordinates alone name no place
        {"name": "Remote", "country_code": "US"},
        {"name": "Remote", "region": "Ontario"},  # matching names do not make these places equal
    ]
    assert make_job(site="x", id="1", url="u", locations=locations)["locations"] == [
        {
            "name": "Berlin, DE",
            "city": "Berlin",
            "country_code": "DE",
            "latitude": 52.5,
        },
        {"name": "Boston"},
        {"name": "Remote", "country_code": "US"},
        {"name": "Remote", "region": "Ontario"},
    ]
    # A cache row of another shape must fail here, so the cache reads it as a miss.
    for malformed in ("Berlin", ["Berlin"], [{"name": "Berlin", "zip": "10115"}]):
        with pytest.raises(TypeError):
            make_job(site="x", id="1", url="u", locations=malformed)
