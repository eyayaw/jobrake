"""CLI commands built from the sites, their exit codes, and output to stdout and files."""

import csv
import functools
import io
import json
import logging
import os
import shlex
import signal
import subprocess
import sys
import types
from pathlib import Path

import pytest
from fakes import StubFetcher

from jobrake import Stopped, cli
from jobrake.models import JOB_FIELDS, make_job
from jobrake.sites import SITES

JOBS = [
    make_job(
        id="1",
        title='Economist, "Senior"',
        company="Acme, Inc.",
        url="https://example.com/1",
        site="indeed",
        locations=[{"name": "Seattle, WA", "city": "Seattle"}, {"name": "Portland, OR"}],
        site_data={"team": "Économie", "levels": ["Senior"]},
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
        locations=[{"name": "Remote"}],
    ),
]


@pytest.fixture
def fetchers(monkeypatch):
    """Replace the CLI's own HttpxFetcher with a stub that records each one it creates."""
    created = []

    class StubHttpx(StubFetcher):
        def __init__(self):
            super().__init__({})
            created.append(self)

    monkeypatch.setattr(cli, "HttpxFetcher", StubHttpx)
    return created


@pytest.fixture
def stub_search(monkeypatch, fetchers):
    """
    Replace a site's search with a stub that keeps its signature and records its options.

    The stub returns ``result``, or raises it when it is an exception.
    """
    calls = []

    def stub(site, result):
        @functools.wraps(SITES[site].search)
        async def search(fetcher, **options):
            calls.append((site, options))
            if isinstance(result, BaseException):
                raise result
            return result

        monkeypatch.setattr(SITES[site], "search", search)
        return calls

    return stub


@pytest.fixture
def run_cli(monkeypatch, stub_search):
    """Run ``cli.main()`` with an Indeed search that returns ``JOBS``."""
    stub_search("indeed", JOBS)

    def run(*argv):
        monkeypatch.setattr(
            "sys.argv", ["jobrake", "indeed", "search", "-q", "x", "-c", "us", *argv]
        )
        return cli.main()

    return run


def test_a_registered_site_gets_every_command_without_a_cli_change(
    fake_site, fetchers, monkeypatch, capsys
):
    # The site's signatures alone give its search, lookup, and posting commands.
    # A submodule the site does not export, such as companies.py, adds none.
    monkeypatch.setattr(fake_site, "companies", types.ModuleType("companies"), raising=False)
    search = shlex.split("fakesite search -q x --board acme --tags a b --remote -n 2")
    monkeypatch.setattr(sys, "argv", ["jobrake", *search])
    assert cli.main() is None
    assert [job["id"] for job in json.loads(capsys.readouterr().out)] == ["0", "1"]
    monkeypatch.setattr(sys, "argv", ["jobrake", "fakesite", "places", "Utrecht", "--region", "NL"])
    assert cli.main() is None
    assert json.loads(capsys.readouterr().out) == [{"id": "1", "name": "Utrecht"}]
    monkeypatch.setattr(sys, "argv", ["jobrake", "fakesite", "postings", "7"])
    assert cli.main() is None
    assert [job["id"] for job in json.loads(capsys.readouterr().out)] == ["7"]
    assert fake_site.calls == [
        {"query": "x", "board": "acme", "results": 2, "remote": True, "tags": ["a", "b"]},
        {"name": "Utrecht", "region": "NL"},
        {"references": ["7"]},
    ]


def test_a_list_option_shows_value_in_its_help(fake_site, monkeypatch, capsys):
    # A list option takes names, codes, or IDs, depending on the site.
    monkeypatch.setattr(sys, "argv", ["jobrake", "fakesite", "search", "-h"])
    with pytest.raises(SystemExit):
        cli.main()
    assert "--tags VALUE [VALUE ...]" in capsys.readouterr().out


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
    monkeypatch.setattr(sys, "argv", ["jobrake", "fakesite", "places", name])
    assert cli.main() == status
    printed = capsys.readouterr().out
    assert (json.loads(printed) if printed else None) == out  # a failure prints nothing
    assert err in caplog.text
    assert [fetcher.closed for fetcher in fetchers] == [1]
    monkeypatch.setattr(sys, "argv", ["jobrake", "fakesite", "places", " "])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2


