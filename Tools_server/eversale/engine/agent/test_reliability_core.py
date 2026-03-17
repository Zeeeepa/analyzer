"""
Test and demonstration of reliability_core.py

Run with: python3 test_reliability_core.py
"""

import asyncio
from reliability_core import (
    ToolResult, BrowserHealthCheck, ReliableExecutor,
    InputValidator, TimeoutConfig,
    create_success_result, create_error_result, create_validation_error
)


async def test_tool_result():
    """Test ToolResult dataclass."""
    print("\n=== Testing ToolResult ===")

    # Success result
    success = ToolResult(success=True, data={"user": "test"}, duration_ms=123)
    print(f"Success: {success}")
    print(f"Dict: {success.to_dict()}")

    # Error result
    error = ToolResult(
        success=False,
        error="Element not found",
        error_code="ELEMENT_NOT_FOUND",
        duration_ms=500,
        retries_used=2
    )
    print(f"Error: {error}")

    # Convenience functions
    result = create_success_result(data="test", duration_ms=100)
    print(f"Created success: {result}")

    error = create_error_result("Invalid input", "VALIDATION_ERROR")
    print(f"Created error: {error}")


def test_timeout_config():
    """Test TimeoutConfig constants."""
    print("\n=== Testing TimeoutConfig ===")
    print(f"FAST: {TimeoutConfig.FAST}s ({TimeoutConfig.to_ms(TimeoutConfig.FAST)}ms)")
    print(f"NORMAL: {TimeoutConfig.NORMAL}s ({TimeoutConfig.to_ms(TimeoutConfig.NORMAL)}ms)")
    print(f"SLOW: {TimeoutConfig.SLOW}s ({TimeoutConfig.to_ms(TimeoutConfig.SLOW)}ms)")
    print(f"MAX: {TimeoutConfig.MAX}s ({TimeoutConfig.to_ms(TimeoutConfig.MAX)}ms)")


async def test_reliable_executor():
    """Test ReliableExecutor with various scenarios."""
    print("\n=== Testing ReliableExecutor ===")

    executor = ReliableExecutor()

    # Test 1: Successful operation
    async def successful_op():
        await asyncio.sleep(0.1)
        return "success"

    result = await executor.execute(successful_op, timeout=TimeoutConfig.FAST)
    print(f"Successful operation: {result}")

    # Test 2: Operation that fails then succeeds
    attempt_count = [0]

    async def flaky_op():
        attempt_count[0] += 1
        if attempt_count[0] < 2:
            raise ValueError("Temporary failure")
        return "success after retry"

    result = await executor.execute(flaky_op, timeout=TimeoutConfig.FAST, retries=2)
    print(f"Flaky operation: {result}")

    # Test 3: Operation that always fails
    async def failing_op():
        raise RuntimeError("Permanent failure")

    result = await executor.execute(failing_op, timeout=TimeoutConfig.FAST, retries=1)
    print(f"Failing operation: {result}")

    # Test 4: Timeout
    async def slow_op():
        await asyncio.sleep(10)
        return "too slow"

    result = await executor.execute(slow_op, timeout=TimeoutConfig.FAST, retries=0)
    print(f"Timeout operation: {result}")

    # Show stats
    print(f"\nExecutor stats: {executor.get_stats()}")


def test_input_validator():
    """Test InputValidator for various inputs."""
    print("\n=== Testing InputValidator ===")

    validator = InputValidator()

    # Test URLs
    urls = [
        ("https://example.com", True),
        ("http://localhost:3000", True),
        ("about:blank", True),
        ("example.com", False),
        ("", False),
        ("ftp://example.com", False),
    ]

    print("\nURL validation:")
    for url, expected in urls:
        is_valid, error = validator.validate_url(url)
        status = "OK" if is_valid == expected else "FAIL"
        print(f"  [{status}] {url!r}: {is_valid} - {error or 'valid'}")

    # Test selectors
    selectors = [
        ("button.primary", True),
        ("#submit-btn", True),
        ("text=Click me", True),
        ("role=button", True),
        ("[data-testid=submit]", True),
        ("//div[@class='test']", True),
        ("", False),
        ("   ", False),
    ]

    print("\nSelector validation:")
    for selector, expected in selectors:
        is_valid, error = validator.validate_selector(selector)
        status = "OK" if is_valid == expected else "FAIL"
        print(f"  [{status}] {selector!r}: {is_valid} - {error or 'valid'}")

    # Test refs
    refs = [
        ("element-123", True),
        ("btn_submit", True),
        ("test-ref-456", True),
        ("", False),
        ("invalid ref!", False),
        ("ref with spaces", False),
    ]

    print("\nRef validation:")
    for ref, expected in refs:
        is_valid, error = validator.validate_ref(ref)
        status = "OK" if is_valid == expected else "FAIL"
        print(f"  [{status}] {ref!r}: {is_valid} - {error or 'valid'}")

    # Test timeouts
    timeouts = [
        (5.0, True),
        (0.5, True),
        (TimeoutConfig.MAX, True),
        (0, False),
        (-1, False),
        (100, False),
    ]

    print("\nTimeout validation:")
    for timeout, expected in timeouts:
        is_valid, error = validator.validate_timeout(timeout)
        status = "OK" if is_valid == expected else "FAIL"
        print(f"  [{status}] {timeout}: {is_valid} - {error or 'valid'}")


async def test_browser_health_check():
    """Test BrowserHealthCheck (without actual browser)."""
    print("\n=== Testing BrowserHealthCheck ===")

    health = BrowserHealthCheck()

    # Mock page object
    class MockPage:
        def __init__(self, should_fail=False):
            self.should_fail = should_fail

        async def evaluate(self, script):
            if self.should_fail:
                raise RuntimeError("Browser crashed")
            await asyncio.sleep(0.1)
            if "readyState" in script:
                return "complete"
            return True

        async def reload(self, wait_until=None):
            await asyncio.sleep(0.1)

        async def goto(self, url):
            await asyncio.sleep(0.1)

    # Test healthy browser
    healthy_page = MockPage(should_fail=False)
    is_alive = await health.check_browser_alive(healthy_page)
    print(f"Healthy browser check: {is_alive}")

    is_loaded = await health.check_page_loaded(healthy_page)
    print(f"Page loaded check: {is_loaded}")

    result = await health.wait_for_ready(healthy_page, timeout=TimeoutConfig.FAST)
    print(f"Wait for ready: {result}")

    # Test crashed browser
    crashed_page = MockPage(should_fail=True)
    is_alive = await health.check_browser_alive(crashed_page)
    print(f"Crashed browser check: {is_alive}")

    print(f"Is unhealthy: {health.is_unhealthy}")


async def main():
    """Run all tests."""
    print("=" * 60)
    print("RELIABILITY CORE TEST SUITE")
    print("=" * 60)

    # Run tests
    await test_tool_result()
    test_timeout_config()
    await test_reliable_executor()
    test_input_validator()
    await test_browser_health_check()

    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
