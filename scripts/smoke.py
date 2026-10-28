"""Query each site once, in sequence, with ``uv run scripts/smoke.py``."""

import asyncio
from typing import Any

from jobrake import scrape

# Each site names the United States its own way.
PLACES: dict[str, dict[str, Any]] = {
    "indeed": {"country": "usa"},
    "linkedin": {"location": "United States"},
}


def column(value: str | None, width: int) -> str:
    # Title and company are nullable summary fields, and a posting can name no place.
    return f"{(value or '?')[:width]:<{width + 1}}"


async def main() -> None:
    """Run one small search per site and print representative fields."""
    for site, place in PLACES.items():
        try:
            jobs = await scrape(site, query="economist", results=10, max_age_hours=168, **place)
            print(f"{site}: {len(jobs)} jobs")
            for job in jobs[:3]:
                print(
                    f"  [{job['date'] or '????-??-??'}] {column(job['title'], 44)} "
                    f"{column(job['company'], 20)} {column('; '.join(place['name'] for place in job['locations']), 24)} "
                    f"desc={len(job.get('description', ''))}ch"
                )
        except Exception as e:  # noqa: BLE001  a smoke run reports each site's failure and goes on
            print(f"{site}: FAILED {type(e).__name__}: {e}")
        await asyncio.sleep(3)


asyncio.run(main())
