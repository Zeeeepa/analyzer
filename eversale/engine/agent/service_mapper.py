"""
Service URL Mapper - Maps common service names to their exact URLs.
Ensures precise navigation to subdomains and specific services.
"""

from typing import Optional, Tuple
import re

# Service name -> exact URL mapping
SERVICE_URLS = {
    # Google Services
    "gmail": "https://mail.google.com",
    "google mail": "https://mail.google.com",
    "mail.google.com": "https://mail.google.com",
    "google maps": "https://www.google.com/maps",
    "maps": "https://www.google.com/maps",
    "maps.google.com": "https://www.google.com/maps",
    "google drive": "https://drive.google.com",
    "drive": "https://drive.google.com",
    "google docs": "https://docs.google.com",
    "google sheets": "https://sheets.google.com",
    "google calendar": "https://calendar.google.com",
    "youtube": "https://www.youtube.com",

    # Email Services
    "outlook": "https://outlook.live.com",
    "outlook mail": "https://outlook.live.com",
    "hotmail": "https://outlook.live.com",
    "yahoo mail": "https://mail.yahoo.com",
    "protonmail": "https://mail.proton.me",
    "zoho mail": "https://mail.zoho.com",
    "mail.zoho.com": "https://mail.zoho.com",

    # Social Media
    "facebook": "https://www.facebook.com",
    "facebook ads library": "https://www.facebook.com/ads/library",
    "fb ads library": "https://www.facebook.com/ads/library",
    "fb ads": "https://www.facebook.com/ads/library",
    "instagram": "https://www.instagram.com",
    "twitter": "https://twitter.com",
    "x": "https://twitter.com",
    "linkedin": "https://www.linkedin.com",
    "reddit": "https://www.reddit.com",
    "tiktok": "https://www.tiktok.com",

    # Business Tools
    "hubspot": "https://app.hubspot.com",
    "salesforce": "https://login.salesforce.com",
    "slack": "https://slack.com",
    "notion": "https://www.notion.so",
    "airtable": "https://airtable.com",
    "zapier": "https://zapier.com",

    # Developer Tools
    "github": "https://github.com",
    "gitlab": "https://gitlab.com",
    "stackoverflow": "https://stackoverflow.com",
    "npmjs": "https://www.npmjs.com",
}

# URL patterns that should be navigated to directly
DIRECT_URL_PATTERNS = [
    r'^https?://',  # Full URLs
    r'^www\.',      # www URLs
    r'^\w+\.\w+\.\w+',  # subdomain.domain.tld
    r'^\w+\.\w{2,}/',   # domain.tld/path
]


def resolve_service_url(text: str) -> Optional[str]:
    """
    Resolve a service name or URL mention to an exact URL.

    Args:
        text: User input that may contain a service name or URL

    Returns:
        Exact URL to navigate to, or None if not found
    """
    text_lower = text.lower().strip()

    # First check if it's already a URL
    for pattern in DIRECT_URL_PATTERNS:
        if re.match(pattern, text_lower):
            url = text_lower
            if not url.startswith('http'):
                url = 'https://' + url
            return url

    # Check service mappings
    for service_name, url in SERVICE_URLS.items():
        if service_name in text_lower:
            return url

    return None


def extract_navigation_target(prompt: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract navigation target from a prompt.

    Args:
        prompt: Full user prompt like "go to gmail" or "navigate to mail.google.com"

    Returns:
        Tuple of (url, search_query) - one will be None
    """
    prompt_lower = prompt.lower()

    # Patterns for navigation commands
    nav_patterns = [
        r'(?:go to|navigate to|open|visit)\s+([^\s,]+(?:\.[^\s,]+)?)',
        r'(?:go to|navigate to|open|visit)\s+([^,]+?)(?:,|and|then|$)',
    ]

    for pattern in nav_patterns:
        match = re.search(pattern, prompt_lower)
        if match:
            target = match.group(1).strip()
            url = resolve_service_url(target)
            if url:
                return url, None

    # Check for service mentions without explicit navigation command
    for service_name, url in SERVICE_URLS.items():
        if service_name in prompt_lower:
            return url, None

    return None, None


def build_maps_search_url(query: str, location: Optional[str] = None) -> str:
    """Build a Google Maps search URL with query and optional location."""
    import urllib.parse

    search_term = query
    if location:
        search_term = f"{query} near {location}"

    encoded_query = urllib.parse.quote(search_term)
    return f"https://www.google.com/maps/search/{encoded_query}"


def extract_maps_query(prompt: str) -> Optional[str]:
    """Extract search query for Google Maps from prompt."""
    prompt_lower = prompt.lower()

    # Patterns for maps searches
    patterns = [
        r'(?:find|search for|look for)\s+(.+?)\s+(?:on|in|from)\s+(?:google\s+)?maps',
        r'(?:google\s+)?maps?\s+(?:search|find)\s+(.+)',
        r'(?:find|search)\s+(.+?)\s+(?:business|shop|store|restaurant|plumber|doctor)',
        r'(?:plumber|restaurant|store|shop|business)\s+(?:in|near)\s+(.+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, prompt_lower)
        if match:
            return match.group(1).strip()

    return None
