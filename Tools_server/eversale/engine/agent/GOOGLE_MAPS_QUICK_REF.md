# Google Maps Business Extraction - Quick Reference

## What Changed

The Google Maps template now extracts **actual Google Maps URLs** for each business listing.

## Example Usage

```bash
eversale "google maps coffee shops in Seattle"
```

## Output

Each business listing now includes a `url` field with the full Google Maps place URL:

```json
{
  "business_name": "Starbucks Reserve Roastery",
  "address": "1124 Pike St, Seattle, WA 98101",
  "phone": "(206) 624-0173",
  "website": "https://www.starbucksreserve.com/en-us/locations/seattle",
  "rating": "4.5 stars",
  "reviews": "12,345 reviews",
  "url": "https://www.google.com/maps/place/Starbucks+Reserve+Roastery/@47.6126,-122.3345,17z/data=..."
}
```

## Supported Prompts

- `"google maps [your search]"`
- `"find businesses [your search]"`
- `"search maps for [your search]"`
- `"local businesses [your search]"`
- `"maps search [your search]"`

## Technical Details

### How It Works

1. **Navigate**: Opens Google Maps search with your query
2. **Wait**: Allows 3 seconds for results to load
3. **Scroll**: Scrolls 800px down to load more results
4. **Extract**: Uses CSS selectors to extract business data including URLs

### Extracted Fields

- `business_name` - Business name
- `address` - Full address
- `phone` - Phone number (if available)
- `website` - Business website (if available)
- `rating` - Star rating (e.g., "4.5 stars")
- `reviews` - Review count (e.g., "523 reviews")
- `url` - **Full Google Maps place URL** (NEW!)

### Limits

- Extracts up to 20 businesses per search
- Results depend on Google Maps availability
- Some fields may be empty if not available on Google Maps

## Files Modified

1. `utils/site_selectors.py` - Added Google Maps CSS selectors
2. `deterministic_workflows.py` - Updated workflow to use proper extraction
3. `action_templates.py` - Enhanced template with full extraction steps

## For Developers

The implementation uses:
- **Site selectors**: Predefined CSS selectors in `site_selectors.py`
- **extract_list_auto**: Automatic selector-based extraction (no LLM)
- **Attribute extraction**: `@href` syntax to extract URL attributes

Example selector:
```python
"url": "a[href*='/maps/place/']@href"
```

This finds `<a>` tags containing `/maps/place/` and extracts their `href` attribute.
