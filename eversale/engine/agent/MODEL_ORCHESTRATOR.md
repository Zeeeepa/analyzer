# Model Orchestrator

Intelligently combine multiple AI model outputs for higher-quality results.

## Overview

The Model Orchestrator coordinates multiple AI models to produce superior results:

- **Kimi K2** (1 trillion params) - Strategic planning and reasoning
- **ChatGPT** (GPT-4o-mini) - Verification and quality checks
- **Browser/Web** - Real-time information gathering
- **MiniCPM/Ollama Vision** - Visual understanding and screenshot analysis

## Features

### 1. Parallel Execution
Fast models (vision, web search) run in parallel to gather context before the primary reasoning step.

### 2. Graceful Fallbacks
If the primary model (Kimi K2) is unavailable, automatically falls back to ChatGPT or local models.

### 3. Conflict Resolution
When models disagree, the orchestrator detects conflicts and adjusts confidence scores accordingly.

### 4. Confidence Scoring
Aggregates confidence from all models, adjusting based on agreement and verification results.

### 5. EventBus Integration
Emits events for monitoring and coordination with the organism core.

### 6. Timeout Handling
Each phase has configurable timeouts to prevent hung operations.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    MODEL ORCHESTRATOR                        │
└─────────────────────────────────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
     PHASE 1          PHASE 2          PHASE 3
  (Parallel)        (Reasoning)     (Verification)
          │                │                │
    ┌─────┴─────┐         │          ┌─────┴─────┐
    │           │         │          │           │
  Vision      Web      Kimi K2     ChatGPT    (optional)
  Model      Search   (Primary)  (Verify)
    │           │         │          │
    └─────┬─────┘         │          └─────┬─────┘
          │               │                │
          └───────────────┼────────────────┘
                          │
                    PHASE 4
                  (Synthesis)
                 ┌─────────┐
                 │ Combine │
                 │ Resolve │
                 │ Score   │
                 └─────────┘
```

## Usage

### Basic Usage

```python
from agent.model_orchestrator import ModelOrchestrator, get_orchestrator
from agent.kimi_k2_client import KimiK2Client
from agent.organism_core import EventBus

# Initialize components
kimi = KimiK2Client(provider="auto")
event_bus = EventBus()

# Create orchestrator
orchestrator = ModelOrchestrator(
    kimi_client=kimi,
    event_bus=event_bus,
    enable_verification=False,
)

# Execute task
result = await orchestrator.execute(
    task="Find Python developers on LinkedIn",
    tools=["kimi_k2", "vision"],
    available_tools=["playwright_navigate", "playwright_extract_entities"],
    context="Building talent pipeline",
)

# Check results
print(f"Confidence: {result.confidence:.2%}")
print(f"Models Used: {result.models_used}")
print(f"Execution Time: {result.execution_time_ms:.1f}ms")
```

### With Verification

```python
orchestrator = ModelOrchestrator(
    kimi_client=kimi,
    chatgpt_api_key="sk-...",
    chatgpt_model="gpt-4o-mini",
    enable_verification=True,  # Enable ChatGPT verification
)

result = await orchestrator.execute(
    task="Complex task requiring verification",
    tools=["kimi_k2", "chatgpt"],
    available_tools=["playwright_navigate"],
)

# Check if verification passed
if ModelType.CHATGPT in result.model_results:
    verification = result.model_results[ModelType.CHATGPT]
    if verification.success:
        verdict = verification.content.get("verdict")
        print(f"Verification: {verdict}")
```

### With Vision Analysis

```python
# Capture screenshot from browser
screenshot = await browser.screenshot()

result = await orchestrator.execute(
    task="Analyze current page state",
    tools=["vision", "kimi_k2"],
    screenshot=screenshot,
    available_tools=["playwright_click", "playwright_fill"],
)

# Vision analysis available in results
if ModelType.OLLAMA_VISION in result.model_results:
    vision = result.model_results[ModelType.OLLAMA_VISION]
    print(f"Visual Analysis: {vision.content}")
```

### Global Singleton Pattern

```python
# Get global orchestrator instance
orch1 = get_orchestrator(
    kimi_client=kimi,
    event_bus=event_bus,
)

# Calling again returns same instance
orch2 = get_orchestrator()
assert orch1 is orch2
```

## Configuration

### Timeouts

```python
orchestrator = ModelOrchestrator(
    parallel_timeout=30.0,       # Phase 1: parallel context gathering
    reasoning_timeout=60.0,      # Phase 2: primary reasoning
    verification_timeout=20.0,   # Phase 3: verification
)
```

### Model Selection

```python
orchestrator = ModelOrchestrator(
    kimi_client=kimi,                # Kimi K2 for planning
    chatgpt_model="gpt-4o-mini",     # ChatGPT for verification
    vision_model="minicpm-v",        # Vision model for screenshots
    enable_verification=True,        # Enable verification step
)
```

## Result Structure

```python
@dataclass
class OrchestratedResult:
    task: str                                  # Original task
    primary_answer: Any                        # Main result (from Kimi/ChatGPT)
    model_results: Dict[ModelType, ModelResult] # All model outputs
    confidence: float                          # Overall confidence (0-1)
    conflicts: List[str]                       # Detected conflicts
    execution_time_ms: float                   # Total execution time
    models_used: Set[ModelType]                # Which models were used
    fallback_chain: List[str]                  # Fallback chain (if any)
