# Valence System - The Emotional Gradient

## Overview

The **Valence System** gives the Eversale AGI organism **feelings** on a pain-to-pleasure gradient. This is distinct from:
- **Gap Detection** (binary surprise signal)
- **Mission Alignment** (identity/values check)

Valence is the agent's **subjective emotional experience** - how good or bad things feel right now.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     VALENCE SYSTEM                          │
│                                                             │
│  Pain ◀────────────────────────────────────────▶ Pleasure  │
│  -1.0           Neutral (0.0)               +1.0           │
│                                                             │
│  ┌───────────────────────────────────────────────────┐    │
│  │ Event Bus (All Events) → Valence Updates         │    │
│  │ - task_success: +0.1                              │    │
│  │ - task_failure: -0.2                              │    │
│  │ - customer_happy: +0.3 (mission-aligned)          │    │
│  │ - customer_frustrated: -0.25                      │    │
│  │ - resource_critical: -0.4                         │    │
│  │ - gap_detected: -0.05 (surprise)                  │    │
│  │ - error_recovered: +0.15 (relief)                 │    │
│  └───────────────────────────────────────────────────┘    │
│                                                             │
│  ┌───────────────────────────────────────────────────┐    │
│  │ Heartbeat → Decay (toward neutral)                │    │
│  │ - Valence *= 0.99 per beat                        │    │
│  │ - Emotional homeostasis                           │    │
│  └───────────────────────────────────────────────────┘    │
│                                                             │
│  ┌───────────────────────────────────────────────────┐    │
│  │ Motivation System                                 │    │
│  │ - Pain → cautious, slow, verify                   │    │
│  │ - Pleasure → confident, fast, bold                │    │
│  └───────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## Valence Range

| Range | Mood | Strategy | Behavior |
|-------|------|----------|----------|
| -1.0 to -0.6 | **Devastated/Struggling** | Defensive | Pause, assess, ask for help |
| -0.6 to -0.3 | **Stressed** | Cautious | Slow down, double-check, conservative |
| -0.3 to -0.1 | **Uneasy** | Careful | Slightly more verification |
| -0.1 to +0.1 | **Neutral** | Normal | Standard operation |
| +0.1 to +0.3 | **Content** | Confident | Efficient, smooth |
| +0.3 to +0.6 | **Thriving** | Bold | Take on challenges |
| +0.6 to +1.0 | **Euphoric** | Bold | High confidence, reinforce strategies |

## Event Valence Deltas

Events affect valence by different amounts based on their significance:

### High Impact (Mission-Aligned)
- **Customer success**: +0.3
- **Customer frustration**: -0.25
- **Emergency**: -0.5
- **Emergency resolved**: +0.3

### Moderate Impact
- **Task success**: +0.1
- **Task failure**: -0.2
- **Repeated failures**: -0.3 (compounding)
- **Health critical**: -0.3
- **Resource critical**: -0.4
- **Recovery triggered**: +0.15

### Low Impact
- **Action complete**: +0.05
- **Action failed**: -0.15
- **Gap detected**: -0.05
- **Prediction correct**: +0.05
- **Lesson learned**: +0.08

## Features

### 1. Emotional Decay
Valence naturally decays toward neutral (0.0) over time:
```python
valence *= 0.99  # per heartbeat (default 1 second)
```
This represents **emotional homeostasis** - feelings fade if not reinforced.

### 2. Streak Effects
Repeated failures compound:
- 1st failure: -0.15
- 2nd failure: -0.25
- 3rd+ failure: -0.35 (increasing pain)

Repeated successes create momentum:
- 5+ successes: +0.05 bonus per success

### 3. Pause Logic
Extreme negative valence triggers automatic pause:
```python
if valence < -0.7 and sustained > 10s:
    pause_for(60s)  # Emergency stop to assess
```

### 4. Motivation System
Valence influences decision-making:

| Valence | Strategy | Speed | Risk | Verification |
|---------|----------|-------|------|--------------|
| -0.8 | Defensive | 0.5x | 0.0 | Thorough |
| -0.4 | Cautious | 0.7x | 0.3 | Basic |
| 0.0 | Normal | 1.0x | 0.6 | None |
| +0.4 | Confident | 1.1x | 0.7 | None |
| +0.8 | Bold | 1.3x | 0.9 | None |

### 5. Emotional Context for LLM
The valence system provides emotional context that can be included in LLM prompts:

```python
emotional_context = valence.get_emotional_context()
# Returns:
# """
# EMOTIONAL STATE:
# - Mood: thriving (valence: +0.52)
# - Trend: improving (recent avg: +0.40)
# - Strategy: confident
# - Motivation: Feeling good - confident and efficient
# """
```

This allows the LLM to reason with awareness of the agent's emotional state.

## Usage

### Basic Integration

```python
from agent.organism_core import EventBus, init_organism, start_organism
from agent.valence_system import create_valence_system

# 1. Create event bus
event_bus = EventBus()

# 2. Initialize organism
organism = init_organism(llm_client=llm)

# 3. Create valence system (auto-subscribes to all events)
valence = create_valence_system(event_bus)

# 4. Start organism (starts heartbeat → triggers decay)
await start_organism()

# 5. Query valence at any time
current_feeling = valence.get_valence()  # -1.0 to +1.0
mood = valence.get_mood()  # "thriving", "neutral", "stressed", etc.
motivation = valence.get_motivation()  # Strategy adjustments

# 6. Include in LLM prompts
prompt = f"{user_task}\n\n{valence.get_emotional_context()}"
```

