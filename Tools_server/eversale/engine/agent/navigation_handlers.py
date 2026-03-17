"""
Navigation and Form Handlers for Eversale Agent.

Extracted from brain_enhanced_v2.py to modularize navigation, form filling,
and page interaction logic.
"""

import asyncio
import random
import re
from typing import Dict, List, Any, Optional
from loguru import logger


# ============================================================================
# Smart Scrolling and Focus Management Functions
# ============================================================================

async def get_fixed_header_height(page) -> int:
    """
    Detect fixed/sticky headers and return their height.

    Args:
        page: Playwright page object

    Returns:
        Height of fixed/sticky headers in pixels
    """
    try:
        height = await page.evaluate('''
            () => {
                const headers = document.querySelectorAll(
                    'header, [class*="header"], nav, [class*="navbar"], [class*="top-bar"]'
                );
                let maxHeight = 0;
                for (const h of headers) {
                    const style = getComputedStyle(h);
                    if (style.position === 'fixed' || style.position === 'sticky') {
                        const rect = h.getBoundingClientRect();
                        if (rect.top === 0) {  // Only count headers at top
                            maxHeight = Math.max(maxHeight, h.offsetHeight);
                        }
                    }
                }
                return maxHeight;
            }
        ''')
        return height or 0
    except Exception as e:
        logger.debug(f"Failed to detect fixed header: {e}")
        return 0


async def is_element_in_viewport(page, selector: str) -> Dict:
    """
    Check if element is visible in viewport.

    Args:
        page: Playwright page object
        selector: CSS selector for element

    Returns:
        Dict with visible, rect, viewport, reason fields
    """
    try:
        result = await page.evaluate('''
            (selector) => {
                const element = document.querySelector(selector);
                if (!element) return { visible: false, reason: 'not_found' };

                const rect = element.getBoundingClientRect();
                const viewHeight = window.innerHeight;
                const viewWidth = window.innerWidth;

                const inViewport = (
                    rect.top >= 0 &&
                    rect.left >= 0 &&
                    rect.bottom <= viewHeight &&
                    rect.right <= viewWidth
                );

                const partiallyVisible = (
                    rect.top < viewHeight &&
                    rect.bottom > 0 &&
                    rect.left < viewWidth &&
                    rect.right > 0
                );

                return {
                    visible: inViewport,
                    partiallyVisible: partiallyVisible,
                    rect: {
                        top: rect.top,
                        left: rect.left,
                        bottom: rect.bottom,
                        right: rect.right,
                        width: rect.width,
                        height: rect.height
                    },
                    viewport: { width: viewWidth, height: viewHeight },
                    reason: inViewport ? 'ok' : (partiallyVisible ? 'partially_visible' : 'out_of_viewport')
                };
            }
        ''', selector)
        return result
    except Exception as e:
        logger.debug(f"Failed to check viewport visibility: {e}")
        return {"visible": False, "reason": f"error: {str(e)}"}


async def smart_scroll_to_element(
    page,
    selector: str,
    padding: int = 100,
    behavior: str = "smooth"
) -> bool:
    """
    Scroll element into view with intelligent positioning.

    Args:
        page: Playwright page object
        selector: CSS selector for element to scroll to
        padding: Extra padding from viewport edges (default 100px)
        behavior: 'smooth' or 'auto' scroll behavior

    Returns:
        True if element is now visible, False otherwise
    """
    try:
        # First check if element exists
        element = await page.query_selector(selector)
        if not element:
            logger.warning(f"Element not found for scrolling: {selector}")
            return False

        # Get bounding box
        box = await element.bounding_box()
        if not box:
            logger.warning(f"Element has no bounding box: {selector}")
            return False

        # Detect fixed headers
        fixed_header_height = await get_fixed_header_height(page)

        # Calculate optimal scroll position
        # Center element vertically, accounting for fixed header and padding
        await page.evaluate('''
            ({selector, padding, fixedHeaderHeight, behavior}) => {
                const element = document.querySelector(selector);
                if (!element) return;

                const rect = element.getBoundingClientRect();
                const viewportHeight = window.innerHeight;

                // Calculate scroll amount to center element
                // Account for fixed header at top
                const elementCenter = rect.top + window.scrollY;
                const targetScrollY = elementCenter - (viewportHeight / 2) - fixedHeaderHeight;

                window.scrollTo({
                    top: Math.max(0, targetScrollY),
                    behavior: behavior
                });
            }
        ''', {
            "selector": selector,
            "padding": padding,
            "fixedHeaderHeight": fixed_header_height,
            "behavior": behavior
        })

        # Wait for scroll to complete
        await asyncio.sleep(0.5 if behavior == "smooth" else 0.2)

        # Verify element is now visible
        visibility = await is_element_in_viewport(page, selector)

        if visibility.get("visible") or visibility.get("partiallyVisible"):
            logger.debug(f"Element scrolled into view: {selector}")
            return True
        else:
            logger.warning(f"Element still not visible after scroll: {selector}")
            return False

    except Exception as e:
        logger.warning(f"Smart scroll failed: {e}")
        return False