@pytest.mark.parametrize(
    ("references", "written", "status"),
    [
        # two references to one posting, one gone, and one whose request failed
        (["1", "https://fake.test/1", "gone", "failed"], ["1"], 1),
        (["gone"], [], None),  # a gone posting is no failure
        (["1"], ["1"], None),
    ],
)
def test_postings_command_writes_what_it_fetched_and_fails_on_a_failed_reference(
    fake_site, fetchers, monkeypatch, capsys, caplog, references, written, status
):
    monkeypatch.setattr(sys, "argv", ["jobrake", "fakesite", "postings", *references])
    assert cli.main() == status
    assert json.loads(capsys.readouterr().out) == [fake_site.job(n) for n in written]
    assert ("gone is no longer on fakesite" in caplog.text) == ("gone" in references)
    assert all(fetcher.closed for fetcher in fetchers)


def test_site_commands_dispatch_their_options(monkeypatch, stub_search):
    stub_search("indeed", [])
    calls = stub_search("linkedin", [])
    # Together the lines use every short flag the two sites declare.
    for argv in (
        "indeed search -q x -c us -l Seattle -r 0 -n 3 -a 48 --remote --language EN"
        " --attributes 3CQB7 6QC5F",
        "indeed search --query x --country us --company-ids fe21",
        'linkedin search -q "" -g 12345 --company-ids 1173 --company-ids 2220078 -d --easy-apply',
        "linkedin search -q x -l Seattle --early-applicant --max-age-hours 24",
    ):
        monkeypatch.setattr(sys, "argv", ["jobrake", *shlex.split(argv)])
        cli.main()

    # Each site receives the options given on its command line, and its search supplies the rest.
    assert calls == [
        (
            "indeed",
            {
                "query": "x",
                "country": "us",
                "location": "Seattle",
                "radius": 0,
                "results": 3,
                "max_age_hours": 48,
                "remote": True,
                "language": "EN",
                "attributes": ["3CQB7", "6QC5F"],
            },
        ),
        ("indeed", {"query": "x", "country": "us", "company_ids": ["fe21"]}),
        (
            "linkedin",
            {
                "query": "",
                "geoid": "12345",
                "company_ids": ["1173", "2220078"],
                "details": True,
                "easy_apply": True,
            },
        ),
        (
            "linkedin",
            {"query": "x", "location": "Seattle", "early_applicant": True, "max_age_hours": 24},
        ),
    ]


def test_invalid_site_arguments_fail_before_scraping(monkeypatch, stub_search):
    for site in ("indeed", "linkedin"):
        stub_search(site, AssertionError("search ran with invalid CLI arguments"))
    for argv in (
        ["indeed", "search", "-q", "x"],
        ["indeed", "search", "-q", "x", "-c", "us", "--easy-apply"],
        ["indeed", "companies", "ABN AMRO"],
        ["linkedin", "attributes", "data scientist"],
        ["linkedin", "search", "-q", "x", "-l", "Seattle", "--attributes", "3CQB7"],
        ["linkedin", "search", "-q", "x", "-l", "Seattle", "--detail"],
        ["linkedin", "search", "-q", "x", "-l", "Seattle", "--country", "usa"],
    ):
        monkeypatch.setattr(sys, "argv", ["jobrake", *argv])
        with pytest.raises(SystemExit) as error:
            cli.main()
        assert error.value.code == 2


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["linkedin", "search"], "location is required without a geoid"),
        (["indeed", "search", "-c", "atlantis"], "unknown Indeed country 'atlantis'"),
    ],
)
def test_a_search_the_library_rejects_is_a_cli_error_before_any_request(
    monkeypatch, capsys, argv, message
):
    fetcher = StubFetcher({})
    monkeypatch.setattr(cli, "HttpxFetcher", lambda: fetcher)
    monkeypatch.setattr(sys, "argv", ["jobrake", *argv])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    assert message in capsys.readouterr().err
    assert fetcher.requests == []


