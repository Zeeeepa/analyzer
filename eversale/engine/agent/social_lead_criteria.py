"""
Social lead criteria parsing and matching utilities (CLI engine).

Used by Reddit/LinkedIn lead finders to keep behavior prompt-driven:
- Extract ICP text / keywords from natural language
- Parse relative date windows (e.g., "last 14 days", "7-14 days", "past 2 weeks")
- Provide simple text matching + scoring helpers
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple


_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "for", "from",
    "how", "i", "if", "in", "into", "is", "it", "its", "just", "me", "my", "of",
    "on", "or", "our", "please", "should", "that", "the", "their", "then", "they",
    "this", "to", "us", "we", "what", "when", "where", "who", "with", "you", "your",
    # Only truly generic words - keep ICP-relevant terms like agency, founder, etc.
    "help", "need", "looking", "find", "get", "want", "would", "could",
}

# Words that are meaningful for ICP matching - never filter these
_ICP_KEYWORDS = {
    "agency", "agencies", "founder", "founders", "ceo", "owner", "owners",
    "saas", "ecommerce", "b2b", "b2c", "startup", "startups", "entrepreneur",
    "marketing", "sales", "growth", "revenue", "mrr", "arr", "client", "clients",
    "business", "company", "companies", "customer", "customers", "leads", "lead",
}


@dataclass(frozen=True)
class RelativeDateWindow:
    """
    A window expressed as days-ago.
    Include items with timestamps in: [now-max_days_ago, now-min_days_ago]
    """

    min_days_ago: int = 7
    max_days_ago: int = 14

    def to_after_before_utc(self, now_utc: Optional[int] = None) -> Tuple[int, int]:
        now = int(now_utc or time.time())
        after_utc = now - int(self.max_days_ago) * 86400
        before_utc = now - int(self.min_days_ago) * 86400
        return after_utc, before_utc


def extract_icp_text(prompt: str) -> Optional[str]:
    """
    Extract an ICP description from a prompt.

    Supports common patterns:
    - "ICP: ...", "icp is ...", "ideal customer profile: ..."
    """
    if not prompt:
        return None

    m = re.search(r"\b(?:icp|ideal customer profile)\s*[:\-]\s*(.+)$", prompt, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()

    m = re.search(r"\bicp\s+is\s+(.+)$", prompt, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()

    return None


def parse_relative_date_window(
    prompt: str,
    default_min_days: int = 7,
    default_max_days: int = 14,
) -> RelativeDateWindow:
    """
    Parse a relative date window from prompt text.

    Examples:
    - "last 14 days" -> min=0, max=14
    - "past 2 weeks" -> min=0, max=14
    - "7-14 days" / "between 7 and 14 days" -> min=7, max=14
    """
    if not prompt:
        return RelativeDateWindow(default_min_days, default_max_days)

    p = prompt.lower()

    # Absolute ISO date: "since 2025-01-15", "after 2025-01-15"
    m = re.search(r"\b(?:since|after|from)\s+(\d{4}-\d{2}-\d{2})\b", p)
    if m:
        try:
            dt = datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
            after_utc = int(dt.timestamp())
            now = int(time.time())
            max_days = max(0, int((now - after_utc) / 86400))
            return RelativeDateWindow(min_days_ago=0, max_days_ago=max_days)
        except Exception:
            pass

    # "last N hours" / "past N hrs"
    m = re.search(r"\b(?:last|past)\s+(\d{1,3})\s*(h|hr|hrs|hour|hours)\b", p)
    if m:
        n = int(m.group(1))
        # Convert to days; keep min=0 for "last/past"
        return RelativeDateWindow(min_days_ago=0, max_days_ago=max(1, int((n + 23) / 24)))

    # Explicit range: "7-14 days", "7 to 14 days", "between 7 and 14 days"
    m = re.search(r"\b(?:between\s+)?(\d{1,3})\s*(?:-|to|and)\s*(\d{1,3})\s*(?:day|days)\b", p)
    if m:
        a = int(m.group(1))
        b = int(m.group(2))
        return RelativeDateWindow(min_days_ago=min(a, b), max_days_ago=max(a, b))

    # "last N days/weeks/months"
    m = re.search(r"\b(?:last|past)\s+(\d{1,3})\s*(day|days|d|week|weeks|w|month|months|mo)\b", p)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        if unit.startswith("week") or unit == "w":
            n *= 7
        elif unit.startswith("month") or unit == "mo":
            n *= 30
        return RelativeDateWindow(min_days_ago=0, max_days_ago=n)

    # Common shortcuts
    if "fortnight" in p:
        return RelativeDateWindow(0, 14)
    if "this week" in p:
        return RelativeDateWindow(0, 7)
    if "this month" in p:
        return RelativeDateWindow(0, 30)
    if "past week" in p or "last week" in p:
        return RelativeDateWindow(0, 7)
    if "past 2 weeks" in p or "last 2 weeks" in p or "past two weeks" in p or "last two weeks" in p:
        return RelativeDateWindow(0, 14)
    if "past month" in p or "last month" in p:
        return RelativeDateWindow(0, 30)
    if "last year" in p or "past year" in p:
        return RelativeDateWindow(0, 365)

    return RelativeDateWindow(default_min_days, default_max_days)


def has_explicit_date_window(prompt: str) -> bool:
    """
    True if the prompt explicitly specifies a time window.
    Used to decide when to use stricter date filtering (e.g. PullPush after/before).
    """
    if not prompt:
        return False

    p = prompt.lower()

    if any(k in p for k in ("today", "yesterday", "last week", "past week", "last month", "past month")):
        return True

    if any(k in p for k in ("fortnight", "this week", "this month", "last year", "past year")):
        return True

    if re.search(r"\b(?:since|after|from)\s+\d{4}-\d{2}-\d{2}\b", p):
        return True

    # Any explicit numeric window
    if re.search(r"\b(?:last|past)\s+\d{1,3}\s*(?:h|hr|hrs|hour|hours|day|days|d|week|weeks|w|month|months|mo)\b", p):
        return True

    # Explicit range
    if re.search(r"\b(?:between\s+)?\d{1,3}\s*(?:-|to|and)\s*\d{1,3}\s*(?:day|days)\b", p):
        return True

    return False


def extract_keywords(text: str, max_keywords: int = 12) -> List[str]:
    """
    Extract a compact keyword list from free-form text.

    - Preserves quoted phrases as keywords
    - Removes stopwords/punctuation
    - Keeps unique tokens (>=3 chars) and top phrases
    """
    if not text:
        return []

    keywords: List[str] = []

    # Quoted phrases first
    for m in re.finditer(r"['\"]([^'\"]{2,80})['\"]", text):
        phrase = m.group(1).strip()
        if phrase and phrase.lower() not in (k.lower() for k in keywords):
            keywords.append(phrase)

    # Tokenize remaining text
    cleaned = re.sub(r"['\"`]", " ", text)
    tokens = re.findall(r"[a-zA-Z0-9][a-zA-Z0-9\-\+]{2,}", cleaned.lower())

    freq = {}
    for t in tokens:
        # Never filter out ICP-relevant keywords
        if t in _STOPWORDS and t not in _ICP_KEYWORDS:
            continue
        if t.isdigit():
            continue
        freq[t] = freq.get(t, 0) + 1

    # Prioritize ICP keywords first, then by frequency
    icp_tokens = [(t, c) for t, c in freq.items() if t in _ICP_KEYWORDS]
    other_tokens = [(t, c) for t, c in freq.items() if t not in _ICP_KEYWORDS]

    # Add ICP keywords first (sorted by frequency)
    for token, _count in sorted(icp_tokens, key=lambda kv: (-kv[1], kv[0])):
        if len(keywords) >= max_keywords:
            break
        if token.lower() not in (k.lower() for k in keywords):
            keywords.append(token)

    # Then add other tokens
    for token, _count in sorted(other_tokens, key=lambda kv: (-kv[1], kv[0])):
        if len(keywords) >= max_keywords:
            break
        if token.lower() not in (k.lower() for k in keywords):
            keywords.append(token)

    return keywords[:max_keywords]


def count_keyword_matches(text: str, keywords: Iterable[str]) -> Tuple[int, List[str]]:
    """
    Count keyword matches with basic word-boundary semantics.
    Returns (count, matched_keywords).
    """
    if not text:
        return 0, []

    hay = text.lower()
    matched: List[str] = []
    count = 0

    for kw in keywords:
        kw_norm = (kw or "").strip().lower()
        if not kw_norm:
            continue

        # Phrase match (contains) for multi-word / special chars
        if " " in kw_norm or "-" in kw_norm or "+" in kw_norm:
            if kw_norm in hay:
                matched.append(kw)
                count += 1
            continue

        # Word-boundary match for single tokens
        if re.search(rf"\b{re.escape(kw_norm)}\b", hay):
            matched.append(kw)
            count += 1

    # De-dupe (preserve order)
    seen = set()
    unique = []
    for k in matched:
        kl = k.lower()
        if kl not in seen:
            seen.add(kl)
            unique.append(k)

    return count, unique
