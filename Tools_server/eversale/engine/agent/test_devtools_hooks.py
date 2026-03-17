"""
Unit tests for DevToolsHooks

Run with: pytest test_devtools_hooks.py -v
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, MagicMock
from collections import deque

# Mock Playwright types for testing
class MockRequest:
    def __init__(self, url, method="GET", resource_type="xhr", headers=None):
        self.url = url
        self.method = method
        self.resource_type = resource_type
        self.headers = headers or {}
        self.failure = None

class MockResponse:
    def __init__(self, request, status=200, status_text="OK", headers=None):
        self.request = request
        self.status = status
        self.status_text = status_text
        self.headers = headers or {}

class MockConsoleMessage:
    def __init__(self, msg_type="log", text="test", location=None):
        self.type = msg_type
        self.text = text
        self.location = location
        self.args = []

class MockPage:
    def __init__(self):
        self._event_handlers = {}

    def on(self, event, handler):
        if event not in self._event_handlers:
            self._event_handlers[event] = []
        self._event_handlers[event].append(handler)

    def remove_listener(self, event, handler):
        if event in self._event_handlers:
            try:
                self._event_handlers[event].remove(handler)
            except ValueError:
                pass

    def emit(self, event, *args):
        """Test helper to emit events"""
        if event in self._event_handlers:
            for handler in self._event_handlers[event]:
                handler(*args)


@pytest.fixture
def mock_page():
    """Create a mock page for testing."""
    return MockPage()


@pytest.fixture
async def devtools(mock_page):
    """Create DevToolsHooks instance with mock page."""
    # Import here to avoid issues if module isn't installed
    from devtools_hooks import DevToolsHooks

    dt = DevToolsHooks(mock_page, max_network_entries=10, max_console_entries=5)
    yield dt
    await dt.cleanup()


@pytest.mark.asyncio
async def test_initialization(mock_page):
    """Test DevToolsHooks initialization."""
    from devtools_hooks import DevToolsHooks

    devtools = DevToolsHooks(
        mock_page,
        max_network_entries=100,
        max_console_entries=50,
        capture_response_bodies=True
    )

    assert devtools.page == mock_page
    assert devtools.max_network_entries == 100
    assert devtools.max_console_entries == 50
    assert devtools.capture_response_bodies is True
    assert len(devtools.network_log) == 0
    assert len(devtools.console_log) == 0
    assert len(devtools.errors) == 0


@pytest.mark.asyncio
async def test_start_capture_network(devtools, mock_page):
    """Test starting network capture."""
    await devtools.start_capture(network=True, console=False)

    assert devtools._capturing_network is True
    assert devtools._capturing_console is False
    assert "request" in mock_page._event_handlers
    assert "response" in mock_page._event_handlers


@pytest.mark.asyncio
async def test_start_capture_console(devtools, mock_page):
    """Test starting console capture."""
    await devtools.start_capture(network=False, console=True)

    assert devtools._capturing_network is False
    assert devtools._capturing_console is True
    assert "console" in mock_page._event_handlers
    assert "pageerror" in mock_page._event_handlers


@pytest.mark.asyncio
async def test_network_request_response(devtools, mock_page):
    """Test network request/response capture."""
    await devtools.start_capture(network=True, console=False)

    # Simulate request
    request = MockRequest("https://example.com/api/data", "GET", "xhr")
    mock_page.emit("request", request)

    # Simulate response
    response = MockResponse(request, status=200, status_text="OK")
    mock_page.emit("response", response)

    # Check captured data
    logs = devtools.get_network_log()
    assert len(logs) == 1
    assert logs[0]["url"] == "https://example.com/api/data"
    assert logs[0]["method"] == "GET"
    assert logs[0]["status_code"] == 200
    assert logs[0]["failed"] is False


@pytest.mark.asyncio
async def test_network_request_failed(devtools, mock_page):
    """Test failed request capture."""
    await devtools.start_capture(network=True, console=False)

    # Simulate failed request
    request = MockRequest("https://example.com/api/data", "GET", "xhr")
    request.failure = "net::ERR_CONNECTION_REFUSED"
    mock_page.emit("request", request)
    mock_page.emit("requestfailed", request)

    # Check captured data
    logs = devtools.get_network_log()
    assert len(logs) == 1
    assert logs[0]["failed"] is True
    assert logs[0]["failure_reason"] == "net::ERR_CONNECTION_REFUSED"

    failed = devtools.get_failed_requests()
    assert len(failed) == 1


@pytest.mark.asyncio
async def test_console_capture(devtools, mock_page):
    """Test console message capture."""
    await devtools.start_capture(network=False, console=True)

    # Simulate console messages
    mock_page.emit("console", MockConsoleMessage("log", "Info message"))
    mock_page.emit("console", MockConsoleMessage("error", "Error message"))
    mock_page.emit("console", MockConsoleMessage("warning", "Warning message"))

    # Check captured data
    logs = devtools.get_console_log()
    assert len(logs) == 3

    errors = devtools.get_console_log(level="error")
    assert len(errors) == 1
    assert errors[0]["text"] == "Error message"


@pytest.mark.asyncio
async def test_page_error_capture(devtools, mock_page):
    """Test page error capture."""
    await devtools.start_capture(network=False, console=True)

    # Simulate page error
    error = Exception("Uncaught TypeError: Cannot read property 'x' of undefined")
    mock_page.emit("pageerror", error)

    # Check captured data
    errors = devtools.get_errors()
    assert len(errors) == 1
    assert "TypeError" in errors[0]["message"]


@pytest.mark.asyncio
async def test_filter_network_by_type(devtools, mock_page):
    """Test filtering network log by resource type."""
    await devtools.start_capture(network=True, console=False)

    # Emit different resource types
    for res_type in ["xhr", "fetch", "document", "image"]:
        request = MockRequest(f"https://example.com/{res_type}", resource_type=res_type)
        response = MockResponse(request)
        mock_page.emit("request", request)
        mock_page.emit("response", response)

    # Filter by type
    xhr_logs = devtools.get_network_log(filter_type="xhr")
    assert len(xhr_logs) == 1
    assert xhr_logs[0]["resource_type"] == "xhr"


@pytest.mark.asyncio
async def test_filter_network_by_status(devtools, mock_page):
    """Test filtering network log by status code."""
    await devtools.start_capture(network=True, console=False)

    # Emit different status codes
    for status in [200, 404, 500]:
        request = MockRequest(f"https://example.com/status/{status}")
        response = MockResponse(request, status=status)
        mock_page.emit("request", request)
        mock_page.emit("response", response)

    # Filter by 4xx
    errors_4xx = devtools.get_network_log(filter_status="4xx")
    assert len(errors_4xx) == 1
    assert errors_4xx[0]["status_code"] == 404

    # Filter by 5xx
    errors_5xx = devtools.get_network_log(filter_status="5xx")
    assert len(errors_5xx) == 1
    assert errors_5xx[0]["status_code"] == 500


@pytest.mark.asyncio
async def test_get_status_code_errors(devtools, mock_page):
    """Test getting HTTP error status codes."""
    await devtools.start_capture(network=True, console=False)

    # Emit mix of status codes
    for status in [200, 201, 404, 500, 503]:
        request = MockRequest(f"https://example.com/status/{status}")
        response = MockResponse(request, status=status)
        mock_page.emit("request", request)
        mock_page.emit("response", response)

    errors = devtools.get_status_code_errors()
    assert len(errors) == 3  # 404, 500, 503
    assert all(e["status_code"] >= 400 for e in errors)


@pytest.mark.asyncio
async def test_get_slow_requests(devtools, mock_page):
    """Test getting slow requests."""
    await devtools.start_capture(network=True, console=False)

    # Mock slow and fast requests
    import time

    # Fast request
    request1 = MockRequest("https://example.com/fast")
    mock_page.emit("request", request1)
    mock_page.emit("response", MockResponse(request1))

    # Slow request (mock timing)
    request2 = MockRequest("https://example.com/slow")
    request_id = str(id(request2))
    devtools._pending_requests[request_id] = {
        "url": request2.url,
        "method": request2.method,
        "resource_type": request2.resource_type,
        "headers": {},
        "start_time": time.time() - 5  # 5 seconds ago
    }
    mock_page.emit("response", MockResponse(request2))

    slow = devtools.get_slow_requests(threshold_ms=3000)
    assert len(slow) >= 1
    assert any("slow" in r["url"] for r in slow)


@pytest.mark.asyncio
async def test_get_blocked_resources(devtools, mock_page):
    """Test getting blocked resources."""
    await devtools.start_capture(network=True, console=False)

    # Simulate blocked request
    request = MockRequest("https://example.com/blocked.js")
    request.failure = "net::ERR_BLOCKED_BY_CSP"
    mock_page.emit("request", request)
    mock_page.emit("requestfailed", request)

    blocked = devtools.get_blocked_resources()
    assert len(blocked) == 1
    assert "blocked" in blocked[0]["failure_reason"].lower()


@pytest.mark.asyncio
async def test_circular_buffer_network(devtools, mock_page):
    """Test network log circular buffer (max entries)."""
    await devtools.start_capture(network=True, console=False)

    # Emit more requests than max_network_entries (10)
    for i in range(15):
        request = MockRequest(f"https://example.com/req{i}")
        response = MockResponse(request)
        mock_page.emit("request", request)
        mock_page.emit("response", response)

    # Should only keep last 10
    logs = devtools.get_network_log()
    assert len(logs) == 10


@pytest.mark.asyncio
async def test_circular_buffer_console(devtools, mock_page):
    """Test console log circular buffer (max entries)."""
    await devtools.start_capture(network=False, console=True)

    # Emit more logs than max_console_entries (5)
    for i in range(10):
        mock_page.emit("console", MockConsoleMessage("log", f"Message {i}"))

    # Should only keep last 5
    logs = devtools.get_console_log()
    assert len(logs) == 5


@pytest.mark.asyncio
async def test_summary(devtools, mock_page):
    """Test summary generation."""
    await devtools.start_capture(network=True, console=True)

    # Add some data
    for i in range(5):
        request = MockRequest(f"https://example.com/req{i}")
        response = MockResponse(request, status=200 if i < 3 else 404)
        mock_page.emit("request", request)
        mock_page.emit("response", response)

    mock_page.emit("console", MockConsoleMessage("error", "Error!"))
    mock_page.emit("console", MockConsoleMessage("warning", "Warning!"))

    summary = devtools.summary()

    assert summary["network"]["total_requests"] == 5
    assert summary["network"]["status_4xx"] == 2
    assert summary["console"]["errors"] == 1
    assert summary["console"]["warnings"] == 1


@pytest.mark.asyncio
async def test_clear(devtools, mock_page):
    """Test clearing captured data."""
    await devtools.start_capture(network=True, console=True)

    # Add data
    request = MockRequest("https://example.com/test")
    response = MockResponse(request)
    mock_page.emit("request", request)
    mock_page.emit("response", response)
    mock_page.emit("console", MockConsoleMessage("log", "Test"))

    assert len(devtools.network_log) > 0
    assert len(devtools.console_log) > 0

    # Clear
    devtools.clear()

    assert len(devtools.network_log) == 0
    assert len(devtools.console_log) == 0


@pytest.mark.asyncio
async def test_stop_capture(devtools, mock_page):
    """Test stopping capture removes handlers."""
    await devtools.start_capture(network=True, console=True)

    assert len(mock_page._event_handlers) > 0

    await devtools.stop_capture()

    assert devtools._capturing_network is False
    assert devtools._capturing_console is False


@pytest.mark.asyncio
async def test_cleanup(devtools, mock_page):
    """Test cleanup stops capture and clears data."""
    await devtools.start_capture(network=True, console=True)

    # Add data
    request = MockRequest("https://example.com/test")
    response = MockResponse(request)
    mock_page.emit("request", request)
    mock_page.emit("response", response)

    await devtools.cleanup()

    assert devtools._capturing_network is False
    assert devtools._capturing_console is False
    assert len(devtools.network_log) == 0
    assert len(devtools.console_log) == 0
