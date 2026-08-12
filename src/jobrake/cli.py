"""A cli entrypoint to jobrake."""

import argparse
import asyncio
import logging
from pathlib import Path

from jobrake import scrape

from .constants import JobrakeConstants as JBC
from .core import site_searches
from .io import WRITERS, to_json

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Search job postings", formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--site", "-s", choices=sorted(site_searches()), required=True)
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
        default=JBC.radius,
        type=int,
        help="radius around the location specified",
    )
    parser.add_argument(
        "--results-wanted",
        "-n",
        default=JBC.results_wanted,
        type=int,
        help="number of unique job postings to fetch",
    )
    parser.add_argument(
        "--hours-old", "-a", default=JBC.hours_old, type=int, help="age of job posted in hours"
    )
    parser.add_argument(
        "--fetch-description",
        "-d",
        default=JBC.fetch_description,
        action="store_true",
        help="fetch the full description of the job post (linkedin only; indeed always includes descriptions)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="always refetch descriptions instead of serving cached ones from disk (linkedin)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help=f"write results to this file, format from the extension ({' or '.join(WRITERS)})",
    )

    args = parser.parse_args()
    # Reject a bad extension upfront (before the scrape, not after paying for it)
    if args.output is not None and args.output.suffix not in WRITERS:
        parser.error(
            f"unsupported output extension {args.output.suffix!r} (use {' or '.join(WRITERS)})"
        )
    # Progress and warnings go to stderr, stdout stays pure JSON for piping.
    # Root stays at WARNING so chatty dependencies (httpx logs every request at INFO) are muted,
    # only our own loggers speak at INFO.
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s [%(name)s] %(message)s")
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
                fetch_description=args.fetch_description,
                cache=not args.no_cache,
            )
        )
    except ValueError as e:
        parser.error(str(e))
    if args.output is None:
        print(to_json(jobs))
    else:
        WRITERS[args.output.suffix](jobs, args.output)
        logger.info("wrote %d jobs to %s", len(jobs), args.output)


if __name__ == "__main__":
    raise SystemExit(main())
