"""
Browser Pool Manager - Instant browser startup + parallel extraction

Features:
- INSTANT STARTUP: Pre-warmed browser ready in <100ms (vs 6+ seconds cold start)
- Keep-alive mode: Browser stays warm between tasks (like Playwright MCP)
- Pool of N browser instances (default 3) for parallel extraction
- Automatic health checking and replacement
- Round-robin or least-loaded assignment
- Per-browser fingerprint profiles
- Graceful shutdown

Design:
- Each browser has a unique fingerprint profile from stealth_enhanced
- Lazy initialization (create on first use) OR eager warmup for instant access
- Async context manager for safe resource handling
- Parallel extraction helper for distributing URLs across pool
- Sticky sessions (same domain = same browser) for cookies/login state
- Health monitoring and automatic browser replacement
- Background warmup on CLI startup for instant first task

Usage:
    # CONTEXT MANAGER MODE (automatic cleanup - recommended)
    async with BrowserPool(size=1, warmup_on_init=True) as pool:
        await pool.wait_for_warmup()  # Wait for browser warmup
        async with pool.browser() as browser_ctx:
            page = browser_ctx.page
            await page.goto("https://example.com")
    # Automatic cleanup on exit

    # MANUAL MODE (explicit initialization and shutdown)
    pool = BrowserPool(size=1, warmup_on_init=True)
    await pool.initialize()  # Pre-launches browser in background
    # ... browser is now ready instantly for first task

    async with pool.browser() as browser_ctx:
        # Use browser_ctx like a normal browser context
        page = browser_ctx.page
        await page.goto("https://example.com")

    # Cleanup
    await pool.shutdown()

    # PARALLEL MODE (multiple browsers for scraping)
    async with BrowserPool(size=5) as pool:
        urls = ["https://site1.com", "https://site2.com", "https://site3.com"]
        results = await pool.parallel_extract(urls, extract_contacts)

Author: Claude
Date: 2025-12-07
Updated: 2025-12-12 (added warmup/keep-alive)
"""

import asyncio
import hashlib
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from loguru import logger

# Import stealth and browser utilities
try:
    from .stealth_enhanced import FingerprintManager, EnhancedStealthSession, get_stealth_session
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False
    logger.warning("stealth_enhanced not available - browsers will use default profiles")

try:
    from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.error("Playwright not available - browser pool cannot function")


# =============================================================================
# Assignment Strategies
# =============================================================================

class AssignmentStrategy(Enum):
    """Strategy for assigning browsers from the pool."""
    ROUND_ROBIN = "round_robin"  # Simple rotation
    LEAST_LOADED = "least_loaded"  # Browser with fewest active tasks
    STICKY_DOMAIN = "sticky_domain"  # Same domain = same browser (for cookies/sessions)
    RANDOM = "random"  # Random selection


# =============================================================================
# Browser Instance Wrapper
# =============================================================================

@dataclass
class BrowserInstance:
    """
    Wrapper for a browser instance with tracking metadata.

    Attributes:
        id: Unique identifier for this browser
        browser: Playwright Browser instance
        context: Playwright BrowserContext instance
        page: Default page in the context
        fingerprint: FingerprintManager for this browser's unique identity
        created_at: Timestamp when browser was created
        active_tasks: Number of currently running tasks
        total_tasks: Total tasks completed
        last_used: Timestamp of last use
        success_count: Number of successful operations
        error_count: Number of failed operations
        healthy: Whether browser is currently healthy
        domains: Set of domains this browser has visited (for sticky sessions)
    """
    id: int
    browser: Optional["Browser"] = None
    context: Optional["BrowserContext"] = None
    page: Optional["Page"] = None
    fingerprint: Optional["FingerprintManager"] = None
    created_at: float = field(default_factory=time.time)
    active_tasks: int = 0
    total_tasks: int = 0
    last_used: float = field(default_factory=time.time)
    success_count: int = 0
    error_count: int = 0
    healthy: bool = True
    domains: Set[str] = field(default_factory=set)

    @property
    def success_rate(self) -> float:
        """Calculate success rate for this browser."""
        total = self.success_count + self.error_count
        if total == 0:
            return 1.0
        return self.success_count / total

    @property
    def age_seconds(self) -> float:
        """Get age of this browser in seconds."""
        return time.time() - self.created_at

    @property
    def idle_seconds(self) -> float:
        """Get seconds since last use."""
        return time.time() - self.last_used

    def mark_used(self):
        """Mark browser as used (update timestamp)."""
        self.last_used = time.time()

    def record_success(self):
        """Record a successful operation."""
        self.success_count += 1
        self.mark_used()

    def record_error(self):
        """Record a failed operation."""
        self.error_count += 1
        self.mark_used()

    def add_domain(self, url: str):
        """Add a domain to the browser's visited domains."""
        try:
            parsed = urlparse(url)
            if parsed.netloc:
                self.domains.add(parsed.netloc)
        except Exception:
            pass


