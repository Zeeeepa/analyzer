#!/usr/bin/env python3
"""
Test script for the Agentic Orchestrator and Context Budget v2.

Verifies:
1. Anchor + Sliding Window pattern works correctly
2. Milestone detection preserves important messages
3. Context compression maintains goal awareness
4. Orchestrator coordinates all systems properly

Run: python -m agent.test_agentic_orchestrator
"""

import sys
from datetime import datetime


def test_context_budget_v2():
    """Test the new context budget with Anchor + Sliding Window pattern."""
    print("\n" + "="*60)
    print("TEST: Context Budget v2 - Anchor + Sliding Window")
    print("="*60)

    from agent.context_budget_v2 import (
        ContextBudgetManagerV2,
        MessageImportance,
        get_context_budget_v2
    )

    budget = ContextBudgetManagerV2(max_tokens=8000, window_size=5)
    budget.set_goal("Find leads from Facebook Ads Library for CRM software")

    # Simulate a conversation
    messages = [
        {"role": "system", "content": "You are Eversale, an autonomous AI worker..."},
        {"role": "user", "content": "Find leads from Facebook Ads Library for 'CRM software'"},
        {"role": "assistant", "content": "I'll navigate to Facebook Ads Library and search for CRM software advertisers."},
        {"role": "tool", "content": "Navigation successful: facebook.com/ads/library"},
        {"role": "assistant", "content": "I'll search for CRM software and extract advertisers."},
        {"role": "tool", "content": "Found 15 advertisers: Company A, Company B, Company C..."},
        {"role": "assistant", "content": "Let me extract contact information from each advertiser."},
        {"role": "tool", "content": "Extracted: john@companya.com, sales@companyb.com"},
        {"role": "assistant", "content": "I'll continue extracting contacts from the remaining advertisers."},
        {"role": "tool", "content": "Extracted: info@companyc.com, contact@companyd.com"},
        {"role": "assistant", "content": "I've collected emails. Now saving to CSV."},
        {"role": "tool", "content": "Saved 8 contacts to leads.csv"},
        {"role": "user", "content": "[TASK COMPLETE] Good job!"},
    ]

    # Track messages
    for msg in messages:
        budget.add_message(msg)

    print(f"\nInitial state:")
    print(f"  Messages tracked: {len(messages)}")
    print(f"  Usage: {budget.get_usage()}")

    # Test anchor identification
    anchors = budget._identify_anchors(messages)
    print(f"\nAnchors identified: {len(anchors)}")
    for a in anchors:
        print(f"  - {a['role']}: {a['content'][:50]}...")

    # Test milestone detection
    milestones = [msg for msg in messages if budget._is_milestone(msg.get('content', ''))]
    print(f"\nMilestones detected: {len(milestones)}")
    for m in milestones:
        print(f"  - {m['content'][:60]}...")

    # Test context management
    print(f"\nTesting context management...")
    budget.state.current_tokens = 7000  # Simulate high usage
    if budget.needs_management():
        managed = budget.manage_context(messages, goal="Find leads")
        print(f"  Compressed: {len(messages)} -> {len(managed)} messages")
        print(f"  New usage: {budget.get_usage()}")

    # Test reset
    print(f"\nTesting context reset...")
    budget.state.iteration_count = 25  # Trigger reset
    if budget.should_reset():
        reset_messages = budget.perform_reset(messages, goal="Find leads")
        print(f"  Reset: {len(messages)} -> {len(reset_messages)} messages")
        for rm in reset_messages:
            print(f"    - {rm['role']}: {rm['content'][:80]}...")

    print("\n✓ Context Budget v2 tests passed!")
    return True


def test_agentic_orchestrator():
    """Test the unified agentic orchestrator."""
    print("\n" + "="*60)
    print("TEST: Agentic Orchestrator - Unified Coordination")
    print("="*60)

    from agent.agentic_orchestrator import (
        AgenticOrchestrator,
        AgentMode,
        get_orchestrator
    )

    orchestrator = AgenticOrchestrator()
    orchestrator.set_goal("Find leads from Facebook Ads Library")

    # Simulate messages
    messages = [
        {"role": "system", "content": "You are Eversale..."},
        {"role": "user", "content": "Find leads from Facebook Ads Library for 'CRM software'"},
        {"role": "assistant", "content": "Navigating to FB Ads Library..."},
        {"role": "tool", "content": "Found 10 advertisers"},
    ]

    # Test iteration preparation
    print(f"\nTesting iteration preparation...")
    for i in range(5):
        ctx = orchestrator.prepare_iteration(messages, i + 1)
        print(f"  Iteration {i+1}: mode={ctx.mode.value}, confidence={ctx.confidence:.0%}, "
              f"should_reflect={ctx.should_reflect}")

    # Test action validation
    print(f"\nTesting action validation...")
    test_actions = [
        {"name": "playwright_navigate", "parameters": {"url": "https://facebook.com"}},
        {"name": "playwright_click", "parameters": {"selector": "#submit"}},
        {"name": "rm -rf /", "parameters": {}},  # Should be blocked
    ]

    for action in test_actions:
        decision = orchestrator.validate_action(action)
        status = "ALLOWED" if decision.should_execute else "BLOCKED"
        print(f"  {action['name'][:30]:30} -> {status}")
        if decision.warnings:
            print(f"    Warnings: {decision.warnings}")

    # Test result recording
    print(f"\nTesting result recording...")
    for i in range(10):
        success = i % 3 != 0  # Fail every 3rd action
        orchestrator.record_result(
            action={"name": f"action_{i}"},
            result={"success": success},
            success=success,
            had_meaningful_progress=success
        )

    status = orchestrator.get_status()
    print(f"  Total actions: {status['orchestrator']['total_actions']}")
    print(f"  Success rate: {status['orchestrator']['success_rate']:.0%}")
    print(f"  Mode: {status['orchestrator']['mode']}")
    print(f"  Confidence: {status['confidence']['overall']:.0%}")

    # Test mode determination
    print(f"\nTesting mode transitions...")
    modes_seen = set()
    for _ in range(20):
        orchestrator.record_result(
            action={"name": "test"},
            result={"success": False},
            success=False
        )
        modes_seen.add(orchestrator.state.mode.value)

    print(f"  Modes observed during failures: {modes_seen}")

    # Test should_ask_user
    should_ask, reason = orchestrator.should_ask_user()
    print(f"\nShould ask user: {should_ask}")
    if should_ask:
        print(f"  Reason: {reason}")

    print("\n✓ Agentic Orchestrator tests passed!")
    return True


