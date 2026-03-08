"""
Auto-Stealth Trigger Heuristics.

This module centralizes the logic that decides when we should escalate
stealth protections. The heuristics look at the URL (domain + path) and
page text for common anti-bot indicators so the browser can automatically
turn on the most aggressive stealth profile before being blocked.
"""

from __future__ import annotations

import re
from typing import Dict, Optional
from urllib.parse import urlparse

# Domains that routinely trigger hard anti-bot checks.
HIGH_RISK_STEALTH_DOMAINS = (
    ("linkedin.com", "LinkedIn aggressively blocks automation traffic"),
    ("facebook.com", "Facebook properties rely on strict bot detection"),
    ("instagram.com", "Instagram deploys multi-layered bot filters"),
    ("tiktok.com", "TikTok fingerprints automation aggressively"),
    ("reddit.com", "Reddit rate-limits and blocks scripted sessions"),
    ("crunchbase.com", "Crunchbase sits behind Cloudflare challenges"),
    ("g2.com", "G2 uses Cloudflare/Akamai style verification"),
    ("glassdoor.com", "Glassdoor enforces login and bot walls"),
    ("indeed.com", "Indeed frequently serves Cloudflare Turnstile"),
    ("yelp.com", "Yelp checks request fingerprints constantly"),
    ("trustradius.com", "TrustRadius leverages Cloudflare protections"),
)

# Path level cues that the upcoming navigation is sensitive.
PATH_TRIGGER_PATTERNS = (
    (re.compile(r"/ads/(?:library|manager)", re.IGNORECASE), "Meta Ads surfaces are heavily protected"),
    (re.compile(r"/checkpoint", re.IGNORECASE), "Checkpoint page indicates prior bot detection"),
    (re.compile(r"/challenge", re.IGNORECASE), "Challenge routes require anti-bot posture"),
    (re.compile(r"/captcha", re.IGNORECASE), "CAPTCHA path shows automated traffic was flagged"),
    (re.compile(r"/cloudflare", re.IGNORECASE), "Cloudflare challenge endpoint detected"),
)

# Keywords that usually appear on bot-detection pages.
CONTENT_TRIGGERS = (
    ("verify you are human", "Site requested human verification"),
    ("are you a robot", "Page explicitly asked if we are a robot"),
    ("unusual traffic", "Google-style unusual traffic warning"),
    ("ddos protection by cloudflare", "Cloudflare DDOS protection page"),
    ("checking your browser", "Cloudflare browser verification"),
    ("bot detection", "Generic bot detection notice"),
    ("attention required", "Cloudflare attention required page"),
    ("access denied | cloudflare", "Cloudflare access denied screen"),
    ("cf-chl", "Cloudflare challenge markup detected"),
    ("turnstile", "Cloudflare Turnstile challenge present"),
)


def _normalize_url(url: str) -> Dict[str, str]:
    """Return lowercase domain/path for the provided URL string."""
    if not url:
        return {"domain": "", "path": ""}

    normalized = url if "://" in url else f"https://{url}"
    try:
        parsed = urlparse(normalized)
    except ValueError:
        return {"domain": "", "path": ""}

    domain = parsed.netloc.lower()
    path = parsed.path.lower()
    return {"domain": domain, "path": path}


def detect_stealth_trigger_from_url(url: str) -> Optional[Dict[str, str]]:
    """
    Inspect a URL for domains or paths that require aggressive stealth.

    Returns a dict describing the trigger when matched, otherwise None.
    """
    parts = _normalize_url(url)
    domain = parts["domain"]
    path = parts["path"]

    if domain:
        for risky_domain, reason in HIGH_RISK_STEALTH_DOMAINS:
            if risky_domain in domain:
                return {
                    "reason": reason,
                    "domain": domain,
                    "source": "domain",
                    "level": "aggressive",
                }

    if path:
        for pattern, reason in PATH_TRIGGER_PATTERNS:
            if pattern.search(path):
                return {
                    "reason": reason,
                    "domain": domain or "unknown",
                    "source": "path",
                    "level": "aggressive",
                }

    return None


def detect_stealth_trigger_from_content(content: str) -> Optional[str]:
    """
    Inspect page text for bot-detection cues.

    Returns a short reason string when a cue is found, else None.
    """
    if not content:
        return None

    lower_content = content.lower()
    for indicator, reason in CONTENT_TRIGGERS:
        if indicator in lower_content:
            return reason

    return None


__all__ = [
    "detect_stealth_trigger_from_url",
    "detect_stealth_trigger_from_content",
]