# =============================================================================
# Browser Pool Manager
# =============================================================================

class BrowserPool:
    """
    Manages a pool of browser instances for parallel operations.

    Features:
    - Lazy initialization of browsers
    - Multiple assignment strategies (round-robin, least-loaded, sticky)
    - Health monitoring and automatic replacement
    - Parallel extraction across pool
    - Graceful shutdown

    Args:
        size: Number of browsers in the pool (default 3)
        strategy: Assignment strategy (default ROUND_ROBIN)
        health_check_interval: Seconds between health checks (default 60)
        max_browser_age: Max age before browser replacement in seconds (default 3600)
        max_idle_time: Max idle time before closing browser (default 300)
        headless: Whether to run browsers in headless mode (default True)
        enable_stealth: Whether to use stealth fingerprints (default True)
    """

    def __init__(
        self,
        size: int = 3,
        strategy: AssignmentStrategy = AssignmentStrategy.ROUND_ROBIN,
        health_check_interval: int = 60,
        max_browser_age: int = 3600,  # 1 hour
        max_idle_time: int = 300,  # 5 minutes
        headless: bool = True,
        enable_stealth: bool = True,
        warmup_on_init: bool = False,  # NEW: Pre-launch browsers on init for instant startup
    ):
        """Initialize browser pool configuration."""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright is required for BrowserPool")

        self.size = size
        self.strategy = strategy
        self.health_check_interval = health_check_interval
        self.max_browser_age = max_browser_age
        self.max_idle_time = max_idle_time
        self.headless = headless
        self.enable_stealth = enable_stealth and STEALTH_AVAILABLE
        self.warmup_on_init = warmup_on_init  # NEW

        # Pool state
        self.browsers: List[BrowserInstance] = []
        self.playwright: Optional["Playwright"] = None
        self._initialized = False
        self._round_robin_index = 0
        self._health_check_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        self._warmup_task: Optional[asyncio.Task] = None  # NEW: Background warmup task

        # Domain mapping for sticky sessions
        self._domain_to_browser: Dict[str, int] = {}  # domain -> browser_id

        # Locks for thread safety
        self._pool_lock = asyncio.Lock()
        self._assignment_lock = asyncio.Lock()

        # Stats
        self.stats = {
            'browsers_created': 0,
            'browsers_replaced': 0,
            'acquisitions': 0,
            'releases': 0,
            'health_checks': 0,
            'errors': 0,
            'warmup_hits': 0,  # NEW: Times warm browser was used instantly
            'warmup_misses': 0,  # NEW: Times browser had to be created on-demand
        }

    # =========================================================================
    # Async Context Manager Support
    # =========================================================================

    async def __aenter__(self):
        """Async context manager entry - initializes pool and returns self."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - guaranteed cleanup."""
        await self.shutdown()
        return False  # Don't suppress exceptions

    # =========================================================================
    # Initialization and Shutdown
    # =========================================================================

    async def initialize(self):
        """
        Initialize the browser pool.

        Creates playwright instance and starts health monitoring.
        If warmup_on_init=True, pre-launches all browsers for instant access.
        Otherwise, browsers are created lazily on first acquisition.
        """
        if self._initialized:
            logger.debug("Browser pool already initialized")
            return

        logger.info(f"Initializing browser pool (size={self.size}, strategy={self.strategy.value}, warmup={self.warmup_on_init})")

        # Start playwright
        self.playwright = await async_playwright().start()

        # Pre-create browser instances (but don't launch browsers yet - lazy init)
        for i in range(self.size):
            instance = BrowserInstance(id=i)

            # Create unique fingerprint for each browser
            if self.enable_stealth:
                instance.fingerprint = FingerprintManager(seed=f"pool-{i}")

            self.browsers.append(instance)

        self._initialized = True

        # Start health check background task
        self._health_check_task = asyncio.create_task(self._health_check_loop())

        # NEW: Warmup browsers in background if requested
        if self.warmup_on_init:
            logger.info("Starting browser warmup in background...")
            self._warmup_task = asyncio.create_task(self._warmup_browsers())
            logger.info("Browser pool initialized with warmup (browsers launching in background)")
        else:
            logger.info("Browser pool initialized (browsers will be created on demand)")

    async def shutdown(self):
        """
        Gracefully shutdown the browser pool.

        Closes all browsers and stops health monitoring.
        """
        logger.info("Shutting down browser pool...")

        # Signal shutdown
        self._shutdown_event.set()

        # Stop warmup task (NEW)
        if self._warmup_task:
            self._warmup_task.cancel()
            try:
                await self._warmup_task
            except asyncio.CancelledError:
                pass

        # Stop health check task
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        # Close all browsers
        async with self._pool_lock:
            for instance in self.browsers:
                await self._close_browser_instance(instance)

        # Stop playwright
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None

        self._initialized = False
        logger.info("Browser pool shutdown complete")

    async def _close_browser_instance(self, instance: BrowserInstance):
        """Close a single browser instance."""
        if instance.browser:
            try:
                await instance.browser.close()
                logger.debug(f"Closed browser {instance.id}")
            except Exception as e:
                logger.warning(f"Error closing browser {instance.id}: {e}")
            finally:
                instance.browser = None
                instance.context = None
                instance.page = None

    # =========================================================================
    # Browser Creation and Management
    # =========================================================================

    async def _ensure_browser_ready(self, instance: BrowserInstance) -> bool:
        """
        Ensure browser instance is created and ready.

        Lazy initialization - creates browser on first use.

        Args:
            instance: BrowserInstance to ensure is ready

        Returns:
            True if browser is ready, False if creation failed
        """
        # Already created and healthy
        if instance.browser and instance.healthy:
            return True

        # Need to create or replace
        try:
            # Close existing if unhealthy
            if instance.browser:
                await self._close_browser_instance(instance)

            # Launch new browser
            logger.debug(f"Creating browser {instance.id}...")

            # Browser launch args
            launch_args = {
                'headless': self.headless,
            }

            # Add stealth args if available
            if self.enable_stealth and instance.fingerprint:
                # Use stealth args from stealth_utils if available
                try:
                    from .stealth_utils import get_stealth_args
                    stealth_args = get_stealth_args()
                    launch_args.update(stealth_args)
                except ImportError:
                    pass

            instance.browser = await self.playwright.chromium.launch(**launch_args)

            # Create context with fingerprint
            context_args = {}

            if self.enable_stealth and instance.fingerprint:
                fp = instance.fingerprint.fingerprint
                context_args = {
                    'viewport': {
                        'width': fp['screen']['width'],
                        'height': fp['screen']['height']
                    },
                    'screen': {
                        'width': fp['screen']['width'],
                        'height': fp['screen']['height']
                    },
                    'locale': fp['locale']['languages'][0] if fp['locale']['languages'] else 'en-US',
                    'timezone_id': fp['locale']['timezone'],
                }

            instance.context = await instance.browser.new_context(**context_args)

            # Inject fingerprint script if using stealth
            if self.enable_stealth and instance.fingerprint:
                injection_script = instance.fingerprint.get_injection_script()
                await instance.context.add_init_script(injection_script)

            # Create default page
            instance.page = await instance.context.new_page()

            instance.healthy = True
            instance.created_at = time.time()
            self.stats['browsers_created'] += 1

            logger.debug(f"Browser {instance.id} created successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to create browser {instance.id}: {e}")
            instance.healthy = False
            self.stats['errors'] += 1
            return False

    async def _replace_browser(self, instance: BrowserInstance):
        """
        Replace an unhealthy or aged browser.

        Args:
            instance: BrowserInstance to replace
        """
        logger.info(f"Replacing browser {instance.id}")

        # Close old browser
        await self._close_browser_instance(instance)

        # Reset state
        instance.active_tasks = 0
        instance.total_tasks = 0
        instance.success_count = 0
        instance.error_count = 0
        instance.domains.clear()
        instance.healthy = False

        # Create new fingerprint
        if self.enable_stealth:
            instance.fingerprint = FingerprintManager(seed=f"pool-{instance.id}-{time.time()}")

        # Recreate browser
        await self._ensure_browser_ready(instance)

        self.stats['browsers_replaced'] += 1

    async def _warmup_browsers(self):
        """
        Background task to pre-launch all browsers for instant access.

        This runs in the background during CLI startup so browsers are
        ready by the time the user enters their first command.
        """
        logger.debug("Browser warmup started")
        warmup_start = time.time()

        try:
            # Launch all browsers in parallel
            tasks = []
            for instance in self.browsers:
                tasks.append(self._ensure_browser_ready(instance))

            # Wait for all to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Count successes
            success_count = sum(1 for r in results if r is True)
            warmup_elapsed = time.time() - warmup_start

            if success_count == len(self.browsers):
                logger.info(f"Browser warmup complete: {success_count}/{len(self.browsers)} browsers ready in {warmup_elapsed:.2f}s")
            else:
                logger.warning(f"Browser warmup partial: {success_count}/{len(self.browsers)} browsers ready in {warmup_elapsed:.2f}s")

        except asyncio.CancelledError:
            logger.debug("Browser warmup cancelled")
            raise
        except Exception as e:
            logger.error(f"Browser warmup failed: {e}")

    async def wait_for_warmup(self, timeout: float = 10.0) -> bool:
        """
        Wait for browser warmup to complete.

        Args:
            timeout: Max seconds to wait (default 10.0)

        Returns:
            True if warmup completed, False if timed out or not running
        """
        if not self._warmup_task:
            return False

        try:
            await asyncio.wait_for(self._warmup_task, timeout=timeout)
            return True
        except asyncio.TimeoutError:
            logger.warning(f"Browser warmup did not complete within {timeout}s")
            return False
        except Exception as e:
            logger.error(f"Error waiting for warmup: {e}")
            return False

    # =========================================================================
    # Browser Assignment
    # =========================================================================

    async def _get_next_browser(self, url: Optional[str] = None) -> Optional[BrowserInstance]:
        """
        Get next browser based on assignment strategy.

        Args:
            url: Optional URL for sticky domain assignment

        Returns:
            BrowserInstance or None if no healthy browser available
        """
        async with self._assignment_lock:
            if self.strategy == AssignmentStrategy.STICKY_DOMAIN and url:
                return await self._get_sticky_browser(url)
            elif self.strategy == AssignmentStrategy.LEAST_LOADED:
                return await self._get_least_loaded_browser()
            elif self.strategy == AssignmentStrategy.RANDOM:
                return await self._get_random_browser()
            else:  # ROUND_ROBIN
                return await self._get_round_robin_browser()

    async def _get_round_robin_browser(self) -> Optional[BrowserInstance]:
        """Get browser using round-robin strategy."""
        # Try all browsers in round-robin order
        for _ in range(self.size):
            instance = self.browsers[self._round_robin_index]
            self._round_robin_index = (self._round_robin_index + 1) % self.size

            # Ensure browser is ready
            if await self._ensure_browser_ready(instance):
                return instance

        logger.error("No healthy browsers available in pool")
        return None

    async def _get_least_loaded_browser(self) -> Optional[BrowserInstance]:
        """Get browser with fewest active tasks."""
        # Find browser with minimum active tasks
        best = None
        min_load = float('inf')

        for instance in self.browsers:
            if await self._ensure_browser_ready(instance):
                if instance.active_tasks < min_load:
                    min_load = instance.active_tasks
                    best = instance

        return best

    async def _get_random_browser(self) -> Optional[BrowserInstance]:
        """Get random healthy browser."""
        import random

        # Get all healthy browsers
        healthy = []
        for instance in self.browsers:
            if await self._ensure_browser_ready(instance):
                healthy.append(instance)

        if not healthy:
            return None

        return random.choice(healthy)

    async def _get_sticky_browser(self, url: str) -> Optional[BrowserInstance]:
        """
        Get browser for specific domain (sticky sessions).

        Same domain always gets same browser to preserve cookies/login state.

        Args:
            url: URL to get browser for

        Returns:
            BrowserInstance or None if no healthy browser available
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc

            # Check if we have a browser assigned to this domain
            if domain in self._domain_to_browser:
                browser_id = self._domain_to_browser[domain]
                instance = self.browsers[browser_id]

                if await self._ensure_browser_ready(instance):
                    instance.add_domain(url)
                    return instance

            # Assign new browser to this domain
            # Use least-loaded strategy for new domains
            instance = await self._get_least_loaded_browser()
            if instance:
                self._domain_to_browser[domain] = instance.id
                instance.add_domain(url)
                return instance

            return None

        except Exception as e:
            logger.warning(f"Error in sticky browser assignment: {e}")
            # Fallback to round-robin
            return await self._get_round_robin_browser()

    # =========================================================================
    # Public API - Acquire/Release
    # =========================================================================

    async def acquire(self, url: Optional[str] = None) -> Optional[BrowserInstance]:
        """
        Acquire a browser from the pool.

        Args:
            url: Optional URL for sticky domain assignment

        Returns:
            BrowserInstance or None if no browser available
        """
        if not self._initialized:
            await self.initialize()

        instance = await self._get_next_browser(url)

        if instance:
            # Track warmup effectiveness (NEW)
            if instance.browser is not None:
                self.stats['warmup_hits'] += 1  # Browser was already warm
            else:
                self.stats['warmup_misses'] += 1  # Had to create on-demand

            instance.active_tasks += 1
            instance.total_tasks += 1
            instance.mark_used()
            self.stats['acquisitions'] += 1
            logger.debug(f"Acquired browser {instance.id} (active={instance.active_tasks})")

        return instance

    async def release(self, instance: BrowserInstance, success: bool = True):
        """
        Release a browser back to the pool.

        Args:
            instance: BrowserInstance to release
            success: Whether the operation was successful
        """
        instance.active_tasks = max(0, instance.active_tasks - 1)

        if success:
            instance.record_success()
        else:
            instance.record_error()

        self.stats['releases'] += 1
        logger.debug(f"Released browser {instance.id} (active={instance.active_tasks})")

    @asynccontextmanager
    async def browser(self, url: Optional[str] = None):
        """
        Context manager for safely acquiring and releasing a browser.

        Usage:
            async with pool.browser() as instance:
                page = instance.page
                await page.goto("https://example.com")

        Args:
            url: Optional URL for sticky domain assignment

        Yields:
            BrowserInstance
        """
        instance = await self.acquire(url)

        if not instance:
            raise RuntimeError("No browser available from pool")

        success = True
        try:
            yield instance
        except Exception as e:
            success = False
            logger.error(f"Error in browser context: {e}")
            raise
        finally:
            await self.release(instance, success=success)

    # =========================================================================
    # Health Monitoring
    # =========================================================================

    async def _health_check_loop(self):
        """Background task for periodic health checks."""
        logger.info(f"Health check loop started (interval={self.health_check_interval}s)")

        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(self.health_check_interval)
                await self._perform_health_check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error: {e}")

    async def _perform_health_check(self):
        """Perform health check on all browsers."""
        self.stats['health_checks'] += 1

        async with self._pool_lock:
            for instance in self.browsers:
                # Skip if browser not yet created (lazy init)
                if not instance.browser:
                    continue

                # Check if browser is too old
                if instance.age_seconds > self.max_browser_age:
                    logger.info(f"Browser {instance.id} exceeded max age ({instance.age_seconds:.0f}s)")
                    await self._replace_browser(instance)
                    continue

                # Check if browser is idle too long
                if instance.idle_seconds > self.max_idle_time and instance.active_tasks == 0:
                    logger.info(f"Browser {instance.id} idle for {instance.idle_seconds:.0f}s, closing")
                    await self._close_browser_instance(instance)
                    continue

                # Check browser health
                try:
                    # Try to get page title as health check
                    if instance.page:
                        await instance.page.evaluate("() => document.title")
                        instance.healthy = True
                except Exception as e:
                    logger.warning(f"Browser {instance.id} health check failed: {e}")
                    instance.healthy = False

                    # Replace if not in use
                    if instance.active_tasks == 0:
                        await self._replace_browser(instance)

    async def check_health(self) -> Dict[str, Any]:
        """
        Manually trigger health check and return status.

        Returns:
            Dict with health status for each browser
        """
        await self._perform_health_check()

        status = {
            'pool_size': self.size,
            'initialized': self._initialized,
            'strategy': self.strategy.value,
            'browsers': []
        }

        for instance in self.browsers:
            browser_status = {
                'id': instance.id,
                'created': instance.browser is not None,
                'healthy': instance.healthy,
                'active_tasks': instance.active_tasks,
                'total_tasks': instance.total_tasks,
                'success_rate': instance.success_rate,
                'age_seconds': instance.age_seconds if instance.browser else 0,
                'idle_seconds': instance.idle_seconds if instance.browser else 0,
                'domains_visited': len(instance.domains),
            }
            status['browsers'].append(browser_status)

        return status

    # =========================================================================
    # Parallel Extraction
    # =========================================================================

    async def parallel_extract(
        self,
        urls: List[str],
        extractor_fn: Callable[[BrowserInstance, str], Any],
        max_concurrent: Optional[int] = None,
        aggregate: bool = True,
    ) -> List[Any]:
        """
        Extract data from multiple URLs in parallel using the browser pool.

        Args:
            urls: List of URLs to process
            extractor_fn: Async function that takes (BrowserInstance, url) and returns result
            max_concurrent: Max concurrent extractions (default: pool size)
            aggregate: Whether to aggregate results into single list (default: True)

        Returns:
            List of results from extractor_fn for each URL

        Example:
            async def extract_contacts(browser: BrowserInstance, url: str):
                await browser.page.goto(url)
                # ... extract logic ...
                return contacts

            results = await pool.parallel_extract(urls, extract_contacts)
        """
        if not self._initialized:
            await self.initialize()

        max_concurrent = max_concurrent or self.size

        # Semaphore to limit concurrency
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_url(url: str) -> Tuple[str, Any, bool]:
            """Process single URL with error handling."""
            async with semaphore:
                try:
                    async with self.browser(url) as instance:
                        result = await extractor_fn(instance, url)
                        return url, result, True
                except Exception as e:
                    logger.error(f"Extraction failed for {url}: {e}")
                    return url, None, False

        # Process all URLs concurrently
        logger.info(f"Starting parallel extraction for {len(urls)} URLs (max_concurrent={max_concurrent})")
        start_time = time.time()

        tasks = [process_url(url) for url in urls]
        results = await asyncio.gather(*tasks)

        elapsed = time.time() - start_time
        logger.info(f"Parallel extraction completed in {elapsed:.2f}s")

        # Aggregate results
        if aggregate:
            aggregated = []
            for url, result, success in results:
                if success and result:
                    # Handle different result types
                    if isinstance(result, list):
                        aggregated.extend(result)
                    else:
                        aggregated.append(result)
            return aggregated
        else:
            # Return raw results with metadata
            return [
                {'url': url, 'result': result, 'success': success}
                for url, result, success in results
            ]

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics."""
        return {
            **self.stats,
            'pool_size': self.size,
            'strategy': self.strategy.value,
            'browsers_active': sum(1 for b in self.browsers if b.browser is not None),
            'total_active_tasks': sum(b.active_tasks for b in self.browsers),
            'total_completed_tasks': sum(b.total_tasks for b in self.browsers),
        }

    def get_browser_by_id(self, browser_id: int) -> Optional[BrowserInstance]:
        """Get browser instance by ID."""
        if 0 <= browser_id < len(self.browsers):
            return self.browsers[browser_id]
        return None

    def get_browsers_by_domain(self, domain: str) -> List[BrowserInstance]:
        """Get all browsers that have visited a domain."""
        return [b for b in self.browsers if domain in b.domains]


