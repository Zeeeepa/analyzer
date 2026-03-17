#!/usr/bin/env python3
"""
Token/Overhead Optimizer for Browser Agent

Reduces token usage by:
1. Snapshot throttling - skip snapshots after non-DOM-changing actions
2. Snapshot caching - return cached snapshot if page hasn't changed
3. Snapshot compression - remove non-interactive elements, truncate text, limit depth
4. Token estimation and budget tracking

Usage:
    optimizer = TokenOptimizer()

    # Check if snapshot needed
    if optimizer.should_resnapshot('scroll'):
        snapshot = await browser.get_snapshot()
    else:
        snapshot = optimizer.get_cached_snapshot()

    # Compress snapshot
    compressed = optimizer.compress_snapshot(snapshot)

    # Get minimal context for LLM
    context = optimizer.get_minimal_context(task, snapshot)
"""

import hashlib
import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field


DEFAULT_CONFIG = {
    'max_snapshot_elements': 100,
    'max_text_length': 200,
    'max_tree_depth': 5,
    'cache_ttl_seconds': 30,
    'skip_snapshot_after': ['scroll', 'hover', 'wait'],
    'compress_lists': True,
    'remove_hidden': True,
    'estimate_tokens_enabled': True,
    'token_budget': 8000,  # Max tokens for context
    'auto_compress_threshold': 0.8,  # Auto-compress if context exceeds 80% of budget
}


@dataclass
class SnapshotCache:
    """Cached snapshot data."""
    snapshot: Dict[str, Any]
    hash_value: str
    timestamp: float
    compressed: Optional[Dict[str, Any]] = None


@dataclass
class TokenStats:
    """Token usage statistics."""
    raw_tokens: int = 0
    compressed_tokens: int = 0
    saved_tokens: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    auto_compressions: int = 0


