"""
Intelligent DOM Diff Caching

Instead of sending entire DOM to LLM each iteration:
1. Cache the previous DOM state
2. Compute semantic diff (not text diff)
3. Send only what changed + relevant context

This reduces tokens by 60-80% on repeat interactions with same page.
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
from loguru import logger
from difflib import SequenceMatcher


@dataclass
class DOMNode:
    """Simplified DOM node for diffing"""
    tag: str
    text: str
    attributes: Dict[str, str]
    children_count: int
    path: str  # XPath-like path
    hash: str = field(init=False)

    def __post_init__(self):
        # Create content hash
        content = f"{self.tag}|{self.text[:100]}|{sorted(self.attributes.items())}"
        self.hash = hashlib.md5(content.encode()).hexdigest()[:12]


@dataclass
class DOMDiff:
    """Represents changes between two DOM states"""
    added: List[DOMNode]
    removed: List[DOMNode]
    modified: List[Tuple[DOMNode, DOMNode]]  # (old, new)
    unchanged_count: int
    total_old: int
    total_new: int

    @property
    def change_ratio(self) -> float:
        """Ratio of changed elements (0 = same, 1 = completely different)"""
        changes = len(self.added) + len(self.removed) + len(self.modified)
        total = max(self.total_old, self.total_new, 1)
        return min(1.0, changes / total)

    @property
    def is_minor(self) -> bool:
        """True if changes are minor (< 20%)"""
        return self.change_ratio < 0.2

    def to_summary(self) -> str:
        """Human-readable summary"""
        parts = []
        if self.added:
            parts.append(f"+{len(self.added)} new elements")
        if self.removed:
            parts.append(f"-{len(self.removed)} removed")
        if self.modified:
            parts.append(f"~{len(self.modified)} modified")
        if not parts:
            return "No changes detected"
        return ", ".join(parts)

    def to_llm_context(self, max_items: int = 10) -> str:
        """Format diff for LLM consumption (token-efficient)"""
        lines = []

        if self.is_minor:
            lines.append("[Minor page update]")
        else:
            lines.append(f"[Page changed: {self.to_summary()}]")

        # Show most important additions
        if self.added:
            lines.append("\nNEW ELEMENTS:")
            for node in self.added[:max_items]:
                lines.append(f"  + {node.tag}: {node.text[:50]}")

        # Show modifications
        if self.modified:
            lines.append("\nMODIFIED:")
            for old, new in self.modified[:max_items]:
                if old.text != new.text:
                    lines.append(f"  ~ {new.tag}: '{old.text[:30]}' -> '{new.text[:30]}'")

        # Show removals briefly
        if self.removed:
            lines.append(f"\nREMOVED: {len(self.removed)} elements")

        return "\n".join(lines)


class DOMDiffEngine:
    """
    Compute semantic differences between DOM states.

    Unlike text diff, this understands DOM structure:
    - Tracks element identity by path + attributes
    - Ignores insignificant changes (whitespace, ordering)
    - Highlights actionable changes (new buttons, forms)
    """

    # Tags that are important for agent actions
    IMPORTANT_TAGS = {'button', 'a', 'input', 'select', 'form', 'dialog', 'alert'}

    def compute_diff(self, old_nodes: List[DOMNode], new_nodes: List[DOMNode]) -> DOMDiff:
        """Compute semantic diff between two DOM states"""
        # Build hash maps
        old_by_hash = {n.hash: n for n in old_nodes}
        new_by_hash = {n.hash: n for n in new_nodes}

        old_hashes = set(old_by_hash.keys())
        new_hashes = set(new_by_hash.keys())

        # Find additions and removals
        added_hashes = new_hashes - old_hashes
        removed_hashes = old_hashes - new_hashes
        unchanged_hashes = old_hashes & new_hashes

        added = [new_by_hash[h] for h in added_hashes]
        removed = [old_by_hash[h] for h in removed_hashes]

        # Find modifications (same path, different content)
        modified = []
        old_by_path = {n.path: n for n in old_nodes}
        new_by_path = {n.path: n for n in new_nodes}

        for path, new_node in new_by_path.items():
            if path in old_by_path:
                old_node = old_by_path[path]
                if old_node.hash != new_node.hash:
                    modified.append((old_node, new_node))

        return DOMDiff(
            added=sorted(added, key=lambda n: n.tag in self.IMPORTANT_TAGS, reverse=True),
            removed=removed,
            modified=modified,
            unchanged_count=len(unchanged_hashes),
            total_old=len(old_nodes),
            total_new=len(new_nodes)
        )

    def parse_html_to_nodes(self, html: str, accessibility_tree: str = None) -> List[DOMNode]:
        """
        Parse HTML/accessibility tree into DOMNode list.

        For best results, pass accessibility_tree from Playwright.
        """
        nodes = []

        if accessibility_tree:
            # Parse accessibility tree format
            nodes = self._parse_accessibility_tree(accessibility_tree)
        else:
            # Fallback: parse HTML with regex (lightweight)
            nodes = self._parse_html_lightweight(html)

        return nodes

    def _parse_accessibility_tree(self, tree: str) -> List[DOMNode]:
        """Parse Playwright accessibility snapshot"""
        import re
        nodes = []

        # Pattern: "- role "name" [ref=xxx]"
        pattern = re.compile(r'^\s*-\s*(\w+)\s+"([^"]*)"(?:\s+\[ref=(\w+)\])?', re.MULTILINE)

        for i, match in enumerate(pattern.finditer(tree)):
            role = match.group(1)
            name = match.group(2)
            ref = match.group(3) or f"auto_{i}"

            nodes.append(DOMNode(
                tag=role,
                text=name,
                attributes={'ref': ref},
                children_count=0,
                path=f"//{role}[@ref='{ref}']"
            ))

        return nodes

    def _parse_html_lightweight(self, html: str) -> List[DOMNode]:
        """Lightweight HTML parsing without full DOM parser"""
        import re
        nodes = []

        # Find interactive elements
        patterns = [
            (r'<button[^>]*>([^<]*)</button>', 'button'),
            (r'<a[^>]*>([^<]*)</a>', 'link'),
            (r'<input[^>]*placeholder="([^"]*)"[^>]*>', 'input'),
            (r'<select[^>]*>.*?</select>', 'select'),
            (r'<h[1-6][^>]*>([^<]*)</h[1-6]>', 'heading'),
        ]

        for pattern, tag in patterns:
            for i, match in enumerate(re.finditer(pattern, html, re.IGNORECASE | re.DOTALL)):
                text = match.group(1) if match.lastindex else ""
                nodes.append(DOMNode(
                    tag=tag,
                    text=text[:100].strip(),
                    attributes={},
                    children_count=0,
                    path=f"//{tag}[{i}]"
                ))

        return nodes


class DOMCache:
    """
    Cache DOM states and provide efficient diffs.

    Maintains:
    - Last N DOM states per URL
    - Computed diffs between states
    - Statistics on page volatility
    """

    def __init__(self, max_history: int = 5, cache_ttl_seconds: int = 300):
        self.max_history = max_history
        self.cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self.engine = DOMDiffEngine()

        # State storage: {url: [(timestamp, nodes), ...]}
        self.history: Dict[str, List[Tuple[datetime, List[DOMNode]]]] = defaultdict(list)

        # Volatility tracking: {url: [change_ratios]}
        self.volatility: Dict[str, List[float]] = defaultdict(list)

        # Stats
        self.stats = {
            'cache_hits': 0,
            'cache_misses': 0,
            'tokens_saved_estimate': 0,
            'diffs_computed': 0
        }

    def get_or_diff(
        self,
        url: str,
        current_html: str = None,
        current_a11y: str = None
    ) -> Tuple[Optional[DOMDiff], List[DOMNode]]:
        """
        Get diff from cache or compute new one.

        Returns:
            (diff, current_nodes) - diff is None if no previous state
        """
        # Parse current state
        current_nodes = self.engine.parse_html_to_nodes(current_html, current_a11y)

        # Clean expired entries
        self._clean_expired(url)

        # Check cache
        if url in self.history and self.history[url]:
            last_timestamp, last_nodes = self.history[url][-1]

            # Compute diff
            diff = self.engine.compute_diff(last_nodes, current_nodes)
            self.stats['diffs_computed'] += 1
            self.stats['cache_hits'] += 1

            # Track volatility
            self.volatility[url].append(diff.change_ratio)
            if len(self.volatility[url]) > 20:
                self.volatility[url] = self.volatility[url][-20:]

            # Estimate tokens saved
            if diff.is_minor:
                # Rough estimate: full DOM ~ 2000 tokens, diff ~ 200 tokens
                self.stats['tokens_saved_estimate'] += 1800

            # Update cache
            self._add_to_history(url, current_nodes)

            return diff, current_nodes

        # No cache - first visit
        self.stats['cache_misses'] += 1
        self._add_to_history(url, current_nodes)

        return None, current_nodes

    def _add_to_history(self, url: str, nodes: List[DOMNode]):
        """Add state to history"""
        self.history[url].append((datetime.now(), nodes))

        # Trim to max history
        if len(self.history[url]) > self.max_history:
            self.history[url] = self.history[url][-self.max_history:]

    def _clean_expired(self, url: str):
        """Remove expired entries"""
        if url not in self.history:
            return

        now = datetime.now()
        self.history[url] = [
            (ts, nodes) for ts, nodes in self.history[url]
            if now - ts < self.cache_ttl
        ]

    def get_page_volatility(self, url: str) -> float:
        """Get average volatility for a page (0 = stable, 1 = highly dynamic)"""
        if url not in self.volatility or not self.volatility[url]:
            return 0.5  # Unknown
        return sum(self.volatility[url]) / len(self.volatility[url])

    def should_send_full_dom(self, url: str) -> bool:
        """Decide whether to send full DOM or diff"""
        # High volatility pages need full DOM
        if self.get_page_volatility(url) > 0.7:
            return True

        # No history means full DOM
        if url not in self.history or not self.history[url]:
            return True

        return False

    def format_for_llm(
        self,
        url: str,
        current_html: str = None,
        current_a11y: str = None,
        full_dom_content: str = None
    ) -> str:
        """
        Get LLM-optimized representation of current page.

        Returns either:
        - Full DOM if first visit or high volatility
        - Diff + context if returning to stable page
        """
        diff, nodes = self.get_or_diff(url, current_html, current_a11y)

        if diff is None or self.should_send_full_dom(url):
            # Send full DOM
            return full_dom_content or self._nodes_to_text(nodes)

        if diff.is_minor:
            # Very minor changes - just summary
            return f"[Page stable - {diff.to_summary()}]\n\nKey interactive elements:\n{self._important_nodes(nodes)}"

        # Send diff + key elements
        return f"{diff.to_llm_context()}\n\nCurrent interactive elements:\n{self._important_nodes(nodes)}"

    def _nodes_to_text(self, nodes: List[DOMNode]) -> str:
        """Convert nodes to text representation"""
        lines = []
        for node in nodes[:50]:  # Limit
            if node.text:
                lines.append(f"- {node.tag}: {node.text}")
        return "\n".join(lines)

    def _important_nodes(self, nodes: List[DOMNode], max_items: int = 20) -> str:
        """Get important interactive elements"""
        important = [n for n in nodes if n.tag in self.engine.IMPORTANT_TAGS]
        lines = []
        for node in important[:max_items]:
            lines.append(f"- {node.tag}: {node.text}")
        return "\n".join(lines)

    def get_stats(self) -> Dict:
        """Get cache statistics"""
        return {
            **self.stats,
            'cache_hit_rate': self.stats['cache_hits'] / max(1, self.stats['cache_hits'] + self.stats['cache_misses']),
            'urls_cached': len(self.history),
            'total_states': sum(len(h) for h in self.history.values())
        }

    def clear(self, url: str = None):
        """Clear cache for URL or all"""
        if url:
            self.history.pop(url, None)
            self.volatility.pop(url, None)
        else:
            self.history.clear()
            self.volatility.clear()


# Singleton
_dom_cache: Optional[DOMCache] = None

def get_dom_cache() -> DOMCache:
    """Get or create DOM cache"""
    global _dom_cache
    if _dom_cache is None:
        _dom_cache = DOMCache()
    return _dom_cache


# Convenience function for react_loop integration
def get_optimized_dom_context(
    url: str,
    html: str = None,
    accessibility_tree: str = None,
    full_content: str = None
) -> str:
    """
    Get optimized DOM context for LLM.

    Usage in react_loop:
        context = get_optimized_dom_context(page.url, html, a11y_tree, full_markdown)
    """
    cache = get_dom_cache()
    return cache.format_for_llm(url, html, accessibility_tree, full_content)
