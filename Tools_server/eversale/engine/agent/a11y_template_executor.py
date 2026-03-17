"""
A11y Template Executor - Execute action templates using A11yBrowser.

This module bridges action_templates.py with a11y_browser.py, enabling
template-driven browser automation using accessibility refs instead of CSS selectors.

Why:
- Templates provide deterministic action flows (like Playwright MCP)
- A11y refs are stable and semantic (no selector healing needed)
- Best of both worlds: structured templates + reliable automation

Usage:
    from a11y_template_executor import execute_template_a11y
    from a11y_browser import A11yBrowser
    from action_templates import TEMPLATES

    async with A11yBrowser() as browser:
        result = await execute_template_a11y(
            "search_fb_ads",
            {"query": "sales automation"},
            browser
        )
        if result["success"]:
            print(f"Found {len(result['data'])} prospects")
"""

import asyncio
import re
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

try:
    from .action_templates import TEMPLATES, ActionTemplate, ActionStep
    from .a11y_browser import A11yBrowser, Snapshot, ActionResult
except ImportError:
    from action_templates import TEMPLATES, ActionTemplate, ActionStep
    from a11y_browser import A11yBrowser, Snapshot, ActionResult


@dataclass
class TemplateExecutionResult:
    """Result of template execution."""
    success: bool
    template_name: str
    steps_executed: int
    steps_failed: int
    data: List[Dict[str, Any]] = None
    final_url: Optional[str] = None
    error: Optional[str] = None
    extraction_status: str = "unknown"
    extraction_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for compatibility."""
        return {
            "success": self.success,
            "template": self.template_name,
            "steps_executed": self.steps_executed,
            "steps_failed": self.steps_failed,
            "data": self.data or [],
            "url": self.final_url,
            "error": self.error,
            "extraction_status": self.extraction_status,
            "extraction_count": self.extraction_count,
        }


def get_template_by_name(name: str) -> Optional[ActionTemplate]:
    """Get template by name from TEMPLATES list."""
    for template in TEMPLATES:
        if template.name == name:
            return template
    return None


async def execute_template_a11y(
    template_name: str,
    variables: Dict[str, str],
    browser: A11yBrowser
) -> Dict[str, Any]:
    """
    Execute an action template using A11yBrowser.

    Args:
        template_name: Name of template to execute (e.g., "search_fb_ads")
        variables: Variables to substitute in template (e.g., {"query": "..."})
        browser: A11yBrowser instance (must be launched)

    Returns:
        Dict with:
        - success: bool
        - data: List of extracted items (for extraction templates)
        - final_url: str
        - error: str (if failed)
        - steps_executed: int
        - steps_failed: int
        - extraction_status: "success" | "empty" | "failed"
        - extraction_count: int

    Example:
        async with A11yBrowser() as browser:
            result = await execute_template_a11y(
                "search_fb_ads",
                {"query": "sales automation"},
                browser
            )
            if result["success"]:
                for ad in result["data"]:
                    print(f"Advertiser: {ad['advertiser']}")
    """
    template = get_template_by_name(template_name)
    if not template:
        return {
            "success": False,
            "error": f"Template '{template_name}' not found",
            "template": template_name,
            "steps_executed": 0,
            "steps_failed": 0,
            "data": [],
        }

    result = TemplateExecutionResult(
        success=True,
        template_name=template_name,
        steps_executed=0,
        steps_failed=0,
        data=[],
    )

    current_snapshot: Optional[Snapshot] = None

    # Execute each step
    for i, step in enumerate(template.steps):
        try:
            # Substitute variables in params
            step_params = _substitute_variables(step.params, variables)

            # Map template action to a11y browser method
            action_result = await _execute_step(
                step.tool,
                step_params,
                browser,
                current_snapshot
            )

            if not action_result.success:
                result.steps_failed += 1
                if not step.optional:
                    result.success = False
                    result.error = f"Step {i+1} failed: {action_result.error}"
                    break
            else:
                result.steps_executed += 1

                # Update snapshot if this action returned one
                if action_result.action == "snapshot" and action_result.data.get("snapshot"):
                    current_snapshot = action_result.data["snapshot"]

                # Extract data if this is an extraction step
                if step.tool == "playwright_extract_fb_ads":
                    extracted = action_result.data.get("ads", [])
                    result.data = extracted
                elif step.tool == "playwright_extract_list":
                    extracted = action_result.data.get("items", [])
                    result.data = extracted

            # Wait after step
            if step.wait_after > 0:
                await asyncio.sleep(step.wait_after)

        except Exception as e:
            result.steps_failed += 1
            if not step.optional:
                result.success = False
                result.error = f"Step {i+1} exception: {str(e)}"
                break

    # Get final URL
    try:
        result.final_url = await browser.get_url()
    except Exception:
        result.final_url = None

    # Set extraction status
    if result.data and len(result.data) > 0:
        result.extraction_status = "success"
        result.extraction_count = len(result.data)
    elif result.success:
        result.extraction_status = "empty"
        result.extraction_count = 0
    else:
        result.extraction_status = "failed"
        result.extraction_count = 0

    return result.to_dict()


def _substitute_variables(params: Dict[str, Any], variables: Dict[str, str]) -> Dict[str, Any]:
    """Substitute {variable} placeholders in step params."""
    substituted = {}
    for key, value in params.items():
        if isinstance(value, str):
            # Replace {var} with actual values
            for var_name, var_value in variables.items():
                value = value.replace(f"{{{var_name}}}", var_value)

            # Handle unsubstituted placeholders in URLs
            if key == "url" and "{" in value:
                # Remove query params with unresolved placeholders
                if "?" in value:
                    base, query = value.split("?", 1)
                    if re.search(r'\{[^}]+\}', query):
                        value = base
                # Remove path segments with placeholders
                value = re.sub(r'/\{[^}]+\}/?', '/', value)

        substituted[key] = value

    return substituted


async def _execute_step(
    tool: str,
    params: Dict[str, Any],
    browser: A11yBrowser,
    snapshot: Optional[Snapshot]
) -> ActionResult:
    """
    Execute a single template step using A11yBrowser.

    Maps template tool names to a11y browser methods:
    - playwright_navigate -> browser.navigate()
    - playwright_click -> browser.click() (find ref from snapshot)
    - playwright_fill -> browser.type() (find ref from snapshot)
    - playwright_snapshot -> browser.snapshot()
    - playwright_wait -> browser.wait()
    - playwright_scroll -> browser.scroll()
    - playwright_extract_fb_ads -> _extract_fb_ads()
    - playwright_extract_list -> _extract_list()
    """

    # Navigate
    if tool == "playwright_navigate":
        url = params.get("url", "")
        return await browser.navigate(url)

    # Snapshot
    if tool == "playwright_snapshot" or tool == "browser_snapshot" or tool == "a11y_snapshot":
        snapshot = await browser.snapshot()
        return ActionResult(
            success=True,
            action="snapshot",
            data={"snapshot": snapshot}
        )

    # Wait
    if tool == "playwright_wait":
        seconds = params.get("time", 1)
        return await browser.wait(seconds)

    # Scroll
    if tool == "playwright_scroll":
        direction = params.get("direction", "down")
        amount = params.get("amount", 500)
        return await browser.scroll(direction, amount)

    # Click (need to find element from snapshot)
    if tool == "playwright_click" or tool == "browser_click" or tool == "a11y_click":
        element_desc = params.get("element", "")
        if not snapshot:
            snapshot = await browser.snapshot()

        ref = _find_element_ref(element_desc, snapshot)
        if ref:
            return await browser.click(ref)
        else:
            return ActionResult(
                success=False,
                action="click",
                error=f"Element '{element_desc}' not found in snapshot"
            )

    # Fill/Type (need to find element from snapshot)
    if tool == "playwright_fill" or tool == "playwright_type" or tool == "browser_type" or tool == "a11y_type":
        element_desc = params.get("element", "")
        text = params.get("text", params.get("value", ""))

        if not snapshot:
            snapshot = await browser.snapshot()

        ref = _find_element_ref(element_desc, snapshot)
        if ref:
            return await browser.type(ref, text)
        else:
            return ActionResult(
                success=False,
                action="type",
                error=f"Element '{element_desc}' not found in snapshot"
            )

    # Screenshot
    if tool == "playwright_screenshot":
        path = params.get("path")
        full_page = params.get("full_page", False)
        return await browser.screenshot(path, full_page)

    # Evaluate
    if tool == "playwright_evaluate":
        script = params.get("function", "")
        return await browser.evaluate(script)

    # Extract FB Ads
    if tool == "playwright_extract_fb_ads":
        max_ads = params.get("max_ads", 200)
        return await _extract_fb_ads(browser, max_ads)

    # Extract List (generic)
    if tool == "playwright_extract_list":
        limit = params.get("limit", 100)
        return await _extract_list(browser, limit)

    # Hover
    if tool == "playwright_hover" or tool == "a11y_hover":
        element_desc = params.get("element", "")
        if not snapshot:
            snapshot = await browser.snapshot()

        ref = _find_element_ref(element_desc, snapshot)
        if ref:
            return await browser.hover(ref)
        else:
            return ActionResult(
                success=False,
                action="hover",
                error=f"Element '{element_desc}' not found in snapshot"
            )

    # Select
    if tool == "playwright_select" or tool == "a11y_select":
        element_desc = params.get("element", "")
        value = params.get("value", "")

        if not snapshot:
            snapshot = await browser.snapshot()

        ref = _find_element_ref(element_desc, snapshot)
        if ref:
            return await browser.select(ref, value)
        else:
            return ActionResult(
                success=False,
                action="select",
                error=f"Element '{element_desc}' not found in snapshot"
            )

    # Unknown tool - skip it
    return ActionResult(
        success=True,
        action="skip",
        data={"skipped_tool": tool}
    )


def _find_element_ref(description: str, snapshot: Snapshot) -> Optional[str]:
    """
    Find element ref from snapshot based on description.

    Searches by:
    1. Role match (e.g., "Compose button" -> role=button, name contains "compose")
    2. Name match (partial, case-insensitive)
    3. Value match (for inputs)

    Args:
        description: Human-readable element description (e.g., "Search button", "Email input")
        snapshot: Current page snapshot

    Returns:
        Element ref (e.g., "e38") or None
    """
    if not snapshot or not description:
        return None

    desc_lower = description.lower()

    # Extract role hint from description (e.g., "search button" -> role=button)
    role_keywords = {
        "button": "button",
        "link": "link",
        "input": "textbox",
        "textbox": "textbox",
        "searchbox": "searchbox",
        "checkbox": "checkbox",
        "radio": "radio",
        "dropdown": "combobox",
        "combobox": "combobox",
    }

    target_role = None
    for keyword, role in role_keywords.items():
        if keyword in desc_lower:
            target_role = role
            break

    # Search elements
    candidates = []
    for el in snapshot.elements:
        score = 0

        # Role match
        if target_role and el.role == target_role:
            score += 10

        # Name match (partial)
        if el.name:
            name_lower = el.name.lower()
            # Remove role keyword from description for name matching
            desc_for_name = desc_lower
            for keyword in role_keywords.keys():
                desc_for_name = desc_for_name.replace(keyword, "").strip()

            if desc_for_name in name_lower or name_lower in desc_for_name:
                score += 20

            # Exact word match bonus
            if desc_for_name and desc_for_name in name_lower.split():
                score += 10

        # Value match (for inputs)
        if el.value and desc_lower in el.value.lower():
            score += 5

        if score > 0:
            candidates.append((score, el))

    # Return highest scoring element
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1].ref

    return None


async def _extract_fb_ads(browser: A11yBrowser, max_ads: int = 200) -> ActionResult:
    """
    Extract advertiser data from Facebook Ads Library page.

    Uses JavaScript evaluation to extract:
    - Advertiser name (from FB page links)
    - FB page URL
    - Landing URL (from l.facebook.com redirect links)
    - Ad text preview

    Args:
        browser: A11yBrowser instance
        max_ads: Maximum number of ads to extract

    Returns:
        ActionResult with ads list in data dict
    """
    try:
        # Use JavaScript to extract ads directly - this gets actual hrefs
        js_extract = """
        () => {
            const ads = [];
            const seen = new Set();

            // Find all links on the page
            const links = document.querySelectorAll('a');

            // Build a map of FB page links and landing page links
            const fbPageLinks = [];  // Links to facebook.com/[id]/
            const landingLinks = [];  // Links to l.facebook.com/l.php

            for (const link of links) {
                const href = link.href || '';
                const text = (link.textContent || '').trim();

                // FB page links: https://www.facebook.com/[page_id]/
                if (href.match(/facebook\\.com\\/\\d+\\/?$/) ||
                    href.match(/facebook\\.com\\/[a-zA-Z0-9._-]+\\/?$/)) {
                    // Skip navigation links
                    const textLower = text.toLowerCase();
                    if (textLower.length > 2 &&
                        !['home', 'facebook', 'log in', 'sign up', 'help', 'about'].includes(textLower)) {
                        fbPageLinks.push({
                            name: text,
                            href: href,
                            element: link
                        });
                    }
                }

                // Landing page links: l.facebook.com/l.php?u=...
                if (href.includes('l.facebook.com/l.php') || href.includes('lm.facebook.com/l.php')) {
                    // Extract the actual URL from the redirect
                    const match = href.match(/[?&]u=([^&]+)/);
                    if (match) {
                        try {
                            const decodedUrl = decodeURIComponent(match[1]);
                            landingLinks.push({
                                text: text,
                                redirectUrl: href,
                                landingUrl: decodedUrl,
                                element: link
                            });
                        } catch (e) {
                            // URL decode failed, use as-is
                            landingLinks.push({
                                text: text,
                                redirectUrl: href,
                                landingUrl: match[1],
                                element: link
                            });
                        }
                    }
                }
            }

            // Match FB page links with nearby landing links
            for (const fbLink of fbPageLinks) {
                const name = fbLink.name;
                const nameLower = name.toLowerCase();

                // Skip if already seen
                if (seen.has(nameLower)) continue;

                // Skip if name is too short or looks like UI element
                if (name.length < 3) continue;
                if (['sponsored', 'active', 'inactive'].includes(nameLower)) continue;

                // Find the closest landing link (within same ad card)
                let landingUrl = '';
                let bestDistance = Infinity;

                const fbRect = fbLink.element.getBoundingClientRect();

                for (const landing of landingLinks) {
                    const landingRect = landing.element.getBoundingClientRect();

                    // Calculate distance between elements
                    const distance = Math.sqrt(
                        Math.pow(fbRect.top - landingRect.top, 2) +
                        Math.pow(fbRect.left - landingRect.left, 2)
                    );

                    // If within 500px and closer than previous best
                    if (distance < 500 && distance < bestDistance) {
                        bestDistance = distance;
                        landingUrl = landing.landingUrl;
                    }
                }

                // Get nearby text for ad content
                let adText = '';
                const parent = fbLink.element.closest('div[class]');
                if (parent) {
                    // Look for text content in parent
                    const textNodes = parent.querySelectorAll('span, div');
                    for (const node of textNodes) {
                        const nodeText = (node.textContent || '').trim();
                        if (nodeText.length > 50 && nodeText.length < 500 &&
                            !nodeText.includes('Library ID') &&
                            !nodeText.includes('Started running')) {
                            adText = nodeText.substring(0, 200);
                            break;
                        }
                    }
                }

                seen.add(nameLower);

                ads.push({
                    advertiser: name,
                    fb_page_url: fbLink.href,
                    landing_url: landingUrl,
                    url: landingUrl || fbLink.href,
                    text: adText
                });

                if (ads.length >= """ + str(max_ads) + """) break;
            }

            return ads;
        }
        """

        result = await browser.evaluate(js_extract)

        if result.success and result.data.get("result"):
            ads = result.data["result"]

            # Get current URL for source tracking
            current_url = await browser.get_url()

            return ActionResult(
                success=True,
                action="extract_fb_ads",
                data={
                    "ads": ads,
                    "ads_count": len(ads),
                    "source_url": current_url,
                }
            )
        else:
            # Fallback to accessibility tree method if JS fails
            return await _extract_fb_ads_fallback(browser, max_ads)

    except Exception as e:
        return ActionResult(
            success=False,
            action="extract_fb_ads",
            error=str(e)
        )


async def _extract_fb_ads_fallback(browser: A11yBrowser, max_ads: int = 200) -> ActionResult:
    """
    Fallback extraction using accessibility tree when JavaScript fails.
    """
    try:
        snapshot = await browser.snapshot(force=True)
        ads = []
        seen_advertisers = set()

        if not snapshot or not snapshot.elements:
            return ActionResult(
                success=False,
                action="extract_fb_ads",
                error="Empty snapshot"
            )

        skip_names = {
            "meta ad library", "ad library", "facebook", "home", "create",
            "settings", "help", "about", "filters", "search", "log in",
            "sign up", "privacy", "terms", "cookies", "ad choices",
            "see all", "load more", "show more", "learn more",
            "video playback", "playing this video", "trouble playing"
        }

        elements = snapshot.elements
        i = 0
        while i < len(elements) and len(ads) < max_ads:
            el = elements[i]

            if el.role == "link" and el.name:
                raw_name = el.name.strip()
                raw_name_lower = raw_name.lower()

                if raw_name_lower in skip_names or len(raw_name) < 3:
                    i += 1
                    continue

                # Extract advertiser name from long link text
                name = raw_name
                for splitter in [" Read This", " Ready to", " Discover", " Learn", " Find out", " Get ", " Start ", " Join "]:
                    if splitter.lower() in raw_name_lower:
                        idx = raw_name_lower.find(splitter.lower())
                        name = raw_name[:idx].strip()
                        break

                if len(name) > 50 and "." in name:
                    name = name.split()[0] if " " in name else name[:50]

                name_lower = name.lower()
                if name_lower in seen_advertisers:
                    i += 1
                    continue

                # Check for ad context
                started_running = ""
                for j in range(i + 1, min(i + 15, len(elements))):
                    next_el = elements[j]
                    if next_el.role == "text" and next_el.name:
                        if "started running" in next_el.name.lower():
                            started_running = next_el.name
                            break

                if started_running or "facebook.com" not in name_lower:
                    seen_advertisers.add(name_lower)
                    fb_page_url = f"https://www.facebook.com/{name.replace(' ', '')}"

                    ads.append({
                        "advertiser": name,
                        "url": fb_page_url,
                        "landing_url": "",
                        "fb_page_url": fb_page_url,
                        "text": started_running,
                    })

            i += 1

        return ActionResult(
            success=True,
            action="extract_fb_ads",
            data={
                "ads": ads,
                "ads_count": len(ads),
                "source_url": snapshot.url,
            }
        )
    except Exception as e:
        return ActionResult(
            success=False,
            action="extract_fb_ads",
            error=str(e)
        )


async def _extract_list(browser: A11yBrowser, limit: int = 100) -> ActionResult:
    """
    Extract generic list items from current page.

    Looks for:
    - Links with meaningful text
    - List items
    - Headings

    Args:
        browser: A11yBrowser instance
        limit: Maximum items to extract

    Returns:
        ActionResult with items list in data dict
    """
    try:
        snapshot = await browser.snapshot()
        items = []

        # Extract links and headings as items
        for el in snapshot.elements:
            if len(items) >= limit:
                break

            # Skip navigation and common UI elements
            if el.role in {"button", "searchbox", "textbox", "checkbox"}:
                continue

            # Include meaningful links and headings
            if el.role in {"link", "heading"} and el.name:
                name = el.name.strip()
                if len(name) > 3 and len(name) < 200:
                    items.append({
                        "title": name,
                        "type": el.role,
                        "url": snapshot.url,  # Would need link extraction for actual URLs
                    })

        return ActionResult(
            success=True,
            action="extract_list",
            data={
                "items": items,
                "count": len(items),
                "source_url": snapshot.url,
            }
        )
    except Exception as e:
        return ActionResult(
            success=False,
            action="extract_list",
            error=str(e)
        )


# === Example Usage ===

async def example():
    """Example of executing templates with A11yBrowser."""
    print("A11y Template Executor Example")
    print("=" * 60)

    async with A11yBrowser(headless=False, slow_mo=500) as browser:
        # Example 1: Search Facebook Ads
        print("\n1. Executing search_fb_ads template...")
        result = await execute_template_a11y(
            "search_fb_ads",
            {"query": "sales automation"},
            browser
        )

        print(f"   Success: {result['success']}")
        print(f"   Steps executed: {result['steps_executed']}")
        print(f"   Steps failed: {result['steps_failed']}")
        print(f"   Final URL: {result.get('url', 'N/A')}")

        if result.get('data'):
            print(f"   Extracted {len(result['data'])} ads:")
            for ad in result['data'][:3]:
                print(f"     - {ad.get('advertiser', 'Unknown')}")

        # Example 2: Open Gmail
        print("\n2. Executing open_gmail template...")
        result2 = await execute_template_a11y(
            "open_gmail",
            {},
            browser
        )
        print(f"   Success: {result2['success']}")
        print(f"   Final URL: {result2.get('url', 'N/A')}")

    print("\n" + "=" * 60)
    print("Example complete!")


if __name__ == "__main__":
    asyncio.run(example())
