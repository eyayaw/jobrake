"""CLI output tests for stdout and files, with explicit and inferred formats."""

import csv
import io
import json
import logging
import os
import sys
from pathlib import Path

import pytest

from jobrake import cli, defaults
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
        monkeypatch.setattr("sys.argv", ["jobrake", "indeed", "-q", "x", "-c", "usa", *argv])
        return cli.main()

    return run


def test_places_command_prints_the_selected_providers_candidates(monkeypatch, capsys):
    linkedin_hits = [{"geoId": "102011674", "displayName": "Amsterdam, North Holland, Netherlands"}]
    indeed_hits = [{"suggestion": "Boston, MA", "locationType": "CITY"}]

    class StubHttpx:
        instances: list = []

        def __init__(self):
            self.closed = False
            StubHttpx.instances.append(self)

        async def close(self):
            self.closed = True

    async def fake_linkedin(fetcher, name):
        assert name == "amsterdam"
        return linkedin_hits

    async def fake_indeed(fetcher, name, country):
        assert (name, country) == ("boston", "usa")
        return indeed_hits

    monkeypatch.setattr(cli, "HttpxFetcher", StubHttpx)
    monkeypatch.setattr(cli.linkedin, "places", fake_linkedin)
    monkeypatch.setattr(cli.indeed, "places", fake_indeed)
    monkeypatch.setattr(sys, "argv", ["jobrake", "places", "linkedin", "amsterdam"])
    assert cli.main() is None
    assert json.loads(capsys.readouterr().out) == linkedin_hits
    monkeypatch.setattr(sys, "argv", ["jobrake", "places", "indeed", "boston", "-c", "usa"])
    assert cli.main() is None
    assert json.loads(capsys.readouterr().out) == indeed_hits
    linkedin_hits = None  # a failed lookup exits nonzero with nothing on stdout
    monkeypatch.setattr(sys, "argv", ["jobrake", "places", "linkedin", "amsterdam"])
    assert cli.main() == 1
    assert capsys.readouterr().out == ""
    assert StubHttpx.instances and all(f.closed for f in StubHttpx.instances)


def test_provider_commands_dispatch_expected_options(monkeypatch):
    calls = []

    async def record(site, **kwargs):
        calls.append((site, kwargs))
        return []

    monkeypatch.setattr(cli, "scrape", record)
    for argv in (
        [
            "indeed",
            "--query",
            "x",
            "--country",
            "usa",
            "--location",
            "Seattle",
            "--radius",
            "0",
            "--results",
            "3",
            "--max-age",
            "48",
        ],
        ["linkedin", "-q", "x", "-l", "Seattle", "--details", "--no-cache", "--geoid"],
        ["linkedin", "-q", "x", "--geoid", "12345"],
    ):
        monkeypatch.setattr(sys, "argv", ["jobrake", *argv])
        cli.main()

    assert calls == [
        (
            "indeed",
            {
                "query": "x",
                "location": "Seattle",
                "country": "usa",
                "radius": 0,
                "results": 3,
                "max_age_hours": 48,
                "details": defaults.DETAILS,
                "cache": defaults.CACHE,
                "geoid": defaults.GEOID,
            },
        ),
        (
            "linkedin",
            {
                "query": "x",
                "location": "Seattle",
                "country": None,
                "radius": defaults.LINKEDIN_RADIUS,
                "results": defaults.RESULTS,
                "max_age_hours": defaults.MAX_AGE_HOURS,
                "details": True,
                "cache": False,
                "geoid": True,
            },
        ),
        (
            "linkedin",
            {
                "query": "x",
                "location": None,
                "country": None,
                "radius": defaults.LINKEDIN_RADIUS,
                "results": defaults.RESULTS,
                "max_age_hours": defaults.MAX_AGE_HOURS,
                "details": defaults.DETAILS,
                "cache": defaults.CACHE,
                "geoid": "12345",
            },
        ),
    ]


