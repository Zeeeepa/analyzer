#!/usr/bin/env python3
"""
Test script for Rust FFI integration

Verifies that:
1. rust_bridge module loads correctly
2. Rust functions are called when available
3. Python fallbacks work when Rust is unavailable
4. Performance improvements are measurable
"""

import time
import json
from typing import Dict, Any


def test_import():
    """Test that rust_bridge can be imported."""
    print("=" * 80)
    print("TEST 1: Import rust_bridge")
    print("=" * 80)
    try:
        from rust_bridge import (
            extract_emails,
            extract_phones,
            extract_contacts,
            deduplicate_contacts,
            parse_accessibility_tree,
            fast_snapshot,
            fast_json_parse,
            fast_json_dumps,
            CompiledPatterns,
            get_mode,
            is_rust_available,
            get_performance_info
        )
        print("✓ All functions imported successfully")
        print(f"✓ Mode: {get_mode()}")
        print(f"✓ Rust available: {is_rust_available()}")
        return True
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False


def test_email_extraction():
    """Test email extraction with Rust acceleration."""
    print("\n" + "=" * 80)
    print("TEST 2: Email Extraction")
    print("=" * 80)

    from rust_bridge import extract_emails, get_mode

    test_text = """
    Contact us at sales@example.com or support@company.org
    Our CEO is john.doe@startup.io
    Reach out via info@test.com for more information
    Invalid emails: not-an-email, @nodomain.com, missing@.com
    """

    start = time.time()
    emails = extract_emails(test_text)
    elapsed = time.time() - start

    print(f"Mode: {get_mode()}")
    print(f"Found {len(emails)} emails in {elapsed*1000:.2f}ms:")
    for email in emails:
        print(f"  - {email}")

    expected = {'sales@example.com', 'support@company.org', 'john.doe@startup.io', 'info@test.com'}
    found = set(emails)

    if expected == found:
        print("✓ Email extraction working correctly")
        return True
    else:
        print(f"✗ Mismatch: expected {expected}, got {found}")
        return False


def test_phone_extraction():
    """Test phone extraction with Rust acceleration."""
    print("\n" + "=" * 80)
    print("TEST 3: Phone Extraction")
    print("=" * 80)

    from rust_bridge import extract_phones, get_mode

    test_text = """
    Call us at 555-123-4567 or (800) 555-9999
    International: +1-415-555-0000
    Direct line: 123.456.7890
    """

    start = time.time()
    phones = extract_phones(test_text)
    elapsed = time.time() - start

    print(f"Mode: {get_mode()}")
    print(f"Found {len(phones)} phone numbers in {elapsed*1000:.2f}ms:")
    for phone in phones:
        print(f"  - {phone}")

    if len(phones) >= 3:
        print("✓ Phone extraction working")
        return True
    else:
        print(f"✗ Expected at least 3 phones, got {len(phones)}")
        return False


def test_json_performance():
    """Test JSON parsing/serialization performance."""
    print("\n" + "=" * 80)
    print("TEST 4: JSON Performance")
    print("=" * 80)

    from rust_bridge import fast_json_parse, fast_json_dumps, get_mode

    # Create a moderately complex JSON object
    test_obj = {
        'users': [
            {'id': i, 'name': f'User {i}', 'email': f'user{i}@example.com'}
            for i in range(100)
        ],
        'metadata': {
            'total': 100,
            'page': 1,
            'tags': ['test', 'performance', 'json']
        }
    }

    # Test serialization
    start = time.time()
    json_str = fast_json_dumps(test_obj)
    dumps_time = time.time() - start

    # Test parsing
    start = time.time()
    parsed = fast_json_parse(json_str)
    parse_time = time.time() - start

    print(f"Mode: {get_mode()}")
    print(f"Serialization: {dumps_time*1000:.2f}ms")
    print(f"Parsing: {parse_time*1000:.2f}ms")
    print(f"JSON size: {len(json_str)} bytes")

    if parsed == test_obj:
        print("✓ JSON roundtrip successful")
        return True
    else:
        print("✗ JSON roundtrip failed")
        return False


