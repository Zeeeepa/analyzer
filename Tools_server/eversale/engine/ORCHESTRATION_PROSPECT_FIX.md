# Orchestration Prospect Display Fix

## Problem
When extraction tools returned prospect data, the orchestration layer was showing URLs instead of prospect names/details in the goal results.

## Root Cause
The template result handling in `orchestration.py` (lines 739-790) was checking for extracted data using `result.get("data")` etc., but wasn't robustly handling all cases where:
1. Data might be in different keys (ads, items, posts, listings, etc.)
2. ToolResult objects with nested data structures
3. Cases where no data was extracted

## Solution
Enhanced the prospect extraction and display logic in `/mnt/c/ev29/cli/engine/agent/orchestration.py`:

### Changes Made (lines 739-815)

#### 1. More Robust Data Extraction
- Changed from OR chain to explicit loop through all possible data keys
- Added clear `extracted_data` variable to track what was found
- Added placeholder for future ToolResult nested data handling

```python
# Before: OR chain
extracted_data = (
    result.get("data") or
    result.get("items") or
    # ...
)

# After: Explicit loop with early break
extracted_data = None
for key in ['data', 'items', 'ads', 'posts', 'listings', 'results', 'profiles']:
    data = result.get(key)
    if data and isinstance(data, list) and len(data) > 0:
        extracted_data = data
        break
```

#### 2. Enhanced Prospect Name Extraction
Added more field options for finding prospect names:
- `business_name` (for local business listings)
- `company` (for company directories)

```python
prospect_name = (
    first_item.get("advertiser") or
    first_item.get("title") or
    first_item.get("name") or
    first_item.get("author") or
    first_item.get("business_name") or  # NEW
    first_item.get("company") or         # NEW
    first_item.get("link", "")[:60]
)
```

#### 3. Enhanced URL Extraction
Added `website` as fallback option:

```python
prospect_url = (
    first_item.get("url") or
    first_item.get("link") or
    first_item.get("landing_url") or
    first_item.get("website")  # NEW
)
```

#### 4. MANDATORY Output - Always Show Something
Added guaranteed fallback to show prospect data even if fields are missing:

```python
# MANDATORY: Always show at least prospect name or URL
if prospect_name and prospect_url:
    summary_parts.append(f"Prospect: {prospect_name} | {prospect_url}")
elif prospect_name:
    summary_parts.append(f"Prospect: {prospect_name}")
elif prospect_url:
    summary_parts.append(f"Prospect: {prospect_url}")
else:
    # Show whatever we can find
    summary_parts.append(f"Prospect: {str(first_item)[:100]}")
```

#### 5. Better "No Results" Messages
When no prospects are extracted, the system now intelligently explains why:

```python
# MANDATORY: If no prospects extracted, explain why
elif result.get("url"):
    # Check if this was an extraction attempt
    template_name = template.name.lower()
    if any(word in template_name for word in ['extract', 'find', 'search', 'scrape', 'collect']):
        summary_parts.append(f"No prospects found - check {result['url']}")
    else:
        summary_parts.append(f"URL: {result['url']}")
```

#### 6. Consistent Count Display
Changed wording from "Found X results" to "Found X total" for clarity.

## Testing

### Unit Tests
Created test script at `/mnt/c/ev29/cli/test_orchestration_fix.py` that validates:

1. **Test 1**: Ads with advertiser + URL
   - Input: Result with 'ads' key containing 2 prospects
   - Output: `Prospect: Test Company 1 | https://example.com/company1 - (Found 2 total)`

2. **Test 2**: Data with name + website
   - Input: Result with 'data' key containing local business
   - Output: `Prospect: Best Local Service | https://localbiz.com - (Found 1 total)`

3. **Test 3**: No extracted data (extraction template)
   - Input: Result with URL but no prospect data
   - Output: `No prospects found - check https://example.com`

4. **Test 4**: Items with only link field
   - Input: Result with 'items' key, no name/advertiser
   - Output: `Prospect: https://example.com/item1 | https://example.com/item1 - (Found 1 total)`

All tests passed successfully.

### Import Validation
Verified that module imports correctly:
```bash
python3 -c "from agent.orchestration import OrchestrationMixin; print('Success')"
# Output: Success (with normal warnings)
```

## Impact

### Before
- Prospect data often showed as URLs only
- Inconsistent display format
- Missing data when fields had different names

### After
- Always shows prospect name when available
- Consistent format: "Prospect: {name} | {url}"
- Handles multiple field name variations (advertiser, title, name, business_name, company)
- Mandatory output - always shows something meaningful
- Clear "No prospects found" messages for failed extractions

## Files Modified
- `/mnt/c/ev29/cli/engine/agent/orchestration.py` (lines 739-815)

## Files Created
- `/mnt/c/ev29/cli/test_orchestration_fix.py` (test script)
- `/mnt/c/ev29/cli/engine/ORCHESTRATION_PROSPECT_FIX.md` (this document)

## Backwards Compatibility
The changes are fully backwards compatible:
- All existing result formats still work
- Added fields are optional (fallback chain)
- Import signatures unchanged
- No breaking changes to API

## Next Steps (Optional Future Enhancements)
1. Add handling for ToolResult objects with deeply nested data
2. Add more field name variations based on real-world usage
3. Add configurable output format templates
4. Add prospect data validation/sanitization
