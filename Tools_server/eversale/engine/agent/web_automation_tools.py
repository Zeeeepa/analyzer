"""
Advanced Web Automation Tools for Business Tasks
- STEALTH MODE (comprehensive anti-detection)
- Human-like timing and behavior
- Smart form filling
- Data extraction
- Session management
- CAPTCHA solving (vision-based + manual fallback, NO paid APIs)
"""

import asyncio
import random
import json
import csv
import ast
from pathlib import Path
from typing import Dict, Any, List, Optional
from loguru import logger

# Import hallucination guard for extraction validation
try:
    from .hallucination_guard import get_guard
    HALLUCINATION_GUARD_AVAILABLE = True
except ImportError:
    HALLUCINATION_GUARD_AVAILABLE = False

# Import stealth utilities for human-like behavior
from .stealth_utils import (
    human_delay,
    between_action_delay,
    reading_delay,
    thinking_delay,
    typing_delay,
    human_scroll,
    rate_limiter,
)

# Import CAPTCHA solver (vision-based, no paid APIs)
try:
    from .captcha_solver import LocalCaptchaSolver, PageCaptchaHandler
    CAPTCHA_AVAILABLE = True
except ImportError:
    CAPTCHA_AVAILABLE = False
    logger.debug("CAPTCHA solver not available")

# Import visual fallback for screenshot + click when selectors fail
try:
    from .selector_fallbacks import get_visual_fallback
    VISUAL_FALLBACK_AVAILABLE = True
except ImportError:
    VISUAL_FALLBACK_AVAILABLE = False
    get_visual_fallback = None


