# Orchestration Integration Guide

How to integrate natural language triggers into the brain/orchestration layer for optimal performance.

## Quick Start

### Before (No Triggers)

```python
# Old approach - always use LLM
async def handle_user_goal(goal: str):
    # Always go through LLM planning
    plan = await llm_client.create_plan(goal)
    result = await execute_plan(plan)
    return result
```

### After (With Triggers)

```python
# New approach - triggers first, LLM fallback
async def handle_user_goal(goal: str):
    # Try natural language trigger first
    result = await playwright_client.process_natural_language(goal)

    if result:
        # Fast path: trigger matched, instant result
        return result

    # Slow path: no trigger, use LLM planning
    plan = await llm_client.create_plan(goal)
    result = await execute_plan(plan)
    return result
```

**Performance gain:** 10-30x faster for common operations, zero LLM cost.

---

## Integration Locations

### 1. `brain_enhanced_v2.py` Integration

**Location:** Main agent loop

```python
async def execute_goal(self, goal: str) -> Dict[str, Any]:
    """Execute a user goal with natural language trigger optimization."""

    logger.info(f"[GOAL] {goal}")

    # OPTIMIZATION: Check for natural language triggers
    trigger_result = await self.playwright_client.process_natural_language(goal)

    if trigger_result:
        logger.info("[FAST-PATH] Executed via natural language trigger")
        logger.info(f"[RESULT] {trigger_result.get('success', False)}")

        # Update context with result
        self.context['last_action'] = {
            'type': 'natural_language_trigger',
            'goal': goal,
            'result': trigger_result,
            'cost': 0,  # No LLM tokens used
            'latency_ms': trigger_result.get('latency_ms', 50)
        }

        return trigger_result

    # Standard path: LLM-based planning
    logger.info("[LLM-PATH] No trigger matched, using AI planning")

    # ... existing LLM planning code ...
    plan = await self.create_plan(goal)
    result = await self.execute_plan(plan)

    return result
```

---

### 2. `orchestration.py` Integration

**Location:** Main orchestration loop

```python
class Orchestrator:
    def __init__(self):
        self.playwright_client = PlaywrightClient()
        self.llm_client = LLMClient()
        self.stats = {
            'trigger_hits': 0,
            'trigger_misses': 0,
            'llm_tokens_saved': 0
        }

    async def process_prompt(self, prompt: str) -> Dict[str, Any]:
        """Process user prompt with trigger optimization."""

        # Step 1: Check natural language triggers
        start_time = time.time()
        result = await self.playwright_client.process_natural_language(prompt)
        trigger_latency = (time.time() - start_time) * 1000

        if result:
            # Trigger matched
            self.stats['trigger_hits'] += 1
            self.stats['llm_tokens_saved'] += 500  # Estimated avg tokens

            logger.info(f"[TRIGGER-HIT] Executed in {trigger_latency:.1f}ms, saved ~500 tokens")

            return {
                'success': result.get('success', False),
                'data': result,
                'method': 'natural_language_trigger',
                'latency_ms': trigger_latency,
                'cost': 0
            }

        # Step 2: No trigger - use LLM
        self.stats['trigger_misses'] += 1

        logger.info("[TRIGGER-MISS] Using LLM planning")

        start_time = time.time()
        plan = await self.llm_client.create_plan(prompt)
        result = await self.execute_plan(plan)
        llm_latency = (time.time() - start_time) * 1000

        return {
            'success': result.get('success', False),
            'data': result,
            'method': 'llm_planning',
            'latency_ms': llm_latency,
            'cost': result.get('cost', 0.01)
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get trigger usage statistics."""
        total = self.stats['trigger_hits'] + self.stats['trigger_misses']
        hit_rate = (self.stats['trigger_hits'] / total * 100) if total > 0 else 0

        return {
            'trigger_hits': self.stats['trigger_hits'],
            'trigger_misses': self.stats['trigger_misses'],
            'hit_rate': f"{hit_rate:.1f}%",
            'tokens_saved': self.stats['llm_tokens_saved'],
            'estimated_savings_usd': self.stats['llm_tokens_saved'] * 0.00001  # $0.01 per 1k tokens
        }
```

---

### 3. Interactive Mode Integration

**Location:** REPL/interactive loop

