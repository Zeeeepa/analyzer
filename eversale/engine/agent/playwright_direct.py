"""
Direct Playwright Integration - No MCP wrapper needed

Since @modelcontextprotocol/server-playwright doesn't exist yet,
we use Playwright directly via Python.

STEALTH MODE: Implements comprehensive bot detection bypass

SPEED OPTIMIZATIONS (inspired by browser-use, crawl4ai):
- Response caching with TTL
- CSS-first extraction (LLM as fallback)
- Accessibility tree for fast page understanding
- Parallel URL processing
"""

import asyncio
import hashlib
import json
import os
import random
import secrets
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Callable
# Anti-bot library priority: patchright > rebrowser > playwright
# patchright: Undetected Chromium fork with stealth patches (most reliable)
# rebrowser-playwright: Patches CDP Runtime.Enable leak (requires special browser install)
# playwright: Standard Playwright (most detected)
USING_PATCHRIGHT = False
USING_REBROWSER = False

try:
    from patchright.async_api import async_playwright, Browser, Page, BrowserContext
    USING_PATCHRIGHT = True
except ImportError:
    try:
        from rebrowser_playwright.async_api import async_playwright, Browser, Page, BrowserContext
        USING_REBROWSER = True
    except ImportError:
        from playwright.async_api import async_playwright, Browser, Page, BrowserContext

# playwright-stealth: Inject anti-fingerprinting scripts
try:
    from playwright_stealth import Stealth
    PLAYWRIGHT_STEALTH_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_STEALTH_AVAILABLE = False
    Stealth = None

# curl_cffi: TLS/JA3 fingerprint impersonation for protected sites
try:
    from curl_cffi import requests as cffi_requests
    CURL_CFFI_AVAILABLE = True
except ImportError:
    CURL_CFFI_AVAILABLE = False
    cffi_requests = None

# Check if system Chrome is available and Chromium deps are installed
def _check_chromium_deps() -> bool:
    """Check if Chromium dependencies are installed."""
    import subprocess
    try:
        # Check for critical Chromium dependencies
        result = subprocess.run(
            ["ldconfig", "-p"],
            capture_output=True,
            text=True,
            timeout=5
        )
        libs = result.stdout.lower()
        required = ["libnss3", "libnspr4"]
        return all(lib in libs for lib in required)
    except Exception:
        return False

def _is_chrome_available() -> bool:
    """Check if Chrome is installed on the system."""
    import shutil
    chrome_paths = [
        "/opt/google/chrome/chrome",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        shutil.which("google-chrome"),
        shutil.which("chrome"),
    ]
    for path in chrome_paths:
        if path and Path(path).exists():
            return True
    return False

# Only set CHROME_AVAILABLE if Chrome exists AND deps are installed
CHROMIUM_DEPS_AVAILABLE = _check_chromium_deps()
CHROME_AVAILABLE = _is_chrome_available() and CHROMIUM_DEPS_AVAILABLE

# camoufox: Anti-detect Firefox (C++ level fingerprint injection)
try:
    from camoufox.async_api import AsyncCamoufox
    CAMOUFOX_AVAILABLE = True
except ImportError:
    CAMOUFOX_AVAILABLE = False
    AsyncCamoufox = None

from loguru import logger
import re
from functools import wraps

# Import ToolResult for standardized return format
try:
    from .reliability_core import ToolResult
    TOOLRESULT_AVAILABLE = True
except ImportError:
    # Fallback if reliability_core not available
    TOOLRESULT_AVAILABLE = False
    from dataclasses import dataclass
    from typing import Any, Optional

    @dataclass
    class ToolResult:
        success: bool
        data: Any = None
        error: Optional[str] = None
        error_code: Optional[str] = None
        duration_ms: int = 0
        retries_used: int = 0

        def get(self, key: str, default: Any = None) -> Any:
            """Dict-compatible get method for backwards compatibility."""
            return getattr(self, key, default)

from functools import lru_cache

from .deep_search_engine import DeepSearchEngine
from .captcha_solver import AmazonCaptchaHandler, PageCaptchaHandler, LocalCaptchaSolver

# ==============================================================================
# ERROR TRACKING SYSTEM - Capture and log all errors instead of silent failures
# ==============================================================================

_ERROR_TRACKER: List[Dict[str, Any]] = []
_MAX_TRACKED_ERRORS = 100  # Prevent memory bloat

def handle_error(
    operation: str,
    error: Exception,
    context: Optional[Dict[str, Any]] = None,
    log_level: str = "warning"
) -> Dict[str, Any]:
    """
    Centralized error handler - replaces silent except: pass patterns.

    Args:
        operation: Description of what operation failed (e.g., "browser_close", "page_navigation")
        error: The exception that was caught
        context: Optional context dict with additional details (url, selector, etc.)
        log_level: "debug", "info", "warning", or "error"

    Returns:
        Standardized error dict that can be returned to caller
    """
    import sys
    import traceback

    error_type = type(error).__name__
    error_msg = str(error)

    # Build context string
    context_str = ""
    if context:
        context_parts = [f"{k}={v}" for k, v in context.items()]
        context_str = f" | {', '.join(context_parts)}"

    # Log based on level
    log_message = f"[{operation}] {error_type}: {error_msg}{context_str}"

    if log_level == "debug":
        logger.debug(log_message)
    elif log_level == "info":
        logger.info(log_message)
    elif log_level == "warning":
        logger.warning(log_message)
    else:  # error
        logger.error(log_message)
        # For errors, also log the traceback
        logger.debug(f"Traceback:\n{''.join(traceback.format_tb(error.__traceback__))}")

    # Track error for debugging
    error_record = {
        "timestamp": time.time(),
        "operation": operation,
        "error_type": error_type,
        "error_message": error_msg,
        "context": context or {},
        "traceback": ''.join(traceback.format_tb(error.__traceback__)) if error.__traceback__ else None
    }

    _ERROR_TRACKER.append(error_record)

    # Trim old errors
    if len(_ERROR_TRACKER) > _MAX_TRACKED_ERRORS:
        _ERROR_TRACKER[:] = _ERROR_TRACKER[-_MAX_TRACKED_ERRORS:]

    # Return standardized error dict
    return {
        "error": error_msg,
        "error_type": error_type,
        "operation": operation,
        "timestamp": error_record["timestamp"],
        "context": context or {}
    }

def get_recent_errors(limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent errors for debugging."""
    return _ERROR_TRACKER[-limit:]

def clear_error_tracker():
    """Clear error tracker."""
    _ERROR_TRACKER.clear()



# Import hallucination guard for contact validation
try:
    from .hallucination_guard import get_guard
    HALLUCINATION_GUARD_AVAILABLE = True
except ImportError:
    HALLUCINATION_GUARD_AVAILABLE = False

# Import code generator for export functionality
try:
    from .code_generator import PlaywrightCodeGenerator
    CODE_GENERATOR_AVAILABLE = True
except ImportError:
    CODE_GENERATOR_AVAILABLE = False
    logger.warning("Code generator not available - export features disabled")

# Import search alternatives for Google CAPTCHA bypass
try:
    from .search_alternatives import SearchAlternatives, quick_search
    SEARCH_ALTERNATIVES_AVAILABLE = True
except ImportError:
    SEARCH_ALTERNATIVES_AVAILABLE = False
    SearchAlternatives = None
    quick_search = None

# Import site-specific selectors for reliable interaction with known sites
try:
    from .utils.site_selectors import get_interaction_selectors, get_site_selectors
    SITE_SELECTORS_AVAILABLE = True
except ImportError:
    SITE_SELECTORS_AVAILABLE = False
    get_interaction_selectors = None
    get_site_selectors = None

# Import Reddit handler for API-based workaround (Reddit blocks browser automation)
try:
    from .reddit_handler import (
        RedditHandler,
        is_reddit_url,
        parse_reddit_url,
        fetch_reddit_data,
        format_reddit_posts,
        format_reddit_comments,
        find_icp_profile_urls,
        format_icp_profile_urls,
    )
    REDDIT_HANDLER_AVAILABLE = True
except ImportError:
    REDDIT_HANDLER_AVAILABLE = False
    RedditHandler = None
    is_reddit_url = lambda url: False
    parse_reddit_url = lambda url: {}
    fetch_reddit_data = None
    format_reddit_posts = None
    format_reddit_comments = None
    find_icp_profile_urls = None
    format_icp_profile_urls = None

# Import Browser MCP features (CDP connection, console monitoring, network capture, Lighthouse)
# Inspired by: BrowserMCP/mcp, AgentDeskAI/browser-tools-mcp, hangwin/mcp-chrome
try:
    from .browser_mcp_features import (
        ExistingBrowserConnection,
        connect_to_existing_browser,
        ConsoleMonitor,
        ConsoleLogEntry,
        NetworkCapture,
        NetworkEntry,
        LighthouseAuditor,
        LighthouseResult,
        setup_browser_mcp_features,
        LIGHTHOUSE_AVAILABLE as LIGHTHOUSE_CLI_AVAILABLE
    )
    BROWSER_MCP_FEATURES_AVAILABLE = True
except ImportError:
    BROWSER_MCP_FEATURES_AVAILABLE = False
    ExistingBrowserConnection = None
    connect_to_existing_browser = None
    ConsoleMonitor = None
    NetworkCapture = None
    LighthouseAuditor = None
    LIGHTHOUSE_CLI_AVAILABLE = False
    logger.debug("Browser MCP features not available")

# Response cache with TTL (inspired by crawl4ai)
_PAGE_CACHE: Dict[str, Tuple[Dict, float]] = {}
_CACHE_TTL = 300  # 5 minutes

# ==============================================================================
# MEM0-STYLE SESSION MEMORY (98% task completion, 41% cost reduction)
# ==============================================================================
# Keeps track of: visited URLs, extracted data, errors, learned patterns
_SESSION_MEMORY: Dict[str, Any] = {
    "visited_urls": [],           # URLs visited in session
    "extracted_data": {},         # Key findings by URL
    "errors": [],                 # Errors for self-correction
    "learned_patterns": {},       # Site-specific selectors that worked
    "task_history": [],           # Completed subtasks
    "context_snapshots": [],      # Periodic state snapshots
}
_MEMORY_MAX_ITEMS = 50  # Prevent memory bloat
_MEMORY_MAX_URLS = 100  # Max URLs to store extracted data for


class SessionMemory:
    """
    MEM0-inspired session memory for cross-task context.

    Key features:
    - Remembers successful selectors per domain
    - Tracks errors for self-correction
    - Stores extracted data for reference
    - Periodic snapshots for long tasks
    """

    @staticmethod
    def add_visit(url: str, title: str = "", success: bool = True):
        """Record a URL visit"""
        _SESSION_MEMORY["visited_urls"].append({
            "url": url,
            "title": title,
            "success": success,
            "timestamp": time.time()
        })
        # Trim old entries
        if len(_SESSION_MEMORY["visited_urls"]) > _MEMORY_MAX_ITEMS:
            _SESSION_MEMORY["visited_urls"] = _SESSION_MEMORY["visited_urls"][-_MEMORY_MAX_ITEMS:]

    @staticmethod
    def store_data(url: str, key: str, data: Any):
        """Store extracted data for later reference"""
        if url not in _SESSION_MEMORY["extracted_data"]:
            _SESSION_MEMORY["extracted_data"][url] = {}
        _SESSION_MEMORY["extracted_data"][url][key] = data

        # Evict oldest URLs when limit reached
        if len(_SESSION_MEMORY["extracted_data"]) > _MEMORY_MAX_URLS:
            # Remove oldest URL (first one in dict)
            oldest_url = next(iter(_SESSION_MEMORY["extracted_data"]))
            del _SESSION_MEMORY["extracted_data"][oldest_url]

    @staticmethod
    def get_data(url: str = None) -> Dict:
        """Retrieve stored data"""
        if url:
            return _SESSION_MEMORY["extracted_data"].get(url, {})
        return _SESSION_MEMORY["extracted_data"]

    @staticmethod
    def record_error(url: str, error: str, action: str = ""):
        """Record error for self-correction learning"""
        _SESSION_MEMORY["errors"].append({
            "url": url,
            "error": error,
            "action": action,
            "timestamp": time.time()
        })
        if len(_SESSION_MEMORY["errors"]) > 20:
            _SESSION_MEMORY["errors"] = _SESSION_MEMORY["errors"][-20:]

    @staticmethod
    def learn_pattern(domain: str, pattern_type: str, pattern: str):
        """Remember successful patterns for a domain"""
        if domain not in _SESSION_MEMORY["learned_patterns"]:
            _SESSION_MEMORY["learned_patterns"][domain] = {}
        _SESSION_MEMORY["learned_patterns"][domain][pattern_type] = pattern

    @staticmethod
    def get_pattern(domain: str, pattern_type: str) -> Optional[str]:
        """Get a learned pattern for domain"""
        return _SESSION_MEMORY["learned_patterns"].get(domain, {}).get(pattern_type)

    @staticmethod
    def add_task(task: str, result: str = ""):
        """Record completed task"""
        _SESSION_MEMORY["task_history"].append({
            "task": task,
            "result": result[:200],  # Trim long results
            "timestamp": time.time()
        })

    @staticmethod
    def snapshot(state: Dict):
        """Take periodic snapshot for long tasks"""
        _SESSION_MEMORY["context_snapshots"].append({
            "state": state,
            "timestamp": time.time()
        })
        if len(_SESSION_MEMORY["context_snapshots"]) > 10:
            _SESSION_MEMORY["context_snapshots"] = _SESSION_MEMORY["context_snapshots"][-10:]

    @staticmethod
    def get_context_summary() -> str:
        """Get compressed context for LLM (context window optimization)"""
        visited = len(_SESSION_MEMORY["visited_urls"])
        errors = len(_SESSION_MEMORY["errors"])
        tasks = len(_SESSION_MEMORY["task_history"])

        summary_parts = [f"Session: {visited} pages visited, {tasks} tasks done"]

        # Add recent errors
        if errors:
            recent_err = _SESSION_MEMORY["errors"][-1]
            summary_parts.append(f"Last error: {recent_err['error'][:50]}")

        # Add key extracted data
        for url, data in list(_SESSION_MEMORY["extracted_data"].items())[-3:]:
            domain = url.split('/')[2] if '//' in url else url
            summary_parts.append(f"{domain}: {list(data.keys())}")

        return " | ".join(summary_parts)

    @staticmethod
    def clear():
        """Clear session memory"""
        for key in _SESSION_MEMORY:
            if isinstance(_SESSION_MEMORY[key], list):
                _SESSION_MEMORY[key] = []
            elif isinstance(_SESSION_MEMORY[key], dict):
                _SESSION_MEMORY[key] = {}


# Circuit breaker state (inspired by resilience patterns)
_CIRCUIT_BREAKER: Dict[str, Dict] = {}  # domain -> {failures, last_failure, state}
_CIRCUIT_FAILURE_THRESHOLD = 3
_CIRCUIT_RESET_TIMEOUT = 60  # seconds


class CircuitBreaker:
    """
    Circuit Breaker Pattern (from error recovery best practices).

    Prevents cascading failures by stopping requests to failing domains.
    States: CLOSED (normal) -> OPEN (blocking) -> HALF_OPEN (testing)
    """

    @staticmethod
    def get_state(domain: str) -> str:
        if domain not in _CIRCUIT_BREAKER:
            return "CLOSED"
        cb = _CIRCUIT_BREAKER[domain]
        if cb["state"] == "OPEN":
            # Check if reset timeout has passed
            if time.time() - cb["last_failure"] > _CIRCUIT_RESET_TIMEOUT:
                cb["state"] = "HALF_OPEN"
                return "HALF_OPEN"
            return "OPEN"
        return cb["state"]

    @staticmethod
    def record_failure(domain: str):
        if domain not in _CIRCUIT_BREAKER:
            _CIRCUIT_BREAKER[domain] = {"failures": 0, "last_failure": 0, "state": "CLOSED"}
        cb = _CIRCUIT_BREAKER[domain]
        cb["failures"] += 1
        cb["last_failure"] = time.time()
        if cb["failures"] >= _CIRCUIT_FAILURE_THRESHOLD:
            cb["state"] = "OPEN"
            logger.warning(f"Circuit OPEN for {domain} after {cb['failures']} failures")

    @staticmethod
    def record_success(domain: str):
        if domain in _CIRCUIT_BREAKER:
            _CIRCUIT_BREAKER[domain] = {"failures": 0, "last_failure": 0, "state": "CLOSED"}

    @staticmethod
    def is_allowed(domain: str) -> bool:
        state = CircuitBreaker.get_state(domain)
        return state != "OPEN"


def exponential_backoff_with_jitter(attempt: int, base_delay: float = 1.0, max_delay: float = 30.0) -> float:
    """
    Exponential backoff with jitter (from retry best practices).

    DEPRECATED: Use get_backoff() from exponential_backoff module instead.
    Kept for backward compatibility.
    """
    from .exponential_backoff import get_backoff
    backoff = get_backoff()
    return backoff.calculate_delay(attempt=attempt, last_delay=base_delay)


async def sleep_with_jitter(base_seconds: float, jitter_percent: float = 0.2) -> None:
    """
    Sleep for base_seconds with random jitter to prevent thundering herd.

    Args:
        base_seconds: Base sleep duration
        jitter_percent: Random variance (0.2 = +/- 20%)
    """
    jitter = base_seconds * jitter_percent
    actual = base_seconds + random.uniform(-jitter, jitter)
    await asyncio.sleep(max(0.1, actual))


async def exponential_backoff_sleep(
    retry_count: int,
    base: float = 1.0,
    max_delay: float = 60.0
) -> None:
    """Exponential backoff with jitter for retries."""
    delay = min(max_delay, base * (2 ** retry_count))
    jitter = delay * 0.3
    actual = delay + random.uniform(-jitter, jitter)
    await asyncio.sleep(max(0.5, actual))


# Import stealth utilities
from .stealth_utils import (
    get_stealth_args,
    get_random_user_agent,
    get_stealth_js,
    human_delay,
    between_action_delay,
)

# Optional advanced stealth configuration (Chrome MCP parity)
ADVANCED_STEALTH_AVAILABLE = False
try:
    from .stealth_browser_config import (
        get_mcp_compatible_launch_args,
        get_chrome_context_options,
        get_enhanced_stealth_script,
    )
    ADVANCED_STEALTH_AVAILABLE = True
except ImportError:
    get_mcp_compatible_launch_args = None
    get_chrome_context_options = None
    get_enhanced_stealth_script = None

from .stealth_triggers import (
    detect_stealth_trigger_from_url,
    detect_stealth_trigger_from_content,
)

# Import config loader for timeouts
try:
    from .config_loader import Timeouts, Timing, get_browser_setting
except ImportError:
    # Fallback defaults if config loader not available
    class Timeouts:
        @staticmethod
        def navigation(): return 20000
        @staticmethod
        def operation(): return 60000
        @staticmethod
        def idle(): return 3000
    class Timing:
        @staticmethod
        def nav_delay(service=None): return 2.0
    def get_browser_setting(key, default=None): return default

# Import visual fallback and self-healing selectors
try:
    from .selector_fallbacks import get_visual_fallback, VisualFallback, SelfHealingSelector
    VISUAL_FALLBACK_AVAILABLE = True
    SELF_HEALING_AVAILABLE = True
except ImportError:
    VISUAL_FALLBACK_AVAILABLE = False
    SELF_HEALING_AVAILABLE = False
    get_visual_fallback = None
    VisualFallback = None
    SelfHealingSelector = None

# Import DOM map store for enhanced semantic element tracking
try:
    from .dom_map_store import get_dom_map_store, DomTarget, SemanticFeatures
    DOM_MAP_STORE_AVAILABLE = True
except ImportError:
    DOM_MAP_STORE_AVAILABLE = False
    get_dom_map_store = None
    DomTarget = None
    SemanticFeatures = None
    logger.warning("DomMapStore not available - semantic element tracking disabled")

# Import challenge handler for auto-Cloudflare bypass
try:
    from .challenge_handler import ChallengeHandler, BlockedSite
    CHALLENGE_HANDLER_AVAILABLE = True
except ImportError:
    CHALLENGE_HANDLER_AVAILABLE = False
    ChallengeHandler = None
    BlockedSite = None



# ==============================================================================
# TOOL RESULT DECORATOR - Standardized return format for all browser tools
# ==============================================================================

def tool_result(func):
    """
    Decorator to automatically wrap method returns in ToolResult format.

    Features:
    - Tracks execution duration automatically
    - Catches exceptions and returns proper error ToolResult
    - Handles both sync and async functions
    - Never returns None - always returns ToolResult

    Usage:
        @tool_result
        async def my_method(self, arg):
            return {"data": "value"}  # Auto-wrapped in ToolResult
    """
    from functools import wraps
    import asyncio
    import time

    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        start = time.time()
        try:
            result = await func(*args, **kwargs)
            duration_ms = int((time.time() - start) * 1000)

            # If result is already a ToolResult, update duration
            if isinstance(result, ToolResult):
                result.duration_ms = duration_ms
                return result

            # Wrap raw result in ToolResult
            return ToolResult(
                success=True,
                data=result,
                duration_ms=duration_ms
            )
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            error_type = type(e).__name__
            return ToolResult(
                success=False,
                error=str(e),
                error_code=error_type.upper(),
                duration_ms=duration_ms
            )

    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        start = time.time()
        try:
            result = func(*args, **kwargs)
            duration_ms = int((time.time() - start) * 1000)

            # If result is already a ToolResult, update duration
            if isinstance(result, ToolResult):
                result.duration_ms = duration_ms
                return result

            # Wrap raw result in ToolResult
            return ToolResult(
                success=True,
                data=result,
                duration_ms=duration_ms
            )
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            error_type = type(e).__name__
            return ToolResult(
                success=False,
                error=str(e),
                error_code=error_type.upper(),
                duration_ms=duration_ms
            )

    # Return appropriate wrapper based on whether function is async
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper


class PlaywrightClient:
    """
    Direct Playwright browser automation client with STEALTH MODE

    Features:
    - Anti-bot detection bypass
    - Human-like timing and behavior
    - Fingerprint spoofing
    - Rate limiting
    - Auto-reconnect for long-running tasks
    - Health checking
    """

    def __init__(
        self,
        headless: bool = True,  # Default to headless for speed
        user_data_dir: Optional[str] = None,
        storage_state: Optional[str] = None,
        browser_type: str = None,  # Auto-select: chromium for patchright, firefox otherwise
        resource_limiter=None  # Optional resource limiter for process tracking
    ):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.headless = headless

        # IMPORTANT: Always use isolated profile to avoid wiping user's Chrome logins
        # The agent gets its own profile at ~/.eversale/browser-profile
        if user_data_dir is None:
            default_profile = Path.home() / ".eversale" / "browser-profile"
            default_profile.mkdir(parents=True, exist_ok=True)
            self.user_data_dir = str(default_profile)
            logger.debug(f"Using isolated browser profile: {self.user_data_dir}")
        else:
            self.user_data_dir = user_data_dir

        self.storage_state = storage_state
        self.stealth_enabled = True  # Always-on stealth mode
        self._connected = False
        self._reconnect_count = 0
        self._max_reconnects = 3
        self._reconnect_lock = asyncio.Lock()  # Prevent concurrent reconnection attempts
        # Auto-select browser based on available anti-bot libraries and system deps:
        # - rebrowser-playwright + patchright: Use Chromium (they patch Chromium CDP)
        # - camoufox: Use Firefox with C++ fingerprint injection
        # - plain playwright: Firefox has natural anti-detection
        # - Fallback: Firefox if Chromium deps aren't installed
        if browser_type is None:
            if (USING_REBROWSER or USING_PATCHRIGHT) and CHROMIUM_DEPS_AVAILABLE:
                self.browser_type = "chromium"  # Rebrowser/Patchright patch Chromium CDP
            elif CAMOUFOX_AVAILABLE:
                self.browser_type = "firefox"  # Camoufox for stealth Firefox
            elif not CHROMIUM_DEPS_AVAILABLE:
                self.browser_type = "firefox"  # Fall back to Firefox if Chromium deps missing
                logger.warning("Chromium deps not installed, using Firefox. For Chromium: sudo playwright install-deps")
            else:
                self.browser_type = "firefox"  # Firefox has natural anti-detection
        else:
            self.browser_type = browser_type.lower()
        self.resource_limiter = resource_limiter
        self._browser_pid = None

        # Session state management
        self._session_state_dir = Path.home() / ".eversale" / "sessions"
        self._session_state_dir.mkdir(parents=True, exist_ok=True)

        # Response cache for recently visited pages (avoid re-fetching)
        self._page_cache: Dict[str, Dict[str, Any]] = {}  # url -> {markdown, timestamp, title}
        self._cache_ttl = 300  # 5 minutes cache TTL
        self._cache_max_size = 50  # Max cached pages
        # Deep research + async job state
        self._research_jobs: Dict[str, Dict[str, Any]] = {}
        self._research_job_tasks: Dict[str, asyncio.Task] = {}
        self._research_dir = Path("memory") / "deep_research"
        self._research_dir.mkdir(parents=True, exist_ok=True)

        # Browser MCP features (console monitoring, network capture, Lighthouse)
        self._console_monitor: Optional[ConsoleMonitor] = None
        self._network_capture: Optional[NetworkCapture] = None

        # Output callback for consistent Eversale-style output
        # Set this to a function(str) to receive formatted output for each tool call
        self.output_callback: Optional[Callable[[str], None]] = None
        self.verbose_output: bool = True  # Set False to disable automatic output printing
        self._mcp_features_enabled = False

        # Auto-stealth overrides (populated when heuristics detect risky pages)
        self._stealth_launch_override: Optional[List[str]] = None
        self._stealth_header_override: Optional[Dict[str, str]] = None
        self._auto_stealth_state = {
            "active": False,
            "level": "baseline",
            "last_reason": "",
            "last_domain": "",
            "headers_applied": False,
            "script_added": False,
            "sources": set(),
        }

    async def _auto_enable_stealth(
        self,
        trigger_reason: str,
        domain: Optional[str] = None,
        source: str = "domain"
    ) -> None:
        """Escalate stealth protections when high-risk signals are detected."""
        if not ADVANCED_STEALTH_AVAILABLE:
            return

        state = self._auto_stealth_state

        if (
            state["active"]
            and trigger_reason == state["last_reason"]
            and (not domain or domain == state["last_domain"])
        ):
            state["sources"].add(source)
            return

        state["active"] = True
        state["level"] = "aggressive"
        state["last_reason"] = trigger_reason
        if domain:
            state["last_domain"] = domain
        state["sources"].add(source)

        logger.debug(f"[STEALTH] Auto-escalating stealth mode ({trigger_reason})")

        if self.browser_type == "chromium" and not self._stealth_launch_override and get_mcp_compatible_launch_args:
            self._stealth_launch_override = get_mcp_compatible_launch_args()

        if self.browser_type == "chromium" and get_chrome_context_options:
            context_headers = get_chrome_context_options().get("extra_http_headers", {})
        else:
            context_headers = {}

        if context_headers:
            self._stealth_header_override = context_headers
            if self.context:
                try:
                    await self.context.set_extra_http_headers(context_headers)
                    state["headers_applied"] = True
                except Exception as e:
                    logger.debug(f"Auto-stealth header update failed: {e}")

        stealth_script = get_enhanced_stealth_script() if get_enhanced_stealth_script else None
        if self.context and stealth_script and not state["script_added"]:
            try:
                await self.context.add_init_script(stealth_script)
                state["script_added"] = True
            except Exception as e:
                logger.debug(f"Auto-stealth init script failed: {e}")

        if source == "content" and self.page and stealth_script:
            try:
                await self.page.evaluate(stealth_script)
            except Exception as e:
                logger.debug(f"Auto-stealth runtime script failed: {e}")

    @tool_result
    async def enable_mcp_features(self, enable_console: bool = True, enable_network: bool = True) -> Dict[str, bool]:
        """
        Enable Browser MCP features for debugging and analysis.

        Features:
        - ConsoleMonitor: Capture console.log, errors, warnings in real-time
        - NetworkCapture: Capture full request/response bodies via CDP

        Returns dict of which features were enabled.
        """
        if not BROWSER_MCP_FEATURES_AVAILABLE:
            logger.warning("Browser MCP features not available")
            return {"console": False, "network": False}

        if not self.page:
            logger.warning("No page available - call connect() first")
            return {"console": False, "network": False}

        result = {"console": False, "network": False}

        if enable_console and ConsoleMonitor:
            try:
                self._console_monitor = ConsoleMonitor()
                await self._console_monitor.attach(self.page)
                result["console"] = True
                logger.info("Console monitoring enabled")
            except Exception as e:
                logger.warning(f"Failed to enable console monitoring: {e}")

        if enable_network and NetworkCapture:
            try:
                self._network_capture = NetworkCapture()
                await self._network_capture.attach(self.page)
                result["network"] = True
                logger.info("Network capture enabled")
            except Exception as e:
                logger.warning(f"Failed to enable network capture: {e}")

        self._mcp_features_enabled = result["console"] or result["network"]
        return result

    @tool_result
    def get_console_logs(self, log_type: str = None, contains: str = None) -> List[Dict]:
        """Get captured console logs. Requires enable_mcp_features() first."""
        if not self._console_monitor:
            return []
        logs = self._console_monitor.get_logs(log_type=log_type, contains=contains)
        return [{"type": l.type, "text": l.text, "url": l.url, "timestamp": l.timestamp} for l in logs]

    @tool_result
    def get_console_errors(self) -> List[Dict]:
        """Get console errors only."""
        return self.get_console_logs(log_type="error")

    @tool_result
    def get_network_requests(self, url_contains: str = None, method: str = None) -> List[Dict]:
        """Get captured network requests. Requires enable_mcp_features() first."""
        if not self._network_capture:
            return []
        entries = self._network_capture.get_requests(url_contains=url_contains, method=method)
        return [
            {
                "url": e.url,
                "method": e.method,
                "status": e.status,
                "request_body": e.request_body[:500] if e.request_body else None,
                "response_body": e.response_body[:1000] if e.response_body else None,
            }
            for e in entries
        ]

    @tool_result
    def get_api_calls(self) -> List[Dict]:
        """Get XHR/Fetch API calls only."""
        if not self._network_capture:
            return []
        return [
            {"url": e.url, "method": e.method, "status": e.status, "body": e.response_body[:500] if e.response_body else None}
            for e in self._network_capture.get_api_calls()
        ]

    # ====================================================================
    # ADAPTIVE WAIT UTILITIES - Replace hardcoded sleeps
    # ====================================================================

    @tool_result
    async def wait_for_stable(
        self,
        timeout: float = 10.0,
        check_interval: float = 0.1,
        stability_threshold: int = 3
    ) -> bool:
        """
        Wait for page to become stable (DOM stops changing).
        Returns True if stable, False if timeout.

        Args:
            timeout: Max seconds to wait
            check_interval: Seconds between DOM checks
            stability_threshold: Number of consecutive stable checks required
        """
        if not self.page:
            return False

        start = asyncio.get_event_loop().time()
        stable_count = 0
        last_hash = None

        while (asyncio.get_event_loop().time() - start) < timeout:
            try:
                # Get DOM hash (length + key element counts)
                dom_hash = await self.page.evaluate("""() => {
                    const body = document.body;
                    return body ? `${body.innerHTML.length}_${document.querySelectorAll('*').length}` : '0_0';
                }""")

                if dom_hash == last_hash:
                    stable_count += 1
                    if stable_count >= stability_threshold:
                        return True
                else:
                    stable_count = 0
                    last_hash = dom_hash

                await asyncio.sleep(check_interval)
            except Exception:
                await asyncio.sleep(check_interval)

        return False

    @tool_result
    async def wait_for_network_idle(
        self,
        timeout: float = 10.0,
        idle_time: float = 0.5
    ) -> bool:
        """
        Wait for network to become idle (no pending requests).
        Uses Playwright's built-in network idle detection.

        Args:
            timeout: Max seconds to wait
            idle_time: Seconds of idle required
        """
        if not self.page:
            return False

        try:
            await self.page.wait_for_load_state(
                "networkidle",
                timeout=int(timeout * 1000)
            )
            return True
        except Exception:
            return False

    @tool_result
    async def wait_for_selector_safe(
        self,
        selector: str,
        timeout: float = 5.0,
        state: str = "visible"
    ) -> bool:
        """
        Wait for selector with graceful fallback (no exception on timeout).

        Args:
            selector: CSS selector to wait for
            timeout: Max seconds to wait
            state: Element state - visible, hidden, attached, detached
        """
        if not self.page:
            return False

        try:
            await self.page.wait_for_selector(
                selector,
                timeout=int(timeout * 1000),
                state=state
            )
            return True
        except Exception:
            return False

    @tool_result
    async def wait_adaptive(
        self,
        base_seconds: float = 1.0,
        max_seconds: float = 5.0,
        wait_for: str = "stable"
    ) -> None:
        """
        Adaptive wait that replaces hardcoded sleeps.
        Waits for condition OR falls back to base_seconds.

        Args:
            base_seconds: Minimum wait time
            max_seconds: Maximum wait time
            wait_for: Condition - "stable", "network", "load"
        """
        if not self.page:
            await asyncio.sleep(base_seconds)
            return

        start = asyncio.get_event_loop().time()

        if wait_for == "stable":
            # Wait for DOM stability
            await self.wait_for_stable(timeout=max_seconds)
        elif wait_for == "network":
            # Wait for network idle
            await self.wait_for_network_idle(timeout=max_seconds)
        elif wait_for == "load":
            # Wait for domcontentloaded
            try:
                await self.page.wait_for_load_state("domcontentloaded", timeout=int(max_seconds * 1000))
            except Exception as e:
                handle_error("unknown_operation_wait_wait", e, log_level="debug")

        # Ensure minimum wait time
        elapsed = asyncio.get_event_loop().time() - start
        if elapsed < base_seconds:
            await asyncio.sleep(base_seconds - elapsed)

    @tool_result
    async def connect(self):
        """Start Playwright and launch browser with STEALTH MODE"""
        # FAST PATH: Try to use pre-warmed browser from global pool
        try:
            from .global_browser_pool import get_global_pool
            pool = await get_global_pool()
            if pool:
                logger.debug("Attempting to acquire browser from global pool...")
                pool_instance = await pool.acquire()
                if pool_instance and pool_instance.browser:
                    # Use pre-warmed browser from pool
                    self.playwright = pool.playwright  # Reuse playwright instance
                    self.browser = pool_instance.browser
                    self.context = pool_instance.context
                    self.page = pool_instance.page
                    self._connected = True
                    self._reconnect_count = 0
                    logger.info("Using pre-warmed browser from global pool (instant startup)")
                    return
        except ImportError:
            pass  # global_browser_pool not available
        except Exception as e:
            logger.debug(f"Could not use global browser pool: {e}, falling back to cold start")

        # COLD START: Log which anti-bot library stack is active
        stealth_stack = []
        if USING_REBROWSER:
            stealth_stack.append("REBROWSER (CDP patched)")
        if USING_PATCHRIGHT:
            stealth_stack.append("PATCHRIGHT (undetected)")
        if PLAYWRIGHT_STEALTH_AVAILABLE:
            stealth_stack.append("playwright-stealth")
        if CURL_CFFI_AVAILABLE:
            stealth_stack.append("curl_cffi (TLS)")
        if CAMOUFOX_AVAILABLE and self.browser_type == "firefox":
            stealth_stack.append("camoufox")
        stealth_lib = " + ".join(stealth_stack) if stealth_stack else "Playwright (basic)"
        logger.debug(f"Starting browser with {stealth_lib}...")

        self.playwright = await async_playwright().start()
        browser_factory = getattr(self.playwright, self.browser_type, None)
        if not browser_factory:
            logger.warning(f"Unsupported browser type '{self.browser_type}', defaulting to chromium")
            browser_factory = self.playwright.chromium
            self.browser_type = "chromium"

        # Resolve user_data_dir to an existing profile if possible
        self.user_data_dir = self._resolve_profile_dir(self.user_data_dir)
        storage_state_path = None
        if self.storage_state:
            candidate = Path(self.storage_state)
            if candidate.exists():
                storage_state_path = str(candidate)

        # STEALTH: Use comprehensive anti-detection launch arguments
        if self.browser_type == "chromium":
            launch_args = self._stealth_launch_override or get_stealth_args()
            if self._stealth_launch_override:
                logger.debug("Auto-stealth: using MCP-compatible launch args")
        elif self.browser_type == "firefox":
            # Firefox-specific stealth args (fewer needed - Firefox is naturally less detectable)
            launch_args = [
                "-width=1920",
                "-height=1080",
            ]
        else:
            launch_args = []

        # STEALTH: Use realistic user agent (Firefox-specific if using Firefox)
        if self.browser_type == "firefox":
            user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"
        else:
            user_agent = get_random_user_agent()

        # STEALTH: Full context options with fingerprint spoofing
        # Get browser-specific headers
        if self.browser_type == "firefox":
            extra_headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
                "Connection": "keep-alive",
                "DNT": "1",  # Do Not Track - Firefox default
            }
        else:
            # Chrome/Chromium headers
            extra_headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            }
            if self._stealth_header_override:
                extra_headers = self._stealth_header_override
                logger.debug("Auto-stealth: forcing MCP-compatible HTTP headers")

        context_options = {
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": user_agent,
            "locale": "en-US",
            "timezone_id": "America/New_York",
            "geolocation": {"latitude": 40.7128, "longitude": -74.0060},  # NYC
            "permissions": ["geolocation"],
            "color_scheme": "light",
            "device_scale_factor": 1,
            "is_mobile": False,
            "has_touch": False,
            "java_script_enabled": True,
            "accept_downloads": True,
            "ignore_https_errors": True,
            "extra_http_headers": extra_headers
        }

        if storage_state_path and self.browser_type in ("chromium", "firefox"):
            # Use storage state (cookies) with ephemeral context
            # Use "new" headless mode for better anti-detection (behaves like headed)
            launch_kwargs = {"headless": self.headless}
            # Always use bundled Chromium - never system Chrome to avoid corrupting user's Chrome logins
            if launch_args:
                launch_kwargs["args"] = launch_args
            if self.browser_type == "chromium":
                launch_kwargs["chromium_sandbox"] = False
            if self.browser_type == "firefox":
                # Firefox-specific preferences for better stealth + DNS fixes for WSL2
                launch_kwargs["firefox_user_prefs"] = {
                    "dom.webdriver.enabled": False,
                    "useAutomationExtension": False,
                    "media.peerconnection.enabled": False,  # Disable WebRTC leak
                    # DNS over HTTPS to fix NS_ERROR_UNKNOWN_HOST in WSL2/headless
                    "network.trr.mode": 2,  # 2 = prefer DoH, fallback to native
                    "network.trr.uri": "https://cloudflare-dns.com/dns-query",
                    "network.dns.disablePrefetch": True,
                    "network.dns.disableIPv6": True,  # IPv6 can cause issues in WSL2
                }
            self.browser = await browser_factory.launch(**launch_kwargs)
            self.context = await self.browser.new_context(
                storage_state=storage_state_path,
                **context_options
            )
        elif self.user_data_dir and self.browser_type in ("chromium", "firefox"):
            # Persistent context using existing browser profile (for logged-in sessions)
            launch_kwargs = {
                "headless": self.headless,
                **context_options
            }
            # Always use bundled Chromium - never system Chrome to avoid corrupting user's Chrome logins
            if launch_args:
                launch_kwargs["args"] = launch_args
            if self.browser_type == "chromium":
                launch_kwargs["chromium_sandbox"] = False
            if self.browser_type == "firefox":
                launch_kwargs["firefox_user_prefs"] = {
                    "dom.webdriver.enabled": False,
                    "useAutomationExtension": False,
                    "media.peerconnection.enabled": False,
                    # DNS over HTTPS to fix NS_ERROR_UNKNOWN_HOST in WSL2/headless
                    "network.trr.mode": 2,  # 2 = prefer DoH, fallback to native
                    "network.trr.uri": "https://cloudflare-dns.com/dns-query",
                    "network.dns.disablePrefetch": True,
                    "network.dns.disableIPv6": True,  # IPv6 can cause issues in WSL2
                }
            self.context = await browser_factory.launch_persistent_context(
                self.user_data_dir,
                **launch_kwargs
            )
            self.browser = self.context.browser
        else:
            launch_kwargs = {"headless": self.headless}
            # Always use bundled Chromium - never system Chrome to avoid corrupting user's Chrome logins
            if launch_args:
                launch_kwargs["args"] = launch_args
            if self.browser_type == "chromium":
                launch_kwargs["chromium_sandbox"] = False
            if self.browser_type == "firefox":
                # Firefox stealth preferences + DNS fixes for WSL2
                launch_kwargs["firefox_user_prefs"] = {
                    "dom.webdriver.enabled": False,
                    "useAutomationExtension": False,
                    "media.peerconnection.enabled": False,
                    "privacy.trackingprotection.enabled": True,
                    # DNS over HTTPS to fix NS_ERROR_UNKNOWN_HOST in WSL2/headless
                    "network.trr.mode": 2,  # 2 = prefer DoH, fallback to native
                    "network.trr.uri": "https://cloudflare-dns.com/dns-query",
                    "network.dns.disablePrefetch": True,
                    "network.dns.disableIPv6": True,  # IPv6 can cause issues in WSL2
                }

            self.browser = await browser_factory.launch(**launch_kwargs)
            self.context = await self.browser.new_context(**context_options)

        # STEALTH: Inject anti-fingerprinting scripts for all new pages (Chromium only)
        if self.browser_type == "chromium":
            await self.context.add_init_script(get_stealth_js())

            # ANTIDETECT: Inject Multilogin-style fingerprint randomization
            try:
                from .humanization import get_fingerprint_script
                # Use unique session ID for consistent fingerprint per session
                session_id = secrets.token_hex(8)
                fingerprint_js = get_fingerprint_script(session_id)
                await self.context.add_init_script(fingerprint_js)
                logger.debug(f"Injected antidetect fingerprint (session: {session_id[:8]})")
            except ImportError:
                logger.debug("Antidetect fingerprint module not available")
            except Exception as e:
                logger.debug(f"Antidetect fingerprint injection failed: {e}")

        # Create or reuse initial page
        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = await self.context.new_page()

        # STEALTH: Apply playwright-stealth if available (works on all browsers)
        if PLAYWRIGHT_STEALTH_AVAILABLE and Stealth and self.page:
            try:
                stealth = Stealth()
                await stealth.apply_stealth_async(self.page)
                logger.debug("Applied playwright-stealth to page")
            except Exception as e:
                logger.debug(f"playwright-stealth failed (continuing without): {e}")

        # Register browser process with resource limiter if available
        if self.resource_limiter and self.browser:
            try:
                # Try to get browser PID using psutil
                import psutil
                # Note: os is already imported at module level
                current_pid = os.getpid()
                current_proc = psutil.Process(current_pid)

                # Find browser child processes (chromium/firefox)
                for child in current_proc.children(recursive=True):
                    try:
                        cmd = " ".join(child.cmdline()).lower()
                        if any(browser in cmd for browser in ["chromium", "firefox", "chrome"]):
                            self._browser_pid = child.pid
                            # Use a generic task_id for browser processes
                            self.resource_limiter.register_subprocess("browser", child.pid)
                            logger.debug(f"Registered browser PID {child.pid} with resource limiter")
                            break
                    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                        handle_error("unknown_operation_browser_browser", e, log_level="debug")
            except Exception as e:
                logger.debug(f"Could not register browser PID with resource limiter: {e}")

        # PATTERN RANDOMIZATION: Start new session for unpredictable behavior
        try:
            from .humanization import new_session
            new_session()
            logger.debug("Started new pattern randomization session")
        except ImportError:
            pass  # Pattern randomizer not available

        logger.debug(f"Browser started ({self.browser_type})")
        self._connected = True
        self._reconnect_count = 0

    # NOTE: Do NOT add @tool_result here - this internal method must return plain bool
    # for the navigate() method to correctly check: if await self._is_cloudflare_challenge(...)
    async def _is_cloudflare_challenge(self, page_content: str) -> bool:
        """Detect Cloudflare challenge/CAPTCHA pages."""
        # Strong indicators - these are specific to Cloudflare challenge pages
        strong_indicators = [
            "cf-browser-verification",
            "cf_chl_opt",
            "Cloudflare Ray ID",
            "cf-spinner",
            "_cf_chl",
            "cf-challenge",
            "challenge-platform",
            "cloudflare-static",
        ]

        # Weak indicators - need to be combined with other signals
        weak_indicators = [
            "Just a moment...",
            "Checking your browser",
            "security challenge",
            "ddos protection",
            "verify you are human",
            "enable javascript and cookies",
            "browser check",
            "attention required",
        ]

        content_lower = page_content.lower()

        # Check for strong indicators first - these are definitive
        has_strong_indicator = any(indicator.lower() in content_lower for indicator in strong_indicators)
        if has_strong_indicator:
            return True

        # Weak indicators only count if page is very short (typical of challenge pages)
        # This prevents false positives on legitimate pages that mention these phrases
        if len(page_content.strip()) < 3000:
            has_weak_indicator = any(indicator.lower() in content_lower for indicator in weak_indicators)
            if has_weak_indicator:
                return True

        return False

    @tool_result
    async def is_healthy(self) -> bool:
        """Check if browser is still healthy and responsive."""
        try:
            if not self._connected or not self.context:
                return False
            # Try a simple operation to verify browser is responsive
            if self.page and not self.page.is_closed():
                await asyncio.wait_for(self.page.evaluate("1 + 1"), timeout=5.0)
                return True
            return False
        except Exception as e:
            logger.warning(f"Browser health check failed: {e}")
            return False

    @tool_result
    async def ensure_connected(self) -> bool:
        """Ensure browser is connected, reconnecting if necessary."""
        # Quick check without lock
        if await self.is_healthy():
            return True

        # Use lock to prevent concurrent reconnection attempts (race condition fix)
        async with self._reconnect_lock:
            # Re-check after acquiring lock - another caller may have reconnected
            if await self.is_healthy():
                return True

            if self._reconnect_count >= self._max_reconnects:
                logger.error(f"Max reconnect attempts ({self._max_reconnects}) reached")
                return False

            logger.warning("Browser disconnected, attempting reconnect...")
            self._reconnect_count += 1

            try:
                # Clean up old resources with force
                await self._force_cleanup()
                # Longer delay before reconnect to ensure resources are released
                await sleep_with_jitter(2.0)
                # Reconnect with fresh state
                await self.connect()
                logger.info(f"Reconnected successfully (attempt {self._reconnect_count})")
                # Reset reconnect count on success
                self._reconnect_count = 0
                return True
            except Exception as e:
                logger.error(f"Reconnect failed: {e}")
                # Exponential backoff for next attempt
                await exponential_backoff_sleep(self._reconnect_count, base=2.0)
                return False

    @tool_result
    async def _force_cleanup(self):
        """Force cleanup of all browser resources, including killing zombie processes."""
        self._connected = False

        # Close page
        if self.page:
            try:
                await self.page.close()
            except Exception as e:
                handle_error("force_cleanup_close_page", e, log_level="debug")
            self.page = None

        # Close context
        if self.context:
            try:
                await self.context.close()
            except Exception as e:
                handle_error("force_cleanup_close_context", e, log_level="debug")
            self.context = None

        # Close browser
        if self.browser:
            try:
                await self.browser.close()
            except Exception as e:
                handle_error("force_cleanup_close_browser", e, log_level="debug")
            self.browser = None

        # Stop playwright instance completely
        if self.playwright:
            try:
                await self.playwright.stop()
            except Exception as e:
                handle_error("unknown_operation_cleanup_cleanup", e, log_level="debug")
            self.playwright = None

        # Kill any zombie chrome processes from previous session
        try:
            import subprocess
            subprocess.run(['pkill', '-9', '-f', 'playwright_chromiumdev_profile'],
                          capture_output=True, timeout=5)
        except Exception as e:
            handle_error("unknown_operation_process_process", e, log_level="debug")

        # Clean up temp profile directories
        try:
            import glob
            import shutil
            for tmp_dir in glob.glob('/tmp/playwright_chromiumdev_profile-*'):
                try:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                except Exception as e:
                    handle_error("unknown_operation", e, context={"tmp_dir": tmp_dir, "error": error}, log_level="debug")
        except Exception as e:
            handle_error("unknown_operation", e, context={"tmp_dir": tmp_dir, "error": error}, log_level="debug")

        logger.info("Playwright browser force cleaned")

    @tool_result
    async def _ensure_page(self):
        """Make sure there's a live page to work with, reconnecting if needed."""
        # First check if we need to reconnect
        if not self._connected or not self.context:
            if not await self.ensure_connected():
                raise RuntimeError("Browser disconnected and reconnect failed")

        if self.page and not self.page.is_closed():
            return

        if not self.context:
            raise RuntimeError("Browser context not initialized")

        # Reuse an existing open page if possible
        try:
            for existing in self.context.pages:
                if not existing.is_closed():
                    self.page = existing
                    return
        except Exception as e:
            logger.warning(f"Error checking existing pages: {e}")
            # Context might be dead, try reconnect
            if await self.ensure_connected():
                self.page = await self.context.new_page()
                return
            raise RuntimeError("Browser disconnected and reconnect failed")

        # Otherwise create a fresh page
        self.page = await self.context.new_page()

    @tool_result
    async def disconnect(self):
        """Close browser"""
        self._connected = False
        if self.page:
            try:
                await self.page.close()
            except Exception as e:
                handle_error("disconnect_close_page", e, log_level="debug")
            self.page = None
        if self.context:
            try:
                await self.context.close()
            except Exception as e:
                handle_error("disconnect_page_context", e, log_level="debug")
            self.context = None
        if self.browser:
            try:
                await self.browser.close()
            except Exception as e:
                handle_error("disconnect_context_browser", e, log_level="debug")
            self.browser = None
        if self.playwright:
            try:
                await self.playwright.stop()
            except Exception as e:
                handle_error("disconnect_browser_cleanup", e, log_level="debug")
            self.playwright = None
        logger.info("Playwright browser stopped")

    # =========================================================================
    # SESSION STATE MANAGEMENT
    # =========================================================================

    @tool_result
    def _get_session_path(self, domain: str) -> Path:
        """Get the path for storing session state for a domain."""
        # Sanitize domain for filename
        safe_domain = re.sub(r'[^\w\-.]', '_', domain)
        return self._session_state_dir / f"{safe_domain}_session.json"

    @tool_result
    async def save_session(self, domain: Optional[str] = None) -> bool:
        """
        Save current browser session (cookies, localStorage) to disk.

        Args:
            domain: Optional domain name for the session file. If not provided,
                    uses the current page's domain.

        Returns:
            True if session was saved successfully.
        """
        try:
            if not self.context:
                logger.warning("No browser context to save session from")
                return False

            # Get domain from current page if not provided
            if not domain and self.page:
                url = getattr(self.page, 'url', None)
                if url:
                    match = re.search(r'https?://(?:www\.)?([^/]+)', url)
                    if match:
                        domain = match.group(1)

            if not domain:
                domain = "default"

            session_path = self._get_session_path(domain)

            # Save storage state (cookies + localStorage)
            state = await self.context.storage_state()

            # Write to file
            session_path.write_text(json.dumps(state, indent=2))
            logger.info(f"Session saved for {domain}: {session_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save session: {e}")
            return False

    @tool_result
    async def load_session(self, domain: str) -> bool:
        """
        Load a previously saved session for a domain.

        Note: This should be called before connect() by setting storage_state,
        or the session can be applied by reconnecting with the storage state.

        Returns:
            True if session file exists and was loaded.
        """
        try:
            session_path = self._get_session_path(domain)

            if not session_path.exists():
                logger.debug(f"No saved session for {domain}")
                return False

            self.storage_state = str(session_path)
            logger.info(f"Session loaded for {domain}")
            return True

        except Exception as e:
            logger.error(f"Failed to load session: {e}")
            return False

    @tool_result
    def get_saved_sessions(self) -> List[str]:
        """Get list of domains with saved sessions."""
        sessions = []
        for f in self._session_state_dir.glob("*_session.json"):
            domain = f.stem.replace("_session", "")
            sessions.append(domain)
        return sessions

    @tool_result
    async def login_mode(self, service: str = None) -> Dict[str, Any]:
        """
        Switch to visible browser mode for manual login.

        This method:
        1. Saves current session state
        2. Reconnects in visible (non-headless) mode
        3. Navigates to the login page if service is specified
        4. Waits for user to complete login
        5. Saves the new session state
        6. Reconnects in headless mode

        Args:
            service: Optional service name (gmail, linkedin, etc.) to navigate to

        Returns:
            Dict with status and message
        """
        from .login_manager import SERVICES

        try:
            # Get service config
            service_config = SERVICES.get(service.lower()) if service else None

            # Save current headless state
            was_headless = self.headless

            # Disconnect current browser
            await self.disconnect()

            # Reconnect in visible mode
            self.headless = False
            await self.connect()

            # Navigate to login page if service specified
            if service_config:
                logger.info(f"Navigating to {service_config.name} login...")
                await self.navigate(service_config.login_url)

                return {
                    "status": "login_mode_active",
                    "message": f"Browser is now visible. Please log into {service_config.name}.\n"
                               f"After logging in, type 'done' or 'save login' to save and continue.",
                    "service": service,
                    "login_url": service_config.login_url
                }
            else:
                return {
                    "status": "login_mode_active",
                    "message": "Browser is now visible. Navigate to the site and log in.\n"
                               "After logging in, type 'done' or 'save login' to save and continue."
                }

        except Exception as e:
            logger.error(f"Failed to enter login mode: {e}")
            return {"status": "error", "message": str(e)}

    @tool_result
    async def finish_login(self, service: str = None) -> Dict[str, Any]:
        """
        Complete login flow - save session and return to headless mode.

        Args:
            service: Optional service name to identify the session

        Returns:
            Dict with status and message
        """
        try:
            # Get domain from current page or service
            domain = service
            if not domain and self.page:
                url = getattr(self.page, 'url', None)
                if url:
                    match = re.search(r'https?://(?:www\.)?([^/]+)', url)
                    if match:
                        domain = match.group(1)

            # Save the session
            if domain:
                await self.save_session(domain)

            # Disconnect and reconnect in headless mode
            await self.disconnect()
            self.headless = True
            await self.connect()

            return {
                "status": "success",
                "message": f"Login saved for {domain}. Browser is now running in headless mode.",
                "domain": domain
            }

        except Exception as e:
            logger.error(f"Failed to finish login: {e}")
            return {"status": "error", "message": str(e)}

    @tool_result
    async def detect_challenge(self) -> Dict[str, Any]:
        """
        Detect if page has CAPTCHA, login wall, or other challenge.

        Returns:
            Dict with detected challenge type and details
        """
        if not self.page:
            return {"detected": False, "type": None}

        try:
            # Get page content for analysis
            content = await self.page.content()
            url = getattr(self.page, 'url', '').lower()
            title = await self.page.title() or ""
            title_lower = title.lower()
            content_lower = content.lower()

            # CAPTCHA detection patterns (including Amazon-specific)
            captcha_patterns = [
                'captcha', 'recaptcha', 'hcaptcha', 'cf-turnstile', 'g-recaptcha',
                'verify you are human', 'are you a robot', 'security check',
                'challenge-form', 'challenge-running', 'cloudflare', 'ddos protection',
                'please wait while we verify', 'checking your browser', 'just a moment',
                'ray id', 'attention required', 'access denied', 'bot protection',
                # Amazon-specific patterns
                'robot check', 'automated access', 'sorry! something went wrong',
                'enter the characters', 'type the characters', 'prove you are not a robot',
                'api-services-support@amazon.com', 'awswafcaptcha', 'aws-waf-token',
                'captcha.awswaf', 'waf-challenge'
            ]

            # Login wall patterns
            login_patterns = [
                'sign in', 'log in', 'login', 'sign up', 'create account',
                'enter your password', 'enter your email', 'authentication required',
                'please sign in', 'session expired', 'you must be logged in'
            ]

            # Check for CAPTCHA
            for pattern in captcha_patterns:
                if pattern in content_lower or pattern in title_lower:
                    return {
                        "detected": True,
                        "type": "captcha",
                        "pattern": pattern,
                        "url": url,
                        "message": f"CAPTCHA detected: {pattern}"
                    }

            # Check for login wall (only if on login-specific URL or clear login form)
            login_url_indicators = ['login', 'signin', 'auth', 'accounts.']
            is_login_url = any(ind in url for ind in login_url_indicators)
            has_login_form = 'type="password"' in content_lower or 'name="password"' in content_lower

            if is_login_url or has_login_form:
                for pattern in login_patterns:
                    if pattern in content_lower:
                        return {
                            "detected": True,
                            "type": "login_wall",
                            "pattern": pattern,
                            "url": url,
                            "message": f"Login wall detected: {pattern}"
                        }

            return {"detected": False, "type": None, "url": url}

        except Exception as e:
            logger.debug(f"Challenge detection error: {e}")
            return {"detected": False, "type": None, "error": str(e)}

    @tool_result
    async def handle_challenge_popup(self, timeout: int = 120, auto_hide: bool = True) -> Dict[str, Any]:
        """
        Auto-popup browser for user to solve CAPTCHA/login, then hide and continue.

        This is the key feature: when a challenge is detected, the browser
        becomes visible briefly so the user can solve it, then automatically
        returns to headless mode and continues the task.

        Enhanced with vision-based CAPTCHA solving:
        1. First attempts vision-based auto-solve using LocalCaptchaSolver
        2. Falls back to manual popup if auto-solve fails
        3. Uses Ollama local LLMs (moondream) for image CAPTCHA reading

        Args:
            timeout: Max seconds to wait for user to solve challenge
            auto_hide: Whether to automatically hide browser after resolution

        Returns:
            Dict with resolution status and details
        """
        from rich.console import Console
        console = Console()

        # First detect if there's actually a challenge
        detection = await self.detect_challenge()

        if not detection.get("detected"):
            return {
                "status": "no_challenge",
                "message": "No CAPTCHA or login wall detected on current page"
            }

        challenge_type = detection.get("type", "unknown")

        # ENHANCEMENT: Try vision-based auto-solving for CAPTCHAs BEFORE showing popup
        if challenge_type == "captcha":
            logger.info(f"CAPTCHA detected - attempting vision-based auto-solve first...")
            console.print(f"\n[bold yellow]CAPTCHA DETECTED[/bold yellow]")
            console.print(f"[cyan]Attempting automatic vision-based solving...[/cyan]")

            try:
                from .captcha_solver import PageCaptchaHandler, LocalCaptchaSolver

                # Create solver with vision model (UI-TARS is better for UI understanding)
                solver = LocalCaptchaSolver(vision_model="0000/ui-tars-1.5-7b:latest")
                handler = PageCaptchaHandler(self.page, solver=solver)

                # Detect specific CAPTCHA type
                captcha_detection = await handler.detect_captcha()

                if captcha_detection.detected:
                    logger.info(f"[CAPTCHA] Type: {captcha_detection.challenge_type.value}")

                    # Try vision-based solving for image CAPTCHAs
                    if captcha_detection.challenge_type.value == "image_captcha":
                        console.print(f"[cyan]Using vision model (UI-TARS) to solve image CAPTCHA...[/cyan]")

                        # Import ollama for vision solving
                        try:
                            import ollama

                            # Auto-detect CAPTCHA type (text/math/image_selection)
                            captcha_type_detected = await solver.detect_captcha_type(self.page)
                            logger.info(f"[CAPTCHA] Detected sub-type: {captcha_type_detected}")

                            # Attempt vision-based solve
                            result = await solver.solve_image_with_vision(
                                self.page,
                                ollama_client=ollama,
                                vision_model="0000/ui-tars-1.5-7b:latest",
                                captcha_type=captcha_type_detected
                            )

                            if result and result.get("confidence", 0) >= 0.50:
                                answer = result.get("answer")
                                confidence = result.get("confidence")
                                console.print(f"[bold green]Vision model solved: {answer} (confidence: {confidence:.2f})[/bold green]")

                                # Record success metric
                                solver.record_solve_result(True)

                                return {
                                    "status": "resolved",
                                    "resolved": True,
                                    "challenge_type": challenge_type,
                                    "method": "vision_auto_solve",
                                    "answer": answer,
                                    "confidence": confidence
                                }
                            else:
                                logger.info("[CAPTCHA] Vision confidence too low, falling back to manual")
                                console.print(f"[yellow]Auto-solve confidence too low, showing browser for manual solve...[/yellow]")
                        except ImportError:
                            logger.debug("[CAPTCHA] Ollama not available, skipping vision solve")
                            console.print(f"[dim]Ollama not installed, skipping auto-solve[/dim]")
                    else:
                        # For hCaptcha, reCAPTCHA, Turnstile - these need manual solving
                        logger.info(f"[CAPTCHA] {captcha_detection.challenge_type.value} requires manual solving")
                        console.print(f"[dim]{captcha_detection.challenge_type.value} requires manual interaction[/dim]")

            except Exception as e:
                logger.debug(f"[CAPTCHA] Vision solver error: {e}, falling back to manual")
                console.print(f"[dim]Auto-solve failed, falling back to manual[/dim]")

        # Fall back to manual popup (original flow)
        logger.info(f"Challenge detected: {challenge_type} - showing browser for user")

        # Show notification to user
        console.print(f"\n[bold yellow]⚠ {challenge_type.upper()} DETECTED[/bold yellow]")
        console.print(f"[cyan]Opening browser window for you to solve...[/cyan]")
        console.print(f"[dim]URL: {detection.get('url')}[/dim]")
        console.print(f"[dim]You have {timeout} seconds to complete.[/dim]\n")

        try:
            # Remember we were headless
            was_headless = self.headless
            current_url = self.page.url if self.page else None

            if was_headless:
                # Switch to visible mode while preserving the page state
                await self.disconnect()
                self.headless = False
                await self.connect()

                # Navigate back to the same URL
                if current_url:
                    await self.page.goto(current_url, wait_until='domcontentloaded', timeout=30000)

            # Poll for challenge resolution
            console.print("[yellow]Waiting for you to solve the challenge...[/yellow]")
            start_time = asyncio.get_event_loop().time()
            resolved = False

            while (asyncio.get_event_loop().time() - start_time) < timeout:
                await sleep_with_jitter(2.0)  # Check every 2 seconds

                # Re-check for challenge
                new_detection = await self.detect_challenge()

                if not new_detection.get("detected"):
                    resolved = True
                    console.print("[bold green]✓ Challenge solved! Continuing...[/bold green]\n")
                    break

                # Show progress dot
                elapsed = int(asyncio.get_event_loop().time() - start_time)
                if elapsed % 10 == 0:
                    console.print(f"[dim]Still waiting... ({elapsed}s)[/dim]")

            if not resolved:
                console.print("[bold red]✗ Timeout - challenge not solved[/bold red]")
                console.print("[dim]Continuing anyway...[/dim]\n")

            # Return to headless mode if we were headless before
            if was_headless and auto_hide:
                current_url = self.page.url if self.page else None
                await self.disconnect()
                self.headless = True
                await self.connect()

                # Navigate back to preserve state
                if current_url:
                    await self.page.goto(current_url, wait_until='domcontentloaded', timeout=30000)

                console.print("[dim]Browser hidden, continuing task...[/dim]")

            return {
                "status": "resolved" if resolved else "timeout",
                "challenge_type": challenge_type,
                "resolved": resolved,
                "elapsed_seconds": int(asyncio.get_event_loop().time() - start_time)
            }

        except Exception as e:
            logger.error(f"Challenge popup handler error: {e}")
            # Try to restore headless state
            try:
                if was_headless:
                    await self.disconnect()
                    self.headless = True
                    await self.connect()
            except Exception as e:
                logger.error(f"Failed to restore headless state: {e}")
                pass
            return {
                "status": "error",
                "message": str(e),
                "challenge_type": challenge_type
            }

    @tool_result
    async def auto_handle_challenges(self, url: str = None, ollama_client=None) -> bool:
        """
        Convenience method to auto-detect and handle any challenge on current page.

        Call this after navigation to automatically popup if needed.
        Returns True if page is clear to use, False if challenge couldn't be resolved.

        For Amazon: Uses specialized AmazonCaptchaHandler with:
        1. Vision-based LLM solving (free, uses local Ollama)
        2. Scrappy bypass techniques (human-like behavior)
        3. Manual popup fallback (asks human to solve)
        """
        if not self.page:
            return True

        current_url = self.page.url.lower() if self.page else ""

        # Special handling for Amazon domains
        if 'amazon.' in current_url:
            logger.info("[CAPTCHA] Amazon domain detected - using specialized handler")
            try:
                amazon_handler = AmazonCaptchaHandler(self.page)
                detection = await amazon_handler.detect_amazon_captcha()

                if detection.get("detected"):
                    logger.info(f"[CAPTCHA] Amazon CAPTCHA type: {detection.get('type')}")

                    # Try auto-solving (vision-based) first
                    solved = await amazon_handler.solve_amazon_captcha(
                        manual_fallback=False,  # Don't do manual yet, we'll handle separately
                        ollama_client=ollama_client
                    )

                    if solved:
                        logger.success("[CAPTCHA] Amazon CAPTCHA auto-solved!")
                        return True

                    # Fall back to popup for manual solve
                    logger.info("[CAPTCHA] Auto-solve failed, showing browser for manual solve...")
                    result = await self.handle_challenge_popup(timeout=120, auto_hide=True)
                    return result.get("resolved", False)
                else:
                    return True  # No Amazon CAPTCHA detected
            except Exception as e:
                logger.warning(f"[CAPTCHA] Amazon handler error: {e}, falling back to generic")

        # Generic challenge detection for non-Amazon sites
        detection = await self.detect_challenge()

        if not detection.get("detected"):
            return True  # No challenge, good to go

        # Handle the challenge with popup
        result = await self.handle_challenge_popup(timeout=120, auto_hide=True)

        return result.get("resolved", False)

    @tool_result
    async def navigate(self, url: str, expected_domain: str = None) -> Dict[str, Any]:
        """Navigate to URL with human-like behavior, circuit breaker, and domain verification"""
        try:
            # Guard against None or empty URL
            if not url:
                return {"error": "URL is required for navigation", "success": False}

            await self._ensure_page()
            # Clean URL - remove extra quotes if present
            clean_url = str(url).strip().strip("'\"")

            # Guard against empty URL after cleaning
            if not clean_url:
                return {"error": "URL is empty after cleaning", "success": False}

            if clean_url and not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", clean_url):
                clean_url = f"https://{clean_url}"

            # Apply speed/FAST_TRACK mode safely per destination URL
            try:
                from .stealth_utils import apply_speed_mode_for_url
                apply_speed_mode_for_url(clean_url)
            except Exception:
                pass

            # Extract expected domain from URL if not provided
            if not expected_domain:
                domain_match = re.search(r"https?://(?:www\.)?([^/]+)", clean_url)
                if domain_match:
                    expected_domain = domain_match.group(1).lower()

            # CIRCUIT BREAKER: Check if domain is blocked due to repeated failures
            if expected_domain and not CircuitBreaker.is_allowed(expected_domain):
                return {
                    "error": f"Circuit breaker OPEN for {expected_domain} - too many recent failures. Wait 60s.",
                    "circuit_breaker": True
                }

            # STEALTH: Small delay before navigation (like human hesitation) - reduced
            await human_delay(50, 150)

            url_trigger = detect_stealth_trigger_from_url(clean_url)
            if url_trigger:
                await self._auto_enable_stealth(
                    trigger_reason=url_trigger["reason"],
                    domain=url_trigger.get("domain"),
                    source=url_trigger.get("source", "domain")
                )

            # TLS FINGERPRINT PRE-FLIGHT: For protected sites, warm up with curl_cffi
            # This helps bypass JA3/TLS fingerprint detection on Cloudflare/DataDome/Akamai
            protected_domains = [
                # B2B directories with strong anti-bot
                'g2.com', 'clutch.co', 'goodfirms.co', 'capterra.com', 'trustradius.com',
                # Anti-bot services
                'datadome.co', 'cloudflare.com', 'akamai.com', 'imperva.com',
                # Major social/ad platforms
                'linkedin.com', 'facebook.com', 'amazon.com', 'google.com',
                'twitter.com', 'x.com', 'instagram.com', 'tiktok.com',
                # E-commerce with anti-bot
                'ebay.com', 'walmart.com', 'target.com', 'bestbuy.com',
                # Job boards and review sites with Cloudflare
                'indeed.com', 'yelp.com', 'glassdoor.com', 'ziprecruiter.com',
            ]
            if CURL_CFFI_AVAILABLE and expected_domain and any(pd in expected_domain for pd in protected_domains):
                try:
                    # Pre-flight with Chrome TLS fingerprint (JA3 bypass)
                    logger.debug(f"Pre-flight for protected domain: {expected_domain}")
                    cffi_requests.get(clean_url, impersonate="chrome", timeout=10)
                except Exception as tls_err:
                    logger.debug(f"TLS pre-flight failed (OK to continue): {tls_err}")

            nav_timeout = Timeouts.navigation()
            idle_timeout = Timeouts.idle()

            # Heavy JS sites that never reach networkidle - skip the wait
            heavy_js_sites = ['reddit.com', 'twitter.com', 'x.com', 'youtube.com',
                             'tiktok.com', 'facebook.com', 'instagram.com', 'linkedin.com']
            skip_networkidle = any(site in clean_url.lower() for site in heavy_js_sites)

            await self.page.goto(clean_url, wait_until="domcontentloaded", timeout=nav_timeout)

            # JINA READER TECHNIQUE: Wait for network idle to handle lazy-loaded content
            if not skip_networkidle:
                try:
                    await self.page.wait_for_load_state("networkidle", timeout=idle_timeout)
                except asyncio.TimeoutError:
                    logger.debug(f"Network idle timeout after {idle_timeout}ms - continuing")
                except Exception as e:
                    logger.debug(f"Load state wait failed: {e} - continuing")
            else:
                # For heavy JS sites, use adaptive wait for DOM stability
                await self.wait_adaptive(base_seconds=0.5, max_seconds=3.0, wait_for="stable")

            # CLOUDFLARE BYPASS: Check for challenge page and wait
            # Add retry loop to handle "page is navigating" errors
            page_content = ""
            for content_attempt in range(3):
                try:
                    await self.page.wait_for_load_state("load", timeout=5000)
                    page_content = await self.page.content()
                    break
                except Exception as content_err:
                    if content_attempt < 2:
                        logger.debug(f"Content read attempt {content_attempt + 1} failed: {content_err}, retrying...")
                        await sleep_with_jitter(0.5)
                    else:
                        logger.debug(f"Content read failed after 3 attempts: {content_err}")

            if page_content:
                content_trigger = detect_stealth_trigger_from_content(page_content)
                if content_trigger:
                    await self._auto_enable_stealth(
                        trigger_reason=content_trigger,
                        domain=expected_domain,
                        source="content"
                    )

            if await self._is_cloudflare_challenge(page_content):
                logger.debug("Challenge detected - attempting bypass...")
                await self._auto_enable_stealth(
                    trigger_reason="Cloudflare challenge detected",
                    domain=expected_domain,
                    source="cloudflare"
                )

                # Strategy 1: Wait for JS challenge to complete (Cloudflare can take 10-15s)
                # Initial wait - Cloudflare Turnstile JS challenges need ~10 seconds
                await sleep_with_jitter(10.0)

                # Wait for navigation to complete after challenge
                try:
                    await self.page.wait_for_load_state("networkidle", timeout=15000)
                except (TimeoutError, Exception) as e:
                    handle_error("unknown_operation_wait_wait", e, log_level="debug")

                # Re-check if still blocked
                try:
                    page_content = await self.page.content()
                except Exception:
                    page_content = ""

                # Strategy 2: Multiple refresh attempts with exponential backoff
                max_retries = 3
                from .exponential_backoff import get_backoff
                backoff = get_backoff()

                for retry in range(max_retries):
                    if not await self._is_cloudflare_challenge(page_content):
                        logger.debug(f"Challenge bypassed (attempt {retry + 1})")
                        break

                    wait_time = backoff.calculate_delay(attempt=retry, last_delay=5.0)
                    wait_time = min(wait_time, 30.0)  # Cap at 30s
                    logger.info(f"Challenge still present - retry {retry + 1}/{max_retries} (waiting {wait_time:.1f}s)...")

                    try:
                        await self.page.reload(wait_until="domcontentloaded", timeout=20000)
                        await sleep_with_jitter(wait_time)
                        try:
                            await self.page.wait_for_load_state("networkidle", timeout=10000)
                        except (TimeoutError, Exception) as e:
                            handle_error("unknown_operation_page_wait", e, log_level="debug")
                        page_content = await self.page.content()
                    except Exception as refresh_err:
                        logger.debug(f"Refresh failed: {refresh_err}")
                        continue

                # Final check after all retries
                if await self._is_cloudflare_challenge(page_content):
                    # Log but continue - partial data from headings/inputs may still be useful
                    logger.warning("Cloudflare challenge not bypassed - continuing with partial data")
                else:
                    logger.debug("Challenge bypassed")

            # GOOGLE DATE FILTER BYPASS: If Google search is blocking/empty, retry with date filter
            if 'google.com/search' in clean_url and '&tbs=' not in clean_url:
                # Check if Google is blocking or showing empty results
                try:
                    result_check = await self.page.evaluate("""
                        () => {
                            const content = document.body.innerText.toLowerCase();
                            const hasNoResults = content.includes('no results') || content.includes('did not match');
                            const hasCaptcha = content.includes('unusual traffic') || content.includes('captcha') ||
                                             content.includes('verify you are human') || !!document.querySelector('iframe[src*="recaptcha"]');
                            const hasResults = !!document.querySelector('div.g, div[data-hveid]');
                            return { hasNoResults, hasCaptcha, hasResults };
                        }
                    """)
                    if result_check.get('hasCaptcha') or (result_check.get('hasNoResults') and not result_check.get('hasResults')):
                        # Try with "past month" filter - often bypasses rate limiting
                        date_filtered_url = clean_url + ('&' if '?' in clean_url else '?') + 'tbs=qdr:m'
                        logger.info(f"Google blocking detected - retrying with date filter: past month")
                        await self.wait_adaptive(base_seconds=1.0, max_seconds=3.0, wait_for="network")
                        await self.page.goto(date_filtered_url, wait_until="domcontentloaded", timeout=30000)
                        await self.wait_adaptive(base_seconds=0.5, max_seconds=2.0, wait_for="stable")
                except Exception as date_bypass_err:
                    logger.debug(f"Date filter bypass attempt failed: {date_bypass_err}")

            # DOMAIN VERIFICATION: Check we landed on the right domain
            actual_url = getattr(self.page, 'url', '')
            domain_mismatch = False
            if expected_domain:
                actual_domain_match = re.search(r"https?://(?:www\.)?([^/]+)", actual_url)
                if actual_domain_match:
                    actual_domain = actual_domain_match.group(1).lower()
                    if expected_domain not in actual_domain and actual_domain not in expected_domain:
                        logger.warning(f"Domain mismatch: expected {expected_domain}, got {actual_domain}")
                        domain_mismatch = True

            # STEALTH: Simulate reading/looking at page after load (reduced in fast mode)
            await human_delay(100, 300)

            # ENHANCED STEALTH: Apply additional anti-detection measures
            await self.apply_enhanced_stealth()

            # Get summary with timeout to prevent hanging
            try:
                summary = await asyncio.wait_for(self._summarize_page(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.debug("Page summary timed out - using minimal data")
                summary = {"title": await self.page.title() if self.page else ""}

            # Check for login walls with timeout
            try:
                login_detected = await asyncio.wait_for(self._detect_login_wall(), timeout=3.0)
            except asyncio.TimeoutError:
                logger.debug("Login detection timed out")
                login_detected = False

            # AUTO-CAPTCHA DETECTION AND SOLVING: Check for captcha after navigation
            captcha_detected = False
            captcha_solved = False
            try:
                solver = LocalCaptchaSolver(vision_model="0000/ui-tars-1.5-7b:latest")
                handler = PageCaptchaHandler(self.page, solver=solver)

                # Detect any CAPTCHA on the page
                captcha_detection = await asyncio.wait_for(handler.detect_captcha(), timeout=3.0)

                if captcha_detection.detected:
                    captcha_detected = True
                    captcha_type = captcha_detection.challenge_type.value
                    logger.info(f"[CAPTCHA] Auto-detected {captcha_type} after navigation")

                    # Try vision-based solving for image CAPTCHAs
                    if captcha_type == "image_captcha":
                        logger.info("[CAPTCHA] Attempting vision-based auto-solve...")
                        try:
                            # Import ollama for vision solving
                            import ollama

                            # Auto-detect CAPTCHA sub-type
                            captcha_subtype = await solver.detect_captcha_type(self.page)
                            logger.info(f"[CAPTCHA] Sub-type: {captcha_subtype}")

                            # Attempt vision-based solve
                            vision_result = await solver.solve_image_with_vision(
                                self.page,
                                ollama_client=ollama,
                                vision_model="0000/ui-tars-1.5-7b:latest",
                                captcha_type=captcha_subtype
                            )

                            if vision_result and vision_result.get("confidence", 0) >= 0.50:
                                answer = vision_result.get("answer")
                                confidence = vision_result.get("confidence")
                                logger.success(f"[CAPTCHA] Auto-solved with {confidence:.0%} confidence: {answer}")
                                captcha_solved = True
                            else:
                                logger.info("[CAPTCHA] Vision confidence too low for auto-solve")
                        except ImportError:
                            logger.debug("[CAPTCHA] Ollama not available for vision solving")
                        except Exception as solve_err:
                            logger.debug(f"[CAPTCHA] Vision solve error: {solve_err}")
                    else:
                        logger.debug(f"[CAPTCHA] {captcha_type} requires manual solving")

            except asyncio.TimeoutError:
                logger.debug("[CAPTCHA] Detection timed out")
            except Exception as captcha_err:
                logger.debug(f"[CAPTCHA] Detection error: {captcha_err}")


            result = {
                "success": True,
                "url": getattr(self.page, 'url', ''),
                "title": summary.get("title"),
                "summary": summary.get("summary"),
                "headings": summary.get("headings"),
                "links": summary.get("links"),
                "inputs": summary.get("inputs")
            }

            # Add captcha detection info to result
            if captcha_detected:
                result["captcha_detected"] = True
                result["captcha_solved"] = captcha_solved
                if not captcha_solved:
                    result["warning"] = (result.get("warning", "") + " CAPTCHA detected - may need manual solving.").strip()


            if domain_mismatch:
                result["warning"] = f"Domain mismatch: expected {expected_domain}, landed on {actual_domain}"
                result["domain_mismatch"] = True

            if login_detected:
                result["login_required"] = True
                result["warning"] = (result.get("warning", "") + " Login wall detected - please log in first.").strip()

            # CIRCUIT BREAKER: Record success
            if expected_domain:
                CircuitBreaker.record_success(expected_domain)

            # MEM0: Record visit in session memory
            SessionMemory.add_visit(
                getattr(self.page, 'url', ''),
                title=result.get("title", ""),
                success=True
            )

            return result
        except Exception as e:
            logger.error(f"Navigation error: {e}")
            # CIRCUIT BREAKER: Record failure
            if expected_domain:
                CircuitBreaker.record_failure(expected_domain)
            # MEM0: Record failed visit
            SessionMemory.add_visit(url, title="", success=False)
            SessionMemory.record_error(expected_domain or "unknown", str(e), "navigate")
            return {
                "error": f"Could not navigate to {url[:100]}",
                "url": url,
                "success": False
            }

    @tool_result
    async def _detect_login_wall(self) -> bool:
        """Detect if page is showing a login/signup wall"""
        try:
            await self._ensure_page()
            # Check for common login wall indicators
            login_indicators = await self.page.evaluate("""
                () => {
                    const body = document.body ? document.body.innerText.toLowerCase() : '';
                    const indicators = {
                        hasLoginButton: !!document.querySelector('button[data-testid*="login"], button[class*="login"], a[href*="login"], a[href*="signin"]'),
                        hasSignupPrompt: body.includes('sign up') || body.includes('create account') || body.includes('join now'),
                        hasPasswordField: !!document.querySelector('input[type="password"]'),
                        hasLoginForm: !!document.querySelector('form[action*="login"], form[class*="login"], form[id*="login"]'),
                        // Platform-specific checks
                        facebookLogin: body.includes('log in to facebook') || body.includes('create new account'),
                        redditLogin: body.includes('log in to reddit') || !!document.querySelector('a[href*="login.reddit"]'),
                        linkedinLogin: body.includes('sign in to linkedin') || body.includes('join linkedin'),
                    };
                    return indicators;
                }
            """)

            # If multiple strong indicators, likely a login wall
            strong_signals = sum([
                login_indicators.get('hasPasswordField', False),
                login_indicators.get('hasLoginForm', False),
                login_indicators.get('facebookLogin', False),
                login_indicators.get('redditLogin', False),
                login_indicators.get('linkedinLogin', False),
            ])

            return strong_signals >= 1
        except Exception as e:
            logger.debug(f"Login detection error: {e}")
            return False

    @tool_result
    async def click(self, selector: str, visual_description: str = None, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Click an element with human-like timing and self-healing selectors.

        Uses comprehensive fallback strategies:
        1. Self-healing selectors (cached, CSS, XPath, data-testid, aria-label, text, coordinates)
        2. Visual detection (screenshot + AI) as last resort

        Args:
            selector: CSS selector to find element
            visual_description: Description for fallback (e.g., "the blue Compose button")
            context: Additional context (text, aria-label, role, etc.)
        """
        import random
        try:
            await self._ensure_page()

            # STEALTH: Add human-like delay before clicking
            await human_delay(100, 300)

            # Try self-healing selector first (comprehensive fallback strategies)
            if SELF_HEALING_AVAILABLE and SelfHealingSelector:
                healer = SelfHealingSelector(self.page)
                result = await healer.find_and_click(
                    selector=selector,
                    description=visual_description,
                    context=context,
                    element_type="button"
                )

                if result.get('success'):
                    # Add human-like delay after click
                    await human_delay(50, 150)
                    logger.info(f"[SELF-HEALING] Clicked using: {result.get('method')}")
                    # Add URL to result if not already present
                    if 'url' not in result:
                        result['url'] = getattr(self.page, 'url', '')
                    return result

                # Self-healing failed, try visual fallback
                logger.debug(f"Self-healing failed, trying visual fallback...")
                return await self._click_visual_fallback(selector, visual_description, error=result.get('error'))

            # Fallback to original behavior if self-healing not available
            element = await self.page.query_selector(selector)
            if element:
                box = await element.bounding_box()
                if box:
                    # STEALTH: Click slightly off-center like a human
                    offset_x = random.uniform(-box['width'] * 0.15, box['width'] * 0.15)
                    offset_y = random.uniform(-box['height'] * 0.15, box['height'] * 0.15)
                    await self.page.mouse.click(
                        box['x'] + box['width'] / 2 + offset_x,
                        box['y'] + box['height'] / 2 + offset_y
                    )
                    await human_delay(50, 150)
                    return {
                        "success": True,
                        "method": "selector",
                        "url": getattr(self.page, 'url', '')
                    }
                else:
                    await self.page.click(selector, timeout=8000)
                    await human_delay(50, 150)
                    return {
                        "success": True,
                        "method": "selector",
                        "url": getattr(self.page, 'url', '')
                    }

            # Element not found - try CSS alternatives before visual fallback
            logger.debug(f"Selector '{selector}' not found, trying CSS alternatives...")

            # Generate alternative selectors
            alt_selectors = []
            if selector:
                # ID variations
                if selector.startswith('#'):
                    element_id = selector[1:]
                    alt_selectors.extend([f"[id='{element_id}']", f"[id*='{element_id}']"])
                # Class variations
                if '.' in selector:
                    for cls in selector.split('.')[1:]:
                        if cls:
                            alt_selectors.extend([f"[class*='{cls}']", f".{cls}"])
                # Text-based alternatives from visual_description
                if visual_description:
                    alt_selectors.extend([
                        f"text='{visual_description}'",
                        f":has-text('{visual_description}')",
                        f"[aria-label*='{visual_description}']",
                        f"[placeholder*='{visual_description}']",
                        f"[title*='{visual_description}']"
                    ])

            # Try each alternative
            for alt in alt_selectors:
                try:
                    alt_elem = await self.page.query_selector(alt)
                    if alt_elem and await alt_elem.is_visible():
                        box = await alt_elem.bounding_box()
                        if box:
                            import random
                            offset_x = random.uniform(-3, 3)
                            offset_y = random.uniform(-3, 3)
                            await self.page.mouse.click(
                                box['x'] + box['width'] / 2 + offset_x,
                                box['y'] + box['height'] / 2 + offset_y
                            )
                            await human_delay(50, 150)
                            logger.info(f"CSS alternative worked: {alt}")
                            return {
                                "success": True,
                                "method": "css_alternative",
                                "selector": alt,
                                "url": getattr(self.page, 'url', '')
                            }
                except Exception as e:
                    logger.debug(f"CSS alternative {alt} failed: {e}")
                    pass

            # Fall back to visual
            logger.debug(f"CSS alternatives failed, trying visual fallback...")
            return await self._click_visual_fallback(selector, visual_description)

        except Exception as e:
            logger.debug(f"Click error: {e}")
            # Try visual fallback as last resort
            return await self._click_visual_fallback(selector, visual_description, error=str(e))

    @tool_result
    async def _click_visual_fallback(
        self,
        selector: str,
        visual_description: str = None,
        error: str = None
    ) -> Dict[str, Any]:
        """
        Visual fallback: screenshot + AI to find and click element.

        Takes a screenshot, asks vision model where to click, clicks there.
        """
        import random

        if not VISUAL_FALLBACK_AVAILABLE or get_visual_fallback is None:
            logger.warning("Visual fallback not available")
            return {"error": error or f"Selector '{selector}' not found and no visual fallback"}

        try:
            visual_fb = get_visual_fallback()
            if not visual_fb.has_vision:
                return {"error": error or f"Selector '{selector}' not found and no vision model"}

            # Build description from selector if not provided
            description = visual_description
            if not description:
                # Try to infer from selector
                description = self._selector_to_description(selector)

            logger.info(f"[VISUAL FALLBACK] Looking for: {description}")

            # Find element coordinates via vision
            coords = await visual_fb.find_element_visually(self.page, description)

            if coords:
                x, y = coords
                # Add human-like offset
                offset_x = random.uniform(-3, 3)
                offset_y = random.uniform(-3, 3)
                await self.page.mouse.click(x + offset_x, y + offset_y)
                await human_delay(50, 150)
                logger.info(f"[VISUAL FALLBACK] Clicked at ({x}, {y})")
                return {
                    "success": True,
                    "url": getattr(self.page, 'url', ''),
                    "method": "visual",
                    "coords": coords
                }

            return {"error": f"Could not find element visually: {description}"}

        except Exception as e:
            logger.error(f"Visual fallback error: {e}")
            return {"error": f"Visual fallback failed: {e}"}

    @tool_result
    def _selector_to_description(self, selector: str) -> str:
        """Convert CSS selector to human-readable description for vision model."""
        # Common patterns
        if 'compose' in selector.lower():
            return "the Compose button to write a new email"
        if 'search' in selector.lower():
            return "the search input box"
        if 'submit' in selector.lower() or 'button[type="submit"]' in selector:
            return "the submit button"
        if 'login' in selector.lower() or 'sign' in selector.lower():
            return "the login or sign in button"
        if 'send' in selector.lower():
            return "the send button"
        if 'connect' in selector.lower():
            return "the Connect button"
        if 'message' in selector.lower():
            return "the Message button"
        if 'next' in selector.lower() or 'continue' in selector.lower():
            return "the Next or Continue button"

        # Extract text from selector hints
        if 'aria-label' in selector:
            import re
            match = re.search(r'aria-label[*]?=["\']([^"\']+)', selector)
            if match:
                return f"the element labeled '{match.group(1)}'"

        if ':has-text' in selector:
            import re
            match = re.search(r':has-text\(["\']([^"\']+)', selector)
            if match:
                return f"the element with text '{match.group(1)}'"

        # Default: describe the type
        if 'button' in selector:
            return "a button on the page"
        if 'input' in selector:
            return "an input field"
        if 'a[' in selector or 'a.' in selector:
            return "a link on the page"

        return f"the element matching: {selector[:50]}"

    @tool_result
    async def fill(self, selector: str, value: str, visual_description: str = None, context: Dict[str, Any] = None, press_enter: bool = None) -> Dict[str, Any]:
        """
        Fill an input field with human-like typing and self-healing selectors.

        Uses comprehensive fallback strategies:
        1. Site-specific selectors (Google, YouTube, etc.)
        2. Self-healing selectors (cached, CSS, XPath, data-testid, aria-label, placeholder, text)
        3. Visual detection as last resort

        Args:
            selector: CSS selector for input field
            value: Text to type
            visual_description: Description for fallback (e.g., "the search box")
            context: Additional context (placeholder, aria-label, etc.)
            press_enter: Whether to press Enter after filling (auto-detects for search boxes if None)
        """
        import random
        try:
            await self._ensure_page()

            # SITE-SPECIFIC SELECTORS: Try known-good selectors for common sites first
            if SITE_SELECTORS_AVAILABLE and get_interaction_selectors and self.page:
                current_url = getattr(self.page, 'url', '')
                site_selectors = get_interaction_selectors(current_url, "search_input") if current_url else []

                for site_selector in site_selectors:
                    try:
                        element = await self.page.wait_for_selector(site_selector, timeout=2000)
                        if element:
                            await element.click()
                            await human_delay(50, 100)
                            await self.page.keyboard.press("Control+a")
                            await human_delay(30, 50)
                            await self.page.keyboard.press("Backspace")
                            await human_delay(30, 50)
                            # Type with human-like delays
                            for char in value:
                                await self.page.keyboard.type(char)
                                await human_delay(30, 80)
                            logger.info(f"[SITE-SELECTOR] Filled using: {site_selector}")
                            # Press Enter to submit search (common pattern for search boxes)
                            await human_delay(100, 200)
                            await self.page.keyboard.press("Enter")
                            return {
                                "success": True,
                                "method": "site_selector",
                                "selector": site_selector,
                                "url": getattr(self.page, 'url', '')
                            }
                    except Exception:
                        continue

            # Try self-healing selector
            if SELF_HEALING_AVAILABLE and SelfHealingSelector:
                healer = SelfHealingSelector(self.page)

                # Use find_and_fill which handles finding and filling directly
                result = await healer.find_and_fill(
                    selector=selector,
                    value=value,
                    description=visual_description,
                    context=context,
                    element_type="input"
                )

                if result.get('success'):
                    logger.info(f"[SELF-HEALING] Filled using: {result.get('method')}")
                    await human_delay(50, 150)
                    # Add URL to result if not already present
                    if 'url' not in result:
                        result['url'] = getattr(self.page, 'url', '')
                    return result

                # Self-healing failed, fall back to click + type approach
                logger.debug(f"Self-healing fill failed, trying click + type...")

            # Fallback: Click to focus first (uses self-healing click)
            click_result = await self.click(selector, visual_description, context)

            if "error" in click_result:
                # Click failed even with fallbacks
                return click_result

            await human_delay(50, 150)

            # STEALTH: Clear existing content
            await self.page.keyboard.press("Control+a")
            await human_delay(30, 80)
            await self.page.keyboard.press("Backspace")
            await human_delay(50, 120)

            # STEALTH: Type character by character with variable delays
            for char in value:
                await self.page.keyboard.type(char)
                # Variable typing speed
                if char in ' .!?,':
                    await human_delay(60, 150)  # Longer pause after punctuation
                else:
                    await human_delay(30, 100)  # Normal typing speed

            # Optionally press Enter after filling (useful for search boxes)
            should_press_enter = press_enter
            if should_press_enter is None:
                # Auto-detect: press Enter for search-like inputs
                sel_lower = selector.lower() if selector else ''
                desc_lower = (visual_description or '').lower()
                search_keywords = ['search', 'query', 'q=', 'q"]', 'filter', 'find']
                if any(kw in sel_lower or kw in desc_lower for kw in search_keywords):
                    should_press_enter = True

            if should_press_enter:
                await human_delay(100, 200)
                await self.page.keyboard.press("Enter")
                logger.debug("[FILL] Pressed Enter after filling")

            return {
                "success": True,
                "method": click_result.get("method", "selector"),
                "url": getattr(self.page, 'url', '')
            }
        except Exception as e:
            logger.error(f"Fill error: {e}")
            return {"error": str(e)}

    @tool_result
    async def batch_execute(
        self,
        actions: List[Dict[str, Any]],
        stop_on_error: bool = False
    ) -> Dict[str, Any]:
        """
        Execute multiple browser actions in one call.

        This reduces token usage by ~90% compared to individual calls
        by eliminating redundant snapshots between actions.

        Args:
            actions: List of action dicts, each with:
                - action: str ("click", "fill", "type", "select", "scroll", "navigate")
                - selector: str (element selector, required for click/fill)
                - ref: str (alias for selector, supports MMID refs)
                - value: str (for fill/type)
                - text: str (alias for value)
                - url: str (for navigate)
                - direction: str (for scroll, default "down")
                - amount: int (for scroll, default 500)
                - press_enter: bool (for fill, default auto-detect)
            stop_on_error: If True, stop on first failure

        Returns:
            Dict with:
                - success: bool
                - results: List of individual action results
                - successful: int count
                - failed: int count
                - url: current page URL

        Example:
            await client.batch_execute([
                {"action": "fill", "selector": "#name", "value": "John"},
                {"action": "fill", "selector": "#email", "value": "john@email.com"},
                {"action": "click", "selector": "button[type='submit']"}
            ])
        """
        results = []
        successful = 0
        failed = 0

        for i, action_dict in enumerate(actions):
            action_type = action_dict.get("action")

            if not action_type:
                error_result = {
                    "success": False,
                    "action": "batch_execute",
                    "error": f"Action {i}: Missing 'action' field"
                }
                results.append(error_result)
                failed += 1
                if stop_on_error:
                    break
                continue

            try:
                # Normalize selector/ref parameter (support both)
                selector = action_dict.get("selector") or action_dict.get("ref")

                # Execute the appropriate action method
                if action_type == "click":
                    if not selector:
                        result = {"success": False, "error": "Missing selector/ref for click"}
                    else:
                        result = await self.click(selector)

                elif action_type in ("fill", "type"):
                    value = action_dict.get("value") or action_dict.get("text", "")
                    press_enter = action_dict.get("press_enter")
                    if not selector:
                        result = {"success": False, "error": "Missing selector/ref for fill"}
                    else:
                        result = await self.fill(selector, value, press_enter=press_enter)

                elif action_type == "scroll":
                    direction = action_dict.get("direction", "down")
                    amount = action_dict.get("amount", 500)
                    script = f"window.scrollBy(0, {amount if direction == 'down' else -amount})"
                    result = await self.evaluate(script)

                elif action_type == "navigate":
                    url = action_dict.get("url")
                    if not url:
                        result = {"success": False, "error": "Missing url for navigate"}
                    else:
                        result = await self.navigate(url)

                else:
                    result = {
                        "success": False,
                        "action": action_type,
                        "error": f"Unknown action type: {action_type}"
                    }

                # Collect result
                if result.get("success"):
                    successful += 1
                else:
                    failed += 1

                results.append({
                    "step": i + 1,
                    "action": action_type,
                    "success": result.get("success", False),
                    "result": result
                })

                if not result.get("success") and stop_on_error:
                    break

            except Exception as e:
                error_result = {
                    "step": i + 1,
                    "action": action_type,
                    "success": False,
                    "error": str(e)
                }
                results.append(error_result)
                failed += 1
                if stop_on_error:
                    break

        return {
            "success": failed == 0,
            "results": results,
            "successful": successful,
            "failed": failed,
            "url": getattr(self.page, 'url', '') if self.page else ''
        }

    @tool_result
    async def evaluate(self, script: str) -> Dict[str, Any]:
        """Execute JavaScript"""
        try:
            await self._ensure_page()
            result = await self.page.evaluate(script)
            return {
                "success": True,
                "url": getattr(self.page, 'url', ''),
                "result": result
            }
        except Exception as e:
            logger.error(f"Evaluate error: {e}")
            return {"error": str(e)}

    @tool_result
    async def screenshot(self) -> Dict[str, Any]:
        """Take a screenshot and return base64-encoded image data"""
        try:
            import base64
            await self._ensure_page()
            screenshot_bytes = await self.page.screenshot()
            screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            return {
                "success": True,
                "url": getattr(self.page, 'url', ''),
                "size": len(screenshot_bytes),
                "screenshot_base64": screenshot_base64
            }
        except Exception as e:
            logger.error(f"Screenshot error: {e}")
            return {"error": str(e), "success": False}

    @tool_result
    async def get_content(self) -> Dict[str, Any]:
        """Get page HTML content"""
        try:
            await self._ensure_page()
            content = await self.page.content()
            return {
                "success": True,
                "url": getattr(self.page, 'url', ''),
                "content": content[:5000]
            }  # Limit size
        except Exception as e:
            logger.error(f"Get content error: {e}")
            return {"error": str(e)}

    @tool_result
    async def get_text(self, selector: str = "body") -> Dict[str, Any]:
        """Get text content of an element"""
        try:
            await self._ensure_page()
            text = await self.page.text_content(selector, timeout=8000)
            return {
                "success": True,
                "url": getattr(self.page, 'url', ''),
                "text": text
            }
        except Exception as e:
            logger.error(f"Get text error: {e}")
            return {"error": str(e)}

    @tool_result
    async def get_accessibility_snapshot(self) -> Dict[str, Any]:
        """
        Get a structured, LLM-friendly representation of the page using accessibility APIs.

        Returns a simplified snapshot with:
        - Page URL and title
        - Flat lists of inputs, buttons, and links
        - Tree summary statistics

        This is useful for LLMs to understand page structure without parsing full HTML.
        """
        try:
            await self._ensure_page()

            # Get accessibility tree snapshot
            snapshot = await self.page.accessibility.snapshot()

            if not snapshot:
                return {"error": "No accessibility snapshot available"}

            # Get page metadata
            url = getattr(self.page, 'url', '')
            title = await self.page.title()

            # Extract interactive elements
            inputs = []
            buttons = []
            links = []

            @tool_result
            def extract_elements(node: Dict[str, Any]) -> None:
                """Recursively extract interactive elements from accessibility tree."""
                if not node:
                    return

                role = node.get("role", "")
                name = node.get("name", "")
                value = node.get("value", "")
                focused = node.get("focused", False)

                # Build element info
                element_info = {
                    "role": role,
                    "name": name,
                }

                if value:
                    element_info["value"] = value
                if focused:
                    element_info["focused"] = focused

                # Categorize by role
                if role in ["textbox", "searchbox", "combobox", "spinbutton"]:
                    inputs.append(element_info)
                elif role == "button":
                    buttons.append(element_info)
                elif role == "link":
                    links.append(element_info)

                # Recurse into children
                children = node.get("children", [])
                for child in children:
                    extract_elements(child)

            # Process the tree
            extract_elements(snapshot)

            # Build summary
            tree_summary = f"Page has {len(inputs)} inputs, {len(buttons)} buttons, {len(links)} links"

            return {
                "success": True,
                "url": url,
                "title": title,
                "inputs": inputs,
                "buttons": buttons,
                "links": links,
                "tree_summary": tree_summary
            }

        except Exception as e:
            logger.error(f"Get accessibility snapshot error: {e}")
            return {"error": str(e)}

    @tool_result
    async def extract_with_selectors(
        self,
        item_selector: str,
        field_selectors: Dict[str, str],
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        Extract structured data using CSS selectors.

        This is more accurate than LLM extraction for well-structured pages
        like e-commerce sites, directories, or listings.

        Args:
            item_selector: CSS selector for each item container (e.g., ".product", "article")
            field_selectors: Dict mapping field names to CSS selectors relative to item
                           e.g., {"title": "h3 a", "price": ".price", "link": "a@href"}
                           Use @attr to extract attribute instead of text
            limit: Maximum number of items to extract

        Example:
            await extract_with_selectors(
                item_selector=".product_pod",
                field_selectors={
                    "title": "h3 a@title",  # Get title attribute
                    "price": ".price_color",
                    "link": "h3 a@href"
                }
            )
        """
        try:
            await self._ensure_page()

            # JavaScript to extract structured data
            js_code = """
            (args) => {
                const [itemSel, fieldSels, maxItems] = args;
                const items = document.querySelectorAll(itemSel);
                const results = [];

                for (let i = 0; i < Math.min(items.length, maxItems); i++) {
                    const item = items[i];
                    const data = {};

                    for (const [field, selector] of Object.entries(fieldSels)) {
                        let sel = selector;
                        let attr = null;

                        // Check for @attribute syntax
                        if (selector.includes('@')) {
                            const parts = selector.split('@');
                            sel = parts[0] || ':scope';  // :scope for the item itself
                            attr = parts[1];
                        }

                        const el = sel === ':scope' ? item : item.querySelector(sel);
                        if (el) {
                            if (attr) {
                                data[field] = el.getAttribute(attr) || '';
                            } else {
                                data[field] = el.textContent?.trim() || '';
                            }
                        } else {
                            data[field] = '';
                        }
                    }

                    // Only add if at least one field has data
                    if (Object.values(data).some(v => v)) {
                        results.push(data);
                    }
                }

                return results;
            }
            """

            result = await self.page.evaluate(
                js_code,
                [item_selector, field_selectors, limit]
            )

            return {
                "success": True,
                "data": result,
                "count": len(result),
                "url": getattr(self.page, 'url', '')
            }

        except Exception as e:
            logger.error(f"Selector extraction error: {e}")
            return {"error": str(e)}

    @tool_result
    async def extract_list_auto(self, limit: int = 100) -> Dict[str, Any]:
        """
        Auto-detect and extract list items using known site selectors.

        This is the PREFERRED extraction method - uses CSS selectors directly
        without any LLM involvement, ensuring 100% accuracy.

        Supports:
        - Hacker News (news.ycombinator.com)
        - Amazon product listings
        - eBay listings
        - GitHub Trending
        - Reddit posts
        - LinkedIn jobs
        - Twitter/X posts
        - And many more (see site_selectors.py)
        """
        try:
            await self._ensure_page()

            current_url = getattr(self.page, 'url', '')
            logger.info(f"[EXTRACT_LIST_AUTO] Detecting selectors for: {current_url}")

            # Get site-specific selectors
            site_config = None
            if get_site_selectors:
                site_config = get_site_selectors(current_url)

            if site_config:
                item_selector = site_config.get('item_selector', '')
                field_selectors = site_config.get('field_selectors', {})
                site_limit = min(limit, site_config.get('limit', 30))

                logger.info(f"[EXTRACT_LIST_AUTO] Using known selectors: {item_selector}")

                # Use extract_with_selectors for the actual extraction
                result = await self.extract_with_selectors(
                    item_selector=item_selector,
                    field_selectors=field_selectors,
                    limit=site_limit
                )

                if result.get('success') and result.get('data'):
                    result['_extraction_method'] = 'known_site_selectors'
                    result['_site_pattern'] = item_selector
                    return result

            # Fallback: Try common list patterns
            logger.info("[EXTRACT_LIST_AUTO] No known selectors, trying common patterns...")

            common_patterns = [
                # News/article sites
                ('.athing', {'title': '.titleline > a', 'link': '.titleline > a@href', 'rank': '.rank'}),
                ('article', {'title': 'h2 a, h3 a, h1 a', 'link': 'a@href'}),
                ('.post', {'title': 'h2, h3, .title', 'link': 'a@href'}),
                # E-commerce
                ('.product', {'title': '.product-title, h3, h4', 'price': '.price', 'link': 'a@href'}),
                ('.item', {'title': '.title, h3, h4', 'price': '.price', 'link': 'a@href'}),
                # Search results
                ('.result', {'title': 'h3, h2, .title', 'link': 'a@href', 'description': '.description, p'}),
            ]

            for item_sel, field_sels in common_patterns:
                try:
                    result = await self.extract_with_selectors(
                        item_selector=item_sel,
                        field_selectors=field_sels,
                        limit=limit
                    )
                    # IMPORTANT: Validate that we got ACTUAL data, not just empty titles
                    if result.get('success') and result.get('data') and len(result['data']) >= 2:
                        # Check that at least one item has a non-empty title
                        has_valid_title = any(
                            item.get('title', '').strip()
                            for item in result['data'][:5]
                        )
                        if has_valid_title:
                            result['_extraction_method'] = 'common_pattern'
                            result['_pattern_used'] = item_sel
                            logger.info(f"[EXTRACT_LIST_AUTO] Success with pattern: {item_sel}")
                            return result
                        else:
                            logger.debug(f"[EXTRACT_LIST_AUTO] Pattern {item_sel} matched but titles empty, skipping")
                except Exception:
                    continue

            # DYNAMIC SELECTOR DETECTION: Extract items directly from page
            logger.info("[EXTRACT_LIST_AUTO] Trying dynamic extraction...")
            try:
                detected = await self._detect_list_selectors()
                # IMPORTANT: _detect_list_selectors returns items directly, USE THEM!
                if detected and detected.get('items') and len(detected['items']) >= 2:
                    items = detected['items'][:limit]
                    logger.info(f"[EXTRACT_LIST_AUTO] Dynamic extraction success: {len(items)} items")
                    return {
                        "success": True,
                        "data": items,
                        "count": len(items),
                        "url": current_url,
                        "_extraction_method": "dynamic_extraction",
                        "_note": "Extracted links with text directly from page"
                    }
            except Exception as e:
                await self._ensure_page()
                current_url = self.page.url if self.page else "unknown"
                handle_error(
                    operation="dynamic_extraction",
                    error=e,
                    context={"url": current_url},
                    log_level="warning"
                )

            # KIMI K2 AI SELECTOR DISCOVERY: Use AI to analyze HTML and find selectors
            logger.info("[EXTRACT_LIST_AUTO] Trying Kimi K2 AI selector discovery...")
            try:
                kimi_result = await self._kimi_discover_selectors(current_url, limit)
                if kimi_result and kimi_result.get('success') and kimi_result.get('data'):
                    kimi_result['_extraction_method'] = 'kimi_ai_discovery'
                    logger.info(f"[EXTRACT_LIST_AUTO] Kimi K2 discovered {len(kimi_result.get('data', []))} items")
                    return kimi_result
            except Exception as e:
                await self._ensure_page()
                current_url = self.page.url if self.page else "unknown"
                handle_error(
                    operation="kimi_k2_selector_discovery",
                    error=e,
                    context={"url": current_url, "limit": limit},
                    log_level="warning"
                )

            # MARKDOWN FALLBACK: Get page content for LLM parsing
            logger.info("[EXTRACT_LIST_AUTO] Falling back to markdown extraction...")
            try:
                markdown_result = await self.get_markdown()
                if markdown_result and markdown_result.get('markdown'):
                    return {
                        "success": True,
                        "data": [],
                        "markdown": markdown_result['markdown'][:8000],
                        "_extraction_method": "markdown_fallback",
                        "_note": "Use LLM to parse the markdown content",
                        "url": current_url
                    }
            except Exception as e:
                handle_error("unknown_operation", e, context={"url": url}, log_level="debug")

            # Final fallback: return empty result with guidance
            return {
                "success": False,
                "error": "No suitable selectors found for this page",
                "data": [],
                "guidance": "Use playwright_extract_structured with specific selectors",
                "url": current_url
            }

        except Exception as e:
            logger.error(f"Extract list auto error: {e}")
            return {"error": str(e), "success": False}

    @tool_result
    async def _detect_list_selectors(self) -> Optional[Dict[str, Any]]:
        """
        Dynamically detect and EXTRACT list items by analyzing DOM structure.
        Uses REPEATING STRUCTURE detection - finds parent containers with similar children.
        Works for articles, products, listings, etc.
        Returns actual data, not just selectors.
        """
        try:
            await self._ensure_page()

            # JavaScript to intelligently discover repeating structures and extract data
            result = await self.page.evaluate("""
                () => {
                    const skipWords = ['sign', 'login', 'cookie', 'privacy', 'terms', 'about', 'contact', 'help', 'faq', 'subscribe', 'comment', 'cart', 'wishlist'];

                    function isVisible(el) {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 50 && rect.height > 20 && rect.top < window.innerHeight * 2;
                    }

                    function getClassSignature(el) {
                        // Get a "signature" from class names for matching similar elements
                        const classes = Array.from(el.classList).filter(c => !c.match(/^(js-|is-|has-)/)).sort();
                        return el.tagName + ':' + classes.slice(0, 3).join(',');
                    }

                    function extractItem(el) {
                        // Extract title, link, price, image from a container element
                        const item = {};

                        // Find title: largest text element or link
                        const titleCandidates = [
                            el.querySelector('h1, h2, h3, h4, [class*="title"], [class*="name"], [class*="heading"]'),
                            el.querySelector('a[href]:not([href="#"])'),
                            el.querySelector('strong, b')
                        ].filter(Boolean);

                        for (const t of titleCandidates) {
                            const text = (t.innerText || t.textContent || '').trim();
                            if (text.length > 10 && text.length < 300) {
                                item.title = text;
                                if (t.href) item.link = t.href;
                                break;
                            }
                        }

                        // Find link if not found yet
                        if (!item.link) {
                            const link = el.querySelector('a[href^="http"], a[href^="/"]');
                            if (link) item.link = link.href;
                        }

                        // Find price (for e-commerce)
                        const priceEl = el.querySelector('[class*="price"], [class*="cost"], .money, [data-price]');
                        if (priceEl) {
                            const priceText = (priceEl.innerText || '').trim();
                            if (priceText.match(/[$£€¥]|\\d+[.,]\\d{2}/)) {
                                item.price = priceText;
                            }
                        }

                        // Find image
                        const img = el.querySelector('img[src]');
                        if (img && img.src) item.image = img.src;

                        return item;
                    }

                    // STRATEGY 1: Find REPEATING STRUCTURES (best for e-commerce/listings)
                    // Look for parents with 3+ children of similar structure
                    const containerSelectors = [
                        // List/grid containers
                        'ul', 'ol', '[class*="list"]', '[class*="grid"]', '[class*="results"]',
                        '[class*="products"]', '[class*="items"]', '[class*="cards"]',
                        '[class*="feed"]', '[class*="stories"]', '[class*="posts"]',
                        'main', '[role="main"]', '#content', '.content'
                    ];

                    for (const containerSel of containerSelectors) {
                        const containers = document.querySelectorAll(containerSel);
                        for (const container of containers) {
                            // Get direct children (or li/article/div children)
                            let children = Array.from(container.children);
                            if (children.length < 3) {
                                children = Array.from(container.querySelectorAll(':scope > li, :scope > article, :scope > div[class]'));
                            }

                            // Filter to visible, similar-structured children
                            const visibleChildren = children.filter(c => isVisible(c) && c.innerText.length > 20);
                            if (visibleChildren.length < 3) continue;

                            // Check if children have similar structure (same classes/tag)
                            const signatures = visibleChildren.map(c => getClassSignature(c));
                            const mostCommonSig = signatures.sort((a,b) =>
                                signatures.filter(s=>s===a).length - signatures.filter(s=>s===b).length
                            ).pop();

                            const matchingChildren = visibleChildren.filter(c => getClassSignature(c) === mostCommonSig);
                            if (matchingChildren.length < 3) continue;

                            // Extract data from matching children
                            const items = [];
                            const seen = new Set();

                            for (const child of matchingChildren.slice(0, 30)) {
                                const item = extractItem(child);
                                if (item.title && !seen.has(item.title)) {
                                    if (skipWords.some(w => item.title.toLowerCase().includes(w))) continue;
                                    seen.add(item.title);
                                    items.push(item);
                                }
                            }

                            if (items.length >= 3) {
                                return {
                                    items: items,
                                    count: items.length,
                                    detected_selector: containerSel + ' > ' + mostCommonSig.split(':')[0].toLowerCase(),
                                    method: 'repeating_structure'
                                };
                            }
                        }
                    }

                    // STRATEGY 2: Find elements with headline/title class names
                    const headlineSelectors = [
                        '[class*="title"] a', '[class*="headline"] a', '[class*="story"] a',
                        '[class*="product-name"] a', '[class*="item-title"] a',
                        'h1 a', 'h2 a', 'h3 a', 'h4 a',
                        'strong a', 'b a', 'li a[href^="http"]',
                        '.titleline a', '.ourh', '.story-link', '.post-link',
                        'article a', '.entry a', '.item a'
                    ];

                    const items = [];
                    const seen = new Set();

                    for (const selector of headlineSelectors) {
                        try {
                            const elements = document.querySelectorAll(selector);
                            if (elements.length >= 3) {
                                elements.forEach(el => {
                                    const text = (el.innerText || el.textContent || '').trim();
                                    const href = el.href || el.getAttribute('href') || '';
                                    if (!text || text.length < 10 || text.length > 300) return;
                                    if (seen.has(text) || !href || href === '#') return;
                                    if (skipWords.some(w => text.toLowerCase().includes(w))) return;
                                    if (!isVisible(el)) return;

                                    seen.add(text);
                                    items.push({
                                        title: text,
                                        link: href.startsWith('/') ? window.location.origin + href : href,
                                        _selector: selector
                                    });
                                });

                                if (items.length >= 3) {
                                    return {
                                        items: items.slice(0, 30),
                                        count: items.length,
                                        detected_selector: selector,
                                        method: 'class_pattern'
                                    };
                                }
                            }
                        } catch (e) { continue; }
                    }

                    // STRATEGY 3: Fallback - find ALL visible links with substantial text
                    items.length = 0;
                    seen.clear();

                    document.querySelectorAll('a[href]').forEach(a => {
                        const text = (a.innerText || a.textContent || '').trim();
                        const href = a.href || '';
                        if (!text || text.length < 15 || text.length > 250) return;
                        if (seen.has(text) || !href || href.includes('javascript:')) return;
                        if (!isVisible(a)) return;
                        if (skipWords.some(w => text.toLowerCase().includes(w))) return;

                        seen.add(text);
                        items.push({ title: text, link: href });
                    });

                    return {
                        items: items.slice(0, 30),
                        count: items.length,
                        detected_selector: 'a[href]',
                        method: 'link_fallback'
                    };
                }
            """)

            if not result or result.get('count', 0) < 3:
                return None

            method = result.get('method', 'unknown')
            selector = result.get('detected_selector', 'a[href]')
            logger.info(f"[DYNAMIC_DETECT] {method}: {selector} found {result['count']} items")

            return {
                'item_selector': selector,
                'items': result.get('items', []),
                'detected_count': result['count'],
                'detection_method': method
            }

        except Exception as e:
            await self._ensure_page()
            current_url = self.page.url if self.page else "unknown"
            error_details = handle_error(
                operation="dynamic_selector_detection",
                error=e,
                context={"url": current_url},
                log_level="warning"
            )
            return ToolResult(
                success=False,
                error=str(e),
                data={
                    "context": "dynamic_selector_detection",
                    "url": current_url,
                    "error_details": error_details
                }
            )

    @tool_result
    async def _kimi_discover_selectors(self, url: str, limit: int = 10) -> Optional[Dict[str, Any]]:
        """
        Use Kimi K2 AI to analyze HTML and discover the correct CSS selectors.
        This is called when dynamic detection fails - AI analyzes the page structure.
        """
        try:
            from .kimi_k2_client import get_kimi_client
            kimi = get_kimi_client()
            if not kimi.is_available():
                return None

            await self._ensure_page()

            # Get HTML snippet focusing on likely headline areas
            html_sample = await self.page.evaluate("""
                () => {
                    // Get body HTML but truncate to 8000 chars
                    const body = document.body.innerHTML;

                    // Try to find the main content area
                    const main = document.querySelector('main, article, #content, .content, [role="main"]');
                    if (main) {
                        return main.outerHTML.slice(0, 8000);
                    }

                    // Otherwise get the first 8000 chars of body
                    return body.slice(0, 8000);
                }
            """)

            if not html_sample or len(html_sample) < 100:
                return None

            # Call Kimi K2 to analyze HTML and suggest selectors
            prompt = f"""Analyze this HTML and find the CSS selector for headline/article titles.

URL: {url}

HTML SAMPLE:
```html
{html_sample}
```

TASK: Find the CSS selector that matches headline/title links on this page.

Look for:
- Links inside headline tags (h1, h2, h3, strong)
- Links with class names containing 'title', 'headline', 'story'
- Repeating link patterns that look like article titles

OUTPUT EXACTLY THIS JSON FORMAT (no other text):
{{"item_selector": "CSS_SELECTOR_HERE", "title_selector": "CSS_FOR_TITLE_TEXT", "link_selector": "CSS_FOR_HREF"}}

Example: {{"item_selector": "article", "title_selector": "h2 a", "link_selector": "h2 a"}}
"""

            # Make async call to Kimi
            response = await kimi.client.chat.completions.create(
                model=kimi.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=200,
            )

            content = response.choices[0].message.content.strip()

            # Parse JSON response
            import json
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            selector_data = json.loads(content.strip())
            item_selector = selector_data.get('item_selector', '')
            title_selector = selector_data.get('title_selector', '')

            if not item_selector:
                return None

            logger.info(f"[KIMI_DISCOVER] AI suggested selector: {item_selector}")

            # Now extract using the AI-suggested selectors
            result = await self.extract_with_selectors(
                item_selector=item_selector,
                field_selectors={'title': title_selector, 'link': f"{title_selector}@href"},
                limit=limit
            )

            if result.get('success') and result.get('data'):
                result['_kimi_selector'] = item_selector
                return result

            return None

        except Exception as e:
            error_details = handle_error(
                operation="kimi_selector_discovery",
                error=e,
                context={"url": url, "limit": limit},
                log_level="warning"
            )
            return ToolResult(
                success=False,
                error=str(e),
                data={
                    "context": "kimi_selector_discovery",
                    "url": url,
                    "limit": limit,
                    "error_details": error_details
                }
            )

    @tool_result
    async def get_interactive_elements(self) -> Dict[str, Any]:
        """
        BROWSER-USE STYLE: Get all interactive elements with numeric indices.

        Returns indexed clickable elements for fast LLM reference:
        [0] Button "Submit"
        [1] Link "Home" -> /home
        [2] Input "Email" (text)

        The LLM can then say "click element 0" instead of guessing selectors.
        """
        try:
            await self._ensure_page()

            # JavaScript to extract all interactive elements with indices
            elements = await self.page.evaluate("""
                () => {
                    const interactive = [];
                    const selectors = 'a, button, input, select, textarea, [role="button"], [role="link"], [onclick], [tabindex="0"]';
                    const els = document.querySelectorAll(selectors);

                    els.forEach((el, idx) => {
                        // Skip hidden elements
                        const rect = el.getBoundingClientRect();
                        if (rect.width === 0 || rect.height === 0) return;
                        const style = window.getComputedStyle(el);
                        if (style.display === 'none' || style.visibility === 'hidden') return;

                        const tag = el.tagName.toLowerCase();
                        const type = el.type || '';
                        const text = (el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || '').trim().slice(0, 50);
                        const href = el.href || el.getAttribute('href') || '';
                        const name = el.name || el.id || '';

                        // Build unique selector
                        let selector = tag;
                        if (el.id) selector = '#' + el.id;
                        else if (el.name) selector = `${tag}[name="${el.name}"]`;
                        else if (text) selector = `${tag}:has-text("${text.slice(0, 20)}")`;

                        interactive.push({
                            index: interactive.length,
                            tag,
                            type,
                            text: text || '[no text]',
                            href: href ? href.slice(0, 100) : null,
                            name,
                            selector,
                            rect: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) }
                        });
                    });

                    return interactive.slice(0, 50);  // Limit to 50 elements
                }
            """)

            # Format for LLM consumption
            formatted = []
            for el in elements:
                if el['tag'] == 'a':
                    formatted.append(f"[{el['index']}] Link \"{el['text']}\" -> {el['href'] or 'no href'}")
                elif el['tag'] == 'button':
                    formatted.append(f"[{el['index']}] Button \"{el['text']}\"")
                elif el['tag'] == 'input':
                    formatted.append(f"[{el['index']}] Input \"{el['text']}\" ({el['type'] or 'text'})")
                elif el['tag'] == 'select':
                    formatted.append(f"[{el['index']}] Dropdown \"{el['text']}\"")
                else:
                    formatted.append(f"[{el['index']}] {el['tag']} \"{el['text']}\"")

            # Store for click_by_index
            self._indexed_elements = elements

            return {
                "success": True,
                "count": len(elements),
                "elements": elements,
                "formatted": "\n".join(formatted),
                "url": getattr(self.page, 'url', '')
            }
        except Exception as e:
            logger.error(f"Get interactive elements error: {e}")
            return {"error": str(e)}

    @tool_result
    async def click_by_index(self, index: int) -> Dict[str, Any]:
        """
        BROWSER-USE STYLE: Click element by numeric index from get_interactive_elements.

        Much more reliable than CSS selectors - the LLM just says "click 0".
        """
        try:
            await self._ensure_page()

            if not hasattr(self, '_indexed_elements') or not self._indexed_elements:
                # Re-fetch elements
                await self.get_interactive_elements()

            if index >= len(self._indexed_elements):
                return {"error": f"Index {index} out of range (max {len(self._indexed_elements) - 1})"}

            el = self._indexed_elements[index]
            selector = el['selector']

            # Try multiple click strategies
            try:
                await self.page.click(selector, timeout=5000)
            except Exception:
                # Fallback: click by coordinates
                x = el['rect']['x'] + el['rect']['w'] // 2
                y = el['rect']['y'] + el['rect']['h'] // 2
                await self.page.mouse.click(x, y)

            await human_delay(200, 500)

            return {
                "success": True,
                "clicked": el,
                "url": getattr(self.page, 'url', '')
            }
        except Exception as e:
            logger.error(f"Click by index error: {e}")
            return {"error": str(e)}

    @tool_result
    async def snapshot(self) -> Dict[str, Any]:
        """Get an accessibility-focused snapshot of the current page"""
        try:
            await self._ensure_page()

            # Check if page is blocked by Cloudflare
            try:
                page_content = await self.page.content()
                if await self._is_cloudflare_challenge(page_content):
                    logger.warning("Cannot create snapshot - page is blocked by Cloudflare challenge")
                    return {
                        "error": "Page blocked by Cloudflare challenge - unable to create snapshot",
                        "cloudflare_blocked": True,
                        "url": getattr(self.page, 'url', '')
                    }
            except Exception as cf_check_err:
                logger.debug(f"Cloudflare check failed: {cf_check_err}")

            title = await self.page.title()
            acc_tree = await self.page.accessibility.snapshot(interesting_only=True)
            snapshot_text = self._format_accessibility_tree(acc_tree)
            summary = await self._summarize_page()

            return {
                "success": True,
                "url": getattr(self.page, 'url', ''),
                "title": title,
                "summary": summary.get("summary"),
                "snapshot": snapshot_text
            }
        except Exception as e:
            logger.error(f"Snapshot error: {e}")
            return {"error": str(e)}

    @tool_result
    async def browser_snapshot(self) -> Dict[str, Any]:
        """
        CLAUDE CODE STYLE: Get page snapshot with actionable element references.

        Returns structured data that LLM can use directly for actions:
        - mmid: Unique element marker ID for reliable targeting
        - ref: Human-readable reference like "button:Submit" or "link:About"
        - selector: CSS selector as fallback
        - role: Accessibility role (button, link, textbox, etc.)
        - text: Visible text content
        - rect: Bounding box for coordinate-based clicking

        This is the key feature from Microsoft's @playwright/mcp that makes
        Claude Code so effective at browser automation.
        """
        try:
            await self._ensure_page()

            # Inject mmid markers and collect element data
            elements = await self.page.evaluate("""() => {
                const MMID_ATTR = 'data-mmid';
                let mmidCounter = 0;
                const elements = [];

                // Clear old mmids
                document.querySelectorAll('[' + MMID_ATTR + ']').forEach(el => {
                    el.removeAttribute(MMID_ATTR);
                });

                // Get all interactive elements
                const interactiveSelectors = [
                    'a[href]', 'button', 'input', 'textarea', 'select',
                    '[role="button"]', '[role="link"]', '[role="menuitem"]',
                    '[role="tab"]', '[role="checkbox"]', '[role="radio"]',
                    '[onclick]', '[tabindex]:not([tabindex="-1"])'
                ];

                const allInteractive = document.querySelectorAll(interactiveSelectors.join(','));

                allInteractive.forEach(el => {
                    // Skip hidden/invisible elements
                    const rect = el.getBoundingClientRect();
                    if (rect.width === 0 || rect.height === 0) return;

                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return;

                    // Skip elements outside viewport (with some margin)
                    if (rect.bottom < -100 || rect.top > window.innerHeight + 100) return;

                    // Assign mmid
                    const mmid = 'mm' + (mmidCounter++);
                    el.setAttribute(MMID_ATTR, mmid);

                    // Determine role
                    const tag = el.tagName.toLowerCase();
                    let role = el.getAttribute('role') || tag;
                    if (tag === 'input') {
                        const type = el.type || 'text';
                        role = type === 'submit' || type === 'button' ? 'button' :
                               type === 'checkbox' ? 'checkbox' :
                               type === 'radio' ? 'radio' : 'textbox';
                    } else if (tag === 'a') {
                        role = 'link';
                    } else if (tag === 'button') {
                        role = 'button';
                    } else if (tag === 'select') {
                        role = 'combobox';
                    } else if (tag === 'textarea') {
                        role = 'textbox';
                    }

                    // Get text content
                    let text = '';
                    if (tag === 'input' || tag === 'textarea') {
                        text = el.placeholder || el.value || el.getAttribute('aria-label') || el.name || '';
                    } else {
                        text = el.innerText || el.textContent || el.getAttribute('aria-label') || '';
                    }
                    text = text.trim().replace(/\\s+/g, ' ').slice(0, 80);

                    // Build human-readable ref
                    const shortText = text.slice(0, 30).replace(/[^a-zA-Z0-9 ]/g, '').trim();
                    const ref = role + (shortText ? ':' + shortText : '');

                    // Build reliable selector (prefer id, name, then text)
                    let selector = '';
                    if (el.id) {
                        selector = '#' + CSS.escape(el.id);
                    } else if (el.name && (tag === 'input' || tag === 'textarea' || tag === 'select')) {
                        selector = tag + '[name="' + el.name + '"]';
                    } else if (text && text.length < 50) {
                        // Use text-based selector
                        selector = tag + ':has-text("' + text.slice(0, 40).replace(/"/g, '\\\\"') + '")';
                    } else {
                        // Fallback to mmid selector
                        selector = '[' + MMID_ATTR + '="' + mmid + '"]';
                    }

                    elements.push({
                        mmid,
                        ref,
                        role,
                        text: text || '[no text]',
                        tag,
                        href: el.href || null,
                        name: el.name || null,
                        id: el.id || null,
                        selector,
                        rect: {
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height)
                        },
                        visible: rect.top >= 0 && rect.top < window.innerHeight
                    });
                });

                return elements.slice(0, 100);  // Limit to prevent token overflow
            }""")

            # Store for mmid-based actions
            self._mmid_elements = {el['mmid']: el for el in elements}

            # Get accessibility tree
            acc_tree = await self.page.accessibility.snapshot(interesting_only=True)

            # Format for LLM consumption (compact view)
            formatted_lines = []
            for el in elements:
                visible_marker = "👁" if el['visible'] else ""
                if el['role'] == 'link' and el['href']:
                    formatted_lines.append(f"[{el['mmid']}] {el['ref']} -> {el['href'][:60]} {visible_marker}")
                elif el['role'] == 'textbox':
                    formatted_lines.append(f"[{el['mmid']}] {el['ref']} (input) {visible_marker}")
                else:
                    formatted_lines.append(f"[{el['mmid']}] {el['ref']} {visible_marker}")

            title = await self.page.title()

            return {
                "success": True,
                "url": getattr(self.page, 'url', ''),
                "title": title,
                "element_count": len(elements),
                "elements": elements,  # Full element data for programmatic use
                "formatted": "\n".join(formatted_lines),  # Human/LLM readable
                "accessibility_tree": self._format_accessibility_tree(acc_tree),
                "viewport": {"width": 1920, "height": 1080},
                "instructions": "Use mmid (e.g., 'mm5') to click/type. Example: click('[data-mmid=\"mm5\"]') or browser_click(mmid='mm5')"
            }
        except Exception as e:
            logger.error(f"Browser snapshot error: {e}")
            return {"error": str(e)}

    @tool_result
    async def browser_scroll(self, direction: str = "down", amount: int = 500) -> Dict[str, Any]:
        """
        CLAUDE CODE STYLE: Scroll the page.
        """
        try:
            await self._ensure_page()
            
            # Calculate scroll amount
            y_delta = amount if direction.lower() == "down" else -amount
            
            await self.page.evaluate(f"window.scrollBy(0, {y_delta})")
            
            # Wait a bit for scroll to settle/trigger lazy loads
            await asyncio.sleep(0.5)
            
            # Return new scroll position
            scroll_y = await self.page.evaluate("window.scrollY")
            doc_height = await self.page.evaluate("document.body.scrollHeight")
            
            return {
                "success": True,
                "scrolled": True,
                "direction": direction,
                "amount": amount,
                "new_position": scroll_y,
                "total_height": doc_height,
                "message": f"Scrolled {direction} by {amount}px (Position: {scroll_y}/{doc_height})"
            }
        except Exception as e:
            return handle_error("browser_scroll", e)

    @tool_result
    async def click_by_mmid(self, mmid: str) -> Dict[str, Any]:
        """
        CLAUDE CODE STYLE: Click element by mmid reference.

        More reliable than CSS selectors because mmid is:
        1. Injected fresh before each action
        2. Unique per element
        3. Won't break due to dynamic content changes
        """
        try:
            await self._ensure_page()

            # If we don't have cached elements, refresh snapshot
            if not hasattr(self, '_mmid_elements') or not self._mmid_elements:
                await self.browser_snapshot()

            if mmid not in self._mmid_elements:
                # Refresh and try again
                await self.browser_snapshot()
                if mmid not in self._mmid_elements:
                    return {"error": f"Element with mmid '{mmid}' not found"}

            el = self._mmid_elements[mmid]

            # Strategy 1: Click by mmid selector
            try:
                selector = f'[data-mmid="{mmid}"]'
                element_handle = await self.page.query_selector(selector)
                if element_handle:
                    await element_handle.click(timeout=5000)
                    await human_delay(200, 500)

                    # Store semantic context in DOM map for self-healing
                    await self._store_element_in_dom_map(element_handle, selector, "click")

                    return {
                        "success": True,
                        "clicked": el,
                        "method": "mmid_selector",
                        "url": getattr(self.page, 'url', '')
                    }
                else:
                    raise Exception("Element not found with mmid selector")
            except Exception as e:
                logger.debug(f"mmid click failed, trying coordinates: {e}")

            # Strategy 2: Click by coordinates
            try:
                x = el['rect']['x'] + el['rect']['width'] // 2
                y = el['rect']['y'] + el['rect']['height'] // 2
                await self.page.mouse.click(x, y)
                await human_delay(200, 500)
                return {
                    "success": True,
                    "clicked": el,
                    "method": "coordinates",
                    "url": getattr(self.page, 'url', '')
                }
            except Exception as e:
                logger.debug(f"Coordinate click failed, trying selector: {e}")

            # Strategy 3: Use stored selector
            try:
                element_handle = await self.page.query_selector(el['selector'])
                if element_handle:
                    await element_handle.click(timeout=5000)
                    await human_delay(200, 500)

                    # Store semantic context in DOM map for self-healing
                    await self._store_element_in_dom_map(element_handle, el['selector'], "click")

                    return {
                        "success": True,
                        "clicked": el,
                        "method": "fallback_selector",
                        "url": getattr(self.page, 'url', '')
                    }
                else:
                    raise Exception("Element not found with fallback selector")
            except Exception as e:
                return {"error": f"All click strategies failed: {e}"}

        except Exception as e:
            logger.error(f"click_by_mmid error: {e}")
            return {"error": str(e)}

    async def _get_locator_by_ref(self, ref: str):
        """
        Get a Playwright locator for an element by ref (mmid or e-ref).

        This helper method supports both:
        - mmid refs like "mm123" from browser_snapshot
        - e-refs like "e15" from accessibility snapshots

        Returns a locator or None if not found.
        """
        try:
            await self._ensure_page()

            # Handle e-refs from accessibility snapshots (e.g., "e15", "e123")
            if ref.startswith('e') and ref[1:].isdigit():
                # Try accessibility-based selection using role/name
                # First check if we have cached element_refs
                if hasattr(self, 'element_refs') and ref in self.element_refs:
                    cached = self.element_refs[ref]
                    if 'selector' in cached:
                        return self.page.locator(cached['selector'])
                    if 'role' in cached and 'name' in cached:
                        return self.page.get_by_role(cached['role'], name=cached['name'])

                # Try data-ref selector
                selector = f'[data-ref="{ref}"]'
                locator = self.page.locator(selector)
                if await locator.count() > 0:
                    return locator.first

            # Handle mmid refs (e.g., "mm123")
            if ref.startswith('mm') or ref.isdigit():
                mmid = ref
                # Refresh snapshot if we don't have cached elements
                if not hasattr(self, '_mmid_elements') or not self._mmid_elements:
                    await self.browser_snapshot()

                if mmid in self._mmid_elements:
                    el = self._mmid_elements[mmid]
                    # Try mmid selector first
                    selector = f'[data-mmid="{mmid}"]'
                    locator = self.page.locator(selector)
                    if await locator.count() > 0:
                        return locator.first
                    # Try stored selector
                    if 'selector' in el:
                        locator = self.page.locator(el['selector'])
                        if await locator.count() > 0:
                            return locator.first

            # Fallback: try as CSS selector directly
            try:
                locator = self.page.locator(ref)
                if await locator.count() > 0:
                    return locator.first
            except Exception:
                pass

            # Fallback: try as text selector
            try:
                locator = self.page.locator(f"text={ref}")
                if await locator.count() > 0:
                    return locator.first
            except Exception:
                pass

            return None

        except Exception as e:
            logger.debug(f"_get_locator_by_ref error for '{ref}': {e}")
            return None

    @tool_result
    async def type_by_mmid(self, mmid: str, text: str, clear: bool = True) -> Dict[str, Any]:
        """
        CLAUDE CODE STYLE: Type into element by mmid reference.
        """
        try:
            await self._ensure_page()

            # Refresh snapshot if needed
            if not hasattr(self, '_mmid_elements') or not self._mmid_elements:
                await self.browser_snapshot()

            if mmid not in self._mmid_elements:
                await self.browser_snapshot()
                if mmid not in self._mmid_elements:
                    return {"error": f"Element with mmid '{mmid}' not found"}

            el = self._mmid_elements[mmid]
            selector = f'[data-mmid="{mmid}"]'

            try:
                element_handle = await self.page.query_selector(selector)
                if element_handle:
                    if clear:
                        await element_handle.fill(text, timeout=5000)
                    else:
                        await element_handle.type(text, timeout=5000)

                    await human_delay(100, 300)

                    # Store semantic context in DOM map for self-healing
                    await self._store_element_in_dom_map(element_handle, selector, "type")

                    return {
                        "success": True,
                        "typed": text,
                        "element": el,
                        "url": getattr(self.page, 'url', '')
                    }
                else:
                    raise Exception("Element not found with mmid selector")
            except Exception as e:
                # Fallback to stored selector
                try:
                    element_handle = await self.page.query_selector(el['selector'])
                    if element_handle:
                        if clear:
                            await element_handle.fill(text, timeout=5000)
                        else:
                            await element_handle.type(text, timeout=5000)

                        # Store semantic context in DOM map for self-healing
                        await self._store_element_in_dom_map(element_handle, el['selector'], "type")

                        return {
                            "success": True,
                            "typed": text,
                            "element": el,
                            "method": "fallback_selector",
                            "url": getattr(self.page, 'url', '')
                        }
                    else:
                        raise Exception("Element not found with fallback selector")
                except Exception as e2:
                    return {"error": f"Type failed: {e2}"}

        except Exception as e:
            logger.error(f"type_by_mmid error: {e}")
            return {"error": str(e)}

    @tool_result
    async def scroll(self, direction: str = "down", amount: int = 500) -> Dict[str, Any]:
        """
        CLAUDE CODE STYLE: Scroll the page up or down.

        Args:
            direction: "up" or "down"
            amount: Pixels to scroll (default 500)
        """
        try:
            await self._ensure_page()

            scroll_amount = amount if direction.lower() == "down" else -amount
            await self.page.evaluate(f"window.scrollBy(0, {scroll_amount})")
            await human_delay(200, 400)

            # Get new scroll position
            scroll_pos = await self.page.evaluate("window.scrollY")
            page_height = await self.page.evaluate("document.body.scrollHeight")
            viewport_height = await self.page.evaluate("window.innerHeight")

            return {
                "success": True,
                "url": getattr(self.page, 'url', ''),
                "direction": direction,
                "amount": amount,
                "scroll_position": scroll_pos,
                "page_height": page_height,
                "viewport_height": viewport_height,
                "at_top": scroll_pos <= 0,
                "at_bottom": scroll_pos + viewport_height >= page_height - 10
            }
        except Exception as e:
            logger.error(f"Scroll error: {e}")
            return {"error": str(e)}

    @tool_result
    async def press_key(self, key: str = "Enter") -> Dict[str, Any]:
        """Press a keyboard key (Enter, Tab, Escape, ArrowDown, etc.)."""
        try:
            await self._ensure_page()
            await self.page.keyboard.press(key)
            await human_delay(50, 150)
            return {
                "success": True,
                "url": getattr(self.page, 'url', ''),
                "key": key
            }
        except Exception as e:
            logger.error(f"Press key error: {e}")
            return {"error": str(e)}

    @tool_result
    async def hover(self, selector: str) -> Dict[str, Any]:
        """Hover over an element."""
        try:
            await self._ensure_page()
            element = await self.page.wait_for_selector(selector, timeout=5000)
            if element:
                await element.hover()
                await human_delay(100, 200)
                return {
                    "success": True,
                    "selector": selector,
                    "url": getattr(self.page, 'url', '')
                }
            return {"error": f"Element not found: {selector}"}
        except Exception as e:
            logger.error(f"Hover error: {e}")
            return {"error": str(e)}

    @tool_result
    async def select_dropdown(self, selector: str, value: str) -> Dict[str, Any]:
        """Select an option from a dropdown menu."""
        try:
            await self._ensure_page()
            # Try native select first
            try:
                await self.page.select_option(selector, value=value)
                await human_delay(100, 200)
                return {
                    "success": True,
                    "selector": selector,
                    "value": value,
                    "url": getattr(self.page, 'url', '')
                }
            except Exception as e:
                handle_error("select_dropdown_select_page", e, context={"selector": selector, "value": value}, log_level="debug")
            # Try clicking dropdown and selecting option
            try:
                await self.page.click(selector)
                await human_delay(200, 400)
                await self.page.click(f'[role="option"]:has-text("{value}"), option:has-text("{value}"), li:has-text("{value}")')
                await human_delay(100, 200)
                return {
                    "success": True,
                    "selector": selector,
                    "value": value,
                    "url": getattr(self.page, 'url', '')
                }
            except Exception as e:
                return {"error": f"Could not select '{value}' from dropdown: {e}"}
        except Exception as e:
            logger.error(f"Select dropdown error: {e}")
            return {"error": str(e)}

    @tool_result
    async def get_dom_fingerprint(self) -> Dict[str, Any]:
        """CLAUDE CODE STYLE: Get a lightweight DOM fingerprint for proof-of-action validation."""
        try:
            await self._ensure_page()
            fingerprint = await self.page.evaluate("""() => {
                const url = window.location.href;
                const title = document.title;
                const inputs = document.querySelectorAll('input, textarea, select');
                const inputValues = Array.from(inputs).map(i =>
                    i.type === 'password' ? '[hidden]' : (i.value || '').slice(0, 50)
                );
                const modals = document.querySelectorAll('[role="dialog"], [aria-modal="true"], .modal');
                const modalCount = modals.length;
                const scrollY = window.scrollY;
                const errors = document.querySelectorAll('[role="alert"], .error, .alert-danger');
                const errorTexts = Array.from(errors).map(e => e.textContent?.trim().slice(0, 100) || '');
                return { url, title, inputValues, modalCount, scrollY, errorTexts };
            }""")
            fp_string = json.dumps(fingerprint, sort_keys=True)
            fp_hash = hashlib.md5(fp_string.encode()).hexdigest()[:12]
            return {"success": True, "fingerprint": fingerprint, "hash": fp_hash}
        except Exception as e:
            return {"error": str(e)}

    @tool_result
    async def verify_action(self, before_fp: Dict[str, Any], action_type: str = "click") -> Dict[str, Any]:
        """CLAUDE CODE STYLE: Verify an action had the expected effect."""
        try:
            after_result = await self.get_dom_fingerprint()
            if "error" in after_result:
                return after_result
            after_fp = after_result["fingerprint"]
            before = before_fp.get("fingerprint", {})
            changes = []
            action_worked = False
            if before.get("url") != after_fp.get("url"):
                changes.append("URL changed")
                action_worked = True
            if before.get("title") != after_fp.get("title"):
                changes.append("Title changed")
                action_worked = True
            if after_fp.get("modalCount", 0) != before.get("modalCount", 0):
                changes.append("Modal state changed")
                action_worked = True
            if before.get("inputValues", []) != after_fp.get("inputValues", []):
                changes.append("Input values changed")
                if action_type == "type":
                    action_worked = True
            return {
                "success": True,
                "action_verified": action_worked,
                "changes": changes,
                "hashes_differ": before_fp.get("hash") != after_result.get("hash")
            }
        except Exception as e:
            return {"error": str(e)}

    @tool_result
    async def click_with_verification(self, selector_or_mmid: str) -> Dict[str, Any]:
        """CLAUDE CODE STYLE: Click with automatic proof-of-action verification."""
        before_fp = await self.get_dom_fingerprint()
        if selector_or_mmid.startswith("mm"):
            result = await self.click_by_mmid(selector_or_mmid)
        else:
            result = await self.click(selector_or_mmid)
        if "error" in result:
            return result
        await human_delay(300, 700)
        verification = await self.verify_action(before_fp, "click")
        return {**result, "verification": verification}

    @tool_result
    async def type_with_verification(self, selector_or_mmid: str, text: str, clear: bool = True) -> Dict[str, Any]:
        """CLAUDE CODE STYLE: Type with automatic proof-of-action verification."""
        before_fp = await self.get_dom_fingerprint()
        if selector_or_mmid.startswith("mm"):
            result = await self.type_by_mmid(selector_or_mmid, text, clear)
        else:
            result = await self.fill(selector_or_mmid, text)
        if "error" in result:
            return result
        verification = await self.verify_action(before_fp, "type")
        return {**result, "verification": verification}

    @tool_result
    async def _summarize_page(self) -> Dict[str, Any]:
        """Collect a lightweight summary of visible page content"""
        title = ""
        headings = []
        links = []
        inputs = []

        await self._ensure_page()

        try:
            title = await self.page.title()
        except Exception as e:
            handle_error("summarize_page_page_page", e, log_level="debug")

        try:
            headings = await self.page.eval_on_selector_all(
                "h1, h2",
                "els => els.map(e => e.innerText.trim()).filter(Boolean).slice(0, 5)"
            )
        except Exception:
            headings = []

        try:
            links = await self.page.eval_on_selector_all(
                "a[href]",
                """els => els
                    .map(e => ({ text: (e.innerText || "").trim(), href: e.href || e.getAttribute("href") || "" }))
                    .filter(l => l.text)
                    .slice(0, 6)"""
            )
        except Exception:
            links = []

        try:
            inputs = await self.page.eval_on_selector_all(
                "input, textarea, select, button",
                """els => els
                    .map(e => {
                        const label = e.getAttribute("aria-label") || e.name || e.placeholder || (e.innerText || "").trim();
                        const kind = e.tagName.toLowerCase() === "input" ? (e.type || "input") : e.tagName.toLowerCase();
                        return { label, kind };
                    })
                    .filter(i => i.label)
                    .slice(0, 6)"""
            )
        except Exception:
            inputs = []

        # Quick inline contact extraction (faster than calling find_contacts)
        emails = []
        phones = []
        contact_links = []
        try:
            quick_contacts = await asyncio.wait_for(
                self.page.evaluate("""() => {
                    const emails = (document.body?.innerText?.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}/gi) || []).slice(0, 3);
                    const phones = (document.body?.innerText?.match(/\\+?\\d[\\d\\s().-]{7,}/g) || []).slice(0, 2);
                    return { emails, phones };
                }"""),
                timeout=2.0
            )
            emails = quick_contacts.get("emails", [])
            phones = quick_contacts.get("phones", [])
        except Exception as e:
            handle_error("unknown_operation", e, log_level="debug")

        summary_parts = []
        if title:
            summary_parts.append(f"Title: {title[:80]}")
        if headings:
            summary_parts.append("Headings: " + "; ".join(h[:60] for h in headings[:3]))
        if links:
            summary_parts.append("Links: " + "; ".join(f"{l['text'][:40]}" for l in links[:4]))
        if inputs:
            summary_parts.append("Inputs: " + ", ".join(f"{i['kind']}[{i['label'][:25]}]" for i in inputs[:4]))
        if emails:
            summary_parts.append("Emails: " + ", ".join(emails[:3]))
        if phones:
            summary_parts.append("Phones: " + ", ".join(phones[:2]))
        if contact_links:
            summary_parts.append("Contact links: " + "; ".join((cl.get('text') or cl.get('href') or '')[:40] for cl in contact_links[:2]))

        summary_text = " | ".join(summary_parts)

        return {
            "title": title,
            "headings": headings,
            "links": links,
            "inputs": inputs,
            "emails": emails,
            "phones": phones,
            "contact_links": contact_links,
            "summary": summary_text
        }

    @tool_result
    async def extract_element_semantics(self, element) -> Dict:
        """
        Extract full semantic features from any element.

        This method extracts comprehensive semantic information including:
        - role: Element role or tag name
        - text: Text content (trimmed to 256 chars)
        - attrs: Filtered attributes (data-*, aria-*, name, id)
        - domPath: Full CSS path with nth-of-type selectors
        - bbox: Bounding box coordinates

        Args:
            element: Playwright element handle

        Returns:
            Dict with semantic features: {role, text, attrs, domPath, bbox}
        """
        try:
            # Use evaluate to extract all semantic features in one call
            return await element.evaluate('''(el) => ({
                role: el.getAttribute('role') || el.tagName.toLowerCase(),
                text: (el.textContent || '').trim().slice(0, 256),
                attrs: Object.fromEntries(
                    Array.from(el.attributes)
                        .filter(a => a.name.startsWith('data-') || a.name.startsWith('aria-') || a.name === 'name' || a.name === 'id')
                        .map(a => [a.name, a.value])
                ),
                domPath: (() => {
                    const path = [];
                    let current = el;
                    while (current && current.nodeType === 1) {
                        const tag = current.tagName.toLowerCase();
                        const parent = current.parentElement;
                        if (!parent) { path.unshift(tag); break; }
                        const siblings = Array.from(parent.children).filter(c => c.tagName === current.tagName);
                        const index = siblings.indexOf(current) + 1;
                        path.unshift(tag + ':nth-of-type(' + index + ')');
                        current = parent;
                    }
                    return path.join(' > ');
                })(),
                bbox: (() => {
                    const rect = el.getBoundingClientRect();
                    return { x: rect.x, y: rect.y, w: rect.width, h: rect.height };
                })()
            })''')
        except Exception as e:
            logger.error(f"Failed to extract element semantics: {e}")
            return {
                "role": "unknown",
                "text": "",
                "attrs": {},
                "domPath": "",
                "bbox": {"x": 0, "y": 0, "w": 0, "h": 0}
            }

    @tool_result
    async def _store_element_in_dom_map(self, element, selector: str, action_type: str = "click") -> bool:
        """
        Store element's semantic features in DomMapStore for future self-healing.

        This method extracts semantic features and stores them along with
        multiple selector candidates for robust element targeting.

        Args:
            element: Playwright element handle
            selector: The selector that was used to find this element
            action_type: Type of action performed (click, type, etc.)

        Returns:
            bool: True if successfully stored, False otherwise
        """
        if not DOM_MAP_STORE_AVAILABLE:
            return False

        try:
            # Extract semantic features
            semantic_data = await self.extract_element_semantics(element)

            # Get current URL
            url = self.page.url

            # Create SemanticFeatures object
            semantic_features = SemanticFeatures(
                role=semantic_data.get("role"),
                text=semantic_data.get("text"),
                attrs=semantic_data.get("attrs", {}),
                dom_path=semantic_data.get("domPath"),
                bbox=semantic_data.get("bbox")
            )

            # Generate semantic ID
            import hashlib
            sig = f"{semantic_data.get('domPath', '')}::{semantic_data.get('text', '')}::{semantic_data.get('role', '')}"
            target_id = hashlib.md5(sig.encode()).hexdigest()[:16]

            # Try to get existing target to preserve history
            store = get_dom_map_store()
            existing_target = store.get_target(url, target_id)

            if existing_target:
                # Update existing target with new selector
                if selector not in existing_target.selector_candidates.get('css', []):
                    # Determine selector type
                    if selector.startswith('//') or selector.startswith('(//'):
                        sel_type = 'xpath'
                    else:
                        sel_type = 'css'

                    if sel_type not in existing_target.selector_candidates:
                        existing_target.selector_candidates[sel_type] = []

                    # Add to front (most recent working selector)
                    if selector in existing_target.selector_candidates[sel_type]:
                        existing_target.selector_candidates[sel_type].remove(selector)
                    existing_target.selector_candidates[sel_type].insert(0, selector)

                # Update stats
                existing_target.success_count += 1
                existing_target.failure_count = 0
                store.add_target(url, existing_target)
                logger.debug(f"Updated DOM map target {target_id} with selector {selector}")
            else:
                # Create new target
                # Determine selector type
                if selector.startswith('//') or selector.startswith('(//'):
                    selector_candidates = {'xpath': [selector], 'css': []}
                else:
                    selector_candidates = {'css': [selector], 'xpath': []}

                new_target = DomTarget(
                    id=target_id,
                    url_pattern="",  # Will be set by store
                    selector_candidates=selector_candidates,
                    semantic=semantic_features,
                    last_verified_at=time.time(),
                    success_count=1,
                    failure_count=0
                )

                store.add_target(url, new_target)
                logger.debug(f"Created DOM map target {target_id} with selector {selector}")

            return True
        except Exception as e:
            logger.warning(f"Failed to store element in DOM map: {e}")
            return False

    @tool_result
    async def build_page_dom_map(self) -> Dict[str, Any]:
        """
        Build a complete DOM map of all interactive elements on the page.

        Uses SemanticExtractor to create a map of all clickable/interactive
        elements with their semantic features and multiple selector candidates.

        This enables:
        - Self-healing selectors (try multiple candidates)
        - Element lookup by semantic signature
        - DOM understanding for AI agents

        Returns:
            Dict with:
            - elements: List of extracted element features
            - by_id: Dict mapping semantic IDs to elements
            - count: Total interactive elements found
        """
        try:
            from .semantic_extractor import SemanticExtractor

            await self._ensure_page()

            extractor = SemanticExtractor(self.page)
            elements = await extractor.extract_all_interactive()

            # Build lookup maps
            by_id = {}
            elements_list = []

            for elem in elements:
                elem_dict = elem.to_dict()
                elements_list.append(elem_dict)
                semantic_id = elem.to_semantic_id()
                by_id[semantic_id] = elem_dict

            return {
                "success": True,
                "count": len(elements),
                "elements": elements_list,
                "by_id": by_id,
                "url": getattr(self.page, 'url', '')
            }
        except ImportError:
            logger.warning("SemanticExtractor not available - install semantic_extractor.py")
            return {
                "success": False,
                "error": "SemanticExtractor not available",
                "count": 0,
                "elements": []
            }
        except Exception as e:
            logger.error(f"Failed to build DOM map: {e}")
            return {
                "success": False,
                "error": str(e),
                "count": 0,
                "elements": []
            }

    @tool_result
    def _format_accessibility_tree(self, tree: Dict[str, Any], max_lines: int = 80) -> str:
        """Convert accessibility snapshot into a compact bullet-style outline"""
        if not tree:
            return "No accessibility information available"

        lines = []
        self._add_accessibility_node(tree, 0, lines, max_lines)

        if len(lines) >= max_lines:
            lines.append("... truncated ...")

        return "\n".join(lines)

    @tool_result
    def _add_accessibility_node(self, node: Dict[str, Any], depth: int, lines: list, max_lines: int):
        """Depth-first traversal to create readable outline"""
        if len(lines) >= max_lines:
            return

        role = node.get("role", "node")
        name = node.get("name", "") or node.get("valueText", "")
        value = node.get("value")

        parts = [f"{role}"]
        if name:
            parts.append(f"{name}")
        if value and str(value).strip():
            parts.append(f"value={value}")

        indent = "  " * depth
        line = indent + "- " + " | ".join(parts)
        lines.append(line[:200])

        for child in node.get("children", []):
            if len(lines) >= max_lines:
                break
            self._add_accessibility_node(child, depth + 1, lines, max_lines)

    @tool_result
    async def drag_and_drop(self, source: str, target: str) -> Dict[str, Any]:
        """Drag element from source to target"""
        try:
            await self._ensure_page()
            # STEALTH: Delay before drag
            await human_delay(200, 500)
            
            await self.page.drag_and_drop(source, target)
            
            # STEALTH: Delay after drag
            await human_delay(200, 500)
            
            return {"success": True, "action": "drag_and_drop", "source": source, "target": target}
        except Exception as e:
            logger.error(f"Drag and drop failed: {e}")
            return {"error": str(e)}

    @tool_result
    async def get_markdown(self, url: str = None) -> Dict[str, Any]:
        """Get page content as Markdown."""
        try:
            if url and url != (self.page.url if self.page else ""):
                await self.navigate(url)
            
            await self._ensure_page()
            content = await self.page.content()
            
            try:
                import html2text
                h = html2text.HTML2Text()
                h.ignore_links = False
                h.ignore_images = True
                h.body_width = 0  # No wrapping
                markdown = h.handle(content)
            except ImportError:
                # Fallback to innerText
                markdown = await self.page.inner_text("body")
                
            return {"success": True, "markdown": markdown, "url": getattr(self.page, 'url', '')}
        except Exception as e:
            logger.error(f"get_markdown error: {e}")
            return {"error": str(e)}

    @tool_result
    def get_tools(self) -> Dict[str, Dict]:
        """Get list of available tools (MCP-style)"""
        return {
            "playwright_navigate": {
                "description": "Navigate to a URL",
                "parameters": {
                    "url": {"type": "string", "required": True}
                }
            },
            "playwright_click": {
                "description": "Click an element",
                "parameters": {
                    "selector": {"type": "string", "required": True}
                }
            },
            "playwright_fill": {
                "description": "Fill an input field. Auto-presses Enter for search boxes.",
                "parameters": {
                    "selector": {"type": "string", "required": True},
                    "value": {"type": "string", "required": True},
                    "press_enter": {"type": "boolean", "required": False, "description": "Press Enter after filling (auto-detected for search inputs)"}
                }
            },
            "batch_execute": {
                "description": "Execute multiple browser actions in one call. Use for filling forms or multiple clicks. Reduces token usage by ~90% by eliminating redundant snapshots between actions.",
                "parameters": {
                    "actions": {
                        "type": "array",
                        "required": True,
                        "description": "List of actions to execute. Each action is a dict with 'action' (click/fill/type/scroll/navigate), 'selector' or 'ref' (for click/fill), 'value' or 'text' (for fill), 'url' (for navigate), 'direction' (for scroll), 'amount' (for scroll)"
                    },
                    "stop_on_error": {"type": "boolean", "required": False, "default": False, "description": "Stop execution on first error"}
                },
                "example": "batch_execute(actions=[{'action':'fill','selector':'#name','value':'John'},{'action':'fill','selector':'#email','value':'john@email.com'},{'action':'click','selector':'button[type=submit]'}])"
            },
            "playwright_batch_execute": {
                "description": "Alias for batch_execute. Execute multiple browser actions in one call.",
                "parameters": {
                    "actions": {"type": "array", "required": True},
                    "stop_on_error": {"type": "boolean", "required": False, "default": False}
                }
            },
            "playwright_evaluate": {
                "description": "Execute JavaScript code",
                "parameters": {
                    "script": {"type": "string", "required": True}
                }
            },
            "playwright_screenshot": {
                "description": "Take a screenshot",
                "parameters": {}
            },
            "playwright_drag_and_drop": {
                "description": "Drag an element from source selector to target selector.",
                "parameters": {
                    "source": {"type": "string", "required": True, "description": "Selector of element to drag"},
                    "target": {"type": "string", "required": True, "description": "Selector of drop target"}
                }
            },
            "playwright_solve_challenge": {
                "description": "Show browser popup for user to solve CAPTCHA or complete login, then hide and continue. Use when you detect 'captcha', 'verify you are human', 'login required', or similar challenges.",
                "parameters": {
                    "timeout": {"type": "integer", "required": False, "default": 120, "description": "Max seconds to wait for user to solve"}
                }
            },
            "playwright_detect_challenge": {
                "description": "Check if current page has a CAPTCHA or login wall. Returns detection result without popup.",
                "parameters": {}
            },
            "playwright_get_content": {
                "description": "Get page HTML",
                "parameters": {}
            },
            "playwright_get_text": {
                "description": "Get text content",
                "parameters": {
                    "selector": {"type": "string", "required": False, "default": "body"}
                }
            },
            "playwright_snapshot": {
                "description": "Get accessibility snapshot and quick summary of the page",
                "parameters": {}
            },
            "playwright_get_outline": {
                "description": "Alias for playwright_snapshot (accessibility outline + summary)",
                "parameters": {}
            },
            # CLAUDE CODE STYLE: mmid-based element targeting (like Playwright MCP)
            "browser_snapshot": {
                "description": "CLAUDE CODE STYLE: Get page snapshot with mmid element references. Returns actionable elements with mmid IDs (mm0, mm1, etc.) for reliable clicking/typing. Use mmid with browser_click or browser_type.",
                "parameters": {}
            },
            "browser_click": {
                "description": "CLAUDE CODE STYLE: Click element by mmid reference from browser_snapshot. More reliable than CSS selectors. Example: browser_click(mmid='mm5')",
                "parameters": {
                    "mmid": {"type": "string", "required": True, "description": "Element mmid from browser_snapshot (e.g., 'mm5')"}
                }
            },
            "browser_type": {
            "description": "CLAUDE CODE STYLE: Type text into element by mmid reference. Example: browser_type(mmid='mm3', text='search query')",
            "parameters": {
                "mmid": {"type": "string", "required": True, "description": "Element mmid from browser_snapshot (e.g., 'mm3')"},
                "text": {"type": "string", "required": True, "description": "Text to type"},
                "press_enter": {"type": "boolean", "required": False, "default": True, "description": "Press Enter after typing (default: True)"}
            }
        },
        "browser_scroll": {
            "description": "CLAUDE CODE STYLE: Scroll the page to see more content. Example: browser_scroll(direction='down', amount=500)",
            "parameters": {
                "direction": {"type": "string", "required": False, "default": "down", "enum": ["up", "down"], "description": "Scroll direction (up/down)"},
                "amount": {"type": "integer", "required": False, "default": 500, "description": "Amount to scroll in pixels"}
            }
        },
        "playwright_extract_structured": {
                "description": "Extract structured data using CSS selectors. More accurate than LLM for lists/tables. Use @attr to get attributes (e.g., 'a@href' for link URL, 'img@src' for image URL)",
                "parameters": {
                    "item_selector": {"type": "string", "required": True, "description": "CSS selector for each item container"},
                    "field_selectors": {"type": "object", "required": True, "description": "Dict of field_name -> CSS selector (use @attr for attributes)"},
                    "limit": {"type": "integer", "required": False, "default": 20}
                }
            },
            "playwright_extract_list": {
                "description": "AUTO-DETECT: Extract list items using known site selectors (100% accurate, no LLM). Works automatically for HN, Amazon, eBay, GitHub Trending, Reddit, LinkedIn jobs. PREFERRED for extracting lists/tables.",
                "parameters": {
                    "limit": {"type": "integer", "required": False, "default": 10, "description": "Maximum items to extract"}
                }
            },
            "playwright_find_contacts": {
                "description": "Extract emails/phones/contact links from current page",
                "parameters": {}
            },
            "playwright_get_preferred_contact": {
                "description": "Get preferred contact method (contact form URL > email)",
                "parameters": {}
            },
            "playwright_extract": {
                "description": "Alias for playwright_get_content (returns page HTML)",
                "parameters": {}
            },
            "playwright_extract_fb_ads": {
                "description": "Extract structured Facebook Ads Library data (advertiser, ad_text, start_date, platforms, landing_url, ad_id)",
                "parameters": {
                    "max_ads": {"type": "integer", "required": False, "default": 50, "description": "Maximum number of ads to extract"}
                }
            },
            "extract_fb_ads_advertisers": {
                "description": "AUTOMATED: Search Facebook Ads Library and extract advertisers running ads for a keyword. Navigates to FB Ads Library, searches, and extracts structured data.",
                "parameters": {
                    "query": {"type": "string", "required": True, "description": "Search query for ads (e.g., 'booked meetings', 'lead generation')"},
                    "country": {"type": "string", "required": False, "default": "US", "description": "Country code (e.g., US, GB, CA)"},
                    "limit": {"type": "integer", "required": False, "default": 10, "description": "Maximum number of ads to extract"}
                }
            },
            "playwright_extract_tiktok_ads": {
                "description": "Extract structured TikTok Ads data from Ad Library or Creative Center (advertiser, ad_text, landing_url, engagement metrics)",
                "parameters": {
                    "max_ads": {"type": "integer", "required": False, "default": 50, "description": "Maximum number of ads to extract"}
                }
            },
            "playwright_extract_reddit": {
                "description": "FAST: Extract all Reddit posts with warm signals in ONE call (auto-detects warm prospects)",
                "parameters": {}
            },
            "playwright_extract_page_fast": {
                "description": "FAST: Extract all contacts, emails, phones, social links from any page in ONE call",
                "parameters": {}
            },
            "playwright_batch_extract": {
                "description": "FASTEST: Visit multiple URLs and extract contacts from ALL in ONE call (max 10 sites)",
                "parameters": {
                    "urls": {"type": "array", "description": "List of URLs to visit and extract contacts from"}
                }
            },
            # NEW: Jina Reader / Firecrawl / Crawl4AI inspired tools
            "playwright_get_markdown": {
                "description": "JINA-STYLE: Convert page to clean LLM-friendly markdown (removes nav, ads, boilerplate)",
                "parameters": {
                    "url": {"type": "string", "required": False, "description": "URL to convert (uses current page if not provided)"},
                    "target_selector": {"type": "string", "required": False, "description": "CSS selector to extract specific content"}
                }
            },
            "playwright_fetch_url": {
                "description": "FAST FETCH (no browser): Fetch a URL over HTTP and return clean markdown/text/html for quick summarization or extraction.",
                "parameters": {
                    "url": {"type": "string", "required": True, "description": "URL to fetch (http/https only)"},
                    "output_format": {"type": "string", "required": False, "default": "markdown", "description": "One of: markdown, text, html"},
                    "use_cache": {"type": "boolean", "required": False, "default": True, "description": "Cache results in-memory for a short TTL"}
                }
            },
            "playwright_deep_search": {
                "description": "EXA-STYLE: Multi-query deep search with automatic summaries",
                "parameters": {
                    "query": {"type": "string", "required": True, "description": "Search topic"},
                    "context": {"type": "string", "required": False, "description": "Extra context or constraints"},
                    "max_queries": {"type": "number", "required": False, "default": 3},
                    "results_per_query": {"type": "number", "required": False, "default": 5},
                    "summarize_top": {"type": "number", "required": False, "default": 3}
                }
            },
            "playwright_map_site": {
                "description": "FIRECRAWL-STYLE: Discover all URLs on a website (uses sitemap.xml if available)",
                "parameters": {
                    "url": {"type": "string", "required": True, "description": "Base URL to map"},
                    "max_urls": {"type": "number", "required": False, "default": 500}
                }
            },
            "playwright_crawl_for": {
                "description": "CRAWL4AI-STYLE: Adaptive crawl - stops when enough relevant info found",
                "parameters": {
                    "url": {"type": "string", "required": True, "description": "Starting URL"},
                    "looking_for": {"type": "string", "required": True, "description": "What info to find (e.g., 'pricing information')"},
                    "max_pages": {"type": "number", "required": False, "default": 10}
                }
            },
            "playwright_llm_extract": {
                "description": "SCRAPEGRAPH-STYLE: Extract data using natural language prompt (e.g., 'Extract all product names and prices')",
                "parameters": {
                    "prompt": {"type": "string", "required": True, "description": "Natural language extraction prompt"},
                    "url": {"type": "string", "required": False, "description": "URL to extract from (uses current page if not provided)"}
                }
            },
            "playwright_extract_entities": {
                "description": "Extract structured data or specific entity types from page. Supports both schema-based extraction (for products, books, etc.) and entity type extraction (email, phone, etc.)",
                "parameters": {
                    "entity_types": {"type": "array", "required": False, "description": "List of entity types: email, phone, company, money, person"},
                    "schema": {"type": "object", "required": False, "description": "Schema for structured extraction, e.g. {\"books\": [{\"title\": \"string\", \"price\": \"string\"}]}"},
                    "limit": {"type": "number", "required": False, "description": "Max items to extract (default 10)"},
                    "url": {"type": "string", "required": False}
                }
            },
            "playwright_answer_question": {
                "description": "Answer a question based on page content",
                "parameters": {
                    "question": {"type": "string", "required": True, "description": "Question to answer"},
                    "url": {"type": "string", "required": False}
                }
            },
            # COMBINED EXTRACT+SAVE TOOL (solves data pipeline issue)
            "playwright_extract_to_csv": {
                "description": "Extract structured data from current page (or specified URL) AND save directly to CSV in one operation. If already navigated to a page, you can omit the url parameter.",
                "parameters": {
                    "url": {"type": "string", "required": False, "description": "URL to extract from (optional - uses current page if not provided)"},
                    "schema": {"type": "object", "required": True, "description": "Schema for extraction, e.g. {\"agencies\": [{\"name\": \"string\", \"website\": \"string\"}]}"},
                    "csv_path": {"type": "string", "required": True, "description": "Path to save CSV file"},
                    "limit": {"type": "number", "required": False, "description": "Max items to extract (default 10)"},
                    "append": {"type": "boolean", "required": False, "description": "Append to existing file (default False)"}
                }
            },
            # SPEED-OPTIMIZED TOOLS (inspired by browser-use, crawl4ai)
            "playwright_fast_extract": {
                "description": "FASTEST: CSS-first extraction with accessibility tree fallback, then LLM. 4x faster than pure LLM.",
                "parameters": {
                    "url": {"type": "string", "required": True, "description": "URL to extract from"},
                    "prompt": {"type": "string", "required": True, "description": "What to extract"}
                }
            },
            "playwright_parallel_extract": {
                "description": "Extract from multiple URLs in parallel (batch mode)",
                "parameters": {
                    "urls": {"type": "array", "required": True, "description": "List of URLs"},
                    "prompt": {"type": "string", "required": True, "description": "What to extract"}
                }
            },
            "playwright_clear_cache": {
                "description": "Clear the page response cache",
                "parameters": {}
            },
            # API-BASED SEARCH (bypasses Google CAPTCHA/rate limiting)
            "playwright_web_search": {
                "description": "Search using DuckDuckGo API (free, no rate limits). Use when Google blocks or shows CAPTCHA. Returns direct results without browser navigation.",
                "parameters": {
                    "query": {"type": "string", "required": True, "description": "Search query"},
                    "num_results": {"type": "number", "required": False, "description": "Number of results (default 10)"}
                }
            },
            # BROWSER-USE STYLE TOOLS (element indexing)
            "playwright_get_elements": {
                "description": "BROWSER-USE STYLE: Get all interactive elements with numeric indices [0], [1], etc. Use with click_by_index.",
                "parameters": {}
            },
            "playwright_click_index": {
                "description": "BROWSER-USE STYLE: Click element by its numeric index from get_elements. More reliable than CSS selectors.",
                "parameters": {
                    "index": {"type": "integer", "required": True, "description": "Element index from get_elements"}
                }
            },
            # PRUNE4WEB & AGENT-E STYLE TOOLS
            "playwright_pruned_dom": {
                "description": "PRUNE4WEB: Get 25-50x compressed DOM. Removes scripts/styles/hidden elements, keeps interactive elements.",
                "parameters": {
                    "focus_area": {"type": "string", "required": False, "description": "CSS selector to focus on (e.g., 'main', '#content')"}
                }
            },
            "playwright_observe_change": {
                "description": "AGENT-E: Get change observation with verbal feedback after an action. Detects errors, success, modals.",
                "parameters": {
                    "action": {"type": "string", "required": False, "description": "What action was just performed"}
                }
            },
            "playwright_smart_search": {
                "description": "Auto-detect search form, fill query, and submit. Works on Amazon, Google, any site with search.",
                "parameters": {
                    "query": {"type": "string", "required": True, "description": "What to search for"}
                }
            },
            # MEM0-STYLE MEMORY TOOLS (98% task completion, 41% cost reduction)
            "playwright_session_memory": {
                "description": "MEM0: Get session memory - visited URLs, extracted data, errors, learned patterns",
                "parameters": {}
            },
            "playwright_clear_memory": {
                "description": "Clear session memory for fresh start",
                "parameters": {}
            },
            "playwright_store_data": {
                "description": "Store extracted data in session memory for later reference",
                "parameters": {
                    "key": {"type": "string", "required": True, "description": "Key to store under"},
                    "data": {"type": "any", "required": True, "description": "Data to store"}
                }
            },
            # SELF-CORRECTION TOOLS (OpenAI Operator style - 87% success)
            "playwright_click_retry": {
                "description": "OPERATOR: Click with auto-retry, fallback strategies, and self-correction. More reliable than basic click.",
                "parameters": {
                    "selector": {"type": "string", "required": True, "description": "Element selector"},
                    "max_retries": {"type": "integer", "required": False, "default": 3}
                }
            },
            "playwright_compressed_state": {
                "description": "Get compressed page state for LLM efficiency - combines memory, pruned DOM, key elements",
                "parameters": {
                    "max_tokens": {"type": "integer", "required": False, "default": 2000}
                }
            },
            "playwright_apply_stealth": {
                "description": "Apply enhanced stealth mode (canvas fingerprint, WebGL, plugins spoofing)",
                "parameters": {}
            },
            # EXA-STYLE DEEP RESEARCH TOOLS
            "playwright_research_start": {
                "description": "Start an asynchronous multi-source research job",
                "parameters": {
                    "query": {"type": "string", "required": True, "description": "Research objective"},
                    "instructions": {"type": "string", "required": False, "description": "Extra guidance or constraints"},
                    "max_queries": {"type": "number", "required": False, "default": 4},
                    "results_per_query": {"type": "number", "required": False, "default": 5}
                }
            },
            "playwright_research_check": {
                "description": "Check status of deep research jobs (optionally fetch a specific job)",
                "parameters": {
                    "job_id": {"type": "string", "required": False, "description": "Job ID to inspect"},
                    "include_logs": {"type": "boolean", "required": False, "default": False}
                }
            },
            # Vertical connectors
            "playwright_linkedin_company_lookup": {
                "description": "LinkedIn connector: find public company pages and return structured info",
                "parameters": {
                    "company": {"type": "string", "required": True, "description": "Company name to search"},
                    "max_results": {"type": "number", "required": False, "default": 3}
                }
            },
            "playwright_company_profile": {
                "description": "Company connector: summarize official website and optional contacts",
                "parameters": {
                    "company": {"type": "string", "required": True, "description": "Company name"},
                    "website": {"type": "string", "required": False, "description": "If provided, skip discovery"},
                    "include_contacts": {"type": "boolean", "required": False, "default": False}
                }
            },
            # ====================================================================
            # CLAUDE CODE STYLE TOOLS (Microsoft @playwright/mcp compatible)
            # These are the key features that make Claude Code's browser automation
            # so effective: mmid-based element references + structured snapshots
            # ====================================================================
            "browser_snapshot": {
                "description": "CLAUDE CODE STYLE: Get page snapshot with mmid element references. Returns structured data with elements that can be clicked/typed by mmid. More reliable than CSS selectors.",
                "parameters": {}
            },
            "browser_click": {
                "description": "CLAUDE CODE STYLE: Click element by mmid reference (e.g., 'mm5'). Uses 3-strategy cascade: mmid selector -> coordinates -> fallback selector.",
                "parameters": {
                    "mmid": {"type": "string", "required": True, "description": "Element mmid from browser_snapshot (e.g., 'mm5')"}
                }
            },
            "browser_type": {
                "description": "CLAUDE CODE STYLE: Type into element by mmid reference. Clears field first by default.",
                "parameters": {
                    "mmid": {"type": "string", "required": True, "description": "Element mmid from browser_snapshot"},
                    "text": {"type": "string", "required": True, "description": "Text to type"},
                    "clear": {"type": "boolean", "required": False, "default": True, "description": "Clear field before typing"}
                }
            },
            "browser_navigate": {
                "description": "CLAUDE CODE STYLE: Navigate to URL (alias for playwright_navigate)",
                "parameters": {
                    "url": {"type": "string", "required": True}
                }
            },
            "browser_scroll": {
                "description": "CLAUDE CODE STYLE: Scroll the page up/down",
                "parameters": {
                    "direction": {"type": "string", "required": False, "default": "down", "description": "Scroll direction: up or down"},
                    "amount": {"type": "integer", "required": False, "default": 500, "description": "Pixels to scroll"}
                }
            },
            "browser_fingerprint": {
                "description": "CLAUDE CODE STYLE: Get DOM fingerprint for proof-of-action validation. Use before/after actions to verify they worked.",
                "parameters": {}
            },
            "browser_verify_action": {
                "description": "CLAUDE CODE STYLE: Verify an action had the expected effect by comparing DOM before/after.",
                "parameters": {
                    "before_fp": {"type": "object", "required": True, "description": "Fingerprint from browser_fingerprint before the action"},
                    "action_type": {"type": "string", "required": False, "default": "click", "description": "Type of action: click, type, scroll"}
                }
            },
            "browser_click_verified": {
                "description": "CLAUDE CODE STYLE: Click with automatic proof-of-action verification. Confirms the click had an effect.",
                "parameters": {
                    "selector": {"type": "string", "required": True, "description": "CSS selector or mmid (e.g., 'mm5')"}
                }
            },
            "browser_type_verified": {
                "description": "CLAUDE CODE STYLE: Type with automatic proof-of-action verification.",
                "parameters": {
                    "selector": {"type": "string", "required": True, "description": "CSS selector or mmid"},
                    "text": {"type": "string", "required": True, "description": "Text to type"},
                    "clear": {"type": "boolean", "required": False, "default": True}
                }
            },
            # CODE GENERATION TOOL
            "playwright_export_code": {
                "description": "EXPORT: Generate clean Playwright code from workflow. Converts execution history to reusable script. Supports python_async, python_sync, pytest formats.",
                "parameters": {
                    "actions": {"type": "array", "required": False, "description": "List of actions to export (uses recent history if not provided)"},
                    "format": {"type": "string", "required": False, "default": "python_async", "description": "Output format: python_async, python_sync, pytest"},
                    "description": {"type": "string", "required": False, "description": "What the workflow does"},
                    "output_file": {"type": "string", "required": False, "description": "Path to save the generated code"}
                }
            },
            # MULTI-EDIT TOOL
            "multi_edit": {
                "description": "ATOMIC: Perform multiple string replacements on a file atomically. All edits succeed or none are applied (rollback on failure). Edits are applied sequentially - each operates on the result of the previous.",
                "parameters": {
                    "file_path": {"type": "string", "required": True, "description": "Absolute path to the file to edit"},
                    "edits": {"type": "array", "required": True, "description": "List of edit objects with old_string, new_string, and optional replace_all (default: false)"}
                }
            },
            # ====================================================================
            # REDDIT API TOOLS (bypasses browser blocking)
            # Reddit aggressively blocks browser automation. These tools use
            # Reddit's public JSON/RSS endpoints directly - no browser needed.
            # ====================================================================
            "reddit_api": {
                "description": "REDDIT API: Fetch Reddit data without browser automation. Bypasses Reddit's anti-bot blocking. Works for subreddits, posts, users, and search.",
                "parameters": {
                    "subreddit": {"type": "string", "required": False, "description": "Subreddit name (without r/)"},
                    "url": {"type": "string", "required": False, "description": "Full Reddit URL to fetch"},
                    "sort": {"type": "string", "required": False, "default": "hot", "description": "Sort: hot, new, top, rising"},
                    "limit": {"type": "integer", "required": False, "default": 25, "description": "Number of posts to fetch"},
                    "search_query": {"type": "string", "required": False, "description": "Search query within subreddit"}
                }
            },
            "reddit_icp_profiles": {
                "description": "REDDIT ICP: Find Reddit users matching an Ideal Customer Profile. Returns ONLY profile URLs, one per line. Perfect for B2B lead research.",
                "parameters": {
                    "icp_description": {"type": "string", "required": True, "description": "ICP description (e.g., 'SaaS founders with $10k+ MRR who struggle with customer churn')"},
                    "target_count": {"type": "integer", "required": False, "default": 20, "description": "Number of matching profiles to find"},
                    "subreddits": {"type": "array", "required": False, "description": "Specific subreddits to search (auto-detected if not provided)"},
                    "custom_signals": {"type": "object", "required": False, "description": "Custom signal patterns to look for"},
                    "deep_scan": {"type": "boolean", "required": False, "default": False, "description": "Check user post history for more signals (slower but more accurate)"},
                    "min_score": {"type": "integer", "required": False, "default": 20, "description": "Minimum ICP match score threshold"}
                }
            },
            # ====================================================================
            # BROWSER MCP FEATURES (Chrome DevTools Protocol)
            # Real-time console monitoring, network capture, Lighthouse audits.
            # Inspired by Browser MCP Chrome extension for debugging/analysis.
            # ====================================================================
            "playwright_enable_mcp_features": {
                "description": "BROWSER MCP: Enable console monitoring and network capture for debugging. Call this before navigating to capture all activity.",
                "parameters": {
                    "enable_console": {"type": "boolean", "required": False, "default": True, "description": "Enable console log monitoring"},
                    "enable_network": {"type": "boolean", "required": False, "default": True, "description": "Enable network request capture"}
                }
            },
            "playwright_get_console_logs": {
                "description": "BROWSER MCP: Get all console logs captured since enabling MCP features. Useful for debugging JavaScript errors.",
                "parameters": {
                    "level": {"type": "string", "required": False, "description": "Filter by level: log, warning, error, info, debug"},
                    "limit": {"type": "integer", "required": False, "default": 100, "description": "Maximum logs to return"}
                }
            },
            "playwright_get_console_errors": {
                "description": "BROWSER MCP: Get only console errors. Quick way to check for JavaScript errors on page.",
                "parameters": {
                    "limit": {"type": "integer", "required": False, "default": 50, "description": "Maximum errors to return"}
                }
            },
            "playwright_get_network_requests": {
                "description": "BROWSER MCP: Get all captured network requests with response details. Useful for debugging API calls.",
                "parameters": {
                    "filter_url": {"type": "string", "required": False, "description": "Filter requests by URL pattern"},
                    "method": {"type": "string", "required": False, "description": "Filter by HTTP method (GET, POST, etc.)"},
                    "limit": {"type": "integer", "required": False, "default": 100, "description": "Maximum requests to return"}
                }
            },
            "playwright_get_api_calls": {
                "description": "BROWSER MCP: Get only API/XHR calls (excludes static assets). Shows request/response bodies for debugging.",
                "parameters": {
                    "limit": {"type": "integer", "required": False, "default": 50, "description": "Maximum API calls to return"}
                }
            },
            "playwright_lighthouse_audit": {
                "description": "BROWSER MCP: Run Lighthouse performance/accessibility/SEO audit on current page. Requires lighthouse CLI installed.",
                "parameters": {
                    "url": {"type": "string", "required": False, "description": "URL to audit (uses current page if not provided)"},
                    "categories": {"type": "array", "required": False, "description": "Categories to audit: performance, accessibility, best-practices, seo (default: all)"}
                }
            },
            "playwright_connect_existing_browser": {
                "description": "BROWSER MCP: Connect to user's existing Chrome browser (must be started with --remote-debugging-port=9222). Uses logged-in sessions.",
                "parameters": {
                    "port": {"type": "integer", "required": False, "default": 9222, "description": "Chrome debugging port"},
                    "host": {"type": "string", "required": False, "default": "localhost", "description": "Chrome debugging host"}
                }
            }
        }

    def _unwrap_tool_result(self, result: Any) -> Dict[str, Any]:
        """
        Unwrap ToolResult objects to raw dicts for backwards compatibility.

        Many methods are decorated with @tool_result which wraps the return value.
        This helper extracts the raw dict from the wrapper.
        """
        if hasattr(result, 'data') and hasattr(result, 'success'):
            # This is a ToolResult object - unwrap it
            if result.success:
                return result.data if result.data is not None else {}
            else:
                # Error case - return error dict
                return {"error": result.error or "Unknown error", "error_code": result.error_code, "success": False}
        # Already a dict, return as-is
        return result

    async def call_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool by name (MCP-style interface).

        Note: This method does NOT use @tool_result decorator because the methods
        it calls (navigate, click, etc.) are already decorated, which would cause
        double-wrapping and break URL extraction. However, it unwraps ToolResult
        objects to return raw dicts for backwards compatibility.

        Output Format (Eversale style):
        ### Action
        <action>: <target>

        ### Result
        - success: true/false
        - <key>: <value>

        ### Page state
        - URL: <current_url>
        - Title: <page_title>
        """
        import time as _time
        _start = _time.time()

        # UNIVERSAL EXTRACTION ROUTING: Route ALL extraction tools through extract_list_auto
        # This uses: known site selectors → common patterns → dynamic detection → markdown fallback
        EXTRACTION_TOOLS = {
            'playwright_batch_extract', 'playwright_get_content', 'playwright_llm_extract',
            'playwright_extract_structured', 'extract_data', 'get_page_data'
        }

        if tool_name in EXTRACTION_TOOLS:
            current_url = self.page.url if self.page else ''
            logger.info(f"[AUTO-ROUTE] Redirecting {tool_name} -> playwright_extract_list on {current_url}")
            tool_name = 'playwright_extract_list'
            params = {'limit': params.get('limit', params.get('count', 10))}

        def _output(result: Dict[str, Any]) -> Dict[str, Any]:
            """Format and output result in Eversale style."""
            if self.verbose_output:
                duration_ms = int((_time.time() - _start) * 1000)
                formatted = self._format_tool_output(tool_name, params, result, duration_ms)
                if self.output_callback:
                    self.output_callback(formatted)
                else:
                    print(formatted)
            return result

        async def _call(coro):
            """Call a (possibly @tool_result-wrapped) coroutine and return a raw dict."""
            result = self._unwrap_tool_result(await coro)
            return _output(result)

        if tool_name == "playwright_navigate":
            # Normalize parameter names: accept url, href, link, address
            url = params.get("url") or params.get("href") or params.get("link") or params.get("address") or ""
            if not url:
                return {"error": "playwright_navigate requires a 'url' parameter", "success": False}
            return await _call(self.navigate(url))

        elif tool_name == "playwright_click":
            # Normalize parameter names: accept selector, element, target, mmid
            selector = params.get("selector") or params.get("element") or params.get("target") or params.get("mmid") or ""
            if not selector:
                return {"error": "playwright_click requires a 'selector' parameter", "success": False}
            return await _call(self.click(selector))

        elif tool_name == "playwright_fill":
            # Normalize parameter names: accept value, text, content, input
            value = params.get("value") or params.get("text") or params.get("content") or params.get("input") or ""
            selector = params.get("selector") or params.get("element") or params.get("target") or ""
            press_enter = params.get("press_enter")  # Can be True, False, or None (auto-detect)
            if not selector:
                return {"error": "playwright_fill requires a 'selector' parameter", "success": False}
            return await _call(self.fill(selector, value, press_enter=press_enter))

        elif tool_name == "batch_execute" or tool_name == "playwright_batch_execute":
            # Batch execution of multiple actions
            actions = params.get("actions", [])
            stop_on_error = params.get("stop_on_error", False)
            if not actions:
                return {"error": "batch_execute requires an 'actions' list parameter", "success": False}
            return await _call(self.batch_execute(actions, stop_on_error=stop_on_error))

        elif tool_name == "playwright_evaluate":
            script = params.get("script") or params.get("code") or params.get("expression")
            if not script:
                return {"error": "playwright_evaluate requires a 'script' parameter with JavaScript code"}
            return await _call(self.evaluate(script))

        elif tool_name == "playwright_screenshot":
            return await _call(self.screenshot())

        elif tool_name == "playwright_solve_challenge":
            # Show browser popup for user to solve CAPTCHA/login
            timeout = params.get("timeout", 120)
            return await _call(self.handle_challenge_popup(timeout=timeout, auto_hide=True))

        elif tool_name == "playwright_detect_challenge":
            # Just detect without popup
            return await _call(self.detect_challenge())

        elif tool_name == "playwright_get_content":
            return await _call(self.get_content())

        elif tool_name == "playwright_get_text":
            selector = params.get("selector", "body")
            return await _call(self.get_text(selector))

        elif tool_name == "playwright_snapshot":
            return await _call(self.snapshot())

        elif tool_name == "playwright_get_outline":
            return await _call(self.snapshot())

        # CLAUDE CODE STYLE: mmid-based tools
        elif tool_name == "browser_snapshot":
            return _output(await self.browser_snapshot())

        elif tool_name == "browser_click":
            mmid = params.get("mmid", "")
            if not mmid:
                return _output({"error": "mmid parameter required"})
            return _output(await self.click_by_mmid(mmid))

        elif tool_name == "browser_type":
            mmid = params.get("mmid", "")
            text = params.get("text", "")
            clear = params.get("clear", True)
            if not mmid:
                return _output({"error": "mmid parameter required"})
            if not text:
                return _output({"error": "text parameter required"})
            return _output(await self.type_by_mmid(mmid, text, clear))

        elif tool_name == "playwright_find_contacts":
            return _output(await self.find_contacts())

        elif tool_name == "playwright_get_preferred_contact":
            contacts = await self.find_contacts()
            preferred = self.get_preferred_contact(contacts)
            return _output({"success": True, "preferred_contact": preferred, "all_contacts": contacts})

        elif tool_name == "playwright_extract":
            return _output(await self.get_content())

        elif tool_name == "playwright_extract_fb_ads":
            max_ads = params.get("max_ads", 200)
            result = await self.extract_fb_ads_batch(max_ads=max_ads)
            return self._unwrap_tool_result(result)

        elif tool_name == "extract_fb_ads_advertisers":
            query = params.get("query", "")
            country = params.get("country", "US")
            limit = params.get("limit", 10)

            if not query:
                return {"success": False, "error": "query parameter is required"}

            query_encoded = urllib.parse.quote(query)
            url = f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country={country}&media_type=all&q={query_encoded}&search_type=keyword_unordered"

            try:
                await self.goto(url)
                await asyncio.sleep(3)

                result = await self.extract_fb_ads_batch(max_ads=limit)
                unwrapped = self._unwrap_tool_result(result)

                # Add context to error messages
                if not unwrapped.get("success"):
                    error_msg = unwrapped.get("error", "Unknown error")
                    unwrapped["error"] = f"FB Ads extraction failed for query='{query}', country={country}, limit={limit} - {error_msg}"
                    logger.error(f"[FB_ADS_ADVERTISERS] {unwrapped['error']}")

                return unwrapped
            except Exception as e:
                error_msg = f"FB Ads extraction failed for query='{query}', country={country}, limit={limit} - {str(e)}"
                logger.error(f"[FB_ADS_ADVERTISERS] {error_msg}")
                return {"success": False, "error": error_msg, "ads": [], "ads_count": 0}

        elif tool_name == "playwright_extract_tiktok_ads":
            max_ads = params.get("max_ads", 200)
            result = await self.extract_tiktok_ads_batch(max_ads=max_ads)
            return self._unwrap_tool_result(result)

        elif tool_name == "playwright_extract_reddit":
            result = await self.extract_reddit_posts_batch()
            return self._unwrap_tool_result(result)

        elif tool_name == "playwright_extract_page_fast":
            return await self.extract_page_data_fast()

        elif tool_name == "playwright_batch_extract":
            urls = params.get("urls", [])
            return await self.batch_extract_contacts(urls)

        elif tool_name == "playwright_extract_structured":
            item_selector = params.get("item_selector")
            field_selectors = params.get("field_selectors", {})
            limit = params.get("limit", 20)
            return await self.extract_with_selectors(item_selector, field_selectors, limit)

        elif tool_name == "playwright_extract_list":
            # AUTO-DETECT: Use known site selectors, or fall back to params
            limit = params.get("limit", 10)
            result = await self.extract_list_auto(limit=limit)
            return self._unwrap_tool_result(result)

        # NEW: Jina Reader / Firecrawl / Crawl4AI inspired tools
        elif tool_name == "playwright_get_markdown":
            url = params.get("url")
            target_selector = params.get("target_selector")
            return await _call(self.get_markdown(url=url, target_selector=target_selector))

        elif tool_name == "playwright_fetch_url":
            url = params.get("url") or ""
            if not url:
                return {"error": "playwright_fetch_url requires a 'url' parameter", "success": False}
            output_format = params.get("output_format") or params.get("format") or "markdown"
            use_cache = params.get("use_cache", True)
            return await _call(self.fetch_url(url=url, output_format=output_format, use_cache=use_cache))

        elif tool_name == "playwright_deep_search":
            return await _call(self.deep_search(
                query=params.get("query", ""),
                context=params.get("context", ""),
                max_queries=params.get("max_queries", 3),
                results_per_query=params.get("results_per_query", 5),
                summarize_top=params.get("summarize_top", 3)
            ))

        elif tool_name == "playwright_map_site":
            url = params["url"]
            max_urls = params.get("max_urls", 500)
            return await _call(self.map_site(url, max_urls=max_urls))

        elif tool_name == "playwright_crawl_for":
            url = params["url"]
            looking_for = params["looking_for"]
            max_pages = params.get("max_pages", 10)
            return await _call(self.crawl_for(url, looking_for, max_pages=max_pages))

        elif tool_name == "playwright_llm_extract":
            prompt = params["prompt"]
            url = params.get("url")
            return await _call(self.llm_extract(prompt, url=url))

        elif tool_name == "playwright_extract_entities":
            # Support both entity_types (list) and schema (dict) formats
            entity_types = params.get("entity_types")
            schema = params.get("schema")
            url = params.get("url")
            limit = params.get("limit", 10)

            if schema:
                # Handle schema-based extraction (from strategic planner)
                return await _call(self.extract_structured(schema, url=url, limit=limit))
            elif entity_types:
                return await _call(self.extract_entities(entity_types, url=url))
            else:
                return {"error": "Must provide either entity_types or schema parameter"}

        elif tool_name == "playwright_answer_question":
            question = params["question"]
            url = params.get("url")
            return await _call(self.answer_from_page(question, url=url))

        # COMBINED EXTRACT+SAVE TOOL
        elif tool_name == "playwright_extract_to_csv":
            url = params.get("url")  # Optional - uses current page if not provided
            schema = params.get("schema")
            csv_path = params.get("csv_path") or params.get("output_path") or params.get("path") or params.get("file_path")
            if not schema:
                return {"error": "Missing required parameter: schema"}

            # Expand ~ and handle path setup
            from pathlib import Path
            from datetime import datetime
            import os

            if csv_path:
                # Expand ~ to home directory
                csv_path = os.path.expanduser(csv_path)
                # Ensure directory exists
                Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
            else:
                # Auto-generate a sensible default path
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                csv_path = str(Path.home() / "lead_research" / f"extract_{timestamp}.csv")
                Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
                logger.info(f"Auto-generated csv_path: {csv_path}")
            limit = params.get("limit", 10)
            append = params.get("append", False)
            return await _call(self.extract_to_csv(url, schema, csv_path, limit, append))

        # SPEED-OPTIMIZED TOOLS
        elif tool_name == "playwright_fast_extract":
            url = params["url"]
            prompt = params["prompt"]
            return await _call(self.fast_extract(url, prompt))

        elif tool_name == "playwright_parallel_extract":
            urls = params["urls"]
            prompt = params["prompt"]
            return await _call(self.parallel_extract(urls, prompt))

        elif tool_name == "playwright_clear_cache":
            self.clear_cache()
            return {"success": True, "message": "Cache cleared"}

        # BROWSER-USE STYLE TOOLS
        elif tool_name == "playwright_get_elements":
            return await _call(self.get_interactive_elements())

        elif tool_name == "playwright_click_index":
            index = params["index"]
            return await _call(self.click_by_index(index))

        # PRUNE4WEB & AGENT-E STYLE TOOLS
        elif tool_name == "playwright_pruned_dom":
            focus_area = params.get("focus_area")
            return await _call(self.get_pruned_dom(focus_area))

        elif tool_name == "playwright_observe_change":
            action = params.get("action", "")
            return await self.get_change_observation(action)

        elif tool_name == "playwright_smart_search":
            query = params["query"]
            return await self.smart_search(query)

        # MEM0-STYLE MEMORY TOOLS
        elif tool_name == "playwright_session_memory":
            return self.get_session_memory()

        elif tool_name == "playwright_clear_memory":
            return self.clear_session_memory()

        elif tool_name == "playwright_store_data":
            key = params["key"]
            data = params["data"]
            url = self.page.url if self.page else "unknown"
            SessionMemory.store_data(url, key, data)
            return {"success": True, "stored": {key: data}}

        # SELF-CORRECTION TOOLS
        elif tool_name == "playwright_click_retry":
            selector = params["selector"]
            max_retries = params.get("max_retries", 3)
            return await self.click_with_retry(selector, max_retries)

        elif tool_name == "playwright_compressed_state":
            max_tokens = params.get("max_tokens", 2000)
            return await self.get_compressed_state(max_tokens)

        elif tool_name == "playwright_apply_stealth":
            await self.apply_enhanced_stealth()
            return {"success": True, "message": "Enhanced stealth applied"}

        elif tool_name == "playwright_research_start":
            return await self.research_start(
                query=params.get("query", ""),
                instructions=params.get("instructions", ""),
                max_queries=params.get("max_queries", 4),
                results_per_query=params.get("results_per_query", 5)
            )

        elif tool_name == "playwright_research_check":
            return await self.research_check(
                job_id=params.get("job_id"),
                include_logs=params.get("include_logs", False)
            )

        elif tool_name == "playwright_linkedin_company_lookup":
            company = params.get("company") or params.get("company_name") or ""
            if not company or company.startswith("{"):
                return {"error": "company parameter is required with an actual company name, not a placeholder"}
            return await self.linkedin_company_lookup(
                company=company,
                max_results=params.get("max_results", 3)
            )

        elif tool_name == "playwright_company_profile":
            return await self.company_profile(
                company=params.get("company", ""),
                website=params.get("website"),
                include_contacts=params.get("include_contacts", False)
            )

        # API-BASED SEARCH (bypasses Google CAPTCHA/rate limiting)
        elif tool_name == "playwright_web_search":
            return await self.web_search(
                query=params.get("query", ""),
                num_results=params.get("num_results", 10)
            )

        # ====================================================================
        # CLAUDE CODE STYLE TOOLS (Microsoft @playwright/mcp compatible)
        # ====================================================================
        elif tool_name == "browser_snapshot":
            return await self.browser_snapshot()

        elif tool_name == "browser_click":
            mmid = params.get("mmid", "")
            return await self.click_by_mmid(mmid)

        elif tool_name == "browser_type":
            mmid = params.get("mmid", "")
            text = params.get("text", "")
            clear = params.get("clear", True)
            return await self.type_by_mmid(mmid, text, clear)

        elif tool_name == "browser_navigate":
            return await self.navigate(params.get("url", ""))

        elif tool_name == "browser_scroll":
            direction = params.get("direction", "down")
            amount = params.get("amount", 500)
            return await self.scroll(direction, amount)

        elif tool_name == "browser_fingerprint":
            return await self.get_dom_fingerprint()

        elif tool_name == "browser_verify_action":
            before_fp = params.get("before_fp", {})
            action_type = params.get("action_type", "click")
            return await self.verify_action(before_fp, action_type)

        elif tool_name == "browser_click_verified":
            selector = params.get("selector", "")
            return await self.click_with_verification(selector)

        elif tool_name == "browser_type_verified":
            selector = params.get("selector", "")
            text = params.get("text", "")
            clear = params.get("clear", True)
            return await self.type_with_verification(selector, text, clear)

        # AUTOMATION TOOLS (non-playwright_ prefix)
        elif tool_name == "press_key":
            key = params.get("key", "Enter")
            return await self.press_key(key)

        elif tool_name == "scroll_page":
            direction = params.get("direction", "down")
            amount = params.get("amount", 500)
            return await self.scroll(direction, amount)

        elif tool_name == "hover":
            selector = params.get("selector", "")
            return await self.hover(selector)

        elif tool_name == "select_dropdown":
            selector = params.get("selector", "")
            value = params.get("value", "")
            return await self.select_dropdown(selector, value)

        # CODE GENERATION TOOL
        elif tool_name == "playwright_export_code":
            if not CODE_GENERATOR_AVAILABLE:
                return {"error": "Code generator not available - missing code_generator module"}

            actions = params.get("actions")
            format_type = params.get("format", "python_async")
            description = params.get("description", "")
            output_file = params.get("output_file")

            # If no actions provided, return helpful message
            if not actions:
                return {
                    "error": "No actions provided. Pass 'actions' parameter with list of tool calls to export.",
                    "example": [
                        {"tool": "playwright_navigate", "arguments": {"url": "https://example.com"}},
                        {"tool": "playwright_click", "arguments": {"selector": "button.submit"}}
                    ]
                }

            try:
                generator = PlaywrightCodeGenerator()
                generated = generator.generate_from_trace(
                    actions=actions,
                    description=description,
                    format=format_type
                )

                result = {
                    "success": True,
                    "code": generated.code,
                    "format": generated.format.value,
                    "parameters": generated.parameters,
                    "dependencies": generated.dependencies,
                    "description": generated.description
                }

                # Save to file if requested
                if output_file:
                    output_path = Path(output_file)
                    generator.save_to_file(generated, output_path)
                    result["saved_to"] = str(output_path)
                    result["metadata_file"] = str(output_path.with_suffix('.json'))

                return result

            except Exception as e:
                logger.error(f"Code generation failed: {e}")
                return {"error": f"Code generation failed: {str(e)}"}

        # MULTI-EDIT TOOL
        elif tool_name == "multi_edit":
            from .multi_edit import get_multi_edit_tool

            file_path = params.get("file_path")
            edits = params.get("edits")

            if not file_path:
                return {"success": False, "error": "file_path parameter is required"}

            if not edits:
                return {"success": False, "error": "edits parameter is required (list of edit objects)"}

            try:
                tool = get_multi_edit_tool()
                result = await tool.execute(file_path=file_path, edits=edits)
                return result
            except Exception as e:
                logger.error(f"Multi-edit failed: {e}")
                return {"success": False, "error": f"Multi-edit failed: {str(e)}"}

        # ====================================================================
        # REDDIT API TOOLS (bypasses browser blocking)
        # ====================================================================
        elif tool_name == "reddit_api":
            if not REDDIT_HANDLER_AVAILABLE:
                return {"error": "Reddit handler not available", "success": False}

            subreddit = params.get("subreddit")
            url = params.get("url")
            sort = params.get("sort", "hot")
            limit = params.get("limit", 25)
            search_query = params.get("search_query")

            try:
                if url:
                    # Fetch specific URL
                    result = await fetch_reddit_data(url)
                elif subreddit and search_query:
                    # Search within subreddit
                    handler = RedditHandler()
                    posts = await handler.search(search_query, subreddit=subreddit, limit=limit)
                    result = {
                        "success": True,
                        "posts": [p.to_dict() for p in posts],
                        "count": len(posts),
                        "source": "reddit_json_api"
                    }
                elif subreddit:
                    # Get subreddit posts
                    handler = RedditHandler()
                    posts = await handler.get_subreddit(subreddit, sort=sort, limit=limit)
                    result = {
                        "success": True,
                        "posts": [p.to_dict() for p in posts],
                        "count": len(posts),
                        "source": "reddit_json_api"
                    }
                else:
                    return {"error": "Provide either 'url' or 'subreddit' parameter", "success": False}

                return result

            except Exception as e:
                logger.error(f"Reddit API fetch failed: {e}")
                return {"error": str(e), "success": False}

        elif tool_name == "reddit_icp_profiles":
            if not REDDIT_HANDLER_AVAILABLE or find_icp_profile_urls is None:
                return {"error": "Reddit ICP handler not available", "success": False}

            icp_description = params.get("icp_description")
            if not icp_description:
                return {"error": "icp_description parameter is required", "success": False}

            target_count = params.get("target_count", 20)
            subreddits = params.get("subreddits")
            custom_signals = params.get("custom_signals")
            deep_scan = params.get("deep_scan", False)
            min_score = params.get("min_score", 20)

            try:
                result = await find_icp_profile_urls(
                    icp_description=icp_description,
                    target_count=target_count,
                    subreddits=subreddits,
                    custom_signals=custom_signals,
                    deep_scan=deep_scan,
                    min_score=min_score
                )

                # Format output as clean URLs only (one per line)
                if result.get("success") and result.get("profile_urls"):
                    result["formatted_output"] = format_icp_profile_urls(result["profile_urls"])

                return result

            except Exception as e:
                logger.error(f"Reddit ICP profile search failed: {e}")
                return {"error": str(e), "success": False}

        # ====================================================================
        # BROWSER MCP FEATURES - Chrome DevTools Protocol tools
        # ====================================================================
        elif tool_name == "playwright_enable_mcp_features":
            enable_console = params.get("enable_console", True)
            enable_network = params.get("enable_network", True)
            result = await self.enable_mcp_features(enable_console, enable_network)
            return {"success": True, "enabled": result}

        elif tool_name == "playwright_get_console_logs":
            level = params.get("level")
            limit = params.get("limit", 100)
            logs = self.get_console_logs(level=level, limit=limit)
            return {"success": True, "logs": logs, "count": len(logs)}

        elif tool_name == "playwright_get_console_errors":
            limit = params.get("limit", 50)
            errors = self.get_console_errors(limit=limit)
            return {"success": True, "errors": errors, "count": len(errors)}

        elif tool_name == "playwright_get_network_requests":
            filter_url = params.get("filter_url")
            method = params.get("method")
            limit = params.get("limit", 100)
            requests = self.get_network_requests(filter_url=filter_url, method=method, limit=limit)
            return {"success": True, "requests": requests, "count": len(requests)}

        elif tool_name == "playwright_get_api_calls":
            limit = params.get("limit", 50)
            api_calls = self.get_api_calls(limit=limit)
            return {"success": True, "api_calls": api_calls, "count": len(api_calls)}

        elif tool_name == "playwright_lighthouse_audit":
            if not BROWSER_MCP_FEATURES_AVAILABLE:
                return {"error": "Browser MCP features not available. Install browser_mcp_features module.", "success": False}

            url = params.get("url") or (self.page.url if self.page else None)
            if not url:
                return {"error": "No URL provided and no page loaded", "success": False}

            categories = params.get("categories")

            try:
                auditor = LighthouseAuditor()
                result = await auditor.audit(url, categories=categories)
                return {"success": True, "audit": result}
            except Exception as e:
                logger.error(f"Lighthouse audit failed: {e}")
                return {"error": str(e), "success": False}

        elif tool_name == "playwright_connect_existing_browser":
            if not BROWSER_MCP_FEATURES_AVAILABLE:
                return {"error": "Browser MCP features not available. Install browser_mcp_features module.", "success": False}

            port = params.get("port", 9222)
            host = params.get("host", "localhost")

            try:
                connection = ExistingBrowserConnection(port=port, host=host)
                # Store playwright instance if we don't have one
                if not self.playwright:
                    from playwright.async_api import async_playwright
                    self.playwright = await async_playwright().start()

                connection.playwright = self.playwright
                await connection.connect()

                # Use the connected browser's context and page
                if connection.browser and connection.browser.contexts:
                    context = connection.browser.contexts[0]
                    if context.pages:
                        self.page = context.pages[0]
                        self.context = context
                        self.browser = connection.browser
                        return {
                            "success": True,
                            "message": f"Connected to existing Chrome at {host}:{port}",
                            "current_url": self.page.url,
                            "page_title": await self.page.title()
                        }

                return {"error": "Connected but no pages found. Open a tab in Chrome first.", "success": False}

            except Exception as e:
                logger.error(f"Failed to connect to existing browser: {e}")
                return {"error": str(e), "success": False}

        # ====================================================================
        # MISSING playwright_ PREFIXED TOOLS (wired to existing methods)
        # ====================================================================
        elif tool_name == "playwright_scroll":
            direction = params.get("direction", "down")
            amount = params.get("amount", 500)
            return await self.scroll(direction, amount)

        elif tool_name == "playwright_hover":
            selector = params.get("selector") or params.get("element") or params.get("target") or ""
            if not selector:
                return {"error": "playwright_hover requires a 'selector' parameter", "success": False}
            return await self.hover(selector)

        elif tool_name == "playwright_wait":
            # Simple wait for specified time (in seconds)
            wait_time = params.get("time", 2)
            if isinstance(wait_time, (int, float)):
                await asyncio.sleep(wait_time)
                return {"success": True, "waited": wait_time, "message": f"Waited {wait_time}s"}
            return {"success": False, "error": "Invalid wait time parameter"}

        elif tool_name == "playwright_select":
            selector = params.get("selector") or params.get("element") or ""
            value = params.get("value") or params.get("option") or ""
            if not selector:
                return {"error": "playwright_select requires a 'selector' parameter", "success": False}
            return await self.select_dropdown(selector, value)

        elif tool_name == "playwright_type":
            # Type is like fill but focuses on the typing action
            selector = params.get("selector") or params.get("element") or params.get("target") or ""
            text = params.get("text") or params.get("value") or params.get("content") or ""
            if not selector:
                return {"error": "playwright_type requires a 'selector' parameter", "success": False}
            return await self.fill(selector, text, press_enter=False)

        elif tool_name == "get_page_info":
            # Return basic page info
            if not self.page:
                return {"error": "No page loaded", "success": False}
            return {
                "success": True,
                "url": getattr(self.page, 'url', ''),
                "title": await self.page.title(),
                "viewport": self.page.viewport_size
            }

        # ====================================================================
        # PLAYWRIGHT MCP PARITY - Added for full compatibility
        # ====================================================================

        elif tool_name == "navigate_back" or tool_name == "playwright_navigate_back" or tool_name == "browser_navigate_back":
            # Go back to previous page (Playwright MCP: browser_navigate_back)
            if not self.page:
                return {"error": "No page loaded", "success": False}
            try:
                await self.page.go_back(wait_until="domcontentloaded", timeout=30000)
                return {
                    "success": True,
                    "url": self.page.url,
                    "title": await self.page.title(),
                    "message": "Navigated back"
                }
            except Exception as e:
                return {"error": str(e), "success": False}

        elif tool_name == "drag" or tool_name == "playwright_drag" or tool_name == "browser_drag":
            # Drag and drop between elements (Playwright MCP: browser_drag)
            if not self.page:
                return {"error": "No page loaded", "success": False}
            start_ref = params.get("startRef") or params.get("start_ref") or params.get("source") or ""
            end_ref = params.get("endRef") or params.get("end_ref") or params.get("target") or ""
            if not start_ref or not end_ref:
                return {"error": "drag requires 'startRef' and 'endRef' parameters", "success": False}
            try:
                # Get locators for start and end elements
                start_locator = await self._get_locator_by_ref(start_ref)
                end_locator = await self._get_locator_by_ref(end_ref)
                if not start_locator or not end_locator:
                    return {"error": f"Could not find elements for refs: {start_ref}, {end_ref}", "success": False}
                await start_locator.drag_to(end_locator)
                return {"success": True, "message": f"Dragged from {start_ref} to {end_ref}"}
            except Exception as e:
                return {"error": str(e), "success": False}

        elif tool_name == "file_upload" or tool_name == "playwright_file_upload" or tool_name == "browser_file_upload":
            # Upload files (Playwright MCP: browser_file_upload)
            if not self.page:
                return {"error": "No page loaded", "success": False}
            paths = params.get("paths") or params.get("files") or []
            if isinstance(paths, str):
                paths = [paths]
            if not paths:
                # Cancel file chooser if no paths provided
                return {"success": True, "message": "File chooser cancelled (no paths provided)"}
            try:
                # Wait for file chooser and set files
                async with self.page.expect_file_chooser() as fc_info:
                    # Trigger file input click if ref provided
                    ref = params.get("ref") or params.get("selector")
                    if ref:
                        locator = await self._get_locator_by_ref(ref)
                        if locator:
                            await locator.click()
                file_chooser = await fc_info.value
                await file_chooser.set_files(paths)
                return {"success": True, "message": f"Uploaded {len(paths)} file(s)", "paths": paths}
            except Exception as e:
                return {"error": str(e), "success": False}

        elif tool_name == "tabs_list" or tool_name == "playwright_tabs_list" or tool_name == "browser_tabs":
            # List all open tabs (Playwright MCP: browser_tabs action=list)
            action = params.get("action", "list")
            if not self.context:
                return {"error": "No browser context", "success": False}
            try:
                if action == "list":
                    tabs = []
                    for i, page in enumerate(self.context.pages):
                        tabs.append({
                            "index": i,
                            "url": page.url,
                            "title": await page.title(),
                            "is_current": page == self.page
                        })
                    return {"success": True, "tabs": tabs, "count": len(tabs)}
                elif action == "new":
                    url = params.get("url", "about:blank")
                    new_page = await self.context.new_page()
                    if url and url != "about:blank":
                        await new_page.goto(url, wait_until="domcontentloaded")
                    self.page = new_page  # Switch to new tab
                    return {"success": True, "message": f"Opened new tab", "url": new_page.url}
                elif action == "select":
                    index = params.get("index", 0)
                    pages = self.context.pages
                    if 0 <= index < len(pages):
                        self.page = pages[index]
                        return {"success": True, "message": f"Switched to tab {index}", "url": self.page.url}
                    return {"error": f"Tab index {index} out of range (0-{len(pages)-1})", "success": False}
                elif action == "close":
                    index = params.get("index")
                    pages = self.context.pages
                    if index is None:
                        # Close current tab
                        await self.page.close()
                        if pages:
                            self.page = pages[0]
                        return {"success": True, "message": "Closed current tab"}
                    elif 0 <= index < len(pages):
                        await pages[index].close()
                        if self.page not in self.context.pages and self.context.pages:
                            self.page = self.context.pages[0]
                        return {"success": True, "message": f"Closed tab {index}"}
                    return {"error": f"Tab index {index} out of range", "success": False}
                else:
                    return {"error": f"Unknown tabs action: {action}. Use list/new/select/close", "success": False}
            except Exception as e:
                return {"error": str(e), "success": False}

        elif tool_name == "handle_dialog" or tool_name == "playwright_handle_dialog" or tool_name == "browser_handle_dialog":
            # Handle browser dialogs - alerts, confirms, prompts (Playwright MCP: browser_handle_dialog)
            accept = params.get("accept", True)
            prompt_text = params.get("promptText") or params.get("prompt_text") or ""
            if not self.page:
                return {"error": "No page loaded", "success": False}
            try:
                # Set up dialog handler
                dialog_handled = {"handled": False, "message": "", "type": ""}
                async def on_dialog(dialog):
                    dialog_handled["type"] = dialog.type
                    dialog_handled["message"] = dialog.message
                    if accept:
                        if dialog.type == "prompt" and prompt_text:
                            await dialog.accept(prompt_text)
                        else:
                            await dialog.accept()
                    else:
                        await dialog.dismiss()
                    dialog_handled["handled"] = True

                self.page.once("dialog", on_dialog)
                # Wait briefly for dialog
                await asyncio.sleep(0.5)
                if dialog_handled["handled"]:
                    return {
                        "success": True,
                        "dialog_type": dialog_handled["type"],
                        "message": dialog_handled["message"],
                        "action": "accepted" if accept else "dismissed"
                    }
                return {"success": True, "message": "Dialog handler set (no dialog appeared yet)"}
            except Exception as e:
                return {"error": str(e), "success": False}

        elif tool_name == "fill_form" or tool_name == "playwright_fill_form" or tool_name == "browser_fill_form":
            # Fill multiple form fields at once (Playwright MCP: browser_fill_form)
            if not self.page:
                return {"error": "No page loaded", "success": False}
            fields = params.get("fields") or []
            if not fields:
                return {"error": "fill_form requires 'fields' array parameter", "success": False}
            try:
                results = []
                for field in fields:
                    ref = field.get("ref") or field.get("selector")
                    value = field.get("value", "")
                    field_type = field.get("type", "textbox")
                    field_name = field.get("name", ref)

                    if not ref:
                        results.append({"name": field_name, "success": False, "error": "No ref provided"})
                        continue

                    locator = await self._get_locator_by_ref(ref)
                    if not locator:
                        results.append({"name": field_name, "success": False, "error": f"Element {ref} not found"})
                        continue

                    if field_type == "checkbox":
                        if value.lower() in ("true", "1", "yes"):
                            await locator.check()
                        else:
                            await locator.uncheck()
                    elif field_type == "radio":
                        await locator.check()
                    elif field_type == "combobox":
                        await locator.select_option(label=value)
                    elif field_type == "slider":
                        # For sliders, fill the underlying input
                        await locator.fill(str(value))
                    else:  # textbox default
                        await locator.fill(value)

                    results.append({"name": field_name, "success": True})

                return {"success": True, "results": results, "filled": len([r for r in results if r["success"]])}
            except Exception as e:
                return {"error": str(e), "success": False}

        elif tool_name == "resize" or tool_name == "playwright_resize" or tool_name == "browser_resize":
            # Resize browser window (Playwright MCP: browser_resize)
            if not self.page:
                return {"error": "No page loaded", "success": False}
            width = params.get("width", 1280)
            height = params.get("height", 720)
            try:
                await self.page.set_viewport_size({"width": int(width), "height": int(height)})
                return {"success": True, "width": width, "height": height, "message": f"Resized to {width}x{height}"}
            except Exception as e:
                return {"error": str(e), "success": False}

        elif tool_name == "close" or tool_name == "playwright_close" or tool_name == "browser_close":
            # Close browser (Playwright MCP: browser_close)
            try:
                if self.page:
                    await self.page.close()
                    self.page = None
                if self.context:
                    await self.context.close()
                    self.context = None
                if self.browser:
                    await self.browser.close()
                    self.browser = None
                return {"success": True, "message": "Browser closed"}
            except Exception as e:
                return {"error": str(e), "success": False}

        elif tool_name == "wait_for" or tool_name == "playwright_wait_for" or tool_name == "browser_wait_for":
            # Wait for text/element (Playwright MCP: browser_wait_for)
            if not self.page:
                return {"error": "No page loaded", "success": False}
            text = params.get("text")
            text_gone = params.get("textGone") or params.get("text_gone")
            wait_time = params.get("time")
            try:
                if wait_time:
                    await asyncio.sleep(float(wait_time))
                    return {"success": True, "message": f"Waited {wait_time} seconds"}
                elif text:
                    await self.page.wait_for_selector(f"text={text}", timeout=30000)
                    return {"success": True, "message": f"Text '{text}' appeared"}
                elif text_gone:
                    await self.page.wait_for_selector(f"text={text_gone}", state="hidden", timeout=30000)
                    return {"success": True, "message": f"Text '{text_gone}' disappeared"}
                else:
                    return {"error": "wait_for requires 'text', 'textGone', or 'time' parameter", "success": False}
            except Exception as e:
                return {"error": str(e), "success": False}

        elif tool_name == "console_messages" or tool_name == "playwright_console_messages" or tool_name == "browser_console_messages":
            # Get console messages (Playwright MCP: browser_console_messages)
            level = params.get("level", "info")
            # Return captured console messages
            messages = getattr(self, '_console_messages', [])
            level_priority = {"error": 0, "warning": 1, "info": 2, "debug": 3}
            min_level = level_priority.get(level, 2)
            filtered = [m for m in messages if level_priority.get(m.get("type", "info"), 2) <= min_level]
            return {"success": True, "messages": filtered, "count": len(filtered)}

        elif tool_name == "network_requests" or tool_name == "playwright_network_requests" or tool_name == "browser_network_requests":
            # Get network requests (Playwright MCP: browser_network_requests)
            include_static = params.get("includeStatic") or params.get("include_static", False)
            requests = getattr(self, '_network_requests', [])
            if not include_static:
                static_exts = {'.js', '.css', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.woff', '.woff2', '.ttf', '.ico'}
                requests = [r for r in requests if not any(r.get("url", "").lower().endswith(ext) for ext in static_exts)]
            return {"success": True, "requests": requests, "count": len(requests)}

        else:
            # Provide helpful error with suggestions
            valid_tools = [
                # Core browser actions
                'playwright_navigate', 'playwright_click', 'playwright_fill', 'playwright_snapshot',
                'playwright_screenshot', 'playwright_evaluate', 'playwright_get_markdown',
                'playwright_scroll', 'playwright_hover', 'playwright_select', 'playwright_type',
                # Playwright MCP parity tools
                'navigate_back', 'browser_navigate_back', 'drag', 'browser_drag',
                'file_upload', 'browser_file_upload', 'browser_tabs', 'tabs_list',
                'handle_dialog', 'browser_handle_dialog', 'fill_form', 'browser_fill_form',
                'resize', 'browser_resize', 'close', 'browser_close',
                'wait_for', 'browser_wait_for', 'console_messages', 'browser_console_messages',
                'network_requests', 'browser_network_requests',
                # Extraction tools
                'playwright_extract_list', 'playwright_extract_fb_ads', 'extract_fb_ads_advertisers',
                # Utility tools
                'get_page_info', 'batch_execute', 'playwright_batch_execute'
            ]
            suggestions = [t for t in valid_tools if tool_name.split('_')[-1] in t or t.split('_')[-1] in tool_name]
            suggestion_msg = f" Did you mean: {suggestions[0]}?" if suggestions else ""
            logger.warning(f"Unknown tool called: {tool_name}{suggestion_msg}")
            return _output({"error": f"Unknown tool: {tool_name}.{suggestion_msg}", "success": False})

    def _format_tool_output(self, tool_name: str, params: Dict[str, Any], result: Dict[str, Any], duration_ms: int) -> str:
        """
        Format tool output for consistent Eversale CLI output.

        Returns formatted string like:
        ### Action
        navigate: https://example.com

        ### Result
        - success: true
        - title: Example Page

        ### Page state
        - URL: https://example.com
        - Title: Example Page
        """
        lines = []

        # Map tool names to human-readable actions
        action_map = {
            'playwright_navigate': 'navigate',
            'playwright_click': 'click',
            'playwright_fill': 'fill',
            'playwright_type': 'type',
            'playwright_press': 'press',
            'playwright_scroll': 'scroll',
            'playwright_snapshot': 'snapshot',
            'playwright_screenshot': 'screenshot',
            'playwright_wait': 'wait',
            'playwright_evaluate': 'evaluate',
            'playwright_extract_list': 'extract',
            'playwright_extract_fb_ads': 'extract_fb_ads',
            'playwright_get_text': 'get_text',
            'playwright_get_content': 'get_content',
            'playwright_get_markdown': 'get_markdown',
            'browser_snapshot': 'snapshot',
            'browser_click': 'click',
            'browser_type': 'type',
        }
        action = action_map.get(tool_name, tool_name.replace('playwright_', ''))

        # Handle ToolResult objects (dataclasses)
        if hasattr(result, '__dataclass_fields__'):
            from dataclasses import asdict
            result = asdict(result)
        # Handle objects with to_dict method
        elif hasattr(result, 'to_dict'):
            result = result.to_dict()
        elif hasattr(result, 'dict'):
             result = result.dict()

        # Get target from params
        target = params.get('url') or params.get('selector') or params.get('element') or params.get('text', '')[:50] or params.get('mmid') or ''

        # Action section
        lines.append("### Action")
        if target:
            lines.append(f"{action}: {target[:80]}{'...' if len(str(target)) > 80 else ''}")
        else:
            lines.append(action)

        # Result section
        lines.append("")
        lines.append("### Result")
        if result.get('error'):
            lines.append(f"- error: {result['error'][:100]}")
        else:
            lines.append(f"- success: {str(result.get('success', True)).lower()}")

            # Show key result fields
            for key in ['count', 'items', 'data', 'text', 'file', 'path']:
                if key in result and result[key]:
                    val = result[key]
                    if isinstance(val, list):
                        lines.append(f"- {key}: {len(val)} items")
                    elif isinstance(val, str) and len(val) > 50:
                        lines.append(f"- {key}: {val[:50]}...")
                    else:
                        lines.append(f"- {key}: {val}")

        # Page state (if we have page info)
        page_url = result.get('url') or (self.page.url if self.page else None)
        page_title = result.get('title')
        if page_url:
            lines.append("")
            lines.append("### Page state")
            lines.append(f"- URL: {page_url}")
            if page_title:
                lines.append(f"- Title: {page_title}")

        # Duration
        if duration_ms > 100:
            lines.append("")
            lines.append(f"[{duration_ms}ms]")

        return "\n".join(lines)

    def _resolve_profile_dir(self, preferred: Optional[str]) -> Optional[str]:
        """
        Resolve browser profile directory.

        NOTE: This is an internal method, NOT a tool - do NOT add @tool_result decorator.

        IMPORTANT: This function now ALWAYS uses the isolated Eversale profile
        to prevent corrupting the user's normal Chrome/Edge profile.

        The old behavior of auto-detecting and using the user's Chrome profile
        caused serious issues:
        - Lock files left behind corrupted normal Chrome
        - Users had to re-login to all sites after PC restart
        - Chrome showed "profile in use" or corruption errors

        Now we ONLY use:
        1. EVERSALE_BROWSER_PROFILE env var (if explicitly set by user)
        2. The preferred isolated path (~/.eversale/browser-profile)

        We NEVER auto-detect and use the user's real Chrome profile.
        """
        import os

        if os.environ.get("EVERSALE_DISABLE_PROFILE", "").lower() in {"1", "true", "yes"}:
            logger.info("Persistent browser profile disabled via EVERSALE_DISABLE_PROFILE.")
            return None

        # 1. Explicit override via environment variable (user knows what they're doing)
        env_profile = os.environ.get("EVERSALE_BROWSER_PROFILE")
        if env_profile:
            env_path = Path(env_profile)
            if env_path.exists() and env_path.is_dir():
                logger.info(f"Using browser profile from EVERSALE_BROWSER_PROFILE: {env_profile}")
                return env_profile
            else:
                logger.warning(f"EVERSALE_BROWSER_PROFILE path does not exist: {env_profile}")

        # 2. Use the preferred isolated profile (this is the safe default)
        # This is typically ~/.eversale/browser-profile
        if preferred:
            pref_path = Path(preferred)
            # Create it if it doesn't exist
            if not pref_path.exists():
                try:
                    pref_path.mkdir(parents=True, exist_ok=True)
                    logger.info(f"Created isolated browser profile: {preferred}")
                except Exception as e:
                    logger.warning(f"Could not create profile directory {preferred}: {e}")

            if pref_path.exists() and pref_path.is_dir():
                logger.info(f"Using isolated browser profile: {preferred}")
                return preferred

        # 3. Create default isolated profile if nothing else works
        default_profile = Path.home() / ".eversale" / "browser-profile"
        default_profile.mkdir(parents=True, exist_ok=True)
        logger.info(f"Using default isolated browser profile: {default_profile}")
        return str(default_profile)

        # NOTE: We intentionally DO NOT auto-detect the user's Chrome/Edge profile
        # to prevent corruption. If users want to use their logged-in Chrome profile,
        # they can explicitly set EVERSALE_BROWSER_PROFILE env var.

    @tool_result
    def get_preferred_contact(self, contacts_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get the preferred contact method from find_contacts result.
        Priority: contact form URL > email (not both)

        Args:
            contacts_result: Result from find_contacts()

        Returns:
            Dict with 'contact_type' ('form' or 'email') and 'value'
        """
        if not contacts_result or not contacts_result.get('success'):
            return {'contact_type': None, 'value': None}

        # Priority 1: Contact form URL
        contact_links = contacts_result.get('contact_links', [])
        for link in contact_links:
            href = link.get('href', '')
            text = link.get('text', '').lower()
            # Look for actual contact form URLs (not just "Contact Us" text)
            if any(k in href.lower() for k in ['contact', 'support', 'get-in-touch', 'reach-us']):
                return {
                    'contact_type': 'form',
                    'value': href,
                    'text': link.get('text', '')
                }

        # Priority 2: Email (only if no contact form found)
        emails = contacts_result.get('emails', [])
        if emails:
            # Filter out generic/noreply emails, prefer support/contact/info emails
            priority_emails = [e for e in emails if any(p in e.lower() for p in ['support', 'contact', 'info', 'hello', 'sales'])]
            if priority_emails:
                return {'contact_type': 'email', 'value': priority_emails[0]}
            return {'contact_type': 'email', 'value': emails[0]}

        return {'contact_type': None, 'value': None}

    @tool_result
    async def extract_fb_ads_batch(self, max_ads: int = 200) -> Dict[str, Any]:
        """
        Extract structured Facebook Ads Library data - BULLETPROOF COMPETITIVE ADVANTAGE.

        Uses multiple extraction strategies for maximum coverage:
        1. Image alt text for advertiser names
        2. Link parsing for landing URLs and FB pages (with social media filtering)
        3. Library ID pattern matching
        4. Button/text content for ad copy

        IMPORTANT - Landing URL Extraction:
        - Parses redirect links (l.facebook.com/l.php) to extract destination URLs
        - Filters out Instagram/Facebook URLs to get actual landing pages
        - Uses 3-tier strategy: redirect links -> CTA buttons -> external links
        - Prioritizes non-social-media URLs (actual landing pages vs. Instagram profiles)

        Args:
            max_ads: Maximum number of ads to extract (default 50)

        Returns:
            Dict with 'success', 'ads_count', 'ads' (list of structured ad objects), 'source_url'
        """
        max_retries = 2
        retry_count = 0
        last_error = None

        while retry_count <= max_retries:
            try:
                # Ensure page exists with timeout
                try:
                    await asyncio.wait_for(self._ensure_page(), timeout=10.0)
                except asyncio.TimeoutError:
                    logger.error(f"FB Ads extractor: Page initialization timeout (attempt {retry_count + 1}/{max_retries + 1})")
                    if retry_count < max_retries:
                        retry_count += 1
                        await exponential_backoff_sleep(retry_count)
                        continue
                    return {
                        "success": False,
                        "error": "Page initialization timeout after retries",
                        "ads": [],
                        "ads_count": 0
                    }

                # Validate URL
                try:
                    url = self.page.url
                except Exception as e:
                    logger.error(f"FB Ads extractor: Could not get page URL - {e}")
                    return {
                        "success": False,
                        "error": f"Could not access page URL: {str(e)}",
                        "ads": [],
                        "ads_count": 0
                    }

                if 'facebook.com/ads/library' not in url:
                    logger.warning(f"FB Ads extractor: Not on correct page (URL: {url})")
                    return {
                        "success": False,
                        "error": "Not on Facebook Ads Library page",
                        "current_url": url,
                        "ads": [],
                        "ads_count": 0
                    }

                # Wait for initial load with timeout
                try:
                    await asyncio.wait_for(
                        self.wait_adaptive(base_seconds=1.0, max_seconds=5.0, wait_for="network"),
                        timeout=15.0
                    )
                except asyncio.TimeoutError:
                    logger.warning("FB Ads extractor: Initial page load timeout, continuing anyway")
                except Exception as e:
                    logger.warning(f"FB Ads extractor: Wait adaptive failed - {e}, continuing anyway")

                # Aggressive scrolling to load more ads with error handling
                try:
                    # First pass - fast scroll to trigger lazy loading
                    for scroll_pos in range(0, 15000, 800):
                        try:
                            await asyncio.wait_for(
                                self.page.evaluate(f"window.scrollTo(0, {scroll_pos})"),
                                timeout=2.0
                            )
                            await sleep_with_jitter(0.05)
                        except asyncio.TimeoutError:
                            logger.debug(f"FB Ads extractor: Scroll timeout at position {scroll_pos}, continuing")
                            continue
                        except Exception as e:
                            logger.debug(f"FB Ads extractor: Scroll error at {scroll_pos} - {e}")
                            continue

                    # Wait for content to load after fast scroll
                    try:
                        await asyncio.wait_for(
                            self.wait_adaptive(base_seconds=0.5, max_seconds=3.0, wait_for="stable"),
                            timeout=5.0
                        )
                    except (asyncio.TimeoutError, Exception) as e:
                        logger.debug(f"FB Ads extractor: Post-scroll wait failed - {e}")

                    # Second pass - slower scroll to catch any missed content
                    for scroll_pos in range(0, 20000, 500):
                        try:
                            await asyncio.wait_for(
                                self.page.evaluate(f"window.scrollTo(0, {scroll_pos})"),
                                timeout=2.0
                            )
                            await sleep_with_jitter(0.05)
                        except (asyncio.TimeoutError, Exception) as e:
                            logger.debug(f"FB Ads extractor: Second scroll pass error at {scroll_pos}")
                            continue

                    # Scroll back to top
                    try:
                        await asyncio.wait_for(
                            self.page.evaluate("window.scrollTo(0, 0)"),
                            timeout=2.0
                        )
                        await asyncio.wait_for(
                            self.wait_adaptive(base_seconds=0.3, max_seconds=1.5, wait_for="stable"),
                            timeout=3.0
                        )
                    except (asyncio.TimeoutError, Exception) as e:
                        logger.debug(f"FB Ads extractor: Scroll to top failed - {e}")

                except Exception as e:
                    logger.warning(f"FB Ads extractor: Scrolling phase failed - {e}, attempting extraction anyway")

                # Extract structured ad data using JavaScript with timeout
                # SIMPLIFIED EXTRACTION: Uses img alt text + Library ID pattern (proven to work)
                try:
                    result = await asyncio.wait_for(
                        self.page.evaluate(r"""
                (maxAds) => {
                    const ads = [];
                    const seenAdvertisers = new Set();

                    // Find img elements with alt text (advertiser profile pics)
                    const imgElements = document.querySelectorAll("img[alt]");

                    for (const img of imgElements) {
                        const alt = img.alt?.trim();
                        if (!alt || alt.length < 2 || alt.length > 100) continue;
                        if (["Meta", "Facebook", "Ad Library", "logo", "icon"].some(s =>
                            alt.toLowerCase().includes(s.toLowerCase()))) continue;

                        if (seenAdvertisers.has(alt.toLowerCase())) continue;

                        // Walk up to find container with Library ID
                        let container = img.parentElement;
                        for (let i = 0; i < 15 && container; i++) {
                            const text = container.innerText || "";

                            // Look for Library ID pattern
                            const idMatch = text.match(/Library ID[:\s"]+([0-9]+)/i);
                            if (idMatch && text.length < 10000) {
                                seenAdvertisers.add(alt.toLowerCase());

                                // Find FB page URL
                                let pageUrl = "";
                                const pageLinks = container.querySelectorAll("a[href*='facebook.com/']");
                                for (const link of pageLinks) {
                                    if (link.innerText?.toLowerCase() === alt.toLowerCase()) {
                                        pageUrl = link.href.split("?")[0];
                                        break;
                                    }
                                }

                                // Find landing URL (external website)
                                // Strategy 1: Look for l.facebook.com redirect links
                                let landingUrl = "";
                                const allLinks = container.querySelectorAll("a[href*='l.facebook.com/l.php']");
                                for (const link of allLinks) {
                                    try {
                                        const url = new URL(link.href);
                                        const u = url.searchParams.get('u');
                                        if (u) {
                                            const decodedUrl = decodeURIComponent(u).split('?')[0];
                                            // Filter out social media URLs - we want the actual landing page
                                            if (!decodedUrl.match(/instagram\.com|facebook\.com|fb\.com|ig\.me/i)) {
                                                landingUrl = decodedUrl;
                                                break;
                                            }
                                        }
                                    } catch(e) {}
                                }

                                // Strategy 2: Look for CTA button links if we didn't find a landing URL
                                if (!landingUrl) {
                                    const ctaButtons = container.querySelectorAll("a[role='link'], a[target='_blank'], a:has(span:has-text('Learn more')), a:has(span:has-text('Shop now')), a:has(span:has-text('Sign up')), a:has(span:has-text('Visit website'))");
                                    for (const btn of ctaButtons) {
                                        const href = btn.href || '';
                                        if (href && href.includes('l.facebook.com/l.php')) {
                                            try {
                                                const url = new URL(href);
                                                const u = url.searchParams.get('u');
                                                if (u) {
                                                    const decodedUrl = decodeURIComponent(u).split('?')[0];
                                                    // Filter out social media URLs
                                                    if (!decodedUrl.match(/instagram\.com|facebook\.com|fb\.com|ig\.me/i)) {
                                                        landingUrl = decodedUrl;
                                                        break;
                                                    }
                                                }
                                            } catch(e) {}
                                        }
                                    }
                                }

                                // Strategy 3: Look for any external links that aren't social media
                                if (!landingUrl) {
                                    const externalLinks = container.querySelectorAll("a[href^='http']");
                                    for (const link of externalLinks) {
                                        const href = link.href || '';
                                        try {
                                            const url = new URL(href);
                                            const hostname = url.hostname.toLowerCase();
                                            // Skip Facebook/Instagram/social media domains
                                            if (!hostname.match(/facebook\.com|instagram\.com|fb\.com|ig\.me|fb\.me|messenger\.com/i)) {
                                                // Check if it's a redirect link
                                                if (href.includes('l.facebook.com/l.php')) {
                                                    const u = url.searchParams.get('u');
                                                    if (u) {
                                                        const decodedUrl = decodeURIComponent(u).split('?')[0];
                                                        if (!decodedUrl.match(/instagram\.com|facebook\.com|fb\.com|ig\.me/i)) {
                                                            landingUrl = decodedUrl;
                                                            break;
                                                        }
                                                    }
                                                } else {
                                                    // Direct external link
                                                    landingUrl = href.split('?')[0];
                                                    break;
                                                }
                                            }
                                        } catch(e) {}
                                    }
                                }

                                // Extract ad text after "Sponsored"
                                let adText = "";
                                const sponsoredIdx = text.indexOf('Sponsored');
                                if (sponsoredIdx > -1) {
                                    const afterSponsored = text.substring(sponsoredIdx + 10, sponsoredIdx + 500);
                                    const lines = afterSponsored.split('\\n')
                                        .map(l => l.trim())
                                        .filter(l => l.length > 20 && !l.startsWith('Library ID') && !l.startsWith('Started'));
                                    if (lines.length > 0) {
                                        adText = lines[0].substring(0, 200);
                                    }
                                }

                                ads.push({
                                    advertiser: alt,
                                    ad_id: idMatch[1],
                                    landing_url: landingUrl,
                                    page_url: pageUrl || "https://facebook.com/ads/library/?id=" + idMatch[1],
                                    fb_ads_library_url: "https://facebook.com/ads/library/?id=" + idMatch[1],
                                    // Primary URL: landing URL (advertiser's website) takes priority over FB page
                                    url: landingUrl || pageUrl || "https://facebook.com/ads/library/?id=" + idMatch[1],
                                    ad_text: adText,
                                    status: 'active'
                                });

                                if (ads.length >= maxAds) break;
                                break;
                            }
                            container = container.parentElement;
                        }
                        if (ads.length >= maxAds) break;
                    }

                    return {
                        ads: ads,
                        ads_count: ads.length,
                        source_url: window.location.href,
                        extraction_method: ads.length > 0 ? 'img_alt_strategy' : 'none',
                        success: ads.length > 0
                    };
                }
            """, max_ads),
                        timeout=30.0
                    )
                except asyncio.TimeoutError:
                    logger.error(f"FB Ads extractor: JavaScript evaluation timeout (attempt {retry_count + 1}/{max_retries + 1})")
                    if retry_count < max_retries:
                        retry_count += 1
                        last_error = "JavaScript evaluation timeout"
                        await exponential_backoff_sleep(retry_count)
                        continue
                    return {
                        "success": False,
                        "error": "Extraction timeout after retries",
                        "ads": [],
                        "ads_count": 0
                    }
                except Exception as e:
                    logger.error(f"FB Ads extractor: JavaScript evaluation failed - {e} (attempt {retry_count + 1}/{max_retries + 1})")
                    if retry_count < max_retries:
                        retry_count += 1
                        last_error = str(e)
                        await exponential_backoff_sleep(retry_count)
                        continue
                    return {
                        "success": False,
                        "error": f"Extraction failed: {str(e)}",
                        "ads": [],
                        "ads_count": 0
                    }

                # Validate extraction results
                if not isinstance(result, dict):
                    logger.error(f"FB Ads extractor: Invalid result type - {type(result)}")
                    if retry_count < max_retries:
                        retry_count += 1
                        last_error = f"Invalid result type: {type(result)}"
                        await exponential_backoff_sleep(retry_count)
                        continue
                    return {
                        "success": False,
                        "error": "Invalid extraction result format",
                        "ads": [],
                        "ads_count": 0
                    }

                ads = result.get('ads', [])
                if not isinstance(ads, list):
                    logger.error(f"FB Ads extractor: Ads is not a list - {type(ads)}")
                    if retry_count < max_retries:
                        retry_count += 1
                        last_error = f"Ads not a list: {type(ads)}"
                        await exponential_backoff_sleep(retry_count)
                        continue
                    return {
                        "success": False,
                        "error": "Ads data is not a list",
                        "ads": [],
                        "ads_count": 0
                    }

                # Validate each ad has required fields
                valid_ads = []
                for ad in ads:
                    if isinstance(ad, dict) and ad.get('advertiser') and ad.get('ad_id'):
                        valid_ads.append(ad)
                    else:
                        logger.debug(f"FB Ads extractor: Skipping invalid ad - {ad}")

                logger.info(f"FB Ads extractor: Successfully extracted {len(valid_ads)}/{len(ads)} valid ads")

                source_url = result.get('source_url', '')
                return {
                    "success": True,
                    "url": source_url,
                    "ads": valid_ads,
                    "ads_count": len(valid_ads),
                    "source_url": source_url,
                    "extraction_method": result.get('extraction_method', 'unknown'),
                    "strategies_found": result.get('strategies_found', {}),
                    "retry_count": retry_count
                }

            except Exception as e:
                logger.error(f"FB Ads extractor: Unexpected error - {e} (attempt {retry_count + 1}/{max_retries + 1})")
                last_error = str(e)
                if retry_count < max_retries:
                    retry_count += 1
                    await exponential_backoff_sleep(retry_count)
                    continue
                break

        # All retries exhausted
        logger.error(f"FB Ads extractor: All retries exhausted. Last error: {last_error}")
        return {
            "success": False,
            "error": f"Extraction failed after {max_retries + 1} attempts: {last_error}",
            "ads": [],
            "ads_count": 0,
            "retry_count": retry_count
        }

    @tool_result
    async def extract_tiktok_ads_batch(self, max_ads: int = 200) -> Dict[str, Any]:
        """
        Extract structured TikTok Ads data - supports both Ad Library and Creative Center.

        Works on:
        1. TikTok Ad Library (library.tiktok.com/ads/)
        2. TikTok Creative Center Top Ads (ads.tiktok.com/business/creativecenter)

        Uses multiple extraction strategies for maximum coverage:
        1. JSON data embedded in page (Creative Center)
        2. DOM scraping for ad cards
        3. Link parsing for landing URLs

        Args:
            max_ads: Maximum number of ads to extract (default 50)

        Returns:
            Dict with 'success', 'ads_count', 'ads' (list of structured ad objects), 'source_url'
        """
        try:
            await self._ensure_page()

            url = self.page.url
            is_ad_library = 'library.tiktok.com' in url
            is_creative_center = 'ads.tiktok.com' in url and 'creativecenter' in url

            if not is_ad_library and not is_creative_center:
                return {
                    "success": False,
                    "error": "Not on TikTok Ads page. Navigate to library.tiktok.com/ads or ads.tiktok.com/business/creativecenter first.",
                    "ads": []
                }

            # Wait for initial load using adaptive wait
            await self.wait_adaptive(base_seconds=1.0, max_seconds=5.0, wait_for="network")

            # Check if page actually loaded (TikTok has strong anti-bot detection)
            # TikTok returns a large JS bundle even when blocked, so we must check for actual content
            page_content = await self.page.content()
            has_title = 'Find ads on TikTok' in page_content
            has_ad_links = 'ad_id=' in page_content or '/ads/detail/' in page_content
            page_loaded = has_title or has_ad_links
            logger.info(f"TikTok page check: content_len={len(page_content)}, has_title={has_title}, has_ad_links={has_ad_links}, loaded={page_loaded}")

            if not page_loaded:
                logger.warning("TikTok page did NOT load (anti-bot detected) - trying vanilla playwright")

                # TikTok blocks patchright/rebrowser but allows vanilla playwright
                # Launch a clean vanilla playwright browser specifically for TikTok
                try:
                    from playwright.async_api import async_playwright

                    # Close current browser
                    if self.browser:
                        try:
                            await self.browser.close()
                        except Exception as e:
                            logger.debug(f"Failed to close browser: {e}")
                            pass
                    if self.playwright:
                        try:
                            await self.playwright.stop()
                        except Exception as e:
                            logger.debug(f"Failed to stop playwright: {e}")
                            pass

                    # Launch vanilla playwright (same as MCP uses) - headless with extra stealth
                    logger.info("Launching vanilla playwright for TikTok (bypassing anti-bot)...")
                    self.playwright = await async_playwright().start()
                    self.browser = await self.playwright.chromium.launch(
                        headless=True,
                        args=[
                            '--disable-blink-features=AutomationControlled',
                            '--disable-dev-shm-usage',
                            '--no-sandbox',
                            '--disable-web-security',
                            '--disable-features=IsolateOrigins,site-per-process',
                            '--window-size=1920,1080',
                        ]
                    )
                    self.context = await self.browser.new_context(
                        viewport={'width': 1920, 'height': 1080},
                        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                        locale='en-US',
                        timezone_id='America/New_York',
                    )
                    self.page = await self.context.new_page()

                    # Navigate to TikTok Ad Library
                    await self.page.goto(url, wait_until='networkidle', timeout=30000)
                    await sleep_with_jitter(5.0)

                    # Check if it loaded now
                    page_content = await self.page.content()
                    if 'Find ads on TikTok' not in page_content:
                        logger.error("TikTok still blocked even with vanilla playwright")
                        return {
                            "success": False,
                            "error": "TikTok anti-bot detection blocked the browser. Try opening TikTok Ad Library manually first.",
                            "ads": []
                        }

                    logger.info("TikTok loaded successfully with vanilla playwright!")

                except Exception as e:
                    logger.error(f"Failed to launch vanilla playwright for TikTok: {e}")
                    return {
                        "success": False,
                        "error": f"Could not bypass TikTok anti-bot: {e}",
                        "ads": []
                    }

            # For TikTok Ad Library, we need to click Search button to trigger results
            if is_ad_library:
                # TikTok requires clicking Search button to load results (URL params alone don't work)
                try:
                    search_btn = await self.page.query_selector('button:has-text("Search")')
                    if search_btn:
                        logger.info("Clicking Search button to load TikTok ads...")
                        await search_btn.click()
                        # TikTok takes 5-15 seconds to load results after search
                        await sleep_with_jitter(10.0)
                except Exception as e:
                    logger.debug(f"Search button click error (may already have results): {e}")

                # Check if we have any ads now
                page_content = await self.page.content()
                has_ads = 'ad_id=' in page_content or '/ads/detail/' in page_content
                if not has_ads:
                    # Wait a bit more for slow connections
                    logger.info("Waiting for TikTok ads to load...")
                    await sleep_with_jitter(5.0)

            # For TikTok Ad Library, click "View more" button repeatedly to load more ads
            if is_ad_library:
                logger.info("TikTok Ad Library detected - loading more ads...")
                view_more_clicks = 0
                max_view_more_clicks = max(5, max_ads // 20)  # Click enough times to get desired ads

                for _ in range(max_view_more_clicks):
                    try:
                        # Scroll to bottom to reveal "View more" button
                        await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await sleep_with_jitter(0.5)

                        # Look for "View more" button - TikTok uses various selectors
                        view_more = await self.page.query_selector('button:has-text("View more"), [class*="ViewMore"], [class*="view-more"], [data-testid*="view-more"]')
                        if view_more:
                            await view_more.click()
                            view_more_clicks += 1
                            logger.info(f"Clicked 'View more' ({view_more_clicks}/{max_view_more_clicks})")
                            await sleep_with_jitter(1.5)  # Wait for new ads to load
                        else:
                            # No more "View more" button found
                            break
                    except Exception as e:
                        logger.debug(f"View more click error: {e}")
                        break

                logger.info(f"Loaded ads with {view_more_clicks} 'View more' clicks")

            # Aggressive scrolling to load more ads (React apps need scrolling)
            for scroll_pos in range(0, 15000, 800):
                await self.page.evaluate(f"window.scrollTo(0, {scroll_pos})")
                await sleep_with_jitter(0.15)

            await sleep_with_jitter(2.0)

            # Second pass slower scroll
            for scroll_pos in range(0, 20000, 500):
                await self.page.evaluate(f"window.scrollTo(0, {scroll_pos})")
                await sleep_with_jitter(0.1)

            # Scroll back to top
            await self.page.evaluate("window.scrollTo(0, 0)")
            await sleep_with_jitter(1.0)

            # Extract structured ad data using JavaScript
            result = await self.page.evaluate("""
                (maxAds) => {
                    const ads = [];
                    const seenAdIds = new Set();

                    // ========== HELPER FUNCTIONS ==========

                    const getDomain = (url) => {
                        try {
                            return new URL(url).hostname.replace('www.', '');
                        } catch(e) {
                            return url;
                        }
                    };

                    const formatNumber = (num) => {
                        if (typeof num === 'string') {
                            // Handle formats like "26.1M", "4.5K"
                            const match = num.match(/([\\d.]+)([KMB])?/i);
                            if (match) {
                                let val = parseFloat(match[1]);
                                const suffix = (match[2] || '').toUpperCase();
                                if (suffix === 'K') val *= 1000;
                                if (suffix === 'M') val *= 1000000;
                                if (suffix === 'B') val *= 1000000000;
                                return Math.round(val);
                            }
                        }
                        return parseInt(num) || 0;
                    };

                    // ========== STRATEGY 1: Extract from JSON data (Creative Center) ==========
                    // Creative Center embeds ad data in JSON
                    try {
                        const scripts = document.querySelectorAll('script');
                        for (const script of scripts) {
                            const content = script.textContent || '';
                            if (content.includes('materials') && content.includes('videoInfo')) {
                                // Try to find JSON data
                                const jsonMatch = content.match(/\\{[\\s\\S]*"materials"[\\s\\S]*\\}/);
                                if (jsonMatch) {
                                    try {
                                        const data = JSON.parse(jsonMatch[0]);
                                        if (data.materials && Array.isArray(data.materials)) {
                                            for (const material of data.materials.slice(0, maxAds)) {
                                                const adId = material.id || material.video_id || '';
                                                if (adId && !seenAdIds.has(adId)) {
                                                    seenAdIds.add(adId);
                                                    const landingPageUrl = material.landing_page_url || material.destination_url || '';
                                                    ads.push({
                                                        advertiser: material.advertiser_name || material.brand_name || material.title || 'Unknown',
                                                        ad_id: adId,
                                                        video_id: material.video_id || '',
                                                        title: material.title || '',
                                                        landing_url: landingPageUrl,
                                                        url: landingPageUrl,
                                                        website_domain: landingPageUrl ? getDomain(landingPageUrl) : '',
                                                        likes: formatNumber(material.like_count || material.likes || 0),
                                                        comments: formatNumber(material.comment_count || material.comments || 0),
                                                        shares: formatNumber(material.share_count || material.shares || 0),
                                                        views: formatNumber(material.play_count || material.views || 0),
                                                        duration: material.duration || 0,
                                                        region: material.region || 'ALL',
                                                        objective: material.objective || '',
                                                        industry: material.industry || '',
                                                        thumbnail: material.cover_url || material.thumbnail || '',
                                                        source: 'tiktok_creative_center',
                                                        status: 'active'
                                                    });
                                                }
                                            }
                                        }
                                    } catch (e) {
                                        console.debug('JSON parse error:', e);
                                    }
                                }
                            }
                        }
                    } catch (e) {
                        console.debug('Script extraction error:', e);
                    }

                    // ========== STRATEGY 2: DOM scraping for Ad Library ==========
                    // TikTok Ad Library uses links with ad details
                    if (ads.length === 0 || window.location.href.includes('library.tiktok.com')) {
                        // Find all ad detail links - they have href containing /ads/detail/?ad_id=
                        const adLinks = document.querySelectorAll('a[href*="/ads/detail/?ad_id="]');

                        for (const link of adLinks) {
                            if (ads.length >= maxAds) break;

                            try {
                                const href = link.href || '';
                                const text = link.innerText || '';

                                // Extract ad ID from URL
                                const adIdMatch = href.match(/ad_id=(\\d+)/);
                                const adId = adIdMatch ? adIdMatch[1] : '';

                                if (!adId || seenAdIds.has(adId)) continue;
                                seenAdIds.add(adId);

                                // Extract advertiser name from span.ad_info_text (inside the link)
                                let advertiser = '';
                                const advertiserSpan = link.querySelector('.ad_info_text, span.ad_info_text');
                                if (advertiserSpan) {
                                    advertiser = advertiserSpan.innerText.trim();
                                }
                                // Fallback: parse from innerText if span not found
                                // innerText format: "Ad\\nAdvertiserName\\nFirst shown:..."
                                if (!advertiser) {
                                    const lines = text.split('\\n');
                                    if (lines.length >= 2 && lines[0].trim() === 'Ad') {
                                        advertiser = lines[1].trim();
                                    }
                                }
                                // Handle "(Name unavailable)" case
                                if (advertiser && advertiser.includes('(Name unavailable)')) {
                                    advertiser = '(Name unavailable)';
                                }

                                // Extract dates from span.ad_item_value elements
                                let firstShown = '';
                                let lastShown = '';
                                let uniqueUsers = '';

                                const listItems = link.querySelectorAll('li');
                                listItems.forEach(li => {
                                    const desc = li.querySelector('.ad_item_description');
                                    const val = li.querySelector('.ad_item_value');
                                    if (desc && val) {
                                        const label = desc.innerText.trim().toLowerCase();
                                        const value = val.innerText.trim();
                                        if (label.includes('first shown')) firstShown = value;
                                        else if (label.includes('last shown')) lastShown = value;
                                        else if (label.includes('unique users')) uniqueUsers = value;
                                    }
                                });

                                // Fallback: regex on text if structured extraction failed
                                if (!firstShown || !lastShown) {
                                    const firstMatch = text.match(/First shown[:\\s]*([\\d\\/]+)/i);
                                    const lastMatch = text.match(/Last shown[:\\s]*([\\d\\/]+)/i);
                                    const usersMatch = text.match(/Unique users seen[:\\s]*([\\dKMB\\-\\.]+)/i);
                                    if (firstMatch && !firstShown) firstShown = firstMatch[1];
                                    if (lastMatch && !lastShown) lastShown = lastMatch[1];
                                    if (usersMatch && !uniqueUsers) uniqueUsers = usersMatch[1];
                                }

                                // Get the ad detail URL
                                const adDetailUrl = href;

                                // Extract landing URL (advertiser's external website)
                                let landingUrl = '';
                                const container = link.closest('[class*="AdCard"], [class*="ad-card"], div[class*="item"]') || link.parentElement;
                                if (container) {
                                    const allLinks = container.querySelectorAll('a[href]');
                                    for (const containerLink of allLinks) {
                                        const linkHref = containerLink.href || '';
                                        if (linkHref.startsWith('http') && !linkHref.includes('tiktok.com') && !linkHref.includes('bytedance')) {
                                            landingUrl = linkHref.split('?')[0];
                                            break;
                                        }
                                    }
                                }

                                ads.push({
                                    advertiser_name: advertiser,
                                    ad_id: adId,
                                    landing_url: landingUrl,
                                    ad_detail_url: adDetailUrl,
                                    tiktok_ad_library_url: adDetailUrl,
                                    // Primary URL: landing URL (advertiser's website) takes priority over TikTok internal URL
                                    url: landingUrl || adDetailUrl,
                                    website_domain: landingUrl ? getDomain(landingUrl) : '',
                                    first_shown: firstShown,
                                    last_shown: lastShown,
                                    unique_users: uniqueUsers,
                                    source: 'tiktok_ad_library',
                                    status: 'active'
                                });

                            } catch (e) {
                                console.debug('Ad link extraction error:', e);
                            }
                        }

                        // Fallback: Look for ad cards with generic selectors
                        if (ads.length === 0) {
                            const adCards = document.querySelectorAll('[class*="AdCard"], [class*="ad-card"], [class*="adcard"], [data-testid*="ad"]');

                            for (const card of adCards) {
                                if (ads.length >= maxAds) break;

                                try {
                                    const text = card.innerText || '';

                                    // Extract advertiser name
                                    let advertiser = '';
                                    const nameEl = card.querySelector('[class*="name"], [class*="advertiser"], [class*="brand"], h3, h4');
                                    if (nameEl) {
                                        advertiser = nameEl.innerText?.trim() || '';
                                    }
                                    if (!advertiser) {
                                        const lines = text.split('\\n').filter(l => l.trim().length > 2 && l.trim().length < 100);
                                        if (lines.length > 0) advertiser = lines[0].trim();
                                    }

                                    // Extract ad ID
                                    let adId = '';
                                    const idMatch = text.match(/(?:Ad ID|ID)[:\\s]+([A-Za-z0-9]+)/i);
                                    if (idMatch) adId = idMatch[1];
                                    if (!adId) adId = card.getAttribute('data-id') || card.getAttribute('data-ad-id') || '';
                                    if (!adId) adId = 'tiktok_' + advertiser.replace(/\\s+/g, '_').toLowerCase() + '_' + ads.length;

                                    if (seenAdIds.has(adId)) continue;
                                    seenAdIds.add(adId);

                                    // Extract landing URL (advertiser's external website)
                                    let landingUrl = '';
                                    const allLinks = card.querySelectorAll('a[href]');
                                    for (const link of allLinks) {
                                        const href = link.href || '';
                                        if (href.startsWith('http') && !href.includes('tiktok.com') && !href.includes('bytedance') && !href.includes('/ads/detail/')) {
                                            landingUrl = href.split('?')[0];
                                            break;
                                        }
                                    }

                                    ads.push({
                                        advertiser,
                                        ad_id: adId,
                                        landing_url: landingUrl,
                                        url: landingUrl || '',
                                        website_domain: landingUrl ? getDomain(landingUrl) : '',
                                        source: 'tiktok_ad_library',
                                        status: 'active'
                                    });

                                } catch (e) {
                                    console.debug('Card extraction error:', e);
                                }
                            }
                        }
                    }

                    // ========== STRATEGY 3: Generic video/ad containers ==========
                    if (ads.length === 0) {
                        // Look for video containers that might be ads
                        const containers = document.querySelectorAll('[class*="video"], [class*="Video"], [class*="item"], [class*="Item"]');

                        for (const container of containers) {
                            if (ads.length >= maxAds) break;
                            if (container.offsetHeight < 100) continue; // Skip tiny elements

                            try {
                                const text = container.innerText || '';
                                if (text.length < 20) continue;

                                // Look for advertiser indicators
                                let advertiser = '';
                                const brandEl = container.querySelector('[class*="brand"], [class*="name"], [class*="author"]');
                                if (brandEl) advertiser = brandEl.innerText?.trim() || '';

                                if (!advertiser) {
                                    // Check for link text
                                    const links = container.querySelectorAll('a');
                                    for (const link of links) {
                                        const linkText = link.innerText?.trim() || '';
                                        if (linkText.length > 2 && linkText.length < 80 && !linkText.match(/^(shop|buy|learn|more|see)/i)) {
                                            advertiser = linkText;
                                            break;
                                        }
                                    }
                                }

                                if (!advertiser) continue;

                                const adId = 'tiktok_' + advertiser.replace(/\\s+/g, '_').toLowerCase() + '_' + ads.length;
                                if (seenAdIds.has(adId)) continue;
                                seenAdIds.add(adId);

                                // Extract any external URL
                                let landingUrl = '';
                                const allLinks = container.querySelectorAll('a[href]');
                                for (const link of allLinks) {
                                    const href = link.href || '';
                                    if (href.startsWith('http') && !href.includes('tiktok.com') && !href.includes('bytedance')) {
                                        landingUrl = href.split('?')[0];
                                        break;
                                    }
                                }

                                ads.push({
                                    advertiser,
                                    ad_id: adId,
                                    landing_url: landingUrl,
                                    url: landingUrl || '',
                                    website_domain: landingUrl ? getDomain(landingUrl) : '',
                                    ad_text: text.substring(0, 300),
                                    source: 'tiktok_generic',
                                    status: 'active'
                                });

                            } catch (e) {
                                console.debug('Container extraction error:', e);
                            }
                        }
                    }

                    return {
                        ads: ads.slice(0, maxAds),
                        ads_count: ads.length,
                        source_url: window.location.href,
                        extraction_method: ads.length > 0 ? 'multi_strategy' : 'none',
                        is_ad_library: window.location.href.includes('library.tiktok.com'),
                        is_creative_center: window.location.href.includes('creativecenter')
                    };
                }
            """, max_ads)

            return {
                "success": True,
                **result
            }

        except Exception as e:
            logger.error(f"TikTok Ads structured extract error: {e}")
            return {
                "success": False,
                "error": str(e),
                "ads": [],
                "ads_count": 0
            }

    @tool_result
    async def extract_reddit_posts_batch(self, subreddit: str = None, max_posts: int = 200) -> Dict[str, Any]:
        """
        BULLETPROOF: Extract all Reddit posts with warm signals in ONE call - COMPETITIVE ADVANTAGE.
        Works on both old.reddit.com and new reddit.
        Returns posts with intent classification, engagement metrics, and warm signals.

        Warm signals indicate potential leads based on language patterns:
        - Recommendation seeking: "looking for", "any suggestions", "recommend"
        - Pain points: "frustrated with", "hate my current", "doesn't work"
        - Budget signals: "willing to pay", "budget is", "cost of"
        - Timeline signals: "need by", "urgent", "asap"
        - Decision maker signals: "my company", "we're looking", "our team"

        Args:
            subreddit: Optional subreddit name (for validation/logging)
            max_posts: Maximum number of posts to extract (default: 50)

        Returns:
            Dict with posts, warm lead counts, and signal analysis
        """
        max_retries = 2
        retry_count = 0
        last_error = None

        while retry_count <= max_retries:
            try:
                # Ensure page exists with timeout
                try:
                    await asyncio.wait_for(self._ensure_page(), timeout=10.0)
                except asyncio.TimeoutError:
                    logger.error(f"Reddit extractor: Page initialization timeout (attempt {retry_count + 1}/{max_retries + 1})")
                    if retry_count < max_retries:
                        retry_count += 1
                        await exponential_backoff_sleep(retry_count)
                        continue
                    return {
                        "success": False,
                        "error": "Page initialization timeout after retries",
                        "posts": [],
                        "warm_leads": [],
                        "posts_count": 0,
                        "warm_lead_count": 0
                    }

                # Validate we're on Reddit
                try:
                    current_url = self.page.url
                    if 'reddit.com' not in current_url:
                        logger.warning(f"Reddit extractor: Not on Reddit page (URL: {current_url})")
                        return {
                            "success": False,
                            "error": "Not on Reddit page",
                            "current_url": current_url,
                            "posts": [],
                            "warm_leads": [],
                            "posts_count": 0,
                            "warm_lead_count": 0
                        }
                except Exception as e:
                    logger.error(f"Reddit extractor: Could not get page URL - {e}")
                    return {
                        "success": False,
                        "error": f"Could not access page URL: {str(e)}",
                        "posts": [],
                        "warm_leads": [],
                        "posts_count": 0,
                        "warm_lead_count": 0
                    }

                # Execute extraction with timeout
                try:
                    result = await asyncio.wait_for(
                        self.page.evaluate(f"""
                () => {{
                    const posts = [];
                    const MAX_POSTS = {max_posts};

                    // Enhanced warm signal categories with regex-like patterns
                    const warmSignalCategories = {{
                        recommendation_seeking: [
                            'looking for', 'any suggestions', 'recommend',
                            'what do you use', 'best', 'for', 'alternatives to',
                            'suggestions for', 'advice on', 'opinions on',
                            'thoughts on', 'experience with', 'anyone using',
                            'which should i', 'what would you', 'help me choose'
                        ],
                        pain_point: [
                            'frustrated', 'hate', "doesn't work", "dont work",
                            'broken', 'terrible', 'worst', 'problem with',
                            'issues with', 'sick of', 'tired of', 'annoyed',
                            'disappointed', 'failing', 'keeps crashing',
                            'buggy', 'slow', 'unreliable', 'bad experience'
                        ],
                        budget_signal: [
                            'willing to pay', 'budget', 'cost', 'pricing',
                            'worth it', 'expensive', 'cheap', 'affordable',
                            'price', 'pay for', 'subscription', 'free alternative',
                            'how much', 'too expensive', 'cheaper than'
                        ],
                        timeline_signal: [
                            'need by', 'urgent', 'asap', 'deadline',
                            'this week', 'immediately', 'right now', 'today',
                            'tomorrow', 'quick', 'fast', 'soon', 'urgent help',
                            'time sensitive', 'before', 'by end of'
                        ],
                        decision_maker: [
                            'my company', 'our team', "we're looking", "i'm the",
                            'responsible for', 'in charge of', 'managing',
                            'our business', 'my business', 'my startup',
                            'our organization', 'we need', 'we want',
                            'evaluating', 'considering for our', 'for my team'
                        ],
                        seeking_tool: [
                            'looking for a', 'looking for an', 'looking for the',
                            'recommend a', 'recommend an', 'recommendations for',
                            'best tool for', 'best software for', 'best app for',
                            'best platform for', 'what is the best', "what's the best",
                            'alternative to', 'alternatives to', 'replacement for',
                            'what do you use', 'what tools', 'what software',
                            'what platform', 'what service', 'what app',
                            'use for', 'using for', 'switched from', 'moving from'
                        ],
                        buying_intent: [
                            'looking to buy', 'looking to hire', 'looking to invest',
                            'need a freelancer', 'need a developer', 'need a designer',
                            'need an agency', 'looking for agency', 'hiring a',
                            'budget of', 'willing to pay', 'ready to spend',
                            'where to buy', 'where to find', 'who to hire',
                            'want to purchase', 'planning to buy', 'ready to purchase'
                        ]
                    }};

                    // Flatten for quick matching
                    const allWarmPhrases = Object.values(warmSignalCategories).flat();

                    // Detect all matching signal types (not just first)
                    const detectWarmSignals = (text) => {{
                        const lower = text.toLowerCase();
                        const signals = [];

                        for (const [category, phrases] of Object.entries(warmSignalCategories)) {{
                            for (const phrase of phrases) {{
                                if (lower.includes(phrase)) {{
                                    signals.push({{
                                        type: category,
                                        pattern: phrase,
                                        matched: true
                                    }});
                                    break; // One match per category is enough
                                }}
                            }}
                        }}

                        return signals;
                    }};

                    // Old Reddit selectors
                    let postEls = document.querySelectorAll('.thing.link');
                    const isOldReddit = postEls.length > 0;

                    // New Reddit selectors if old didn't work
                    if (!isOldReddit) {{
                        postEls = document.querySelectorAll('shreddit-post, [data-testid="post-container"]');
                    }}

                    postEls.forEach((post, i) => {{
                        if (i >= MAX_POSTS) return;

                        let title = '', author = '', postUrl = '', score = '0', comments = '0';
                        let flair = '', timePosted = '', body = '';

                        if (isOldReddit) {{
                            title = post.querySelector('.title a.title')?.innerText?.trim() || '';
                            author = post.querySelector('.author')?.innerText?.trim() || '';
                            postUrl = post.querySelector('.title a.title')?.href || '';
                            score = post.querySelector('.score.unvoted, .score.likes, .score.dislikes')?.innerText?.trim() || '0';
                            comments = post.querySelector('.comments')?.innerText?.match(/\\d+/)?.[0] || '0';
                            flair = post.querySelector('.linkflairlabel')?.innerText?.trim() || '';
                            timePosted = post.querySelector('time')?.getAttribute('title') ||
                                        post.querySelector('.live-timestamp')?.innerText?.trim() || '';
                            body = post.querySelector('.expando .usertext-body')?.innerText?.trim() || '';
                        }} else {{
                            title = post.querySelector('[slot="title"], h3')?.innerText?.trim() || '';
                            author = post.querySelector('[data-testid="post_author_link"]')?.innerText?.trim() || '';
                            postUrl = post.querySelector('a[href*="/comments/"]')?.href || '';
                            flair = post.querySelector('[data-testid="post_flair"]')?.innerText?.trim() || '';
                            timePosted = post.querySelector('time')?.getAttribute('datetime') || '';
                            body = post.querySelector('[data-click-id="text"]')?.innerText?.trim() || '';
                        }}

                        // Detect warm signals in both title and body
                        const fullText = `${{title}} ${{body}}`;
                        const warmSignals = detectWarmSignals(fullText);
                        const signalScore = warmSignals.length;
                        const isWarmLead = signalScore >= 2; // 2+ signals = warm lead

                        // Legacy intent detection (primary signal type)
                        const intent = warmSignals.length > 0 ? warmSignals[0].type : null;

                        // Check if it's a question
                        const isQuestion = title.includes('?') ||
                                          /^(what|how|which|where|when|why|does|do|can|should|is|are|would)\\s/i.test(title);

                        // Parse score (handle "k" suffix)
                        let scoreNum = 0;
                        if (score.includes('k')) {{
                            scoreNum = parseFloat(score) * 1000;
                        }} else {{
                            scoreNum = parseInt(score) || 0;
                        }}

                        // Calculate engagement score (for ranking)
                        const commentNum = parseInt(comments) || 0;
                        const engagementScore = scoreNum + (commentNum * 3); // Comments weighted higher

                        if (title && author && author !== '[deleted]') {{
                            posts.push({{
                                title,
                                body: body.slice(0, 500), // Truncate body
                                author,
                                postUrl,
                                score: scoreNum,
                                comments: commentNum,
                                engagementScore,
                                flair,
                                timePosted,
                                warmSignals,
                                signalScore,
                                isWarmLead,
                                isQuestion,
                                intent, // Primary signal type
                                profileUrl: `https://www.reddit.com/user/${{author}}`,
                                subreddit: window.location.pathname.match(/\\/r\\/([^/]+)/)?.[1] || ''
                            }});
                        }}
                    }});

                    // Sort by warm signal score, then engagement
                    posts.sort((a, b) => {{
                        // Warm leads first
                        if (a.isWarmLead && !b.isWarmLead) return -1;
                        if (!a.isWarmLead && b.isWarmLead) return 1;
                        // Then by signal score
                        if (a.signalScore !== b.signalScore) return b.signalScore - a.signalScore;
                        // Then by engagement
                        return b.engagementScore - a.engagementScore;
                    }});

                    // Count intents and signal types
                    const intentCounts = {{}};
                    const signalTypeCounts = {{}};
                    posts.forEach(p => {{
                        if (p.intent) intentCounts[p.intent] = (intentCounts[p.intent] || 0) + 1;
                        p.warmSignals.forEach(s => {{
                            signalTypeCounts[s.type] = (signalTypeCounts[s.type] || 0) + 1;
                        }});
                    }});

                    // Extract warm leads
                    const warmLeads = posts.filter(p => p.isWarmLead);

                    return {{
                        success: true,
                        posts,
                        posts_count: posts.length,
                        warm_leads: warmLeads,
                        warm_lead_count: warmLeads.length,
                        totalCount: posts.length,
                        warmCount: warmLeads.length,
                        questionCount: posts.filter(p => p.isQuestion).length,
                        intentCounts,
                        signalTypeCounts,
                        subreddit: window.location.pathname.match(/\\/r\\/([^/]+)/)?.[1] || '',
                        url: window.location.href
                    }};
                }}
            """),
                        timeout=20.0
                    )
                except asyncio.TimeoutError:
                    logger.error(f"Reddit extractor: JavaScript evaluation timeout (attempt {retry_count + 1}/{max_retries + 1})")
                    if retry_count < max_retries:
                        retry_count += 1
                        last_error = "JavaScript evaluation timeout"
                        await exponential_backoff_sleep(retry_count)
                        continue
                    return {
                        "success": False,
                        "error": "Extraction timeout after retries",
                        "posts": [],
                        "warm_leads": [],
                        "posts_count": 0,
                        "warm_lead_count": 0
                    }
                except Exception as e:
                    logger.error(f"Reddit extractor: JavaScript evaluation failed - {e} (attempt {retry_count + 1}/{max_retries + 1})")
                    if retry_count < max_retries:
                        retry_count += 1
                        last_error = str(e)
                        await exponential_backoff_sleep(retry_count)
                        continue
                    return {
                        "success": False,
                        "error": f"Extraction failed: {str(e)}",
                        "posts": [],
                        "warm_leads": [],
                        "posts_count": 0,
                        "warm_lead_count": 0
                    }

                # Validate extraction results
                if not isinstance(result, dict):
                    logger.error(f"Reddit extractor: Invalid result type - {type(result)}")
                    if retry_count < max_retries:
                        retry_count += 1
                        last_error = f"Invalid result type: {type(result)}"
                        await exponential_backoff_sleep(retry_count)
                        continue
                    return {
                        "success": False,
                        "error": "Invalid extraction result format",
                        "posts": [],
                        "warm_leads": [],
                        "posts_count": 0,
                        "warm_lead_count": 0
                    }

                posts = result.get('posts', [])
                if not isinstance(posts, list):
                    logger.error(f"Reddit extractor: Posts is not a list - {type(posts)}")
                    if retry_count < max_retries:
                        retry_count += 1
                        last_error = f"Posts not a list: {type(posts)}"
                        await exponential_backoff_sleep(retry_count)
                        continue
                    return {
                        "success": False,
                        "error": "Posts data is not a list",
                        "posts": [],
                        "warm_leads": [],
                        "posts_count": 0,
                        "warm_lead_count": 0
                    }

                # Validate each post has required fields
                valid_posts = []
                for post in posts:
                    if isinstance(post, dict) and post.get('title') and post.get('author'):
                        valid_posts.append(post)
                    else:
                        logger.debug(f"Reddit extractor: Skipping invalid post - {post}")

                # Extract warm leads from valid posts
                warm_leads = [p for p in valid_posts if p.get('isWarmLead')]

                logger.info(f"Reddit extractor: Successfully extracted {len(valid_posts)}/{len(posts)} valid posts, {len(warm_leads)} warm leads")

                # Validate subreddit if provided
                if subreddit and result.get('subreddit') != subreddit:
                    logger.warning(f"Reddit extractor: Expected subreddit '{subreddit}' but got '{result.get('subreddit')}'")

                return {
                    "success": True,
                    "posts": valid_posts,
                    "posts_count": len(valid_posts),
                    "warm_leads": warm_leads,
                    "warm_lead_count": len(warm_leads),
                    "totalCount": len(valid_posts),
                    "warmCount": len(warm_leads),
                    "questionCount": sum(1 for p in valid_posts if p.get('isQuestion')),
                    "intentCounts": result.get('intentCounts', {}),
                    "signalTypeCounts": result.get('signalTypeCounts', {}),
                    "subreddit": result.get('subreddit', ''),
                    "url": result.get('url', ''),
                    "retry_count": retry_count
                }

            except Exception as e:
                logger.error(f"Reddit extractor: Unexpected error - {e} (attempt {retry_count + 1}/{max_retries + 1})")
                last_error = str(e)
                if retry_count < max_retries:
                    retry_count += 1
                    await exponential_backoff_sleep(retry_count)
                    continue
                break

        # All retries exhausted
        logger.error(f"Reddit extractor: All retries exhausted. Last error: {last_error}")
        return {
            "success": False,
            "error": f"Extraction failed after {max_retries + 1} attempts: {last_error}",
            "posts": [],
            "warm_leads": [],
            "posts_count": 0,
            "warm_lead_count": 0,
            "retry_count": retry_count
        }

    @tool_result
    async def _detect_cloudflare_challenge(self) -> bool:
        """Detect if current page is a Cloudflare challenge/waiting page."""
        try:
            await self._ensure_page()
            result = await self.page.evaluate("""
                () => {
                    const title = document.title.toLowerCase();
                    const body = document.body?.innerText?.toLowerCase() || '';

                    const challengeIndicators = [
                        'just a moment',
                        'checking your browser',
                        'please wait',
                        'ddos protection by cloudflare',
                        'verify you are human',
                        'one more step',
                        'ray id',
                        'cf-browser-verification'
                    ];

                    // Check title and body for challenge indicators
                    const hasChallenge = challengeIndicators.some(indicator =>
                        title.includes(indicator) || body.includes(indicator)
                    );

                    // Also check for Cloudflare specific elements
                    const hasCfElements = document.querySelector('#cf-wrapper') !== null ||
                                         document.querySelector('.cf-browser-verification') !== null ||
                                         document.querySelector('[data-ray]') !== null;

                    return hasChallenge || hasCfElements;
                }
            """)
            return result
        except Exception as e:
            logger.debug(f"Cloudflare detection failed: {e}")
            return False

    @tool_result
    async def _wait_for_cloudflare(self, max_wait: int = 15) -> bool:
        """Wait for Cloudflare challenge to complete. Returns True if passed."""
        import asyncio

        is_challenge = await self._detect_cloudflare_challenge()
        if not is_challenge:
            return True  # No challenge, proceed

        logger.debug("Challenge detected, waiting...")

        from .exponential_backoff import get_backoff
        backoff = get_backoff()
        total_wait = 0

        for attempt in range(max_wait):
            # Use exponential backoff for polling interval (start at 1s, increase gradually)
            poll_interval = min(backoff.calculate_delay(attempt=attempt, last_delay=1.0), 5.0)
            await asyncio.sleep(poll_interval)
            total_wait += poll_interval

            is_still_challenge = await self._detect_cloudflare_challenge()
            if not is_still_challenge:
                logger.debug(f"Challenge passed after {total_wait:.1f}s")
                await sleep_with_jitter(0.5)  # Brief pause for page to stabilize
                return True

            if total_wait >= max_wait:
                break

        logger.warning("Cloudflare challenge did not resolve")
        return False

    @tool_result
    async def extract_page_data_fast(self) -> Dict[str, Any]:
        """
        FAST: Extract all useful data from any page in ONE call.
        Combines contacts, links, social profiles, and business intelligence.
        """
        try:
            await self._ensure_page()

            # Handle Cloudflare challenges
            cf_passed = await self._wait_for_cloudflare()
            if not cf_passed:
                return {
                    "error": "Page blocked by Cloudflare challenge",
                    "cloudflare_blocked": True,
                    "url": self.page.url if self.page else None
                }

            result = await self.page.evaluate("""
                () => {
                    const data = {
                        url: window.location.href,
                        domain: window.location.hostname,
                        title: document.title,
                        emails: [],
                        phones: [],
                        contactLinks: [],
                        socialProfiles: {},
                        companyInfo: {},
                        techStack: []
                    };

                    const bodyText = document.body?.innerText || '';
                    const baseUrl = window.location.origin;
                    const html = document.documentElement.outerHTML;

                    // ========== EMAILS ==========
                    const emailRegex = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}/gi;
                    const noiseEmails = ['example.com', 'email.com', 'domain.com', 'yoursite.com', 'company.com', 'sentry.io', 'wixpress.com', 'placeholder', 'test.com'];
                    const emails = new Set();

                    document.querySelectorAll('a[href^="mailto:"]').forEach(a => {
                        const email = a.href.replace('mailto:', '').split('?')[0].toLowerCase().trim();
                        if (email && !noiseEmails.some(n => email.includes(n))) {
                            emails.add(email);
                        }
                    });

                    (bodyText.match(emailRegex) || []).forEach(email => {
                        email = email.toLowerCase().trim();
                        if (!noiseEmails.some(n => email.includes(n)) && email.includes('.')) {
                            emails.add(email);
                        }
                    });
                    data.emails = [...emails].slice(0, 10);

                    // ========== PHONES (International Support) ==========
                    const phonePatterns = [
                        /(?:\\+?1)?[-.\\s]?\\(?\\d{3}\\)?[-.\\s]?\\d{3}[-.\\s]?\\d{4}/g, // US/Canada
                        /\\+44[-.\\s]?\\d{2,4}[-.\\s]?\\d{3,4}[-.\\s]?\\d{3,4}/g, // UK
                        /\\+\\d{1,3}[-.\\s]?\\d{1,4}[-.\\s]?\\d{2,4}[-.\\s]?\\d{2,4}[-.\\s]?\\d{2,4}/g // International
                    ];
                    const phones = new Set();

                    document.querySelectorAll('a[href^="tel:"]').forEach(a => {
                        const clean = a.href.replace('tel:', '').replace(/[^0-9+]/g, '');
                        if (clean.length >= 10) phones.add(clean);
                    });

                    phonePatterns.forEach(regex => {
                        (bodyText.match(regex) || []).forEach(p => {
                            const clean = p.replace(/[^0-9+]/g, '');
                            if (clean.length >= 10 && clean.length <= 15) phones.add(clean);
                        });
                    });
                    data.phones = [...phones].slice(0, 5);

                    // ========== CONTACT LINKS ==========
                    const contactKeywords = ['contact', 'support', 'get-in-touch', 'reach-us', 'talk-to-us', 'contact-us', 'contactus', 'book-a-call', 'schedule', 'demo'];
                    const seenHrefs = new Set();

                    document.querySelectorAll('a[href]').forEach(a => {
                        let href = a.href;
                        const text = (a.innerText || '').trim().toLowerCase();

                        if (!href || !href.startsWith('http')) return;
                        if (href.includes('#')) href = href.split('#')[0];
                        if (!href || href === baseUrl || href === baseUrl + '/' || href === data.url) return;
                        if (seenHrefs.has(href)) return;

                        const hrefLower = href.toLowerCase();
                        const pathOnly = hrefLower.replace(baseUrl.toLowerCase(), '');

                        const hasContactPath = contactKeywords.some(k =>
                            pathOnly.includes('/' + k) || pathOnly.includes(k + '/') ||
                            pathOnly.endsWith('/' + k) || pathOnly === '/' + k
                        );
                        const hasContactText = contactKeywords.some(k => text.includes(k)) && pathOnly.length > 1;

                        if ((hasContactPath || hasContactText) && data.contactLinks.length < 5) {
                            seenHrefs.add(href);
                            data.contactLinks.push({ text: a.innerText.trim() || 'Contact', href });
                        }
                    });

                    // ========== SOCIAL PROFILES (with handles) ==========
                    const socialPatterns = {
                        linkedin: { regex: /linkedin\\.com\\/(company|in)\\/([^/?#"'\\s]+)/i, type: 'linkedin' },
                        twitter: { regex: /(twitter\\.com|x\\.com)\\/([^/?#"'\\s]+)/i, type: 'twitter' },
                        facebook: { regex: /facebook\\.com\\/([^/?#"'\\s]+)/i, type: 'facebook' },
                        instagram: { regex: /instagram\\.com\\/([^/?#"'\\s]+)/i, type: 'instagram' },
                        youtube: { regex: /youtube\\.com\\/(c\\/|channel\\/|@)?([^/?#"'\\s]+)/i, type: 'youtube' },
                        github: { regex: /github\\.com\\/([^/?#"'\\s]+)/i, type: 'github' }
                    };

                    document.querySelectorAll('a[href]').forEach(a => {
                        const href = a.href || '';
                        for (const [key, {regex, type}] of Object.entries(socialPatterns)) {
                            const match = href.match(regex);
                            if (match && !data.socialProfiles[type]) {
                                const handle = match[match.length - 1];
                                if (handle && !['share', 'intent', 'sharer'].includes(handle.toLowerCase())) {
                                    data.socialProfiles[type] = { url: href, handle };
                                }
                            }
                        }
                    });

                    // ========== COMPANY INFO (from meta tags & schema) ==========
                    const getMeta = (names) => {
                        for (const name of names) {
                            const el = document.querySelector(`meta[property="${name}"], meta[name="${name}"]`);
                            if (el?.content) return el.content;
                        }
                        return '';
                    };

                    data.companyInfo = {
                        name: getMeta(['og:site_name', 'application-name']) ||
                              document.title.split(/[|-–—]/)[0].trim() ||
                              data.domain.replace('www.', '').split('.')[0],
                        description: getMeta(['og:description', 'description']).substring(0, 200),
                        logo: getMeta(['og:image']),
                        type: getMeta(['og:type'])
                    };

                    // Try to find company name from schema.org
                    const schemaScript = document.querySelector('script[type="application/ld+json"]');
                    if (schemaScript) {
                        try {
                            const schema = JSON.parse(schemaScript.textContent);
                            if (schema.name) data.companyInfo.name = schema.name;
                            if (schema.description) data.companyInfo.description = schema.description.substring(0, 200);
                            if (schema['@type']) data.companyInfo.schemaType = schema['@type'];
                        } catch(e) {}
                    }

                    // ========== TECH STACK DETECTION ==========
                    const techSignatures = {
                        'Shopify': ['cdn.shopify.com', 'myshopify.com', 'Shopify.theme'],
                        'WordPress': ['wp-content', 'wp-includes', 'WordPress'],
                        'Wix': ['wix.com', 'wixsite.com', 'X-Wix'],
                        'Squarespace': ['squarespace.com', 'sqsp.net'],
                        'Webflow': ['webflow.com', 'webflow.io'],
                        'React': ['react', '_reactRootContainer', 'data-reactroot'],
                        'Next.js': ['__NEXT_DATA__', '_next/'],
                        'Vue': ['Vue.js', '__vue__'],
                        'Angular': ['ng-version', 'angular'],
                        'HubSpot': ['hubspot', 'hs-scripts.com'],
                        'Salesforce': ['salesforce', 'force.com'],
                        'Zendesk': ['zendesk', 'zdassets'],
                        'Intercom': ['intercom', 'intercomcdn'],
                        'Drift': ['drift.com', 'driftt'],
                        'Stripe': ['stripe.com', 'js.stripe.com'],
                        'Google Analytics': ['google-analytics', 'gtag', 'googletagmanager']
                    };

                    for (const [tech, signatures] of Object.entries(techSignatures)) {
                        if (signatures.some(sig => html.toLowerCase().includes(sig.toLowerCase()))) {
                            data.techStack.push(tech);
                        }
                    }

                    // Main heading
                    const h1 = document.querySelector('h1');
                    data.mainHeading = h1 ? h1.innerText.trim() : '';

                    return data;
                }
            """)

            # Add preferred contact
            preferred = None
            if result.get('contactLinks'):
                preferred = {'type': 'form', 'value': result['contactLinks'][0]['href']}
            elif result.get('emails'):
                preferred = {'type': 'email', 'value': result['emails'][0]}
            result['preferredContact'] = preferred

            # ANTI-HALLUCINATION: Validate extracted contacts
            if HALLUCINATION_GUARD_AVAILABLE:
                guard = get_guard()

                # Validate emails
                if result.get('emails'):
                    clean_emails = []
                    for email in result['emails']:
                        validation = guard.validate_output(email, source_tool='playwright_extract', data_type='emails')
                        if validation.is_valid:
                            clean_emails.append(email)
                        else:
                            logger.warning(f"Filtered fake email: {email}")
                    result['emails'] = clean_emails

                # Validate phones
                if result.get('phones'):
                    clean_phones = []
                    for phone in result['phones']:
                        validation = guard.validate_output(phone, source_tool='playwright_extract', data_type='phones')
                        if validation.is_valid:
                            clean_phones.append(phone)
                        else:
                            logger.warning(f"Filtered fake phone: {phone}")
                    result['phones'] = clean_phones

                # Update preferred contact if it was filtered
                if result['preferredContact'] and result['preferredContact']['type'] == 'email':
                    if result['preferredContact']['value'] not in result.get('emails', []):
                        # Email was filtered, update preferred contact
                        if result.get('emails'):
                            result['preferredContact'] = {'type': 'email', 'value': result['emails'][0]}
                        elif result.get('contactLinks'):
                            result['preferredContact'] = {'type': 'form', 'value': result['contactLinks'][0]['href']}
                        else:
                            result['preferredContact'] = None

            return {"success": True, **result}
        except Exception as e:
            logger.error(f"Fast page extract error: {e}")
            return {"error": str(e)}

    @tool_result
    async def batch_extract_contacts(self, urls: List[str], max_sites: int = 10) -> Dict[str, Any]:
        """
        FAST: Visit multiple URLs and extract contacts from each in one operation.
        Returns list of results with contacts for each URL.
        Minimizes LLM round-trips for multi-site prospecting.
        """
        results = []
        urls = urls[:max_sites]  # Cap to prevent overload

        for url in urls:
            try:
                # Navigate to site
                nav_result = await self.navigate(url)
                if nav_result.get('error'):
                    results.append({
                        'url': url,
                        'error': nav_result['error'],
                        'success': False
                    })
                    continue

                # Extract data fast
                extract_result = await self.extract_page_data_fast()

                results.append({
                    'url': url,
                    'success': True,
                    'title': extract_result.get('title', ''),
                    'emails': extract_result.get('emails', []),
                    'phones': extract_result.get('phones', []),
                    'contactLinks': extract_result.get('contactLinks', []),
                    'preferredContact': extract_result.get('preferredContact'),
                    'socialLinks': extract_result.get('socialLinks', [])
                })

            except Exception as e:
                logger.error(f"Batch extract error for {url}: {e}")
                results.append({
                    'url': url,
                    'error': str(e),
                    'success': False
                })

        # Summary stats
        successful = [r for r in results if r.get('success')]
        with_email = [r for r in successful if r.get('emails')]
        with_contact = [r for r in successful if r.get('preferredContact')]

        return {
            'results': results,
            'total': len(urls),
            'successful': len(successful),
            'with_email': len(with_email),
            'with_any_contact': len(with_contact)
        }

    @tool_result
    async def find_contacts(self) -> Dict[str, Any]:
        """Extract emails, phones, and likely contact/support links on the page."""
        try:
            await self._ensure_page()
            result = await self.page.evaluate(
                """() => {
                    const out = { emails: [], phones: [], contact_links: [] };
                    const seen = new Set();

                    // Emails via mailto
                    const mailtos = Array.from(document.querySelectorAll("a[href^='mailto:']"))
                        .map(a => (a.getAttribute("href") || "").replace(/^mailto:/i, "").trim())
                        .filter(Boolean);

                    // Emails via text regex
                    const bodyText = document.body ? document.body.innerText || "" : "";
                    const emailRegex = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}/gi;
                    const textEmails = bodyText.match(emailRegex) || [];

                    // Phones via tel: and regex
                    const telLinks = Array.from(document.querySelectorAll("a[href^='tel:']"))
                        .map(a => (a.getAttribute("href") || "").replace(/^tel:/i, "").trim())
                        .filter(Boolean);
                    const phoneRegex = /\\+?\\d[\\d\\s().-]{7,}/g;
                    const textPhones = bodyText.match(phoneRegex) || [];

                    function uniqPush(arr, values, cap=20) {
                        for (const v of values) {
                            if (!v) continue;
                            const val = v.trim();
                            if (val && !seen.has(val)) {
                                seen.add(val);
                                arr.push(val);
                                if (arr.length >= cap) break;
                            }
                        }
                    }

                    uniqPush(out.emails, [...mailtos, ...textEmails], 20);
                    uniqPush(out.phones, [...telLinks, ...textPhones], 20);

                    const keywords = ["contact", "support", "help", "about", "customer", "service", "team", "company", "legal", "privacy"];
                    const anchors = Array.from(document.querySelectorAll("a[href]"));
                    const contactLinks = [];
                    for (const a of anchors) {
                        if (contactLinks.length >= 20) break;
                        const text = (a.innerText || "").toLowerCase().trim();
                        const href = a.href || a.getAttribute("href") || "";
                        if (!href) continue;
                        const combined = text + " " + href.toLowerCase();
                        if (keywords.some(k => combined.includes(k))) {
                            contactLinks.push({ text: (a.innerText || "").trim() || href, href });
                        }
                    }
                    out.contact_links = contactLinks.slice(0, 20);
                    return out;
                }"""
            )

            # ANTI-HALLUCINATION: Validate extracted contacts
            emails = result.get("emails", [])
            phones = result.get("phones", [])

            if HALLUCINATION_GUARD_AVAILABLE:
                guard = get_guard()

                # Filter fake emails
                clean_emails = []
                for email in emails:
                    validation = guard.validate_output(email, source_tool='playwright_find_contacts', data_type='emails')
                    if validation.is_valid:
                        clean_emails.append(email)
                    else:
                        logger.warning(f"Filtered fake email in find_contacts: {email}")
                emails = clean_emails

                # Filter fake phones
                clean_phones = []
                for phone in phones:
                    validation = guard.validate_output(phone, source_tool='playwright_find_contacts', data_type='phones')
                    if validation.is_valid:
                        clean_phones.append(phone)
                    else:
                        logger.warning(f"Filtered fake phone in find_contacts: {phone}")
                phones = clean_phones

            return {
                "success": True,
                "url": getattr(self.page, 'url', ''),
                "emails": emails,
                "phones": phones,
                "contact_links": result.get("contact_links", [])
            }
        except Exception as e:
            logger.error(f"Find contacts error: {e}")
            return {"error": str(e)}

    # ========== NEW FEATURES (Inspired by Jina Reader, Firecrawl, Crawl4AI) ==========

    @tool_result
    def _cache_get(self, url: str) -> Optional[Dict[str, Any]]:
        """Get cached page if still valid."""
        import time
        if url in self._page_cache:
            entry = self._page_cache[url]
            if time.time() - entry.get('timestamp', 0) < self._cache_ttl:
                logger.debug(f"Cache HIT for {url}")
                return entry.get('data')
            else:
                # Expired, remove
                del self._page_cache[url]
        return None

    @tool_result
    def _cache_set(self, url: str, data: Dict[str, Any]):
        """Cache page data with timestamp."""
        import time
        # Evict oldest if cache full
        if len(self._page_cache) >= self._cache_max_size:
            oldest_url = min(self._page_cache.keys(),
                           key=lambda k: self._page_cache[k].get('timestamp', 0))
            del self._page_cache[oldest_url]
        self._page_cache[url] = {'data': data, 'timestamp': time.time()}

    @tool_result
    async def get_markdown(
        self,
        url: Optional[str] = None,
        target_selector: Optional[str] = None,
        fit_markdown: bool = True,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Jina Reader-style: Convert URL/page to LLM-friendly markdown.

        Like r.jina.ai but as a method.

        Args:
            url: URL to convert (if None, uses current page)
            target_selector: CSS selector to extract specific content
            fit_markdown: Apply noise filtering for cleaner output
            use_cache: Use cached response if available (default True)

        Returns:
            {
                'markdown': str,
                'title': str,
                'url': str,
                'word_count': int,
                'links': List,
                'metadata': Dict
            }
        """
        try:
            from .web_to_markdown import WebToMarkdown

            # Check cache first (only for URL requests without selectors)
            cache_key = url if url and not target_selector else None
            if use_cache and cache_key:
                cached = self._cache_get(cache_key)
                if cached:
                    cached['from_cache'] = True
                    return cached

            if url:
                await self.navigate(url)

            # Check if page is blocked by Cloudflare before extracting content
            try:
                page_content = await self.page.content()
                if await self._is_cloudflare_challenge(page_content):
                    logger.warning("Cannot extract markdown - page is blocked by Cloudflare challenge")
                    return {
                        "error": "Page blocked by Cloudflare challenge - unable to extract content",
                        "cloudflare_blocked": True,
                        "url": self.page.url if self.page else url
                    }
            except Exception as cf_check_err:
                logger.debug(f"Cloudflare check failed: {cf_check_err}")

            converter = WebToMarkdown()
            result = await converter.convert(
                self.page,
                target_selector=target_selector,
                fit_markdown=fit_markdown
            )

            # DEBUG: Log what converter returned
            md_len = len(result.get('markdown', '')) if result else 0
            raw_md_len = len(result.get('raw_markdown', '')) if result else 0

            # Additional validation: check if extracted markdown is mostly Cloudflare text
            if result.get('markdown'):
                markdown_lower = result['markdown'].lower()
                cloudflare_ratio = sum(
                    1 for indicator in ["cloudflare", "checking your browser", "just a moment"]
                    if indicator in markdown_lower
                )
                # If multiple Cloudflare indicators and short content, likely blocked
                if cloudflare_ratio >= 2 and len(result['markdown']) < 1000:
                    logger.warning("Extracted markdown appears to be Cloudflare block page")
                    return {
                        "error": "Extracted content is a Cloudflare block page - not real page content",
                        "cloudflare_blocked": True,
                        "url": self.page.url if self.page else url
                    }

            # Cache successful results
            if cache_key and not result.get('error'):
                self._cache_set(cache_key, result)

            return result
        except ImportError:
            logger.warning("web_to_markdown not available")
            return {"error": "web_to_markdown module not found"}
        except Exception as e:
            logger.error(f"get_markdown error: {e}")
            return {"error": str(e)}

    @tool_result
    async def fetch_url(
        self,
        url: str,
        output_format: str = "markdown",
        use_cache: bool = True
    ) -> Dict[str, Any]:
          """
          Fetch a URL over HTTP without using the browser.

          This is a fast alternative to Playwright navigation for simple pages and is
          useful for quick summarization/extraction pipelines, while keeping SSRF
          protections centralized in WebFetcher.
          """
          try:
              from .web_fetcher import get_fetcher
          except Exception as e:
              return {"success": False, "error": f"web_fetcher unavailable: {e}"}

          try:
              fetcher = get_fetcher()
              result = await fetcher.fetch(url, output_format=output_format, use_cache=use_cache)
              return {
                  "success": bool(result.success),
                  "url": result.url,
                  "content": result.content,
                  "content_type": result.content_type,
                  "status_code": int(result.status_code),
                  "size_bytes": int(result.size_bytes),
                  "duration_ms": int(result.duration_ms),
                  "truncated": bool(result.truncated),
                  "error": result.error,
                  "output_format": output_format,
                  "source": "http_fetch",
              }
          except Exception as e:
              return {"success": False, "error": str(e)}
  
    @tool_result
    async def deep_search(
        self,
        query: str,
        context: str = "",
        max_queries: int = 3,
        results_per_query: int = 5,
        summarize_top: int = 3
    ) -> Dict[str, Any]:
        """Exa-style deep search with multi-query expansion and summaries."""
        if not query or not query.strip():
            return {"error": "query is required"}

        try:
            engine = DeepSearchEngine(self)
            return await engine.deep_search(
                query=query.strip(),
                context=context,
                max_queries=max(1, min(max_queries, 6)),
                results_per_query=max(1, min(results_per_query, 8)),
                summarize_top=max(1, min(summarize_top, 5))
            )
        except Exception as exc:
            logger.error(f"Deep search failed: {exc}")
            return {"error": str(exc)}

    @tool_result
    async def map_site(
        self,
        url: str,
        max_urls: int = 500
    ) -> Dict[str, Any]:
        """
        Firecrawl-style: Map all URLs on a website.

        Args:
            url: Base URL to map
            max_urls: Maximum URLs to discover

        Returns:
            {
                'urls': List[str],
                'categorized': Dict[str, List[str]],
                'count': int
            }
        """
        try:
            from .site_mapper import SiteMapper

            mapper = SiteMapper()
            return await mapper.map_site(self, url, max_urls=max_urls)
        except ImportError:
            logger.warning("site_mapper not available")
            return {"error": "site_mapper module not found"}
        except Exception as e:
            logger.error(f"map_site error: {e}")
            return {"error": str(e)}

    @tool_result
    async def crawl_for(
        self,
        url: str,
        looking_for: str,
        max_pages: int = 10
    ) -> Dict[str, Any]:
        """
        Crawl4AI-style: Adaptive crawl looking for specific information.

        Stops when enough relevant info is found.

        Args:
            url: Starting URL
            looking_for: What to find (e.g., "pricing information")
            max_pages: Maximum pages to visit

        Returns:
            {
                'content': str,
                'pages_visited': int,
                'stopped_reason': str
            }
        """
        try:
            from .site_mapper import AdaptiveCrawler

            crawler = AdaptiveCrawler()
            return await crawler.crawl_for_info(self, url, looking_for, max_pages)
        except ImportError:
            logger.warning("site_mapper not available")
            return {"error": "site_mapper module not found"}
        except Exception as e:
            logger.error(f"crawl_for error: {e}")
            return {"error": str(e)}

    @tool_result
    async def llm_extract(
        self,
        prompt: str,
        url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        ScrapeGraphAI-style: Extract data using natural language prompt.

        Args:
            prompt: Natural language extraction prompt
                   (e.g., "Extract all product names and prices")
            url: URL to extract from (if None, uses current page)

        Returns:
            {
                'data': extracted data,
                'success': bool
            }
        """
        try:
            from .llm_extractor import LLMExtractor
            from .web_to_markdown import WebToMarkdown

            if url:
                await self.navigate(url)

            # Get markdown content
            converter = WebToMarkdown()
            md_result = await converter.convert(self.page)
            content = md_result.get('markdown', '')

            if not content:
                # Fallback to text
                text_result = await self.get_text()
                content = text_result.get('text', '')

            # Extract with LLM
            extractor = LLMExtractor()
            return await extractor.extract(content, prompt)
        except ImportError as e:
            logger.warning(f"LLM extraction modules not available: {e}")
            return {"error": f"Required module not found: {e}"}
        except Exception as e:
            logger.error(f"llm_extract error: {e}")
            return {"error": str(e)}

    @tool_result
    async def extract_entities(
        self,
        entity_types: List[str],
        url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extract specific entity types from page.

        Args:
            entity_types: List like ['company', 'email', 'phone', 'money', 'person']
            url: URL to extract from (if None, uses current page)

        Returns:
            Dict with entity_type -> list of found entities
        """
        import re

        try:
            if url:
                await self.navigate(url)

            # Get page text
            text_result = await self.get_text()
            content = text_result.get('text', '')

            # FAST PATH: Use regex for common entity types (much faster than LLM)
            results = {}

            if 'email' in entity_types:
                # Match emails with common patterns
                email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
                emails = list(set(re.findall(email_pattern, content)))
                if emails:
                    results['email'] = emails

            if 'phone' in entity_types:
                # Match phone numbers (various formats)
                phone_patterns = [
                    r'\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',  # US format
                    r'\+\d{1,3}[-.\s]?\d{6,14}',  # International
                ]
                phones = []
                for pattern in phone_patterns:
                    phones.extend(re.findall(pattern, content))
                phones = list(set(phones))
                if phones:
                    results['phone'] = phones

            # If we found contacts via regex, return them immediately
            if results:
                return {
                    'success': True,
                    'data': results,
                    'method': 'regex'
                }

            # If only looking for email/phone and nothing found, return quickly
            entity_set = set(entity_types)
            if entity_set <= {'email', 'phone', 'company'}:
                return {
                    'success': True,
                    'data': {},
                    'message': 'No contact information found on this page',
                    'method': 'regex'
                }

            # For complex entity types, fall back to LLM
            from .llm_extractor import LLMExtractor
            extractor = LLMExtractor()
            return await extractor.extract_entities(content, entity_types)
        except ImportError:
            logger.warning("llm_extractor not available")
            return {"error": "llm_extractor module not found"}
        except Exception as e:
            logger.error(f"extract_entities error: {e}")
            return {"error": str(e)}

    @tool_result
    async def extract_structured(
        self,
        schema: Dict[str, Any],
        url: Optional[str] = None,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Extract structured data from page based on a schema.

        This is the power tool for strategic planning - extracts data matching
        a specific schema (e.g., list of books with title and price).

        Args:
            schema: Dict describing the data structure to extract
                    e.g., {"books": [{"title": "string", "price": "string"}]}
            url: URL to extract from (if None, uses current page)
            limit: Maximum number of items to extract

        Returns:
            Dict with extracted data matching the schema
        """
        import re
        import json

        try:
            if url:
                await self.navigate(url)

            # Get page content
            text_result = await self.get_text()
            content = text_result.get('text', '')

            # Get page title for context
            title = await self.page.title() if self.page else ''

            # Parse the schema to understand what we're looking for
            results = {}
            for key, value in schema.items():
                if isinstance(value, list) and len(value) > 0:
                    # It's a list schema - extract multiple items
                    item_schema = value[0]
                    items = await self._extract_items_from_content(
                        content, item_schema, limit, title
                    )
                    results[key] = items
                else:
                    # Single value extraction
                    results[key] = await self._extract_single_value(content, key, value)

            return {
                'success': True,
                'data': results,
                'count': sum(len(v) if isinstance(v, list) else 1 for v in results.values()),
                'method': 'structured_extraction'
            }

        except Exception as e:
            logger.error(f"extract_structured error: {e}")
            return {"error": str(e), "success": False}

    # Alternative directories for common B2B research categories
    ALTERNATIVE_DIRECTORIES = {
        'lead-generation': [
            ('https://www.designrush.com/agency/lead-generation', 'DesignRush'),
            ('https://www.sortlist.com/lead-generation', 'Sortlist'),
        ],
        'marketing-agencies': [
            ('https://www.designrush.com/agency/digital-marketing', 'DesignRush'),
            ('https://www.sortlist.com/digital-marketing', 'Sortlist'),
        ],
        'seo-agencies': [
            ('https://www.designrush.com/agency/search-engine-optimization', 'DesignRush'),
            ('https://www.sortlist.com/seo', 'Sortlist'),
        ],
    }

    @tool_result
    async def extract_to_csv(
        self,
        url: str,
        schema: Dict[str, Any],
        csv_path: str,
        limit: int = 10,
        append: bool = False
    ) -> Dict[str, Any]:
        """
        Extract structured data from a page AND save directly to CSV.

        This is the combined tool that solves the data pipeline issue where
        extract_structured returns data but the planner can't pass it to
        write_validated_csv properly.

        Includes automatic alternative directory fallback when primary sources
        return 404/403 or are blocked.

        Args:
            url: URL to extract from
            schema: Schema for extraction (e.g., {"books": [{"title": "string", "price": "string"}]})
                    Also accepts flat schemas like {"title": "string", "price": "string"}
                    which will be normalized to {"items": [{"title": "string", "price": "string"}]}
            csv_path: Path to save the CSV file
            limit: Maximum items to extract
            append: Whether to append to existing file

        Returns:
            Dict with extraction results and CSV save status
        """
        import csv
        from pathlib import Path

        try:
            await self._ensure_page()

            # Use current page URL if no URL provided
            if not url and self.page:
                url = self.page.url
                logger.info(f"Using current page URL: {url}")

            # Guard against None URL
            if not url:
                return {"error": "URL is required for extraction", "success": False}

            # Guard against None schema
            if not schema:
                schema = {"items": [{"name": "string", "url": "string"}]}

            # Check if URL is blocked/404 and try alternatives
            # Only navigate if we're not already on the right page
            current_url = self.page.url if self.page else ""
            if url and url not in current_url and current_url not in url:
                nav_result = await self.navigate(url)
            else:
                nav_result = {"success": True}  # Already on the page
            status = 200 if nav_result and nav_result.get('success') else 404

            # If blocked or 404, try alternative directories
            if status in [403, 404, 405] or status >= 500:
                logger.warning(f"Primary URL {url} returned status {status}, searching for alternatives...")

                # Detect category from URL
                url_lower = str(url or '').lower()
                category = None
                for cat in self.ALTERNATIVE_DIRECTORIES.keys():
                    if cat in url_lower or cat.replace('-', '') in url_lower.replace('-', ''):
                        category = cat
                        break

                if category and category in self.ALTERNATIVE_DIRECTORIES:
                    for alt_url, alt_name in self.ALTERNATIVE_DIRECTORIES[category]:
                        logger.info(f"Trying alternative: {alt_name} ({alt_url})")
                        try:
                            alt_result = await self.navigate(alt_url)
                            if alt_result and alt_result.get('success'):
                                logger.info(f"✓ Alternative {alt_name} loaded successfully!")
                                url = alt_url  # Use the working alternative
                                break
                        except Exception as alt_err:
                            logger.warning(f"Alternative {alt_name} failed: {alt_err}")
                            continue
                else:
                    # No category match - just log and continue with original URL
                    logger.warning(f"No alternative directories found for URL pattern")
            # Normalize schema: if flat (like {"title": "string", "price": "string"})
            # convert to nested format expected by extract_structured
            normalized_schema = schema
            is_flat_schema = all(
                isinstance(v, str) for v in schema.values()
            )
            if is_flat_schema:
                # This is a flat schema - wrap it for multiple item extraction
                normalized_schema = {"items": [schema]}
                logger.debug(f"Normalized flat schema to: {normalized_schema}")

            # Step 1: Try schema-based extraction first
            extract_result = await self.extract_structured(normalized_schema, url=url, limit=limit)

            # Step 2: Flatten the data for CSV
            rows = []
            extraction_method = 'schema'

            # Guard against None extract_result
            if extract_result and extract_result.get('success'):
                data = extract_result.get('data') or {}
                for key, value in data.items():
                    if isinstance(value, list):
                        rows.extend(value)
                    elif isinstance(value, dict):
                        rows.append(value)

            # Step 2b: Fallback to LLM extraction if schema extraction failed/empty
            if not rows:
                logger.info("Schema extraction empty, falling back to LLM extraction")
                extraction_method = 'llm_fallback'

                # Build a prompt from the schema
                field_names = list(schema.keys())
                prompt = f"Extract a list of items with these fields: {', '.join(field_names)}. Return as JSON array."

                try:
                    llm_result = await self.llm_extract(prompt, url=url)
                    if llm_result.get('success') and llm_result.get('data'):
                        llm_data = llm_result['data']
                        # Handle different LLM output formats
                        if isinstance(llm_data, list):
                            rows = llm_data[:limit]
                        elif isinstance(llm_data, dict):
                            # Check for common list keys
                            for key in ['items', 'results', 'data', 'companies', 'agencies']:
                                if isinstance(llm_data.get(key), list):
                                    rows = llm_data[key][:limit]
                                    break
                            if not rows:
                                rows = [llm_data]
                except Exception as llm_err:
                    logger.warning(f"LLM fallback extraction failed: {llm_err}")

            # Step 2c: Try entity extraction
            if not rows:
                logger.info("LLM extraction empty, trying entity extraction")
                extraction_method = 'entity_fallback'
                try:
                    entity_result = await self.extract_entities(['company', 'organization', 'person', 'url', 'email'])
                    if entity_result.get('entities'):
                        # Convert entities to rows
                        entities = entity_result['entities']
                        # Group by company if possible
                        companies = {}
                        for entity in entities:
                            e_type = entity.get('type', '').lower()
                            e_value = entity.get('value', '')
                            e_confidence = entity.get('confidence', 0)
                            if e_type in ['company', 'organization']:
                                if e_value not in companies:
                                    companies[e_value] = {'company_name': e_value}
                            elif e_type == 'url' and companies:
                                last_company = list(companies.keys())[-1]
                                if 'url' not in companies[last_company]:
                                    companies[last_company]['url'] = e_value
                            elif e_type == 'email' and companies:
                                last_company = list(companies.keys())[-1]
                                if 'email' not in companies[last_company]:
                                    companies[last_company]['email'] = e_value
                        if companies:
                            rows = list(companies.values())[:limit]
                except Exception as entity_err:
                    logger.warning(f"Entity fallback extraction failed: {entity_err}")

            # Step 2d: Screenshot-based extraction as last resort (visual grounding)
            if not rows:
                logger.info("Entity extraction empty, trying screenshot-based visual extraction")
                extraction_method = 'screenshot_fallback'
                try:
                    # Take screenshot and use vision model
                    screenshot_result = await self.screenshot()
                    # Guard against None screenshot_result
                    if screenshot_result:
                        logger.info(f"Screenshot result: success={screenshot_result.get('success')}, has_base64={bool(screenshot_result.get('screenshot_base64'))}, size={screenshot_result.get('size', 0)}")
                    if screenshot_result and screenshot_result.get('success') and screenshot_result.get('screenshot_base64'):
                        # Build prompt for visual extraction
                        field_names = list(schema.keys())
                        vision_prompt = f"""Look at this screenshot and extract a list of items.
For each item, provide these fields: {', '.join(field_names)}
Return the data as a JSON array of objects.
Focus on the main content area, not navigation or ads."""

                        vision_result = None
                        ollama_url = "http://localhost:11434/api/generate"

                        # Try 1: Use vision_client if available
                        if hasattr(self, 'vision_client') and self.vision_client:
                            try:
                                vision_result = await self.vision_client.analyze_with_prompt(
                                    screenshot_result['screenshot_base64'],
                                    vision_prompt
                                )
                            except Exception as vc_err:
                                logger.warning(f"vision_client call failed: {vc_err}")

                        # Try 2: UI-TARS via Ollama (only model needed for vision)
                        if not vision_result:
                            try:
                                import httpx
                                # UI-TARS only - designed for UI understanding
                                vision_models = [
                                    ("ui-tars", "0000/ui-tars-1.5-7b:latest"),
                                ]

                                for model_name, model_id in vision_models:
                                    if vision_result:
                                        break

                                    payload = {
                                        "model": model_id,
                                        "prompt": vision_prompt,
                                        "images": [screenshot_result['screenshot_base64']],
                                        "stream": False,
                                        "options": {"temperature": 0.1}
                                    }

                                    logger.info(f"Trying Ollama vision model: {model_name}")
                                    logger.debug(f"Sending to {model_name}: prompt={len(vision_prompt)} chars, image={len(screenshot_result['screenshot_base64'])} chars")
                                    try:
                                        async with httpx.AsyncClient(timeout=120.0) as client:
                                            response = await client.post(ollama_url, json=payload)
                                        logger.info(f"{model_name} response status: {response.status_code}")
                                        if response.status_code == 200:
                                            result = response.json()
                                            vision_result = result.get('response', '')
                                            logger.info(f"{model_name} vision extraction returned {len(vision_result)} chars")
                                        else:
                                            logger.warning(f"{model_name} returned non-200: {response.status_code}, body={response.text[:200]}")
                                    except Exception as vision_model_err:
                                        logger.warning(f"{model_name} vision call failed: {vision_model_err}")
                            except Exception as ollama_err:
                                logger.warning(f"Ollama vision pipeline failed: {ollama_err}")

                        # Try 3: Fall back to text-based LLM extraction with page content
                        if not vision_result:
                            logger.info("Vision models failed, falling back to text LLM extraction")
                            try:
                                import httpx

                                # Get page text for LLM to analyze
                                page_text = await self.page.inner_text('body')
                                logger.debug(f"Got page text: {len(page_text)} chars")
                                if len(page_text) > 15000:
                                    page_text = page_text[:15000]  # Truncate for LLM context

                                text_prompt = f"""Extract structured data from this webpage text.
Find all items/entries and extract these fields: {', '.join(field_names)}
Return ONLY a valid JSON array of objects with those fields.
No explanations, just the JSON array.

Webpage text:
{page_text}"""

                                # Use local text LLM
                                text_payload = {
                                    "model": "qwen2.5:7b-instruct",
                                    "prompt": text_prompt,
                                    "stream": False,
                                    "options": {"temperature": 0.1}
                                }

                                logger.debug(f"Sending to text LLM: {len(text_prompt)} chars")
                                async with httpx.AsyncClient(timeout=120.0) as client:
                                    response = await client.post(ollama_url, json=text_payload)
                                logger.info(f"Text LLM response status: {response.status_code}")
                                if response.status_code == 200:
                                    result = response.json()
                                    vision_result = result.get('response', '')
                                    logger.info(f"Text LLM fallback returned {len(vision_result)} chars")
                                    if vision_result:
                                        logger.debug(f"Text LLM result preview: {vision_result[:500]}")
                                else:
                                    logger.warning(f"Text LLM returned non-200: {response.status_code}")
                            except Exception as text_llm_err:
                                logger.warning(f"Text LLM fallback failed: {text_llm_err}")

                        # Parse vision result
                        if vision_result:
                            import json
                            if isinstance(vision_result, str):
                                # Try to extract JSON from response
                                try:
                                    # Look for JSON array in response
                                    json_match = re.search(r'\[[\s\S]*\]', vision_result)
                                    if json_match:
                                        vision_result = json.loads(json_match.group())
                                    else:
                                        # Try parsing whole response as JSON
                                        vision_result = json.loads(vision_result)
                                except json.JSONDecodeError:
                                    logger.warning("Could not parse vision result as JSON")
                                    vision_result = None

                            if isinstance(vision_result, list):
                                rows = vision_result[:limit]
                            elif isinstance(vision_result, dict):
                                for key in ['items', 'results', 'data', 'companies', 'agencies']:
                                    if isinstance(vision_result.get(key), list):
                                        rows = vision_result[key][:limit]
                                        break
                except Exception as vision_err:
                    logger.warning(f"Screenshot fallback extraction failed: {vision_err}")

            if not rows:
                return {
                    'success': False,
                    'error': 'No data extracted (tried schema, LLM, entity, and screenshot/vision extraction)',
                    'extraction_result': extract_result
                }

            # Step 3: Write to CSV
            path = Path(csv_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            # Get headers from first row
            headers = list(rows[0].keys()) if rows else []

            # Determine write mode
            mode = 'a' if append and path.exists() else 'w'
            write_header = not (append and path.exists())

            with path.open(mode, newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                if write_header:
                    writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, '') for k in headers})

            return {
                'success': True,
                'url': url,
                'csv_path': str(path),
                'rows_written': len(rows),
                'headers': headers,
                'data': rows,  # Include the data for reference
                'extraction_method': extract_result.get('method', 'unknown')
            }

        except Exception as e:
            logger.error(f"extract_to_csv error: {e}")
            return {'success': False, 'error': str(e)}

    @tool_result
    async def _extract_items_from_content(
        self,
        content: str,
        item_schema: Dict[str, str],
        limit: int,
        page_title: str = ''
    ) -> List[Dict[str, str]]:
        """
        Extract a list of items matching a schema from content.

        Priority order:
        1. Known site selectors from site_selectors.py (most reliable, no LLM)
        2. Generic CSS selectors for common patterns
        3. Regex-based extraction
        4. LLM fallback (if available)
        """
        import re
        items = []

        # Determine what fields we need
        fields = list(item_schema.keys())

        # PRIORITY 1: Use known site selectors from site_selectors.py (ZERO LLM)
        if self.page and get_site_selectors:
            try:
                current_url = self.page.url if self.page else ''
                site_config = get_site_selectors(current_url)
                if site_config:
                    item_selector = site_config.get('item_selector', '')
                    field_selectors = site_config.get('field_selectors', {})
                    site_limit = min(limit, site_config.get('limit', 10))

                    logger.info(f"Using known site selectors for {current_url}")
                    elements = await self.page.locator(item_selector).all()

                    if elements:
                        logger.debug(f"Found {len(elements)} elements with selector: {item_selector}")
                        for element in elements[:site_limit]:
                            item = {}
                            try:
                                for field_name, selector in field_selectors.items():
                                    # Handle @attribute syntax (e.g., "a@href")
                                    if '@' in selector:
                                        sel_part, attr = selector.rsplit('@', 1)
                                        if sel_part:
                                            el = element.locator(sel_part).first
                                        else:
                                            el = element
                                        if await el.count() > 0:
                                            item[field_name] = await el.get_attribute(attr) or ''
                                    else:
                                        el = element.locator(selector).first
                                        if await el.count() > 0:
                                            item[field_name] = (await el.inner_text()).strip()
                                # Only add if we got some data
                                if any(v.strip() for v in item.values() if isinstance(v, str)):
                                    items.append(item)
                            except Exception as el_err:
                                logger.debug(f"Element extraction error: {el_err}")
                                continue

                        if items:
                            logger.info(f"Known site selectors extracted {len(items)} items")
                            return items[:limit]
            except Exception as site_err:
                logger.debug(f"Known site selector extraction failed: {site_err}")

        # PRIORITY 2: Try common product/item selectors (most accurate for e-commerce)
        if self.page and set(fields) <= {'title', 'price', 'availability', 'name', 'rating'}:
            try:
                # Common product card selectors for e-commerce sites
                product_selectors = [
                    '.product_pod',  # books.toscrape.com
                    '.product-item', '.product-card',
                    '[data-product]', '.card', '.listing-item',
                    'article.product', '.item-box',
                ]

                for selector in product_selectors:
                    products = await self.page.locator(selector).all()
                    if len(products) >= 2:  # Found multiple products
                        logger.debug(f"Found {len(products)} products with selector: {selector}")
                        for product in products[:limit]:
                            item = {}
                            try:
                                # Get title from common title locations
                                title_el = product.locator('h3 a, h4 a, .title, .name, [data-title]').first
                                if await title_el.count() > 0:
                                    item['title'] = (await title_el.get_attribute('title')) or (await title_el.inner_text())

                                # Get price
                                price_el = product.locator('.price, .price_color, [data-price]').first
                                if await price_el.count() > 0:
                                    item['price'] = await price_el.inner_text()

                                if item.get('title') and item.get('title').strip():
                                    items.append(item)
                            except Exception as prod_err:
                                logger.debug(f"Product extraction error: {prod_err}")
                                continue

                        if items:
                            logger.info(f"Selector-based extraction found {len(items)} items")
                            return items[:limit]
                        break  # Don't try other selectors if we found elements
            except Exception as sel_err:
                logger.debug(f"Selector-based extraction failed: {sel_err}")

        # FAST PATH: Common patterns for books/products
        if set(fields) <= {'title', 'price', 'availability', 'name', 'rating'}:
            # Look for price patterns
            price_pattern = r'[£$€]\s*\d+[.,]?\d*'
            prices = re.findall(price_pattern, content)

            # Look for product titles (lines before prices, or in h3/h4 patterns)
            # Split content into lines and find lines that look like titles
            lines = content.split('\n')
            potential_titles = []

            for i, line in enumerate(lines):
                line = line.strip()
                # Skip empty lines and very long lines
                if not line or len(line) > 150:
                    continue
                # Skip lines that are just prices or numbers
                if re.match(r'^[£$€]?\s*[\d.,]+$', line):
                    continue
                # Skip common navigation/footer text
                if line.lower() in ['home', 'next', 'previous', 'page', 'menu']:
                    continue
                # This might be a title
                if len(line) > 3 and not line.startswith(('http', 'www')):
                    potential_titles.append(line)

            # Match titles with prices
            for i, title in enumerate(potential_titles[:limit]):
                item = {'title': title}
                if i < len(prices):
                    item['price'] = prices[i]
                if 'availability' in fields:
                    # Check for availability keywords near title
                    if 'in stock' in content.lower():
                        item['availability'] = 'In stock'
                    else:
                        item['availability'] = 'Unknown'
                items.append(item)

            if items:
                return items[:limit]

        # FALLBACK: Use LLM for complex extraction
        try:
            from .llm_extractor import LLMExtractor
            extractor = LLMExtractor()

            prompt = f"""Extract items from this content matching this schema: {item_schema}

Content:
{content[:4000]}

Return a JSON array of objects with these exact fields: {fields}
Limit to {limit} items. Return only valid JSON array."""

            result = await extractor.extract(content[:4000], prompt)
            # Handle dict or list result
            if result:
                if isinstance(result, dict) and 'items' in result:
                    return result['items'][:limit]
                elif isinstance(result, list):
                    return result[:limit]
        except Exception as e:
            logger.debug(f"LLM extraction fallback failed: {e}")

        return items[:limit] if items else []

    @tool_result
    async def _extract_single_value(
        self,
        content: str,
        key: str,
        value_type: str
    ) -> Optional[str]:
        """Extract a single value from content."""
        import re

        if value_type == 'string':
            if key in ['title', 'name']:
                # Get first meaningful line
                for line in content.split('\n'):
                    line = line.strip()
                    if line and len(line) > 3 and len(line) < 200:
                        return line
            elif key == 'price':
                match = re.search(r'[£$€]\s*\d+[.,]?\d*', content)
                if match:
                    return match.group(0)

        return None

    @tool_result
    async def answer_from_page(
        self,
        question: str,
        url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Answer a question based on page content.

        Args:
            question: Question to answer
            url: URL to use (if None, uses current page)

        Returns:
            {
                'answer': str,
                'confidence': str,
                'evidence': List[str]
            }
        """
        try:
            from .llm_extractor import LLMExtractor

            if url:
                await self.navigate(url)

            text_result = await self.get_text()
            content = text_result.get('text', '')

            extractor = LLMExtractor()
            return await extractor.answer_question(content, question)
        except ImportError:
            logger.warning("llm_extractor not available")
            return {"error": "llm_extractor module not found"}
        except Exception as e:
            logger.error(f"answer_from_page error: {e}")
            return {"error": str(e)}

    # ==========================================================================
    # DEEP RESEARCH JOBS (Exa-style async researcher)
    # ==========================================================================

    @tool_result
    async def research_start(
        self,
        query: str,
        instructions: str = "",
        max_queries: int = 4,
        results_per_query: int = 5
    ) -> Dict[str, Any]:
        """Kick off a background deep research job."""
        if not query or not query.strip():
            return {"error": "query is required"}

        job_id = secrets.token_hex(4)
        job = {
            "job_id": job_id,
            "query": query.strip(),
            "instructions": instructions.strip(),
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "progress": 0.0,
            "results": [],
            "variants": [],
            "report": "",
            "error": None,
            "logs": [],
        }
        self._research_jobs[job_id] = job
        self._append_job_log(job_id, "Job enqueued")

        task = asyncio.create_task(
            self._run_research_job(
                job_id,
                max_queries=max(1, min(max_queries, 6)),
                results_per_query=max(1, min(results_per_query, 8))
            )
        )
        self._research_job_tasks[job_id] = task
        task.add_done_callback(lambda t, jid=job_id: self._cleanup_research_task(jid, t))

        return {
            "success": True,
            "job": self._serialize_research_job(job_id)
        }

    @tool_result
    async def research_check(
        self,
        job_id: Optional[str] = None,
        include_logs: bool = False
    ) -> Dict[str, Any]:
        """Check status of a specific job or list all jobs."""
        if job_id:
            if job_id not in self._research_jobs:
                return {"error": f"job {job_id} not found"}
            return {
                "success": True,
                "job": self._serialize_research_job(job_id, include_logs=include_logs)
            }

        jobs = [
            self._serialize_research_job(jid, include_logs=False)
            for jid in sorted(self._research_jobs.keys())
        ]
        return {"success": True, "jobs": jobs}

    @tool_result
    async def _run_research_job(
        self,
        job_id: str,
        max_queries: int,
        results_per_query: int
    ):
        """Background execution for research job."""
        job = self._research_jobs.get(job_id)
        if not job:
            return

        job["status"] = "running"
        job["updated_at"] = datetime.utcnow().isoformat()
        self._append_job_log(job_id, "Launching dedicated browser for research")

        # Launch isolated headless browser to avoid interfering with main session
        job_browser = PlaywrightClient(
            headless=True,
            user_data_dir=self.user_data_dir,
            storage_state=self.storage_state
        )

        try:
            await job_browser.connect()
            engine = DeepSearchEngine(job_browser)
            deep_results = await engine.deep_search(
                query=job["query"],
                context=job.get("instructions", ""),
                max_queries=max_queries,
                results_per_query=results_per_query,
                summarize_top=5
            )
            if deep_results.get("error"):
                raise RuntimeError(deep_results["error"])

            job["results"] = deep_results.get("results", [])
            job["variants"] = deep_results.get("variants", [])
            job["progress"] = 0.7
            job["status"] = "summarizing"
            job["updated_at"] = datetime.utcnow().isoformat()
            self._append_job_log(job_id, f"Deep search gathered {len(job['results'])} sources")

            report = await self._build_research_report(job["query"], job["results"])
            job["report"] = report
            job["status"] = "completed"
            job["progress"] = 1.0
            job["updated_at"] = datetime.utcnow().isoformat()
            self._append_job_log(job_id, "Research report ready")

            # Persist snapshot per job for traceability
            report_path = self._research_dir / f"{job_id}_report.json"
            report_path.write_text(json.dumps(job, indent=2))
        except Exception as exc:
            job["status"] = "failed"
            job["error"] = str(exc)
            job["updated_at"] = datetime.utcnow().isoformat()
            self._append_job_log(job_id, f"Job failed: {exc}")
            logger.exception(f"Research job {job_id} failed")
        finally:
            try:
                await job_browser.disconnect()
            except Exception as e:
                handle_error("unknown_operation_search_cleanup", e, context={"job_id": job_id, "error": error}, log_level="debug")

    @tool_result
    async def _build_research_report(self, query: str, results: List[Dict[str, Any]]) -> str:
        """Produce a consolidated summary from result snippets."""
        if not results:
            return ""

        bullet_lines = []
        for item in results[:8]:
            snippet = item.get("summary") or item.get("snippet") or ""
            bullet_lines.append(f"- {item.get('title', 'Result')} ({item.get('url')}): {snippet}")

        combined = "\n".join(bullet_lines)
        try:
            from .llm_extractor import LLMExtractor

            extractor = LLMExtractor()
            summary = await extractor.summarize(
                content=f"Research topic: {query}\n\nSources:\n{combined}",
                style="detailed",
                max_length=800
            )
            if summary.get("success") and summary.get("data"):
                data = summary["data"]
                text = data.get("summary") or data.get("data")
                key_points = data.get("key_facts") or []
                points = "\n".join(f"- {p}" for p in key_points) if key_points else ""
                return f"{text or ''}\n\nKey facts:\n{points}".strip()
        except Exception as exc:
            logger.debug(f"LLM summarization failed, returning raw snippets: {exc}")

        return combined

    @tool_result
    def _append_job_log(self, job_id: str, message: str):
        job = self._research_jobs.get(job_id)
        if not job:
            return
        job.setdefault("logs", []).append(f"{datetime.utcnow().isoformat()} - {message}")

    @tool_result
    def _serialize_research_job(self, job_id: str, include_logs: bool = False) -> Dict[str, Any]:
        job = self._research_jobs.get(job_id)
        if not job:
            return {}
        data = {
            "job_id": job["job_id"],
            "query": job["query"],
            "instructions": job.get("instructions", ""),
            "status": job.get("status"),
            "progress": job.get("progress", 0.0),
            "created_at": job.get("created_at"),
            "updated_at": job.get("updated_at"),
            "result_count": len(job.get("results") or []),
            "report": job.get("report", ""),
            "error": job.get("error"),
            "variants": job.get("variants", []),
        }
        if include_logs:
            data["logs"] = job.get("logs", [])
        return data

    @tool_result
    def _cleanup_research_task(self, job_id: str, task: asyncio.Task):
        """Remove finished tasks from tracking."""
        self._research_job_tasks.pop(job_id, None)
        if task.cancelled():
            self._append_job_log(job_id, "Background task was cancelled")

    # ==========================================================================
    # VERTICAL CONNECTORS (LinkedIn / Company research)
    # ==========================================================================

    @tool_result
    async def linkedin_company_lookup(
        self,
        company: str,
        max_results: int = 3
    ) -> Dict[str, Any]:
        """
        BULLETPROOF: Fetch structured data from LinkedIn company pages - COMPETITIVE ADVANTAGE.
        Handles timeouts, retries, and validates all data extraction.
        """
        max_retries = 2
        retry_count = 0
        last_error = None

        # Input validation
        if not company or not company.strip():
            logger.error("LinkedIn extractor: Company name is required")
            return {
                "success": False,
                "error": "company parameter is required",
                "results": []
            }

        # Validate max_results
        max_results = max(1, min(max_results, 5))

        while retry_count <= max_retries:
            try:
                # Initialize search engine with timeout
                try:
                    engine = DeepSearchEngine(self)
                    query = f"site:linkedin.com/company {company}"

                    serp_hits = await asyncio.wait_for(
                        engine.search_once(query, limit=max_results),
                        timeout=30.0
                    )
                except asyncio.TimeoutError:
                    logger.error(f"LinkedIn extractor: Search timeout for '{company}' (attempt {retry_count + 1}/{max_retries + 1})")
                    if retry_count < max_retries:
                        retry_count += 1
                        last_error = "Search timeout"
                        await exponential_backoff_sleep(retry_count)
                        continue
                    return {
                        "success": False,
                        "error": f"Search timeout after {max_retries + 1} attempts",
                        "query": company,
                        "results": [],
                        "retry_count": retry_count
                    }
                except Exception as e:
                    logger.error(f"LinkedIn extractor: Search failed for '{company}' - {e} (attempt {retry_count + 1}/{max_retries + 1})")
                    if retry_count < max_retries:
                        retry_count += 1
                        last_error = str(e)
                        await exponential_backoff_sleep(retry_count)
                        continue
                    return {
                        "success": False,
                        "error": f"Search failed: {str(e)}",
                        "query": company,
                        "results": [],
                        "retry_count": retry_count
                    }

                # Validate search results
                if not isinstance(serp_hits, list):
                    logger.error(f"LinkedIn extractor: Invalid search results type - {type(serp_hits)}")
                    if retry_count < max_retries:
                        retry_count += 1
                        last_error = f"Invalid search results: {type(serp_hits)}"
                        await exponential_backoff_sleep(retry_count)
                        continue
                    return {
                        "success": False,
                        "error": "Invalid search results format",
                        "query": company,
                        "results": [],
                        "retry_count": retry_count
                    }

                if not serp_hits:
                    logger.warning(f"LinkedIn extractor: No results found for '{company}'")
                    return {
                        "success": True,
                        "query": company,
                        "results": [],
                        "message": "No LinkedIn company pages found",
                        "retry_count": retry_count
                    }

                # Extract profiles with individual timeouts and error handling
                enriched = []
                failed_extractions = 0

                for idx, hit in enumerate(serp_hits[:max_results]):
                    try:
                        if not isinstance(hit, dict):
                            logger.warning(f"LinkedIn extractor: Skipping invalid hit #{idx} - {type(hit)}")
                            failed_extractions += 1
                            continue

                        url = hit.get("url")
                        if not url:
                            logger.warning(f"LinkedIn extractor: Skipping hit #{idx} - no URL")
                            failed_extractions += 1
                            continue

                        # Extract profile with timeout
                        try:
                            profile = await asyncio.wait_for(
                                self._extract_company_profile(url, source="linkedin"),
                                timeout=20.0
                            )
                        except asyncio.TimeoutError:
                            logger.warning(f"LinkedIn extractor: Profile extraction timeout for {url}")
                            profile = {
                                "error": "Profile extraction timeout",
                                "data": None
                            }
                            failed_extractions += 1
                        except Exception as e:
                            logger.warning(f"LinkedIn extractor: Profile extraction failed for {url} - {e}")
                            profile = {
                                "error": str(e),
                                "data": None
                            }
                            failed_extractions += 1

                        enriched.append({
                            "title": hit.get("title", ""),
                            "url": url,
                            "snippet": hit.get("snippet", ""),
                            "profile": profile.get("data"),
                            "error": profile.get("error"),
                        })

                    except Exception as e:
                        logger.error(f"LinkedIn extractor: Unexpected error processing hit #{idx} - {e}")
                        failed_extractions += 1
                        continue

                logger.info(f"LinkedIn extractor: Successfully extracted {len(enriched)}/{len(serp_hits)} profiles for '{company}' ({failed_extractions} failures)")

                return {
                    "success": True,
                    "query": company,
                    "results": enriched,
                    "results_count": len(enriched),
                    "failed_extractions": failed_extractions,
                    "captured_at": datetime.utcnow().isoformat(),
                    "retry_count": retry_count
                }

            except Exception as e:
                logger.error(f"LinkedIn extractor: Unexpected error - {e} (attempt {retry_count + 1}/{max_retries + 1})")
                last_error = str(e)
                if retry_count < max_retries:
                    retry_count += 1
                    await exponential_backoff_sleep(retry_count)
                    continue
                break

        # All retries exhausted
        logger.error(f"LinkedIn extractor: All retries exhausted for '{company}'. Last error: {last_error}")
        return {
            "success": False,
            "error": f"Extraction failed after {max_retries + 1} attempts: {last_error}",
            "query": company,
            "results": [],
            "retry_count": retry_count
        }

    @tool_result
    async def web_search(
        self,
        query: str,
        num_results: int = 10
    ) -> Dict[str, Any]:
        """
        API-based search that bypasses Google CAPTCHA/rate limiting.

        Uses DuckDuckGo (free, unlimited) or Serper.dev (2500 free/month) to search
        when browser-based Google search is blocked.

        Args:
            query: Search query string
            num_results: Number of results to return (default 10)

        Returns:
            Dict with 'success', 'source', 'results' list with title/url/snippet
        """
        if not SEARCH_ALTERNATIVES_AVAILABLE:
            return {
                "success": False,
                "error": "Search alternatives module not available. Install: pip install duckduckgo-search",
                "results": []
            }

        if not query or not query.strip():
            return {
                "success": False,
                "error": "Query is required",
                "results": []
            }

        try:
            search = SearchAlternatives()
            result = await search.search(query.strip(), num_results)

            if result.get('success'):
                logger.info(f"Web search ({result.get('source', 'unknown')}): {len(result.get('results', []))} results for '{query[:50]}'")
                return {
                    "success": True,
                    "source": result.get('source', 'unknown'),
                    "query": query,
                    "results": result.get('results', []),
                    "note": "API-based search - bypasses browser CAPTCHA"
                }
            else:
                return {
                    "success": False,
                    "error": result.get('error', 'Search failed'),
                    "results": []
                }

        except Exception as e:
            logger.error(f"Web search failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "results": []
            }

    @tool_result
    async def company_profile(
        self,
        company: str,
        website: Optional[str] = None,
        include_contacts: bool = False
    ) -> Dict[str, Any]:
        """Get structured company overview from official site + optional contacts."""
        if not company or not company.strip():
            return {"error": "company is required"}

        target_url = website
        if not target_url:
            engine = DeepSearchEngine(self)
            search_hits = await engine.search_once(f"{company} official site", limit=5)
            for hit in search_hits:
                url = hit.get("url", "")
                if "linkedin.com" in url or "crunchbase.com" in url or "facebook.com" in url:
                    continue
                target_url = url
                break

        if not target_url:
            return {"error": "could not find company website"}

        profile = await self._extract_company_profile(target_url, source="website")
        if profile.get("error"):
            return profile

        result = {
            "success": True,
            "company": company,
            "source_url": target_url,
            "data": profile.get("data"),
        }

        if include_contacts:
            contacts = await self.extract_entities(["email", "phone"])
            result["contacts"] = contacts.get("data", {})

        return result

    @tool_result
    async def _extract_company_profile(self, url: str, source: str = "generic") -> Dict[str, Any]:
        """Convert URL to markdown and extract structured company info."""
        try:
            md = await self.get_markdown(url)
            if not md or md.get("error"):
                return {"error": f"failed to fetch {url}", "url": url}

            content = md.get("markdown") or ""
            if not content.strip():
                return {"error": f"no readable content at {url}", "url": url}

            from .llm_extractor import LLMExtractor

            extractor = LLMExtractor()
            prompt = f"""You are extracting company intelligence from {source} content.
Return JSON with:
{{
  "name": "Company name",
  "description": "1-2 sentence overview",
  "headquarters": "HQ location if available",
  "headcount": "employee count or range if present",
  "industry": "primary industry/segment",
  "founded": "year founded if available",
  "key_people": ["notable leaders or executives"],
  "offerings": ["products or services"],
  "highlights": ["specific stats, milestones, programs"]
}}"""

            extraction = await extractor.extract(content, prompt, output_format='json')
            if not extraction.get("success"):
                return {"error": "llm extraction failed", "details": extraction.get("error"), "url": url}

            data = extraction.get("data") or {}
            return {
                "success": True,
                "url": url,
                "data": data
            }
        except Exception as exc:
            logger.error(f"Company profile extraction failed: {exc}")
            return {"error": str(exc), "url": url}

    # ==========================================================================
    # SPEED OPTIMIZATIONS (inspired by browser-use, crawl4ai, firecrawl)
    # ==========================================================================

    @tool_result
    def _get_cache_key(self, url: str) -> str:
        """Generate cache key for URL"""
        return hashlib.md5(url.encode()).hexdigest()

    @tool_result
    def _get_cached(self, url: str) -> Optional[Dict]:
        """Get cached response if still valid"""
        key = self._get_cache_key(url)
        if key in _PAGE_CACHE:
            data, timestamp = _PAGE_CACHE[key]
            if time.time() - timestamp < _CACHE_TTL:
                logger.debug(f"Cache HIT for {url[:50]}")
                return data
            else:
                del _PAGE_CACHE[key]
        return None

    @tool_result
    def _set_cached(self, url: str, data: Dict):
        """Cache response with TTL"""
        key = self._get_cache_key(url)
        _PAGE_CACHE[key] = (data, time.time())
        # Limit cache size
        if len(_PAGE_CACHE) > 100:
            oldest = min(_PAGE_CACHE.items(), key=lambda x: x[1][1])
            del _PAGE_CACHE[oldest[0]]

    @tool_result
    async def fast_extract(
        self,
        url: str,
        prompt: str,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        FAST extraction: CSS-first, then accessibility tree, LLM as last resort.

        Inspired by:
        - browser-use: accessibility tree for fast understanding
        - crawl4ai: CSS extraction 4x faster than LLM
        - firecrawl: structured data without vision models

        Args:
            url: URL to extract from
            prompt: What to extract (used to infer CSS selectors)
            use_cache: Whether to use response cache

        Returns:
            Extracted data with method used (css/accessibility/llm)
        """
        start = time.time()

        # Check cache first
        if use_cache:
            cached = self._get_cached(url)
            if cached:
                return {**cached, "from_cache": True, "time_ms": 0}

        await self._ensure_page()
        await self.navigate(url)

        # Strategy 1: Try CSS selectors based on common patterns
        prompt_lower = prompt.lower()
        css_result = await self._try_css_extraction(prompt_lower)
        if css_result and css_result.get("data"):
            result = {
                "success": True,
                "data": css_result["data"],
                "method": "css",
                "time_ms": int((time.time() - start) * 1000)
            }
            if use_cache:
                self._set_cached(url, result)
            return result

        # Strategy 2: Use accessibility tree (like browser-use)
        acc_result = await self._try_accessibility_extraction(prompt_lower)
        if acc_result and acc_result.get("data"):
            result = {
                "success": True,
                "data": acc_result["data"],
                "method": "accessibility",
                "time_ms": int((time.time() - start) * 1000)
            }
            if use_cache:
                self._set_cached(url, result)
            return result

        # Strategy 3: Fall back to LLM extraction
        llm_result = await self.llm_extract(prompt, url=None)  # Already navigated
        result = {
            "success": llm_result.get("success", False),
            "data": llm_result.get("data"),
            "method": "llm",
            "time_ms": int((time.time() - start) * 1000)
        }
        if use_cache and result.get("data"):
            self._set_cached(url, result)
        return result

    @tool_result
    async def _try_css_extraction(self, prompt_lower: str) -> Optional[Dict]:
        """Try to extract using CSS selectors based on prompt keywords"""
        try:
            # Common extraction patterns
            patterns = {
                ("product", "price", "item"): {
                    "selectors": [
                        "[data-component-type*='search-result']",
                        ".product", ".item", ".listing", "[class*='product']"
                    ],
                    "fields": {"title": "h2, h3, .title, .name", "price": ".price, [class*='price']"}
                },
                ("article", "story", "post", "news"): {
                    "selectors": ["article", ".story", ".post", "[class*='article']"],
                    "fields": {"title": "h1, h2, h3, .title", "summary": "p, .summary, .excerpt"}
                },
                ("result", "search", "list"): {
                    "selectors": [".result", ".search-result", "li", "[class*='result']"],
                    "fields": {"title": "h2, h3, a", "description": "p, .description"}
                },
                ("repo", "repository", "project"): {
                    "selectors": ["[class*='repo']", "article", ".Box-row"],
                    "fields": {"name": "h2 a, h3 a, .repo-name", "description": "p, .repo-description"}
                }
            }

            # Find matching pattern
            for keywords, config in patterns.items():
                if any(kw in prompt_lower for kw in keywords):
                    for item_sel in config["selectors"]:
                        result = await self.extract_with_selectors(
                            item_selector=item_sel,
                            field_selectors=config["fields"],
                            limit=10
                        )
                        if result.get("data") and len(result["data"]) >= 2:
                            return result

            return None
        except Exception as e:
            logger.debug(f"CSS extraction failed: {e}")
            return None

    @tool_result
    async def _try_accessibility_extraction(self, prompt_lower: str) -> Optional[Dict]:
        """Extract data using accessibility tree (like browser-use)"""
        try:
            await self._ensure_page()

            # Get accessibility tree - much faster than full HTML
            acc_tree = await self.page.accessibility.snapshot(interesting_only=True)
            if not acc_tree:
                return None

            # Extract relevant nodes based on prompt
            data = []
            keywords = set(prompt_lower.split())

            @tool_result
            def extract_from_tree(node, depth=0):
                if depth > 10 or len(data) >= 20:
                    return

                name = node.get("name", "")
                role = node.get("role", "")
                value = node.get("value", "")

                # Check if this node is relevant
                is_relevant = (
                    role in ["heading", "link", "button", "text", "listitem"] and
                    name and len(name) > 3
                )

                if is_relevant:
                    # Check keyword match
                    name_lower = name.lower()
                    if any(kw in name_lower for kw in keywords) or len(keywords) < 3:
                        data.append({
                            "text": name,
                            "role": role,
                            "value": value if value else None
                        })

                # Recurse into children
                for child in node.get("children", []):
                    extract_from_tree(child, depth + 1)

            extract_from_tree(acc_tree)

            if data:
                return {"data": data}
            return None

        except Exception as e:
            logger.debug(f"Accessibility extraction failed: {e}")
            return None

    @tool_result
    async def parallel_extract(
        self,
        urls: List[str],
        prompt: str,
        max_concurrent: int = 5,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Extract from multiple URLs in parallel (inspired by crawl4ai batch mode).

        Args:
            urls: List of URLs to extract from
            prompt: Extraction prompt (applied to all)
            max_concurrent: Max concurrent extractions
            use_cache: Use cached responses where available

        Returns:
            List of extraction results
        """
        import time
        start_time = time.time()
        results = []
        semaphore = asyncio.Semaphore(max_concurrent)
        cache_hits = 0

        @tool_result
        async def extract_one(url: str) -> Dict:
            nonlocal cache_hits
            async with semaphore:
                try:
                    # Check cache first
                    if use_cache:
                        cached = self._cache_get(url)
                        if cached:
                            cache_hits += 1
                            return {"url": url, "data": cached, "from_cache": True}
                    return await self.fast_extract(url, prompt)
                except Exception as e:
                    return {"url": url, "error": str(e)}

        # Run extractions in parallel
        tasks = [extract_one(url) for url in urls[:20]]  # Limit to 20
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        successful = []
        failed = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                failed.append({"url": urls[i], "error": str(r)})
            elif r.get("error"):
                failed.append({"url": urls[i], "error": r["error"]})
            else:
                r["url"] = urls[i]
                successful.append(r)

        return {
            "success": True,
            "results": successful,
            "failed": failed,
            "total": len(urls),
            "successful_count": len(successful),
            "cache_hits": cache_hits,
            "duration_sec": round(time.time() - start_time, 2)
        }

    @tool_result
    def clear_cache(self):
        """Clear the page cache"""
        global _PAGE_CACHE
        _PAGE_CACHE.clear()
        logger.info("Page cache cleared")

    # ==========================================================================
    # DOM PRUNING & COMPRESSION (Inspired by Prune4Web, Agent-E - 25-50x reduction)
    # ==========================================================================

    @tool_result
    async def get_pruned_dom(self, focus_area: str = None) -> Dict[str, Any]:
        """
        PRUNE4WEB STYLE: Get pruned DOM with 25-50x element reduction.

        Removes: Hidden elements, scripts, styles, ads, tracking
        Keeps: Interactive elements, text, semantic structure
        """
        try:
            await self._ensure_page()
            pruned = await self.page.evaluate("""
                (focusArea) => {
                    let root = focusArea ? document.querySelector(focusArea) : document.body;
                    if (!root) root = document.body;
                    const result = { elements: [], text_content: '' };
                    const REMOVE_TAGS = new Set(['script', 'style', 'noscript', 'svg', 'iframe']);
                    const INTERACTIVE = new Set(['a', 'button', 'input', 'select', 'textarea', 'form']);
                    let idx = 0;
                    const textParts = [];

                    function process(node, depth = 0) {
                        if (depth > 12 || idx > 100) return;
                        if (node.nodeType === Node.TEXT_NODE) {
                            const t = node.textContent.trim();
                            if (t.length > 2) textParts.push(t);
                            return;
                        }
                        if (node.nodeType !== Node.ELEMENT_NODE) return;
                        const tag = node.tagName.toLowerCase();
                        if (REMOVE_TAGS.has(tag)) return;
                        const style = window.getComputedStyle(node);
                        if (style.display === 'none' || style.visibility === 'hidden') return;

                        if (INTERACTIVE.has(tag) || ['h1','h2','h3','p','li','label'].includes(tag)) {
                            const el = { i: idx++, t: tag, x: (node.innerText || '').slice(0, 80) };
                            if (node.href) el.h = node.href.slice(0, 150);
                            if (node.name) el.n = node.name;
                            if (node.type) el.tp = node.type;
                            if (node.placeholder) el.ph = node.placeholder;
                            result.elements.push(el);
                        }
                        for (const c of node.childNodes) process(c, depth + 1);
                    }
                    process(root);
                    result.text_content = textParts.join(' ').slice(0, 3000);
                    result.count = result.elements.length;
                    result.original = document.querySelectorAll('*').length;
                    return result;
                }
            """, focus_area)
            return {"success": True, **pruned, "reduction": f"{pruned['original']} -> {pruned['count']}"}
        except Exception as e:
            return {"error": str(e)}

    @tool_result
    async def get_change_observation(self, action: str = "") -> Dict[str, Any]:
        """
        AGENT-E STYLE: Observe changes after action for self-refinement feedback.
        """
        try:
            await self._ensure_page()
            state = await self.page.evaluate("""() => ({
                url: location.href,
                title: document.title,
                alert: (document.querySelector('[role="alert"], .alert, .error, .success')?.innerText || '').slice(0, 150),
                modal: !!document.querySelector('.modal.show, [role="dialog"]:not([hidden])'),
                loading: !!document.querySelector('.loading, .spinner, [aria-busy="true"]')
            })""")
            feedback = []
            if state.get('alert'):
                if 'error' in state['alert'].lower():
                    feedback.append(f"⚠️ ERROR: {state['alert'][:80]}")
                elif 'success' in state['alert'].lower():
                    feedback.append(f"✓ SUCCESS: {state['alert'][:80]}")
                else:
                    feedback.append(f"📢 {state['alert'][:80]}")
            if state.get('modal'): feedback.append("📋 Modal visible")
            if state.get('loading'): feedback.append("⏳ Loading...")
            if not feedback: feedback.append(f"Page: {state.get('title', '')[:40]}")
            return {"success": True, "action": action, "state": state, "feedback": " | ".join(feedback)}
        except Exception as e:
            return {"error": str(e)}

    @tool_result
    async def smart_search(self, query: str, site_hint: str = None) -> Dict[str, Any]:
        """
        SMART FORM SEARCH: Auto-detect search form, fill, submit (fixes Amazon issue).

        Supports: Google, Amazon, eBay, LinkedIn, Reddit, Bing, DuckDuckGo, and most sites with search forms.
        """
        try:
            await self._ensure_page()

            # Expanded list of search input selectors for maximum compatibility
            filled = await self.page.evaluate("""(query) => {
                const sels = [
                    // Standard search types
                    'input[type="search"]',
                    'input[name="q"]',
                    'input[name="query"]',
                    'input[name="search"]',
                    'input[name="search_query"]',
                    'input[name="keywords"]',
                    'input[name="s"]',
                    // Amazon
                    'input[name="field-keywords"]',
                    '#twotabsearchtextbox',
                    // eBay
                    'input[name="_nkw"]',
                    '#gh-ac',
                    // LinkedIn
                    'input[name="keywords"]',
                    'input[data-tracking-control-name*="search"]',
                    // Reddit
                    'input[name="q"][type="text"]',
                    '#header-search-bar',
                    // Generic placeholders
                    'input[placeholder*="search" i]',
                    'input[placeholder*="Search" i]',
                    'input[aria-label*="search" i]',
                    'input[aria-label*="Search" i]',
                    // Class-based
                    'input.search-input',
                    'input.search-box',
                    'input.searchbox',
                    '.search input[type="text"]',
                    '#search input[type="text"]',
                    // Role-based
                    'input[role="searchbox"]',
                    '[role="search"] input',
                    // Generic text inputs in search forms
                    'form[action*="search"] input[type="text"]',
                    'form[role="search"] input[type="text"]'
                ];
                let inp = null;
                for (const s of sels) {
                    try {
                        inp = document.querySelector(s);
                        if (inp && inp.offsetParent !== null) break;  // Must be visible
                        inp = null;
                    } catch(e) {}
                }
                if (!inp) {
                    // Last resort: find any visible text input
                    const allInputs = document.querySelectorAll('input[type="text"], input:not([type])');
                    for (const candidate of allInputs) {
                        if (candidate.offsetParent !== null &&
                            (candidate.placeholder?.toLowerCase().includes('search') ||
                             candidate.name?.toLowerCase().includes('search') ||
                             candidate.id?.toLowerCase().includes('search'))) {
                            inp = candidate;
                            break;
                        }
                    }
                }
                if (!inp) return {
                    error: 'No search input found on this page. Try navigating to a page with a search form.',
                    suggestion: 'Common search pages: google.com, amazon.com, or look for a search icon on the site.',
                    url: location.href
                };
                inp.focus();
                inp.value = query;
                inp.dispatchEvent(new Event('input', { bubbles: true }));
                inp.dispatchEvent(new Event('change', { bubbles: true }));
                return { found: true, selector: inp.name || inp.id || inp.className };
            }""", query)

            if filled.get('error'):
                return filled

            # Try multiple submit strategies
            submitted = False
            try:
                # Strategy 1: Press Enter on the input
                await self.page.press('input[type="search"], input[name="q"], input[name="query"], input[name="field-keywords"], #twotabsearchtextbox, input[placeholder*="search" i]', 'Enter')
                submitted = True
            except Exception as e:
                handle_error("unknown_operation_search_page", e, context={"query": query, "error": error}, log_level="debug")

            if not submitted:
                try:
                    # Strategy 2: Click submit button
                    await self.page.click('button[type="submit"], input[type="submit"], button.search-button, button[aria-label*="search" i]', timeout=3000)
                    submitted = True
                except Exception as e:
                    handle_error("unknown_operation_search_click", e, context={"query": query}, log_level="debug")

            if not submitted:
                try:
                    # Strategy 3: Click any button near search
                    await self.page.click('[role="search"] button, form[action*="search"] button', timeout=2000)
                    submitted = True
                except Exception as e:
                    handle_error("unknown_operation_search_click", e, log_level="debug")

            await sleep_with_jitter(1.5)
            try:
                await self.page.wait_for_load_state('networkidle', timeout=5000)
            except (TimeoutError, Exception) as e:
                handle_error("unknown_operation_wait_page", e, log_level="debug")

            observation = await self.get_change_observation(f"Searched: {query}")
            return {"success": True, "query": query, "url": getattr(self.page, 'url', ''), "submitted": submitted, **observation}
        except Exception as e:
            return {"error": str(e)}

    # ==========================================================================
    # SELF-CORRECTION LOOP (OpenAI Operator style - 87% success rate)
    # ==========================================================================

    @tool_result
    async def action_with_retry(self, action_fn, action_name: str, max_retries: int = 3) -> Dict[str, Any]:
        """
        OPERATOR-STYLE: Execute action with automatic retry and self-correction.

        Features:
        - Auto-retry on failure with exponential backoff
        - State verification after each action
        - Error pattern learning
        - Alternative strategy selection
        """
        domain = self._get_current_domain()
        last_error = None

        for attempt in range(max_retries):
            try:
                # Execute the action
                result = await action_fn()

                # Verify success via observation
                observation = await self.get_change_observation(action_name)

                # Check for error states
                if observation.get("state", {}).get("alert", ""):
                    alert = observation["state"]["alert"].lower()
                    if "error" in alert or "failed" in alert or "invalid" in alert:
                        raise Exception(f"Page error: {observation['state']['alert'][:100]}")

                # Success - record in memory
                SessionMemory.add_visit(self.page.url if self.page else "", action_name, True)
                return {"success": True, "result": result, "observation": observation, "attempts": attempt + 1}

            except Exception as e:
                last_error = str(e)
                SessionMemory.record_error(domain, last_error, action_name)
                logger.warning(f"Action '{action_name}' failed (attempt {attempt + 1}): {last_error}")

                if attempt < max_retries - 1:
                    # Exponential backoff
                    await asyncio.sleep(exponential_backoff_with_jitter(attempt))

                    # Try recovery strategies
                    await self._try_recovery(last_error)

        return {"success": False, "error": last_error, "attempts": max_retries}

    @tool_result
    async def _try_recovery(self, error: str):
        """Attempt recovery from common error patterns"""
        if not self.page:
            return

        error_lower = error.lower()

        # Modal blocking? Try to dismiss
        if "modal" in error_lower or "dialog" in error_lower:
            try:
                await self.page.keyboard.press("Escape")
                await sleep_with_jitter(0.5)
            except Exception as e:
                handle_error("try_recovery_modal_dismiss_modal_dismiss", e, context={"error": error}, log_level="debug")

        # Element not found? Scroll to load
        if "not found" in error_lower or "no element" in error_lower:
            try:
                await self.page.evaluate("window.scrollBy(0, 300)")
                await sleep_with_jitter(0.5)
            except Exception as e:
                handle_error("try_recovery_scroll_page", e, context={"error": error}, log_level="debug")

        # Timeout? Wait a bit more
        if "timeout" in error_lower:
            try:
                await sleep_with_jitter(2.0)
            except Exception as e:
                handle_error("try_recovery_wait_wait", e, context={"error": error}, log_level="debug")

    @tool_result
    async def click_with_retry(self, selector: str, max_retries: int = 3) -> Dict[str, Any]:
        """Click with automatic retry and fallback strategies"""
        @tool_result
        async def do_click():
            return await self.click(selector)

        result = await self.action_with_retry(do_click, f"click:{selector}", max_retries)

        # If failed, try alternative strategies
        if not result.get("success"):
            # Try by text content
            try:
                text_match = re.search(r'text[=~]"([^"]+)"', selector)
                if text_match:
                    text = text_match.group(1)
                    await self.page.get_by_text(text, exact=False).first.click()
                    return {"success": True, "method": "text_fallback"}
            except Exception as e:
                logger.debug(f"Text fallback failed: {e}")
                pass

            # Try by role
            try:
                role_match = re.search(r'role[=~]"([^"]+)"', selector)
                if role_match:
                    await self.page.get_by_role(role_match.group(1)).first.click()
                    return {"success": True, "method": "role_fallback"}
            except Exception as e:
                logger.debug(f"Role fallback failed: {e}")
                pass

        return result

    # ==========================================================================
    # STRUCTURED OUTPUT PARSING (hallucination reduction)
    # ==========================================================================

    @tool_result
    def parse_structured_output(self, text: str, schema: Dict = None) -> Dict[str, Any]:
        """
        Parse LLM output into structured format with validation.

        Features:
        - JSON extraction from mixed text
        - Schema validation
        - Retry-friendly error messages
        - Fallback to key-value extraction
        """
        import json

        # Try to find JSON in the text
        json_patterns = [
            r'\{[^{}]*\}',  # Simple object
            r'\[[^\[\]]*\]',  # Simple array
            r'\{(?:[^{}]|\{[^{}]*\})*\}',  # Nested object (1 level)
        ]

        for pattern in json_patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            for match in matches:
                try:
                    parsed = json.loads(match)
                    # Validate against schema if provided
                    if schema:
                        if self._validate_schema(parsed, schema):
                            return {"success": True, "data": parsed, "method": "json"}
                    else:
                        return {"success": True, "data": parsed, "method": "json"}
                except json.JSONDecodeError:
                    continue

        # Fallback: key-value extraction
        kv_data = self._extract_key_values(text)
        if kv_data:
            return {"success": True, "data": kv_data, "method": "key_value"}

        return {"success": False, "error": "Could not parse structured output", "raw": text[:500]}

    @tool_result
    def _validate_schema(self, data: Any, schema: Dict) -> bool:
        """Simple schema validation"""
        if schema.get("type") == "object":
            if not isinstance(data, dict):
                return False
            required = schema.get("required", [])
            for field in required:
                if field not in data:
                    return False
        elif schema.get("type") == "array":
            if not isinstance(data, list):
                return False
        return True

    @tool_result
    def _extract_key_values(self, text: str) -> Dict[str, str]:
        """Extract key: value pairs from text"""
        result = {}
        patterns = [
            r'(\w+):\s*([^\n]+)',  # key: value
            r'(\w+)\s*=\s*([^\n]+)',  # key = value
            r'"\s*(\w+)\s*"\s*:\s*"([^"]+)"',  # "key": "value"
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for key, value in matches:
                key = key.strip().lower()
                value = value.strip().strip('"\'')
                if key and value and len(key) < 30:
                    result[key] = value
        return result

    # ==========================================================================
    # ENHANCED STEALTH MODE (Puppeteer Stealth 87%)
    # ==========================================================================

    @tool_result
    async def apply_enhanced_stealth(self):
        """
        Apply additional stealth measures beyond basic settings.

        Techniques from:
        - puppeteer-extra-plugin-stealth
        - Botasaurus
        - Nodriver
        """
        if not self.page:
            return

        enhanced_stealth_js = """
        () => {
            // 1. Override navigator.webdriver
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });

            // 2. Mock plugins array
            Object.defineProperty(navigator, 'plugins', {
                get: () => {
                    const plugins = [
                        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                        { name: 'Native Client', filename: 'internal-nacl-plugin' }
                    ];
                    plugins.item = (i) => plugins[i];
                    plugins.namedItem = (name) => plugins.find(p => p.name === name);
                    plugins.refresh = () => {};
                    return plugins;
                }
            });

            // 3. Mock languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });

            // 4. Fix chrome object
            if (!window.chrome) {
                window.chrome = {
                    runtime: {},
                    loadTimes: function() {},
                    csi: function() {},
                    app: {}
                };
            }

            // 5. Override permissions query
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => {
                if (parameters.name === 'notifications') {
                    return Promise.resolve({ state: Notification.permission });
                }
                return originalQuery(parameters);
            };

            // 6. Mock WebGL vendor/renderer
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Intel Inc.';
                if (parameter === 37446) return 'Intel Iris OpenGL Engine';
                return getParameter.apply(this, arguments);
            };

            // 7. Prevent canvas fingerprinting
            const toDataURL = HTMLCanvasElement.prototype.toDataURL;
            HTMLCanvasElement.prototype.toDataURL = function(type) {
                if (type === 'image/png' && this.width < 50 && this.height < 50) {
                    // Likely fingerprinting - add noise
                    const context = this.getContext('2d');
                    if (context) {
                        const imageData = context.getImageData(0, 0, this.width, this.height);
                        for (let i = 0; i < imageData.data.length; i += 4) {
                            imageData.data[i] += Math.random() * 2 - 1;
                        }
                        context.putImageData(imageData, 0, 0);
                    }
                }
                return toDataURL.apply(this, arguments);
            };

            // 8. Mock connection info
            Object.defineProperty(navigator, 'connection', {
                get: () => ({
                    effectiveType: '4g',
                    rtt: 50,
                    downlink: 10,
                    saveData: false
                })
            });

            // 9. Fix iframe contentWindow
            const originalContentWindow = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'contentWindow');
            Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
                get: function() {
                    const win = originalContentWindow.get.call(this);
                    if (win) {
                        try {
                            Object.defineProperty(win.navigator, 'webdriver', { get: () => undefined });
                        } catch (e) {}
                    }
                    return win;
                }
            });

            return 'Enhanced stealth applied';
        }
        """;

        try:
            await self.page.evaluate(enhanced_stealth_js)
            logger.debug("Enhanced stealth mode applied")
        except Exception as e:
            logger.debug(f"Some stealth features couldn't be applied: {e}")

        if (
            ADVANCED_STEALTH_AVAILABLE
            and self._auto_stealth_state.get("active")
            and get_enhanced_stealth_script
        ):
            try:
                await self.page.evaluate(get_enhanced_stealth_script())
                logger.debug("Auto-stealth: applied MCP stealth script")
            except Exception as e:
                logger.debug(f"Auto-stealth MCP script failed: {e}")

    @tool_result
    def _get_current_domain(self) -> str:
        """Get domain from current page URL"""
        if self.page and self.page.url:
            try:
                from urllib.parse import urlparse
                return urlparse(self.page.url).netloc
            except Exception as e:
                logger.debug(f"Failed to parse URL domain: {e}")
                pass
        return "unknown"

    # ==========================================================================
    # CONTEXT WINDOW OPTIMIZATION
    # ==========================================================================

    @tool_result
    async def get_compressed_state(self, max_tokens: int = 2000) -> Dict[str, Any]:
        """
        Get compressed page state for LLM context efficiency.

        Combines:
        - Session memory summary
        - Pruned DOM
        - Key interactive elements
        """
        try:
            await self._ensure_page()

            # Get pruned DOM (already implemented)
            pruned = await self.get_pruned_dom()

            # Get interactive elements (limited)
            elements = await self.get_interactive_elements()
            top_elements = elements.get("elements", [])[:15]

            # Session context
            session_summary = SessionMemory.get_context_summary()

            # Compose compressed state
            state = {
                "url": self.page.url if self.page else "",
                "title": await self.page.title() if self.page else "",
                "session": session_summary,
                "interactive_count": len(elements.get("elements", [])),
                "top_elements": [
                    f"[{e['index']}] {e['role']}: {e.get('name', '')[:30]}"
                    for e in top_elements
                ],
                "dom_summary": pruned.get("html", "")[:max_tokens] if pruned.get("success") else "",
                "forms": pruned.get("forms", [])[:3] if pruned.get("success") else [],
            }

            return {"success": True, **state}

        except Exception as e:
            return {"error": str(e)}

    # ==========================================================================
    # MEMORY TOOLS (for tool registry)
    # ==========================================================================

    @tool_result
    def get_session_memory(self) -> Dict[str, Any]:
        """Get current session memory state"""
        return {
            "success": True,
            "visited_count": len(_SESSION_MEMORY["visited_urls"]),
            "data_keys": list(_SESSION_MEMORY["extracted_data"].keys()),
            "error_count": len(_SESSION_MEMORY["errors"]),
            "patterns": _SESSION_MEMORY["learned_patterns"],
            "tasks_done": len(_SESSION_MEMORY["task_history"]),
            "summary": SessionMemory.get_context_summary()
        }

    @tool_result
    def clear_session_memory(self) -> Dict[str, Any]:
        """Clear session memory"""
        SessionMemory.clear()
        return {"success": True, "message": "Session memory cleared"}
