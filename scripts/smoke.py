"""Live smoke: one query per site, sequential, polite. Run: uv run scripts/smoke.py"""

import asyncio

from jobrake import scrape


async def main():
    for site in ("indeed", "linkedin"):
        try:
            jobs = await scrape(
                site,
                search_term="economist",
                location="United States",
                country="usa",
                results_wanted=10,
                hours_old=168,
            )
            print(f"{site}: {len(jobs)} jobs")
            for job in jobs[:3]:
                print(
                    f"  [{job['date'] or '????-??-??'}] {job['title'][:44]:<45} "
                    f"{job['company'][:20]:<21} {job['location'][:24]:<25} "
                    f"desc={len(job['description'])}ch"
                )
        except Exception as e:
            print(f"{site}: FAILED {type(e).__name__}: {e}")
        await asyncio.sleep(3)


asyncio.run(main())
