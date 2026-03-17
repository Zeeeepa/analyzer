# Complex Form Handler Module

**Location:** `/mnt/c/ev29/eversale-cli/engine/agent/complex_form_handler.py`

A specialized module for handling complex web forms in browser automation. Goes beyond basic Playwright actions to handle real-world form patterns found on modern websites.

---

## Features

### 1. Form Type Detection
Automatically identifies form complexity:
- **Simple forms** - Basic input fields
- **Autocomplete forms** - Typeahead/suggestion dropdowns
- **Multi-step forms** - Wizard-style with next/previous
- **Conditional forms** - Fields that appear/disappear based on selections
- **Dynamic forms** - AJAX-loaded fields

### 2. Input Type Support

| Input Type | Description | Example Sites |
|------------|-------------|---------------|
| **Text** | Standard input fields | All sites |
| **Autocomplete** | Typeahead with suggestions | Google, LinkedIn |
| **Location** | Google Places-style autocomplete | Indeed, Yelp, Zillow, Airbnb |
| **Native Select** | Standard `<select>` dropdowns | Most forms |
| **Custom Select** | Styled dropdowns (div-based) | Modern SPAs |
| **Radio** | Radio button groups | Surveys, forms |
| **Checkbox** | Single or multiple checkboxes | Agreements, preferences |
| **File Upload** | File input fields | Upload forms |
| **Slider** | Range inputs | Price filters, ratings |
| **Date Picker** | Calendar inputs | Booking sites |

### 3. Human-Like Interactions

Integrates with the humanization module for realistic behavior:
- **Bezier cursor movement** - Natural mouse curves (not straight lines)
- **Human typing** - QWERTY errors, corrections, fatigue
- **Variable delays** - Random timing between actions
- **Natural scrolling** - Momentum-based scrolling

### 4. Site-Specific Handlers

Pre-built handlers for popular websites:
- **Indeed.com** - Job search with location autocomplete
- **Yelp.com** - Business search
- **Zillow.com** - Property search with filters
- **Target.com** - Store selector
- **LinkedIn.com** - Job search filters *(coming soon)*
- **Airbnb.com** - Date pickers and location *(coming soon)*

---

## Installation

The module is included in the eversale-cli package. No additional installation required.

### Dependencies
```python
# Required
from playwright.async_api import async_playwright

# Optional (for humanization)
from agent.humanization import BezierCursor, HumanTyper
```

---

## Quick Start

### Basic Usage

```python
from playwright.async_api import async_playwright
from agent.complex_form_handler import ComplexFormHandler

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        # Create handler
        handler = ComplexFormHandler(page)

        # Wait for form to load
        await handler.wait_for_form_ready()

        # Fill autocomplete field
        await handler.fill_autocomplete(
            selector='input[name="location"]',
            value='San Francisco, CA'
        )

        await browser.close()
```

---

## API Reference

### Core Class: `ComplexFormHandler`

#### Constructor
```python
handler = ComplexFormHandler(page, use_humanization=True)
```

**Parameters:**
- `page` - Playwright page object
- `use_humanization` - Enable human-like interactions (default: `True`)

---

### Methods

#### `detect_form_type()`
Analyze and detect form complexity.

```python
form_type = await handler.detect_form_type()
# Returns: FormType.SIMPLE | FormType.AUTOCOMPLETE | FormType.MULTI_STEP | etc.
```

---

#### `wait_for_form_ready(timeout=10000)`
Wait for dynamic form elements to fully load.

```python
is_ready = await handler.wait_for_form_ready(timeout=10000)
# Returns: True if ready, False on timeout
```

**Features:**
- Waits for form elements to appear
- Waits for network idle
- Waits for loading spinners to disappear

---

#### `fill_autocomplete(selector, value, suggestion_selector=None, exact_match=True, clear_first=True)`
Fill autocomplete/typeahead inputs.

```python
success = await handler.fill_autocomplete(
    selector='input[name="city"]',
    value='San Francisco',
    exact_match=False
)
```

**Parameters:**
- `selector` - Input field CSS selector
- `value` - Text to type
- `suggestion_selector` - Optional dropdown selector (auto-detected if None)
- `exact_match` - Wait for exact text match in suggestions (default: True)
- `clear_first` - Clear field before typing (default: True)

**Auto-detects suggestion dropdowns:**
- `[role="listbox"]`
- `.autocomplete-results`
- `.pac-container` (Google Places)
- And more...

---

#### `fill_location_input(selector, location, wait_for_coordinates=False)`
Fill Google Places-style location autocomplete.

