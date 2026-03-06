#!/usr/bin/env python3
"""
Comparison test: UI-TARS vs Moondream for CAPTCHA solving
Tests both models side-by-side to verify UI-TARS integration and performance
"""

import asyncio
from playwright.async_api import async_playwright
import base64
from loguru import logger
import time


async def test_both_models():
    """Test UI-TARS and moondream on the same test image"""
    print("\n" + "=" * 80)
    print("COMPARISON TEST: UI-TARS vs Moondream for CAPTCHA Recognition")
    print("=" * 80)

    try:
        import ollama

        # Check available models
        models = ollama.list()
        model_names = [m.get('model', m.get('name', 'unknown')) for m in models.get('models', [])]
        print(f"\nAvailable models: {model_names}\n")

        # Check both models are available
        has_uitars = any('UI-TARS' in name or 'ui-tars' in name.lower() for name in model_names)
        has_moondream = any('moondream' in name.lower() for name in model_names)

        if not has_uitars:
            print("ERROR: UI-TARS not found. Install with: ollama pull 0000/ui-tars-1.5-7b:latest")
            return False

        if not has_moondream:
            print("ERROR: moondream not found. Install with: ollama pull moondream")
            return False

        print("Both models are available. Creating test image...\n")

        # Create a test page with CAPTCHA-like text
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            # Create a test CAPTCHA-like image with distorted text
            await page.set_content("""
                <html>
                <head>
                    <style>
                        @keyframes distort {
                            0%, 100% { transform: skewX(0deg); }
                            50% { transform: skewX(-5deg); }
                        }
                        #captcha {
                            font-size: 48px;
                            font-weight: bold;
                            font-family: 'Courier New', monospace;
                            color: #333;
                            background: linear-gradient(135deg, #f0f0f0 0%, #e0e0e0 100%);
                            padding: 20px 40px;
                            letter-spacing: 8px;
                            border: 2px solid #999;
                            border-radius: 5px;
                            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
                            transform: skewX(-3deg) rotate(-2deg);
                            display: inline-block;
                        }
                        body {
                            padding: 50px;
                            background: white;
                        }
                    </style>
                </head>
                <body>
                    <div id="captcha">Abc7X2</div>
                </body>
                </html>
            """)

            await asyncio.sleep(1)  # Wait for render

            # Get screenshot
            element = await page.query_selector('#captcha')
            if not element:
                print("ERROR: Could not find test element")
                await browser.close()
                return False

            screenshot_bytes = await element.screenshot()
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')

            expected_text = "Abc7X2"
            prompt = """Look at this CAPTCHA image carefully.
Read the distorted text exactly as shown, character by character.
The text may be warped, overlapping, or have lines through it.
Respond ONLY with the exact characters visible - no explanations or extra text."""

            results = {}

            # Test 1: UI-TARS
            print("Testing UI-TARS...")
            print("-" * 80)
            start_time = time.time()
            try:
                response = ollama.generate(
                    model='0000/ui-tars-1.5-7b:latest',
                    prompt=prompt,
                    images=[screenshot_b64],
                    options={'temperature': 0.1, 'num_predict': 50}
                )
                uitars_time = time.time() - start_time
                uitars_answer = response.get('response', '').strip()

                # Clean answer
                uitars_clean = uitars_answer.replace('"', '').replace("'", '').strip()
                uitars_clean = uitars_clean.split('\n')[0]

                print(f"Raw response: '{uitars_answer}'")
                print(f"Cleaned answer: '{uitars_clean}'")
                print(f"Time taken: {uitars_time:.2f}s")

                # Check accuracy
                uitars_correct = uitars_clean.upper() == expected_text.upper()
                uitars_partial = expected_text.upper() in uitars_clean.upper()

                results['UI-TARS'] = {
                    'answer': uitars_clean,
                    'correct': uitars_correct,
                    'partial': uitars_partial,
                    'time': uitars_time
                }

                if uitars_correct:
                    print("Result: CORRECT")
                elif uitars_partial:
                    print("Result: PARTIAL (contains expected text)")
                else:
                    print("Result: INCORRECT")

            except Exception as e:
                print(f"ERROR: {e}")
                results['UI-TARS'] = {'error': str(e)}

            print()

            # Test 2: moondream
            print("Testing moondream...")
            print("-" * 80)
            start_time = time.time()
            try:
                response = ollama.generate(
                    model='moondream:latest',
                    prompt=prompt,
                    images=[screenshot_b64],
                    options={'temperature': 0.1, 'num_predict': 50}
                )
                moondream_time = time.time() - start_time
                moondream_answer = response.get('response', '').strip()

                # Clean answer
                moondream_clean = moondream_answer.replace('"', '').replace("'", '').strip()
                moondream_clean = moondream_clean.split('\n')[0]

                print(f"Raw response: '{moondream_answer}'")
                print(f"Cleaned answer: '{moondream_clean}'")
                print(f"Time taken: {moondream_time:.2f}s")

                # Check accuracy
                moondream_correct = moondream_clean.upper() == expected_text.upper()
                moondream_partial = expected_text.upper() in moondream_clean.upper()

                results['moondream'] = {
                    'answer': moondream_clean,
                    'correct': moondream_correct,
                    'partial': moondream_partial,
                    'time': moondream_time
                }

                if moondream_correct:
                    print("Result: CORRECT")
                elif moondream_partial:
                    print("Result: PARTIAL (contains expected text)")
                else:
                    print("Result: INCORRECT")

            except Exception as e:
                print(f"ERROR: {e}")
                results['moondream'] = {'error': str(e)}

            await browser.close()

            # Print comparison summary
            print("\n" + "=" * 80)
            print("COMPARISON SUMMARY")
            print("=" * 80)
            print(f"Expected text: {expected_text}")
            print()

            for model, result in results.items():
                if 'error' in result:
                    print(f"{model:15} | ERROR: {result['error']}")
                else:
                    accuracy = "CORRECT" if result['correct'] else ("PARTIAL" if result['partial'] else "INCORRECT")
                    print(f"{model:15} | Answer: '{result['answer']:10}' | {accuracy:10} | Time: {result['time']:.2f}s")

            print("=" * 80)

            # Determine winner
            uitars_result = results.get('UI-TARS', {})
            moondream_result = results.get('moondream', {})

            if 'error' not in uitars_result and 'error' not in moondream_result:
                if uitars_result['correct'] and not moondream_result['correct']:
                    print("\nWINNER: UI-TARS (more accurate)")
                elif moondream_result['correct'] and not uitars_result['correct']:
                    print("\nWINNER: moondream (more accurate)")
                elif uitars_result['correct'] and moondream_result['correct']:
                    if uitars_result['time'] < moondream_result['time']:
                        print("\nTIE on accuracy, UI-TARS is faster")
                    else:
                        print("\nTIE on accuracy, moondream is faster")
                else:
                    print("\nBoth models struggled with this CAPTCHA")

            return True

    except ImportError:
        print("ERROR: Ollama Python package not installed")
        return False
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run the comparison test"""
    success = await test_both_models()

    if success:
        print("\nComparison test completed successfully!")
        print("\nConfiguration in captcha_solver.py:")
        print("- Default model: 0000/ui-tars-1.5-7b:latest")
        print("- Fallback chain: ['0000/ui-tars-1.5-7b:latest', 'moondream:latest', 'moondream']")
        print("\nUI-TARS is now the primary vision model for CAPTCHA solving.")

    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
