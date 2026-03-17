#!/usr/bin/env python3
"""
Test suite for Advanced Pre-Action Validation

Tests all validation features:
- Visibility detection
- Viewport detection
- Obstruction detection
- Auto-dismissal
- Scroll behavior
- Interactability checks

Usage:
    python -m agent.test_action_validation
    python -m agent.test_action_validation --visual  # Run with visible browser
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from agent.action_engine import ActionEngine


class ValidationTestSuite:
    """Test suite for action validation features."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.engine = None
        self.passed = 0
        self.failed = 0

    async def setup(self):
        """Initialize the engine."""
        logger.info("Setting up test environment...")
        self.engine = ActionEngine(headless=self.headless)
        await self.engine.connect()
        logger.info("Engine connected")

    async def teardown(self):
        """Clean up."""
        if self.engine:
            await self.engine.disconnect()
        logger.info(f"\nTest Results: {self.passed} passed, {self.failed} failed")

    def assert_true(self, condition: bool, test_name: str, message: str = ""):
        """Assert that condition is true."""
        if condition:
            logger.success(f"✓ {test_name}")
            self.passed += 1
        else:
            logger.error(f"✗ {test_name}: {message}")
            self.failed += 1

    def assert_false(self, condition: bool, test_name: str, message: str = ""):
        """Assert that condition is false."""
        self.assert_true(not condition, test_name, message)

    # ==============================================================================
    # TEST CASES
    # ==============================================================================

    async def test_element_not_found(self):
        """Test detection of non-existent element."""
        page = self.engine.browser.page
        await page.goto("https://example.com")

        is_ready, reason, fix = await ActionEngine.validate_element_interactable(
            page,
            "#non-existent-element"
        )

        self.assert_false(is_ready, "test_element_not_found")
        self.assert_true(
            "not found" in reason.lower(),
            "test_element_not_found_reason",
            f"Expected 'not found' in reason, got: {reason}"
        )

    async def test_hidden_element_display_none(self):
        """Test detection of display: none element."""
        page = self.engine.browser.page

        # Create test page with hidden element
        await page.goto("about:blank")
        await page.set_content("""
            <html>
                <body>
                    <button id="hidden-btn" style="display: none;">Hidden</button>
                </body>
            </html>
        """)

        is_ready, reason, fix = await ActionEngine.validate_element_interactable(
            page,
            "#hidden-btn"
        )

        self.assert_false(is_ready, "test_hidden_element_display_none")
        self.assert_true(
            "display: none" in reason,
            "test_hidden_element_display_none_reason",
            f"Expected 'display: none' in reason, got: {reason}"
        )
        self.assert_true(
            fix.get("suggested_action") == "wait_for_visible",
            "test_hidden_element_suggestion"
        )

    async def test_hidden_element_visibility_hidden(self):
        """Test detection of visibility: hidden element."""
        page = self.engine.browser.page

        await page.goto("about:blank")
        await page.set_content("""
            <html>
                <body>
                    <button id="hidden-btn" style="visibility: hidden;">Hidden</button>
                </body>
            </html>
        """)

        is_ready, reason, fix = await ActionEngine.validate_element_interactable(
            page,
            "#hidden-btn"
        )

        self.assert_false(is_ready, "test_hidden_element_visibility_hidden")
        self.assert_true(
            "visibility: hidden" in reason,
            "test_hidden_element_visibility_hidden_reason"
        )

    async def test_hidden_element_opacity_zero(self):
        """Test detection of opacity: 0 element."""
        page = self.engine.browser.page

        await page.goto("about:blank")
        await page.set_content("""
            <html>
                <body>
                    <button id="hidden-btn" style="opacity: 0;">Hidden</button>
                </body>
            </html>
        """)

        is_ready, reason, fix = await ActionEngine.validate_element_interactable(
            page,
            "#hidden-btn"
        )

        self.assert_false(is_ready, "test_hidden_element_opacity_zero")
        self.assert_true(
            "opacity: 0" in reason,
            "test_hidden_element_opacity_zero_reason"
        )

    async def test_element_outside_viewport(self):
        """Test detection of element outside viewport."""
        page = self.engine.browser.page

        await page.goto("about:blank")
        await page.set_content("""
            <html>
                <body>
                    <div style="height: 3000px;"></div>
                    <button id="far-btn">Far Away</button>
                </body>
            </html>
        """)

        is_ready, reason, fix = await ActionEngine.validate_element_interactable(
            page,
            "#far-btn"
        )

        self.assert_false(is_ready, "test_element_outside_viewport")
        self.assert_true(
            "outside viewport" in reason.lower(),
            "test_element_outside_viewport_reason"
        )
        self.assert_true(
            fix.get("scroll_needed"),
            "test_element_outside_viewport_scroll_needed"
        )

    async def test_scroll_into_view(self):
        """Test scrolling element into view."""
        page = self.engine.browser.page

        await page.goto("about:blank")
        await page.set_content("""
            <html>
                <body>
                    <div style="height: 3000px;"></div>
                    <button id="far-btn">Far Away</button>
                </body>
            </html>
        """)

        # Initially outside viewport
        is_ready, _, _ = await ActionEngine.validate_element_interactable(page, "#far-btn")
        self.assert_false(is_ready, "test_scroll_into_view_initial")

        # Scroll into view
        scroll_success = await ActionEngine.scroll_element_into_view(page, "#far-btn")
        self.assert_true(scroll_success, "test_scroll_into_view_success")

        # Now should be in viewport
        is_ready, _, _ = await ActionEngine.validate_element_interactable(page, "#far-btn")
        self.assert_true(is_ready, "test_scroll_into_view_final")

    async def test_obstruction_cookie_banner(self):
        """Test detection of cookie banner obstruction."""
        page = self.engine.browser.page

        await page.goto("about:blank")
        await page.set_content("""
            <html>
                <body>
                    <button id="action-btn" style="position: absolute; top: 100px; left: 100px;">
                        Click Me
                    </button>
                    <div id="cookie-banner" style="
                        position: fixed;
                        top: 0;
                        left: 0;
                        width: 100%;
                        height: 100%;
                        background: rgba(0,0,0,0.5);
                        z-index: 9999;
                    ">
                        <div class="cookie-consent">
                            <button id="accept-cookies">Accept Cookies</button>
                        </div>
                    </div>
                </body>
            </html>
        """)

        is_ready, reason, fix = await ActionEngine.validate_element_interactable(
            page,
            "#action-btn"
        )

        self.assert_false(is_ready, "test_obstruction_cookie_banner")
        self.assert_true(
            fix.get("obstruction_type") == "cookie_banner",
            "test_obstruction_cookie_banner_type",
            f"Expected cookie_banner, got: {fix.get('obstruction_type')}"
        )
        self.assert_true(
            fix.get("suggested_action") == "dismiss_obstruction",
            "test_obstruction_cookie_banner_suggestion"
        )

    async def test_dismiss_cookie_banner(self):
        """Test automatic dismissal of cookie banner."""
        page = self.engine.browser.page

        await page.goto("about:blank")
        await page.set_content("""
            <html>
                <body>
                    <button id="action-btn">Click Me</button>
                    <div id="cookie-banner" style="
                        position: fixed;
                        top: 0;
                        left: 0;
                        width: 100%;
                        height: 100%;
                        z-index: 9999;
                    ">
                        <button id="accept-cookies">Accept Cookies</button>
                    </div>
                    <script>
                        document.getElementById('accept-cookies').onclick = function() {
                            document.getElementById('cookie-banner').style.display = 'none';
                        };
                    </script>
                </body>
            </html>
        """)

        # Initially obstructed
        is_ready, _, _ = await ActionEngine.validate_element_interactable(page, "#action-btn")
        self.assert_false(is_ready, "test_dismiss_cookie_banner_initial")

        # Dismiss obstruction
        dismiss_success = await ActionEngine.dismiss_obstructions(page)
        self.assert_true(dismiss_success, "test_dismiss_cookie_banner_success")

        # Should now be accessible
        await asyncio.sleep(0.5)  # Wait for DOM update
        is_ready, _, _ = await ActionEngine.validate_element_interactable(page, "#action-btn")
        self.assert_true(is_ready, "test_dismiss_cookie_banner_final")

    async def test_disabled_element(self):
        """Test detection of disabled element."""
        page = self.engine.browser.page

        await page.goto("about:blank")
        await page.set_content("""
            <html>
                <body>
                    <button id="disabled-btn" disabled>Disabled</button>
                </body>
            </html>
        """)

        is_ready, reason, fix = await ActionEngine.validate_element_interactable(
            page,
            "#disabled-btn"
        )

        self.assert_false(is_ready, "test_disabled_element")
        self.assert_true(
            "disabled" in reason.lower(),
            "test_disabled_element_reason"
        )
        self.assert_true(
            "disabled" in fix.get("interactability_issues", []),
            "test_disabled_element_issues"
        )

    async def test_readonly_element(self):
        """Test detection of readonly element."""
        page = self.engine.browser.page

        await page.goto("about:blank")
        await page.set_content("""
            <html>
                <body>
                    <input id="readonly-input" value="Read Only" readonly>
                </body>
            </html>
        """)

        is_ready, reason, fix = await ActionEngine.validate_element_interactable(
            page,
            "#readonly-input"
        )

        self.assert_false(is_ready, "test_readonly_element")
        self.assert_true(
            "readonly" in fix.get("interactability_issues", []),
            "test_readonly_element_issues"
        )

    async def test_pointer_events_none(self):
        """Test detection of pointer-events: none element."""
        page = self.engine.browser.page

        await page.goto("about:blank")
        await page.set_content("""
            <html>
                <body>
                    <button id="no-pointer" style="pointer-events: none;">
                        No Pointer Events
                    </button>
                </body>
            </html>
        """)

        is_ready, reason, fix = await ActionEngine.validate_element_interactable(
            page,
            "#no-pointer"
        )

        self.assert_false(is_ready, "test_pointer_events_none")
        self.assert_true(
            "pointer-events: none" in fix.get("interactability_issues", []),
            "test_pointer_events_none_issues"
        )

    async def test_valid_element(self):
        """Test that valid element passes all checks."""
        page = self.engine.browser.page

        await page.goto("about:blank")
        await page.set_content("""
            <html>
                <body>
                    <button id="valid-btn">Valid Button</button>
                </body>
            </html>
        """)

        is_ready, reason, fix = await ActionEngine.validate_element_interactable(
            page,
            "#valid-btn"
        )

        self.assert_true(is_ready, "test_valid_element", f"Reason: {reason}")
        self.assert_true(
            fix is None,
            "test_valid_element_no_fix",
            "Valid element should have no fix suggestions"
        )

    async def test_validate_and_prepare_auto_scroll(self):
        """Test high-level validate_and_prepare_action with auto-scroll."""
        page = self.engine.browser.page

        await page.goto("about:blank")
        await page.set_content("""
            <html>
                <body>
                    <div style="height: 3000px;"></div>
                    <button id="far-btn">Far Away</button>
                </body>
            </html>
        """)

        # Should auto-scroll and prepare element
        ready, error = await self.engine.validate_and_prepare_action("#far-btn", "click")

        self.assert_true(ready, "test_validate_and_prepare_auto_scroll", f"Error: {error}")

    async def test_validate_and_prepare_auto_dismiss(self):
        """Test high-level validate_and_prepare_action with auto-dismiss."""
        page = self.engine.browser.page

        await page.goto("about:blank")
        await page.set_content("""
            <html>
                <body>
                    <button id="action-btn">Click Me</button>
                    <div class="cookie-banner" style="
                        position: fixed;
                        top: 0;
                        left: 0;
                        width: 100%;
                        height: 100%;
                        z-index: 9999;
                    ">
                        <button id="accept-cookies">Accept Cookies</button>
                    </div>
                    <script>
                        document.getElementById('accept-cookies').onclick = function() {
                            document.querySelector('.cookie-banner').remove();
                        };
                    </script>
                </body>
            </html>
        """)

        # Should auto-dismiss and prepare element
        ready, error = await self.engine.validate_and_prepare_action("#action-btn", "click")

        self.assert_true(ready, "test_validate_and_prepare_auto_dismiss", f"Error: {error}")

    async def test_real_website_example(self):
        """Test validation on a real website (example.com)."""
        page = self.engine.browser.page

        await page.goto("https://example.com")

        # Example.com has a simple page with a link
        # Try to validate the "More information..." link
        selectors = ["a", "a[href]", "body a"]

        for selector in selectors:
            try:
                is_ready, reason, fix = await ActionEngine.validate_element_interactable(
                    page,
                    selector
                )
                if is_ready:
                    logger.success(f"Found valid element with selector: {selector}")
                    self.assert_true(True, "test_real_website_example")
                    return
            except Exception as e:
                logger.debug(f"Selector {selector} failed: {e}")

        # If we get here, no valid element found
        self.assert_true(False, "test_real_website_example", "No valid element found on example.com")

    # ==============================================================================
    # RUN ALL TESTS
    # ==============================================================================

    async def run_all(self):
        """Run all test cases."""
        logger.info("Starting Action Validation Test Suite\n")

        await self.setup()

        try:
            # Basic visibility tests
            logger.info("\n=== Visibility Tests ===")
            await self.test_element_not_found()
            await self.test_hidden_element_display_none()
            await self.test_hidden_element_visibility_hidden()
            await self.test_hidden_element_opacity_zero()

            # Viewport tests
            logger.info("\n=== Viewport Tests ===")
            await self.test_element_outside_viewport()
            await self.test_scroll_into_view()

            # Obstruction tests
            logger.info("\n=== Obstruction Tests ===")
            await self.test_obstruction_cookie_banner()
            await self.test_dismiss_cookie_banner()

            # Interactability tests
            logger.info("\n=== Interactability Tests ===")
            await self.test_disabled_element()
            await self.test_readonly_element()
            await self.test_pointer_events_none()

            # Positive tests
            logger.info("\n=== Positive Tests ===")
            await self.test_valid_element()

            # High-level tests
            logger.info("\n=== High-Level API Tests ===")
            await self.test_validate_and_prepare_auto_scroll()
            await self.test_validate_and_prepare_auto_dismiss()

            # Real website test
            logger.info("\n=== Real Website Test ===")
            await self.test_real_website_example()

        finally:
            await self.teardown()


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Test Action Validation")
    parser.add_argument(
        "--visual",
        action="store_true",
        help="Run with visible browser (default: headless)"
    )
    args = parser.parse_args()

    suite = ValidationTestSuite(headless=not args.visual)
    await suite.run_all()


if __name__ == "__main__":
    asyncio.run(main())
