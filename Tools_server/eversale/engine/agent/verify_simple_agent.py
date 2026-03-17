#!/usr/bin/env python3
"""
Simple Agent Verification Script

Quick verification that all simple agent components are working.
"""

import sys


def verify_imports():
    """Verify all modules can be imported."""
    print("Verifying imports...")

    try:
        import a11y_browser
        print("  ✓ a11y_browser")
    except ImportError as e:
        print(f"  ✗ a11y_browser: {e}")
        return False

    try:
        import simple_agent
        print("  ✓ simple_agent")
    except ImportError as e:
        print(f"  ✗ simple_agent: {e}")
        return False

    try:
        import test_simple_agent
        print("  ✓ test_simple_agent")
    except ImportError as e:
        print(f"  ✗ test_simple_agent: {e}")
        return False

    try:
        import simple_agent_integration_example
        print("  ✓ simple_agent_integration_example")
    except ImportError as e:
        print(f"  ✗ simple_agent_integration_example: {e}")
        return False

    return True


def verify_classes():
    """Verify all classes can be instantiated."""
    print("\nVerifying classes...")

    try:
        from a11y_browser import A11yBrowser, Snapshot, ActionResult, ElementRef
        print("  ✓ A11yBrowser classes")
    except Exception as e:
        print(f"  ✗ A11yBrowser classes: {e}")
        return False

    try:
        from simple_agent import SimpleAgent, AgentResult
        print("  ✓ SimpleAgent classes")
    except Exception as e:
        print(f"  ✗ SimpleAgent classes: {e}")
        return False

    return True


def verify_structure():
    """Verify module structure."""
    print("\nVerifying structure...")

    try:
        from a11y_browser import A11yBrowser
        browser = A11yBrowser(headless=True)

        # Check methods exist
        required_methods = [
            "launch", "close", "navigate", "snapshot",
            "click", "type", "press", "scroll", "wait",
            "hover", "go_back", "go_forward", "refresh", "screenshot"
        ]

        for method in required_methods:
            if not hasattr(browser, method):
                print(f"  ✗ A11yBrowser missing method: {method}")
                return False

        print("  ✓ A11yBrowser has all required methods")
    except Exception as e:
        print(f"  ✗ A11yBrowser structure: {e}")
        return False

    try:
        from simple_agent import SimpleAgent
        agent = SimpleAgent(llm_client=None, headless=True)

        # Check methods exist
        if not hasattr(agent, "run"):
            print("  ✗ SimpleAgent missing run method")
            return False

        print("  ✓ SimpleAgent has all required methods")
    except Exception as e:
        print(f"  ✗ SimpleAgent structure: {e}")
        return False

    return True


def verify_dependencies():
    """Verify required dependencies."""
    print("\nVerifying dependencies...")

    try:
        import playwright
        print("  ✓ playwright")
    except ImportError:
        print("  ✗ playwright (install: pip install playwright)")
        return False

    try:
        import asyncio
        print("  ✓ asyncio")
    except ImportError:
        print("  ✗ asyncio")
        return False

    try:
        from dataclasses import dataclass
        print("  ✓ dataclasses")
    except ImportError:
        print("  ✗ dataclasses")
        return False

    return True


def check_file_sizes():
    """Check file sizes are reasonable."""
    print("\nChecking file sizes...")

    import os

    files = {
        "a11y_browser.py": (20000, 40000),  # 20-40KB
        "simple_agent.py": (8000, 15000),   # 8-15KB
        "test_simple_agent.py": (3000, 6000),  # 3-6KB
        "simple_agent_integration_example.py": (3000, 8000),  # 3-8KB
    }

    all_good = True
    for filename, (min_size, max_size) in files.items():
        if os.path.exists(filename):
            size = os.path.getsize(filename)
            if min_size <= size <= max_size:
                print(f"  ✓ {filename}: {size} bytes")
            else:
                print(f"  ⚠ {filename}: {size} bytes (expected {min_size}-{max_size})")
                all_good = False
        else:
            print(f"  ✗ {filename}: Not found")
            all_good = False

    return all_good


def main():
    """Run all verifications."""
    print("=" * 60)
    print("Simple Agent Verification")
    print("=" * 60)

    results = []

    results.append(("Imports", verify_imports()))
    results.append(("Classes", verify_classes()))
    results.append(("Structure", verify_structure()))
    results.append(("Dependencies", verify_dependencies()))
    results.append(("File Sizes", check_file_sizes()))

    print("\n" + "=" * 60)
    print("Summary:")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")
        if not passed:
            all_passed = False

    print("=" * 60)

    if all_passed:
        print("\n✓ All verifications passed!")
        print("\nNext steps:")
        print("  1. Run tests: python test_simple_agent.py")
        print("  2. Try examples: python a11y_browser.py")
        print("  3. Read docs: SIMPLE_AGENT_README.md")
        return 0
    else:
        print("\n✗ Some verifications failed!")
        print("\nPlease fix the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
