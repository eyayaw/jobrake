"""Tests for the text/date helpers."""

from jobrake.utils import epoch_ms_to_date, html_text


def test_html_text_strips_tags_and_unescapes():
    assert html_text("<p>Turner &amp; Townsend</p>") == "Turner & Townsend"


def test_epoch_ms_to_date():
    assert epoch_ms_to_date(1717200000000) == "2024-06-01"
    assert epoch_ms_to_date(None) == ""
