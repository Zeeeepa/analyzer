"""
Test reliable browser tools integration with brain_enhanced_v2 and playwright_direct.

This verifies that:
1. ReliableBrowserAdapter properly wraps MCP client
2. Validation catches invalid inputs early
3. Health checks work correctly
4. Backward compatibility is maintained
"""

import asyncio
from unittest.mock import Mock, AsyncMock, patch
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))


class MockMCPClient:
    """Mock MCP client for testing."""

    async def call_tool(self, tool_name: str, params: dict):
        """Simulate successful tool calls."""
        if tool_name == "playwright_navigate":
            return {"success": True, "url": params.get("url")}
        elif tool_name == "playwright_click":
            return {"success": True, "clicked": True}
        elif tool_name == "playwright_fill":
            return {"success": True, "filled": True}
        elif tool_name == "playwright_snapshot":
            return {"success": True, "content": "Test snapshot"}
        elif tool_name == "playwright_evaluate":
            return {"success": True, "result": "http://example.com"}
        else:
            return {"success": True, "data": f"{tool_name} executed"}


async def test_reliable_browser_adapter():
    """Test ReliableBrowserAdapter wraps MCP client correctly."""
    print("\n=== Testing ReliableBrowserAdapter ===\n")

    try:
        from reliable_browser_tools import ReliableBrowserAdapter, wrap_mcp_client

        mock_mcp = MockMCPClient()

        # Test wrapping
        adapter = wrap_mcp_client(mock_mcp, enable_reliability=True)
        print("[PASS] ReliableBrowserAdapter created successfully")

        # Test navigation with valid URL
        result = await adapter.call_tool("playwright_navigate", {"url": "https://example.com"})
        print(f"[PASS] Navigate with valid URL: {result}")

        # Test navigation with invalid URL
        result = await adapter.call_tool("playwright_navigate", {"url": "not-a-url"})
        if "error" in result:
            print(f"[PASS] Navigate with invalid URL caught: {result.get('error')}")
        else:
            print(f"[WARN] Invalid URL should have been caught: {result}")

        # Test click with valid selector
        result = await adapter.call_tool("playwright_click", {"selector": "#button"})
        print(f"[PASS] Click with valid selector: {result}")

        # Test click with empty selector
        result = await adapter.call_tool("playwright_click", {"selector": ""})
        if "error" in result:
            print(f"[PASS] Click with empty selector caught: {result.get('error')}")
        else:
            print(f"[WARN] Empty selector should have been caught: {result}")

        # Test fill with valid inputs
        result = await adapter.call_tool("playwright_fill", {"selector": "#input", "value": "test text"})
        print(f"[PASS] Fill with valid inputs: {result}")

        # Test non-browser tool passes through
        result = await adapter.call_tool("some_other_tool", {"param": "value"})
        print(f"[PASS] Non-browser tool passes through: {result}")

        return True

    except Exception as e:
        print(f"[FAIL] ReliableBrowserAdapter test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_brain_enhanced_integration():
    """Test brain_enhanced_v2 integration."""
    print("\n=== Testing brain_enhanced_v2 Integration ===\n")

    try:
        # Import after mocking
        mock_mcp = MockMCPClient()

        # Test that BrowserToolAdapter uses wrapped client
        from brain_enhanced_v2 import BrowserToolAdapter, RELIABLE_BROWSER_AVAILABLE

        if RELIABLE_BROWSER_AVAILABLE:
            print("[PASS] Reliable browser tools available in brain_enhanced_v2")

            # Create adapter
            adapter = BrowserToolAdapter(mock_mcp, query="test query")

            # Check that MCP is wrapped
            print(f"[PASS] BrowserToolAdapter MCP type: {type(adapter.mcp).__name__}")

            # Test navigate through adapter
            result = await adapter.navigate("https://example.com")
            print(f"[PASS] Navigate through BrowserToolAdapter: {result}")
        else:
            print("[WARN] Reliable browser tools not available in brain_enhanced_v2")
            return False

        return True

    except Exception as e:
        print(f"[FAIL] brain_enhanced_v2 integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_playwright_direct_validation():
    """Test playwright_direct validation layer."""
    print("\n=== Testing playwright_direct Validation ===\n")

    try:
        from playwright_direct import RELIABLE_BROWSER_TOOLS_AVAILABLE, BrowserInputValidator

        if RELIABLE_BROWSER_TOOLS_AVAILABLE:
            print("[PASS] Reliable browser tools available in playwright_direct")

            validator = BrowserInputValidator()

            # Test URL validation
            valid, error = validator.validate_url("https://example.com")
            assert valid, f"Valid URL failed: {error}"
            print("[PASS] URL validation - valid URL")

            valid, error = validator.validate_url("not a url")
            assert not valid, "Invalid URL should fail"
            print(f"[PASS] URL validation - invalid URL caught: {error}")

            # Test selector validation
            valid, error = validator.validate_target("#button")
            assert valid, f"Valid selector failed: {error}"
            print("[PASS] Selector validation - valid selector")

            valid, error = validator.validate_target("")
            assert not valid, "Empty selector should fail"
            print(f"[PASS] Selector validation - empty selector caught: {error}")

            # Test text validation
            valid, error = validator.validate_text("normal text")
            assert valid, f"Valid text failed: {error}"
            print("[PASS] Text validation - valid text")

            valid, error = validator.validate_text("x" * 10001)
            assert not valid, "Too long text should fail"
            print(f"[PASS] Text validation - too long text caught: {error}")
        else:
            print("[WARN] Reliable browser tools not available in playwright_direct")
            return False

        return True

    except Exception as e:
        print(f"[FAIL] playwright_direct validation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all integration tests."""
    print("\n" + "=" * 60)
    print("Reliable Browser Tools Integration Tests")
    print("=" * 60)

    results = []

    # Run tests
    results.append(await test_reliable_browser_adapter())
    results.append(await test_brain_enhanced_integration())
    results.append(await test_playwright_direct_validation())

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"\nPassed: {passed}/{total}")

    if passed == total:
        print("\n[SUCCESS] All integration tests passed!")
        return 0
    else:
        print(f"\n[FAILURE] {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
