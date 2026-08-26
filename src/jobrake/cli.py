"""Command-line search and output dispatch."""

import argparse
import asyncio
import logging
import os
import sys
import time
from contextlib import suppress
from pathlib import Path
from typing import Never

from jobrake import __version__, scrape

from . import defaults
from .io import RENDERERS
from .sites import site_searchers

logger = logging.getLogger(__name__)

_CLEAR_LINE = "\r\x1b[2K"


class _ArgumentParser(argparse.ArgumentParser):
    """Report parse errors without repeating the full usage line."""

    def error(self, message: str) -> Never:
        self.exit(2, f"{self.prog}: error: {message}\nRun '{self.prog} -h' for help.\n")


class _StatusHandler(logging.StreamHandler):
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
        except Exception:
            self.handleError(record)

    def clear(self) -> None:
        """Erase the status line so a traceback starts on its own line."""
        if self._showing_progress:
            self._showing_progress = False
            # Cleanup failures must not replace the original exception.
            with suppress(Exception):
                self.stream.write(_CLEAR_LINE)
                self.flush()


def main() -> int | None:
    """
    Scrape from command-line arguments and write the selected format.

    Returns:
        ``1`` when stdout closes early or the output file cannot be written. Normal completion returns ``None``.
    """
    parser = _ArgumentParser(
        prog="jobrake",
        description="Search job postings",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # The version action exits before argparse checks required arguments.
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--site", "-s", choices=sorted(site_searchers()), required=True)
    parser.add_argument("--search-term", "-q", required=True, help="search query")
    parser.add_argument(
        "--location",
        "-l",
        help="location, e.g., United States, or New York (required for linkedin)",
    )
    parser.add_argument(
        "--country", "-c", help="country name, e.g., usa, uk, netherlands (ignored by linkedin)"
    )
    parser.add_argument(
        "--radius",
        "-r",
        default=defaults.RADIUS,
        type=int,
        help="radius around the location specified",
    )
    parser.add_argument(
        "--results-wanted",
        "-n",
        default=defaults.RESULTS_WANTED,
        type=int,
        help="number of unique job postings to fetch",
    )
    parser.add_argument(
        "--hours-old", "-a", default=defaults.HOURS_OLD, type=int, help="age of postings in hours"
    )
    parser.add_argument(
        "--detail",
        "-d",
        default=defaults.DETAIL,
        action="store_true",
        help="fetch each LinkedIn posting page for its description and other detail fields. "
        "Indeed search results already contain them",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="always refetch postings instead of serving cached ones from disk (linkedin)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="write results to this file instead of stdout",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=list(RENDERERS),
        help="output format, defaults to the --output extension, or json on stdout",
    )

    args = parser.parse_args()
    # Settle the output path and format before the scrape spends any requests.
    if args.output is not None:
        if args.output.is_dir():
            parser.error(f"output path is a directory: {args.output}")
        if not args.output.parent.is_dir():
            parser.error(f"output directory does not exist: {args.output.parent}")
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
    # Progress and warnings go to stderr, stdout stays pure data for piping.
    # The WARNING root level mutes dependencies such as httpx, which logs every
    # request at INFO. Only jobrake logs progress at INFO.
    handler = _StatusHandler()
    logging.basicConfig(level=logging.WARNING, handlers=[handler])
    logging.getLogger("jobrake").setLevel(logging.INFO)
    try:
        jobs = asyncio.run(
            scrape(
                args.site,
                search_term=args.search_term,
                location=args.location,
                country=args.country,
                distance=args.radius,
                results_wanted=args.results_wanted,
                hours_old=args.hours_old,
                detail=args.detail,
                cache=not args.no_cache,
            )
        )
    except ValueError as e:
        parser.error(str(e))
    finally:
        # An exceptional exit would otherwise start its traceback beside the progress line.
        handler.clear()
    if args.output is not None and not jobs:
        logger.warning("no jobs found; leaving %s untouched", args.output)
        return None
    rendered = RENDERERS[fmt](jobs)
    if args.output is None:
        try:
            sys.stdout.write(rendered)
            # Flush now: when the output fits the pipe buffer, a closed pipe
            # would otherwise surface at interpreter exit, past this handler.
            sys.stdout.flush()
        except BrokenPipeError:
            # The downstream reader (e.g. `jobrake ... | head`) stopped early.
            # Keep this handler local. SIGPIPE, signal(SIGPIPE, SIG_DFL),
            # works only on Unix and changes signal handling for the whole process.
            # Point stdout at /dev/null so the exit-time flush stays quiet.
            with open(os.devnull, "w") as devnull:
                os.dup2(devnull.fileno(), sys.stdout.fileno())
            return 1
        return None

    try:
        args.output.write_text(rendered, encoding="utf-8")
    except OSError as error:
        logger.error("could not write %s: %s", args.output, error)
        return 1
    logger.info("wrote %d jobs to %s", len(jobs), args.output)


if __name__ == "__main__":
    raise SystemExit(main())
