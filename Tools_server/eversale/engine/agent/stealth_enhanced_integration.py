"""
Stealth Enhanced Integration Examples
======================================

Shows how to integrate stealth_enhanced.py with existing Eversale components:
- playwright_direct.py
- stealth_utils.py
- bs_detector.py
- captcha_solver.py

Example usage patterns for maximum stealth.

Author: Claude
Date: 2025-12-02
"""

import asyncio
import os
from playwright.async_api import async_playwright
from typing import Optional
from loguru import logger

from .stealth_enhanced import (
    FingerprintManager,
    BehaviorMimicry,
    ProxyManager,
    EnhancedStealthSession,
    create_stealth_context,
    get_stealth_session,
    enhance_existing_page,
    SiteProfile,
)


# =============================================================================
# EXAMPLE 1: Basic Enhanced Stealth Session
# =============================================================================

async def example_basic_stealth():
    """
    Basic usage: Create stealth session and navigate safely.
    """
    async with async_playwright() as p:
        # Create stealth context with fingerprint
        context, fp_manager = await create_stealth_context(
            p,
            headless=False,
            fingerprint_seed="my-session-123"
        )

        page = await context.new_page()

        # Use enhanced stealth session
        async with get_stealth_session(page) as session:
            # Navigate with automatic profile detection
            await session.navigate("https://linkedin.com")

            # Wait and read (human-like)
            await session.wait_and_read(content_length=2000)

            # Scroll naturally
            await session.scroll("down")

            # Click element with natural mouse movement
            await session.click("button.sign-in")

            # Type with human-like patterns (including typos)
            await session.type("#username", "myemail@example.com")
            await session.type("#password", "mypassword")

            # Submit
            await session.click("button[type='submit']")

        await context.close()


# =============================================================================
# EXAMPLE 2: Integration with Existing PlaywrightClient
# =============================================================================

async def example_integrate_with_playwright_client():
    """
    Enhance existing PlaywrightClient with stealth features.
    """
    from .playwright_direct import PlaywrightClient

    # Create client
    client = PlaywrightClient(headless=False)
    await client.connect()

    # Enhance the page with stealth
    await enhance_existing_page(client.page, fingerprint_seed="session-456")

    # Now use stealth session for all interactions
    async with get_stealth_session(client.page) as session:
        await session.navigate("https://facebook.com/ads/library")
        await session.scroll("down")
        await session.click(".search-button")

    await client.disconnect()


# =============================================================================
# EXAMPLE 3: Proxy Rotation with Stealth
# =============================================================================

async def example_proxy_rotation():
    """
    Use proxy rotation with stealth fingerprints.
    """
    # Create proxy manager
    proxy_manager = ProxyManager()

    # Add proxies (residential preferred for social media)
    proxy_manager.add_proxy(
        server="http://proxy1.example.com:8080",
        username="user1",
        password=os.environ.get("PROXY1_PASSWORD", "TEST_password_placeholder"),  # Configure via environment
        proxy_type="residential"
    )
    proxy_manager.add_proxy(
        server="http://proxy2.example.com:8080",
        username="user2",
        password=os.environ.get("PROXY2_PASSWORD", "TEST_password_placeholder"),  # Configure via environment
        proxy_type="mobile"
    )

    async with async_playwright() as p:
        # Get proxy for domain (sticky session)
        proxy = proxy_manager.get_proxy(domain="linkedin.com", sticky=True)

        # Create context with proxy
        context, fp_manager = await create_stealth_context(
            p,
            headless=False,
            proxy=proxy,
            fingerprint_seed="proxy-session-1"
        )

        page = await context.new_page()

        async with get_stealth_session(page, proxy_manager=proxy_manager) as session:
            try:
                await session.navigate("https://linkedin.com")
                # ... do work ...

                # Record success
                proxy_manager.record_success(proxy)

            except Exception as e:
                # Record failure
                proxy_manager.record_failure(proxy)
                logger.error(f"Proxy failed: {e}")

        # Print proxy stats
        logger.info(f"Proxy stats: {proxy_manager.get_stats()}")

        await context.close()


# =============================================================================
# EXAMPLE 4: Site-Specific Profiles
# =============================================================================

