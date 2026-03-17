# Unified Validators Module

**Location**: `/mnt/c/ev29/cli/engine/agent/utils/validators.py`

## Overview

Centralized validation logic consolidating patterns from multiple modules:
- `reliability_core.py` - URL, selector validation (best implementation)
- `data_validator.py` - Email validation with regex patterns
- `agentic_guards.py` - Phone, URL normalization
- `command_parser.py` - URL normalization
- `deduplicator.py` - URL normalization for comparison

## Import

```python
# Import specific validators
from engine.agent.utils.validators import (
    validate_url, validate_email, validate_phone,
    normalize_url, sanitize_filename
)

# Or import from utils package
from engine.agent.utils import validate_url, is_valid_email

# Or import all
from engine.agent.utils.validators import *
```

## Quick Reference

### URL Validation & Normalization

```python
# Validate URL (returns tuple: bool, error_message)
valid, error = validate_url("https://example.com")
# (True, None)

valid, error = validate_url("not a url")
# (False, "URL must include scheme (http:// or https://)")

# Require HTTPS
valid, error = validate_url("http://test.com", require_https=True)
# (False, "HTTPS required but got: http")

# Normalize URL (add scheme, remove www, etc.)
url = normalize_url("example.com")
# "https://example.com"

url = normalize_url("www.example.com", remove_www=True)
# "https://example.com"

# Normalize for comparison (lowercase, remove www, trailing slash)
url = normalize_url_for_comparison("HTTPS://WWW.Example.com/Path/")
# "https://example.com/path"

# Quick boolean check
if is_valid_url(url):
    # ...
```

### Email Validation

```python
# Validate email (returns tuple: bool, message)
valid, msg = validate_email("user@company.com")
# (True, "Valid")

valid, msg = validate_email("test@test.com")
# (False, "Garbage email detected: test@test.com")

# Quick boolean check
if is_valid_email(email):
    # ...
```

### Phone Validation & Normalization

```python
# Validate phone (returns tuple: bool, message)
valid, msg = validate_phone("+1 (555) 123-4567")
# (True, "Valid")

valid, msg = validate_phone("123")
# (False, "Invalid phone length: 123")

# Normalize phone (digits only, remove US country code)
phone = normalize_phone("+1 (555) 123-4567")
# "5551234567"

# Quick boolean check
if is_valid_phone(phone):
    # ...
```

### Selector Validation

```python
# Validate CSS/XPath/Playwright selector (returns tuple: bool, error_message)
valid, error = validate_selector("button.primary")
# (True, None)

valid, error = validate_selector("//div[@id='main']")
# (True, None)

valid, error = validate_selector("text=Click me")
# (True, None)

valid, error = validate_selector("")
# (False, "Selector must be a non-empty string")

# Quick boolean check
if is_valid_selector(selector):
    # ...
```

### Ref Validation

```python
# Validate accessibility reference/MMID (returns tuple: bool, error_message)
valid, error = validate_ref("header-nav-1")
# (True, None)

valid, error = validate_ref("invalid ref!")
# (False, "Ref must be alphanumeric with hyphens/underscores only. Got: invalid ref!")

# Quick boolean check
if is_valid_ref(ref):
    # ...
```

### JSON Validation

```python
# Validate and parse JSON (returns tuple: bool, parsed_data_or_None)
valid, data = validate_json('{"key": "value"}')
# (True, {'key': 'value'})

valid, data = validate_json('not json')
# (False, None)

# Quick boolean check
if is_valid_json(text):
    # ...
```

### Filename Sanitization

```python
# Sanitize filename (remove invalid chars, ensure safe for filesystem)
filename = sanitize_filename("My File: Test.txt")
# "My File_ Test.txt"

filename = sanitize_filename("file/with\\path.txt")
# "file_with_path.txt"

filename = sanitize_filename("   leading spaces.txt   ")
# "leading_spaces.txt"
```

## Function Reference

### Validation Functions (return tuple)

| Function | Returns | Description |
|----------|---------|-------------|
| `validate_url(url, require_https=False)` | `(bool, str or None)` | Validate URL format and scheme |
| `validate_email(email)` | `(bool, str)` | Validate email address format |
| `validate_phone(phone)` | `(bool, str)` | Validate phone number format |
| `validate_selector(selector)` | `(bool, str or None)` | Validate CSS/XPath/Playwright selector |
| `validate_ref(ref)` | `(bool, str or None)` | Validate accessibility reference (MMID) |
| `validate_json(text)` | `(bool, dict or None)` | Validate and parse JSON string |

### Normalization Functions (return string)

| Function | Returns | Description |
|----------|---------|-------------|
| `normalize_url(url, add_scheme=True, remove_www=False, remove_trailing_slash=False)` | `str` | Normalize URL to canonical format |
| `normalize_url_for_comparison(url)` | `str` | Normalize URL for deduplication (lowercase, no www, no trailing slash) |
| `normalize_phone(phone)` | `str` | Normalize phone to digits only, remove US country code |
| `sanitize_filename(filename, replacement='_')` | `str` | Remove invalid characters from filename |

### Convenience Functions (return bool)

| Function | Returns | Description |
|----------|---------|-------------|
| `is_valid_url(url)` | `bool` | Quick boolean URL check |
| `is_valid_email(email)` | `bool` | Quick boolean email check |
| `is_valid_phone(phone)` | `bool` | Quick boolean phone check |
| `is_valid_selector(selector)` | `bool` | Quick boolean selector check |
| `is_valid_ref(ref)` | `bool` | Quick boolean ref check |
| `is_valid_json(text)` | `bool` | Quick boolean JSON check |

## Design Principles

1. **Single Source of Truth**: All validation logic in one place
2. **Consistent Return Types**: Validation functions return `(bool, error_or_data)` tuples
3. **Comprehensive Error Messages**: Clear error messages for debugging
4. **Performance Optimized**: Compiled regex patterns for speed
5. **Convenience Functions**: Quick boolean checks available for all validators

## Migrating Existing Code

Replace scattered validation with unified validators:

```python
# BEFORE (scattered across multiple files)
from reliability_core import InputValidator
validator = InputValidator()
valid, error = validator.validate_url(url)

# AFTER (unified)
from engine.agent.utils import validate_url
valid, error = validate_url(url)
```

## Supported Patterns

### URL Schemes
- `http://`, `https://`, `file://`, `ftp://`, `ftps://`

### Email Patterns
- Standard RFC 5322 format
- Rejects garbage patterns: `example.com`, `test@test`, `noreply@`, etc.

### Phone Patterns
- Accepts 7-15 digits with flexible formatting
- Rejects garbage: `0000000`, `1111111`, `1234567`, `9999999`

### Selector Patterns
- CSS selectors
- XPath (`//`, `(`)
- Playwright selectors (`text=`, `role=`, `data-testid=`, `placeholder=`, `alt=`, `title=`)

### Ref Patterns
- Alphanumeric with hyphens and underscores only
- Max 100 characters

## Examples

See comprehensive test suite in `/mnt/c/ev29/cli/engine/agent/utils/validators.py` docstrings.
