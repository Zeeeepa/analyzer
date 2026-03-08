#!/usr/bin/env python3
"""
Token Optimizer Integration Example

This file demonstrates how to integrate TokenOptimizer with the browser agent
to reduce token usage and improve performance.
"""

from token_optimizer import TokenOptimizer, create_optimizer
import json


# Example 1: Basic Integration with Browser Agent
async def browser_agent_with_optimizer():
    """
    Example of integrating TokenOptimizer into a browser agent loop.
    """
    # Initialize optimizer
    optimizer = create_optimizer(
        max_elements=100,
        max_text_length=200,
        token_budget=8000
    )

    # Browser agent loop
    task = "Find and click the submit button"
    last_action = None

    while True:
        # Check if we need a fresh snapshot
        if optimizer.should_resnapshot(last_action or 'navigate'):
            # Take new snapshot (expensive operation)
            snapshot = await get_browser_snapshot()  # Your browser snapshot function

            # Cache it
            optimizer.cache_snapshot(snapshot)

            # Compress it
            compressed_snapshot = optimizer.compress_snapshot(snapshot)
        else:
            # Reuse cached snapshot (free!)
            compressed_snapshot = optimizer.get_cached_snapshot()
            if compressed_snapshot:
                compressed_snapshot = optimizer.compress_snapshot(compressed_snapshot)

        # Build minimal context for LLM
        context = optimizer.get_minimal_context(task, compressed_snapshot)

        # Check token budget before sending to LLM
        within_budget, tokens, message = optimizer.check_budget(context)
        if not within_budget:
            print(f"WARNING: {message}")
            # Auto-compression already applied by get_minimal_context

        # Send to LLM
        action = await send_to_llm(context)  # Your LLM call

        # Execute action
        await execute_action(action)
        last_action = action['type']

        # Update stats for monitoring
        raw_tokens = optimizer.estimate_tokens(json.dumps(snapshot))
        compressed_tokens = optimizer.estimate_tokens(context)
        optimizer.update_stats(raw_tokens, compressed_tokens)

        # Check if done
        if action.get('done'):
            break

    # Print stats
    stats = optimizer.get_stats()
    print(f"Token savings: {stats['savings_pct']:.1f}%")
    print(f"Cache hit rate: {stats['cache_hit_rate']:.1f}%")


# Example 2: Playwright Direct Integration
class BrowserAgentWithOptimizer:
    """
    Browser agent with built-in token optimization.
    """

    def __init__(self):
        self.optimizer = TokenOptimizer({
            'max_snapshot_elements': 150,
            'max_text_length': 300,
            'max_tree_depth': 5,
            'cache_ttl_seconds': 30,
            'skip_snapshot_after': ['scroll', 'hover', 'wait', 'mouse_move'],
            'compress_lists': True,
            'remove_hidden': True,
            'token_budget': 10000,
            'auto_compress_threshold': 0.75,
        })
        self.last_action = None

    async def get_page_state(self):
        """
        Get page state with smart caching and compression.
        """
        # Check if we can reuse cached snapshot
        if not self.optimizer.should_resnapshot(self.last_action or 'navigate'):
            cached = self.optimizer.get_cached_snapshot()
            if cached:
                return self.optimizer.compress_snapshot(cached)

        # Take fresh snapshot
        snapshot = await self._take_snapshot()

        # Cache it
        self.optimizer.cache_snapshot(snapshot)

        # Return compressed version
        return self.optimizer.compress_snapshot(snapshot)

    async def execute_with_context(self, task: str):
        """
        Execute task with optimized context.
        """
        # Get optimized page state
        page_state = await self.get_page_state()

        # Build minimal context
        context = self.optimizer.get_minimal_context(task, page_state)

        # Check budget
        within_budget, tokens, message = self.optimizer.check_budget(context)
        print(message)

        # Send to LLM and execute
        action = await self._call_llm(context)
        await self._execute_action(action)

        # Track action for next iteration
        self.last_action = action.get('type')

        return action

    def get_optimization_stats(self):
        """Get token optimization statistics."""
        return self.optimizer.get_stats()

    async def _take_snapshot(self):
        """Placeholder for actual snapshot logic."""
        # Your actual snapshot code here
        pass

    async def _call_llm(self, context):
        """Placeholder for LLM call."""
        # Your actual LLM call here
        pass

    async def _execute_action(self, action):
        """Placeholder for action execution."""
        # Your actual action execution here
        pass