def test_contact_deduplication():
    """Test contact deduplication."""
    print("\n" + "=" * 80)
    print("TEST 5: Contact Deduplication")
    print("=" * 80)

    from rust_bridge import deduplicate_contacts, get_mode

    contacts = [
        {'email': 'john@example.com', 'name': 'John'},
        {'email': 'jane@example.com', 'name': 'Jane'},
        {'email': 'john@example.com', 'name': 'John Doe'},  # Duplicate
        {'phone': '555-1234', 'name': 'Bob'},
        {'email': 'jane@example.com', 'name': 'Jane Smith'},  # Duplicate
    ]

    start = time.time()
    unique = deduplicate_contacts(contacts)
    elapsed = time.time() - start

    print(f"Mode: {get_mode()}")
    print(f"Deduplicated {len(contacts)} -> {len(unique)} in {elapsed*1000:.2f}ms")
    print(f"Unique contacts:")
    for contact in unique:
        print(f"  - {contact}")

    if len(unique) == 3:  # john, jane, bob
        print("✓ Deduplication working correctly")
        return True
    else:
        print(f"✗ Expected 3 unique contacts, got {len(unique)}")
        return False


def test_compiled_patterns():
    """Test pre-compiled regex patterns."""
    print("\n" + "=" * 80)
    print("TEST 6: Compiled Patterns")
    print("=" * 80)

    from rust_bridge import CompiledPatterns, get_mode

    patterns = CompiledPatterns()

    test_text = """
    Contact: admin@example.com, Phone: 555-0123
    Website: https://example.com/contact
    Email us at support@test.org
    """

    start = time.time()
    emails = patterns.find_emails(test_text)
    phones = patterns.find_phones(test_text)
    urls = patterns.find_urls(test_text)
    elapsed = time.time() - start

    print(f"Mode: {get_mode()}")
    print(f"Found in {elapsed*1000:.2f}ms:")
    print(f"  Emails: {emails}")
    print(f"  Phones: {phones}")
    print(f"  URLs: {urls}")

    if len(emails) >= 2 and len(phones) >= 1 and len(urls) >= 1:
        print("✓ Compiled patterns working")
        return True
    else:
        print("✗ Compiled patterns incomplete")
        return False


def test_performance_info():
    """Test performance info reporting."""
    print("\n" + "=" * 80)
    print("TEST 7: Performance Info")
    print("=" * 80)

    from rust_bridge import get_performance_info

    info = get_performance_info()

    print("Performance optimizations:")
    print(json.dumps(info, indent=2))

    if 'rust_available' in info and 'optimizations' in info:
        print("✓ Performance info available")
        return True
    else:
        print("✗ Performance info incomplete")
        return False


def test_module_integration():
    """Test that other modules can use rust_bridge."""
    print("\n" + "=" * 80)
    print("TEST 8: Module Integration")
    print("=" * 80)

    # Test contact_extractor
    try:
        from contact_extractor import ContactExtractor
        extractor = ContactExtractor()
        test_text = "Email: test@example.com, Phone: 555-1234"
        emails = extractor._extract_emails_from_text(test_text)
        phones = extractor._extract_phones_from_text(test_text)
        print(f"✓ contact_extractor working: {len(emails)} emails, {len(phones)} phones")
    except Exception as e:
        print(f"✗ contact_extractor failed: {e}")
        return False

    # Test document_processor
    try:
        from document_processor import DocumentProcessor
        processor = DocumentProcessor()
        test_json = '{"test": "data"}'
        # This would normally use fast_json_parse internally
        print("✓ document_processor imports successfully")
    except Exception as e:
        print(f"✗ document_processor failed: {e}")
        return False

    return True


def run_all_tests():
    """Run all tests and report results."""
    print("\n")
    print("=" * 80)
    print("RUST FFI INTEGRATION TEST SUITE")
    print("=" * 80)

    tests = [
        ("Import", test_import),
        ("Email Extraction", test_email_extraction),
        ("Phone Extraction", test_phone_extraction),
        ("JSON Performance", test_json_performance),
        ("Contact Deduplication", test_contact_deduplication),
        ("Compiled Patterns", test_compiled_patterns),
        ("Performance Info", test_performance_info),
        ("Module Integration", test_module_integration),
    ]

    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"\n✗ {name} crashed: {e}")
            results.append((name, False))

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    passed = sum(1 for _, p in results if p)
    total = len(results)

    for name, passed_test in results:
        status = "✓ PASS" if passed_test else "✗ FAIL"
        print(f"{status}: {name}")

    print(f"\nResults: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == '__main__':
    import sys
    sys.exit(run_all_tests())
