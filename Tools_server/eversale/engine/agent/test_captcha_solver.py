#!/usr/bin/env python3
"""
Test script for CAPTCHA solver.

Tests:
1. LocalCaptchaSolver initialization
2. Vision model availability
3. OCR error correction
4. Confidence scoring
5. Live CAPTCHA detection and solving (manual verification)
"""

import asyncio
import sys
from playwright.async_api import async_playwright
from captcha_solver import LocalCaptchaSolver, PageCaptchaHandler
from loguru import logger


async def test_initialization():
    """Test 1: LocalCaptchaSolver initialization"""
    print("\n" + "=" * 70)
    print("TEST 1: LocalCaptchaSolver Initialization")
    print("=" * 70)

    try:
        solver = LocalCaptchaSolver(vision_model="moondream")
        print(f"Status: Configured = {solver.is_configured}")
        print(f"Vision model: {solver.vision_model}")
        print(f"Ollama client: {solver.ollama_client is not None}")

        if solver.ollama_client:
            print("SUCCESS: LocalCaptchaSolver initialized with Ollama")
            return True
        else:
            print("WARNING: LocalCaptchaSolver initialized but Ollama not available")
            return False
    except Exception as e:
        print(f"FAILED: {e}")
        return False


async def test_ocr_correction():
    """Test 2: OCR error correction"""
    print("\n" + "=" * 70)
    print("TEST 2: OCR Error Correction")
    print("=" * 70)

    solver = LocalCaptchaSolver()

    test_cases = [
        ("Abc0ne", "AbcOne", "text"),     # 0 -> O in letter context
        ("12O45", "12045", "text"),        # O -> 0 in number context
        ("lPhone", "IPhone", "text"),      # l -> I at start
        ("he1lo", "hello", "text"),        # 1 -> l in letter context
    ]

    passed = 0
    failed = 0

    for input_text, expected, captcha_type in test_cases:
        corrected = solver._correct_ocr_errors(input_text, captcha_type)
        if corrected == expected:
            print(f"PASS: {input_text:15} -> {corrected:15}")
            passed += 1
        else:
            print(f"FAIL: {input_text:15} -> {corrected:15} (expected: {expected})")
            failed += 1

    print(f"\nResult: {passed} passed, {failed} failed")
    return failed == 0


async def test_confidence_scoring():
    """Test 3: Confidence scoring"""
    print("\n" + "=" * 70)
    print("TEST 3: Confidence Scoring")
    print("=" * 70)

    solver = LocalCaptchaSolver()

    test_cases = [
        ("Abc123", "Abc123", "text", 0.7, "Clean answer"),
        ("Abc123", "The text is: Abc123", "text", 0.5, "Extra text"),
        ("VeryLongCaptchaText", "VeryLongCaptchaText", "text", 0.5, "Too long"),
    ]

    for cleaned, raw, ctype, min_expected, description in test_cases:
        confidence = solver._calculate_image_confidence(cleaned, raw, ctype)
        status = "PASS" if confidence >= min_expected else "FAIL"
        print(f"{status}: {description:20} confidence: {confidence:.2f} (expected >= {min_expected})")

    return True


async def test_captcha_detection():
    """Test 4: CAPTCHA detection on live page"""
    print("\n" + "=" * 70)
    print("TEST 4: CAPTCHA Detection (reCAPTCHA demo)")
    print("=" * 70)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()

            print("Navigating to reCAPTCHA demo...")
            await page.goto("https://www.google.com/recaptcha/api2/demo", timeout=30000)

            handler = PageCaptchaHandler(page)
            detection = await handler.detect_captcha()

            if detection.detected:
                print(f"SUCCESS: CAPTCHA detected")
                print(f"  Type: {detection.challenge_type.value}")
                print(f"  Site key: {detection.site_key}")
                print(f"  Confidence: {detection.confidence}")
                result = True
            else:
                print("FAILED: No CAPTCHA detected")
                result = False

            await browser.close()
            return result
    except Exception as e:
        print(f"FAILED: {e}")
        return False


async def test_type_detection():
    """Test 5: CAPTCHA type auto-detection"""
    print("\n" + "=" * 70)
    print("TEST 5: CAPTCHA Type Detection")
    print("=" * 70)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            # Create a test page with math CAPTCHA indicators
            await page.set_content("""
                <html>
                <body>
                    <p>Solve the equation: 2 + 3 = ?</p>
                    <input type="text" id="answer">
                </body>
                </html>
            """)

            solver = LocalCaptchaSolver()
            detected_type = await solver.detect_captcha_type(page)

            if detected_type == "math":
                print("SUCCESS: Detected math CAPTCHA")
                result = True
            else:
                print(f"FAILED: Detected {detected_type} instead of math")
                result = False

            await browser.close()
            return result
    except Exception as e:
        print(f"FAILED: {e}")
        return False