# Example 3: Aggressive Optimization for Large Pages
def handle_large_page(snapshot):
    """
    Handle very large pages with aggressive optimization.
    """
    # Create optimizer with aggressive settings
    optimizer = create_optimizer(
        max_elements=50,          # Very low limit
        max_text_length=100,      # Short text
        token_budget=5000         # Tight budget
    )

    # Compress snapshot
    compressed = optimizer.compress_snapshot(snapshot)

    # Estimate savings
    raw_tokens = optimizer.estimate_tokens(json.dumps(snapshot))
    compressed_tokens = optimizer.estimate_tokens(json.dumps(compressed))
    savings_pct = ((raw_tokens - compressed_tokens) / raw_tokens) * 100

    print(f"Compressed {raw_tokens} -> {compressed_tokens} tokens ({savings_pct:.1f}% savings)")

    return compressed


# Example 4: Monitoring Token Usage
class TokenMonitor:
    """
    Monitor token usage across multiple sessions.
    """

    def __init__(self):
        self.optimizer = TokenOptimizer()
        self.session_stats = []

    def track_snapshot(self, snapshot):
        """Track a snapshot and update stats."""
        # Compress
        compressed = self.optimizer.compress_snapshot(snapshot)

        # Calculate tokens
        raw_tokens = self.optimizer.estimate_tokens(json.dumps(snapshot))
        compressed_tokens = self.optimizer.estimate_tokens(json.dumps(compressed))

        # Update stats
        self.optimizer.update_stats(raw_tokens, compressed_tokens)

        return compressed

    def end_session(self):
        """End session and save stats."""
        stats = self.optimizer.get_stats()
        self.session_stats.append(stats)
        self.optimizer.reset_stats()
        return stats

    def get_aggregate_stats(self):
        """Get aggregate stats across all sessions."""
        if not self.session_stats:
            return {}

        total_raw = sum(s['raw_tokens'] for s in self.session_stats)
        total_compressed = sum(s['compressed_tokens'] for s in self.session_stats)
        total_saved = sum(s['saved_tokens'] for s in self.session_stats)

        return {
            'total_sessions': len(self.session_stats),
            'total_raw_tokens': total_raw,
            'total_compressed_tokens': total_compressed,
            'total_saved_tokens': total_saved,
            'avg_savings_pct': (total_saved / total_raw * 100) if total_raw > 0 else 0,
        }


# Example 5: Adaptive Optimization
class AdaptiveOptimizer:
    """
    Automatically adjust optimization settings based on page complexity.
    """

    def __init__(self):
        self.optimizer = TokenOptimizer()

    def optimize_for_page(self, snapshot):
        """
        Analyze page and adjust optimization settings.
        """
        # Analyze snapshot complexity
        element_count = self._count_elements(snapshot)
        avg_text_length = self._avg_text_length(snapshot)

        # Adjust settings based on complexity
        if element_count > 500:
            # Very large page - aggressive compression
            self.optimizer.config['max_snapshot_elements'] = 50
            self.optimizer.config['max_text_length'] = 100
        elif element_count > 200:
            # Large page - moderate compression
            self.optimizer.config['max_snapshot_elements'] = 100
            self.optimizer.config['max_text_length'] = 150
        else:
            # Small page - light compression
            self.optimizer.config['max_snapshot_elements'] = 200
            self.optimizer.config['max_text_length'] = 300

        # Compress with adaptive settings
        return self.optimizer.compress_snapshot(snapshot)

    def _count_elements(self, snapshot):
        """Count total elements in snapshot."""
        if isinstance(snapshot, dict) and 'elements' in snapshot:
            return len(snapshot['elements'])
        elif isinstance(snapshot, list):
            return len(snapshot)
        return 0

    def _avg_text_length(self, snapshot):
        """Calculate average text length."""
        # Simplified calculation
        return 100


if __name__ == '__main__':
    print("Token Optimizer Integration Examples")
    print("=" * 50)
    print("\nSee source code for usage examples:")
    print("1. browser_agent_with_optimizer() - Basic integration")
    print("2. BrowserAgentWithOptimizer - Class-based integration")
    print("3. handle_large_page() - Aggressive optimization")
    print("4. TokenMonitor - Token usage monitoring")
    print("5. AdaptiveOptimizer - Adaptive optimization based on page complexity")
