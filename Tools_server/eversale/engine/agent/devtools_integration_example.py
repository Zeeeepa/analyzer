"""
Example: Integrating DevToolsHooks with playwright_direct.py

Shows how to add DevTools monitoring to existing browser automation.
"""

import asyncio
from pathlib import Path
from devtools_hooks import DevToolsHooks

# Import playwright_direct components
try:
    from patchright.async_api import async_playwright
except ImportError:
    try:
        from rebrowser_playwright.async_api import async_playwright
    except ImportError:
        from playwright.async_api import async_playwright


async def example_with_devtools():
    """
    Example: Add DevTools monitoring to browser automation.

    This shows how to wrap existing automation with DevTools inspection
    for debugging and monitoring purposes.
    """
    async with async_playwright() as p:
        # Launch browser (can use stealth mode, profiles, etc.)
        browser = await p.chromium.launch(
            headless=False,
            args=['--start-maximized']
        )

        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080}
        )

        page = await context.new_page()

        # Attach DevTools hooks
        devtools = DevToolsHooks(
            page,
            max_network_entries=500,
            max_console_entries=200,
            capture_response_bodies=False  # Save memory
        )

        try:
            # Start capturing before automation
            await devtools.start_capture(network=True, console=True)
            print("DevTools capture started\n")

            # Run your automation
            print("Navigating to example.com...")
            await page.goto("https://example.com", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            # Get real-time diagnostics
            summary = devtools.summary()
            print(f"\nPage Load Summary:")
            print(f"  Total requests: {summary['network']['total_requests']}")
            print(f"  Failed requests: {summary['network']['failed_requests']}")
            print(f"  4xx errors: {summary['network']['status_4xx']}")
            print(f"  5xx errors: {summary['network']['status_5xx']}")
            print(f"  Avg request time: {summary['network']['average_duration_ms']}ms")
            print(f"  Console errors: {summary['console']['errors']}")
            print(f"  Console warnings: {summary['console']['warnings']}")

            # Check for issues
            if summary['network']['failed_requests'] > 0:
                print("\nFailed Requests:")
                for req in devtools.get_failed_requests():
                    print(f"  - {req['url']}")
                    print(f"    Reason: {req['failure_reason']}")

            if summary['network']['status_4xx'] > 0 or summary['network']['status_5xx'] > 0:
                print("\nHTTP Errors:")
                for req in devtools.get_status_code_errors():
                    print(f"  - {req['status_code']} {req['url']}")

            if summary['console']['errors'] > 0:
                print("\nConsole Errors:")
                for log in devtools.get_console_log(level="error")[:5]:
                    print(f"  - {log['text']}")

            # Check for slow requests
            slow = devtools.get_slow_requests(threshold_ms=1000)
            if slow:
                print(f"\nSlow Requests (>1s): {len(slow)}")
                for req in slow[:5]:
                    print(f"  - {req['duration_ms']}ms: {req['url']}")

            # Resource type breakdown
            print("\nResource Types:")
            for res_type, count in summary['network']['resource_types'].items():
                print(f"  {res_type}: {count}")

        except Exception as e:
            print(f"\nAutomation error: {e}")

            # Use DevTools to diagnose the failure
            print("\nDevTools Diagnostics:")

            errors = devtools.get_errors()
            if errors:
                print(f"  Page errors: {len(errors)}")
                for err in errors:
                    print(f"    - {err['message']}")

            console_errors = devtools.get_console_log(level="error")
            if console_errors:
                print(f"  Console errors: {len(console_errors)}")

            failed_requests = devtools.get_failed_requests()
            if failed_requests:
                print(f"  Failed requests: {len(failed_requests)}")

        finally:
            # Always cleanup
            await devtools.stop_capture()
            print("\nDevTools capture stopped")
            await browser.close()


async def example_continuous_monitoring():
    """
    Example: Monitor multiple pages with DevTools.

    Shows how to use DevTools for continuous monitoring across
    multiple page navigations.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        devtools = DevToolsHooks(
            page,
            max_network_entries=200,  # Smaller buffer for continuous monitoring
            max_console_entries=100,
            capture_response_bodies=False
        )

        await devtools.start_capture(network=True, console=True)

        try:
            urls = [
                "https://example.com",
                "https://github.com",
                "https://stackoverflow.com"
            ]

            for url in urls:
                print(f"\nNavigating to {url}...")

                # Clear logs before each navigation
                devtools.clear()

                await page.goto(url, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)

                # Get summary for this page
                summary = devtools.summary()
                print(f"  Requests: {summary['network']['total_requests']}")
                print(f"  Failed: {summary['network']['failed_requests']}")
                print(f"  Errors: {summary['console']['errors']}")

                # Alert on issues
                if summary['network']['failed_requests'] > 0:
                    print(f"  WARNING: {summary['network']['failed_requests']} requests failed!")

                if summary['console']['errors'] > 0:
                    print(f"  WARNING: {summary['console']['errors']} console errors!")

        finally:
            await devtools.cleanup()
            await browser.close()


async def example_performance_testing():
    """
    Example: Use DevTools for performance testing.

    Measures page load performance and identifies bottlenecks.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)  # Headless for performance
        page = await browser.new_page()

        devtools = DevToolsHooks(page)
        await devtools.start_capture(network=True, console=False)

        try:
            import time
            start_time = time.time()

            await page.goto("https://example.com")
            await page.wait_for_load_state("networkidle")

            load_time = time.time() - start_time

            summary = devtools.summary()

            print("\nPerformance Report:")
            print(f"  Page load time: {load_time:.2f}s")
            print(f"  Total requests: {summary['network']['total_requests']}")
            print(f"  Average request time: {summary['network']['average_duration_ms']}ms")

            # Find the slowest requests
            slow_requests = devtools.get_slow_requests(threshold_ms=500)
            print(f"\n  Slow requests (>500ms): {len(slow_requests)}")
            for req in slow_requests[:10]:
                print(f"    {req['duration_ms']}ms - {req['resource_type']} - {req['url'][:80]}")

            # Resource breakdown
            print("\n  Resource breakdown:")
            for res_type, count in summary['network']['resource_types'].items():
                type_logs = devtools.get_network_log(filter_type=res_type)
                avg_time = sum(log.get('duration_ms', 0) for log in type_logs) / len(type_logs) if type_logs else 0
                print(f"    {res_type}: {count} requests, avg {avg_time:.0f}ms")

        finally:
            await devtools.cleanup()
            await browser.close()