async def example_site_profiles():
    """
    Demonstrate site-specific stealth profiles.
    """
    async with async_playwright() as p:
        context, fp_manager = await create_stealth_context(p, headless=False)
        page = await context.new_page()

        async with get_stealth_session(page) as session:
            # LinkedIn: slow, cautious, human-like
            await session.navigate("https://linkedin.com/in/someone")
            # Profile automatically detected, uses:
            # - Mobile proxy preference
            # - Slow delays (3-7s navigation, 1-3s actions)
            # - Scrolling before extraction
            # - Random movements
            # - Reading pauses

            await session.scroll("down")
            await session.wait_and_read(3000)

            # Amazon: very slow, mimics shopping
            await session.navigate("https://amazon.com/product")
            # Profile uses:
            # - Residential proxy
            # - Very slow delays (3-8s navigation, 1-4s actions)
            # - Session warmup (visit homepage first)
            # - Multiple page visits

            # Google: faster, less cautious
            await session.navigate("https://google.com/search?q=test")
            # Profile uses:
            # - Datacenter proxy OK
            # - Fast delays (1-3s navigation)
            # - No unnecessary scrolling
            # - Frequent rotation

        await context.close()


# =============================================================================
# EXAMPLE 5: Advanced Fingerprint Customization
# =============================================================================

async def example_custom_fingerprint():
    """
    Create custom fingerprint with specific characteristics.
    """
    # Generate fingerprint with seed (reproducible)
    fp_manager = FingerprintManager(seed="my-custom-seed-789")

    # Access fingerprint details
    fp = fp_manager.fingerprint
    logger.info(f"Screen: {fp['screen']['width']}x{fp['screen']['height']}")
    logger.info(f"WebGL: {fp['webgl']['vendor']}")
    logger.info(f"CPU cores: {fp['hardware']['cores']}")
    logger.info(f"Timezone: {fp['locale']['timezone']}")

    async with async_playwright() as p:
        # Create context with this fingerprint
        context_options = fp_manager.get_context_options()
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-automation",
        ]

        browser = await p.chromium.launch(headless=False, args=launch_args)
        context = await browser.new_context(**context_options)

        # Inject fingerprint
        await context.add_init_script(fp_manager.get_injection_script())

        page = await context.new_page()
        await page.goto("https://browserleaks.com/canvas")

        # Test fingerprint
        await asyncio.sleep(10)

        await browser.close()


# =============================================================================
# EXAMPLE 6: CAPTCHA Handling with Stealth
# =============================================================================

async def example_captcha_handling():
    """
    Handle CAPTCHAs with stealth session.
    """
    from .captcha_solver import PageCaptchaHandler, ScrappyCaptchaBypasser

    async with async_playwright() as p:
        context, fp_manager = await create_stealth_context(p, headless=False)
        page = await context.new_page()

        # Create CAPTCHA handler
        captcha_handler = PageCaptchaHandler(page)

        async with get_stealth_session(page) as session:
            await session.navigate("https://example.com/protected")

            # Check for CAPTCHA
            captcha_info = await captcha_handler.detect_captcha()

            if captcha_info["has_captcha"]:
                logger.warning(f"CAPTCHA detected: {captcha_info['type']}")

                # Try free bypass first (human-like behavior + manual solve)
                bypasser = ScrappyCaptchaBypasser(page)
                success = await bypasser.bypass(
                    manual_fallback=True,
                    manual_timeout=60
                )

                if success:
                    logger.success("CAPTCHA bypassed!")
                else:
                    logger.error("CAPTCHA bypass failed")
            else:
                logger.info("No CAPTCHA detected")

        await context.close()


# =============================================================================
# EXAMPLE 7: Full Production Pattern
# =============================================================================

