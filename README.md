# jobrake

The job boards shed new postings every day. Bring a rake. 🍂

<table>
<tr>
<td valign="top" width="55%">
<blockquote>
Read it as "<b>job-rake</b>". Say it fast and it is "<b>job break</b>". (^_~)
<br><br>
And if your name happens to be Jo, read it again: <b>Jo-brake</b>—the brake on the job-board doomscroll.
</blockquote>
</td>
<td valign="top">
<pre>
⠀⠀⠀⠀⠀⢠⣤⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⢻⣿⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⢻⣷⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⢿⣷⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠈⢿⣷⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⣿⣇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⣿⡆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢹⡿⠄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢠⣶⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠻⠿⠀⠀⠀⠀⠀⢀⣀⣀⣀⣤⣤⣤⡀⠀⠀
⠀⠀⠀⠀⠀⠀⣀⣀⣀⣠⣤⣤⣤⣶⣶⣶⣾⣿⣿⠿⣿⣿⠛⢻⣿⡋⢻⣷⠀⠀
⠀⢰⣾⣿⣿⣿⡿⠿⣿⣿⠛⢻⣯⠉⢻⣿⠀⠘⣿⠀⠘⣿⡄⠀⢿⡇⠀⢿⡇⠀
⠀⠈⢻⣇⠀⢹⣿⠀⠘⣿⡀⠘⣿⠀⠀⢿⡄⠀⢹⠀⠀⢹⡇⠀⠘⠇⠀⠘⠃⠀
⠀⠀⠀⢿⠀⠀⢿⠀⠀⠹⠇⠀⠙⠀⠀⠈⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠈⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
</pre>
</td>
</tr>
</table>

jobrake is a minimal Python package and CLI tool for scraping job postings from LinkedIn and Indeed.

<table>
<tr>
<td valign="top" width="50%">

```sh
jobrake --site linkedin \
  --search-term "data scientist" \
  --location "amsterdam, netherlands" \
  --radius 100 \
  --hours-old 48 \
  --results-wanted 5 \
  --detail
```

</td>
<td valign="top" width="50%">

```sh
jobrake -s indeed \
  -q "data scientist" \
  -l amsterdam -c netherlands \
  -r 100 \
  -a 48 \
  -n 5
# -d: # no need, search results contain details
```

</td>
</tr>
</table>

## Installation

