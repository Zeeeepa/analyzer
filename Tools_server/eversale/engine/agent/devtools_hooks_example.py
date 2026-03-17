"""
Example usage of DevToolsHooks for debugging and monitoring.

This file demonstrates different use cases for the DevToolsHooks class.
"""

import asyncio
from playwright.async_api import async_playwright
from devtools_hooks import DevToolsHooks, quick_devtools_summary


async def example_basic_capture():
    """Basic usage: Capture network and console during page load."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        # Create DevTools hooks
        devtools = DevToolsHooks(page)
        await devtools.start_capture(network=True, console=True)

        # Navigate and interact
        await page.goto("https://example.com")
        await page.wait_for_timeout(2000)

        # Get summary
        summary = devtools.summary()
        print("\nPage Load Summary:")
        print(f"  Total requests: {summary['network']['total_requests']}")
        print(f"  Failed requests: {summary['network']['failed_requests']}")
        print(f"  Console errors: {summary['console']['errors']}")
        print(f"  Average request time: {summary['network']['average_duration_ms']}ms")

        await devtools.stop_capture()
        await browser.close()


async def example_error_detection():
    """Detect and report errors during automation."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        devtools = DevToolsHooks(page)
        await devtools.start_capture(network=True, console=True)

        # Navigate to a page (may have errors)
        await page.goto("https://example.com")
        await page.wait_for_timeout(2000)

        # Check for errors
        errors = devtools.get_errors()
        console_errors = devtools.get_console_log(level="error")
        failed_requests = devtools.get_failed_requests()

        print("\nError Report:")
        print(f"  Page errors: {len(errors)}")
        for error in errors:
            print(f"    - {error['message']}")

        print(f"\n  Console errors: {len(console_errors)}")
        for log in console_errors:
            print(f"    - {log['text']}")

        print(f"\n  Failed requests: {len(failed_requests)}")
        for req in failed_requests:
            print(f"    - {req['url']} ({req['failure_reason']})")

        await devtools.cleanup()
        await browser.close()


async def example_network_analysis():
    """Analyze network performance and identify slow requests."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        devtools = DevToolsHooks(page)
        await devtools.start_capture(network=True, console=False)

        await page.goto("https://example.com")
        await page.wait_for_timeout(3000)

        # Find slow requests
        slow_requests = devtools.get_slow_requests(threshold_ms=1000)
        print("\nSlow Requests (>1s):")
        for req in slow_requests:
            print(f"  {req['duration_ms']}ms - {req['url']}")

        # Check for 4xx/5xx errors
        status_errors = devtools.get_status_code_errors()
        print(f"\nHTTP Errors: {len(status_errors)}")
        for req in status_errors:
            print(f"  {req['status_code']} - {req['url']}")

        # Filter by resource type
        xhr_requests = devtools.get_network_log(filter_type="xhr")
        print(f"\nXHR Requests: {len(xhr_requests)}")

        await devtools.cleanup()
        await browser.close()


async def example_blocked_resources():
    """Detect blocked resources (CORS, CSP, etc.)."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        devtools = DevToolsHooks(page)
        await devtools.start_capture(network=True, console=True)

        await page.goto("https://example.com")
        await page.wait_for_timeout(2000)

        # Check for blocked resources
        blocked = devtools.get_blocked_resources()
        print(f"\nBlocked Resources: {len(blocked)}")
        for res in blocked:
            print(f"  {res['url']}")
            print(f"    Reason: {res['failure_reason']}")

        await devtools.cleanup()
        await browser.close()


async def example_quick_summary():
    """Use the convenience function for quick debugging."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        await page.goto("https://example.com")

        # Quick 5-second capture and summary
        summary = await quick_devtools_summary(page, duration_seconds=5)

        print("\nQuick DevTools Summary:")
        print(f"  Network:")
        print(f"    Total requests: {summary['network']['total_requests']}")
        print(f"    Failed: {summary['network']['failed_requests']}")
        print(f"    4xx errors: {summary['network']['status_4xx']}")
        print(f"    5xx errors: {summary['network']['status_5xx']}")
        print(f"\n  Console:")
        print(f"    Total messages: {summary['console']['total_messages']}")
        print(f"    Errors: {summary['console']['errors']}")
        print(f"    Warnings: {summary['console']['warnings']}")
        print(f"\n  Resource types:")
        for res_type, count in summary['network']['resource_types'].items():
            print(f"    {res_type}: {count}")

        await browser.close()


async def example_memory_efficient():
    """Configure for long-running sessions with memory limits."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        # Create with smaller buffers and no response body capture
        devtools = DevToolsHooks(
            page,
            max_network_entries=100,  # Only keep last 100 requests
            max_console_entries=50,   # Only keep last 50 console logs
            max_error_entries=25,     # Only keep last 25 errors
            capture_response_bodies=False  # Don't capture bodies (saves memory)
        )

        await devtools.start_capture(network=True, console=True)

        # Run long automation
        await page.goto("https://example.com")
        for i in range(10):
            await page.reload()
            await page.wait_for_timeout(1000)

        # Logs automatically rotate (circular buffer)
        summary = devtools.summary()
        print(f"\nAfter 10 reloads:")
        print(f"  Network log size: {summary['network']['total_requests']} (max 100)")
        print(f"  Console log size: {summary['console']['total_messages']} (max 50)")

        await devtools.cleanup()
        await browser.close()


async def example_integration_with_automation():
    """
    Real-world example: Integrate DevTools monitoring into automation.
    Useful for debugging why automation fails.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        devtools = DevToolsHooks(page)
        await devtools.start_capture(network=True, console=True)

        try:
            # Your automation code
            await page.goto("https://example.com")
            await page.click("button")  # Might fail
            await page.fill("input", "test")

        except Exception as e:
            # On failure, check DevTools for clues
            print(f"\nAutomation failed: {e}")
            print("\nDiagnostics:")

            # Check for JavaScript errors
            errors = devtools.get_errors()
            if errors:
                print(f"  JavaScript errors detected: {len(errors)}")
                for err in errors:
                    print(f"    - {err['message']}")

            # Check for failed API calls
            failed_requests = devtools.get_failed_requests()
            if failed_requests:
                print(f"  Failed network requests: {len(failed_requests)}")
                for req in failed_requests:
                    print(f"    - {req['url']}")

            # Check for console errors
            console_errors = devtools.get_console_log(level="error")
            if console_errors:
                print(f"  Console errors: {len(console_errors)}")
                for log in console_errors[:5]:  # Show first 5
                    print(f"    - {log['text']}")

            # Check for HTTP errors
            http_errors = devtools.get_status_code_errors()
            if http_errors:
                print(f"  HTTP errors: {len(http_errors)}")
                for req in http_errors:
                    print(f"    - {req['status_code']} {req['url']}")

        finally:
            await devtools.cleanup()
            await browser.close()


if __name__ == "__main__":
    print("DevToolsHooks Examples\n")
    print("=" * 60)

    # Run examples (uncomment the one you want to try)
    # asyncio.run(example_basic_capture())
    # asyncio.run(example_error_detection())
    # asyncio.run(example_network_analysis())
    # asyncio.run(example_blocked_resources())
    # asyncio.run(example_quick_summary())
    # asyncio.run(example_memory_efficient())
    asyncio.run(example_integration_with_automation())
