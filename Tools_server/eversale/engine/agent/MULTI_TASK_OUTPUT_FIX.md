# Multi-Task Output Format Fix

## Problem

When running multiple tasks in sequence (e.g., "Go to FB Ads... Go to Reddit..."), the output format handler was getting confused:

1. Each task executes and returns its own result
2. Results are compiled into a summary: "Goal 1: ..., Goal 2: ..., Goal 3: ..."
3. `format_output(original_prompt, summary)` is called
4. The formatter tried to apply the template to the SUMMARY string, not individual task results
5. Result: Format gets mixed up, data attributed to wrong tasks

## Solution

Enhanced `output_format_handler.py` with multi-task awareness:

### Key Changes

1. **Multi-task detection** (`_is_multi_task_result`):
   - Detects "Goal N:" or "Task N:" patterns in result strings
   - If 2+ tasks found, triggers special handling

2. **Multi-task formatting** (`_format_multi_task_result`):
   - Splits result into individual task sections
   - Extracts structured data from each task separately
   - Applies format template to each task independently
   - Combines formatted tasks with clear separation

3. **Selective template application** (`_apply_selective_template`):
   - Only shows template lines with actual data
   - Prevents "N/A" spam for irrelevant fields
   - Each task only shows its relevant output lines

4. **Data extraction** (`_extract_data_from_task_result`):
   - Extracts URLs and categorizes by domain (FB, Reddit, LinkedIn, etc.)
   - Extracts usernames, advertiser names, etc.
   - Returns structured dict for template application

## Example

### Input (Multi-Task Result)
```
Goal 1: Found 3 FB advertiser(s): ACME Corp
  URL: https://facebook.com/ads/123
Goal 2: Found thread at https://reddit.com/r/leadgen/456 by u/sales_expert
```

### User's Format Spec
```
Format:
FB_PROSPECT_URL: <url>
REDDIT: thread=<url> user=<username>
```

### Output (Before Fix)
```
FB_PROSPECT_URL: N/A
REDDIT: thread=N/A user=N/A
```
(Tried to apply format to the summary text, failed)

### Output (After Fix)
```
Goal 1:
FB_PROSPECT_URL: https://facebook.com/ads/123

Goal 2:
REDDIT: thread=https://reddit.com/r/leadgen/456 user=sales_expert
```

## Benefits

- Clear task separation - no confusion about which data belongs to which task
- No cross-contamination - each task's data stays isolated
- Clean output - only shows relevant fields per task (no N/A spam)
- Maintains task labels - users can see "Goal 1:", "Goal 2:", etc.

## Files Modified

- `/mnt/c/ev29/cli/engine/agent/output_format_handler.py` (NEW)
  - Added `_is_multi_task_result()`
  - Added `_format_multi_task_result()`
  - Added `_apply_selective_template()`
  - Added `_extract_data_from_task_result()`
  - Enhanced `format_output()` with multi-task handling

## Testing

All tests pass:
- Multi-task detection works correctly
- Data extraction categorizes URLs by domain
- Template application is selective (only relevant fields)
- No cross-contamination between tasks
- Integration with full workflow works
