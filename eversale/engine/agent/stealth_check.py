"""
Stealth Setup Checker
=====================

This module provides utilities to check and verify the stealth configuration,
including TLS fingerprinting availability and effectiveness.

Usage:
    python -m agent.stealth_check

Author: Claude
Date: 2025-12-02
"""

import sys
from typing import Dict, Any
from loguru import logger

def check_stealth_setup() -> Dict[str, Any]:
    """
    Check all stealth components and their availability.

    Returns:
        Dict with status of all stealth components
    """
    results = {
        "tls_fingerprinting": None,
        "stealth_utils": None,
        "captcha_solver": None,
        "overall_status": "checking"
    }

    # Check TLS fingerprinting
    print("\n" + "="*70)
    print("STEALTH SETUP CHECK")
    print("="*70 + "\n")

    print("1. TLS Fingerprinting (curl_cffi)")
    print("-" * 70)
    try:
        from .tls_fingerprint import check_tls_fingerprinting, HAS_CURL_CFFI

        if HAS_CURL_CFFI:
            print("✓ curl_cffi is installed")
            tls_result = check_tls_fingerprinting()
            results["tls_fingerprinting"] = tls_result

            if tls_result["test_passed"]:
                print(f"✓ TLS fingerprint test passed")
                if tls_result.get("fingerprint_data"):
                    ja3 = tls_result["fingerprint_data"].get("ja3_hash", "N/A")
                    print(f"  JA3 Hash: {ja3}")
                print(f"  Available impersonations: {len(tls_result['impersonations'])}")
            else:
                print(f"✗ TLS test failed: {tls_result['message']}")
        else:
            print("✗ curl_cffi not installed")
            print("  Install with: pip install curl_cffi")
            results["tls_fingerprinting"] = {"available": False, "message": "Not installed"}

    except Exception as e:
        print(f"✗ Error checking TLS fingerprinting: {e}")
        results["tls_fingerprinting"] = {"available": False, "error": str(e)}

    # Check stealth utils
    print("\n2. Stealth Utilities")
    print("-" * 70)
    try:
        from .stealth_utils import get_stealth_args, get_random_user_agent
        print("✓ Stealth utilities available")
        print(f"  Sample UA: {get_random_user_agent()[:50]}...")
        results["stealth_utils"] = {"available": True}
    except ImportError:
        print("✗ Stealth utilities not available")
        results["stealth_utils"] = {"available": False}
    except Exception as e:
        print(f"✗ Error checking stealth utilities: {e}")
        results["stealth_utils"] = {"available": False, "error": str(e)}

    # Check CAPTCHA solver
    print("\n3. CAPTCHA Solver")
    print("-" * 70)
    try:
        from .captcha_solver import PageCaptchaHandler
        print("✓ CAPTCHA solver available")
        results["captcha_solver"] = {"available": True}
    except ImportError:
        print("✗ CAPTCHA solver not available")
        results["captcha_solver"] = {"available": False}
    except Exception as e:
        print(f"✗ Error checking CAPTCHA solver: {e}")
        results["captcha_solver"] = {"available": False, "error": str(e)}

    # Overall status
    print("\n" + "="*70)
    print("OVERALL STATUS")
    print("="*70)

    tls_ok = results.get("tls_fingerprinting", {}).get("available", False)
    stealth_ok = results.get("stealth_utils", {}).get("available", False)
    captcha_ok = results.get("captcha_solver", {}).get("available", False)

    total_components = 3
    working_components = sum([tls_ok, stealth_ok, captcha_ok])

    if working_components == total_components:
        results["overall_status"] = "excellent"
        print(f"✓ All {total_components} stealth components working (10/10 stealth)")
    elif working_components >= 2:
        results["overall_status"] = "good"
        print(f"✓ {working_components}/{total_components} stealth components working (good stealth)")
    elif working_components >= 1:
        results["overall_status"] = "partial"
        print(f"⚠ {working_components}/{total_components} stealth components working (partial stealth)")
    else:
        results["overall_status"] = "minimal"
        print(f"✗ No stealth components working (minimal stealth)")

    # Recommendations
    if not tls_ok:
        print("\nRECOMMENDATION: Install curl_cffi for TLS fingerprinting:")
        print("  pip install curl_cffi")

    print("\n" + "="*70 + "\n")

    return results


def test_tls_comparison():
    """
    Compare TLS fingerprints between curl_cffi and standard requests.

    This helps verify that TLS fingerprinting is actually working.
    """
    print("\n" + "="*70)
    print("TLS FINGERPRINT COMPARISON TEST")
    print("="*70 + "\n")

    try:
        from .tls_fingerprint import test_ja3_fingerprint, HAS_CURL_CFFI

        if not HAS_CURL_CFFI:
            print("✗ curl_cffi not available - cannot run comparison test")
            return

        print("Testing TLS fingerprints against browserleaks.com...")
        print("(This may take a few seconds)\n")

        result = test_ja3_fingerprint()

        if "error" in result:
            print(f"✗ Test failed: {result['error']}")
            return

        print("Chrome TLS Fingerprint (curl_cffi):")
        if result.get("chrome_fingerprint"):
            print(f"  JA3 Hash: {result.get('ja3_hash_chrome', 'N/A')}")
            fp = result["chrome_fingerprint"]
            print(f"  TLS Version: {fp.get('tls_version', 'N/A')}")
            print(f"  User Agent: {fp.get('user_agent', 'N/A')[:60]}...")
        else:
            print("  ✗ Could not retrieve Chrome fingerprint")

        print("\nStandard Requests Fingerprint (Playwright-like):")
        if result.get("standard_fingerprint"):
            print(f"  JA3 Hash: {result.get('ja3_hash_standard', 'N/A')}")
            fp = result["standard_fingerprint"]
            print(f"  TLS Version: {fp.get('tls_version', 'N/A')}")
            print(f"  User Agent: {fp.get('user_agent', 'N/A')[:60]}...")
        else:
            print("  ✗ Could not retrieve standard fingerprint")

        print("\nComparison:")
        if result.get("match") is False:
            print("✓ TLS fingerprints differ (GOOD - curl_cffi is working!)")
            print("  Anti-bot systems will see different signatures")
        elif result.get("match") is True:
            print("✗ TLS fingerprints match (BAD - curl_cffi may not be working)")
            print("  You may need to reinstall curl_cffi")
        else:
            print("⚠ Could not compare fingerprints")

    except Exception as e:
        print(f"✗ Error during comparison test: {e}")

    print("\n" + "="*70 + "\n")


def main():
    """Run all stealth checks."""
    # Basic setup check
    results = check_stealth_setup()

    # If TLS is available, run comparison test
    if results.get("tls_fingerprinting", {}).get("available"):
        test_tls_comparison()

    # Exit with appropriate code
    if results["overall_status"] in ["excellent", "good"]:
        sys.exit(0)
    elif results["overall_status"] == "partial":
        sys.exit(1)
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()
