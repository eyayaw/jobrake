"""Tests for the text/date helpers."""

import pytest

from jobrake.utils import epoch_ms_to_date, html_text


def test_html_text_strips_tags_and_unescapes():
    assert html_text("<p>Turner &amp; Townsend</p>") == "Turner & Townsend"


def test_epoch_ms_to_date():
    assert epoch_ms_to_date(1717200000000) == "2024-06-01"


def test_epoch_ms_to_date_rejects_what_cannot_be_milliseconds():
    with pytest.raises(ValueError):
        epoch_ms_to_date("not a timestamp")
    with pytest.raises(ValueError):
        epoch_ms_to_date(1717200000)  # seconds: reads as 1970-01-20
    with pytest.raises(ValueError):
        epoch_ms_to_date(1e18)  # past what datetime can represent
