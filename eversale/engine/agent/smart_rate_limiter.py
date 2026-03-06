"""
Smart Rate Limiter - Adaptive per-domain rate limiting

Features:
- Per-domain rate limits (LinkedIn slower than Google)
- Adaptive delays based on response codes (429 = slow down)
- Burst protection (no more than N requests in M seconds)
- Exponential backoff on errors
- Rate limit persistence across restarts

Usage Example:
    ```python
    from agent.smart_rate_limiter import SmartRateLimiter

    # Initialize rate limiter
    limiter = SmartRateLimiter()

    # Before making a request
    await limiter.acquire("linkedin.com")
    response = await page.goto("https://linkedin.com/...")

    # After getting response
    limiter.record_response("linkedin.com", response.status)

    # Check current stats
    stats = limiter.get_stats()
    print(f"LinkedIn delay: {stats['linkedin.com']['current_delay']}s")
    ```
"""

import asyncio
import time
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from collections import deque
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class DomainProfile:
    """Rate limit profile for a domain"""
    domain: str
    default_delay: float  # Base delay between requests (seconds)
    current_delay: float  # Current adaptive delay
    max_delay: float  # Maximum delay (cap for exponential backoff)
    min_delay: float  # Minimum delay (floor)
    burst_limit: int  # Max requests in burst_window
    burst_window: int  # Burst window in seconds
    last_request_time: float  # Timestamp of last request
    request_times: List[float]  # Recent request timestamps for burst tracking
    consecutive_errors: int  # Track consecutive errors
    slowdown_until: float  # Timestamp when slowdown expires

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization"""
        data = asdict(self)
        # Convert deque to list if needed
        if isinstance(data.get('request_times'), deque):
            data['request_times'] = list(data['request_times'])
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'DomainProfile':
        """Create from dict (JSON deserialization)"""
        # Ensure request_times is a list
        if 'request_times' in data:
            data['request_times'] = list(data['request_times'])
        return cls(**data)


class SmartRateLimiter:
    """
    Intelligent rate limiter with per-domain profiles and adaptive behavior.

    Automatically adjusts delays based on server responses:
    - 429 (Too Many Requests): Doubles delay, remembers for 1 hour
    - 503 (Service Unavailable): Increases delay temporarily
    - 200-399 (Success): Gradually reduces delay back to default
    - CAPTCHA detected: Significantly slows down

    Enforces burst protection to prevent overwhelming any domain.
    """

    # Default domain configurations
    DOMAIN_CONFIGS = {
        'linkedin.com': {
            'default_delay': 10.0,
            'max_delay': 120.0,
            'min_delay': 5.0,
            'burst_limit': 5,
            'burst_window': 60,
        },
        'facebook.com': {
            'default_delay': 5.0,
            'max_delay': 60.0,
            'min_delay': 2.0,
            'burst_limit': 8,
            'burst_window': 60,
        },
        'google.com': {
            'default_delay': 2.0,
            'max_delay': 30.0,
            'min_delay': 1.0,
            'burst_limit': 15,
            'burst_window': 60,
        },
        'default': {
            'default_delay': 1.0,
            'max_delay': 30.0,
            'min_delay': 0.5,
            'burst_limit': 10,
            'burst_window': 60,
        }
    }

    def __init__(self, persistence_path: Optional[str] = None):
        """
        Initialize rate limiter.

        Args:
            persistence_path: Path to save/load rate limit state.
                            Defaults to ~/.eversale/rate_limits.json
        """
        self.profiles: Dict[str, DomainProfile] = {}
        self.locks: Dict[str, asyncio.Lock] = {}

        # Set persistence path
        if persistence_path is None:
            eversale_dir = Path.home() / '.eversale'
            eversale_dir.mkdir(exist_ok=True)
            self.persistence_path = eversale_dir / 'rate_limits.json'
        else:
            self.persistence_path = Path(persistence_path)

        # Load saved state
        self._load_state()

        logger.info(f"SmartRateLimiter initialized with {len(self.profiles)} cached domains")

    def _get_domain_config(self, domain: str) -> dict:
        """Get configuration for a domain, falling back to default"""
        # Try exact match
        if domain in self.DOMAIN_CONFIGS:
            return self.DOMAIN_CONFIGS[domain].copy()

        # Try matching subdomain (e.g., www.linkedin.com -> linkedin.com)
        for config_domain in self.DOMAIN_CONFIGS:
            if config_domain != 'default' and domain.endswith(config_domain):
                return self.DOMAIN_CONFIGS[config_domain].copy()

        # Use default
        return self.DOMAIN_CONFIGS['default'].copy()

    def _get_or_create_profile(self, domain: str) -> DomainProfile:
        """Get existing profile or create new one"""
        if domain not in self.profiles:
            config = self._get_domain_config(domain)
            self.profiles[domain] = DomainProfile(
                domain=domain,
                default_delay=config['default_delay'],
                current_delay=config['default_delay'],
                max_delay=config['max_delay'],
                min_delay=config['min_delay'],
                burst_limit=config['burst_limit'],
                burst_window=config['burst_window'],
                last_request_time=0.0,
                request_times=[],
                consecutive_errors=0,
                slowdown_until=0.0,
            )
            self.locks[domain] = asyncio.Lock()

        return self.profiles[domain]

    def _clean_old_requests(self, profile: DomainProfile) -> None:
        """Remove request timestamps outside the burst window"""
        now = time.time()
        cutoff = now - profile.burst_window

        # Filter out old timestamps
        profile.request_times = [
            t for t in profile.request_times
            if t > cutoff
        ]

    def _check_burst_limit(self, profile: DomainProfile) -> bool:
        """Check if burst limit would be exceeded"""
        self._clean_old_requests(profile)
        return len(profile.request_times) >= profile.burst_limit

    def _calculate_delay(self, profile: DomainProfile) -> float:
        """Calculate required delay before next request"""
        now = time.time()

        # Check if we're in a slowdown period (e.g., after 429)
        if now < profile.slowdown_until:
            # Use increased delay during slowdown
            delay = profile.current_delay
        else:
            # Gradually recover to default delay
            if profile.current_delay > profile.default_delay:
                # Reduce by 10% each successful request
                profile.current_delay *= 0.9
                profile.current_delay = max(
                    profile.current_delay,
                    profile.default_delay
                )
            delay = profile.current_delay

        # Calculate time since last request
        time_since_last = now - profile.last_request_time

        # Return remaining delay needed
        return max(0, delay - time_since_last)

    async def acquire(self, domain: str) -> None:
        """
        Wait until it's safe to make a request to the domain.

        This enforces both time-based delays and burst limits.

        Args:
            domain: Domain name (e.g., "linkedin.com")
        """
        profile = self._get_or_create_profile(domain)

        # Use lock to ensure sequential access per domain
        async with self.locks[domain]:
            # Check burst limit
            while self._check_burst_limit(profile):
                logger.warning(
                    f"Burst limit reached for {domain} "
                    f"({len(profile.request_times)}/{profile.burst_limit}), "
                    f"waiting..."
                )
                await asyncio.sleep(1.0)
                self._clean_old_requests(profile)

            # Calculate and apply delay
            delay = self._calculate_delay(profile)
            if delay > 0:
                logger.debug(f"Rate limiting {domain}: waiting {delay:.2f}s")
                await asyncio.sleep(delay)

            # Record this request
            now = time.time()
            profile.last_request_time = now
            profile.request_times.append(now)

            # Persist state after each request
            self._save_state()

    def record_response(
        self,
        domain: str,
        status: int,
        is_captcha: bool = False
    ) -> None:
        """
        Record response and adjust rate limits accordingly.

        Args:
            domain: Domain name
            status: HTTP status code
            is_captcha: Whether a CAPTCHA was detected
        """
        profile = self._get_or_create_profile(domain)

        now = time.time()

        if is_captcha:
            # CAPTCHA detected - severe slowdown
            logger.warning(f"CAPTCHA detected for {domain}, slowing down significantly")
            profile.current_delay = min(profile.current_delay * 3, profile.max_delay)
            profile.slowdown_until = now + 3600  # 1 hour
            profile.consecutive_errors += 1

        elif status == 429:
            # Too Many Requests - double delay
            logger.warning(f"429 Too Many Requests from {domain}, doubling delay")
            profile.current_delay = min(profile.current_delay * 2, profile.max_delay)
            profile.slowdown_until = now + 3600  # 1 hour
            profile.consecutive_errors += 1

        elif status == 503:
            # Service Unavailable - temporary increase
            logger.warning(f"503 Service Unavailable from {domain}, increasing delay")
            profile.current_delay = min(profile.current_delay * 1.5, profile.max_delay)
            profile.slowdown_until = now + 1800  # 30 minutes
            profile.consecutive_errors += 1

        elif status >= 500:
            # Other server errors - moderate increase
            logger.warning(f"{status} error from {domain}, moderately increasing delay")
            profile.current_delay = min(profile.current_delay * 1.2, profile.max_delay)
            profile.consecutive_errors += 1

        elif 200 <= status < 400:
            # Success - reset error counter
            profile.consecutive_errors = 0

            # If we're past slowdown period, start recovering
            if now >= profile.slowdown_until:
                if profile.current_delay > profile.default_delay:
                    logger.debug(
                        f"Successful request to {domain}, "
                        f"reducing delay from {profile.current_delay:.2f}s"
                    )

        else:
            # Client errors (4xx except 429) - don't adjust
            pass

        # Apply exponential backoff if many consecutive errors
        if profile.consecutive_errors >= 3:
            backoff_multiplier = 2 ** (profile.consecutive_errors - 2)
            profile.current_delay = min(
                profile.current_delay * backoff_multiplier,
                profile.max_delay
            )
            logger.warning(
                f"{profile.consecutive_errors} consecutive errors for {domain}, "
                f"delay now {profile.current_delay:.2f}s"
            )

        # Persist state after response
        self._save_state()

    def record_captcha(self, domain: str) -> None:
        """
        Convenience method to record CAPTCHA detection.

        Args:
            domain: Domain name where CAPTCHA was detected
        """
        self.record_response(domain, status=200, is_captcha=True)

    def get_stats(self) -> Dict[str, dict]:
        """
        Get current rate limit statistics for all domains.

        Returns:
            Dictionary mapping domain to stats dict with:
            - current_delay: Current delay in seconds
            - default_delay: Default delay in seconds
            - requests_in_window: Number of requests in burst window
            - burst_limit: Maximum allowed in burst window
            - consecutive_errors: Number of consecutive errors
            - slowdown_active: Whether domain is in slowdown period
        """
        stats = {}
        now = time.time()

        for domain, profile in self.profiles.items():
            self._clean_old_requests(profile)

            stats[domain] = {
                'current_delay': round(profile.current_delay, 2),
                'default_delay': round(profile.default_delay, 2),
                'requests_in_window': len(profile.request_times),
                'burst_limit': profile.burst_limit,
                'consecutive_errors': profile.consecutive_errors,
                'slowdown_active': now < profile.slowdown_until,
                'slowdown_expires_in': max(0, round(profile.slowdown_until - now)),
            }

        return stats

    def reset_domain(self, domain: str) -> None:
        """
        Reset rate limit state for a domain to defaults.

        Args:
            domain: Domain name to reset
        """
        if domain in self.profiles:
            config = self._get_domain_config(domain)
            profile = self.profiles[domain]
            profile.current_delay = config['default_delay']
            profile.consecutive_errors = 0
            profile.slowdown_until = 0.0
            profile.request_times = []

            logger.info(f"Reset rate limits for {domain}")
            self._save_state()

    def _save_state(self) -> None:
        """Persist rate limit state to JSON file"""
        try:
            state = {
                domain: profile.to_dict()
                for domain, profile in self.profiles.items()
            }

            with open(self.persistence_path, 'w') as f:
                json.dump(state, f, indent=2)

            logger.debug(f"Saved rate limit state to {self.persistence_path}")

        except Exception as e:
            logger.error(f"Failed to save rate limit state: {e}")

    def _load_state(self) -> None:
        """Load rate limit state from JSON file"""
        try:
            if not self.persistence_path.exists():
                logger.debug("No saved rate limit state found")
                return

            with open(self.persistence_path, 'r') as f:
                state = json.load(f)

            for domain, data in state.items():
                try:
                    profile = DomainProfile.from_dict(data)
                    self.profiles[domain] = profile
                    self.locks[domain] = asyncio.Lock()
                except Exception as e:
                    logger.error(f"Failed to load profile for {domain}: {e}")

            logger.info(f"Loaded rate limit state from {self.persistence_path}")

        except Exception as e:
            logger.error(f"Failed to load rate limit state: {e}")


# Global instance for easy access
_global_limiter: Optional[SmartRateLimiter] = None


def get_global_limiter() -> SmartRateLimiter:
    """Get or create global rate limiter instance"""
    global _global_limiter
    if _global_limiter is None:
        _global_limiter = SmartRateLimiter()
    return _global_limiter


# Convenience functions using global instance
async def acquire(domain: str) -> None:
    """Acquire rate limit permission for domain (uses global limiter)"""
    limiter = get_global_limiter()
    await limiter.acquire(domain)


def record_response(domain: str, status: int, is_captcha: bool = False) -> None:
    """Record response for domain (uses global limiter)"""
    limiter = get_global_limiter()
    limiter.record_response(domain, status, is_captcha)


def get_stats() -> Dict[str, dict]:
    """Get rate limit stats (uses global limiter)"""
    limiter = get_global_limiter()
    return limiter.get_stats()
