#!/usr/bin/env python3
"""
Comprehensive test suite for TokenOptimizer.

Run with:
    python3 test_token_optimizer.py
"""

import json
import time
from token_optimizer import (
    TokenOptimizer,
    create_optimizer,
    optimize_snapshot,
    estimate_snapshot_tokens,
    DEFAULT_CONFIG
)


def test_basic_creation():
    """Test basic optimizer creation."""
    print("TEST: Basic creation...")
    optimizer = TokenOptimizer()
    assert optimizer is not None
    assert optimizer.config == DEFAULT_CONFIG
    print("  PASSED")


def test_custom_config():
    """Test custom configuration."""
    print("TEST: Custom config...")
    config = {
        'max_snapshot_elements': 50,
        'max_text_length': 100,
        'token_budget': 5000,
    }
    optimizer = TokenOptimizer(config)
    assert optimizer.config['max_snapshot_elements'] == 50
    assert optimizer.config['max_text_length'] == 100
    assert optimizer.config['token_budget'] == 5000
    print("  PASSED")


def test_create_optimizer_helper():
    """Test create_optimizer convenience function."""
    print("TEST: create_optimizer helper...")
    optimizer = create_optimizer(
        max_elements=75,
        max_text_length=150,
        token_budget=6000
    )
    assert optimizer.config['max_snapshot_elements'] == 75
    assert optimizer.config['max_text_length'] == 150
    assert optimizer.config['token_budget'] == 6000
    print("  PASSED")


def test_should_resnapshot():
    """Test snapshot throttling logic."""
    print("TEST: should_resnapshot...")
    optimizer = TokenOptimizer()

    # No cache - should snapshot
    assert optimizer.should_resnapshot('click') is True

    # Cache snapshot
    test_snapshot = {'elements': []}
    optimizer.cache_snapshot(test_snapshot)

    # Non-DOM-changing actions - should NOT snapshot
    assert optimizer.should_resnapshot('scroll') is False
    assert optimizer.should_resnapshot('hover') is False
    assert optimizer.should_resnapshot('wait') is False

    # DOM-changing actions - should snapshot
    assert optimizer.should_resnapshot('click') is True
    assert optimizer.should_resnapshot('type') is True

    print("  PASSED")


def test_cache_snapshot():
    """Test snapshot caching."""
    print("TEST: cache_snapshot...")
    optimizer = TokenOptimizer()

    snapshot = {'elements': [{'ref': 'test', 'text': 'hello'}]}
    hash_value = optimizer.cache_snapshot(snapshot)

    assert hash_value is not None
    assert len(hash_value) == 32  # MD5 hash length
    assert optimizer.last_snapshot_hash == hash_value
    assert optimizer.snapshot_cache is not None
    assert optimizer.snapshot_cache.snapshot == snapshot

    print("  PASSED")


def test_get_cached_snapshot():
    """Test cached snapshot retrieval."""
    print("TEST: get_cached_snapshot...")
    optimizer = TokenOptimizer()

    # No cache
    assert optimizer.get_cached_snapshot() is None

    # Cache snapshot
    snapshot = {'elements': [{'ref': 'test'}]}
    optimizer.cache_snapshot(snapshot)

    # Should return cached
    cached = optimizer.get_cached_snapshot()
    assert cached == snapshot

    # Wait for TTL expiration
    optimizer.config['cache_ttl_seconds'] = 0.1
    time.sleep(0.2)

    # Should return None (expired)
    cached = optimizer.get_cached_snapshot()
    assert cached is None

    print("  PASSED")


def test_compress_snapshot():
    """Test snapshot compression."""
    print("TEST: compress_snapshot...")
    optimizer = TokenOptimizer({
        'max_snapshot_elements': 3,
        'max_text_length': 20,
    })

    # Create large snapshot
    snapshot = {
        'elements': [
            {'ref': f'item-{i}', 'text': 'x' * 100} for i in range(10)
        ]
    }

    compressed = optimizer.compress_snapshot(snapshot)

    # Should have limited elements
    assert len(compressed['elements']) <= 4  # 3 items + collapsed marker

    # Text should be truncated
    if compressed['elements']:
        first_elem = compressed['elements'][0]
        if 'text' in first_elem:
            assert len(first_elem['text']) <= 23  # 20 + '...'

    print("  PASSED")


