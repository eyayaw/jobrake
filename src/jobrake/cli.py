"""Command-line search and output dispatch, built from each site's signatures."""

import argparse
import asyncio
import inspect
import json
import logging
import os
import signal
import sys
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from gettext import ngettext
from pathlib import Path
from types import ModuleType
from typing import Any, Never, TextIO, override

from jobrake import __version__

from .fetchkit import HttpxFetcher
from .io import RENDERERS
from .models import JobDict, Stopped
from .sites import SITES
from .utils import site_options

logger = logging.getLogger(__name__)

_CLEAR_LINE = "\r\x1b[2K"


class _ArgumentParser(argparse.ArgumentParser):
    """Report parse errors without repeating the full usage line."""

    @override
    def error(self, message: str) -> Never:
        self.exit(2, f"{self.prog}: error: {message}\nRun '{self.prog} -h' for help.\n")


class _StatusHandler(logging.StreamHandler[TextIO]):
    """
    Stderr handler with terse prefixes and a terminal progress line.

    A record logged with ``extra={"progress": (done, total)}`` rewrites the
    current terminal line with its message; ordinary records erase that line
    first, so warnings landing mid-fetch stay legible. A non-terminal stderr
    skips progress records and receives no control codes.
    """

    _showing_progress = False

    @override
    def format(self, record: logging.LogRecord) -> str:
        head = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created))
        if record.levelno > logging.INFO:
            head += f" {record.levelname}"
        if record.name.partition(".")[0] != "jobrake":
            head += f" [{record.name}]"
        line = f"{head} {record.getMessage()}"
        if record.exc_info:
            line += "\n" + logging.Formatter().formatException(record.exc_info)
        return line

    @override
    def emit(self, record: logging.LogRecord) -> None:
        progress = getattr(record, "progress", None)
        try:
            self.clear()
            if not progress:
                super().emit(record)
            elif self.stream.isatty():
                # Flag first, so clear() erases even an interrupted write.
                self._showing_progress = True
                self.stream.write(record.getMessage())
                self.flush()
        except Exception:  # noqa: BLE001  Handler.emit must not raise; handleError reports it
            self.handleError(record)

    def clear(self) -> None:
        """Erase the status line so a traceback starts on its own line."""
        if self._showing_progress:
            self._showing_progress = False
            # Cleanup failures must not replace the original exception.
            with suppress(Exception):
                self.stream.write(_CLEAR_LINE)
                self.flush()


# Short flags for common option names, whichever site declares them.
_SHORT_FLAGS = {
    "query": "-q",
    "location": "-l",
    "country": "-c",
    "radius": "-r",
    "results": "-n",
    "max_age_hours": "-a",
    "geoid": "-g",
    "details": "-d",
    "board": "-b",
}

# The functions a site may export, each a command of that site, in help order.
COMMANDS = ("search", "postings", "places", "companies", "attributes")
# The commands that write postings, and so take --output and --format. The
# lookups print their candidates as JSON.
_WRITES_POSTINGS = ("search", "postings")


def _add_parser(
    add_parser: Callable[..., argparse.ArgumentParser],
    name: str,
    target: Callable[..., object] | ModuleType,
) -> argparse.ArgumentParser:
    """Add a subcommand described by the first line of ``target``'s docstring."""
    line = (inspect.getdoc(target) or "").splitlines()[0]
    help_text = line[:1].lower() + line[1:].removesuffix(".")
    return add_parser(name, allow_abbrev=False, help=help_text, description=line)


def _add_arguments(parser: argparse.ArgumentParser, function: Callable[..., object]) -> None:
    """
    Add one argument per argument of a site function after the fetcher.

    The text a lookup or ``postings`` takes first becomes a positional
    argument, and each keyword option a flag named after it.
    """
    for name, option in site_options(function).items():
        if option.positional:
            many: dict[str, Any] = {"nargs": "+"} if option.kind is not str else {}
            parser.add_argument(name, metavar=name.upper(), help=option.help, **many)
            continue
        flags = [f"--{name.replace('_', '-')}"]
        if name in _SHORT_FLAGS:
            flags.append(_SHORT_FLAGS[name])
        required = option.default is inspect.Parameter.empty
        help_text = option.help
        if option.default not in (None, False, "", inspect.Parameter.empty):
            help_text += f" (default: {option.default})"
        # An omitted flag leaves the option to the site function's own default.
        settings: dict[str, Any] = {"default": argparse.SUPPRESS, "help": help_text}
        if option.kind is bool:
            settings["action"] = "store_true"
        elif option.kind == list[str]:
            settings |= {"action": "extend", "nargs": "+", "metavar": "ID"}
        elif option.kind is int:
            settings["type"] = int
        parser.add_argument(*flags, dest=name, required=required, **settings)


