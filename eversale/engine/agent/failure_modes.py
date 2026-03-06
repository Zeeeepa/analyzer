from enum import Enum
from typing import List, Dict, Any, Optional, Callable, Awaitable
from dataclasses import dataclass, field
from loguru import logger

class FailureMode(Enum):
    # Tier 0 — Core execution
    NAVIGATION_FAILED = "NAVIGATION_FAILED"
    DOM_NOT_STABLE = "DOM_NOT_STABLE"
    OVERLAY_BLOCKING_INTERACTION = "OVERLAY_BLOCKING_INTERACTION"
    ELEMENT_NOT_FOUND = "ELEMENT_NOT_FOUND"
    ACTION_NOT_APPLIED = "ACTION_NOT_APPLIED"
    UNEXPECTED_REDIRECT = "UNEXPECTED_REDIRECT"
    INFINITE_SCROLL_REQUIRED = "INFINITE_SCROLL_REQUIRED"

    # Tier 1 — Access & blocking
    AUTH_REQUIRED = "AUTH_REQUIRED"
    MFA_REQUIRED = "MFA_REQUIRED"
    CAPTCHA_PRESENT = "CAPTCHA_PRESENT"
    RATE_LIMITED = "RATE_LIMITED"
    BOT_DETECTED = "BOT_DETECTED"
    GEO_BLOCKED = "GEO_BLOCKED"

    # Tier 2 — Data integrity
    PARTIAL_EXTRACTION = "PARTIAL_EXTRACTION"
    PAGINATION_REQUIRED = "PAGINATION_REQUIRED"
    DUPLICATE_DETECTED = "DUPLICATE_DETECTED"
    OUTPUT_VALIDATION_FAILED = "OUTPUT_VALIDATION_FAILED"

    # Tier 3 — Safety & irreversible actions
    DANGEROUS_ACTION_DETECTED = "DANGEROUS_ACTION_DETECTED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    POLICY_BLOCKED = "POLICY_BLOCKED"

@dataclass
class FailureHandler:
    name: FailureMode
    detectors: List[Callable[[Any], Awaitable[bool]]]  # page -> bool
    recovery_steps: List[Callable[[Any], Awaitable[bool]]] # page -> success
    retry_policy: Dict[str, Any] = field(default_factory=lambda: {
        "max_retries": 3,
        "backoff": 1.0,
        "jitter": True
    })
    exit_condition: Callable[[Any], Awaitable[bool]] = None # When to stop and escalate

@dataclass
class SiteHints:
    expected_failure_modes: List[FailureMode] = field(default_factory=list)
    preferred_selectors: List[str] = field(default_factory=list)
    max_pages: int = 5
    custom_hints: Dict[str, Any] = field(default_factory=dict)

# Pre-defined site hints
SITE_HINTS = {
    "facebook.com": SiteHints(
        expected_failure_modes=[
            FailureMode.INFINITE_SCROLL_REQUIRED,
            FailureMode.AUTH_REQUIRED,
            FailureMode.DOM_NOT_STABLE,
            FailureMode.OVERLAY_BLOCKING_INTERACTION,
            FailureMode.CAPTCHA_PRESENT,  # Cloudflare challenges
            FailureMode.BOT_DETECTED,     # Bot detection checks
        ],
        preferred_selectors=["div[aria-labelledby]", "a[href*='l.facebook.com/l.php']"]
    ),
    "reddit.com": SiteHints(
        expected_failure_modes=[FailureMode.BOT_DETECTED, FailureMode.RATE_LIMITED, FailureMode.INFINITE_SCROLL_REQUIRED, FailureMode.OVERLAY_BLOCKING_INTERACTION],
        preferred_selectors=["shreddit-post", "div[data-testid='post-container']"]
    ),
    "linkedin.com": SiteHints(
        expected_failure_modes=[FailureMode.AUTH_REQUIRED, FailureMode.BOT_DETECTED, FailureMode.RATE_LIMITED, FailureMode.OVERLAY_BLOCKING_INTERACTION],
        preferred_selectors=[".reusable-search__result-container", ".feed-shared-update-v2"],
        custom_hints={"search_engine_filter": "linkedin.com/in"}
    ),
    "google.com/maps": SiteHints(
        expected_failure_modes=[FailureMode.DOM_NOT_STABLE, FailureMode.INFINITE_SCROLL_REQUIRED, FailureMode.OVERLAY_BLOCKING_INTERACTION],
        preferred_selectors=["a[href*='/maps/place/']", "[role='feed']"]
    )
}
