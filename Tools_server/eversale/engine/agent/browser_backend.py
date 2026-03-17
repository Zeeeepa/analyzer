"""
Browser Backend Abstraction Layer

Provides a unified interface for browser automation that can be implemented
by different backend technologies (Playwright, CDP, etc.).

This enables:
1. Session reuse across different automation tools
2. Incremental migration from one backend to another
3. Testing different backends without changing high-level code
4. Using existing Chrome sessions via CDP for login persistence

Key Concepts:
- SnapshotResult: Structured page state with actionable element refs
- InteractionResult: Outcome of user interactions (click, type, etc.)
- BrowserBackend: Abstract interface all implementations must follow
- BackendFactory: Auto-detection and creation of appropriate backend
"""

import os
import json
import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from pathlib import Path
from loguru import logger


@dataclass
class ElementRef:
    """
    Reference to an actionable element on the page.

    Inspired by Microsoft Playwright MCP's element referencing system.
    Multiple targeting strategies for reliability.
    """
    # Unique marker ID (injected into DOM)
    mmid: str

    # Human-readable reference (e.g., "button:Submit", "link:About")
    ref: str

    # Element details
    role: str  # ARIA role (button, link, textbox, etc.)
    text: str  # Visible text content
    tag: str   # HTML tag name

    # Targeting strategies
    selector: str  # CSS selector
    href: Optional[str] = None
    name: Optional[str] = None
    id: Optional[str] = None
    placeholder: Optional[str] = None

    # Position and visibility
    rect: Optional[Dict[str, int]] = None  # {x, y, width, height}
    visible: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class SnapshotResult:
    """
    Structured representation of page state.

    Contains all information needed for AI to understand page
    and take actions (click, type, navigate, etc.).
    """
    url: str
    title: str

    # List of all actionable elements with refs
    elements: List[ElementRef]

    # Element lookup by mmid (for fast access)
    refs: Dict[str, ElementRef] = field(default_factory=dict)

    # Optional accessibility tree as text
    accessibility_tree: Optional[str] = None

    # Optional page summary
    summary: Optional[str] = None

    # Metadata
    timestamp: float = field(default_factory=lambda: asyncio.get_event_loop().time())

    def __post_init__(self):
        """Build refs lookup after initialization."""
        if not self.refs:
            self.refs = {el.mmid: el for el in self.elements}

    def get_by_mmid(self, mmid: str) -> Optional[ElementRef]:
        """Get element by mmid."""
        return self.refs.get(mmid)

    def get_by_role(self, role: str, text: Optional[str] = None) -> List[ElementRef]:
        """Get elements by role, optionally filtered by text."""
        results = [el for el in self.elements if el.role == role]
        if text:
            text_lower = text.lower()
            results = [el for el in results if text_lower in el.text.lower()]
        return results

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'url': self.url,
            'title': self.title,
            'elements': [el.to_dict() for el in self.elements],
            'accessibility_tree': self.accessibility_tree,
            'summary': self.summary,
            'timestamp': self.timestamp,
        }


