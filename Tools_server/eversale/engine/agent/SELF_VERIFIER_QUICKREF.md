# Self Verifier Quick Reference

## 30-Second Start

```python
from agent.self_verifier import SelfVerifier

# Minimal setup (just consistency checks)
verifier = SelfVerifier()

# Verify output
result = await verifier.verify(
    answer="I found 15 Python books. Added 3 to cart.",
    task="Find Python books"
)

if result.passed:
    print(f"✓ Verified ({result.confidence:.0%})")
else:
    print(f"✗ Issues: {result.issues}")
```

## Common Patterns

### 1. Standalone Verification
```python
verifier = SelfVerifier(config={
    'enabled_checks': ['consistency']  # No external deps
})

result = await verifier.verify(answer, task)
```

### 2. With LLM Second Opinion
```python
from agent.llm_client import LLMClient

verifier = SelfVerifier(
    llm_client=LLMClient(),
    config={'enabled_checks': ['consistency', 'second_opinion']}
)
```

### 3. With Web Search
```python
async def web_search(query):
    # Your search implementation
    return results

verifier = SelfVerifier(
    search_fn=web_search,
    config={'enabled_checks': ['consistency', 'web_fact']}
)
```

### 4. With Visual Verification
```python
async def analyze_screenshot(screenshot, question):
    # Your vision model
    return description

result = await verifier.verify(
    answer=answer,
    task=task,
    screenshot=screenshot_data  # Pass screenshot for visual checks
)
```

### 5. EventBus Integration
```python
from agent.organism_core import EventBus, OrganismEvent, EventType

event_bus = EventBus()

# Auto-subscribes to ACTION_COMPLETE
verifier = SelfVerifier(event_bus=event_bus)

# Emit event (verification happens automatically)
event = OrganismEvent(
    event_type=EventType.ACTION_COMPLETE,
    source="action_engine",
    data={'task': task, 'result': answer}
)
await event_bus.publish(event)  # Note: use publish(), not emit()
```

## Configuration Options

```python
config = {
    # Confidence threshold (0.0-1.0)
    'min_verification_confidence': 0.6,

    # Enabled strategies
    'enabled_checks': [
        'consistency',      # Fast, no deps (ALWAYS recommended)
        'second_opinion',   # Requires llm_client
        'web_fact',        # Requires search_fn
        'visual'           # Requires vision_fn + screenshot
    ]
}
```

## Verification Result

```python
result = await verifier.verify(answer, task)

# Access results
result.passed           # True/False
result.confidence       # 0.0-1.0
result.issues          # List[str] of problems
result.checks          # List[CheckResult] individual checks
result.duration_ms     # How long it took
result.summary()       # Human-readable report
```

## Check Results

Each check returns:

```python
check = result.checks[0]

check.check_type       # "consistency", "web_fact", etc.
check.passed          # True/False
check.confidence      # 0.0-1.0
check.details         # Description
check.issues          # List[str] of issues
```

## Claim Types

Claims extracted from output:

- **fact**: "X is Y", "located in Z"
- **statistic**: "20%", "$100", "15 items"
- **action_result**: "Successfully completed X", "Found N items"
- **reasoning**: Logical chains

## Verification Strategies

| Strategy | Speed | Requires | Catches |
|----------|-------|----------|---------|
| **consistency** | <1ms | None | Contradictions, incomplete thoughts |
| **second_opinion** | 500-2000ms | LLM | Reasoning errors, misunderstandings |
| **web_fact** | 300-1000ms | search_fn | Factual errors, false claims |
| **visual** | 1000-3000ms | vision_fn | UI state mismatches |

## Confidence Weights

```
Overall =
  20% consistency +
  40% second_opinion +
  30% web_fact +
  10% visual
```

## Common Use Cases

### 1. Verify Before Returning to User
```python
async def execute_task(task):
    result = await perform_action(task)

    verification = await verifier.verify(result, task)

    if verification.passed:
        return result
    else:
        # Retry, ask human, or return with warning
        return f"{result}\n\n⚠️ Low confidence: {verification.issues}"
```

### 2. Quality Gate in Pipeline
```python
async def action_pipeline(task):
    # Execute
    result = await action_engine.execute(task)

    # Verify
    verification = await verifier.verify(result, task)

    # Gate
    if verification.confidence < 0.7:
        logger.warning(f"Low confidence: {verification.summary()}")
        # Trigger review, alert, or retry

    return result
```

### 3. Automatic Monitoring
```python
# Set up EventBus integration
event_bus = EventBus()
verifier = SelfVerifier(event_bus=event_bus)

# All action completions are automatically verified
# Check stats periodically
stats = verifier.get_verification_stats()
if stats['pass_rate'] < 0.8:
    alert("Verification pass rate dropped to {stats['pass_rate']:.0%}")
```

### 4. Custom Domain Checks
```python
# Create custom checker
class CustomChecker:
    async def check_domain_rules(self, answer, task):
        # Your domain-specific validation
        return CheckResult(...)

# Use with standard verifier
standard_result = await verifier.verify(answer, task)
custom_result = await custom_checker.check_domain_rules(answer, task)

# Combine results
all_checks = standard_result.checks + [custom_result]
```

## Statistics

```python
stats = verifier.get_verification_stats()

stats['total_verifications']  # Total runs
stats['pass_rate']           # Success rate (0.0-1.0)
stats['avg_confidence']      # Average confidence
stats['common_issues']       # Top issues with counts
```

## Error Handling

The verifier **never fails** - it gracefully degrades:

```python
# If search unavailable → optimistic pass (confidence 0.5)
# If LLM fails → skip second opinion
# If vision fails → skip visual check
# If exception → log warning, return safe default
```

## Performance Tips

1. **Enable only needed checks** - Faster verification
2. **Cache search results** - Avoid redundant lookups (automatic)
3. **Use consistency always** - Free validation (<1ms)
4. **Batch verifications** - Process multiple in parallel
5. **Monitor duration** - Tune timeouts for your use case

## Testing

```python
# Run test suite
python3 test_self_verifier.py

# Run integration examples
PYTHONPATH=/mnt/c/ev29 python3 agent/self_verifier_example.py
```

## Common Issues

### "EventBus has no attribute 'emit'"
Use `event_bus.publish(event)` not `event_bus.emit(event)`

### "No claims extracted"
Normal for short outputs. Consistency check still runs.

### "Low confidence but passed"
Threshold is 0.6 by default. Adjust with `min_verification_confidence`

### "Web search returning no results"
Implement `search_fn` or disable `web_fact` checks

## Integration Checklist

- [ ] Import SelfVerifier
- [ ] Choose verification strategies
- [ ] Configure LLM/search/vision if needed
- [ ] Call `verify()` after actions
- [ ] Check `result.passed` and `result.confidence`
- [ ] Handle low confidence appropriately
- [ ] Monitor verification stats

## Next Steps

1. **Basic**: Use standalone with consistency checks
2. **Intermediate**: Add LLM second opinion
3. **Advanced**: Full integration with EventBus
4. **Production**: Monitor stats, tune thresholds

## See Also

- **SELF_VERIFIER_GUIDE.md** - Full documentation
- **self_verifier_example.py** - Integration examples
- **test_self_verifier.py** - Test suite