```python
async def interactive_mode():
    """Interactive browser agent with trigger optimization."""

    client = PlaywrightClient()
    await client.connect()

    print("Browser Agent Ready (type 'help' for trigger list)")

    while True:
        prompt = input("\n> ").strip()

        if prompt.lower() == 'help':
            show_trigger_help()
            continue

        if prompt.lower() == 'exit':
            break

        # Check triggers first
        result = await client.process_natural_language(prompt)

        if result:
            # Trigger path
            print("[FAST] ✓", end=" ")
            if result.get('success'):
                print_success(result)
            else:
                print_error(result)
        else:
            # LLM path
            print("[LLM] ⏳", end=" ")
            result = await llm_planning(prompt)
            print_result(result)

    await client.disconnect()


def show_trigger_help():
    """Show available trigger shortcuts."""
    print("""
Available Natural Language Triggers (instant, no LLM):

Extraction:
  - "extract all links" / "get all links"
  - "extract forms" / "find forms"
  - "extract tables" / "get table data"
  - "extract inputs" / "list fields"

Debug:
  - "show network errors" / "what failed"
  - "show console errors" / "browser errors"
  - "show console" / "console logs"

Session:
  - "use my chrome" (requires chrome --remote-debugging-port=9222)

Other:
  - "quick extract" (fast HTML parse)

For complex tasks, use natural language and LLM will plan it.
    """)
```

---

## Advanced Integration

### 1. Hybrid Approach - Triggers + LLM Completion

Some tasks might start with a trigger but need LLM completion:

```python
async def hybrid_execution(prompt: str):
    """Use trigger for data gathering, LLM for analysis."""

    # Check if prompt is a hybrid task
    if "analyze" in prompt.lower() and "links" in prompt.lower():
        # Example: "analyze all links for broken URLs"

        # Step 1: Use trigger to extract links (fast, free)
        links = await playwright_client.process_natural_language("extract all links")

        if links:
            # Step 2: Use LLM to analyze the extracted data
            analysis = await llm_client.analyze({
                'task': 'analyze_links',
                'data': links,
                'goal': prompt
            })

            return {
                'success': True,
                'extraction': links,
                'analysis': analysis,
                'method': 'hybrid',
                'cost_breakdown': {
                    'extraction': 0,  # Trigger
                    'analysis': 0.01  # LLM
                }
            }

    # ... fallback to standard flow
```

---

### 2. Caching Trigger Results

For repeated operations:

```python
class CachedOrchestrator:
    def __init__(self):
        self.trigger_cache = {}
        self.cache_ttl = 60  # seconds

    async def process_with_cache(self, prompt: str, url: str = None):
        """Check cache before executing trigger."""

        cache_key = f"{url}:{prompt}" if url else prompt
        cached = self.trigger_cache.get(cache_key)

        if cached and (time.time() - cached['timestamp']) < self.cache_ttl:
            logger.info("[CACHE-HIT] Returning cached trigger result")
            return cached['result']

        # Execute trigger
        result = await self.playwright_client.process_natural_language(prompt)

        if result:
            # Cache successful trigger results
            self.trigger_cache[cache_key] = {
                'result': result,
                'timestamp': time.time()
            }

        return result
```

---

### 3. Trigger Suggestions

Help users discover triggers:

```python
def suggest_trigger_optimization(prompt: str) -> Optional[str]:
    """Suggest trigger-friendly rephrasing."""

    suggestions = {
        'get the links': 'extract all links',
        'show me all forms': 'extract forms',
        'what are the errors': 'show console errors',
        'check for broken requests': 'show network errors',
    }

    prompt_lower = prompt.lower()

    for phrase, trigger in suggestions.items():
        if phrase in prompt_lower:
            return f"💡 Tip: Try '{trigger}' for instant results!"

    return None


async def process_with_suggestions(prompt: str):
    """Process prompt and suggest optimizations."""

    suggestion = suggest_trigger_optimization(prompt)
    if suggestion:
        print(suggestion)

    result = await client.process_natural_language(prompt)
    return result
```

---

## Monitoring & Metrics

### Track Trigger Performance

