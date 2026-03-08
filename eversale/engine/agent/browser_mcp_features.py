#!/usr/bin/env python3
"""
Browser MCP Features - Techniques from Browser MCP Extensions

Implements features inspired by:
- BrowserMCP/mcp: CDP existing browser connection
- AgentDeskAI/browser-tools-mcp: Console monitoring, Lighthouse audits
- hangwin/mcp-chrome: Network body capture

These are NEW capabilities not previously in Eversale, enabling:
1. Connect to user's existing Chrome (with all logins intact)
2. Real-time console log monitoring for debugging
3. Full network request/response body capture via CDP
4. Lighthouse performance/accessibility/SEO audits

Author: Eversale Team
Date: December 2024
"""

import asyncio
import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from loguru import logger

# Feature availability flags
CDP_AVAILABLE = False
LIGHTHOUSE_AVAILABLE = False

# Check for Playwright CDP support
try:
    from playwright.async_api import async_playwright
    CDP_AVAILABLE = True
except ImportError:
    logger.warning("Playwright not available for CDP features")

# Check for Lighthouse CLI
try:
    result = subprocess.run(
        ["lighthouse", "--version"],
        capture_output=True,
        text=True,
        timeout=5
    )
    if result.returncode == 0:
        LIGHTHOUSE_AVAILABLE = True
        logger.debug(f"Lighthouse available: {result.stdout.strip()}")
except (subprocess.TimeoutExpired, FileNotFoundError):
    logger.info("Lighthouse CLI not found - audits disabled. Install: npm install -g lighthouse")


# ==============================================================================
# 1. CDP EXISTING BROWSER CONNECTION
# ==============================================================================
# Key insight from Browser MCP: Users want to use their EXISTING browser with
# all logins intact, not a fresh Playwright instance. This bypasses:
# - Login walls (already authenticated)
# - CAPTCHAs (real fingerprint)
# - Bot detection (genuine browser profile)
# ==============================================================================

