"""
Test file to verify all browser improvement module exports work correctly.

Run with: python3 test_browser_improvements_exports.py
"""

import sys
import asyncio


def test_imports():
    """Test that all browser improvement modules can be imported."""
    print("Testing browser improvement module imports...")

    try:
        from agent import (
            # DOM First Browser
            DOMFirstBrowser, ElementNode, DOMSnapshotResult, DOMObserveResult,
            # CDP Browser Connector
            CDPBrowserConnector, CDPBrowserInstance,
            connect_to_existing_chrome, auto_connect_chrome,
            # Extraction Helpers
            extract_links, extract_clickable, extract_forms, extract_inputs,
            extract_tables, extract_text_content, extract_structured,
            extract_contact_forms, extract_navigation_links,
            QuickExtractor, ExtractedElement,
            # DevTools Hooks
            DevToolsHooks, quick_devtools_summary,
            # Token Optimizer
            TokenOptimizer, create_optimizer, optimize_snapshot,
            estimate_snapshot_tokens, TOKEN_OPTIMIZER_DEFAULT_CONFIG,
            # Browser Backend
            BrowserBackend, PlaywrightBackend, CDPBackend, BackendFactory,
            create_backend, BackendElementRef, BackendSnapshotResult,
            InteractionResult, NavigationResult, BackendObserveResult,
            # Convenience functions
            get_optimized_browser,
        )

        # Check which modules are available
        modules = {
            'DOMFirstBrowser': DOMFirstBrowser,
            'CDPBrowserConnector': CDPBrowserConnector,
            'QuickExtractor': QuickExtractor,
            'DevToolsHooks': DevToolsHooks,
            'TokenOptimizer': TokenOptimizer,
            'BrowserBackend': BrowserBackend,
            'get_optimized_browser': get_optimized_browser,
        }

        print("\nModule availability:")
        for name, module in modules.items():
            status = "AVAILABLE" if module is not None else "NOT AVAILABLE"
            print(f"  {name}: {status}")

        # Check extraction functions
        extraction_funcs = {
            'extract_links': extract_links,
            'extract_clickable': extract_clickable,
            'extract_forms': extract_forms,
            'extract_inputs': extract_inputs,
            'extract_tables': extract_tables,
        }

        print("\nExtraction functions:")
        for name, func in extraction_funcs.items():
            status = "AVAILABLE" if func is not None else "NOT AVAILABLE"
            print(f"  {name}: {status}")

        print("\n✓ All imports successful!")
        return True

    except ImportError as e:
        print(f"\n✗ Import failed: {e}")
        return False
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        return False


async def test_get_optimized_browser():
    """Test the convenience function for creating optimized browser."""
    print("\n\nTesting get_optimized_browser() convenience function...")

    try:
        from agent import get_optimized_browser, BrowserBackend

        if get_optimized_browser is None:
            print("  get_optimized_browser not available - skipping test")
            return False

        if BrowserBackend is None:
            print("  BrowserBackend not available - skipping test")
            return False

        # Test that the function is callable
        print(f"  Function signature: {get_optimized_browser.__name__}")
        print(f"  Function type: {type(get_optimized_browser)}")

        # Note: We don't actually call it here because it requires a browser installation
        # But we can verify it's properly defined
        print("  ✓ get_optimized_browser is properly defined")

        return True

    except Exception as e:
        print(f"  ✗ Test failed: {e}")
        return False


async def test_token_optimizer():
    """Test token optimizer exports."""
    print("\n\nTesting Token Optimizer exports...")

    try:
        from agent import TokenOptimizer, create_optimizer, TOKEN_OPTIMIZER_DEFAULT_CONFIG

        if TokenOptimizer is None:
            print("  TokenOptimizer not available - skipping test")
            return False

        print(f"  TokenOptimizer class: {TokenOptimizer}")
        print(f"  create_optimizer function: {create_optimizer}")
        print(f"  Default config available: {TOKEN_OPTIMIZER_DEFAULT_CONFIG is not None}")

        if create_optimizer:
            # Try creating an optimizer instance
            optimizer = create_optimizer()
            print(f"  ✓ Created optimizer instance: {type(optimizer)}")
        else:
            print("  create_optimizer not available - using direct class")
            optimizer = TokenOptimizer()
            print(f"  ✓ Created optimizer instance: {type(optimizer)}")

        return True

    except Exception as e:
        print(f"  ✗ Test failed: {e}")
        return False