```

## Conflict Resolution

The orchestrator automatically detects and handles conflicts:

1. **Verification Rejection**: If ChatGPT verification rejects the primary answer, confidence drops to 0.3
2. **Vision Errors**: If vision detects errors, confidence is reduced by 20%
3. **Model Agreement**: Higher agreement = higher confidence

```python
result = await orchestrator.execute(...)

if result.conflicts:
    print("Conflicts detected:")
    for conflict in result.conflicts:
        print(f"  - {conflict}")

    if result.confidence < 0.5:
        print("⚠️  Low confidence - manual review recommended")
```

## Statistics

Track orchestrator performance:

```python
stats = orchestrator.get_stats()

print(f"Total Executions: {stats['total_executions']}")
print(f"Success Rate: {stats['success_rate']:.2%}")
print(f"Avg Confidence: {stats['avg_confidence']:.2f}")
print(f"Avg Execution Time: {stats['avg_execution_time_ms']:.1f}ms")
print(f"Conflicts Detected: {stats['conflicts_detected']}")
print(f"Fallbacks Triggered: {stats['fallbacks_triggered']}")

# Model usage breakdown
print("\nModel Usage:")
for model, count in stats['model_usage'].items():
    print(f"  {model}: {count}")
```

## EventBus Integration

The orchestrator emits events for monitoring:

```python
from agent.organism_core import EventType, OrganismEvent

# Subscribe to events
def on_action_complete(event: OrganismEvent):
    print(f"Action complete: {event.data}")

event_bus.subscribe(EventType.ACTION_START, on_action_start)
event_bus.subscribe(EventType.ACTION_COMPLETE, on_action_complete)
event_bus.subscribe(EventType.ACTION_FAILED, on_action_failed)

# Events emitted automatically during execution
result = await orchestrator.execute(...)
```

## Error Handling

The orchestrator handles errors gracefully:

```python
try:
    result = await orchestrator.execute(...)

    # Check for failures
    for model_type, model_result in result.model_results.items():
        if not model_result.success:
            print(f"{model_type.value} failed: {model_result.error}")

    # Overall status
    if result.primary_answer is None:
        print("All models failed - fallback to manual execution")

except Exception as e:
    print(f"Orchestration failed: {e}")
```

## Best Practices

### 1. Use Verification for Critical Tasks

```python
# For high-stakes operations, enable verification
orchestrator = ModelOrchestrator(
    enable_verification=True,
    chatgpt_model="gpt-4o-mini",  # Fast and accurate
)
```

### 2. Provide Rich Context

```python
# Give models as much context as possible
result = await orchestrator.execute(
    task="Extract contacts",
    context="Previous attempts failed due to CAPTCHA",
    screenshot=screenshot,
    web_search_query="CAPTCHA bypass techniques",
)
```

### 3. Monitor Confidence Scores

```python
result = await orchestrator.execute(...)

if result.confidence < 0.7:
    # Low confidence - consider manual intervention
    await notify_human(result)
else:
    # High confidence - proceed automatically
    await execute_plan(result.primary_answer)
```

### 4. Handle Timeouts Appropriately

```python
# Adjust timeouts based on task complexity
orchestrator = ModelOrchestrator(
    parallel_timeout=60.0,      # Longer for complex vision analysis
    reasoning_timeout=120.0,    # Longer for complex planning
)
```

### 5. Clean Up Resources

```python
try:
    result = await orchestrator.execute(...)
finally:
    await orchestrator.close()  # Clean up API clients
```

## Examples

See `agent/model_orchestrator_example.py` for comprehensive examples:

- Basic orchestration with Kimi K2 + Vision
- Multi-model verification
- Vision analysis with screenshots
- Conflict resolution
- Fallback chain handling
- Parallel context gathering
- Global singleton pattern

Run examples:

```bash
python -m agent.model_orchestrator_example
```

## Testing

Run integration tests:

```bash
pytest test_model_orchestrator.py -v
```

Or run directly:

```bash
python test_model_orchestrator.py
```

## Performance

Typical execution times:

- **Phase 1 (Parallel)**: 2-5 seconds (vision + web search)
- **Phase 2 (Reasoning)**: 5-15 seconds (Kimi K2 planning)
- **Phase 3 (Verification)**: 3-8 seconds (ChatGPT verification)
- **Total**: 10-30 seconds for complete orchestration

Parallel execution saves 50-70% compared to sequential execution.

## Future Enhancements

- [ ] Web search integration with browser automation
- [ ] Multi-agent collaboration (multiple Kimi K2 instances)
- [ ] Caching of model outputs for identical tasks
- [ ] Dynamic model selection based on task type
- [ ] Budget optimization across models
- [ ] Real-time streaming of intermediate results
- [ ] A/B testing of different model combinations

## Related Components

- `agent/kimi_k2_client.py` - Kimi K2 strategic planner
- `agent/organism_core.py` - EventBus and nervous system
- `agent/vision_processor.py` - Vision processing mixin
- `agent/brain_enhanced_v2.py` - Main agent brain (uses orchestrator)

## License

Part of the Eversale autonomous AI worker system.
