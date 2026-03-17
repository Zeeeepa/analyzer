"""
Unified validators for the agent system.
Consolidates validation logic from multiple modules into a single source of truth.

Centralizes validation from:
- reliability_core.py (URL, selector validation - best implementation)
- data_validator.py (email validation with regex patterns)
- agentic_guards.py (phone, URL normalization)
- command_parser.py (URL normalization)
- deduplicator.py (URL normalization for comparison)

Philosophy:
- Single source of truth for all validation logic
- Consistent return types (bool, tuple, or custom result objects)
- Comprehensive error messages for debugging
- Performance-optimized with compiled regex patterns
"""

import re
import json
from urllib.parse import urlparse, urlunparse
from typing import Optional, Tuple, Dict, Any


# =============================================================================
# COMPILED REGEX PATTERNS (for performance)
# =============================================================================

EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
PHONE_REGEX = re.compile(r'^[\d\s\-\+\(\)\.]{7,20}$')
URL_REGEX = re.compile(r'^https?://[^\s<>"{}|\\^`\[\]]+$')
REF_PATTERN = re.compile(r'^[a-zA-Z0-9\-_]+$')

# Garbage email patterns
GARBAGE_EMAIL_PATTERNS = [
    r'example\.com',
    r'test@test',
    r'xxx@',
    r'noreply@',
    r'no-reply@',
    r'donotreply@',
    r'placeholder',
]

# Garbage phone patterns
GARBAGE_PHONE_PATTERNS = ['0000000', '1111111', '1234567', '9999999']

# Selector patterns (from reliability_core.py)
SELECTOR_PATTERNS = {
    'css': r'^[a-zA-Z0-9\s\.\#\[\]\=\>\~\+\-\*\:\(\)\"\'\_]+$',
    'xpath': r'^(\/\/|\()',
    'text': r'^text=',
    'role': r'^role=',
    'test_id': r'^data-testid=',
    'placeholder': r'^placeholder=',
    'alt': r'^alt=',
    'title': r'^title=',
}

# Valid URL schemes
VALID_URL_SCHEMES = ('http', 'https', 'file', 'ftp', 'ftps')


# =============================================================================
# URL VALIDATION & NORMALIZATION
# =============================================================================

def validate_url(url: str, require_https: bool = False) -> Tuple[bool, Optional[str]]:
    """
    Validate URL format and scheme.
    Best implementation from reliability_core.py.

    Args:
        url: URL string to validate
        require_https: If True, only accept HTTPS URLs

    Returns:
        (is_valid, error_message) tuple
        - (True, None) if valid
        - (False, "error message") if invalid

    Examples:
        >>> validate_url("https://example.com")
        (True, None)
        >>> validate_url("not a url")
        (False, "URL must include scheme (http:// or https://)")
        >>> validate_url("http://example.com", require_https=True)
        (False, "HTTPS required but got: http")
    """
    if not url or not isinstance(url, str):
        return False, "URL must be a non-empty string"

    # Strip whitespace
    url = url.strip()

    # Parse URL
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Invalid URL format: {str(e)}"

    # Check scheme exists
    if not parsed.scheme:
        return False, "URL must include scheme (http:// or https://)"

    # Check scheme is valid
    if parsed.scheme not in VALID_URL_SCHEMES:
        return False, f"Invalid URL scheme: {parsed.scheme}. Must be one of: {', '.join(VALID_URL_SCHEMES)}"

    # Check HTTPS requirement
    if require_https and parsed.scheme != 'https':
        return False, f"HTTPS required but got: {parsed.scheme}"

    # Check netloc for http/https
    if parsed.scheme in ('http', 'https') and not parsed.netloc:
        return False, "URL must include domain (e.g., example.com)"

    return True, None


def normalize_url(url: str, add_scheme: bool = True, remove_www: bool = False,
                  remove_trailing_slash: bool = False) -> str:
    """
    Normalize URL to canonical format.
    Combines best practices from multiple modules.

    Args:
        url: URL to normalize
        add_scheme: If True, add https:// if missing
        remove_www: If True, remove www. prefix
        remove_trailing_slash: If True, remove trailing slash from path

    Returns:
        Normalized URL string

    Examples:
        >>> normalize_url("example.com")
        "https://example.com"
        >>> normalize_url("www.example.com", remove_www=True)
        "https://example.com"
        >>> normalize_url("https://example.com/path/", remove_trailing_slash=True)
        "https://example.com/path"
    """
    if not url:
        return ''

    url = url.strip()

    # Add scheme if missing
    if add_scheme and not url.startswith(('http://', 'https://', 'file://', 'ftp://', 'ftps://')):
        # Smart detection: if starts with www. or contains . without spaces, add https://
        if url.startswith('www.') or ('.' in url and ' ' not in url):
            url = f'https://{url}'

    # Parse URL
    try:
        parsed = urlparse(url)
    except Exception:
        return url  # Return original if parsing fails

    # Remove www. if requested
    netloc = parsed.netloc
    if remove_www and netloc.startswith('www.'):
        netloc = netloc[4:]

    # Handle trailing slash
    path = parsed.path
    if remove_trailing_slash and path.endswith('/') and len(path) > 1:
        path = path.rstrip('/')

    # Reconstruct URL
    normalized = urlunparse((
        parsed.scheme,
        netloc,
        path,
        parsed.params,
        parsed.query,
        parsed.fragment
    ))

    return normalized