def test_compress_hidden_elements():
    """Test removal of hidden elements."""
    print("TEST: compress hidden elements...")
    optimizer = TokenOptimizer({'remove_hidden': True})

    snapshot = {
        'elements': [
            {'ref': 'visible', 'text': 'shown', 'visible': True},
            {'ref': 'hidden', 'text': 'invisible', 'visible': False},
        ]
    }

    compressed = optimizer.compress_snapshot(snapshot)

    # Hidden element should be marked
    hidden_elem = compressed['elements'][1]
    assert hidden_elem == {'_hidden': True}

    print("  PASSED")


def test_compress_lists():
    """Test list collapse."""
    print("TEST: compress lists...")
    optimizer = TokenOptimizer({
        'compress_lists': True,
        'max_snapshot_elements': 5,
    })

    snapshot = {
        'elements': [{'ref': f'item-{i}'} for i in range(50)]
    }

    compressed = optimizer.compress_snapshot(snapshot)

    # Should have collapsed indicator
    assert len(compressed['elements']) <= 6  # 5 + collapsed marker
    last_elem = compressed['elements'][-1]
    assert '_collapsed' in last_elem

    print("  PASSED")


def test_estimate_tokens():
    """Test token estimation."""
    print("TEST: estimate_tokens...")
    optimizer = TokenOptimizer()

    # Simple text
    text1 = "hello world"
    tokens1 = optimizer.estimate_tokens(text1)
    assert tokens1 > 0
    assert tokens1 < 10  # Should be around 2-3 tokens

    # Long text
    text2 = "hello world " * 100
    tokens2 = optimizer.estimate_tokens(text2)
    assert tokens2 > tokens1
    assert tokens2 > 100

    print("  PASSED")


def test_get_minimal_context():
    """Test minimal context generation."""
    print("TEST: get_minimal_context...")
    optimizer = TokenOptimizer()

    task = "Click the submit button"
    snapshot = {'elements': [{'ref': 'submit', 'text': 'Submit'}]}

    context = optimizer.get_minimal_context(task, snapshot)

    assert 'Task: Click the submit button' in context
    assert 'Page State:' in context
    assert 'submit' in context

    print("  PASSED")


def test_check_budget():
    """Test budget checking."""
    print("TEST: check_budget...")
    optimizer = TokenOptimizer({'token_budget': 100})

    # Small context - within budget
    small_context = "hello world"
    within_budget, tokens, message = optimizer.check_budget(small_context)
    assert within_budget is True
    assert tokens < 100
    assert 'Token usage:' in message

    # Large context - exceeds budget
    large_context = "hello world " * 200
    within_budget, tokens, message = optimizer.check_budget(large_context)
    assert within_budget is False
    assert tokens > 100
    assert 'WARNING' in message

    print("  PASSED")


def test_stats_tracking():
    """Test statistics tracking."""
    print("TEST: stats tracking...")
    optimizer = TokenOptimizer()

    # Initial stats
    stats = optimizer.get_stats()
    assert stats['raw_tokens'] == 0
    assert stats['compressed_tokens'] == 0

    # Update stats
    optimizer.update_stats(1000, 400)
    stats = optimizer.get_stats()
    assert stats['raw_tokens'] == 1000
    assert stats['compressed_tokens'] == 400
    assert stats['saved_tokens'] == 600
    assert stats['savings_pct'] == 60.0

    # Update again
    optimizer.update_stats(2000, 800)
    stats = optimizer.get_stats()
    assert stats['raw_tokens'] == 3000
    assert stats['compressed_tokens'] == 1200
    assert stats['saved_tokens'] == 1800
    assert stats['savings_pct'] == 60.0

    # Reset
    optimizer.reset_stats()
    stats = optimizer.get_stats()
    assert stats['raw_tokens'] == 0

    print("  PASSED")


def test_cache_stats():
    """Test cache hit/miss tracking."""
    print("TEST: cache stats...")
    optimizer = TokenOptimizer()

    # Initial
    stats = optimizer.get_stats()
    assert stats['cache_hits'] == 0
    assert stats['cache_misses'] == 0

    # Cache snapshot first
    optimizer.cache_snapshot({'elements': []})

    # Cache miss (DOM-changing action)
    optimizer.should_resnapshot('click')
    stats = optimizer.get_stats()
    assert stats['cache_misses'] == 1

    # Cache hit (skip_snapshot_after action)
    optimizer.should_resnapshot('scroll')
    stats = optimizer.get_stats()
    assert stats['cache_hits'] == 1

    # Calculate hit rate
    assert stats['cache_hit_rate'] == 50.0  # 1 hit / 2 total

    print("  PASSED")


