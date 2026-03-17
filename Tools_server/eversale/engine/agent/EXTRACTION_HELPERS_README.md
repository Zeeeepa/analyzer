# Extraction Helpers

Fast, efficient JavaScript-based extraction utilities for browser automation. These helpers run optimized JavaScript directly in the browser to extract structured data without requiring LLM analysis.

## Features

- Pure JavaScript execution for maximum speed
- Filtering and limiting performed in-browser
- Minimal data transfer overhead
- Element refs (mmid) for subsequent interactions
- Batch multiple extractions in parallel
- Production-ready error handling

## Quick Start

```python
from extraction_helpers import (
    extract_links,
    extract_clickable,
    extract_forms,
    QuickExtractor
)

# Extract signup links
signup_links = await extract_links(page, contains_text='sign up', limit=10)
for link in signup_links:
    print(f"{link['text']} -> {link['href']}")
    # Click using mmid: await page.click(f"[data-mmid='{link['mmid']}']")

# Extract all buttons
buttons = await extract_clickable(page, role='button')

# Batch multiple extractions
extractor = QuickExtractor(page)
result = await extractor.extract({
    'links': {'contains_text': 'contact'},
    'buttons': {'role': 'button'},
    'forms': True
})
```

## API Reference

### extract_links(page, contains_text=None, domain=None, limit=50)

Extract links from the page with optional filtering.

**Parameters:**
- `page`: Playwright page object
- `contains_text`: Filter links containing this text (case-insensitive)
- `domain`: Filter links to specific domain (e.g., 'example.com')
- `limit`: Maximum number of links to return (default: 50)

**Returns:** List of link objects with:
- `mmid`: Element reference for interactions
- `tag`: 'a'
- `text`: Link text content
- `href`: Link URL
- `aria_label`: ARIA label if present
- `x`, `y`, `width`, `height`: Element position and size

**Examples:**

```python
# Get all links
all_links = await extract_links(page, limit=100)

# Find signup/register links
signup_links = await extract_links(page, contains_text='sign up')

# Get external links to specific domain
github_links = await extract_links(page, domain='github.com')

# Find contact links
contact_links = await extract_links(page, contains_text='contact')
```

---

### extract_clickable(page, contains_text=None, role=None, limit=50)

Extract clickable elements (buttons, links, inputs) with optional filtering.

**Parameters:**
- `page`: Playwright page object
- `contains_text`: Filter elements containing this text
- `role`: Filter by ARIA role (button, link, menuitem, etc.)
- `limit`: Maximum number of elements to return (default: 50)

**Returns:** List of clickable element objects with:
- `mmid`: Element reference
- `tag`: HTML tag name
- `text`: Element text or value
- `role`: ARIA role
- `type`: Input type if applicable
- `href`: URL if link
- `aria_label`: ARIA label
- `x`, `y`, `width`, `height`: Position and size

**Examples:**

```python
# Get all buttons
buttons = await extract_clickable(page, role='button')

# Find submit buttons
submit_btns = await extract_clickable(page, contains_text='submit')

# Get all clickable elements
all_clickable = await extract_clickable(page, limit=100)

# Find "Add to Cart" buttons
cart_btns = await extract_clickable(page, contains_text='add to cart')
```

---

### extract_forms(page)

Extract all forms and their input fields.

**Parameters:**
- `page`: Playwright page object

**Returns:** List of form objects with:
- `mmid`: Form element reference
- `tag`: 'form'
- `name`: Form name attribute
- `action`: Form action URL
- `method`: Form method (get/post)
- `fields`: List of input field objects
- `field_count`: Number of fields

Each field object contains:
- `mmid`: Field element reference
- `tag`: Input tag name
- `type`: Input type
- `name`: Field name
- `placeholder`: Placeholder text
- `value`: Current value
- `required`: Whether required
- `aria_label`: ARIA label

**Examples:**

```python
# Get all forms
forms = await extract_forms(page)
for form in forms:
    print(f"Form: {form['name']} with {form['field_count']} fields")
    for field in form['fields']:
        print(f"  - {field['name']} ({field['type']})")

# Find login form
forms = await extract_forms(page)
login_form = next((f for f in forms if 'login' in f['name'].lower()), None)
```

---

### extract_inputs(page)

Extract all input fields, including those not in forms.

**Parameters:**
- `page`: Playwright page object

**Returns:** List of input objects with same structure as form fields

**Examples:**

```python
# Get all inputs
inputs = await extract_inputs(page)

# Find email inputs
email_inputs = [i for i in inputs if i['type'] == 'email']

# Find required fields
required = [i for i in inputs if i['required']]

# Find visible inputs only
visible = [i for i in inputs if i['is_visible']]
```

