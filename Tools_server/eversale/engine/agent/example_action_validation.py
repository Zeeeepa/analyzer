#!/usr/bin/env python3
"""
Example: Advanced Pre-Action Validation

Demonstrates the new validation features that ensure clicks/types ALWAYS succeed.

Usage:
    python -m agent.example_action_validation
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from agent.action_engine import ActionEngine


async def example_1_basic_validation():
    """Example 1: Basic validation check before clicking."""
    logger.info("\n" + "="*60)
    logger.info("EXAMPLE 1: Basic Validation")
    logger.info("="*60)

    engine = ActionEngine(headless=False)
    await engine.connect()

    try:
        page = engine.browser.page

        # Navigate to a test page
        await page.goto("about:blank")
        await page.set_content("""
            <html>
                <body>
                    <h1>Test Page</h1>
                    <button id="visible-btn">I'm Visible</button>
                    <button id="hidden-btn" style="display: none;">I'm Hidden</button>
                </body>
            </html>
        """)

        # Test 1: Visible button
        logger.info("\n[1] Checking visible button...")
        is_ready, reason, fix = await ActionEngine.validate_element_interactable(
            page,
            "#visible-btn"
        )

        if is_ready:
            logger.success(f"✓ Button is ready to click: {reason}")
        else:
            logger.error(f"✗ Button not ready: {reason}")

        # Test 2: Hidden button
        logger.info("\n[2] Checking hidden button...")
        is_ready, reason, fix = await ActionEngine.validate_element_interactable(
            page,
            "#hidden-btn"
        )

        if is_ready:
            logger.success(f"✓ Button is ready to click: {reason}")
        else:
            logger.warning(f"✗ Button not ready: {reason}")
            if fix:
                logger.info(f"   Suggested action: {fix.get('suggested_action')}")

    finally:
        await engine.disconnect()


async def example_2_auto_scroll():
    """Example 2: Auto-scroll element into view."""
    logger.info("\n" + "="*60)
    logger.info("EXAMPLE 2: Auto-Scroll")
    logger.info("="*60)

    engine = ActionEngine(headless=False)
    await engine.connect()

    try:
        page = engine.browser.page

        await page.goto("about:blank")
        await page.set_content("""
            <html>
                <body>
                    <h1>Scroll Test</h1>
                    <div style="height: 2000px; background: linear-gradient(white, blue);">
                        Spacer
                    </div>
                    <button id="far-away-btn">I'm Far Away!</button>
                </body>
            </html>
        """)

        logger.info("\n[1] Validating element far down the page...")
        is_ready, reason, fix = await ActionEngine.validate_element_interactable(
            page,
            "#far-away-btn"
        )

        if not is_ready:
            logger.warning(f"Element not ready: {reason}")

            if fix.get("scroll_needed"):
                logger.info("[2] Auto-scrolling element into view...")
                scroll_success = await ActionEngine.scroll_element_into_view(
                    page,
                    "#far-away-btn"
                )

                if scroll_success:
                    logger.success("✓ Scrolled successfully!")

                    # Re-validate
                    logger.info("[3] Re-validating after scroll...")
                    is_ready, reason, _ = await ActionEngine.validate_element_interactable(
                        page,
                        "#far-away-btn"
                    )

                    if is_ready:
                        logger.success(f"✓ Element is now ready: {reason}")
                    else:
                        logger.error(f"✗ Still not ready: {reason}")

    finally:
        await engine.disconnect()


async def example_3_dismiss_obstruction():
    """Example 3: Auto-dismiss cookie banner."""
    logger.info("\n" + "="*60)
    logger.info("EXAMPLE 3: Dismiss Obstruction")
    logger.info("="*60)

    engine = ActionEngine(headless=False)
    await engine.connect()

    try:
        page = engine.browser.page

        await page.goto("about:blank")
        await page.set_content("""
            <html>
                <head>
                    <style>
                        #cookie-banner {
                            position: fixed;
                            bottom: 0;
                            left: 0;
                            right: 0;
                            background: #333;
                            color: white;
                            padding: 20px;
                            z-index: 9999;
                        }
                        #accept-btn {
                            background: green;
                            color: white;
                            padding: 10px 20px;
                            border: none;
                            cursor: pointer;
                        }
                    </style>
                </head>
                <body>
                    <h1>Page with Cookie Banner</h1>
                    <button id="action-btn">Click Me</button>

                    <div id="cookie-banner">
                        <p>We use cookies. Accept them?</p>
                        <button id="accept-btn" class="accept-cookies">Accept Cookies</button>
                    </div>

                    <script>
                        document.getElementById('accept-btn').onclick = function() {
                            document.getElementById('cookie-banner').style.display = 'none';
                        };
                    </script>
                </body>
            </html>
        """)

        logger.info("\n[1] Validating button with cookie banner present...")
        is_ready, reason, fix = await ActionEngine.validate_element_interactable(
            page,
            "#action-btn"
        )

        if not is_ready:
            obstruction_type = fix.get("obstruction_type", "unknown")
            logger.warning(f"Element obstructed by: {obstruction_type}")

            if fix.get("suggested_action") == "dismiss_obstruction":
                logger.info("[2] Attempting to dismiss obstruction...")
                dismiss_success = await ActionEngine.dismiss_obstructions(page)

                if dismiss_success:
                    logger.success("✓ Obstruction dismissed!")

                    # Wait a moment for DOM to update
                    await asyncio.sleep(0.5)

                    # Re-validate
                    logger.info("[3] Re-validating after dismissal...")
                    is_ready, reason, _ = await ActionEngine.validate_element_interactable(
                        page,
                        "#action-btn"
                    )

                    if is_ready:
                        logger.success(f"✓ Element is now ready: {reason}")
                    else:
                        logger.error(f"✗ Still not ready: {reason}")
        else:
            logger.success(f"✓ Element is ready: {reason}")

    finally:
        await engine.disconnect()


async def example_4_high_level_api():
    """Example 4: Use high-level validate_and_prepare_action."""
    logger.info("\n" + "="*60)
    logger.info("EXAMPLE 4: High-Level API (Auto-Fix Everything)")
    logger.info("="*60)

    engine = ActionEngine(headless=False)
    await engine.connect()

    try:
        page = engine.browser.page

        await page.goto("about:blank")
        await page.set_content("""
            <html>
                <body>
                    <h1>High-Level API Test</h1>

                    <!-- Button far down the page -->
                    <div style="height: 2000px;"></div>
                    <button id="scroll-test">Needs Scroll</button>

                    <!-- Cookie banner blocking everything -->
                    <div id="cookie-banner" style="
                        position: fixed;
                        top: 0;
                        left: 0;
                        width: 100%;
                        height: 100%;
                        background: rgba(0,0,0,0.8);
                        z-index: 9999;
                        color: white;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                    ">
                        <div>
                            <h2>Cookie Consent</h2>
                            <button id="accept-cookies" class="accept">
                                Accept Cookies
                            </button>
                        </div>
                    </div>

                    <script>
                        document.getElementById('accept-cookies').onclick = function() {
                            document.getElementById('cookie-banner').remove();
                        };
                    </script>
                </body>
            </html>
        """)

        # This single call will:
        # 1. Detect the cookie banner obstruction
        # 2. Dismiss it automatically
        # 3. Detect that element is outside viewport
        # 4. Scroll it into view
        # 5. Hover before action (human-like)
        # 6. Return ready=True if all succeeded

        logger.info("\n[1] Using validate_and_prepare_action (auto-fixes everything)...")
        ready, error = await engine.validate_and_prepare_action(
            "#scroll-test",
            action_type="click"
        )

        if ready:
            logger.success("✓ Element is ready! All issues auto-fixed.")
            logger.info("    - Cookie banner was dismissed")
            logger.info("    - Element was scrolled into view")
            logger.info("    - Hover was applied (human-like)")
            logger.info("\n[2] Now we can safely click...")
            await page.click("#scroll-test")
            logger.success("✓ Click succeeded!")
        else:
            logger.error(f"✗ Could not prepare element: {error}")

    finally:
        await engine.disconnect()


async def example_5_real_world_scenario():
    """Example 5: Real-world scenario with multiple elements."""
    logger.info("\n" + "="*60)
    logger.info("EXAMPLE 5: Real-World Form Submission")
    logger.info("="*60)

    engine = ActionEngine(headless=False)
    await engine.connect()

    try:
        page = engine.browser.page

        # Simulate a real form with various validation challenges
        await page.goto("about:blank")
        await page.set_content("""
            <html>
                <head>
                    <style>
                        body { font-family: Arial; padding: 20px; }
                        .form-group { margin: 20px 0; }
                        input { padding: 10px; width: 300px; }
                        button { padding: 10px 20px; background: blue; color: white; border: none; }
                        button:disabled { background: gray; }
                        #loading { display: none; }
                    </style>
                </head>
                <body>
                    <h1>Registration Form</h1>

                    <div class="form-group">
                        <input id="name" placeholder="Your name">
                    </div>

                    <div class="form-group">
                        <input id="email" placeholder="Your email">
                    </div>

                    <div class="form-group">
                        <button id="submit-btn" disabled>Submit (disabled until form filled)</button>
                    </div>

                    <div id="loading">Processing...</div>

                    <script>
                        // Enable submit button when both fields filled
                        const nameInput = document.getElementById('name');
                        const emailInput = document.getElementById('email');
                        const submitBtn = document.getElementById('submit-btn');

                        function checkForm() {
                            if (nameInput.value && emailInput.value) {
                                submitBtn.disabled = false;
                            }
                        }

                        nameInput.addEventListener('input', checkForm);
                        emailInput.addEventListener('input', checkForm);

                        submitBtn.onclick = function() {
                            document.getElementById('loading').style.display = 'block';
                            submitBtn.disabled = true;
                        };
                    </script>
                </body>
            </html>
        """)

        # Step 1: Validate submit button (should be disabled)
        logger.info("\n[1] Checking submit button (should be disabled)...")
        ready, error = await engine.validate_and_prepare_action(
            "#submit-btn",
            action_type="click"
        )

        if not ready:
            logger.warning(f"✓ Correctly detected: {error}")
        else:
            logger.error("✗ Should have detected disabled state")

        # Step 2: Fill form fields
        logger.info("\n[2] Filling form fields...")
        await page.fill("#name", "John Doe")
        await page.fill("#email", "john@example.com")

        # Wait for JavaScript to enable button
        await asyncio.sleep(0.5)

        # Step 3: Re-validate submit button (should now be enabled)
        logger.info("\n[3] Re-checking submit button (should now be enabled)...")
        ready, error = await engine.validate_and_prepare_action(
            "#submit-btn",
            action_type="click"
        )

        if ready:
            logger.success("✓ Submit button is now ready!")
            logger.info("\n[4] Clicking submit...")
            await page.click("#submit-btn")
            logger.success("✓ Form submitted!")
        else:
            logger.error(f"✗ Submit button still not ready: {error}")

    finally:
        await engine.disconnect()


async def main():
    """Run all examples."""
    logger.info("\n" + "="*70)
    logger.info("ACTION VALIDATION EXAMPLES")
    logger.info("Demonstrating advanced pre-action validation features")
    logger.info("="*70)

    # Run examples
    await example_1_basic_validation()
    await asyncio.sleep(1)

    await example_2_auto_scroll()
    await asyncio.sleep(1)

    await example_3_dismiss_obstruction()
    await asyncio.sleep(1)

    await example_4_high_level_api()
    await asyncio.sleep(1)

    await example_5_real_world_scenario()

    logger.info("\n" + "="*70)
    logger.info("ALL EXAMPLES COMPLETED")
    logger.info("="*70)


if __name__ == "__main__":
    asyncio.run(main())
