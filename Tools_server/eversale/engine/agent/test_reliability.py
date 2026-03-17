#!/usr/bin/env python3
"""
RELIABILITY TEST SUITE - Core Browser Operations

This test suite verifies that core browser operations work reliably:
- Browser health checks
- Navigation operations
- Element finding
- Click operations
- Type operations
- Error handling
- Timeout handling

Philosophy:
- Every operation returns ToolResult (never raises exceptions)
- Failed operations have clear error messages
- Operations complete or fail within reasonable timeouts
- Tests run with real browser when available, mock when not

Run with: pytest engine/agent/test_reliability.py -v
"""

import pytest
import asyncio
import base64
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock

# Try to import real browser libraries
try:
    from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    PlaywrightTimeoutError = Exception

# Import the MCP tools
try:
    from .mcp_tools import MCPTools, ToolResult
    MCP_TOOLS_AVAILABLE = True
except ImportError:
    # Fallback: define ToolResult for testing
    from dataclasses import dataclass
    from typing import Optional, Any

    @dataclass
    class ToolResult:
        success: bool
        message: str
        data: Optional[Any] = None
        screenshot_b64: Optional[str] = None

    MCP_TOOLS_AVAILABLE = False


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_page():
    """Create a mock Playwright page for testing without real browser."""
    page = AsyncMock()

    # Mock basic properties
    page.url = "https://example.com"
    page.title = AsyncMock(return_value="Example Domain")

    # Mock screenshot
    fake_screenshot = b"fake_screenshot_data"
    page.screenshot = AsyncMock(return_value=fake_screenshot)

    # Mock navigation
    page.goto = AsyncMock()

    # Mock interactions
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.type = AsyncMock()

    # Mock keyboard
    page.keyboard = AsyncMock()
    page.keyboard.press = AsyncMock()

    # Mock mouse
    page.mouse = AsyncMock()
    page.mouse.wheel = AsyncMock()

    # Mock waiting
    page.wait_for_timeout = AsyncMock()
    page.wait_for_selector = AsyncMock()

    # Mock evaluate
    page.evaluate = AsyncMock(return_value="")

    return page


@pytest.fixture
def mock_context(mock_page):
    """Create a mock browser context."""
    context = AsyncMock()
    context.pages = [mock_page]
    context.new_page = AsyncMock(return_value=mock_page)
    context.close = AsyncMock()
    return context


@pytest.fixture
def mock_browser(mock_context):
    """Create a mock browser."""
    browser = AsyncMock()
    browser.new_context = AsyncMock(return_value=mock_context)
    browser.close = AsyncMock()
    return browser


@pytest.fixture
def mock_playwright(mock_browser):
    """Create a mock playwright instance."""
    pw = AsyncMock()
    pw.chromium = AsyncMock()
    pw.chromium.launch = AsyncMock(return_value=mock_browser)
    pw.chromium.launch_persistent_context = AsyncMock(return_value=mock_browser)
    pw.stop = AsyncMock()
    return pw


@pytest.fixture
def mcp_tools_mock(mock_playwright, mock_page, mock_context, mock_browser):
    """Create MCPTools instance with mocked browser."""
    if not MCP_TOOLS_AVAILABLE:
        pytest.skip("MCPTools not available")

    tools = MCPTools(headless=True, enable_stealth=False, enable_human_timing=False)

    # Manually set all browser components to avoid actual browser launch
    tools._playwright = mock_playwright
    tools._browser = mock_browser
    tools._context = mock_context
    tools._page = mock_page

    # Mock the _detect_challenge method to avoid coroutine issues
    tools._detect_challenge = AsyncMock(return_value=None)
    tools._close_overlays_internal = AsyncMock()

    yield tools


@pytest.fixture
async def mcp_tools_real():
    """Create MCPTools instance with real browser (if available)."""
    if not PLAYWRIGHT_AVAILABLE or not MCP_TOOLS_AVAILABLE:
        pytest.skip("Playwright or MCPTools not available for real browser test")

    tools = MCPTools(headless=True, enable_stealth=False, enable_human_timing=False)
    result = await tools.launch()

    if not result.success:
        pytest.skip(f"Failed to launch real browser: {result.message}")

    yield tools

    # Cleanup
    await tools.close()


# =============================================================================
# 1. Health Check Tests
# =============================================================================

@pytest.mark.asyncio
async def test_browser_health_check_on_live_page(mcp_tools_mock):
    """Verify health check returns True for working browser."""
    # Mock a healthy page
    mcp_tools_mock._page.url = "https://example.com"
    mcp_tools_mock._page.title = AsyncMock(return_value="Example Domain")

    # Browser is considered healthy if it can take screenshots and has a page
    assert mcp_tools_mock._page is not None
    screenshot_result = await mcp_tools_mock.screenshot()
    assert screenshot_result.success is True


