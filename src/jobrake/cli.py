"""Command-line search and output dispatch, built from each site's signatures."""

import argparse
import asyncio
import inspect
import io
import json
import logging
import os
import sys
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from pathlib import Path
from types import ModuleType
from typing import Any, Never, TextIO, override

from jobrake import __version__, scrape

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
    current terminal line as a bar ending in its counter; ordinary records
    erase that line first, so warnings landing mid-fetch stay legible. A
    non-terminal stderr skips progress records and receives no control codes.
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
                done, total = progress
                bar = "#" * round(20 * done / total)
                # Flag first, so clear() erases even an interrupted write.
                self._showing_progress = True
                self.stream.write(f"[{bar:<20}] [{done}/{total}] ")
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


# Short flags for the option names that sites share.
_SHORT_FLAGS = {
    "query": "-q",
    "location": "-l",
    "country": "-c",
    "radius": "-r",
    "results": "-n",
    "max_age_hours": "-a",
    "geoid": "-g",
    "details": "-d",
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


def _add_output_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="write results to a new file instead of stdout",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=list(RENDERERS),
        help="output format. Defaults to the --output extension or JSON for stdout",
    )


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
            _add_arguments(command, function)
            if name in _WRITES_POSTINGS:
                _add_output_args(command)
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


async def _with_own_fetcher[T](
    function: Callable[..., Awaitable[T]], *args: object, **options: object
) -> T:
    """Call a site function with an ``HttpxFetcher`` that it closes afterward."""
    fetcher = HttpxFetcher()
    try:
        return await function(fetcher, *args, **options)
    finally:
        await fetcher.close()


def _call_args(
    args: argparse.Namespace, function: Callable[..., object]
) -> tuple[Any, dict[str, Any]]:
    """Return the positional argument and the options the command line gave a site function."""
    (positional, _), *options = site_options(function).items()
    names = {name for name, _ in options}
    return vars(args)[positional], {k: v for k, v in vars(args).items() if k in names}


def _lookup(parser: _ArgumentParser, args: argparse.Namespace) -> int | None:
    """Print a lookup's candidates as JSON, or return 1 after a failed request."""
    lookup = getattr(SITES[args.site], args.command)
    text, options = _call_args(args, lookup)
    try:
        hits = asyncio.run(_with_own_fetcher(lookup, text, **options))
    except ValueError as e:
        parser.error(str(e))
    except Stopped as stop:
        logger.error("%s", stop)  # noqa: TRY400  the message says what failed; a traceback adds nothing
        return 1
    if not hits:
        logger.warning(
            "no %s found for %r. Check the spelling or try another query", args.command, text
        )
    return _write_stdout(json.dumps(hits, indent=2, ensure_ascii=False) + "\n")


def _fetch_postings(args: argparse.Namespace) -> tuple[list[JobDict], bool]:
    """
    Fetch the named postings, one record per posting in reference order, and whether a reference failed.

    A reference to a posting the site reports gone logs a warning. A failed
    reference has no key in the result of ``postings``, and the site has
    reported why.
    """
    fetch = SITES[args.site].postings
    references, options = _call_args(args, fetch)
    found = asyncio.run(_with_own_fetcher(fetch, references, **options))
    for reference, job in found.items():
        if job is None:
            logger.warning("%s is no longer on %s", reference, args.site)
    jobs = (job for job in found.values() if job is not None)
    failed = any(reference not in found for reference in references)
    return list({(job["site"], job["id"]): job for job in jobs}.values()), failed


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
        fmt = args.output.suffix.removeprefix(".")
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
    if args.output is None:
        return _write_stdout(RENDERERS[fmt](jobs))
    if not jobs:
        logger.warning("no jobs found; leaving %s untouched", args.output)
        return None
    try:
        with args.output.open("x", encoding="utf-8") as output:
            output.write(RENDERERS[fmt](jobs))
    except OSError as error:
        logger.error("could not write %s: %s", args.output, error)  # noqa: TRY400  the user needs the message, not a traceback
        return 1
    logger.info("wrote %d jobs to %s", len(jobs), args.output)
    return None


def main() -> int | None:
    """
    Run a search, posting fetch, or lookup.

    Returns:
        ``1`` when a search or lookup stops on a failed request, a named posting could not be fetched, stdout closes early, or the output file cannot be written. Normal completion returns ``None``.
    """
    # The output is JSON or CSV data, so it is UTF-8 like a file -o writes, whatever
    # the console's code page.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = _build_parser()
    args = parser.parse_args()
    # Progress and warnings go to stderr, stdout stays pure data for piping.
    # The WARNING root level mutes dependencies such as httpx, which logs every
    # request at INFO. Only jobrake logs progress at INFO.
    handler = _StatusHandler()
    logging.basicConfig(level=logging.WARNING, handlers=[handler])
    logging.getLogger("jobrake").setLevel(logging.INFO)
    if args.command not in _WRITES_POSTINGS:
        return _lookup(parser, args)
    # Settle the output before the fetch spends any requests.
    fmt = _settle_output(parser, args)
    status = None
    try:
        if args.command == "postings":
            jobs, failed = _fetch_postings(args)
            # Like a stopped search, a fetch with a failed reference writes what it got and exits 1.
            status = 1 if failed else None
        else:
            search = site_options(SITES[args.site].search)
            options = {k: v for k, v in vars(args).items() if k in search}
            jobs = asyncio.run(scrape(args.site, **options))
    except ValueError as e:
        parser.error(str(e))
    except Stopped as stop:
        logger.error("%s", stop)  # noqa: TRY400  the message says what failed; a traceback adds nothing
        jobs, status = stop.partial, 1
    finally:
        # An exceptional exit would otherwise start its traceback beside the progress line.
        handler.clear()
    return _write_jobs(args, jobs, fmt) or status


if __name__ == "__main__":
    raise SystemExit(main())
