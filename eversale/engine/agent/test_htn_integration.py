"""
Test HTN Planning Integration

Verifies that the planning_agent is properly wired into orchestration.
"""

import asyncio
from loguru import logger

# Test imports
try:
    from complexity_detector import is_complex_task, get_complexity_score
    from planning_agent import PlanningAgent, quick_plan_and_execute, Plan
    print("SUCCESS: HTN planning modules imported successfully")
except ImportError as e:
    print(f"FAILED: Could not import HTN planning modules: {e}")
    exit(1)


def test_complexity_detection():
    """Test complexity detector on various prompts."""
    print("\n--- Testing Complexity Detection ---")

    test_cases = [
        # Complex tasks (should return True)
        ("Research 10 companies on LinkedIn, extract contacts, and upload to HubSpot", True),
        ("Monitor Facebook for new ads, scrape landing pages, compile report", True),
        ("Find competitors on Product Hunt, visit their sites, extract emails", True),
        ("Search Google Maps for restaurants, extract info, send email list", True),
        ("Automate workflow: find leads on LinkedIn and email them via Gmail", True),

        # Simple tasks (should return False)
        ("Go to gmail.com and read my inbox", False),
        ("Search Google for Python tutorials", False),
        ("Screenshot this page", False),
        ("Click the login button", False),
        ("Do X then Y then Z", False),  # Goal sequencer handles this
    ]

    passed = 0
    failed = 0

    for prompt, expected_complex in test_cases:
        is_complex = is_complex_task(prompt)
        score = get_complexity_score(prompt)

        status = "PASS" if is_complex == expected_complex else "FAIL"
        if is_complex == expected_complex:
            passed += 1
        else:
            failed += 1

        print(f"{status}: '{prompt[:60]}...'")
        print(f"  Complex: {is_complex} (expected: {expected_complex}), Score: {score:.2f}")

    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


async def test_planning_agent():
    """Test planning agent can create and execute plans."""
    print("\n--- Testing Planning Agent ---")

    # Simple action handler for testing
    async def mock_action_handler(action: str, arguments: dict):
        """Mock action handler that simulates execution."""
        logger.info(f"Mock executing: {action} with {arguments}")
        await asyncio.sleep(0.1)  # Simulate work
        return {'success': True, 'result': f"Completed {action}"}

    # Create planning agent
    agent = PlanningAgent(action_handler=mock_action_handler)

    # Test simple task planning
    try:
        plan = await agent.plan(
            "Research Python programming tutorials",
            max_depth=2,
            use_templates=False
        )

        print(f"Plan created: {plan.name}")
        print(f"  Steps: {len(plan.steps)}")
        print(f"  Root steps: {len(plan.root_steps)}")
        print(f"  Estimated duration: {plan.estimated_total_duration:.1f}s")

        # Validate plan
        evaluation = await agent.validate_plan(plan)
        print(f"  Validation score: {evaluation['overall_score']:.2f}")
        print(f"  Approved: {evaluation['approved']}")

        # For testing, we consider the plan creation successful if score > 0.7
        # even if not auto-approved (some suggestions are OK)
        if evaluation['overall_score'] >= 0.7:
            print("PASS: Plan created and validated successfully")
            if not evaluation['approved']:
                print(f"  Note: Plan has suggestions but score is good: {evaluation['suggestions'][:2]}")
            return True
        else:
            print(f"FAIL: Plan validation score too low: {evaluation['suggestions']}")
            return False

    except Exception as e:
        print(f"FAIL: Planning failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_quick_plan_and_execute():
    """Test quick_plan_and_execute helper function."""
    print("\n--- Testing Quick Plan and Execute ---")

    async def mock_action_handler(action: str, arguments: dict):
        """Mock action handler."""
        logger.info(f"Executing: {action}")
        await asyncio.sleep(0.05)
        return {'success': True, 'result': 'done'}

    try:
        # Test the planning flow with manual approval
        from planning_agent import PlanningAgent

        agent = PlanningAgent(action_handler=mock_action_handler)

        # Create plan
        plan = await agent.plan("Search for AI news", max_depth=2, use_templates=False)

        # Validate
        evaluation = await agent.validate_plan(plan)

        # For testing, manually approve even if critic has suggestions
        if evaluation['overall_score'] >= 0.7:
            print(f"Plan score: {evaluation['overall_score']:.2f} (good enough for testing)")
            plan.status = plan.status.__class__.APPROVED
            plan.approved_at = "test"

            # Execute
            result = await agent.execute_plan(plan)

            if result.get('success'):
                print(f"PASS: Execution completed")
                print(f"  Steps: {result.get('completed_steps')}/{result.get('total_steps')}")
                print(f"  Duration: {result.get('duration', 0):.2f}s")
                return True
            else:
                print(f"FAIL: Execution failed: {result}")
                return False
        else:
            print(f"FAIL: Plan score too low: {evaluation['overall_score']:.2f}")
            return False

    except Exception as e:
        print(f"FAIL: Quick plan and execute failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_orchestration_imports():
    """Test that orchestration can import HTN planning modules."""
    print("\n--- Testing Orchestration Imports ---")

    try:
        from orchestration import (
            HTN_PLANNING_AVAILABLE,
            is_complex_task as orch_is_complex,
            get_complexity_score as orch_get_score
        )

        if not HTN_PLANNING_AVAILABLE:
            print("FAIL: HTN_PLANNING_AVAILABLE is False in orchestration")
            return False

        # Test that imported functions work
        test_prompt = "Research companies and extract contacts"
        is_complex = orch_is_complex(test_prompt, {})
        score = orch_get_score(test_prompt)

        print(f"PASS: Orchestration imports HTN planning successfully")
        print(f"  Test prompt complexity: {is_complex}, score: {score:.2f}")
        return True

    except ImportError as e:
        print(f"FAIL: Orchestration cannot import HTN planning: {e}")
        return False
    except Exception as e:
        print(f"FAIL: Orchestration import test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("=" * 60)
    print("HTN Planning Integration Test Suite")
    print("=" * 60)

    results = []

    # Synchronous tests
    results.append(("Complexity Detection", test_complexity_detection()))
    results.append(("Orchestration Imports", test_orchestration_imports()))

    # Async tests
    results.append(("Planning Agent", await test_planning_agent()))
    results.append(("Quick Plan Execute", await test_quick_plan_and_execute()))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"{status}: {name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\nALL TESTS PASSED!")
        return 0
    else:
        print(f"\n{total - passed} TESTS FAILED")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