def normalize_url_for_comparison(url: str) -> str:
    """
    Normalize URL for deduplication/comparison purposes.
    From deduplicator.py - strips www, lowercases, removes trailing slash.

    Args:
        url: URL to normalize

    Returns:
        Normalized URL for comparison

    Examples:
        >>> normalize_url_for_comparison("HTTPS://WWW.Example.com/Path/")
        "https://example.com/path"
    """
    if not url:
        return ''

    # Add scheme if missing
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    try:
        parsed = urlparse(url.lower())
        # Remove www., normalize path
        netloc = parsed.netloc.replace('www.', '')
        path = parsed.path.rstrip('/')

        # Reconstruct with just scheme + netloc + path
        return f"{parsed.scheme}://{netloc}{path}"
    except Exception:
        return url.lower()


# =============================================================================
# SELECTOR VALIDATION
# =============================================================================

def validate_selector(selector: str) -> Tuple[bool, Optional[str]]:
    """
    Validate selector format.
    From reliability_core.py - supports CSS, XPath, text=, role=, and Playwright selectors.

    Args:
        selector: Selector string to validate

    Returns:
        (is_valid, error_message) tuple
        - (True, None) if valid
        - (False, "error message") if invalid

    Examples:
        >>> validate_selector("button.primary")
        (True, None)
        >>> validate_selector("//div[@id='main']")
        (True, None)
        >>> validate_selector("text=Click me")
        (True, None)
        >>> validate_selector("")
        (False, "Selector must be a non-empty string")
    """
    if not selector or not isinstance(selector, str):
        return False, "Selector must be a non-empty string"

    selector = selector.strip()

    # Empty after strip
    if not selector:
        return False, "Selector cannot be empty or whitespace only"

    # Check if it matches any known pattern
    for selector_type, pattern in SELECTOR_PATTERNS.items():
        if re.match(pattern, selector, re.IGNORECASE):
            return True, None

    # If no pattern matches, check for basic syntax errors
    if selector.count('(') != selector.count(')'):
        return False, "Unbalanced parentheses in selector"

    if selector.count('[') != selector.count(']'):
        return False, "Unbalanced brackets in selector"

    if selector.count('{') != selector.count('}'):
        return False, "Unbalanced braces in selector"

    # Passed basic checks - assume valid CSS
    return True, None


def validate_ref(ref: str) -> Tuple[bool, Optional[str]]:
    """
    Validate accessibility reference (MMID) format.
    From reliability_core.py - refs are injected by dom_distillation.py.

    Args:
        ref: Reference string to validate (should be alphanumeric with hyphens/underscores)

    Returns:
        (is_valid, error_message) tuple

    Examples:
        >>> validate_ref("header-nav-1")
        (True, None)
        >>> validate_ref("btn_submit_2024")
        (True, None)
        >>> validate_ref("invalid ref!")
        (False, "Ref must be alphanumeric with hyphens/underscores only. Got: invalid ref!")
    """
    if not ref or not isinstance(ref, str):
        return False, "Ref must be a non-empty string"

    ref = ref.strip()

    if not ref:
        return False, "Ref cannot be empty or whitespace only"

    # Check pattern
    if not REF_PATTERN.match(ref):
        return False, f"Ref must be alphanumeric with hyphens/underscores only. Got: {ref}"

    # Length check (reasonable bounds)
    if len(ref) > 100:
        return False, f"Ref is too long ({len(ref)} chars). Max 100 chars."

    return True, None


# =============================================================================
# EMAIL VALIDATION
# =============================================================================

def validate_email(email: str) -> Tuple[bool, str]:
    """
    Validate email address format.
    From agentic_guards.py and data_validator.py.

    Args:
        email: Email address to validate

    Returns:
        (is_valid, message) tuple
        - (True, "Valid") if valid
        - (False, "error message") if invalid

    Examples:
        >>> validate_email("user@example.com")
        (True, "Valid")
        >>> validate_email("invalid@")
        (False, "Invalid email format: invalid@")
        >>> validate_email("test@example.com")
        (False, "Garbage email detected: test@example.com")
    """
    if not email or not isinstance(email, str):
        return False, "Empty or invalid email"

    email = email.strip().lower()

    # Check format
    if not EMAIL_REGEX.match(email):
        return False, f"Invalid email format: {email}"

    # Check for garbage patterns
    for pattern in GARBAGE_EMAIL_PATTERNS:
        if re.search(pattern, email, re.IGNORECASE):
            return False, f"Garbage email detected: {email}"

    return True, "Valid"


# =============================================================================
# PHONE VALIDATION
# =============================================================================