class TokenOptimizer:
    """
    Optimizes token usage for browser agent by reducing snapshot overhead.

    Features:
    - Snapshot throttling: Skip snapshots after actions that don't change DOM
    - Snapshot caching: Return cached snapshot if page hasn't changed
    - Snapshot compression: Remove noise, truncate text, limit depth
    - Token estimation: Estimate tokens before sending to LLM
    - Budget tracking: Warn if context exceeds budget, auto-compress if needed
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize optimizer with config."""
        self.config = {**DEFAULT_CONFIG, **(config or {})}

        # Snapshot cache
        self.snapshot_cache: Optional[SnapshotCache] = None
        self.last_snapshot_hash: Optional[str] = None

        # Token stats
        self.stats = TokenStats()

        # Compression state
        self._compression_enabled = True

    def should_resnapshot(self, action_type: str) -> bool:
        """
        Check if we should take a new snapshot after the given action.

        Args:
            action_type: Type of action just performed (e.g., 'scroll', 'click', 'type')

        Returns:
            True if snapshot needed, False to use cached snapshot
        """
        # Always snapshot if no cache
        if self.snapshot_cache is None:
            return True

        # Check if cache is stale
        cache_age = time.time() - self.snapshot_cache.timestamp
        if cache_age > self.config['cache_ttl_seconds']:
            return True

        # Skip snapshot for non-DOM-changing actions
        skip_actions = self.config['skip_snapshot_after']
        if action_type.lower() in skip_actions:
            self.stats.cache_hits += 1
            return False

        # All other actions need fresh snapshot
        self.stats.cache_misses += 1
        return True

    def cache_snapshot(self, snapshot: Dict[str, Any]) -> str:
        """
        Cache a snapshot and return its hash.

        Args:
            snapshot: Raw snapshot data

        Returns:
            Hash of the snapshot
        """
        # Compute hash
        snapshot_str = json.dumps(snapshot, sort_keys=True)
        hash_value = hashlib.md5(snapshot_str.encode()).hexdigest()

        # Update cache
        self.snapshot_cache = SnapshotCache(
            snapshot=snapshot,
            hash_value=hash_value,
            timestamp=time.time()
        )
        self.last_snapshot_hash = hash_value

        return hash_value

    def get_cached_snapshot(self) -> Optional[Dict[str, Any]]:
        """Get cached snapshot if available and valid."""
        if self.snapshot_cache is None:
            return None

        # Check TTL
        cache_age = time.time() - self.snapshot_cache.timestamp
        if cache_age > self.config['cache_ttl_seconds']:
            return None

        return self.snapshot_cache.snapshot

    def compress_snapshot(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compress snapshot to reduce token usage.

        Compression strategies:
        1. Remove non-interactive elements (static text, divs without actions)
        2. Truncate long text content
        3. Limit tree depth
        4. Remove hidden elements
        5. Collapse repetitive structures (e.g., 100 list items -> "100 items: [sample]")

        Args:
            snapshot: Raw snapshot data

        Returns:
            Compressed snapshot
        """
        if not self._compression_enabled:
            return snapshot

        compressed = {}

        # Handle different snapshot formats
        if isinstance(snapshot, dict):
            if 'elements' in snapshot:
                # Element-based snapshot
                compressed['elements'] = self._compress_elements(
                    snapshot['elements'],
                    depth=0
                )
            else:
                # Generic dict snapshot
                for key, value in snapshot.items():
                    compressed[key] = self._compress_value(value, depth=0)
        elif isinstance(snapshot, list):
            compressed = self._compress_elements(snapshot, depth=0)
        else:
            compressed = snapshot

        return compressed

    def _compress_elements(self, elements: List[Any], depth: int) -> List[Any]:
        """Compress list of elements."""
        max_depth = self.config['max_tree_depth']
        max_elements = self.config['max_snapshot_elements']
        compress_lists = self.config['compress_lists']

        # Limit depth
        if depth >= max_depth:
            return [{'_truncated': f'Max depth {max_depth} reached'}]

        # Collapse long lists
        if compress_lists and len(elements) > max_elements:
            # Keep first few items + summary
            sample = elements[:3]
            compressed_sample = [self._compress_element(el, depth) for el in sample]
            return [
                *compressed_sample,
                {
                    '_collapsed': f'{len(elements) - 3} more items (total: {len(elements)})',
                    '_sample': compressed_sample[0] if compressed_sample else {}
                }
            ]

        # Compress each element
        return [self._compress_element(el, depth) for el in elements[:max_elements]]

    def _compress_element(self, element: Any, depth: int) -> Any:
        """Compress a single element."""
        if not isinstance(element, dict):
            return self._compress_value(element, depth)

        compressed = {}

        for key, value in element.items():
            # Remove hidden elements
            if self.config['remove_hidden']:
                if key == 'visible' and value is False:
                    return {'_hidden': True}
                if key == 'display' and value == 'none':
                    return {'_hidden': True}

            # Compress text
            if key in ('text', 'label', 'placeholder', 'value', 'title'):
                compressed[key] = self._truncate_text(str(value))
            # Recurse into nested structures
            elif isinstance(value, (dict, list)):
                compressed[key] = self._compress_value(value, depth + 1)
            # Keep other fields as-is
            else:
                compressed[key] = value

        return compressed

    def _compress_value(self, value: Any, depth: int) -> Any:
        """Compress arbitrary value."""
        if isinstance(value, dict):
            return self._compress_element(value, depth)
        elif isinstance(value, list):
            return self._compress_elements(value, depth)
        elif isinstance(value, str):
            return self._truncate_text(value)
        else:
            return value

    def _truncate_text(self, text: str) -> str:
        """Truncate long text."""
        max_length = self.config['max_text_length']
        if len(text) <= max_length:
            return text
        return text[:max_length] + '...'

    def get_minimal_context(self, task: str, snapshot: Dict[str, Any]) -> str:
        """
        Build minimal context string for LLM.

        Args:
            task: User task/goal
            snapshot: Snapshot data (raw or compressed)

        Returns:
            Minimal context string
        """
        # Compress snapshot if needed
        compressed = self.compress_snapshot(snapshot)

        # Format context
        context_parts = [
            f"Task: {task}",
            "",
            "Page State:",
            json.dumps(compressed, indent=2)
        ]

        context = "\n".join(context_parts)

        # Check token budget
        estimated_tokens = self.estimate_tokens(context)
        budget = self.config['token_budget']
        threshold = self.config['auto_compress_threshold']

        if estimated_tokens > budget * threshold:
            # Auto-compress if over threshold
            self.stats.auto_compressions += 1
            context = self._aggressive_compress(context)

        return context

    def _aggressive_compress(self, context: str) -> str:
        """Apply aggressive compression to context."""
        # Remove extra whitespace
        context = re.sub(r'\n\s*\n', '\n', context)
        context = re.sub(r' {2,}', ' ', context)

        # Truncate long lines
        lines = context.split('\n')
        compressed_lines = []
        for line in lines:
            if len(line) > 300:
                compressed_lines.append(line[:300] + '...')
            else:
                compressed_lines.append(line)

        return '\n'.join(compressed_lines)

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.

        Uses simple heuristic: ~4 characters per token
        (actual varies by tokenizer, but this is close enough for budgeting)

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        if not self.config['estimate_tokens_enabled']:
            return 0

        # Simple heuristic: ~4 chars per token
        # More accurate: count words + punctuation
        words = len(text.split())
        chars = len(text)

        # Weighted average: favor word count but account for long words
        estimated = int((words * 1.3) + (chars / 4.5))

        return estimated

    def check_budget(self, context: str) -> Tuple[bool, int, str]:
        """
        Check if context fits within token budget.

        Args:
            context: Context string to check

        Returns:
            Tuple of (within_budget, estimated_tokens, message)
        """
        estimated = self.estimate_tokens(context)
        budget = self.config['token_budget']

        within_budget = estimated <= budget
        usage_pct = (estimated / budget) * 100

        if within_budget:
            message = f"Token usage: {estimated}/{budget} ({usage_pct:.1f}%)"
        else:
            message = f"WARNING: Token budget exceeded! {estimated}/{budget} ({usage_pct:.1f}%)"

        return within_budget, estimated, message

    def get_stats(self) -> Dict[str, Any]:
        """Get token usage statistics."""
        return {
            'raw_tokens': self.stats.raw_tokens,
            'compressed_tokens': self.stats.compressed_tokens,
            'saved_tokens': self.stats.saved_tokens,
            'savings_pct': (
                (self.stats.saved_tokens / self.stats.raw_tokens * 100)
                if self.stats.raw_tokens > 0 else 0
            ),
            'cache_hits': self.stats.cache_hits,
            'cache_misses': self.stats.cache_misses,
            'cache_hit_rate': (
                (self.stats.cache_hits / (self.stats.cache_hits + self.stats.cache_misses) * 100)
                if (self.stats.cache_hits + self.stats.cache_misses) > 0 else 0
            ),
            'auto_compressions': self.stats.auto_compressions,
        }

    def reset_stats(self):
        """Reset statistics."""
        self.stats = TokenStats()

    def update_stats(self, raw_tokens: int, compressed_tokens: int):
        """Update token statistics."""
        self.stats.raw_tokens += raw_tokens
        self.stats.compressed_tokens += compressed_tokens
        self.stats.saved_tokens += (raw_tokens - compressed_tokens)

    def set_compression_enabled(self, enabled: bool):
        """Enable/disable compression."""
        self._compression_enabled = enabled

    def clear_cache(self):
        """Clear snapshot cache."""
        self.snapshot_cache = None
        self.last_snapshot_hash = None


# Convenience functions for common usage patterns

def create_optimizer(
    max_elements: int = 100,
    max_text_length: int = 200,
    token_budget: int = 8000
) -> TokenOptimizer:
    """
    Create a TokenOptimizer with custom settings.

    Args:
        max_elements: Max elements in compressed snapshot
        max_text_length: Max length for text fields
        token_budget: Max tokens for context

    Returns:
        TokenOptimizer instance
    """
    config = {
        'max_snapshot_elements': max_elements,
        'max_text_length': max_text_length,
        'token_budget': token_budget,
    }
    return TokenOptimizer(config)


def optimize_snapshot(snapshot: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    One-shot snapshot compression.

    Args:
        snapshot: Raw snapshot data
        config: Optional config override

    Returns:
        Compressed snapshot
    """
    optimizer = TokenOptimizer(config)
    return optimizer.compress_snapshot(snapshot)


def estimate_snapshot_tokens(snapshot: Dict[str, Any]) -> int:
    """
    Estimate tokens for a snapshot.

    Args:
        snapshot: Snapshot data

    Returns:
        Estimated token count
    """
    optimizer = TokenOptimizer()
    snapshot_str = json.dumps(snapshot)
    return optimizer.estimate_tokens(snapshot_str)


# Example usage
if __name__ == '__main__':
    # Create optimizer
    optimizer = TokenOptimizer()

    # Example snapshot
    example_snapshot = {
        'elements': [
            {
                'ref': 'button-1',
                'type': 'button',
                'text': 'Click me' * 50,  # Long text
                'visible': True,
                'x': 100,
                'y': 200,
            },
            {
                'ref': 'div-1',
                'type': 'div',
                'text': 'Some static text',
                'visible': False,  # Hidden
            },
            *[
                {
                    'ref': f'list-item-{i}',
                    'type': 'li',
                    'text': f'Item {i}',
                }
                for i in range(200)  # Long list
            ]
        ]
    }

    # Compress snapshot
    compressed = optimizer.compress_snapshot(example_snapshot)

    # Estimate tokens
    raw_tokens = optimizer.estimate_tokens(json.dumps(example_snapshot))
    compressed_tokens = optimizer.estimate_tokens(json.dumps(compressed))

    print(f"Raw tokens: {raw_tokens}")
    print(f"Compressed tokens: {compressed_tokens}")
    print(f"Saved: {raw_tokens - compressed_tokens} tokens ({(raw_tokens - compressed_tokens) / raw_tokens * 100:.1f}%)")
    print(f"\nCompressed snapshot:")
    print(json.dumps(compressed, indent=2))

    # Check budget
    context = optimizer.get_minimal_context("Click the submit button", example_snapshot)
    within_budget, tokens, message = optimizer.check_budget(context)
    print(f"\n{message}")

    # Stats
    print(f"\nStats:")
    print(json.dumps(optimizer.get_stats(), indent=2))
