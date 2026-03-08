# Model Orchestrator Integration Guide

How to integrate the Model Orchestrator into the main brain (`brain_enhanced_v2.py`).

## Integration Points

The orchestrator can be integrated at multiple levels:

### 1. Task Planning (Strategic Level)

Replace direct Kimi K2 calls with orchestrated planning:

```python
# In brain_enhanced_v2.py

from agent.model_orchestrator import ModelOrchestrator, get_orchestrator

class EnhancedBrain:
    def __init__(self, ...):
        # ... existing init code ...

        # Add orchestrator
        self.orchestrator = get_orchestrator(
            kimi_client=self.kimi_client,
            event_bus=self.event_bus,  # If using organism_core
            enable_verification=self.config.get("enable_verification", False),
        )

    async def plan_task(self, prompt: str):
        """Strategic planning with multi-model orchestration."""

        # Gather context
        screenshot = None
        if self.browser:
            screenshot = await self.browser_manager.capture_screenshot()

        # Orchestrate planning
        result = await self.orchestrator.execute(
            task=prompt,
            tools=["kimi_k2", "vision"],
            screenshot=screenshot,
            available_tools=self.get_available_tools(),
            context=self.get_context_summary(),
        )

        # Check confidence
        if result.confidence < 0.5:
            logger.warning(f"Low confidence plan ({result.confidence:.2%})")
            if result.conflicts:
                logger.warning(f"Conflicts detected: {result.conflicts}")

        # Return primary plan
        return result.primary_answer
```

### 2. Tool Execution (Tactical Level)

Use orchestrator for complex tool decisions:

```python
async def execute_tool(self, tool_name: str, args: dict):
    """Execute tool with orchestrated decision-making."""

    # For complex tools, use orchestrator
    if tool_name in ["playwright_extract_entities", "playwright_batch_extract"]:
        # Get visual context
        screenshot = await self.browser_manager.capture_screenshot()

        # Orchestrate execution strategy
        result = await self.orchestrator.execute(
            task=f"Execute {tool_name} with {args}",
            tools=["vision", "kimi_k2"],
            screenshot=screenshot,
            available_tools=[tool_name],
        )

        # Execute based on orchestrated plan
        return await self._execute_orchestrated_tool(tool_name, args, result)

    # For simple tools, execute directly
    return await self._execute_tool_direct(tool_name, args)
```

### 3. Error Recovery (Recovery Level)

Use orchestrator for intelligent recovery:

```python
async def recover_from_error(self, error: Exception, context: dict):
    """Recover from errors using multi-model analysis."""

    # Gather diagnostic info
    screenshot = await self.browser_manager.capture_screenshot()
    page_state = await self.browser.page.content()

    # Orchestrate recovery strategy
    result = await self.orchestrator.execute(
        task=f"Recover from error: {error}",
        tools=["vision", "kimi_k2", "chatgpt"],
        screenshot=screenshot,
        context=f"Error: {error}\nPage state: {page_state[:500]}",
        available_tools=self.get_available_tools(),
    )

    # Execute recovery plan
    if result.confidence > 0.6:
        return await self._execute_recovery_plan(result.primary_answer)
    else:
        # Escalate to human
        return await self._escalate_to_human(error, result)
```

## Full Integration Example

