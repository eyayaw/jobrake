"""CLI output tests for stdout and files, with explicit and inferred formats."""

import csv
import json
import os
import sys

import pytest

from jobrake import cli
from jobrake.models import JOB_FIELDS, make_job

JOBS = [
    make_job(
        id="1",
        title='Economist, "Senior"',
        company="Acme, Inc.",
        url="https://example.com/1",
        site="indeed",
        location="Seattle, WA",
        description="line one\nline two",
        date="2026-08-01",
    ),
    make_job(
        id="2",
        title="Analyst",
        company="Beta",
        url="https://example.com/2",
        site="indeed",
        location="Remote",
    ),
]


@pytest.fixture
def run_cli(monkeypatch):
    """Run ``cli.main()`` with a stubbed scrape returning ``JOBS``."""

    async def fake_scrape(*args, **kwargs):
        return JOBS

    monkeypatch.setattr(cli, "scrape", fake_scrape)

    def run(*argv):
        monkeypatch.setattr("sys.argv", ["jobrake", "-s", "indeed", "-q", "x", "-c", "usa", *argv])
        return cli.main()

    return run


def test_default_output_is_json_on_stdout(run_cli, capsys):
    run_cli()
    assert json.loads(capsys.readouterr().out) == JOBS


def test_format_selects_stdout_and_overrides_output_extension(run_cli, capsys, tmp_path):
    run_cli("--format", "jsonl")
    assert [json.loads(line) for line in capsys.readouterr().out.splitlines()] == JOBS
    out = tmp_path / "jobs.txt"
    run_cli("--format", "jsonl", "-o", str(out))
    assert [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()] == JOBS


def test_output_csv_roundtrips_hostile_fields(run_cli, tmp_path, capsys):
    out = tmp_path / "jobs.csv"
    run_cli("-o", str(out))
    with out.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0].keys() == set(JOB_FIELDS)
    # Unavailable summaries and absent details read back as empty cells.
    expected = [
        {name: "" if job.get(name) is None else str(job[name]) for name in JOB_FIELDS}
        for job in JOBS
    ]
    assert rows == expected
    assert capsys.readouterr().out == ""  # File output leaves stdout silent.


def test_output_jsonl_one_object_per_line(run_cli, tmp_path):
    out = tmp_path / "jobs.jsonl"
    run_cli("-o", str(out))
    lines = out.read_text(encoding="utf-8").splitlines()
    # A leaked raw newline in a description would break the per-line parse.
    assert [json.loads(line) for line in lines] == JOBS


def test_output_json_writes_file(run_cli, tmp_path):
    out = tmp_path / "jobs.json"
    run_cli("-o", str(out))
    assert json.loads(out.read_text(encoding="utf-8")) == JOBS


def test_closed_pipe_ends_quietly(run_cli, monkeypatch):
    read_end, write_end = os.pipe()
    os.close(read_end)
    with open(write_end, "w") as stdout:
        monkeypatch.setattr(sys, "stdout", stdout)
        assert run_cli() == 1


def test_unknown_extension_fails_before_scraping(run_cli, monkeypatch, tmp_path):
    async def must_not_run(*args, **kwargs):
        raise AssertionError("scrape ran despite a bad --output")

    monkeypatch.setattr(cli, "scrape", must_not_run)
    with pytest.raises(SystemExit):
        run_cli("-o", str(tmp_path / "jobs.xlsx"))
