"""
Error utility functions for generating helpful error messages and formatting outputs.

Extracted from brain_enhanced_v2.py to make error handling reusable across modules.
"""

import json
from typing import Any, Dict


# Error guidance dictionary containing all error types with helpful messages
ERROR_GUIDANCE = {
    "timeout": {
        "message": "The page took too long to load.",
        "suggestions": [
            "Try again - the site may be temporarily slow",
            "Check if the URL is correct",
            "The site may be blocking automated access"
        ]
    },
    "navigation": {
        "message": "Could not navigate to the page.",
        "suggestions": [
            "Verify the URL is correct and accessible",
            "The site may require login - try logging in manually first",
            "Check your internet connection"
        ]
    },
    "login_required": {
        "message": "This page requires authentication.",
        "suggestions": [
            "Please log in to the site manually in the browser",
            "After logging in, say 'continue' and I'll retry",
            "Your session cookies will be saved for future use"
        ]
    },
    "captcha": {
        "message": "The site is showing a CAPTCHA challenge.",
        "suggestions": [
            "Please solve the CAPTCHA manually in the browser",
            "After solving, say 'continue' and I'll retry",
            "Consider using a different approach or site"
        ]
    },
    "blocked": {
        "message": "The site appears to be blocking automated access.",
        "suggestions": [
            "Try accessing the site manually first",
            "Use a different browser profile",
            "The site may have anti-bot protection"
        ]
    },
    "rate_limited": {
        "message": "The site is rate limiting requests.",
        "suggestions": [
            "Wait a few minutes before trying again",
            "Reduce the frequency of requests",
            "The site may have usage limits"
        ]
    },
    "no_data": {
        "message": "No matching data found on the page.",
        "suggestions": [
            "Verify the page contains the information you're looking for",
            "Try a more specific or different search query",
            "The page structure may have changed"
        ]
    },
    "content_empty": {
        "message": "The page loaded but appears to be empty.",
        "suggestions": [
            "The page may require JavaScript to load content",
            "Check if the URL is correct",
            "The site may be experiencing issues"
        ]
    },
    "extraction_failed": {
        "message": "Could not extract the requested information.",
        "suggestions": [
            "Try rephrasing your extraction request",
            "The page may use dynamic content that's hard to extract",
            "Consider using CSS selectors for known site patterns"
        ]
    },
    "invalid_url": {
        "message": "The URL format is invalid.",
        "suggestions": [
            "Use a complete URL like https://example.com",
            "Check for typos or special characters",
            "Make sure the domain is correct"
        ]
    }
}


def friendly_error(error_type: str, details: str = "", url: str = "") -> str:
    """
    Generate helpful error messages with guidance for common issues.

    Args:
        error_type: Type of error (timeout, blocked, login_required, etc.)
        details: Additional error details to include
        url: URL where the error occurred

    Returns:
        Formatted error message with suggestions

    Example:
        >>> friendly_error("timeout", "Page took 60s to load", "https://example.com")
        ❌ The page took too long to load.
        Details: Page took 60s to load
        URL: https://example.com

        💡 Suggestions:
          • Try again - the site may be temporarily slow
          • Check if the URL is correct
          • The site may be blocking automated access
    """
    info = ERROR_GUIDANCE.get(error_type, {
        "message": f"An error occurred: {error_type}",
        "suggestions": ["Please try again", "Check the URL and try a different approach"]
    })

    result = f"❌ {info['message']}"
    if details:
        result += f"\nDetails: {details}"
    if url:
        result += f"\nURL: {url}"
    result += "\n\n💡 Suggestions:\n" + "\n".join(f"  • {s}" for s in info['suggestions'])
    return result


def format_extract_output(data: Any, title: str = "Data") -> str:
    """
    Format extracted data for display, with fallback to string representation.

    Args:
        data: Data to format (dict, list, or any other type)
        title: Title prefix for the output

    Returns:
        Formatted string representation of the data (max 1200 chars)

    Example:
        >>> format_extract_output({"name": "John", "email": "john@example.com"}, "Contact")
        Contact:
        {
          "name": "John",
          "email": "john@example.com"
        }
    """
    if not data:
        return f"{title}: no data found."
    try:
        return f"{title}:\n{json.dumps(data, indent=2, default=str)[:1200]}"
    except Exception:
        # Fallback to string representation with length limit
        text = str(data)
        if len(text) > 1200:
            text = text[:1200].rstrip() + "..."
        return f"{title}: {text}"
