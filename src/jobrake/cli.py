"""Command-line search and output dispatch."""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from contextlib import suppress
from pathlib import Path
from typing import Never

from jobrake import __version__, scrape

from . import defaults
from .fetchkit import HttpxFetcher
from .io import RENDERERS
from .sites import indeed, linkedin, site_searchers

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


def _add_linkedin_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--location",
        "-l",
        help="location, preferably with region and country. Optional with --geoid ID",
    )
    parser.add_argument(
        "--geoid",
        "-g",
        nargs="?",
        const=True,
        default=defaults.GEOID,
        metavar="ID",
        help="search by geoId: resolve --location through LinkedIn's place lookup, or send ID as given",
    )
    parser.add_argument(
        "--details",
        "-d",
        default=defaults.DETAILS,
        action="store_true",
        help="fetch posting pages for descriptions and other details",
    )
    parser.add_argument(
        "--no-cache",
        dest="cache",
        action="store_false",
        default=defaults.CACHE,
        help="refetch posting details instead of using the disk cache",
    )
    parser.set_defaults(
        country=None,
        radius=defaults.LINKEDIN_RADIUS,
    )


def _add_indeed_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--location", "-l", help="city or area within the selected country")
    parser.add_argument(
        "--country",
        "-c",
        required=True,
        default=argparse.SUPPRESS,
        help="Indeed country edition, e.g., usa, uk, or netherlands",
    )
    parser.add_argument(
        "--radius",
        "-r",
        default=defaults.INDEED_RADIUS,
        type=int,
        help=f"search radius in kilometers (default: {defaults.INDEED_RADIUS})",
    )
    # Indeed search results already contain descriptions, and postings are not
    # fetched individually, so details, cache, and geoid do not apply.
    parser.set_defaults(details=defaults.DETAILS, cache=defaults.CACHE, geoid=defaults.GEOID)


_SITE_ARGS = {"linkedin": _add_linkedin_args, "indeed": _add_indeed_args}


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--query",
        "-q",
        required=True,
        default=argparse.SUPPRESS,
        help="job title, keywords, or Boolean query",
    )
    parser.add_argument(
        "--results",
        "-n",
        default=defaults.RESULTS,
        type=int,
        help=f"maximum number of unique jobs to return (default: {defaults.RESULTS})",
    )
    parser.add_argument(
        "--max-age",
        "-a",
        dest="max_age_hours",
        default=defaults.MAX_AGE_HOURS,
        metavar="HOURS",
        type=int,
        help=f"maximum posting age in hours (default: {defaults.MAX_AGE_HOURS})",
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
        help="output format. Defaults to the --output extension or JSON for stdout",
    )


def _build_parser() -> _ArgumentParser:
    parser = _ArgumentParser(prog="jobrake", description="Search job postings", allow_abbrev=False)
    # The version action exits before argparse checks the required subcommand.
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="provider", required=True)
    for name in sorted(site_searchers()):
        subparser = subparsers.add_parser(name, allow_abbrev=False)
        # Mutate this subparser by adding arguments and defaults.
        _add_common_args(subparser)
        _SITE_ARGS[name](subparser)
    lookup = subparsers.add_parser(
        "places",
        allow_abbrev=False,
        description="Show how a provider resolves a place name",
    )
    sites = lookup.add_subparsers(dest="site", required=True)
    li = sites.add_parser(
        "linkedin",
        allow_abbrev=False,
        description="Print LinkedIn's candidate places for the name, best match first, as JSON",
    )
    ind = sites.add_parser(
        "indeed",
        allow_abbrev=False,
        description=(
            "Print an Indeed edition's location suggestions for the name, best match first, as JSON"
        ),
    )
    for sub in (li, ind):
        sub.add_argument("name", help="place name, e.g. 'amsterdam'")
    ind.add_argument(
        "--country",
        "-c",
        required=True,
        default=argparse.SUPPRESS,
        help="Indeed country edition, e.g., usa, uk, or netherlands",
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
        with open(os.devnull, "w") as devnull:
            os.dup2(devnull.fileno(), sys.stdout.fileno())
        return 1
    return None


async def _lookup_places(args: argparse.Namespace) -> list[dict] | None:
    """Run the selected provider's place lookup with a fetcher of its own."""
    fetcher = HttpxFetcher()
    try:
        match args.site:
            case "linkedin":
                return await linkedin.places(fetcher, args.name)
            case "indeed":
                return await indeed.places(fetcher, args.name, args.country)
            case _:
                raise ValueError(f"unknown provider {args.site}")
    finally:
        await fetcher.close()


def main() -> int | None:
    """
    Run the parsed command: a provider scrape in the selected format, or a places lookup.

    Returns:
        ``1`` when stdout closes early, the output file cannot be written, or a places lookup fails. Normal completion returns ``None``.
    """
    parser = _build_parser()
    args = parser.parse_args()
    # Progress and warnings go to stderr, stdout stays pure data for piping.
    # The WARNING root level mutes dependencies such as httpx, which logs every
    # request at INFO. Only jobrake logs progress at INFO.
    handler = _StatusHandler()
    logging.basicConfig(level=logging.WARNING, handlers=[handler])
    logging.getLogger("jobrake").setLevel(logging.INFO)
    if args.provider == "places":
        try:
            hits = asyncio.run(_lookup_places(args))
        except ValueError as e:
            parser.error(str(e))
        if hits is None:
            return 1
        if not hits:
            logger.warning("no places match %r", args.name)
        return _write_stdout(json.dumps(hits, indent=2, ensure_ascii=False) + "\n")
    if args.provider == "linkedin" and args.location is None and not isinstance(args.geoid, str):
        parser.error("--location/-l is required unless --geoid receives an ID")
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
    try:
        jobs = asyncio.run(
            scrape(
                args.provider,
                query=args.query,
                location=args.location,
                country=args.country,
                radius=args.radius,
                results=args.results,
                max_age_hours=args.max_age_hours,
                details=args.details,
                cache=args.cache,
                geoid=args.geoid,
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
        return _write_stdout(rendered)

    try:
        args.output.write_text(rendered, encoding="utf-8")
    except OSError as error:
        logger.error("could not write %s: %s", args.output, error)
        return 1
    logger.info("wrote %d jobs to %s", len(jobs), args.output)


if __name__ == "__main__":
    raise SystemExit(main())
