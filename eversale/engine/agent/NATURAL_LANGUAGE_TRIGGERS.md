# Natural Language Triggers - Quick Reference

Fast-track common browser operations without LLM overhead.

## What Are Natural Language Triggers?

Natural language triggers are shortcuts that let users execute common browser operations instantly by matching specific phrases in their prompts. When a trigger matches, the action executes directly without LLM processing - zero tokens, instant results.

## Benefits

- **Zero LLM tokens** - No API costs for common operations
- **Instant execution** - No planning/reasoning delay
- **Predictable output** - Consistent JSON structure
- **Lower latency** - Sub-second response times

## Trigger Categories

### 1. CDP/Session Reuse

Connect to your existing Chrome browser to preserve logged-in sessions.

**Triggers:**
- "use my chrome"
- "use existing chrome"
- "connect to my browser"
- "use my browser"
- "keep me logged in"
- "use my logins"
- "preserve session"
- "stay logged in"

**What it does:**
- Connects to Chrome via CDP (Chrome DevTools Protocol)
- Preserves all logged-in sessions
- No need to re-authenticate

**Requirements:**
- Launch Chrome with: `chrome --remote-debugging-port=9222`

**Example:**
```python
result = await client.process_natural_language("use my chrome")
# -> Connects to existing Chrome, all logins preserved
```

---

### 2. Direct Extraction (No LLM)

Extract structured data instantly without LLM processing.

#### Links

**Triggers:**
- "extract links"
- "get all links"
- "find all links"
- "list links"
- "extract links containing X" (with filter)

**Output:**
```json
{
  "success": true,
  "links": [
    {"text": "Example", "href": "https://example.com", "mmid": "mm1"},
    ...
  ],
  "count": 10
}
```

#### Forms

**Triggers:**
- "extract forms"
- "find forms"
- "get forms"
- "list forms"

**Output:**
```json
{
  "success": true,
  "forms": [
    {
      "action": "/submit",
      "method": "POST",
      "fields": [...]
    }
  ],
  "count": 2
}
```

#### Input Fields

**Triggers:**
- "extract inputs"
- "find inputs"
- "get input fields"
- "list fields"

**Output:**
```json
{
  "success": true,
  "inputs": [
    {
      "type": "text",
      "name": "email",
      "placeholder": "Enter email",
      "mmid": "mm5"
    }
  ],
  "count": 5
}
```

#### Tables

**Triggers:**
- "extract tables"
- "get table data"
- "find tables"
- "scrape table"

**Output:**
```json
{
  "success": true,
  "tables": [
    {
      "headers": ["Name", "Price"],
      "rows": [...]
    }
  ],
  "count": 1
}
```

#### Contact Forms

**Triggers:**
- "extract contact form"
- "find contact form"
- "get contact info"

**Output:**
```json
{
  "success": true,
  "contact_forms": [...]
}
```

---

### 3. Debug Output (DevTools)

Access browser console and network debugging data.

**Requirements:**
- Must call `playwright_enable_mcp_features` first to start capturing

#### Network Errors

**Triggers:**
- "show network errors"
- "what failed"
- "debug requests"
- "failed requests"
- "network failures"
- "api errors"

**Output:**
```json
{
  "success": true,
  "failed_requests": [
    {
      "url": "https://api.example.com/data",
      "method": "GET",
      "status": 404,
      "error": "Not Found"
    }
  ],
  "count": 1
}
```

#### Console Errors

**Triggers:**
- "show console errors"
- "check for errors"
- "javascript errors"
- "console log errors"
- "browser errors"

**Output:**
```json
{
  "success": true,
  "errors": [
    {
      "type": "error",
      "message": "Uncaught TypeError...",
      "source": "main.js:42"
    }
  ]
}
```

#### All Console Logs

**Triggers:**
- "show console"
- "console logs"
- "browser logs"

#### Network Requests

**Triggers:**
- "show network"
- "network requests"
- "api calls"

---

### 4. Quick Inspect (No Browser)

Fast HTML parsing without browser overhead.

**Triggers:**
- "quick extract"
- "parse this html"
- "no browser extract"
- "fast extract"
- "parse html"

**What it does:**
- Parses current page HTML instantly
- No browser rendering overhead
- Extracts links, forms, headings, etc.

**Output:**
```json
{
  "success": true,
  "links_count": 15,
  "forms_count": 2,
  "headings": {
    "h1": ["Welcome"],
    "h2": ["Features", "Pricing"]
  },
  "title": "Example Page"
}
```

---

## Integration Guide

### Basic Usage

