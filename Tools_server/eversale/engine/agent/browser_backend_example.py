"""
Browser Backend Usage Examples

Shows how to use the unified browser backend interface for automation.
"""

import asyncio
from browser_backend import create_backend, BackendFactory


async def example_basic_automation():
    """Basic automation using auto-detected backend."""
    # Auto-detect best backend (CDP if Chrome running, else Playwright)
    backend = await create_backend('auto', headless=False)

    if not backend:
        print("Failed to create backend")
        return

    try:
        # Navigate
        nav_result = await backend.navigate('https://example.com')
        print(f"Navigation: {nav_result.success}, URL: {nav_result.url}")

        # Get snapshot
        snapshot = await backend.snapshot()
        print(f"Page: {snapshot.title}")
        print(f"Found {len(snapshot.elements)} interactive elements")

        # Show first 5 elements
        for el in snapshot.elements[:5]:
            print(f"  {el.ref} - {el.text[:50]}")

        # Click a button (if exists)
        buttons = snapshot.get_by_role('button')
        if buttons:
            print(f"\nClicking button: {buttons[0].text}")
            click_result = await backend.click(buttons[0].mmid)
            print(f"Click result: {click_result.success}")

        # Type into search box (if exists)
        textboxes = snapshot.get_by_role('textbox')
        if textboxes:
            print(f"\nTyping into: {textboxes[0].text}")
            type_result = await backend.type(textboxes[0].mmid, "test query")
            print(f"Type result: {type_result.success}")

    finally:
        await backend.disconnect()


async def example_explicit_playwright():
    """Explicitly use Playwright backend."""
    backend = await create_backend('playwright', headless=True)

    if not backend:
        print("Failed to create Playwright backend")
        return

    try:
        await backend.navigate('https://github.com')
        snapshot = await backend.snapshot()

        # Find sign-in button
        sign_in_buttons = [
            el for el in snapshot.elements
            if 'sign in' in el.text.lower() and el.role == 'link'
        ]

        if sign_in_buttons:
            print(f"Found sign-in: {sign_in_buttons[0].ref}")

    finally:
        await backend.disconnect()


async def example_cdp_reuse_session():
    """Use CDP to connect to existing Chrome with logins."""
    # Start Chrome with: chrome --remote-debugging-port=9222
    backend = await create_backend('cdp', cdp_url='http://localhost:9222')

    if not backend:
        print("Failed to connect to Chrome CDP")
        print("Start Chrome with: chrome --remote-debugging-port=9222")
        return

    try:
        # Reuse existing session - already logged in!
        await backend.navigate('https://twitter.com/home')
        snapshot = await backend.snapshot()

        print(f"Page: {snapshot.title}")
        print("Using existing login session via CDP")

    finally:
        await backend.disconnect()


async def example_context_manager():
    """Use context manager for automatic cleanup."""
    async with await create_backend('auto') as backend:
        if backend:
            await backend.navigate('https://news.ycombinator.com')
            snapshot = await backend.snapshot()

            # Get all links
            links = snapshot.get_by_role('link')
            print(f"Found {len(links)} links on HN frontpage")

            # Click first story
            if links:
                await backend.click(links[0].mmid)
                await asyncio.sleep(2)  # Wait for navigation

                # Take screenshot
                screenshot = await backend.screenshot()
                print(f"Screenshot size: {len(screenshot)} bytes")


async def example_error_handling():
    """Proper error handling."""
    backend = await create_backend('auto')

    if not backend:
        print("Backend creation failed")
        return

    try:
        # Navigate
        nav_result = await backend.navigate('https://example.com')
        if not nav_result.success:
            print(f"Navigation failed: {nav_result.error}")
            return

        # Try to click non-existent element
        click_result = await backend.click('mm99999')
        if not click_result.success:
            print(f"Click failed: {click_result.error}")
            print(f"Error type: {click_result.error_type}")

    finally:
        await backend.disconnect()


async def example_switching_backends():
    """Compare Playwright vs CDP performance."""
    url = 'https://example.com'

    # Try Playwright first
    async with BackendFactory.create('playwright') as pw_backend:
        if await pw_backend.connect():
            nav = await pw_backend.navigate(url)
            print(f"Playwright load time: {nav.load_time_ms:.0f}ms")

    # Try CDP (if available)
    async with BackendFactory.create('cdp') as cdp_backend:
        if await cdp_backend.connect():
            nav = await cdp_backend.navigate(url)
            print(f"CDP load time: {nav.load_time_ms:.0f}ms")
        else:
            print("CDP not available (Chrome not running with debug port)")


if __name__ == '__main__':
    print("Browser Backend Examples\n")

    # Run examples
    print("=== Basic Automation ===")
    asyncio.run(example_basic_automation())

    print("\n=== Context Manager ===")
    asyncio.run(example_context_manager())

    print("\n=== Error Handling ===")
    asyncio.run(example_error_handling())
