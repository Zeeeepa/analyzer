# Valence System - Quick Start Guide

## 5-Minute Integration

### 1. Initialize (One Line)

```python
from agent.organism_core import get_organism
from agent.valence_system import create_valence_system

organism = get_organism()
valence = create_valence_system(organism.event_bus)
```

That's it. The valence system is now:
- ✓ Subscribed to all events
- ✓ Updating emotional state automatically
- ✓ Decaying with heartbeat
- ✓ Ready to query

### 2. Query Emotional State

```python
# Get current feeling (-1 to +1)
feeling = valence.get_valence()  # e.g., -0.42

# Get mood (human-readable)
mood = valence.get_mood()  # "stressed", "neutral", "thriving", etc.

# Get motivation (how to behave)
motivation = valence.get_motivation()
# Returns: {
#   "strategy": "cautious",
#   "speed_multiplier": 0.7,
#   "risk_tolerance": 0.3,
#   "verification_level": 1,
#   "message": "Feeling stressed - slowing down and double-checking"
# }
```

### 3. Adjust Behavior

```python
# Check if should pause
should_pause, reason = valence.should_pause()
if should_pause:
    logger.warning(f"Pausing: {reason}")
    return

# Adjust speed based on emotion
motivation = valence.get_motivation()
if motivation["speed_multiplier"] < 1.0:
    await asyncio.sleep(1.0)  # Slow down when stressed
```

### 4. Add to LLM Prompts

```python
# Include emotional context in prompts
prompt = f"""
{user_task}

{valence.get_emotional_context()}
"""

# LLM now knows the agent's emotional state and can adjust reasoning
```

## Common Patterns

### Pattern 1: Risk-Adjusted Decision Making

```python
def can_take_risky_action(valence_system) -> bool:
    motivation = valence_system.get_motivation()
    return motivation["risk_tolerance"] > 0.7

if can_take_risky_action(valence):
    execute_high_risk_action()
else:
    logger.info("Too cautious for this action - skipping")
```

### Pattern 2: Verification Level

```python
def should_verify(valence_system, action_type: str) -> bool:
    motivation = valence_system.get_motivation()

    # Always verify high-risk actions
    if action_type == "payment":
        return True

    # Otherwise use emotional state
    return motivation["verification_level"] >= 1

if should_verify(valence, "form_submit"):
    verify_before_submit()
```

### Pattern 3: Emotional Monitoring

```python
# Log emotional state periodically
profile = valence.get_emotional_profile()

logger.info(
    f"Emotional state: {profile.mood} "
    f"(valence: {profile.current_valence:+.2f}, "
    f"trend: {profile.trend})"
)
```

### Pattern 4: Manual Feeling Injection

```python
# User gives positive feedback
valence.inject_feeling(+0.3, reason="user_praised_results")

# User reports error
valence.inject_feeling(-0.2, reason="user_reported_bug")
```

## Visualization

### Terminal Output

```python
# Simple bar chart (one line)
print(valence.plot_simple())
# Output: "    ◀==========|          ▶    -0.42 (stressed)"

# Full history chart
print(valence.plot_history(width=60, height=10))
# Output: Multi-line ASCII chart showing valence over time
```

### Status Report

```python
from agent.valence_system import get_emotional_summary

print(get_emotional_summary(valence))
# Output:
# EMOTIONAL STATE SUMMARY
# ==================================================
# Valence:      -0.42 (stressed)
# Trend:        declining (recent avg: -0.30)
# Volatility:   0.15
# Time in mood: 45s
# Strategy:     cautious
#
#     ◀==========|          ▶    -0.42 (stressed)
#
# Motivation: Feeling stressed - slowing down and double-checking
```

## Event Triggers

The valence system automatically responds to these events:

| Event | Delta | Notes |
|-------|-------|-------|
| `ACTION_COMPLETE` | +0.05 | Success |
| `ACTION_FAILED` | -0.15 | Failure |
| `customer_happy` | +0.3 | Mission-aligned |
| `customer_frustrated` | -0.25 | Mission failure |
| `GAP_DETECTED` | -0.05 | Surprise |
| `HEALTH_CRITICAL` | -0.3 | System issues |
| `RECOVERY_TRIGGERED` | +0.15 | Relief |

See `valence_system.py::EVENT_VALENCE_DELTAS` for complete list.

## Integration Checklist

- [ ] Import `create_valence_system`
- [ ] Initialize with event bus
- [ ] Query before risky actions
- [ ] Include emotional context in LLM prompts
- [ ] Adjust speed based on motivation
- [ ] Log emotional state periodically
- [ ] Handle pause recommendations
- [ ] (Optional) Inject manual feelings for user feedback

## Debugging

### Check if Working

```python
# Trigger a test event
from agent.organism_core import OrganismEvent, EventType

await organism.event_bus.publish(OrganismEvent(
    event_type=EventType.ACTION_FAILED,
    source="test",
    data={"message": "test failure"}
))

# Check valence changed
print(f"Valence after failure: {valence.get_valence()}")
# Should be negative
```

### View History

```python
# Get recent history
summary = valence.get_history_summary(window_minutes=10)
print(f"Events in last 10 min: {summary['count']}")
print(f"Avg valence: {summary['avg_valence']:+.2f}")
print(f"Range: {summary['min_valence']:+.2f} to {summary['max_valence']:+.2f}")
```

### Save/Load State

```python
# Save current state
valence.save()

# State saved to: memory/valence_state.json
# Automatically loaded on next initialization
```

## Best Practices

1. **Query before risky actions** - Check `should_pause()` and `risk_tolerance`
2. **Include in prompts** - LLM performs better with emotional context
3. **Don't override constantly** - Let valence decay naturally
4. **Log emotional state** - Helps debug behavior changes
5. **Use motivation system** - Don't hardcode behavior, use valence-driven adjustments
6. **Monitor trends** - Sustained negative valence indicates systemic issues
7. **Respect pause recommendations** - If valence says pause, something is wrong

## Examples

Run the interactive demo:

```bash
python agent/valence_example.py
```

Run tests:

```bash
pytest agent/test_valence_system.py -v
```

## Full Documentation

See `VALENCE_SYSTEM.md` for complete documentation.

## Questions?

**Q: When should I check valence?**
A: Before any risky action, when building LLM prompts, or when deciding strategy.

**Q: How often does valence update?**
A: On every event emission, plus decay every heartbeat (default 1 second).

**Q: Can I manually set valence?**
A: Use `inject_feeling()`, not direct assignment. Or let events drive it.

**Q: What if valence gets stuck negative?**
A: Either fix the underlying issues causing failures, or trigger recovery events.

**Q: Does valence persist across restarts?**
A: Yes, saved to `memory/valence_state.json` automatically.

**Q: How do I integrate with existing brain?**
A: See `valence_brain_integration.py` for examples.
