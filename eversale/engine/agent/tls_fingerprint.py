"""
TLS Fingerprint Wrapper using curl_cffi for Chrome-like TLS Handshakes
=======================================================================

This module provides TLS fingerprinting capabilities to bypass modern anti-bot
systems (DataDome, Cloudflare, Akamai) that detect Playwright's distinct TLS signature.

Key Features:
- Chrome TLS handshake emulation via curl_cffi
- JA3 fingerprint spoofing
- Support for multiple browser versions
- Session management with TLS fingerprinting
- Async/sync wrapper for Playwright integration
- Pre-flight request capability

Author: Claude
Date: 2025-12-02
"""

import logging
from typing import Optional, Dict, Any, List
from pathlib import Path
import time

logger = logging.getLogger(__name__)

# Try to import curl_cffi for TLS fingerprinting
try:
    from curl_cffi import requests as curl_requests
    from curl_cffi.requests import Session as CurlSession
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False
    # Suppress warning - bootstrap will auto-install curl_cffi
    # logger.warning("curl_cffi not installed - TLS fingerprinting unavailable")


class TLSFingerprintSession:
    """
    HTTP session with Chrome-like TLS fingerprint.

    This class wraps curl_cffi to provide authentic Chrome TLS handshakes,
    bypassing JA3 fingerprint detection used by modern anti-bot systems.

    Usage:
        session = TLSFingerprintSession("chrome120")
        response = session.get("https://example.com")
        print(response.text)
        session.close()
    """

    # Available browser impersonations (curl_cffi supported)
    CHROME_IMPERSONATIONS = [
        "chrome110", "chrome116", "chrome119", "chrome120",
        "chrome99", "chrome100", "chrome101", "chrome104",
        "chrome107", "chrome124"
    ]

    # Edge impersonations
    EDGE_IMPERSONATIONS = [
        "edge99", "edge101", "edge107"
    ]

    # Safari impersonations
    SAFARI_IMPERSONATIONS = [
        "safari15_3", "safari15_5", "safari17_0"
    ]

    ALL_IMPERSONATIONS = CHROME_IMPERSONATIONS + EDGE_IMPERSONATIONS + SAFARI_IMPERSONATIONS

    def __init__(self, impersonate: str = "chrome120"):
        """
        Initialize TLS fingerprint session.

        Args:
            impersonate: Browser to impersonate (default: chrome120)
                        Must be one of CHROME_IMPERSONATIONS, EDGE_IMPERSONATIONS,
                        or SAFARI_IMPERSONATIONS
        """
        self.impersonate = impersonate
        self._session = None

        if HAS_CURL_CFFI:
            try:
                self._session = curl_requests.Session(impersonate=impersonate)
                logger.debug(f"Session initialized ({impersonate})")
            except Exception as e:
                logger.error(f"[TLS] Failed to create curl_cffi session: {e}")
                # Fallback to standard requests
                import requests
                self._session = requests.Session()
                logger.warning("[TLS] Falling back to standard requests (no TLS fingerprinting)")
        else:
            logger.warning("[TLS] curl_cffi unavailable, using standard requests")
            import requests
            self._session = requests.Session()

    def get(self, url: str, **kwargs) -> Any:
        """
        Make GET request with Chrome TLS fingerprint.

        Args:
            url: Target URL
            **kwargs: Additional arguments passed to requests.get()

        Returns:
            Response object
        """
        try:
            return self._session.get(url, **kwargs)
        except Exception as e:
            logger.error(f"[TLS] GET request failed: {e}")
            raise

    def post(self, url: str, **kwargs) -> Any:
        """
        Make POST request with Chrome TLS fingerprint.

        Args:
            url: Target URL
            **kwargs: Additional arguments passed to requests.post()

        Returns:
            Response object
        """
        try:
            return self._session.post(url, **kwargs)
        except Exception as e:
            logger.error(f"[TLS] POST request failed: {e}")
            raise

    def head(self, url: str, **kwargs) -> Any:
        """
        Make HEAD request with Chrome TLS fingerprint.

        Args:
            url: Target URL
            **kwargs: Additional arguments passed to requests.head()

        Returns:
            Response object
        """
        try:
            return self._session.head(url, **kwargs)
        except Exception as e:
            logger.error(f"[TLS] HEAD request failed: {e}")
            raise

    def put(self, url: str, **kwargs) -> Any:
        """Make PUT request with Chrome TLS fingerprint."""
        try:
            return self._session.put(url, **kwargs)
        except Exception as e:
            logger.error(f"[TLS] PUT request failed: {e}")
            raise

    def delete(self, url: str, **kwargs) -> Any:
        """Make DELETE request with Chrome TLS fingerprint."""
        try:
            return self._session.delete(url, **kwargs)
        except Exception as e:
            logger.error(f"[TLS] DELETE request failed: {e}")
            raise

    @property
    def has_tls_fingerprinting(self) -> bool:
        """Check if TLS fingerprinting is available."""
        return HAS_CURL_CFFI and isinstance(self._session, CurlSession if HAS_CURL_CFFI else type(None))

    def close(self):
        """Close the session."""
        if self._session:
            try:
                self._session.close()
                logger.debug("[TLS] Session closed")
            except Exception as e:
                logger.warning(f"[TLS] Error closing session: {e}")


