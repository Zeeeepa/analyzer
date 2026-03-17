# Google Maps URL Extraction - Implementation Summary

## Overview

Improved the Google Maps template in the CLI agent to properly extract business listing URLs. The template now returns actual Google Maps place URLs in the format:
```
https://www.google.com/maps/place/Business+Name/@latitude,longitude,zoom/...
```

## Changes Made

### 1. Added Google Maps Selectors (`utils/site_selectors.py`)

Added comprehensive CSS selectors for Google Maps to enable accurate extraction:

```python
"google.com/maps": {
    "item_selector": "div[role='article'], a[href*='/maps/place/']",
    "field_selectors": {
        "business_name": "div[aria-label]:first-of-type, .fontHeadlineSmall, div.fontHeadlineLarge",
        "address": "div[aria-label*='Address'], .fontBodyMedium",
        "phone": "div[aria-label*='Phone'], button[aria-label*='Phone']",
        "website": "a[aria-label*='Website']@href",
        "rating": "span[role='img'][aria-label*='stars']@aria-label",
        "reviews": "span[aria-label*='reviews']",
        "url": "a[href*='/maps/place/']@href"  # KEY: Extracts Google Maps place URL
    },
    "limit": 20
}
```

**Key improvement**: The `url` field uses `@href` syntax to extract the actual href attribute from links, providing full Google Maps place URLs.

### 2. Updated Workflow (`deterministic_workflows.py`)

Improved the `GOOGLE_MAPS_WORKFLOW` to use proper extraction:

**Before**:
```python
WorkflowStep(
    tool="extract",  # Generic tool that doesn't exist
    args={
        "selector": "div[role='article']",
        "fields": ["business_name", "address", "phone", "website", "rating", "reviews"]
    },
    description="Extract business data"
)
```

**After**:
```python
WorkflowStep(
    tool="extract_list_auto",  # Uses site_selectors.py for accurate extraction
    args={"limit": 20},
    description="Extract business data with URLs using site selectors"
)
```

**Additional improvements**:
- Increased wait time from 2s to 3s for better page load
- Adjusted scroll amount to 800px for optimal result loading
- Added skip error strategy for scroll (non-critical)
- Updated description to mention URL extraction

### 3. Updated Action Template (`action_templates.py`)

Enhanced the `search_google_maps` template to include full workflow:

**Before**:
```python
steps=[
    ActionStep("playwright_navigate", {"url": "https://www.google.com/maps"}, "Navigate to Google Maps"),
    ActionStep("playwright_snapshot", {}, "Capture initial map state"),
]
```

**After**:
```python
steps=[
    ActionStep("playwright_navigate", {"url": "https://www.google.com/maps/search/{query}"}, "Navigate to Google Maps search"),
    ActionStep("playwright_wait", {"time": 3}, "Wait for results to load"),
    ActionStep("playwright_scroll", {"direction": "down", "amount": 800}, "Scroll to load more results"),
    ActionStep("playwright_extract_list", {"limit": 20}, "Extract business listings with URLs"),
]
```

### 4. Improved Pattern Matching

Added "search maps" pattern to workflow matcher for better prompt recognition.

## Usage

Users can now use any of these prompts:

```
eversale "google maps coffee shops in Seattle"
eversale "find businesses restaurants in NYC"
eversale "search maps for dentists near me"
eversale "local businesses plumbers in Boston"
```

## Expected Output Format

```json
{
    "success": true,
    "data": [
        {
            "business_name": "Starbucks",
            "address": "1234 Pike St, Seattle, WA 98101",
            "phone": "(206) 555-1234",
            "website": "https://www.starbucks.com",
            "rating": "4.2 stars",
            "reviews": "523 reviews",
            "url": "https://www.google.com/maps/place/Starbucks/@47.6097,-122.3331,17z/data=..."
        },
        {
            "business_name": "Local Coffee Shop",
            "address": "5678 Main St, Seattle, WA 98102",
            "phone": "(206) 555-5678",
            "website": "https://localcoffee.com",
            "rating": "4.8 stars",
            "reviews": "234 reviews",
            "url": "https://www.google.com/maps/place/Local+Coffee+Shop/@47.6142,-122.3201,17z/..."
        }
    ],
    "count": 20,
    "url": "https://www.google.com/maps/search/coffee+shops+in+Seattle"
}
```

## Key Benefits

1. **Actual URLs**: Each business now includes its full Google Maps place URL
2. **Accurate Extraction**: Uses CSS selectors instead of LLM guessing
3. **Complete Data**: Extracts business name, address, phone, website, rating, reviews, AND URL
4. **Reliable**: No dependency on LLM interpretation for extraction
5. **Fast**: Direct DOM extraction is faster than LLM-based extraction

## Files Modified

1. `/mnt/c/ev29/cli/engine/agent/utils/site_selectors.py` - Added Google Maps selectors
2. `/mnt/c/ev29/cli/engine/agent/deterministic_workflows.py` - Updated workflow to use extract_list_auto
3. `/mnt/c/ev29/cli/engine/agent/action_templates.py` - Enhanced template with full workflow

## Testing

Created test script at `/mnt/c/ev29/cli/engine/agent/test_google_maps_extraction.py`

Run with:
```bash
cd /mnt/c/ev29/cli/engine/agent
python3 test_google_maps_extraction.py
```

All tests pass successfully.

## Technical Details

### Selector Strategy

The selector uses multiple fallback patterns for robustness:

- **Item selector**: Matches business cards (`div[role='article']`) or place links
- **Field selectors**: Use aria-labels and class names for accessibility
- **URL extraction**: Specifically targets links with `/maps/place/` in href

### Attribute Extraction

The `@href` syntax in field selectors tells the extractor to:
1. Find the element matching the selector
2. Extract the `href` attribute instead of text content
3. Return the full URL

Example:
```python
"url": "a[href*='/maps/place/']@href"
```
This means: Find `<a>` tags with `/maps/place/` in href, extract the href attribute value.

## Implementation Philosophy

Follows the "Make it work first" philosophy:
- Uses known patterns (site_selectors.py) for deterministic extraction
- No LLM involvement in extraction (faster, more reliable)
- Simple CSS selectors over complex logic
- Graceful degradation (scroll can fail without breaking workflow)

## Future Enhancements

Potential improvements:
1. Add pagination support for more than 20 results
2. Extract additional fields (opening hours, price level)
3. Add filtering options (rating threshold, distance)
4. Support for clicking into individual listings for more details
