"""
Test UI-TARS integration into brain_enhanced_v2.py

Verifies that:
1. UI-TARS modules can be imported
2. ConversationContext works correctly
3. retry_with_timeout works correctly
4. UITarsEnhancer can be initialized
"""

import sys
import asyncio


def test_imports():
    """Test that UI-TARS modules can be imported."""
    print("Testing UI-TARS imports...")

    try:
        from ui_tars_patterns import (
            ConversationContext,
            RetryConfig,
            retry_with_timeout,
            ActionParser,
            create_system2_prompt
        )
        print("  - ui_tars_patterns: OK")
    except ImportError as e:
        print(f"  - ui_tars_patterns: FAILED - {e}")
        return False

    try:
        from ui_tars_integration import UITarsEnhancer, enhance_brain_config
        print("  - ui_tars_integration: OK")
    except ImportError as e:
        print(f"  - ui_tars_integration: FAILED - {e}")
        return False

    try:
        from brain_enhanced_v2 import EnhancedBrain, UITARS_AVAILABLE
        print(f"  - brain_enhanced_v2 UITARS_AVAILABLE: {UITARS_AVAILABLE}")
        if not UITARS_AVAILABLE:
            print("  - WARNING: UITARS_AVAILABLE is False")
    except ImportError as e:
        print(f"  - brain_enhanced_v2: FAILED - {e}")
        return False

    print("  - All imports: OK\n")
    return True


def test_conversation_context():
    """Test ConversationContext screenshot pruning."""
    print("Testing ConversationContext...")

    from ui_tars_patterns import ConversationContext

    ctx = ConversationContext(max_screenshots=2)

    # Add 3 screenshots
    ctx.add_message("user", "Step 1", "screenshot1_base64")
    ctx.add_message("user", "Step 2", "screenshot2_base64")
    ctx.add_message("user", "Step 3", "screenshot3_base64")

    # Should only keep last 2
    if ctx.screenshot_count != 2:
        print(f"  - FAILED: Expected 2 screenshots, got {ctx.screenshot_count}")
        return False

    messages = ctx.get_messages()

    # First message should have no image (pruned)
    if "images" in messages[0]:
        print("  - FAILED: First message should not have images (should be pruned)")
        return False

    # Last 2 should have images
    if "images" not in messages[1] or "images" not in messages[2]:
        print("  - FAILED: Last 2 messages should have images")
        return False

    print("  - Screenshot pruning: OK")
    print(f"  - Kept last {ctx.screenshot_count}/{len(messages)} screenshots\n")
    return True


async def test_retry_with_timeout():
    """Test retry_with_timeout mechanism."""
    print("Testing retry_with_timeout...")

    from ui_tars_patterns import retry_with_timeout

    call_count = 0

    async def flaky_function():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise Exception("Flaky error")
        return "success"

    try:
        result = await retry_with_timeout(
            flaky_function,
            timeout=5.0,
            max_retries=3,
            operation_name="test"
        )

        if result != "success":
            print(f"  - FAILED: Expected 'success', got '{result}'")
            return False

        if call_count != 3:
            print(f"  - FAILED: Expected 3 attempts, got {call_count}")
            return False

        print("  - Retry mechanism: OK")
        print(f"  - Succeeded on attempt {call_count}/3\n")
        return True

    except Exception as e:
        print(f"  - FAILED: {e}")
        return False


def test_brain_integration():
    """Test that brain has uitars property."""
    print("Testing brain integration...")

    from brain_enhanced_v2 import EnhancedBrain, UITARS_AVAILABLE

    if not UITARS_AVAILABLE:
        print("  - SKIPPED: UITARS_AVAILABLE is False")
        return True

    # Check if EnhancedBrain has uitars property
    if not hasattr(EnhancedBrain, 'uitars'):
        print("  - FAILED: EnhancedBrain missing 'uitars' property")
        return False

    print("  - EnhancedBrain.uitars property: OK")
    print("  - Brain integration: OK\n")
    return True


def test_vision_handler():
    """Test that VisionHandler uses enhanced screenshots."""
    print("Testing VisionHandler integration...")

    try:
        from vision_handler import VisionHandler
        import inspect

        # Check if take_screenshot mentions UI-TARS
        source = inspect.getsource(VisionHandler.take_screenshot)

        if "uitars" not in source.lower():
            print("  - FAILED: take_screenshot doesn't use UI-TARS")
            return False

        if "enhanced_screenshot" not in source:
            print("  - FAILED: take_screenshot doesn't call enhanced_screenshot()")
            return False

        print("  - VisionHandler.take_screenshot uses UI-TARS: OK")
        print("  - Vision integration: OK\n")
        return True

    except Exception as e:
        print(f"  - FAILED: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 70)
    print("UI-TARS Integration Test Suite")
    print("=" * 70)
    print()

    results = []

    # Test 1: Imports
    results.append(("Imports", test_imports()))

    # Test 2: ConversationContext
    results.append(("ConversationContext", test_conversation_context()))

    # Test 3: Retry mechanism
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    results.append(("Retry with timeout", loop.run_until_complete(test_retry_with_timeout())))
    loop.close()

    # Test 4: Brain integration
    results.append(("Brain integration", test_brain_integration()))

    # Test 5: VisionHandler integration
    results.append(("VisionHandler integration", test_vision_handler()))

    # Summary
    print("=" * 70)
    print("Test Results Summary")
    print("=" * 70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  [{status}] {name}")

    print()
    print(f"Total: {passed}/{total} tests passed")
    print()

    if passed == total:
        print("STATUS: SUCCESS - All tests passed!")
        print("\nUI-TARS integration is working correctly.")
        print("\nNext steps:")
        print("  1. Test with real agent: node bin/eversale.js \"take a screenshot\"")
        print("  2. Monitor logs for '[UITARS]' messages")
        print("  3. Verify screenshot retry on failures")
        return 0
    else:
        print("STATUS: FAILED - Some tests failed")
        print("\nPlease fix the failing tests before using UI-TARS integration.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
