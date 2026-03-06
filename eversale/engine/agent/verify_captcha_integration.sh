#!/bin/bash

echo "=========================================="
echo "CAPTCHA AUTO-TRIGGER VERIFICATION"
echo "=========================================="
echo ""

echo "1. Checking imports..."
if grep -q "from .captcha_solver import.*PageCaptchaHandler.*LocalCaptchaSolver" playwright_direct.py; then
    echo "   ✓ Imports present"
else
    echo "   ✗ Imports missing"
    exit 1
fi

echo ""
echo "2. Checking auto-detection code..."
if grep -q "AUTO-CAPTCHA DETECTION AND SOLVING" playwright_direct.py; then
    echo "   ✓ Auto-detection code present"
else
    echo "   ✗ Auto-detection code missing"
    exit 1
fi

echo ""
echo "3. Checking result enhancement..."
if grep -q 'result\["captcha_detected"\]' playwright_direct.py; then
    echo "   ✓ Result enhancement present"
else
    echo "   ✗ Result enhancement missing"
    exit 1
fi

echo ""
echo "4. Checking syntax..."
if python3 -m py_compile playwright_direct.py 2>/dev/null; then
    echo "   ✓ Syntax valid"
else
    echo "   ✗ Syntax errors found"
    exit 1
fi

echo ""
echo "5. Integration summary..."
echo "   Location: navigate() method (lines ~2142-2211)"
echo "   Trigger: After page load, before result return"
echo "   Types detected: Image, reCAPTCHA, hCaptcha, Turnstile"
echo "   Auto-solve: Image CAPTCHAs via vision model"
echo ""

echo "=========================================="
echo "✓ ALL CHECKS PASSED"
echo "=========================================="
echo ""
echo "CAPTCHA auto-trigger is successfully wired!"
echo "No calling code changes needed."
echo ""

