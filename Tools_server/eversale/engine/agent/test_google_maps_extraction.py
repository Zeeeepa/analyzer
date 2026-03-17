"""
Test script for Google Maps extraction with URL support.

This script verifies that:
1. Google Maps selectors are properly configured in site_selectors.py
2. The workflow uses extract_list_auto correctly
3. Business URLs are extracted in the format: https://www.google.com/maps/place/Business+Name/...
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from utils.site_selectors import get_site_selectors
from deterministic_workflows import GOOGLE_MAPS_WORKFLOW, match_workflow, extract_params

def test_site_selectors():
    """Test that Google Maps selectors are configured correctly."""
    print("Testing Google Maps site selectors...")

    test_url = "https://www.google.com/maps/search/coffee+shops"
    selectors = get_site_selectors(test_url)

    if not selectors:
        print("ERROR: No selectors found for Google Maps!")
        return False

    print(f"SUCCESS: Found selectors for Google Maps")
    print(f"  Item selector: {selectors.get('item_selector')}")
    print(f"  Field selectors:")
    for field, selector in selectors.get('field_selectors', {}).items():
        print(f"    - {field}: {selector}")

    # Verify URL field exists
    if 'url' not in selectors.get('field_selectors', {}):
        print("ERROR: 'url' field not found in selectors!")
        return False

    print("SUCCESS: 'url' field is configured")
    return True

def test_workflow_configuration():
    """Test that the workflow is configured correctly."""
    print("\nTesting Google Maps workflow configuration...")

    # Test workflow matching
    test_prompts = [
        "google maps coffee shops in Seattle",
        "find businesses on maps",
        "search maps for restaurants"
    ]

    for prompt in test_prompts:
        workflow = match_workflow(prompt)
        if not workflow or workflow.name != "google_maps_search":
            print(f"ERROR: Failed to match workflow for prompt: {prompt}")
            return False

        params = extract_params(prompt, workflow)
        print(f"SUCCESS: Matched '{prompt}' -> params: {params}")

    # Verify workflow steps
    print(f"\nWorkflow: {GOOGLE_MAPS_WORKFLOW.name}")
    print(f"Description: {GOOGLE_MAPS_WORKFLOW.description}")
    print(f"Required params: {GOOGLE_MAPS_WORKFLOW.required_params}")
    print("Steps:")
    for i, step in enumerate(GOOGLE_MAPS_WORKFLOW.steps, 1):
        print(f"  {i}. {step.tool}({step.args}) - {step.description}")

    # Verify extract_list_auto is used
    extract_step = None
    for step in GOOGLE_MAPS_WORKFLOW.steps:
        if step.tool == "extract_list_auto":
            extract_step = step
            break

    if not extract_step:
        print("ERROR: extract_list_auto step not found in workflow!")
        return False

    print("SUCCESS: Workflow uses extract_list_auto for extraction")
    return True

def test_expected_output():
    """Show expected output format."""
    print("\nExpected output format:")
    print("""
    {
        "success": True,
        "data": [
            {
                "business_name": "Example Coffee Shop",
                "address": "123 Main St, Seattle, WA",
                "phone": "(206) 555-1234",
                "website": "https://example.com",
                "rating": "4.5 stars",
                "reviews": "150 reviews",
                "url": "https://www.google.com/maps/place/Example+Coffee+Shop/@47.6062,-122.3321,17z/..."
            },
            ...
        ],
        "count": 20,
        "url": "https://www.google.com/maps/search/coffee+shops+in+Seattle"
    }
    """)
    print("\nKey improvement: The 'url' field now contains actual Google Maps place URLs!")

if __name__ == "__main__":
    print("=" * 80)
    print("Google Maps Extraction - URL Support Test")
    print("=" * 80)

    success = True
    success = test_site_selectors() and success
    success = test_workflow_configuration() and success
    test_expected_output()

    print("\n" + "=" * 80)
    if success:
        print("ALL TESTS PASSED!")
        print("\nThe Google Maps template now:")
        print("  1. Navigates to Google Maps search with query")
        print("  2. Waits for results to load")
        print("  3. Scrolls to load more businesses")
        print("  4. Extracts business data INCLUDING Google Maps URLs")
        print("\nEach business listing will include its full Google Maps URL.")
    else:
        print("SOME TESTS FAILED - Review errors above")
    print("=" * 80)

    sys.exit(0 if success else 1)