Install from GitHub (not on PyPI) with [`uv`](https://github.com/astral-sh/uv):

```sh
uv add git+https://github.com/eyayaw/jobrake
# or, for the CLI alone:
uv tool install git+https://github.com/eyayaw/jobrake
```

## Usage

### CLI

```sh
jobrake --help
```

> [!TIP]
> Pipe it to [`jq`](https://github.com/jqlang/jq) to filter fields:
>
> ```sh
> jobrake -s indeed -q "data scientist" -c usa -n 2 | jq '.[] | [.date, .title, .company, .url] | @tsv'
>
> "2026-08-15\tApplied AI/Machine Learning Engineer\tOddball\thttps://www.indeed.com/viewjob?jk=c674b457443cf940"
> "2026-08-15\tSenior Data Scientist - Machine Learning\tGeneral Dynamics Information Technology\thttps://www.indeed.com/viewjob?jk=e422bd4de2737ee7"
> ```

Or write directly to a file with `--output | -o`; the extension determines the format: use `-o jobs.csv` for CSV, and `-o jobs.json` or `-o jobs.jsonl` for JSON. CSV keeps a fixed column for each model field, with empty cells for unavailable values. JSON and JSONL keep every identity and summary key while omitting unavailable detail keys.

> [!TIP]
> `-o` replaces the file, so give each run its own; jsonl files then merge with a plain `cat`:
>
> ```sh
> jobrake ... -o runs/2026-08-10.jsonl   # Monday's run
> jobrake ... -o runs/2026-08-11.jsonl   # Tuesday's run
> cat runs/*.jsonl | jq ...              # merge them
> ```

### As a library

```python
import asyncio
import json

from jobrake import scrape


async def main():
    jobs = await scrape(
        "indeed",
        search_term="economist",
        country="United States",
        results_wanted=2,
        hours_old=24,
    )
    print(json.dumps(jobs, indent=2))


asyncio.run(main())
```
<details>
<summary>Expand for the output</summary>

```json
[
  {
    "site": "indeed",
    "id": "44509a9a68d72bcc",
    "url": "https://www.indeed.com/viewjob?jk=44509a9a68d72bcc",
    "title": "Technical Quantitative Analyst",
    "company": "Systems Planning and Analysis, Inc. (SPA)",
    "location": "Arlington, VA, US",
    "date": "2026-08-19",
    "description": "Overview:\nSystems Planning and Analysis, Inc. (SPA) delivers high-impact, technical solutions to complex national security issues. With over 50 years of business expertise and consistent growth, we are known for continuous innovation for our government customers, in both the US and abroad. Our exceptionally talented team is highly collaborative in spirit and practice, producing Results that Matter. Come work with the best! We offer opportunity, unique challenges, and clear-sighted commitment to the mission. SPA: Objective. Responsive. Trusted.\nThe Joint, Office of the Secretary of Defense, Interagency Division provides expert support services to a range of customers spanning across the Department of Defense, Federal Civilian, and international markets. JOID provides a diverse portfolio of analytical and programmatic capabilities to help our customers make informed decisions on their most challenging issues.\nSPA provides critical decision support to enabling and executing a strategy of technological superiority and enabling the delivery and sustainment of secure, resilient, and preeminent capabilities to the warfighter quickly and cost effectively. Our team of experienced military, technical, and operations research analysts is skilled in evaluating military problems, identifying the driving factors, devising innovative approaches, collecting applicable data, developing necessary software tools, and performing thorough and timely assessments to inform technology and acquisition governance decisions to ensure U.S. military forces retain military superiority in the future.\nWe have an immediate need for a Quantitative Analyst SETA to provide onsite support out of Arlington, VA.\nResponsibilities:\nThe successful candidate will serve as a Quantitative Analyst SETA supporting DARPA program managers in the development, integration, and scaling of complex adaptive system modelling and data-intensive analytical capabilities. This role involves integrating complex, multi-source intelligence and commercial/open-source data streams into graph-based, network analytical frameworks to support strategic competition analysis, industrial base resilience, and national security decision-making. The candidate will serve as the primary technical liaison between academic researchers, software engineering teams, and IC stakeholders to ensure tools align with operational requirements. Will also advise DARPA leadership on program execution risks, data architecture scalability, and capability transition strategy.\nQualifications:\nRequired:\nMaster\u2019s degree or PhD in Economics, Data Science, Applied Mathematics, or a related quantitative field\nActive TS/SCI clearance\n5+ years of relevant experience in quantitative economic modeling, advanced econometrics, and network data science/data engineering applied to complex adaptive systems\nDemonstrated experience in large-scale data processing, multi-source data pipeline integration, and managing structured/unstructured data architectures\nPractical experience with graph analytics, network modeling tools, and interconnected data architectures (e.g., Python/R quantitative libraries, graph databases, or network science frameworks)\nStrong background working within or alongside the U.S. Intelligence Community (IC), including familiarity with IC mission environments, data workflows, and intelligence-derived datasets\nUnderstanding of diverse data sources across global economics, financial networks, trade flows, defense industrial supply chains, and multi-INT sources\nAble to work fully onsite based on client needs\nTravel to support program operations up to 15% duty factor\nDesired:\nStrong communication skills\u2014both written (including executive PowerPoint briefs) and oral\u2014with the ability to translate complex econometric and data models for senior defense stakeholders\nExperience with defense industrial base analysis, economic statecraft, strategic competition modeling, or macroeconomic resilience metrics\nHands-on experience building decision-support tools, AI/ML-enabled analytical tools, cloud data engineering workflows, or large language model (LLM) research pipelines\nExperience in high paced private sector quantitative production environment such as systematic investing or trading, real time ad technology development or pharmacological optimization and customization\nPay Range Information: At SPA, we strive to deliver a robust total compensation package that will attract and retain top talent. Elements of the compensation package include competitive base pay and variable compensation opportunities. SPA provides eligible employees with an opportunity to enroll in a variety of benefit programs, generally including health insurance, flexible spending accounts, health savings accounts, retirement savings plans, life and disability insurance programs, and a number of programs that provide for both paid and unpaid time away from work. The specific programs and options available to any given employee may vary depending on eligibility factors such as geographic location, date of hire, etc. Please note that the salary information shown below is a general guideline only. Salaries are commensurate with experience and qualifications, as well as market and business considerations. Virginia, Pay Transparency Salary range: USD $160,000.00/Yr. - USD $200,000.00/Yr.",
    "company_url": "https://www.indeed.com/cmp/Systems-Planning-and-Analysis,-Inc.-(spa)",
    "company_logo": "https://d2q79iu7y748jz.cloudfront.net/s/_squarelogo/256x256/dcf51558b2ac901be663279d5a47cecf",
    "employment_type": "full_time",
    "salary_min": 160000.0,
    "salary_max": 200000.0,
    "salary_currency": "USD",
    "salary_period": "YEAR",
    "city": "Arlington",
    "region": "VA",
    "country_code": "US",
    "latitude": 38.875126,
    "longitude": -77.119606,
    "posted_at": "2026-08-19T05:00:00+00:00",
    "apply_url": "https://talent.spa.com/jobs/23276/job?utm_source=indeed_integration&iis=Job%20Board&iisn=Indeed&indeed-apply-token=73a2d2b2a8d6d5c0a62696875eaebd669103652d3f0c2cd5445d3e66b1592b0f"
  },
  {
    "site": "indeed",
    "id": "05af5f7e6601cbed",
    "url": "https://www.indeed.com/viewjob?jk=05af5f7e6601cbed",
    "title": "Data Analyst, Principal",
    "company": "Atlanta Regional Commission",
    "location": "Atlanta, GA, US",
    "date": "2026-08-19",
    "description": "Job Description:\nThe Atlanta Regional Commission (ARC) serves as the regional planning and intergovernmental coordination agency for metro Atlanta, working to foster thriving communities across the region through collaborative, data-informed planning and investment. ARC coordinates regional growth and development, transportation, and natural resource planning to prepare for the future of the metro Atlanta region. Central to this mission is the calibration and application of socioeconomic models that generate accurate, reliable, and defensible regional forecasts, which serve as the foundation for sound long-range planning decisions across the region.\nThe ARC Office of Research and Innovation is seeking a Principal Data Analyst to manage and enhance our regional forecasting program. In this role, the Principal Data Analyst will lead the application and enhancement of ARC\u2019s REMI (Regional Economic Models, Inc.) modeling platform, develop regional socioeconomic forecasts, conduct economic impact analyses, and produce data, insights, and strategic intelligence that support critical regional initiatives, policy decisions, and planning priorities. This position serves as a key technical leader in ensuring the rigor, accuracy, and policy relevance of the forecasts and analyses that inform regional planning and decision-making. The Principal Data Analyst will also collaborate closely with internal and external stakeholders to translate complex economic and demographic trends into actionable insights that support ARC\u2019s long-range vision and strategic objectives.\nEssential Duties and Responsibilities:\nCalibrate, enhance, and run the REMI economic modeling application to develop regional socioeconomic forecasts to support agency planning priorities.\nCompile, process, and integrate data from federal, state, local, and proprietary sources (e.g., Census, BEA, BLS, Woods & Poole) to support modeling and forecasting.\nDocument modeling assumptions, methodologies, and data sources to ensure transparency, reproducibility, and defensibility of forecasts.\nDevelop economic impact analysis to evaluate the effects of policies, investments, and major initiatives on the region.\nTranslate complex analytical results into clear reports, visualizations, briefings, and presentations for technical and non-technical audiences, including staff, member governments, and stakeholders.\nSupport ARC spatial economic modeling projects.\nCollaborate with planning, transportation, natural resources, and other departments to align forecasts and analyses with agency planning needs and priorities.\nRespond to data and analysis requests from internal teams, local governments, partner agencies, and the public.\nStay current with advances in economic modeling, forecasting methods, and data-analysis tools, and recommend improvements to ARC\u2019s modeling and forecasting capabilities.\nPerform other related duties as assigned.\nMinimum Qualifications:\nEducation: Bachelor\u2019s degree in Economics, Statistics, Data Science, Urban/Regional Planning, Public Policy, or a closely related field.\nExperience: A minimum of three (3) years of progressively responsible experience in economic modeling, forecasting, planning, data analysis, or applied quantitative research.\nOR\nAn equivalent combination of education and experience sufficient to successfully perform the essential duties of the job such as those listed above, unless otherwise subject to any other requirements set forth in law or regulation.\nPreferred Qualifications:\nA master\u2019s degree or doctoral degree is preferred.\nHands-on experience with REMI is strongly preferred.\nProficiency with statistical and data analysis tools is preferred.\nExperience in a regional planning, government, or public-sector research setting.\nFamiliarity with regional transportation, landuse, or demographic forecasting models.\nRequired Knowledge, Skills, Abilities and Competencies:\nStrong understanding of regional and urban economics, demography, and applied econometrics.\nProficiency with ArcGIS Pro for spatial data analysis and mapping.\nDemonstrated experience developing, running, and interpreting econometric or economic impact models.\nExperience working with major socioeconomic and economic data sources (e.g., U.S. Census, ACS, BEA, BLS).\nStrong data visualization and reporting skills.\nCommitment to accuracy, transparency, and reproducibility in analytical work.\nHigh attention to detail, intellectual curiosity, and adaptability. Comfortable working independently and as part of cross-functional teams.\nStrong organizational skills and the ability to manage multiple concurrent projects, track progress, and coordinate with internal and external stakeholders.\nExcellent written and verbal communication skills.\nAdditional Information\nAbout ARC:\nThe Atlanta Regional Commission (ARC) is the regional planning and intergovernmental coordination agency that focuses on issues critical to the region\u2019s success, including growth and development, transportation, water resources, services for older adults and workforce solutions. ARC is dedicated to unifying the region\u2019s collective resources to prepare the metropolitan area for a prosperous future. This is done through professional planning initiatives, the provision of objective information and the involvement of the community in collaborative partnerships.\nARC Strategic Framework\nVision \u2014 ONE great REGION\nMission Statement\nThe Atlanta Regional Commission fosters thriving communities for all within the Atlanta region through collaborative, data-informed planning and investments.\nOur Goals\nHealthy, safe, livable communities in the Atlanta metro area.\nStrategic investments in people, infrastructure, mobility, and preserving natural resources.\nRegional services delivered with operational excellence and efficiency.\nDiverse stakeholders engage and take a regional approach to solve local issues.\nA competitive economy that is inclusive, innovative, and resilient.\nOur Core Values\nExcellence | A commitment to doing our best and going above and beyond in every facet of our work allowing for innovative practices and actions to be created while ensuring our agency\u2019s and our colleague\u2019s success.\nEquity | We represent a belief that there are some things which people should have, that there are basic needs that should be fulfilled, that burdens and rewards should not be spread too divergently across the community, and that policy should be directed with impartiality, fairness and justice towards these ends.\nIntegrity | In our conduct, communication, and collaboration with each other and the region\u2019s residents, we will act with consistency, honesty, transparency, fairness and accountability within and across each of our responsibilities and functions.\nApplication Process:\nThe Atlanta Regional Commission is looking for individuals who enjoy working in a public service environment where the mission is to improve the quality of life for the citizens of the Atlanta region. ARC serves as a forum where leaders come together to discuss and act on issues of regionwide consequence, so it is important that our staff share the public entrepreneurial spirit that defines ARC.\nAs an Equal Opportunity Employer, ARC does not discriminate on the basis of race, color, age, national origin, sex, religion or disability.\nTo request a reasonable accommodation during the application, interview, or testing process, please contact ARC at 404-463-3100 or Human Resources via email at hr@atlantaregional.org.\nARC offers our full-time regular employees a comprehensive and competitive benefits package which includes health insurance, life insurance, retirement benefits, paid time off and more!",
    "company_url": "https://www.indeed.com/cmp/Atlanta-Regional-Commission",
    "employment_type": "full_time",
    "salary_min": 69460.0,
    "salary_max": 93771.0,
    "salary_currency": "USD",
    "salary_period": "YEAR",
    "city": "Atlanta",
    "region": "GA",
    "country_code": "US",
    "latitude": 33.755077,
    "longitude": -84.384544,
    "posted_at": "2026-08-19T05:00:00+00:00",
    "apply_url": "https://www.governmentjobs.com/careers/atlantaregional/jobs/5453248/data-analyst-principal"
  }
]
````
</details>

Every job posting comes back as a flat dict. The `site`, `id`, and `url` fields uniquely identify the posting. The `title`, `company`, `location`, and `date` keys are in every job. Each value is `None` when unavailable, so every job has the same seven identity and summary keys. The rest, `description` and detail fields such as `salary_min`, `employment_type`, and `applicants`, are retrieved from the posting itself and appear only where a value is available. An absent detail key does not say why the value is missing: the posting may omit the field, the site may never publish it, or the page may not have been fetched. All (common) fields have the same meaning across sites, and a field only one site publishes appears only in that site's jobs: `apply_type`, `applicants`, `experience_months`, and `education` come from LinkedIn, `is_remote` and `apply_url` from Indeed. Indeed includes the detail fields in the search response, but LinkedIn requires the `--detail | -d` flag.

`scrape` creates and closes its own fetcher on every call. Pass your own to reuse one session across searches, or to set timeouts, headers, or cookies.

> [!TIP]
> ### Custom fetchers
>
> ```python
> import asyncio
>
> from jobrake import scrape
> from jobrake.fetchkit import HttpxFetcher
>
>
> async def main():
>     async with HttpxFetcher(timeout=30) as fetcher:
>         nl = await scrape(
>             "indeed",
>             search_term="economist",
>             location="Amsterdam",
>             country="Netherlands",
>             fetcher=fetcher,
>         )
>         us = await scrape(
>             "indeed",
>             search_term="economist",
>             location="New York",
>             country="USA",
>             fetcher=fetcher,
>         )
>         return nl, us
>
>
> nl, us = asyncio.run(main())
> ```
> To create a custom fetcher, e.g., around another HTTP client or a browser, subclass `jobrake.fetchkit.BaseFetcher`. Its `fetch` turns any `Exception` the transport raises into an error result. A failed request costs that page and the run continues. Cancellation and exceptions raised outside that boundary propagate.

## Locations and countries

Each site has one **required geographic argument**.

- Indeed needs `country` to pick the edition it queries: a name like `germany`, not an ISO code like `de`.

- LinkedIn needs `location` and ignores `country`. Always make your place names unambiguous, e.g., "Amsterdam, North Holland, Netherlands". A location LinkedIn cannot resolve returns an empty result, with a warning.

The search radius (`--radius` in the cli) is in **kilometers**. The CLI defaults it to 50 and `--hours-old` to 24: postings older than a day are filtered unless you widen it (e.g., `-a 168` for a week). The library's `scrape()` defaults both to `None`: no age filter, and the site's own radius default. See other defaults in [defaults.py](src/jobrake/defaults.py).

## Supported job boards

| Site       | Mechanism                     | Notes                                                                                                      |
| ---------- | ----------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `indeed`   | Mobile-app GraphQL API (POST) | fast and reliable; full descriptions and detail in the search response                                     |
| `linkedin` | Guest search API (HTML cards) | token-bucket pacing (short burst, then ~one request per 3s); optional per-job detail fetch, cached on disk |

<details>
<summary>Glassdoor</summary>
Unlike jobspy, jobrake does not support Glassdoor. Since July 1, 2026, it is <a href="https://web.archive.org/web/20260704043638/https://www.glassdoor.com/about/">part of Indeed</a> and likely serves the same inventory. It is not a priority, but a PR is welcome—for Glassdoor or any other major job board.
</details>

### LinkedIn: Rate limiting and posting detail

LinkedIn rate-limits each visitor, per IP. A few requests may burst immediately, then roughly one every couple of seconds. Search pages are limited more strictly than job-detail pages.

> [!NOTE]
> Each jobrake run keeps its own token bucket and waits before every request until the next one is allowed—roughly one request per **three seconds** after a short burst. The bucket counts only its own requests, while LinkedIn's budget covers everything your IP sends, so a second run from the same address draws down the same allowance. A request that still receives a 429 is retried once after the limit clears.

We extract summary fields from the search results. The description and the rest of attributes live on the job's posting page, so this requires an extra request per job against the same rate limit. Use `--detail | -d` in the CLI to fetch these attributes.

Fetched postings are cached on disk for a week (see [`TTL`](src/jobrake/cache.py)) in your user cache directory, so repeated runs only pay for postings that have not been seen. A posting that is gone (404/410) is remembered and skipped on later cached runs. Pass `--no-cache` (or `cache=False`) to bypass the cache.

I advise being gentle with the guest API. Detail fetches cost one paced request per job, so a long list takes its time by design. The cache makes repeats cheap. If you want only some of the jobs, list without `-d` and fetch the interesting ones with `linkedin.fetch_postings(fetcher, urls)`. It maps each URL to the posting's fields or to `None` when the posting is gone (404/410). A URL that failed transiently is absent and safe to retry.

```py
import asyncio
from jobrake.sites import linkedin, scrape
from jobrake.fetchkit import HttpxFetcher
search_results = asyncio.run(
scrape(
    "linkedin", 
    search_term="data scientist",
    location="amsterdam, netherlands", 
    results_wanted=10
))
# Inspect the results and keep the interesting ones and fetch the details for those.
leads = [job["url"] for job in search_results if not "senior" in (job.get("title") or "").lower()]
jobs = asyncio.run(linkedin.fetch_postings(HttpxFetcher(), leads))
```

## Credits

jobrake owes a lot to [python-jobspy](https://pypi.org/project/python-jobspy/): the Indeed mobile-app GraphQL endpoint, its public app key, and the LinkedIn guest-search approach were all adapted from it. Thanks.

## Disclaimer

> [!WARNING]
> Scraping these sites may violate their terms of service. This package is not affiliated with any site it scrapes; check their terms and decide for yourself whether your use complies.
