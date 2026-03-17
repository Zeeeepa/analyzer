"""
Quick verification that UI-TARS integration was applied correctly
"""

import sys


def verify_integration():
    """Verify UI-TARS is now integrated"""
    print("Verifying UI-TARS Integration...")
    print("=" * 70)

    errors = []
    warnings = []
    successes = []

    # Check 1: brain_enhanced_v2.py imports
    with open("brain_enhanced_v2.py", "r") as f:
        brain_content = f.read()

    if "from .ui_tars_integration import UITarsEnhancer" in brain_content:
        successes.append("brain_enhanced_v2.py imports UITarsEnhancer")
    else:
        errors.append("brain_enhanced_v2.py missing UITarsEnhancer import")

    if "from .ui_tars_patterns import RetryConfig, ConversationContext" in brain_content:
        successes.append("brain_enhanced_v2.py imports UI-TARS patterns")
    else:
        errors.append("brain_enhanced_v2.py missing UI-TARS patterns import")

    # Check 2: UITARS_AVAILABLE flag
    if "UITARS_AVAILABLE = True" in brain_content:
        successes.append("UITARS_AVAILABLE flag set")
    else:
        warnings.append("UITARS_AVAILABLE flag not found (may use try/except)")

    # Check 3: ConversationContext initialization
    if "_uitars_context = ConversationContext(max_screenshots=5)" in brain_content:
        successes.append("ConversationContext initialized with max 5 screenshots")
    else:
        errors.append("ConversationContext not initialized in __init__")

    # Check 4: UITarsEnhancer property
    if "def uitars(self):" in brain_content or "@property" in brain_content and "uitars" in brain_content:
        successes.append("uitars property added to EnhancedBrain")
    else:
        errors.append("uitars property missing from EnhancedBrain")

    # Check 5: RetryConfig in property
    if "RetryConfig(" in brain_content and "screenshot_timeout=5.0" in brain_content:
        successes.append("RetryConfig with 5s screenshot timeout")
    else:
        warnings.append("RetryConfig may not be configured correctly")

    # Check 6: vision_handler.py integration
    with open("vision_handler.py", "r") as f:
        vision_content = f.read()

    if "self.brain.uitars" in vision_content:
        successes.append("vision_handler.py uses brain.uitars")
    else:
        errors.append("vision_handler.py doesn't use brain.uitars")

    if "enhanced_screenshot()" in vision_content:
        successes.append("vision_handler.py calls enhanced_screenshot()")
    else:
        errors.append("vision_handler.py doesn't call enhanced_screenshot()")

    if "[UITARS]" in vision_content:
        successes.append("vision_handler.py has UI-TARS logging")
    else:
        warnings.append("vision_handler.py missing [UITARS] log markers")

    # Check 7: __init__.py exports
    with open("__init__.py", "r") as f:
        init_content = f.read()

    if "from .ui_tars_integration import UITarsEnhancer" in init_content:
        successes.append("__init__.py exports UITarsEnhancer")
    else:
        warnings.append("__init__.py doesn't export UI-TARS utilities")

    if "UITarsEnhancer" in init_content and "ConversationContext" in init_content:
        successes.append("__init__.py includes UI-TARS in __all__")
    else:
        warnings.append("__init__.py may not export all UI-TARS utilities")

    # Print results
    print("\nSUCCESSES:")
    for s in successes:
        print(f"  - {s}")

    if warnings:
        print("\nWARNINGS:")
        for w in warnings:
            print(f"  ! {w}")

    if errors:
        print("\nERRORS:")
        for e in errors:
            print(f"  X {e}")

    print("\n" + "=" * 70)

    if errors:
        print("STATUS: FAILED - Integration incomplete")
        print("\nPlease review errors above")
        return False
    elif warnings:
        print("STATUS: WARNING - Integration mostly complete")
        print("\nReview warnings, but integration should work")
        print("\nNext steps:")
        print("  1. Test: cd /mnt/c/ev29/cli && node bin/eversale.js \"take a screenshot\"")
        print("  2. Look for [UITARS] log messages")
        print("  3. Verify screenshot retry on failures")
        return True
    else:
        print("STATUS: SUCCESS - UI-TARS integration complete!")
        print("\nAll checks passed. UI-TARS patterns are now active.")
        print("\nExpected behavior:")
        print("  - Screenshots retry up to 3x on failure (5s timeout)")
        print("  - Screenshot context limited to last 5 (auto-prune)")
        print("  - Enhanced reliability for browser automation")
        print("\nTest with:")
        print("  cd /mnt/c/ev29/cli")
        print("  node bin/eversale.js \"take a screenshot and describe it\"")
        print("\nMonitor logs for:")
        print("  [UITARS] Screenshot context management enabled (max 5)")
        print("  [UITARS] Enhanced browser automation with tiered retry enabled")
        print("  [UITARS] Enhanced screenshot captured with 3x retry")
        return True


if __name__ == "__main__":
    success = verify_integration()
    sys.exit(0 if success else 1)