```python
success = await handler.fill_location_input(
    selector='input[name="location"]',
    location='New York, NY',
    wait_for_coordinates=True
)
```

**Parameters:**
- `selector` - Input field CSS selector
- `location` - Location string (city, state, address)
- `wait_for_coordinates` - Wait for geocoding to complete (default: False)

**Use cases:**
- Indeed job search
- Yelp business search
- Zillow property search
- Airbnb location search

---

#### `select_dropdown(selector, value, is_native=None)`
Select option from dropdown (handles both native and custom).

```python
# Native <select>
await handler.select_dropdown(
    selector='select[name="country"]',
    value='United States',
    is_native=True
)

# Custom dropdown
await handler.select_dropdown(
    selector='.custom-select',
    value='Option 2',
    is_native=False
)

# Auto-detect
await handler.select_dropdown(
    selector='select[name="state"]',
    value='California'
)
```

**Parameters:**
- `selector` - Dropdown CSS selector
- `value` - Value or text to select
- `is_native` - True for `<select>`, False for custom, None to auto-detect

---

#### `fill_radio_group(name, value)`
Select a radio button by name and value.

```python
success = await handler.fill_radio_group(
    name='gender',
    value='male'
)
```

**Parameters:**
- `name` - Radio group name attribute
- `value` - Value to select

---

#### `fill_checkbox_group(selectors, check=True)`
Check/uncheck multiple checkboxes.

```python
success = await handler.fill_checkbox_group(
    selectors=[
        'input[name="newsletter"]',
        'input[name="terms"]',
        'input[name="privacy"]'
    ],
    check=True
)
```

**Parameters:**
- `selectors` - List of checkbox CSS selectors
- `check` - True to check, False to uncheck (default: True)

---

#### `set_slider_value(selector, value, min_value=0, max_value=100)`
Set a slider/range input to specific value.

```python
success = await handler.set_slider_value(
    selector='input[type="range"]',
    value=75,
    min_value=0,
    max_value=100
)
```

**Parameters:**
- `selector` - Slider CSS selector
- `value` - Target value
- `min_value` - Minimum slider value (default: 0)
- `max_value` - Maximum slider value (default: 100)

---

#### `upload_file(selector, file_path)`
Upload file to file input.

```python
success = await handler.upload_file(
    selector='input[type="file"]',
    file_path='/path/to/document.pdf'
)
```

**Parameters:**
- `selector` - File input CSS selector
- `file_path` - Absolute path to file

---

#### `fill_field(field)`
Fill a single form field based on its type.

```python
from agent.complex_form_handler import FormField, InputType

field = FormField(
    selector='input[name="email"]',
    value='test@example.com',
    input_type=InputType.EMAIL,
    retry_count=3
)

success = await handler.fill_field(field)
```

**Parameters:**
- `field` - FormField object

**FormField attributes:**
- `selector` - CSS selector
- `value` - Value to fill
- `input_type` - InputType enum (default: InputType.TEXT)
- `wait_for_selector` - Prerequisite selector for conditional fields (optional)
- `validate_selector` - Validation check selector (optional)
- `retry_count` - Number of retry attempts (default: 3)

---

#### `fill_multi_step_form(steps, submit_button_selector=None)`
Fill a multi-step wizard form.

```python
from agent.complex_form_handler import FormStep, FormField, InputType

steps = [
    FormStep(
        step_number=1,
        fields=[
            FormField('input[name="email"]', 'test@example.com', InputType.EMAIL),
            FormField('input[name="password"]', 'Pass123', InputType.PASSWORD)
        ],
        next_button_selector='button:has-text("Next")'
    ),
    FormStep(
        step_number=2,
        fields=[
            FormField('input[name="name"]', 'John Doe', InputType.TEXT)
        ]
    )
]

result = await handler.fill_multi_step_form(
    steps=steps,
    submit_button_selector='button[type="submit"]'
)

print(result)
# {
#     'success': True,
#     'steps_completed': 2,
#     'filled_fields': ['input[name="email"]', ...],
#     'failed_fields': []
# }
```

**Parameters:**
- `steps` - List of FormStep objects
- `submit_button_selector` - Final submit button selector (optional)

**Returns:**
Dictionary with:
- `success` - Overall success status
- `steps_completed` - Number of steps completed
- `filled_fields` - List of successfully filled field selectors
- `failed_fields` - List of failed field selectors

---

## Site-Specific Handlers

### `SiteSpecificHandlers.indeed_job_search(page, job_title, location)`

Fill Indeed.com job search form.

