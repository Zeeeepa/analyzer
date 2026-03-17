"""
Unit tests for auto-stealth trigger heuristics.

Run with:
    pytest test_stealth_triggers.py -v
"""

from .stealth_triggers import (
    detect_stealth_trigger_from_url,
    detect_stealth_trigger_from_content,
)


def test_detect_domain_trigger():
    result = detect_stealth_trigger_from_url("https://www.linkedin.com/company/eversale/")
    assert result is not None
    assert result["source"] == "domain"
    assert "LinkedIn" in result["reason"]


def test_detect_path_trigger():
    result = detect_stealth_trigger_from_url("https://facebook.com/ads/library/?active_status=all")
    assert result is not None
    assert result["source"] in {"path", "domain"}
    assert "Facebook" in result["reason"] or "Ads" in result["reason"]


def test_detect_content_trigger():
    reason = detect_stealth_trigger_from_content("Please verify you are human before continuing.")
    assert reason is not None
    assert "human" in reason.lower()


def test_no_trigger_for_safe_url():
    assert detect_stealth_trigger_from_url("https://example.com/about") is None


def test_no_trigger_for_empty_content():
    assert detect_stealth_trigger_from_content("") is None
