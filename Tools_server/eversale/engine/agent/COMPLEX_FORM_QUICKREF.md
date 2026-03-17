# Complex Form Handler - Quick Reference

**One-page cheat sheet for the Complex Form Handler module.**

---

## Import

```python
from agent.complex_form_handler import (
    ComplexFormHandler,
    FormField,
    FormStep,
    InputType,
    SiteSpecificHandlers
)
```

---

## Basic Usage

```python
# Initialize
handler = ComplexFormHandler(page)

# Wait for form
await handler.wait_for_form_ready()

# Detect type
form_type = await handler.detect_form_type()
```

---

## Common Operations

### Autocomplete Input
```python
await handler.fill_autocomplete(
    selector='input[name="search"]',
    value='San Francisco, CA'
)
```

### Location Input (Google Places)
```python
await handler.fill_location_input(
    selector='input[name="location"]',
    location='New York, NY'
)
```

### Dropdown - Native
```python
await handler.select_dropdown(
    selector='select[name="country"]',
    value='United States',
    is_native=True
)
```

### Dropdown - Custom
```python
await handler.select_dropdown(
    selector='.custom-select',
    value='Option 2',
    is_native=False
)
```

### Radio Button
```python
await handler.fill_radio_group(
    name='gender',
    value='male'
)
```

### Checkboxes
```python
await handler.fill_checkbox_group(
    selectors=['input[name="agree"]', 'input[name="terms"]'],
    check=True
)
```

### Slider
```python
await handler.set_slider_value(
    selector='input[type="range"]',
    value=75,
    min_value=0,
    max_value=100
)
```

### File Upload
```python
await handler.upload_file(
    selector='input[type="file"]',
    file_path='/path/to/file.pdf'
)
```

---

## Multi-Step Forms

```python
steps = [
    FormStep(
        step_number=1,
        fields=[
            FormField('input[name="email"]', 'test@example.com', InputType.EMAIL)
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

result = await handler.fill_multi_step_form(steps)
# Returns: {'success': True, 'steps_completed': 2, ...}
```

---

## Site-Specific Handlers

### Indeed Job Search
```python
await SiteSpecificHandlers.indeed_job_search(
    page=page,
    job_title='Software Engineer',
    location='San Francisco, CA'
)
```

### Yelp Business Search
```python
await SiteSpecificHandlers.yelp_business_search(
    page=page,
    business='Italian Restaurant',
    location='New York, NY'
)
```

### Zillow Property Search
```python
await SiteSpecificHandlers.zillow_property_search(
    page=page,
    location='Austin, TX',
    min_price=300000,
    max_price=500000,
    bedrooms=3
)
```

### Target Store Selector
```python
await SiteSpecificHandlers.target_store_selector(
    page=page,
    zip_code='90210'
)
```

---

## Input Types Enum

```python
InputType.TEXT           # Standard text input
InputType.EMAIL          # Email input
InputType.PASSWORD       # Password input
InputType.NUMBER         # Numeric input
InputType.AUTOCOMPLETE   # Typeahead/autocomplete
InputType.LOCATION       # Google Places autocomplete
InputType.SELECT_NATIVE  # Standard <select>
InputType.SELECT_CUSTOM  # Custom styled dropdown
InputType.RADIO          # Radio button group
InputType.CHECKBOX       # Checkbox(es)
InputType.FILE           # File upload
InputType.SLIDER         # Range slider
InputType.DATE_PICKER    # Date picker
```

---

## Form Types Enum

```python
FormType.SIMPLE        # Basic form
FormType.AUTOCOMPLETE  # Has autocomplete inputs
FormType.CONDITIONAL   # Conditional fields
FormType.MULTI_STEP    # Wizard with steps
FormType.DYNAMIC       # AJAX-loaded fields
FormType.COMPLEX       # Combination of above
```

---

## FormField Object

```python
FormField(
    selector='input[name="email"]',      # CSS selector
    value='test@example.com',            # Value to fill
    input_type=InputType.EMAIL,          # Type of input
    wait_for_selector=None,              # Wait for this before filling
    validate_selector=None,              # Validation check
    retry_count=3                        # Number of retries
)
```

---

## FormStep Object

```python
FormStep(
    step_number=1,                       # Step number
    fields=[...],                        # List of FormField objects
    next_button_selector='button.next',  # Button to next step
    validation_selector='.step-valid'    # Validation element
)
```

---

## Configuration

### Timeouts
```python
handler.DEFAULT_TIMEOUT = 10000                        # 10 sec
handler.AUTOCOMPLETE_SUGGESTION_TIMEOUT = 5000         # 5 sec
handler.AJAX_LOAD_TIMEOUT = 3000                       # 3 sec
```

### Delays
```python
handler.TYPING_DELAY_MS = (50, 150)                    # Per keystroke
handler.CLICK_DELAY_MS = (100, 300)                    # After click
handler.FORM_FIELD_DELAY_MS = (200, 500)               # Between fields
handler.STEP_TRANSITION_DELAY_MS = (500, 1000)         # Between steps
```

### Disable Humanization
```python
handler = ComplexFormHandler(page, use_humanization=False)
```

---

## Error Handling

```python
try:
    success = await handler.fill_autocomplete(selector, value)

    if not success:
        logger.error("Fill failed after retries")

except Exception as e:
    logger.error(f"Error: {e}")
```

---

## Return Values

Most methods return:
- `True/False` - Simple success/failure
- `Dict` - Detailed results (for multi-step forms)

Example multi-step result:
```python
{
    'success': True,
    'steps_completed': 2,
    'filled_fields': ['input[name="email"]', ...],
    'failed_fields': []
}
```

---

## Advanced: Conditional Fields

```python
FormField(
    selector='select[name="state"]',
    value='California',
    input_type=InputType.SELECT_NATIVE,
    wait_for_selector='select[name="state"]:visible'  # Wait for field to appear
)
```

---

## Advanced: Validation

```python
FormField(
    selector='input[name="email"]',
    value='test@example.com',
    input_type=InputType.EMAIL,
    validate_selector='.email-valid-icon'  # Wait for validation to pass
)
```

---

## Tips

1. Always call `wait_for_form_ready()` first
2. Use `detect_form_type()` for adaptive handling
3. Enable humanization for anti-bot sites
4. Use site-specific handlers when available
5. Add validation selectors for critical fields
6. Increase timeouts for slow sites
7. Check return values for success confirmation

---

## Files

| File | Purpose |
|------|---------|
| `complex_form_handler.py` | Main module |
| `COMPLEX_FORM_HANDLER_README.md` | Full documentation |
| `complex_form_handler_example.py` | Usage examples |
| `complex_form_handler_test.py` | Unit tests |
| `COMPLEX_FORM_INTEGRATION.md` | Integration guide |
| `COMPLEX_FORM_QUICKREF.md` | This file |

---

## Run Examples

```bash
# All examples
python complex_form_handler_example.py

# Specific example
python complex_form_handler_example.py 3  # Indeed search
```

---

## Run Tests

```bash
python complex_form_handler_test.py
```

---

**Location:** `/mnt/c/ev29/eversale-cli/engine/agent/complex_form_handler.py`

**Version:** 1.0.0

**Created:** December 6, 2025

