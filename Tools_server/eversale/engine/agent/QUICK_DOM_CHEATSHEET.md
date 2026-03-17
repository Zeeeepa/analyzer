# Quick DOM Inspect - Cheat Sheet

Fast reference for using quick_dom_inspect in agent workflows.

## Import

```python
from agent import (
    quick_extract_links,
    quick_extract_forms,
    quick_find_element,
    quick_summary
)
```

## Common Patterns

### Pattern 1: Login Form Analysis

```python
# Get HTML once
html = await browser.get_html()

# Extract login form
forms = quick_extract_forms(html)
login_form = forms[0]

# Find fields
email = next(i for i in login_form['inputs'] if i['type'] == 'email')
password = next(i for i in login_form['inputs'] if i['type'] == 'password')

# Now interact
await browser.type(email['id'], "user@example.com")
await browser.type(password['id'], "password")
```

### Pattern 2: Navigation Discovery

```python
# Extract navigation links
html = cached_html
links = quick_extract_links(html, contains_text="dashboard")

if links:
    await browser.navigate(links[0]['href'])
```

### Pattern 3: Search Results

```python
# Extract product links
html = await browser.get_html()
all_links = quick_extract_links(html)
products = [l for l in all_links if '/product/' in l['href']]

for product in products:
    print(f"{product['text']}: {product['href']}")
```

### Pattern 4: Quick Page Overview

```python
# Get summary without detailed parsing
summary = quick_summary(html)

print(f"Page has {summary['link_count']} links")
print(f"Forms: {summary['form_count']}")
print(f"Main heading: {summary['h1_headings'][0]}")
```

### Pattern 5: Button Discovery

```python
# Find submit button
submit = quick_find_element(html, text="Submit", tag="button")
if submit:
    await browser.click(submit['id'])
```

## Quick Reference Table

| Function | Use Case | Returns |
|----------|----------|---------|
| `quick_extract_links()` | Find navigation, product links | List of `{href, text, title}` |
| `quick_extract_forms()` | Analyze form structure | List of `{action, method, inputs}` |
| `quick_extract_inputs()` | Find all input fields | List of `{type, name, id, required}` |
| `quick_extract_buttons()` | Find clickable buttons | List of `{text, type, id}` |
| `quick_find_element()` | Find specific element | Single `{tag, text, id}` or None |
| `quick_summary()` | Page overview | Dict with counts and samples |

## Performance Tips

1. **Get HTML once** - Call `browser.get_html()` or `browser.snapshot()` once, then use quick_dom functions multiple times
2. **Analyze before action** - Use quick_dom to plan your actions, then execute with browser
3. **Cache HTML** - Store HTML between operations to avoid re-fetching
4. **Use filters** - Pass `contains_text` to reduce results and speed up finding

## When to Use

**Use quick_dom when:**
- You have cached/stored HTML
- Analyzing structure before interacting
- Reducing browser roundtrips
- Planning multi-step workflows

**Don't use when:**
- Need fresh page state (use browser.snapshot())
- Checking dynamic content
- Need visual/screenshot data
- Interacting with page (use browser actions)

## One-Liners

```python
# Find login link
login_link = quick_find_element(html, text="login", tag="a")

# Count forms
form_count = len(quick_extract_forms(html))

# Get all required fields
required = [i for i in quick_extract_inputs(html) if i['required']]

# Extract h1
title = quick_extract_text(html, selector='h1')

# Find signup button
signup = quick_extract_buttons(html, contains_text="sign up")[0]
```

## Real-World Example

```python
# Login workflow optimization
async def smart_login(browser, email, password):
    # 1. Navigate (1 browser call)
    await browser.navigate("https://example.com/login")

    # 2. Get HTML once (1 browser call)
    html = await browser.get_html()

    # 3. Analyze locally (0 browser calls)
    forms = quick_extract_forms(html)
    login_form = forms[0]

    email_field = next(i for i in login_form['inputs'] if i['type'] == 'email')
    password_field = next(i for i in login_form['inputs'] if i['type'] == 'password')
    submit_btn = quick_find_element(html, text="login", tag="button")

    # 4. Execute (3 browser calls)
    await browser.type(email_field['id'], email)
    await browser.type(password_field['id'], password)
    await browser.click(submit_btn['id'])

    # Total: 5 browser calls
    # Without quick_dom: 8+ browser calls
    # Savings: 37%+
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No forms found | Check HTML has `<form>` tags, not just inputs |
| Links missing | Ensure links have `href` attribute |
| Empty text | Element might be self-closing or empty |
| Wrong results | HTML might be malformed, check source |