def test_a_stopped_search_writes_what_it_collected_and_fails(run_cli, stub_search, capsys, caplog):
    stub_search("indeed", Stopped("indeed request failed: HTTP 429", partial=JOBS[:1]))
    assert run_cli() == 1
    assert json.loads(capsys.readouterr().out) == JOBS[:1]
    assert "indeed request failed: HTTP 429" in caplog.text

    stub_search("indeed", Stopped("indeed request failed: HTTP 429"))
    assert run_cli() == 1
    assert capsys.readouterr().out == ""


def test_a_stopped_details_search_names_the_command_that_retries(stub_search, monkeypatch, caplog):
    failed = [
        "https://www.linkedin.com/jobs/view/111",
        "https://www.linkedin.com/jobs/view/222?x=1",
    ]
    stub_search("linkedin", Stopped("details failed", partial=JOBS[:1], failed=failed))
    monkeypatch.setattr("sys.argv", ["jobrake", "linkedin", "search", "-l", "Berlin", "--details"])
    assert cli.main() == 1
    assert (
        "retry with: jobrake linkedin postings https://www.linkedin.com/jobs/view/111 "
        "'https://www.linkedin.com/jobs/view/222?x=1'"
    ) in caplog.text


def test_ctrl_c_ends_the_run_with_one_line_and_dies_of_sigint(
    run_cli, stub_search, monkeypatch, capsys, caplog
):
    # A shell stops a loop only when the command it ran died of the signal.
    sent = []
    monkeypatch.setattr(signal, "signal", lambda number, action: sent.append((number, action)))
    monkeypatch.setattr(os, "kill", lambda pid, number: sent.append((pid, number)))
    stub_search("indeed", KeyboardInterrupt())
    assert run_cli() == 130
    # asyncio.run sets its own SIGINT handler first, so only the last two calls are the CLI's.
    assert sent[-2:] == [(signal.SIGINT, signal.SIG_DFL), (os.getpid(), signal.SIGINT)]
    assert capsys.readouterr().out == ""
    assert [record.getMessage() for record in caplog.records] == [
        "interrupted, so the output is missing or cut short"
    ]


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
        reader = csv.DictReader(f)
        rows = list(reader)
    assert reader.fieldnames == list(JOB_FIELDS)
    # Unavailable summaries and absent details read back as empty cells, the places as their names,
    # and the site's own fields as JSON.
    nested = [
        {
            "locations": "Seattle, WA; Portland, OR",
            "site_data": '{"team": "Économie", "levels": ["Senior"]}',
        },
        {"locations": "Remote", "site_data": ""},
    ]
    expected = [
        {name: "" if (value := job.get(name)) is None else str(value) for name in JOB_FIELDS}
        | cells
        for job, cells in zip(JOBS, nested, strict=True)
    ]
    assert rows == expected
    assert capsys.readouterr().out == ""  # File output leaves stdout silent.


@pytest.mark.parametrize(
    ("name", "read"),
    [
        ("jobs.json", json.loads),
        # The extension picks the format whatever its case. A leaked raw newline in a description
        # would break the per-line parse.
        ("jobs.JSONL", lambda text: [json.loads(line) for line in text.splitlines()]),
    ],
)
def test_output_file_takes_the_format_its_extension_names(run_cli, tmp_path, name, read):
    out = tmp_path / name
    run_cli("-o", str(out))
    assert read(out.read_text(encoding="utf-8")) == JOBS


def test_no_jobs_does_not_create_output(run_cli, stub_search, tmp_path):
    stub_search("indeed", [])
    out = tmp_path / "jobs.json"
    run_cli("-o", str(out))
    assert not out.exists()


def test_closed_pipe_ends_quietly(run_cli, fake_site, monkeypatch, caplog):
    read_end, write_end = os.pipe()
    os.close(read_end)
    with os.fdopen(write_end, "w") as stdout:
        monkeypatch.setattr(sys, "stdout", stdout)
        assert run_cli() == 1

    monkeypatch.setattr(sys, "argv", ["jobrake", "fakesite", "places", "a"])
    read_end, write_end = os.pipe()
    os.close(read_end)
    with os.fdopen(write_end, "w") as stdout:
        monkeypatch.setattr(sys, "stdout", stdout)
        assert cli.main() == 1
    assert "could not write" not in caplog.text