---

### extract_text_content(page, selector=None)

Extract text content from page or specific element.

**Parameters:**
- `page`: Playwright page object
- `selector`: Optional CSS selector to extract from specific element

**Returns:** Extracted text content as string

**Examples:**

```python
# Get full page text
full_text = await extract_text_content(page)

# Get main content only
main_text = await extract_text_content(page, selector='main')

# Get article text
article = await extract_text_content(page, selector='article')
```

---

### extract_tables(page)

Extract all tables with headers and row data.

**Parameters:**
- `page`: Playwright page object

**Returns:** List of table objects with:
- `mmid`: Table element reference
- `tag`: 'table'
- `headers`: List of header cell texts
- `rows`: List of row arrays (each row is array of cell texts)
- `row_count`: Number of data rows
- `column_count`: Number of columns

**Examples:**

```python
# Get all tables
tables = await extract_tables(page)
for table in tables:
    print(f"Table: {table['column_count']} cols, {table['row_count']} rows")
    print(f"Headers: {table['headers']}")
    for row in table['rows']:
        print(f"  {row}")

# Convert to CSV
import csv
table = tables[0]
with open('output.csv', 'w') as f:
    writer = csv.writer(f)
    writer.writerow(table['headers'])
    writer.writerows(table['rows'])
```

---

### extract_structured(page, schema)

Extract data according to a custom schema with CSS selectors.

**Parameters:**
- `page`: Playwright page object
- `schema`: Dict mapping field names to CSS selectors. Use `@attr` syntax to extract attributes (e.g., `'a@href'`)

**Returns:** Dict with extracted values for each schema field

**Examples:**

```python
# Extract product information
product = await extract_structured(page, {
    'title': 'h1.product-title',
    'price': '.price',
    'image': 'img.main@src',
    'rating': '[data-rating]@data-rating',
    'description': '.product-description'
})

# Extract article metadata
article = await extract_structured(page, {
    'headline': 'h1',
    'author': '.author-name',
    'date': 'time@datetime',
    'category': '.category',
    'body': 'article .content'
})

# Extract job listing
job = await extract_structured(page, {
    'title': '.job-title',
    'company': '.company-name',
    'location': '.location',
    'salary': '.salary-range',
    'apply_url': 'a.apply-button@href'
})
```

---

### QuickExtractor

Batch multiple extraction operations in parallel for better performance.

**Constructor:**
```python
extractor = QuickExtractor(page)
```

**Method: extract(operations)**

Execute multiple extraction operations in parallel.

**Parameters:**
- `operations`: Dict mapping result keys to extraction configs. Config can be `True` (use defaults) or dict with params

**Returns:** Dict mapping result keys to extraction results

**Examples:**

```python
# Batch multiple extractions
extractor = QuickExtractor(page)
result = await extractor.extract({
    'links': {'contains_text': 'signup', 'limit': 5},
    'buttons': {'role': 'button'},
    'forms': True,
    'inputs': True,
    'tables': True
})

# Access results
signup_links = result['links']
all_buttons = result['buttons']
all_forms = result['forms']

# Extract structured data + lists
result = await extractor.extract({
    'product': {
        'type': 'structured',
        'schema': {
            'title': 'h1',
            'price': '.price',
            'image': 'img@src'
        }
    },
    'related': {'type': 'links', 'contains_text': 'related'},
    'reviews': {'type': 'text', 'selector': '.reviews'}
})
```

---

## Convenience Functions

### extract_contact_forms(page)

Extract forms that look like contact/signup forms (have email, tel, or text inputs).

```python
contact_forms = await extract_contact_forms(page)
```

### extract_navigation_links(page, limit=20)

Extract main navigation links from header/menu areas.

```python
nav_links = await extract_navigation_links(page)
for link in nav_links:
    print(f"{link['text']} -> {link['href']}")
```

---

## Real-World Examples

### Lead Generation Workflow

```python
from extraction_helpers import QuickExtractor, extract_contact_forms

# Navigate to target site
await page.goto('https://example-business.com')

# Extract all contact information in one batch
extractor = QuickExtractor(page)
data = await extractor.extract({
    'contact_links': {'type': 'links', 'contains_text': 'contact'},
    'contact_forms': {'type': 'forms'},
    'nav_links': {'type': 'links', 'limit': 20},
    'company_info': {
        'type': 'structured',
        'schema': {
            'name': 'h1, .company-name',
            'tagline': '.tagline, .description',
            'phone': 'a[href^="tel:"]',
            'email': 'a[href^="mailto:"]'
        }
    }
})

# Filter to actual contact forms
contact_forms = await extract_contact_forms(page)

# Click on contact link if no form found
if not contact_forms and data['contact_links']:
    contact_link = data['contact_links'][0]
    await page.click(f"[data-mmid='{contact_link['mmid']}']")
    await page.wait_for_load_state('networkidle')
    contact_forms = await extract_contact_forms(page)
```