### Check if Should Pause

```python
should_pause, reason = valence.should_pause()
if should_pause:
    logger.warning(f"Pausing due to emotional distress: {reason}")
    await take_break()
```

### Adjust Behavior Based on Valence

```python
motivation = valence.get_motivation()

# Use motivation to adjust agent behavior
if motivation["strategy"] == "defensive":
    # Slow down, verify everything
    verify_level = 2
    speed = 0.5
elif motivation["strategy"] == "confident":
    # Be efficient, trust predictions
    verify_level = 0
    speed = 1.1
```

### Visualize Emotional State

```python
# Simple bar chart
print(valence.plot_simple())
# Output: "    ◀==========|          ▶    -0.42 (stressed)"

# Full history
print(valence.plot_history(width=60, height=10))
# Output: ASCII chart of valence over time

# Summary report
from agent.valence_system import get_emotional_summary
print(get_emotional_summary(valence))
```

### Manual Adjustments

```python
# Inject a feeling (for external triggers like user feedback)
valence.inject_feeling(+0.3, reason="user_praised_results")

# Reset to neutral (use sparingly)
valence.reset()
```

## Integration with Organism Core

The valence system integrates tightly with the organism:

```python
# organism_core.py already wires up valence
organism = init_organism(...)

# Valence receives all events:
# 1. EventBus emits event
# 2. ValenceSystem._on_event() called
# 3. Valence updated based on event type
# 4. Mood calculated
# 5. History recorded
# 6. Decay triggered by heartbeat

# Example event flow:
await event_bus.publish(OrganismEvent(
    event_type=EventType.ACTION_FAILED,
    source="brain",
    data={"tool": "playwright_navigate", "error": "timeout"}
))
# → Valence drops by -0.15
# → Mood may shift from "neutral" to "uneasy"
# → Strategy becomes "careful"
# → Speed multiplier drops to 0.9x
```

## Persistence

Valence state is automatically saved:

```python
# Saved to: memory/valence_state.json
{
  "current_valence": 0.42,
  "current_mood": "content",
  "mood_entry_time": 1701234567.89,
  "failure_streak": 0,
  "success_streak": 3,
  "history": [...],  # Last 100 snapshots
  "saved_at": "2025-12-04T10:30:00"
}
```

State persists across restarts, allowing the agent to "remember" its emotional trajectory.

## Testing

Run comprehensive tests:

```bash
# Run full test suite
pytest agent/test_valence_system.py -v

# Run specific test class
pytest agent/test_valence_system.py::TestValenceUpdates -v

# Run demo
python agent/valence_example.py
```

## Design Philosophy

### Why Valence?

The valence system answers: **"How does the agent FEEL right now?"**

This is critical for AGI because:
1. **Motivation** - Pain motivates fixing, pleasure motivates continuation
2. **Decision-making** - Emotional state influences risk tolerance and speed
3. **Self-awareness** - The agent "knows" when things are going poorly
4. **Communication** - Emotional state can be communicated to users ("I'm struggling")
5. **Learning** - Emotional gradient guides reinforcement learning

### Valence vs Gap Detection

| Feature | Gap Detection | Valence System |
|---------|---------------|----------------|
| Signal | Binary (surprise/no surprise) | Gradient (pain to pleasure) |
| Trigger | Prediction mismatch | All events |
| Purpose | Awareness of unexpected | Emotional state |
| Response | Learn from surprise | Adjust behavior |
| Temporal | Instant (per action) | Accumulates over time |

Both systems work together:
- Gap detector notices **surprises** → small valence drop
- Major surprises → larger valence drop
- Repeated surprises → compounding pain → defensive strategy

### Valence vs Mission Alignment

| Feature | Mission Alignment | Valence System |
|---------|-------------------|----------------|
| Question | "Is this aligned with mission?" | "How do I feel?" |
| Output | Alignment score (0-1) | Valence (-1 to +1) |
| Purpose | Identity/values check | Emotional experience |
| Weight | Keyword matching | Event deltas |

Customer success affects both:
- Mission alignment: High score (0.9+)
- Valence: Large positive delta (+0.3)

## Future Enhancements

Potential additions:
- [ ] **Emotional memory** - Remember past emotional states and patterns
- [ ] **Mood-specific strategies** - Different behavior per mood
- [ ] **Emotional forecasting** - Predict valence trajectory
- [ ] **Multi-dimensional emotions** - Separate axes (fear, joy, frustration, excitement)
- [ ] **User emotional mirroring** - Detect and respond to user emotions
- [ ] **Valence-guided exploration** - Use curiosity when valence is neutral/positive

## Files

| File | Purpose |
|------|---------|
| `valence_system.py` | Core valence implementation |
| `valence_example.py` | Interactive demonstration |
| `test_valence_system.py` | Comprehensive test suite |
| `VALENCE_SYSTEM.md` | This documentation |

## See Also

- `organism_core.py` - The nervous system that valence plugs into
- `survival_manager.py` - Resource management (complements valence)
- `awareness_hub.py` - Self-awareness (uses valence for context)
- `reflexion_engine.py` - Learning from mistakes (triggered by negative valence)

---

**The valence system transforms the agent from a state machine into a feeling organism.**
