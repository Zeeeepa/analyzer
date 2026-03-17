"""
FAST_TRACK Safety Module - Prevent FAST_TRACK on public-facing sites

This module ensures FAST_TRACK mode is NEVER used on public websites
where bot detection is a concern. It maintains a list of safe domains
and provides validation before enabling FAST_TRACK mode.

CRITICAL: FAST_TRACK should only be used for:
- Internal tools/dashboards
- Private admin panels
- Local development
- Trusted APIs
- Non-sensitive high-volume tasks

NEVER use FAST_TRACK on:
- Public e-commerce sites
- Social media platforms
- Government websites
- Banking/financial sites
- Any site with anti-bot measures
"""

import re
from typing import Optional, Set, List
from dataclasses import dataclass
from loguru import logger
from urllib.parse import urlparse


@dataclass
class SafetyConfig:
    """Configuration for FAST_TRACK safety checks"""
    # Whitelisted domains (FAST_TRACK allowed)
    safe_domains: Set[str] = None

    # URL patterns that are safe (regex)
    safe_patterns: List[str] = None

    # Strict mode - reject unless explicitly whitelisted
    strict_mode: bool = True

    # Log all safety checks
    verbose_logging: bool = True

    def __post_init__(self):
        if self.safe_domains is None:
            self.safe_domains = {
                # Local development
                'localhost',
                '127.0.0.1',
                '0.0.0.0',
                # Common local domains
                '.local',
                '.test',
                '.dev',
                # Internal networks
                '192.168.',
                '10.',
                '172.16.',
            }

        if self.safe_patterns is None:
            self.safe_patterns = [
                r'^https?://localhost',
                r'^https?://127\.0\.0\.1',
                r'^https?://192\.168\.',
                r'^https?://10\.',
                r'^https?://.*\.local',
                r'^https?://.*\.test',
                r'^https?://.*\.dev',
            ]


