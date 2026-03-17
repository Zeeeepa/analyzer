"""
Visual Element Finder - Vision-based element localization using moondream.

This module provides visual element grounding capabilities, allowing the agent
to locate UI elements by natural language descriptions rather than CSS selectors.
Uses the moondream vision model to analyze screenshots and return coordinates.

Key Features:
- Natural language element finding ("Find the login button")
- Vision-based localization (no selectors needed)
- Self-healing (adapts to UI changes)
- Confidence scoring for reliability

Usage:
    finder = VisualElementFinder(ollama_client)
    result = await finder.find_element(page, "login button")
    await finder.find_and_click(page, "submit button")
    await finder.find_and_fill(page, "email input field", "user@example.com")
"""

import asyncio
import base64
import re
import logging
from typing import Dict, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class VisualElementFinder:
    """
    Vision-based element finder using moondream for visual grounding.

    This class uses a vision language model to locate UI elements on a webpage
    by analyzing screenshots and natural language descriptions.
    """

    def __init__(self, ollama_client, vision_model: str = "moondream"):
        """
        Initialize the Visual Element Finder.

        Args:
            ollama_client: Ollama client instance for LLM calls
            vision_model: Vision model to use (default: moondream)
        """
        self.ollama = ollama_client
        self.vision_model = vision_model
        self.screenshot_cache = {}  # Cache screenshots to avoid redundant captures

    async def _take_screenshot(self, page) -> Tuple[bytes, int, int]:
        """
        Take a screenshot of the current page.

        Args:
            page: Playwright page object

        Returns:
            Tuple of (screenshot_bytes, width, height)
        """
        try:
            # Get viewport size
            viewport = page.viewport_size
            width = viewport.get('width', 1920)
            height = viewport.get('height', 1080)

            # Take screenshot
            screenshot_bytes = await page.screenshot(type='png', full_page=False)

            logger.debug(f"Screenshot captured: {width}x{height}, {len(screenshot_bytes)} bytes")
            return screenshot_bytes, width, height

        except Exception as e:
            logger.error(f"Failed to capture screenshot: {e}")
            raise

    def _encode_image(self, image_bytes: bytes) -> str:
        """
        Encode image bytes to base64.

        Args:
            image_bytes: Raw image bytes

        Returns:
            Base64 encoded string
        """
        return base64.b64encode(image_bytes).decode('utf-8')

    def _parse_coordinates(self, response_text: str, width: int, height: int) -> Optional[Dict]:
        """
        Parse coordinates from moondream response.

        Expected formats:
        - "x=0.5, y=0.3" (percentage)
        - "x=500, y=300" (pixels)
        - "center at (0.5, 0.3)"
        - "located at x: 0.5, y: 0.3"

        Args:
            response_text: Raw response from vision model
            width: Screenshot width in pixels
            height: Screenshot height in pixels

        Returns:
            Dict with x, y coordinates in pixels, or None if parsing fails
        """
        try:
            # Clean the response text
            text = response_text.lower().strip()

            # Try various regex patterns
            patterns = [
                r'x[=:]\s*([0-9.]+).*?y[=:]\s*([0-9.]+)',  # x=0.5, y=0.3
                r'\(([0-9.]+),\s*([0-9.]+)\)',              # (0.5, 0.3)
                r'([0-9.]+)\s*,\s*([0-9.]+)',               # 0.5, 0.3
            ]

            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    x_val = float(match.group(1))
                    y_val = float(match.group(2))

                    # Convert percentage to pixels if needed
                    # Heuristic: values <= 1.0 are percentages
                    if x_val <= 1.0:
                        x_val = int(x_val * width)
                    else:
                        x_val = int(x_val)

                    if y_val <= 1.0:
                        y_val = int(y_val * height)
                    else:
                        y_val = int(y_val)

                    # Sanity check: ensure coordinates are within bounds
                    if 0 <= x_val <= width and 0 <= y_val <= height:
                        logger.debug(f"Parsed coordinates: x={x_val}, y={y_val}")
                        return {'x': x_val, 'y': y_val}

            logger.warning(f"Failed to parse coordinates from: {response_text}")
            return None

        except Exception as e:
            logger.error(f"Error parsing coordinates: {e}")
            return None

    def _extract_confidence(self, response_text: str) -> float:
        """
        Extract confidence score from response.

        Args:
            response_text: Raw response from vision model

        Returns:
            Confidence score between 0.0 and 1.0
        """
        # Look for confidence indicators
        text = response_text.lower()

        # Explicit confidence scores
        conf_match = re.search(r'confidence[=:]\s*([0-9.]+)', text)
        if conf_match:
            return min(1.0, float(conf_match.group(1)))

        # Heuristic: presence of uncertainty words reduces confidence
        uncertainty_words = ['maybe', 'possibly', 'might', 'unclear', 'uncertain']
        confidence = 0.8  # Default confidence

        for word in uncertainty_words:
            if word in text:
                confidence -= 0.2
                break

        # Heuristic: very short responses are less confident
        if len(response_text.strip()) < 20:
            confidence -= 0.1

        return max(0.0, min(1.0, confidence))

    async def find_element(self, page, description: str) -> Dict:
        """
        Find an element on the page using visual grounding.

        Args:
            page: Playwright page object
            description: Natural language description (e.g., "login button", "email input field")

        Returns:
            Dict with:
                - x: X coordinate in pixels
                - y: Y coordinate in pixels
                - confidence: Confidence score (0.0-1.0)
                - selector_hint: Optional CSS selector hint (empty for vision-only)
                - success: Boolean indicating if element was found
                - error: Error message if failed
        """
        try:
            logger.info(f"Finding element: '{description}'")

            # Take screenshot
            screenshot_bytes, width, height = await self._take_screenshot(page)
            image_b64 = self._encode_image(screenshot_bytes)

            # Construct prompt for moondream
            prompt = f"""Find the {description} on this webpage.

Return the approximate location as coordinates. Use percentage values (0.0 to 1.0) where:
- x=0.0 is left edge, x=1.0 is right edge
- y=0.0 is top edge, y=1.0 is bottom edge

Format your response EXACTLY like this:
x=0.5, y=0.3

If you cannot find the element, respond with:
x=-1, y=-1

Be precise and only return the coordinates."""

            # Call moondream vision model
            logger.debug(f"Calling {self.vision_model} with prompt: {prompt[:100]}...")

            response = await asyncio.to_thread(
                self.ollama.chat,
                model=self.vision_model,
                messages=[{
                    'role': 'user',
                    'content': prompt,
                    'images': [image_b64]
                }]
            )

            response_text = response['message']['content']
            logger.debug(f"Moondream response: {response_text}")

            # Parse coordinates
            coords = self._parse_coordinates(response_text, width, height)

            if coords is None or coords['x'] < 0 or coords['y'] < 0:
                return {
                    'success': False,
                    'error': f'Could not locate element: {description}',
                    'x': -1,
                    'y': -1,
                    'confidence': 0.0,
                    'selector_hint': '',
                    'raw_response': response_text
                }

            # Extract confidence
            confidence = self._extract_confidence(response_text)

            return {
                'success': True,
                'x': coords['x'],
                'y': coords['y'],
                'confidence': confidence,
                'selector_hint': '',  # Vision-only, no selector
                'raw_response': response_text
            }

        except Exception as e:
            logger.error(f"Error in find_element: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'x': -1,
                'y': -1,
                'confidence': 0.0,
                'selector_hint': '',
                'raw_response': ''
            }

    async def find_and_click(self, page, description: str) -> bool:
        """
        Find an element and click it.

        Args:
            page: Playwright page object
            description: Natural language description of element to click

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Finding and clicking: '{description}'")

            # Find element
            result = await self.find_element(page, description)

            if not result['success']:
                logger.error(f"Failed to find element: {result.get('error', 'Unknown error')}")
                return False

            # Check confidence threshold
            if result['confidence'] < 0.5:
                logger.warning(f"Low confidence ({result['confidence']:.2f}) for clicking '{description}'")

            # Click at coordinates
            x, y = result['x'], result['y']
            logger.info(f"Clicking at ({x}, {y}) with confidence {result['confidence']:.2f}")

            await page.mouse.click(x, y)

            # Wait a moment for potential navigation or state changes
            await asyncio.sleep(0.5)

            logger.info(f"Successfully clicked '{description}'")
            return True

        except Exception as e:
            logger.error(f"Error in find_and_click: {e}", exc_info=True)
            return False

    async def find_and_fill(self, page, description: str, value: str) -> bool:
        """
        Find an input element and fill it with a value.

        Args:
            page: Playwright page object
            description: Natural language description of input field
            value: Value to fill

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Finding and filling '{description}' with '{value}'")

            # Find element
            result = await self.find_element(page, description)

            if not result['success']:
                logger.error(f"Failed to find element: {result.get('error', 'Unknown error')}")
                return False

            # Check confidence threshold
            if result['confidence'] < 0.5:
                logger.warning(f"Low confidence ({result['confidence']:.2f}) for filling '{description}'")

            # Click to focus
            x, y = result['x'], result['y']
            logger.debug(f"Clicking input at ({x}, {y})")
            await page.mouse.click(x, y)

            # Wait for focus
            await asyncio.sleep(0.3)

            # Clear existing content (Ctrl+A, Delete)
            await page.keyboard.press('Control+A')
            await page.keyboard.press('Backspace')

            # Type the value
            logger.debug(f"Typing value: {value}")
            await page.keyboard.type(value, delay=50)  # 50ms between keystrokes

            # Wait a moment for input to register
            await asyncio.sleep(0.3)

            logger.info(f"Successfully filled '{description}' with '{value}'")
            return True

        except Exception as e:
            logger.error(f"Error in find_and_fill: {e}", exc_info=True)
            return False

    async def find_multiple(self, page, descriptions: list) -> Dict[str, Dict]:
        """
        Find multiple elements in a single screenshot pass.

        Args:
            page: Playwright page object
            descriptions: List of element descriptions

        Returns:
            Dict mapping descriptions to find_element results
        """
        try:
            logger.info(f"Finding {len(descriptions)} elements")

            # Take screenshot once
            screenshot_bytes, width, height = await self._take_screenshot(page)

            results = {}
            for desc in descriptions:
                # Reuse screenshot
                image_b64 = self._encode_image(screenshot_bytes)

                prompt = f"""Find the {desc} on this webpage.

Return the approximate location as coordinates. Use percentage values (0.0 to 1.0) where:
- x=0.0 is left edge, x=1.0 is right edge
- y=0.0 is top edge, y=1.0 is bottom edge

Format your response EXACTLY like this:
x=0.5, y=0.3

If you cannot find the element, respond with:
x=-1, y=-1"""

                response = await asyncio.to_thread(
                    self.ollama.chat,
                    model=self.vision_model,
                    messages=[{
                        'role': 'user',
                        'content': prompt,
                        'images': [image_b64]
                    }]
                )

                response_text = response['message']['content']
                coords = self._parse_coordinates(response_text, width, height)
                confidence = self._extract_confidence(response_text)

                if coords and coords['x'] >= 0 and coords['y'] >= 0:
                    results[desc] = {
                        'success': True,
                        'x': coords['x'],
                        'y': coords['y'],
                        'confidence': confidence,
                        'selector_hint': '',
                        'raw_response': response_text
                    }
                else:
                    results[desc] = {
                        'success': False,
                        'error': f'Could not locate: {desc}',
                        'x': -1,
                        'y': -1,
                        'confidence': 0.0,
                        'selector_hint': '',
                        'raw_response': response_text
                    }

            return results

        except Exception as e:
            logger.error(f"Error in find_multiple: {e}", exc_info=True)
            return {}

    def clear_cache(self):
        """Clear the screenshot cache."""
        self.screenshot_cache.clear()
        logger.debug("Screenshot cache cleared")