@dataclass
class ExistingBrowserConnection:
    """
    Connect to user's existing Chrome browser via CDP.

    Usage:
        # User starts Chrome with: chrome --remote-debugging-port=9222
        conn = ExistingBrowserConnection(port=9222)
        context = await conn.connect()
        page = context.pages[0]  # Use existing tab
        # Now you have access to all logged-in sessions!

    Benefits:
        - Uses existing logins (Gmail, LinkedIn, Facebook, etc.)
        - Real browser fingerprint (bypasses most bot detection)
        - No CAPTCHA for authenticated sessions
        - User's cookies, extensions, and settings preserved
    """

    port: int = 9222
    host: str = "localhost"
    playwright: Any = None
    browser: Any = None
    context: Any = None
    _connected: bool = False

    async def connect(self) -> Any:
        """
        Connect to existing Chrome browser via CDP.

        Returns:
            BrowserContext with access to all existing tabs and sessions.

        Raises:
            ConnectionError: If Chrome is not running with remote debugging.
        """
        if not CDP_AVAILABLE:
            raise ImportError("Playwright required for CDP connection")

        cdp_url = f"http://{self.host}:{self.port}"
        logger.info(f"Connecting to existing browser at {cdp_url}")

        try:
            self.playwright = await async_playwright().start()

            # Connect over CDP - this attaches to the existing browser
            self.browser = await self.playwright.chromium.connect_over_cdp(cdp_url)

            # Get the default context (user's existing browser context)
            contexts = self.browser.contexts
            if contexts:
                self.context = contexts[0]
                logger.info(f"Connected to existing browser with {len(self.context.pages)} tab(s)")
            else:
                # Create new context if none exists (shouldn't happen with user browser)
                self.context = await self.browser.new_context()
                logger.warning("No existing context, created new one")

            self._connected = True
            return self.context

        except Exception as e:
            error_msg = str(e)
            if "connect ECONNREFUSED" in error_msg or "Failed to connect" in error_msg:
                raise ConnectionError(
                    f"Cannot connect to Chrome at {cdp_url}. "
                    f"Please start Chrome with: chrome --remote-debugging-port={self.port}"
                ) from e
            raise

    async def get_pages(self) -> List[Any]:
        """Get all open pages/tabs in the browser."""
        if not self._connected or not self.context:
            raise RuntimeError("Not connected. Call connect() first.")
        return self.context.pages

    async def get_current_page(self) -> Any:
        """Get the currently active page."""
        pages = await self.get_pages()
        # Return the most recently used page (last in list typically)
        return pages[-1] if pages else None

    async def new_page(self) -> Any:
        """Create a new page in the existing browser."""
        if not self._connected or not self.context:
            raise RuntimeError("Not connected. Call connect() first.")
        return await self.context.new_page()

    async def disconnect(self):
        """Disconnect from browser (doesn't close the browser)."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self._connected = False
        logger.info("Disconnected from existing browser")

    @staticmethod
    def get_chrome_launch_command(port: int = 9222) -> str:
        """Get the command to launch Chrome with remote debugging."""
        import platform
        system = platform.system()

        if system == "Windows":
            return f'"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port={port}'
        elif system == "Darwin":  # macOS
            return f'"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port={port}'
        else:  # Linux
            return f"google-chrome --remote-debugging-port={port}"


async def connect_to_existing_browser(port: int = 9222) -> ExistingBrowserConnection:
    """
    Convenience function to connect to an existing Chrome browser.

    Example:
        conn = await connect_to_existing_browser(9222)
        page = await conn.get_current_page()
        await page.goto("https://mail.google.com")  # Already logged in!
    """
    conn = ExistingBrowserConnection(port=port)
    await conn.connect()
    return conn


# ==============================================================================
# 2. CONSOLE LOG MONITORING
# ==============================================================================
# Key insight from BrowserTools MCP: Capture all console.log messages in
# real-time for debugging. Helps detect:
# - JavaScript errors before they cause failures
# - Authentication errors
# - API failures
# - Debug information
# ==============================================================================

@dataclass
class ConsoleLogEntry:
    """A captured console log entry."""
    type: str  # log, warn, error, info, debug
    text: str
    url: str
    timestamp: float
    location: Optional[str] = None  # file:line:col
    args: List[str] = field(default_factory=list)


class ConsoleMonitor:
    """
    Real-time console log monitoring for Playwright pages.

    Usage:
        monitor = ConsoleMonitor()
        await monitor.attach(page)

        # ... do stuff with page ...

        # Get all logs
        logs = monitor.get_logs()
        errors = monitor.get_errors()

        # Or use callback for real-time
        monitor.on_log(lambda entry: print(f"[{entry.type}] {entry.text}"))

    Key Feature: Captures logs that would otherwise be invisible,
    making debugging much easier when automation fails.
    """

    def __init__(self, max_entries: int = 1000):
        self.logs: List[ConsoleLogEntry] = []
        self.max_entries = max_entries
        self._callbacks: List[Callable[[ConsoleLogEntry], None]] = []
        self._page_errors: List[Dict[str, Any]] = []
        self._attached_pages: set = set()

    async def attach(self, page) -> None:
        """
        Attach monitor to a Playwright page.

        Args:
            page: Playwright page object
        """
        page_id = id(page)
        if page_id in self._attached_pages:
            logger.debug("Console monitor already attached to this page")
            return

        # Monitor console messages
        page.on("console", self._handle_console_message)

        # Monitor page errors (uncaught exceptions)
        page.on("pageerror", self._handle_page_error)

        self._attached_pages.add(page_id)
        logger.debug(f"Console monitor attached to page: {page.url}")

    def _handle_console_message(self, msg) -> None:
        """Handle incoming console message."""
        try:
            entry = ConsoleLogEntry(
                type=msg.type,
                text=msg.text,
                url=msg.page.url if msg.page else "",
                timestamp=time.time(),
                location=f"{msg.location.get('url', '')}:{msg.location.get('lineNumber', '')}:{msg.location.get('columnNumber', '')}" if hasattr(msg, 'location') and msg.location else None,
            )

            self.logs.append(entry)

            # Trim old entries
            if len(self.logs) > self.max_entries:
                self.logs = self.logs[-self.max_entries:]

            # Call registered callbacks
            for callback in self._callbacks:
                try:
                    callback(entry)
                except Exception as e:
                    logger.error(f"Console callback error: {e}")

        except Exception as e:
            logger.error(f"Error handling console message: {e}")

    def _handle_page_error(self, error) -> None:
        """Handle page errors (uncaught exceptions)."""
        self._page_errors.append({
            "error": str(error),
            "timestamp": time.time()
        })

        # Also log as console error
        entry = ConsoleLogEntry(
            type="error",
            text=f"Page Error: {error}",
            url="",
            timestamp=time.time()
        )
        self.logs.append(entry)

        for callback in self._callbacks:
            try:
                callback(entry)
            except Exception:
                pass

    def on_log(self, callback: Callable[[ConsoleLogEntry], None]) -> None:
        """Register callback for real-time log notifications."""
        self._callbacks.append(callback)

    def get_logs(self,
                 log_type: Optional[str] = None,
                 since: Optional[float] = None,
                 contains: Optional[str] = None) -> List[ConsoleLogEntry]:
        """
        Get captured logs with optional filtering.

        Args:
            log_type: Filter by type (log, warn, error, info)
            since: Only logs after this timestamp
            contains: Only logs containing this text

        Returns:
            Filtered list of console log entries
        """
        result = self.logs

        if log_type:
            result = [l for l in result if l.type == log_type]

        if since:
            result = [l for l in result if l.timestamp >= since]

        if contains:
            result = [l for l in result if contains.lower() in l.text.lower()]

        return result

    def get_errors(self) -> List[ConsoleLogEntry]:
        """Get only error-level logs."""
        return self.get_logs(log_type="error")

    def get_warnings(self) -> List[ConsoleLogEntry]:
        """Get only warning-level logs."""
        return self.get_logs(log_type="warning")

    def get_page_errors(self) -> List[Dict[str, Any]]:
        """Get uncaught page errors."""
        return self._page_errors.copy()

    def clear(self) -> None:
        """Clear all captured logs."""
        self.logs.clear()
        self._page_errors.clear()

    def to_dict(self) -> List[Dict[str, Any]]:
        """Export logs as list of dicts."""
        return [
            {
                "type": l.type,
                "text": l.text,
                "url": l.url,
                "timestamp": l.timestamp,
                "location": l.location
            }
            for l in self.logs
        ]


# ==============================================================================
# 3. NETWORK BODY CAPTURE VIA CDP
# ==============================================================================
# Key insight from BrowserTools MCP: Capture full request/response bodies
# using CDP Debugger API. This enables:
# - See what API calls a page makes
# - Capture authentication tokens
# - Replicate AJAX requests directly
# - Debug failed API calls
# ==============================================================================

@dataclass
class NetworkEntry:
    """A captured network request/response."""
    request_id: str
    url: str
    method: str
    status: Optional[int] = None
    request_headers: Dict[str, str] = field(default_factory=dict)
    response_headers: Dict[str, str] = field(default_factory=dict)
    request_body: Optional[str] = None
    response_body: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    resource_type: str = "other"
    error: Optional[str] = None


class NetworkCapture:
    """
    Full network request/response capture via CDP.

    Usage:
        capture = NetworkCapture()
        await capture.attach(page)

        # ... navigate and interact ...

        # Get all captured requests
        requests = capture.get_requests()

        # Find specific API calls
        api_calls = capture.get_requests(url_contains="/api/")

        # Get response bodies
        for req in api_calls:
            print(f"{req.url}: {req.response_body[:100]}")

    Key Feature: Unlike regular network monitoring, this captures
    the actual response BODIES, not just headers.
    """

    def __init__(self,
                 capture_bodies: bool = True,
                 max_body_size: int = 1_000_000,  # 1MB max per body
                 max_entries: int = 500):
        self.entries: Dict[str, NetworkEntry] = {}  # request_id -> entry
        self.capture_bodies = capture_bodies
        self.max_body_size = max_body_size
        self.max_entries = max_entries
        self._cdp_session = None
        self._attached = False

    async def attach(self, page) -> None:
        """
        Attach network capture to page via CDP session.

        Args:
            page: Playwright page object
        """
        if self._attached:
            logger.debug("Network capture already attached")
            return

        try:
            # Create CDP session
            self._cdp_session = await page.context.new_cdp_session(page)

            # Enable network domain
            await self._cdp_session.send("Network.enable")

            # Set up event handlers
            self._cdp_session.on("Network.requestWillBeSent", self._on_request)
            self._cdp_session.on("Network.responseReceived", self._on_response)
            self._cdp_session.on("Network.loadingFinished", self._on_loading_finished)
            self._cdp_session.on("Network.loadingFailed", self._on_loading_failed)

            self._attached = True
            logger.debug("Network capture attached via CDP")

        except Exception as e:
            logger.error(f"Failed to attach network capture: {e}")
            raise

    def _on_request(self, params: Dict[str, Any]) -> None:
        """Handle outgoing request."""
        request_id = params.get("requestId")
        request = params.get("request", {})

        entry = NetworkEntry(
            request_id=request_id,
            url=request.get("url", ""),
            method=request.get("method", "GET"),
            request_headers=request.get("headers", {}),
            resource_type=params.get("type", "other").lower()
        )

        # Capture request body if present
        if self.capture_bodies and request.get("postData"):
            body = request.get("postData", "")
            if len(body) <= self.max_body_size:
                entry.request_body = body

        self.entries[request_id] = entry
        self._trim_entries()

    def _on_response(self, params: Dict[str, Any]) -> None:
        """Handle response received."""
        request_id = params.get("requestId")
        response = params.get("response", {})

        if request_id in self.entries:
            entry = self.entries[request_id]
            entry.status = response.get("status")
            entry.response_headers = response.get("headers", {})

    def _on_loading_finished(self, params: Dict[str, Any]) -> None:
        """Handle loading finished - now we can get response body."""
        if not self.capture_bodies:
            return

        request_id = params.get("requestId")
        if request_id not in self.entries:
            return

        # Schedule body retrieval (can't await in sync callback)
        asyncio.create_task(self._fetch_response_body(request_id))

    async def _fetch_response_body(self, request_id: str) -> None:
        """Fetch response body via CDP."""
        if not self._cdp_session or request_id not in self.entries:
            return

        try:
            result = await self._cdp_session.send(
                "Network.getResponseBody",
                {"requestId": request_id}
            )

            body = result.get("body", "")
            is_base64 = result.get("base64Encoded", False)

            # Skip binary content
            if is_base64:
                body = f"[Base64 encoded, {len(body)} chars]"
            elif len(body) > self.max_body_size:
                body = body[:self.max_body_size] + f"... [truncated, total {len(body)} chars]"

            self.entries[request_id].response_body = body

        except Exception as e:
            # Some responses don't have bodies (redirects, etc.)
            if "No resource with given identifier" not in str(e):
                logger.debug(f"Could not get response body for {request_id}: {e}")

    def _on_loading_failed(self, params: Dict[str, Any]) -> None:
        """Handle loading failed."""
        request_id = params.get("requestId")
        if request_id in self.entries:
            self.entries[request_id].error = params.get("errorText", "Unknown error")

    def _trim_entries(self) -> None:
        """Keep entries under max limit."""
        if len(self.entries) > self.max_entries:
            # Remove oldest entries
            sorted_ids = sorted(
                self.entries.keys(),
                key=lambda k: self.entries[k].timestamp
            )
            for request_id in sorted_ids[:len(self.entries) - self.max_entries]:
                del self.entries[request_id]

    def get_requests(self,
                     url_contains: Optional[str] = None,
                     method: Optional[str] = None,
                     status: Optional[int] = None,
                     resource_type: Optional[str] = None,
                     has_body: bool = False) -> List[NetworkEntry]:
        """
        Get captured network requests with optional filtering.

        Args:
            url_contains: Filter by URL substring
            method: Filter by HTTP method (GET, POST, etc.)
            status: Filter by status code
            resource_type: Filter by type (xhr, fetch, document, etc.)
            has_body: Only include requests with response body

        Returns:
            List of matching network entries
        """
        result = list(self.entries.values())

        if url_contains:
            result = [e for e in result if url_contains in e.url]

        if method:
            result = [e for e in result if e.method.upper() == method.upper()]

        if status:
            result = [e for e in result if e.status == status]

        if resource_type:
            result = [e for e in result if e.resource_type == resource_type]

        if has_body:
            result = [e for e in result if e.response_body]

        return sorted(result, key=lambda e: e.timestamp)

    def get_api_calls(self) -> List[NetworkEntry]:
        """Get XHR/Fetch API calls (most commonly needed)."""
        return [
            e for e in self.entries.values()
            if e.resource_type in ("xhr", "fetch")
        ]

    def find_auth_tokens(self) -> List[Dict[str, str]]:
        """
        Find potential authentication tokens in requests/responses.

        Returns:
            List of dicts with token info
        """
        tokens = []
        auth_patterns = ["bearer", "authorization", "token", "api-key", "x-auth"]

        for entry in self.entries.values():
            # Check request headers
            for header, value in entry.request_headers.items():
                if any(p in header.lower() for p in auth_patterns):
                    tokens.append({
                        "source": "request_header",
                        "header": header,
                        "value": value[:50] + "..." if len(value) > 50 else value,
                        "url": entry.url
                    })

            # Check response headers
            for header, value in entry.response_headers.items():
                if any(p in header.lower() for p in auth_patterns):
                    tokens.append({
                        "source": "response_header",
                        "header": header,
                        "value": value[:50] + "..." if len(value) > 50 else value,
                        "url": entry.url
                    })

        return tokens

    def to_har(self) -> Dict[str, Any]:
        """Export captured requests in HAR format (partial)."""
        entries = []
        for entry in self.entries.values():
            entries.append({
                "request": {
                    "method": entry.method,
                    "url": entry.url,
                    "headers": [{"name": k, "value": v} for k, v in entry.request_headers.items()],
                    "postData": {"text": entry.request_body} if entry.request_body else None
                },
                "response": {
                    "status": entry.status,
                    "headers": [{"name": k, "value": v} for k, v in entry.response_headers.items()],
                    "content": {"text": entry.response_body} if entry.response_body else None
                },
                "time": entry.timestamp
            })

        return {
            "log": {
                "version": "1.2",
                "entries": entries
            }
        }

    def clear(self) -> None:
        """Clear all captured entries."""
        self.entries.clear()

    async def detach(self) -> None:
        """Detach from page and cleanup."""
        if self._cdp_session:
            try:
                await self._cdp_session.detach()
            except Exception:
                pass
        self._cdp_session = None
        self._attached = False


# ==============================================================================
# 4. LIGHTHOUSE AUDITS
# ==============================================================================
# Key insight from BrowserTools MCP: Lighthouse audits help detect:
# - Performance issues that cause automation to fail
# - Accessibility issues blocking element interaction
# - SEO metadata useful for scraping
# ==============================================================================

@dataclass
class LighthouseResult:
    """Results from a Lighthouse audit."""
    url: str
    category: str  # performance, accessibility, best-practices, seo
    score: float  # 0-100
    issues: List[Dict[str, Any]]
    metrics: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    raw_output: Optional[Dict] = None


class LighthouseAuditor:
    """
    Run Lighthouse audits for performance, accessibility, SEO.

    Usage:
        auditor = LighthouseAuditor()

        # Run all audits
        results = await auditor.audit_all("https://example.com")

        # Run specific audit
        perf = await auditor.audit_performance("https://example.com")
        print(f"Performance score: {perf.score}")

        # Get issues
        for issue in perf.issues:
            print(f"- {issue['title']}: {issue['description']}")

    Requires: npm install -g lighthouse
    """

    def __init__(self, chrome_port: Optional[int] = None):
        """
        Initialize auditor.

        Args:
            chrome_port: Optional port for existing Chrome instance.
                        If provided, uses that browser instead of launching new one.
        """
        self.chrome_port = chrome_port
        self._check_lighthouse()

    def _check_lighthouse(self) -> None:
        """Check if Lighthouse is available."""
        if not LIGHTHOUSE_AVAILABLE:
            logger.warning(
                "Lighthouse CLI not found. Install with: npm install -g lighthouse"
            )

    async def audit(self,
                    url: str,
                    categories: List[str] = None,
                    output_format: str = "json") -> Dict[str, LighthouseResult]:
        """
        Run Lighthouse audit on URL.

        Args:
            url: URL to audit
            categories: List of categories to audit:
                       - performance
                       - accessibility
                       - best-practices
                       - seo
            output_format: json or html

        Returns:
            Dict mapping category name to LighthouseResult
        """
        if not LIGHTHOUSE_AVAILABLE:
            logger.error("Lighthouse not available")
            return {}

        categories = categories or ["performance", "accessibility", "best-practices", "seo"]

        # Build command
        cmd = [
            "lighthouse",
            url,
            f"--output={output_format}",
            "--output-path=stdout",
            "--chrome-flags=--headless --no-sandbox --disable-gpu",
            f"--only-categories={','.join(categories)}",
            "--quiet"
        ]

        # Use existing Chrome if port specified
        if self.chrome_port:
            cmd.append(f"--port={self.chrome_port}")

        try:
            # Run Lighthouse (can take 30-60 seconds)
            logger.info(f"Running Lighthouse audit on {url}...")
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=120  # 2 minute timeout
            )

            if process.returncode != 0:
                logger.error(f"Lighthouse failed: {stderr.decode()}")
                return {}

            # Parse results
            data = json.loads(stdout.decode())
            return self._parse_results(url, data)

        except asyncio.TimeoutError:
            logger.error("Lighthouse audit timed out")
            return {}
        except Exception as e:
            logger.error(f"Lighthouse error: {e}")
            return {}

    def _parse_results(self, url: str, data: Dict) -> Dict[str, LighthouseResult]:
        """Parse Lighthouse JSON output into results."""
        results = {}

        categories = data.get("categories", {})
        audits = data.get("audits", {})

        for cat_name, cat_data in categories.items():
            score = (cat_data.get("score") or 0) * 100

            # Get issues (failed audits in this category)
            issues = []
            for audit_ref in cat_data.get("auditRefs", []):
                audit_id = audit_ref.get("id")
                audit = audits.get(audit_id, {})

                # Only include failed/warning audits
                if audit.get("score") is not None and audit.get("score") < 1:
                    issues.append({
                        "id": audit_id,
                        "title": audit.get("title", ""),
                        "description": audit.get("description", ""),
                        "score": audit.get("score", 0),
                        "displayValue": audit.get("displayValue", ""),
                        "details": audit.get("details", {})
                    })

            # Get metrics for performance category
            metrics = {}
            if cat_name == "performance":
                metric_ids = [
                    "first-contentful-paint",
                    "largest-contentful-paint",
                    "total-blocking-time",
                    "cumulative-layout-shift",
                    "speed-index"
                ]
                for metric_id in metric_ids:
                    if metric_id in audits:
                        metrics[metric_id] = {
                            "value": audits[metric_id].get("numericValue"),
                            "display": audits[metric_id].get("displayValue")
                        }

            results[cat_name] = LighthouseResult(
                url=url,
                category=cat_name,
                score=score,
                issues=issues,
                metrics=metrics,
                raw_output=cat_data
            )

        return results

    async def audit_performance(self, url: str) -> Optional[LighthouseResult]:
        """Run performance audit only."""
        results = await self.audit(url, categories=["performance"])
        return results.get("performance")

    async def audit_accessibility(self, url: str) -> Optional[LighthouseResult]:
        """Run accessibility audit only."""
        results = await self.audit(url, categories=["accessibility"])
        return results.get("accessibility")

    async def audit_seo(self, url: str) -> Optional[LighthouseResult]:
        """Run SEO audit only."""
        results = await self.audit(url, categories=["seo"])
        return results.get("seo")

    async def audit_all(self, url: str) -> Dict[str, LighthouseResult]:
        """Run all audit categories."""
        return await self.audit(url)

    def format_report(self, results: Dict[str, LighthouseResult]) -> str:
        """Format audit results as readable report."""
        lines = ["# Lighthouse Audit Report\n"]

        for cat_name, result in results.items():
            emoji = "✅" if result.score >= 90 else "⚠️" if result.score >= 50 else "❌"
            lines.append(f"\n## {emoji} {cat_name.title()}: {result.score:.0f}/100\n")

            # Show metrics for performance
            if result.metrics:
                lines.append("### Metrics")
                for metric, data in result.metrics.items():
                    lines.append(f"- {metric}: {data.get('display', 'N/A')}")
                lines.append("")

            # Show top issues
            if result.issues:
                lines.append(f"### Issues ({len(result.issues)})")
                for issue in result.issues[:5]:  # Top 5
                    score = issue.get('score', 0) * 100
                    lines.append(f"- **{issue['title']}** ({score:.0f}%)")
                    if issue.get('displayValue'):
                        lines.append(f"  - {issue['displayValue']}")
                lines.append("")

        return "\n".join(lines)


# ==============================================================================
# INTEGRATION HELPERS
# ==============================================================================

async def setup_browser_mcp_features(page,
                                     enable_console: bool = True,
                                     enable_network: bool = True) -> Dict[str, Any]:
    """
    Setup Browser MCP features on a Playwright page.

    Usage:
        page = await browser.new_page()
        features = await setup_browser_mcp_features(page)

        # Access features
        console = features['console']
        network = features['network']

        # ... do stuff ...

        # Get captured data
        logs = console.get_logs()
        requests = network.get_requests()

    Returns:
        Dict with 'console' and 'network' monitors
    """
    result = {}

    if enable_console:
        console = ConsoleMonitor()
        await console.attach(page)
        result['console'] = console

    if enable_network:
        network = NetworkCapture()
        await network.attach(page)
        result['network'] = network

    return result


# ==============================================================================
# CLI ENTRY POINT FOR TESTING
# ==============================================================================

async def _test_features():
    """Test Browser MCP features."""
    print("=" * 60)
    print("Browser MCP Features Test")
    print("=" * 60)

    # Test 1: Check feature availability
    print("\n1. Feature Availability:")
    print(f"   - CDP Connection: {'✅' if CDP_AVAILABLE else '❌'}")
    print(f"   - Lighthouse: {'✅' if LIGHTHOUSE_AVAILABLE else '❌'}")

    # Test 2: Show Chrome launch command
    print("\n2. To use existing browser connection:")
    cmd = ExistingBrowserConnection.get_chrome_launch_command()
    print(f"   Start Chrome with: {cmd}")
    print("   Then connect with: conn = await connect_to_existing_browser(9222)")

    # Test 3: Lighthouse audit example
    if LIGHTHOUSE_AVAILABLE:
        print("\n3. Lighthouse Audit Example:")
        auditor = LighthouseAuditor()
        results = await auditor.audit("https://example.com", categories=["performance"])
        if results:
            perf = results.get("performance")
            if perf:
                print(f"   Performance Score: {perf.score:.0f}/100")
                print(f"   Issues: {len(perf.issues)}")

    print("\n" + "=" * 60)
    print("Test complete!")


if __name__ == "__main__":
    asyncio.run(_test_features())
