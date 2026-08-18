"""Tests for the text/date helpers."""

import logging

import pytest

from jobrake.utils import epoch_ms_to_iso, html_text, iso_date


def test_html_text_strips_tags_and_unescapes():
    assert html_text("<p>Turner &amp; Townsend</p>") == "Turner & Townsend"


def test_html_text_one_line_per_block():
    html = "<h2>The role</h2><p>Build <b>models</b> daily.</p><ul><li>Ship</li><li>Learn</li></ul>"
    assert html_text(html) == "The role\nBuild models daily.\nShip\nLearn"


def test_html_text_spaces_table_cells():
    html = "<table><tr><td>Clearance</td><td>None</td></tr><tr><td>Type</td><td>Regular</td></tr></table>"
    assert html_text(html) == "Clearance None\nType Regular"


def test_html_text_drops_style_bodies():
    assert html_text("<style>p { color: red; }</style><p>Prose stays.</p>") == "Prose stays."


def test_epoch_ms_to_iso():
    assert epoch_ms_to_iso(1717200000000) == "2024-06-01T00:00:00+00:00"


def test_epoch_ms_to_iso_rejects_what_cannot_be_milliseconds():
    with pytest.raises(ValueError, match="not epoch milliseconds"):
        epoch_ms_to_iso("not a timestamp")
    with pytest.raises(ValueError):
        epoch_ms_to_iso(1717200000)  # seconds: reads as 1970-01-20
    with pytest.raises(ValueError):
        epoch_ms_to_iso(1e18)  # past what datetime can represent


def test_iso_date_takes_dates_and_timestamps():
    assert iso_date("2026-08-05T08:04:27.000Z") == "2026-08-05"
    assert iso_date("2026-08-01") == "2026-08-01"
    assert iso_date(None) is None


def test_iso_date_passes_junk_through_with_a_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="jobrake.utils"):
        assert iso_date("posted yesterday, allegedly") == "posted yes"
    assert any("ISO" in record.message for record in caplog.records)
