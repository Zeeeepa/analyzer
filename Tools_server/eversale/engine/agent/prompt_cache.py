import hashlib
import json
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class CachedAction:
    action: Dict[str, Any]
    success_count: int
    fail_count: int
    last_used: datetime
    site_domain: str


class PromptCache:
    """
    Page-state aware prompt cache.
    Hash URL + interactive elements -> cached action sequence.
    Skip LLM call entirely on cache hit.
    """

    def __init__(self, ttl_hours: int = 168):  # 1 week default
        self.cache: Dict[str, CachedAction] = {}
        self.ttl = timedelta(hours=ttl_hours)
        self.stats = {'hits': 0, 'misses': 0, 'skipped_llm_calls': 0}

    def get_page_hash(self, url: str, elements: list, goal: str) -> str:
        """
        Generate deterministic hash from page state + goal.
        Uses URL domain + sorted element signatures + goal keywords.
        """
        from urllib.parse import urlparse
        domain = urlparse(url).netloc

        # Extract element signatures (tag + text + type)
        element_sigs = sorted([
            f"{e.get('tag', '')}:{e.get('text', '')[:20]}:{e.get('type', '')}"
            for e in elements if e.get('is_interactive')
        ])

        # Extract goal keywords (normalize)
        goal_normalized = ' '.join(sorted(goal.lower().split()))

        # Combine for hash
        hash_input = f"{domain}|{json.dumps(element_sigs)}|{goal_normalized}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:32]

    async def get_cached_action(self, page_hash: str) -> Optional[Dict[str, Any]]:
        """
        Look up cached action for page state.
        Returns None if no cache hit or cache expired.
        Only returns cached action if success rate > 70%.
        """
        if page_hash not in self.cache:
            self.stats['misses'] += 1
            return None

        cached = self.cache[page_hash]

        # Check TTL
        if datetime.now() - cached.last_used > self.ttl:
            del self.cache[page_hash]
            self.stats['misses'] += 1
            return None

        # Check success rate (must be > 70%)
        total = cached.success_count + cached.fail_count
        if total > 3 and cached.success_count / total < 0.7:
            self.stats['misses'] += 1
            return None

        self.stats['hits'] += 1
        self.stats['skipped_llm_calls'] += 1
        cached.last_used = datetime.now()
        return cached.action

    def cache_action(self, page_hash: str, action: Dict[str, Any], domain: str):
        """Cache successful action for future use."""
        if page_hash in self.cache:
            self.cache[page_hash].success_count += 1
            self.cache[page_hash].last_used = datetime.now()
        else:
            self.cache[page_hash] = CachedAction(
                action=action,
                success_count=1,
                fail_count=0,
                last_used=datetime.now(),
                site_domain=domain
            )

    def record_failure(self, page_hash: str):
        """Record action failure to update success rate."""
        if page_hash in self.cache:
            self.cache[page_hash].fail_count += 1

    def get_stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        total = self.stats['hits'] + self.stats['misses']
        hit_rate = self.stats['hits'] / total if total > 0 else 0
        return {
            **self.stats,
            'hit_rate': f"{hit_rate:.1%}",
            'cached_patterns': len(self.cache),
            'estimated_cost_savings': f"${self.stats['skipped_llm_calls'] * 0.01:.2f}"
        }