async def focus_element_humanlike(page, selector: str) -> bool:
    """
    Focus element like a human would - hover, pause, then focus.

    Args:
        page: Playwright page object
        selector: CSS selector for element to focus

    Returns:
        True if focus succeeded, False otherwise
    """
    try:
        element = await page.query_selector(selector)
        if not element:
            logger.warning(f"Element not found for focusing: {selector}")
            return False

        box = await element.bounding_box()
        if not box:
            logger.warning(f"Element has no bounding box: {selector}")
            return False

        # 1. Move mouse near element (not directly to it)
        near_x = box['x'] + box['width'] / 2 + random.randint(-20, 20)
        near_y = box['y'] + box['height'] / 2 + random.randint(-20, 20)
        await page.mouse.move(near_x, near_y)
        await asyncio.sleep(random.uniform(0.05, 0.15))

        # 2. Move to element center
        center_x = box['x'] + box['width'] / 2
        center_y = box['y'] + box['height'] / 2
        await page.mouse.move(center_x, center_y)
        await asyncio.sleep(random.uniform(0.05, 0.1))

        # 3. Hover over element
        await element.hover()
        await asyncio.sleep(random.uniform(0.05, 0.1))

        # 4. Focus the element
        await element.focus()

        logger.debug(f"Element focused: {selector}")
        return True

    except Exception as e:
        logger.warning(f"Human-like focus failed: {e}")
        return False


async def scroll_to_trigger_lazy_load(page, target_selector: str, max_scrolls: int = 10) -> bool:
    """
    Scroll down to trigger lazy loading of target element.

    Args:
        page: Playwright page object
        target_selector: CSS selector for element to find
        max_scrolls: Maximum number of scroll attempts (default 10)

    Returns:
        True if element found, False otherwise
    """
    try:
        for i in range(max_scrolls):
            # Check if element exists
            element = await page.query_selector(target_selector)
            if element:
                logger.debug(f"Lazy-loaded element found after {i} scrolls: {target_selector}")
                return True

            # Get current scroll position
            prev_scroll = await page.evaluate('window.scrollY')

            # Scroll down one viewport (80% to create overlap)
            await page.evaluate('window.scrollBy(0, window.innerHeight * 0.8)')
            await asyncio.sleep(0.5)  # Wait for lazy load to trigger

            # Check if we've reached the bottom
            new_scroll = await page.evaluate('window.scrollY')
            if new_scroll == prev_scroll:
                logger.debug("Reached bottom of page without finding element")
                break

        logger.warning(f"Element not found after {max_scrolls} scrolls: {target_selector}")
        return False

    except Exception as e:
        logger.warning(f"Lazy load scroll failed: {e}")
        return False


async def scroll_until_element_found(
    page,
    selector: str,
    max_scrolls: int = 20,
    scroll_pause: float = 0.5
) -> bool:
    """
    Keep scrolling until element found or max reached (infinite scroll handling).

    Args:
        page: Playwright page object
        selector: CSS selector for element to find
        max_scrolls: Maximum number of scroll attempts (default 20)
        scroll_pause: Pause between scrolls in seconds (default 0.5)

    Returns:
        True if element found, False otherwise
    """
    try:
        for i in range(max_scrolls):
            # Check if element exists
            element = await page.query_selector(selector)
            if element:
                logger.debug(f"Element found after {i} scrolls: {selector}")
                return True

            # Get current scroll position and page height
            scroll_info = await page.evaluate('''
                () => ({
                    scrollY: window.scrollY,
                    scrollHeight: document.documentElement.scrollHeight,
                    viewportHeight: window.innerHeight
                })
            ''')

            prev_scroll = scroll_info['scrollY']

            # Scroll down one viewport
            await page.evaluate('window.scrollBy(0, window.innerHeight * 0.8)')
            await asyncio.sleep(scroll_pause)

            # Check if we've reached the bottom
            new_scroll_info = await page.evaluate('''
                () => ({
                    scrollY: window.scrollY,
                    scrollHeight: document.documentElement.scrollHeight
                })
            ''')

            # If scroll position hasn't changed and we're near bottom, stop
            if (new_scroll_info['scrollY'] == prev_scroll and
                new_scroll_info['scrollY'] + scroll_info['viewportHeight'] >= scroll_info['scrollHeight'] - 100):
                logger.debug("Reached bottom of page without finding element")
                break

        logger.warning(f"Element not found after {max_scrolls} scrolls: {selector}")
        return False

    except Exception as e:
        logger.warning(f"Infinite scroll search failed: {e}")
        return False


