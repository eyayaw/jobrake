"""Indeed country editions by ISO 3166-1 alpha-2 code."""

from typing import Annotated

# The country option of every Indeed function that searches one edition.
Country = Annotated[str, "ISO 3166-1 alpha-2 code of an Indeed edition, e.g., de, gb, or us"]

# The country sites Indeed lists at https://www.indeed.com/worldwide, as read
# on 2026-10-29. The code is also the edition's API code and, except in
# _SUBDOMAINS, its website subdomain. The API answered HTTP 400 for unlisted
# countries we tried, such as SI and HR.
# fmt: off
_EDITIONS = {
    "ae", "ar", "at", "au", "be", "bh", "br", "ca", "ch", "cl", "cn", "co", "cr",
    "cz", "de", "dk", "ec", "eg", "es", "fi", "fr", "gb", "gr", "hk", "hu", "id",
    "ie", "il", "in", "it", "jp", "kr", "kw", "lu", "ma", "mx", "my", "ng", "nl",
    "no", "nz", "om", "pa", "pe", "ph", "pk", "pl", "pt", "qa", "ro", "sa", "se",
    "sg", "th", "tr", "tw", "ua", "us", "uy", "ve", "vn", "za",
}
# fmt: on
_SUBDOMAINS = {"gb": "uk", "my": "malaysia", "us": "www"}


def indeed_domain(country: str) -> tuple[str, str]:
    """
    Resolve an ISO country code, in either case, to an Indeed edition.

    Returns:
        The website subdomain and uppercase API country code.

    Raises:
        ValueError: No Indeed edition has the code.
    """
    code = country.strip().lower()
    if code not in _EDITIONS:
        raise ValueError(
            f"unknown Indeed country {country!r}. Pass the ISO 3166-1 alpha-2 code of an "
            f"Indeed edition: {' '.join(sorted(_EDITIONS))}"
        )
    return _SUBDOMAINS.get(code, code), code.upper()