### E-commerce Scraping

```python
# Search for products
await page.goto('https://shop.example.com/search?q=laptop')

# Extract product listings
products = []
extractor = QuickExtractor(page)

# Try structured extraction first
for i in range(1, 21):  # First 20 products
    product = await extract_structured(page, {
        'title': f'.product-{i} .title',
        'price': f'.product-{i} .price',
        'rating': f'.product-{i} .rating@data-rating',
        'image': f'.product-{i} img@src',
        'url': f'.product-{i} a@href'
    })
    if product['title']:
        products.append(product)

# Fallback: Extract all product links
if not products:
    links = await extract_links(page, contains_text='', limit=50)
    product_links = [l for l in links if '/product/' in l['href']]
```

### Form Automation

```python
# Find and fill registration form
forms = await extract_forms(page)
signup_form = next((f for f in forms if 'signup' in f['name'].lower()), None)

if signup_form:
    for field in signup_form['fields']:
        mmid = field['mmid']

        if field['type'] == 'email':
            await page.fill(f"[data-mmid='{mmid}']", 'user@example.com')
        elif field['type'] == 'text' and 'name' in field['name']:
            await page.fill(f"[data-mmid='{mmid}']", 'John Doe')
        elif field['type'] == 'tel':
            await page.fill(f"[data-mmid='{mmid}']", '555-1234')

    # Find and click submit button
    buttons = await extract_clickable(page, contains_text='submit')
    if buttons:
        await page.click(f"[data-mmid='{buttons[0]['mmid']}']")
```

### Competitor Analysis

```python
# Analyze competitor pricing
competitors = [
    'https://competitor1.com',
    'https://competitor2.com',
    'https://competitor3.com'
]

pricing_data = []

for url in competitors:
    await page.goto(url)

    # Extract pricing table
    tables = await extract_tables(page)
    pricing_table = tables[0] if tables else None

    # Extract structured pricing info
    pricing = await extract_structured(page, {
        'basic_price': '.plan-basic .price',
        'pro_price': '.plan-pro .price',
        'enterprise_price': '.plan-enterprise .price',
        'features': '.features-list'
    })

    pricing_data.append({
        'url': url,
        'pricing': pricing,
        'table': pricing_table
    })

# Compare results
for data in pricing_data:
    print(f"{data['url']}: Basic ${data['pricing']['basic_price']}")
```

---

## Performance Tips

1. **Use QuickExtractor for multiple operations** - Runs extractions in parallel
2. **Limit results** - Set reasonable `limit` parameters to reduce processing
3. **Filter in-browser** - Use `contains_text` and `role` filters instead of filtering in Python
4. **Reuse page object** - Don't create new pages for each extraction
5. **Batch related extractions** - Combine related operations in one QuickExtractor call

---

## Error Handling

All extraction functions include production-ready error handling:

```python
# Functions return empty results on error, never raise
links = await extract_links(page)  # Returns [] if error
text = await extract_text_content(page)  # Returns '' if error

# Check for errors in QuickExtractor results
result = await extractor.extract({'links': True, 'forms': True})
if not result['links']:
    logger.warning("No links found")

# Extraction exceptions are logged but don't crash
```

---

## Integration with Existing Agent

```python
from extraction_helpers import QuickExtractor

class EnhancedAgent:
    async def understand_page(self, page):
        """Get comprehensive page understanding."""
        extractor = QuickExtractor(page)

        page_data = await extractor.extract({
            'nav': {'type': 'links', 'limit': 20},
            'clickable': {'type': 'clickable', 'limit': 50},
            'forms': True,
            'tables': True,
            'text': {'type': 'text'}
        })

        return {
            'url': page.url,
            'navigation': page_data['nav'],
            'interactive_elements': page_data['clickable'],
            'forms': page_data['forms'],
            'tables': page_data['tables'],
            'content_preview': page_data['text'][:500]
        }
```

---

## Testing

Run the test suite:

```bash
pytest engine/agent/test_extraction_helpers.py -v
```

---

## Notes

- All functions automatically inject `mmid` attributes on first use
- `mmid` format: `mm-XXXX` where XXXX is a random counter
- Attribute name randomized (`data-mmid`, `data-mmid-v1`, `data-mmid-id`) to avoid detection
- Elements are filtered for visibility by default in `extract_clickable`
- All text is trimmed and normalized
- Empty/null results are filtered out

---

## License

Part of the Eversale CLI desktop agent.