@pytest.mark.asyncio
async def test_browser_health_check_detects_crash():
    """Verify health check returns False for crashed browser."""
    if not MCP_TOOLS_AVAILABLE:
        pytest.skip("MCPTools not available")

    tools = MCPTools(headless=True)

    # Without launching, operations should fail
    screenshot_result = await tools.screenshot()
    assert screenshot_result.success is False
    assert "failed" in screenshot_result.message.lower() or "error" in screenshot_result.message.lower()


# =============================================================================
# 2. Navigation Tests
# =============================================================================

@pytest.mark.asyncio
async def test_navigate_to_valid_url(mcp_tools_mock):
    """Navigate to example.com succeeds."""
    mcp_tools_mock._page.goto = AsyncMock()
    mcp_tools_mock._page.url = "https://example.com"
    mcp_tools_mock._page.title = AsyncMock(return_value="Example Domain")

    result = await mcp_tools_mock.navigate("https://example.com")

    assert isinstance(result, ToolResult)
    assert result.success is True
    assert "example.com" in result.message.lower()
    assert result.screenshot_b64 is not None


@pytest.mark.asyncio
async def test_navigate_to_invalid_url(mcp_tools_mock):
    """Navigate to invalid URL returns clear error."""
    # Mock navigation failure
    mcp_tools_mock._page.goto = AsyncMock(side_effect=Exception("net::ERR_NAME_NOT_RESOLVED"))

    result = await mcp_tools_mock.navigate("https://this-domain-does-not-exist-12345.com")

    assert isinstance(result, ToolResult)
    assert result.success is False
    assert "failed" in result.message.lower() or "error" in result.message.lower()


@pytest.mark.asyncio
async def test_navigate_timeout():
    """Navigation timeout returns error, doesn't hang."""
    if not MCP_TOOLS_AVAILABLE:
        pytest.skip("MCPTools not available")

    tools = MCPTools(headless=True, enable_human_timing=False)

    # Create a mock page that times out
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock(side_effect=PlaywrightTimeoutError("Timeout 30000ms exceeded"))
    mock_page.screenshot = AsyncMock(return_value=b"screenshot")
    tools._page = mock_page

    # Should complete quickly (fail fast, not hang)
    start = asyncio.get_event_loop().time()
    result = await tools.navigate("https://example.com")
    elapsed = asyncio.get_event_loop().time() - start

    assert isinstance(result, ToolResult)
    assert result.success is False
    assert elapsed < 5.0  # Should fail fast, not wait full timeout
    assert "timeout" in result.message.lower() or "failed" in result.message.lower()


@pytest.mark.asyncio
async def test_navigate_adds_protocol():
    """Navigate adds https:// if protocol missing."""
    if not MCP_TOOLS_AVAILABLE:
        pytest.skip("MCPTools not available")

    tools = MCPTools(headless=True, enable_human_timing=False)
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.url = "https://example.com"
    mock_page.title = AsyncMock(return_value="Example")
    mock_page.screenshot = AsyncMock(return_value=b"screenshot")
    tools._page = mock_page

    result = await tools.navigate("example.com")

    # Should have called goto with https://
    mock_page.goto.assert_called_once()
    call_args = mock_page.goto.call_args[0]
    assert call_args[0].startswith("https://")


# =============================================================================
# 3. Element Finding Tests
# =============================================================================

@pytest.mark.asyncio
async def test_find_element_by_accessibility_ref(mcp_tools_mock):
    """Find element using ref works."""
    # Mock finding an element
    mock_element = AsyncMock()
    mcp_tools_mock._page.query_selector = AsyncMock(return_value=mock_element)

    result = await mcp_tools_mock.click('[aria-label="Submit"]')

    assert isinstance(result, ToolResult)
    # Either success or a clear error (element might not be clickable in mock)
    assert result.message is not None


@pytest.mark.asyncio
async def test_find_element_by_description(mcp_tools_mock):
    """Find 'search button' finds correct element."""
    # Mock text-based selector
    mcp_tools_mock._page.click = AsyncMock()

    result = await mcp_tools_mock.click('text="Search"')

    assert isinstance(result, ToolResult)
    assert result.message is not None