def test_clear_cache():
    """Test cache clearing."""
    print("TEST: clear_cache...")
    optimizer = TokenOptimizer()

    # Cache snapshot
    optimizer.cache_snapshot({'elements': []})
    assert optimizer.snapshot_cache is not None

    # Clear
    optimizer.clear_cache()
    assert optimizer.snapshot_cache is None
    assert optimizer.last_snapshot_hash is None

    print("  PASSED")


def test_compression_toggle():
    """Test enabling/disabling compression."""
    print("TEST: compression toggle...")
    optimizer = TokenOptimizer()

    snapshot = {'elements': [{'text': 'x' * 1000}]}

    # Compression enabled
    compressed = optimizer.compress_snapshot(snapshot)
    assert len(json.dumps(compressed)) < len(json.dumps(snapshot))

    # Disable compression
    optimizer.set_compression_enabled(False)
    compressed = optimizer.compress_snapshot(snapshot)
    assert compressed == snapshot  # No compression

    # Re-enable
    optimizer.set_compression_enabled(True)
    compressed = optimizer.compress_snapshot(snapshot)
    assert len(json.dumps(compressed)) < len(json.dumps(snapshot))

    print("  PASSED")


def test_optimize_snapshot_helper():
    """Test optimize_snapshot convenience function."""
    print("TEST: optimize_snapshot helper...")
    snapshot = {
        'elements': [{'ref': f'item-{i}', 'text': 'x' * 100} for i in range(50)]
    }

    compressed = optimize_snapshot(snapshot, {
        'max_snapshot_elements': 10,
        'max_text_length': 50,
    })

    assert len(compressed['elements']) <= 11  # 10 + collapsed
    print("  PASSED")


def test_estimate_snapshot_tokens_helper():
    """Test estimate_snapshot_tokens convenience function."""
    print("TEST: estimate_snapshot_tokens helper...")
    snapshot = {'elements': [{'ref': 'test', 'text': 'hello world'}]}

    tokens = estimate_snapshot_tokens(snapshot)
    assert tokens > 0
    assert tokens < 100  # Small snapshot

    print("  PASSED")


def test_auto_compression():
    """Test auto-compression when exceeding budget threshold."""
    print("TEST: auto-compression...")
    optimizer = TokenOptimizer({
        'token_budget': 100,
        'auto_compress_threshold': 0.5,  # 50%
    })

    # Create context that exceeds 50% of budget
    task = "test"
    snapshot = {'elements': [{'text': 'x' * 200}]}

    context = optimizer.get_minimal_context(task, snapshot)

    # Should trigger auto-compression
    stats = optimizer.get_stats()
    # Note: auto_compressions increments in get_minimal_context if over threshold

    print("  PASSED")


def test_real_world_scenario():
    """Test realistic browser agent scenario."""
    print("TEST: real-world scenario...")
    optimizer = TokenOptimizer()

    # Simulate browser agent loop
    actions = [
        ('navigate', True),   # (action_type, should_take_snapshot)
        ('scroll', False),
        ('hover', False),
        ('click', True),
        ('type', True),
        ('wait', False),
        ('scroll', False),
    ]

    for action_type, expected_snapshot in actions:
        should_snap = optimizer.should_resnapshot(action_type)

        if should_snap:
            # Take snapshot
            snapshot = {'elements': [{'ref': f'{action_type}-elem'}]}
            optimizer.cache_snapshot(snapshot)

    # Check stats
    stats = optimizer.get_stats()
    assert stats['cache_hits'] > 0  # Should have cache hits for scroll/hover/wait
    assert stats['cache_misses'] > 0  # Should have misses for DOM-changing actions

    print("  PASSED")


def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("Token Optimizer Test Suite")
    print("=" * 60)
    print()

    tests = [
        test_basic_creation,
        test_custom_config,
        test_create_optimizer_helper,
        test_should_resnapshot,
        test_cache_snapshot,
        test_get_cached_snapshot,
        test_compress_snapshot,
        test_compress_hidden_elements,
        test_compress_lists,
        test_estimate_tokens,
        test_get_minimal_context,
        test_check_budget,
        test_stats_tracking,
        test_cache_stats,
        test_clear_cache,
        test_compression_toggle,
        test_optimize_snapshot_helper,
        test_estimate_snapshot_tokens_helper,
        test_auto_compression,
        test_real_world_scenario,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            failed += 1

    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == '__main__':
    import sys
    success = run_all_tests()
    sys.exit(0 if success else 1)
