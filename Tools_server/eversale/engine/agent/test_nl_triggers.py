"""
Test Natural Language Triggers for UI-TARS Features

Tests all natural language patterns for:
1. System-2 reasoning triggers
2. ConversationContext triggers
3. Tiered retry config triggers
4. Coordinate normalization triggers
5. Existing patterns (navigation, click, type, search, extract)
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from command_parser import CommandParser, ActionType
from action_templates import find_template
from intelligent_task_router import route_task, ExecutionPath


def test_system2_triggers():
    """Test System-2 reasoning triggers"""
    print("\n=== Testing System-2 Reasoning Triggers ===")
    parser = CommandParser()

    test_cases = [
        "use system-2 reasoning",
        "enable system-2",
        "use thought and reflection",
        "enable thinking and reflection",
        "think before acting",
        "use deliberate reasoning",
    ]

    for prompt in test_cases:
        action = parser.parse(prompt)
        template = find_template(prompt)
        routing = route_task(prompt)

        print(f"\nPrompt: '{prompt}'")
        print(f"  Parser: {action.action_type.value if action.action_type != ActionType.UNKNOWN else 'UNKNOWN'}")
        print(f"  Template: {template.name if template else 'None'}")
        print(f"  Router: {routing.path.value} - {routing.reasoning}")

        # Assertions
        assert action.action_type == ActionType.ENABLE_SYSTEM2 or template is not None, \
            f"Failed to recognize System-2 trigger: '{prompt}'"


def test_conversation_context_triggers():
    """Test ConversationContext triggers"""
    print("\n=== Testing ConversationContext Triggers ===")
    parser = CommandParser()

    test_cases = [
        "take screenshot with context",
        "screenshot with context",
        "use conversation context",
        "enable context management",
        "keep screenshot history",
        "maintain screenshot context",
        "context-aware screenshot",
    ]

    for prompt in test_cases:
        action = parser.parse(prompt)
        template = find_template(prompt)
        routing = route_task(prompt)

        print(f"\nPrompt: '{prompt}'")
        print(f"  Parser: {action.action_type.value if action.action_type != ActionType.UNKNOWN else 'UNKNOWN'}")
        print(f"  Template: {template.name if template else 'None'}")
        print(f"  Router: {routing.path.value} - {routing.reasoning}")

        # Assertions
        assert action.action_type == ActionType.ENABLE_CONTEXT or template is not None, \
            f"Failed to recognize ConversationContext trigger: '{prompt}'"


def test_retry_config_triggers():
    """Test tiered retry config triggers"""
    print("\n=== Testing Tiered Retry Config Triggers ===")
    parser = CommandParser()

    test_cases = [
        "retry with tiered timeouts",
        "retry with tiered timeout",
        "use tiered retry",
        "use tiered timeouts",
        "enable smart retry",
        "use ui-tars retry",
        "retry with backoff",
        "retry with exponential backoff",
    ]

    for prompt in test_cases:
        action = parser.parse(prompt)
        template = find_template(prompt)
        routing = route_task(prompt)

        print(f"\nPrompt: '{prompt}'")
        print(f"  Parser: {action.action_type.value if action.action_type != ActionType.UNKNOWN else 'UNKNOWN'}")
        print(f"  Template: {template.name if template else 'None'}")
        print(f"  Router: {routing.path.value} - {routing.reasoning}")

        # Assertions
        assert action.action_type == ActionType.ENABLE_RETRY or template is not None, \
            f"Failed to recognize retry config trigger: '{prompt}'"


def test_coordinate_normalization_triggers():
    """Test coordinate normalization triggers"""
    print("\n=== Testing Coordinate Normalization Triggers ===")
    parser = CommandParser()

    test_cases = [
        "normalize coordinates",
        "normalize coordinate",
        "use normalized coordinates",
        "enable coordinate normalization",
        "use 0-1000 range",
        "use 0-1000 coordinates",
        "transform coordinates",
        "convert coordinates",
    ]

    for prompt in test_cases:
        action = parser.parse(prompt)
        template = find_template(prompt)
        routing = route_task(prompt)

        print(f"\nPrompt: '{prompt}'")
        print(f"  Parser: {action.action_type.value if action.action_type != ActionType.UNKNOWN else 'UNKNOWN'}")
        print(f"  Template: {template.name if template else 'None'}")
        print(f"  Router: {routing.path.value} - {routing.reasoning}")

        # Assertions
        assert action.action_type == ActionType.ENABLE_NORMALIZE or template is not None, \
            f"Failed to recognize coordinate normalization trigger: '{prompt}'"


def test_existing_patterns():
    """Test that existing NL patterns still work"""
    print("\n=== Testing Existing NL Patterns ===")
    parser = CommandParser()

    test_cases = [
        # Navigation
        ("go to google.com", ActionType.NAVIGATE),
        ("open https://github.com", ActionType.NAVIGATE),
        ("navigate to facebook.com", ActionType.NAVIGATE),

        # Click
        ("click Login button", ActionType.CLICK),
        ("click on the Submit button", ActionType.CLICK),
        ("press the Login button", ActionType.CLICK),

        # Type
        ("type 'hello world' in text field", ActionType.TYPE),
        ("enter 'test@example.com' in email field", ActionType.TYPE),
        ("fill username with 'admin'", ActionType.TYPE),

        # Search
        ("search for python tutorials", ActionType.SEARCH),
        ("find machine learning on google", ActionType.SEARCH),
        ("google artificial intelligence", ActionType.SEARCH),

        # Screenshot
        ("take screenshot", ActionType.SCREENSHOT),
        ("capture screen", ActionType.SCREENSHOT),
        ("screenshot", ActionType.SCREENSHOT),

        # Scroll
        ("scroll down", ActionType.SCROLL),
        ("scroll up", ActionType.SCROLL),
        ("scroll to bottom", ActionType.SCROLL),

        # Wait
        ("wait 5 seconds", ActionType.WAIT),
        ("pause for 3 seconds", ActionType.WAIT),
        ("wait", ActionType.WAIT),

        # Back/Forward
        ("go back", ActionType.BACK),
        ("navigate back", ActionType.BACK),
        ("go forward", ActionType.FORWARD),

        # Refresh
        ("refresh", ActionType.REFRESH),
        ("reload page", ActionType.REFRESH),

        # Close
        ("close tab", ActionType.CLOSE),
        ("exit browser", ActionType.CLOSE),
    ]

    for prompt, expected_type in test_cases:
        action = parser.parse(prompt)

        print(f"\nPrompt: '{prompt}'")
        print(f"  Expected: {expected_type.value}")
        print(f"  Got: {action.action_type.value if action.action_type != ActionType.UNKNOWN else 'UNKNOWN'}")

        # Assertions
        assert action.action_type == expected_type, \
            f"Failed to parse existing pattern: '{prompt}' (expected {expected_type.value}, got {action.action_type.value})"


def test_extraction_patterns():
    """Test extraction patterns"""
    print("\n=== Testing Extraction Patterns ===")

    test_cases = [
        "extract data from page",
        "get data from current page",
        "scrape listings",
        "collect information",
    ]

    for prompt in test_cases:
        template = find_template(prompt)

        print(f"\nPrompt: '{prompt}'")
        print(f"  Template: {template.name if template else 'None'}")

        # Should match extract_data template
        assert template is not None and template.name == "extract_data", \
            f"Failed to match extraction pattern: '{prompt}'"


def test_workflow_templates():
    """Test workflow templates and router detection (FB Ads, LinkedIn, Reddit, etc.)"""
    print("\n=== Testing Workflow Templates and Router Detection ===")

    test_cases = [
        # (prompt, expected_workflow_name) - router detection is primary
        ("search facebook ads for marketing agencies", "fb_ads"),
        ("fb ads library search for real estate", "fb_ads"),
        ("search linkedin for AI engineers", "linkedin"),
        ("find on linkedin data scientists", "linkedin"),
        ("search reddit for programming advice", "reddit"),
        ("find on reddit warm leads", "reddit"),
        ("google maps search for coffee shops", "google_maps"),
        ("open gmail", "gmail"),
        ("check gmail inbox", "gmail"),
    ]

    for prompt, expected_workflow in test_cases:
        template = find_template(prompt)
        routing = route_task(prompt)

        print(f"\nPrompt: '{prompt}'")
        print(f"  Template: {template.name if template else 'None'}")
        print(f"  Router: {routing.path.value} - {routing.workflow_name or 'None'}")

        # Router should detect workflow (deterministic path)
        # Template match is optional since router handles deterministic workflows
        assert routing.path == ExecutionPath.DETERMINISTIC and routing.workflow_name == expected_workflow, \
            f"Router failed to detect workflow: '{prompt}' (expected {expected_workflow}, got {routing.workflow_name})"


def run_all_tests():
    """Run all test suites"""
    print("=" * 70)
    print("NATURAL LANGUAGE TRIGGER TESTS")
    print("=" * 70)

    try:
        test_system2_triggers()
        test_conversation_context_triggers()
        test_retry_config_triggers()
        test_coordinate_normalization_triggers()
        test_existing_patterns()
        test_extraction_patterns()
        test_workflow_templates()

        print("\n" + "=" * 70)
        print("ALL TESTS PASSED!")
        print("=" * 70)

    except AssertionError as e:
        print("\n" + "=" * 70)
        print(f"TEST FAILED: {e}")
        print("=" * 70)
        raise


if __name__ == "__main__":
    run_all_tests()