async def scroll_element_into_view_if_needed(page, selector: str) -> bool:
    """
    Check if element is in viewport, scroll if needed.
    Convenience function that combines checking and scrolling.

    Args:
        page: Playwright page object
        selector: CSS selector for element

    Returns:
        True if element is now visible, False otherwise
    """
    try:
        # Check current visibility
        visibility = await is_element_in_viewport(page, selector)

        if visibility.get("visible"):
            logger.debug(f"Element already in viewport: {selector}")
            return True

        # Not visible, try scrolling
        logger.debug(f"Element not visible, scrolling into view: {selector}")
        return await smart_scroll_to_element(page, selector)

    except Exception as e:
        logger.warning(f"Scroll if needed failed: {e}")
        return False


async def prepare_element_for_interaction(page, selector: str) -> bool:
    """
    Prepare element for interaction: scroll into view and focus.
    This is the main function to call before clicking/filling elements.

    Args:
        page: Playwright page object
        selector: CSS selector for element

    Returns:
        True if element is ready for interaction, False otherwise
    """
    try:
        # Step 1: Ensure element exists
        element = await page.query_selector(selector)
        if not element:
            logger.warning(f"Element not found: {selector}")
            return False

        # Step 2: Scroll into view if needed
        scrolled = await scroll_element_into_view_if_needed(page, selector)
        if not scrolled:
            logger.warning(f"Could not scroll element into view: {selector}")
            # Continue anyway - maybe it will still work

        # Step 3: Focus element with human-like behavior
        focused = await focus_element_humanlike(page, selector)
        if not focused:
            logger.warning(f"Could not focus element: {selector}")
            # Continue anyway - element might still be clickable

        # Step 4: Final visibility check
        visibility = await is_element_in_viewport(page, selector)
        if visibility.get("visible") or visibility.get("partiallyVisible"):
            logger.debug(f"Element ready for interaction: {selector}")
            return True
        else:
            logger.warning(f"Element still not visible after preparation: {selector}")
            return False

    except Exception as e:
        logger.warning(f"Element preparation failed: {e}")
        return False


