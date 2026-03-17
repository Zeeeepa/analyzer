# Planning Agent Quick Start Guide

Get started with Eversale's Hierarchical Task Network Planning Agent in 5 minutes.

## Installation

No additional dependencies required - uses existing Eversale environment.

```bash
# Verify installation
python3 -c "from agent.planning_agent import planning_agent; print('✓ Planning Agent ready')"
```

## Basic Usage

### 1. Simple Plan & Execute

```python
from agent.planning_agent import quick_plan_and_execute

async def my_action_handler(action, arguments):
    """Your action executor"""
    print(f"Executing: {action}")
    return {'success': True}

# One-liner: plan, validate, and execute
result = await quick_plan_and_execute(
    task="Research Stripe and extract contacts",
    action_handler=my_action_handler
)

print(f"Success: {result['success']}")
```

### 2. Full Control

```python
from agent.planning_agent import PlanningAgent

# Initialize
agent = PlanningAgent(action_handler=my_action_handler)

# Create plan
plan = await agent.plan(
    task="Generate leads from Facebook Ads",
    max_depth=3
)

# Validate
evaluation = await agent.validate_plan(plan)
print(f"Score: {evaluation['overall_score']}")

# Execute if approved
if evaluation['approved']:
    await agent.approve_plan(plan)
    result = await agent.execute_plan(plan)
```

### 3. Using Templates

```python
from agent.planning_agent import PlanTemplate

# Load existing template
template = PlanTemplate.load('sdr_lead_gen')

# Instantiate with parameters
plan = template.instantiate({
    'target_keyword': 'CRM software',
    'source': 'https://facebook.com/ads/library',
    'max_leads': 50
})

# Execute
agent = PlanningAgent(action_handler=my_handler)
await agent.approve_plan(plan, user_approval=False)
result = await agent.execute_plan(plan)
```

## Integration with Eversale

### With Brain Enhanced V2

```python
from agent.brain_enhanced_v2 import EnhancedBrain
from agent.planning_agent import PlanningAgent

brain = EnhancedBrain()

async def brain_handler(action, arguments):
    """Route to brain methods"""
    if hasattr(brain, action):
        method = getattr(brain, action)
        return await method(**arguments)
    return await brain.execute_action(action, arguments)

planner = PlanningAgent(action_handler=brain_handler)

# Now brain executes plans
plan = await planner.plan("Research company")
await planner.approve_plan(plan, user_approval=False)
result = await planner.execute_plan(plan)
```

### With Task Decomposer

```python
from agent.task_decomposer import task_decomposer
from agent.planning_agent import planning_agent

# Get atomic operations
atomic_ops = task_decomposer.decompose(
    "Search Facebook Ads for 'dog food'"
)

# Or use planning agent for hierarchy
plan = await planning_agent.plan(
    "Search Facebook Ads for 'dog food'",
    max_depth=3
)

# Planning agent provides better structure for complex tasks
```

### With Capability Router

```python
from agent.capability_router import route_to_capability
from agent.planning_agent import planning_agent

user_input = "Research the company Stripe"

# Try capability first
match = route_to_capability(user_input)

if match:
    # Use capability
    result = execute_capability(match)
else:
    # Use planning agent
    plan = await planning_agent.plan(user_input)
    result = await execute_plan(plan)
```

## Common Patterns

### Pattern 1: Research Task

```python
plan = await agent.plan(
    task="Research OpenAI and extract team info",
    context={'target_url': 'https://openai.com'},
    max_depth=3
)

# Plan automatically includes:
# - Navigation steps
# - Search/extraction logic
# - Validation
# - Error handling with retries
```

### Pattern 2: Data Extraction

```python
plan = await agent.plan(
    task="Extract leads from 50 companies",
    context={
        'sources': ['company1.com', 'company2.com', ...],
        'batch_size': 10
    },
    max_depth=3
)

# Plan includes:
# - Batch processing (parallel where possible)
# - Checkpointing every N items
# - Fallbacks for failures
# - Export to CSV
```

### Pattern 3: Monitoring Task

```python
plan = await agent.plan(
    task="Monitor inbox for urgent emails every 30 minutes",
    context={'urgency_keywords': ['urgent', 'asap', 'critical']},
    max_depth=2
)

# Plan includes:
# - Check inbox
# - Filter by keywords
# - Classify urgency
# - Generate alerts
# - Track state between runs
```

## Error Handling

### Automatic Retry

```python
# Plans automatically retry failed steps
step.max_retries = 3  # Default

# High-risk steps get more retries
if 'browser' in action:
    step.max_retries = 5
```

### Fallback Steps

```python
# Fallbacks added automatically for risky operations
step.fallback_steps = ['screenshot_fallback', 'manual_fallback']

# Execution tries: primary → retry 3x → fallback #1 → fallback #2
```

### Replanning

```python
# After failure, replan affected portion
new_plan = await agent.replan(
    original_plan=plan,
    failed_step_id='step_5',
    partial=True  # Only replan failed subtree
)

# Execute recovery plan
result = await agent.execute_plan(new_plan)
```

## Checkpointing

```python
# Automatic checkpoints every N steps
result = await agent.execute_plan(
    plan,
    checkpoint_interval=5  # Checkpoint every 5 completed steps
)

# Resume after crash
plan = Plan.load('plan_id')
if plan.status == PlanStatus.PAUSED:
    result = await agent.executor.resume(plan.plan_id)

# Rollback to checkpoint
await agent.executor.rollback(plan.plan_id, checkpoint_index=-1)
```

