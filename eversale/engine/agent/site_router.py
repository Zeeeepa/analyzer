"""
Site router: choose default sources (and ask for clarification) for general browser tasks.

Design goals:
- Works across industries by routing by intent (shopping, travel, jobs, local, research, etc.).
- Minimal: avoid hardcoding 250 brittle flows; use a small curated source set per intent.
- Predictable: if ambiguous, return a single clarifying question with 2-4 options.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus


@dataclass(frozen=True)
class Source:
    key: str
    name: str
    url: str
    why: str


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _contains_any(hay: str, needles: Tuple[str, ...]) -> bool:
    return any(n in hay for n in needles)


def _detect_region(prompt_lower: str) -> str:
    """
    Very small region detector to pick reasonable domain variants.
    Returns: "us" | "uk" | "ca" | "au" | "eu" | "in" | "global"
    """
    if not prompt_lower:
        return "global"

    if _contains_any(prompt_lower, (" united states", " usa", " us ", " u.s.", "america", "california", "texas", "nyc", "new york")):
        return "us"
    if _contains_any(prompt_lower, (" uk", " united kingdom", " england", " london", " britain")):
        return "uk"
    if _contains_any(prompt_lower, (" canada", " toronto", " vancouver", " ontario")):
        return "ca"
    if _contains_any(prompt_lower, (" australia", " sydney", " melbourne", " au ")) or "australian" in prompt_lower:
        return "au"
    if _contains_any(prompt_lower, (" india", " delhi", " mumbai", " bengaluru", " bangalore")):
        return "in"
    if _contains_any(prompt_lower, (" eu", " europe", " european union", " germany", " france", " spain", " italy", " netherlands")):
        return "eu"

    return "global"


def _brand_to_url(prompt_lower: str, region: str) -> Optional[str]:
    """
    If the prompt clearly names a destination site/app, return a reasonable start URL.
    """
    # Normalize Unicode whitespace to regular space for matching
    p = re.sub(r'[\u00a0\u2000-\u200b\u202f\u205f\u3000]+', ' ', prompt_lower)

    # Explicit "tool" destinations / sub-products (must come before broader brand checks).
    if re.search(r'ads\s+library|fb\s+ads\s+library|meta\s+ads\s+library', p):
        return "https://www.facebook.com/ads/library/"

    if re.search(r'gmail|mail\.google\.com|google\s+mail', p):
        return "https://mail.google.com/"

    if re.search(r'zoho\s+mail|mail\.zoho', p):
        return "https://mail.zoho.com/"

    # Common explicit destinations
    # Hacker News (avoid misrouting due to "news" substring in "hackernews")
    if (
        "news.ycombinator.com" in p
        or re.search(r"(?:^|\b)(?:hacker\s*news|hackernews|hn)(?:\b|$)", p)
    ):
        return "https://news.ycombinator.com/"

    if "youtube" in p:
        return "https://www.youtube.com/"
    if "wikipedia" in p or "wiki" in p:
        return "https://en.wikipedia.org/"
    if "github" in p:
        return "https://github.com/"
    if re.search(r'stack\s+overflow|stackoverflow', p):
        return "https://stackoverflow.com/"
    if "reddit" in p:
        return "https://www.reddit.com/"
    if "linkedin" in p:
        return "https://www.linkedin.com/"
    if "x.com" in p or "twitter" in p:
        return "https://x.com/"
    if "instagram" in p:
        return "https://www.instagram.com/"
    if "tiktok" in p:
        return "https://www.tiktok.com/"
    if "facebook.com" in p or (re.search(r"\bfacebook\b", p) and "ads" not in p):
        return "https://www.facebook.com/"
    if "meta.com" in p or re.search(r"^(?:visit|go to|open)\s+meta\b", p):
        return "https://www.meta.com/"
    if re.search(r'google\s+maps|maps\.google', p):
        return "https://www.google.com/maps"

    # Shopping brands (region variants)
    if "amazon" in p:
        if region == "uk":
            return "https://www.amazon.co.uk/"
        if region == "ca":
            return "https://www.amazon.ca/"
        if region == "au":
            return "https://www.amazon.com.au/"
        if region == "in":
            return "https://www.amazon.in/"
        return "https://www.amazon.com/"

    if "ebay" in p:
        return "https://www.ebay.com/"

    if "walmart" in p:
        return "https://www.walmart.com/"

    if re.search(r'best\s+buy|bestbuy', p):
        return "https://www.bestbuy.com/"

    if "apple" in p and _contains_any(p, ("buy", "purchase", "order", "store")):
        return "https://www.apple.com/"

    # Travel brands
    if "booking.com" in p or "booking " in p:
        return "https://www.booking.com/"
    if "airbnb" in p:
        return "https://www.airbnb.com/"
    if "expedia" in p:
        return "https://www.expedia.com/"
    if "skyscanner" in p:
        return "https://www.skyscanner.com/"

    # Job & Research brands
    if "glassdoor" in p:
        return "https://www.glassdoor.com/"
    if "levels.fyi" in p:
        return "https://www.levels.fyi/"

    # AI Assistants
    if "claude.ai" in p or re.search(r"\bclaude\b", p):
        return "https://claude.ai/"
    if "chatgpt" in p or "chat.openai" in p or re.search(r"\bopenai\b", p):
        return "https://chatgpt.com/"
    if "gemini" in p or "bard" in p:
        return "https://gemini.google.com/"
    if "perplexity" in p:
        return "https://www.perplexity.ai/"
    if "grok" in p and "x.com" not in p:
        return "https://grok.com/"
    if "copilot" in p and "github" not in p:
        return "https://copilot.microsoft.com/"

    # SDR/Outbound Tools
    if "apollo.io" in p or re.search(r"\bapollo\b", p):
        return "https://app.apollo.io/"
    if "lemlist" in p:
        return "https://app.lemlist.com/"
    if "smartlead" in p:
        return "https://app.smartlead.ai/"
    if "instantly" in p and "instantly.ai" in p:
        return "https://app.instantly.ai/"
    if "hunter.io" in p or re.search(r"\bhunter\b", p):
        return "https://hunter.io/"
    if "snov" in p:
        return "https://app.snov.io/"
    if "reply.io" in p:
        return "https://app.reply.io/"
    if "outreach.io" in p or re.search(r"\boutreach\b", p):
        return "https://app.outreach.io/"
    if "salesloft" in p:
        return "https://app.salesloft.com/"
    if "zoominfo" in p:
        return "https://app.zoominfo.com/"
    if "lusha" in p:
        return "https://www.lusha.com/"
    if "seamless.ai" in p or "seamless ai" in p:
        return "https://www.seamless.ai/"

    return None


def _detect_intent(prompt_lower: str) -> Tuple[str, float]:
    """
    Return (intent, confidence). Intent is a coarse label.
    """
    p = prompt_lower or ""

    if _contains_any(p, ("flight", "flights", "airfare", "airline", "layover", "hotel", "hotels", "airbnb", "car rental", "rental car", "itinerary")):
        return "travel", 0.85

    if _contains_any(p, ("buy", "purchase", "order", "add to cart", "checkout", "deal", "discount", "coupon", "price", "shipping")):
        return "shopping", 0.8

    if _contains_any(p, ("near me", "directions", "maps", "map", "local", "hours", "phone number", "address")):
        return "local", 0.8

    if _contains_any(p, ("job", "jobs", "apply", "application", "resume", "cv", "career", "hiring", "salary")):
        return "jobs", 0.75

    if _contains_any(p, ("apartment", "rent", "rental", "house", "homes", "zillow", "realtor", "listing", "mortgage")):
        return "real_estate", 0.75

    if _contains_any(p, ("watch", "stream", "netflix", "hulu", "prime video", "disney+", "episode", "season")):
        return "streaming", 0.7

    if _contains_any(p, ("how to", "tutorial", "course", "learn", "lesson", "syllabus")):
        return "learning", 0.65

    if _contains_any(p, ("api", "docs", "documentation", "error", "stack trace", "npm", "pip", "pypi", "github", "stackoverflow")):
        return "dev", 0.7

    if _contains_any(p, ("news", "breaking", "headline", "press release")):
        return "news", 0.6

    if _contains_any(p, ("definition", "meaning", "what is", "wikipedia", "wiki")):
        return "reference", 0.65

    # Default: general web research
    return "search", 0.55


def _default_sources(intent: str, region: str, query: str) -> List[Source]:
    q = quote_plus(query or "")

    # Basic region variants for Google/Bing
    google = "https://www.google.com/search?q=" + q
    if region == "uk":
        google = "https://www.google.co.uk/search?q=" + q
    elif region == "ca":
        google = "https://www.google.ca/search?q=" + q
    elif region == "au":
        google = "https://www.google.com.au/search?q=" + q
    elif region == "in":
        google = "https://www.google.co.in/search?q=" + q

    bing = "https://www.bing.com/search?q=" + q

    sources: List[Source] = []

    if intent == "travel":
        sources = [
            Source("google_flights", "Google Flights", "https://www.google.com/travel/flights", "Broad coverage + fast comparisons"),
            Source("google_hotels", "Google Hotels", "https://www.google.com/travel/hotels", "Broad inventory + filters"),
            Source("skyscanner", "Skyscanner", "https://www.skyscanner.com/", "Alternative metasearch"),
            Source("booking", "Booking.com", "https://www.booking.com/", "Hotels inventory"),
        ]
    elif intent == "shopping":
        amazon = "https://www.amazon.com/s?k=" + q
        if region == "uk":
            amazon = "https://www.amazon.co.uk/s?k=" + q
        elif region == "ca":
            amazon = "https://www.amazon.ca/s?k=" + q
        elif region == "au":
            amazon = "https://www.amazon.com.au/s?k=" + q
        elif region == "in":
            amazon = "https://www.amazon.in/s?k=" + q

        sources = [
            Source("amazon", "Amazon", amazon, "Fast product search"),
            Source("google_shopping", "Google Search", google, "Broad discovery (includes merchants/reviews)"),
            Source("ebay", "eBay", "https://www.ebay.com/sch/i.html?_nkw=" + q, "Marketplace + used items"),
            Source("walmart", "Walmart", "https://www.walmart.com/search?q=" + q, "US retail"),
        ]
    elif intent == "local":
        sources = [
            Source("google_maps", "Google Maps", "https://www.google.com/maps/search/" + q, "Best general local coverage"),
            Source("yelp", "Yelp", "https://www.yelp.com/search?find_desc=" + q, "Reviews-heavy"),
            Source("google_search", "Google Search", google, "Fallback discovery"),
        ]
    elif intent == "jobs":
        sources = [
            Source("linkedin_jobs", "LinkedIn Jobs", "https://www.linkedin.com/jobs/search/?keywords=" + q, "Largest professional graph"),
            Source("indeed", "Indeed", "https://www.indeed.com/jobs?q=" + q, "Broad job inventory"),
            Source("google_search", "Google Search", google, "Fallback discovery"),
        ]
    elif intent == "real_estate":
        sources = [
            Source("zillow", "Zillow", "https://www.zillow.com/homes/" + q + "_rb/", "US residential listings"),
            Source("realtor", "Realtor.com", "https://www.realtor.com/realestateandhomes-search/" + q, "US residential listings"),
            Source("google_search", "Google Search", google, "Fallback discovery"),
        ]
    elif intent == "dev":
        sources = [
            Source("github_search", "GitHub", "https://github.com/search?q=" + q, "Code + issues"),
            Source("stackoverflow", "Stack Overflow", "https://stackoverflow.com/search?q=" + q, "Q&A"),
            Source("documentation", "Google Search", google, "Broad web docs"),
            Source("npm", "NPM", "https://www.npmjs.com/search?q=" + q, "JavaScript packages"),
            Source("pypi", "PyPI", "https://pypi.org/search/?q=" + q, "Python packages"),
        ]
    elif intent == "news":
        sources = [
            Source("google_news", "Google News", "https://news.google.com/search?q=" + q, "Broad news aggregation"),
            Source("reuters", "Reuters", "https://www.reuters.com/search/news?blob=" + q, "Global news"),
            Source("ap_news", "AP News", "https://apnews.com/search?q=" + q, "Reliable wire service"),
        ]
    elif intent == "reference":
        sources = [
            Source("wikipedia", "Wikipedia", "https://en.wikipedia.org/wiki/Special:Search?search=" + q, "Fast reference"),
            Source("britannica", "Britannica", "https://www.britannica.com/search?query=" + q, "Encyclopedic depth"),
            Source("merriam_webster", "Merriam-Webster", "https://www.merriam-webster.com/dictionary/" + q, "Definitions"),
        ]
    elif intent == "learning":
        sources = [
            Source("youtube", "YouTube", "https://www.youtube.com/results?search_query=" + q, "Tutorials/demos"),
            Source("google_search", "Google Search", google, "Broad learning resources"),
        ]
    elif intent == "streaming":
        sources = [
            Source("google_search", "Google Search", google, "Find official streaming availability"),
        ]
    else:
        sources = [
            Source("google_search", "Google Search", google, "Best general discovery"),
            Source("bing_search", "Bing", bing, "Fallback"),
        ]

    return sources


def suggest_sources(prompt: str) -> Dict[str, Any]:
    """
    Return:
    - {status:"ok", intent, confidence, sources:[...], start_url}
    - {status:"needs_clarification", question, options:[...], intent, confidence}
    """
    p = _norm(prompt)
    if not p:
        return {"status": "ok", "intent": "search", "confidence": 0.0, "sources": []}

    region = _detect_region(p)

    # If user included any explicit URL, don't override: let the agent follow the URL.
    if re.search(r"https?://", p):
        return {"status": "ok", "intent": "explicit_url", "confidence": 0.95, "sources": []}

    brand_url = _brand_to_url(p, region)
    if brand_url:
        return {
            "status": "ok",
            "intent": "explicit_site",
            "confidence": 0.95,
            "sources": [Source("explicit", "Requested site", brand_url, "User mentioned this site").__dict__],
            "start_url": brand_url,
        }

    # If the user explicitly asked to navigate somewhere ("go to/open/visit ..."),
    # prefer that destination over intent-based routing (e.g., avoid sending "go to hackernews"
    # to Google News just because it contains "news").
    nav_match = re.search(
        r"^\s*(?:go\s+to|open|visit|navigate(?:\s+to)?)\s+(.+?)(?:\s+(?:and|then)\b|[.;,:!?]|$)",
        p,
    )
    if nav_match:
        target = (nav_match.group(1) or "").strip()
        target = target.strip().strip('\'"').strip()

        # Strip common annotations like "(no login)" / "(not logged in)" etc.
        while True:
            stripped = re.sub(r"\s*\([^)]{0,80}\)\s*$", "", target).strip()
            if stripped == target:
                break
            target = stripped

        target = target.strip("()[]<>")
        target = target.rstrip(".,;:!?)]\"'")

        if target:
            target_url = _brand_to_url(target.lower(), region)
            if not target_url:
                target_lower = target.lower()
                if target_lower.startswith(("http://", "https://")):
                    target_url = target
                elif "." in target:
                    target_url = f"https://{target}"
                elif " " in target:
                    # Multi-word targets are usually ambiguous (e.g. "new york times").
                    # Ask once rather than guessing a likely-wrong domain.
                    q = quote_plus(target)
                    google_search = "https://www.google.com/search?q=" + q
                    if region == "uk":
                        google_search = "https://www.google.co.uk/search?q=" + q
                    elif region == "ca":
                        google_search = "https://www.google.ca/search?q=" + q
                    elif region == "au":
                        google_search = "https://www.google.com.au/search?q=" + q
                    elif region == "in":
                        google_search = "https://www.google.co.in/search?q=" + q

                    opts = [
                        Source("duckduckgo_html", "DuckDuckGo (HTML)", "https://html.duckduckgo.com/html/?q=" + q, "Find the official site (low-JS)").__dict__,
                        Source("bing_search", "Bing", "https://www.bing.com/search?q=" + q, "Find the official site").__dict__,
                        Source("google_search", "Google Search", google_search, "Find the official site").__dict__,
                    ]
                    slug = re.sub(r"[^a-z0-9]+", "", target_lower)
                    if 3 <= len(slug) <= 32:
                        opts.append(
                            Source("guess_com", f"Try {slug}.com", f"https://{slug}.com", "Best-guess domain").__dict__
                        )

                    return {
                        "status": "needs_clarification",
                        "intent": "explicit_site",
                        "confidence": 0.6,
                        "question": f"What’s the exact URL for “{target}”? (Paste it, or pick an option.)",
                        "options": opts,
                        "region": region,
                    }
                else:
                    target_url = f"https://{target}.com"

            return {
                "status": "ok",
                "intent": "explicit_site",
                "confidence": 0.9,
                "sources": [Source("explicit", "Requested site", target_url, "User asked to navigate here").__dict__],
                "start_url": target_url,
                "region": region,
            }

    intent, conf = _detect_intent(p)

    # If prompt is a transactional action without specifying where, ask once.
    if intent in ("shopping", "travel", "real_estate") and conf >= 0.75:
        if intent == "shopping" and not _contains_any(p, ("amazon", "ebay", "walmart", "best buy", "bestbuy")):
            opts = _default_sources("shopping", region, prompt)[:4]
            return {
                "status": "needs_clarification",
                "intent": intent,
                "confidence": conf,
                "question": "Where should I do this shopping task?",
                "options": [o.__dict__ for o in opts],
            }
        if intent == "travel" and not _contains_any(p, ("google flights", "booking", "airbnb", "expedia", "skyscanner")):
            opts = _default_sources("travel", region, prompt)[:4]
            return {
                "status": "needs_clarification",
                "intent": intent,
                "confidence": conf,
                "question": "Which travel source should I use?",
                "options": [o.__dict__ for o in opts],
            }

    sources = _default_sources(intent, region, prompt)
    start_url = sources[0].url if sources else None
    return {
        "status": "ok",
        "intent": intent,
        "confidence": conf,
        "sources": [s.__dict__ for s in sources],
        "start_url": start_url,
        "region": region,
    }
