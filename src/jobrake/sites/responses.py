"""Reading a site's JSON response into postings, and the ``Stopped`` each failure raises."""

import json
import logging
from collections.abc import Callable
from gettext import ngettext
from typing import Any

from jobrake.fetchkit import FetchResult
from jobrake.models import JobDict, Stopped
from jobrake.utils import finite


def read_json[T](
    result: FetchResult,
    unpack: Callable[[Any], T],
    *,
    site: str,
    board: str | None = None,
    unknown: str | None = None,
    partial: list[JobDict] | None = None,
) -> T:
    """
    Return what ``unpack`` takes from the JSON body of a site's response.

    ``unpack`` raises ``KeyError`` or ``TypeError`` for a body without what
    the site needs. ``board`` names the board in the message of a failed
    request. ``unknown`` is the message for a 404, which without it counts
    as a failed request. ``partial`` holds the postings of the pages before
    this one, which a failure keeps.

    Raises:
        Stopped: The site answered 404 and ``unknown`` is given, the request
            failed, or the body is unreadable.
    """
    partial = [] if partial is None else partial
    if result.status == 404 and unknown:
        raise Stopped(unknown, partial=partial)
    count = ngettext("%d posting", "%d postings", len(partial)) % len(partial)
    kept = f". Kept the {count} collected" if partial else ""
    if result.error:
        where = f" of board {board!r}" if board else ""
        raise Stopped(f"{site} search{where} stopped: {result.error}{kept}", partial=partial)
    # ValueError covers JSONDecodeError and an integer longer than Python reads.
    try:
        return unpack(json.loads(result.text))
    except (ValueError, KeyError, TypeError) as error:
        raise Stopped(
            f"{site} sent a response this version cannot read ({error!r}), "
            f"likely an API change{kept}",
            partial=partial,
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
        TypeError: The list is not a list, the count is not a number, or
            ``payload`` is not an object.
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
    item, which costs only that item and logs a warning.
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