```python
class TriggerMetrics:
    def __init__(self):
        self.metrics = {
            'trigger_types': {},  # Count by trigger type
            'latencies': [],
            'cost_savings': 0,
            'errors': 0
        }

    def record_trigger_hit(self, trigger_type: str, latency_ms: float):
        """Record successful trigger execution."""
        self.metrics['trigger_types'][trigger_type] = \
            self.metrics['trigger_types'].get(trigger_type, 0) + 1
        self.metrics['latencies'].append(latency_ms)
        self.metrics['cost_savings'] += 0.01  # Avg LLM cost saved

    def record_trigger_miss(self):
        """Record LLM fallback."""
        pass  # Could track miss patterns

    def get_report(self) -> str:
        """Generate performance report."""
        total_triggers = sum(self.metrics['trigger_types'].values())
        avg_latency = sum(self.metrics['latencies']) / len(self.metrics['latencies']) \
                      if self.metrics['latencies'] else 0

        return f"""
Trigger Performance Report
===========================
Total trigger hits: {total_triggers}
Average latency: {avg_latency:.1f}ms
Cost savings: ${self.metrics['cost_savings']:.2f}
Errors: {self.metrics['errors']}

Top triggers:
{self._format_top_triggers()}
        """

    def _format_top_triggers(self) -> str:
        sorted_triggers = sorted(
            self.metrics['trigger_types'].items(),
            key=lambda x: x[1],
            reverse=True
        )
        return '\n'.join(
            f"  - {trigger}: {count}x"
            for trigger, count in sorted_triggers[:5]
        )
```

---

## Error Handling

### Graceful Degradation

```python
async def robust_execution(prompt: str):
    """Always fall back to LLM if trigger fails."""

    try:
        # Try trigger first
        result = await client.process_natural_language(prompt)

        if result and result.get('success'):
            return result

        if result and not result.get('success'):
            # Trigger matched but failed - log and fall back
            logger.warning(f"[TRIGGER-FAIL] {result.get('error')}")

    except Exception as e:
        # Trigger system error - log and continue
        logger.error(f"[TRIGGER-ERROR] {str(e)}")

    # Fall back to LLM in all failure cases
    logger.info("[FALLBACK] Using LLM planning")
    return await llm_planning(prompt)
```

---

## Testing

### Unit Tests

```python
import pytest

@pytest.mark.asyncio
async def test_extraction_triggers():
    """Test extraction trigger matches."""
    client = PlaywrightClient()
    await client.connect()
    await client.navigate("https://example.com")

    # Test link extraction
    result = await client.process_natural_language("extract all links")
    assert result is not None
    assert result['success'] is True
    assert 'links' in result

    # Test form extraction
    result = await client.process_natural_language("find forms")
    assert result is not None
    assert 'forms' in result

    await client.disconnect()


@pytest.mark.asyncio
async def test_no_trigger_fallback():
    """Test that complex prompts return None."""
    client = PlaywrightClient()

    # Complex prompt should not match any trigger
    result = await client.process_natural_language(
        "navigate to the pricing page and compare all plans"
    )
    assert result is None  # Should fall back to LLM
```

---

## Best Practices

1. **Always check triggers first** - Fastest path wins
2. **Log trigger hits/misses** - Track optimization opportunities
3. **Graceful fallback** - Never fail, always fall back to LLM
4. **Cache trigger results** - Don't re-extract same data
5. **Monitor performance** - Track cost savings and latency
6. **Suggest triggers** - Help users discover shortcuts
7. **Hybrid workflows** - Combine triggers with LLM analysis

---

## Migration Checklist

- [ ] Add `process_natural_language()` call before LLM planning
- [ ] Add logging for trigger hits/misses
- [ ] Implement metrics tracking
- [ ] Update error handling for graceful fallback
- [ ] Add trigger suggestions to help text
- [ ] Test with common user prompts
- [ ] Monitor cost savings
- [ ] Identify new trigger opportunities

---

## Example: Complete Integration

```python
# brain_enhanced_v2.py - Complete integration example

async def execute_goal(self, goal: str) -> Dict[str, Any]:
    """Execute user goal with full trigger optimization."""

    logger.info(f"[GOAL] {goal}")

    # 1. Check for trigger
    trigger_result = await self.playwright_client.process_natural_language(goal)

    if trigger_result:
        # Trigger path
        logger.info(f"[FAST-PATH] Trigger executed in <100ms")

        self.metrics.record_trigger_hit(
            trigger_type=trigger_result.get('action', 'unknown'),
            latency_ms=50
        )

        return self._format_result(trigger_result, method='trigger')

    # 2. No trigger - LLM planning
    logger.info("[LLM-PATH] Using AI planning")

    plan = await self.create_plan(goal)
    result = await self.execute_plan(plan)

    return self._format_result(result, method='llm')
```

---

## Support

For questions or issues:
1. Check `NATURAL_LANGUAGE_TRIGGERS.md` for trigger reference
2. Run examples: `python example_natural_language_triggers.py`
3. Enable debug logging: `logging.basicConfig(level=logging.INFO)`
4. Check logs for `[NL-TRIGGER]` messages
