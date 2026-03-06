"""
Rust Bridge - Unified interface for Rust FFI acceleration

Provides a consistent interface that uses Rust when available, with Python fallbacks.
This module abstracts away the FFI complexity and provides simple, drop-in replacements.

Usage:
    from rust_bridge import extract_emails, parse_dom, json_parse, deduplicate_contacts

    # Will use Rust if available, Python fallback otherwise
    emails = extract_emails(text)
"""

import json
import re
from typing import Dict, List, Any, Optional, Tuple
from loguru import logger

# Try to import Rust core library
try:
    import eversale_core
    USE_RUST_CORE = True
    logger.info("Rust core library loaded - performance optimizations enabled")
except ImportError:
    USE_RUST_CORE = False
    # Silently use Python fallbacks - Rust is optional
    logger.debug("Rust core library not available - using Python fallbacks")


# ==============================================================================
# EMAIL EXTRACTION
# ==============================================================================

def extract_emails(text: str) -> List[str]:
    """
    Extract all email addresses from text.
    Uses Rust implementation when available for 10-100x speedup.
    """
    if USE_RUST_CORE:
        try:
            return eversale_core.extract_emails(text)
        except Exception as e:
            logger.warning(f"Rust extract_emails failed, falling back to Python: {e}")

    # Python fallback
    pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    return re.findall(pattern, text, re.IGNORECASE)


def extract_phones(text: str) -> List[str]:
    """
    Extract all phone numbers from text.
    Uses Rust implementation when available for 10-100x speedup.
    """
    if USE_RUST_CORE:
        try:
            return eversale_core.extract_phones(text)
        except Exception as e:
            logger.warning(f"Rust extract_phones failed, falling back to Python: {e}")

    # Python fallback
    patterns = [
        r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
        r'\b\(\d{3}\)\s*\d{3}[-.]?\d{4}\b',
        r'\b1[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b',
        r'\+\d{1,3}[-.\s]?\d{1,14}\b',
    ]
    phones = []
    for pattern in patterns:
        phones.extend(re.findall(pattern, text))
    return phones


def extract_contacts(text: str) -> Dict[str, List[str]]:
    """
    Extract all contact information (emails + phones) from text.
    Uses Rust implementation when available.
    """
    if USE_RUST_CORE:
        try:
            return eversale_core.extract_contacts(text)
        except Exception as e:
            logger.warning(f"Rust extract_contacts failed, falling back to Python: {e}")

    # Python fallback
    return {
        'emails': extract_emails(text),
        'phones': extract_phones(text)
    }