class FastTrackSafety:
    """
    Safety validator for FAST_TRACK mode.

    Prevents FAST_TRACK from being used on public-facing sites
    where humanization is critical for avoiding detection.

    Example:
        safety = FastTrackSafety()

        # Check if FAST_TRACK is safe
        if safety.is_safe("https://internal-tool.company.local"):
            config.fast_track = True

        # Add custom safe domain
        safety.add_safe_domain("internal-dashboard.company.com")
    """

    def __init__(self, config: Optional[SafetyConfig] = None):
        self.config = config or SafetyConfig()
        self._warning_shown = set()  # Track shown warnings

    def is_safe(self, url: str) -> bool:
        """
        Check if FAST_TRACK is safe for this URL.

        Args:
            url: The URL to check

        Returns:
            True if FAST_TRACK is safe, False if humanization is required
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # Check domain whitelist
            if self._is_domain_safe(domain):
                if self.config.verbose_logging:
                    logger.debug(f"FAST_TRACK SAFE: Domain '{domain}' is whitelisted")
                return True

            # Check URL patterns
            if self._matches_safe_pattern(url):
                if self.config.verbose_logging:
                    logger.debug(f"FAST_TRACK SAFE: URL matches safe pattern")
                return True

            # In strict mode, reject unless explicitly whitelisted
            if self.config.strict_mode:
                self._log_rejection(url, domain, "Not in whitelist (strict mode)")
                return False

            # Non-strict mode - could add heuristics here
            # For now, reject by default for safety
            self._log_rejection(url, domain, "Not explicitly whitelisted")
            return False

        except Exception as e:
            logger.error(f"Error checking FAST_TRACK safety: {e}")
            # Fail safe - reject on error
            return False

    def _is_domain_safe(self, domain: str) -> bool:
        """Check if domain is in safe list."""
        for safe_domain in self.config.safe_domains:
            # Exact match
            if domain == safe_domain:
                return True

            # Suffix match (e.g., '.local' matches 'app.local')
            if safe_domain.startswith('.') and domain.endswith(safe_domain):
                return True

            # Prefix match for IP ranges (e.g., '192.168.' matches '192.168.1.1')
            if safe_domain.endswith('.') and domain.startswith(safe_domain):
                return True

        return False

    def _matches_safe_pattern(self, url: str) -> bool:
        """Check if URL matches any safe pattern."""
        for pattern in self.config.safe_patterns:
            if re.match(pattern, url, re.IGNORECASE):
                return True
        return False

    def _log_rejection(self, url: str, domain: str, reason: str):
        """Log FAST_TRACK rejection."""
        # Only warn once per domain
        if domain not in self._warning_shown:
            logger.warning(
                f"FAST_TRACK REJECTED for '{domain}': {reason}. "
                f"Using full humanization to avoid detection. "
                f"To enable FAST_TRACK, add domain to whitelist."
            )
            self._warning_shown.add(domain)
        elif self.config.verbose_logging:
            logger.debug(f"FAST_TRACK rejected for '{domain}': {reason}")

    def add_safe_domain(self, domain: str):
        """
        Add a domain to the safe list.

        Args:
            domain: Domain to whitelist (e.g., 'internal-tool.company.com')
        """
        domain = domain.lower()
        self.config.safe_domains.add(domain)
        logger.info(f"Added '{domain}' to FAST_TRACK whitelist")

    def add_safe_pattern(self, pattern: str):
        """
        Add a URL pattern to the safe list.

        Args:
            pattern: Regex pattern (e.g., r'^https://.*\.internal\.company\.com')
        """
        self.config.safe_patterns.append(pattern)
        logger.info(f"Added pattern '{pattern}' to FAST_TRACK whitelist")

    def remove_safe_domain(self, domain: str):
        """Remove a domain from the safe list."""
        domain = domain.lower()
        self.config.safe_domains.discard(domain)
        logger.info(f"Removed '{domain}' from FAST_TRACK whitelist")

    def get_safe_domains(self) -> Set[str]:
        """Get current safe domain list."""
        return self.config.safe_domains.copy()

    def enforce(self, url: str, cursor_config, typer_config, scroller_config):
        """
        Enforce FAST_TRACK safety on humanization configs.

        If URL is not safe, forcibly disable FAST_TRACK.

        Args:
            url: URL being accessed
            cursor_config: CursorConfig instance
            typer_config: TypingConfig instance
            scroller_config: ScrollConfig instance
        """
        if not self.is_safe(url):
            # Force disable FAST_TRACK
            if hasattr(cursor_config, 'fast_track') and cursor_config.fast_track:
                cursor_config.fast_track = False
                logger.warning("Disabled FAST_TRACK for cursor (unsafe domain)")

            if hasattr(typer_config, 'fast_track') and typer_config.fast_track:
                typer_config.fast_track = False
                logger.warning("Disabled FAST_TRACK for typer (unsafe domain)")

            if hasattr(scroller_config, 'fast_track') and scroller_config.fast_track:
                scroller_config.fast_track = False
                logger.warning("Disabled FAST_TRACK for scroller (unsafe domain)")


# Global safety checker instance
_global_safety: Optional[FastTrackSafety] = None


def get_safety_checker() -> FastTrackSafety:
    """Get or create global safety checker instance."""
    global _global_safety
    if _global_safety is None:
        _global_safety = FastTrackSafety()
    return _global_safety


def is_fast_track_safe(url: str) -> bool:
    """
    Convenience function to check if FAST_TRACK is safe for a URL.

    Args:
        url: The URL to check

    Returns:
        True if FAST_TRACK can be safely used
    """
    checker = get_safety_checker()
    return checker.is_safe(url)


def enforce_fast_track_safety(url: str, cursor_config, typer_config, scroller_config):
    """
    Convenience function to enforce FAST_TRACK safety.

    Automatically disables FAST_TRACK if URL is not whitelisted.
    """
    checker = get_safety_checker()
    checker.enforce(url, cursor_config, typer_config, scroller_config)