async def example_production_pattern():
    """
    Production-ready pattern combining all stealth features.
    """
    from .bs_detector import get_integrity_validator

    # Setup
    proxy_manager = ProxyManager()
    proxy_manager.add_proxy(
        server="http://residential-proxy.com:8080",
        username="user",
        password=os.environ.get("PROXY_PASSWORD", "TEST_password_placeholder"),  # Configure via environment
        proxy_type="residential"
    )

    validator = get_integrity_validator()

    async with async_playwright() as p:
        # Get proxy
        proxy = proxy_manager.get_proxy(domain="target.com", sticky=True)

        # Create stealth context
        context, fp_manager = await create_stealth_context(
            p,
            headless=False,
            proxy=proxy,
            fingerprint_seed="production-session-1"
        )

        page = await context.new_page()

        try:
            # Use stealth session
            async with get_stealth_session(page, proxy_manager=proxy_manager) as session:
                # Navigate
                await session.navigate("https://target.com/data")

                # Wait for page load
                await session.wait_and_read(2000)

                # Scroll to load content
                await session.scroll("down")
                await asyncio.sleep(2)

                # Extract data
                data = await page.evaluate("""() => {
                    return {
                        title: document.title,
                        emails: Array.from(document.querySelectorAll('a[href^="mailto:"]'))
                            .map(a => a.href.replace('mailto:', '')),
                    };
                }""")

                # Validate extracted data (no hallucinations)
                page_content = await page.content()
                is_valid, issues, hint = validator.verify_output(
                    claimed_output=str(data),
                    actual_page_content=page_content,
                    task_type="extraction"
                )

                if is_valid:
                    logger.success(f"Valid data extracted: {data}")
                    proxy_manager.record_success(proxy)
                else:
                    logger.warning(f"Data validation failed: {issues}")
                    logger.info(f"Hint: {hint}")

        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            proxy_manager.record_failure(proxy)

        finally:
            await context.close()


# =============================================================================
# EXAMPLE 8: Behavioral Testing
# =============================================================================

async def example_behavioral_testing():
    """
    Test behavioral mimicry components individually.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        await page.goto("https://example.com")

        # Test natural mouse movement
        logger.info("Testing mouse movement...")
        await BehaviorMimicry.move_mouse_naturally(page, 500, 300)
        await asyncio.sleep(1)

        # Test natural typing
        logger.info("Testing natural typing...")
        await page.goto("https://www.google.com")
        await BehaviorMimicry.type_naturally(
            page,
            'textarea[name="q"]',
            "test query with typos",
            typo_probability=0.1  # 10% chance for demo
        )
        await asyncio.sleep(2)

        # Test natural scrolling
        logger.info("Testing natural scrolling...")
        await BehaviorMimicry.scroll_naturally(page, "down", 500)
        await asyncio.sleep(1)

        # Test micro-movements
        logger.info("Testing micro-movements...")
        await BehaviorMimicry.random_micro_movements(page, count=5)

        # Test reading pause
        logger.info("Testing reading pause...")
        await BehaviorMimicry.reading_pause(content_length=2000)

        await browser.close()


# =============================================================================
# EXAMPLE 9: Integration with Existing Stealth Utils
# =============================================================================

async def example_combine_with_existing_stealth():
    """
    Combine enhanced stealth with existing stealth_utils.py.
    """
    from .stealth_utils import (
        get_stealth_args,
        get_random_user_agent,
        StealthSession as OldStealthSession
    )

    async with async_playwright() as p:
        # Use existing stealth args
        launch_args = get_stealth_args()
        user_agent = get_random_user_agent()

        # Create fingerprint
        fp_manager = FingerprintManager()

        # Combine options
        browser = await p.chromium.launch(headless=False, args=launch_args)

        context_options = fp_manager.get_context_options()
        context_options["user_agent"] = user_agent

        context = await browser.new_context(**context_options)
        await context.add_init_script(fp_manager.get_injection_script())

        page = await context.new_page()

        # Use enhanced stealth session
        async with get_stealth_session(page) as session:
            await session.navigate("https://example.com")
            # Now has BOTH old stealth utils AND new fingerprinting

        await browser.close()


# =============================================================================
# MAIN - Run All Examples
# =============================================================================

async def main():
    """Run example demonstrations."""
    logger.info("=== Stealth Enhanced Integration Examples ===\n")

    # Uncomment to run specific examples:

    # logger.info("Example 1: Basic Stealth")
    # await example_basic_stealth()

    # logger.info("\nExample 2: PlaywrightClient Integration")
    # await example_integrate_with_playwright_client()

    # logger.info("\nExample 3: Proxy Rotation")
    # await example_proxy_rotation()

    # logger.info("\nExample 4: Site Profiles")
    # await example_site_profiles()

    # logger.info("\nExample 5: Custom Fingerprint")
    # await example_custom_fingerprint()

    # logger.info("\nExample 6: CAPTCHA Handling")
    # await example_captcha_handling()

    # logger.info("\nExample 7: Production Pattern")
    # await example_production_pattern()

    logger.info("\nExample 8: Behavioral Testing")
    await example_behavioral_testing()

    # logger.info("\nExample 9: Combine with Existing")
    # await example_combine_with_existing_stealth()


if __name__ == "__main__":
    asyncio.run(main())
