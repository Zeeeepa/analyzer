"""
Quick test to verify date_picker_handler module loads and works
"""

import asyncio
from datetime import datetime
from loguru import logger


async def test_import():
    """Test that module imports correctly"""
    try:
        from date_picker_handler import (
            DatePickerHandler,
            DatePickerResult,
            DatePickerType,
            fill_date_simple,
            fill_date_range_simple,
        )
        logger.info("✓ Module imports successfully")
        return True
    except ImportError as e:
        logger.error(f"✗ Import failed: {e}")
        return False


async def test_date_parsing():
    """Test date parsing functionality"""
    from date_picker_handler import DatePickerHandler

    # Create mock page (we just need the date parsing function)
    class MockPage:
        pass

    handler = DatePickerHandler(MockPage())

    test_cases = [
        ("2025-12-15", "ISO format"),
        ("12/15/2025", "US format"),
        ("Dec 15, 2025", "Natural format"),
        ("December 15, 2025", "Full month format"),
    ]

    all_passed = True
    for date_str, desc in test_cases:
        try:
            parsed = await handler.parse_date(date_str)
            expected = datetime(2025, 12, 15)
            if parsed.date() == expected.date():
                logger.info(f"✓ {desc}: '{date_str}' → {parsed.strftime('%Y-%m-%d')}")
            else:
                logger.error(f"✗ {desc}: '{date_str}' → {parsed.strftime('%Y-%m-%d')} (expected {expected.strftime('%Y-%m-%d')})")
                all_passed = False
        except Exception as e:
            logger.error(f"✗ {desc}: '{date_str}' → ERROR: {e}")
            all_passed = False

    return all_passed


async def test_month_display_parsing():
    """Test month display parsing"""
    from date_picker_handler import DatePickerHandler

    class MockPage:
        pass

    handler = DatePickerHandler(MockPage())

    test_cases = [
        ("December 2025", datetime(2025, 12, 1)),
        ("Dec 2025", datetime(2025, 12, 1)),
        ("2025 December", datetime(2025, 12, 1)),
        ("January 2026", datetime(2026, 1, 1)),
    ]

    all_passed = True
    for text, expected in test_cases:
        result = handler._parse_month_display(text)
        if result and result.month == expected.month and result.year == expected.year:
            logger.info(f"✓ Month display: '{text}' → {result.strftime('%B %Y')}")
        else:
            logger.error(f"✗ Month display: '{text}' → {result} (expected {expected})")
            all_passed = False

    return all_passed


async def test_signature_detection():
    """Test date picker signature definitions"""
    from date_picker_handler import DATEPICKER_SIGNATURES

    logger.info(f"Testing {len(DATEPICKER_SIGNATURES)} date picker signatures...")

    expected_types = [
        "html5",
        "booking_com",
        "airbnb",
        "jquery_ui",
        "react_datepicker",
        "flatpickr",
        "kayak",
        "expedia",
    ]

    found_types = [sig.type for sig in DATEPICKER_SIGNATURES]

    all_found = True
    for expected in expected_types:
        if expected in found_types:
            logger.info(f"✓ Signature defined: {expected}")
        else:
            logger.error(f"✗ Missing signature: {expected}")
            all_found = False

    return all_found


async def run_all_tests():
    """Run all quick tests"""
    logger.info("="*70)
    logger.info("Date Picker Handler - Quick Tests")
    logger.info("="*70)

    tests = [
        ("Module Import", test_import),
        ("Date Parsing", test_date_parsing),
        ("Month Display Parsing", test_month_display_parsing),
        ("Signature Detection", test_signature_detection),
    ]

    results = []
    for name, test_func in tests:
        logger.info(f"\n{'─'*70}")
        logger.info(f"Test: {name}")
        logger.info(f"{'─'*70}")
        try:
            passed = await test_func()
            results.append((name, passed))
        except Exception as e:
            logger.error(f"Test crashed: {e}")
            results.append((name, False))

    # Summary
    logger.info("\n" + "="*70)
    logger.info("Test Summary")
    logger.info("="*70)

    total = len(results)
    passed = sum(1 for _, p in results if p)
    failed = total - passed

    for name, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        logger.info(f"{status}: {name}")

    logger.info(f"\nTotal: {total} | Passed: {passed} | Failed: {failed}")

    if failed == 0:
        logger.info("\n🎉 All tests passed!")
        return True
    else:
        logger.error(f"\n❌ {failed} test(s) failed")
        return False


if __name__ == "__main__":
    # Configure logger
    logger.remove()
    logger.add(
        lambda msg: print(msg, end=""),
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        colorize=True
    )

    # Run tests
    success = asyncio.run(run_all_tests())
    exit(0 if success else 1)
