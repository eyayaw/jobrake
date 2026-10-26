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
from typing import Never, TextIO

from jobrake import __version__, scrape

from .fetchkit import HttpxFetcher
from .io import RENDERERS
from .models import JobDict, Stopped
from .sites import SITES, indeed, linkedin
from .utils import Option, site_options

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


def _add_linkedin_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--location",
        "-l",
        default=argparse.SUPPRESS,
        help="location, preferably with region and country. Optional with --geoid ID",
    )
    parser.add_argument(
        "--geoid",
        "-g",
        default=argparse.SUPPRESS,
        metavar="ID",
        help="LinkedIn place ID from 'jobrake places linkedin', in place of --location",
    )
    parser.add_argument(
        "--radius",
        "-r",
        default=argparse.SUPPRESS,
        type=int,
        help="search radius in kilometers (default: unset)",
    )
    parser.add_argument(
        "--company",
        dest="company_ids",
        action="append",
        default=argparse.SUPPRESS,
        metavar="ID",
        help="filter jobs by company ID (repeat for several companies)",
    )
    parser.add_argument(
        "--easy-apply",
        action="store_true",
        default=argparse.SUPPRESS,
        help="restrict results to jobs with LinkedIn's Easy Apply form",
    )
    parser.add_argument(
        "--early-applicant",
        action="store_true",
        default=argparse.SUPPRESS,
        help="use LinkedIn's filter for fewer than 10 applicants",
    )
    parser.add_argument(
        "--details",
        "-d",
        default=argparse.SUPPRESS,
        action="store_true",
        help="fetch posting pages for descriptions and other details",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        default=argparse.SUPPRESS,
        help="refetch postings and refresh their cached copies",
    )


def _add_indeed_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--location",
        "-l",
        default=argparse.SUPPRESS,
        help="city or area within the selected country",
    )
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
        default=argparse.SUPPRESS,
        type=int,
        help=f"search radius in kilometers (default: {site_options(indeed.search)['radius'].default})",
    )
    parser.add_argument(
        "--company",
        dest="company_ids",
        action="append",
        default=argparse.SUPPRESS,
        metavar="ID",
        help="filter jobs by company ID (one per search)",
    )
    parser.add_argument(
        "--remote",
        action="store_true",
        default=argparse.SUPPRESS,
        help="restrict results to postings tagged Remote by Indeed",
    )
    parser.add_argument(
        "--language",
        default=argparse.SUPPRESS,
        metavar="CODE",
        help="restrict postings by Indeed language code (two letters, e.g., EN or NL)",
    )
    parser.add_argument(
        "--attribute",
        dest="attributes",
        action="append",
        default=argparse.SUPPRESS,
        metavar="CODE",
        help="filter jobs by attribute code (repeat to require all codes)",
    )


_SITE_ARGS = {"linkedin": _add_linkedin_args, "indeed": _add_indeed_args}

# Spelled out because "linkedin".title() gives "Linkedin".
_SITE_LABELS = {"linkedin": "LinkedIn", "indeed": "Indeed"}