class NavigationHandlersMixin:
    """
    Mixin class providing navigation and form handling capabilities.

    Requires the parent class to have:
    - _call_direct_tool(name, args) method
    - _emit_explainable_summary(summary, issues) method
    - browser property
    """

    async def _try_click_through(self, prompt: str) -> Optional[str]:
        """
        Fast path for "navigate to X and click Y" patterns.
        Handles common click-through navigation requests.
        """
        lower = prompt.lower()
        url = None
        click_target = None

        # Pattern: "navigate to X and click Y"
        match = re.search(
            r"navigate\s+to\s+(\S+\.(?:com|org|net|io|gov|edu)[^\s,]*)[,\s]+(?:and\s+)?click\s+(?:on\s+)?(?:the\s+)?['\"]?([^'\",.]+)['\"]?",
            lower
        )
        if match:
            url = match.group(1)
            click_target = match.group(2).strip()

        # Check for pagination pattern: "visit X, go to page N"
        if not url:
            page_match = re.search(
                r"(?:visit|navigate\s+to)\s+(\S+\.(?:com|org|net|io|gov|edu)[^\s,]*)[,\s]+(?:and\s+)?(?:go\s+to\s+)?page\s+(\d+)",
                lower
            )
            if page_match:
                url = page_match.group(1)
                page_num = page_match.group(2)
                logger.info(f"Pagination detected: {url} -> page {page_num}")
                return await self._handle_pagination(url, page_num, prompt)

        # Check for search pattern: "navigate to X, search for Y"
        if not url:
            search_match = re.search(
                r"navigate\s+to\s+(\S+\.(?:com|org|net|io|gov|edu)[^\s,]*)[,\s]+(?:and\s+)?search\s+(?:for\s+)?['\"]?([^'\"]+)['\"]?",
                lower
            )
            if search_match:
                url = search_match.group(1)
                search_query = search_match.group(2).strip()
                # Remove trailing phrases like "and tell me..."
                search_query = re.sub(r'\s+and\s+.*$', '', search_query, flags=re.IGNORECASE)
                logger.info(f"Search detected: {url} -> search '{search_query}'")
                return await self._handle_site_search(url, search_query, prompt)

        # Check for form fill pattern: "go to X, fill Y with Z"
        # Note: Skip patterns like "fill the form" or "fill out the form" - those should go to LLM
        if not url:
            fill_patterns = [
                r"go\s+to\s+(\S+\.(?:com|org|net|io|gov|edu)[^\s,]*)[,\s]+(?:and\s+)?fill\s+(?:in\s+)?(?:the\s+)?([^'\"]+?)\s+(?:field\s+)?(?:with|as)\s+['\"]?([^'\"]+)['\"]?",
                r"navigate\s+to\s+(\S+\.(?:com|org|net|io|gov|edu)[^\s,]*)[,\s]+(?:and\s+)?fill\s+(?:in\s+)?(?:the\s+)?([^'\"]+?)\s+(?:field\s+)?(?:with|as)\s+['\"]?([^'\"]+)['\"]?",
            ]
            for pattern in fill_patterns:
                match = re.search(pattern, lower, re.IGNORECASE)
                if match:
                    url = match.group(1)
                    field_name = match.group(2).strip()
                    field_value = match.group(3).strip()
                    # Skip generic "form" or "out" field names - these are from "fill the form" / "fill out"
                    if field_name.lower() in ['form', 'out', 'the form', 'out the form']:
                        logger.debug(f"Skipping generic form fill pattern: '{field_name}'")
                        continue
                    logger.info(f"Form fill detected: {url} -> fill '{field_name}' with '{field_value}'")
                    return await self._handle_form_fill(url, field_name, field_value, prompt)

        if not url or not click_target:
            return None

        # Ensure URL has protocol
        if not url.startswith('http'):
            url = 'https://' + url

        logger.info(f"Click-through detected: {url} -> click '{click_target}'")

        try:
            # Step 1: Navigate to the URL
            nav_result = await self._call_direct_tool("playwright_navigate", {"url": url})
            if not nav_result or nav_result.get("error"):
                return f"Failed to navigate to {url}: {nav_result.get('error', 'Unknown error')}"

            # Step 2: Click the target element
            click_target_clean = click_target.strip().rstrip('.')

            # Try multiple selector strategies
            selectors_to_try = [
                f"a:has-text('{click_target_clean}')",
                f"button:has-text('{click_target_clean}')",
                f"a[href*='{click_target_clean.lower().replace(' ', '-')}']",
                f"a[href*='{click_target_clean.lower().replace(' ', '_')}']",
                f"a[href*='{click_target_clean.lower()}']",
                f"text={click_target_clean}",
            ]

            click_success = False
            for selector in selectors_to_try:
                try:
                    click_result = await self._call_direct_tool("playwright_click", {"selector": selector})
                    if click_result and click_result.get("success"):
                        click_success = True
                        logger.info(f"Click succeeded with selector: {selector}")
                        break
                except Exception:
                    continue

            if not click_success:
                # Fallback: try clicking by visible text using JavaScript
                js_click = f"""
                    (() => {{
                        const links = document.querySelectorAll('a, button');
                        for (const el of links) {{
                            if (el.textContent.toLowerCase().includes('{click_target_clean.lower()}')) {{
                                el.click();
                                return true;
                            }}
                        }}
                        return false;
                    }})()
                """
                js_result = await self._call_direct_tool("playwright_evaluate", {"script": js_click})
                if js_result and js_result.get("result"):
                    click_success = True

            # Step 3: Wait and get the new page content
            await asyncio.sleep(1)

            # Step 4: Get snapshot of the new page
            snapshot = await self._call_direct_tool("playwright_snapshot", {})

            if snapshot:
                title = snapshot.get("title", "")
                current_url = snapshot.get("url", "")
                summary_text = snapshot.get("summary", "")

                # Format the response
                result = f"**Navigated to {url}**\n"
                if click_success:
                    result += f"**Clicked on '{click_target}'**\n\n"
                else:
                    result += f"**Could not find '{click_target}' to click**\n\n"

                result += f"**Current Page: {title}**\n"
                result += f"URL: {current_url}\n\n"

                if summary_text:
                    result += f"Page Content:\n{summary_text[:500]}"

                self._emit_explainable_summary(result, [])
                return result

        except Exception as e:
            logger.warning(f"Click-through handler failed: {e}")
            return None

        return None

    async def _handle_pagination(self, url: str, page_num: str, original_prompt: str) -> Optional[str]:
        """
        Handle pagination tasks: navigate to URL with page number.
        """
        # Ensure URL has protocol
        if not url.startswith('http'):
            url = 'https://' + url

        try:
            # Build paginated URL - try common patterns
            paginated_urls = [
                f"{url}/page/{page_num}",
                f"{url}?page={page_num}",
                f"{url}/page/{page_num}/",
                url.rstrip('/') + f"/page/{page_num}",
            ]

            # Navigate to first working URL
            nav_result = None
            used_url = None
            for purl in paginated_urls:
                nav_result = await self._call_direct_tool("playwright_navigate", {"url": purl})
                if nav_result and nav_result.get("success"):
                    used_url = purl
                    break

            if not nav_result or not used_url:
                return f"Failed to navigate to page {page_num} of {url}"

            # Wait and extract content
            await asyncio.sleep(1)

            # Try to extract main content
            snapshot = await self._call_direct_tool("playwright_snapshot", {})

            result = f"**Navigated to page {page_num} of {url}**\n"
            result += f"URL: {used_url}\n\n"

            if snapshot:
                result += f"**Page: {snapshot.get('title', 'Unknown')}**\n"
                summary = snapshot.get('summary', '')[:400]
                if summary:
                    result += f"\n{summary}"

            self._emit_explainable_summary(result, [])
            return result

        except Exception as e:
            logger.warning(f"Pagination handler failed: {e}")
            return None

    async def _handle_site_search(self, url: str, search_query: str, original_prompt: str) -> Optional[str]:
        """
        Handle site search tasks: navigate to URL, search for query, extract results.
        Works with Amazon, eBay, and other e-commerce/search sites.
        """
        # Ensure URL has protocol
        if not url.startswith('http'):
            url = 'https://' + url

        try:
            # Step 1: Navigate to the URL
            nav_result = await self._call_direct_tool("playwright_navigate", {"url": url})
            if not nav_result or nav_result.get("error"):
                return f"Failed to navigate to {url}: {nav_result.get('error', 'Unknown error')}"

            # Step 2: Use smart_search to find and fill search form
            search_result = await self._call_direct_tool("playwright_smart_search", {"query": search_query})

            if search_result and search_result.get("error"):
                # Fallback: try direct form fill
                await self._call_direct_tool("playwright_fill", {
                    "selector": "input[type='search'], input[name='q'], input[name='field-keywords']",
                    "value": search_query
                })
                await self._call_direct_tool("playwright_evaluate", {
                    "script": "document.querySelector('form').submit()"
                })
                await asyncio.sleep(2)

            # Step 3: Wait for results and extract data
            await asyncio.sleep(1)

            # Step 4: Extract product/search results based on site
            site_lower = url.lower()
            extraction_result = None

            if 'amazon' in site_lower:
                extraction_result = await self._call_direct_tool("playwright_extract_structured", {
                    "item_selector": "[data-component-type='s-search-result']",
                    "field_selectors": {
                        "title": "h2 span",
                        "price": ".a-price .a-offscreen",
                        "rating": ".a-icon-alt"
                    },
                    "limit": 10
                })
            elif 'ebay' in site_lower:
                extraction_result = await self._call_direct_tool("playwright_extract_structured", {
                    "item_selector": ".s-item",
                    "field_selectors": {
                        "title": ".s-item__title",
                        "price": ".s-item__price"
                    },
                    "limit": 10
                })
            else:
                # Generic extraction - try to find product-like items
                extraction_result = await self._call_direct_tool("playwright_llm_extract", {
                    "prompt": f"Extract the top products/results for '{search_query}' with titles and prices"
                })

            # Format response
            result = f"**Searched {url} for '{search_query}'**\n\n"

            if extraction_result and extraction_result.get("data"):
                data = extraction_result.get("data", [])
                if isinstance(data, list):
                    result += f"**Found {len(data)} results:**\n"
                    for i, item in enumerate(data[:5], 1):
                        if isinstance(item, dict):
                            title = item.get("title", "Unknown")
                            price = item.get("price", "N/A")
                            result += f"{i}. {title} - {price}\n"
                        else:
                            result += f"{i}. {item}\n"
                else:
                    result += str(data)[:500]
            else:
                # Fallback: get page snapshot
                snapshot = await self._call_direct_tool("playwright_snapshot", {})
                if snapshot:
                    result += f"Page: {snapshot.get('title', 'Unknown')}\n"
                    result += f"URL: {snapshot.get('url', '')}\n"
                    summary = snapshot.get('summary', '')[:300]
                    if summary:
                        result += f"\n{summary}"

            self._emit_explainable_summary(result, [])
            return result

        except Exception as e:
            logger.warning(f"Site search handler failed: {e}")
            return None

    async def _handle_form_fill(self, url: str, field_name: str, field_value: str, original_prompt: str) -> Optional[str]:
        """
        Handle form fill tasks: navigate to URL, fill field, describe the form.
        """
        # Ensure URL has protocol
        if not url.startswith('http'):
            url = 'https://' + url

        try:
            # Step 1: Navigate to the URL
            nav_result = await self._call_direct_tool("playwright_navigate", {"url": url})
            if not nav_result or nav_result.get("error"):
                return f"Failed to navigate to {url}: {nav_result.get('error', 'Unknown error')}"

            # Step 2: Get form info before filling
            snapshot_before = await self._call_direct_tool("playwright_snapshot", {})

            # Step 3: Try to fill the field
            field_name_clean = field_name.lower().replace(' ', '').replace('_', '').replace('-', '')
            selectors_to_try = [
                f"input[name*='{field_name_clean}']",
                f"input[name*='{field_name.lower().replace(' ', '_')}']",
                f"input[name*='{field_name.lower().replace(' ', '-')}']",
                f"input[placeholder*='{field_name}' i]",
                f"input[id*='{field_name_clean}']",
                f"textarea[name*='{field_name_clean}']",
            ]

            fill_success = False
            for selector in selectors_to_try:
                try:
                    fill_result = await self._call_direct_tool("playwright_fill", {
                        "selector": selector,
                        "value": field_value
                    })
                    if fill_result and fill_result.get("success"):
                        fill_success = True
                        logger.info(f"Fill succeeded with selector: {selector}")
                        break
                except Exception:
                    continue

            # Step 4: Get form fields to describe
            form_fields = await self._call_direct_tool("playwright_evaluate", {"script": """
                (() => {
                    const inputs = document.querySelectorAll('input, textarea, select');
                    const fields = [];
                    for (const inp of inputs) {
                        if (inp.type === 'hidden') continue;
                        fields.push({
                            name: inp.name || inp.id || 'unnamed',
                            type: inp.type || inp.tagName.toLowerCase(),
                            placeholder: inp.placeholder || '',
                            required: inp.required
                        });
                    }
                    return fields;
                })()
            """})

            # Format response
            result = f"**Navigated to {url}**\n"
            if fill_success:
                result += f"**Filled '{field_name}' with '{field_value}'**\n\n"
            else:
                result += f"**Could not find field '{field_name}' to fill**\n\n"

            result += "**Form Fields Found:**\n"
            if form_fields and form_fields.get("result"):
                for field in form_fields["result"]:
                    field_info = f"- {field.get('name', 'unnamed')} ({field.get('type', 'text')})"
                    if field.get('placeholder'):
                        field_info += f" - placeholder: {field['placeholder']}"
                    if field.get('required'):
                        field_info += " [required]"
                    result += field_info + "\n"
            else:
                result += "- Could not enumerate form fields\n"

            self._emit_explainable_summary(result, [])
            return result

        except Exception as e:
            logger.warning(f"Form fill handler failed: {e}")
            return None

    async def _execute_multi_field_form(self, url: str, prompt: str) -> Optional[str]:
        """
        Handle multi-field form fill tasks like httpbin forms.
        Parses field:value pairs from prompt, navigates, fills all fields, describes state.
        """
        if not url.startswith('http'):
            url = 'https://' + url

        logger.info(f"[MULTI-FORM] Filling multi-field form at {url}")

        try:
            # Step 1: Navigate to the form
            nav_result = await self._call_direct_tool("playwright_navigate", {"url": url})
            if not nav_result or nav_result.get("error"):
                return f"Failed to navigate to {url}"

            await asyncio.sleep(1)  # Wait for form to load

            # Step 2: Parse field:value pairs from prompt
            lower = prompt.lower()
            fields_to_fill = {}

            # Extract customer name
            m = re.search(r"customer\s*name\s*['\"]([^'\"]+)['\"]", lower)
            if m:
                fields_to_fill['custname'] = m.group(1)

            # Extract telephone
            m = re.search(r"telephone\s*['\"]([^'\"]+)['\"]", lower)
            if m:
                fields_to_fill['custtel'] = m.group(1)

            # Extract email
            m = re.search(r"email\s*['\"]([^'\"]+)['\"]", lower)
            if m:
                fields_to_fill['custemail'] = m.group(1)

            # Extract pizza size (radio button)
            m = re.search(r"(?:pizza\s*)?size\s*['\"]([^'\"]+)['\"]", lower)
            if m:
                fields_to_fill['size'] = m.group(1).lower()

            # Extract toppings (checkboxes)
            toppings = re.findall(r"(?:topping[s]?\s*)?['\"]?(bacon|mushroom|cheese|onion)['\"]?", lower, re.I)
            if toppings:
                fields_to_fill['toppings'] = [t.lower() for t in toppings]

            # Extract delivery time
            m = re.search(r"delivery\s*time[^'\"]*['\"]([^'\"]+)['\"]", lower)
            if m:
                fields_to_fill['delivery'] = m.group(1)

            # Extract delivery instructions
            m = re.search(r"delivery\s*instructions?[^'\"]*['\"]([^'\"]+)['\"]", lower)
            if m:
                fields_to_fill['comments'] = m.group(1)

            logger.info(f"[MULTI-FORM] Parsed fields: {fields_to_fill}")

            # Step 3: Fill each field
            fill_results = {}
            for field_name, value in fields_to_fill.items():
                if field_name == 'toppings':
                    # Handle checkboxes
                    for topping in value:
                        try:
                            await self._call_direct_tool("playwright_click", {"selector": f"input[value='{topping}']"})
                            fill_results[f"topping_{topping}"] = "checked"
                        except Exception as e:
                            logger.debug(f"Failed to check topping '{topping}': {e}")
                            fill_results[f"topping_{topping}"] = "failed"
                elif field_name == 'size':
                    # Handle radio button
                    try:
                        await self._call_direct_tool("playwright_click", {"selector": f"input[value='{value}']"})
                        fill_results[field_name] = value
                    except Exception as e:
                        logger.debug(f"Failed to click radio button for '{field_name}': {e}")
                        fill_results[field_name] = "failed"
                else:
                    # Handle text inputs
                    selectors = [
                        f"input[name='{field_name}']",
                        f"textarea[name='{field_name}']",
                        f"input[id='{field_name}']",
                        f"textarea[id='{field_name}']",
                    ]
                    filled = False
                    for sel in selectors:
                        try:
                            result = await self._call_direct_tool("playwright_fill", {"selector": sel, "value": value})
                            if result and result.get("success"):
                                fill_results[field_name] = value
                                filled = True
                                break
                        except Exception as e:
                            logger.debug(f"Failed to fill selector for '{field_name}': {e}")
                            continue
                    if not filled:
                        fill_results[field_name] = "not found"

            # Step 4: Get current form state
            form_state = await self._call_direct_tool("playwright_evaluate", {"script": """
                (() => {
                    const form = document.querySelector('form');
                    if (!form) return {error: 'No form found'};
                    const data = new FormData(form);
                    const state = {};
                    for (let [key, value] of data.entries()) {
                        if (state[key]) {
                            if (Array.isArray(state[key])) state[key].push(value);
                            else state[key] = [state[key], value];
                        } else {
                            state[key] = value;
                        }
                    }
                    return state;
                })()
            """})

            # Format result
            result = f"**Form at {url} - Multi-Field Fill Complete**\n\n"
            result += "**Fields Filled:**\n"
            for field, status in fill_results.items():
                result += f"  - {field}: {status}\n"

            result += "\n**Current Form State:**\n"
            if form_state and form_state.get("result"):
                for key, val in form_state["result"].items():
                    result += f"  - {key}: {val}\n"
            else:
                result += "  - Could not read form state\n"

            self._emit_explainable_summary(result, [])
            return result

        except Exception as e:
            logger.warning(f"Multi-field form fill failed: {e}")
            return None

    async def smart_click(self, selector: str, description: str = None) -> Dict[str, Any]:
        """
        Click with automatic visual fallback on failure.

        Args:
            selector: CSS selector to try first
            description: Human-readable description for visual fallback

        Returns:
            Result dict with success/error status
        """
        # Import here to avoid circular imports
        from .selector_fallbacks import click_with_visual_fallback

        page = self.browser.page if self.browser else None
        if not page:
            return {"error": "No browser page available"}

        try:
            # Try primary selector first
            await page.click(selector, timeout=5000)
            logger.debug(f"Clicked via selector: {selector}")
            return {"success": True, "method": "selector"}
        except Exception as e:
            logger.debug(f"Selector click failed: {e}")

            # Try visual fallback if description provided
            if description:
                try:
                    visual_result = await click_with_visual_fallback(
                        page=page,
                        selector=selector,
                        description=description
                    )
                    if visual_result.get('success'):
                        logger.success(f"[VISUAL] Clicked via visual fallback: {description}")
                        return visual_result
                except Exception as ve:
                    logger.debug(f"Visual fallback failed: {ve}")

            # Both failed - raise the original error
            raise