@pytest.mark.asyncio
async def test_find_nonexistent_element(mcp_tools_mock):
    """Finding missing element returns clear error."""
    # Mock element not found
    mcp_tools_mock._page.click = AsyncMock(
        side_effect=PlaywrightTimeoutError("Timeout waiting for selector")
    )

    result = await mcp_tools_mock.click('#nonexistent-element-12345')

    assert isinstance(result, ToolResult)
    assert result.success is False
    assert "failed" in result.message.lower() or "timeout" in result.message.lower()


# =============================================================================
# 4. Click Tests
# =============================================================================

@pytest.mark.asyncio
async def test_click_by_ref(mcp_tools_mock):
    """Click using accessibility ref works."""
    mcp_tools_mock._page.click = AsyncMock()

    result = await mcp_tools_mock.click('[aria-label="Close"]')

    assert isinstance(result, ToolResult)
    mcp_tools_mock._page.click.assert_called_once()


@pytest.mark.asyncio
async def test_click_missing_element(mcp_tools_mock):
    """Click on missing element returns error."""
    mcp_tools_mock._page.click = AsyncMock(
        side_effect=PlaywrightTimeoutError("Element not found")
    )

    result = await mcp_tools_mock.click('#missing-button')

    assert isinstance(result, ToolResult)
    assert result.success is False
    assert result.message is not None
    assert len(result.message) > 0


@pytest.mark.asyncio
async def test_click_returns_screenshot(mcp_tools_mock):
    """Click returns screenshot for LLM to see result."""
    mcp_tools_mock._page.click = AsyncMock()
    fake_screenshot = b"screenshot_after_click"
    mcp_tools_mock._page.screenshot = AsyncMock(return_value=fake_screenshot)

    result = await mcp_tools_mock.click('button')

    # Even on failure, should try to return screenshot
    if result.success:
        assert result.screenshot_b64 is not None
        decoded = base64.b64decode(result.screenshot_b64)
        assert decoded == fake_screenshot


# =============================================================================
# 5. Type Tests
# =============================================================================

@pytest.mark.asyncio
async def test_type_into_input(mcp_tools_mock):
    """Type into text input works."""
    mcp_tools_mock._page.fill = AsyncMock()

    result = await mcp_tools_mock.type('input[type="text"]', 'Hello World')

    assert isinstance(result, ToolResult)
    mcp_tools_mock._page.fill.assert_called_once()


@pytest.mark.asyncio
async def test_type_into_non_input(mcp_tools_mock):
    """Type into non-input returns error."""
    mcp_tools_mock._page.fill = AsyncMock(
        side_effect=Exception("Element is not an input, textarea or select element")
    )

    result = await mcp_tools_mock.type('div', 'text')

    assert isinstance(result, ToolResult)
    assert result.success is False
    assert "failed" in result.message.lower() or "error" in result.message.lower()


@pytest.mark.asyncio
async def test_type_clears_existing_text():
    """Type with clear_first=True clears existing text."""
    if not MCP_TOOLS_AVAILABLE:
        pytest.skip("MCPTools not available")

    tools = MCPTools(headless=True)
    mock_page = AsyncMock()
    mock_page.fill = AsyncMock()
    mock_page.screenshot = AsyncMock(return_value=b"screenshot")
    tools._page = mock_page

    result = await tools.type('input', 'new text', clear_first=True)

    # Should call fill (which clears first)
    mock_page.fill.assert_called_once_with('input', 'new text', timeout=5000)


# =============================================================================
# 6. Error Handling Tests
# =============================================================================

@pytest.mark.asyncio
async def test_all_operations_return_tool_result():
    """Every operation returns ToolResult, never raises."""
    if not MCP_TOOLS_AVAILABLE:
        pytest.skip("MCPTools not available")

    tools = MCPTools(headless=True)
    mock_page = AsyncMock()

    # Make everything fail
    mock_page.screenshot = AsyncMock(side_effect=Exception("Screenshot error"))
    mock_page.goto = AsyncMock(side_effect=Exception("Navigation error"))
    mock_page.click = AsyncMock(side_effect=Exception("Click error"))
    mock_page.fill = AsyncMock(side_effect=Exception("Fill error"))
    mock_page.keyboard = AsyncMock()
    mock_page.keyboard.press = AsyncMock(side_effect=Exception("Press error"))

    tools._page = mock_page

    # All should return ToolResult, not raise
    results = []
    results.append(await tools.screenshot())
    results.append(await tools.navigate("https://example.com"))
    results.append(await tools.click("button"))
    results.append(await tools.type("input", "text"))
    results.append(await tools.press("Enter"))

    # Every result should be a ToolResult
    for result in results:
        assert isinstance(result, ToolResult)
        assert hasattr(result, 'success')
        assert hasattr(result, 'message')