# =============================================================================
# Example Usage
# =============================================================================

async def example_basic_usage():
    """Example: Basic pool usage with context manager."""
    pool = BrowserPool(size=3, strategy=AssignmentStrategy.ROUND_ROBIN)

    try:
        # Initialize pool
        await pool.initialize()

        # Use a browser
        async with pool.browser() as instance:
            page = instance.page
            await page.goto("https://example.com")
            title = await page.title()
            print(f"Page title: {title}")

        # Check pool health
        health = await pool.check_health()
        print(f"Pool health: {health}")

    finally:
        await pool.shutdown()


async def example_parallel_extraction():
    """Example: Parallel extraction from multiple URLs."""

    # Define extraction function
    async def extract_page_info(instance: BrowserInstance, url: str) -> Dict[str, str]:
        """Extract title and URL from a page."""
        try:
            await instance.page.goto(url, wait_until="domcontentloaded", timeout=10000)
            title = await instance.page.title()
            return {
                'url': url,
                'title': title,
                'success': True
            }
        except Exception as e:
            return {
                'url': url,
                'title': None,
                'success': False,
                'error': str(e)
            }

    # Create pool
    pool = BrowserPool(size=5, strategy=AssignmentStrategy.LEAST_LOADED)

    try:
        await pool.initialize()

        # URLs to process
        urls = [
            "https://example.com",
            "https://httpbin.org",
            "https://www.python.org",
            "https://github.com",
            "https://stackoverflow.com",
        ]

        # Extract in parallel
        results = await pool.parallel_extract(
            urls,
            extract_page_info,
            aggregate=False  # Keep individual results
        )

        # Print results
        for result in results:
            print(f"{result['url']}: {result.get('title', 'Failed')}")

        # Print stats
        print(f"\nPool stats: {pool.get_stats()}")

    finally:
        await pool.shutdown()


