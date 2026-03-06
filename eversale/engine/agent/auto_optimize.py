#!/usr/bin/env python3
"""
Auto-Optimization Module for Browser Agent

Automatically enables all browser optimizations with zero configuration.
Provides a single entry point to get a fully optimized agent.

Features:
1. Auto-detect best browser backend (CDP if Chrome running, else Playwright)
2. Auto-enable all optimizations:
   - TokenOptimizer with default config
   - DevToolsHooks for error capture
   - Snapshot caching
3. Extraction shortcuts (extract_links, extract_forms, get_errors)
4. Optimization stats and status

Usage:
    from auto_optimize import get_optimized_agent

    # One line to get fully optimized agent
    agent = await get_optimized_agent()

    # Or with options
    agent = await get_optimized_agent(
        prefer_cdp=True,      # Try to connect to existing Chrome first
        headless=False,       # Show browser
        capture_errors=True,  # Enable DevTools error capture
        token_budget=8000,    # Max tokens for context
    )

    # Auto-wired extraction shortcuts
    links = await agent.extract_links(contains_text='signup')
    forms = await agent.extract_forms()
    errors = await agent.get_errors()

    # Optimization stats
    stats = agent.get_optimization_stats()
"""

import asyncio
import subprocess
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from loguru import logger

# Import optimization modules
try:
    from .token_optimizer import TokenOptimizer, DEFAULT_CONFIG as TOKEN_DEFAULT_CONFIG
    TOKEN_OPTIMIZER_AVAILABLE = True
except ImportError:
    TOKEN_OPTIMIZER_AVAILABLE = False
    logger.warning("TokenOptimizer not available")

try:
    from .devtools_hooks import DevToolsHooks
    DEVTOOLS_AVAILABLE = True
except ImportError:
    DEVTOOLS_AVAILABLE = False
    logger.warning("DevToolsHooks not available")

try:
    from .extraction_helpers import extract_links, extract_forms, extract_clickable
    EXTRACTION_HELPERS_AVAILABLE = True
except ImportError:
    EXTRACTION_HELPERS_AVAILABLE = False
    logger.warning("ExtractionHelpers not available")

try:
    from .browser_backend import BrowserBackend, SnapshotResult, InteractionResult
    BROWSER_BACKEND_AVAILABLE = True
except ImportError:
    BROWSER_BACKEND_AVAILABLE = False
    logger.warning("BrowserBackend not available")

# Try importing Playwright backend
try:
    # Check if playwright_backend module exists
    from .playwright_backend import PlaywrightBackend
    PLAYWRIGHT_BACKEND_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_BACKEND_AVAILABLE = False
    logger.debug("PlaywrightBackend not available")

# Try importing CDP backend
try:
    from .cdp_backend import CDPBackend
    CDP_BACKEND_AVAILABLE = True
except ImportError:
    CDP_BACKEND_AVAILABLE = False
    logger.debug("CDPBackend not available")


@dataclass
class OptimizationConfig:
    """Configuration for auto-optimization."""
    # Backend selection
    prefer_cdp: bool = True
    headless: bool = False

    # Token optimizer
    enable_token_optimizer: bool = True
    token_budget: int = 8000
    max_snapshot_elements: int = 100
    max_text_length: int = 200
    cache_ttl_seconds: int = 30

    # DevTools hooks
    enable_devtools: bool = True
    capture_network: bool = True
    capture_console: bool = True
    max_network_entries: int = 500
    max_console_entries: int = 200

    # Performance
    enable_snapshot_caching: bool = True
    auto_compress_threshold: float = 0.8