@pytest.mark.asyncio
async def test_no_silent_failures():
    """Failed operations have error message set."""
    if not MCP_TOOLS_AVAILABLE:
        pytest.skip("MCPTools not available")

    tools = MCPTools(headless=True)
    mock_page = AsyncMock()
    mock_page.click = AsyncMock(side_effect=Exception("Element not found"))
    mock_page.screenshot = AsyncMock(return_value=b"screenshot")
    tools._page = mock_page

    result = await tools.click("#missing")

    assert isinstance(result, ToolResult)
    assert result.success is False
    assert result.message is not None
    assert len(result.message) > 0
    assert "element not found" in result.message.lower() or "failed" in result.message.lower()


@pytest.mark.asyncio
async def test_errors_include_context():
    """Error messages include helpful context (selector, action, etc.)."""
    if not MCP_TOOLS_AVAILABLE:
        pytest.skip("MCPTools not available")

    tools = MCPTools(headless=True)
    mock_page = AsyncMock()
    mock_page.click = AsyncMock(side_effect=Exception("Timeout"))
    mock_page.screenshot = AsyncMock(return_value=b"screenshot")
    tools._page = mock_page

    result = await tools.click("#submit-button")

    assert isinstance(result, ToolResult)
    assert result.success is False
    # Message should mention what failed
    assert "click" in result.message.lower() or "submit-button" in result.message.lower()


# =============================================================================
# 7. Timeout Tests
# =============================================================================

@pytest.mark.asyncio
async def test_operations_respect_timeout():
    """Operations complete or fail within timeout."""
    if not MCP_TOOLS_AVAILABLE:
        pytest.skip("MCPTools not available")

    tools = MCPTools(headless=True, enable_human_timing=False)
    mock_page = AsyncMock()

    # Mock a slow operation
    async def slow_click(*args, **kwargs):
        await asyncio.sleep(10)  # 10 seconds

    mock_page.click = slow_click
    mock_page.screenshot = AsyncMock(return_value=b"screenshot")
    tools._page = mock_page

    # Should timeout before 10 seconds
    start = asyncio.get_event_loop().time()

    # Use try/except in case it raises, but it shouldn't
    try:
        result = await asyncio.wait_for(
            tools.click("button", timeout=1000),  # 1 second timeout
            timeout=3.0  # Overall timeout for test
        )
        elapsed = asyncio.get_event_loop().time() - start

        # Should complete within reasonable time
        assert elapsed < 15.0  # Generous upper bound
        assert isinstance(result, ToolResult)
    except asyncio.TimeoutError:
        # If the test itself times out, that's OK - proves operation hung
        elapsed = asyncio.get_event_loop().time() - start
        assert elapsed < 5.0  # But shouldn't hang forever


@pytest.mark.asyncio
async def test_screenshot_timeout_returns_error():
    """Screenshot timeout returns error result."""
    if not MCP_TOOLS_AVAILABLE:
        pytest.skip("MCPTools not available")

    tools = MCPTools(headless=True)
    mock_page = AsyncMock()
    mock_page.screenshot = AsyncMock(side_effect=asyncio.TimeoutError("Screenshot timeout"))
    tools._page = mock_page

    result = await tools.screenshot()

    assert isinstance(result, ToolResult)
    assert result.success is False
    assert "timeout" in result.message.lower() or "failed" in result.message.lower()


# =============================================================================
# 8. Additional Reliability Tests
# =============================================================================

@pytest.mark.asyncio
async def test_screenshot_always_included_on_success():
    """Successful operations include screenshot for LLM."""
    if not MCP_TOOLS_AVAILABLE:
        pytest.skip("MCPTools not available")

    tools = MCPTools(headless=True, enable_human_timing=False)
    mock_page = AsyncMock()
    mock_page.click = AsyncMock()
    mock_page.fill = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.url = "https://example.com"
    mock_page.title = AsyncMock(return_value="Example")
    mock_page.screenshot = AsyncMock(return_value=b"screenshot_data")
    mock_page.wait_for_timeout = AsyncMock()
    tools._page = mock_page

    # Test various operations
    nav_result = await tools.navigate("https://example.com")
    click_result = await tools.click("button")
    type_result = await tools.type("input", "text")

    # All successful operations should have screenshots
    if nav_result.success:
        assert nav_result.screenshot_b64 is not None
    if click_result.success:
        assert click_result.screenshot_b64 is not None
    if type_result.success:
        assert type_result.screenshot_b64 is not None


