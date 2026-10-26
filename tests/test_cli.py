"""CLI commands built from the sites, their exit codes, and output to stdout and files."""

import csv
import io
import json
import logging
import os
import sys
from pathlib import Path

import pytest
from fakes import StubFetcher

from jobrake import Stopped, cli, sites
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
        language="en",
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


def test_a_registered_site_gets_every_command_without_a_cli_change(
    fake_site, fetchers, monkeypatch, capsys
):
    # The site's signatures alone give its search, lookup, and posting commands.
    search = ["fakesite", "-q", "x", "--board", "acme", "--tags", "a", "b", "--remote", "-n", "2"]
    monkeypatch.setattr(sys, "argv", ["jobrake", *search])
    assert cli.main() is None
    assert [job["id"] for job in json.loads(capsys.readouterr().out)] == ["0", "1"]
    monkeypatch.setattr(sys, "argv", ["jobrake", "places", "fakesite", "Utrecht", "--region", "NL"])
    assert cli.main() is None
    assert json.loads(capsys.readouterr().out) == [{"id": "1", "name": "Utrecht"}]
    monkeypatch.setattr(sys, "argv", ["jobrake", "postings", "fakesite", "7", "--refresh"])
    assert cli.main() is None
    assert [job["id"] for job in json.loads(capsys.readouterr().out)] == ["7"]
    assert fake_site.calls == [
        {"query": "x", "board": "acme", "results": 2, "remote": True, "tags": ["a", "b"]},
        {"name": "Utrecht", "region": "NL"},
        {"references": ["7"], "refresh": True},
    ]


@pytest.fixture
def fetchers(monkeypatch):
    """Replace the CLI's own HttpxFetcher with a stub that records each one it creates."""
    created = []

    class StubHttpx:
        def __init__(self):
            self.closed = False
            created.append(self)

        async def close(self):
            self.closed = True

    monkeypatch.setattr(cli, "HttpxFetcher", StubHttpx)
    return created


@pytest.mark.parametrize(
    ("name", "status", "out", "err"),
    [
        ("Utrecht", None, [{"id": "1", "name": "Utrecht"}], ""),
        ("nowhere", None, [], "no places found for 'nowhere'"),
        ("offline", 1, None, "place lookup failed: connection reset"),
    ],
)
def test_a_lookup_prints_its_candidates_or_fails(
    fake_site, fetchers, monkeypatch, capsys, caplog, name, status, out, err
):
    monkeypatch.setattr(sys, "argv", ["jobrake", "places", "fakesite", name])
    assert cli.main() == status
    printed = capsys.readouterr().out
    assert (json.loads(printed) if printed else None) == out  # a failure prints nothing
    assert err in caplog.text
    assert [fetcher.closed for fetcher in fetchers] == [True]
    monkeypatch.setattr(sys, "argv", ["jobrake", "places", "fakesite", " "])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2


def test_postings_command_renders_what_it_fetched(fake_site, fetchers, monkeypatch, capsys, caplog):
    # two references to one posting, one gone, one failed and so absent
    references = ["1", "https://fake.test/1", "gone", "failed"]
    monkeypatch.setattr(sys, "argv", ["jobrake", "postings", "fakesite", *references])
    assert cli.main() is None
    assert json.loads(capsys.readouterr().out) == [fake_site.job("1")]  # one record per posting
    assert "gone is no longer on fakesite" in caplog.text
    # nothing fetched: the failures were already reported, so stdout stays empty
    monkeypatch.setattr(sys, "argv", ["jobrake", "postings", "fakesite", "failed"])
    assert cli.main() == 1
    assert capsys.readouterr().out == ""
    assert all(fetcher.closed for fetcher in fetchers)


def test_site_commands_dispatch_their_options(monkeypatch):
    calls = []

    async def record(site, **kwargs):
        calls.append((site, kwargs))
        return []

    monkeypatch.setattr(cli, "scrape", record)
    for argv in (
        ["indeed", "--query", "x", "--country", "usa", "--location", "Seattle", "--radius", "0"],
        ["indeed", "-q", "x", "-c", "usa", "-l", "Seattle", "-r", "0", "-n", "3", "-a", "48"],
        ["indeed", "-q", "x", "-c", "usa", "--company-ids", "fe21", "--remote"],
        ["indeed", "-q", "x", "-c", "usa", "--language", "EN", "--attributes", "3CQB7", "6QC5F"],
        ["linkedin", "-q", "x", "-l", "Seattle", "-d", "--refresh", "--easy-apply"],
        ["linkedin", "-q", "", "-g", "12345", "--company-ids", "1173", "--company-ids", "2220078"],
        ["linkedin", "-q", "x", "-l", "Seattle", "--early-applicant", "--max-age-hours", "24"],
    ):
        monkeypatch.setattr(sys, "argv", ["jobrake", *argv])
        cli.main()

    # Each site receives the options given on its command line, and its search
    # supplies the rest.
    assert calls == [
        ("indeed", {"query": "x", "country": "usa", "location": "Seattle", "radius": 0}),
        (
            "indeed",
            {
                "query": "x",
                "country": "usa",
                "location": "Seattle",
                "radius": 0,
                "results": 3,
                "max_age_hours": 48,
            },
        ),
        ("indeed", {"query": "x", "country": "usa", "company_ids": ["fe21"], "remote": True}),
        (
            "indeed",
            {"query": "x", "country": "usa", "language": "EN", "attributes": ["3CQB7", "6QC5F"]},
        ),
        (
            "linkedin",
            {
                "query": "x",
                "location": "Seattle",
                "details": True,
                "refresh": True,
                "easy_apply": True,
            },
        ),
        ("linkedin", {"query": "", "geoid": "12345", "company_ids": ["1173", "2220078"]}),
        (
            "linkedin",
            {"query": "x", "location": "Seattle", "early_applicant": True, "max_age_hours": 24},
        ),
    ]


