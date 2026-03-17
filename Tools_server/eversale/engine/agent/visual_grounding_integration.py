"""
Visual Grounding Integration Example for Eversale

Shows how to integrate visual_grounding.py with existing Eversale modules:
- playwright_direct.py for browser automation
- dom_distillation.py for DOM understanding
- vision_analyzer.py for vision capabilities
- selector_fallbacks.py for robust element finding

This demonstrates real-world usage patterns.
"""

import asyncio
from pathlib import Path
from typing import Dict, List, Any, Optional
from loguru import logger

from playwright.async_api import async_playwright, Page, Browser

from visual_grounding import (
    VisualGroundingEngine,
    GroundingStrategy,
    ElementType,
    VisualElement,
    ground_and_click,
    ground_and_fill,
    ground_and_extract_text
)


# ==============================================================================
# INTEGRATION PATTERNS
# ==============================================================================

class EnhancedWebAutomation:
    """
    Enhanced web automation using visual grounding.

    Combines traditional selectors with visual grounding for
    maximum reliability across different websites.
    """

    def __init__(self):
        self.grounding_engine = VisualGroundingEngine()
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None

    async def __aenter__(self):
        """Async context manager entry."""
        from playwright.async_api import async_playwright
        self.playwright = await async_playwright().__aenter__()
        self.browser = await self.playwright.chromium.launch(headless=False)
        self.page = await self.browser.new_page()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.__aexit__(exc_type, exc_val, exc_tb)

    async def smart_click(
        self,
        selector: Optional[str] = None,
        description: Optional[str] = None,
        timeout: int = 5000
    ) -> bool:
        """
        Smart click: Try CSS selector first, fallback to visual grounding.

        Args:
            selector: Optional CSS selector
            description: Optional natural language description
            timeout: Timeout in milliseconds

        Returns:
            True if click succeeded
        """
        # Try CSS selector first (fastest)
        if selector:
            try:
                await self.page.click(selector, timeout=timeout)
                logger.info(f"✓ Clicked via selector: {selector}")
                return True
            except Exception as e:
                logger.debug(f"Selector failed: {e}")

        # Fallback to visual grounding
        if description:
            logger.info(f"Falling back to visual grounding: {description}")
            result = await self.grounding_engine.ground_element(
                self.page,
                description,
                strategy=GroundingStrategy.HYBRID
            )

            if result.success:
                success = await self.grounding_engine.click_grounded_element(
                    self.page,
                    result.best_match
                )
                if success:
                    logger.info(f"✓ Clicked via visual grounding")
                    return True

        logger.error("Failed to click element")
        return False

    async def smart_fill(
        self,
        text: str,
        selector: Optional[str] = None,
        description: Optional[str] = None,
        timeout: int = 5000
    ) -> bool:
        """
        Smart fill: Try CSS selector first, fallback to visual grounding.

        Args:
            text: Text to fill
            selector: Optional CSS selector
            description: Optional natural language description
            timeout: Timeout in milliseconds

        Returns:
            True if fill succeeded
        """
        # Try CSS selector first
        if selector:
            try:
                await self.page.fill(selector, text, timeout=timeout)
                logger.info(f"✓ Filled via selector: {selector}")
                return True
            except Exception as e:
                logger.debug(f"Selector failed: {e}")

        # Fallback to visual grounding
        if description:
            logger.info(f"Falling back to visual grounding: {description}")
            result = await self.grounding_engine.ground_element(
                self.page,
                description,
                strategy=GroundingStrategy.HYBRID,
                element_type=ElementType.INPUT
            )

            if result.success:
                success = await self.grounding_engine.fill_grounded_element(
                    self.page,
                    result.best_match,
                    text
                )
                if success:
                    logger.info(f"✓ Filled via visual grounding")
                    return True

        logger.error("Failed to fill element")
        return False

    async def extract_form_fields(self) -> Dict[str, VisualElement]:
        """
        Extract all form fields from the current page using visual grounding.

        Returns:
            Dict mapping field descriptions to VisualElements
        """
        # Common form field descriptions
        field_descriptions = [
            "email input",
            "password input",
            "username input",
            "first name input",
            "last name input",
            "phone input",
            "submit button",
            "login button",
            "sign up button",
        ]

        logger.info(f"Extracting {len(field_descriptions)} potential form fields...")

        results = await self.grounding_engine.ground_multiple_elements(
            self.page,
            field_descriptions
        )

        # Filter to successful matches
        fields = {}
        for desc, result in results.items():
            if result.success and result.best_match.confidence > 0.5:
                fields[desc] = result.best_match

        logger.info(f"Found {len(fields)} form fields")
        return fields

    async def fill_form(self, field_data: Dict[str, str]) -> Dict[str, bool]:
        """
        Intelligently fill a form using natural language field descriptions.

        Args:
            field_data: Dict mapping field descriptions to values
                       e.g., {"email input": "user@example.com", ...}

        Returns:
            Dict mapping field descriptions to success status
        """
        results = {}

        for field_desc, value in field_data.items():
            logger.info(f"Filling '{field_desc}' with '{value}'...")

            result = await self.grounding_engine.ground_element(
                self.page,
                field_desc,
                strategy=GroundingStrategy.HYBRID,
                element_type=ElementType.INPUT
            )

            if result.success:
                success = await self.grounding_engine.fill_grounded_element(
                    self.page,
                    result.best_match,
                    value
                )
                results[field_desc] = success
            else:
                results[field_desc] = False

        return results