```python
from playwright_direct import PlaywrightClient

client = PlaywrightClient()
await client.connect()
await client.navigate("https://example.com")

# Try natural language trigger
result = await client.process_natural_language("extract all links")

if result:
    # Trigger matched - instant result
    print(f"Found {result['count']} links")
else:
    # No trigger - use LLM planning
    result = await llm_based_planning(prompt)
```

### Integration with LLM Planning

```python
async def handle_user_prompt(prompt: str):
    """Check triggers first, fall back to LLM."""

    # Step 1: Check for natural language trigger
    result = await playwright_client.process_natural_language(prompt)

    if result:
        # Direct action executed - return immediately
        return result

    # Step 2: No trigger matched - use LLM planning
    plan = await llm_client.create_plan(prompt)
    result = await execute_plan(plan)

    return result
```

### Enabling Debug Features

```python
# Enable MCP features for debugging
await client.call_tool('playwright_enable_mcp_features', {
    'enable_console': True,
    'enable_network': True
})

# Navigate to page
await client.navigate("https://example.com")

# Now debug triggers will work
result = await client.process_natural_language("show network errors")
```

---

## Complete Trigger List

| Category | Triggers | LLM Bypass | Requirements |
|----------|----------|------------|--------------|
| **CDP** | "use my chrome", "keep me logged in" | No | Chrome with `--remote-debugging-port=9222` |
| **Links** | "extract links", "get all links" | Yes | Page loaded |
| **Forms** | "extract forms", "find forms" | Yes | Page loaded |
| **Inputs** | "extract inputs", "list fields" | Yes | Page loaded |
| **Tables** | "extract tables", "get table data" | Yes | Page loaded |
| **Contacts** | "extract contact form" | Yes | Page loaded |
| **Network Errors** | "show network errors", "what failed" | Yes | MCP features enabled |
| **Console Errors** | "show console errors", "browser errors" | Yes | MCP features enabled |
| **Console Logs** | "show console", "console logs" | Yes | MCP features enabled |
| **Network** | "show network", "api calls" | Yes | MCP features enabled |
| **Quick Parse** | "quick extract", "parse html" | Yes | Page loaded |

---

## Performance Comparison

| Method | Latency | Cost | Use Case |
|--------|---------|------|----------|
| **Natural Language Trigger** | <100ms | $0 | Common operations |
| **LLM Planning** | 1-3s | $0.01-0.05 | Complex reasoning |

**When to use triggers:**
- Repetitive extractions
- Debugging workflows
- Known data patterns
- Cost-sensitive operations

**When to use LLM:**
- Complex multi-step tasks
- Ambiguous instructions
- Decision-making needed
- Unknown page structure

---

## Adding New Triggers

To add a new trigger pattern:

1. **Edit `_check_natural_language_triggers()`** in `playwright_direct.py`
2. **Add trigger patterns** to the appropriate category
3. **Add handler** in `_handle_direct_action()`
4. **Test** with example prompt

Example:
```python
# In _check_natural_language_triggers()
if any(trigger in prompt_lower for trigger in ['extract buttons', 'find buttons']):
    return {
        'action': 'extract_buttons',
        'tool': 'extraction_helpers.extract_buttons',
        'params': {},
        'skip_llm': True,
        'reason': 'Direct button extraction'
    }

# In _handle_direct_action()
elif action == 'extract_buttons':
    from extraction_helpers import extract_buttons
    result = await extract_buttons(self.page)
    return {'success': True, 'buttons': result, 'count': len(result)}
```

---

## Debugging

Enable verbose logging to see trigger matches:

```python
import logging
logging.basicConfig(level=logging.INFO)

# Logs will show:
# [NL-TRIGGER] Matched: extract_links - Direct link extraction without LLM
# [NL-TRIGGER] Direct execution complete: True
```

---

## FAQ

**Q: What if a trigger doesn't match?**
A: `process_natural_language()` returns `None`, and you should fall back to LLM planning.

**Q: Can I customize trigger phrases?**
A: Yes, edit the trigger lists in `_check_natural_language_triggers()`.

**Q: Do triggers work with complex prompts?**
A: Yes, triggers check for phrase presence. "Please extract all links from this page" will match "extract all links".

**Q: How do I see which triggers matched?**
A: Check logs for `[NL-TRIGGER]` messages, or inspect the returned result.

**Q: Can I disable triggers?**
A: Don't call `process_natural_language()` - just use LLM planning directly.

---

## Examples

See `example_natural_language_triggers.py` for complete working examples.

Quick test:
```bash
cd /mnt/c/ev29/cli/engine/agent
python example_natural_language_triggers.py
```