# Standalone utility functions for use outside the mixin
async def try_click_with_fallback(
    call_direct_tool,
    click_target: str,
    emit_summary=None
) -> bool:
    """
    Try to click an element using multiple strategies.

    Args:
        call_direct_tool: Async function to call playwright tools
        click_target: Text or description of element to click
        emit_summary: Optional function to emit progress summary

    Returns:
        True if click succeeded, False otherwise
    """
    click_target_clean = click_target.strip().rstrip('.')

    selectors_to_try = [
        f"a:has-text('{click_target_clean}')",
        f"button:has-text('{click_target_clean}')",
        f"a[href*='{click_target_clean.lower().replace(' ', '-')}']",
        f"a[href*='{click_target_clean.lower().replace(' ', '_')}']",
        f"text={click_target_clean}",
    ]

    for selector in selectors_to_try:
        try:
            result = await call_direct_tool("playwright_click", {"selector": selector})
            if result and result.get("success"):
                logger.info(f"Click succeeded with selector: {selector}")
                return True
        except Exception:
            continue

    # Fallback: JavaScript click
    js_click = f"""
        (() => {{
            const links = document.querySelectorAll('a, button');
            for (const el of links) {{
                if (el.textContent.toLowerCase().includes('{click_target_clean.lower()}')) {{
                    el.click();
                    return true;
                }}
            }}
            return false;
        }})()
    """
    js_result = await call_direct_tool("playwright_evaluate", {"script": js_click})
    return js_result and js_result.get("result")


