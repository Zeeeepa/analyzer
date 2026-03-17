"""
Accessibility-First Browser Client

This is the primary browser interface for Eversale CLI v2.9+.
Uses accessibility snapshots and element refs (like Playwright MCP).

Why this approach:
- Accessibility refs are STABLE (no selector healing needed)
- Semantic elements are meaningful to LLMs
- Simple: snapshot -> see refs -> click ref -> done

Usage:
    async with A11yBrowser() as browser:
        await browser.navigate("https://google.com")
        snapshot = await browser.snapshot()
        # snapshot shows: [e38] searchbox "Search"
        await browser.click("e38")
        await browser.type("e38", "hello world")
        await browser.press("Enter")
"""

import asyncio
import re
import time
import hashlib
from typing import Optional, Dict, Any, List, Tuple, Set, Union
from dataclasses import dataclass, field
from playwright.async_api import async_playwright, Page, Browser, BrowserContext, Locator
from loguru import logger

try:
    from . import a11y_config as config
except ImportError:
    import a11y_config as config

# Import stealth configuration for anti-bot detection
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
        # Optional import - stealth features will be disabled if not available
        pass

# Import challenge handler for Cloudflare bypass and alternatives
CHALLENGE_HANDLER_AVAILABLE = False
try:
    from .challenge_handler import (
        ChallengeHandler,
        get_challenge_handler,
        BlockedSite,
        ALTERNATIVES
    )
    CHALLENGE_HANDLER_AVAILABLE = True
except ImportError:
    try:
        from challenge_handler import (
            ChallengeHandler,
            get_challenge_handler,
            BlockedSite,
            ALTERNATIVES
        )
        CHALLENGE_HANDLER_AVAILABLE = True
    except ImportError:
        # Optional import - challenge handling will be disabled if not available
        pass

# Import Reddit handler for API-based bypass (Reddit blocks browser automation)
REDDIT_HANDLER_AVAILABLE = False
try:
    from .reddit_handler import (
        RedditHandler,
        is_reddit_url,
        fetch_reddit_data,
    )
    REDDIT_HANDLER_AVAILABLE = True
except ImportError:
    try:
        from reddit_handler import (
            RedditHandler,
            is_reddit_url,
            fetch_reddit_data,
        )
        REDDIT_HANDLER_AVAILABLE = True
    except ImportError:
        # Optional import - Reddit handler will use fallback URL detection
        is_reddit_url = lambda url: "reddit.com" in url.lower()
        pass

# Import search handler for file/content search operations
SEARCH_HANDLER_AVAILABLE = False
try:
    from .search_handler import (
        SearchHandler,
        get_search_handler,
        glob_files,
        grep_content,
        find_files_by_name,
        find_files_containing,
    )
    SEARCH_HANDLER_AVAILABLE = True
except ImportError:
    try:
        from search_handler import (
            SearchHandler,
            get_search_handler,
            glob_files,
            grep_content,
            find_files_by_name,
            find_files_containing,
        )
        SEARCH_HANDLER_AVAILABLE = True
    except ImportError:
        # Optional import - search handler features will be disabled if not available
        pass

# Import CAPTCHA solver for auto-solving CAPTCHAs
CAPTCHA_SOLVER_AVAILABLE = False
try:
    from .captcha_solver import LocalCaptchaSolver
    CAPTCHA_SOLVER_AVAILABLE = True
except ImportError:
    try:
        from captcha_solver import LocalCaptchaSolver
        CAPTCHA_SOLVER_AVAILABLE = True
    except ImportError:
        # Optional import - CAPTCHA solver will be disabled if not available
        pass

# Import date picker handler for date inputs
DATE_PICKER_AVAILABLE = False
try:
    from .date_picker_handler import DatePickerHandler
    DATE_PICKER_AVAILABLE = True
except ImportError:
    try:
        from date_picker_handler import DatePickerHandler
        DATE_PICKER_AVAILABLE = True
    except ImportError:
        # Optional import - date picker handler will be disabled if not available
        pass

# Import complex form handler for multi-field forms
COMPLEX_FORM_AVAILABLE = False
try:
    from .complex_form_handler import ComplexFormHandler
    COMPLEX_FORM_AVAILABLE = True
except ImportError:
    try:
        from complex_form_handler import ComplexFormHandler
        COMPLEX_FORM_AVAILABLE = True
    except ImportError:
        # Optional import - complex form handler will be disabled if not available
        pass

# Import retry handler for automatic retries with fixes
RETRY_HANDLER_AVAILABLE = False
try:
    from .retry_handler_v2 import RetryHandler
    RETRY_HANDLER_AVAILABLE = True
except ImportError:
    try:
        from retry_handler_v2 import RetryHandler
        RETRY_HANDLER_AVAILABLE = True
    except ImportError:
        # Optional import - retry handler will be disabled if not available
        pass


@dataclass
class ElementRef:
    """Represents an accessibility element with its ref."""
    ref: str  # e.g., "e38"
    role: str  # e.g., "button", "textbox", "link"
    name: str  # accessible name
    value: Optional[str] = None
    description: Optional[str] = None
    focused: bool = False
    disabled: bool = False

    def __str__(self) -> str:
        parts = [f"[{self.ref}]", self.role]
        if self.name:
            parts.append(f'"{self.name}"')
        if self.value:
            parts.append(f"value={self.value}")
        if self.focused:
            parts.append("(focused)")
        if self.disabled:
            parts.append("(disabled)")
        return " ".join(parts)

    def __hash__(self) -> int:
        """Hash based on semantic content (role, name, value) for diffing."""
        content = f"{self.role}|{self.name}|{self.value or ''}"
        return int(hashlib.md5(content.encode()).hexdigest()[:16], 16)

    def __eq__(self, other) -> bool:
        """Compare elements by semantic content for diffing."""
        if not isinstance(other, ElementRef):
            return False
        return (self.role == other.role and
                self.name == other.name and
                self.value == other.value)


@dataclass
class SnapshotDiff:
    """Represents the difference between two snapshots."""
    added_elements: List[ElementRef] = field(default_factory=list)
    removed_elements: List[ElementRef] = field(default_factory=list)
    changed_elements: List[ElementRef] = field(default_factory=list)
    url_changed: bool = False
    title_changed: bool = False

    def __str__(self) -> str:
        """Compact string representation for LLM consumption - optimized for token efficiency."""
        if not (self.added_elements or self.removed_elements or self.changed_elements or
                self.url_changed or self.title_changed):
            return "No changes"

        lines = []

        # Only mention URL/title if they actually changed
        if self.url_changed:
            lines.append("URL changed")
        if self.title_changed:
            lines.append("Title changed")

        # Compact format: just ref, role, and name
        if self.added_elements:
            lines.append(f"+{len(self.added_elements)}:")
            for el in self.added_elements:
                # Minimal: [ref] role "name"
                name_part = f' "{el.name}"' if el.name else ''
                lines.append(f"  +[{el.ref}] {el.role}{name_part}")

        if self.removed_elements:
            lines.append(f"-{len(self.removed_elements)}:")
            for el in self.removed_elements:
                name_part = f' "{el.name}"' if el.name else ''
                lines.append(f"  -[{el.ref}] {el.role}{name_part}")

        if self.changed_elements:
            lines.append(f"~{len(self.changed_elements)}:")
            for el in self.changed_elements:
                name_part = f' "{el.name}"' if el.name else ''
                value_part = f' ={el.value}' if el.value else ''
                lines.append(f"  ~[{el.ref}] {el.role}{name_part}{value_part}")

        return "\n".join(lines)


@dataclass
class Snapshot:
    """Accessibility snapshot of the page."""
    url: str
    title: str
    elements: List[ElementRef]
    raw_tree: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        lines = [f"Page: {self.title}", f"URL: {self.url}", "", "Elements:"]
        for el in self.elements:
            lines.append(f"  {el}")
        return "\n".join(lines)

    def find_ref(self, ref: str) -> Optional[ElementRef]:
        """Find element by ref."""
        for el in self.elements:
            if el.ref == ref:
                return el
        return None

    def find_by_role(self, role: str) -> List[ElementRef]:
        """Find elements by role."""
        return [el for el in self.elements if el.role == role]

    def find_by_name(self, name: str, partial: bool = True) -> List[ElementRef]:
        """Find elements by accessible name."""
        name_lower = name.lower()
        if partial:
            return [el for el in self.elements if name_lower in (el.name or "").lower()]
        return [el for el in self.elements if (el.name or "").lower() == name_lower]

    def to_diff(self, previous: Optional['Snapshot']) -> SnapshotDiff:
        """
        Compute the difference between this snapshot and a previous one.
        Returns a SnapshotDiff with only the changes, reducing token usage by 70-80%.

        Args:
            previous: Previous snapshot to compare against, or None for first snapshot

        Returns:
            SnapshotDiff object containing only what changed
        """
        if previous is None:
            # First snapshot - all elements are "added"
            return SnapshotDiff(
                added_elements=self.elements.copy(),
                url_changed=True,
                title_changed=True
            )

        # Build lookup maps by ref for comparison
        prev_by_ref = {el.ref: el for el in previous.elements}
        curr_by_ref = {el.ref: el for el in self.elements}

        # Get all refs
        prev_refs = set(prev_by_ref.keys())
        curr_refs = set(curr_by_ref.keys())

        # Find added refs (in current but not in previous)
        added_refs = curr_refs - prev_refs
        added = [curr_by_ref[ref] for ref in added_refs]

        # Find removed refs (in previous but not in current)
        removed_refs = prev_refs - curr_refs
        removed = [prev_by_ref[ref] for ref in removed_refs]

        # Find changed elements (same ref exists in both, but content differs)
        changed = []
        common_refs = prev_refs & curr_refs
        for ref in common_refs:
            prev_el = prev_by_ref[ref]
            curr_el = curr_by_ref[ref]
            # Compare semantic content (role, name, value, focused, disabled)
            if (prev_el.role != curr_el.role or
                prev_el.name != curr_el.name or
                prev_el.value != curr_el.value or
                prev_el.focused != curr_el.focused or
                prev_el.disabled != curr_el.disabled):
                changed.append(curr_el)

        return SnapshotDiff(
            added_elements=added,
            removed_elements=removed,
            changed_elements=changed,
            url_changed=(self.url != previous.url),
            title_changed=(self.title != previous.title)
        )

    def to_compact_string(self) -> str:
        """
        Return a minimal string representation optimized for token efficiency.
        Omits verbose details and focuses on actionable elements.

        Returns:
            Compact string with just refs, roles, and names
        """
        lines = [f"{self.title} | {self.url}"]

        # Group elements by role for better readability
        by_role: Dict[str, List[ElementRef]] = {}
        for el in self.elements:
            if el.role not in by_role:
                by_role[el.role] = []
            by_role[el.role].append(el)

        # Output grouped by role
        for role in sorted(by_role.keys()):
            elements = by_role[role]
            lines.append(f"\n{role} ({len(elements)}):")
            for el in elements:
                # Minimal format: [ref] "name" value
                parts = [f"[{el.ref}]"]
                if el.name:
                    parts.append(f'"{el.name}"')
                if el.value:
                    parts.append(f"={el.value}")
                lines.append(f"  {' '.join(parts)}")

        return "\n".join(lines)


@dataclass
class ActionResult:
    """Result of a browser action."""
    success: bool
    action: str
    ref: Optional[str] = None
    error: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)


