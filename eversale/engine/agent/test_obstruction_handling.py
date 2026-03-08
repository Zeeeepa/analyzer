"""
Test script for obstruction detection and handling in BrowserManager.

This demonstrates the new obstruction handling features:
- Detecting cookie banners, modals, chat widgets, etc.
- Automatically dismissing obstructions
- Ensuring elements are clickable before interaction
- Z-index analysis for overlay detection
"""

import asyncio
from pathlib import Path
import sys

# Add agent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from loguru import logger


async def test_obstruction_detection():
    """Test obstruction detection on real websites with common obstructions."""

    # Import here to avoid issues if playwright not installed
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("Playwright not installed. Run: pip install playwright && playwright install")
        return

    from browser_manager import BrowserManager, OBSTRUCTION_PATTERNS

    # Mock MCP client for testing
    class MockMCP:
        def __init__(self):
            self._mcp_server = None
            self.page = None

        class MockServer:
            def __init__(self, page):
                self.client = self
                self.page = page

    logger.info("Starting obstruction detection test")

    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720}
        )
        page = await context.new_page()

        # Create mock MCP with page
        mock_mcp = MockMCP()
        mock_server = MockMCP.MockServer(page)
        mock_mcp._mcp_server = mock_server

        # Create BrowserManager
        browser_mgr = BrowserManager(
            mcp_client=mock_mcp,
            ollama_client=None,
            vision_model=None
        )

        # Test sites with different obstruction types
        test_sites = [
            {
                'url': 'https://www.cookiebot.com/en/what-is-behind-website-cookie-consent-notices/',
                'name': 'Cookiebot (Cookie Banner)',
                'expected': ['cookie_banner']
            },
            {
                'url': 'https://www.cnn.com',
                'name': 'CNN (Newsletter Popup)',
                'expected': ['newsletter_popup', 'modal']
            },
            {
                'url': 'https://www.zendesk.com',
                'name': 'Zendesk (Chat Widget)',
                'expected': ['chat_widget']
            },
        ]

        for site in test_sites:
            logger.info(f"\n{'='*60}")
            logger.info(f"Testing: {site['name']}")
            logger.info(f"URL: {site['url']}")
            logger.info(f"{'='*60}\n")

            try:
                # Navigate to site
                await page.goto(site['url'], wait_until='domcontentloaded', timeout=15000)
                await asyncio.sleep(2)  # Wait for dynamic content

                # Detect obstructions
                logger.info("Detecting obstructions...")
                obstructions = await browser_mgr.detect_obstructions()

                if obstructions:
                    logger.info(f"Found {len(obstructions)} obstruction(s):")
                    for obs in obstructions:
                        logger.info(f"  - {obs.type}: z-index={obs.z_index}, "
                                  f"coverage={obs.covers_percent:.1f}%, "
                                  f"dismissible={obs.dismissible}, "
                                  f"method={obs.dismiss_method}")
                else:
                    logger.warning("No obstructions detected")

                # Try to dismiss obstructions
                logger.info("\nAttempting to dismiss obstructions...")
                dismissed = await browser_mgr.scan_and_dismiss_obstructions(aggressive=True)
                logger.info(f"Dismissed {dismissed} obstruction(s)")

                # Get high z-index elements
                logger.info("\nAnalyzing high z-index elements...")
                high_z_elements = await browser_mgr.get_elements_by_z_index(min_z_index=100)
                if high_z_elements:
                    logger.info(f"Found {len(high_z_elements)} elements with z-index >= 100:")
                    for elem in high_z_elements[:5]:  # Show top 5
                        logger.info(f"  - {elem['selector']}: z={elem['z_index']}, "
                                  f"coverage={elem['coverage']:.1f}%, "
                                  f"visible={elem['visible']}")

                # Show stats
                logger.info(f"\nStats: {browser_mgr.stats}")

                await asyncio.sleep(3)

            except Exception as e:
                logger.error(f"Error testing {site['name']}: {e}")

        logger.info("\n" + "="*60)
        logger.info("Test complete!")
        logger.info(f"Final stats: {browser_mgr.stats}")
        logger.info("="*60)

        await browser.close()


async def test_ensure_element_clickable():
    """Test ensuring an element is clickable by dismissing obstructions."""

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("Playwright not installed")
        return

    from browser_manager import BrowserManager

    logger.info("Testing ensure_element_clickable")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={'width': 1280, 'height': 720})
        page = await context.new_page()

        # Create test HTML with modal blocking a button
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                #modal {
                    position: fixed;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 100%;
                    background: rgba(0,0,0,0.5);
                    z-index: 9999;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }
                #modal-content {
                    background: white;
                    padding: 20px;
                    border-radius: 8px;
                }
                #target-button {
                    position: absolute;
                    top: 50%;
                    left: 50%;
                    transform: translate(-50%, -50%);
                }
            </style>
        </head>
        <body>
            <button id="target-button">Click Me (Behind Modal)</button>

            <div id="modal" role="dialog" aria-modal="true">
                <div id="modal-content">
                    <h2>Modal Overlay</h2>
                    <p>This modal is blocking the button</p>
                    <button class="close">Close</button>
                </div>
            </div>
        </body>
        </html>
        """

        await page.set_content(html)

        # Create BrowserManager
        class MockMCP:
            def __init__(self):
                self._mcp_server = None

            class MockServer:
                def __init__(self, page):
                    self.client = self
                    self.page = page

        mock_mcp = MockMCP()
        mock_server = MockMCP.MockServer(page)
        mock_mcp._mcp_server = mock_server

        browser_mgr = BrowserManager(mcp_client=mock_mcp)

        # Test ensure_element_clickable
        logger.info("Checking if target button is clickable...")
        is_clickable = await browser_mgr.ensure_element_clickable('#target-button')

        if is_clickable:
            logger.info("Button is now clickable! Modal was dismissed.")
        else:
            logger.warning("Button is still obstructed")

        await asyncio.sleep(3)
        await browser.close()


async def test_auto_dismiss_on_navigation():
    """Test automatic dismissal of obstructions after navigation."""

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("Playwright not installed")
        return

    from browser_manager import BrowserManager

    logger.info("Testing auto_dismiss_on_navigation")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={'width': 1280, 'height': 720})
        page = await context.new_page()

        # Create BrowserManager
        class MockMCP:
            def __init__(self):
                self._mcp_server = None

            class MockServer:
                def __init__(self, page):
                    self.client = self
                    self.page = page

        mock_mcp = MockMCP()
        mock_server = MockMCP.MockServer(page)
        mock_mcp._mcp_server = mock_server

        browser_mgr = BrowserManager(mcp_client=mock_mcp)

        # Navigate to a site with cookie banner
        url = 'https://www.cookiebot.com/en/'
        logger.info(f"Navigating to {url}")
        await page.goto(url, wait_until='domcontentloaded', timeout=15000)

        # Auto-dismiss obstructions
        dismissed = await browser_mgr.auto_dismiss_on_navigation(url)
        logger.info(f"Auto-dismissed {dismissed} obstruction(s)")

        await asyncio.sleep(5)
        await browser.close()


if __name__ == '__main__':
    logger.info("Obstruction Handling Test Suite")
    logger.info("="*60)

    # Run tests
    asyncio.run(test_obstruction_detection())

    # Uncomment to run other tests
    # asyncio.run(test_ensure_element_clickable())
    # asyncio.run(test_auto_dismiss_on_navigation())