def validate_phone(phone: str) -> Tuple[bool, str]:
    """
    Validate phone number format.
    From agentic_guards.py.

    Args:
        phone: Phone number to validate

    Returns:
        (is_valid, message) tuple
        - (True, "Valid") if valid
        - (False, "error message") if invalid

    Examples:
        >>> validate_phone("+1 (555) 123-4567")
        (True, "Valid")
        >>> validate_phone("123")
        (False, "Invalid phone length: 123")
        >>> validate_phone("0000000")
        (False, "Garbage phone detected: 0000000")
    """
    if not phone or not isinstance(phone, str):
        return False, "Empty or invalid phone"

    # Remove common formatting
    cleaned = re.sub(r'[\s\-\(\)\.]', '', phone)

    # Check length (should be 7-15 digits)
    digits_only = re.sub(r'[^\d]', '', cleaned)
    if len(digits_only) < 7 or len(digits_only) > 15:
        return False, f"Invalid phone length: {phone}"

    # Check for obvious garbage
    if digits_only in GARBAGE_PHONE_PATTERNS:
        return False, f"Garbage phone detected: {phone}"

    return True, "Valid"


def normalize_phone(phone: str) -> str:
    """
    Normalize phone number to digits only, removing US country code prefix.
    From deduplicator.py.

    Args:
        phone: Phone number to normalize

    Returns:
        Normalized phone number (digits only)

    Examples:
        >>> normalize_phone("+1 (555) 123-4567")
        "5551234567"
        >>> normalize_phone("1-800-FLOWERS")
        "800"
    """
    if not phone:
        return ''

    # Extract digits only
    digits = re.sub(r'\D', '', phone)

    # Remove leading 1 for US numbers
    if digits.startswith('1') and len(digits) == 11:
        digits = digits[1:]

    return digits


# =============================================================================
# JSON VALIDATION
# =============================================================================

def validate_json(text: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Validate and parse JSON string.

    Args:
        text: JSON string to validate

    Returns:
        (is_valid, parsed_data or None) tuple
        - (True, dict) if valid JSON
        - (False, None) if invalid

    Examples:
        >>> validate_json('{"key": "value"}')
        (True, {'key': 'value'})
        >>> validate_json('not json')
        (False, None)
    """
    if not text or not isinstance(text, str):
        return False, None

    try:
        parsed = json.loads(text.strip())
        return True, parsed
    except json.JSONDecodeError:
        return False, None
    except Exception:
        return False, None


# =============================================================================
# FILENAME SANITIZATION
# =============================================================================

def sanitize_filename(filename: str, replacement: str = '_') -> str:
    """
    Remove invalid characters from filename.
    Ensures filename is safe for filesystem operations across platforms.

    Args:
        filename: Filename to sanitize
        replacement: Character to replace invalid chars with (default: '_')

    Returns:
        Sanitized filename

    Examples:
        >>> sanitize_filename("My File: Test.txt")
        "My_File__Test.txt"
        >>> sanitize_filename("file/with\\path.txt")
        "file_with_path.txt"
        >>> sanitize_filename("   leading spaces.txt   ")
        "leading_spaces.txt"
    """
    if not filename:
        return 'unnamed'

    # Strip whitespace
    filename = filename.strip()

    # Replace invalid characters (Windows + Unix)
    # Invalid: < > : " / \ | ? * and ASCII control chars
    invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'
    sanitized = re.sub(invalid_chars, replacement, filename)

    # Remove leading/trailing dots and spaces (Windows doesn't like these)
    sanitized = sanitized.strip('. ')

    # Collapse multiple replacements
    if len(replacement) == 1:
        sanitized = re.sub(f'{re.escape(replacement)}+', replacement, sanitized)

    # Ensure not empty after sanitization
    if not sanitized:
        return 'unnamed'

    # Limit length (most filesystems support 255, but be conservative)
    max_length = 200
    if len(sanitized) > max_length:
        # Preserve extension if present
        parts = sanitized.rsplit('.', 1)
        if len(parts) == 2:
            name, ext = parts
            sanitized = name[:max_length - len(ext) - 1] + '.' + ext
        else:
            sanitized = sanitized[:max_length]

    return sanitized


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def is_valid_url(url: str) -> bool:
    """Quick boolean check if URL is valid."""
    valid, _ = validate_url(url)
    return valid


def is_valid_email(email: str) -> bool:
    """Quick boolean check if email is valid."""
    valid, _ = validate_email(email)
    return valid


def is_valid_phone(phone: str) -> bool:
    """Quick boolean check if phone is valid."""
    valid, _ = validate_phone(phone)
    return valid


def is_valid_selector(selector: str) -> bool:
    """Quick boolean check if selector is valid."""
    valid, _ = validate_selector(selector)
    return valid


def is_valid_ref(ref: str) -> bool:
    """Quick boolean check if ref is valid."""
    valid, _ = validate_ref(ref)
    return valid


def is_valid_json(text: str) -> bool:
    """Quick boolean check if JSON is valid."""
    valid, _ = validate_json(text)
    return valid
