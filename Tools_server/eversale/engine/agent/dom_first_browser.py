"""
DOM-First Browser - Ref-based snapshot system with smart re-snapshot logic

This module implements a DOM-first approach to browser automation where:
1. Snapshots return interactive elements with stable refs
2. Actions use refs directly (no selector healing needed)
3. Smart re-snapshot logic - only resnapshot when DOM changes

Designed for production use with proper error handling and logging.

Usage:
    async with DOMFirstBrowser() as browser:
        await browser.navigate("https://example.com")

        # Get snapshot
        snapshot = await browser.snapshot()
        # Returns: {"nodes": [...], "refs": {...}, "url": "...", "title": "..."}

        # Click using ref
        await browser.click("e38")

        # Type using ref
        await browser.type("e42", "hello world")

        # Run JavaScript
        data = await browser.run_code("return document.title")

        # Observe network/console
        result = await browser.observe(network=True, console=True)
"""

import asyncio
import hashlib
import json
import time
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from loguru import logger

# Import stealth configuration if available
STEALTH_AVAILABLE = False
try:
    from .stealth_browser_config import (
        get_mcp_compatible_launch_args,
        get_chrome_context_options
    )
    STEALTH_AVAILABLE = True
except ImportError:
    try:
        from stealth_browser_config import (
            get_mcp_compatible_launch_args,
            get_chrome_context_options
        )
        STEALTH_AVAILABLE = True
    except ImportError:
        pass

# Import a11y config for settings
try:
    from . import a11y_config as config
except ImportError:
    import a11y_config as config


@dataclass
class ElementNode:
    """Represents an interactive element in the DOM."""
    ref: str  # e.g., "e38"
    role: str  # e.g., "button", "textbox", "link"
    name: str  # accessible name
    value: Optional[str] = None
    description: Optional[str] = None
    focused: bool = False
    disabled: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "ref": self.ref,
            "role": self.role,
            "name": self.name,
            "value": self.value,
            "description": self.description,
            "focused": self.focused,
            "disabled": self.disabled
        }

    def __hash__(self) -> int:
        """Hash based on semantic content for change detection."""
        content = f"{self.role}|{self.name}|{self.value or ''}"
        return int(hashlib.md5(content.encode()).hexdigest()[:16], 16)


@dataclass
class SnapshotResult:
    """Result of a snapshot operation."""
    nodes: List[Dict[str, Any]]  # List of element dicts
    refs: Dict[str, Dict[str, Any]]  # Mapping of ref -> element data
    url: str
    title: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "nodes": self.nodes,
            "refs": self.refs,
            "url": self.url,
            "title": self.title,
            "timestamp": self.timestamp
        }


@dataclass
class ObserveResult:
    """Result of an observe operation."""
    console_messages: List[Dict[str, Any]] = field(default_factory=list)
    network_requests: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "console": self.console_messages,
            "network": self.network_requests,
            "timestamp": self.timestamp
        }