async def test_extraction_helpers():
    """Test extraction helper exports."""
    print("\n\nTesting Extraction Helpers exports...")

    try:
        from agent import QuickExtractor, ExtractedElement

        if QuickExtractor is None:
            print("  QuickExtractor not available - skipping test")
            return False

        print(f"  QuickExtractor class: {QuickExtractor}")
        print(f"  ExtractedElement class: {ExtractedElement}")
        print("  ✓ Extraction helper classes available")

        return True

    except Exception as e:
        print(f"  ✗ Test failed: {e}")
        return False


async def test_devtools_hooks():
    """Test DevTools hooks exports."""
    print("\n\nTesting DevTools Hooks exports...")

    try:
        from agent import DevToolsHooks, quick_devtools_summary

        if DevToolsHooks is None:
            print("  DevToolsHooks not available - skipping test")
            return False

        print(f"  DevToolsHooks class: {DevToolsHooks}")
        print(f"  quick_devtools_summary function: {quick_devtools_summary}")
        print("  ✓ DevTools hooks available")

        return True

    except Exception as e:
        print(f"  ✗ Test failed: {e}")
        return False


async def test_browser_backend():
    """Test browser backend exports."""
    print("\n\nTesting Browser Backend exports...")

    try:
        from agent import (
            BrowserBackend, PlaywrightBackend, CDPBackend,
            BackendFactory, create_backend
        )

        if BrowserBackend is None:
            print("  BrowserBackend not available - skipping test")
            return False

        print(f"  BrowserBackend (abstract): {BrowserBackend}")
        print(f"  PlaywrightBackend: {PlaywrightBackend}")
        print(f"  CDPBackend: {CDPBackend}")
        print(f"  BackendFactory: {BackendFactory}")
        print(f"  create_backend function: {create_backend}")
        print("  ✓ Browser backend classes available")

        return True

    except Exception as e:
        print(f"  ✗ Test failed: {e}")
        return False


async def test_dom_first_browser():
    """Test DOM First Browser exports."""
    print("\n\nTesting DOM First Browser exports...")

    try:
        from agent import DOMFirstBrowser, ElementNode

        if DOMFirstBrowser is None:
            print("  DOMFirstBrowser not available - skipping test")
            return False

        print(f"  DOMFirstBrowser class: {DOMFirstBrowser}")
        print(f"  ElementNode class: {ElementNode}")
        print("  ✓ DOM First Browser available")

        return True

    except Exception as e:
        print(f"  ✗ Test failed: {e}")
        return False


async def test_cdp_connector():
    """Test CDP Browser Connector exports."""
    print("\n\nTesting CDP Browser Connector exports...")

    try:
        from agent import CDPBrowserConnector, CDPBrowserInstance

        if CDPBrowserConnector is None:
            print("  CDPBrowserConnector not available - skipping test")
            return False

        print(f"  CDPBrowserConnector class: {CDPBrowserConnector}")
        print(f"  CDPBrowserInstance class: {CDPBrowserInstance}")
        print("  ✓ CDP Browser Connector available")

        return True

    except Exception as e:
        print(f"  ✗ Test failed: {e}")
        return False


async def run_all_tests():
    """Run all tests."""
    print("=" * 70)
    print("BROWSER IMPROVEMENTS EXPORT TESTS")
    print("=" * 70)

    # Test imports first
    if not test_imports():
        print("\nImport test failed - stopping here")
        return False

    # Run async tests
    tests = [
        test_get_optimized_browser(),
        test_token_optimizer(),
        test_extraction_helpers(),
        test_devtools_hooks(),
        test_browser_backend(),
        test_dom_first_browser(),
        test_cdp_connector(),
    ]

    results = await asyncio.gather(*tests, return_exceptions=True)

    # Check results
    passed = sum(1 for r in results if r is True)
    failed = sum(1 for r in results if r is not True)

    print("\n" + "=" * 70)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 70)

    return failed == 0


if __name__ == "__main__":
    # Add engine to path
    sys.path.insert(0, '..')

    # Run tests
    success = asyncio.run(run_all_tests())

    if success:
        print("\n✓ All tests passed!")
        sys.exit(0)
    else:
        print("\n✗ Some tests failed")
        sys.exit(1)