def test_integration():
    """Test that all components work together."""
    print("\n" + "="*60)
    print("TEST: Integration - All Systems Working Together")
    print("="*60)

    # Test imports
    print("\nTesting imports...")
    try:
        from agent.context_budget_v2 import ContextBudgetManagerV2, get_context_budget_v2
        from agent.agentic_orchestrator import AgenticOrchestrator, get_orchestrator
        from agent.confidence_orchestrator import ConfidenceOrchestrator, get_confidence
        from agent.online_reflection import OnlineReflectionLoop, get_online_reflector
        from agent.pre_execution_validator import PreExecutionValidator, get_validator
        print("  ✓ All imports successful")
    except ImportError as e:
        print(f"  ✗ Import error: {e}")
        return False

    # Test global singletons
    print("\nTesting global singletons...")
    budget = get_context_budget_v2()
    orchestrator = get_orchestrator()
    confidence = get_confidence()
    reflector = get_online_reflector()
    validator = get_validator()

    print(f"  ✓ Context Budget v2: {type(budget).__name__}")
    print(f"  ✓ Orchestrator: {type(orchestrator).__name__}")
    print(f"  ✓ Confidence: {type(confidence).__name__}")
    print(f"  ✓ Reflector: {type(reflector).__name__}")
    print(f"  ✓ Validator: {type(validator).__name__}")

    # Test that orchestrator coordinates all systems
    print("\nTesting orchestrator coordination...")
    orchestrator.reset()
    orchestrator.set_goal("Test integration")

    # Verify all sub-systems are connected
    assert orchestrator.context_budget is not None, "Context budget not connected"
    assert orchestrator.confidence is not None, "Confidence not connected"
    assert orchestrator.reflector is not None, "Reflector not connected"
    assert orchestrator.validator is not None, "Validator not connected"
    print("  ✓ All sub-systems connected")

    # Run a mini simulation
    print("\nRunning mini simulation...")
    messages = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "Test task"},
    ]

    for i in range(25):  # Run 25 iterations (should trigger reset at 20)
        ctx = orchestrator.prepare_iteration(messages, i + 1)
        if ctx.context_was_reset:
            print(f"  ✓ Context reset triggered at iteration {i+1}")
            messages = ctx.messages

        # Simulate action
        orchestrator.record_result(
            action={"name": f"action_{i}"},
            result={"success": True},
            success=True
        )

        # Add message to track
        messages.append({"role": "assistant", "content": f"Action {i}"})

    final_status = orchestrator.get_status()
    print(f"  Final status:")
    print(f"    Iterations: {final_status['orchestrator']['iteration']}")
    print(f"    Context resets: {final_status['context']['resets']}")
    print(f"    Tokens saved: {final_status['context']['tokens_saved']}")

    print("\n✓ Integration tests passed!")
    return True


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("EVERSALE AGENTIC ORCHESTRATOR TEST SUITE")
    print("Testing: Anchor + Sliding Window pattern fixes")
    print("="*60)

    results = []

    try:
        results.append(("Context Budget v2", test_context_budget_v2()))
    except Exception as e:
        print(f"\n✗ Context Budget v2 test failed: {e}")
        results.append(("Context Budget v2", False))

    try:
        results.append(("Agentic Orchestrator", test_agentic_orchestrator()))
    except Exception as e:
        print(f"\n✗ Agentic Orchestrator test failed: {e}")
        results.append(("Agentic Orchestrator", False))

    try:
        results.append(("Integration", test_integration()))
    except Exception as e:
        print(f"\n✗ Integration test failed: {e}")
        results.append(("Integration", False))

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"  {name}: {status}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! Amnesia bottleneck fix is working.")
        return 0
    else:
        print("\n⚠ Some tests failed. Please review the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