class DOMFirstBrowser:
    """
    DOM-first browser with ref-based interactions.

    Features:
    - Accessibility tree snapshots with stable refs
    - Smart re-snapshot logic (only when DOM changes)
    - Network and console observation
    - JavaScript execution with JSON return
    - Production-ready error handling
    """

    def __init__(
        self,
        headless: bool = True,
        slow_mo: int = 0,
        viewport: tuple = (1280, 720),
        user_agent: Optional[str] = None
    ):
        self.headless = headless
        self.slow_mo = slow_mo
        self.viewport = viewport
        self.user_agent = user_agent

        # Playwright objects
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

        # Ref tracking
        self._ref_counter = 0
        self._ref_map: Dict[str, Any] = {}  # ref -> element locator info

        # Smart re-snapshot logic
        self._last_snapshot_hash: Optional[str] = None
        self._last_snapshot: Optional[SnapshotResult] = None
        self._dom_mutation_count = 0

        # Observation tracking
        self._console_messages: List[Dict[str, Any]] = []
        self._network_requests: List[Dict[str, Any]] = []

        # Performance metrics
        self._metrics = {
            "snapshots_taken": 0,
            "snapshot_cache_hits": 0,
            "actions_executed": 0,
            "action_failures": 0,
            "dom_mutations_detected": 0
        }

    async def __aenter__(self) -> "DOMFirstBrowser":
        await self.launch()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        await self.close()
        return False

    async def launch(self) -> None:
        """Launch the browser with stealth configuration."""
        try:
            self._playwright = await async_playwright().start()

            # Build launch options
            launch_opts = {
                "headless": self.headless,
                "slow_mo": self.slow_mo,
            }

            if STEALTH_AVAILABLE:
                launch_opts["args"] = get_mcp_compatible_launch_args()
                launch_opts["channel"] = "chrome"

            try:
                self._browser = await self._playwright.chromium.launch(**launch_opts)
            except Exception:
                # Fallback without channel if Chrome not installed
                launch_opts.pop("channel", None)
                self._browser = await self._playwright.chromium.launch(**launch_opts)

            # Create context
            context_opts = {
                "viewport": {"width": self.viewport[0], "height": self.viewport[1]}
            }

            if self.user_agent:
                context_opts["user_agent"] = self.user_agent
            elif STEALTH_AVAILABLE:
                context_opts.update(get_chrome_context_options())

            self._context = await self._browser.new_context(**context_opts)

            # Create page
            self._page = await self._context.new_page()

            # Set up listeners for observation
            self._console_messages = []
            self._page.on("console", lambda msg: self._console_messages.append({
                "type": msg.type,
                "text": msg.text,
                "location": msg.location,
                "timestamp": time.time()
            }))

            self._network_requests = []
            self._page.on("request", lambda req: self._network_requests.append({
                "url": req.url,
                "method": req.method,
                "headers": req.headers,
                "timestamp": time.time()
            }))

            # Set up DOM mutation observer for smart re-snapshot
            await self._setup_mutation_observer()

            logger.info("DOMFirstBrowser launched successfully")

        except Exception as e:
            logger.error(f"Failed to launch browser: {e}")
            raise

    async def close(self) -> None:
        """Close the browser and cleanup resources."""
        try:
            if self._page:
                await self._page.close()
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()

            logger.info("DOMFirstBrowser closed successfully")
        except Exception as e:
            logger.warning(f"Error during browser cleanup: {e}")

    async def _setup_mutation_observer(self) -> None:
        """Set up DOM mutation observer for smart re-snapshot detection."""
        try:
            await self._page.evaluate("""
                () => {
                    if (!window.__domMutationCount) {
                        window.__domMutationCount = 0;

                        const observer = new MutationObserver((mutations) => {
                            // Filter out insignificant mutations (style changes, etc.)
                            const significantMutations = mutations.filter(m =>
                                m.type === 'childList' ||
                                (m.type === 'attributes' &&
                                 ['disabled', 'aria-disabled', 'hidden'].includes(m.attributeName))
                            );

                            if (significantMutations.length > 0) {
                                window.__domMutationCount += significantMutations.length;
                            }
                        });

                        observer.observe(document.body, {
                            childList: true,
                            subtree: true,
                            attributes: true,
                            attributeFilter: ['disabled', 'aria-disabled', 'hidden']
                        });
                    }
                }
            """)
        except Exception as e:
            logger.warning(f"Failed to set up mutation observer: {e}")

    async def _check_dom_mutations(self) -> int:
        """Check how many DOM mutations occurred since last check."""
        try:
            count = await self._page.evaluate("() => window.__domMutationCount || 0")
            # Reset counter
            await self._page.evaluate("() => { window.__domMutationCount = 0; }")
            return count
        except Exception:
            return 0

    async def navigate(self, url: str, wait_until: str = "domcontentloaded") -> bool:
        """
        Navigate to a URL.

        Args:
            url: URL to navigate to
            wait_until: Wait until "load", "domcontentloaded", or "networkidle"

        Returns:
            True if navigation succeeded, False otherwise
        """
        try:
            await self._page.goto(url, wait_until=wait_until, timeout=30000)

            # Clear snapshot cache after navigation
            self._last_snapshot_hash = None
            self._last_snapshot = None

            # Reset mutation observer
            await self._setup_mutation_observer()

            logger.info(f"Navigated to {url}")
            return True

        except Exception as e:
            logger.error(f"Navigation failed to {url}: {e}")
            return False

    async def snapshot(self, force: bool = False) -> SnapshotResult:
        """
        Get accessibility snapshot of the page.

        Returns a snapshot with:
        - nodes[]: list of interactive elements with refs
        - refs{}: mapping of ref IDs to element data
        - url, title, timestamp

        Smart re-snapshot logic:
        - If DOM hasn't changed significantly, returns cached snapshot
        - If force=True, always takes new snapshot

        Args:
            force: If True, bypass cache and force new snapshot

        Returns:
            SnapshotResult with nodes, refs, url, title
        """
        try:
            # Check if DOM changed since last snapshot
            mutation_count = await self._check_dom_mutations()

            if not force and self._last_snapshot is not None and mutation_count == 0:
                # No significant DOM changes - return cached snapshot
                self._metrics["snapshot_cache_hits"] += 1
                logger.debug("Snapshot cache hit - DOM unchanged")
                return self._last_snapshot

            if mutation_count > 0:
                self._metrics["dom_mutations_detected"] += mutation_count
                logger.debug(f"DOM mutations detected: {mutation_count}")

            # Reset refs for new snapshot
            self._ref_counter = 0
            self._ref_map = {}
            elements = []

            # Get accessibility tree
            try:
                raw_tree = await asyncio.wait_for(
                    self._page.accessibility.snapshot(),
                    timeout=config.DEFAULT_TIMEOUT / 1000
                )

                if raw_tree:
                    elements = self._parse_a11y_tree(raw_tree)
                    logger.debug(f"Parsed {len(elements)} elements from accessibility tree")

            except asyncio.TimeoutError:
                logger.warning("Accessibility snapshot timed out")
            except Exception as e:
                logger.warning(f"Accessibility tree error: {e}")

            # Fallback to DOM queries if needed
            if len(elements) < getattr(config, 'FALLBACK_ELEMENT_THRESHOLD', 20):
                fallback_elements = await self._fallback_snapshot()
                # Merge without duplicates
                existing_names = {el.name.lower() for el in elements if el.name}
                for el in fallback_elements:
                    if el.name and el.name.lower() not in existing_names:
                        elements.append(el)
                        existing_names.add(el.name.lower())

            # Limit elements
            elements = elements[:config.MAX_ELEMENTS_PER_SNAPSHOT]

            # Build nodes and refs
            nodes = []
            refs = {}

            for el in elements:
                node_dict = el.to_dict()
                nodes.append(node_dict)
                refs[el.ref] = {
                    "role": el.role,
                    "name": el.name,
                    "value": el.value,
                    "disabled": el.disabled,
                    "focused": el.focused
                }

            # Create snapshot result
            snapshot = SnapshotResult(
                nodes=nodes,
                refs=refs,
                url=self._page.url,
                title=await self._page.title()
            )

            # Cache snapshot
            self._last_snapshot = snapshot
            self._metrics["snapshots_taken"] += 1

            logger.info(f"Snapshot taken: {len(nodes)} elements at {snapshot.url}")

            return snapshot

        except Exception as e:
            logger.error(f"Snapshot failed: {e}")
            raise

    def _parse_a11y_tree(self, node: Dict, depth: int = 0, parent_role: str = "") -> List[ElementNode]:
        """Parse accessibility tree into ElementNode list."""
        elements = []

        role = node.get("role", "")
        name = node.get("name", "")
        value = node.get("value")

        # Interactive roles to include
        interactive_roles = {
            "button", "link", "textbox", "searchbox", "checkbox", "radio",
            "combobox", "slider", "tab", "menuitem", "option", "spinbutton"
        }

        # Include meaningful text nodes
        is_meaningful_text = (
            role == "text" and
            name and
            len(name.strip()) > 0 and
            parent_role not in {"button", "link"}
        )

        if role in interactive_roles or is_meaningful_text:
            ref = self._make_ref()
            self._ref_map[ref] = {
                "role": role,
                "name": name,
                "node": node,
            }

            elements.append(ElementNode(
                ref=ref,
                role=role,
                name=name or "",
                value=value,
                description=node.get("description"),
                focused=node.get("focused", False),
                disabled=node.get("disabled", False),
            ))

        # Recurse into children
        children = node.get("children")
        if children:
            for child in children:
                elements.extend(self._parse_a11y_tree(child, depth + 1, role))

        return elements

    async def _fallback_snapshot(self) -> List[ElementNode]:
        """Fallback snapshot using DOM queries."""
        elements = []

        selectors = [
            ("button", "button"),
            ("a", "link"),
            ("input[type='text'], input[type='email'], input[type='password'], textarea", "textbox"),
            ("input[type='search']", "searchbox"),
            ("input[type='checkbox']", "checkbox"),
            ("input[type='radio']", "radio"),
            ("select", "combobox"),
        ]

        for selector, role in selectors:
            try:
                locators = await self._page.locator(selector).all()
                for loc in locators[:50]:  # Limit per selector
                    try:
                        # Get meaningful name
                        name = None
                        name = await loc.get_attribute("aria-label") or name
                        name = await loc.get_attribute("placeholder") or name
                        name = await loc.get_attribute("title") or name

                        if not name:
                            try:
                                name = await loc.inner_text(timeout=1000)
                            except Exception:
                                pass

                        name = (name or "").strip()[:100]

                        if name:
                            ref = self._make_ref()
                            self._ref_map[ref] = {
                                "role": role,
                                "name": name,
                                "locator": loc,
                            }

                            disabled = False
                            try:
                                disabled = await loc.is_disabled()
                            except Exception:
                                pass

                            elements.append(ElementNode(
                                ref=ref,
                                role=role,
                                name=name,
                                disabled=disabled,
                            ))
                    except Exception:
                        continue
            except Exception:
                continue

        return elements

    def _make_ref(self) -> str:
        """Generate a new element ref (e1, e2, e3, ...)."""
        self._ref_counter += 1
        return f"e{self._ref_counter}"

    async def _get_locator(self, ref: str):
        """Get Playwright locator for a ref."""
        if ref not in self._ref_map:
            return None

        info = self._ref_map[ref]

        # If we have a direct locator, use it
        if "locator" in info:
            return info["locator"]

        # Otherwise find by role and name
        role = info.get("role", "")
        name = info.get("name", "")

        try:
            if role and name:
                # Map roles to Playwright's expected names
                role_map = {
                    "textbox": "textbox",
                    "searchbox": "searchbox",
                    "button": "button",
                    "link": "link",
                    "checkbox": "checkbox",
                    "radio": "radio",
                    "combobox": "combobox",
                }

                mapped_role = role_map.get(role, role)

                try:
                    locator = self._page.get_by_role(mapped_role, name=name, exact=True)
                    if await locator.count() > 0:
                        return locator
                except Exception:
                    pass

                try:
                    locator = self._page.get_by_role(mapped_role, name=name, exact=False)
                    if await locator.count() > 0:
                        return locator
                except Exception:
                    pass

            # Fallback to text search
            if name:
                try:
                    locator = self._page.get_by_text(name, exact=False)
                    if await locator.count() > 0:
                        return locator.first
                except Exception:
                    pass
        except Exception:
            pass

        return None

    async def click(self, ref: str, timeout: int = 5000) -> bool:
        """
        Click an element by ref.

        Args:
            ref: Element ref from snapshot (e.g., "e38")
            timeout: Max time to wait for element (ms)

        Returns:
            True if click succeeded, False otherwise
        """
        try:
            locator = await self._get_locator(ref)
            if not locator:
                logger.error(f"Element ref '{ref}' not found")
                self._metrics["action_failures"] += 1
                return False

            await locator.click(timeout=timeout)
            self._metrics["actions_executed"] += 1
            logger.debug(f"Clicked element {ref}")
            return True

        except Exception as e:
            logger.error(f"Click failed on {ref}: {e}")
            self._metrics["action_failures"] += 1
            return False

    async def type(self, ref: str, text: str, clear: bool = True, timeout: int = 5000) -> bool:
        """
        Type text into an element by ref.

        Args:
            ref: Element ref from snapshot
            text: Text to type
            clear: If True, clear existing text first
            timeout: Max time to wait for element (ms)

        Returns:
            True if typing succeeded, False otherwise
        """
        try:
            locator = await self._get_locator(ref)
            if not locator:
                logger.error(f"Element ref '{ref}' not found")
                self._metrics["action_failures"] += 1
                return False

            if clear:
                await locator.fill(text, timeout=timeout)
            else:
                await locator.press_sequentially(text, timeout=timeout)

            self._metrics["actions_executed"] += 1
            logger.debug(f"Typed '{text[:20]}...' into element {ref}")
            return True

        except Exception as e:
            logger.error(f"Type failed on {ref}: {e}")
            self._metrics["action_failures"] += 1
            return False

    async def run_code(self, js: str) -> Any:
        """
        Execute JavaScript and return JSON-compatible result.

        Args:
            js: JavaScript code to execute
                Can be a function like: "() => document.title"
                Or a statement like: "return document.title"

        Returns:
            Result of the JavaScript execution (JSON-compatible types only)
            Returns None if execution fails
        """
        try:
            # If js is a function string, evaluate it directly
            # If js is a statement, wrap it in a function
            if js.strip().startswith("(") or js.strip().startswith("function"):
                result = await self._page.evaluate(js)
            else:
                # Wrap in function
                wrapped = f"() => {{ {js} }}"
                result = await self._page.evaluate(wrapped)

            logger.debug(f"Executed JavaScript: {js[:50]}...")
            return result

        except Exception as e:
            logger.error(f"JavaScript execution failed: {e}")
            return None

    async def observe(self, network: bool = False, console: bool = False) -> ObserveResult:
        """
        Get network requests and/or console messages.

        Args:
            network: If True, include network requests
            console: If True, include console messages

        Returns:
            ObserveResult with console and/or network data
        """
        result = ObserveResult()

        if console:
            result.console_messages = self._console_messages.copy()

        if network:
            result.network_requests = self._network_requests.copy()

        logger.debug(f"Observe: {len(result.console_messages)} console, {len(result.network_requests)} network")

        return result

    def get_metrics(self) -> Dict[str, Any]:
        """Get performance metrics."""
        metrics = self._metrics.copy()

        # Calculate cache hit rate
        total_snapshots = metrics["snapshots_taken"] + metrics["snapshot_cache_hits"]
        if total_snapshots > 0:
            metrics["cache_hit_rate"] = metrics["snapshot_cache_hits"] / total_snapshots * 100
        else:
            metrics["cache_hit_rate"] = 0.0

        # Calculate success rate
        total_actions = metrics["actions_executed"] + metrics["action_failures"]
        if total_actions > 0:
            metrics["action_success_rate"] = metrics["actions_executed"] / total_actions * 100
        else:
            metrics["action_success_rate"] = 100.0

        return metrics

    @property
    def page(self) -> Page:
        """Get the Playwright page object for advanced usage."""
        return self._page