def test_invalid_site_arguments_fail_before_scraping(monkeypatch):
    async def must_not_run(*args, **kwargs):
        raise AssertionError("scrape ran with invalid CLI arguments")

    monkeypatch.setattr(cli, "scrape", must_not_run)
    for argv in (
        ["indeed", "-q", "x"],
        ["indeed", "-q", "x", "-c", "usa", "--easy-apply"],
        ["companies", "indeed", "ABN AMRO"],
        ["attributes", "linkedin", "data scientist"],
        ["linkedin", "-q", "x", "-l", "Seattle", "--attributes", "3CQB7"],
        ["linkedin", "-q", "x", "-l", "Seattle", "--detail"],
        ["linkedin", "-q", "x", "-l", "Seattle", "--country", "usa"],
    ):
        monkeypatch.setattr(sys, "argv", ["jobrake", *argv])
        with pytest.raises(SystemExit):
            cli.main()


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["linkedin"], "location is required without a geoid"),
        (["indeed", "-c", "atlantis"], "unknown Indeed country 'atlantis'"),
    ],
)
def test_a_search_the_library_rejects_is_a_cli_error_before_any_request(
    monkeypatch, capsys, argv, message
):
    fetcher = StubFetcher({})
    monkeypatch.setattr(sites, "HttpxFetcher", lambda: fetcher)
    monkeypatch.setattr(sys, "argv", ["jobrake", *argv, "-q", ""])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    assert message in capsys.readouterr().err
    assert fetcher.requests == []


def test_default_output_is_json_on_stdout(run_cli, capsys):
    run_cli()
    assert json.loads(capsys.readouterr().out) == JOBS


def test_a_stopped_search_writes_what_it_collected_and_fails(run_cli, monkeypatch, capsys, caplog):
    async def stopped(*args, **kwargs):
        raise Stopped("indeed search stopped: HTTP 429", partial=JOBS[:1])

    monkeypatch.setattr(cli, "scrape", stopped)
    assert run_cli() == 1
    assert json.loads(capsys.readouterr().out) == JOBS[:1]
    assert "indeed search stopped: HTTP 429" in caplog.text


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
        {name: "" if (value := job.get(name)) is None else str(value) for name in JOB_FIELDS}
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


def test_no_jobs_does_not_create_output(run_cli, monkeypatch, tmp_path):
    async def no_jobs(*args, **kwargs):
        return []

    monkeypatch.setattr(cli, "scrape", no_jobs)
    out = tmp_path / "jobs.json"
    run_cli("-o", str(out))
    assert not out.exists()


def test_closed_pipe_ends_quietly(run_cli, fake_site, monkeypatch):
    read_end, write_end = os.pipe()
    os.close(read_end)
    with os.fdopen(write_end, "w") as stdout:
        monkeypatch.setattr(sys, "stdout", stdout)
        assert run_cli() == 1

    monkeypatch.setattr(sys, "argv", ["jobrake", "places", "fakesite", "a"])
    read_end, write_end = os.pipe()
    os.close(read_end)
    with os.fdopen(write_end, "w") as stdout:
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
    existing = tmp_path / "jobs.json"
    existing.write_text("previous run", encoding="utf-8")
    with pytest.raises(SystemExit):
        run_cli("-o", str(existing))
    # Exclusive creation refuses a dangling symlink, and a read-only directory
    # refuses any new file. Either would cost a finished scrape its results.
    dangling = tmp_path / "dangling.json"
    dangling.symlink_to(tmp_path / "nowhere.json")
    with pytest.raises(SystemExit):
        run_cli("-o", str(dangling))
    locked = tmp_path / "locked"
    locked.mkdir(mode=0o555)
    with pytest.raises(SystemExit):
        run_cli("-o", str(locked / "jobs.json"))
    errors = capsys.readouterr().err
    assert "unsupported output extension" in errors
    assert "output directory does not exist" in errors
    assert "output path is a directory" in errors
    assert f"output file already exists: {existing}" in errors
    assert f"output file already exists: {dangling}" in errors
    assert f"output directory is not writable: {locked}" in errors
    assert "usage:" not in errors
    assert errors.count("Run 'jobrake -h' for help.") == 6


def test_status_handler_progress():
    def emit(handler, msg, level=logging.INFO, progress=None, exc_info=None):
        record = logging.LogRecord("jobrake.test", level, __file__, 0, msg, None, exc_info)
        record.progress = progress
        handler.emit(record)

    class Tty(io.StringIO):
        def isatty(self):
            return True

    stream = Tty()
    handler = cli._StatusHandler(stream)  # noqa: SLF001  the handler is the unit under test; the CLI only wires it
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
    handler = cli._StatusHandler(plain)  # noqa: SLF001  the handler is the unit under test; the CLI only wires it
    emit(handler, "details", progress=(1, 2))
    emit(handler, "finished")
    assert "1/2" not in plain.getvalue()
    assert "finished" in plain.getvalue()


def test_output_write_error_reports_and_fails(run_cli, monkeypatch, tmp_path, caplog):
    def deny_write(*args, **kwargs):
        raise PermissionError("permission denied")

    monkeypatch.setattr(Path, "open", deny_write)
    out = tmp_path / "jobs.json"
    assert run_cli("-o", str(out)) == 1
    assert f"could not write {out}: permission denied" in caplog.text
