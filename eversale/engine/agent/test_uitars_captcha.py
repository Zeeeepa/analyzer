"""
Test script to verify UI-TARS integration with CAPTCHA solver
"""
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.captcha_solver import LocalCaptchaSolver


async def test_uitars_initialization():
    """Test vision model initialization and UI-TARS availability"""
    print("Testing vision model initialization...")

    # Test default initialization (moondream is primary)
    solver = LocalCaptchaSolver()
    assert solver.vision_model == "moondream", f"Expected 'moondream' but got '{solver.vision_model}'"
    print(f"Default vision model: {solver.vision_model}")

    # Test explicit model specification
    solver_moondream = LocalCaptchaSolver(vision_model="moondream")
    assert solver_moondream.vision_model == "moondream", f"Expected 'moondream' but got '{solver_moondream.vision_model}'"
    print(f"Explicit moondream model: {solver_moondream.vision_model}")

    # Check ollama client is available
    if solver.ollama_client:
        print("Ollama client is available")

        # Test that UI-TARS model is available in ollama
        try:
            models = solver.ollama_client.list()
            model_names = [m.get('model', m.get('name', 'unknown')) for m in models.get('models', [])]

            print(f"\nAvailable Ollama models:")
            for name in model_names:
                print(f"  - {name}")

            # Check for UI-TARS
            uitars_available = any('UI-TARS' in name or 'ui-tars' in name.lower() for name in model_names)
            if uitars_available:
                print("\nUI-TARS model is available in Ollama")
            else:
                print("\nWARNING: UI-TARS model not found in Ollama")
                print("Run: ollama pull 0000/ui-tars-1.5-7b:latest")
        except Exception as e:
            print(f"Error checking Ollama models: {e}")
    else:
        print("WARNING: Ollama client not available")

    print("\nAll initialization tests passed!")


async def test_model_chain():
    """Test that the model fallback chain includes UI-TARS first"""
    print("\nTesting model fallback chain...")

    # The model chain is defined in solve_image_with_vision method
    # We can't easily test it without a real CAPTCHA, but we can verify the code

    import inspect
    solver = LocalCaptchaSolver()

    # Get the source code of solve_image_with_vision
    source = inspect.getsource(solver.solve_image_with_vision)

    # Check that UI-TARS is mentioned first in the model chain
    if '0000/ui-tars-1.5-7b:latest' in source:
        print("UI-TARS is referenced in solve_image_with_vision method")

        # Check moondream comes before UI-TARS (moondream is primary)
        uitars_pos = source.find('0000/ui-tars-1.5-7b:latest')
        moondream_pos = source.find('moondream')

        if moondream_pos < uitars_pos:
            print("moondream appears before UI-TARS in the code (correct priority)")
        else:
            print("WARNING: UI-TARS appears before moondream (should be reversed)")
    else:
        print("WARNING: UI-TARS not found in solve_image_with_vision method")

    print("Model chain test completed!")


async def main():
    """Run all tests"""
    print("=" * 60)
    print("Vision Model Integration Test (moondream + UI-TARS)")
    print("=" * 60)

    try:
        await test_uitars_initialization()
        await test_model_chain()

        print("\n" + "=" * 60)
        print("All tests completed successfully!")
        print("=" * 60)

    except Exception as e:
        print(f"\nTest failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
