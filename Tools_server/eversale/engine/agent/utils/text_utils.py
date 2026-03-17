"""Text utility functions for Eversale agent.

This module provides text processing utilities including:
- Text truncation and cleanup
- URL extraction from text
- URL stripping from text
"""

import re
from typing import List


def shorten_text(text: str, limit: int = 800) -> str:
    """Shorten text to a specified limit with whitespace cleanup.

    Args:
        text: The text to shorten
        limit: Maximum length (default: 800 characters)

    Returns:
        Shortened text with normalized whitespace, appending "..." if truncated

    Examples:
        >>> shorten_text("Hello   world", 100)
        "Hello world"
        >>> shorten_text("A" * 1000, 10)
        "AAAAAAAAAA..."
    """
    if not text:
        return ""
    clean = re.sub(r'\s+', ' ', str(text)).strip()
    return clean if len(clean) <= limit else clean[:limit].rstrip() + "..."


def extract_urls(text: str) -> List[str]:
    """Extract URLs or bare domains from text.

    Supports:
    - Full URLs (http://, https://)
    - www. prefixed domains
    - Bare domains (example.com)
    - Preserves balanced parentheses (for Wikipedia URLs)

    Args:
        text: The text to extract URLs from

    Returns:
        List of unique URLs (normalized to https://)

    Examples:
        >>> extract_urls("Visit https://example.com and www.test.org")
        ['https://example.com', 'https://www.test.org']
        >>> extract_urls("Check example.com for info")
        ['https://example.com']
    """
    if not text:
        return []
    pattern = r'(https?://[^\s\'"]+|www\.[^\s\'"]+|\b[a-zA-Z0-9.-]+\.[a-z]{2,}(?:/[^\s\'"]*)?)'
    urls = []
    for match in re.findall(pattern, text):
        url = match.strip()
        # Strip trailing punctuation, but preserve balanced parentheses (for Wikipedia URLs)
        while url and url[-1] in '.,;]':
            url = url[:-1]
        # Only strip trailing ) if unbalanced (more closing than opening)
        while url and url[-1] == ')' and url.count(')') > url.count('('):
            url = url[:-1]
        if not url:
            continue
        if not url.startswith('http://') and not url.startswith('https://'):
            url = 'https://' + url.lstrip('/')
        if url not in urls:
            urls.append(url)
    return urls


def strip_urls(text: str, urls: List[str]) -> str:
    """Remove URL strings from text to isolate the user's ask.

    Removes both the full URL and bare domain versions, then cleans up
    orphaned navigation phrases like "go to", "visit", etc.

    Args:
        text: The text to clean
        urls: List of URLs to remove

    Returns:
        Cleaned text with URLs and orphaned navigation phrases removed

    Examples:
        >>> strip_urls("Go to https://example.com and search", ["https://example.com"])
        "search"
        >>> strip_urls("Visit www.test.org for info", ["https://www.test.org"])
        "for info"
    """
    cleaned = text
    for u in urls:
        cleaned = cleaned.replace(u, "")
        bare = u.replace("https://", "").replace("http://", "")
        cleaned = cleaned.replace(bare, "")
    # Clean up orphaned navigation phrases after URL removal
    cleaned = re.sub(r'\b(go to|visit|navigate to|open|browse to)\s+and\b', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\b(go to|visit|navigate to|open|browse to)\s*$', '', cleaned, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', cleaned).strip()
