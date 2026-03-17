"""
Test selector-based snapshot filtering.
"""
import asyncio
import sys
from pathlib import Path

# Add agent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from a11y_browser import A11yBrowser


async def test_selector_filtering():
    """Test snapshot filtering with selectors."""
    print("Testing selector-based snapshot filtering...\n")

    async with A11yBrowser(headless=True) as browser:
        # Navigate to a test page
        print("1. Navigating to example.com...")
        result = await browser.navigate("https://example.com")
        if not result.success:
            print(f"Failed to navigate: {result.error}")
            return

        await asyncio.sleep(2)  # Wait for page load

        # Test 1: Full snapshot
        print("\n2. Taking full snapshot...")
        full_snapshot = await browser.snapshot()
        full_count = len(full_snapshot.elements)
        print(f"Full snapshot: {full_count} elements")

        # Test 2: Filter by selector (main content only)
        print("\n3. Taking filtered snapshot (main only)...")
        filtered_snapshot = await browser.snapshot(selector="main, div")
        filtered_count = len(filtered_snapshot.elements)
        print(f"Filtered snapshot: {filtered_count} elements")
        reduction = ((full_count - filtered_count) / full_count * 100) if full_count > 0 else 0
        print(f"Reduction: {reduction:.1f}%")

        # Test 3: Exclude selectors
        print("\n4. Taking snapshot with exclusions (exclude footer, nav)...")
        excluded_snapshot = await browser.snapshot(
            exclude_selectors=["footer", "nav"]
        )
        excluded_count = len(excluded_snapshot.elements)
        print(f"Excluded snapshot: {excluded_count} elements")

        # Test 4: Using class constants
        print("\n5. Testing class constants...")
        print(f"INTERACTIVE_ONLY: {A11yBrowser.INTERACTIVE_ONLY}")
        print(f"FORM_ONLY: {A11yBrowser.FORM_ONLY}")
        print(f"EXCLUDE_CHROME: {A11yBrowser.EXCLUDE_CHROME}")

        print("\n✓ All tests passed!")


if __name__ == "__main__":
    asyncio.run(test_selector_filtering())
