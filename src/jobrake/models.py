"""The job dict: one shape for every site."""


def make_job(
    *,
    id: str,
    title: str,
    company: str,
    url: str,
    site: str,
    location: str,
    description: str = "",
    date: str = "",
) -> dict:
    """
    Normalize scraped fields into the job dict.

    ``id`` is the site-local posting identifier (LinkedIn's numeric posting
    id, Indeed's job key): stable per posting, unique only within a site.
    """
    return {
        "id": (id or "").strip(),
        "title": (title or "").strip(),
        "company": (company or "").strip(),
        "url": (url or "").strip(),
        "location": (location or "").strip(),
        "description": (description or "").strip(),
        "date": (date or "")[:10],
        "site": site,
    }


# Derived, not declared, so the field list can never drift from the dict shape.
JOB_FIELDS = tuple(make_job(id="", title="", company="", url="", site="", location=""))
