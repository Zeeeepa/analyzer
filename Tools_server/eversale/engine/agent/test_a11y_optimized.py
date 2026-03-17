"""
Test script for optimized a11y system.

Run with: python test_a11y_optimized.py
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from a11y_browser import A11yBrowser, create_browser
from simple_agent import SimpleAgent
import a11y_config


async def test_browser_metrics():
    """Test browser with metrics tracking."""
    print("=" * 60)
    print("Test 1: Browser with Metrics")
    print("=" * 60)

    async with A11yBrowser(headless=True) as browser:
        # Navigate
        print("\n1. Navigating to example.com...")
        await browser.navigate("https://example.com")

        # First snapshot (cache miss)
        print("2. Taking first snapshot...")
        snapshot1 = await browser.snapshot()
        print(f"   Found {len(snapshot1.elements)} elements")

        # Second snapshot (should be cache hit)
        print("3. Taking second snapshot (should be cached)...")
        snapshot2 = await browser.snapshot()
        print(f"   Found {len(snapshot2.elements)} elements")

        # Click something
        if snapshot1.elements:
            print(f"\n4. Clicking first element: {snapshot1.elements[0]}")
            result = await browser.click(snapshot1.elements[0].ref)
            print(f"   Result: {result.success}")

        # Get metrics
        print("\n5. Metrics:")
        metrics = browser.get_metrics()
        for key, value in metrics.items():
            if isinstance(value, float):
                print(f"   {key}: {value:.3f}")
            else:
                print(f"   {key}: {value}")

    print("\nTest 1 completed!")


async def test_agent_retry():
    """Test agent with retry logic."""
    print("\n" + "=" * 60)
    print("Test 2: Agent with Retry")
    print("=" * 60)

    # Configure for testing
    a11y_config.LOG_ACTIONS = True
    a11y_config.LOG_ERRORS = True
    a11y_config.MAX_RETRIES = 2

    # Use fallback mode (no LLM)
    agent = SimpleAgent(llm_client=None, headless=True, max_steps=5)

    print("\nRunning agent task...")
    result = await agent.run("Search Google for Python tutorials")

    print(f"\nResult:")
    print(f"  Success: {result.success}")
    print(f"  Steps: {result.steps_taken}")
    print(f"  Final URL: {result.final_url}")
    if result.error:
        print(f"  Error: {result.error}")

    print(f"\nMetrics:")
    for key, value in result.metrics.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.3f}")
        else:
            print(f"  {key}: {value}")

    print("\nTest 2 completed!")


async def test_snapshot_caching():
    """Test snapshot caching performance."""
    print("\n" + "=" * 60)
    print("Test 3: Snapshot Caching Performance")
    print("=" * 60)

    import time

    a11y_config.ENABLE_SNAPSHOT_CACHE = True
    a11y_config.SNAPSHOT_CACHE_TTL = 5.0

    async with A11yBrowser(headless=True) as browser:
        await browser.navigate("https://example.com")

        # Measure uncached snapshot
        print("\n1. First snapshot (uncached)...")
        start = time.time()
        snapshot1 = await browser.snapshot()
        uncached_time = time.time() - start
        print(f"   Time: {uncached_time * 1000:.1f}ms")
        print(f"   Elements: {len(snapshot1.elements)}")

        # Measure cached snapshot
        print("\n2. Second snapshot (cached)...")
        start = time.time()
        snapshot2 = await browser.snapshot()
        cached_time = time.time() - start
        print(f"   Time: {cached_time * 1000:.1f}ms")
        print(f"   Elements: {len(snapshot2.elements)}")

        # Calculate speedup
        if cached_time > 0:
            speedup = uncached_time / cached_time
            print(f"\n   Speedup: {speedup:.1f}x faster")

        # Verify cache hit
        metrics = browser.get_metrics()
        print(f"\n3. Cache stats:")
        print(f"   Snapshots taken: {metrics['snapshots_taken']}")
        print(f"   Cache hits: {metrics['cache_hits']}")
        print(f"   Hit rate: {metrics['cache_hit_rate']:.1f}%")

    print("\nTest 3 completed!")


async def test_config_customization():
    """Test configuration customization."""
    print("\n" + "=" * 60)
    print("Test 4: Configuration Customization")
    print("=" * 60)

    # Show current config
    print("\nCurrent configuration:")
    print(f"  SNAPSHOT_CACHE_TTL: {a11y_config.SNAPSHOT_CACHE_TTL}s")
    print(f"  MAX_RETRIES: {a11y_config.MAX_RETRIES}")
    print(f"  DEFAULT_TIMEOUT: {a11y_config.DEFAULT_TIMEOUT}ms")
    print(f"  ENABLE_SNAPSHOT_CACHE: {a11y_config.ENABLE_SNAPSHOT_CACHE}")
    print(f"  ENABLE_AUTO_RETRY: {a11y_config.ENABLE_AUTO_RETRY}")
    print(f"  LOG_ACTIONS: {a11y_config.LOG_ACTIONS}")

    # Modify config
    print("\nModifying configuration...")
    a11y_config.SNAPSHOT_CACHE_TTL = 10.0
    a11y_config.MAX_RETRIES = 3
    a11y_config.LOG_ACTIONS = False

    print("\nNew configuration:")
    print(f"  SNAPSHOT_CACHE_TTL: {a11y_config.SNAPSHOT_CACHE_TTL}s")
    print(f"  MAX_RETRIES: {a11y_config.MAX_RETRIES}")
    print(f"  LOG_ACTIONS: {a11y_config.LOG_ACTIONS}")

    # Reset to defaults
    a11y_config.SNAPSHOT_CACHE_TTL = 2.0
    a11y_config.MAX_RETRIES = 2
    a11y_config.LOG_ACTIONS = True

    print("\nTest 4 completed!")


async def main():
    """Run all tests."""
    print("\nA11y System Optimization Tests")
    print("=" * 60)

    try:
        await test_browser_metrics()
        await test_agent_retry()
        await test_snapshot_caching()
        await test_config_customization()

        print("\n" + "=" * 60)
        print("All tests completed successfully!")
        print("=" * 60)

    except Exception as e:
        print(f"\nTest failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
