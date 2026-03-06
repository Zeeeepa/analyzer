# Extraction Helpers Quick Reference

Fast JavaScript-based page data extraction for browser automation.

## Installation

```python
from extraction_helpers import (
    extract_links, extract_clickable, extract_forms,
    extract_inputs, extract_text_content, extract_tables,
    extract_structured, QuickExtractor
)
```

## Function Summary

| Function | Purpose | Key Params |
|----------|---------|------------|
| `extract_links()` | Extract links | `contains_text`, `domain`, `limit` |
| `extract_clickable()` | Extract buttons/interactive | `contains_text`, `role`, `limit` |
| `extract_forms()` | Extract forms + fields | None |
| `extract_inputs()` | Extract all inputs | None |
| `extract_text_content()` | Extract page text | `selector` |
| `extract_tables()` | Extract tables | None |
| `extract_structured()` | Custom schema extraction | `schema` |

## Quick Examples

### Find signup links
```python
links = await extract_links(page, contains_text='sign up', limit=10)
```

### Get all buttons
```python
buttons = await extract_clickable(page, role='button')
```

### Extract contact forms
```python
forms = await extract_forms(page)
contact_form = forms[0] if forms else None
```

### Batch multiple extractions
```python
extractor = QuickExtractor(page)
result = await extractor.extract({
    'links': {'contains_text': 'contact'},
    'buttons': True,
    'forms': True
})
```

### Custom structured extraction
```python
product = await extract_structured(page, {
    'title': 'h1.title',
    'price': '.price',
    'image': 'img@src'  # Use @attr for attributes
})
```

## Return Values

All functions return structured data with `mmid` refs for interactions:

```python
link = {
    'mmid': 'mm-1234',      # For interactions
    'text': 'Contact Us',
    'href': '/contact',
    'x': 100, 'y': 200      # Position
}

# Use mmid to interact
await page.click(f"[data-mmid='{link['mmid']}']")
```

## Error Handling

- Never raises exceptions
- Returns empty results on error: `[]` or `''`
- Errors logged to logger

```python
links = await extract_links(page)  # Returns [] on error
text = await extract_text_content(page)  # Returns '' on error
```

## Performance Tips

1. Use QuickExtractor for multiple operations (runs in parallel)
2. Set reasonable `limit` values
3. Filter in-browser with `contains_text` / `role`
4. Reuse page object

## Common Patterns

### Lead generation
```python
extractor = QuickExtractor(page)
data = await extractor.extract({
    'contact_links': {'type': 'links', 'contains_text': 'contact'},
    'forms': True,
    'nav': {'type': 'links', 'limit': 10}
})
```

### Form automation
```python
forms = await extract_forms(page)
for field in forms[0]['fields']:
    if field['type'] == 'email':
        await page.fill(f"[data-mmid='{field['mmid']}']", 'user@example.com')
```

### Product scraping
```python
result = await extractor.extract({
    'product': {
        'type': 'structured',
        'schema': {'title': 'h1', 'price': '.price', 'image': 'img@src'}
    },
    'tables': True
})
```

## Files

- `extraction_helpers.py` - Main module
- `test_extraction_helpers.py` - Test suite
- `EXTRACTION_HELPERS_README.md` - Full documentation
- `example_extraction_usage.py` - Usage examples

## Testing

```bash
pytest engine/agent/test_extraction_helpers.py -v
python3 engine/agent/example_extraction_usage.py
```