# ==============================================================================
# EXAMPLE WORKFLOWS
# ==============================================================================

async def example_login_workflow():
    """
    Example: Login workflow using visual grounding.

    Demonstrates how to handle login forms without knowing the exact selectors.
    """
    logger.info("=" * 70)
    logger.info("EXAMPLE: Login Workflow with Visual Grounding")
    logger.info("=" * 70)

    async with EnhancedWebAutomation() as automation:
        # Navigate to login page
        await automation.page.goto("https://example.com/login")

        # Fill login form using natural language
        form_data = {
            "email input": "user@example.com",
            "password input": "SecurePassword123"
        }

        results = await automation.fill_form(form_data)

        for field, success in results.items():
            if success:
                logger.info(f"✓ {field}: filled")
            else:
                logger.error(f"✗ {field}: failed")

        # Click login button
        await automation.smart_click(description="the login button")

        # Wait for navigation
        await asyncio.sleep(2)

        logger.info("✓ Login workflow complete")


async def example_search_workflow():
    """
    Example: Search workflow demonstrating hybrid approach.
    """
    logger.info("=" * 70)
    logger.info("EXAMPLE: Search Workflow")
    logger.info("=" * 70)

    async with EnhancedWebAutomation() as automation:
        # Navigate to Google
        await automation.page.goto("https://www.google.com")

        # Fill search using hybrid approach (try selector, fallback to vision)
        await automation.smart_fill(
            text="Eversale AI agent",
            selector="input[name='q']",  # Known selector
            description="the search input"  # Fallback description
        )

        await asyncio.sleep(1)

        # Click search button
        await automation.smart_click(
            selector="input[name='btnK']",
            description="the Google Search button"
        )

        await asyncio.sleep(3)
        logger.info("✓ Search workflow complete")


async def example_form_extraction():
    """
    Example: Extract all form fields from a page.
    """
    logger.info("=" * 70)
    logger.info("EXAMPLE: Form Field Extraction")
    logger.info("=" * 70)

    async with EnhancedWebAutomation() as automation:
        # Navigate to a page with forms
        await automation.page.goto("https://www.google.com")

        # Extract all form fields
        fields = await automation.extract_form_fields()

        logger.info(f"\nExtracted {len(fields)} form fields:")
        for desc, element in fields.items():
            logger.info(f"  - {desc}")
            logger.info(f"    Type: {element.element_type.value}")
            logger.info(f"    Confidence: {element.confidence:.2f}")
            logger.info(f"    Method: {element.match_method.value}")

        logger.info("✓ Form extraction complete")


async def example_canvas_interaction():
    """
    Example: Interact with canvas-based UI elements.
    """
    logger.info("=" * 70)
    logger.info("EXAMPLE: Canvas Interaction")
    logger.info("=" * 70)

    async with EnhancedWebAutomation() as automation:
        # Navigate to a canvas-based application
        # (Using a demo page for illustration)
        await automation.page.goto("https://developer.mozilla.org/en-US/docs/Web/API/Canvas_API")

        # Try to find canvas elements
        result = await automation.grounding_engine.ground_canvas_element(
            automation.page,
            "the canvas drawing area",
            canvas_selector="canvas"
        )

        if result:
            logger.info(f"✓ Found canvas element")
            logger.info(f"  Confidence: {result.confidence:.2f}")
            logger.info(f"  Center: {result.center}")

            # You could click on the canvas at specific coordinates
            if result.center:
                x, y = result.center
                await automation.page.mouse.click(x, y)
                logger.info(f"✓ Clicked canvas at ({x}, {y})")
        else:
            logger.info("No canvas element found")

        logger.info("✓ Canvas interaction example complete")


async def example_complex_page_navigation():
    """
    Example: Navigate a complex page using region focus.
    """
    logger.info("=" * 70)
    logger.info("EXAMPLE: Complex Page Navigation with Region Focus")
    logger.info("=" * 70)

    async with EnhancedWebAutomation() as automation:
        # Navigate to a complex page
        await automation.page.goto("https://news.ycombinator.com")

        # Use region focus to find elements on complex pages
        result = await automation.grounding_engine.ground_element(
            automation.page,
            "the login link",
            strategy=GroundingStrategy.REGION_FOCUS
        )

        if result.success:
            logger.info(f"✓ Found element using region focus")
            logger.info(f"  Confidence: {result.best_match.confidence:.2f}")

            # Click the element
            await automation.grounding_engine.click_grounded_element(
                automation.page,
                result.best_match
            )

            await asyncio.sleep(2)
            logger.info("✓ Navigation complete")
        else:
            logger.error("✗ Region focus failed")


