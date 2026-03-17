"""
Utility functions for the agent module.
"""

from .error_utils import (
    ERROR_GUIDANCE,
    friendly_error,
    format_extract_output
)

from .cache_base import (
    CacheBase,
    AsyncCacheBase,
    create_llm_cache,
    create_selector_cache,
    create_dom_cache,
    create_session_cache,
    create_api_cache,
    create_memory_only_cache
)

from .validators import (
    validate_url,
    validate_selector,
    validate_ref,
    validate_email,
    validate_phone,
    validate_json,
    normalize_url,
    normalize_url_for_comparison,
    normalize_phone,
    sanitize_filename,
    is_valid_url,
    is_valid_email,
    is_valid_phone,
    is_valid_selector,
    is_valid_ref,
    is_valid_json
)

__all__ = [
    'ERROR_GUIDANCE',
    'friendly_error',
    'format_extract_output',
    'CacheBase',
    'AsyncCacheBase',
    'create_llm_cache',
    'create_selector_cache',
    'create_dom_cache',
    'create_session_cache',
    'create_api_cache',
    'create_memory_only_cache',
    'validate_url',
    'validate_selector',
    'validate_ref',
    'validate_email',
    'validate_phone',
    'validate_json',
    'normalize_url',
    'normalize_url_for_comparison',
    'normalize_phone',
    'sanitize_filename',
    'is_valid_url',
    'is_valid_email',
    'is_valid_phone',
    'is_valid_selector',
    'is_valid_ref',
    'is_valid_json'
]
