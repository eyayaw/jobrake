"""Shared plumbing: job normalization and small text/date helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from bs4 import BeautifulSoup


def html_text(html: str) -> str:
    """Plain text from an HTML fragment (descriptions arrive as HTML)."""
    if not html:
        return ""
    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)


def epoch_ms_to_date(ms) -> str:
    """``YYYY-MM-DD`` (UTC) from epoch milliseconds; ``""`` if unparseable."""
    try:
        return datetime.fromtimestamp(float(ms) / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


def make_job(
    *,
    title: str,
    company: str,
    url: str,
    site: str,
    location: str = "",
    description: str = "",
    date: str = "",
) -> dict:
    return {
        "title": (title or "").strip(),
        "company": (company or "").strip(),
        "url": (url or "").strip(),
        "location": (location or "").strip(),
        "description": (description or "").strip(),
        "date": (date or "")[:10],
        "site": site,
    }