@dataclass
class InteractionResult:
    """
    Result of a browser interaction (click, type, etc.).
    """
    success: bool

    # Error details if not successful
    error: Optional[str] = None
    error_type: Optional[str] = None  # "timeout", "not_found", "network", etc.

    # Optional proof of action
    screenshot: Optional[bytes] = None

    # Changed state (URL, DOM fingerprint, etc.)
    url: Optional[str] = None
    url_changed: bool = False
    dom_changed: bool = False

    # Performance metrics
    duration_ms: Optional[float] = None

    # Method used (for debugging)
    method: Optional[str] = None  # "mmid_selector", "coordinates", "fallback", etc.

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (excluding screenshot for size)."""
        d = asdict(self)
        d.pop('screenshot', None)  # Too large for logging
        return d


@dataclass
class NavigationResult:
    """Result of page navigation."""
    success: bool
    url: str
    title: Optional[str] = None
    error: Optional[str] = None
    load_time_ms: Optional[float] = None


@dataclass
class ObserveResult:
    """Result of observing page state (network, console, etc.)."""
    network_requests: List[Dict[str, Any]] = field(default_factory=list)
    console_messages: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class BrowserBackend(ABC):
    """
    Abstract base class for browser automation backends.

    All implementations (Playwright, CDP, etc.) must implement these methods.
    This ensures interchangeable backends.
    """

    def __init__(self, headless: bool = False, **kwargs):
        """
        Initialize backend.

        Args:
            headless: Run browser in headless mode
            **kwargs: Backend-specific configuration
        """
        self.headless = headless
        self.config = kwargs
        self._connected = False

    @abstractmethod
    async def connect(self) -> bool:
        """
        Connect to browser.

        Returns:
            True if connection successful
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close browser connection and cleanup."""
        pass

    @abstractmethod
    async def navigate(self, url: str, wait_until: str = 'load') -> NavigationResult:
        """
        Navigate to URL.

        Args:
            url: Target URL
            wait_until: When to consider navigation complete
                       ('load', 'domcontentloaded', 'networkidle')

        Returns:
            NavigationResult with success status
        """
        pass

    @abstractmethod
    async def snapshot(self) -> SnapshotResult:
        """
        Get structured snapshot of current page state.

        Returns:
            SnapshotResult with elements, refs, and accessibility tree
        """
        pass

    @abstractmethod
    async def click(self, ref: str, **kwargs) -> InteractionResult:
        """
        Click element by reference.

        Args:
            ref: Element reference (mmid, selector, etc.)
            **kwargs: Backend-specific options (timeout, force, etc.)

        Returns:
            InteractionResult with success status
        """
        pass

    @abstractmethod
    async def type(self, ref: str, text: str, clear: bool = True, **kwargs) -> InteractionResult:
        """
        Type text into element.

        Args:
            ref: Element reference (mmid, selector, etc.)
            text: Text to type
            clear: Clear existing text first
            **kwargs: Backend-specific options

        Returns:
            InteractionResult with success status
        """
        pass

    @abstractmethod
    async def scroll(self, direction: str = 'down', amount: int = 500) -> InteractionResult:
        """
        Scroll page.

        Args:
            direction: 'up' or 'down'
            amount: Pixels to scroll

        Returns:
            InteractionResult with new scroll position
        """
        pass

    @abstractmethod
    async def run_code(self, js: str) -> Any:
        """
        Execute JavaScript in page context.

        Args:
            js: JavaScript code to execute

        Returns:
            Result of JavaScript execution
        """
        pass

    @abstractmethod
    async def observe(self, network: bool = False, console: bool = False) -> ObserveResult:
        """
        Observe page state and events.

        Args:
            network: Include network requests
            console: Include console messages

        Returns:
            ObserveResult with collected data
        """
        pass

    @abstractmethod
    async def screenshot(self, full_page: bool = False) -> bytes:
        """
        Take screenshot of page.

        Args:
            full_page: Capture full scrollable page vs viewport only

        Returns:
            PNG screenshot bytes
        """
        pass

    @property
    def is_connected(self) -> bool:
        """Check if backend is connected."""
        return self._connected

    async def __aenter__(self):
        """Context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.disconnect()


