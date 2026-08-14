"""Country editions: name aliases -> (subdomain, API country code)."""

from __future__ import annotations

# Ported from jobspy's Country enum, keeping only what Indeed needs. A value
# is the subdomain; where the API code differs it is "subdomain:code".
# fmt: off
_INDEED = {
    "argentina": "ar", "australia": "au", "austria": "at", "bahrain": "bh",
    "bangladesh": "bd", "belgium": "be", "bulgaria": "bg", "brazil": "br",
    "canada": "ca", "chile": "cl", "china": "cn", "colombia": "co",
    "costa rica": "cr", "croatia": "hr", "cyprus": "cy",
    "czech republic": "cz", "czechia": "cz", "denmark": "dk", "ecuador": "ec",
    "egypt": "eg", "estonia": "ee", "finland": "fi", "france": "fr",
    "germany": "de", "greece": "gr", "hong kong": "hk", "hungary": "hu",
    "india": "in", "indonesia": "id", "ireland": "ie", "israel": "il",
    "italy": "it", "japan": "jp", "kuwait": "kw", "latvia": "lv",
    "lithuania": "lt", "luxembourg": "lu", "malaysia": "malaysia:my",
    "malta": "malta:mt", "mexico": "mx", "morocco": "ma", "netherlands": "nl",
    "new zealand": "nz", "nigeria": "ng", "norway": "no", "oman": "om",
    "pakistan": "pk", "panama": "pa", "peru": "pe", "philippines": "ph",
    "poland": "pl", "portugal": "pt", "qatar": "qa", "romania": "ro",
    "saudi arabia": "sa", "singapore": "sg", "slovakia": "sk",
    "slovenia": "sl", "south africa": "za", "south korea": "kr",
    "spain": "es", "sweden": "se", "switzerland": "ch", "taiwan": "tw",
    "thailand": "th", "türkiye": "tr", "turkey": "tr", "ukraine": "ua",
    "united arab emirates": "ae", "uk": "uk:gb", "united kingdom": "uk:gb",
    "usa": "www:us", "us": "www:us", "united states": "www:us",
    "uruguay": "uy", "venezuela": "ve", "vietnam": "vn",
}
# fmt: on


def indeed_domain(country: str) -> tuple[str, str]:
    """(subdomain, API country code) for an Indeed country edition."""
    try:
        value = _INDEED[country.strip().lower()]
    except KeyError:
        raise ValueError(
            f"unknown Indeed country {country!r}; one of {', '.join(sorted(_INDEED))}"
        ) from None
    subdomain, _, code = value.partition(":")
    return subdomain, (code or subdomain).upper()
