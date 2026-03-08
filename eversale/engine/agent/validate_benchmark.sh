#!/bin/bash
# Validate benchmark system is ready to run

echo "========================================"
echo "Benchmark System Validation"
echo "========================================"
echo

# Check Python version
echo "1. Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1)
echo "   $PYTHON_VERSION"
echo

# Check required modules
echo "2. Checking required modules..."
python3 << 'PYEOF'
import sys

modules = [
    ('token_optimizer', 'Token compression and caching'),
    ('dom_first_browser', 'Snapshot-first browser'),
    ('extraction_helpers', 'JavaScript extraction utilities'),
]

all_ok = True
for module, desc in modules:
    try:
        __import__(module)
        print(f"   ✓ {module:25} - {desc}")
    except ImportError as e:
        print(f"   ✗ {module:25} - MISSING: {e}")
        all_ok = False

if not all_ok:
    print("\n   ERROR: Some required modules are missing!")
    sys.exit(1)
PYEOF

if [ $? -ne 0 ]; then
    echo
    echo "   FAILED: Required modules missing"
    exit 1
fi
echo

# Check optional modules
echo "3. Checking optional modules..."
python3 << 'PYEOF'
try:
    from playwright_direct import DirectPlaywright
    print("   ✓ playwright_direct (OLD approach available)")
except ImportError:
    print("   ℹ playwright_direct not available (will use estimates)")
PYEOF
echo

# Check benchmark script
echo "4. Validating benchmark script..."
if [ -f "benchmark_improvements.py" ]; then
    echo "   ✓ benchmark_improvements.py exists"
    
    # Check it imports
    python3 -c "import benchmark_improvements" 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "   ✓ benchmark_improvements.py imports successfully"
    else
        echo "   ✗ benchmark_improvements.py has import errors"
        exit 1
    fi
else
    echo "   ✗ benchmark_improvements.py not found"
    exit 1
fi
echo

# Check test script
echo "5. Validating test script..."
if [ -f "test_benchmark.py" ]; then
    echo "   ✓ test_benchmark.py exists"
else
    echo "   ✗ test_benchmark.py not found"
    exit 1
fi
echo

# Check documentation
echo "6. Checking documentation..."
docs=("BENCHMARK_README.md" "BENCHMARK_QUICKSTART.md" "BENCHMARK_INDEX.md")
for doc in "${docs[@]}"; do
    if [ -f "$doc" ]; then
        echo "   ✓ $doc"
    else
        echo "   ✗ $doc missing"
    fi
done
echo

# Check Playwright
echo "7. Checking Playwright installation..."
python3 << 'PYEOF'
try:
    from playwright.async_api import async_playwright
    print("   ✓ Playwright installed")
except ImportError:
    print("   ✗ Playwright not installed")
    print("   Run: pip install playwright && playwright install chromium")
PYEOF
echo

# Summary
echo "========================================"
echo "✓ Benchmark system ready!"
echo "========================================"
echo
echo "Quick start:"
echo "  python benchmark_improvements.py --tasks 1    # Quick test"
echo "  python test_benchmark.py                      # Test output"
echo "  python benchmark_improvements.py              # Full benchmark"
echo
echo "Documentation:"
echo "  BENCHMARK_QUICKSTART.md  - Quick reference"
echo "  BENCHMARK_README.md      - Complete guide"
echo "  BENCHMARK_INDEX.md       - File index"
echo
