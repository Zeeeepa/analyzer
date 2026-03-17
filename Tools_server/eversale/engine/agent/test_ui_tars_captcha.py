"""
Test UI-TARS as replacement for both moondream (vision) and qwen3:8b (text validation)

This script tests:
1. UI-TARS for CAPTCHA image reading (replacing moondream)
2. UI-TARS for answer validation (replacing qwen3:8b)
3. Performance comparison
"""

import asyncio
import base64
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional
import sys

try:
    import ollama
    HAS_OLLAMA = True
except ImportError:
    print("ERROR: ollama not installed. Run: pip install ollama")
    HAS_OLLAMA = False
    sys.exit(1)


class UITarsEvaluator:
    """Evaluate UI-TARS for CAPTCHA solving"""

    def __init__(self):
        self.ollama_client = ollama
        self.results = {
            "vision_tests": [],
            "validation_tests": [],
            "performance": {}
        }

    async def test_vision_capability(self, test_cases: list) -> Dict[str, Any]:
        """
        Test UI-TARS for CAPTCHA vision (replacing moondream)

        Tests:
        - Text CAPTCHA reading
        - Math CAPTCHA solving
        - OCR accuracy
        """
        print("\n" + "="*70)
        print("VISION CAPABILITY TEST - UI-TARS vs moondream")
        print("="*70)

        vision_results = []

        for test_case in test_cases:
            test_name = test_case["name"]
            captcha_type = test_case["type"]
            expected_answer = test_case.get("expected_answer")

            print(f"\n[TEST] {test_name} ({captcha_type})")

            # Simulate CAPTCHA image (in real test, use actual screenshot)
            test_prompt = self._get_captcha_prompt(captcha_type, test_case.get("description"))

            # Test UI-TARS
            uitars_start = time.time()
            uitars_result = await self._test_model_vision(
                model="0000/ui-tars-1.5-7b:latest",
                prompt=test_prompt,
                test_case=test_case
            )
            uitars_time = time.time() - uitars_start

            # Test moondream for comparison
            moondream_start = time.time()
            moondream_result = await self._test_model_vision(
                model="moondream:latest",
                prompt=test_prompt,
                test_case=test_case
            )
            moondream_time = time.time() - moondream_start

            # Compare results
            result = {
                "test": test_name,
                "type": captcha_type,
                "expected": expected_answer,
                "ui_tars": {
                    "answer": uitars_result,
                    "time": round(uitars_time, 2),
                    "correct": uitars_result == expected_answer if expected_answer else None
                },
                "moondream": {
                    "answer": moondream_result,
                    "time": round(moondream_time, 2),
                    "correct": moondream_result == expected_answer if expected_answer else None
                }
            }

            vision_results.append(result)

            # Print comparison
            print(f"  UI-TARS:   {uitars_result} ({uitars_time:.2f}s)")
            print(f"  moondream: {moondream_result} ({moondream_time:.2f}s)")
            if expected_answer:
                print(f"  Expected:  {expected_answer}")
                print(f"  Winner:    {'UI-TARS' if uitars_result == expected_answer else 'moondream' if moondream_result == expected_answer else 'Neither'}")

        return vision_results

    async def test_validation_capability(self, test_cases: list) -> Dict[str, Any]:
        """
        Test UI-TARS for answer validation (replacing qwen3:8b)

        Tests:
        - Context-based validation
        - Format checking
        - Plausibility assessment
        """
        print("\n" + "="*70)
        print("VALIDATION CAPABILITY TEST - UI-TARS vs qwen3:8b")
        print("="*70)

        validation_results = []

        for test_case in test_cases:
            test_name = test_case["name"]
            answer = test_case["answer"]
            captcha_type = test_case["type"]
            image_desc = test_case.get("image_desc", "unclear image")
            raw_answer = test_case.get("raw_answer", answer)
            expected_valid = test_case.get("expected_valid")

            print(f"\n[TEST] {test_name}")
            print(f"  Answer: {answer}")
            print(f"  Type: {captcha_type}")

            validation_prompt = self._create_validation_prompt(
                answer, captcha_type, image_desc, raw_answer
            )

            # Test UI-TARS
            uitars_start = time.time()
            uitars_result = await self._test_model_validation(
                model="0000/ui-tars-1.5-7b:latest",
                prompt=validation_prompt
            )
            uitars_time = time.time() - uitars_start

            # Test qwen3:8b for comparison
            qwen_start = time.time()
            qwen_result = await self._test_model_validation(
                model="qwen3:8b",
                prompt=validation_prompt
            )
            qwen_time = time.time() - qwen_start

            # Compare results
            result = {
                "test": test_name,
                "answer": answer,
                "expected_valid": expected_valid,
                "ui_tars": {
                    "valid": uitars_result.get("valid"),
                    "confidence": uitars_result.get("confidence"),
                    "reason": uitars_result.get("reason"),
                    "time": round(uitars_time, 2),
                    "correct": uitars_result.get("valid") == expected_valid if expected_valid is not None else None
                },
                "qwen3": {
                    "valid": qwen_result.get("valid"),
                    "confidence": qwen_result.get("confidence"),
                    "reason": qwen_result.get("reason"),
                    "time": round(qwen_time, 2),
                    "correct": qwen_result.get("valid") == expected_valid if expected_valid is not None else None
                }
            }

            validation_results.append(result)

            # Print comparison
            print(f"  UI-TARS:   valid={uitars_result.get('valid')}, conf={uitars_result.get('confidence'):.2f} ({uitars_time:.2f}s)")
            print(f"             {uitars_result.get('reason')}")
            print(f"  qwen3:8b:  valid={qwen_result.get('valid')}, conf={qwen_result.get('confidence'):.2f} ({qwen_time:.2f}s)")
            print(f"             {qwen_result.get('reason')}")
            if expected_valid is not None:
                print(f"  Expected:  {expected_valid}")
                print(f"  Winner:    {'UI-TARS' if uitars_result.get('valid') == expected_valid else 'qwen3:8b' if qwen_result.get('valid') == expected_valid else 'Neither'}")

        return validation_results

    def _get_captcha_prompt(self, captcha_type: str, description: str = "") -> str:
        """Get type-specific prompt for vision test"""
        if captcha_type == "text":
            return f"""Look at this CAPTCHA image carefully.
Read the distorted text exactly as shown, character by character.
The text may be warped, overlapping, or have lines through it.
Respond ONLY with the exact characters visible - no explanations or extra text.
{description}
Example: If you see "Abc123", respond with: Abc123"""

        elif captcha_type == "math":
            return f"""Look at this CAPTCHA image carefully.
You will see a math problem like "2 + 3 = ?" or "5 × 4 = ?".
Solve the math problem and respond ONLY with the number answer.
Do not include the equation, equals sign, or any explanation.
{description}
Example: If you see "2 + 3 = ?", respond with: 5"""

        else:
            return f"""Analyze this CAPTCHA image and extract the required information.
{description}
Respond with ONLY the answer, no explanations."""

    def _create_validation_prompt(self, answer: str, captcha_type: str,
                                   image_desc: str, raw_answer: str) -> str:
        """Create validation prompt"""
        return f"""Analyze this CAPTCHA solving attempt:

CAPTCHA Type: {captcha_type}
Vision Model Answer: {answer}
Image Description: {image_desc}
Raw Output: {raw_answer}

Questions to answer:
1. Does the answer format match the expected CAPTCHA type?
2. Is the answer plausible (not gibberish or random characters)?
3. Any red flags suggesting wrong answer (e.g., too long, contains error messages)?

Consider:
- Text CAPTCHAs are typically 3-10 alphanumeric characters
- Math CAPTCHAs should be a number
- Image selection should be grid positions (e.g., "1,4,7")

Return ONLY a JSON object with this exact format:
{{"valid": true/false, "confidence": 0.0-1.0, "reason": "brief explanation"}}"""

    async def _test_model_vision(self, model: str, prompt: str,
                                  test_case: Dict[str, Any]) -> str:
        """Test a model's vision capability"""
        try:
            # For this test, we'll use a text-only simulation
            # In real scenario, this would use an actual CAPTCHA image

            # Simulate with text description
            full_prompt = prompt + f"\n\nCAPTCHA shows: {test_case.get('description', 'text')}"

            response = self.ollama_client.generate(
                model=model,
                prompt=full_prompt,
                options={'temperature': 0.1, 'num_predict': 50}
            )

            answer = response.get('response', '').strip()

            # Clean answer
            cleaned = self._clean_answer(answer, test_case["type"])

            return cleaned or answer

        except Exception as e:
            return f"ERROR: {e}"

    async def _test_model_validation(self, model: str, prompt: str) -> Dict[str, Any]:
        """Test a model's validation capability"""
        try:
            response = self.ollama_client.generate(
                model=model,
                prompt=prompt,
                options={'temperature': 0.1, 'num_predict': 150}
            )

            response_text = response.get('response', '').strip()

            # Parse JSON response
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(0))
                return {
                    "valid": result.get("valid", False),
                    "confidence": float(result.get("confidence", 0.0)),
                    "reason": result.get("reason", "No reason provided")
                }
            else:
                # Fallback: check for positive/negative keywords
                positive_keywords = ["valid", "plausible", "correct", "matches", "reasonable"]
                negative_keywords = ["invalid", "implausible", "wrong", "gibberish", "error"]

                text_lower = response_text.lower()

                has_positive = any(kw in text_lower for kw in positive_keywords)
                has_negative = any(kw in text_lower for kw in negative_keywords)

                if has_positive and not has_negative:
                    return {"valid": True, "confidence": 0.7, "reason": "Text analysis suggests valid"}
                elif has_negative:
                    return {"valid": False, "confidence": 0.3, "reason": "Text analysis suggests invalid"}
                else:
                    return {"valid": True, "confidence": 0.5, "reason": "Uncertain from text analysis"}

        except Exception as e:
            return {"valid": False, "confidence": 0.0, "reason": f"Error: {e}"}

    def _clean_answer(self, answer: str, captcha_type: str) -> Optional[str]:
        """Clean and validate answer"""
        if not answer:
            return None

        # Remove quotes and extra whitespace
        cleaned = answer.replace('"', '').replace("'", '').strip()

        # Take first line only
        cleaned = cleaned.split('\n')[0]

        # Remove common LLM prefixes
        prefixes_to_remove = [
            "the text is:", "the answer is:", "i see:", "response:",
            "the code is:", "captcha:", "text:", "answer:"
        ]
        for prefix in prefixes_to_remove:
            if cleaned.lower().startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()

        return cleaned if cleaned else None

    def print_summary(self, vision_results: list, validation_results: list):
        """Print test summary"""
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)

        # Vision summary
        print("\nVISION TESTS:")
        uitars_vision_correct = sum(1 for r in vision_results if r["ui_tars"].get("correct") == True)
        moondream_vision_correct = sum(1 for r in vision_results if r["moondream"].get("correct") == True)
        uitars_vision_time = sum(r["ui_tars"]["time"] for r in vision_results)
        moondream_vision_time = sum(r["moondream"]["time"] for r in vision_results)

        print(f"  UI-TARS:   {uitars_vision_correct}/{len(vision_results)} correct, avg {uitars_vision_time/len(vision_results):.2f}s")
        print(f"  moondream: {moondream_vision_correct}/{len(vision_results)} correct, avg {moondream_vision_time/len(vision_results):.2f}s")

        # Validation summary
        print("\nVALIDATION TESTS:")
        uitars_val_correct = sum(1 for r in validation_results if r["ui_tars"].get("correct") == True)
        qwen_val_correct = sum(1 for r in validation_results if r["qwen3"].get("correct") == True)
        uitars_val_time = sum(r["ui_tars"]["time"] for r in validation_results)
        qwen_val_time = sum(r["qwen3"]["time"] for r in validation_results)

        print(f"  UI-TARS:   {uitars_val_correct}/{len(validation_results)} correct, avg {uitars_val_time/len(validation_results):.2f}s")
        print(f"  qwen3:8b:  {qwen_val_correct}/{len(validation_results)} correct, avg {qwen_val_time/len(validation_results):.2f}s")

        # Recommendation
        print("\nRECOMMENDATION:")
        if uitars_vision_correct >= moondream_vision_correct and uitars_val_correct >= qwen_val_correct:
            print("  ✓ UI-TARS can replace BOTH moondream AND qwen3:8b")
            print("  ✓ Simplifies system to single model")
            print("  ✓ Use UI-TARS as default for vision + validation")
        elif uitars_vision_correct >= moondream_vision_correct:
            print("  ✓ UI-TARS can replace moondream for vision")
            print("  - Keep qwen3:8b for validation")
        elif uitars_val_correct >= qwen_val_correct:
            print("  - Keep moondream for vision")
            print("  ✓ UI-TARS can replace qwen3:8b for validation")
        else:
            print("  - Keep current setup (moondream + qwen3:8b)")
            print("  - UI-TARS needs more training/tuning for CAPTCHA tasks")


