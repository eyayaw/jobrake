"""Search a fake job board."""

from typing import Annotated

from jobrake.models import JobDict, make_job

calls: list[dict[str, object]] = []  # the options of each search; the fake_site fixture resets it


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
    return [
        make_job(site="fakesite", id=str(n), url=f"https://fake.test/{n}") for n in range(results)
    ]
