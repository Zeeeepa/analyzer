"""
Test protection trigger patterns and executor integration.

Tests that natural language triggers correctly invoke:
- P1: CAPTCHA solver
- P2: Cloudflare handler
- P3: Stealth mode
"""

import asyncio
from intent_detector import detect_intent
from executors import ALL_EXECUTORS


def test_intent_detection():
    """Test that protection triggers are correctly detected."""
    test_cases = [
        # CAPTCHA (P1)
        ("handle captcha", "P1", "solve_captcha"),
        ("solve the captcha", "P1", "solve_captcha"),
        ("captcha detected", "P1", "solve_captcha"),
        ("bypass recaptcha", "P1", "solve_captcha"),

        # Cloudflare (P2)
        ("bypass cloudflare", "P2", "handle_cloudflare"),
        ("cloudflare is blocking", "P2", "handle_cloudflare"),
        ("handle cloudflare challenge", "P2", "handle_cloudflare"),
        ("site is blocked by cloudflare", "P2", "handle_cloudflare"),

        # Stealth (P3)
        ("use stealth mode", "P3", "enable_stealth"),
        ("enable anti-detection", "P3", "enable_stealth"),
        ("avoid bot detection", "P3", "enable_stealth"),
        ("turn on stealth", "P3", "enable_stealth"),
    ]

    print("Testing intent detection:")
    print("-" * 80)

    passed = 0
    failed = 0

    for prompt, expected_cap, expected_action in test_cases:
        intent = detect_intent(prompt)

        if intent.capability == expected_cap and intent.action == expected_action:
            status = "PASS"
            passed += 1
        else:
            status = "FAIL"
            failed += 1

        print(f"[{status}] {prompt:40} -> {intent.capability}/{intent.action} (expected {expected_cap}/{expected_action})")

    print("-" * 80)
    print(f"Results: {passed} passed, {failed} failed")
    return failed == 0


def test_executor_registration():
    """Test that protection executors are registered in ALL_EXECUTORS."""
    print("\nTesting executor registration:")
    print("-" * 80)

    expected = {
        "P1": "P1_CaptchaSolver",
        "P2": "P2_CloudflareHandler",
        "P3": "P3_StealthMode",
    }

    passed = 0
    failed = 0

    for cap_id, expected_name in expected.items():
        if cap_id in ALL_EXECUTORS:
            executor = ALL_EXECUTORS[cap_id]
            actual_name = executor.__name__

            if actual_name == expected_name:
                status = "PASS"
                passed += 1
                print(f"[{status}] {cap_id}: {actual_name} - {executor.action}")
            else:
                status = "FAIL"
                failed += 1
                print(f"[{status}] {cap_id}: {actual_name} (expected {expected_name})")
        else:
            status = "FAIL"
            failed += 1
            print(f"[{status}] {cap_id}: NOT REGISTERED")

    print("-" * 80)
    print(f"Results: {passed} passed, {failed} failed")
    return failed == 0


async def test_executor_instantiation():
    """Test that protection executors can be instantiated."""
    print("\nTesting executor instantiation:")
    print("-" * 80)

    passed = 0
    failed = 0

    for cap_id in ["P1", "P2", "P3"]:
        try:
            executor_class = ALL_EXECUTORS[cap_id]
            executor = executor_class(browser=None, context={})

            print(f"[PASS] {cap_id}: {executor_class.__name__} instantiated successfully")
            print(f"       capability={executor.capability}, action={executor.action}")
            passed += 1

        except Exception as e:
            print(f"[FAIL] {cap_id}: {e}")
            failed += 1

    print("-" * 80)
    print(f"Results: {passed} passed, {failed} failed")
    return failed == 0


async def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("PROTECTION TRIGGER PATTERN TESTS")
    print("=" * 80 + "\n")

    test1 = test_intent_detection()
    test2 = test_executor_registration()
    test3 = await test_executor_instantiation()

    print("\n" + "=" * 80)
    if test1 and test2 and test3:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