async def main():
    """Run UI-TARS evaluation"""

    if not HAS_OLLAMA:
        return

    evaluator = UITarsEvaluator()

    # Vision test cases
    vision_test_cases = [
        {
            "name": "Simple text CAPTCHA",
            "type": "text",
            "description": "The text 'AbC123' in slightly distorted font",
            "expected_answer": "AbC123"
        },
        {
            "name": "Math CAPTCHA",
            "type": "math",
            "description": "The equation '7 + 5 = ?'",
            "expected_answer": "12"
        },
        {
            "name": "Complex text CAPTCHA",
            "type": "text",
            "description": "The text 'xY9pQ2' with heavy distortion and line overlays",
            "expected_answer": "xY9pQ2"
        },
        {
            "name": "Ambiguous characters",
            "type": "text",
            "description": "The text 'O0Il1' (O vs 0, I vs l vs 1)",
            "expected_answer": "O0Il1"
        }
    ]

    # Validation test cases
    validation_test_cases = [
        {
            "name": "Valid text answer",
            "answer": "AbC123",
            "type": "text",
            "image_desc": "Clear text with moderate distortion",
            "raw_answer": "The text is: AbC123",
            "expected_valid": True
        },
        {
            "name": "Invalid text (too long)",
            "answer": "ThisIsWayTooLongForACaptcha",
            "type": "text",
            "image_desc": "Unclear, heavily distorted",
            "raw_answer": "I think it says ThisIsWayTooLongForACaptcha but I'm not sure",
            "expected_valid": False
        },
        {
            "name": "Valid math answer",
            "answer": "12",
            "type": "math",
            "image_desc": "Clear equation '7 + 5 = ?'",
            "raw_answer": "12",
            "expected_valid": True
        },
        {
            "name": "Invalid format (text in math)",
            "answer": "seven plus five",
            "type": "math",
            "image_desc": "Math equation",
            "raw_answer": "The answer is seven plus five equals twelve",
            "expected_valid": False
        },
        {
            "name": "Valid with OCR correction",
            "answer": "O0Il1",
            "type": "text",
            "image_desc": "Text with ambiguous characters O, 0, I, l, 1",
            "raw_answer": "O0Il1",
            "expected_valid": True
        }
    ]

    # Run tests
    vision_results = await evaluator.test_vision_capability(vision_test_cases)
    validation_results = await evaluator.test_validation_capability(validation_test_cases)

    # Print summary and recommendation
    evaluator.print_summary(vision_results, validation_results)

    # Save detailed results
    results_file = Path.home() / ".eversale" / "ui_tars_evaluation.json"
    results_file.parent.mkdir(exist_ok=True)

    with open(results_file, "w") as f:
        json.dump({
            "vision_results": vision_results,
            "validation_results": validation_results,
            "timestamp": time.time()
        }, f, indent=2)

    print(f"\nDetailed results saved to: {results_file}")


if __name__ == "__main__":
    asyncio.run(main())