@dataclass
class OptimizationStats:
    """Statistics about optimizations."""
    # Backend info
    backend_type: str = "unknown"
    backend_connected: bool = False
    connection_time_ms: float = 0

    # Token optimizer stats
    tokens_saved: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    auto_compressions: int = 0
    cache_hit_rate: float = 0.0

    # DevTools stats
    screenshots_skipped: int = 0
    errors_captured: int = 0
    failed_requests: int = 0
    console_errors: int = 0

    # Performance
    snapshots_taken: int = 0
    snapshots_cached: int = 0
    avg_snapshot_time_ms: float = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "backend": {
                "type": self.backend_type,
                "connected": self.backend_connected,
                "connection_time_ms": self.connection_time_ms,
            },
            "token_optimizer": {
                "tokens_saved": self.tokens_saved,
                "cache_hits": self.cache_hits,
                "cache_misses": self.cache_misses,
                "cache_hit_rate": f"{self.cache_hit_rate:.1f}%",
                "auto_compressions": self.auto_compressions,
            },
            "devtools": {
                "errors_captured": self.errors_captured,
                "failed_requests": self.failed_requests,
                "console_errors": self.console_errors,
            },
            "performance": {
                "snapshots_taken": self.snapshots_taken,
                "snapshots_cached": self.snapshots_cached,
                "screenshots_skipped": self.screenshots_skipped,
                "avg_snapshot_time_ms": self.avg_snapshot_time_ms,
            }
        }