## Progress Tracking

```python
async def progress_handler(progress):
    """Track execution progress"""
    print(f"{progress['percent']:.0f}% complete")
    print(f"{progress['completed']}/{progress['total']} steps")

result = await agent.execute_plan(
    plan,
    progress_callback=progress_handler
)
```

## Creating Templates

```python
# After successful execution, save as template
if result['success'] and plan.critic_score >= 0.8:
    template = agent.create_template(
        name="My Custom Workflow",
        description="Does X, Y, Z",
        category="custom",
        plan=plan
    )

    print(f"Created template: {template.template_id}")

# Reuse template
plan = template.instantiate({
    'required_param': 'value',
    'optional_param': 'value'
})
```

## Performance Tips

### 1. Use Templates for Common Tasks

```python
# Templates are 10x faster than planning from scratch
template = PlanTemplate.load('sdr_lead_gen')
plan = template.instantiate(params)  # Instant
```

### 2. Adjust Max Depth

```python
# Shallow plans execute faster
plan = await agent.plan(task, max_depth=2)  # Fast, less detailed

# Deep plans are more robust
plan = await agent.plan(task, max_depth=4)  # Slow, very detailed
```

### 3. Enable Parallelization

```python
# Mark steps as parallel when possible
step.task_type = TaskType.PARALLEL

# Executor runs parallel groups concurrently
parallel_groups = plan.get_parallel_steps()
```

### 4. Optimize Checkpoint Interval

```python
# More frequent = slower but safer
result = await agent.execute_plan(plan, checkpoint_interval=3)

# Less frequent = faster but less safe
result = await agent.execute_plan(plan, checkpoint_interval=10)
```

## Debugging

### View Plan Structure

```python
# Human-readable summary
print(agent.get_plan_summary(plan))

# Inspect steps
for step_id, step in plan.steps.items():
    print(f"{step.name}: {step.status.value}")

# Check dependencies
for step in plan.steps.values():
    print(f"{step.name} depends on: {step.depends_on}")
```

### Check Validation Issues

```python
evaluation = await agent.validate_plan(plan)

if not evaluation['approved']:
    print("Feasibility issues:", evaluation['feasibility']['suggestions'])
    print("Efficiency issues:", evaluation['efficiency']['suggestions'])
    print("Risk issues:", evaluation['risk']['suggestions'])
```

### Monitor Execution

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Now see detailed execution logs
result = await agent.execute_plan(plan)
```

## Examples

Run the demo to see all features:

```bash
# Run all examples
python examples/planning_agent_demo.py

# Interactive mode
python examples/planning_agent_demo.py interactive
```

## Common Issues

### Issue: Plan validation fails

**Solution:** Check suggestions and reduce complexity

```python
evaluation = await agent.validate_plan(plan)
print(evaluation['suggestions'])

# Try simpler plan
plan = await agent.plan(task, max_depth=2)
```

### Issue: Execution hangs

**Solution:** Check for circular dependencies or blocked steps

```python
# Find blocked steps
blocked = [s for s in plan.steps.values() if s.status == StepStatus.BLOCKED]
print(f"Blocked: {[s.step_id for s in blocked]}")

# Check dependencies
for step in blocked:
    print(f"{step.step_id} waiting for: {step.depends_on}")
```

### Issue: Too many failures

**Solution:** Increase retries or add fallbacks

```python
# Increase retries globally
for step in plan.steps.values():
    step.max_retries = 5

# Add fallbacks manually
step.fallback_steps.append('manual_fallback_step')
```

## Next Steps

1. **Read Full Documentation:** `/mnt/c/ev29/agent/PLANNING_AGENT_README.md`
2. **Check Integration Guide:** `/mnt/c/ev29/agent/PLANNING_AGENT_INTEGRATION.md`
3. **Run Examples:** `/mnt/c/ev29/examples/planning_agent_demo.py`
4. **Create Custom Templates:** Based on your workflows
5. **Integrate with Brain:** Use as action executor

## Quick Reference

```python
# Core imports
from agent.planning_agent import (
    PlanningAgent,
    Plan,
    PlanStep,
    PlanTemplate,
    PlanCritic,
    PlanExecutor,
    quick_plan_and_execute
)

# Initialize
agent = PlanningAgent(action_handler=my_handler)

# Plan
plan = await agent.plan(task, max_depth=3)

# Validate
evaluation = await agent.validate_plan(plan)

# Approve
await agent.approve_plan(plan, user_approval=False)

# Execute
result = await agent.execute_plan(plan)

# Save/Load
plan.save()
loaded = Plan.load(plan_id)

# Templates
template = PlanTemplate.load('template_id')
plan = template.instantiate(params)

# Replan
new_plan = await agent.replan(plan, failed_step_id)

# Checkpoint
await agent.executor.rollback(plan_id, -1)
```

## Support

- Documentation: `/mnt/c/ev29/agent/PLANNING_AGENT_*.md`
- Examples: `/mnt/c/ev29/examples/planning_agent_demo.py`
- Source: `/mnt/c/ev29/agent/planning_agent.py`

---

**Happy Planning!** 🎯