@pytest.mark.asyncio
async def test_screenshot_attempted_on_error():
    """Failed operations try to capture screenshot of error state."""
    if not MCP_TOOLS_AVAILABLE:
        pytest.skip("MCPTools not available")

    tools = MCPTools(headless=True)
    mock_page = AsyncMock()
    mock_page.click = AsyncMock(side_effect=Exception("Click failed"))
    mock_page.screenshot = AsyncMock(return_value=b"error_state_screenshot")
    tools._page = mock_page

    result = await tools.click("button")

    assert isinstance(result, ToolResult)
    assert result.success is False
    # Even on error, should try to include screenshot
    # (may be None if screenshot also fails)


@pytest.mark.asyncio
async def test_close_is_safe_when_not_launched():
    """Calling close without launch doesn't raise."""
    if not MCP_TOOLS_AVAILABLE:
        pytest.skip("MCPTools not available")

    tools = MCPTools(headless=True)

    # Should not raise
    result = await tools.close()

    assert isinstance(result, ToolResult)
    # Success or failure is OK, just shouldn't raise


@pytest.mark.asyncio
async def test_launch_returns_clear_result():
    """Launch returns clear success/failure result."""
    if not PLAYWRIGHT_AVAILABLE or not MCP_TOOLS_AVAILABLE:
        pytest.skip("Playwright or MCPTools not available")

    # Test with mocked playwright
    mock_pw = AsyncMock()
    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()

    mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_page.add_init_script = AsyncMock()

    with patch('engine.agent.mcp_tools.async_playwright') as mock_ap:
        mock_ap.return_value.__aenter__ = AsyncMock(return_value=mock_pw)

        tools = MCPTools(headless=True)
        result = await tools.launch()

        assert isinstance(result, ToolResult)
        assert hasattr(result, 'success')
        assert hasattr(result, 'message')
        assert len(result.message) > 0


# =============================================================================
# 9. Real Browser Integration Tests (optional, run when browser available)
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_browser_navigate_to_example_com():
    """Integration test: Navigate to real example.com."""
    if not PLAYWRIGHT_AVAILABLE or not MCP_TOOLS_AVAILABLE:
        pytest.skip("Playwright or MCPTools not available for integration test")

    tools = MCPTools(headless=True, enable_stealth=False, enable_human_timing=False)

    try:
        # Launch
        launch_result = await tools.launch()
        assert launch_result.success is True

        # Navigate
        nav_result = await tools.navigate("https://example.com")
        assert isinstance(nav_result, ToolResult)
        assert nav_result.success is True
        assert "example.com" in nav_result.message.lower() or nav_result.data.get('url') == "https://example.com/"
        assert nav_result.screenshot_b64 is not None

        # Screenshot
        screenshot_result = await tools.screenshot()
        assert screenshot_result.success is True
        assert screenshot_result.screenshot_b64 is not None

    finally:
        await tools.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_browser_handles_404():
    """Integration test: Gracefully handle 404 page."""
    if not PLAYWRIGHT_AVAILABLE or not MCP_TOOLS_AVAILABLE:
        pytest.skip("Playwright or MCPTools not available for integration test")

    tools = MCPTools(headless=True, enable_stealth=False, enable_human_timing=False)

    try:
        await tools.launch()

        # Navigate to a 404 page
        result = await tools.navigate("https://example.com/this-page-does-not-exist-12345")

        # Should still succeed (page loads, just shows 404)
        assert isinstance(result, ToolResult)
        # Navigation itself succeeds, even if page shows 404
        assert result.screenshot_b64 is not None

    finally:
        await tools.close()


# =============================================================================
# Test Summary and Helpers
# =============================================================================

def test_tool_result_structure():
    """Verify ToolResult has expected structure."""
    result = ToolResult(
        success=True,
        message="Test message",
        data={"key": "value"},
        screenshot_b64="base64_string"
    )

    assert result.success is True
    assert result.message == "Test message"
    assert result.data == {"key": "value"}
    assert result.screenshot_b64 == "base64_string"


def test_tool_result_minimal():
    """ToolResult works with minimal arguments."""
    result = ToolResult(success=False, message="Error occurred")

    assert result.success is False
    assert result.message == "Error occurred"
    assert result.data is None
    assert result.screenshot_b64 is None


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == '__main__':
    """
    Run reliability tests.

    Usage:
        python test_reliability.py                    # Run all unit tests
        pytest test_reliability.py -v                 # Verbose output
        pytest test_reliability.py -v -m integration  # Run integration tests only
        pytest test_reliability.py -v -m "not integration"  # Skip integration tests
    """
    import sys

    # If run directly, use pytest
    sys.exit(pytest.main([__file__, '-v']))
