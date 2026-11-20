"""Reading a site's responses: one JSON, XML, or HTML body, its postings, and a search's pages."""

import json
import logging
import xml.etree.ElementTree as ET
from collections.abc import AsyncGenerator, Callable, Set
from contextlib import suppress
from gettext import ngettext
from typing import Any

lazy from bs4 import BeautifulSoup

from jobrake.fetchkit import FetchResult
from jobrake.models import JobDict, Stopped
from jobrake.utils import finite, report_progress

# What a parser raises for site data it cannot read: a missing key or index, a value of the wrong
# type, text that does not parse, such as JSON, a number, a date, or a URL, or JSON nested deeper
# than Python's recursion limit.
UNREADABLE = (TypeError, ValueError, LookupError, AttributeError, RecursionError)


def _stop_if_failed(result: FetchResult, site: str, board: str | None, unknown: str | None) -> None:
    if result.status == 404 and unknown:
        raise Stopped(unknown)
    if result.error:
        where = f" for board {board!r}" if board else ""
        raise Stopped(f"{site} request{where} failed: {result.error}")


def _unreadable(site: str, error: Exception) -> Stopped:
    return Stopped(
        f"{site} sent a response this version cannot read ({error!r}), likely an API change"
    )


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

    ``unpack`` raises one of ``UNREADABLE`` for a body without what the site needs.
    ``board`` names the board in the message of a failed request.
    ``unknown`` is the message for a 404, which without it counts as a failed request.

    Raises:
        Stopped: The site answered 404 and ``unknown`` is given, the request failed,
            or the body is unreadable.
    """
    _stop_if_failed(result, site, board, unknown)
    try:
        return unpack(json.loads(result.text))
    except UNREADABLE as error:
        # Workday answers 200 with its maintenance page while a data center is down (measured
        # 2026-11-14 on two career sites).
        if result.text.lstrip().startswith("<"):
            raise Stopped(
                f"{site} sent a web page where its API sends JSON, so the site may be "
                "under maintenance. Try again later"
            ) from error
        raise _unreadable(site, error) from error


def read_xml[T](
    result: FetchResult,
    unpack: Callable[[ET.Element], T],
    *,
    site: str,
    board: str | None = None,
    unknown: str | None = None,
) -> T:
    """
    Return what ``unpack`` takes from the root element of a site's XML response.

    ``unpack`` raises one of ``UNREADABLE`` for a document without what the site needs.
    ``board`` and ``unknown`` work as in ``read_json``.

    Raises:
        Stopped: The site answered 404 and ``unknown`` is given, the request failed,
            or the body is unreadable.
    """
    _stop_if_failed(result, site, board, unknown)
    # Expat opens no file or connection, and Expat 2.7.2 and later limit entity expansion
    # (https://docs.python.org/3/library/xml.html, 2026-11-15).
    try:
        return unpack(ET.fromstring(result.text))
    except (ET.ParseError, *UNREADABLE) as error:
        raise _unreadable(site, error) from error


def read_html[T](result: FetchResult, unpack: Callable[[BeautifulSoup], T], *, site: str) -> T:
    """
    Return what ``unpack`` takes from the HTML page of a site's response.

    ``unpack`` raises one of ``UNREADABLE`` for a page without what the site needs.

    Raises:
        Stopped: The request failed or the page is unreadable.
    """
    _stop_if_failed(result, site, None, None)
    try:
        return unpack(BeautifulSoup(result.text, "html.parser"))
    except UNREADABLE as error:
        raise _unreadable(site, error) from error


def json_ld(page: BeautifulSoup, types: Set[str]) -> list[dict[str, Any]]:
    """
    Return the page's JSON-LD nodes whose ``@type`` names one of ``types``, in page order.

    A node may head a script, sit in a top-level array, or sit in an ``@graph``, and its ``@type``
    may be a list (JSON-LD 1.1, sections 3.5, 4.9, and 9, checked 2026-11-20). A script that does
    not parse is skipped, so the page's other nodes stay readable.
    """
    # A stack, so the nodes come out in document order without recursing into the page's nesting.
    stack: list[Any] = []
    for script in reversed(page.find_all("script", type="application/ld+json")):
        with suppress(ValueError, RecursionError):
            stack.append(json.loads(script.get_text()))
    nodes = []
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            stack.extend(reversed(node))
        elif isinstance(node, dict):
            kind = node.get("@type")
            kinds = kind if isinstance(kind, list) else [kind]
            if not types.isdisjoint(k for k in kinds if isinstance(k, str)):
                nodes.append(node)
            stack.append(node.get("@graph"))
    return nodes


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
    Return a page's ``payload[key]`` list and the count of all matches in ``payload[total]``.

    Raises:
        KeyError: ``payload`` lacks ``key`` or ``total``.
        TypeError: ``payload[key]`` is not a list, ``payload[total]`` is not a number,
            or ``payload`` is not an object.
    """
    count = finite(payload[total])
    if count is None:
        raise TypeError(f"{total} {payload[total]!r} is not a number")
    return json_list(payload, key), int(count)


def cut_short(where: str, total: int, offset: int) -> Stopped:
    """
    Return the ``Stopped`` for an empty page that came before the ``total`` a search reported.

    ``where`` names the site, and the board when it has one. ``offset`` counts the cards sent.
    """
    return Stopped(
        f"{where} reported {total} postings but sent an empty page after {offset}, so the result "
        "may be incomplete. Postings may have closed during the search. A rerun reads the "
        "current list"
    )


def parse_postings(
    items: list[Any], parse: Callable[[Any], JobDict], *, site: str
) -> list[JobDict]:
    """
    Parse each item of a site's posting list, skipping one that ``parse`` rejects.

    ``parse`` raises one of ``UNREADABLE`` for a malformed item, which is left out of the result
    and logged as a warning.
    """
    # The site's own logger, so a handler set on one site still sees its warnings.
    logger = logging.getLogger(f"jobrake.sites.{site}")
    jobs = []
    for item in items:
        try:
            jobs.append(parse(item))
        except UNREADABLE as error:
            logger.warning("skipping malformed %s posting: %r", site, error)
    return jobs


async def collect(
    site: str, pages: AsyncGenerator[tuple[list[JobDict], int]], results: int
) -> list[JobDict]:
    """
    Gather a search's pages into at most ``results`` postings, in the site's order.

    ``pages`` yields each page's postings with the count the site can serve for the search,
    and ends where the site does. It is asked for a page only while postings are missing,
    so the code after its last ``yield`` runs only for a search the site ended short of ``results``.
    A posting that a later page repeats is kept once, and each page logs a progress record.

    Raises:
        Stopped: ``pages`` raised it. ``partial`` holds the postings of the pages before it,
            which the message counts.
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