class _FullDisk(io.StringIO):
    def write(self, text):
        raise OSError(28, "No space left on device")


@pytest.mark.parametrize(
    ("stdout", "error"),
    [
        (_FullDisk, "[Errno 28] No space left on device"),
        # PYTHONIOENCODING=ascii sets such a stdout, which cannot encode the É in JOBS.
        (lambda: io.TextIOWrapper(io.BytesIO(), encoding="ascii"), "'ascii' codec can't encode"),
    ],
)
def test_a_stdout_write_error_reports_and_fails(stdout, error, run_cli, monkeypatch, caplog):
    monkeypatch.setattr(sys, "stdout", stdout())
    assert run_cli() == 1
    assert f"could not write stdout: {error}" in caplog.text


@pytest.mark.parametrize(("crash", "status", "written"), [(False, 0, 3), (True, 1, 0)])
def test_a_closed_stderr_leaves_the_exit_status_of_a_run_or_a_crash(
    tmp_path, crash, status, written
):
    # A real process, because a failed stderr write surfaces in the flush at interpreter exit.
    code = (
        "import fakesite, sys\n"
        "from jobrake import cli, sites\n"
        "sites.SITES['fakesite'] = fakesite\n"
        f"cli.HttpxFetcher = {'None' if crash else 'cli.HttpxFetcher'}\n"
        "sys.argv = ['jobrake', 'fakesite', 'search', '-q', 'x', '-n', '3']\n"
        "raise SystemExit(cli.main())\n"
    )
    env = os.environ | {
        "PYTHONPATH": str(Path(__file__).parent),
        "JOBRAKE_CACHE_PATH": str(tmp_path / "jobrake.sqlite3"),
    }
    read_end, write_end = os.pipe()
    os.close(read_end)
    with (tmp_path / "jobs.json").open("w") as stdout:
        done = subprocess.run(
            [sys.executable, "-c", code], env=env, stdout=stdout, stderr=write_end, check=False
        )
    os.close(write_end)
    assert done.returncode == status
    output = (tmp_path / "jobs.json").read_text(encoding="utf-8")
    assert len(json.loads(output or "[]")) == written


_CLI = [sys.executable, "-m", "jobrake.cli"]
_CLOSED_BY_CALLER = (
    "import sys\nfrom jobrake import cli\nsys.argv = ['jobrake', '--version']\n"
    "try:\n    cli.main()\nexcept SystemExit:\n    sys.stdout.close()\n"
)
_BARE_STDOUT = (
    "import sys\nfrom jobrake import cli\n"
    # A pipe that fails once, in the exit hook's flush, which must not need fileno to silence it.
    "class Sink:\n    failed = False\n    def write(self, text): return len(text)\n"
    "    def flush(self):\n        if not Sink.failed:\n"
    "            Sink.failed = True\n            raise BrokenPipeError\n"
    "sys.stdout = Sink()\nsys.argv = ['jobrake', '--version']\n"
    "try:\n    cli.main()\nexcept SystemExit:\n    pass\n"
)


@pytest.mark.parametrize(
    ("command", "dead_pipe", "status"),
    [
        ([*_CLI, "-h"], "stdout", 0),
        ([*_CLI, "bogus"], "stderr", 2),
        (["sh", "-c", 'exec "$@" >&-', "sh", *_CLI, "-h"], None, 0),  # Python makes stdout None
        ([sys.executable, "-c", _CLOSED_BY_CALLER], None, 0),  # a program embedding the CLI
        ([sys.executable, "-c", _BARE_STDOUT], None, 0),  # a stdout without closed or fileno
    ],
)
def test_a_closed_stream_leaves_the_exit_status_and_stderr_clean(command, dead_pipe, status):
    # A real process, because argparse's output fails in the flush at interpreter exit, and an
    # error in an exit hook shows only on stderr.
    read_end, write_end = os.pipe()
    os.close(read_end)
    stdout = write_end if dead_pipe == "stdout" else subprocess.DEVNULL
    stderr = write_end if dead_pipe == "stderr" else subprocess.PIPE
    done = subprocess.run(command, stdout=stdout, stderr=stderr, check=False)
    os.close(write_end)
    assert done.returncode == status
    assert b"Exception ignored" not in (done.stderr or b"")


