"""Indeed country-edition lookup tests."""

import pytest

from jobrake.countries import indeed_domain


def test_indeed_domain_aliases_and_api_codes():
    assert indeed_domain("usa") == ("www", "US")
    assert indeed_domain("United States") == ("www", "US")
    assert indeed_domain("uk") == ("uk", "GB")
    assert indeed_domain("netherlands") == ("nl", "NL")


def test_indeed_domain_rejects_unknown_country():
    with pytest.raises(ValueError, match="Atlantis"):
        indeed_domain("Atlantis")