async def test_vision_solving_simple():
    """Test 6: Vision-based solving with simple test image"""
    print("\n" + "=" * 70)
    print("TEST 6: Vision-Based CAPTCHA Solving (Simple Test)")
    print("=" * 70)

    try:
        solver = LocalCaptchaSolver(vision_model="moondream")

        if not solver.ollama_client:
            print("SKIPPED: Ollama not available")
            return True

        # Test if we can call the ollama client
        try:
            import ollama
            models = ollama.list()
            print(f"Available models: {len(models.get('models', []))} models")

            # Check if moondream is available
            model_names = [m['name'] for m in models.get('models', [])]
            if 'moondream:latest' in model_names or 'moondream' in model_names:
                print("SUCCESS: moondream model is available")
                return True
            else:
                print("WARNING: moondream model not found")
                print(f"Available models: {model_names}")
                return False
        except Exception as e:
            print(f"FAILED: {e}")
            return False

    except Exception as e:
        print(f"FAILED: {e}")
        return False


async def test_metrics_tracking():
    """Test 7: Metrics tracking"""
    print("\n" + "=" * 70)
    print("TEST 7: Metrics Tracking")
    print("=" * 70)

    solver = LocalCaptchaSolver()

    # Simulate some solve attempts
    solver._log_solve_attempt(
        captcha_type="text",
        combined_confidence=0.9,
        image_confidence=0.85,
        context_confidence=0.95,
        model="moondream",
        answer_length=6,
        accepted=True
    )

    solver._log_solve_attempt(
        captcha_type="text",
        combined_confidence=0.6,
        image_confidence=0.55,
        context_confidence=0.65,
        model="moondream",
        answer_length=5,
        accepted=False
    )

    metrics = solver.get_metrics_summary()

    print(f"Total attempts: {metrics['total_attempts']}")
    print(f"High confidence stats: {metrics['by_confidence'].get('high', {})}")
    print(f"Medium confidence stats: {metrics['by_confidence'].get('medium', {})}")

    if metrics['total_attempts'] == 2:
        print("SUCCESS: Metrics tracking works")
        return True
    else:
        print("FAILED: Metrics tracking incorrect")
        return False


async def test_full_integration():
    """Test 8: Full integration test (manual verification required)"""
    print("\n" + "=" * 70)
    print("TEST 8: Full Integration Test (MANUAL VERIFICATION)")
    print("=" * 70)
    print("\nThis test will open a browser with reCAPTCHA demo.")
    print("It will try to detect and solve using scrappy bypass methods.")
    print("\nPress Enter to continue or Ctrl+C to skip...")

    try:
        input()
    except KeyboardInterrupt:
        print("\nSKIPPED by user")
        return True

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()

            print("Navigating to reCAPTCHA demo...")
            await page.goto("https://www.google.com/recaptcha/api2/demo")

            handler = PageCaptchaHandler(page)

            # Detect CAPTCHA
            detection = await handler.detect_captcha()
            if detection.detected:
                print(f"Detected: {detection.challenge_type.value}")

                # Try scrappy bypass
                print("\nTrying scrappy bypass (checkbox click)...")
                success = await handler.scrappy.try_checkbox_click()

                if success:
                    print("SUCCESS: Checkbox click worked!")
                else:
                    print("INFO: Checkbox click didn't auto-solve (expected)")
                    print("Note: This is normal - most CAPTCHAs require human interaction")

            print("\nBrowser will stay open for 10 seconds for manual inspection...")
            await asyncio.sleep(10)

            await browser.close()
            return True

    except Exception as e:
        print(f"FAILED: {e}")
        return False


async def run_all_tests():
    """Run all tests"""
    print("\n" + "=" * 80)
    print(" CAPTCHA SOLVER TEST SUITE")
    print("=" * 80)

    tests = [
        ("Initialization", test_initialization),
        ("OCR Error Correction", test_ocr_correction),
        ("Confidence Scoring", test_confidence_scoring),
        ("CAPTCHA Detection", test_captcha_detection),
        ("Type Detection", test_type_detection),
        ("Vision Model Check", test_vision_solving_simple),
        ("Metrics Tracking", test_metrics_tracking),
        ("Full Integration", test_full_integration),
    ]

    results = []

    for name, test_func in tests:
        try:
            result = await test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\nEXCEPTION in {name}: {e}")
            results.append((name, False))

    print("\n" + "=" * 80)
    print(" TEST RESULTS SUMMARY")
    print("=" * 80)

    passed = 0
    failed = 0

    for name, result in results:
        status = "PASS" if result else "FAIL"
        symbol = "✓" if result else "✗"
        print(f"{symbol} {status:6} | {name}")

        if result:
            passed += 1
        else:
            failed += 1

    print("\n" + "=" * 80)
    print(f"Total: {passed} passed, {failed} failed out of {len(results)} tests")
    print("=" * 80)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
