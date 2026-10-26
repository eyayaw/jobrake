"""Command-line search and output dispatch, built from each site's signatures."""

import argparse
import asyncio
import inspect
import json
import logging
import os
import sys
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from pathlib import Path
from types import ModuleType
from typing import Any, Never, TextIO, get_args

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

# The lookups a site may define, with the help of the command that runs them.
_LOOKUPS = {
    "places": "find place IDs by name",
    "companies": "find company IDs by name",
    "attributes": "find attribute codes in matching postings",
}


def _add_parser(
    add_parser: Callable[..., argparse.ArgumentParser],
    name: str,
    target: Callable[..., object] | ModuleType,
) -> argparse.ArgumentParser:
    """Add a subcommand described by the first line of ``target``'s docstring."""
    line = (inspect.getdoc(target) or "").splitlines()[0]
    help_text = line[:1].lower() + line[1:].removesuffix(".")
    return add_parser(name, allow_abbrev=False, help=help_text, description=line)


def _add_positional(parser: argparse.ArgumentParser, function: Callable[..., object]) -> None:
    """Add the argument a lookup or posting fetch takes after the fetcher: one text, or several."""
    parameter = list(inspect.signature(function).parameters.values())[1]
    kind, help_text = get_args(parameter.annotation)
    many: dict[str, Any] = {"nargs": "+"} if kind is not str else {}
    parser.add_argument(parameter.name, metavar=parameter.name.upper(), help=help_text, **many)


def _add_options(parser: argparse.ArgumentParser, function: Callable[..., object]) -> None:
    """Add one flag per keyword option of a site function, named after the option."""
    for name, option in site_options(function).items():
        flags = [f"--{name.replace('_', '-')}"]
        if name in _SHORT_FLAGS:
            flags.append(_SHORT_FLAGS[name])
        required = option.default is inspect.Parameter.empty
        help_text = option.help
        if option.default not in (None, False, inspect.Parameter.empty):
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
    commands = parser.add_subparsers(dest="command", required=True)
    for site, module in SITES.items():
        search = _add_parser(commands.add_parser, site, module)
        _add_options(search, module.search)
        _add_output_args(search)
    if fetchers := {site: module for site, module in SITES.items() if hasattr(module, "postings")}:
        postings = commands.add_parser(
            "postings",
            allow_abbrev=False,
            help="fetch known postings by ID or URL",
            description="Fetch known postings by ID or URL",
        )
        sites = postings.add_subparsers(dest="site", required=True)
        for site, module in fetchers.items():
            fetch = _add_parser(sites.add_parser, site, module.postings)
            _add_positional(fetch, module.postings)
            _add_options(fetch, module.postings)
            _add_output_args(fetch)
    for kind, help_text in _LOOKUPS.items():
        lookups = {
            site: getattr(module, kind) for site, module in SITES.items() if hasattr(module, kind)
        }
        if not lookups:
            continue
        command = commands.add_parser(
            kind,
            allow_abbrev=False,
            help=help_text,
            description=help_text[:1].upper() + help_text[1:],
        )
        sites = command.add_subparsers(dest="site", required=True)
        for site, lookup in lookups.items():
            sub = _add_parser(sites.add_parser, site, lookup)
            _add_positional(sub, lookup)
            _add_options(sub, lookup)
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
    positional = list(inspect.signature(function).parameters)[1]
    options = site_options(function)
    return vars(args)[positional], {k: v for k, v in vars(args).items() if k in options}


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


def _fetch_postings(args: argparse.Namespace) -> list[JobDict]:
    """
    Fetch the named postings, one record per posting in reference order.

    A reference to a posting the site reports gone logs a warning.
    """
    fetch = SITES[args.site].postings
    references, options = _call_args(args, fetch)
    found = asyncio.run(_with_own_fetcher(fetch, references, **options))
    for reference, job in found.items():
        if job is None:
            logger.warning("%s is no longer on %s", reference, args.site)
    jobs = (job for job in found.values() if job is not None)
    return list({(job["site"], job["id"]): job for job in jobs}.values())


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
        ``1`` when a search or lookup stops on a failed request, no named posting could be fetched, stdout closes early, or the output file cannot be written. Normal completion returns ``None``.
    """
    parser = _build_parser()
    args = parser.parse_args()
    # Progress and warnings go to stderr, stdout stays pure data for piping.
    # The WARNING root level mutes dependencies such as httpx, which logs every
    # request at INFO. Only jobrake logs progress at INFO.
    handler = _StatusHandler()
    logging.basicConfig(level=logging.WARNING, handlers=[handler])
    logging.getLogger("jobrake").setLevel(logging.INFO)
    if args.command in _LOOKUPS:
        return _lookup(parser, args)
    # Settle the output before the fetch spends any requests.
    fmt = _settle_output(parser, args)
    if args.command == "postings":
        try:
            jobs = _fetch_postings(args)
        except ValueError as e:
            parser.error(str(e))
        finally:
            handler.clear()
        # An empty result means every named posting failed, each already reported.
        return _write_jobs(args, jobs, fmt) if jobs else 1
    options = {k: v for k, v in vars(args).items() if k in site_options(SITES[args.command].search)}
    status = None
    try:
        jobs = asyncio.run(scrape(args.command, **options))
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
