"""
Smart Selector - Intelligent Element Selection

Combines element inspection + visual targeting for robust automation.

This is the high-level API that ReAct loop should use for element interactions.
It automatically:
1. Tries visual targeting (pixel-perfect)
2. Falls back to selector strategies (ARIA, ID, etc.)
3. Validates interactability before acting
4. Provides detailed diagnostics on failure
5. Self-heals broken selectors

Usage:
    selector = SmartSelector(page)
    await selector.click("Submit button")
    await selector.fill("Email input", "user@example.com")
    items = await selector.extract_list("First product card")
"""

import base64
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from loguru import logger

from element_inspector import ElementInspector, SelectorStrategy
from visual_targeting import VisualTargeting, TargetingResult


@dataclass
class SmartSelectorResult:
    """Result of smart element selection."""
    success: bool
    method: str  # 'visual', 'selector', 'fallback'
    selector: Optional[str] = None
    coordinates: Optional[Tuple[int, int]] = None
    confidence: float = 0.0
    issues: List[str] = None
    suggestions: List[str] = None

    def __post_init__(self):
        if self.issues is None:
            self.issues = []
        if self.suggestions is None:
            self.suggestions = []


class SmartSelector:
    """
    Intelligent element selection combining visual + structural targeting.

    Handles the full lifecycle:
    1. Element location (visual or selector)
    2. Interactability validation
    3. Pre-interaction fixes (scroll into view, wait for enabled)
    4. Interaction execution
    5. Post-interaction verification
    """

    def __init__(
        self,
        page,
        visual_targeting: Optional[VisualTargeting] = None,
        prefer_visual: bool = True
    ):
        """
        Initialize smart selector.

        Args:
            page: Playwright page instance
            visual_targeting: Optional VisualTargeting instance
            prefer_visual: Try visual targeting before selectors
        """
        self.page = page
        self.inspector = ElementInspector(page)
        self.visual = visual_targeting or VisualTargeting()
        self.prefer_visual = prefer_visual

        # Cache for selector quality
        self._selector_cache: Dict[str, str] = {}

    async def locate(
        self,
        description: str,
        context: str = "",
        fallback_selectors: List[str] = None
    ) -> SmartSelectorResult:
        """
        Intelligently locate an element.

        Args:
            description: Natural language description (e.g., "Submit button")
            context: Optional context about the action
            fallback_selectors: Optional list of CSS selectors to try

        Returns:
            SmartSelectorResult with location info
        """
        # Strategy 1: Visual targeting (if enabled)
        if self.prefer_visual:
            visual_result = await self._try_visual(description, context)
            if visual_result.success:
                return visual_result

        # Strategy 2: Fallback selectors
        if fallback_selectors:
            for selector in fallback_selectors:
                selector_result = await self._try_selector(selector, description)
                if selector_result.success:
                    return selector_result

        # Strategy 3: Generate smart selectors from description
        generated = self._generate_selectors_from_description(description)
        for selector in generated:
            selector_result = await self._try_selector(selector, description)
            if selector_result.success:
                return selector_result

        # All strategies failed
        return SmartSelectorResult(
            success=False,
            method='none',
            issues=[f"Could not locate: {description}"],
            suggestions=[
                "Check if element exists on page",
                "Verify element is not in iframe",
                "Wait for page to load fully"
            ]
        )

    async def click(
        self,
        description: str,
        context: str = "",
        fallback_selectors: List[str] = None,
        humanized: bool = True
    ) -> SmartSelectorResult:
        """
        Intelligently click an element.

        Args:
            description: What to click (e.g., "Submit button")
            context: Why we're clicking (for visual targeting)
            fallback_selectors: Manual selectors to try
            humanized: Use human-like mouse movement

        Returns:
            SmartSelectorResult
        """
        # Locate element
        location = await self.locate(description, context, fallback_selectors)

        if not location.success:
            return location

        # Validate interactability
        if location.selector:
            diagnosis = await self.inspector.diagnose_interaction_failure(location.selector)

            if not diagnosis['is_interactable']:
                # Try to fix issues
                fixed = await self._fix_interaction_issues(diagnosis)

                if not fixed:
                    return SmartSelectorResult(
                        success=False,
                        method=location.method,
                        selector=location.selector,
                        issues=diagnosis['issues'],
                        suggestions=diagnosis['suggestions']
                    )

        # Perform click
        try:
            if location.coordinates:
                # Visual targeting - click coordinates
                x, y = location.coordinates
                if humanized:
                    # Use humanized clicking if available
                    try:
                        from humanization.bezier_cursor import BezierCursor
                        cursor = BezierCursor()
                        await cursor.click_at(self.page, coordinates=(x, y))
                    except ImportError:
                        await self.page.mouse.click(x, y)
                else:
                    await self.page.mouse.click(x, y)

            elif location.selector:
                # Selector-based click
                await self.page.click(location.selector, timeout=5000)

            logger.info(f"Clicked: {description} via {location.method}")

            return SmartSelectorResult(
                success=True,
                method=location.method,
                selector=location.selector,
                coordinates=location.coordinates,
                confidence=location.confidence
            )

        except Exception as e:
            logger.warning(f"Click failed for {description}: {e}")

            return SmartSelectorResult(
                success=False,
                method=location.method,
                selector=location.selector,
                issues=[f"Click failed: {str(e)}"],
                suggestions=["Element may have moved", "Page may have changed"]
            )

    async def fill(
        self,
        description: str,
        text: str,
        fallback_selectors: List[str] = None,
        humanized: bool = True
    ) -> SmartSelectorResult:
        """
        Intelligently fill an input field.

        Args:
            description: Input description (e.g., "Email field")
            text: Text to fill
            fallback_selectors: Manual selectors to try
            humanized: Use human-like typing

        Returns:
            SmartSelectorResult
        """
        # Locate element
        location = await self.locate(description, fallback_selectors=fallback_selectors)

        if not location.success:
            return location

        # Must have selector for filling (can't fill by coordinates)
        if not location.selector:
            # Try to get selector from coordinates
            if location.coordinates:
                location.selector = await self._selector_from_coordinates(location.coordinates)

        if not location.selector:
            return SmartSelectorResult(
                success=False,
                method=location.method,
                issues=["Cannot fill: no selector available"],
                suggestions=["Provide fallback_selectors", "Element may not be an input"]
            )

        # Validate interactability
        diagnosis = await self.inspector.diagnose_interaction_failure(location.selector)

        if not diagnosis['is_interactable']:
            fixed = await self._fix_interaction_issues(diagnosis)
            if not fixed:
                return SmartSelectorResult(
                    success=False,
                    method=location.method,
                    selector=location.selector,
                    issues=diagnosis['issues'],
                    suggestions=diagnosis['suggestions']
                )

        # Perform fill
        try:
            if humanized:
                # Use human-like typing if available
                try:
                    from humanization.human_typer import HumanTyper
                    typer = HumanTyper()
                    await typer.type_text(self.page, text, selector=location.selector)
                except ImportError:
                    await self.page.fill(location.selector, text)
            else:
                await self.page.fill(location.selector, text)

            logger.info(f"Filled {description} with: {text[:20]}...")

            return SmartSelectorResult(
                success=True,
                method=location.method,
                selector=location.selector,
                confidence=location.confidence
            )

        except Exception as e:
            logger.warning(f"Fill failed for {description}: {e}")

            return SmartSelectorResult(
                success=False,
                method=location.method,
                selector=location.selector,
                issues=[f"Fill failed: {str(e)}"],
                suggestions=["Element may not be an input", "Field may be readonly"]
            )

    async def extract_list(
        self,
        first_item_description: str,
        max_items: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Extract all items from a list by finding similar siblings.

        Args:
            first_item_description: Description of first item
            max_items: Maximum items to extract

        Returns:
            List of item dictionaries with text, attributes, etc.
        """
        # Locate first item
        location = await self.locate(first_item_description)

        if not location.success or not location.selector:
            logger.warning(f"Could not locate first item: {first_item_description}")
            return []

        # Find similar siblings
        siblings = await self.inspector.get_similar_siblings(location.selector)

        # Include first item
        first = await self.inspector.inspect_element(location.selector)

        items = []

        if first:
            items.append({
                'text': first.inner_text,
                'id': first.id,
                'classes': first.classes,
                'href': first.attributes.get('href'),
                'index': 0
            })

        # Add siblings
        for i, sibling in enumerate(siblings[:max_items-1], 1):
            items.append({
                'text': sibling.inner_text,
                'id': sibling.id,
                'classes': sibling.classes,
                'href': sibling.attributes.get('href'),
                'index': i
            })

        logger.info(f"Extracted {len(items)} items from list")

        return items

    async def verify_element_exists(
        self,
        description: str,
        fallback_selectors: List[str] = None
    ) -> bool:
        """
        Quick check: does this element exist on page?

        Args:
            description: Element description
            fallback_selectors: Manual selectors to try

        Returns:
            True if element found
        """
        location = await self.locate(description, fallback_selectors=fallback_selectors)
        return location.success

    async def get_element_text(
        self,
        description: str,
        fallback_selectors: List[str] = None
    ) -> Optional[str]:
        """
        Get text content of an element.

        Args:
            description: Element description
            fallback_selectors: Manual selectors to try

        Returns:
            Text content or None
        """
        location = await self.locate(description, fallback_selectors=fallback_selectors)

        if not location.success or not location.selector:
            return None

        snapshot = await self.inspector.inspect_element(location.selector)

        return snapshot.inner_text if snapshot else None

    async def wait_for_element(
        self,
        description: str,
        timeout: float = 10.0,
        fallback_selectors: List[str] = None
    ) -> SmartSelectorResult:
        """
        Wait for element to appear.

        Args:
            description: Element description
            timeout: Timeout in seconds
            fallback_selectors: Manual selectors to try

        Returns:
            SmartSelectorResult when element appears (or timeout)
        """
        import asyncio

        start_time = asyncio.get_event_loop().time()

        while (asyncio.get_event_loop().time() - start_time) < timeout:
            location = await self.locate(description, fallback_selectors=fallback_selectors)

            if location.success:
                return location

            await asyncio.sleep(0.5)

        return SmartSelectorResult(
            success=False,
            method='timeout',
            issues=[f"Element not found within {timeout}s: {description}"],
            suggestions=["Increase timeout", "Check if element loads dynamically"]
        )

    # ===== Internal Methods =====

    async def _try_visual(
        self,
        description: str,
        context: str = ""
    ) -> SmartSelectorResult:
        """Try visual targeting."""
        try:
            # Take screenshot
            screenshot = await self.page.screenshot()
            screenshot_b64 = base64.b64encode(screenshot).decode()

            # Locate via vision
            result = await self.visual.locate_element(screenshot_b64, description, context)

            if result.success and result.coordinates:
                return SmartSelectorResult(
                    success=True,
                    method='visual',
                    coordinates=result.coordinates,
                    confidence=result.confidence
                )

            return SmartSelectorResult(success=False, method='visual')

        except Exception as e:
            logger.debug(f"Visual targeting failed: {e}")
            return SmartSelectorResult(success=False, method='visual')

    async def _try_selector(
        self,
        selector: str,
        description: str
    ) -> SmartSelectorResult:
        """Try CSS selector."""
        snapshot = await self.inspector.inspect_element(selector)

        if snapshot:
            # Analyze quality
            quality = await self.inspector.analyze_selector_quality(snapshot)

            return SmartSelectorResult(
                success=True,
                method='selector',
                selector=quality.recommended_selector,  # Use recommended, not original
                confidence=quality.confidence
            )

        return SmartSelectorResult(success=False, method='selector')

    async def _fix_interaction_issues(self, diagnosis: Dict[str, Any]) -> bool:
        """
        Try to fix common interaction issues.

        Returns:
            True if fixed
        """
        snapshot = diagnosis.get('snapshot')

        if not snapshot:
            return False

        selector = diagnosis.get('quality_report', {}).get('recommended_selector')

        if not selector:
            return False

        try:
            # Fix: Not in viewport -> scroll
            if not snapshot.is_in_viewport:
                await self.page.locator(selector).scroll_into_view_if_needed()
                logger.info(f"Scrolled element into view: {selector}")

            # Fix: Hidden -> wait for visible
            if not snapshot.is_visible:
                await self.page.wait_for_selector(selector, state='visible', timeout=5000)
                logger.info(f"Waited for element to become visible: {selector}")

            # Fix: Disabled -> wait for enabled
            if not snapshot.is_enabled:
                # Try waiting briefly for element to be enabled
                await asyncio.sleep(1)
                # Check again
                new_snapshot = await self.inspector.inspect_element(selector)
                if new_snapshot and not new_snapshot.is_enabled:
                    return False  # Can't fix

            return True

        except Exception as e:
            logger.warning(f"Failed to fix interaction issues: {e}")
            return False

    async def _selector_from_coordinates(
        self,
        coordinates: Tuple[int, int]
    ) -> Optional[str]:
        """
        Get selector for element at coordinates.

        Args:
            coordinates: (x, y) pixel coordinates

        Returns:
            CSS selector or None
        """
        x, y = coordinates

        try:
            # Use evaluate to find element at coordinates
            selector = await self.page.evaluate('''
                (coords) => {
                    const el = document.elementFromPoint(coords[0], coords[1]);
                    if (!el) return null;

                    // Generate selector
                    if (el.id) return `#${el.id}`;
                    if (el.getAttribute('aria-label')) {
                        return `[aria-label="${el.getAttribute('aria-label')}"]`;
                    }
                    // Fallback: tag + class
                    if (el.classList.length > 0) {
                        return `${el.tagName.toLowerCase()}.${el.classList[0]}`;
                    }
                    return el.tagName.toLowerCase();
                }
            ''', [x, y])

            return selector

        except Exception as e:
            logger.warning(f"Failed to get selector from coordinates: {e}")
            return None

    def _generate_selectors_from_description(self, description: str) -> List[str]:
        """
        Generate CSS selectors from natural language description.

        Args:
            description: Natural language (e.g., "Submit button")

        Returns:
            List of candidate selectors
        """
        selectors = []
        desc_lower = description.lower()

        # Extract key words
        words = desc_lower.split()

        # Strategy 1: ARIA label
        selectors.append(f'[aria-label="{description}"]')
        selectors.append(f'[aria-label*="{words[0]}"]')

        # Strategy 2: Button with text
        if 'button' in desc_lower:
            text = desc_lower.replace('button', '').strip()
            selectors.extend([
                f'button:has-text("{text}")',
                f'[role="button"]:has-text("{text}")',
                f'input[type="submit"][value*="{text}"]'
            ])

        # Strategy 3: Link with text
        elif 'link' in desc_lower:
            text = desc_lower.replace('link', '').strip()
            selectors.extend([
                f'a:has-text("{text}")',
                f'[role="link"]:has-text("{text}")'
            ])

        # Strategy 4: Input field
        elif 'input' in desc_lower or 'field' in desc_lower:
            text = desc_lower.replace('input', '').replace('field', '').strip()
            selectors.extend([
                f'input[placeholder*="{text}"]',
                f'input[name*="{text}"]',
                f'[data-testid*="{text}"]',
                f'label:has-text("{text}") + input'
            ])

        # Strategy 5: Generic text matching
        if words:
            selectors.append(f':has-text("{description}")')

        return selectors


# Convenience exports
__all__ = [
    'SmartSelector',
    'SmartSelectorResult'
]