```python
# brain_enhanced_v2.py

from agent.model_orchestrator import ModelOrchestrator, get_orchestrator, ModelType
from agent.kimi_k2_client import KimiK2Client, get_kimi_client
from agent.organism_core import EventBus, EventType

class EnhancedBrain:
    def __init__(self, config: dict):
        # ... existing init ...

        # Initialize Kimi K2
        self.kimi_client = get_kimi_client(config)

        # Initialize EventBus (if using organism)
        self.event_bus = EventBus()

        # Initialize Orchestrator
        self.orchestrator = get_orchestrator(
            kimi_client=self.kimi_client,
            event_bus=self.event_bus,
            chatgpt_api_key=config.get("openai_api_key"),
            enable_verification=config.get("enable_verification", False),
            parallel_timeout=30.0,
            reasoning_timeout=60.0,
        )

        # Subscribe to orchestrator events
        self.event_bus.subscribe(EventType.ACTION_COMPLETE, self._on_orchestration_complete)
        self.event_bus.subscribe(EventType.ACTION_FAILED, self._on_orchestration_failed)

    async def think_and_act(self, prompt: str) -> str:
        """Main agent loop with orchestrated decision-making."""

        # Phase 1: Strategic Planning (Orchestrated)
        logger.info(f"Planning task: {prompt}")

        screenshot = None
        if self.browser:
            screenshot = await self.browser_manager.capture_screenshot()

        plan_result = await self.orchestrator.execute(
            task=prompt,
            tools=["kimi_k2", "vision"],
            screenshot=screenshot,
            available_tools=self.get_available_tools(),
            context=self.get_recent_history(),
        )

        logger.info(f"Plan confidence: {plan_result.confidence:.2%}")

        # Check if plan is trustworthy
        if plan_result.confidence < 0.5:
            logger.warning("Low confidence plan - requesting human verification")
            return await self._request_human_approval(plan_result)

        # Phase 2: Execution
        plan = plan_result.primary_answer

        if not plan:
            return "Failed to create plan"

        # Execute plan steps
        results = []
        for step in plan.steps:
            try:
                result = await self.execute_tool(step.tool, step.arguments)
                results.append(result)
            except Exception as e:
                # Orchestrated recovery
                recovery = await self.recover_from_error(e, {
                    "step": step,
                    "plan": plan,
                    "results_so_far": results,
                })
                if recovery:
                    results.append(recovery)
                else:
                    break

        return self._format_results(results)

    async def execute_tool(self, tool_name: str, args: dict):
        """Execute tool with optional orchestration for complex cases."""

        # Simple tools - direct execution
        if tool_name in ["playwright_navigate", "playwright_click", "playwright_fill"]:
            return await self._execute_tool_direct(tool_name, args)

        # Complex tools - orchestrated execution
        screenshot = await self.browser_manager.capture_screenshot()

        execution_plan = await self.orchestrator.execute(
            task=f"Execute {tool_name} optimally",
            tools=["vision", "chatgpt"],
            screenshot=screenshot,
            context=f"Tool: {tool_name}, Args: {args}",
        )

        # Check for issues detected by vision
        if ModelType.OLLAMA_VISION in execution_plan.model_results:
            vision = execution_plan.model_results[ModelType.OLLAMA_VISION]
            if vision.success and "error" in str(vision.content).lower():
                logger.warning(f"Vision detected issues: {vision.content[:200]}")

        return await self._execute_tool_direct(tool_name, args)

    async def recover_from_error(self, error: Exception, context: dict):
        """Orchestrated error recovery."""

        screenshot = await self.browser_manager.capture_screenshot()

        recovery_result = await self.orchestrator.execute(
            task=f"Recover from: {str(error)[:200]}",
            tools=["vision", "kimi_k2", "chatgpt"],
            screenshot=screenshot,
            context=str(context)[:1000],
            available_tools=self.get_available_tools(),
        )

        if recovery_result.confidence < 0.6:
            logger.error("Cannot recover with confidence - escalating")
            return None

        # Execute recovery plan
        logger.info(f"Recovery plan confidence: {recovery_result.confidence:.2%}")
        return recovery_result.primary_answer

    def _on_orchestration_complete(self, event):
        """Handle orchestration completion events."""
        logger.debug(f"Orchestration complete: {event.data}")

        # Update metrics
        self.stats["orchestration_calls"] += 1
        self.stats["avg_orchestration_time"] = event.data.get("execution_time_ms", 0)

    def _on_orchestration_failed(self, event):
        """Handle orchestration failure events."""
        logger.warning(f"Orchestration failed: {event.data}")

        # Update failure metrics
        self.stats["orchestration_failures"] += 1

    def get_available_tools(self) -> List[str]:
        """Get list of available tool names."""
        return [
            "playwright_navigate",
            "playwright_click",
            "playwright_fill",
            "playwright_extract_entities",
            "playwright_screenshot",
            "playwright_batch_extract",
            "save_to_csv",
        ]

    def get_recent_history(self) -> str:
        """Get recent action history for context."""
        if hasattr(self, "messages"):
            recent = self.messages[-5:]  # Last 5 messages
            return "\n".join(str(m) for m in recent)
        return ""

    async def cleanup(self):
        """Cleanup resources."""
        await self.orchestrator.close()
        # ... other cleanup ...
```

## Configuration

Add to `config/config.yaml`:

```yaml
orchestrator:
  enabled: true
  enable_verification: false  # Set to true for critical tasks
  parallel_timeout: 30.0
  reasoning_timeout: 60.0
  verification_timeout: 20.0

  # Model selection
  chatgpt_model: "gpt-4o-mini"
  vision_model: "minicpm-v"

  # When to use orchestration
  use_for:
    - planning  # Strategic planning
    - recovery  # Error recovery
    - complex_tools  # Complex tool execution
```

## Gradual Migration

You can migrate gradually:

### Step 1: Use for Planning Only

```python
# Only use orchestrator for initial planning
async def plan_task(self, prompt: str):
    if self.config.get("orchestrator.enabled"):
        return await self._orchestrated_planning(prompt)
    else:
        return await self._legacy_planning(prompt)
```

### Step 2: Add for Recovery

```python
# Use for recovery after multiple failures
async def handle_failure(self, error, attempts):
    if attempts >= 2 and self.config.get("orchestrator.enabled"):
        return await self._orchestrated_recovery(error)
    else:
        return await self._legacy_recovery(error)
```