async def example_error_only_monitoring():
    """
    Example: Lightweight error-only monitoring.

    Only track errors and failures, ignore successful requests.
    Useful for production monitoring.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        # Small buffers since we only care about errors
        devtools = DevToolsHooks(
            page,
            max_network_entries=50,
            max_console_entries=25,
            max_error_entries=25,
            capture_response_bodies=False
        )

        await devtools.start_capture(network=True, console=True)

        try:
            await page.goto("https://example.com")
            await page.wait_for_timeout(2000)

            # Only check for problems
            failed_requests = devtools.get_failed_requests()
            http_errors = devtools.get_status_code_errors()
            page_errors = devtools.get_errors()
            console_errors = devtools.get_console_log(level="error")

            has_issues = (
                len(failed_requests) > 0 or
                len(http_errors) > 0 or
                len(page_errors) > 0 or
                len(console_errors) > 0
            )

            if has_issues:
                print("\nISSUES DETECTED:")
                if failed_requests:
                    print(f"  Failed requests: {len(failed_requests)}")
                if http_errors:
                    print(f"  HTTP errors: {len(http_errors)}")
                if page_errors:
                    print(f"  Page errors: {len(page_errors)}")
                if console_errors:
                    print(f"  Console errors: {len(console_errors)}")
            else:
                print("\nNo issues detected - page loaded successfully")

        finally:
            await devtools.cleanup()
            await browser.close()


if __name__ == "__main__":
    print("DevTools Integration Examples\n")
    print("=" * 60)

    # Run examples (uncomment the one you want)
    asyncio.run(example_with_devtools())
    # asyncio.run(example_continuous_monitoring())
    # asyncio.run(example_performance_testing())
    # asyncio.run(example_error_only_monitoring())
