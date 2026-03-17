# Quick DOM Inspect

Lightweight HTML parsing utility for extracting data from cached/stored HTML without browser roundtrips.

## Why Use This?

When you already have HTML from a previous browser fetch, MCP snapshot, or cache, you can extract data instantly without:
- Making another browser call
- Waiting for MCP roundtrip
- Incurring additional latency

## Installation

Already included in the agent. Import from:

```python
from agent import (
    quick_extract_links,
    quick_extract_forms,
    quick_extract_inputs,
    quick_extract_buttons,
    quick_find_element,
    quick_summary
)
```

## Quick Start

```python
# You already have HTML from somewhere
html = await browser.get_html()  # or from cache, file, etc.

# Extract data without any additional browser calls
links = quick_extract_links(html, contains_text="signup")
forms = quick_extract_forms(html)
buttons = quick_extract_buttons(html, contains_text="submit")
```

## API Reference

### `quick_extract_links(html, contains_text=None, domain=None, base_url=None)`

Extract all links from HTML.

**Parameters:**
- `html` (str): Raw HTML string
- `contains_text` (str, optional): Filter links by text content (case-insensitive)
- `domain` (str, optional): Filter links by domain
- `base_url` (str, optional): Base URL for resolving relative links

**Returns:** List of dicts with keys: `href`, `text`, `title`, `rel`, `target`

**Example:**
```python
links = quick_extract_links(html, contains_text="login")
# [{'href': '/login', 'text': 'Login Here', 'title': '', 'rel': '', 'target': ''}]
```

### `quick_extract_forms(html)`

Extract all forms with their input fields.

**Parameters:**
- `html` (str): Raw HTML string

**Returns:** List of dicts with keys: `action`, `method`, `id`, `name`, `inputs`

**Example:**
```python
forms = quick_extract_forms(html)
# [{'action': '/login', 'method': 'post', 'id': 'login-form', 'inputs': [...]}]

# Access inputs
for form in forms:
    for input_field in form['inputs']:
        print(f"{input_field['name']}: {input_field['type']}")
```

### `quick_extract_inputs(html)`

Extract all input fields (not grouped by form).

**Parameters:**
- `html` (str): Raw HTML string

**Returns:** List of dicts with input field details

**Example:**
```python
inputs = quick_extract_inputs(html)
# [{'tag': 'input', 'type': 'email', 'name': 'user_email', 'id': 'email-input', ...}]
```

### `quick_extract_buttons(html, contains_text=None)`

Extract buttons and input[type=submit/button].

**Parameters:**
- `html` (str): Raw HTML string
- `contains_text` (str, optional): Filter by button text

**Returns:** List of dicts with button details

**Example:**
```python
buttons = quick_extract_buttons(html, contains_text="submit")
# [{'tag': 'button', 'text': 'Submit Form', 'type': 'submit', 'id': 'submit-btn'}]
```

### `quick_find_element(html, text=None, role=None, tag=None)`

Find a single element by text, ARIA role, or tag name.

**Parameters:**
- `html` (str): Raw HTML string
- `text` (str, optional): Text to search for (partial match)
- `role` (str, optional): ARIA role
- `tag` (str, optional): HTML tag name

**Returns:** Dict with element details or `None`

**Example:**
```python
elem = quick_find_element(html, text="Sign Up", tag="button")
# {'tag': 'button', 'text': 'Sign Up Now', 'id': 'signup-btn', ...}
```

### `quick_extract_text(html, selector=None)`

Extract text content from HTML.