```python
from agent.complex_form_handler import SiteSpecificHandlers

success = await SiteSpecificHandlers.indeed_job_search(
    page=page,
    job_title='Software Engineer',
    location='San Francisco, CA'
)
```

**Parameters:**
- `page` - Playwright page
- `job_title` - Job title to search
- `location` - Location string

---

### `SiteSpecificHandlers.yelp_business_search(page, business, location)`

Fill Yelp.com business search form.

```python
success = await SiteSpecificHandlers.yelp_business_search(
    page=page,
    business='Italian Restaurant',
    location='New York, NY'
)
```

**Parameters:**
- `page` - Playwright page
- `business` - Business type or name
- `location` - Location string

---

### `SiteSpecificHandlers.zillow_property_search(page, location, min_price=None, max_price=None, bedrooms=None)`

Fill Zillow.com property search with filters.

```python
success = await SiteSpecificHandlers.zillow_property_search(
    page=page,
    location='Austin, TX',
    min_price=300000,
    max_price=500000,
    bedrooms=3
)
```

**Parameters:**
- `page` - Playwright page
- `location` - Location to search
- `min_price` - Minimum price (optional)
- `max_price` - Maximum price (optional)
- `bedrooms` - Number of bedrooms (optional)

---

### `SiteSpecificHandlers.target_store_selector(page, zip_code)`

Select Target store by ZIP code.

```python
success = await SiteSpecificHandlers.target_store_selector(
    page=page,
    zip_code='90210'
)
```

**Parameters:**
- `page` - Playwright page
- `zip_code` - ZIP code to search

---

## Advanced Examples

### Example 1: Conditional Form Fields

Handle forms where fields appear based on previous selections.

```python
from agent.complex_form_handler import FormField, InputType

fields = [
    # Select country first
    FormField(
        selector='select[name="country"]',
        value='United States',
        input_type=InputType.SELECT_NATIVE
    ),
    # State field only appears after country is selected
    FormField(
        selector='select[name="state"]',
        value='California',
        input_type=InputType.SELECT_NATIVE,
        wait_for_selector='select[name="state"]:visible'
    ),
    # City autocomplete appears after state
    FormField(
        selector='input[name="city"]',
        value='San Francisco',
        input_type=InputType.AUTOCOMPLETE,
        wait_for_selector='input[name="city"]:visible'
    )
]

for field in fields:
    success = await handler.fill_field(field)
```

---

### Example 2: Form Validation

Ensure fields are validated before proceeding.

```python
field = FormField(
    selector='input[name="email"]',
    value='test@example.com',
    input_type=InputType.EMAIL,
    validate_selector='.email-valid-checkmark',  # Wait for this to appear
    retry_count=3
)

success = await handler.fill_field(field)
```

---

### Example 3: Complex Multi-Step Form

```python
from agent.complex_form_handler import FormStep, FormField, InputType

steps = [
    # Step 1: Personal Info
    FormStep(
        step_number=1,
        fields=[
            FormField('input[name="first_name"]', 'John', InputType.TEXT),
            FormField('input[name="last_name"]', 'Doe', InputType.TEXT),
            FormField('input[name="email"]', 'john@example.com', InputType.EMAIL)
        ],
        next_button_selector='button:has-text("Next")',
        validation_selector='.step-1-complete'  # Wait for validation
    ),

    # Step 2: Address
    FormStep(
        step_number=2,
        fields=[
            FormField(
                'input[name="address"]',
                '123 Main St, San Francisco, CA',
                InputType.LOCATION
            ),
            FormField('select[name="country"]', 'United States', InputType.SELECT_NATIVE)
        ],
        next_button_selector='button:has-text("Continue")'
    ),

    # Step 3: Preferences
    FormStep(
        step_number=3,
        fields=[
            FormField('input[name="newsletter"]', True, InputType.CHECKBOX),
            FormField('input[name="terms"]', True, InputType.CHECKBOX)
        ]
    )
]

result = await handler.fill_multi_step_form(
    steps=steps,
    submit_button_selector='button[type="submit"]'
)

if result['success']:
    print(f"Form completed! Filled {len(result['filled_fields'])} fields")
else:
    print(f"Form failed. Failed fields: {result['failed_fields']}")
```

---

## Error Handling

The module includes built-in retry logic and error handling:

### Retry Logic
- Each field can specify `retry_count` (default: 3)
- Retries with exponential backoff
- Logs warnings on failure

### Exception Handling
```python
try:
    success = await handler.fill_autocomplete(
        selector='input[name="location"]',
        value='San Francisco, CA'
    )

    if not success:
        logger.error("Failed to fill autocomplete after retries")

except Exception as e:
    logger.error(f"Unexpected error: {e}")
```