def _build_parser() -> _ArgumentParser:
    parser = _ArgumentParser(
        prog="jobrake", description="Find and fetch job postings", allow_abbrev=False
    )
    # The version action exits before argparse checks the required subcommand.
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sites = parser.add_subparsers(dest="site", required=True)
    for site, module in SITES.items():
        commands = _add_parser(sites.add_parser, site, module).add_subparsers(
            dest="command", required=True
        )
        for name in (name for name in COMMANDS if name in module.__all__):
            function = getattr(module, name)
            command = _add_parser(commands.add_parser, name, function)
            # main() reports an error it finds after parsing through this
            # parser, so the message names the command and its help.
            command.set_defaults(command_parser=command)
            _add_arguments(command, function)
            if name not in _WRITES_POSTINGS:
                continue
            command.add_argument(
                "--output", "-o", type=Path, help="write results to a new file instead of stdout"
            )
            command.add_argument(
                "--format",
                "-f",
                choices=list(RENDERERS),
                help="output format. Defaults to the --output extension or JSON for stdout",
            )
    return parser


def _write_stdout(text: str) -> int | None:
    """
    Write a command's data output to stdout.

    Returns:
        ``1`` when the downstream reader has closed the pipe. ``None`` otherwise.
    """
    try:
        sys.stdout.write(text)
        # Flush now: when the output fits the pipe buffer, a closed pipe
        # would otherwise surface at interpreter exit, past this handler.
        sys.stdout.flush()
    except BrokenPipeError:
        # The downstream reader (e.g. `jobrake ... | head`) stopped early.
        # Keep this handler local. SIGPIPE, signal(SIGPIPE, SIG_DFL),
        # works only on Unix and changes signal handling for the whole process.
        # Point stdout at /dev/null so the exit-time flush stays quiet.
        with Path(os.devnull).open("w") as devnull:
            os.dup2(devnull.fileno(), sys.stdout.fileno())
        return 1
    return None


def _run(
    parser: _ArgumentParser, function: Callable[..., Awaitable[Any]], options: dict[str, Any]
) -> tuple[Any, int | None]:
    """
    Call a site function with an ``HttpxFetcher`` of its own, closed afterward.

    Returns:
        What the function returned and ``None``, or the ``partial`` of a stopped one and ``1``.
    """

    async def call() -> Any:  # noqa: ANN401  the return type differs by command
        async with HttpxFetcher() as fetcher:
            return await function(fetcher, **options)

    try:
        return asyncio.run(call()), None
    except ValueError as error:
        parser.error(str(error))
    except Stopped as stop:
        logger.error("%s", stop)  # noqa: TRY400  the message says what failed
        return stop.partial, 1


def _write_hits(command: str, text: str, hits: list[dict[str, str]]) -> int | None:
    """Print a lookup's candidates as JSON, warning when there are none."""
    if not hits:
        logger.warning("no %s found for %r. Check the spelling or try another query", command, text)
    return _write_stdout(json.dumps(hits, indent=2, ensure_ascii=False) + "\n")


def _fetched(
    args: argparse.Namespace, found: dict[str, JobDict | None]
) -> tuple[list[JobDict], int | None]:
    """
    Return one record per posting fetched, in reference order, and 1 when a reference failed.

    A reference to a posting the site reports gone logs a warning. A failed
    reference has no key in ``found``, and the site has reported why.
    """
    for reference, job in found.items():
        if job is None:
            logger.warning("%s is no longer on %s", reference, args.site)
    jobs = (job for job in found.values() if job is not None)
    # Like a stopped search, a fetch with a failed reference writes what it got and exits 1.
    status = 1 if any(reference not in found for reference in args.references) else None
    return list({(job["site"], job["id"]): job for job in jobs}.values()), status