### Step 3: Expand to All Decisions

```python
# Use orchestrator for all complex decisions
async def make_decision(self, decision_type: str, context: dict):
    if self.config.get("orchestrator.enabled"):
        return await self._orchestrated_decision(decision_type, context)
    else:
        return await self._legacy_decision(decision_type, context)
```

## Performance Considerations

### 1. Caching

Cache orchestration results for identical tasks:

```python
from functools import lru_cache
import hashlib

class EnhancedBrain:
    def __init__(self):
        self._orchestration_cache = {}

    async def orchestrate_with_cache(self, task: str, **kwargs):
        # Create cache key
        cache_key = hashlib.md5(f"{task}{kwargs}".encode()).hexdigest()

        # Check cache
        if cache_key in self._orchestration_cache:
            logger.debug("Using cached orchestration result")
            return self._orchestration_cache[cache_key]

        # Execute
        result = await self.orchestrator.execute(task=task, **kwargs)

        # Cache result
        self._orchestration_cache[cache_key] = result

        return result
```

### 2. Selective Orchestration

Only use orchestration when needed:

```python
def should_orchestrate(self, task: str) -> bool:
    """Decide if task needs orchestration."""

    # Simple tasks - no orchestration
    simple_keywords = ["navigate", "click", "screenshot"]
    if any(kw in task.lower() for kw in simple_keywords):
        return False

    # Complex tasks - use orchestration
    complex_keywords = ["extract", "research", "analyze", "compare"]
    if any(kw in task.lower() for kw in complex_keywords):
        return True

    return False

async def think_and_act(self, prompt: str):
    if self.should_orchestrate(prompt):
        return await self._orchestrated_execution(prompt)
    else:
        return await self._direct_execution(prompt)
```

### 3. Async Background Orchestration

Run orchestration in background while executing simple plan:

```python
async def parallel_execute(self, prompt: str):
    # Start simple execution
    simple_task = asyncio.create_task(self._simple_execution(prompt))

    # Start orchestrated planning in parallel
    orchestrated_task = asyncio.create_task(self._orchestrated_planning(prompt))

    # Wait for simple execution
    simple_result = await simple_task

    # Check if orchestration has better plan
    if orchestrated_task.done():
        orchestrated_result = await orchestrated_task
        if orchestrated_result.confidence > 0.8:
            logger.info("Orchestrated plan is better - using it instead")
            return await self._execute_plan(orchestrated_result.primary_answer)

    return simple_result
```

## Monitoring

Track orchestrator performance:

```python
async def get_stats(self):
    """Get agent statistics including orchestrator."""

    stats = {
        # ... existing stats ...

        "orchestrator": self.orchestrator.get_stats(),
    }

    return stats
```

Monitor in real-time:

```python
# Subscribe to orchestrator events
self.event_bus.subscribe(EventType.ACTION_COMPLETE, lambda e:
    logger.info(f"Orchestration: {e.data['execution_time_ms']:.1f}ms, "
                f"confidence: {e.data['confidence']:.2%}")
)
```

## Troubleshooting

### Issue: Orchestrator Too Slow

**Solution**: Reduce timeouts and disable verification:

```python
orchestrator = ModelOrchestrator(
    enable_verification=False,
    parallel_timeout=10.0,
    reasoning_timeout=30.0,
)
```

### Issue: Low Confidence Scores

**Solution**: Enable verification and provide more context:

```python
result = await orchestrator.execute(
    task=prompt,
    tools=["kimi_k2", "vision", "chatgpt"],
    screenshot=screenshot,
    context=rich_context,  # More context = better results
)
```

### Issue: Conflicts Detected

**Solution**: Investigate and resolve:

```python
if result.conflicts:
    logger.warning(f"Conflicts: {result.conflicts}")

    # Check individual model results
    for model_type, model_result in result.model_results.items():
        logger.info(f"{model_type.value}: {model_result.content}")

    # Manual resolution
    if should_trust_vision(result):
        return result.model_results[ModelType.OLLAMA_VISION].content
    else:
        return result.primary_answer
```

## Related Documentation

- `agent/MODEL_ORCHESTRATOR.md` - Full orchestrator documentation
- `agent/model_orchestrator_example.py` - Usage examples
- `agent/kimi_k2_client.py` - Kimi K2 client documentation
- `agent/organism_core.py` - EventBus and nervous system

## Next Steps

1. Review `agent/MODEL_ORCHESTRATOR.md` for detailed API documentation
2. Run examples: `python -m agent.model_orchestrator_example`
3. Run tests: `pytest test_model_orchestrator.py -v`
4. Integrate into your brain step-by-step
5. Monitor performance and adjust timeouts/settings