class PlaywrightBackend(BrowserBackend):
    """
    Playwright implementation of BrowserBackend.

    Wraps existing playwright_direct.py functionality into the
    unified backend interface.
    """

    def __init__(self, headless: bool = False, **kwargs):
        super().__init__(headless, **kwargs)
        self.pw = None
        self.page = None
        self._mmid_elements: Dict[str, ElementRef] = {}

    async def connect(self) -> bool:
        """Launch Playwright browser."""
        try:
            # Import playwright_direct's DirectPlaywright
            from .playwright_direct import DirectPlaywright

            # Create instance with stealth mode
            self.pw = DirectPlaywright(headless=self.headless)
            await self.pw.launch()

            self.page = self.pw.page
            self._connected = True

            logger.debug("PlaywrightBackend connected")
            return True

        except Exception as e:
            logger.error(f"PlaywrightBackend connection failed: {e}")
            return False

    async def disconnect(self) -> None:
        """Close Playwright browser."""
        try:
            if self.pw:
                await self.pw.close()
                self.pw = None
                self.page = None
                self._connected = False
                logger.debug("PlaywrightBackend disconnected")
        except Exception as e:
            logger.error(f"PlaywrightBackend disconnect error: {e}")

    async def navigate(self, url: str, wait_until: str = 'load') -> NavigationResult:
        """Navigate using Playwright."""
        try:
            start = asyncio.get_event_loop().time()
            result = await self.pw.navigate(url)
            duration = (asyncio.get_event_loop().time() - start) * 1000

            if result.get('success'):
                title = await self.page.title() if self.page else None
                return NavigationResult(
                    success=True,
                    url=result.get('url', url),
                    title=title,
                    load_time_ms=duration
                )
            else:
                return NavigationResult(
                    success=False,
                    url=url,
                    error=result.get('error', 'Navigation failed')
                )
        except Exception as e:
            return NavigationResult(success=False, url=url, error=str(e))

    async def snapshot(self) -> SnapshotResult:
        """Get snapshot using Playwright's browser_snapshot."""
        try:
            result = await self.pw.browser_snapshot()

            if result.get('error'):
                raise Exception(result['error'])

            # Convert to ElementRef objects
            elements = []
            for el_dict in result.get('elements', []):
                el = ElementRef(
                    mmid=el_dict.get('mmid'),
                    ref=el_dict.get('ref'),
                    role=el_dict.get('role'),
                    text=el_dict.get('text', ''),
                    tag=el_dict.get('tag'),
                    selector=el_dict.get('selector'),
                    href=el_dict.get('href'),
                    name=el_dict.get('name'),
                    id=el_dict.get('id'),
                    placeholder=el_dict.get('placeholder'),
                    rect=el_dict.get('rect'),
                    visible=el_dict.get('visible', True)
                )
                elements.append(el)
                self._mmid_elements[el.mmid] = el

            return SnapshotResult(
                url=result.get('url', ''),
                title=result.get('title', ''),
                elements=elements,
                summary=result.get('summary')
            )

        except Exception as e:
            logger.error(f"PlaywrightBackend snapshot error: {e}")
            # Return empty snapshot on error
            return SnapshotResult(url='', title='', elements=[])

    async def click(self, ref: str, **kwargs) -> InteractionResult:
        """Click using Playwright's click_by_mmid."""
        try:
            start = asyncio.get_event_loop().time()

            # Handle both mmid and selector refs
            if ref.startswith('mm'):
                result = await self.pw.click_by_mmid(ref)
            else:
                result = await self.pw.click(ref)

            duration = (asyncio.get_event_loop().time() - start) * 1000

            if result.get('success'):
                return InteractionResult(
                    success=True,
                    url=result.get('url'),
                    method=result.get('method', 'playwright'),
                    duration_ms=duration
                )
            else:
                return InteractionResult(
                    success=False,
                    error=result.get('error', 'Click failed'),
                    error_type='click_failed'
                )

        except Exception as e:
            logger.error(f"PlaywrightBackend click error: {e}")
            return InteractionResult(success=False, error=str(e), error_type='exception')

    async def type(self, ref: str, text: str, clear: bool = True, **kwargs) -> InteractionResult:
        """Type using Playwright's type_by_mmid."""
        try:
            start = asyncio.get_event_loop().time()

            # Handle both mmid and selector refs
            if ref.startswith('mm'):
                result = await self.pw.type_by_mmid(ref, text, clear=clear)
            else:
                # Fallback to selector-based typing
                from .playwright_direct import handle_error
                try:
                    element = await self.page.query_selector(ref)
                    if not element:
                        raise Exception(f"Element not found: {ref}")

                    if clear:
                        await element.fill('')
                    await element.type(text)
                    result = {'success': True}
                except Exception as e:
                    result = {'error': str(e)}

            duration = (asyncio.get_event_loop().time() - start) * 1000

            if result.get('success'):
                return InteractionResult(
                    success=True,
                    duration_ms=duration
                )
            else:
                return InteractionResult(
                    success=False,
                    error=result.get('error', 'Type failed'),
                    error_type='type_failed'
                )

        except Exception as e:
            logger.error(f"PlaywrightBackend type error: {e}")
            return InteractionResult(success=False, error=str(e), error_type='exception')

    async def scroll(self, direction: str = 'down', amount: int = 500) -> InteractionResult:
        """Scroll using Playwright."""
        try:
            result = await self.pw.browser_scroll(direction=direction, amount=amount)

            if result.get('success'):
                return InteractionResult(
                    success=True,
                    method='scroll'
                )
            else:
                return InteractionResult(
                    success=False,
                    error=result.get('error', 'Scroll failed')
                )
        except Exception as e:
            return InteractionResult(success=False, error=str(e))

    async def run_code(self, js: str) -> Any:
        """Execute JavaScript via Playwright."""
        try:
            if not self.page:
                raise Exception("Page not available")
            return await self.page.evaluate(js)
        except Exception as e:
            logger.error(f"PlaywrightBackend run_code error: {e}")
            return None

    async def observe(self, network: bool = False, console: bool = False) -> ObserveResult:
        """Observe page events."""
        result = ObserveResult()

        # Note: Full network/console monitoring would require
        # setting up listeners at page creation time.
        # This is a simplified implementation.

        if console:
            # Could implement console message collection
            pass

        if network:
            # Could implement network request collection
            pass

        return result

    async def screenshot(self, full_page: bool = False) -> bytes:
        """Take screenshot via Playwright."""
        try:
            if not self.page:
                raise Exception("Page not available")
            return await self.page.screenshot(full_page=full_page)
        except Exception as e:
            logger.error(f"PlaywrightBackend screenshot error: {e}")
            return b''


