"""
Test Suite for Visual Grounding Module

Demonstrates usage and validates functionality.
"""

import asyncio
from pathlib import Path
from playwright.async_api import async_playwright
from loguru import logger

from visual_grounding import (
    VisualGroundingEngine,
    GroundingStrategy,
    ElementType,
    get_engine,
    ground_and_click,
    ground_and_fill,
    ground_and_extract_text
)


async def test_basic_grounding():
    """Test basic element grounding on a simple page."""
    logger.info("=" * 70)
    logger.info("TEST: Basic Element Grounding")
    logger.info("=" * 70)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        # Navigate to a test page
        await page.goto("https://www.google.com")

        # Initialize engine
        engine = VisualGroundingEngine()

        # Test 1: Ground the search input
        logger.info("\n1. Grounding search input...")
        result = await engine.ground_element(
            page,
            "the search input box",
            element_type=ElementType.INPUT
        )

        if result.success:
            logger.info(f"✓ Found search input with confidence {result.best_match.confidence:.2f}")
            logger.info(f"  Method: {result.best_match.match_method.value}")
            logger.info(f"  Center: {result.best_match.center}")
        else:
            logger.error(f"✗ Failed to find search input: {result.error}")

        # Test 2: Ground the search button
        logger.info("\n2. Grounding search button...")
        result = await engine.ground_element(
            page,
            "the Google Search button",
            element_type=ElementType.BUTTON
        )

        if result.success:
            logger.info(f"✓ Found search button with confidence {result.best_match.confidence:.2f}")
            logger.info(f"  Method: {result.best_match.match_method.value}")
        else:
            logger.error(f"✗ Failed to find search button: {result.error}")

        await browser.close()


async def test_hybrid_strategy():
    """Test hybrid grounding (DOM + Vision fallback)."""
    logger.info("=" * 70)
    logger.info("TEST: Hybrid Grounding Strategy")
    logger.info("=" * 70)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        await page.goto("https://www.google.com")

        engine = VisualGroundingEngine()

        # Test with HYBRID strategy (default)
        logger.info("\nTesting HYBRID strategy...")
        result = await engine.ground_element(
            page,
            "the search box",
            strategy=GroundingStrategy.HYBRID
        )

        if result.success:
            logger.info(f"✓ Hybrid grounding succeeded")
            logger.info(f"  Strategy: {result.strategy_used.value}")
            logger.info(f"  Confidence: {result.best_match.confidence:.2f}")
            logger.info(f"  Processing time: {result.processing_time:.3f}s")
        else:
            logger.error(f"✗ Hybrid grounding failed")

        await browser.close()


async def test_multiple_elements():
    """Test grounding multiple elements in parallel."""
    logger.info("=" * 70)
    logger.info("TEST: Multiple Element Grounding")
    logger.info("=" * 70)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        await page.goto("https://www.google.com")

        engine = VisualGroundingEngine()

        # Ground multiple elements at once
        descriptions = [
            "the search input",
            "the Google Search button",
            "the I'm Feeling Lucky button"
        ]

        logger.info(f"\nGrounding {len(descriptions)} elements in parallel...")
        results = await engine.ground_multiple_elements(page, descriptions)

        for desc, result in results.items():
            if result.success:
                logger.info(f"✓ '{desc}': confidence {result.best_match.confidence:.2f}")
            else:
                logger.error(f"✗ '{desc}': failed")

        await browser.close()


async def test_actions():
    """Test actions on grounded elements."""
    logger.info("=" * 70)
    logger.info("TEST: Actions on Grounded Elements")
    logger.info("=" * 70)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        await page.goto("https://www.google.com")

        engine = VisualGroundingEngine()

        # Test 1: Fill an input
        logger.info("\n1. Filling search input...")
        result = await engine.ground_element(
            page,
            "the search input",
            element_type=ElementType.INPUT
        )

        if result.success:
            success = await engine.fill_grounded_element(
                page,
                result.best_match,
                "Eversale AI agent"
            )
            if success:
                logger.info("✓ Successfully filled input")
            else:
                logger.error("✗ Failed to fill input")

            # Wait to see the result
            await asyncio.sleep(2)

        # Test 2: Click a button
        logger.info("\n2. Clicking search button...")
        result = await engine.ground_element(
            page,
            "the Google Search button",
            element_type=ElementType.BUTTON
        )

        if result.success:
            success = await engine.click_grounded_element(page, result.best_match)
            if success:
                logger.info("✓ Successfully clicked button")
                await asyncio.sleep(3)  # Wait for search results
            else:
                logger.error("✗ Failed to click button")

        await browser.close()


async def test_convenience_functions():
    """Test convenience functions."""
    logger.info("=" * 70)
    logger.info("TEST: Convenience Functions")
    logger.info("=" * 70)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        await page.goto("https://www.google.com")

        # Test ground_and_fill
        logger.info("\n1. Using ground_and_fill...")
        success = await ground_and_fill(page, "the search input", "Eversale test")

        if success:
            logger.info("✓ ground_and_fill succeeded")
        else:
            logger.error("✗ ground_and_fill failed")

        await asyncio.sleep(1)

        # Test ground_and_click
        logger.info("\n2. Using ground_and_click...")
        success = await ground_and_click(page, "the Google Search button")

        if success:
            logger.info("✓ ground_and_click succeeded")
            await asyncio.sleep(3)
        else:
            logger.error("✗ ground_and_click failed")

        await browser.close()