---

## Timeouts

Configurable timeouts for different operations:

| Operation | Default Timeout | Configuration |
|-----------|-----------------|---------------|
| Default | 10 seconds | `DEFAULT_TIMEOUT` |
| Autocomplete suggestions | 5 seconds | `AUTOCOMPLETE_SUGGESTION_TIMEOUT` |
| AJAX load | 3 seconds | `AJAX_LOAD_TIMEOUT` |

### Custom Timeouts
```python
handler.DEFAULT_TIMEOUT = 15000  # 15 seconds
handler.AUTOCOMPLETE_SUGGESTION_TIMEOUT = 8000  # 8 seconds
```

---

## Human-Like Delays

The module uses randomized delays to simulate human behavior:

| Action | Delay Range | Purpose |
|--------|-------------|---------|
| Typing | 50-150ms | Between keystrokes |
| Click | 100-300ms | After clicking |
| Form field transition | 200-500ms | Between fields |
| Step transition | 500-1000ms | Between wizard steps |

### Disable Humanization
```python
handler = ComplexFormHandler(page, use_humanization=False)
```

---

## Integration with Eversale Agent

### Use in ReAct Loop

```python
from agent.complex_form_handler import ComplexFormHandler, SiteSpecificHandlers

# In tool execution
async def execute_form_fill(context):
    page = context['page']

    # Detect form type
    handler = ComplexFormHandler(page)
    form_type = await handler.detect_form_type()

    if form_type == FormType.AUTOCOMPLETE:
        # Use autocomplete handler
        success = await handler.fill_autocomplete(...)
    elif form_type == FormType.MULTI_STEP:
        # Use multi-step handler
        result = await handler.fill_multi_step_form(...)
```

### Add to Tool Registry

```python
# In tools.py or similar
tools = {
    'fill_form': {
        'handler': ComplexFormHandler,
        'description': 'Fill complex web forms with autocomplete, multi-step, etc.'
    }
}
```

---

## Testing

Run the example file to test various scenarios:

```bash
# Run all examples
python complex_form_handler_example.py

# Run specific example
python complex_form_handler_example.py 3  # Indeed job search
```

---

## Troubleshooting

### Autocomplete suggestions not appearing
- Increase `AUTOCOMPLETE_SUGGESTION_TIMEOUT`
- Check if suggestion selector is correct
- Try `exact_match=False` for fuzzy matching

### Custom dropdown not working
- Set `is_native=False` explicitly
- Check the option selector pattern
- Use browser DevTools to inspect dropdown structure

### Multi-step form validation failing
- Add `validation_selector` to each FormStep
- Increase delays between steps
- Check if "Next" button is enabled

### Fields not visible
- Use `wait_for_selector` in FormField
- Ensure prerequisite fields are filled first
- Check for AJAX loading indicators

---

## Best Practices

1. **Always wait for form ready**
   ```python
   await handler.wait_for_form_ready()
   ```

2. **Use site-specific handlers when available**
   ```python
   # Good
   await SiteSpecificHandlers.indeed_job_search(page, title, location)

   # Instead of
   await handler.fill_autocomplete(...)
   ```

3. **Enable humanization for anti-bot protection**
   ```python
   handler = ComplexFormHandler(page, use_humanization=True)
   ```

4. **Handle conditional fields properly**
   ```python
   FormField(
       selector='...',
       value='...',
       wait_for_selector='...'  # Wait for field to appear
   )
   ```

5. **Add validation checks**
   ```python
   FormField(
       selector='...',
       value='...',
       validate_selector='.success-icon'  # Confirm field is valid
   )
   ```

---

## Future Enhancements

- [ ] LinkedIn job search handler
- [ ] Airbnb date picker handler
- [ ] Amazon product search filters
- [ ] Google Forms integration
- [ ] Salesforce form automation
- [ ] Microsoft Dynamics form handling
- [ ] Custom CAPTCHA solver integration
- [ ] Form recording and replay
- [ ] Visual form analysis (OCR-based)

---

## Contributing

To add a new site-specific handler:

1. Add method to `SiteSpecificHandlers` class
2. Follow naming convention: `{site}__{action}` (e.g., `linkedin_job_search`)
3. Test on actual site
4. Document in this README

---

## License

Part of the eversale-cli package. See main LICENSE file.

---

## Support

For issues or questions:
- Check examples in `complex_form_handler_example.py`
- Review this documentation
- Contact: manzhosovr@gmail.com