async def fill_form_field(
    call_direct_tool,
    field_name: str,
    field_value: str
) -> bool:
    """
    Try to fill a form field using multiple selector strategies.

    Args:
        call_direct_tool: Async function to call playwright tools
        field_name: Name/identifier of the field
        field_value: Value to fill

    Returns:
        True if fill succeeded, False otherwise
    """
    field_name_clean = field_name.lower().replace(' ', '').replace('_', '').replace('-', '')

    selectors_to_try = [
        f"input[name*='{field_name_clean}']",
        f"input[name*='{field_name.lower().replace(' ', '_')}']",
        f"input[name*='{field_name.lower().replace(' ', '-')}']",
        f"input[placeholder*='{field_name}' i]",
        f"input[id*='{field_name_clean}']",
        f"textarea[name*='{field_name_clean}']",
    ]

    for selector in selectors_to_try:
        try:
            result = await call_direct_tool("playwright_fill", {
                "selector": selector,
                "value": field_value
            })
            if result and result.get("success"):
                logger.info(f"Fill succeeded with selector: {selector}")
                return True
        except Exception:
            continue

    return False


async def get_form_fields(call_direct_tool) -> List[Dict[str, Any]]:
    """
    Get list of visible form fields on the current page.

    Args:
        call_direct_tool: Async function to call playwright tools

    Returns:
        List of field info dicts with name, type, placeholder, required
    """
    form_fields = await call_direct_tool("playwright_evaluate", {"script": """
        (() => {
            const inputs = document.querySelectorAll('input, textarea, select');
            const fields = [];
            for (const inp of inputs) {
                if (inp.type === 'hidden') continue;
                fields.push({
                    name: inp.name || inp.id || 'unnamed',
                    type: inp.type || inp.tagName.toLowerCase(),
                    placeholder: inp.placeholder || '',
                    required: inp.required
                });
            }
            return fields;
        })()
    """})

    if form_fields and form_fields.get("result"):
        return form_fields["result"]
    return []


async def build_paginated_url(base_url: str, page_num: int) -> List[str]:
    """
    Build list of possible paginated URLs for a given page number.

    Args:
        base_url: Base URL to paginate
        page_num: Page number to navigate to

    Returns:
        List of possible paginated URLs to try
    """
    return [
        f"{base_url}/page/{page_num}",
        f"{base_url}?page={page_num}",
        f"{base_url}/page/{page_num}/",
        base_url.rstrip('/') + f"/page/{page_num}",
    ]