async def test_canvas_grounding():
    """Test grounding elements in canvas applications."""
    logger.info("=" * 70)
    logger.info("TEST: Canvas Element Grounding")
    logger.info("=" * 70)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        # Navigate to a page with canvas (example: a drawing app)
        # For this test, we'll use a simple HTML5 canvas demo
        await page.goto("https://developer.mozilla.org/en-US/docs/Web/API/Canvas_API")

        engine = VisualGroundingEngine()

        logger.info("\nLooking for canvas element...")

        # Try to ground an element within a canvas
        # Note: This will work better on actual canvas applications
        result = await engine.ground_canvas_element(
            page,
            "the canvas drawing area",
            canvas_selector="canvas"
        )

        if result:
            logger.info(f"✓ Found canvas element")
            logger.info(f"  Is canvas element: {result.is_canvas_element}")
            logger.info(f"  Confidence: {result.confidence:.2f}")
        else:
            logger.info("✗ No canvas element found (this is expected on this page)")

        await browser.close()


async def test_region_focus():
    """Test region focus strategy for complex pages."""
    logger.info("=" * 70)
    logger.info("TEST: Region Focus Strategy")
    logger.info("=" * 70)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        # Navigate to a complex page
        await page.goto("https://news.ycombinator.com")

        engine = VisualGroundingEngine()

        logger.info("\nUsing REGION_FOCUS strategy...")
        result = await engine.ground_element(
            page,
            "the login link",
            strategy=GroundingStrategy.REGION_FOCUS
        )

        if result.success:
            logger.info(f"✓ Region focus succeeded")
            logger.info(f"  Confidence: {result.best_match.confidence:.2f}")
            if result.best_match.region_path:
                logger.info(f"  Region path: {len(result.best_match.region_path)} levels")
        else:
            logger.error(f"✗ Region focus failed")

        await browser.close()


async def test_stats():
    """Test statistics tracking."""
    logger.info("=" * 70)
    logger.info("TEST: Statistics Tracking")
    logger.info("=" * 70)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        await page.goto("https://www.google.com")

        engine = VisualGroundingEngine()

        # Perform several groundings
        await engine.ground_element(page, "the search input")
        await engine.ground_element(page, "the Google Search button")
        await engine.ground_element(page, "the I'm Feeling Lucky button")

        # Get stats
        stats = engine.get_stats()

        logger.info("\nGrounding Statistics:")
        logger.info(f"  Total groundings: {stats['total_groundings']}")
        logger.info(f"  DOM successes: {stats['dom_successes']}")
        logger.info(f"  Vision successes: {stats['vision_successes']}")
        logger.info(f"  Region focus uses: {stats['region_focus_uses']}")
        logger.info(f"  Average confidence: {stats['avg_confidence']:.2f}")

        await browser.close()


async def test_error_handling():
    """Test error handling and graceful degradation."""
    logger.info("=" * 70)
    logger.info("TEST: Error Handling")
    logger.info("=" * 70)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        await page.goto("https://www.google.com")

        engine = VisualGroundingEngine()

        # Test 1: Non-existent element
        logger.info("\n1. Searching for non-existent element...")
        result = await engine.ground_element(
            page,
            "the purple unicorn button that doesn't exist"
        )

        if not result.success:
            logger.info("✓ Correctly failed to find non-existent element")
        else:
            logger.warning("✗ False positive - found non-existent element")

        # Test 2: Invalid strategy
        logger.info("\n2. Testing with unavailable vision model...")
        # This will gracefully fall back to DOM-only if vision unavailable
        result = await engine.ground_element(
            page,
            "the search input",
            strategy=GroundingStrategy.VISION_ONLY
        )

        if result.success:
            logger.info("✓ Vision strategy worked")
        else:
            logger.info("✓ Vision strategy gracefully failed (expected if no vision model)")

        await browser.close()


async def run_all_tests():
    """Run all test cases."""
    logger.info("\n" + "=" * 70)
    logger.info("VISUAL GROUNDING MODULE - COMPREHENSIVE TEST SUITE")
    logger.info("=" * 70 + "\n")

    tests = [
        ("Basic Grounding", test_basic_grounding),
        ("Hybrid Strategy", test_hybrid_strategy),
        ("Multiple Elements", test_multiple_elements),
        ("Actions", test_actions),
        ("Convenience Functions", test_convenience_functions),
        ("Canvas Grounding", test_canvas_grounding),
        ("Region Focus", test_region_focus),
        ("Statistics", test_stats),
        ("Error Handling", test_error_handling),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            logger.info(f"\n{'=' * 70}")
            logger.info(f"Running: {test_name}")
            logger.info(f"{'=' * 70}")
            await test_func()
            passed += 1
            logger.info(f"✓ {test_name} PASSED")
        except Exception as e:
            failed += 1
            logger.error(f"✗ {test_name} FAILED: {e}")
            import traceback
            traceback.print_exc()

        # Wait between tests
        await asyncio.sleep(1)

    # Print summary
    logger.info("\n" + "=" * 70)
    logger.info("TEST SUMMARY")
    logger.info("=" * 70)
    logger.info(f"Passed: {passed}/{len(tests)}")
    logger.info(f"Failed: {failed}/{len(tests)}")
    logger.info("=" * 70 + "\n")


if __name__ == "__main__":
    # Run individual test
    # asyncio.run(test_basic_grounding())

    # Or run all tests
    asyncio.run(run_all_tests())
