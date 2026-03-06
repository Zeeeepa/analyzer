"""
Site Profiles System - Intelligent per-site configuration

Configures optimal settings for known websites:
- Bot-protected sites: headful mode, extended timeouts, human CAPTCHA solving
- Standard sites: headless mode, normal timeouts
- Search engines: stealth mode, extended waits

Usage:
    from .site_profiles import get_site_profile, is_bot_protected, PROTECTED_DOMAINS

    profile = get_site_profile("google.com")
    if profile.requires_headful:
        await browser.show_browser()
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse
import re
from loguru import logger


@dataclass
class SiteProfile:
    """Configuration profile for a specific site."""
    domain: str
    requires_headful: bool = False  # Start in headful mode
    timeout_multiplier: float = 1.0  # Multiply default timeouts
    extra_wait_seconds: int = 0  # Additional wait after navigation
    stealth_level: str = "normal"  # "normal", "high", "maximum"
    captcha_likely: bool = False  # Expect CAPTCHA challenges
    login_required: bool = False  # Site requires login for full access
    rate_limit_delay: float = 0.0  # Delay between requests (seconds)
    alternative_domains: List[str] = field(default_factory=list)  # Fallback domains
    notes: str = ""


# === BOT-PROTECTED DOMAINS ===
# These sites aggressively block automated access
BOT_PROTECTED_DOMAINS: Dict[str, SiteProfile] = {
    # Google family
    "google.com": SiteProfile(
        domain="google.com",
        requires_headful=True,
        timeout_multiplier=2.0,
        extra_wait_seconds=3,
        stealth_level="maximum",
        captcha_likely=True,
        rate_limit_delay=2.0,
        alternative_domains=["duckduckgo.com", "bing.com"],
        notes="Heavy bot detection, reCAPTCHA common"
    ),
    "youtube.com": SiteProfile(
        domain="youtube.com",
        requires_headful=True,
        timeout_multiplier=2.0,
        extra_wait_seconds=5,
        stealth_level="maximum",
        captcha_likely=True,
        notes="Google-owned, aggressive bot detection"
    ),

    # Social media
    "linkedin.com": SiteProfile(
        domain="linkedin.com",
        requires_headful=True,
        timeout_multiplier=2.5,
        extra_wait_seconds=5,
        stealth_level="maximum",
        captcha_likely=True,
        login_required=True,
        rate_limit_delay=3.0,
        notes="Very aggressive anti-bot, requires login for most content"
    ),
    "twitter.com": SiteProfile(
        domain="twitter.com",
        requires_headful=True,
        timeout_multiplier=2.0,
        extra_wait_seconds=3,
        stealth_level="high",
        captcha_likely=True,
        login_required=True,
        alternative_domains=["nitter.net"],
        notes="API blocks, login walls"
    ),
    "x.com": SiteProfile(
        domain="x.com",
        requires_headful=True,
        timeout_multiplier=2.0,
        extra_wait_seconds=3,
        stealth_level="high",
        captcha_likely=True,
        login_required=True,
        alternative_domains=["nitter.net"],
        notes="Same as twitter.com"
    ),
    "reddit.com": SiteProfile(
        domain="reddit.com",
        requires_headful=True,
        timeout_multiplier=2.0,
        extra_wait_seconds=3,
        stealth_level="high",
        captcha_likely=True,
        alternative_domains=["old.reddit.com", "teddit.net"],
        notes="Cloudflare protection, rate limiting"
    ),
    "facebook.com": SiteProfile(
        domain="facebook.com",
        requires_headful=True,
        timeout_multiplier=2.5,
        extra_wait_seconds=5,
        stealth_level="maximum",
        captcha_likely=True,
        login_required=True,
        notes="Very aggressive bot detection"
    ),
    "instagram.com": SiteProfile(
        domain="instagram.com",
        requires_headful=True,
        timeout_multiplier=2.5,
        extra_wait_seconds=5,
        stealth_level="maximum",
        captcha_likely=True,
        login_required=True,
        notes="Facebook-owned, aggressive detection"
    ),

    # Developer platforms
    "github.com": SiteProfile(
        domain="github.com",
        requires_headful=True,
        timeout_multiplier=1.5,
        extra_wait_seconds=2,
        stealth_level="high",
        captcha_likely=True,
        notes="Rate limiting, some CAPTCHA"
    ),

    # E-commerce
    "amazon.com": SiteProfile(
        domain="amazon.com",
        requires_headful=True,
        timeout_multiplier=2.0,
        extra_wait_seconds=3,
        stealth_level="maximum",
        captcha_likely=True,
        rate_limit_delay=2.0,
        notes="Heavy anti-bot, CAPTCHA common"
    ),
    "ebay.com": SiteProfile(
        domain="ebay.com",
        requires_headful=True,
        timeout_multiplier=1.5,
        extra_wait_seconds=2,
        stealth_level="high",
        captcha_likely=True,
        notes="Bot detection, rate limiting"
    ),

    # Cloudflare-protected sites
    "cloudflare.com": SiteProfile(
        domain="cloudflare.com",
        requires_headful=True,
        timeout_multiplier=1.5,
        extra_wait_seconds=5,
        stealth_level="maximum",
        captcha_likely=True,
        notes="Cloudflare's own site - maximum protection"
    ),
}


# === STANDARD DOMAINS ===
# These sites work well with headless automation
STANDARD_DOMAINS: Dict[str, SiteProfile] = {
    # News sites
    "bbc.com": SiteProfile(domain="bbc.com", extra_wait_seconds=1),
    "cnn.com": SiteProfile(domain="cnn.com", extra_wait_seconds=1),
    "nytimes.com": SiteProfile(domain="nytimes.com", extra_wait_seconds=1),
    "espn.com": SiteProfile(domain="espn.com", extra_wait_seconds=1),
    "theverge.com": SiteProfile(domain="theverge.com", extra_wait_seconds=1),
    "arstechnica.com": SiteProfile(domain="arstechnica.com", extra_wait_seconds=1),
    "techcrunch.com": SiteProfile(domain="techcrunch.com", extra_wait_seconds=1),

    # Reference
    "wikipedia.org": SiteProfile(domain="wikipedia.org"),
    "stackoverflow.com": SiteProfile(domain="stackoverflow.com", extra_wait_seconds=1),

    # Developer
    "hackernews.com": SiteProfile(domain="hackernews.com"),
    "news.ycombinator.com": SiteProfile(domain="news.ycombinator.com"),
    "dev.to": SiteProfile(domain="dev.to", extra_wait_seconds=1),

    # Search alternatives
    "duckduckgo.com": SiteProfile(
        domain="duckduckgo.com",
        stealth_level="high",
        extra_wait_seconds=1,
        notes="Privacy-focused, less bot detection"
    ),
    "bing.com": SiteProfile(
        domain="bing.com",
        timeout_multiplier=1.2,
        extra_wait_seconds=1,
        stealth_level="high",
        notes="Less aggressive than Google"
    ),
}


# === HELPER FUNCTIONS ===

def extract_domain(url: str) -> str:
    """Extract base domain from URL."""
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # Remove www. prefix
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain
    except Exception:
        return url.lower()


def get_base_domain(domain: str) -> str:
    """Get base domain (e.g., 'old.reddit.com' -> 'reddit.com')."""
    parts = domain.split('.')
    if len(parts) >= 2:
        # Handle .co.uk, .com.au, etc.
        if parts[-2] in ('co', 'com', 'org', 'net', 'gov', 'edu'):
            if len(parts) >= 3:
                return '.'.join(parts[-3:])
        return '.'.join(parts[-2:])
    return domain


def get_site_profile(url_or_domain: str) -> SiteProfile:
    """
    Get site profile for a URL or domain.

    Returns appropriate profile with configured settings.
    Falls back to default profile if domain not known.
    """
    domain = extract_domain(url_or_domain)
    base_domain = get_base_domain(domain)

    # Check exact match first
    if domain in BOT_PROTECTED_DOMAINS:
        return BOT_PROTECTED_DOMAINS[domain]
    if domain in STANDARD_DOMAINS:
        return STANDARD_DOMAINS[domain]

    # Check base domain
    if base_domain in BOT_PROTECTED_DOMAINS:
        return BOT_PROTECTED_DOMAINS[base_domain]
    if base_domain in STANDARD_DOMAINS:
        return STANDARD_DOMAINS[base_domain]

    # Check for partial matches (subdomains)
    for known_domain, profile in BOT_PROTECTED_DOMAINS.items():
        if domain.endswith('.' + known_domain) or domain == known_domain:
            return profile

    for known_domain, profile in STANDARD_DOMAINS.items():
        if domain.endswith('.' + known_domain) or domain == known_domain:
            return profile

    # Return default profile
    return SiteProfile(domain=domain)


def is_bot_protected(url_or_domain: str) -> bool:
    """Check if a site is known to be bot-protected."""
    profile = get_site_profile(url_or_domain)
    return profile.requires_headful or profile.captcha_likely


def get_timeout_for_site(url_or_domain: str, base_timeout: float = 45.0) -> float:
    """Get adjusted timeout for a site."""
    profile = get_site_profile(url_or_domain)
    return base_timeout * profile.timeout_multiplier


def get_alternative_urls(url: str, query: str = "") -> List[str]:
    """Get alternative URLs for a blocked site."""
    profile = get_site_profile(url)
    alternatives = []

    for alt_domain in profile.alternative_domains:
        # Build alternative URL
        if query:
            # For search engines
            if 'duckduckgo' in alt_domain:
                alternatives.append(f"https://{alt_domain}/?q={query.replace(' ', '+')}")
            elif 'bing' in alt_domain:
                alternatives.append(f"https://{alt_domain}/search?q={query.replace(' ', '+')}")
            else:
                alternatives.append(f"https://{alt_domain}")
        else:
            alternatives.append(f"https://{alt_domain}")

    return alternatives


# === PROTECTED DOMAIN SET (for quick lookups) ===
PROTECTED_DOMAINS: Set[str] = set(BOT_PROTECTED_DOMAINS.keys())


# === LOGGING ===

def log_site_profile(url: str) -> None:
    """Log site profile info for debugging."""
    profile = get_site_profile(url)
    logger.debug(
        f"[SITE-PROFILE] {profile.domain}: "
        f"headful={profile.requires_headful}, "
        f"timeout={profile.timeout_multiplier}x, "
        f"stealth={profile.stealth_level}, "
        f"captcha={profile.captcha_likely}"
    )


# === INTEGRATION HELPERS ===

async def configure_browser_for_site(browser, url: str) -> None:
    """
    Configure browser settings based on site profile.

    Args:
        browser: A11yBrowser or similar browser instance
        url: Target URL
    """
    profile = get_site_profile(url)

    # Switch to headful if needed
    if profile.requires_headful and hasattr(browser, 'show_browser'):
        if hasattr(browser, 'headless') and browser.headless:
            logger.info(f"[SITE-PROFILE] Switching to headful mode for {profile.domain}")
            await browser.show_browser()

    # Log profile
    log_site_profile(url)


def should_use_headful(url: str) -> bool:
    """Check if headful mode should be used for this URL."""
    profile = get_site_profile(url)
    return profile.requires_headful


def get_wait_time(url: str) -> int:
    """Get extra wait time after navigation for this URL."""
    profile = get_site_profile(url)
    return profile.extra_wait_seconds


if __name__ == "__main__":
    # Test the module
    test_urls = [
        "https://www.google.com/search?q=test",
        "https://github.com/anthropics/claude",
        "https://old.reddit.com/r/programming",
        "https://news.ycombinator.com",
        "https://bbc.com/news",
        "https://some-unknown-site.com",
    ]

    print("Site Profile Test Results:")
    print("=" * 60)

    for url in test_urls:
        profile = get_site_profile(url)
        protected = "PROTECTED" if is_bot_protected(url) else "standard"
        print(f"\n{url}")
        print(f"  Domain: {profile.domain}")
        print(f"  Status: {protected}")
        print(f"  Headful: {profile.requires_headful}")
        print(f"  Timeout: {profile.timeout_multiplier}x")
        print(f"  CAPTCHA: {profile.captcha_likely}")
        if profile.alternative_domains:
            print(f"  Alternatives: {', '.join(profile.alternative_domains)}")