def _settle_output(parser: _ArgumentParser, args: argparse.Namespace) -> str:
    """Validate the output path and choose the render format before any request."""
    if args.output is not None:
        if args.output.is_dir():
            parser.error(f"output path is a directory: {args.output}")
        if not args.output.parent.is_dir():
            parser.error(f"output directory does not exist: {args.output.parent}")
        # lexists also sees a dangling symlink, which exclusive creation refuses.
        if os.path.lexists(args.output):
            parser.error(f"output file already exists: {args.output}")
        if not os.access(args.output.parent, os.W_OK | os.X_OK):
            parser.error(f"output directory is not writable: {args.output.parent}")
    if args.format:
        fmt = args.format
    elif args.output:
        fmt = args.output.suffix.removeprefix(".").lower()
    else:
        fmt = "json"
    if fmt not in RENDERERS:
        parser.error(
            f"unsupported output extension {args.output.suffix!r}. "
            f"Use {' or '.join('.' + name for name in RENDERERS)} or pass --format"
        )
    return fmt


def _write_jobs(args: argparse.Namespace, jobs: list[JobDict], fmt: str) -> int | None:
    """
    Render jobs to stdout or to the output file.

    Returns:
        ``1`` when stdout closes early or the file cannot be written. ``None`` otherwise.
    """
    count = len(jobs)
    if args.output is None:
        logger.info(ngettext("found %d job", "found %d jobs", count), count)
        return _write_stdout(RENDERERS[fmt](jobs))
    if not jobs:
        logger.warning("no jobs found, so %s was not created", args.output)
        return None
    # Render before creating the file, so a render that fails leaves none behind.
    text = RENDERERS[fmt](jobs)
    try:
        with args.output.open("x", encoding="utf-8") as output:
            output.write(text)
    except OSError as error:
        logger.error(  # noqa: TRY400  the message says what failed
            "could not write %s: %s", args.output, error
        )
        return 1
    logger.info(ngettext("wrote %d job to %s", "wrote %d jobs to %s", count), count, args.output)
    return None


def main() -> int | None:
    """
    Run a search, posting fetch, or lookup.

    Returns:
        ``1`` when a search or lookup stops on a failed request, a named posting
        could not be fetched, stdout closes early, or the output file cannot be
        written. ``130`` when Ctrl-C interrupts the run. Normal completion
        returns ``None``.
    """
    parser = _build_parser()
    args = parser.parse_args()
    # Progress and warnings go to stderr, stdout stays pure data for piping.
    # The WARNING root level mutes dependencies such as httpx, which logs every
    # request at INFO. Only jobrake logs progress at INFO.
    handler = _StatusHandler()
    logging.basicConfig(level=logging.WARNING, handlers=[handler])
    logging.getLogger("jobrake").setLevel(logging.INFO)
    function = getattr(SITES[args.site], args.command)
    # In signature order, so the text a lookup takes comes first.
    options = {name: vars(args)[name] for name in site_options(function) if name in vars(args)}
    # A lookup prints its candidates and has no output to settle. A search and a
    # posting fetch settle theirs before spending any requests.
    command = args.command_parser
    fmt = _settle_output(command, args) if args.command in _WRITES_POSTINGS else None
    try:
        found, status = _run(command, function, options)
    except KeyboardInterrupt:
        logger.warning("interrupted, so no output was written")
        if sys.platform != "win32":
            # Die of SIGINT, as CPython does for an uncaught KeyboardInterrupt
            # (https://bugs.python.org/issue1054041, checked 2026-11-14). A
            # shell stops a loop only when the command it ran died of the signal.
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            os.kill(os.getpid(), signal.SIGINT)
        return 130  # 128 + SIGINT, the status a shell reports for that death
    finally:
        # An exceptional exit would otherwise start its traceback beside the progress line.
        handler.clear()
    if fmt is None:
        # A stopped lookup prints nothing.
        return status or _write_hits(args.command, next(iter(options.values())), found)
    if args.command == "postings":
        found, status = _fetched(args, found)
    if status and not found:
        # An empty document would pass for a search that completed and found nothing.
        return status
    return _write_jobs(args, found, fmt) or status


if __name__ == "__main__":
    raise SystemExit(main())
