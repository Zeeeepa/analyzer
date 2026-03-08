from typing import Dict, List, Any

# Platform identification patterns (Data only)
PLATFORM_FB_ADS = "fb_ads"
PLATFORM_REDDIT = "reddit"
PLATFORM_LINKEDIN = "linkedin"
PLATFORM_GOOGLE_MAPS = "google_maps"

PLATFORM_INDICATORS = {
    PLATFORM_FB_ADS: {
        "keywords": ["ads library", "meta ads", "facebook ads", "fb ads"],
        "workflow": "fb_ads",
        "default_query": "booked meetings"
    },
    PLATFORM_REDDIT: {
        "keywords": ["subreddit", "redditor", "thread", "karma", "upvotes", "downvotes", "commenters", "commenter", "on reddit", "reddit"],
        "workflow": "reddit",
        "default_topic": "lead generation"
    },
    PLATFORM_LINKEDIN: {
        "keywords": ["linkedin", "/in/", "linkedin.com/in", "linkedin posts", "thought leader"],
        "workflow": "linkedin_warm",
        "default_query": "sales"
    },
    PLATFORM_GOOGLE_MAPS: {
        "keywords": ["google maps", "maps.google"],
        "workflow": "google_maps",
        "default_query": "businesses"
    }
}

# Navigation service mappings
NAVIGATION_SERVICES = {
    "zoho": {"keywords": ["zoho", "zoho mail"], "url": "mail.zoho.com"},
    "gmail": {"keywords": ["gmail", "google mail"], "url": "mail.google.com"},
    "outlook": {"keywords": ["outlook", "hotmail"], "url": "outlook.live.com"},
    "yahoo": {"keywords": ["yahoo", "yahoo mail"], "url": "mail.yahoo.com"}
}

# Regex patterns for count extraction
COUNT_PATTERNS = [
    r'(?:find|get|search|show|give|extract|scrape|output|return|collect|gather)\s+(?:exactly\s+)?(\d+)\b',
    r'(\d+)\s+(?:reddit|linkedin|fb|facebook|advertiser|user|lead|profile|person|people|unique)',
    r'(?:top|first|best)\s+(\d+)(?:\s+|$)',
    r'(?:collect|gather)\s+(\d+)\s+unique',
]

# TLDs for generic navigation fix
COMMON_TLDS = [".com", ".org", ".net", ".io", ".gov", ".edu", ".ai", ".app", ".dev"]

SITE_NAME_TO_URL = {
    'wikipedia': 'https://en.wikipedia.org',
    'google': 'https://www.google.com',
    'reddit': 'https://www.reddit.com',
    'hackernews': 'https://news.ycombinator.com',
    'hn': 'https://news.ycombinator.com',
    'facebook': 'https://www.facebook.com',
    'fb': 'https://www.facebook.com',
    'twitter': 'https://twitter.com',
    'linkedin': 'https://www.linkedin.com',
    'youtube': 'https://www.youtube.com',
    'amazon': 'https://www.amazon.com',
    'github': 'https://github.com',
    'example': 'https://example.com',
    'gmail': 'https://mail.google.com',
    'zoho': 'https://mail.zoho.com',
    # AI Assistants
    'claude': 'https://claude.ai',
    'chatgpt': 'https://chatgpt.com',
    'openai': 'https://chatgpt.com',
    'gemini': 'https://gemini.google.com',
    'perplexity': 'https://www.perplexity.ai',
    'grok': 'https://grok.com',
    'copilot': 'https://copilot.microsoft.com',
    # SDR/Outbound Tools
    'apollo': 'https://app.apollo.io',
    'lemlist': 'https://app.lemlist.com',
    'smartlead': 'https://app.smartlead.ai',
    'instantly': 'https://app.instantly.ai',
    'hunter': 'https://hunter.io',
    'snov': 'https://app.snov.io',
    'outreach': 'https://app.outreach.io',
    'salesloft': 'https://app.salesloft.com',
    'zoominfo': 'https://app.zoominfo.com',
    'lusha': 'https://www.lusha.com',
    'seamless': 'https://www.seamless.ai',
}
