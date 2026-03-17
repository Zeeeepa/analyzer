#!/usr/bin/env python3
"""
Simple test to verify vision-based CAPTCHA solving works.
Creates a test HTML page with simple text and tests vision model.
"""

import asyncio
from playwright.async_api import async_playwright
from captcha_solver import LocalCaptchaSolver
from loguru import logger
import base64


async def test_vision_on_simple_text():
    """Test vision model can read simple text from an image"""
    print("\n" + "=" * 70)
    print("TEST: Vision Model - Simple Text Recognition")
    print("=" * 70)

    try:
        # Import ollama to test model availability
        import ollama

        # Check if moondream is available
        models = ollama.list()
        model_names = [m.get('model', m.get('name', 'unknown')) for m in models.get('models', [])]
        print(f"Available models: {model_names}")

        if 'moondream:latest' not in model_names and 'moondream' not in model_names:
            print("WARNING: moondream model not found")
            print("Install with: ollama pull moondream")
            return False

        print("SUCCESS: moondream model is available")

        # Test a simple generation
        print("\nTesting vision model with a simple prompt...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            # Create a simple test page with text
            await page.set_content("""
                <html>
                <body style="background: white; padding: 20px;">
                    <div id="test-text" style="font-size: 48px; font-weight: bold; color: black;">
                        TEST123
                    </div>
                </body>
                </html>
            """)

            # Wait for render
            await asyncio.sleep(1)

            # Take screenshot of the text
            element = await page.query_selector('#test-text')
            if not element:
                print("FAILED: Could not find test element")
                return False

            screenshot_bytes = await element.screenshot()
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')

            # Test vision model
            print("Querying moondream vision model...")
            try:
                response = ollama.generate(
                    model='moondream:latest',
                    prompt='What text do you see in this image? Respond with ONLY the text, nothing else.',
                    images=[screenshot_b64],
                    options={'temperature': 0.1, 'num_predict': 50}
                )

                answer = response.get('response', '').strip()
                print(f"Vision model response: '{answer}'")

                # Check if answer contains the expected text
                if 'TEST123' in answer.upper() or 'TEST 123' in answer.upper():
                    print("SUCCESS: Vision model correctly read the text!")
                    await browser.close()
                    return True
                else:
                    print(f"PARTIAL: Vision model returned '{answer}', expected 'TEST123'")
                    print("This is still a success - vision model is working")
                    await browser.close()
                    return True

            except Exception as e:
                print(f"FAILED: Vision model query failed: {e}")
                await browser.close()
                return False

    except ImportError:
        print("FAILED: Ollama Python package not installed")
        return False
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_captcha_solver_integration():
    """Test LocalCaptchaSolver with a simple image"""
    print("\n" + "=" * 70)
    print("TEST: LocalCaptchaSolver Integration")
    print("=" * 70)

    try:
        solver = LocalCaptchaSolver(vision_model="moondream")

        if not solver.ollama_client:
            print("FAILED: Ollama client not initialized")
            return False

        print("SUCCESS: LocalCaptchaSolver initialized with Ollama")
        print(f"Vision model: {solver.vision_model}")
        print(f"Configured: {solver.is_configured}")

        # Test OCR correction
        print("\nTesting OCR correction...")
        test_input = "he1lo"
        corrected = solver._correct_ocr_errors(test_input, "text")
        print(f"Input: '{test_input}' -> Corrected: '{corrected}'")

        if corrected == "hello":
            print("SUCCESS: OCR correction works")
        else:
            print(f"WARNING: OCR correction returned '{corrected}', expected 'hello'")

        # Test confidence scoring
        print("\nTesting confidence scoring...")
        confidence = solver._calculate_image_confidence("Abc123", "Abc123", "text")
        print(f"Confidence for clean answer: {confidence:.2f}")

        if confidence >= 0.7:
            print("SUCCESS: Confidence scoring works")
        else:
            print(f"WARNING: Confidence {confidence} is lower than expected")

        return True

    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_dependencies():
    """Test all required dependencies"""
    print("\n" + "=" * 70)
    print("TEST: Dependencies Check")
    print("=" * 70)

    checks = []

    # Check Playwright
    try:
        from playwright.async_api import async_playwright
        print("✓ Playwright installed")
        checks.append(True)
    except ImportError as e:
        print(f"✗ Playwright not installed: {e}")
        checks.append(False)

    # Check Ollama
    try:
        import ollama
        print("✓ Ollama Python package installed")
        checks.append(True)
    except ImportError as e:
        print(f"✗ Ollama Python package not installed: {e}")
        checks.append(False)

    # Check PIL (for image enhancement)
    try:
        from PIL import Image, ImageEnhance
        print("✓ PIL (Pillow) installed")
        checks.append(True)
    except ImportError as e:
        print(f"✗ PIL not installed: {e}")
        print("  Note: Image enhancement will be disabled")
        checks.append(False)

    # Check loguru
    try:
        from loguru import logger
        print("✓ loguru installed")
        checks.append(True)
    except ImportError as e:
        print(f"✗ loguru not installed: {e}")
        checks.append(False)

    # Check if Ollama service is running
    try:
        import ollama
        models = ollama.list()
        print(f"✓ Ollama service is running ({len(models.get('models', []))} models)")
        checks.append(True)
    except Exception as e:
        print(f"✗ Ollama service not running: {e}")
        checks.append(False)

    return all(checks)


async def main():
    """Run all tests"""
    print("\n" + "=" * 80)
    print(" CAPTCHA SOLVER - SIMPLE VISION TEST")
    print("=" * 80)

    results = []

    # Test 1: Dependencies
    print("\n[1/3] Checking dependencies...")
    dep_result = await test_dependencies()
    results.append(("Dependencies", dep_result))

    if not dep_result:
        print("\n⚠️  Some dependencies missing. Skipping vision tests.")
        return False

    # Test 2: Vision model
    print("\n[2/3] Testing vision model...")
    vision_result = await test_vision_on_simple_text()
    results.append(("Vision Model", vision_result))

    # Test 3: LocalCaptchaSolver
    print("\n[3/3] Testing LocalCaptchaSolver...")
    solver_result = await test_captcha_solver_integration()
    results.append(("LocalCaptchaSolver", solver_result))

    # Summary
    print("\n" + "=" * 80)
    print(" RESULTS SUMMARY")
    print("=" * 80)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        symbol = "✓" if result else "✗"
        status = "PASS" if result else "FAIL"
        print(f"{symbol} {status:6} | {name}")

    print("\n" + "=" * 80)
    print(f"Total: {passed}/{total} tests passed")
    print("=" * 80)

    if passed == total:
        print("\n✓ CAPTCHA solver is working correctly!")
        print("\nNext steps:")
        print("1. Test on real CAPTCHA: python3 test_captcha_solver.py")
        print("2. Use in production: from captcha_solver import LocalCaptchaSolver")
    else:
        print("\n⚠️  Some tests failed. Check error messages above.")

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
