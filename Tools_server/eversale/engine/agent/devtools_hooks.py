"""
DevTools Inspection Capabilities for Playwright Pages

Captures network requests, console logs, page errors, and resource failures
using Playwright's event system. Designed for production use with memory limits
and efficient filtering.

Usage:
    from devtools_hooks import DevToolsHooks

    devtools = DevToolsHooks(page)
    await devtools.start_capture(network=True, console=True)

    # Run your automation
    await page.goto("https://example.com")

    # Get captured data
    failed_requests = devtools.get_failed_requests()
    errors = devtools.get_errors()
    summary = devtools.summary()

    await devtools.stop_capture()
"""

import asyncio
import time
from collections import deque
from typing import Dict, List, Any, Optional, Literal
from datetime import datetime
from loguru import logger

# Playwright imports with fallbacks for different anti-bot libraries
try:
    from patchright.async_api import Page, Request, Response, ConsoleMessage, Error
except ImportError:
    try:
        from rebrowser_playwright.async_api import Page, Request, Response, ConsoleMessage, Error
    except ImportError:
        from playwright.async_api import Page, Request, Response, ConsoleMessage, Error


class DevToolsHooks:
    """
    DevTools inspection for Playwright pages.

    Captures network activity, console logs, and errors with memory-efficient
    circular buffers and flexible filtering options.
    """

    def __init__(
        self,
        page: Page,
        max_network_entries: int = 500,
        max_console_entries: int = 200,
        max_error_entries: int = 100,
        capture_response_bodies: bool = False
    ):
        """
        Initialize DevTools hooks.

        Args:
            page: Playwright page instance
            max_network_entries: Max network requests to store (circular buffer)
            max_console_entries: Max console logs to store (circular buffer)
            max_error_entries: Max errors to store (circular buffer)
            capture_response_bodies: Whether to capture response bodies (memory intensive)
        """
        self.page = page
        self.max_network_entries = max_network_entries
        self.max_console_entries = max_console_entries
        self.max_error_entries = max_error_entries
        self.capture_response_bodies = capture_response_bodies

        # Use deque for efficient circular buffers
        self.network_log: deque = deque(maxlen=max_network_entries)
        self.console_log: deque = deque(maxlen=max_console_entries)
        self.errors: deque = deque(maxlen=max_error_entries)

        # Active request tracking (for timing)
        self._pending_requests: Dict[str, Dict[str, Any]] = {}

        # Capture state
        self._capturing_network = False
        self._capturing_console = False
        self._start_time = None

        # Event handler references (for cleanup)
        self._request_handler = None
        self._response_handler = None
        self._request_failed_handler = None
        self._console_handler = None
        self._pageerror_handler = None

    async def start_capture(
        self,
        network: bool = True,
        console: bool = True
    ) -> None:
        """
        Start capturing DevTools events.

        Args:
            network: Capture network requests/responses
            console: Capture console logs and page errors
        """
        self._start_time = time.time()

        if network and not self._capturing_network:
            self._setup_network_handlers()
            self._capturing_network = True
            logger.debug("DevTools network capture started")

        if console and not self._capturing_console:
            self._setup_console_handlers()
            self._capturing_console = True
            logger.debug("DevTools console capture started")

    async def stop_capture(self) -> None:
        """Stop capturing and remove event handlers."""
        if self._capturing_network:
            self._remove_network_handlers()
            self._capturing_network = False
            logger.debug("DevTools network capture stopped")

        if self._capturing_console:
            self._remove_console_handlers()
            self._capturing_console = False
            logger.debug("DevTools console capture stopped")

    def _setup_network_handlers(self) -> None:
        """Setup network request/response event handlers."""
        self._request_handler = self._on_request
        self._response_handler = self._on_response
        self._request_failed_handler = self._on_request_failed

        self.page.on("request", self._request_handler)
        self.page.on("response", self._response_handler)
        self.page.on("requestfailed", self._request_failed_handler)

    def _setup_console_handlers(self) -> None:
        """Setup console and error event handlers."""
        self._console_handler = self._on_console
        self._pageerror_handler = self._on_pageerror

        self.page.on("console", self._console_handler)
        self.page.on("pageerror", self._pageerror_handler)

    def _remove_network_handlers(self) -> None:
        """Remove network event handlers."""
        try:
            if self._request_handler:
                self.page.remove_listener("request", self._request_handler)
            if self._response_handler:
                self.page.remove_listener("response", self._response_handler)
            if self._request_failed_handler:
                self.page.remove_listener("requestfailed", self._request_failed_handler)
        except Exception as e:
            logger.debug(f"Error removing network handlers: {e}")

    def _remove_console_handlers(self) -> None:
        """Remove console event handlers."""
        try:
            if self._console_handler:
                self.page.remove_listener("console", self._console_handler)
            if self._pageerror_handler:
                self.page.remove_listener("pageerror", self._pageerror_handler)
        except Exception as e:
            logger.debug(f"Error removing console handlers: {e}")

    def _on_request(self, request: Request) -> None:
        """Handle request event."""
        try:
            request_id = id(request)

            # Store pending request for timing calculation
            self._pending_requests[str(request_id)] = {
                "url": request.url,
                "method": request.method,
                "resource_type": request.resource_type,
                "headers": dict(request.headers),
                "start_time": time.time(),
            }
        except Exception as e:
            logger.debug(f"Error handling request event: {e}")

    def _on_response(self, response: Response) -> None:
        """Handle response event."""
        try:
            request = response.request
            request_id = str(id(request))

            # Calculate timing
            pending = self._pending_requests.pop(request_id, {})
            start_time = pending.get("start_time", time.time())
            duration_ms = int((time.time() - start_time) * 1000)

            entry = {
                "timestamp": datetime.now().isoformat(),
                "url": request.url,
                "method": request.method,
                "resource_type": request.resource_type,
                "status_code": response.status,
                "status_text": response.status_text,
                "duration_ms": duration_ms,
                "headers": dict(response.headers),
                "failed": False,
            }

            # Optionally capture response body (memory intensive)
            if self.capture_response_bodies:
                try:
                    # Only capture text responses (not images, etc.)
                    content_type = response.headers.get("content-type", "")
                    if any(t in content_type for t in ["text", "json", "javascript", "xml"]):
                        # Note: This is async, we'll skip for now in sync handler
                        # Could be improved with async queue processing
                        pass
                except:
                    pass

            self.network_log.append(entry)
        except Exception as e:
            logger.debug(f"Error handling response event: {e}")

    def _on_request_failed(self, request: Request) -> None:
        """Handle request failure event."""
        try:
            request_id = str(id(request))

            # Calculate timing
            pending = self._pending_requests.pop(request_id, {})
            start_time = pending.get("start_time", time.time())
            duration_ms = int((time.time() - start_time) * 1000)

            entry = {
                "timestamp": datetime.now().isoformat(),
                "url": request.url,
                "method": request.method,
                "resource_type": request.resource_type,
                "status_code": None,
                "status_text": request.failure or "Failed",
                "duration_ms": duration_ms,
                "headers": dict(request.headers),
                "failed": True,
                "failure_reason": request.failure,
            }

            self.network_log.append(entry)
        except Exception as e:
            logger.debug(f"Error handling request failed event: {e}")

    def _on_console(self, msg: ConsoleMessage) -> None:
        """Handle console message event."""
        try:
            entry = {
                "timestamp": datetime.now().isoformat(),
                "level": msg.type,  # log, debug, info, error, warning, etc.
                "text": msg.text,
                "location": msg.location,
                "args": [str(arg) for arg in msg.args] if msg.args else [],
            }

            self.console_log.append(entry)
        except Exception as e:
            logger.debug(f"Error handling console event: {e}")

    def _on_pageerror(self, error: Error) -> None:
        """Handle page error event (uncaught exceptions)."""
        try:
            entry = {
                "timestamp": datetime.now().isoformat(),
                "type": "pageerror",
                "message": str(error),
                "stack": getattr(error, "stack", None),
            }

            self.errors.append(entry)

            # Also add to console log for unified view
            console_entry = {
                "timestamp": datetime.now().isoformat(),
                "level": "error",
                "text": f"Uncaught exception: {error}",
                "location": None,
                "args": [],
            }
            self.console_log.append(console_entry)
        except Exception as e:
            logger.debug(f"Error handling pageerror event: {e}")

    def get_network_log(
        self,
        filter_type: Optional[str] = None,
        filter_status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get network log with optional filtering.

        Args:
            filter_type: Filter by resource type (xhr, fetch, document, image, stylesheet, script, etc.)
            filter_status: Filter by status code pattern (2xx, 3xx, 4xx, 5xx, failed)

        Returns:
            List of network log entries
        """
        logs = list(self.network_log)

        if filter_type:
            logs = [log for log in logs if log.get("resource_type") == filter_type]

        if filter_status:
            if filter_status == "failed":
                logs = [log for log in logs if log.get("failed", False)]
            else:
                # Match status code pattern (e.g., 4xx matches 400-499)
                status_pattern = filter_status.replace("xx", "")
                logs = [
                    log for log in logs
                    if log.get("status_code") and str(log["status_code"]).startswith(status_pattern)
                ]

        return logs

    def get_console_log(
        self,
        level: Optional[Literal["error", "warning", "info", "log", "debug"]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get console log with optional level filtering.

        Args:
            level: Filter by console level (error, warning, info, log, debug)
                  Each level includes more severe levels (e.g., info includes error and warning)

        Returns:
            List of console log entries
        """
        logs = list(self.console_log)

        if level:
            # Define severity order
            severity_order = ["error", "warning", "info", "log", "debug"]
            level_index = severity_order.index(level)
            allowed_levels = severity_order[:level_index + 1]

            logs = [log for log in logs if log.get("level") in allowed_levels]

        return logs

    def get_errors(self) -> List[Dict[str, Any]]:
        """
        Get all captured page errors.

        Returns:
            List of error entries
        """
        return list(self.errors)

    def get_failed_requests(self) -> List[Dict[str, Any]]:
        """
        Get all failed network requests.

        Returns:
            List of failed request entries
        """
        return [log for log in self.network_log if log.get("failed", False)]

    def get_blocked_resources(self) -> List[Dict[str, Any]]:
        """
        Get resources that were blocked (CORS, CSP, etc.).

        Returns:
            List of blocked resource entries
        """
        # Requests with specific failure reasons indicating blocking
        blocking_keywords = ["blocked", "cors", "csp", "mixed content", "refused"]

        return [
            log for log in self.network_log
            if log.get("failed", False) and any(
                keyword in log.get("failure_reason", "").lower()
                for keyword in blocking_keywords
            )
        ]

    def get_slow_requests(self, threshold_ms: int = 3000) -> List[Dict[str, Any]]:
        """
        Get requests that took longer than threshold.

        Args:
            threshold_ms: Duration threshold in milliseconds

        Returns:
            List of slow request entries sorted by duration (slowest first)
        """
        slow = [
            log for log in self.network_log
            if log.get("duration_ms", 0) >= threshold_ms
        ]
        return sorted(slow, key=lambda x: x.get("duration_ms", 0), reverse=True)

    def get_status_code_errors(self) -> List[Dict[str, Any]]:
        """
        Get requests with 4xx or 5xx status codes.

        Returns:
            List of error status code entries
        """
        return [
            log for log in self.network_log
            if log.get("status_code") and log["status_code"] >= 400
        ]

    def summary(self) -> Dict[str, Any]:
        """
        Get quick overview of captured data.

        Returns:
            Summary dict with counts and key metrics
        """
        network_logs = list(self.network_log)
        console_logs = list(self.console_log)

        # Network stats
        total_requests = len(network_logs)
        failed_requests = len([log for log in network_logs if log.get("failed", False)])
        status_4xx = len([log for log in network_logs if log.get("status_code", 0) >= 400 and log.get("status_code", 0) < 500])
        status_5xx = len([log for log in network_logs if log.get("status_code", 0) >= 500])

        # Calculate average duration (excluding failed requests)
        successful_durations = [
            log.get("duration_ms", 0)
            for log in network_logs
            if not log.get("failed", False)
        ]
        avg_duration_ms = int(sum(successful_durations) / len(successful_durations)) if successful_durations else 0

        # Console stats
        console_errors = len([log for log in console_logs if log.get("level") == "error"])
        console_warnings = len([log for log in console_logs if log.get("level") == "warning"])

        # Resource type breakdown
        resource_types = {}
        for log in network_logs:
            res_type = log.get("resource_type", "unknown")
            resource_types[res_type] = resource_types.get(res_type, 0) + 1

        return {
            "capture_duration_seconds": int(time.time() - self._start_time) if self._start_time else 0,
            "network": {
                "total_requests": total_requests,
                "failed_requests": failed_requests,
                "status_4xx": status_4xx,
                "status_5xx": status_5xx,
                "average_duration_ms": avg_duration_ms,
                "resource_types": resource_types,
            },
            "console": {
                "total_messages": len(console_logs),
                "errors": console_errors,
                "warnings": console_warnings,
            },
            "errors": {
                "page_errors": len(self.errors),
            },
            "capturing": {
                "network": self._capturing_network,
                "console": self._capturing_console,
            }
        }

    def clear(self) -> None:
        """Clear all captured data."""
        self.network_log.clear()
        self.console_log.clear()
        self.errors.clear()
        self._pending_requests.clear()
        logger.debug("DevTools capture data cleared")

    async def cleanup(self) -> None:
        """Cleanup resources and stop capture."""
        await self.stop_capture()
        self.clear()

    def __del__(self):
        """Ensure cleanup on garbage collection."""
        try:
            # Sync cleanup for handlers
            self._remove_network_handlers()
            self._remove_console_handlers()
        except:
            pass


# Convenience function for quick summary
async def quick_devtools_summary(page: Page, duration_seconds: int = 5) -> Dict[str, Any]:
    """
    Quick DevTools capture for debugging.

    Args:
        page: Playwright page instance
        duration_seconds: How long to capture (0 = just return current state)

    Returns:
        Summary dict

    Example:
        summary = await quick_devtools_summary(page, duration_seconds=10)
        print(f"Errors: {summary['console']['errors']}")
        print(f"Failed requests: {summary['network']['failed_requests']}")
    """
    devtools = DevToolsHooks(page)
    await devtools.start_capture(network=True, console=True)

    if duration_seconds > 0:
        await asyncio.sleep(duration_seconds)

    summary = devtools.summary()
    await devtools.cleanup()

    return summary
