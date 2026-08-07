"""A cli entrypoint to jobrake."""

import argparse
import asyncio
import json

from jobrake import scrape

from .constants import JobrakeConstants as JBC


def to_json(obj: list, **kwargs):
    if len(obj) < 50 and "indent" not in kwargs:
        kwargs["indent"] = 2

    if "ensure_ascii" not in kwargs:
        kwargs["ensure_ascii"] = False
    return json.dumps(obj, **kwargs)


def main():
    parser = argparse.ArgumentParser(
        description="Search job postings", formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--site", "-s", choices=JBC.sites, required=True)
    parser.add_argument("--search-term", "-q", required=True, help="search query")
    parser.add_argument("--location", "-l", help="location, e.g., United States, or New York (required for linkedin)")
    parser.add_argument("--country", "-c", help="country name, e.g., usa, uk, netherlands (ignored by linkedin)")
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
        help="fetch the full description of the job post",
    )

    args = parser.parse_args()
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
                linkedin_fetch_description=args.fetch_description,
            )
        )
    except ValueError as e:
        parser.error(str(e))
    print(to_json(jobs))


if __name__ == "__main__":
    raise SystemExit(main())