# === Convenience function ===

async def create_browser(**kwargs) -> DOMFirstBrowser:
    """
    Create and launch a DOMFirstBrowser instance.

    Args:
        **kwargs: Arguments to pass to DOMFirstBrowser constructor

    Returns:
        Launched DOMFirstBrowser instance

    Example:
        browser = await create_browser(headless=False)
        await browser.navigate("https://example.com")
        snapshot = await browser.snapshot()
        await browser.click(snapshot.nodes[0]["ref"])
        await browser.close()
    """
    browser = DOMFirstBrowser(**kwargs)
    await browser.launch()
    return browser


# === Example usage ===

async def example():
    """Example usage of DOMFirstBrowser."""
    print("DOMFirstBrowser Example")
    print("=" * 60)

    async with DOMFirstBrowser(headless=False, slow_mo=500) as browser:
        # Navigate
        print("\n1. Navigating to Google...")
        await browser.navigate("https://google.com")

        # Get snapshot
        print("\n2. Getting snapshot...")
        snapshot = await browser.snapshot()
        print(f"   URL: {snapshot.url}")
        print(f"   Title: {snapshot.title}")
        print(f"   Found {len(snapshot.nodes)} interactive elements")

        # Show first 5 elements
        print("\n   First 5 elements:")
        for node in snapshot.nodes[:5]:
            print(f"   [{node['ref']}] {node['role']} \"{node['name']}\"")

        # Find search box by role
        search_box = None
        for node in snapshot.nodes:
            if node['role'] in ['searchbox', 'textbox'] and 'search' in node['name'].lower():
                search_box = node
                break

        if search_box:
            print(f"\n3. Found search box: [{search_box['ref']}] {search_box['name']}")

            # Type and search
            print(f"\n4. Typing into search box...")
            await browser.type(search_box['ref'], "Playwright automation")

            print(f"\n5. Taking second snapshot (should be cached if no DOM changes)...")
            snapshot2 = await browser.snapshot()
            print(f"   Elements: {len(snapshot2.nodes)}")

            # Run JavaScript
            print(f"\n6. Running JavaScript...")
            title = await browser.run_code("return document.title")
            print(f"   Page title from JS: {title}")

            # Observe
            print(f"\n7. Getting observations...")
            obs = await browser.observe(network=True, console=True)
            print(f"   Console messages: {len(obs.console_messages)}")
            print(f"   Network requests: {len(obs.network_requests)}")

        # Metrics
        print(f"\n8. Performance metrics:")
        metrics = browser.get_metrics()
        for key, value in metrics.items():
            print(f"   {key}: {value}")

    print("\n" + "=" * 60)
    print("Example complete!")


if __name__ == "__main__":
    asyncio.run(example())