def _add_search_args(parser: argparse.ArgumentParser, options: dict[str, Option]) -> None:
    parser.add_argument(
        "--query",
        "-q",
        required=True,
        default=argparse.SUPPRESS,
        help="job title or keywords, as interpreted by the provider",
    )
    parser.add_argument(
        "--results",
        "-n",
        default=argparse.SUPPRESS,
        type=int,
        help=f"maximum number of unique jobs to return (default: {options['results'].default})",
    )
    parser.add_argument(
        "--max-age",
        "-a",
        dest="max_age_hours",
        default=argparse.SUPPRESS,
        metavar="HOURS",
        type=int,
        help=f"maximum posting age in hours (default: {options['max_age_hours'].default})",
    )


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
    subparsers = parser.add_subparsers(dest="provider", required=True)
    for name in sorted(SITES):
        subparser = subparsers.add_parser(
            name, allow_abbrev=False, help=f"search {_SITE_LABELS[name]} for job postings"
        )
        # Mutate this subparser by adding arguments.
        _add_search_args(subparser, site_options(SITES[name].search))
        _add_output_args(subparser)
        _SITE_ARGS[name](subparser)
    postings = subparsers.add_parser(
        "postings",
        allow_abbrev=False,
        help="fetch known postings by ID or URL",
        description="Fetch known postings by ID or URL",
    )
    postings_sites = postings.add_subparsers(dest="site", required=True)
    postings_linkedin = postings_sites.add_parser(
        "linkedin",
        allow_abbrev=False,
        help="fetch LinkedIn postings by ID or URL",
        description="Fetch LinkedIn postings by ID or URL",
    )
    postings_linkedin.add_argument(
        "references",
        nargs="+",
        metavar="ID|URL",
        help="numeric LinkedIn posting ID or posting URL",
    )
    postings_linkedin.add_argument(
        "--refresh",
        action="store_true",
        help="refetch postings and refresh their cached copies",
    )
    _add_output_args(postings_linkedin)
    lookup = subparsers.add_parser(
        "places",
        allow_abbrev=False,
        help="show how a provider resolves a place name",
        description="Show how a provider resolves a place name",
    )
    sites = lookup.add_subparsers(dest="site", required=True)
    li = sites.add_parser(
        "linkedin",
        allow_abbrev=False,
        help="print LinkedIn place IDs for a name",
        description="Print LinkedIn's candidate places for the name, best match first, as JSON",
    )
    ind = sites.add_parser(
        "indeed",
        allow_abbrev=False,
        help="print an Indeed edition's location suggestions for a name",
        description=(
            "Print an Indeed edition's location suggestions for the name, best match first, as JSON"
        ),
    )
    for sub in (li, ind):
        sub.add_argument("name", help="place name, e.g., 'amsterdam'")
    ind.add_argument(
        "--country",
        "-c",
        required=True,
        default=argparse.SUPPRESS,
        help="Indeed country edition, e.g., usa, uk, or netherlands",
    )
    companies = subparsers.add_parser(
        "companies",
        allow_abbrev=False,
        help="find company IDs by name",
        description="Find company IDs by name",
    )
    company_sites = companies.add_subparsers(dest="site", required=True)
    company_linkedin = company_sites.add_parser(
        "linkedin",
        allow_abbrev=False,
        help="print LinkedIn company IDs for a name",
        description="List LinkedIn's suggested company names and IDs as JSON",
    )
    company_indeed = company_sites.add_parser(
        "indeed",
        allow_abbrev=False,
        help="print Indeed company IDs for a name",
        description="List an Indeed edition's company suggestions and IDs as JSON",
    )
    for sub in (company_linkedin, company_indeed):
        sub.add_argument("name", help="company name, e.g., 'ABN AMRO'")
    company_indeed.add_argument(
        "--country",
        "-c",
        required=True,
        help="Indeed country edition, e.g., usa, uk, or netherlands",
    )
    attributes = subparsers.add_parser(
        "attributes",
        allow_abbrev=False,
        help="discover attribute codes in matching jobs",
        description="Discover attribute codes in matching jobs",
    )
    attribute_sites = attributes.add_subparsers(dest="site", required=True)
    attribute_indeed = attribute_sites.add_parser(
        "indeed",
        allow_abbrev=False,
        help="print Indeed attribute codes and labels",
        description="List attribute codes and labels from the first 100 matching jobs as JSON",
    )
    attribute_indeed.add_argument("name", metavar="QUERY", help="job title or keywords")
    attribute_indeed.add_argument(
        "--country",
        "-c",
        required=True,
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
        with Path(os.devnull).open("w") as devnull:
            os.dup2(devnull.fileno(), sys.stdout.fileno())
        return 1
    return None


async def _lookup_candidates(args: argparse.Namespace) -> list[dict[str, str]]:
    """Look up places, companies, or attributes with a fetcher of its own."""
    fetcher = HttpxFetcher()
    try:
        match args.site:
            case "linkedin":
                if args.provider == "companies":
                    return await linkedin.companies(fetcher, args.name)
                return await linkedin.places(fetcher, args.name)
            case "indeed":
                if args.provider == "attributes":
                    return await indeed.attributes(fetcher, args.name, country=args.country)
                if args.provider == "companies":
                    return await indeed.companies(fetcher, args.name, country=args.country)
                return await indeed.places(fetcher, args.name, country=args.country)
            case _:
                raise ValueError(f"unknown provider {args.site}")
    finally:
        await fetcher.close()


async def _fetch_postings(args: argparse.Namespace) -> list[JobDict]:
    """
    Fetch the named postings with a fetcher of its own, one record per posting in reference order.

    A reference to a posting the site reports gone logs a warning.
    """
    fetcher = HttpxFetcher()
    try:
        found = await linkedin.postings(fetcher, args.references, refresh=args.refresh)
    finally:
        await fetcher.close()
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
    if args.provider in ("places", "companies", "attributes"):
        try:
            hits = asyncio.run(_lookup_candidates(args))
        except ValueError as e:
            parser.error(str(e))
        except Stopped as stop:
            logger.error("%s", stop)  # noqa: TRY400  the message says what failed; a traceback adds nothing
            return 1
        if not hits:
            logger.warning(
                "no %s found for %r. Check the spelling or try another query",
                args.provider,
                args.name,
            )
        return _write_stdout(json.dumps(hits, indent=2, ensure_ascii=False) + "\n")
    if args.provider == "postings":
        fmt = _settle_output(parser, args)
        try:
            jobs = asyncio.run(_fetch_postings(args))
        except ValueError as e:
            parser.error(str(e))
        finally:
            handler.clear()
        # An empty result means every named posting failed, each already reported.
        return _write_jobs(args, jobs, fmt) if jobs else 1
    # Settle the output before the scrape spends any requests.
    fmt = _settle_output(parser, args)
    accepted = site_options(SITES[args.provider].search)
    options = {name: value for name, value in vars(args).items() if name in accepted}
    status = None
    try:
        jobs = asyncio.run(scrape(args.provider, **options))
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