class A11yBrowser:
    """
    Accessibility-first browser client.

    Primary interface for browser automation using accessibility refs.
    This replaces the CSS selector approach with stable, semantic refs.
    """

    # Selector presets for snapshot filtering (40-60% token reduction)
    INTERACTIVE_ONLY = "main, form, [role='dialog'], [role='navigation'], [role='main']"
    FORM_ONLY = "form, [role='form']"
    EXCLUDE_CHROME = ["header", "footer", "aside", "nav", "[role='banner']", "[role='contentinfo']"]

    def __init__(
        self,
        headless: bool = True,
        slow_mo: int = 0,
        viewport: Tuple[int, int] = (1280, 720),
        user_agent: Optional[str] = None,
        auto_show_on_block: bool = True,  # Auto-show browser when manual intervention needed
    ):
        self.headless = headless
        self.slow_mo = slow_mo
        self.viewport = viewport
        self.user_agent = user_agent
        self.auto_show_on_block = auto_show_on_block

        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._initial_headless = headless  # Track initial state for relaunch

        # Ref tracking
        self._ref_counter = 0
        self._ref_map: Dict[str, Any] = {}  # ref -> locator info
        self._last_snapshot: Optional[Snapshot] = None
        self._previous_snapshot: Optional[Snapshot] = None  # For diffing

        # Performance tracking
        self._snapshot_cache: Dict[str, Tuple[Snapshot, float]] = {}  # url -> (snapshot, timestamp)
        self._metrics: Dict[str, Any] = {
            "snapshots_taken": 0,
            "cache_hits": 0,
            "actions_executed": 0,
            "action_failures": 0,
            "total_action_time": 0.0,
        }

        # Tracing state
        self._tracing_active: bool = False

        # Console and network tracking (initialized in launch)
        self._console_messages: List[Dict[str, Any]] = []
        self._network_requests: List[Dict[str, Any]] = []

        # Initialize handlers (lazy-loaded when needed)
        self._retry_handler = RetryHandler(max_retries=3) if RETRY_HANDLER_AVAILABLE else None
        self._date_picker_handler = None  # Initialized on first use
        self._complex_form_handler = None  # Initialized on first use

    async def __aenter__(self) -> "A11yBrowser":
        await self.launch()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        await self.close()
        return False

    async def with_retry(self, action_method: str, **kwargs) -> ActionResult:
        """
        Execute an action with automatic retry on failure.
        Uses RetryHandler to intelligently retry failed actions.

        Args:
            action_method: Name of the action method (e.g., 'click', 'type', 'navigate')
            **kwargs: Arguments to pass to the action method

        Returns:
            ActionResult from the action

        Example:
            result = await browser.with_retry('click', ref='e38')
            result = await browser.with_retry('navigate', url='https://example.com')
        """
        if not self._retry_handler:
            # No retry handler - just execute once
            method = getattr(self, action_method)
            return await method(**kwargs)

        # Execute with retry logic
        async def executor(func_name, args):
            method = getattr(self, func_name)
            result = await method(**args)
            if not result.success:
                raise Exception(result.error or "Action failed")
            return result

        success, result, error = await self._retry_handler.execute_with_retry(
            action_method, kwargs, executor
        )

        if success:
            return result
        else:
            return ActionResult(
                success=False,
                action=action_method,
                error=error or "Retry failed",
                data=kwargs
            )

    async def launch(self) -> None:
        """Launch the browser with stealth anti-detection configuration."""
        self._playwright = await async_playwright().start()

        # Build launch options with stealth args if available
        launch_opts = {
            "headless": self.headless,
            "slow_mo": self.slow_mo,
        }

        if STEALTH_AVAILABLE:
            launch_opts["args"] = get_mcp_compatible_launch_args()
            # Use Chrome channel for better stealth (matches real Chrome)
            launch_opts["channel"] = "chrome"

        try:
            self._browser = await self._playwright.chromium.launch(**launch_opts)
        except Exception:
            # Fallback without channel if Chrome not installed
            launch_opts.pop("channel", None)
            self._browser = await self._playwright.chromium.launch(**launch_opts)

        # Build context options with stealth if available
        context_opts = {
            "viewport": {"width": self.viewport[0], "height": self.viewport[1]},
            "user_agent": self.user_agent,
        }

        if STEALTH_AVAILABLE:
            try:
                stealth_context = get_chrome_context_options()
                # Merge stealth options (don't override viewport/user_agent)
                for key, value in stealth_context.items():
                    if key not in context_opts:
                        context_opts[key] = value
            except Exception:
                pass  # Stealth context options failed, use basic

        self._context = await self._browser.new_context(**context_opts)
        self._page = await self._context.new_page()

        # Set up console message listener
        self._console_messages = []
        self._page.on("console", lambda msg: self._console_messages.append({
            "type": msg.type,
            "text": msg.text,
            "location": msg.location
        }))

        # Set up network request listener
        self._network_requests = []
        self._page.on("request", lambda req: self._network_requests.append({
            "url": req.url,
            "method": req.method,
            "resource_type": req.resource_type
        }))

    async def close(self) -> None:
        """Close the browser."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def show_browser(self) -> None:
        """
        Switch from headless to headful mode for manual intervention.

        This is useful when manual CAPTCHA solving or login is required.
        The browser will relaunch in visible mode with the same page URL.
        """
        if not self.headless:
            # Already visible, nothing to do
            return

        # Save current URL before closing
        current_url = None
        if self._page:
            try:
                current_url = self._page.url
            except Exception as e:
                # Page may be closed or in invalid state - continue with relaunch
                logger.debug(f"Could not get current URL for relaunch: {e}")

        # Close current browser
        await self.close()

        # Relaunch in headful mode
        self.headless = False
        await self.launch()

        # Navigate back to the same URL if we had one
        if current_url and current_url != "about:blank":
            try:
                await self.navigate(current_url)
            except Exception:
                pass  # If navigation fails, user can manually navigate

    @property
    def page(self) -> Page:
        """Get the current page."""
        if not self._page:
            raise RuntimeError("Browser not launched. Call launch() first.")
        return self._page

    # === Core Actions ===

    async def navigate(
        self,
        url: str,
        wait_until: str = "domcontentloaded",
        auto_handle_blocks: bool = True,
        search_query: Optional[str] = None
    ) -> ActionResult:
        """
        Navigate to a URL with automatic block handling.

        Args:
            url: URL to navigate to (auto-adds https:// if missing)
            wait_until: When to consider navigation complete
            auto_handle_blocks: If True, automatically try alternatives when blocked
            search_query: Optional search query for finding alternatives

        Features:
            - Reddit URLs: Auto-bypass via JSON/RSS API if browser blocked
            - Cloudflare: Auto-wait for JS challenge, then try alternatives
            - Other blocks: Try configured alternatives from challenge_handler
        """
        try:
            # Add https if missing
            if not url.startswith(("http://", "https://")):
                url = f"https://{url}"

            # Special handling for Reddit URLs - use API bypass proactively
            if REDDIT_HANDLER_AVAILABLE and is_reddit_url(url):
                return await self._navigate_reddit(url, search_query)

            # Standard navigation
            await self.page.goto(url, wait_until=wait_until, timeout=30000)

            # Check if we got blocked
            block_check = await self._check_if_blocked()

            if block_check and auto_handle_blocks:
                # Try to handle the block automatically
                handled = await self._handle_block(url, block_check, search_query)
                if handled.success:
                    return handled
                # If handling failed, return the block info
                return ActionResult(
                    success=False,
                    action="navigate",
                    error=f"Site blocked: {block_check} (auto-handle failed)",
                    data={"url": url, "blocked": True, "block_reason": block_check, "alternatives_tried": True}
                )
            elif block_check:
                return ActionResult(
                    success=False,
                    action="navigate",
                    error=f"Site blocked: {block_check}",
                    data={"url": url, "blocked": True, "block_reason": block_check}
                )

            return ActionResult(success=True, action="navigate", data={"url": url})
        except Exception as e:
            return ActionResult(success=False, action="navigate", error=str(e), data={"url": url})

    async def _navigate_reddit(self, url: str, search_query: Optional[str] = None) -> ActionResult:
        """
        Navigate to Reddit using API bypass instead of browser.
        Reddit aggressively blocks automation, so we use their JSON/RSS API.
        """
        try:
            # Try browser first (might work sometimes)
            await self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
            block_check = await self._check_if_blocked()

            if not block_check:
                # Browser worked!
                return ActionResult(success=True, action="navigate", data={"url": url, "method": "browser"})

            # Browser blocked - use API bypass
            if REDDIT_HANDLER_AVAILABLE:
                handler = RedditHandler()

                # Try to fetch via API
                result = await fetch_reddit_data(url)
                if result and result.get("success"):
                    return ActionResult(
                        success=True,
                        action="navigate",
                        data={
                            "url": url,
                            "method": "reddit_api",
                            "api_data": result,
                            "message": "Reddit data fetched via API (browser was blocked)"
                        }
                    )

            # API also failed
            return ActionResult(
                success=False,
                action="navigate",
                error="Reddit blocked browser and API fallback failed",
                data={"url": url, "blocked": True}
            )
        except Exception as e:
            return ActionResult(success=False, action="navigate", error=str(e), data={"url": url})

    async def _handle_block(self, url: str, block_reason: str, search_query: Optional[str] = None) -> ActionResult:
        """
        Handle a blocked page by trying bypass strategies and alternatives.

        Strategy order:
        1. Try CAPTCHA solving (if CAPTCHA detected)
        2. Wait for Cloudflare JS challenge (if applicable)
        3. Try configured alternative sources
        4. Return failure if all fail
        """
        try:
            # Step 1: Try CAPTCHA solving if CAPTCHA detected
            if CAPTCHA_SOLVER_AVAILABLE and "captcha" in block_reason.lower():
                try:
                    solver = LocalCaptchaSolver(page=self.page)
                    solved = await solver.solve_and_inject(auto_fallback=True)
                    if solved:
                        # Wait for page to update after CAPTCHA solve (network requests complete)
                        try:
                            await self.page.wait_for_load_state('networkidle', timeout=3000)
                        except Exception:
                            # Fallback to brief wait if networkidle times out
                            await asyncio.sleep(0.5)
                        # Re-check if still blocked
                        still_blocked = await self._check_if_blocked()
                        if not still_blocked:
                            return ActionResult(
                                success=True,
                                action="navigate",
                                data={"url": url, "method": "captcha_solved"}
                            )
                except Exception:
                    pass  # CAPTCHA solving failed, continue to other strategies

            if not CHALLENGE_HANDLER_AVAILABLE:
                return ActionResult(
                    success=False,
                    action="handle_block",
                    error="Challenge handler not available",
                    data={"url": url, "block_reason": block_reason}
                )

            handler = get_challenge_handler()

            # Step 2: Try Cloudflare bypass (wait for JS challenge)
            if "cloudflare" in block_reason.lower():
                bypassed = await handler.try_bypass_cloudflare(self.page)
                if bypassed:
                    return ActionResult(
                        success=True,
                        action="navigate",
                        data={"url": url, "method": "cloudflare_bypass"}
                    )

            # Step 3: Detect which site is blocked and try alternatives
            blocked_site = handler.detect_blocked_site(url)

            if blocked_site != BlockedSite.UNKNOWN:
                alternatives = handler.get_alternatives(blocked_site)
                query = search_query or self._extract_query_from_url(url)

                for alt in alternatives:
                    try:
                        alt_url = alt.url_template.format(query=query.replace(" ", "+") if query else "")
                        await self.page.goto(alt_url, wait_until="domcontentloaded", timeout=15000)

                        # Check if alternative is also blocked
                        alt_block = await self._check_if_blocked()
                        if not alt_block:
                            return ActionResult(
                                success=True,
                                action="navigate",
                                data={
                                    "url": alt_url,
                                    "original_url": url,
                                    "method": "alternative",
                                    "alternative_source": alt.name
                                }
                            )
                    except Exception:
                        continue  # Try next alternative

            # Step 4: All automated strategies failed - show browser for manual intervention
            if self.auto_show_on_block and self.headless:
                logger.info(f"[a11y] Automated bypass failed for {url}, showing browser for manual intervention")
                await self.show_browser()

                # Wait for user to solve the challenge (poll for up to 120 seconds)
                for _ in range(60):  # 60 x 2s = 120s timeout
                    await asyncio.sleep(2)
                    still_blocked = await self._check_if_blocked()
                    if not still_blocked:
                        logger.info("[a11y] Challenge resolved by user")
                        return ActionResult(
                            success=True,
                            action="navigate",
                            data={"url": self.page.url, "method": "manual_intervention"}
                        )

                # Timeout waiting for user
                return ActionResult(
                    success=False,
                    action="handle_block",
                    error="Manual intervention timeout - challenge not resolved",
                    data={"url": url, "block_reason": block_reason, "manual_timeout": True}
                )

            return ActionResult(
                success=False,
                action="handle_block",
                error="All bypass and alternative strategies failed",
                data={"url": url, "block_reason": block_reason}
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action="handle_block",
                error=str(e),
                data={"url": url}
            )

    def _extract_query_from_url(self, url: str) -> str:
        """Extract search query from URL parameters."""
        try:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            # Common query parameter names
            for key in ['q', 'query', 'search', 'keyword', 'keywords', 's']:
                if key in params:
                    return params[key][0]
            # Try to extract from path (e.g., /search/keyword)
            if '/search/' in parsed.path:
                return parsed.path.split('/search/')[-1].split('/')[0]
            return ""
        except Exception:
            return ""

    async def search_files(
        self,
        pattern: str,
        path: str = ".",
        include_hidden: bool = False
    ) -> ActionResult:
        """
        Search for files matching a glob pattern using SearchHandler.

        Args:
            pattern: Glob pattern (e.g., "*.py", "**/*.ts")
            path: Directory to search in
            include_hidden: Include hidden files/directories

        Returns:
            ActionResult with matching files in data dict

        Example:
            result = await browser.search_files("*.py", "/home/user/project")
            if result.success:
                files = result.data["files"]
        """
        if not SEARCH_HANDLER_AVAILABLE:
            return ActionResult(
                success=False,
                action="search_files",
                error="SearchHandler not available",
                data={"pattern": pattern, "path": path}
            )

        try:
            handler = get_search_handler()
            search_result = handler.glob_search(pattern, path, include_hidden)

            return ActionResult(
                success=True,
                action="search_files",
                data={
                    "files": search_result.files,
                    "total_found": search_result.total_found,
                    "truncated": search_result.truncated,
                    "pattern": pattern,
                    "path": search_result.search_path,
                    "formatted": search_result.to_llm_format()
                }
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action="search_files",
                error=str(e),
                data={"pattern": pattern, "path": path}
            )

    async def search_content(
        self,
        pattern: str,
        path: str = ".",
        file_pattern: Optional[str] = None,
        context_lines: int = 2,
        case_sensitive: bool = True
    ) -> ActionResult:
        """
        Search file contents for a pattern using SearchHandler.

        Args:
            pattern: Search pattern (regex or literal)
            path: File or directory to search
            file_pattern: Glob pattern to filter files (e.g., "*.py")
            context_lines: Lines before/after match to include
            case_sensitive: Case sensitive search

        Returns:
            ActionResult with matches in data dict

        Example:
            result = await browser.search_content("def main", ".", "*.py")
            if result.success:
                matches = result.data["matches"]
        """
        if not SEARCH_HANDLER_AVAILABLE:
            return ActionResult(
                success=False,
                action="search_content",
                error="SearchHandler not available",
                data={"pattern": pattern, "path": path}
            )

        try:
            handler = get_search_handler()
            search_result = handler.grep_search(
                pattern,
                path,
                file_pattern=file_pattern,
                context_lines=context_lines,
                case_sensitive=case_sensitive
            )

            return ActionResult(
                success=True,
                action="search_content",
                data={
                    "matches": [
                        {
                            "file": m.file_path,
                            "line": m.line_number,
                            "content": m.content,
                            "context_before": m.context_before,
                            "context_after": m.context_after
                        }
                        for m in search_result.matches
                    ],
                    "total_matches": search_result.total_matches,
                    "files_searched": search_result.files_searched,
                    "truncated": search_result.truncated,
                    "pattern": pattern,
                    "formatted": search_result.to_llm_format()
                }
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action="search_content",
                error=str(e),
                data={"pattern": pattern, "path": path}
            )

    async def find_files(
        self,
        name: str,
        path: str = "."
    ) -> ActionResult:
        """
        Find files by exact name using SearchHandler.

        Args:
            name: Exact filename to search for
            path: Directory to search in

        Returns:
            ActionResult with matching file paths in data dict

        Example:
            result = await browser.find_files("config.yaml", "/home/user")
            if result.success:
                files = result.data["files"]
        """
        if not SEARCH_HANDLER_AVAILABLE:
            return ActionResult(
                success=False,
                action="find_files",
                error="SearchHandler not available",
                data={"name": name, "path": path}
            )

        try:
            files = find_files_by_name(name, path)
            return ActionResult(
                success=True,
                action="find_files",
                data={
                    "files": files,
                    "name": name,
                    "path": path
                }
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action="find_files",
                error=str(e),
                data={"name": name, "path": path}
            )

    async def find_files_containing(
        self,
        pattern: str,
        path: str = "."
    ) -> ActionResult:
        """
        Find files containing a pattern using SearchHandler.

        Args:
            pattern: Pattern to search for in file contents
            path: Directory to search in

        Returns:
            ActionResult with file paths containing the pattern in data dict

        Example:
            result = await browser.find_files_containing("TODO", ".")
            if result.success:
                files = result.data["files"]
        """
        if not SEARCH_HANDLER_AVAILABLE:
            return ActionResult(
                success=False,
                action="find_files_containing",
                error="SearchHandler not available",
                data={"pattern": pattern, "path": path}
            )

        try:
            files = find_files_containing(pattern, path)
            return ActionResult(
                success=True,
                action="find_files_containing",
                data={
                    "files": files,
                    "pattern": pattern,
                    "path": path
                }
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action="find_files_containing",
                error=str(e),
                data={"pattern": pattern, "path": path}
            )

    async def _check_if_blocked(self) -> Optional[str]:
        """
        Check if the current page shows a block/captcha.
        Returns block reason if blocked, None if not blocked.
        """
        try:
            # Common block indicators
            page_text = await self.page.content()
            page_text_lower = page_text.lower()

            # Reddit block
            if "blocked by network security" in page_text_lower:
                return "Reddit network security block"

            # Google CAPTCHA
            if "unusual traffic" in page_text_lower and "robot" in page_text_lower:
                return "Google CAPTCHA"

            # Cloudflare
            if "checking your browser" in page_text_lower or "cloudflare" in page_text_lower:
                if "just a moment" in page_text_lower or "please wait" in page_text_lower:
                    return "Cloudflare challenge"

            # Generic 403/429
            title = await self.page.title()
            if "403" in title or "forbidden" in title.lower():
                return "403 Forbidden"
            if "429" in title or "too many" in title.lower():
                return "429 Too Many Requests"

            return None
        except Exception:
            return None

    async def snapshot(
        self,
        force: bool = False,
        diff_mode: bool = False,
        selector: Optional[str] = None,
        exclude_selectors: Optional[List[str]] = None
    ) -> Union[Snapshot, SnapshotDiff]:
        """
        Get accessibility snapshot of the page.

        Returns a Snapshot with all interactive elements and their refs.
        This is the PRIMARY way to understand page state.

        The snapshot includes:
        - All interactive elements (buttons, links, inputs, etc.)
        - Their accessibility roles and names
        - Stable refs that can be used for actions

        Args:
            force: If True, bypass cache and force new snapshot
            diff_mode: If True, only return elements that changed since last snapshot
            selector: CSS selector to filter snapshot to specific containers (40-60% token reduction)
            exclude_selectors: List of CSS selectors to exclude from snapshot (e.g., headers, footers)

        Example:
            # Full snapshot
            snapshot = await browser.snapshot()

            # Focus on forms only (reduces tokens)
            snapshot = await browser.snapshot(selector=A11yBrowser.FORM_ONLY)

            # Exclude page chrome (headers, footers, nav)
            snapshot = await browser.snapshot(exclude_selectors=A11yBrowser.EXCLUDE_CHROME)

            # Combine both
            snapshot = await browser.snapshot(
                selector="main",
                exclude_selectors=["footer", "aside"]
            )
        """
        # Use config defaults if not specified
        if selector is None:
            selector = config.DEFAULT_SNAPSHOT_SELECTOR
        if exclude_selectors is None:
            exclude_selectors = config.DEFAULT_EXCLUDE_SELECTORS or []

        current_url = self.page.url
        current_time = time.time()

        # Check cache if enabled
        if config.ENABLE_SNAPSHOT_CACHE and not force and current_url in self._snapshot_cache:
            cached_snapshot, cached_time = self._snapshot_cache[current_url]
            age = current_time - cached_time

            if age < config.SNAPSHOT_CACHE_TTL:
                self._metrics["cache_hits"] += 1
                if config.LOG_METRICS:
                    print(f"[a11y] Cache hit for {current_url} (age: {age:.2f}s)")
                # FIX: Update _previous_snapshot even on cache hit for diff mode
                self._previous_snapshot = cached_snapshot
                return cached_snapshot

        # Reset refs for new snapshot
        self._ref_counter = 0
        self._ref_map = {}
        elements = []
        raw_tree = None

        start_time = time.time()

        try:
            # Get accessibility tree from Playwright
            if config.ENABLE_A11Y_TREE:
                raw_tree = await asyncio.wait_for(
                    self.page.accessibility.snapshot(),
                    timeout=config.DEFAULT_TIMEOUT / 1000
                )
                if raw_tree:
                    # Debug: log what Playwright returned
                    if config.LOG_SNAPSHOTS:
                        children_count = len(raw_tree.get("children", []))
                        print(f"[a11y] Raw tree role: {raw_tree.get('role')}, name: {raw_tree.get('name')[:50] if raw_tree.get('name') else 'None'}, children: {children_count}")
                    elements = self._parse_a11y_tree(raw_tree)
                    if config.LOG_SNAPSHOTS:
                        print(f"[a11y] Parsed {len(elements)} elements from tree")
        except asyncio.TimeoutError:
            if config.LOG_ERRORS:
                print("[a11y] Accessibility snapshot timed out")
        except Exception as e:
            if config.LOG_ERRORS:
                print(f"[a11y] Accessibility tree error: {e}")

        # If accessibility tree gave few elements, supplement with DOM fallback
        fallback_threshold = getattr(config, 'FALLBACK_ELEMENT_THRESHOLD', 20)
        if config.ENABLE_FALLBACK_SNAPSHOT and len(elements) < fallback_threshold:
            fallback_elements = await self._fallback_snapshot()
            # Merge, avoiding duplicates by name
            existing_names = {el.name.lower() for el in elements if el.name}
            for el in fallback_elements:
                if el.name and el.name.lower() not in existing_names:
                    elements.append(el)
                    existing_names.add(el.name.lower())

        # Apply selector-based filtering (40-60% token reduction)
        if selector or exclude_selectors:
            elements = await self._filter_elements_by_selector(
                elements, selector, exclude_selectors
            )
            if config.LOG_SNAPSHOTS:
                print(f"[a11y] After filtering: {len(elements)} elements")

        # Limit elements to prevent huge snapshots
        elements = elements[:config.MAX_ELEMENTS_PER_SNAPSHOT]

        snapshot = Snapshot(
            url=current_url,
            title=await self.page.title(),
            elements=elements,
            raw_tree=raw_tree or {},
        )

        # Update metrics
        self._metrics["snapshots_taken"] += 1
        snapshot_time = time.time() - start_time

        if config.LOG_METRICS and snapshot_time > config.PERFORMANCE_WARNING_THRESHOLD:
            print(f"[a11y] Slow snapshot: {snapshot_time:.2f}s ({len(elements)} elements)")

        # Cache the snapshot
        if config.ENABLE_SNAPSHOT_CACHE:
            self._snapshot_cache[current_url] = (snapshot, current_time)
            # Limit cache size
            if len(self._snapshot_cache) > config.SNAPSHOT_CACHE_SIZE:
                # Remove oldest entry
                oldest_url = min(self._snapshot_cache.keys(),
                               key=lambda k: self._snapshot_cache[k][1])
                del self._snapshot_cache[oldest_url]

        # Handle diff mode - return only changes from previous snapshot
        if diff_mode:
            diff = snapshot.to_diff(self._previous_snapshot)
            # Store current snapshot as previous for next diff
            self._previous_snapshot = snapshot
            self._last_snapshot = snapshot

            if config.LOG_SNAPSHOTS:
                added_count = len(diff.added_elements)
                removed_count = len(diff.removed_elements)
                changed_count = len(diff.changed_elements)
                print(f"[a11y] Snapshot diff: +{added_count} -{removed_count} ~{changed_count} in {snapshot_time:.2f}s")

            return diff

        # Normal mode - return full snapshot
        self._previous_snapshot = snapshot
        self._last_snapshot = snapshot

        if config.LOG_SNAPSHOTS:
            print(f"[a11y] Snapshot: {len(elements)} elements in {snapshot_time:.2f}s")

        return snapshot

    def _parse_a11y_tree(self, node: Dict, depth: int = 0, parent_role: str = "") -> List[ElementRef]:
        """
        Parse accessibility tree into ElementRef list.

        Recursively traverses the tree and extracts meaningful interactive elements.
        Filters out structural elements and focuses on actionable UI.

        Optimized for performance with early returns and minimal allocations.
        """
        elements = []

        role = node.get("role", "")
        name = node.get("name", "")
        value = node.get("value")

        # Also include text nodes with meaningful content (not just whitespace)
        is_meaningful_text = (
            role == "text" and
            name and
            len(name.strip()) > 0 and
            parent_role not in {"button", "link"}  # Avoid duplicate text inside buttons
        )

        if role in config.INTERACTIVE_ROLES or is_meaningful_text:
            ref = self._make_ref()
            self._ref_map[ref] = {
                "role": role,
                "name": name,
                "node": node,
            }

            elements.append(ElementRef(
                ref=ref,
                role=role,
                name=name or "",
                value=value,
                description=node.get("description"),
                focused=node.get("focused", False),
                disabled=node.get("disabled", False),
            ))

    async def _filter_elements_by_selector(
        self,
        elements: List[ElementRef],
        selector: Optional[str] = None,
        exclude_selectors: Optional[List[str]] = None
    ) -> List[ElementRef]:
        """
        Filter elements to only those within/outside selector containers.

        Reduces snapshot token count by 40-60% by focusing on relevant page sections.

        Args:
            elements: List of ElementRef to filter
            selector: CSS selector for containers to include (e.g., "main, form")
            exclude_selectors: List of CSS selectors to exclude (e.g., ["footer", "aside"])

        Returns:
            Filtered list of ElementRef

        Example:
            # Only elements in main content area
            filtered = await self._filter_elements_by_selector(
                elements, selector="main"
            )

            # Exclude headers and footers
            filtered = await self._filter_elements_by_selector(
                elements, exclude_selectors=["header", "footer"]
            )
        """
        if not elements:
            return elements

        filtered = []

        try:
            # Build sets of DOM elements to include/exclude
            include_containers = []
            exclude_containers = []

            if selector:
                # Find all matching container elements
                include_containers = await self.page.query_selector_all(selector)

            if exclude_selectors:
                # Find all elements to exclude
                for excl_sel in exclude_selectors:
                    exclude_containers.extend(
                        await self.page.query_selector_all(excl_sel)
                    )

            # Filter elements based on their position in DOM
            for el_ref in elements:
                try:
                    # Get the actual DOM element for this ref
                    # Use ref_map to locate the element
                    ref_data = self._ref_map.get(el_ref.ref)
                    if not ref_data:
                        continue

                    # Try to find element by role and name
                    role = el_ref.role
                    name = el_ref.name

                    # Build selector for this element
                    if role == "button":
                        locator = self.page.get_by_role("button", name=name) if name else self.page.locator("button")
                    elif role == "link":
                        locator = self.page.get_by_role("link", name=name) if name else self.page.locator("a")
                    elif role == "textbox":
                        locator = self.page.get_by_role("textbox", name=name) if name else self.page.locator("input[type='text'], textarea")
                    else:
                        # Generic role-based locator
                        locator = self.page.get_by_role(role, name=name) if name else self.page.locator(f"[role='{role}']")

                    # Get the first matching element
                    element_handle = await locator.element_handle()
                    if not element_handle:
                        # Can't locate element, skip it if selector filtering is active
                        if not selector:
                            filtered.append(el_ref)
                        continue

                    # Check if element should be excluded
                    should_exclude = False
                    if exclude_containers:
                        for container in exclude_containers:
                            # Check if element is inside an excluded container
                            is_inside = await element_handle.evaluate(
                                "(el, container) => container.contains(el)",
                                container
                            )
                            if is_inside:
                                should_exclude = True
                                break

                    if should_exclude:
                        continue

                    # Check if element should be included
                    should_include = not selector  # Include by default if no selector
                    if include_containers:
                        for container in include_containers:
                            # Check if element is inside an included container
                            is_inside = await element_handle.evaluate(
                                "(el, container) => container.contains(el)",
                                container
                            )
                            if is_inside:
                                should_include = True
                                break

                    if should_include:
                        filtered.append(el_ref)

                except Exception as e:
                    # If we can't determine element location, include it if no selector
                    if not selector:
                        filtered.append(el_ref)
                    if config.LOG_ERRORS:
                        print(f"[a11y] Filter error for {el_ref.ref}: {e}")

        except Exception as e:
            if config.LOG_ERRORS:
                print(f"[a11y] Selector filtering failed: {e}")
            # On error, return unfiltered elements
            return elements

        return filtered
        # Recurse into children
        children = node.get("children")
        if children:
            for child in children:
                elements.extend(self._parse_a11y_tree(child, depth + 1, role))

        return elements

    async def _fallback_snapshot(self) -> List[ElementRef]:
        """
        Fallback snapshot using DOM queries.

        Used when accessibility tree is unavailable or incomplete.
        Queries common interactive elements directly from DOM.

        Optimized with parallel element resolution when enabled.
        """
        elements = []

        # Use configured selectors
        selectors = config.FALLBACK_SELECTORS

        if config.PARALLEL_ELEMENT_RESOLUTION:
            # Parallel resolution for better performance
            tasks = []
            for selector, role in selectors:
                tasks.append(self._process_selector(selector, role))

            # Process selectors in batches
            batch_size = config.MAX_PARALLEL_RESOLUTIONS
            for i in range(0, len(tasks), batch_size):
                batch = tasks[i:i + batch_size]
                results = await asyncio.gather(*batch, return_exceptions=True)
                for result in results:
                    if isinstance(result, list):
                        elements.extend(result)
        else:
            # Sequential resolution (original approach)
            for selector, role in selectors:
                try:
                    batch_elements = await self._process_selector(selector, role)
                    elements.extend(batch_elements)
                except Exception as e:
                    if config.LOG_ERRORS:
                        print(f"[a11y] Failed to process selector '{selector}' for role '{role}': {e}")
                    continue

        return elements

    async def _process_selector(self, selector: str, role: str) -> List[ElementRef]:
        """Process a single selector and return its elements."""
        elements = []

        try:
            locators = await self.page.locator(selector).all()
            for loc in locators[:config.FALLBACK_ELEMENT_LIMIT]:
                try:
                    # Try multiple strategies to get meaningful name
                    name = None

                    # Try aria-label first (most semantic)
                    name = await loc.get_attribute("aria-label")

                    # Try placeholder for inputs
                    if not name:
                        name = await loc.get_attribute("placeholder")

                    # Try title attribute
                    if not name:
                        name = await loc.get_attribute("title")

                    # Try alt for images
                    if not name:
                        name = await loc.get_attribute("alt")

                    # Try visible text (with timeout to avoid hanging)
                    if not name:
                        try:
                            name = await loc.inner_text(timeout=1000)
                        except (TimeoutError, Exception) as e:
                            if config.LOG_ERRORS:
                                print(f"[a11y] Failed to extract inner_text for {selector}: {e}")
                            pass

                    # Try value for inputs
                    if not name:
                        name = await loc.get_attribute("value")

                    # Clean up name
                    name = (name or "").strip()
                    name = re.sub(r'\s+', ' ', name)  # Normalize whitespace
                    name = name[:100]  # Truncate very long names

                    if name:
                        ref = self._make_ref()
                        self._ref_map[ref] = {
                            "role": role,
                            "name": name,
                            "locator": loc,
                        }

                        # Check if disabled
                        disabled = False
                        if role in {"button", "textbox", "checkbox"}:
                            try:
                                disabled = await loc.is_disabled()
                            except (TimeoutError, AttributeError) as e:
                                if config.LOG_ERRORS:
                                    print(f"[a11y] Failed to check disabled state for {role} '{name}': {e}")
                                pass

                        elements.append(ElementRef(
                            ref=ref,
                            role=role,
                            name=name,
                            disabled=disabled,
                        ))
                except Exception as e:
                    # Element became stale or invisible - skip it
                    if config.LOG_ERRORS:
                        print(f"[a11y] Element became stale or invisible during processing (selector: {selector}): {e}")
                    continue
        except Exception as e:
            # Selector failed - return empty list
            if config.LOG_ERRORS:
                print(f"[a11y] Selector query failed for '{selector}': {e}")
            pass

        return elements

    def _make_ref(self) -> str:
        """Generate a new element ref (e1, e2, e3, ...)."""
        self._ref_counter += 1
        return f"e{self._ref_counter}"

    async def _get_locator(self, ref: str) -> Optional[Locator]:
        """
        Get Playwright locator for a ref.

        Tries multiple strategies:
        1. Direct locator (from fallback snapshot)
        2. Role-based locator (from accessibility tree)
        3. Text-based locator (fallback)
        """
        if ref not in self._ref_map:
            return None

        info = self._ref_map[ref]

        # If we have a direct locator (from fallback), use it
        if "locator" in info:
            return info["locator"]

        # Otherwise, find by role and name from accessibility tree
        role = info.get("role", "")
        name = info.get("name", "")

        try:
            # Try role-based locator (most reliable for a11y tree)
            if role and name:
                # Map some roles to Playwright's expected names
                role_map = {
                    "textbox": "textbox",
                    "searchbox": "searchbox",
                    "button": "button",
                    "link": "link",
                    "checkbox": "checkbox",
                    "radio": "radio",
                    "combobox": "combobox",
                    "slider": "slider",
                    "spinbutton": "spinbutton",
                    "tab": "tab",
                    "menuitem": "menuitem",
                    "option": "option",
                    "heading": "heading",
                    "img": "img",
                }

                mapped_role = role_map.get(role, role)

                try:
                    # Try exact name match
                    locator = self.page.get_by_role(mapped_role, name=name, exact=True)
                    # Verify it exists
                    if await locator.count() > 0:
                        return locator
                except Exception as e:
                    if config.LOG_ERRORS:
                        print(f"[a11y] get_by_role exact match failed for role '{mapped_role}', name '{name}': {e}")
                    pass

                try:
                    # Try partial name match
                    locator = self.page.get_by_role(mapped_role, name=name, exact=False)
                    if await locator.count() > 0:
                        return locator
                except Exception as e:
                    if config.LOG_ERRORS:
                        print(f"[a11y] get_by_role partial match failed for role '{mapped_role}', name '{name}': {e}")
                    pass

            # Fallback to text search if role didn't work
            if name:
                try:
                    locator = self.page.get_by_text(name, exact=False)
                    if await locator.count() > 0:
                        return locator.first
                except Exception as e:
                    if config.LOG_ERRORS:
                        print(f"[a11y] get_by_text failed for name '{name}': {e}")
                    pass
        except Exception as e:
            if config.LOG_ERRORS:
                print(f"[a11y] _get_locator failed for ref '{ref}': {e}")
            pass

        return None

    async def _track_action(self, action_func, *args, **kwargs) -> ActionResult:
        """Track action execution time and success/failure."""
        start_time = time.time()
        self._metrics["actions_executed"] += 1

        try:
            result = await action_func(*args, **kwargs)
            if not result.success:
                self._metrics["action_failures"] += 1
            return result
        except Exception as e:
            self._metrics["action_failures"] += 1
            raise
        finally:
            action_time = time.time() - start_time
            self._metrics["total_action_time"] += action_time

            if config.LOG_ACTIONS:
                status = "OK" if result.success else "FAIL"
                print(f"[a11y] {result.action} {status} ({action_time:.2f}s)")

    async def _tab_to_element(self, ref: str, max_tabs: int = None) -> bool:
        """
        Navigate to element using Tab key.

        Args:
            ref: Element ref to navigate to
            max_tabs: Maximum Tab presses to try (defaults to config.MAX_TAB_ATTEMPTS)

        Returns:
            True if element was successfully focused
        """
        if max_tabs is None:
            max_tabs = config.MAX_TAB_ATTEMPTS

        target = self._ref_map.get(ref)
        if not target:
            return False

        target_name = target.get("name", "").lower()
        target_role = target.get("role", "").lower()

        for i in range(max_tabs):
            try:
                await self.page.keyboard.press("Tab")
                await asyncio.sleep(config.KEYBOARD_FALLBACK_DELAY)

                # Get currently focused element info
                focused_info = await self.page.evaluate("""() => {
                    const el = document.activeElement;
                    if (!el) return null;
                    return {
                        tag: el.tagName.toLowerCase(),
                        text: (el.textContent || el.value || el.placeholder || '').trim().toLowerCase(),
                        role: el.getAttribute('role') || '',
                        ariaLabel: el.getAttribute('aria-label') || '',
                        name: el.getAttribute('name') || '',
                        id: el.id || ''
                    };
                }""")

                if not focused_info:
                    continue

                # Check if focused element matches target
                focused_text = focused_info.get("text", "").lower()
                focused_role = focused_info.get("role", "").lower()
                focused_label = focused_info.get("ariaLabel", "").lower()

                # Match by name or label
                if target_name and (
                    target_name in focused_text or
                    target_name in focused_label or
                    focused_text in target_name or
                    focused_label in target_name
                ):
                    if config.LOG_ACTIONS:
                        print(f"[a11y] Tab navigation found element after {i+1} tabs")
                    return True

                # Match by role
                if target_role and focused_role and target_role == focused_role:
                    if target_name and (target_name in focused_text or target_name in focused_label):
                        if config.LOG_ACTIONS:
                            print(f"[a11y] Tab navigation found element after {i+1} tabs")
                        return True

            except Exception as e:
                if config.LOG_ERRORS:
                    print(f"[a11y] Error during Tab navigation: {e}")
                continue

        return False


    async def _keyboard_fallback(self, ref: str, action: str = "activate") -> bool:
        """
        Fallback to keyboard navigation when mouse interaction fails.

        Strategy:
        1. Try Tab navigation to reach element
        2. Press Enter/Space to activate
        3. For inputs, focus and type directly

        Args:
            ref: Element ref to interact with
            action: Type of action (click, activate, focus)

        Returns:
            True if fallback succeeded
        """
        if not config.ENABLE_KEYBOARD_FALLBACK:
            return False

        if config.LOG_ACTIONS:
            print(f"[a11y] Attempting keyboard fallback for {ref} (action: {action})")

        try:
            # Try to navigate to element with Tab
            if await self._tab_to_element(ref):
                # Element is now focused

                target = self._ref_map.get(ref)
                if not target:
                    return False

                target_role = target.get("role", "").lower()

                # Different activation strategies based on element role
                if action == "click" or action == "activate":
                    if target_role in ["button", "link", "tab", "menuitem", "option"]:
                        # Press Enter to activate
                        await self.page.keyboard.press("Enter")
                        await asyncio.sleep(0.2)
                        if config.LOG_ACTIONS:
                            print(f"[a11y] Keyboard fallback: pressed Enter")
                        return True
                    elif target_role in ["checkbox", "radio", "switch"]:
                        # Press Space to toggle
                        await self.page.keyboard.press("Space")
                        await asyncio.sleep(0.2)
                        if config.LOG_ACTIONS:
                            print(f"[a11y] Keyboard fallback: pressed Space")
                        return True
                    else:
                        # Try Enter first, then Space
                        await self.page.keyboard.press("Enter")
                        await asyncio.sleep(0.1)
                        if config.LOG_ACTIONS:
                            print(f"[a11y] Keyboard fallback: pressed Enter (generic)")
                        return True
                elif action == "focus":
                    # Already focused by Tab navigation
                    return True

            else:
                # Tab navigation didn't work, try direct focus via JavaScript
                locator = await self._get_locator(ref)
                if locator:
                    # Try to focus element directly
                    await locator.focus()
                    await asyncio.sleep(0.1)

                    # Then press Enter
                    await self.page.keyboard.press("Enter")
                    await asyncio.sleep(0.2)

                    if config.LOG_ACTIONS:
                        print(f"[a11y] Keyboard fallback: direct focus + Enter")
                    return True

        except Exception as e:
            if config.LOG_ERRORS:
                print(f"[a11y] Keyboard fallback failed: {e}")
            return False

        return False


    async def click(self, ref: str, timeout: int = None) -> ActionResult:
        """
        Click an element by ref.

        Args:
            ref: Element ref from snapshot (e.g., "e38")
            timeout: Max time to wait for element (ms), defaults to config.DEFAULT_TIMEOUT

        Returns:
            ActionResult with success status
        """
        if timeout is None:
            timeout = config.DEFAULT_TIMEOUT

        locator = await self._get_locator(ref)
        if not locator:
            result = ActionResult(
                success=False,
                action="click",
                ref=ref,
                error=f"Element ref '{ref}' not found. Get a new snapshot."
            )
            self._metrics["action_failures"] += 1
            return result

        start_time = time.time()
        self._metrics["actions_executed"] += 1

        try:
            await locator.click(timeout=timeout)
            result = ActionResult(success=True, action="click", ref=ref)
        except Exception as e:
            result = ActionResult(success=False, action="click", ref=ref, error=str(e))
            self._metrics["action_failures"] += 1

            # Try keyboard fallback if click failed
            if config.ENABLE_KEYBOARD_FALLBACK:
                if config.LOG_ACTIONS:
                    print(f"[a11y] Click failed, trying keyboard fallback...")
                keyboard_success = await self._keyboard_fallback(ref, "click")
                if keyboard_success:
                    result = ActionResult(
                        success=True,
                        action="click",
                        ref=ref,
                        data={"method": "keyboard_fallback"}
                    )
                    # Decrement failure counter since we recovered
                    self._metrics["action_failures"] -= 1
        finally:
            action_time = time.time() - start_time
            self._metrics["total_action_time"] += action_time

            if config.LOG_ACTIONS:
                status = "OK" if result.success else "FAIL"
                method = result.data.get("method", "mouse") if result.success else "failed"
                print(f"[a11y] click {ref} {status} ({action_time:.3f}s) [{method}]")

        return result

    async def type(self, ref: str, text: str, clear: bool = True, timeout: int = 5000) -> ActionResult:
        """
        Type text into an element by ref.

        Auto-detects date inputs and uses DatePickerHandler for better reliability.

        Args:
            ref: Element ref from snapshot
            text: Text to type
            clear: If True, clear existing text first
            timeout: Max time to wait for element (ms)

        Returns:
            ActionResult with success status
        """
        locator = await self._get_locator(ref)
        if not locator:
            return ActionResult(
                success=False,
                action="type",
                ref=ref,
                error=f"Element ref '{ref}' not found. Get a new snapshot."
            )

        try:
            # Check if this is a date input - use DatePickerHandler
            if DATE_PICKER_AVAILABLE and self._is_date_input(ref, text):
                try:
                    if not self._date_picker_handler:
                        self._date_picker_handler = DatePickerHandler(self.page)
                    result = await self._date_picker_handler.set_date(locator, text)
                    if result.success:
                        return ActionResult(success=True, action="type", ref=ref, data={"text": text, "method": "date_picker"})
                except Exception:
                    pass  # Fall through to standard typing

            # Standard typing
            if clear:
                await locator.fill(text, timeout=timeout)
            else:
                await locator.press_sequentially(text, timeout=timeout)
            return ActionResult(success=True, action="type", ref=ref, data={"text": text})
        except Exception as e:
            return ActionResult(success=False, action="type", ref=ref, error=str(e))

    def _is_date_input(self, ref: str, text: str) -> bool:
        """Check if input looks like a date field."""
        # Check ref info from last snapshot
        if self._last_snapshot:
            for elem in self._last_snapshot.elements:
                if elem.ref == ref:
                    name_lower = elem.name.lower()
                    if any(x in name_lower for x in ['date', 'birth', 'dob', 'when', 'schedule', 'appointment']):
                        return True

        # Check if text looks like a date
        import re
        date_patterns = [
            r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',  # MM/DD/YYYY or DD-MM-YYYY
            r'\d{4}[/-]\d{1,2}[/-]\d{1,2}',     # YYYY-MM-DD
            r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)',  # Month names
        ]
        text_lower = text.lower()
        return any(re.search(p, text_lower) for p in date_patterns)

    async def press(self, key: str) -> ActionResult:
        """
        Press a keyboard key.

        Args:
            key: Key to press (e.g., "Enter", "Escape", "ArrowDown")
                 See: https://playwright.dev/python/docs/api/class-keyboard#keyboard-press

        Returns:
            ActionResult with success status
        """
        try:
            await self.page.keyboard.press(key)
            return ActionResult(success=True, action="press", data={"key": key})
        except Exception as e:
            return ActionResult(success=False, action="press", error=str(e))

    async def scroll(self, direction: str = "down", amount: int = 500) -> ActionResult:
        """
        Scroll the page.

        Args:
            direction: "down", "up", "left", or "right"
            amount: Pixels to scroll

        Returns:
            ActionResult with success status
        """
        try:
            if direction in {"down", "up"}:
                delta_y = amount if direction == "down" else -amount
                await self.page.mouse.wheel(0, delta_y)
            else:  # left or right
                delta_x = amount if direction == "right" else -amount
                await self.page.mouse.wheel(delta_x, 0)

            # Clear cache after scroll - content may have changed via infinite scroll
            self._snapshot_cache.clear()

            return ActionResult(
                success=True,
                action="scroll",
                data={"direction": direction, "amount": amount}
            )
        except Exception as e:
            return ActionResult(success=False, action="scroll", error=str(e))

    async def wait(self, seconds: float) -> ActionResult:
        """
        Wait for a specified time.

        Args:
            seconds: Time to wait in seconds

        Returns:
            ActionResult with success status
        """
        await asyncio.sleep(seconds)
        return ActionResult(success=True, action="wait", data={"seconds": seconds})

    async def screenshot(self, path: Optional[str] = None, full_page: bool = False) -> ActionResult:
        """
        Take a screenshot.

        Args:
            path: File path to save screenshot (PNG format)
                  If None, returns bytes in data dict
            full_page: If True, capture entire scrollable page

        Returns:
            ActionResult with success status and screenshot data
        """
        try:
            if path:
                await self.page.screenshot(path=path, full_page=full_page)
                return ActionResult(
                    success=True,
                    action="screenshot",
                    data={"path": path, "full_page": full_page}
                )
            else:
                data = await self.page.screenshot(full_page=full_page)
                return ActionResult(
                    success=True,
                    action="screenshot",
                    data={"bytes": len(data), "full_page": full_page, "image_data": data}
                )
        except Exception as e:
            return ActionResult(success=False, action="screenshot", error=str(e))

    async def start_tracing(self, name: str = "trace", screenshots: bool = True, snapshots: bool = True) -> ActionResult:
        """
        Start recording a trace for debugging.

        Args:
            name: Name of the trace
            screenshots: Whether to capture screenshots in trace
            snapshots: Whether to capture DOM snapshots in trace

        Returns:
            ActionResult with success status
        """
        try:
            await self._context.tracing.start(
                name=name,
                screenshots=screenshots,
                snapshots=snapshots
            )
            self._tracing_active = True
            return ActionResult(success=True, action="start_tracing", data={"name": name})
        except Exception as e:
            return ActionResult(success=False, action="start_tracing", error=str(e))

    async def stop_tracing(self, path: str = "trace.zip") -> ActionResult:
        """
        Stop tracing and save to file.

        Args:
            path: File path to save trace (ZIP format)

        Returns:
            ActionResult with success status and trace file path
        """
        try:
            await self._context.tracing.stop(path=path)
            self._tracing_active = False
            return ActionResult(success=True, action="stop_tracing", data={"path": path})
        except Exception as e:
            return ActionResult(success=False, action="stop_tracing", error=str(e))

    async def go_back(self) -> ActionResult:
        """
        Go back in browser history.

        Returns:
            ActionResult with success status
        """
        try:
            await self.page.go_back(timeout=10000)
            return ActionResult(success=True, action="go_back")
        except Exception as e:
            return ActionResult(success=False, action="go_back", error=str(e))

    async def go_forward(self) -> ActionResult:
        """
        Go forward in browser history.

        Returns:
            ActionResult with success status
        """
        try:
            await self.page.go_forward(timeout=10000)
            return ActionResult(success=True, action="go_forward")
        except Exception as e:
            return ActionResult(success=False, action="go_forward", error=str(e))

    async def navigate_back(self) -> ActionResult:
        """
        Go back in browser history. Alias for go_back().

        Returns:
            ActionResult with success status
        """
        return await self.go_back()

    async def navigate_forward(self) -> ActionResult:
        """
        Go forward in browser history. Alias for go_forward().

        Returns:
            ActionResult with success status
        """
        return await self.go_forward()

    async def refresh(self) -> ActionResult:
        """
        Refresh the page.

        Returns:
            ActionResult with success status
        """
        try:
            await self.page.reload(timeout=30000)
            return ActionResult(success=True, action="refresh")
        except Exception as e:
            return ActionResult(success=False, action="refresh", error=str(e))

    async def hover(self, ref: str, timeout: int = 5000) -> ActionResult:
        """
        Hover over an element by ref.

        Args:
            ref: Element ref from snapshot
            timeout: Max time to wait for element (ms)

        Returns:
            ActionResult with success status
        """
        locator = await self._get_locator(ref)
        if not locator:
            return ActionResult(
                success=False,
                action="hover",
                ref=ref,
                error=f"Element ref '{ref}' not found. Get a new snapshot."
            )

        try:
            await locator.hover(timeout=timeout)
            return ActionResult(success=True, action="hover", ref=ref)
        except Exception as e:
            return ActionResult(success=False, action="hover", ref=ref, error=str(e))

    async def select(self, ref: str, value: str, timeout: int = 5000) -> ActionResult:
        """
        Select an option in a dropdown by ref.

        Args:
            ref: Element ref from snapshot (must be a combobox/select)
            value: Option value or label to select
            timeout: Max time to wait for element (ms)

        Returns:
            ActionResult with success status
        """
        locator = await self._get_locator(ref)
        if not locator:
            return ActionResult(
                success=False,
                action="select",
                ref=ref,
                error=f"Element ref '{ref}' not found. Get a new snapshot."
            )

        try:
            # Try by value first, then by label
            try:
                await locator.select_option(value=value, timeout=timeout)
            except Exception as e:
                if config.LOG_ERRORS:
                    print(f"[a11y] select_option by value failed, trying label: {e}")
                await locator.select_option(label=value, timeout=timeout)

            return ActionResult(success=True, action="select", ref=ref, data={"value": value})
        except Exception as e:
            return ActionResult(success=False, action="select", ref=ref, error=str(e))

    async def get_text(self, ref: str, timeout: int = 5000) -> ActionResult:
        """
        Get text content of an element by ref.

        Args:
            ref: Element ref from snapshot
            timeout: Max time to wait for element (ms)

        Returns:
            ActionResult with text in data dict
        """
        locator = await self._get_locator(ref)
        if not locator:
            return ActionResult(
                success=False,
                action="get_text",
                ref=ref,
                error=f"Element ref '{ref}' not found. Get a new snapshot."
            )

        try:
            text = await locator.inner_text(timeout=timeout)
            return ActionResult(success=True, action="get_text", ref=ref, data={"text": text})
        except Exception as e:
            return ActionResult(success=False, action="get_text", ref=ref, error=str(e))

    async def get_value(self, ref: str, timeout: int = 5000) -> ActionResult:
        """
        Get value attribute of an input element by ref.

        Args:
            ref: Element ref from snapshot
            timeout: Max time to wait for element (ms)

        Returns:
            ActionResult with value in data dict
        """
        locator = await self._get_locator(ref)
        if not locator:
            return ActionResult(
                success=False,
                action="get_value",
                ref=ref,
                error=f"Element ref '{ref}' not found. Get a new snapshot."
            )

        try:
            value = await locator.input_value(timeout=timeout)
            return ActionResult(success=True, action="get_value", ref=ref, data={"value": value})
        except Exception as e:
            return ActionResult(success=False, action="get_value", ref=ref, error=str(e))

    async def is_visible(self, ref: str, timeout: int = 5000) -> ActionResult:
        """
        Check if an element is visible by ref.

        Args:
            ref: Element ref from snapshot
            timeout: Max time to wait for element (ms)

        Returns:
            ActionResult with visible boolean in data dict
        """
        locator = await self._get_locator(ref)
        if not locator:
            return ActionResult(
                success=False,
                action="is_visible",
                ref=ref,
                error=f"Element ref '{ref}' not found. Get a new snapshot."
            )

        try:
            visible = await locator.is_visible(timeout=timeout)
            return ActionResult(success=True, action="is_visible", ref=ref, data={"visible": visible})
        except Exception as e:
            return ActionResult(success=False, action="is_visible", ref=ref, error=str(e))

    async def wait_for_element(self, ref: str, state: str = "visible", timeout: int = 10000) -> ActionResult:
        """
        Wait for an element to reach a specific state.

        Args:
            ref: Element ref from snapshot
            state: "visible", "hidden", "attached", or "detached"
            timeout: Max time to wait (ms)

        Returns:
            ActionResult with success status
        """
        locator = await self._get_locator(ref)
        if not locator:
            return ActionResult(
                success=False,
                action="wait_for_element",
                ref=ref,
                error=f"Element ref '{ref}' not found. Get a new snapshot."
            )

        try:
            await locator.wait_for(state=state, timeout=timeout)
            return ActionResult(
                success=True,
                action="wait_for_element",
                ref=ref,
                data={"state": state}
            )
        except Exception as e:
            return ActionResult(success=False, action="wait_for_element", ref=ref, error=str(e))

    async def wait_for_url(self, pattern: str, timeout: int = 10000) -> ActionResult:
        """
        Wait for URL to match a pattern.

        Args:
            pattern: URL pattern (string or regex)
            timeout: Max time to wait (ms)

        Returns:
            ActionResult with success status and final URL
        """
        try:
            await self.page.wait_for_url(pattern, timeout=timeout)
            return ActionResult(
                success=True,
                action="wait_for_url",
                data={"url": self.page.url, "pattern": pattern}
            )
        except Exception as e:
            return ActionResult(success=False, action="wait_for_url", error=str(e))


    async def batch_execute(
        self,
        actions: List[Dict[str, Any]],
        stop_on_error: bool = False
    ) -> ActionResult:
        """
        Execute multiple actions in a single call.

        This reduces token usage by ~90% compared to individual calls
        by eliminating redundant snapshots between actions.

        Args:
            actions: List of action dicts, each with:
                - action: str ("click", "type", "fill", "select", "scroll", "navigate")
                - ref: str (element ref, required for most actions)
                - value: str (for type/select)
                - text: str (for type, alias for value)
                - url: str (for navigate)
                - direction: str (for scroll, default "down")
                - amount: int (for scroll, default 500)
                - clear: bool (for type, default True)
            stop_on_error: If True, stop on first failure

        Returns:
            ActionResult with data containing:
                - results: List of individual action results
                - successful: int count
                - failed: int count

        Example:
            await browser.batch_execute([
                {"action": "type", "ref": "e1", "value": "John"},
                {"action": "type", "ref": "e2", "value": "john@email.com"},
                {"action": "click", "ref": "e3"}
            ])
        """
        results = []
        successful = 0
        failed = 0

        for i, action_dict in enumerate(actions):
            action_type = action_dict.get("action")

            if not action_type:
                result = ActionResult(
                    success=False,
                    action="batch_execute",
                    error=f"Action {i}: Missing 'action' field"
                )
                results.append(result.data if hasattr(result, 'data') else {"error": result.error})
                failed += 1
                if stop_on_error:
                    break
                continue

            try:
                # Execute the appropriate action method
                if action_type == "click":
                    ref = action_dict.get("ref")
                    timeout = action_dict.get("timeout")
                    result = await self.click(ref, timeout=timeout)

                elif action_type == "type":
                    ref = action_dict.get("ref")
                    text = action_dict.get("text") or action_dict.get("value", "")
                    clear = action_dict.get("clear", True)
                    timeout = action_dict.get("timeout", 5000)
                    result = await self.type(ref, text, clear=clear, timeout=timeout)

                elif action_type == "select":
                    ref = action_dict.get("ref")
                    value = action_dict.get("value", "")
                    timeout = action_dict.get("timeout", 5000)
                    result = await self.select(ref, value, timeout=timeout)

                elif action_type == "scroll":
                    direction = action_dict.get("direction", "down")
                    amount = action_dict.get("amount", 500)
                    result = await self.scroll(direction=direction, amount=amount)

                elif action_type == "navigate":
                    url = action_dict.get("url")
                    if not url:
                        result = ActionResult(
                            success=False,
                            action="navigate",
                            error="Missing 'url' parameter"
                        )
                    else:
                        result = await self.navigate(url)

                else:
                    result = ActionResult(
                        success=False,
                        action=action_type,
                        error=f"Unknown action type: {action_type}"
                    )

                # Collect result
                if result.success:
                    successful += 1
                else:
                    failed += 1

                results.append({
                    "action": action_type,
                    "success": result.success,
                    "ref": result.ref,
                    "error": result.error,
                    "data": result.data
                })

                # Stop on error if requested
                if not result.success and stop_on_error:
                    break

            except Exception as e:
                failed += 1
                results.append({
                    "action": action_type,
                    "success": False,
                    "error": str(e)
                })
                if stop_on_error:
                    break

        return ActionResult(
            success=(failed == 0),
            action="batch_execute",
            data={
                "results": results,
                "successful": successful,
                "failed": failed,
                "total": len(actions)
            }
        )

    async def evaluate(self, script: str) -> ActionResult:
        """
        Execute JavaScript in the page context.

        Args:
            script: JavaScript code to execute

        Returns:
            ActionResult with script result in data dict
        """
        try:
            result = await self.page.evaluate(script)
            return ActionResult(success=True, action="evaluate", data={"result": result})
        except Exception as e:
            return ActionResult(success=False, action="evaluate", error=str(e))

    async def run_code(self, code: str) -> ActionResult:
        """
        Run custom Playwright code. The code receives 'page' as argument.

        Args:
            code: Python code to execute with 'page' available
                  Example: "await page.locator('button').click()"

        Returns:
            ActionResult with success status and result data
        """
        try:
            import textwrap

            # Create a namespace with page available
            namespace = {"page": self.page, "asyncio": asyncio}

            # Dedent and clean the code
            code = textwrap.dedent(code).strip()

            # Indent code for wrapping in function
            indented_code = "\n    ".join(code.split("\n"))

            # Wrap code in async function
            wrapped_code = f"""async def _run():
    {indented_code}
"""
            exec(wrapped_code, namespace)
            result = await namespace["_run"]()
            return ActionResult(success=True, action="run_code", data={"result": result})
        except Exception as e:
            return ActionResult(success=False, action="run_code", error=str(e))

    async def get_url(self) -> str:
        """Get current page URL."""
        return self.page.url

    async def get_title(self) -> str:
        """Get current page title."""
        return await self.page.title()

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics.

        Returns:
            Dictionary with metrics including:
            - snapshots_taken: Total snapshots taken
            - cache_hits: Number of cache hits
            - actions_executed: Total actions executed
            - action_failures: Number of failed actions
            - total_action_time: Total time spent on actions (seconds)
            - avg_action_time: Average time per action (seconds)
            - cache_hit_rate: Percentage of cache hits
        """
        metrics = self._metrics.copy()

        # Calculate derived metrics
        if metrics["snapshots_taken"] > 0:
            metrics["cache_hit_rate"] = (
                metrics["cache_hits"] / metrics["snapshots_taken"] * 100
            )
        else:
            metrics["cache_hit_rate"] = 0.0

        if metrics["actions_executed"] > 0:
            metrics["avg_action_time"] = (
                metrics["total_action_time"] / metrics["actions_executed"]
            )
        else:
            metrics["avg_action_time"] = 0.0

        return metrics

    def reset_metrics(self) -> None:
        """Reset performance metrics to zero."""
        self._metrics = {
            "snapshots_taken": 0,
            "cache_hits": 0,
            "actions_executed": 0,
            "action_failures": 0,
            "total_action_time": 0.0,
        }

    def clear_cache(self) -> None:
        """Clear snapshot cache."""
        self._snapshot_cache.clear()

    # === Playwright MCP Parity Tools ===

    async def drag(self, start_ref: str, end_ref: str, timeout: int = 5000) -> ActionResult:
        """
        Drag from start element to end element.

        Args:
            start_ref: Element ref to drag from
            end_ref: Element ref to drag to
            timeout: Max time to wait for elements (ms)

        Returns:
            ActionResult with success status
        """
        start_loc = await self._get_locator(start_ref)
        end_loc = await self._get_locator(end_ref)
        if not start_loc or not end_loc:
            return ActionResult(success=False, action="drag", error="Element not found")
        try:
            await start_loc.drag_to(end_loc, timeout=timeout)
            return ActionResult(success=True, action="drag", data={"from": start_ref, "to": end_ref})
        except Exception as e:
            return ActionResult(success=False, action="drag", error=str(e))

    async def fill_form(self, fields: List[Dict[str, str]], use_complex_handler: bool = True) -> ActionResult:
        """
        Fill multiple form fields at once.

        Auto-uses ComplexFormHandler for complex forms (3+ fields or special types).

        Args:
            fields: List of dicts with "ref" and "value" keys
                   Optional keys: "type" (textbox, checkbox, radio, combobox, slider)
            use_complex_handler: If True, use ComplexFormHandler for advanced forms

        Returns:
            ActionResult with success status and field results

        Example:
            await browser.fill_form([
                {"ref": "e1", "value": "John"},
                {"ref": "e2", "value": "john@example.com"},
                {"ref": "e3", "value": "USA", "type": "combobox"}
            ])
        """
        # Use ComplexFormHandler for advanced forms
        if use_complex_handler and COMPLEX_FORM_AVAILABLE and len(fields) >= 3:
            try:
                if not self._complex_form_handler:
                    self._complex_form_handler = ComplexFormHandler(self.page)

                # Convert refs to locators and fill
                for field in fields:
                    locator = await self._get_locator(field["ref"])
                    if locator:
                        field_type = field.get("type", "textbox")
                        await self._complex_form_handler.fill_field_smart(
                            locator, field["value"], field_type
                        )

                return ActionResult(
                    success=True,
                    action="fill_form",
                    data={"fields": [{"ref": f["ref"], "success": True} for f in fields], "method": "complex_handler"}
                )
            except Exception as e:
                # Complex form handler failed - fall through to standard field-by-field filling
                logger.debug(f"Complex form handler failed, using standard filling: {e}")

        # Standard field-by-field filling
        results = []
        for field in fields:
            result = await self.type(field["ref"], field["value"])
            results.append({"ref": field["ref"], "success": result.success})
        success = all(r["success"] for r in results)
        return ActionResult(success=success, action="fill_form", data={"fields": results})

    async def handle_dialog(self, accept: bool = True, prompt_text: Optional[str] = None) -> ActionResult:
        """
        Handle browser dialogs (alert/confirm/prompt).

        Args:
            accept: Whether to accept the dialog
            prompt_text: Text to enter for prompt dialogs

        Returns:
            ActionResult with success status
        """
        try:
            def handler(dialog):
                if accept:
                    if prompt_text and dialog.type == "prompt":
                        asyncio.create_task(dialog.accept(prompt_text))
                    else:
                        asyncio.create_task(dialog.accept())
                else:
                    asyncio.create_task(dialog.dismiss())

            self.page.on("dialog", handler)
            return ActionResult(success=True, action="handle_dialog", data={"accept": accept})
        except Exception as e:
            return ActionResult(success=False, action="handle_dialog", error=str(e))

    async def console_messages(self, level: str = "all") -> ActionResult:
        """
        Get console log messages.

        Args:
            level: Filter by level ("error", "warning", "info", "all")

        Returns:
            ActionResult with messages in data dict
        """
        messages = getattr(self, '_console_messages', [])
        if level != "all":
            messages = [m for m in messages if m.get("type") == level]
        return ActionResult(success=True, action="console_messages", data={"messages": messages})

    async def network_requests(self, include_static: bool = False) -> ActionResult:
        """
        Get network requests since page load.

        Args:
            include_static: Whether to include static resources (CSS, JS, images)

        Returns:
            ActionResult with requests in data dict
        """
        requests = getattr(self, '_network_requests', [])
        if not include_static:
            static_types = {'.css', '.js', '.png', '.jpg', '.gif', '.woff', '.ico'}
            requests = [r for r in requests if not any(r.get('url', '').endswith(t) for t in static_types)]
        return ActionResult(success=True, action="network_requests", data={"requests": requests})

    async def resize(self, width: int, height: int) -> ActionResult:
        """
        Resize browser viewport.

        Args:
            width: Viewport width in pixels
            height: Viewport height in pixels

        Returns:
            ActionResult with success status
        """
        try:
            await self.page.set_viewport_size({"width": width, "height": height})
            return ActionResult(success=True, action="resize", data={"width": width, "height": height})
        except Exception as e:
            return ActionResult(success=False, action="resize", error=str(e))

    async def file_upload(self, ref: Optional[str] = None, paths: Optional[List[str]] = None) -> ActionResult:
        """
        Upload files to a file input.

        Args:
            ref: Element ref of file input (optional)
            paths: List of absolute file paths to upload

        Returns:
            ActionResult with success status
        """
        try:
            if ref:
                locator = await self._get_locator(ref)
                if locator:
                    await locator.set_input_files(paths or [])
            else:
                async with self.page.expect_file_chooser() as fc_info:
                    file_chooser = await fc_info.value
                    await file_chooser.set_files(paths or [])
            return ActionResult(success=True, action="file_upload", data={"paths": paths})
        except Exception as e:
            return ActionResult(success=False, action="file_upload", error=str(e))

    async def tabs(self, action: str = "list", index: Optional[int] = None) -> ActionResult:
        """
        Manage browser tabs.

        Args:
            action: "list", "new", "close", or "select"
            index: Tab index for "close" or "select" actions

        Returns:
            ActionResult with tab information

        Examples:
            await browser.tabs("list")
            await browser.tabs("new")
            await browser.tabs("close", index=1)
            await browser.tabs("select", index=0)
        """
        try:
            pages = self._context.pages
            if action == "list":
                tabs = [{"index": i, "url": p.url, "title": await p.title()} for i, p in enumerate(pages)]
                return ActionResult(success=True, action="tabs", data={"tabs": tabs, "current": pages.index(self._page)})
            elif action == "new":
                new_page = await self._context.new_page()
                self._page = new_page
                return ActionResult(success=True, action="tabs", data={"action": "new", "index": len(pages)})
            elif action == "close":
                idx = index if index is not None else pages.index(self._page)
                await pages[idx].close()
                if pages[idx] == self._page and pages:
                    self._page = pages[0] if pages else None
                return ActionResult(success=True, action="tabs", data={"action": "close", "index": idx})
            elif action == "select" and index is not None:
                self._page = pages[index]
                return ActionResult(success=True, action="tabs", data={"action": "select", "index": index})
            return ActionResult(success=False, action="tabs", error=f"Unknown action: {action}")
        except Exception as e:
            return ActionResult(success=False, action="tabs", error=str(e))

    async def pdf_save(self, path: str) -> ActionResult:
        """
        Save current page as PDF.

        Args:
            path: File path to save PDF

        Returns:
            ActionResult with success status
        """
        try:
            await self.page.pdf(path=path)
            return ActionResult(success=True, action="pdf_save", data={"path": path})
        except Exception as e:
            return ActionResult(success=False, action="pdf_save", error=str(e))

    async def mouse_click_xy(self, x: int, y: int, button: str = "left") -> ActionResult:
        """
        Click at specific coordinates.

        Args:
            x: X coordinate in pixels
            y: Y coordinate in pixels
            button: Mouse button ("left", "right", "middle")

        Returns:
            ActionResult with success status
        """
        try:
            await self.page.mouse.click(x, y, button=button)
            return ActionResult(success=True, action="mouse_click_xy", data={"x": x, "y": y})
        except Exception as e:
            return ActionResult(success=False, action="mouse_click_xy", error=str(e))

    async def mouse_move_xy(self, x: int, y: int) -> ActionResult:
        """
        Move mouse to specific coordinates.

        Args:
            x: X coordinate in pixels
            y: Y coordinate in pixels

        Returns:
            ActionResult with success status
        """
        try:
            await self.page.mouse.move(x, y)
            return ActionResult(success=True, action="mouse_move_xy", data={"x": x, "y": y})
        except Exception as e:
            return ActionResult(success=False, action="mouse_move_xy", error=str(e))

    async def mouse_drag_xy(self, start_x: int, start_y: int, end_x: int, end_y: int) -> ActionResult:
        """
        Drag from one coordinate to another.

        Args:
            start_x: Starting X coordinate
            start_y: Starting Y coordinate
            end_x: Ending X coordinate
            end_y: Ending Y coordinate

        Returns:
            ActionResult with success status
        """
        try:
            await self.page.mouse.move(start_x, start_y)
            await self.page.mouse.down()
            await self.page.mouse.move(end_x, end_y)
            await self.page.mouse.up()
            return ActionResult(success=True, action="mouse_drag_xy", data={"start": [start_x, start_y], "end": [end_x, end_y]})
        except Exception as e:
            return ActionResult(success=False, action="mouse_drag_xy", error=str(e))

    # === Additional Playwright MCP Parity Tools ===

    async def install_browser(self) -> ActionResult:
        """Install the browser if not already installed."""
        import subprocess
        try:
            result = subprocess.run(
                ["playwright", "install", "chromium"],
                capture_output=True,
                text=True
            )
            success = result.returncode == 0
            return ActionResult(
                success=success,
                action="install_browser",
                data={"output": result.stdout},
                error=result.stderr if not success else None
            )
        except Exception as e:
            return ActionResult(success=False, action="install_browser", error=str(e))

    async def double_click(self, ref: str, timeout: int = 5000) -> ActionResult:
        """
        Double-click an element by ref.

        Args:
            ref: Element ref from snapshot
            timeout: Max time to wait for element (ms)

        Returns:
            ActionResult with success status
        """
        locator = await self._get_locator(ref)
        if not locator:
            return ActionResult(success=False, action="double_click", ref=ref, error=f"Ref '{ref}' not found")
        try:
            await locator.dblclick(timeout=timeout)
            return ActionResult(success=True, action="double_click", ref=ref)
        except Exception as e:
            return ActionResult(success=False, action="double_click", ref=ref, error=str(e))

    async def right_click(self, ref: str, timeout: int = 5000) -> ActionResult:
        """
        Right-click an element by ref.

        Args:
            ref: Element ref from snapshot
            timeout: Max time to wait for element (ms)

        Returns:
            ActionResult with success status
        """
        locator = await self._get_locator(ref)
        if not locator:
            return ActionResult(success=False, action="right_click", ref=ref, error=f"Ref '{ref}' not found")
        try:
            await locator.click(button="right", timeout=timeout)
            return ActionResult(success=True, action="right_click", ref=ref)
        except Exception as e:
            return ActionResult(success=False, action="right_click", ref=ref, error=str(e))

    async def focus(self, ref: str, timeout: int = 5000) -> ActionResult:
        """
        Focus an element by ref.

        Args:
            ref: Element ref from snapshot
            timeout: Max time to wait for element (ms)

        Returns:
            ActionResult with success status
        """
        locator = await self._get_locator(ref)
        if not locator:
            return ActionResult(success=False, action="focus", ref=ref, error=f"Ref '{ref}' not found")
        try:
            await locator.focus(timeout=timeout)
            return ActionResult(success=True, action="focus", ref=ref)
        except Exception as e:
            return ActionResult(success=False, action="focus", ref=ref, error=str(e))

    async def clear(self, ref: str, timeout: int = 5000) -> ActionResult:
        """
        Clear an input field by ref.

        Args:
            ref: Element ref from snapshot
            timeout: Max time to wait for element (ms)

        Returns:
            ActionResult with success status
        """
        locator = await self._get_locator(ref)
        if not locator:
            return ActionResult(success=False, action="clear", ref=ref, error=f"Ref '{ref}' not found")
        try:
            await locator.clear(timeout=timeout)
            return ActionResult(success=True, action="clear", ref=ref)
        except Exception as e:
            return ActionResult(success=False, action="clear", ref=ref, error=str(e))

    async def check(self, ref: str, timeout: int = 5000) -> ActionResult:
        """
        Check a checkbox by ref.

        Args:
            ref: Element ref from snapshot
            timeout: Max time to wait for element (ms)

        Returns:
            ActionResult with success status
        """
        locator = await self._get_locator(ref)
        if not locator:
            return ActionResult(success=False, action="check", ref=ref, error=f"Ref '{ref}' not found")
        try:
            await locator.check(timeout=timeout)
            return ActionResult(success=True, action="check", ref=ref)
        except Exception as e:
            return ActionResult(success=False, action="check", ref=ref, error=str(e))

    async def uncheck(self, ref: str, timeout: int = 5000) -> ActionResult:
        """
        Uncheck a checkbox by ref.

        Args:
            ref: Element ref from snapshot
            timeout: Max time to wait for element (ms)

        Returns:
            ActionResult with success status
        """
        locator = await self._get_locator(ref)
        if not locator:
            return ActionResult(success=False, action="uncheck", ref=ref, error=f"Ref '{ref}' not found")
        try:
            await locator.uncheck(timeout=timeout)
            return ActionResult(success=True, action="uncheck", ref=ref)
        except Exception as e:
            return ActionResult(success=False, action="uncheck", ref=ref, error=str(e))

    async def is_checked(self, ref: str, timeout: int = 5000) -> ActionResult:
        """
        Check if a checkbox is checked.

        Args:
            ref: Element ref from snapshot
            timeout: Max time to wait for element (ms)

        Returns:
            ActionResult with checked boolean in data dict
        """
        locator = await self._get_locator(ref)
        if not locator:
            return ActionResult(success=False, action="is_checked", ref=ref, error=f"Ref '{ref}' not found")
        try:
            checked = await locator.is_checked(timeout=timeout)
            return ActionResult(success=True, action="is_checked", ref=ref, data={"checked": checked})
        except Exception as e:
            return ActionResult(success=False, action="is_checked", ref=ref, error=str(e))

    async def is_enabled(self, ref: str, timeout: int = 5000) -> ActionResult:
        """
        Check if an element is enabled.

        Args:
            ref: Element ref from snapshot
            timeout: Max time to wait for element (ms)

        Returns:
            ActionResult with enabled boolean in data dict
        """
        locator = await self._get_locator(ref)
        if not locator:
            return ActionResult(success=False, action="is_enabled", ref=ref, error=f"Ref '{ref}' not found")
        try:
            enabled = await locator.is_enabled(timeout=timeout)
            return ActionResult(success=True, action="is_enabled", ref=ref, data={"enabled": enabled})
        except Exception as e:
            return ActionResult(success=False, action="is_enabled", ref=ref, error=str(e))

    async def is_editable(self, ref: str, timeout: int = 5000) -> ActionResult:
        """
        Check if an element is editable.

        Args:
            ref: Element ref from snapshot
            timeout: Max time to wait for element (ms)

        Returns:
            ActionResult with editable boolean in data dict
        """
        locator = await self._get_locator(ref)
        if not locator:
            return ActionResult(success=False, action="is_editable", ref=ref, error=f"Ref '{ref}' not found")
        try:
            editable = await locator.is_editable(timeout=timeout)
            return ActionResult(success=True, action="is_editable", ref=ref, data={"editable": editable})
        except Exception as e:
            return ActionResult(success=False, action="is_editable", ref=ref, error=str(e))

    async def get_attribute(self, ref: str, name: str, timeout: int = 5000) -> ActionResult:
        """
        Get an attribute value from an element.

        Args:
            ref: Element ref from snapshot
            name: Attribute name (e.g., "href", "class", "data-id")
            timeout: Max time to wait for element (ms)

        Returns:
            ActionResult with attribute value in data dict
        """
        locator = await self._get_locator(ref)
        if not locator:
            return ActionResult(success=False, action="get_attribute", ref=ref, error=f"Ref '{ref}' not found")
        try:
            value = await locator.get_attribute(name, timeout=timeout)
            return ActionResult(success=True, action="get_attribute", ref=ref, data={"attribute": name, "value": value})
        except Exception as e:
            return ActionResult(success=False, action="get_attribute", ref=ref, error=str(e))

    async def bounding_box(self, ref: str) -> ActionResult:
        """
        Get the bounding box of an element.

        Args:
            ref: Element ref from snapshot

        Returns:
            ActionResult with bounding box coordinates in data dict
            Format: {"x": float, "y": float, "width": float, "height": float}
        """
        locator = await self._get_locator(ref)
        if not locator:
            return ActionResult(success=False, action="bounding_box", ref=ref, error=f"Ref '{ref}' not found")
        try:
            box = await locator.bounding_box()
            return ActionResult(success=True, action="bounding_box", ref=ref, data={"box": box})
        except Exception as e:
            return ActionResult(success=False, action="bounding_box", ref=ref, error=str(e))

    async def scroll_into_view(self, ref: str, timeout: int = 5000) -> ActionResult:
        """
        Scroll an element into view.

        Args:
            ref: Element ref from snapshot
            timeout: Max time to wait for element (ms)

        Returns:
            ActionResult with success status
        """
        locator = await self._get_locator(ref)
        if not locator:
            return ActionResult(success=False, action="scroll_into_view", ref=ref, error=f"Ref '{ref}' not found")
        try:
            await locator.scroll_into_view_if_needed(timeout=timeout)
            return ActionResult(success=True, action="scroll_into_view", ref=ref)
        except Exception as e:
            return ActionResult(success=False, action="scroll_into_view", ref=ref, error=str(e))

    async def wait_for_load_state(self, state: str = "load", timeout: int = 30000) -> ActionResult:
        """
        Wait for page load state.

        Args:
            state: Load state to wait for - "load", "domcontentloaded", or "networkidle"
            timeout: Max time to wait (ms)

        Returns:
            ActionResult with success status
        """
        try:
            await self.page.wait_for_load_state(state, timeout=timeout)
            return ActionResult(success=True, action="wait_for_load_state", data={"state": state})
        except Exception as e:
            return ActionResult(success=False, action="wait_for_load_state", error=str(e))

    async def wait_for_navigation(self, url_pattern: str = None, timeout: int = 30000) -> ActionResult:
        """
        Wait for navigation to complete.

        Args:
            url_pattern: URL pattern to wait for (optional, can be string or regex)
            timeout: Max time to wait (ms)

        Returns:
            ActionResult with success status and final URL
        """
        try:
            if url_pattern:
                await self.page.wait_for_url(url_pattern, timeout=timeout)
            else:
                await self.page.wait_for_load_state("load", timeout=timeout)
            return ActionResult(success=True, action="wait_for_navigation", data={"url": self.page.url})
        except Exception as e:
            return ActionResult(success=False, action="wait_for_navigation", error=str(e))

    # === Testing/Assertion Tools (Playwright MCP Parity) ===

    async def expect_visible(self, ref: str, timeout: int = 5000) -> ActionResult:
        """
        Assert that an element is visible.

        Args:
            ref: Element ref from snapshot
            timeout: Max time to wait for element (ms)

        Returns:
            ActionResult with success status
        """
        try:
            result = await self.is_visible(ref, timeout=timeout)
            if result.success and result.data.get("visible"):
                return ActionResult(success=True, action="expect_visible", ref=ref)
            return ActionResult(success=False, action="expect_visible", ref=ref,
                              error=f"Element '{ref}' is not visible")
        except Exception as e:
            return ActionResult(success=False, action="expect_visible", ref=ref, error=str(e))

    async def expect_hidden(self, ref: str, timeout: int = 5000) -> ActionResult:
        """
        Assert that an element is hidden.

        Args:
            ref: Element ref from snapshot
            timeout: Max time to wait for element (ms)

        Returns:
            ActionResult with success status
        """
        try:
            result = await self.is_visible(ref, timeout=timeout)
            if result.success and not result.data.get("visible"):
                return ActionResult(success=True, action="expect_hidden", ref=ref)
            return ActionResult(success=False, action="expect_hidden", ref=ref,
                              error=f"Element '{ref}' is visible but expected hidden")
        except Exception as e:
            return ActionResult(success=False, action="expect_hidden", ref=ref, error=str(e))

    async def expect_text(self, ref: str, text: str, timeout: int = 5000) -> ActionResult:
        """
        Assert that an element contains specific text.

        Args:
            ref: Element ref from snapshot
            text: Expected text (partial match)
            timeout: Max time to wait for element (ms)

        Returns:
            ActionResult with success status
        """
        try:
            result = await self.get_text(ref, timeout=timeout)
            if result.success:
                actual_text = result.data.get("text", "")
                if text in actual_text:
                    return ActionResult(success=True, action="expect_text", ref=ref,
                                      data={"expected": text, "actual": actual_text})
                return ActionResult(success=False, action="expect_text", ref=ref,
                                  error=f"Expected text '{text}' not found in '{actual_text}'")
            return ActionResult(success=False, action="expect_text", ref=ref, error=result.error)
        except Exception as e:
            return ActionResult(success=False, action="expect_text", ref=ref, error=str(e))

    async def expect_value(self, ref: str, value: str, timeout: int = 5000) -> ActionResult:
        """
        Assert that an input element has a specific value.

        Args:
            ref: Element ref from snapshot
            value: Expected value (exact match)
            timeout: Max time to wait for element (ms)

        Returns:
            ActionResult with success status
        """
        try:
            result = await self.get_value(ref, timeout=timeout)
            if result.success:
                actual_value = result.data.get("value", "")
                if actual_value == value:
                    return ActionResult(success=True, action="expect_value", ref=ref,
                                      data={"expected": value, "actual": actual_value})
                return ActionResult(success=False, action="expect_value", ref=ref,
                                  error=f"Expected value '{value}' but got '{actual_value}'")
            return ActionResult(success=False, action="expect_value", ref=ref, error=result.error)
        except Exception as e:
            return ActionResult(success=False, action="expect_value", ref=ref, error=str(e))

    async def expect_url(self, pattern: str, timeout: int = 5000) -> ActionResult:
        """
        Assert that the current URL matches a pattern.

        Args:
            pattern: Regex pattern to match against URL
            timeout: Max time to wait (ms) - currently unused but kept for API consistency

        Returns:
            ActionResult with success status
        """
        try:
            current_url = self.page.url
            if re.search(pattern, current_url):
                return ActionResult(success=True, action="expect_url",
                                  data={"pattern": pattern, "url": current_url})
            return ActionResult(success=False, action="expect_url",
                              error=f"URL '{current_url}' does not match pattern '{pattern}'")
        except Exception as e:
            return ActionResult(success=False, action="expect_url", error=str(e))

    async def expect_title(self, pattern: str, timeout: int = 5000) -> ActionResult:
        """
        Assert that the page title matches a pattern.

        Args:
            pattern: Regex pattern to match against title
            timeout: Max time to wait (ms) - currently unused but kept for API consistency

        Returns:
            ActionResult with success status
        """
        try:
            title = await self.page.title()
            if re.search(pattern, title):
                return ActionResult(success=True, action="expect_title",
                                  data={"pattern": pattern, "title": title})
            return ActionResult(success=False, action="expect_title",
                              error=f"Title '{title}' does not match pattern '{pattern}'")
        except Exception as e:
            return ActionResult(success=False, action="expect_title", error=str(e))

    async def count_elements(self, role: str = None, name: str = None) -> ActionResult:
        """
        Count elements matching role and/or name.

        Args:
            role: Element role to filter by (optional)
            name: Element name to filter by (optional, partial match)

        Returns:
            ActionResult with count in data dict
        """
        try:
            snapshot = await self.snapshot()
            elements = snapshot.elements

            if role:
                elements = [e for e in elements if e.role == role]
            if name:
                name_lower = name.lower()
                elements = [e for e in elements if name_lower in (e.name or "").lower()]

            return ActionResult(success=True, action="count_elements",
                              data={"count": len(elements), "role": role, "name": name})
        except Exception as e:
            return ActionResult(success=False, action="count_elements", error=str(e))

    async def expect_count(self, count: int, role: str = None, name: str = None) -> ActionResult:
        """
        Assert that the number of matching elements equals count.

        Args:
            count: Expected element count
            role: Element role to filter by (optional)
            name: Element name to filter by (optional, partial match)

        Returns:
            ActionResult with success status
        """
        try:
            result = await self.count_elements(role=role, name=name)
            if result.success:
                actual_count = result.data.get("count", 0)
                if actual_count == count:
                    return ActionResult(success=True, action="expect_count",
                                      data={"expected": count, "actual": actual_count})
                return ActionResult(success=False, action="expect_count",
                                  error=f"Expected {count} elements but found {actual_count}")
            return ActionResult(success=False, action="expect_count", error=result.error)
        except Exception as e:
            return ActionResult(success=False, action="expect_count", error=str(e))

    async def get_inner_html(self, ref: str, timeout: int = 5000) -> ActionResult:
        """
        Get the inner HTML of an element.

        Args:
            ref: Element ref from snapshot
            timeout: Max time to wait for element (ms)

        Returns:
            ActionResult with HTML in data dict
        """
        locator = await self._get_locator(ref)
        if not locator:
            return ActionResult(success=False, action="get_inner_html", ref=ref,
                              error=f"Ref '{ref}' not found")
        try:
            html = await locator.inner_html(timeout=timeout)
            return ActionResult(success=True, action="get_inner_html", ref=ref, data={"html": html})
        except Exception as e:
            return ActionResult(success=False, action="get_inner_html", ref=ref, error=str(e))

    async def get_outer_html(self, ref: str, timeout: int = 5000) -> ActionResult:
        """
        Get the outer HTML of an element.

        Args:
            ref: Element ref from snapshot
            timeout: Max time to wait for element (ms)

        Returns:
            ActionResult with HTML in data dict
        """
        locator = await self._get_locator(ref)
        if not locator:
            return ActionResult(success=False, action="get_outer_html", ref=ref,
                              error=f"Ref '{ref}' not found")
        try:
            html = await locator.evaluate("el => el.outerHTML")
            return ActionResult(success=True, action="get_outer_html", ref=ref, data={"html": html})
        except Exception as e:
            return ActionResult(success=False, action="get_outer_html", ref=ref, error=str(e))


# === Convenience function ===

async def create_browser(**kwargs) -> A11yBrowser:
    """
    Create and launch a browser instance.

    Args:
        **kwargs: Arguments to pass to A11yBrowser constructor
                  (headless, slow_mo, viewport, user_agent)

    Returns:
        Launched A11yBrowser instance

    Example:
        browser = await create_browser(headless=False)
        await browser.navigate("https://example.com")
        ...
        await browser.close()
    """
    browser = A11yBrowser(**kwargs)
    await browser.launch()
    return browser


# === Example usage ===

async def example() -> None:
    """Example usage of A11yBrowser."""
    print("A11yBrowser Example")
    print("=" * 60)

    async with A11yBrowser(headless=False, slow_mo=500) as browser:
        # Navigate
        print("\n1. Navigating to Google...")
        result = await browser.navigate("https://google.com")
        print(f"   Result: {result.success}")

        # Get snapshot - this shows all interactive elements with refs
        print("\n2. Getting accessibility snapshot...")
        snapshot = await browser.snapshot()
        print(f"   Found {len(snapshot.elements)} elements")
        print(f"\n   First 10 elements:")
        for el in snapshot.elements[:10]:
            print(f"   {el}")

        # Find the search box and type
        print("\n3. Finding search box...")
        search_boxes = snapshot.find_by_role("searchbox") or snapshot.find_by_role("textbox")
        if search_boxes:
            ref = search_boxes[0].ref
            print(f"   Found: {search_boxes[0]}")

            print(f"\n4. Typing into search box...")
            await browser.type(ref, "Playwright MCP")

            print(f"\n5. Pressing Enter...")
            await browser.press("Enter")
        else:
            print("   No search box found!")

        # Wait and take screenshot
        print("\n6. Waiting 2 seconds...")
        await browser.wait(2)

        print("\n7. Taking screenshot...")
        result = await browser.screenshot("example_result.png")
        if result.success:
            print(f"   Saved to: {result.data.get('path')}")

        print("\n8. Getting final snapshot...")
        final_snapshot = await browser.snapshot()
        print(f"   Final URL: {final_snapshot.url}")
        print(f"   Final title: {final_snapshot.title}")

    print("\n" + "=" * 60)
    print("Example complete!")


if __name__ == "__main__":
    asyncio.run(example())