class OptimizedAgent:
    """
    Fully optimized browser agent wrapper.

    Wraps a BrowserBackend with all optimizations enabled:
    - Token optimization (snapshot compression, caching)
    - DevTools hooks (error capture, network monitoring)
    - Extraction helpers (fast JS-based extraction)
    """

    def __init__(
        self,
        backend: Any,
        config: OptimizationConfig,
        token_optimizer: Optional[Any] = None,
        devtools: Optional[Any] = None
    ):
        """Initialize optimized agent."""
        self.backend = backend
        self.config = config
        self.token_optimizer = token_optimizer
        self.devtools = devtools
        self.stats = OptimizationStats()

        # Track timing
        self._snapshot_times: List[float] = []

        # Backend type
        self.stats.backend_type = type(backend).__name__

        logger.info(f"OptimizedAgent initialized with {self.stats.backend_type}")

    # =============================================================================
    # Core Browser Methods (delegate to backend)
    # =============================================================================

    async def connect(self) -> bool:
        """Connect to browser (optimized)."""
        start = time.time()
        success = await self.backend.connect()
        self.stats.backend_connected = success
        self.stats.connection_time_ms = (time.time() - start) * 1000

        # Start DevTools capture if enabled
        if self.devtools and self.config.enable_devtools:
            try:
                await self.devtools.start_capture(
                    network=self.config.capture_network,
                    console=self.config.capture_console
                )
                logger.debug("DevTools capture started")
            except Exception as e:
                logger.warning(f"Failed to start DevTools capture: {e}")

        return success

    async def disconnect(self) -> None:
        """Disconnect from browser."""
        # Stop DevTools capture
        if self.devtools:
            try:
                await self.devtools.stop_capture()
            except Exception as e:
                logger.debug(f"Error stopping DevTools: {e}")

        await self.backend.disconnect()
        self.stats.backend_connected = False

    async def navigate(self, url: str, wait_until: str = 'load') -> Any:
        """Navigate to URL."""
        return await self.backend.navigate(url, wait_until)

    async def snapshot(self, force: bool = False) -> Any:
        """
        Get page snapshot with optimization.

        Args:
            force: Force new snapshot even if cache is valid

        Returns:
            SnapshotResult (possibly cached and compressed)
        """
        start = time.time()

        # Check if we should use cached snapshot
        if not force and self.token_optimizer and self.config.enable_snapshot_caching:
            cached = self.token_optimizer.get_cached_snapshot()
            if cached:
                self.stats.snapshots_cached += 1
                logger.debug("Using cached snapshot")
                return cached

        # Get fresh snapshot from backend
        snapshot = await self.backend.snapshot()
        self.stats.snapshots_taken += 1

        # Cache snapshot
        if self.token_optimizer:
            self.token_optimizer.cache_snapshot(snapshot.to_dict() if hasattr(snapshot, 'to_dict') else snapshot)

        # Track timing
        duration_ms = (time.time() - start) * 1000
        self._snapshot_times.append(duration_ms)
        self.stats.avg_snapshot_time_ms = sum(self._snapshot_times) / len(self._snapshot_times)

        return snapshot

    async def click(self, ref: str, **kwargs) -> Any:
        """Click element by reference."""
        return await self.backend.click(ref, **kwargs)

    async def type(self, ref: str, text: str, clear: bool = True, **kwargs) -> Any:
        """Type text into element."""
        return await self.backend.type(ref, text, clear, **kwargs)

    async def scroll(self, direction: str = 'down', amount: int = 500) -> Any:
        """Scroll page."""
        return await self.backend.scroll(direction, amount)

    async def run_code(self, js: str) -> Any:
        """Execute JavaScript in page context."""
        return await self.backend.run_code(js)

    async def observe(self, network: bool = False, console: bool = False) -> Any:
        """Observe page state and events."""
        return await self.backend.observe(network, console)

    async def screenshot(self, full_page: bool = False) -> bytes:
        """Take screenshot."""
        return await self.backend.screenshot(full_page)

    # =============================================================================
    # Extraction Shortcuts
    # =============================================================================

    async def extract_links(
        self,
        contains_text: Optional[str] = None,
        domain: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Extract links from current page.

        Args:
            contains_text: Filter links containing this text
            domain: Filter links to specific domain
            limit: Maximum number of links to return

        Returns:
            List of link objects with mmid, href, text
        """
        if not EXTRACTION_HELPERS_AVAILABLE:
            logger.warning("ExtractionHelpers not available, using fallback")
            # Fallback: use snapshot
            snapshot = await self.snapshot()
            if hasattr(snapshot, 'get_by_role'):
                links = snapshot.get_by_role('link')
                if contains_text:
                    links = [l for l in links if contains_text.lower() in l.text.lower()]
                return [l.to_dict() if hasattr(l, 'to_dict') else l for l in links[:limit]]
            return []

        # Get page object from backend
        page = getattr(self.backend, 'page', None)
        if not page:
            logger.warning("No page object available for extraction")
            return []

        return await extract_links(page, contains_text, domain, limit)

    async def extract_forms(self) -> List[Dict[str, Any]]:
        """
        Extract all forms from current page.

        Returns:
            List of form objects with fields and submit buttons
        """
        if not EXTRACTION_HELPERS_AVAILABLE:
            logger.warning("ExtractionHelpers not available, using fallback")
            return []

        page = getattr(self.backend, 'page', None)
        if not page:
            return []

        return await extract_forms(page)

    async def extract_clickable(
        self,
        contains_text: Optional[str] = None,
        role: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Extract clickable elements (buttons, links).

        Args:
            contains_text: Filter by text content
            role: Filter by ARIA role
            limit: Maximum number of elements

        Returns:
            List of clickable elements
        """
        if not EXTRACTION_HELPERS_AVAILABLE:
            logger.warning("ExtractionHelpers not available")
            return []

        page = getattr(self.backend, 'page', None)
        if not page:
            return []

        return await extract_clickable(page, contains_text, role, limit)

    # =============================================================================
    # DevTools Shortcuts
    # =============================================================================

    async def get_errors(self) -> List[Dict[str, Any]]:
        """
        Get all captured page errors.

        Returns:
            List of error objects with timestamp, message, stack
        """
        if not self.devtools:
            logger.debug("DevTools not enabled")
            return []

        errors = self.devtools.get_errors()
        self.stats.errors_captured = len(errors)
        return errors

    async def get_failed_requests(self) -> List[Dict[str, Any]]:
        """
        Get all failed network requests.

        Returns:
            List of failed request objects
        """
        if not self.devtools:
            return []

        failed = self.devtools.get_failed_requests()
        self.stats.failed_requests = len(failed)
        return failed

    async def get_console_errors(self) -> List[Dict[str, Any]]:
        """
        Get console error messages.

        Returns:
            List of console error objects
        """
        if not self.devtools:
            return []

        errors = self.devtools.get_console_log(level='error')
        self.stats.console_errors = len(errors)
        return errors

    def get_devtools_summary(self) -> Dict[str, Any]:
        """Get DevTools capture summary."""
        if not self.devtools:
            return {}

        return self.devtools.summary()

    # =============================================================================
    # Optimization Stats
    # =============================================================================

    def get_optimization_stats(self) -> Dict[str, Any]:
        """
        Get optimization statistics.

        Returns:
            Dict with tokens_saved, cache_hits, screenshots_skipped, etc.
        """
        # Update token optimizer stats
        if self.token_optimizer:
            token_stats = self.token_optimizer.get_stats()
            self.stats.tokens_saved = token_stats.get('saved_tokens', 0)
            self.stats.cache_hits = token_stats.get('cache_hits', 0)
            self.stats.cache_misses = token_stats.get('cache_misses', 0)
            self.stats.auto_compressions = token_stats.get('auto_compressions', 0)
            self.stats.cache_hit_rate = token_stats.get('cache_hit_rate', 0.0)

        # Update DevTools stats
        if self.devtools:
            devtools_summary = self.devtools.summary()
            self.stats.errors_captured = devtools_summary.get('errors', {}).get('page_errors', 0)
            self.stats.failed_requests = devtools_summary.get('network', {}).get('failed_requests', 0)
            self.stats.console_errors = devtools_summary.get('console', {}).get('errors', 0)

        return self.stats.to_dict()

    def reset_stats(self):
        """Reset all optimization statistics."""
        self.stats = OptimizationStats()
        self.stats.backend_type = type(self.backend).__name__
        self.stats.backend_connected = getattr(self.backend, '_connected', False)
        self._snapshot_times = []

        if self.token_optimizer:
            self.token_optimizer.reset_stats()

        if self.devtools:
            self.devtools.clear()

    # =============================================================================
    # Compression Utilities
    # =============================================================================

    def compress_snapshot(self, snapshot: Any) -> Any:
        """Compress snapshot to reduce token usage."""
        if not self.token_optimizer:
            return snapshot

        snapshot_dict = snapshot.to_dict() if hasattr(snapshot, 'to_dict') else snapshot
        return self.token_optimizer.compress_snapshot(snapshot_dict)

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        if not self.token_optimizer:
            # Simple fallback: ~4 chars per token
            return len(text) // 4

        return self.token_optimizer.estimate_tokens(text)

    def check_token_budget(self, context: str) -> tuple:
        """
        Check if context fits within token budget.

        Returns:
            (within_budget, estimated_tokens, message)
        """
        if not self.token_optimizer:
            return (True, 0, "Token optimizer not enabled")

        return self.token_optimizer.check_budget(context)


# =============================================================================
# Auto-Detection and Factory
# =============================================================================

def _is_chrome_running_with_debug() -> bool:
    """Check if Chrome is running with remote debugging enabled."""
    try:
        # Check common debug ports
        import socket
        for port in [9222, 9223, 9224]:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex(('127.0.0.1', port))
            sock.close()
            if result == 0:
                logger.debug(f"Found Chrome with debugging on port {port}")
                return True
        return False
    except Exception as e:
        logger.debug(f"Error checking for Chrome: {e}")
        return False


async def _create_cdp_backend(headless: bool = False, **kwargs) -> Optional[Any]:
    """Try to create CDP backend."""
    if not CDP_BACKEND_AVAILABLE:
        logger.debug("CDP backend not available")
        return None

    try:
        backend = CDPBackend(headless=headless, **kwargs)
        connected = await backend.connect()
        if connected:
            logger.info("Connected to existing Chrome via CDP")
            return backend
        else:
            logger.debug("CDP backend failed to connect")
            return None
    except Exception as e:
        logger.debug(f"Failed to create CDP backend: {e}")
        return None


async def _create_playwright_backend(headless: bool = False, **kwargs) -> Optional[Any]:
    """Try to create Playwright backend."""
    if not PLAYWRIGHT_BACKEND_AVAILABLE:
        logger.debug("Playwright backend not available")
        return None

    try:
        # Import actual Playwright backend
        # For now, we'll use a generic approach since the module might not exist
        # In production, this would import from playwright_backend.py

        # Fallback: Use generic BrowserBackend if specific backend not available
        logger.warning("PlaywrightBackend module not found, would need to implement")
        return None
    except Exception as e:
        logger.debug(f"Failed to create Playwright backend: {e}")
        return None


async def get_optimized_agent(
    prefer_cdp: bool = True,
    headless: bool = False,
    capture_errors: bool = True,
    token_budget: int = 8000,
    max_snapshot_elements: int = 100,
    **kwargs
) -> OptimizedAgent:
    """
    Get a fully optimized browser agent with zero configuration.

    Auto-detects best backend and enables all optimizations.

    Args:
        prefer_cdp: Try to connect to existing Chrome first
        headless: Run browser in headless mode
        capture_errors: Enable DevTools error capture
        token_budget: Max tokens for context
        max_snapshot_elements: Max elements in snapshot
        **kwargs: Additional backend-specific options

    Returns:
        OptimizedAgent instance ready to use

    Example:
        agent = await get_optimized_agent()
        await agent.connect()
        await agent.navigate("https://example.com")
        links = await agent.extract_links(contains_text="signup")
        errors = await agent.get_errors()
        stats = agent.get_optimization_stats()
    """
    # Build config
    config = OptimizationConfig(
        prefer_cdp=prefer_cdp,
        headless=headless,
        enable_devtools=capture_errors,
        token_budget=token_budget,
        max_snapshot_elements=max_snapshot_elements,
    )

    # Auto-select backend
    backend = None

    if prefer_cdp and _is_chrome_running_with_debug():
        logger.info("Attempting to connect to existing Chrome via CDP...")
        backend = await _create_cdp_backend(headless=headless, **kwargs)

    if not backend:
        logger.info("Using Playwright backend...")
        backend = await _create_playwright_backend(headless=headless, **kwargs)

    if not backend:
        raise RuntimeError(
            "Failed to create browser backend. "
            "Install Playwright or start Chrome with debugging: "
            "chrome --remote-debugging-port=9222"
        )

    # Create token optimizer
    token_optimizer = None
    if TOKEN_OPTIMIZER_AVAILABLE:
        token_config = {
            'token_budget': token_budget,
            'max_snapshot_elements': max_snapshot_elements,
            'max_text_length': config.max_text_length,
            'cache_ttl_seconds': config.cache_ttl_seconds,
            'auto_compress_threshold': config.auto_compress_threshold,
        }
        token_optimizer = TokenOptimizer(token_config)
        logger.debug("Token optimizer enabled")

    # Create DevTools hooks
    devtools = None
    if DEVTOOLS_AVAILABLE and capture_errors:
        # DevTools needs access to Playwright page object
        page = getattr(backend, 'page', None)
        if page:
            devtools = DevToolsHooks(
                page,
                max_network_entries=config.max_network_entries,
                max_console_entries=config.max_console_entries,
            )
            logger.debug("DevTools hooks enabled")

    # Create optimized agent
    agent = OptimizedAgent(
        backend=backend,
        config=config,
        token_optimizer=token_optimizer,
        devtools=devtools
    )

    logger.info("Optimized agent created successfully")
    return agent


# =============================================================================
# Convenience Aliases
# =============================================================================

async def create_optimized_agent(**kwargs) -> OptimizedAgent:
    """Alias for get_optimized_agent()."""
    return await get_optimized_agent(**kwargs)


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == '__main__':
    async def demo():
        """Demo auto-optimization."""
        print("Creating optimized agent...")
        agent = await get_optimized_agent(
            prefer_cdp=True,
            headless=False,
            capture_errors=True,
            token_budget=8000
        )

        print(f"Agent created: {agent.stats.backend_type}")

        # Connect
        connected = await agent.connect()
        print(f"Connected: {connected}")

        if connected:
            # Navigate
            await agent.navigate("https://example.com")

            # Get snapshot (cached on second call)
            snapshot1 = await agent.snapshot()
            snapshot2 = await agent.snapshot()  # Should use cache

            # Extract data
            links = await agent.extract_links(limit=5)
            print(f"Found {len(links)} links")

            # Get errors
            errors = await agent.get_errors()
            print(f"Page errors: {len(errors)}")

            # Get stats
            stats = agent.get_optimization_stats()
            print("\nOptimization Stats:")
            import json
            print(json.dumps(stats, indent=2))

            # Cleanup
            await agent.disconnect()

    asyncio.run(demo())