async def example_multi_step_workflow():
    """
    Example: Multi-step workflow combining multiple techniques.
    """
    logger.info("=" * 70)
    logger.info("EXAMPLE: Multi-Step Workflow")
    logger.info("=" * 70)

    async with EnhancedWebAutomation() as automation:
        # Step 1: Navigate to Google
        logger.info("\nStep 1: Navigate to Google")
        await automation.page.goto("https://www.google.com")

        # Step 2: Fill search
        logger.info("\nStep 2: Fill search box")
        await automation.smart_fill(
            text="Eversale",
            description="the search input"
        )

        await asyncio.sleep(1)

        # Step 3: Click search
        logger.info("\nStep 3: Click search button")
        await automation.smart_click(description="the Google Search button")

        await asyncio.sleep(3)

        # Step 4: Extract search results (first few)
        logger.info("\nStep 4: Extract search results")
        results = await automation.grounding_engine.ground_multiple_elements(
            automation.page,
            [
                "the first search result",
                "the second search result",
                "the third search result"
            ]
        )

        for desc, result in results.items():
            if result.success:
                logger.info(f"  ✓ Found: {desc} (confidence: {result.best_match.confidence:.2f})")

        logger.info("✓ Multi-step workflow complete")


async def example_error_recovery():
    """
    Example: Demonstrate error recovery with visual grounding.
    """
    logger.info("=" * 70)
    logger.info("EXAMPLE: Error Recovery")
    logger.info("=" * 70)

    async with EnhancedWebAutomation() as automation:
        await automation.page.goto("https://www.google.com")

        # Scenario 1: Selector is wrong, but visual grounding saves us
        logger.info("\n1. Testing fallback from bad selector...")
        success = await automation.smart_click(
            selector="button.nonexistent-class",  # Wrong selector
            description="the Google Search button"  # Visual fallback
        )

        if success:
            logger.info("✓ Recovered from bad selector using visual grounding")
        else:
            logger.warning("✗ Even visual grounding couldn't help")

        # Scenario 2: Element doesn't exist
        logger.info("\n2. Testing non-existent element...")
        success = await automation.smart_click(
            description="the purple unicorn button that doesn't exist"
        )

        if not success:
            logger.info("✓ Correctly failed for non-existent element")

        logger.info("✓ Error recovery example complete")


# ==============================================================================
# INTEGRATION WITH EXISTING EVERSALE WORKFLOWS
# ==============================================================================

async def integrate_with_sdr_workflow():
    """
    Example: Integrate visual grounding with Eversale SDR workflow.

    Shows how visual grounding enhances lead generation tasks.
    """
    logger.info("=" * 70)
    logger.info("INTEGRATION: Visual Grounding + SDR Workflow")
    logger.info("=" * 70)

    async with EnhancedWebAutomation() as automation:
        # Navigate to LinkedIn (example)
        logger.info("\n1. Navigate to LinkedIn")
        await automation.page.goto("https://www.linkedin.com")

        # Use visual grounding to find and interact with search
        logger.info("\n2. Find search box using visual grounding")
        result = await automation.grounding_engine.ground_element(
            automation.page,
            "the search input at the top",
            strategy=GroundingStrategy.HYBRID
        )

        if result.success:
            logger.info(f"✓ Found search (confidence: {result.best_match.confidence:.2f})")

            # Fill search with lead criteria
            await automation.grounding_engine.fill_grounded_element(
                automation.page,
                result.best_match,
                "CEO at software company"
            )

            logger.info("✓ Filled search criteria")
        else:
            logger.warning("✗ Could not find search")

        logger.info("\n✓ SDR workflow integration example complete")


# ==============================================================================
# MAIN
# ==============================================================================

async def run_all_examples():
    """Run all integration examples."""
    examples = [
        ("Login Workflow", example_login_workflow),
        ("Search Workflow", example_search_workflow),
        ("Form Extraction", example_form_extraction),
        ("Canvas Interaction", example_canvas_interaction),
        ("Complex Page Navigation", example_complex_page_navigation),
        ("Multi-Step Workflow", example_multi_step_workflow),
        ("Error Recovery", example_error_recovery),
        ("SDR Integration", integrate_with_sdr_workflow),
    ]

    logger.info("\n" + "=" * 70)
    logger.info("VISUAL GROUNDING - INTEGRATION EXAMPLES")
    logger.info("=" * 70 + "\n")

    for name, func in examples:
        try:
            logger.info(f"\n{'=' * 70}")
            logger.info(f"Running: {name}")
            logger.info(f"{'=' * 70}")
            await func()
            logger.info(f"✓ {name} completed")
        except Exception as e:
            logger.error(f"✗ {name} failed: {e}")
            import traceback
            traceback.print_exc()

        await asyncio.sleep(2)

    logger.info("\n" + "=" * 70)
    logger.info("ALL EXAMPLES COMPLETE")
    logger.info("=" * 70 + "\n")


if __name__ == "__main__":
    # Run a single example
    # asyncio.run(example_search_workflow())

    # Or run all examples
    asyncio.run(run_all_examples())
