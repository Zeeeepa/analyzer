"""
Global Browser Pool - Singleton warmup pool for instant CLI startup

This module provides a global browser pool that is initialized once
at CLI startup and reused across all tasks. This eliminates the 6+
second browser launch delay on every task.

Usage:
    from agent.global_browser_pool import get_global_pool, warmup_global_pool

    # During CLI startup (run_ultimate.py)
    await warmup_global_pool()

    # When creating PlaywrightClient
    pool = await get_global_pool()
    if pool:
        browser_instance = await pool.acquire()

Author: Claude
Date: 2025-12-12
"""

import asyncio
from typing import Optional
from loguru import logger

# Import browser pool
try:
    from .browser_pool import BrowserPool, AssignmentStrategy
    POOL_AVAILABLE = True
except ImportError:
    POOL_AVAILABLE = False
    logger.warning("BrowserPool not available")


# =============================================================================
# Global Pool Singleton
# =============================================================================

_global_pool: Optional[BrowserPool] = None
_pool_lock = asyncio.Lock()


async def get_global_pool() -> Optional[BrowserPool]:
    """
    Get the global browser pool instance.

    Returns:
        BrowserPool instance or None if not initialized
    """
    return _global_pool


async def warmup_global_pool(
    size: int = 1,
    headless: bool = True,
    enable_stealth: bool = True,
    background: bool = True
) -> Optional[BrowserPool]:
    """
    Initialize and warmup the global browser pool.

    This should be called ONCE during CLI startup (in run_ultimate.py)
    to pre-launch browsers in the background.

    Args:
        size: Number of browsers in pool (default 1 for CLI)
        headless: Run browsers in headless mode
        enable_stealth: Enable stealth fingerprints
        background: Launch browsers in background (non-blocking)

    Returns:
        BrowserPool instance or None if unavailable
    """
    global _global_pool

    if not POOL_AVAILABLE:
        logger.warning("BrowserPool not available - skipping warmup")
        return None

    async with _pool_lock:
        if _global_pool is not None:
            logger.debug("Global browser pool already initialized")
            return _global_pool

        logger.info(f"Initializing global browser pool (size={size}, headless={headless})")

        # Create pool with warmup enabled
        _global_pool = BrowserPool(
            size=size,
            strategy=AssignmentStrategy.ROUND_ROBIN,
            health_check_interval=300,  # 5 minutes
            max_browser_age=7200,  # 2 hours (longer for CLI reuse)
            max_idle_time=1800,  # 30 minutes
            headless=headless,
            enable_stealth=enable_stealth,
            warmup_on_init=True  # KEY: Pre-launch browsers
        )

        # Initialize pool (starts warmup in background)
        await _global_pool.initialize()

        if not background:
            # Wait for warmup to complete (blocking)
            logger.info("Waiting for browser warmup to complete...")
            await _global_pool.wait_for_warmup(timeout=15.0)
            logger.info("Browser warmup complete")

        return _global_pool


async def shutdown_global_pool():
    """
    Shutdown the global browser pool.

    This should be called during CLI shutdown to clean up browsers.
    """
    global _global_pool

    async with _pool_lock:
        if _global_pool is None:
            return

        logger.info("Shutting down global browser pool...")
        await _global_pool.shutdown()
        _global_pool = None
        logger.info("Global browser pool shutdown complete")


def is_global_pool_ready() -> bool:
    """
    Check if global pool is initialized and has warm browsers.

    Returns:
        True if pool is ready with warm browsers
    """
    if _global_pool is None:
        return False

    # Check if any browser instances are already created
    return any(b.browser is not None for b in _global_pool.browsers)


def get_global_pool_stats() -> dict:
    """
    Get statistics from the global browser pool.

    Returns:
        Dict with pool stats or empty dict if not initialized
    """
    if _global_pool is None:
        return {}

    return _global_pool.get_stats()


# =============================================================================
# Convenience Functions
# =============================================================================

async def acquire_global_browser():
    """
    Acquire a browser from the global pool.

    Returns:
        BrowserInstance or None if pool not available
    """
    pool = await get_global_pool()
    if pool is None:
        return None

    return await pool.acquire()


async def release_global_browser(instance, success: bool = True):
    """
    Release a browser back to the global pool.

    Args:
        instance: BrowserInstance to release
        success: Whether the operation was successful
    """
    pool = await get_global_pool()
    if pool is None:
        return

    await pool.release(instance, success=success)