def test_invalid_output_fails_before_scraping(run_cli, stub_search, tmp_path, capsys):
    stub_search("indeed", AssertionError("search ran despite a bad --output"))
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
    # Exclusive creation refuses a dangling symlink, and a read-only directory refuses any new file.
    # Either would cost a finished scrape its results.
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
    assert errors.count("Run 'jobrake indeed search -h' for help.") == 6


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
    emit(handler, "site details 1/2", progress=(1, 2))
    emit(handler, "failed", level=logging.ERROR, exc_info=(ValueError, ValueError("bad"), None))
    emit(handler, "site details 2/2", progress=(2, 2))
    handler.clear()

    out = stream.getvalue()
    # Each erase sequence replaces the preceding terminal frame.
    frames = out.split("\r\x1b[2K")
    assert frames[0] == "site details 1/2"
    assert "ERROR failed" in frames[1]
    assert "ValueError: bad" in frames[1]
    assert frames[1].endswith("\nsite details 2/2")
    assert frames[2] == ""  # clear() erased the last bar
    handler.clear()  # a second clear writes nothing
    assert stream.getvalue() == out

    # A non-terminal stream keeps ordinary records and drops progress.
    plain = io.StringIO()
    handler = cli._StatusHandler(plain)  # noqa: SLF001  the handler is the unit under test; the CLI only wires it
    emit(handler, "site details 1/2", progress=(1, 2))
    emit(handler, "finished")
    assert "1/2" not in plain.getvalue()
    assert "finished" in plain.getvalue()


def test_an_output_file_that_open_refused_stays(run_cli, monkeypatch, tmp_path, caplog):
    out = tmp_path / "jobs.json"

    def taken(path, *args, **kwargs):
        # Another process creates the file between the command's check and its open.
        with open(path, "wb") as other:  # noqa: PTH123  Path.open is patched
            other.write(b"another run")
        raise FileExistsError(f"[Errno 17] File exists: '{path}'")

    monkeypatch.setattr(Path, "open", taken)
    assert run_cli("-o", str(out)) == 1
    assert f"could not write {out}: [Errno 17] File exists" in caplog.text
    with open(out, "rb") as kept:  # noqa: PTH123  Path.open is patched
        assert kept.read() == b"another run"


@pytest.fixture
def cut_write(monkeypatch):
    """Make an ``--output`` write take its first bytes and then raise the given exception."""
    real_open = Path.open

    def cut(error):
        class Cut:
            def __init__(self, file):
                self.file = file

            def __enter__(self):
                return self

            def __exit__(self, *_):
                self.file.close()

            def write(self, text):
                self.file.write(text[:10])
                self.file.flush()
                raise error

        monkeypatch.setattr(Path, "open", lambda path, *a, **k: Cut(real_open(path, *a, **k)))

    return cut


@pytest.mark.parametrize(
    ("error", "status", "message"),
    [
        (OSError(28, "No space left on device"), 1, "could not write {out}: [Errno 28] No space"),
        (KeyboardInterrupt(), 130, "interrupted, so the output is missing or cut short"),
    ],
)
def test_a_write_cut_short_removes_the_file_it_created(
    error, status, message, run_cli, cut_write, monkeypatch, tmp_path, caplog
):
    monkeypatch.setattr(signal, "signal", lambda *_: None)
    monkeypatch.setattr(os, "kill", lambda *_: None)
    out = tmp_path / "jobs.json"
    cut_write(error)
    assert run_cli("-o", str(out)) == status
    assert message.format(out=out) in caplog.text
    assert not out.exists()


def test_a_cut_short_file_that_cannot_be_removed_stays_with_a_warning(
    run_cli, cut_write, monkeypatch, tmp_path, caplog
):
    def refuse(*_):
        raise PermissionError(13, "Permission denied")

    out = tmp_path / "jobs.json"
    cut_write(OSError(28, "No space left on device"))
    monkeypatch.setattr(Path, "unlink", refuse)
    assert run_cli("-o", str(out)) == 1
    assert out.exists()
    assert f"could not remove {out}: [Errno 13] Permission denied. Delete it" in caplog.text