class CDPBackend(BrowserBackend):
    """
    Chrome DevTools Protocol (CDP) implementation.

    Connects to an existing Chrome instance via CDP.
    Useful for reusing existing login sessions.
    """

    def __init__(self, headless: bool = False, cdp_url: str = None, **kwargs):
        super().__init__(headless, **kwargs)
        self.cdp_url = cdp_url or self._detect_chrome_cdp()
        self.client = None
        self.page_id = None
        self._mmid_elements: Dict[str, ElementRef] = {}

    def _detect_chrome_cdp(self) -> Optional[str]:
        """
        Auto-detect running Chrome with CDP enabled.

        Checks common debug ports (9222, 9223, etc.).
        """
        import socket

        ports = [9222, 9223, 9224, 9333]
        for port in ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.5)
                result = sock.connect_ex(('localhost', port))
                sock.close()

                if result == 0:
                    logger.debug(f"Found Chrome CDP on port {port}")
                    return f"http://localhost:{port}"
            except Exception:
                continue

        return None

    async def connect(self) -> bool:
        """Connect to Chrome via CDP."""
        try:
            if not self.cdp_url:
                logger.warning("No Chrome CDP endpoint found. Start Chrome with: chrome --remote-debugging-port=9222")
                return False

            # Use pychrome or playwright's CDP connection
            try:
                # Try playwright's CDP connect
                from playwright.async_api import async_playwright

                pw = await async_playwright().start()
                browser = await pw.chromium.connect_over_cdp(self.cdp_url)
                contexts = browser.contexts

                if contexts:
                    context = contexts[0]
                    pages = context.pages
                    if pages:
                        self.page = pages[0]
                        self._connected = True
                        logger.debug(f"CDPBackend connected to existing Chrome session")
                        return True

                logger.warning("No pages found in Chrome session")
                return False

            except ImportError:
                logger.error("Playwright not available for CDP connection")
                return False

        except Exception as e:
            logger.error(f"CDPBackend connection failed: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from CDP (don't close browser)."""
        # Don't close the browser since it's an existing session
        self.client = None
        self.page = None
        self._connected = False
        logger.debug("CDPBackend disconnected (browser left running)")

    async def navigate(self, url: str, wait_until: str = 'load') -> NavigationResult:
        """Navigate using CDP."""
        try:
            if not self.page:
                raise Exception("Not connected to page")

            start = asyncio.get_event_loop().time()
            await self.page.goto(url, wait_until=wait_until)
            duration = (asyncio.get_event_loop().time() - start) * 1000

            title = await self.page.title()
            return NavigationResult(
                success=True,
                url=url,
                title=title,
                load_time_ms=duration
            )
        except Exception as e:
            return NavigationResult(success=False, url=url, error=str(e))

    async def snapshot(self) -> SnapshotResult:
        """
        Get snapshot using same MMID injection as Playwright.

        Reuses the accessibility snapshot JavaScript from playwright_direct.
        """
        try:
            if not self.page:
                raise Exception("Not connected to page")

            # Same MMID injection logic as PlaywrightBackend
            elements_data = await self.page.evaluate("""() => {
                const MMID_ATTR = 'data-mmid';
                let mmidCounter = 0;
                const elements = [];

                // Clear old mmids
                document.querySelectorAll('[' + MMID_ATTR + ']').forEach(el => {
                    el.removeAttribute(MMID_ATTR);
                });

                // Get all interactive elements
                const interactiveSelectors = [
                    'a[href]', 'button', 'input', 'textarea', 'select',
                    '[role="button"]', '[role="link"]', '[role="menuitem"]',
                    '[role="tab"]', '[role="checkbox"]', '[role="radio"]',
                    '[onclick]', '[tabindex]:not([tabindex="-1"])'
                ];

                const allInteractive = document.querySelectorAll(interactiveSelectors.join(','));

                allInteractive.forEach(el => {
                    const rect = el.getBoundingClientRect();
                    if (rect.width === 0 || rect.height === 0) return;

                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden') return;

                    const mmid = 'mm' + (mmidCounter++);
                    el.setAttribute(MMID_ATTR, mmid);

                    const tag = el.tagName.toLowerCase();
                    let role = el.getAttribute('role') || tag;

                    let text = '';
                    if (tag === 'input' || tag === 'textarea') {
                        text = el.placeholder || el.value || el.getAttribute('aria-label') || '';
                    } else {
                        text = el.innerText || el.textContent || '';
                    }
                    text = text.trim().slice(0, 80);

                    const ref = role + (text ? ':' + text.slice(0, 30) : '');

                    elements.push({
                        mmid,
                        ref,
                        role,
                        text: text || '[no text]',
                        tag,
                        href: el.href || null,
                        name: el.name || null,
                        id: el.id || null,
                        placeholder: el.placeholder || null,
                        selector: '[' + MMID_ATTR + '="' + mmid + '"]',
                        rect: {
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height)
                        }
                    });
                });

                return elements;
            }""")

            # Convert to ElementRef objects
            elements = []
            for el_dict in elements_data:
                el = ElementRef(**el_dict)
                elements.append(el)
                self._mmid_elements[el.mmid] = el

            url = self.page.url
            title = await self.page.title()

            return SnapshotResult(
                url=url,
                title=title,
                elements=elements
            )

        except Exception as e:
            logger.error(f"CDPBackend snapshot error: {e}")
            return SnapshotResult(url='', title='', elements=[])

    async def click(self, ref: str, **kwargs) -> InteractionResult:
        """Click using CDP."""
        try:
            if not self.page:
                raise Exception("Not connected to page")

            start = asyncio.get_event_loop().time()

            # If mmid ref, use data-mmid selector
            if ref.startswith('mm'):
                selector = f'[data-mmid="{ref}"]'
            else:
                selector = ref

            await self.page.click(selector, timeout=kwargs.get('timeout', 5000))
            duration = (asyncio.get_event_loop().time() - start) * 1000

            return InteractionResult(
                success=True,
                url=self.page.url,
                duration_ms=duration,
                method='cdp'
            )

        except Exception as e:
            logger.error(f"CDPBackend click error: {e}")
            return InteractionResult(success=False, error=str(e), error_type='exception')

    async def type(self, ref: str, text: str, clear: bool = True, **kwargs) -> InteractionResult:
        """Type using CDP."""
        try:
            if not self.page:
                raise Exception("Not connected to page")

            start = asyncio.get_event_loop().time()

            # If mmid ref, use data-mmid selector
            if ref.startswith('mm'):
                selector = f'[data-mmid="{ref}"]'
            else:
                selector = ref

            if clear:
                await self.page.fill(selector, '')
            await self.page.type(selector, text)

            duration = (asyncio.get_event_loop().time() - start) * 1000

            return InteractionResult(
                success=True,
                duration_ms=duration,
                method='cdp'
            )

        except Exception as e:
            logger.error(f"CDPBackend type error: {e}")
            return InteractionResult(success=False, error=str(e), error_type='exception')

    async def scroll(self, direction: str = 'down', amount: int = 500) -> InteractionResult:
        """Scroll using CDP."""
        try:
            if not self.page:
                raise Exception("Not connected to page")

            y_delta = amount if direction.lower() == 'down' else -amount
            await self.page.evaluate(f"window.scrollBy(0, {y_delta})")

            return InteractionResult(success=True, method='scroll')

        except Exception as e:
            return InteractionResult(success=False, error=str(e))

    async def run_code(self, js: str) -> Any:
        """Execute JavaScript via CDP."""
        try:
            if not self.page:
                raise Exception("Not connected to page")
            return await self.page.evaluate(js)
        except Exception as e:
            logger.error(f"CDPBackend run_code error: {e}")
            return None

    async def observe(self, network: bool = False, console: bool = False) -> ObserveResult:
        """Observe page events via CDP."""
        # CDP has better network/console monitoring than Playwright
        # Could implement full request/response/console capture here
        return ObserveResult()

    async def screenshot(self, full_page: bool = False) -> bytes:
        """Take screenshot via CDP."""
        try:
            if not self.page:
                raise Exception("Not connected to page")
            return await self.page.screenshot(full_page=full_page)
        except Exception as e:
            logger.error(f"CDPBackend screenshot error: {e}")
            return b''


class BackendFactory:
    """
    Factory for creating and auto-detecting browser backends.

    Priority order:
    1. CDP (if Chrome is running with debug port)
    2. Playwright (always available)
    """

    @staticmethod
    def create(backend_type: str = 'auto', **kwargs) -> BrowserBackend:
        """
        Create browser backend.

        Args:
            backend_type: 'auto', 'playwright', or 'cdp'
            **kwargs: Backend-specific configuration

        Returns:
            BrowserBackend instance
        """
        if backend_type == 'auto':
            # Try to detect Chrome CDP first
            cdp = CDPBackend(**kwargs)
            if cdp.cdp_url:
                logger.info(f"Auto-detected Chrome CDP at {cdp.cdp_url}")
                return cdp

            # Fallback to Playwright
            logger.info("No Chrome CDP found, using Playwright")
            return PlaywrightBackend(**kwargs)

        elif backend_type == 'playwright':
            return PlaywrightBackend(**kwargs)

        elif backend_type == 'cdp':
            return CDPBackend(**kwargs)

        else:
            raise ValueError(f"Unknown backend type: {backend_type}")

    @staticmethod
    async def create_and_connect(backend_type: str = 'auto', **kwargs) -> Optional[BrowserBackend]:
        """
        Create backend and connect in one step.

        Returns:
            Connected backend or None if connection failed
        """
        backend = BackendFactory.create(backend_type, **kwargs)

        if await backend.connect():
            return backend
        else:
            logger.warning(f"Failed to connect {backend.__class__.__name__}")

            # If auto mode and CDP failed, try Playwright
            if backend_type == 'auto' and isinstance(backend, CDPBackend):
                logger.info("Falling back to Playwright after CDP failure")
                backend = PlaywrightBackend(**kwargs)
                if await backend.connect():
                    return backend

            return None


# Convenience functions
async def create_backend(backend_type: str = 'auto', **kwargs) -> Optional[BrowserBackend]:
    """
    Create and connect a browser backend.

    This is the main entry point for creating a backend.

    Example:
        backend = await create_backend('auto', headless=False)
        if backend:
            await backend.navigate('https://example.com')
            snapshot = await backend.snapshot()
            # ... use snapshot.elements for automation
            await backend.disconnect()
    """
    return await BackendFactory.create_and_connect(backend_type, **kwargs)


__all__ = [
    'ElementRef',
    'SnapshotResult',
    'InteractionResult',
    'NavigationResult',
    'ObserveResult',
    'BrowserBackend',
    'PlaywrightBackend',
    'CDPBackend',
    'BackendFactory',
    'create_backend',
]