async def example_sticky_sessions():
    """Example: Sticky sessions for maintaining cookies/login state."""
    pool = BrowserPool(size=3, strategy=AssignmentStrategy.STICKY_DOMAIN)

    try:
        await pool.initialize()

        # Multiple requests to same domain will use same browser
        urls = [
            "https://example.com/page1",
            "https://example.com/page2",
            "https://example.com/page3",
            "https://other.com/page1",
            "https://other.com/page2",
        ]

        for url in urls:
            async with pool.browser(url) as instance:
                await instance.page.goto(url)
                print(f"Browser {instance.id} visited {url}")
                print(f"  Domains for this browser: {instance.domains}")

    finally:
        await pool.shutdown()


async def example_warmup_mode():
    """Example: Warmup mode for instant CLI startup (like Playwright MCP)."""
    import time

    # Create pool with warmup enabled
    pool = BrowserPool(size=1, warmup_on_init=True, strategy=AssignmentStrategy.ROUND_ROBIN)

    try:
        # Initialize - browser starts launching in background
        print("Initializing pool with warmup...")
        init_start = time.time()
        await pool.initialize()
        init_elapsed = time.time() - init_start
        print(f"Pool initialized in {init_elapsed:.3f}s (browser launching in background)")

        # Optional: Wait for warmup to complete
        print("\nWaiting for browser warmup...")
        warmup_ok = await pool.wait_for_warmup(timeout=10.0)
        print(f"Warmup complete: {warmup_ok}")

        # First task - should be instant since browser is warm
        print("\nFirst task (should be instant)...")
        task1_start = time.time()
        async with pool.browser() as instance:
            await instance.page.goto("https://example.com")
            title = await instance.page.title()
            print(f"Page title: {title}")
        task1_elapsed = time.time() - task1_start
        print(f"First task completed in {task1_elapsed:.3f}s (browser was warm)")

        # Second task - reuses same browser
        print("\nSecond task (reusing browser)...")
        task2_start = time.time()
        async with pool.browser() as instance:
            await instance.page.goto("https://httpbin.org")
            title = await instance.page.title()
            print(f"Page title: {title}")
        task2_elapsed = time.time() - task2_start
        print(f"Second task completed in {task2_elapsed:.3f}s")

        # Show stats
        stats = pool.get_stats()
        print(f"\nPool stats:")
        print(f"  Warmup hits: {stats['warmup_hits']} (instant access)")
        print(f"  Warmup misses: {stats['warmup_misses']} (had to create)")
        print(f"  Total acquisitions: {stats['acquisitions']}")

    finally:
        await pool.shutdown()


async def example_context_manager():
    """Example: Using async context manager for automatic cleanup."""
    import time

    # Context manager handles initialization and cleanup automatically
    async with BrowserPool(size=1, warmup_on_init=True) as pool:
        # Optional: Wait for warmup
        await pool.wait_for_warmup(timeout=10.0)

        # Use the pool
        async with pool.browser() as instance:
            await instance.page.goto("https://example.com")
            title = await instance.page.title()
            print(f"Page title: {title}")

        # Pool automatically shuts down when exiting context
        stats = pool.get_stats()
        print(f"Completed {stats['acquisitions']} acquisitions")

    # Cleanup happens automatically here, even if there was an exception


if __name__ == "__main__":
    """Run examples."""
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "parallel":
        asyncio.run(example_parallel_extraction())
    elif len(sys.argv) > 1 and sys.argv[1] == "sticky":
        asyncio.run(example_sticky_sessions())
    elif len(sys.argv) > 1 and sys.argv[1] == "warmup":
        asyncio.run(example_warmup_mode())
    elif len(sys.argv) > 1 and sys.argv[1] == "context":
        asyncio.run(example_context_manager())
    else:
        asyncio.run(example_basic_usage())