def test_invalid_provider_arguments_fail_before_scraping(monkeypatch):
    async def must_not_run(*args, **kwargs):
        raise AssertionError("scrape ran without the required geography")

    monkeypatch.setattr(cli, "scrape", must_not_run)
    for argv in (
        ["indeed", "-q", "x"],
        ["linkedin", "-q", "x"],
        ["linkedin", "-q", "x", "--geoid"],
        ["linkedin", "-q", "x", "-l", "Seattle", "--detail"],
    ):
        monkeypatch.setattr(sys, "argv", ["jobrake", *argv])
        with pytest.raises(SystemExit):
            cli.main()


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


def test_no_jobs_leaves_output_untouched(run_cli, monkeypatch, tmp_path):
    async def no_jobs(*args, **kwargs):
        return []

    monkeypatch.setattr(cli, "scrape", no_jobs)
    out = tmp_path / "jobs.json"
    out.write_text("previous run", encoding="utf-8")
    run_cli("-o", str(out))
    assert out.read_text(encoding="utf-8") == "previous run"


def test_closed_pipe_ends_quietly(run_cli, monkeypatch):
    read_end, write_end = os.pipe()
    os.close(read_end)
    with open(write_end, "w") as stdout:
        monkeypatch.setattr(sys, "stdout", stdout)
        assert run_cli() == 1

    async def fake_places(fetcher, name):
        return [{"geoId": "1", "displayName": "A"}]

    monkeypatch.setattr(cli.linkedin, "places", fake_places)
    monkeypatch.setattr(sys, "argv", ["jobrake", "places", "linkedin", "a"])
    read_end, write_end = os.pipe()
    os.close(read_end)
    with open(write_end, "w") as stdout:
        monkeypatch.setattr(sys, "stdout", stdout)
        assert cli.main() == 1


def test_invalid_output_fails_before_scraping(run_cli, monkeypatch, tmp_path, capsys):
    async def must_not_run(*args, **kwargs):
        raise AssertionError("scrape ran despite a bad --output")

    monkeypatch.setattr(cli, "scrape", must_not_run)
    with pytest.raises(SystemExit):
        run_cli("-o", str(tmp_path / "jobs.xlsx"))
    with pytest.raises(SystemExit):
        run_cli("-o", str(tmp_path / "missing" / "jobs.json"))
    with pytest.raises(SystemExit):
        run_cli("-o", str(tmp_path))
    errors = capsys.readouterr().err
    assert "unsupported output extension" in errors
    assert "output directory does not exist" in errors
    assert "output path is a directory" in errors
    assert "usage:" not in errors
    assert errors.count("Run 'jobrake -h' for help.") == 3


def test_status_handler_progress():
    def emit(handler, msg, level=logging.INFO, progress=None, exc_info=None):
        record = logging.LogRecord("jobrake.test", level, __file__, 0, msg, None, exc_info)
        record.progress = progress
        handler.emit(record)

    class Tty(io.StringIO):
        def isatty(self):
            return True

    stream = Tty()
    handler = cli._StatusHandler(stream)
    emit(handler, "details", progress=(1, 2))
    emit(handler, "failed", level=logging.ERROR, exc_info=(ValueError, ValueError("bad"), None))
    emit(handler, "details", progress=(2, 2))
    handler.clear()

    out = stream.getvalue()
    # Each erase sequence replaces the preceding terminal frame.
    frames = out.split("\r\x1b[2K")
    assert "#" in frames[0]  # a bar, not merely a counter
    assert "1/2" in frames[0]
    assert "ERROR failed" in frames[1]
    assert "ValueError: bad" in frames[1]
    assert "2/2" in frames[1]
    assert frames[2] == ""  # clear() erased the last bar
    handler.clear()  # a second clear writes nothing
    assert stream.getvalue() == out

    # A non-terminal stream keeps ordinary records and drops progress.
    plain = io.StringIO()
    handler = cli._StatusHandler(plain)
    emit(handler, "details", progress=(1, 2))
    emit(handler, "finished")
    assert "1/2" not in plain.getvalue()
    assert "finished" in plain.getvalue()


def test_output_write_error_reports_and_fails(run_cli, monkeypatch, tmp_path, caplog):
    def deny_write(*args, **kwargs):
        raise PermissionError("permission denied")

    monkeypatch.setattr(Path, "write_text", deny_write)
    out = tmp_path / "jobs.json"
    assert run_cli("-o", str(out)) == 1
    assert f"could not write {out}: permission denied" in caplog.text
