"""Search a fake job board."""

from typing import Annotated

from jobrake import Stopped
from jobrake.models import JobDict, make_job
from jobrake.utils import checked

calls: list[dict[str, object]] = []  # the arguments of each call; the fake_site fixture resets it


def job(posting_id: str) -> JobDict:
    return make_job(site="fakesite", id=posting_id, url=f"https://fake.test/{posting_id}")


@checked
async def search(
    fetcher,
    *,
    query: Annotated[str, "job title or keywords"],
    board: Annotated[str | None, "employer board name"] = None,
    results: Annotated[int, "maximum number of postings"] = 10,
    remote: Annotated[bool, "only remote postings"] = False,
    tags: Annotated[list[str] | None, "tags a posting must carry"] = None,
) -> list[JobDict]:
    calls.append(
        {"query": query, "board": board, "results": results, "remote": remote, "tags": tags}
    )
    return [job(str(n)) for n in range(results)]


@checked
async def places(
    fetcher,
    name: Annotated[str, "place name"],
    *,
    region: Annotated[str | None, "region to look in"] = None,
) -> list[dict[str, str]]:
    """List the fake board's places for a name."""
    calls.append({"name": name, "region": region})
    if not name.strip():
        raise ValueError("place name is blank")
    if name == "offline":
        raise Stopped("place lookup failed: connection reset", partial=[])
    return [] if name == "nowhere" else [{"id": "1", "name": name}]


@checked
async def postings(
    fetcher,
    references: Annotated[list[str], "posting IDs or URLs"],
    *,
    refresh: Annotated[bool, "refetch postings"] = False,
) -> dict[str, JobDict | None]:
    """Fetch known fake postings by ID or URL."""
    references = list(references)
    calls.append({"references": references, "refresh": refresh})
    ids = {ref: ref.removeprefix("https://fake.test/") for ref in references}
    # "gone" is a posting the board reports gone, and "failed" one whose request failed.
    return {ref: None if pid == "gone" else job(pid) for ref, pid in ids.items() if pid != "failed"}
