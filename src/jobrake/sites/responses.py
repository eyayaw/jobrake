"""Reading a site's responses: one JSON body, its list of postings, and a search's pages."""

import json
import logging
from collections.abc import AsyncGenerator, Callable
from gettext import ngettext
from typing import Any

from jobrake.fetchkit import FetchResult
from jobrake.models import JobDict, Stopped
from jobrake.utils import finite, report_progress


def read_json[T](
    result: FetchResult,
    unpack: Callable[[Any], T],
    *,
    site: str,
    board: str | None = None,
    unknown: str | None = None,
) -> T:
    """
    Return what ``unpack`` takes from the JSON body of a site's response.

    ``unpack`` raises ``KeyError``, ``TypeError``, or ``AttributeError`` for a
    body without what the site needs. ``board`` names the board in the message
    of a failed request. ``unknown`` is the message for a 404, which without
    it counts as a failed request.

    Raises:
        Stopped: The site answered 404 and ``unknown`` is given, the request
            failed, or the body is unreadable.
    """
    if result.status == 404 and unknown:
        raise Stopped(unknown)
    if result.error:
        where = f" for board {board!r}" if board else ""
        raise Stopped(f"{site} request{where} failed: {result.error}")
    # ValueError covers JSONDecodeError and an integer longer than Python reads.
    try:
        return unpack(json.loads(result.text))
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise Stopped(
            f"{site} sent a response this version cannot read ({error!r}), likely an API change"
        ) from error


def json_list(payload: Any, key: str | None = None) -> list[Any]:  # noqa: ANN401  any decoded JSON, which json_list checks
    """
    Return ``payload[key]``, or ``payload`` itself without a key, checking that it is a list.

    Raises:
        KeyError: ``payload`` lacks ``key``.
        TypeError: The value is not a list, or ``payload`` is not an object.
    """
    value = payload if key is None else payload[key]
    if not isinstance(value, list):
        raise TypeError(f"{key or 'the response'} is a {type(value).__name__}, not a list")
    return value


def json_page(payload: Any, key: str, total: str) -> tuple[list[Any], int]:  # noqa: ANN401  any decoded JSON, which json_page checks
    """
    Return a page's ``payload[key]`` list and the count of all matches that ``payload[total]`` reports.

    Raises:
        KeyError: ``payload`` lacks ``key`` or ``total``.
        TypeError: ``payload[key]`` is not a list, ``payload[total]`` is not
            a number, or ``payload`` is not an object.
    """
    count = finite(payload[total])
    if count is None:
        raise TypeError(f"{total} {payload[total]!r} is not a number")
    return json_list(payload, key), int(count)


def parse_postings(
    items: list[Any], parse: Callable[[Any], JobDict], *, site: str
) -> list[JobDict]:
    """
    Parse each item of a site's posting list, skipping one that ``parse`` rejects.

    ``parse`` raises ``TypeError`` or ``AttributeError`` for a malformed
    item, which is left out of the result and logged as a warning.
    """
    # The site's own logger, so a handler set on one site still sees its warnings.
    logger = logging.getLogger(f"jobrake.sites.{site}")
    jobs = []
    for item in items:
        try:
            jobs.append(parse(item))
        except (TypeError, AttributeError) as error:
            logger.warning("skipping malformed %s posting: %r", site, error)
    return jobs


async def collect(
    site: str, pages: AsyncGenerator[tuple[list[JobDict], int]], results: int
) -> list[JobDict]:
    """
    Gather a search's pages into at most ``results`` postings, in the site's order.

    ``pages`` yields each page's postings with the count the site can serve
    for the search, and ends where the site does. It is asked for a page only
    while postings are missing, so the code after its last ``yield`` runs only
    for a search the site ended short of ``results``. A posting that a later
    page repeats is kept once, and each page logs a progress record.

    Raises:
        Stopped: ``pages`` raised it. ``partial`` holds the postings of the
            pages before it, which the message counts.
    """
    logger = logging.getLogger(f"jobrake.sites.{site}")
    jobs: dict[str, JobDict] = {}
    try:
        async for page, total in pages:
            for job in page:
                jobs.setdefault(job["id"], job)
            report_progress(logger, f"{site} search", len(jobs), min(results, total))
            if len(jobs) >= results:
                break
    except Stopped as stopped:
        count = ngettext("%d posting", "%d postings", len(jobs)) % len(jobs)
        kept = f". Kept the {count} collected" if jobs else ""
        raise Stopped(f"{stopped}{kept}", partial=list(jobs.values())) from stopped
    finally:
        await pages.aclose()
    return list(jobs.values())[:results]
