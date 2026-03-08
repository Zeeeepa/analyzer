"""
Test SearchHandler integration with A11yBrowser.

This tests that the search_handler is properly wired into a11y_browser.py
and can be called through the browser interface.
"""

import asyncio
from a11y_browser import A11yBrowser, SEARCH_HANDLER_AVAILABLE


async def test_search_integration():
    """Test that SearchHandler is integrated into A11yBrowser."""

    print("=" * 60)
    print("SearchHandler Integration Test")
    print("=" * 60)

    # Check if SearchHandler is available
    print(f"\nSearchHandler Available: {SEARCH_HANDLER_AVAILABLE}")

    if not SEARCH_HANDLER_AVAILABLE:
        print("\nWARNING: SearchHandler is not available!")
        print("This means the import failed. Check the import statements.")
        return

    # Create browser instance (no need to launch for search operations)
    browser = A11yBrowser(headless=True)

    # Test 1: Search for Python files
    print("\n" + "-" * 60)
    print("Test 1: Search for Python files (*.py)")
    print("-" * 60)

    result = await browser.search_files("*.py", ".")

    if result.success:
        print(f"\nSuccess! Found {result.data['total_found']} Python files")
        print(f"Showing first {len(result.data['files'])} files:")
        for i, file_path in enumerate(result.data['files'][:5], 1):
            print(f"  {i}. {file_path}")
        if result.data['truncated']:
            print(f"\n  (... and {result.data['total_found'] - len(result.data['files'])} more)")
    else:
        print(f"\nFailed: {result.error}")

    # Test 2: Search content for a pattern
    print("\n" + "-" * 60)
    print("Test 2: Search content for 'SearchHandler'")
    print("-" * 60)

    result = await browser.search_content("SearchHandler", ".", file_pattern="*.py")

    if result.success:
        print(f"\nSuccess! Found {result.data['total_matches']} matches in {result.data['files_searched']} files")
        if result.data['matches']:
            print(f"\nFirst match:")
            match = result.data['matches'][0]
            print(f"  File: {match['file']}")
            print(f"  Line {match['line']}: {match['content'][:80]}...")
    else:
        print(f"\nFailed: {result.error}")

    # Test 3: Find specific file
    print("\n" + "-" * 60)
    print("Test 3: Find 'search_handler.py' file")
    print("-" * 60)

    result = await browser.find_files("search_handler.py", ".")

    if result.success:
        print(f"\nSuccess! Found {len(result.data['files'])} file(s)")
        for file_path in result.data['files']:
            print(f"  - {file_path}")
    else:
        print(f"\nFailed: {result.error}")

    # Test 4: Find files containing pattern
    print("\n" + "-" * 60)
    print("Test 4: Find files containing 'async def'")
    print("-" * 60)

    result = await browser.find_files_containing("async def", ".")

    if result.success:
        print(f"\nSuccess! Found {len(result.data['files'])} file(s) with 'async def'")
        for i, file_path in enumerate(result.data['files'][:5], 1):
            print(f"  {i}. {file_path}")
        if len(result.data['files']) > 5:
            print(f"\n  (... and {len(result.data['files']) - 5} more)")
    else:
        print(f"\nFailed: {result.error}")

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_search_integration())
