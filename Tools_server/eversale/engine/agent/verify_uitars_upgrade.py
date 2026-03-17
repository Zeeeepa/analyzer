"""
Quick verification that UI-TARS upgrade was applied correctly
"""

import sys


def verify_upgrade():
    """Verify UI-TARS is now the default"""
    print("Verifying UI-TARS CAPTCHA Upgrade...")
    print("=" * 70)

    # Read the file
    with open("captcha_solver.py", "r") as f:
        content = f.read()

    errors = []
    warnings = []
    successes = []

    # Check 1: text_model default
    if 'text_model: str = "0000/ui-tars-1.5-7b:latest"' in content:
        successes.append("✓ text_model default is UI-TARS")
    elif 'text_model: str = "qwen3:8b"' in content:
        errors.append("✗ text_model still defaults to qwen3:8b (should be UI-TARS)")
    else:
        warnings.append("⚠ Could not find text_model parameter")

    # Check 2: model_chain order
    if 'model_chain = ["0000/ui-tars-1.5-7b:latest", "moondream:latest", "moondream"]' in content:
        successes.append("✓ model_chain tries UI-TARS first")
    elif 'model_chain = ["moondream:latest", "moondream", "0000/ui-tars-1.5-7b:latest"]' in content:
        errors.append("✗ model_chain still tries moondream first (should be UI-TARS)")
    else:
        warnings.append("⚠ Could not find model_chain definition")

    # Check 3: Amazon CAPTCHA default
    if 'vision_model: str = "0000/ui-tars-1.5-7b:latest"' in content:
        successes.append("✓ Amazon CAPTCHA uses UI-TARS by default")
    elif 'vision_model: str = "moondream"' in content:
        errors.append("✗ Amazon CAPTCHA still uses moondream (should be UI-TARS)")
    else:
        warnings.append("⚠ Could not find vision_model parameter in solve_amazon_captcha")

    # Check 4: __init__ default (should already be UI-TARS)
    if 'def __init__(self, vision_model: str = "0000/ui-tars-1.5-7b:latest")' in content:
        successes.append("✓ LocalCaptchaSolver __init__ uses UI-TARS")
    else:
        warnings.append("⚠ LocalCaptchaSolver __init__ may not default to UI-TARS")

    # Print results
    print("\nSUCCESSES:")
    for s in successes:
        print(f"  {s}")

    if warnings:
        print("\nWARNINGS:")
        for w in warnings:
            print(f"  {w}")

    if errors:
        print("\nERRORS:")
        for e in errors:
            print(f"  {e}")

    print("\n" + "=" * 70)

    if errors:
        print("STATUS: FAILED - Upgrade not complete")
        print("\nTo fix, run:")
        print("  cd /mnt/c/ev29/cli/engine/agent")
        print("  cp captcha_solver.py.backup captcha_solver.py")
        print("  # Then manually apply changes from UI_TARS_CAPTCHA_UPGRADE.patch")
        return False
    elif warnings:
        print("STATUS: WARNING - Some checks could not be verified")
        print("Please review warnings above")
        return True
    else:
        print("STATUS: SUCCESS - UI-TARS upgrade complete!")
        print("\nNext steps:")
        print("  1. Test with: python3 test_ui_tars_captcha.py")
        print("  2. Monitor production metrics: tail -f ~/.eversale/captcha_metrics.jsonl")
        print("  3. Compare UI-TARS vs qwen3:8b performance over 1 week")
        return True


if __name__ == "__main__":
    success = verify_upgrade()
    sys.exit(0 if success else 1)
