"""Tests for the text/date helpers."""

import logging

import pytest

from jobrake.utils import epoch_ms_to_date, html_text, iso_date


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


def test_iso_date_takes_dates_and_timestamps():
    assert iso_date("2026-08-05T08:04:27.000Z") == "2026-08-05"
    assert iso_date("2026-08-01") == "2026-08-01"
    assert iso_date(None) == ""


def test_iso_date_passes_junk_through_with_a_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="jobrake.utils"):
        assert iso_date("posted yesterday, allegedly") == "posted yes"
    assert any("ISO" in record.message for record in caplog.records)