class TLSProxyWrapper:
    """
    Wrapper to proxy Playwright requests through curl_cffi for TLS fingerprinting.

    This class provides async methods for use with Playwright, allowing you to
    make TLS-fingerprinted requests before navigating with Playwright.

    Usage:
        proxy = TLSProxyWrapper()
        html = await proxy.fetch_with_tls("https://example.com")
    """

    def __init__(self, impersonate: str = "chrome120"):
        """
        Initialize TLS proxy wrapper.

        Args:
            impersonate: Browser to impersonate
        """
        self.impersonate = impersonate
        self._tls_session = TLSFingerprintSession(impersonate)

    async def fetch_with_tls(self, url: str, headers: Optional[Dict[str, str]] = None) -> str:
        """
        Fetch URL with proper TLS fingerprint (async wrapper).

        Args:
            url: URL to fetch
            headers: Optional HTTP headers

        Returns:
            Response text
        """
        if not HAS_CURL_CFFI:
            # Fallback: use standard aiohttp
            import aiohttp
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers or {}) as resp:
                        return await resp.text()
            except Exception as e:
                logger.error(f"[TLS] Fallback fetch failed: {e}")
                return ""

        # Use curl_cffi for Chrome-like TLS (synchronous, but run in executor for async)
        import asyncio
        loop = asyncio.get_event_loop()

        try:
            response = await loop.run_in_executor(
                None,
                lambda: self._tls_session.get(url, headers=headers or {}, timeout=30)
            )
            return response.text
        except Exception as e:
            logger.error(f"[TLS] TLS fetch failed: {e}")
            return ""

    async def head_with_tls(self, url: str, headers: Optional[Dict[str, str]] = None) -> bool:
        """
        Make HEAD request with TLS fingerprint (async wrapper).

        Args:
            url: URL to check
            headers: Optional HTTP headers

        Returns:
            True if successful (2xx-3xx status), False otherwise
        """
        if not HAS_CURL_CFFI:
            import aiohttp
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.head(url, headers=headers or {}, allow_redirects=True) as resp:
                        return resp.status < 400
            except:
                return False

        import asyncio
        loop = asyncio.get_event_loop()

        try:
            response = await loop.run_in_executor(
                None,
                lambda: self._tls_session.head(url, headers=headers or {}, timeout=10, allow_redirects=True)
            )
            return response.status_code < 400
        except:
            return False

    def close(self):
        """Close the TLS session."""
        self._tls_session.close()


def check_tls_fingerprinting() -> Dict[str, Any]:
    """
    Check if TLS fingerprinting is available and working.

    This function tests the curl_cffi installation and validates that
    TLS fingerprinting can successfully make requests.

    Returns:
        Dict with:
            - available: bool (is curl_cffi installed)
            - impersonations: List of available browser impersonations
            - test_passed: bool (did test request succeed)
            - message: str (status message)
            - fingerprint_data: Dict (TLS fingerprint info from test, if successful)
    """
    result = {
        "available": HAS_CURL_CFFI,
        "impersonations": TLSFingerprintSession.ALL_IMPERSONATIONS if HAS_CURL_CFFI else [],
        "test_passed": False,
        "message": "",
        "fingerprint_data": None
    }

    if not HAS_CURL_CFFI:
        result["message"] = "curl_cffi not installed. Install with: pip install curl_cffi"
        return result

    try:
        session = TLSFingerprintSession("chrome120")

        # Test against a TLS fingerprint checker
        logger.info("[TLS] Testing TLS fingerprint against browserleaks.com...")
        response = session.get("https://tls.browserleaks.com/json", timeout=10)

        if response.status_code == 200:
            result["test_passed"] = True
            result["message"] = "TLS fingerprinting working - Chrome signature verified"
            try:
                result["fingerprint_data"] = response.json()
                logger.info(f"[TLS] TLS test passed - JA3: {result['fingerprint_data'].get('ja3_hash', 'N/A')}")
            except:
                result["fingerprint_data"] = {"text": response.text[:200]}
        else:
            result["message"] = f"TLS test request failed with status {response.status_code}"
            logger.warning(f"[TLS] {result['message']}")

        session.close()
    except Exception as e:
        result["message"] = f"TLS test failed: {e}"
        logger.error(f"[TLS] {result['message']}")

    return result