class WebAutomationTools:
    """Advanced tools for business web automation"""

    def __init__(self, playwright_client):
        self.pw = playwright_client

        # Initialize local CAPTCHA solver (vision-based, no API key needed)
        self.captcha_handler = None
        if CAPTCHA_AVAILABLE:
            solver = LocalCaptchaSolver()
            logger.info("[CAPTCHA] Local vision-based solver initialized (no API key required)")

    async def smart_type(
        self,
        selector: str,
        text: str,
        human_like: bool = True,
        visual_description: str = None
    ) -> Dict[str, Any]:
        """
        Type text with human-like delays to avoid detection (STEALTH MODE)

        Falls back to visual detection if selector fails.

        Args:
            selector: CSS selector
            text: Text to type
            human_like: Add random delays between keystrokes
            visual_description: Description for visual fallback (e.g., "the search box")
        """
        try:
            # STEALTH: Human-like click to focus - uses visual fallback if selector fails
            await between_action_delay()
            click_result = await self.wait_and_click(selector, timeout=5000, visual_description=visual_description)

            if "error" in click_result:
                return click_result

            await human_delay(100, 300)

            if human_like:
                # STEALTH: Clear any existing content first
                await self.pw.page.keyboard.press("Control+a")
                await human_delay(30, 80)
                await self.pw.page.keyboard.press("Backspace")
                await human_delay(50, 150)

                # Type character by character with variable human-like delays
                for i, char in enumerate(text):
                    # STEALTH: Occasional typo and correction (2% chance)
                    if random.random() < 0.02 and len(text) > 10:
                        wrong_char = random.choice('abcdefghijklmnopqrstuvwxyz')
                        await self.pw.page.keyboard.type(wrong_char)
                        await human_delay(100, 250)
                        await self.pw.page.keyboard.press("Backspace")
                        await human_delay(80, 180)

                    await self.pw.page.keyboard.type(char)

                    # STEALTH: Variable typing speed
                    if char in ' .!?,\n':
                        await human_delay(80, 200)  # Longer pause after punctuation
                    elif random.random() < 0.1:
                        await human_delay(150, 350)  # Occasional thinking pause
                    else:
                        await typing_delay()  # Normal typing
            else:
                # Still need to type after clicking - clear and type
                await self.pw.page.keyboard.press("Control+a")
                await self.pw.page.keyboard.press("Backspace")
                await self.pw.page.keyboard.type(text)

            return {"success": True, "selector": selector, "text_length": len(text), "method": click_result.get("method", "selector")}

        except Exception as e:
            logger.error(f"Smart type error: {e}")
            return {"error": str(e)}

    async def smart_wait(self, condition: str, value: str = None, timeout: int = 5000) -> Dict[str, Any]:
        """
        Smart waiting for various conditions

        Conditions:
        - 'element': Wait for element to be visible
        - 'navigation': Wait for page navigation
        - 'network': Wait for network to be idle
        - 'time': Wait for specific milliseconds
        """
        try:
            if condition == 'element' and value:
                await self.pw.page.wait_for_selector(value, state='visible', timeout=timeout)
                return {"success": True, "waited_for": f"element {value}"}

            elif condition == 'navigation':
                await self.pw.page.wait_for_load_state('networkidle', timeout=timeout)
                return {"success": True, "waited_for": "navigation"}

            elif condition == 'network':
                await self.pw.page.wait_for_load_state('networkidle', timeout=timeout)
                return {"success": True, "waited_for": "network idle"}

            elif condition == 'time' and value:
                await asyncio.sleep(int(value) / 1000)
                return {"success": True, "waited_for": f"{value}ms"}

            else:
                return {"error": f"Unknown condition: {condition}"}

        except Exception as e:
            logger.error(f"Smart wait error: {e}")
            return {"error": str(e)}

    async def extract_data(self, selector: str, attribute: str = 'text') -> Dict[str, Any]:
        """
        Extract data from page elements

        Attributes:
        - 'text': Inner text
        - 'href': Link URL
        - 'src': Image/script source
        - 'value': Input value
        - 'data-*': Custom data attributes
        """
        try:
            elements = await self.pw.page.query_selector_all(selector)

            if not elements:
                return {"error": f"No elements found for: {selector}"}

            results = []
            for el in elements[:50]:  # Limit to 50 elements
                if attribute == 'text':
                    value = await el.inner_text()
                elif attribute == 'html':
                    value = await el.inner_html()
                else:
                    value = await el.get_attribute(attribute)

                if value:
                    results.append(value.strip())

            # ANTI-HALLUCINATION: Validate extracted data
            if HALLUCINATION_GUARD_AVAILABLE and results:
                guard = get_guard()
                clean_results = []
                for item in results:
                    validation = guard.validate_output(item, source_tool='web_automation_extract')
                    if validation.is_valid:
                        clean_results.append(item)
                    else:
                        logger.warning(f"Filtered suspicious data in extract_data: {item[:50]}...")
                results = clean_results

            return {
                "success": True,
                "selector": selector,
                "attribute": attribute,
                "count": len(results),
                "data": results
            }

        except Exception as e:
            logger.error(f"Extract data error: {e}")
            return {"error": str(e)}

    async def extract_table(self, selector: str = 'table') -> Dict[str, Any]:
        """Extract table data as CSV-ready format"""
        try:
            table = await self.pw.page.query_selector(selector)
            if not table:
                return {"error": f"No table found: {selector}"}

            # Extract headers
            headers = await table.query_selector_all('th')
            header_texts = []
            for h in headers:
                text = await h.inner_text()
                header_texts.append(text.strip())

            # Extract rows
            rows = await table.query_selector_all('tr')
            data_rows = []

            for row in rows[1:]:  # Skip header row
                cells = await row.query_selector_all('td')
                row_data = []
                for cell in cells:
                    text = await cell.inner_text()
                    row_data.append(text.strip())

                if row_data:
                    data_rows.append(row_data)

            # ANTI-HALLUCINATION: Validate table data for fake patterns
            if HALLUCINATION_GUARD_AVAILABLE:
                guard = get_guard()

                # Validate each row
                clean_rows = []
                for row in data_rows:
                    row_valid = True
                    for cell in row:
                        validation = guard.validate_output(cell, source_tool='web_automation_table')
                        if not validation.is_valid:
                            logger.warning(f"Filtered row with suspicious cell: {cell[:30]}...")
                            row_valid = False
                            break
                    if row_valid:
                        clean_rows.append(row)
                data_rows = clean_rows

            return {
                "success": True,
                "headers": header_texts,
                "rows": data_rows,
                "row_count": len(data_rows)
            }

        except Exception as e:
            logger.error(f"Extract table error: {e}")
            return {"error": str(e)}

    async def save_to_csv(self, filename: str, headers: List[str], rows: List[List[str]]) -> Dict[str, Any]:
        """
        Save extracted data to CSV with TRIPLE FAILSAFE parsing

        Layer 1: Parse any string format (JSON, Python, comma-separated)
        Layer 2: Validate and clean data structure
        Layer 3: Fallback to safe defaults if all else fails
        """
        try:
            # ===== LAYER 1: AGGRESSIVE PARSING =====
            # Parse headers if it's a string (JSON or Python list syntax)
            if isinstance(headers, str):
                original_headers = headers
                headers = None

                # Try JSON first
                if headers is None:
                    try:
                        headers = json.loads(original_headers)
                    except (json.JSONDecodeError, ValueError):
                        # Not JSON format, try next parser
                        pass

                # Try Python list syntax (e.g., "['a', 'b']")
                if headers is None:
                    try:
                        headers = ast.literal_eval(original_headers)
                    except (ValueError, SyntaxError):
                        # Not Python literal syntax, try next parser
                        pass

                # Try comma-separated
                if headers is None:
                    try:
                        headers = [h.strip().strip('"\'') for h in original_headers.split(',') if h.strip()]
                    except (AttributeError, TypeError):
                        # Not comma-separated format, will use fallback
                        pass

                # Emergency fallback
                if headers is None or not headers:
                    headers = ['Column1', 'Column2', 'Column3']  # Default headers

            # Parse rows if it's a string (JSON or Python list syntax)
            if isinstance(rows, str):
                original_rows = rows
                rows = None

                # Try JSON first
                if rows is None:
                    try:
                        rows = json.loads(original_rows)
                    except (json.JSONDecodeError, ValueError):
                        # Not JSON format, try next parser
                        pass

                # Try Python list syntax
                if rows is None:
                    try:
                        rows = ast.literal_eval(original_rows)
                    except (ValueError, SyntaxError):
                        # Not Python literal syntax, will use fallback
                        pass

                # Emergency fallback
                if rows is None:
                    rows = []

            # ===== LAYER 2: VALIDATION & CLEANING =====
            # Ensure headers is a flat list of strings
            if not isinstance(headers, list):
                headers = list(headers) if headers else ['Data']

            # Clean headers - remove nested lists, ensure strings
            cleaned_headers = []
            for h in headers:
                if isinstance(h, (list, tuple)):
                    cleaned_headers.extend([str(x) for x in h])
                else:
                    cleaned_headers.append(str(h).strip())
            headers = cleaned_headers if cleaned_headers else ['Data']

            # Ensure rows is a list of lists
            if not isinstance(rows, list):
                rows = []

            # Clean rows - ensure each row is a list
            cleaned_rows = []
            for row in rows:
                if row is None or row == '':
                    continue  # Skip empty rows
                if isinstance(row, (list, tuple)):
                    cleaned_rows.append([str(cell) for cell in row])
                elif isinstance(row, dict):
                    cleaned_rows.append([str(v) for v in row.values()])
                else:
                    cleaned_rows.append([str(row)])  # Single value becomes single-column row
            rows = cleaned_rows

            # ===== LAYER 3: SAFE WRITE WITH VALIDATION =====
            output_dir = Path("workspace/output")
            output_dir.mkdir(parents=True, exist_ok=True)

            filepath = output_dir / filename
            if not filepath.suffix:
                filepath = filepath.with_suffix('.csv')

            # Write with validation
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)

                # Always write headers
                writer.writerow(headers)

                # Write rows with column count validation
                expected_cols = len(headers)
                rows_written = 0
                for row in rows:
                    # Pad or trim row to match header count
                    if len(row) < expected_cols:
                        row = row + [''] * (expected_cols - len(row))
                    elif len(row) > expected_cols:
                        row = row[:expected_cols]

                    writer.writerow(row)
                    rows_written += 1

            # Success message with details
            return {
                "success": True,
                "filepath": str(filepath),
                "rows_written": rows_written,
                "columns": len(headers),
                "headers": headers,
                "message": f"✓ Saved {rows_written} rows × {len(headers)} columns to {filepath.name}"
            }

        except Exception as e:
            # Even if everything fails, create a valid empty CSV
            logger.error(f"Save CSV error: {e}")
            try:
                output_dir = Path("workspace/output")
                output_dir.mkdir(parents=True, exist_ok=True)
                filepath = output_dir / filename
                if not filepath.suffix:
                    filepath = filepath.with_suffix('.csv')

                with open(filepath, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(['Data'])  # Minimal valid CSV

                return {
                    "success": False,
                    "filepath": str(filepath),
                    "rows_written": 0,
                    "error": str(e),
                    "message": f"⚠ Created empty CSV due to error: {e}"
                }
            except Exception as e2:
                return {"error": f"Critical failure: {e2}"}

    async def extract_and_save_csv(self, selector: str, filename: str, column_name: str = "Data") -> Dict[str, Any]:
        """Extract data from selector and immediately save to CSV (simplified workflow)"""
        try:
            # Extract data
            extract_result = await self.extract_data(selector, 'text')

            if 'error' in extract_result:
                return extract_result

            data_items = extract_result.get('data', [])

            if not data_items:
                return {"error": f"No data extracted from selector: {selector}"}

            # Create rows (each item becomes a row with single column)
            rows = [[item] for item in data_items]

            # Save to CSV
            save_result = await self.save_to_csv(filename, [column_name], rows)

            return {
                **save_result,
                "items_extracted": len(data_items),
                "selector": selector
            }

        except Exception as e:
            logger.error(f"Extract and save CSV error: {e}")
            return {"error": str(e)}

    async def take_screenshot(self, name: str = None, full_page: bool = False) -> Dict[str, Any]:
        """Take screenshot for verification"""
        try:
            # Handle string booleans from LLM
            if isinstance(full_page, str):
                full_page = full_page.lower() in ('true', '1', 'yes')

            screenshots_dir = Path("workspace/screenshots")
            screenshots_dir.mkdir(parents=True, exist_ok=True)

            if not name:
                from datetime import datetime
                name = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

            if not name.endswith('.png'):
                name += '.png'

            filepath = screenshots_dir / name

            screenshot_bytes = await self.pw.page.screenshot(
                path=str(filepath),
                full_page=full_page
            )

            return {
                "success": True,
                "filepath": str(filepath),
                "size_bytes": len(screenshot_bytes)
            }

        except Exception as e:
            logger.error(f"Screenshot error: {e}")
            return {"error": str(e)}

    async def scroll_page(self, direction: str = 'down', amount: int = None) -> Dict[str, Any]:
        """
        Scroll page to load dynamic content

        Args:
            direction: 'down', 'up', 'bottom', 'top'
            amount: Pixels to scroll (optional)
        """
        try:
            if direction == 'bottom':
                await self.pw.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            elif direction == 'top':
                await self.pw.page.evaluate('window.scrollTo(0, 0)')
            elif direction == 'down':
                pixels = amount or 500
                await self.pw.page.evaluate(f'window.scrollBy(0, {pixels})')
            elif direction == 'up':
                pixels = amount or 500
                await self.pw.page.evaluate(f'window.scrollBy(0, -{pixels})')

            await asyncio.sleep(0.5)  # Let content load

            return {"success": True, "scrolled": direction}

        except Exception as e:
            logger.error(f"Scroll error: {e}")
            return {"error": str(e)}

    async def press_key(self, key: str) -> Dict[str, Any]:
        """
        Press keyboard key

        Common keys: Enter, Tab, Escape, ArrowDown, ArrowUp, etc.
        """
        try:
            await self.pw.page.keyboard.press(key)
            await asyncio.sleep(0.2)

            return {"success": True, "key": key}

        except Exception as e:
            logger.error(f"Press key error: {e}")
            return {"error": str(e)}

    async def get_cookies(self) -> Dict[str, Any]:
        """Get current cookies (for session persistence)"""
        try:
            cookies = await self.pw.context.cookies()

            return {
                "success": True,
                "cookie_count": len(cookies),
                "cookies": cookies
            }

        except Exception as e:
            logger.error(f"Get cookies error: {e}")
            return {"error": str(e)}

    async def set_cookies(self, cookies: List[Dict]) -> Dict[str, Any]:
        """Set cookies (restore session)"""
        try:
            await self.pw.context.add_cookies(cookies)

            return {
                "success": True,
                "cookies_set": len(cookies)
            }

        except Exception as e:
            logger.error(f"Set cookies error: {e}")
            return {"error": str(e)}

    async def hover(self, selector: str) -> Dict[str, Any]:
        """Hover over element (reveals hidden menus)"""
        try:
            await self.pw.page.hover(selector, timeout=5000)
            await asyncio.sleep(0.3)  # Let hover effects show

            return {"success": True, "selector": selector}

        except Exception as e:
            logger.error(f"Hover error: {e}")
            return {"error": str(e)}

    async def select_dropdown(self, selector: str, value: str) -> Dict[str, Any]:
        """Select option from dropdown"""
        try:
            await self.pw.page.select_option(selector, value=value)

            return {"success": True, "selector": selector, "value": value}

        except Exception as e:
            logger.error(f"Select dropdown error: {e}")
            return {"error": str(e)}

    async def check_checkbox(self, selector: str, checked: bool = True) -> Dict[str, Any]:
        """Check or uncheck checkbox"""
        try:
            if checked:
                await self.pw.page.check(selector)
            else:
                await self.pw.page.uncheck(selector)

            return {"success": True, "selector": selector, "checked": checked}

        except Exception as e:
            logger.error(f"Checkbox error: {e}")
            return {"error": str(e)}

    async def wait_and_click(
        self,
        selector: str,
        timeout: int = 5000,
        visual_description: str = None
    ) -> Dict[str, Any]:
        """
        Wait for element then click (common pattern).

        Falls back to visual detection (screenshot + AI) if selector fails.

        Args:
            selector: CSS selector
            timeout: Wait timeout in ms
            visual_description: Description for visual fallback (e.g., "the blue Submit button")
        """
        try:
            # Handle string timeout from LLM
            if isinstance(timeout, str):
                timeout = int(timeout)
            await self.pw.page.wait_for_selector(selector, state='visible', timeout=timeout)
            await asyncio.sleep(random.uniform(0.1, 0.3))  # Human-like delay
            await self.pw.page.click(selector)

            return {"success": True, "selector": selector, "method": "selector"}

        except Exception as e:
            logger.debug(f"Wait and click selector failed: {e}")
            # Try visual fallback
            return await self._visual_click_fallback(selector, visual_description, str(e))

    async def _visual_click_fallback(
        self,
        selector: str,
        visual_description: str = None,
        original_error: str = None
    ) -> Dict[str, Any]:
        """Use screenshot + vision to find and click element."""
        if not VISUAL_FALLBACK_AVAILABLE or get_visual_fallback is None:
            return {"error": original_error or f"Selector '{selector}' not found"}

        try:
            visual_fb = get_visual_fallback()
            if not visual_fb.has_vision:
                return {"error": original_error or f"Selector '{selector}' not found, no vision model"}

            # Build description if not provided
            description = visual_description
            if not description:
                # Infer from selector
                description = self._selector_to_visual_description(selector)

            logger.info(f"[VISUAL FALLBACK] Looking for: {description}")

            coords = await visual_fb.find_element_visually(self.pw.page, description)

            if coords:
                x, y = coords
                offset_x = random.uniform(-3, 3)
                offset_y = random.uniform(-3, 3)
                await self.pw.page.mouse.click(x + offset_x, y + offset_y)
                await asyncio.sleep(random.uniform(0.1, 0.3))
                logger.info(f"[VISUAL FALLBACK] Clicked at ({x}, {y})")
                return {"success": True, "method": "visual", "coords": coords}

            return {"error": f"Could not find element visually: {description}"}

        except Exception as e:
            logger.error(f"Visual fallback error: {e}")
            return {"error": f"Visual fallback failed: {e}"}

    def _selector_to_visual_description(self, selector: str) -> str:
        """Convert selector to description for vision model."""
        sel_lower = selector.lower()

        if 'submit' in sel_lower:
            return "the Submit button"
        if 'search' in sel_lower:
            return "the search box or search button"
        if 'login' in sel_lower or 'sign' in sel_lower:
            return "the Login or Sign In button"
        if 'compose' in sel_lower:
            return "the Compose button"
        if 'send' in sel_lower:
            return "the Send button"
        if 'next' in sel_lower or 'continue' in sel_lower:
            return "the Next or Continue button"
        if 'add to cart' in sel_lower or 'add-to-cart' in sel_lower:
            return "the Add to Cart button"
        if 'checkout' in sel_lower:
            return "the Checkout button"

        # Try to extract text hints
        import re
        if 'aria-label' in selector:
            match = re.search(r'aria-label[*]?=["\']([^"\']+)', selector)
            if match:
                return f"the element labeled '{match.group(1)}'"

        if ':has-text' in selector:
            match = re.search(r':has-text\(["\']([^"\']+)', selector)
            if match:
                return f"the element with text '{match.group(1)}'"

        if 'button' in sel_lower:
            return "a button"
        if 'input' in sel_lower:
            return "an input field"

        return f"element matching: {selector[:40]}"

    async def get_element_text(self, selector: str = None, **kwargs) -> Dict[str, Any]:
        """Get text content of specific element.

        Args:
            selector: CSS selector to find the element
            **kwargs: Additional params (ignored, but allows LLM flexibility)
        """
        try:
            # Handle case where LLM passes wrong params
            if selector is None:
                # Check if selector was passed as a different param
                selector = kwargs.get('css_selector') or kwargs.get('element') or kwargs.get('target')
                if selector is None:
                    # If just URL was passed, get full page text
                    if 'url' in kwargs:
                        logger.warning(f"get_element_text called with url instead of selector, extracting page text")
                        body = await self.pw.page.query_selector('body')
                        if body:
                            text = await body.inner_text()
                            return {
                                "success": True,
                                "selector": "body",
                                "text": text.strip()[:5000]  # Limit to 5k chars
                            }
                    return {"error": "No selector provided. Use: get_element_text(selector='css_selector')"}

            element = await self.pw.page.query_selector(selector)
            if not element:
                return {"error": f"Element not found: {selector}"}

            text = await element.inner_text()

            return {
                "success": True,
                "selector": selector,
                "text": text.strip()
            }

        except Exception as e:
            logger.error(f"Get element text error: {e}")
            return {"error": str(e)}

    async def detect_contact_form(self) -> Dict[str, Any]:
        """
        Intelligently detect contact form fields on current page
        Returns selectors for name, email, subject, message fields

        Uses multi-strategy approach:
        1. Common Shopify/WooCommerce patterns
        2. Label text matching
        3. Placeholder text matching
        4. Input name/id attributes
        5. Iframe detection
        """
        try:
            form_fields = {
                "name": None,
                "email": None,
                "subject": None,
                "message": None,
                "submit": None
            }

            # Check if form is in iframe
            iframes = await self.pw.page.query_selector_all('iframe')
            in_iframe = len(iframes) > 0

            if in_iframe:
                form_fields["warning"] = f"Found {len(iframes)} iframe(s) - forms may be embedded"

            # Strategy 1: Direct ID/name matching (most reliable)
            id_patterns = {
                "name": ["name", "contact-name", "ContactForm-name", "contact_name", "your-name", "full_name", "fullname"],
                "email": ["email", "contact-email", "ContactForm-email", "contact_email", "your-email", "mail"],
                "subject": ["subject", "contact-subject", "ContactForm-subject", "your-subject"],
                "message": ["message", "comment", "comments", "body", "ContactForm-body", "your-message", "contact-message"]
            }

            for field_type, patterns in id_patterns.items():
                for pattern in patterns:
                    # Try ID selector
                    element = await self.pw.page.query_selector(f'#{pattern}')
                    if element:
                        form_fields[field_type] = f'#{pattern}'
                        break

                    # Try name attribute
                    element = await self.pw.page.query_selector(f'[name="{pattern}"]')
                    if element:
                        form_fields[field_type] = f'[name="{pattern}"]'
                        break

            # Strategy 2: Input type matching
            if not form_fields["email"]:
                email_input = await self.pw.page.query_selector('input[type="email"]')
                if email_input:
                    # Get unique selector
                    email_id = await email_input.get_attribute('id')
                    email_name = await email_input.get_attribute('name')
                    if email_id:
                        form_fields["email"] = f'#{email_id}'
                    elif email_name:
                        form_fields["email"] = f'[name="{email_name}"]'
                    else:
                        form_fields["email"] = 'input[type="email"]'

            # Strategy 3: Textarea for message
            if not form_fields["message"]:
                textareas = await self.pw.page.query_selector_all('textarea')
                if textareas:
                    first_textarea = textareas[0]
                    textarea_id = await first_textarea.get_attribute('id')
                    textarea_name = await first_textarea.get_attribute('name')
                    if textarea_id:
                        form_fields["message"] = f'#{textarea_id}'
                    elif textarea_name:
                        form_fields["message"] = f'[name="{textarea_name}"]'
                    else:
                        form_fields["message"] = 'textarea'

            # Strategy 4: Find submit button
            submit_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Send")',
                'button:has-text("Submit")',
                '[class*="submit"]'
            ]

            for selector in submit_selectors:
                try:
                    submit_btn = await self.pw.page.query_selector(selector)
                    if submit_btn:
                        form_fields["submit"] = selector
                        break
                except Exception as e:
                    logger.debug(f"Submit selector '{selector}' failed: {e}")
                    continue

            # Strategy 5: Get all form inputs for fallback
            all_inputs = await self.pw.page.query_selector_all('input:not([type="hidden"]):not([type="submit"])')
            all_textareas = await self.pw.page.query_selector_all('textarea')

            detected_count = sum(1 for v in form_fields.values() if v and v != "warning")

            return {
                "success": True,
                "form_detected": detected_count >= 2,  # At least 2 fields found
                "fields": form_fields,
                "detected_count": detected_count,
                "total_inputs": len(all_inputs),
                "total_textareas": len(all_textareas),
                "has_iframe": in_iframe,
                "message": f"Detected {detected_count}/5 form fields"
            }

        except Exception as e:
            logger.error(f"Detect contact form error: {e}")
            return {"error": str(e)}

    async def submit_contact_forms(
        self,
        urls: List[str],
        name: str,
        email: str,
        subject: str,
        message: str,
        phone: str = None,
        per_url_timeout: int = 30000,  # 30 seconds per URL
        max_retries: int = 3,  # Maximum retry attempts per form submission
        batch_size: int = 10,  # Write results to disk every N URLs
        overall_timeout: int = 600  # 10 minutes max for entire batch
    ) -> Dict[str, Any]:
        """
        Submit contact forms to multiple URLs in batch.

        This is the main tool for outreach campaigns - given a list of URLs,
        it will visit each one, detect the contact form, fill it out, and submit.
        For sites without forms, it extracts email addresses.

        Args:
            urls: List of contact page URLs to submit to
            name: Your name for the form
            email: Your email address
            subject: Subject line
            message: Message body
            phone: Phone number (optional - uses placeholder if not provided)
            per_url_timeout: Timeout per URL in milliseconds (default: 30000)
            max_retries: Maximum retry attempts per form submission (default: 3)
            batch_size: Write results to disk every N URLs (default: 10)
            overall_timeout: Overall timeout for entire batch in seconds (default: 600)

        Returns:
            Summary with successful submissions, extracted emails, and failures
        """
        start_time = asyncio.get_event_loop().time()

        try:
            # Parse urls if string
            if isinstance(urls, str):
                try:
                    urls = json.loads(urls)
                except (json.JSONDecodeError, ValueError):
                    # Try comma/newline separated
                    urls = [u.strip() for u in urls.replace('\n', ',').split(',') if u.strip()]

            # Initialize results
            results = {
                "submitted": [],
                "extracted_emails": [],
                "failed": [],
                "total": len(urls)
            }

            # Track extracted emails to avoid duplicates
            seen_emails = set()

            # Load existing emails from file to avoid duplicates
            emails_file = Path("workspace/output/extracted_emails.txt")
            if emails_file.exists():
                with open(emails_file, "r") as f:
                    for line in f:
                        email_part = line.split('\t')[0].strip()
                        if email_part:
                            seen_emails.add(email_part)

            async def process_url_with_timeout(url: str, index: int):
                """Process a single URL with timeout and retry logic."""
                logger.info(f"[{index+1}/{len(urls)}] Processing: {url}")

                # Check overall timeout
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > overall_timeout:
                    raise TimeoutError(f"Overall timeout of {overall_timeout}s exceeded")

                # STEALTH: Rate limiting between sites to avoid detection
                from urllib.parse import urlparse
                domain = urlparse(url).netloc
                await rate_limiter.wait_for_slot(domain)

                # STEALTH: Random delay between sites (5-15 seconds like a human browsing)
                if index > 0:
                    delay = random.uniform(5, 15)
                    logger.debug(f"[STEALTH] Waiting {delay:.1f}s before next site")
                    await asyncio.sleep(delay)

                try:
                    # STEALTH: Human-like navigation delay
                    await thinking_delay()

                    # Navigate to the page with timeout
                    await asyncio.wait_for(
                        self.pw.page.goto(url, wait_until='domcontentloaded', timeout=per_url_timeout),
                        timeout=per_url_timeout / 1000
                    )
                    await reading_delay()  # STEALTH: Simulate reading the page

                    # ============ AGGRESSIVE BLOCKER DISMISSAL ============
                    # First pass - dismiss popups that appeared on load
                    await self._dismiss_all_blockers(self.pw.page)
                    await asyncio.sleep(0.5)

                    # Second pass - some popups appear with delay
                    await self._dismiss_all_blockers(self.pw.page)

                    # STEALTH: Human-like scroll to trigger lazy-loaded content
                    try:
                        await human_scroll(self.pw.page, direction="down", amount=random.randint(300, 500))
                        await self._dismiss_all_blockers(self.pw.page)  # Dismiss scroll-triggered popups
                    except Exception as e:
                        logger.debug(f"Human scroll failed: {e}")

                    # Check for iframes and switch if needed
                    form_frame = await self._find_form_frame()

                    # Try to detect and fill form
                    page_context = form_frame if form_frame else self.pw.page

                    # Detect form
                    form_detected = await self._detect_form_fields(page_context)

                    if form_detected and form_detected.get("has_form"):
                        # Scroll form into view
                        try:
                            await page_context.evaluate('''() => {
                                const form = document.querySelector('form');
                                if (form) form.scrollIntoView({behavior: "smooth", block: "center"});
                            }''')
                            await asyncio.sleep(0.5)
                        except Exception as e:
                            logger.debug(f"Form scroll into view failed: {e}")

                        # Dismiss any blockers again before filling
                        await self._dismiss_all_blockers(page_context)

                        # Fill and submit with bounded retry logic
                        submit_success = False
                        for retry_count in range(max_retries):
                            if retry_count > 0:
                                logger.debug(f"  Retry attempt {retry_count}/{max_retries-1}")
                                await self._dismiss_all_blockers(page_context)
                                # Re-detect form fields on retry
                                form_detected = await self._detect_form_fields(page_context)
                                if not form_detected or not form_detected.get("has_form"):
                                    break

                            # Fill the form
                            fill_success = await self._fill_form_fields(
                                page_context,
                                form_detected["fields"],
                                name, email, subject, message, phone
                            )

                            if fill_success:
                                # Dismiss blockers one more time before submit
                                await self._dismiss_all_blockers(page_context)

                                # Try to submit
                                submit_success = await self._submit_form(page_context, form_detected.get("submit_selector"))

                                if not submit_success and retry_count < max_retries - 1:
                                    # Try Enter key method
                                    await self._dismiss_all_blockers(page_context)
                                    await asyncio.sleep(0.5)
                                    submit_success = await self._submit_form(page_context, None)

                                if submit_success:
                                    results["submitted"].append(url)
                                    logger.info(f"  ✓ Form submitted: {url}")
                                    return

                            # If we got here and it's not the last retry, continue to next retry
                            if not submit_success and retry_count < max_retries - 1:
                                await asyncio.sleep(1)  # Small delay before retry
                            else:
                                break

                        # If we exhausted retries without success
                        if not submit_success:
                            results["failed"].append({"url": url, "reason": f"submit failed after {max_retries} retries"})
                    else:
                        # No form found - TRY TO DISCOVER CONTACT PAGE
                        logger.info(f"  🔍 No form on page, searching for contact page...")
                        contact_url = await self._discover_contact_page(url)

                        if contact_url and contact_url != url:
                            logger.info(f"  🔍 Found contact page: {contact_url}")
                            # Navigate to discovered contact page with timeout
                            await asyncio.wait_for(
                                self.pw.page.goto(contact_url, wait_until='domcontentloaded', timeout=per_url_timeout),
                                timeout=per_url_timeout / 1000
                            )
                            await asyncio.sleep(2)

                            # Aggressive blocker dismissal on new page
                            await self._dismiss_all_blockers(self.pw.page)
                            await asyncio.sleep(0.5)
                            await self._dismiss_all_blockers(self.pw.page)

                            # Try again on the new page with bounded retries
                            form_frame2 = await self._find_form_frame()
                            page_context2 = form_frame2 if form_frame2 else self.pw.page
                            form_detected2 = await self._detect_form_fields(page_context2)

                            if form_detected2 and form_detected2.get("has_form"):
                                submit_success2 = False
                                for retry_count in range(max_retries):
                                    if retry_count > 0:
                                        await self._dismiss_all_blockers(page_context2)
                                        form_detected2 = await self._detect_form_fields(page_context2)
                                        if not form_detected2 or not form_detected2.get("has_form"):
                                            break

                                    await self._dismiss_all_blockers(page_context2)
                                    fill_success2 = await self._fill_form_fields(
                                        page_context2,
                                        form_detected2["fields"],
                                        name, email, subject, message, phone
                                    )
                                    if fill_success2:
                                        await self._dismiss_all_blockers(page_context2)
                                        submit_success2 = await self._submit_form(page_context2, form_detected2.get("submit_selector"))
                                        if not submit_success2 and retry_count < max_retries - 1:
                                            await self._dismiss_all_blockers(page_context2)
                                            submit_success2 = await self._submit_form(page_context2, None)
                                        if submit_success2:
                                            results["submitted"].append(contact_url)
                                            logger.info(f"  ✓ Form submitted: {contact_url}")
                                            return
                                    if retry_count < max_retries - 1:
                                        await asyncio.sleep(1)

                            # Still no luck - extract emails
                            emails = await self._extract_emails_from_page()
                            if emails:
                                for email_addr in emails:
                                    if email_addr not in seen_emails:
                                        results["extracted_emails"].append({
                                            "email": email_addr,
                                            "source": contact_url
                                        })
                                        seen_emails.add(email_addr)
                                logger.info(f"  📧 Extracted {len(emails)} email(s): {emails}")
                            else:
                                results["failed"].append({"url": url, "reason": "no form even on contact page"})
                        else:
                            # No contact page found - try to extract emails from current page
                            emails = await self._extract_emails_from_page()
                            if emails:
                                for email_addr in emails:
                                    if email_addr not in seen_emails:
                                        results["extracted_emails"].append({
                                            "email": email_addr,
                                            "source": url
                                        })
                                        seen_emails.add(email_addr)
                                logger.info(f"  📧 Extracted {len(emails)} email(s): {emails}")
                            else:
                                results["failed"].append({"url": url, "reason": "no form or email found"})

                except asyncio.TimeoutError:
                    logger.error(f"  ✗ Timeout processing {url}")
                    results["failed"].append({"url": url, "reason": f"timeout after {per_url_timeout}ms"})
                except Exception as e:
                    logger.error(f"  ✗ Error processing {url}: {e}")
                    results["failed"].append({"url": url, "reason": str(e)})

            # Process URLs with batch writing
            for i, url in enumerate(urls):
                # Check overall timeout
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > overall_timeout:
                    logger.warning(f"Overall timeout of {overall_timeout}s exceeded. Processed {i}/{len(urls)} URLs")
                    break

                await process_url_with_timeout(url, i)

                # Batch write: periodically flush results to disk
                if (i + 1) % batch_size == 0 and results["extracted_emails"]:
                    self._write_emails_batch(results["extracted_emails"], emails_file)
                    results["extracted_emails"] = []  # Clear batch after writing

                # Small delay between requests
                await asyncio.sleep(1)

            # Write any remaining emails
            if results["extracted_emails"]:
                self._write_emails_batch(results["extracted_emails"], emails_file)

            return {
                "success": True,
                "submitted_count": len(results["submitted"]),
                "emails_extracted": len(seen_emails) - (len(seen_emails) - len(results["extracted_emails"]) if results["extracted_emails"] else 0),
                "failed_count": len(results["failed"]),
                "total": results["total"],
                "submitted": results["submitted"],
                "extracted_emails": list(seen_emails),
                "failed": results["failed"],
                "message": f"Submitted {len(results['submitted'])}/{results['total']} forms, extracted {len(seen_emails)} unique emails"
            }

        except Exception as e:
            logger.error(f"Batch form submission error: {e}")
            return {"error": str(e)}

    def _write_emails_batch(self, email_batch: List[Dict[str, str]], emails_file: Path):
        """Write a batch of emails to disk, avoiding duplicates."""
        if not email_batch:
            return

        emails_file.parent.mkdir(parents=True, exist_ok=True)
        with open(emails_file, "a") as f:
            for item in email_batch:
                f.write(f"{item['email']}\t{item['source']}\n")
        logger.info(f"  💾 Wrote {len(email_batch)} emails to {emails_file}")

    async def _discover_contact_page(self, base_url: str) -> str:
        """
        Try to find the contact page on a website.
        Looks for contact links, tries common paths.
        """
        from urllib.parse import urljoin, urlparse

        # Get base domain
        parsed = urlparse(base_url)
        base_domain = f"{parsed.scheme}://{parsed.netloc}"

        # 1. First, look for contact links on the current page
        contact_link_patterns = [
            'a[href*="contact"]',
            'a[href*="Contact"]',
            'a[href*="kontakt"]',
            'a[href*="fale"]',  # Portuguese
            'a[href*="contacto"]',  # Spanish
            'a:has-text("Contact")',
            'a:has-text("Contact Us")',
            'a:has-text("Get in Touch")',
            'a:has-text("Kontakt")',
        ]

        for pattern in contact_link_patterns:
            try:
                link = await self.pw.page.query_selector(pattern)
                if link:
                    href = await link.get_attribute('href')
                    if href:
                        full_url = urljoin(base_domain, href)
                        # Make sure it's same domain
                        if urlparse(full_url).netloc == parsed.netloc:
                            logger.debug(f"  Found contact link: {full_url}")
                            return full_url
            except Exception as e:
                logger.debug(f"Contact link check failed: {e}")
                continue

        # 2. Try common contact page paths
        common_paths = [
            '/contact',
            '/contact-us',
            '/pages/contact',
            '/pages/contact-us',
            '/contacto',
            '/kontakt',
            '/fale-conosco',
            '/get-in-touch',
            '/reach-us',
            '/about/contact',
            '/support/contact',
        ]

        for path in common_paths:
            try:
                test_url = urljoin(base_domain, path)
                # Quick check if page exists (navigate and check for 404)
                response = await self.pw.page.goto(test_url, wait_until='domcontentloaded', timeout=8000)
                if response and response.status == 200:
                    # Check if this page has a form or contact info
                    form = await self.pw.page.query_selector('form')
                    email_link = await self.pw.page.query_selector('a[href^="mailto:"]')
                    if form or email_link:
                        logger.debug(f"  Found contact page at: {test_url}")
                        return test_url
            except Exception as e:
                logger.debug(f"Contact page test failed for {test_url}: {e}")
                continue

        return None

    async def _dismiss_popups(self):
        """Dismiss common popups and overlays"""
        dismiss_selectors = [
            'button[aria-label*="close" i]',
            'button[aria-label*="dismiss" i]',
            '[class*="close-button"]',
            '[class*="popup"] button',
            '[class*="modal"] button[class*="close"]',
            'button:has-text("Accept")',
            'button:has-text("Got it")',
            'button:has-text("No thanks")',
        ]

        for selector in dismiss_selectors:
            try:
                btn = await self.pw.page.query_selector(selector)
                if btn:
                    await btn.click()
                    await asyncio.sleep(0.5)
            except Exception as e:
                logger.debug(f"Dismiss selector '{selector}' failed: {e}")

    async def _find_form_frame(self):
        """Find if contact form is in an iframe"""
        try:
            iframes = await self.pw.page.query_selector_all('iframe')
            for iframe in iframes:
                try:
                    frame = await iframe.content_frame()
                    if frame:
                        # Check if this frame has a form
                        form = await frame.query_selector('form')
                        if form:
                            return frame
                except Exception as e:
                    logger.debug(f"Error checking iframe for form: {e}")
                    continue
        except Exception as e:
            logger.debug(f"Error finding form frame: {e}")
        return None

    async def _detect_form_fields(self, context) -> Dict[str, Any]:
        """Detect form fields in given context (page or frame) - with smart improvisation"""
        fields = {}

        # Extended field patterns - covers more variations
        field_patterns = {
            # Name variations
            "first_name": [
                'input[name*="first" i]', 'input[id*="first" i]', 'input[placeholder*="first" i]',
                '[name="fname"]', '[name="firstName"]', '[name="first_name"]'
            ],
            "last_name": [
                'input[name*="last" i]', 'input[id*="last" i]', 'input[placeholder*="last" i]',
                '[name="lname"]', '[name="lastName"]', '[name="last_name"]', '[name="surname"]'
            ],
            "full_name": [
                'input[name="name" i]', 'input[id="name" i]', 'input[placeholder*="full name" i]',
                'input[placeholder*="your name" i]', '[name="fullName"]', '[name="full_name"]',
                'input[name*="name" i]:not([name*="first"]):not([name*="last"]):not([name*="user"]):not([name*="company"])'
            ],
            "email": [
                'input[type="email"]', 'input[name*="email" i]',
                'input[id*="email" i]', 'input[placeholder*="email" i]'
            ],
            "phone": [
                'input[type="tel"]', 'input[name*="phone" i]', 'input[name*="tel" i]',
                'input[id*="phone" i]', 'input[placeholder*="phone" i]'
            ],
            "company": [
                'input[name*="company" i]', 'input[name*="organization" i]', 'input[name*="business" i]',
                'input[id*="company" i]', 'input[placeholder*="company" i]'
            ],
            "subject": [
                'input[name*="subject" i]', 'input[id*="subject" i]',
                'input[placeholder*="subject" i]', 'input[name*="title" i]'
            ],
            "message": [
                'textarea', 'textarea[name*="message" i]', 'textarea[name*="comment" i]',
                'textarea[id*="message" i]', '[name="message"]', '[name="body"]'
            ],
            "website": [
                'input[name*="website" i]', 'input[name*="url" i]', 'input[type="url"]',
                'input[placeholder*="website" i]'
            ]
        }

        for field_type, selectors in field_patterns.items():
            for selector in selectors:
                try:
                    element = await context.query_selector(selector)
                    if element:
                        # Check if visible
                        is_visible = await element.is_visible()
                        if is_visible:
                            fields[field_type] = selector
                            break
                except Exception as e:
                    logger.debug(f"Field selector check failed for {field_type}: {e}")
                    continue

        # ============ CATCH-ALL: Discover ANY form inputs we missed ============
        # If we only got email but no name/message, try harder
        if 'email' in fields and len(fields) < 3:
            try:
                # Find all visible inputs/textareas inside forms
                all_inputs = await context.evaluate('''() => {
                    const results = [];
                    const forms = document.querySelectorAll('form');
                    forms.forEach(form => {
                        form.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="checkbox"]):not([type="radio"]), textarea').forEach(el => {
                            const rect = el.getBoundingClientRect();
                            if (rect.width > 50 && rect.height > 10) {  // Visible
                                results.push({
                                    tag: el.tagName,
                                    type: el.type || 'text',
                                    name: el.name || '',
                                    id: el.id || '',
                                    placeholder: el.placeholder || '',
                                    selector: el.name ? `[name="${el.name}"]` : (el.id ? `#${el.id}` : null)
                                });
                            }
                        });
                    });
                    return results;
                }''')

                # Map discovered inputs to field types using heuristics
                for inp in all_inputs:
                    if not inp.get('selector'):
                        continue

                    name_lower = (inp.get('name', '') + inp.get('id', '') + inp.get('placeholder', '')).lower()
                    selector = inp['selector']

                    # Already have this selector? Skip
                    if selector in fields.values():
                        continue

                    # Guess field type from name/id/placeholder
                    if inp['tag'] == 'TEXTAREA' and 'message' not in fields:
                        fields['message'] = selector
                    elif any(x in name_lower for x in ['first', 'fname']) and 'first_name' not in fields:
                        fields['first_name'] = selector
                    elif any(x in name_lower for x in ['last', 'lname', 'surname']) and 'last_name' not in fields:
                        fields['last_name'] = selector
                    elif 'name' in name_lower and 'full_name' not in fields and 'first_name' not in fields:
                        fields['full_name'] = selector
                    elif any(x in name_lower for x in ['phone', 'tel', 'mobile']) and 'phone' not in fields:
                        fields['phone'] = selector
                    elif any(x in name_lower for x in ['company', 'org', 'business']) and 'company' not in fields:
                        fields['company'] = selector
                    elif any(x in name_lower for x in ['subject', 'title', 'topic']) and 'subject' not in fields:
                        fields['subject'] = selector

                logger.debug(f"  Catch-all field discovery found {len(fields)} total fields")
            except Exception as e:
                logger.debug(f"  Catch-all field discovery error: {e}")

        # Find submit button - prioritize buttons INSIDE forms, exclude search buttons
        # First try form-contextual selectors (most reliable)
        submit_selectors_priority = [
            'form button[type="submit"]:not([aria-label*="earch"]):not([title*="earch"]):not([class*="search"])',
            'form input[type="submit"]:not([class*="search"])',
            'form button:has-text("Send")', 'form button:has-text("Submit")',
            'form button:has-text("Contact")', 'form button:has-text("Enviar")',  # Portuguese
            'form button:has-text("Get in touch")', 'form button:has-text("Message")',
            '[class*="contact-form"] button[type="submit"]',
            '[class*="wpcf7"] button[type="submit"]',  # WordPress Contact Form 7
            '[id*="contact"] button[type="submit"]',
        ]
        # Fallback to more generic selectors
        submit_selectors_fallback = [
            'button:has-text("Send"):not([aria-label*="earch"])',
            'button:has-text("Submit"):not([aria-label*="earch"])',
            'input[type="submit"][value*="Send"]', 'input[type="submit"][value*="Submit"]',
            '[class*="submit"]:not([class*="search"])',
        ]

        submit_selector = None
        # Try priority selectors first
        for selector in submit_selectors_priority:
            try:
                btn = await context.query_selector(selector)
                if btn:
                    # Extra check: make sure it's visible and not disabled
                    is_visible = await btn.is_visible()
                    is_disabled = await btn.get_attribute('disabled')
                    if is_visible and not is_disabled:
                        submit_selector = selector
                        break
            except Exception as e:
                logger.debug(f"Submit button selector '{selector}' failed: {e}")
                continue

        # If no priority match, try fallbacks
        if not submit_selector:
            for selector in submit_selectors_fallback:
                try:
                    btn = await context.query_selector(selector)
                    if btn:
                        is_visible = await btn.is_visible()
                        is_disabled = await btn.get_attribute('disabled')
                        if is_visible and not is_disabled:
                            submit_selector = selector
                            break
                except Exception as e:
                    logger.debug(f"Fallback submit selector '{selector}' failed: {e}")
                    continue

        # Determine if we have enough to work with
        has_email = 'email' in fields
        has_message = 'message' in fields
        has_any_name = any(k in fields for k in ['first_name', 'last_name', 'full_name'])

        has_form = has_email or (has_message and has_any_name)

        return {
            "has_form": has_form,
            "fields": fields,
            "submit_selector": submit_selector,
            "field_count": len(fields)
        }

    async def _fill_form_fields(self, context, fields: Dict, name: str, email: str, subject: str, message: str, phone: str = None) -> bool:
        """Fill detected form fields with SMART IMPROVISATION - works even with missing data"""
        filled = 0
        import random

        # === IMPROVISE MISSING USER DATA ===

        # If no email provided, generate a plausible one
        if not email:
            random_id = random.randint(1000, 9999)
            email = f"contact{random_id}@inquiry.com"
            logger.info(f"  [IMPROVISE] No email provided, using: {email}")

        # If no name provided, extract from email or use default
        if not name:
            if '@' in email:
                # Try to get name from email (john.smith@... -> John Smith)
                email_prefix = email.split('@')[0]
                name_guess = email_prefix.replace('.', ' ').replace('_', ' ').replace('-', ' ')
                name = ' '.join(word.title() for word in name_guess.split())
                if len(name) < 3 or name.isdigit():
                    name = "Interested Customer"
            else:
                name = "Interested Customer"
            logger.info(f"  [IMPROVISE] No name provided, using: {name}")

        # If no subject provided, generate based on message or default
        if not subject:
            if message:
                # Use first few words of message as subject
                words = message.split()[:5]
                subject = ' '.join(words)
                if len(subject) > 50:
                    subject = subject[:47] + "..."
            else:
                subject = "Question"
            logger.info(f"  [IMPROVISE] No subject provided, using: {subject}")

        # If no message provided, generate a generic one
        if not message:
            message = f"Hi,\n\nI came across your company and would love to learn more about your services. Please get in touch at your earliest convenience.\n\nBest regards,\n{name}"
            logger.info(f"  [IMPROVISE] No message provided, generated generic inquiry")

        # === NOW DERIVE OTHER FIELDS ===

        # Split name into first/last for forms that need it
        name_parts = name.strip().split(' ', 1) if name else ['User', '']
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else first_name  # Use first as last if single name

        # Extract domain from email for company/website improvisation
        email_domain = email.split('@')[1] if email and '@' in email else 'company.com'
        company_name = email_domain.split('.')[0].title() if email_domain else 'My Company'

        # Use provided phone or generate plausible one
        phone_value = phone if phone else f"+1-555-{random.randint(100,999)}-{random.randint(1000,9999)}"

        # Smart mapping: field_type -> what value to use
        field_values = {
            # Name fields - improvise splits
            'first_name': first_name,
            'last_name': last_name,
            'full_name': name,
            'name': name,  # fallback

            # Contact fields
            'email': email,
            'phone': phone_value,

            # Business fields - improvise from email
            'company': company_name,
            'website': f"https://{email_domain}" if email_domain else '',

            # Content fields
            'subject': subject or 'Partnership Inquiry',
            'message': message,
        }

        for field_type, selector in fields.items():
            value = field_values.get(field_type)
            if not value:
                # Last resort: try to improvise based on field name
                if 'name' in field_type.lower():
                    value = name or 'User'
                elif 'phone' in field_type.lower() or 'tel' in field_type.lower():
                    value = phone_value
                elif 'company' in field_type.lower() or 'org' in field_type.lower():
                    value = company_name
                else:
                    continue  # Skip truly unknown fields

            try:
                # Clear and fill
                await context.click(selector)
                await asyncio.sleep(0.2)
                await context.fill(selector, str(value))
                filled += 1
                logger.debug(f"  Filled {field_type}: {value[:30]}...")
            except Exception as e:
                # Try JS injection as fallback
                try:
                    escaped_value = str(value).replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n')
                    await context.evaluate(f'''
                        const el = document.querySelector('{selector}');
                        if (el) {{ el.value = '{escaped_value}'; el.dispatchEvent(new Event('input', {{bubbles: true}})); }}
                    ''')
                    filled += 1
                    logger.debug(f"  Filled {field_type} via JS: {value[:30]}...")
                except Exception:
                    logger.warning(f"  Failed to fill {field_type}")

        return filled >= 2  # Success if at least 2 fields filled

    async def _handle_extras(self, context) -> int:
        """Handle dropdowns, checkboxes, and other required fields that block submission"""
        handled = 0

        # Auto-select first option in required dropdowns
        try:
            selects = await context.query_selector_all('select[required], select:not([class*="hidden"])')
            for select in selects[:5]:  # Limit to 5
                try:
                    # Get first non-empty option
                    options = await select.query_selector_all('option:not([value=""])')
                    if options:
                        value = await options[0].get_attribute('value')
                        if value:
                            await select.select_option(value=value)
                            handled += 1
                except Exception as e:
                    # Individual select may fail - continue with others
                    logger.debug(f"Select option failed: {e}")
        except Exception as e:
            # Dropdown auto-fill is optional - continue without it
            logger.debug(f"Dropdown auto-select failed: {e}")

        # Auto-check required checkboxes (consent, terms, etc.)
        try:
            checkboxes = await context.query_selector_all('input[type="checkbox"][required], input[type="checkbox"][name*="consent"], input[type="checkbox"][name*="agree"], input[type="checkbox"][name*="terms"]')
            for cb in checkboxes[:3]:
                try:
                    is_checked = await cb.is_checked()
                    if not is_checked:
                        await cb.check()
                        handled += 1
                except Exception as e:
                    # Individual checkbox may fail - continue with others
                    logger.debug(f"Checkbox check failed: {e}")
        except Exception as e:
            # Checkbox auto-check is optional - continue without it
            logger.debug(f"Checkbox auto-check failed: {e}")

        # Click any visible "accept cookies" buttons that might be blocking
        try:
            cookie_btns = await context.query_selector_all('button:has-text("Accept"), button:has-text("I agree"), button:has-text("OK"), [class*="cookie"] button')
            for btn in cookie_btns[:2]:
                try:
                    if await btn.is_visible():
                        await btn.click()
                        await asyncio.sleep(0.5)
                        handled += 1
                except Exception as e:
                    # Individual button may fail - continue with others
                    logger.debug(f"Cookie button click failed: {e}")
        except Exception as e:
            # Cookie dismissal is optional - continue without it
            logger.debug(f"Cookie button dismissal failed: {e}")

        return handled

    async def _dismiss_all_blockers(self, context) -> int:
        """
        COMPREHENSIVE blocker dismissal for ecommerce stores.
        Handles: popups, modals, cookie banners, newsletter signups, age verification,
        chat widgets, notification prompts, discount offers, exit intents, etc.
        """
        dismissed = 0

        # ============ STEP 1: ECOMMERCE POPUP PLATFORMS ============
        # Klaviyo (very common on Shopify)
        klaviyo_selectors = [
            '[class*="klaviyo"] button[aria-label*="lose"]',
            '[class*="klaviyo"] button[aria-label*="ismiss"]',
            '[class*="klaviyo"] .needsclick button',
            '.klaviyo-close-form', '.kl-private-reset-css-Xuajs1 button[aria-label]',
            '[data-testid="klaviyo-form-close"]',
        ]

        # Mailchimp popups
        mailchimp_selectors = [
            '[class*="mc-"] button.mc-closeModal',
            '.mc-modal-close', '[class*="mailchimp"] .close',
        ]

        # Privy popups
        privy_selectors = [
            '[class*="privy"] button[aria-label*="lose"]',
            '.privy-popup-close', '[data-privy-close]',
        ]

        # OptinMonster
        optinmonster_selectors = [
            '[class*="optinmonster"] .om-close',
            '.om-close-button', '[data-om-action="close"]',
        ]

        # Justuno
        justuno_selectors = [
            '[class*="justuno"] .ju-close',
            '.ju-popup-close', '[data-ju-close]',
        ]

        # Sumo/SumoMe
        sumo_selectors = [
            '[class*="sumome"] .sumome-close',
            '.sumo-close-button',
        ]

        # Generic ecommerce platforms
        shopify_selectors = [
            '[class*="shopify-"] .close', '[data-shopify-close]',
        ]

        # ============ STEP 2: GENERIC MODALS & DIALOGS ============
        generic_modal_selectors = [
            # Role-based
            '[role="dialog"] button[aria-label*="lose"]',
            '[role="dialog"] button[aria-label*="ismiss"]',
            '[role="dialog"] [class*="close"]',
            '[role="alertdialog"] button[aria-label*="lose"]',
            '[aria-modal="true"] button[aria-label*="lose"]',
            '[aria-modal="true"] [class*="close"]',

            # Class-based modals
            '.modal .close', '.modal-close', '.modal__close',
            '.popup .close', '.popup-close', '.popup__close',
            '.overlay .close', '.overlay-close',
            '.dialog .close', '.dialog-close',

            # Button text patterns
            'button:has-text("Close")', 'button:has-text("X")',
            'button:has-text("No thanks")', 'button:has-text("No, thanks")',
            'button:has-text("Maybe later")', 'button:has-text("Not now")',
            'button:has-text("Skip")', 'button:has-text("Dismiss")',
            'button:has-text("×")',  # Unicode X

            # Icon-based close buttons
            '[class*="close-icon"]', '[class*="icon-close"]',
            '[class*="btn-close"]', '[class*="close-btn"]',
            'button[data-dismiss="modal"]',
            'button[data-testid*="close"]',
            'button[data-action="close"]',
        ]

        # ============ STEP 3: COOKIE CONSENT BANNERS ============
        cookie_selectors = [
            # Common cookie consent platforms
            '#onetrust-accept-btn-handler',  # OneTrust
            '[class*="cookie"] button:has-text("Accept")',
            '[class*="cookie"] button:has-text("OK")',
            '[class*="cookie"] button:has-text("Got it")',
            '[class*="cookie"] button:has-text("I agree")',
            '[class*="gdpr"] button:has-text("Accept")',
            '.cc-btn.cc-dismiss',  # Cookie Consent JS
            '#CybotCookiebotDialogBodyButtonAccept',  # Cookiebot
            '[data-cookie-accept]', '[data-accept-cookies]',
            'button:has-text("Accept all")', 'button:has-text("Accept cookies")',
        ]

        # ============ STEP 4: NEWSLETTER/EMAIL SIGNUPS ============
        newsletter_selectors = [
            '[class*="newsletter"] button:has-text("No")',
            '[class*="newsletter"] button:has-text("Close")',
            '[class*="newsletter"] [class*="close"]',
            '[class*="signup"] button:has-text("No")',
            '[class*="subscribe"] button:has-text("Close")',
            '[class*="email-capture"] .close',
            '[class*="discount"] button:has-text("No")',
            'button:has-text("No, I don\'t want")',
            'button:has-text("Continue without")',
        ]

        # ============ STEP 5: CHAT WIDGETS ============
        chat_selectors = [
            '[class*="intercom"] [aria-label*="lose"]',
            '[class*="drift"] [class*="close"]',
            '[class*="zendesk"] [class*="close"]',
            '[class*="tidio"] [class*="close"]',
            '[class*="livechat"] [class*="close"]',
            '[class*="tawk"] [class*="close"]',
            '[class*="crisp"] [class*="close"]',
            '[class*="freshchat"] [class*="close"]',
            '[class*="chat-widget"] .close',
            'button[aria-label="Minimize"]',
        ]

        # ============ STEP 6: AGE VERIFICATION ============
        age_selectors = [
            '[class*="age-gate"] button:has-text("Yes")',
            '[class*="age-gate"] button:has-text("Enter")',
            '[class*="age-verify"] button:has-text("Yes")',
            'button:has-text("I am over")',
            'button:has-text("I\'m over")',
        ]

        # Combine all selectors
        all_selectors = (
            klaviyo_selectors + mailchimp_selectors + privy_selectors +
            optinmonster_selectors + justuno_selectors + sumo_selectors +
            shopify_selectors + generic_modal_selectors + cookie_selectors +
            newsletter_selectors + chat_selectors + age_selectors
        )

        # Try each selector
        for selector in all_selectors:
            try:
                btns = await context.query_selector_all(selector)
                for btn in btns[:2]:
                    try:
                        if await btn.is_visible():
                            await btn.click(timeout=2000)
                            await asyncio.sleep(0.2)
                            dismissed += 1
                            logger.debug(f"  Dismissed blocker: {selector[:50]}")
                    except Exception as e:
                        # Individual button click may fail - continue trying others
                        logger.debug(f"Blocker button click failed: {e}")
            except Exception as e:
                # Selector query may fail - continue with next selector
                logger.debug(f"Blocker selector '{selector[:30]}' failed: {e}")
                continue

        # ============ STEP 7: ESCAPE KEY (multiple times) ============
        for _ in range(3):
            try:
                await context.keyboard.press('Escape')
                await asyncio.sleep(0.2)
            except Exception as e:
                # Escape key may fail - optional blocker dismissal
                logger.debug(f"Escape key press failed: {e}")

        # ============ STEP 8: CLICK OUTSIDE MODALS ============
        try:
            # Click at (0,0) to dismiss modals that close on outside click
            await context.mouse.click(10, 10)
            await asyncio.sleep(0.2)
        except Exception as e:
            # Outside click may fail - optional blocker dismissal
            logger.debug(f"Outside modal click failed: {e}")

        # ============ STEP 9: JAVASCRIPT REMOVAL OF BLOCKING ELEMENTS ============
        try:
            await context.evaluate('''() => {
                // Remove common overlay/modal classes that block interaction
                const blockers = document.querySelectorAll(
                    '[class*="modal-backdrop"], [class*="overlay"], ' +
                    '[class*="popup-overlay"], [class*="modal-overlay"], ' +
                    '.modal-open, body.modal-open, html.modal-open'
                );
                blockers.forEach(el => {
                    if (el.tagName !== 'FORM') {
                        el.style.display = 'none';
                    }
                });

                // Remove body scroll lock
                document.body.style.overflow = 'auto';
                document.documentElement.style.overflow = 'auto';

                // Remove fixed/sticky elements that might block
                const fixed = document.querySelectorAll('[style*="position: fixed"], [style*="position:fixed"]');
                fixed.forEach(el => {
                    if (el.querySelector('[role="dialog"]') ||
                        el.classList.toString().includes('popup') ||
                        el.classList.toString().includes('modal')) {
                        el.style.display = 'none';
                    }
                });
            }''')
            dismissed += 1
        except Exception as e:
            logger.debug(f"Operation failed: {e}")

        return dismissed

    async def _dismiss_popups(self, context) -> int:
        """Wrapper for backward compatibility"""
        return await self._dismiss_all_blockers(context)

    async def _handle_unexpected_elements(self, context, form_selector: str = None) -> Dict[str, Any]:
        """
        STEP 3: Handle unexpected elements that may appear during form interaction.

        Handles:
        - Loading spinners blocking interaction
        - Sticky headers/footers covering form elements
        - Live chat widgets that expand over forms
        - Toast notifications overlaying content
        - Validation error modals
        - GDPR/privacy consent that blocks interaction
        - Scroll-triggered sticky elements
        - Countdown timers/urgency popups
        - Exit-intent popups triggered during form fill
        - Age verification gates
        - Region/country selectors
        - Currency/language popups
        """
        handled = {
            "loading_spinners": 0,
            "sticky_elements": 0,
            "chat_widgets": 0,
            "toast_notifications": 0,
            "validation_modals": 0,
            "consent_blockers": 0,
            "misc_blockers": 0
        }

        # ============ 1. LOADING SPINNERS & OVERLAYS ============
        spinner_selectors = [
            '[class*="loading"]', '[class*="spinner"]', '[class*="loader"]',
            '[class*="progress"]', '[class*="preload"]', '.sk-circle', '.sk-cube',
            '[class*="ajax-load"]', '[class*="page-load"]', '[class*="wait"]',
            '[data-loading]', '[aria-busy="true"]', '.loading-overlay',
            '[class*="skeleton"]', '[class*="placeholder-"]',
        ]

        for selector in spinner_selectors:
            try:
                elements = await context.query_selector_all(selector)
                for el in elements:
                    try:
                        # Check if it's actually visible and blocking
                        is_visible = await el.is_visible()
                        if is_visible:
                            await el.evaluate('el => el.style.display = "none"')
                            handled["loading_spinners"] += 1
                    except Exception as e:
                        logger.debug(f"Operation failed: {e}")
            except Exception as e:
                logger.debug(f"Selector loop iteration failed: {e}")
                continue

        # Wait for spinners to naturally disappear
        try:
            await context.wait_for_selector('[class*="loading"]', state='hidden', timeout=3000)
        except Exception as e:
            logger.debug(f"Operation failed: {e}")

        # ============ 2. STICKY HEADERS/FOOTERS COVERING FORM ============
        try:
            await context.evaluate('''() => {
                // Find sticky/fixed elements that might cover the form
                const stickies = document.querySelectorAll(
                    'header[style*="fixed"], header[style*="sticky"], ' +
                    '[class*="sticky-header"], [class*="fixed-header"], ' +
                    '[class*="sticky-nav"], [class*="fixed-nav"], ' +
                    'footer[style*="fixed"], [class*="sticky-footer"], ' +
                    '[class*="sticky-bar"], [class*="announcement-bar"]'
                );

                stickies.forEach(el => {
                    // Don't hide the form itself!
                    if (!el.querySelector('form') && !el.matches('form')) {
                        el.style.position = 'relative';
                        el.style.zIndex = '1';
                    }
                });

                // Also handle sticky CTAs/bottom bars
                const bottomBars = document.querySelectorAll(
                    '[class*="bottom-bar"], [class*="cta-bar"], ' +
                    '[class*="floating-cta"], [class*="sticky-cta"]'
                );
                bottomBars.forEach(el => el.style.display = 'none');
            }''')
            handled["sticky_elements"] += 1
        except Exception as e:
            logger.debug(f"Operation failed: {e}")

        # ============ 3. LIVE CHAT WIDGETS THAT EXPAND ============
        chat_selectors = [
            # Intercom
            '#intercom-container', '.intercom-lightweight-app',
            'iframe[name="intercom-frame"]', '[class*="intercom"]',
            # Drift
            '#drift-widget', '#drift-frame-chat', '.drift-frame-controller',
            # Zendesk
            '#launcher', '[class*="zEWidget"]', '#webWidget',
            # Freshchat/Freshdesk
            '#fc_frame', '[class*="freshchat"]', '#freshdesk-widget',
            # Tawk.to
            '.widget-visible', '#tawk-widget', '[class*="tawk"]',
            # Crisp
            '.crisp-client', '#crisp-chatbox', '[class*="crisp"]',
            # HubSpot
            '#hubspot-messages-iframe-container', '[class*="hubspot"]',
            # LiveChat
            '#chat-widget-container', '[class*="livechat"]',
            # Tidio
            '#tidio-chat', '[class*="tidio"]',
            # Generic chat selectors
            '[class*="chat-widget"]', '[class*="chat-button"]',
            '[class*="chat-launcher"]', '[class*="chat-container"]',
            '[class*="support-chat"]', '[class*="live-chat"]',
            '[aria-label*="chat"]', '[title*="chat" i]',
        ]

        for selector in chat_selectors:
            try:
                elements = await context.query_selector_all(selector)
                for el in elements:
                    try:
                        await el.evaluate('el => { el.style.display = "none"; el.style.visibility = "hidden"; }')
                        handled["chat_widgets"] += 1
                    except Exception as e:
                        logger.debug(f"Operation failed: {e}")
            except Exception as e:
                logger.debug(f"Selector loop iteration failed: {e}")
                continue

        # ============ 4. TOAST NOTIFICATIONS ============
        toast_selectors = [
            '[class*="toast"]', '[class*="snackbar"]', '[class*="notification"]',
            '[class*="alert-banner"]', '[class*="flash-message"]',
            '[class*="notice"]', '[role="alert"]', '[role="status"]',
            '[class*="message-bar"]', '[class*="info-bar"]',
        ]

        for selector in toast_selectors:
            try:
                elements = await context.query_selector_all(selector)
                for el in elements:
                    try:
                        is_visible = await el.is_visible()
                        # Don't dismiss if it's inside a form (might be validation feedback)
                        if is_visible:
                            is_in_form = await el.evaluate('el => !!el.closest("form")')
                            if not is_in_form:
                                await el.evaluate('el => el.style.display = "none"')
                                handled["toast_notifications"] += 1
                    except Exception as e:
                        logger.debug(f"Operation failed: {e}")
            except Exception as e:
                logger.debug(f"Selector loop iteration failed: {e}")
                continue

        # ============ 5. VALIDATION ERROR MODALS ============
        validation_modal_selectors = [
            '[class*="error-modal"]', '[class*="validation-error"]',
            '[class*="form-error-popup"]', '[class*="error-dialog"]',
        ]

        for selector in validation_modal_selectors:
            try:
                modals = await context.query_selector_all(selector)
                for modal in modals:
                    try:
                        close_btn = await modal.query_selector('button, [class*="close"]')
                        if close_btn:
                            await close_btn.click()
                            handled["validation_modals"] += 1
                    except Exception as e:
                        logger.debug(f"Operation failed: {e}")
            except Exception as e:
                logger.debug(f"Selector loop iteration failed: {e}")
                continue

        # ============ 6. GDPR/CONSENT BLOCKERS THAT PERSIST ============
        consent_blockers = [
            '[class*="consent-blocker"]', '[class*="privacy-wall"]',
            '[class*="gdpr-overlay"]', '[class*="cookie-wall"]',
            '[class*="tracking-consent"]', '[class*="data-consent"]',
        ]

        for selector in consent_blockers:
            try:
                elements = await context.query_selector_all(selector)
                for el in elements:
                    try:
                        # Try to find and click accept button
                        accept_btn = await el.query_selector(
                            'button:has-text("Accept"), button:has-text("Agree"), ' +
                            'button:has-text("OK"), button:has-text("Got it"), ' +
                            '[class*="accept"], [class*="agree"]'
                        )
                        if accept_btn:
                            await accept_btn.click()
                            handled["consent_blockers"] += 1
                        else:
                            # Just hide it
                            await el.evaluate('el => el.style.display = "none"')
                            handled["consent_blockers"] += 1
                    except Exception as e:
                        logger.debug(f"Operation failed: {e}")
            except Exception as e:
                logger.debug(f"Selector loop iteration failed: {e}")
                continue

        # ============ 7. MISC BLOCKERS (Countdowns, Exit-intent, etc) ============
        misc_selectors = [
            # Countdown/urgency
            '[class*="countdown"]', '[class*="timer"]', '[class*="urgency"]',
            '[class*="limited-time"]', '[class*="hurry"]',
            # Exit intent
            '[class*="exit-intent"]', '[class*="exit-popup"]',
            '[class*="leaving"]', '[class*="dont-go"]',
            # Region/language selectors that block
            '[class*="country-selector"][role="dialog"]',
            '[class*="language-selector"][role="dialog"]',
            '[class*="locale-popup"]', '[class*="geo-popup"]',
            # Age verification that might re-appear
            '[class*="age-gate"]', '[class*="age-verify"]',
            # Welcome mats
            '[class*="welcome-mat"]', '[class*="full-screen-popup"]',
            '[class*="interstitial"]',
        ]

        for selector in misc_selectors:
            try:
                elements = await context.query_selector_all(selector)
                for el in elements:
                    try:
                        is_visible = await el.is_visible()
                        if is_visible:
                            # Try close button first
                            close_btn = await el.query_selector(
                                'button[aria-label*="lose"], [class*="close"], ' +
                                'button:has-text("×"), button:has-text("X"), ' +
                                '[class*="dismiss"]'
                            )
                            if close_btn:
                                await close_btn.click()
                            else:
                                await el.evaluate('el => el.style.display = "none"')
                            handled["misc_blockers"] += 1
                    except Exception as e:
                        logger.debug(f"Operation failed: {e}")
            except Exception as e:
                logger.debug(f"Selector loop iteration failed: {e}")
                continue

        # ============ 8. ENSURE FORM IS SCROLLED INTO VIEW ============
        if form_selector:
            try:
                form = await context.query_selector(form_selector)
                if form:
                    await form.scroll_into_view_if_needed()
                    await asyncio.sleep(0.3)
            except Exception as e:
                logger.debug(f"Operation failed: {e}")
        else:
            # Try to scroll any visible form into view
            try:
                await context.evaluate('''() => {
                    const forms = document.querySelectorAll('form');
                    for (const form of forms) {
                        const rect = form.getBoundingClientRect();
                        if (rect.height > 100) {  // Likely a contact form, not search
                            form.scrollIntoView({ behavior: 'smooth', block: 'center' });
                            break;
                        }
                    }
                }''')
            except Exception as e:
                logger.debug(f"Operation failed: {e}")

        # ============ 9. FINAL JS CLEANUP ============
        try:
            await context.evaluate('''() => {
                // Remove any remaining z-index issues
                const highZ = document.querySelectorAll('[style*="z-index: 9"]');
                highZ.forEach(el => {
                    if (!el.matches('form') && !el.querySelector('form')) {
                        if (el.style.position === 'fixed' || el.style.position === 'absolute') {
                            const rect = el.getBoundingClientRect();
                            // If it covers most of the screen, it's probably a blocker
                            if (rect.width > window.innerWidth * 0.5 && rect.height > window.innerHeight * 0.3) {
                                el.style.display = 'none';
                            }
                        }
                    }
                });

                // Ensure body is scrollable
                document.body.style.overflow = 'auto';
                document.body.style.position = 'static';
                document.documentElement.style.overflow = 'auto';
            }''')
        except Exception as e:
            logger.debug(f"Operation failed: {e}")

        total_handled = sum(handled.values())
        if total_handled > 0:
            logger.debug(f"  Handled {total_handled} unexpected elements: {handled}")

        return handled

    async def _handle_captcha(self, context) -> Dict[str, Any]:
        """
        Detect and solve CAPTCHA on the page.

        Returns:
            {
                "has_captcha": bool,
                "type": str or None,
                "solved": bool,
                "error": str or None
            }
        """
        result = {
            "has_captcha": False,
            "type": None,
            "solved": False,
            "error": None
        }

        if not CAPTCHA_AVAILABLE:
            return result

        try:
            # Create handler for this page (vision-based, no API key needed)
            handler = PageCaptchaHandler(context, LocalCaptchaSolver())

            # Detect CAPTCHA
            detection = await handler.detect_captcha()

            if not detection["has_captcha"]:
                return result

            result["has_captcha"] = True
            result["type"] = detection["type"]

            logger.info(f"  [CAPTCHA] Detected {detection['type']} - attempting vision-based solve...")

            # Try vision-based solving, then manual fallback
            solved = await handler.solve_and_inject(auto_fallback=True)
            result["solved"] = solved

            if solved:
                logger.success(f"  [CAPTCHA] Solved {detection['type']} successfully!")
            else:
                result["error"] = "Failed to solve CAPTCHA - manual intervention needed"
                logger.error(f"  [CAPTCHA] {result['error']}")

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"  [CAPTCHA] Error: {e}")

        return result

    async def _submit_form(self, context, submit_selector: str = None) -> bool:
        """Submit the form with comprehensive pre-submission handling"""
        try:
            # ============ PHASE 0: HANDLE CAPTCHA ============
            captcha_result = await self._handle_captcha(context)
            if captcha_result["has_captcha"] and not captcha_result["solved"]:
                # CAPTCHA present but couldn't solve - still try to submit
                # (some sites have optional CAPTCHAs or they might work anyway)
                logger.warning(f"  [CAPTCHA] Proceeding with submit despite CAPTCHA issue")

            # ============ PHASE 1: CLEAR ALL BLOCKERS ============
            # Dismiss popups/modals
            popups_dismissed = await self._dismiss_popups(context)
            if popups_dismissed:
                logger.debug(f"  Dismissed {popups_dismissed} popup(s)")
                await asyncio.sleep(0.3)

            # Handle unexpected elements (spinners, chat widgets, sticky headers, etc.)
            unexpected = await self._handle_unexpected_elements(context)
            await asyncio.sleep(0.3)

            # Handle dropdowns, checkboxes, cookie banners
            extras = await self._handle_extras(context)
            if extras:
                logger.debug(f"  Handled {extras} extra form elements")

            await asyncio.sleep(0.3)

            # ============ PHASE 2: ENSURE SUBMIT BUTTON IS CLICKABLE ============
            if submit_selector:
                # Scroll the submit button into view first
                try:
                    btn = await context.query_selector(submit_selector)
                    if btn:
                        await btn.scroll_into_view_if_needed()
                        await asyncio.sleep(0.3)

                        # Clear blockers one more time after scrolling
                        await self._dismiss_popups(context)
                        await asyncio.sleep(0.2)
                except Exception as e:
                    logger.debug(f"Operation failed: {e}")

            # ============ PHASE 3: MULTI-STRATEGY SUBMIT ============
            submit_success = False

            if submit_selector:
                # Strategy 1: Normal click
                try:
                    await context.click(submit_selector, timeout=8000)
                    submit_success = True
                    logger.debug("  Submit: Normal click succeeded")
                except Exception as e:
                    logger.debug(f"  Submit: Normal click failed: {e}")

                    # Clear any popup that appeared
                    await self._dismiss_popups(context)
                    await asyncio.sleep(0.3)

                    # Strategy 2: JavaScript click
                    try:
                        btn = await context.query_selector(submit_selector)
                        if btn:
                            await btn.evaluate('el => el.click()')
                            submit_success = True
                            logger.debug("  Submit: JS click succeeded")
                    except Exception as e2:
                        logger.debug(f"  Submit: JS click failed: {e2}")

                        # Strategy 3: Force click with JS
                        try:
                            await context.evaluate(f'''() => {{
                                const btn = document.querySelector('{submit_selector}');
                                if (btn) {{
                                    btn.disabled = false;
                                    btn.click();
                                }}
                            }}''')
                            submit_success = True
                            logger.debug("  Submit: Force JS click succeeded")
                        except Exception as e3:
                            logger.debug(f"  Submit: Force JS click failed: {e3}")

                            # Strategy 4: Submit form directly
                            try:
                                await context.evaluate('''() => {
                                    const forms = document.querySelectorAll('form');
                                    for (const form of forms) {
                                        if (form.querySelector('textarea, input[type="email"]')) {
                                            form.submit();
                                            return true;
                                        }
                                    }
                                    return false;
                                }''')
                                submit_success = True
                                logger.debug("  Submit: Direct form.submit() succeeded")
                            except Exception as e4:
                                logger.debug(f"  Submit: Direct form.submit() failed: {e4}")

                                # Strategy 5: Visual fallback - screenshot + AI click
                                if VISUAL_FALLBACK_AVAILABLE and get_visual_fallback:
                                    try:
                                        visual_fb = get_visual_fallback()
                                        if visual_fb.has_vision:
                                            logger.info("  Submit: Trying visual fallback...")
                                            coords = await visual_fb.find_element_visually(
                                                context,
                                                "the Submit or Send button for the contact form"
                                            )
                                            if coords:
                                                x, y = coords
                                                await context.mouse.click(x + random.uniform(-2, 2), y + random.uniform(-2, 2))
                                                submit_success = True
                                                logger.debug(f"  Submit: Visual click succeeded at ({x}, {y})")
                                    except Exception as e5:
                                        logger.debug(f"  Submit: Visual fallback failed: {e5}")

                                # Strategy 6: Enter key as last resort
                                if not submit_success:
                                    try:
                                        await context.keyboard.press('Enter')
                                        submit_success = True
                                        logger.debug("  Submit: Enter key")
                                    except Exception as e:
                                        logger.debug(f"Operation failed: {e}")
            else:
                # No submit selector, try Enter key and direct submit
                try:
                    await context.keyboard.press('Enter')
                    submit_success = True
                except Exception as e:
                    logger.debug(f"Primary submit method failed: {e}")
                    try:
                        await context.evaluate('''() => {
                            const forms = document.querySelectorAll('form');
                            for (const form of forms) {
                                if (form.querySelector('textarea')) {
                                    form.submit();
                                    return true;
                                }
                            }
                        }''')
                        submit_success = True
                    except Exception as e:
                        logger.debug(f"Operation failed: {e}")

            # ============ PHASE 4: WAIT FOR RESPONSE ============
            await asyncio.sleep(2)

            # Check for success indicators
            try:
                page_text = await context.inner_text('body')
                success_indicators = [
                    'thank you', 'thanks', 'received', 'sent', 'submitted',
                    'success', 'confirmation', "we'll be in touch", 'get back to you'
                ]
                if any(indicator in page_text.lower() for indicator in success_indicators):
                    logger.debug("  Submit: Success indicator found on page")
                    return True
            except Exception as e:
                logger.debug(f"Operation failed: {e}")

            return submit_success

        except Exception as e:
            logger.error(f"Submit error: {e}")
            return False

    async def _extract_emails_from_page(self) -> List[str]:
        """Extract email addresses from current page with smart filtering"""
        import re
        emails = set()

        # Extensive list of garbage email patterns to filter out
        garbage_patterns = [
            # Technical/tracking domains
            'example.com', 'sentry.io', 'sentry-new', 'schema.org', 'wix.com',
            'myshopline.com', 'shopify.com', 'klaviyo.com', 'mailchimp.com',
            'googletagmanager', 'google-analytics', 'facebook.com', 'fb.com',
            'hotjar.com', 'segment.com', 'mixpanel.com', 'amplitude.com',
            'intercom.io', 'zendesk.com', 'crisp.chat', 'drift.com',
            'hubspot.com', 'salesforce.com', 'pardot.com', 'marketo.com',
            # File extensions in email (impossible)
            '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js',
            # Placeholder/test emails
            'test@', 'demo@', 'sample@', 'placeholder@', 'your@', 'email@email',
            'name@domain', 'user@example', 'admin@localhost',
            # Common non-contact addresses
            'noreply@', 'no-reply@', 'donotreply@', 'mailer-daemon@',
            'postmaster@', 'webmaster@', 'hostmaster@', 'abuse@',
            # Encoded/garbage patterns (like sentry DSNs)
            'u002f', 'u002F', '%40', '\\x', '\\u00',
        ]

        # Email domains that are likely real contact addresses (prioritize mailto links)
        priority_emails = []
        regular_emails = []

        try:
            # Get page content
            content = await self.pw.page.content()

            # Find emails in text
            email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
            found = re.findall(email_pattern, content)

            for email in found:
                email_lower = email.lower()

                # Skip if matches any garbage pattern
                if any(x in email_lower for x in garbage_patterns):
                    continue

                # Skip if email local part is too long (likely encoded/garbage)
                local_part = email.split('@')[0]
                if len(local_part) > 40:
                    continue

                # Skip if contains too many numbers (likely auto-generated)
                digit_count = sum(c.isdigit() for c in local_part)
                if digit_count > 10:
                    continue

                regular_emails.append(email)

            # Check mailto links - these are highest priority
            mailto_links = await self.pw.page.query_selector_all('a[href^="mailto:"]')
            for link in mailto_links:
                href = await link.get_attribute('href')
                if href:
                    email = href.replace('mailto:', '').split('?')[0]
                    email_lower = email.lower()

                    # Still filter garbage from mailto
                    if any(x in email_lower for x in garbage_patterns):
                        continue

                    priority_emails.append(email)

            # Combine: priority first, then regular (deduplicated)
            for email in priority_emails:
                emails.add(email)
            for email in regular_emails:
                if email not in emails:
                    emails.add(email)

        except Exception as e:
            logger.error(f"Email extraction error: {e}")

        return list(emails)

    async def detect_captcha(self) -> Dict[str, Any]:
        """
        Detect if CAPTCHA is present on current page

        Checks for:
        - reCAPTCHA v2/v3 (Google)
        - hCaptcha
        - Cloudflare Turnstile
        - Generic CAPTCHA iframes
        """
        try:
            captcha_indicators = []

            # Check for reCAPTCHA
            recaptcha = await self.pw.page.query_selector('[class*="recaptcha"]')
            if recaptcha:
                captcha_indicators.append("reCAPTCHA detected")

            # Check for hCaptcha
            hcaptcha = await self.pw.page.query_selector('[class*="hcaptcha"]')
            if hcaptcha:
                captcha_indicators.append("hCaptcha detected")

            # Check for Cloudflare Turnstile
            turnstile = await self.pw.page.query_selector('[class*="cf-turnstile"]')
            if turnstile:
                captcha_indicators.append("Cloudflare Turnstile detected")

            # Check for generic CAPTCHA iframes
            captcha_iframes = await self.pw.page.query_selector_all('iframe[src*="captcha"]')
            if captcha_iframes:
                captcha_indicators.append(f"{len(captcha_iframes)} CAPTCHA iframe(s) detected")

            # Check for "verify you're human" text
            page_text = await self.pw.page.inner_text('body')
            if any(phrase in page_text.lower() for phrase in ['verify you', 'prove you', 'not a robot', 'security check']):
                captcha_indicators.append("Security verification text detected")

            has_captcha = len(captcha_indicators) > 0

            return {
                "success": True,
                "has_captcha": has_captcha,
                "captcha_types": captcha_indicators,
                "count": len(captcha_indicators)
            }

        except Exception as e:
            logger.error(f"Detect CAPTCHA error: {e}")
            return {"error": str(e)}

    async def fill_contact_form(self, name: str, email: str, subject: str, message: str,
                                auto_detect: bool = True, check_captcha: bool = True,
                                wait_for_user: bool = False) -> Dict[str, Any]:
        """
        Fill contact form with auto-detection and CAPTCHA handling

        Args:
            name: Name to fill
            email: Email to fill
            subject: Subject line
            message: Message body
            auto_detect: Automatically detect form fields (default True)
            check_captcha: Check for CAPTCHA before filling (default True)
            wait_for_user: If CAPTCHA detected, pause and wait for manual solving (default False)
        """
        try:
            fields_filled = []
            errors = []

            # Check for CAPTCHA first
            if check_captcha:
                captcha_check = await self.detect_captcha()
                if captcha_check.get("has_captcha"):
                    logger.warning(f"CAPTCHA detected: {captcha_check['captcha_types']}")

                    # Take screenshot for analysis
                    screenshot_result = await self.take_screenshot(name="captcha_before_solve", full_page=True)

                    if wait_for_user:
                        # SMART 3-STAGE CAPTCHA HANDLING
                        logger.info("Starting smart CAPTCHA handling: LLM attempt → User pause → Continue")

                        # Stage 1: Let LLM try to solve using vision (simple CAPTCHAs)
                        logger.info("Stage 1: LLM attempting to solve CAPTCHA automatically...")

                        # Try common CAPTCHA solving strategies
                        captcha_solved = False
                        try:
                            # Look for checkbox CAPTCHAs (reCAPTCHA v2)
                            checkbox = await self.pw.page.query_selector('iframe[title*="reCAPTCHA"]')
                            if checkbox:
                                logger.info("Attempting reCAPTCHA checkbox click...")
                                try:
                                    # Switch to iframe and click checkbox
                                    frame = await checkbox.content_frame()
                                    if frame:
                                        checkbox_elem = await frame.query_selector('.recaptcha-checkbox-border')
                                        if checkbox_elem:
                                            await checkbox_elem.click()
                                            await asyncio.sleep(2)

                                            # Check if solved
                                            checked = await frame.query_selector('.recaptcha-checkbox-checked')
                                            if checked:
                                                logger.info("✓ LLM solved reCAPTCHA automatically!")
                                                captcha_solved = True
                                except Exception as e:
                                    logger.debug(f"Auto-solve attempt failed: {e}")

                            # Try hCaptcha click
                            if not captcha_solved:
                                hcaptcha_frame = await self.pw.page.query_selector('iframe[title*="hCaptcha"]')
                                if hcaptcha_frame:
                                    logger.info("Attempting hCaptcha click...")
                                    # Similar logic for hCaptcha
                                    pass  # Would need hCaptcha-specific logic

                        except Exception as e:
                            logger.debug(f"LLM CAPTCHA solve attempt error: {e}")

                        # Stage 2: If LLM failed, pause for user
                        if not captcha_solved:
                            logger.warning("Stage 2: LLM could not solve CAPTCHA - requesting user intervention")

                            # Take another screenshot showing current state
                            await self.take_screenshot(name="captcha_needs_user", full_page=True)

                            return {
                                "error": "CAPTCHA_NEEDS_MANUAL_SOLVE",
                                "captcha_types": captcha_check['captcha_types'],
                                "screenshot": screenshot_result.get("filepath"),
                                "llm_attempt": "failed",
                                "message": "⏸ CAPTCHA detected. LLM attempted auto-solve but failed. Please solve manually in the browser window, then type 'continue' to resume.",
                                "action_required": "USER_MANUAL_SOLVE",
                                "instructions": "1. Browser window is open\n2. Solve the CAPTCHA\n3. Type 'continue' to resume form filling"
                            }
                        else:
                            # Stage 3: LLM solved it - continue
                            logger.info("Stage 3: CAPTCHA solved by LLM, continuing with form fill...")
                            await self.take_screenshot(name="captcha_solved_by_llm", full_page=True)
                    else:
                        # Non-interactive mode - log but continue (might work if CAPTCHA is after submit)
                        logger.info("CAPTCHA detected but continuing with form fill (non-interactive mode)...")

            # Detect form first
            if auto_detect:
                detection = await self.detect_contact_form()
                if not detection.get("success") or not detection.get("form_detected"):
                    return {
                        "error": "Could not detect contact form on page",
                        "detection_details": detection
                    }

                form_fields = detection["fields"]
            else:
                return {"error": "Manual form filling not implemented yet - use auto_detect=True"}

            # Fill each field that was detected
            field_data = {
                "name": name,
                "email": email,
                "subject": subject,
                "message": message
            }

            for field_type, selector in form_fields.items():
                if field_type == "submit" or not selector:
                    continue

                value = field_data.get(field_type)
                if not value:
                    continue

                try:
                    # Build visual description based on field type
                    field_descriptions = {
                        "name": "the name input field",
                        "email": "the email input field",
                        "subject": "the subject input field",
                        "message": "the message text area or body field",
                    }
                    visual_desc = field_descriptions.get(field_type, f"the {field_type} input field")

                    # Try to wait for selector, but fall back to visual if needed
                    try:
                        await self.pw.page.wait_for_selector(selector, state='visible', timeout=3000)
                    except Exception as e:
                        logger.debug(f"Operation failed: {e}")  # Will try visual fallback below

                    # Use smart_type for human-like typing - has visual fallback built in
                    if field_type == "message":
                        # Longer message - use smart_type with visual fallback
                        result = await self.smart_type(selector, value, human_like=False, visual_description=visual_desc)
                        if "error" not in result:
                            fields_filled.append(field_type)
                    else:
                        # Short fields - human-like typing with visual fallback
                        result = await self.smart_type(selector, value, human_like=True, visual_description=visual_desc)
                        if "error" not in result:
                            fields_filled.append(field_type)

                    logger.info(f"Filled {field_type} field: {selector}")
                    fields_filled.append(field_type)

                except Exception as field_error:
                    error_msg = f"{field_type}: {str(field_error)}"
                    errors.append(error_msg)
                    logger.warning(f"Failed to fill {field_type}: {field_error}")

            return {
                "success": len(fields_filled) >= 2,  # Success if at least 2 fields filled
                "fields_filled": fields_filled,
                "fields_count": len(fields_filled),
                "errors": errors,
                "submit_button": form_fields.get("submit"),
                "message": f"Filled {len(fields_filled)} form fields successfully"
            }

        except Exception as e:
            logger.error(f"Fill contact form error: {e}")
            return {"error": str(e)}

    def get_tools_definition(self) -> List[Dict[str, Any]]:
        """Return tool definitions for MCP registration"""
        return [
            {
                "name": "smart_type",
                "description": "Type text with human-like delays to avoid bot detection",
                "params": {
                    "selector": "string",
                    "text": "string",
                    "human_like": "boolean (optional, default true)"
                }
            },
            {
                "name": "smart_wait",
                "description": "Wait for various conditions: element, navigation, network, or time",
                "params": {
                    "condition": "string (element|navigation|network|time)",
                    "value": "string (optional)",
                    "timeout": "number (optional, default 5000ms)"
                }
            },
            {
                "name": "extract_data",
                "description": "Extract data from page elements by selector and attribute",
                "params": {
                    "selector": "string (CSS selector)",
                    "attribute": "string (text|href|src|value|data-*, default 'text')"
                }
            },
            {
                "name": "extract_table",
                "description": "Extract table data as CSV-ready format",
                "params": {
                    "selector": "string (optional, default 'table')"
                }
            },
            {
                "name": "save_to_csv",
                "description": "Save extracted data to CSV file",
                "params": {
                    "filename": "string",
                    "headers": "list of strings",
                    "rows": "list of lists"
                }
            },
            {
                "name": "take_screenshot",
                "description": "Take screenshot for visual verification",
                "params": {
                    "name": "string (optional)",
                    "full_page": "boolean (optional, default false)"
                }
            },
            {
                "name": "scroll_page",
                "description": "Scroll page to load dynamic content",
                "params": {
                    "direction": "string (down|up|bottom|top, default 'down')",
                    "amount": "number (optional, pixels to scroll)"
                }
            },
            {
                "name": "press_key",
                "description": "Press keyboard key (Enter, Tab, Escape, etc.)",
                "params": {
                    "key": "string"
                }
            },
            {
                "name": "hover",
                "description": "Hover over element to reveal hidden menus/content",
                "params": {
                    "selector": "string"
                }
            },
            {
                "name": "select_dropdown",
                "description": "Select option from dropdown menu",
                "params": {
                    "selector": "string",
                    "value": "string"
                }
            },
            {
                "name": "check_checkbox",
                "description": "Check or uncheck checkbox",
                "params": {
                    "selector": "string",
                    "checked": "boolean (optional, default true)"
                }
            },
            {
                "name": "wait_and_click",
                "description": "Wait for element to appear then click it",
                "params": {
                    "selector": "string",
                    "timeout": "number (optional, default 5000ms)"
                }
            },
            {
                "name": "get_element_text",
                "description": "Get text content of specific element",
                "params": {
                    "selector": "string"
                }
            },
            {
                "name": "detect_contact_form",
                "description": "Intelligently detect contact form fields on current page using multi-strategy approach (Shopify, WooCommerce, generic forms)",
                "params": {}
            },
            {
                "name": "detect_captcha",
                "description": "Detect if CAPTCHA is present on page (reCAPTCHA, hCaptcha, Cloudflare Turnstile, etc.)",
                "params": {}
            },
            {
                "name": "fill_contact_form",
                "description": "Auto-detect and fill contact form with provided data. Includes CAPTCHA detection and optional user intervention mode",
                "params": {
                    "name": "string",
                    "email": "string",
                    "subject": "string",
                    "message": "string",
                    "auto_detect": "boolean (optional, default true)",
                    "check_captcha": "boolean (optional, default true)",
                    "wait_for_user": "boolean (optional, default false - if true, pauses on CAPTCHA for manual solving)"
                }
            },
            {
                "name": "submit_contact_forms",
                "description": "Submit contact forms to multiple URLs in batch. For outreach campaigns - visits each URL, detects form, fills it, submits. Extracts emails from sites without forms. Use this when user wants to send messages to multiple contact pages.",
                "params": {
                    "urls": "list of contact page URLs (or comma/newline separated string)",
                    "name": "string - your name",
                    "email": "string - your email",
                    "subject": "string - message subject",
                    "message": "string - message body",
                    "phone": "string (optional) - phone number"
                }
            },
            {
                "name": "get_cookies",
                "description": "Get current browser cookies for session persistence",
                "params": {}
            },
            {
                "name": "set_cookies",
                "description": "Set browser cookies to restore session",
                "params": {
                    "cookies": "list of cookie objects"
                }
            }
        ]