def deduplicate_contacts(contacts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Deduplicate a list of contact dictionaries.
    Uses Rust implementation when available for faster processing.
    """
    if USE_RUST_CORE:
        try:
            return eversale_core.deduplicate_contacts(contacts)
        except Exception as e:
            logger.warning(f"Rust deduplicate_contacts failed, falling back to Python: {e}")

    # Python fallback
    seen = set()
    unique = []
    for contact in contacts:
        # Create a unique key from email or phone
        key = contact.get('email') or contact.get('phone') or str(contact)
        if key not in seen:
            seen.add(key)
            unique.append(contact)
    return unique


# ==============================================================================
# DOM PARSING
# ==============================================================================

def parse_accessibility_tree(snapshot_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse Playwright accessibility snapshot into structured tree.
    Uses Rust implementation when available for faster processing.
    """
    if USE_RUST_CORE:
        try:
            return eversale_core.parse_accessibility_tree(snapshot_dict)
        except Exception as e:
            logger.warning(f"Rust parse_accessibility_tree failed, falling back to Python: {e}")

    # Python fallback - return as-is
    return snapshot_dict


def fast_snapshot(elements_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Fast DOM snapshot processing.
    Uses Rust implementation when available.
    """
    if USE_RUST_CORE:
        try:
            return eversale_core.fast_snapshot(elements_data)
        except Exception as e:
            logger.warning(f"Rust fast_snapshot failed, falling back to Python: {e}")

    # Python fallback
    return {
        'total': len(elements_data),
        'interactive': sum(1 for e in elements_data if e.get('is_interactive', False)),
        'elements': elements_data
    }


def extract_elements(html: str, selector_type: str = 'interactive') -> List[Dict[str, Any]]:
    """
    Extract elements from HTML.
    Uses Rust implementation when available for faster HTML parsing.
    """
    if USE_RUST_CORE:
        try:
            return eversale_core.extract_elements(html, selector_type)
        except Exception as e:
            logger.warning(f"Rust extract_elements failed, falling back to Python: {e}")

    # Python fallback - basic extraction
    # This is a simplified fallback; real implementation would use BeautifulSoup
    return []


# ==============================================================================
# JSON PROCESSING
# ==============================================================================

def fast_json_parse(json_str: str) -> Any:
    """
    Fast JSON parsing.
    Uses Rust implementation when available for 2-5x speedup on large JSON.
    """
    if USE_RUST_CORE:
        try:
            return eversale_core.fast_json_parse(json_str)
        except Exception as e:
            logger.warning(f"Rust fast_json_parse failed, falling back to Python: {e}")

    # Python fallback
    return json.loads(json_str)


def fast_json_dumps(obj: Any) -> str:
    """
    Fast JSON serialization.
    Uses Rust implementation when available for 2-5x speedup on large objects.
    """
    if USE_RUST_CORE:
        try:
            return eversale_core.fast_json_dumps(obj)
        except Exception as e:
            logger.warning(f"Rust fast_json_dumps failed, falling back to Python: {e}")

    # Python fallback
    return json.dumps(obj)


# ==============================================================================
# PATTERN MATCHING (for LLM extraction)
# ==============================================================================

class CompiledPatterns:
    """
    Pre-compiled regex patterns for fast matching.
    Uses Rust implementation when available for 10-100x speedup.
    """

    def __init__(self):
        self.use_rust = USE_RUST_CORE
        if self.use_rust:
            try:
                self._rust_patterns = eversale_core.CompiledPatterns()
            except Exception as e:
                logger.warning(f"Failed to initialize Rust CompiledPatterns: {e}")
                self.use_rust = False

        if not self.use_rust:
            # Python fallback - compile patterns
            self._email_re = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', re.IGNORECASE)
            # Multiple phone patterns for comprehensive matching
            self._phone_patterns = [
                re.compile(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'),
                re.compile(r'\b\(\d{3}\)\s*\d{3}[-.]?\d{4}\b'),
                re.compile(r'\+\d{1,3}[-.\s]?\d{1,3}[-.\s]?\d{3,4}[-.\s]?\d{4}\b'),
            ]
            self._url_re = re.compile(r'https?://[^\s<>"\']+')

    def find_emails(self, text: str) -> List[str]:
        """Find all emails in text."""
        if self.use_rust:
            try:
                return self._rust_patterns.find_emails(text)
            except Exception as e:
                logger.warning(f"Rust find_emails failed: {e}")

        return self._email_re.findall(text)

    def find_phones(self, text: str) -> List[str]:
        """Find all phone numbers in text."""
        if self.use_rust:
            try:
                return self._rust_patterns.find_phones(text)
            except Exception as e:
                logger.warning(f"Rust find_phones failed: {e}")

        # Python fallback - use all patterns
        phones = []
        for pattern in self._phone_patterns:
            phones.extend(pattern.findall(text))
        return phones

    def find_urls(self, text: str) -> List[str]:
        """Find all URLs in text."""
        if self.use_rust:
            try:
                return self._rust_patterns.find_urls(text)
            except Exception as e:
                logger.warning(f"Rust find_urls failed: {e}")

        return self._url_re.findall(text)


# ==============================================================================
# PERFORMANCE MONITORING
# ==============================================================================

def get_mode() -> str:
    """Return current execution mode (rust or python)."""
    return "rust" if USE_RUST_CORE else "python"


def is_rust_available() -> bool:
    """Check if Rust core is available."""
    return USE_RUST_CORE


def get_performance_info() -> Dict[str, Any]:
    """Get information about performance optimizations."""
    return {
        'rust_available': USE_RUST_CORE,
        'mode': get_mode(),
        'optimizations': {
            'email_extraction': USE_RUST_CORE,
            'phone_extraction': USE_RUST_CORE,
            'contact_deduplication': USE_RUST_CORE,
            'json_parsing': USE_RUST_CORE,
            'dom_parsing': USE_RUST_CORE,
            'pattern_matching': USE_RUST_CORE
        }
    }


# ==============================================================================
# EXPORTS
# ==============================================================================

__all__ = [
    # Email/Phone extraction
    'extract_emails',
    'extract_phones',
    'extract_contacts',
    'deduplicate_contacts',

    # DOM parsing
    'parse_accessibility_tree',
    'fast_snapshot',
    'extract_elements',

    # JSON processing
    'fast_json_parse',
    'fast_json_dumps',

    # Pattern matching
    'CompiledPatterns',

    # Utilities
    'get_mode',
    'is_rust_available',
    'get_performance_info',
    'USE_RUST_CORE'
]