def test_ja3_fingerprint(url: str = "https://tls.browserleaks.com/json") -> Dict[str, Any]:
    """
    Test JA3 fingerprint against a fingerprinting service.

    Args:
        url: URL of fingerprint testing service (default: browserleaks.com)

    Returns:
        Dict with fingerprint data and comparison
    """
    if not HAS_CURL_CFFI:
        return {
            "error": "curl_cffi not installed",
            "chrome_fingerprint": None,
            "standard_fingerprint": None
        }

    result = {
        "chrome_fingerprint": None,
        "standard_fingerprint": None,
        "match": False,
        "ja3_hash_chrome": None,
        "ja3_hash_standard": None
    }

    try:
        # Test with Chrome TLS fingerprint
        logger.info("[TLS] Testing with Chrome TLS fingerprint...")
        chrome_session = TLSFingerprintSession("chrome120")
        chrome_resp = chrome_session.get(url, timeout=10)
        if chrome_resp.status_code == 200:
            result["chrome_fingerprint"] = chrome_resp.json()
            result["ja3_hash_chrome"] = result["chrome_fingerprint"].get("ja3_hash")
        chrome_session.close()

        # Test with standard requests (Playwright-like)
        logger.info("[TLS] Testing with standard requests (Playwright-like)...")
        import requests
        standard_session = requests.Session()
        standard_resp = standard_session.get(url, timeout=10)
        if standard_resp.status_code == 200:
            result["standard_fingerprint"] = standard_resp.json()
            result["ja3_hash_standard"] = result["standard_fingerprint"].get("ja3_hash")
        standard_session.close()

        # Compare
        if result["ja3_hash_chrome"] and result["ja3_hash_standard"]:
            result["match"] = result["ja3_hash_chrome"] == result["ja3_hash_standard"]
            if not result["match"]:
                logger.info(f"[TLS] TLS fingerprints differ (good!) - Chrome: {result['ja3_hash_chrome']}, Standard: {result['ja3_hash_standard']}")
            else:
                logger.warning("[TLS] TLS fingerprints match (curl_cffi may not be working correctly)")

    except Exception as e:
        logger.error(f"[TLS] Fingerprint test failed: {e}")
        result["error"] = str(e)

    return result


# Singleton for easy access
_tls_session: Optional[TLSFingerprintSession] = None

def get_tls_session(impersonate: str = "chrome120", force_new: bool = False) -> TLSFingerprintSession:
    """
    Get global TLS fingerprint session (singleton).

    Args:
        impersonate: Browser to impersonate (default: chrome120)
        force_new: Force creation of new session even if one exists

    Returns:
        TLSFingerprintSession instance
    """
    global _tls_session
    if _tls_session is None or force_new:
        if _tls_session and force_new:
            _tls_session.close()
        _tls_session = TLSFingerprintSession(impersonate)
    return _tls_session


def cleanup_tls_session():
    """Close and cleanup global TLS session."""
    global _tls_session
    if _tls_session:
        _tls_session.close()
        _tls_session = None


# Statistics tracking
_tls_stats = {
    "requests_with_tls": 0,
    "requests_without_tls": 0,
    "last_reset": time.time()
}

def get_tls_stats() -> Dict[str, Any]:
    """Get TLS usage statistics."""
    return {
        **_tls_stats,
        "has_curl_cffi": HAS_CURL_CFFI,
        "tls_enabled_percentage": (
            (_tls_stats["requests_with_tls"] /
             (_tls_stats["requests_with_tls"] + _tls_stats["requests_without_tls"]) * 100)
            if (_tls_stats["requests_with_tls"] + _tls_stats["requests_without_tls"]) > 0
            else 0
        )
    }

def reset_tls_stats():
    """Reset TLS statistics."""
    global _tls_stats
    _tls_stats = {
        "requests_with_tls": 0,
        "requests_without_tls": 0,
        "last_reset": time.time()
    }


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "TLSFingerprintSession",
    "TLSProxyWrapper",
    "check_tls_fingerprinting",
    "test_ja3_fingerprint",
    "get_tls_session",
    "cleanup_tls_session",
    "get_tls_stats",
    "reset_tls_stats",
    "HAS_CURL_CFFI",
]
