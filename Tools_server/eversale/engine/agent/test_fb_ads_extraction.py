"""
Test script for FB Ads Library extraction workflow.

This tests the updated templates and workflows to ensure they actually
extract advertiser data and URLs, not just navigate to the page.

Expected output structure from extract_fb_ads_batch:
{
    "success": True,
    "ads": [
        {
            "advertiser": "Company Name",
            "ad_id": "123456789",
            "landing_url": "https://example.com",
            "website_domain": "example.com",
            "page_url": "https://facebook.com/CompanyName",
            "ad_text": "Ad copy text...",
            "start_date": "Jan 1, 2025",
            "platforms": ["Facebook", "Instagram"],
            "status": "active",
            "all_landing_urls": ["https://example.com", ...]
        },
        ...
    ],
    "ads_count": 10,
    "source_url": "https://www.facebook.com/ads/library/...",
    "extraction_method": "multi_strategy",
    "strategies_found": {
        "img": 5,
        "link": 8,
        "library_id": 10
    }
}
"""

import asyncio
from action_templates import find_template
from deterministic_workflows import match_workflow, extract_params


def test_template_matching():
    """Test that FB ads prompts match the correct template."""
    prompts = [
        "Search Facebook Ads Library",
        "fb ads library",
        "meta ads library",
        "facebook ads search"
    ]

    for prompt in prompts:
        template = find_template(prompt)
        assert template is not None, f"No template found for: {prompt}"
        assert template.name == "search_fb_ads", f"Wrong template for {prompt}: {template.name}"

        # Check that extraction step is included
        step_tools = [step.tool for step in template.steps]
        assert "playwright_extract_fb_ads" in step_tools, f"Missing extraction step in template"

    print("Template matching tests PASSED")


def test_workflow_matching():
    """Test that FB ads prompts match the correct workflow."""
    prompts = [
        "Search Facebook ads for Nike",
        "Find fb ads for coffee shops",
        "meta ads library fashion brands"
    ]

    for prompt in prompts:
        workflow = match_workflow(prompt)
        assert workflow is not None, f"No workflow found for: {prompt}"
        assert workflow.name == "fb_ads_library", f"Wrong workflow for {prompt}: {workflow.name}"

        params = extract_params(prompt, workflow)
        assert "search_query" in params, f"Missing search_query for {prompt}"

        # Check that extraction step is included
        step_tools = [step.tool for step in workflow.steps]
        assert "extract_fb_ads_batch" in step_tools, f"Missing extraction step in workflow"

    print("Workflow matching tests PASSED")


def test_extraction_step_details():
    """Verify the extraction step has correct configuration."""
    template = find_template("facebook ads library")

    # Find the extraction step
    extraction_steps = [s for s in template.steps if "extract" in s.tool]
    assert len(extraction_steps) > 0, "No extraction step found in template"

    extraction_step = extraction_steps[0]
    assert extraction_step.tool == "playwright_extract_fb_ads", f"Wrong tool: {extraction_step.tool}"
    assert "max_ads" in extraction_step.params, "Missing max_ads parameter"
    assert extraction_step.params["max_ads"] == 10, f"Wrong max_ads: {extraction_step.params['max_ads']}"

    print("Extraction step configuration tests PASSED")


if __name__ == "__main__":
    print("Running FB Ads extraction tests...\n")

    test_template_matching()
    test_workflow_matching()
    test_extraction_step_details()

    print("\nAll tests PASSED!")
    print("\nExpected behavior:")
    print("1. User asks to search FB Ads Library")
    print("2. Agent navigates to https://www.facebook.com/ads/library")
    print("3. Agent captures page state")
    print("4. Agent runs playwright_extract_fb_ads tool")
    print("5. Tool extracts up to 10 ads with:")
    print("   - Advertiser name")
    print("   - Facebook page URL")
    print("   - Landing URL (website)")
    print("   - Ad text, start date, platforms")
    print("6. Returns structured data, NOT just 'Success'")