**Parameters:**
- `html` (str): Raw HTML string
- `selector` (str, optional): Simple selector (tag name, #id, or .class)

**Returns:** Extracted text as string

**Example:**
```python
# All text
all_text = quick_extract_text(html)

# Just h1 headings
h1_text = quick_extract_text(html, selector='h1')

# Specific ID
title = quick_extract_text(html, selector='#page-title')
```

### `quick_extract_headings(html)`

Extract all headings (h1-h6).

**Parameters:**
- `html` (str): Raw HTML string

**Returns:** Dict mapping heading levels to lists of text

**Example:**
```python
headings = quick_extract_headings(html)
# {'h1': ['Main Title'], 'h2': ['Section 1', 'Section 2'], 'h3': [...]}
```

### `quick_extract_tables(html)`

Extract table data.

**Parameters:**
- `html` (str): Raw HTML string

**Returns:** List of dicts with `headers` and `rows` keys

**Example:**
```python
tables = quick_extract_tables(html)
# [{'headers': ['Name', 'Email'], 'rows': [['John', 'john@ex.com']]}]
```

### `quick_summary(html)`

Get a quick overview of HTML structure.

**Parameters:**
- `html` (str): Raw HTML string

**Returns:** Dict with element counts and samples

**Example:**
```python
summary = quick_summary(html)
# {
#   'link_count': 42,
#   'form_count': 2,
#   'button_count': 5,
#   'sample_links': [...],
#   'h1_headings': ['Welcome']
# }
```

## Usage Patterns

### Pattern 1: Login Form Detection

```python
# Already have HTML from previous snapshot
html = cached_html_from_previous_step

# Find login form without browser call
forms = quick_extract_forms(html)
login_form = next((f for f in forms if 'login' in f['action'].lower()), None)

if login_form:
    # Know what fields to fill
    email_field = next((i for i in login_form['inputs'] if i['type'] == 'email'), None)
    password_field = next((i for i in login_form['inputs'] if i['type'] == 'password'), None)

    # Now use actual browser to fill
    await browser.type(email_field['id'], "user@example.com")
    await browser.type(password_field['id'], "password123")
```

### Pattern 2: Search Results Extraction

```python
# After search, extract results without re-snapshotting
html = await browser.get_html()

# Extract all product links
links = quick_extract_links(html)
product_links = [l for l in links if '/product/' in l['href']]

# Process results
for product in product_links:
    print(f"Found: {product['text']} at {product['href']}")
```

### Pattern 3: Navigation Planning

```python
# Get page structure
html = cached_html

# Quick overview
summary = quick_summary(html)
print(f"Page has {summary['link_count']} links, {summary['form_count']} forms")

# Find specific navigation
nav_links = quick_extract_links(html, contains_text="dashboard")
if nav_links:
    dashboard_url = nav_links[0]['href']
    await browser.navigate(dashboard_url)
```

### Pattern 4: Form Validation Prep

```python
# Analyze form structure before filling
forms = quick_extract_forms(html)
registration_form = forms[0]

# Categorize required vs optional
required = [i for i in registration_form['inputs'] if i['required']]
optional = [i for i in registration_form['inputs'] if not i['required']]

print(f"Need to fill {len(required)} required fields")
for field in required:
    print(f"  - {field['name']} ({field['type']})")
```

## When to Use vs Browser Calls

**Use Quick DOM Inspect when:**
- You already have HTML from a previous operation
- You're analyzing structure/content, not interacting
- You need to make decisions before taking action
- You want to reduce latency and roundtrips

**Use Browser Calls when:**
- You need fresh/current page state
- You're actually interacting (clicking, typing)
- You need dynamic content that changes
- You need visual/screenshot context

## Performance

- **Zero latency** - runs locally, no network calls
- **Zero cost** - no LLM tokens, no browser overhead
- **Pure Python** - uses stdlib `html.parser`, no heavy dependencies
- **Fast** - parses typical page (<100KB) in <10ms

## Implementation Details

Uses Python's stdlib `html.parser.HTMLParser` with:
- Proper void element handling (input, br, img, etc.)
- Parent-child relationship tracking
- Malformed HTML tolerance
- No external dependencies beyond stdlib

## Limitations

- **Static analysis only** - doesn't execute JavaScript
- **Simple selectors** - supports tag, #id, .class only (not full CSS)
- **No dynamic content** - won't see changes from JS execution
- **Text-based** - no visual/layout information

For complex scenarios, use browser automation or MCP.

## Examples

See `quick_dom_inspect_example.py` for full working examples:
- Login workflow
- Search results extraction
- Form filling preparation

Run examples:
```bash
python3 engine/agent/quick_dom_inspect_example.py
```
