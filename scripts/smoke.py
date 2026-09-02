"""Query each site once, in sequence, with ``uv run scripts/smoke.py``."""

import asyncio

from jobrake import scrape


def column(value, width):
    # Title, company, and location are nullable summary fields.
    return f"{(value or '?')[:width]:<{width + 1}}"


async def main():
    """Run one small search per provider and print representative fields."""
    for site in ("indeed", "linkedin"):
        try:
            jobs = await scrape(
                site,
                query="economist",
                location="United States",
                country="usa",
                results=10,
                max_age_hours=168,
            )
            print(f"{site}: {len(jobs)} jobs")
            for job in jobs[:3]:
                print(
                    f"  [{job['date'] or '????-??-??'}] {column(job['title'], 44)} "
                    f"{column(job['company'], 20)} {column(job['location'], 24)} "
                    f"desc={len(job.get('description', ''))}ch"
                )
        except Exception as e:
            print(f"{site}: FAILED {type(e).__name__}: {e}")
        await asyncio.sleep(3)


asyncio.run(main())
