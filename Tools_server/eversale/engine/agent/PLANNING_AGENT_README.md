# Hierarchical Task Network (HTN) Planning Agent

Advanced planning system for Eversale that provides enterprise-grade task decomposition, validation, and execution capabilities.

## Overview

The Planning Agent implements a sophisticated HTN planning architecture inspired by AgentOrchestra, Devin, and enterprise multi-agent systems. It transforms complex user requests into validated, executable plans with built-in error recovery and coordination.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Planning Agent                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Task Analysis → Understand requirements                 │
│  2. Resource Check → Verify availability                    │
│  3. Template Matching → Use proven patterns                 │
│  4. Decomposition → Break into hierarchy (3+ levels)        │
│  5. Dependency Graph → Build execution order                │
│  6. Risk Assessment → Identify failure points               │
│  7. Contingency Plans → Add fallbacks                       │
│  8. Critic Validation → Score & approve                     │
│  9. Execution → Run with checkpoints                        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. PlanningAgent
Main orchestrator that coordinates the entire planning pipeline.

```python
from agent.planning_agent import PlanningAgent, quick_plan_and_execute

agent = PlanningAgent(action_handler=my_executor)

# Create a plan
plan = await agent.plan(
    task="Research Stripe and extract contact info",
    max_depth=3,
    use_templates=True
)

# Validate plan
evaluation = await agent.validate_plan(plan)
print(f"Plan score: {evaluation['overall_score']}")
print(f"Suggestions: {evaluation['suggestions']}")

# Approve and execute
if evaluation['approved']:
    await agent.approve_plan(plan)
    result = await agent.execute_plan(plan)
```

### 2. Plan
Immutable plan representation with versioning and checkpointing.

```python
# Plan properties
plan.plan_id              # Unique identifier
plan.name                 # Human-readable name
plan.version              # Version number (for replanning)
plan.steps                # Dict of PlanStep objects
plan.status               # DRAFT, VALIDATED, APPROVED, EXECUTING, etc.
plan.checkpoints          # List of execution checkpoints
plan.critic_score         # Overall quality score (0-1)

# Plan methods
plan.save()                           # Persist to disk
plan.get_ready_steps()                # Get executable steps
plan.get_parallel_steps()             # Get parallelizable groups
plan.mark_step_completed(step_id)     # Update step status
plan.create_checkpoint(data)          # Save checkpoint
plan.get_progress()                   # Get execution progress
```

### 3. PlanStep
Individual step in hierarchical plan.

```python
step = PlanStep(
    step_id="unique_id",
    name="Extract contact info",
    description="Get emails and phones from company website",
    task_type=TaskType.PRIMITIVE,  # or COMPOSITE, PARALLEL, SEQUENTIAL
    action="playwright_extract_contacts",
    arguments={"url": "https://company.com"},

    # Hierarchy
    parent_id="parent_step_id",
    children=["child1", "child2"],
    depth=2,

    # Dependencies
    depends_on=["prev_step_id"],

    # Execution
    status=StepStatus.PENDING,
    max_retries=3,

    # Contingency
    fallback_steps=["fallback_step_id"],
    rollback_action="undo_extract"
)
```

### 4. PlanCritic
Validates plans before execution, scoring feasibility, efficiency, and risk.

```python
critic = PlanCritic()
evaluation = await critic.evaluate(plan)

# Evaluation results
{
    'overall_score': 0.85,              # Weighted score (0-1)
    'feasibility': {
        'score': 0.9,
        'suggestions': [...],
        'required_resources': ['browser', 'memory']
    },
    'efficiency': {
        'score': 0.8,
        'suggestions': [...],
        'parallelization_ratio': 0.4
    },
    'risk': {
        'score': 0.2,                   # Lower is better
        'suggestions': [...],
        'high_risk_steps': [...]
    },
    'completeness': {
        'complete': True,
        'suggestions': []
    },
    'suggestions': [...],               # All suggestions combined
    'approved': True                    # Auto-approve if score >= 0.7
}
```

### 5. PlanExecutor
Executes plans with checkpointing, parallelization, and rollback.

```python
executor = PlanExecutor(action_handler=my_handler)

result = await executor.execute(
    plan,
    checkpoint_interval=5,              # Checkpoint every 5 steps
    progress_callback=my_progress_fn
)

# Result
{
    'success': True,
    'completed_steps': 15,
    'failed_steps': [],
    'total_steps': 15,
    'duration': 234.5
}

# Control execution
await executor.pause(plan_id)          # Pause execution
await executor.resume(plan_id)         # Resume from checkpoint
await executor.rollback(plan_id, -1)   # Rollback to last checkpoint
```

### 6. PlanTemplate
Reusable templates for common workflows.

```python
template = PlanTemplate(
    template_id="sdr_lead_gen",
    name="SDR Lead Generation",
    category="SDR",
    required_params=['target_keyword', 'source'],
    optional_params=['max_leads'],
    step_templates=[...]
)

# Instantiate template
plan = template.instantiate({
    'target_keyword': 'CRM software',
    'source': 'https://facebook.com/ads/library',
    'max_leads': 50
})
```

## Task Decomposition

The Planning Agent supports **hierarchical decomposition** up to configurable depth (default 3 levels).

### Task Types

| Type | Description | Example |
|------|-------------|---------|
| **PRIMITIVE** | Atomic action (cannot decompose) | "Click button", "Fill form field" |
| **COMPOSITE** | Decomposable into sub-tasks | "Research company" → [Navigate, Search, Extract, Save] |
| **PARALLEL** | Can run concurrently | Multiple extractions, batch processing |
| **SEQUENTIAL** | Must run in order | Login → Navigate → Extract |
| **CONDITIONAL** | Execute based on condition | "If login required, then authenticate" |

### Decomposition Strategies

#### Research Task
```
Research Company
├── Navigate to target (15s)
├── Search for information (30s)
├── Extract relevant data (45s)
├── Verify accuracy (20s)
└── Save results (10s)
```

#### Extraction Task
```
Data Extraction
├── Prepare extraction (10s)
├── Extract batch 1 (60s) ──┐
├── Extract batch 2 (60s) ──┤ PARALLEL
└── Extract batch 3 (60s) ──┘
├── Validate data (30s)
└── Export to file (15s)
```

#### Processing Task
```
Data Processing
├── Load data (10s)
├── Clean data (30s)
├── Transform data (40s)
├── Validate output (20s)
└── Save processed data (10s)
```

## Dependency Management

The Planning Agent automatically builds dependency graphs:

```python
# Automatic dependencies based on parent-child relationships
step1 → step2 → step3  # Sequential

# Parallel execution when no dependencies
step1
step2  } PARALLEL
step3

# Complex dependencies
step1 → step2
     ↘  step3 → step4
```

## Risk Assessment & Contingencies

### Automatic Risk Detection

```python
# High-risk operations identified automatically
risk_factors = [
    'browser_dependency',      # Playwright operations
    'external_dependency',     # API calls
    'complex_extraction'       # Multi-step extraction
]

# Automatic contingencies added
step.fallback_steps = ['screenshot_fallback', 'manual_fallback']
step.max_retries = 5  # Increased for risky steps
```

### Fallback Chain

```
Primary Action → Retry (3x) → Fallback #1 → Fallback #2 → Manual Intervention
```

## Checkpointing & Recovery

### Automatic Checkpointing

```python
# Checkpoint every N steps
plan.create_checkpoint({
    'completed_count': 10,
    'extracted_leads': 50,
    'custom_data': {...}
})

# Checkpoints stored in plan
plan.checkpoints = [
    {
        'timestamp': '2025-12-02T10:30:00',
        'completed_steps': ['step1', 'step2', ...],
        'failed_steps': [],
        'data': {...}
    }
]
```

### Crash Recovery

```python
# After crash, resume from last checkpoint
plan = Plan.load('plan_id_12345')
if plan.status == PlanStatus.PAUSED:
    result = await executor.resume(plan.plan_id)
```

### Rollback

```python
# Rollback to specific checkpoint
await executor.rollback(plan_id, checkpoint_index=-1)  # Last checkpoint
await executor.rollback(plan_id, checkpoint_index=2)   # Specific checkpoint
```

## Multi-Agent Coordination

### Resource Allocation

```python
# Resources tracked per step
resources = [
    Resource(resource_type='browser', name='playwright', required=True),
    Resource(resource_type='api', name='openai', required=False),
    Resource(resource_type='memory', name='working_memory', required=True)
]

# Assign steps to different agents
step.assigned_to = "agent_instance_2"
```

### Parallel Execution

```python
# Automatic parallelization
parallel_groups = plan.get_parallel_steps()

# Execute groups concurrently
for group in parallel_groups:
    if len(group) > 1:
        results = await asyncio.gather(*[execute(step) for step in group])
```

### Coordination Protocols

```python
# Prevent conflicts
plan.assigned_agents = {'agent_1', 'agent_2'}

# Leader election for critical sections
if step.metadata.get('critical_section'):
    await acquire_lock(step.step_id)
```

## Plan Templates

### Built-in Templates

| Template | Category | Description |
|----------|----------|-------------|
| `sdr_lead_gen` | SDR | Generate sales leads from target sources |
| `support_triage` | Support | Classify and prioritize support tickets |
| `data_extraction` | Extraction | Extract structured data from websites |
| `monitoring` | Monitoring | Monitor systems and generate alerts |

### Creating Custom Templates

```python
# Create template from successful plan
template = agent.create_template(
    name="Custom Workflow",
    description="My custom workflow",
    category="custom",
    plan=successful_plan
)

# Template stored at memory/plan_templates/{template_id}.json

# Use template
plan = template.instantiate({
    'required_param_1': 'value1',
    'optional_param_2': 'value2'
})
```

## Integration with Eversale

### With brain_enhanced_v2.py

```python
from agent.brain_enhanced_v2 import EnhancedBrain
from agent.planning_agent import PlanningAgent

brain = EnhancedBrain()
planner = PlanningAgent(action_handler=brain.execute_action)

# Use planning agent for complex tasks
plan = await planner.plan(user_input)
evaluation = await planner.validate_plan(plan)

if evaluation['approved']:
    await planner.approve_plan(plan)
    result = await planner.execute_plan(plan)
```

### With task_decomposer.py

```python
from agent.task_decomposer import task_decomposer
from agent.planning_agent import planning_agent

# Use task_decomposer for atomic operations
atomic_steps = task_decomposer.decompose(task)

# Use planning_agent for hierarchical planning
plan = await planning_agent.plan(task, max_depth=3)
```

### With capability_router.py

```python
from agent.capability_router import route_to_capability
from agent.planning_agent import planning_agent

# Route to capability if match found
match = route_to_capability(user_input)

if match:
    # Use capability-specific template
    plan = await planning_agent.plan(
        user_input,
        context={'capability': match.capability}
    )
```

### With scheduler.py and mission_keeper.py

```python
from agent.scheduler import TaskScheduler
from agent.mission_keeper import MissionKeeper
from agent.planning_agent import planning_agent

# Create plan for scheduled task
plan = await planning_agent.plan("Weekly lead generation")

# Store in mission keeper format
mission = {
    'name': plan.name,
    'schedule': '0 9 * * 1',  # Every Monday at 9am
    'prompt': plan.description,
    'plan_id': plan.plan_id
}
```

## Storage & Persistence

### File Structure

```
memory/
├── plans/
│   ├── {plan_id}_v1.json
│   ├── {plan_id}_v2.json      # Replanned versions
│   └── ...
└── plan_templates/
    ├── sdr_lead_gen.json
    ├── support_triage.json
    └── custom_workflow.json
```

### Plan Storage Format

```json
{
  "plan_id": "abc123def456",
  "name": "Research Stripe",
  "version": 1,
  "status": "completed",
  "steps": {
    "step_0": {
      "step_id": "step_0",
      "name": "Navigate to website",
      "status": "completed",
      "result": {...}
    }
  },
  "checkpoints": [...],
  "critic_score": 0.85
}
```

## Replanning

### Dynamic Replanning on Failure

```python
# When a step fails
failed_step_id = "step_5"

# Partial replan (only affected portion)
new_plan = await agent.replan(
    original_plan,
    failed_step_id,
    partial=True
)

# Or full replan
new_plan = await agent.replan(
    original_plan,
    failed_step_id,
    partial=False
)

# Execute new plan
result = await agent.execute_plan(new_plan)
```

### Plan Versioning

```python
# Each replan creates new version
original_plan.version = 1
replanned.version = 2
replanned.parent_plan_id = original_plan.plan_id

# Load specific version
plan_v1 = Plan.load(plan_id, version=1)
plan_v2 = Plan.load(plan_id, version=2)

# Load latest
latest = Plan.load(plan_id)
```

## Performance & Metrics

### Plan Quality Metrics

```python
plan.critic_score           # Overall quality (0-1)
plan.feasibility_score      # Can it be executed? (0-1)
plan.efficiency_score       # How efficient? (0-1)
plan.risk_score             # Risk level (0-1, lower better)
```

### Execution Metrics

```python
plan.estimated_total_duration   # Estimated time (seconds)
plan.actual_total_duration      # Actual time (seconds)

progress = plan.get_progress()
# {
#   'percent': 65.0,
#   'completed': 13,
#   'failed': 1,
#   'executing': 2,
#   'pending': 4,
#   'total': 20
# }
```

### Template Metrics

```python
template.usage_count        # Times used
template.success_rate       # Success percentage
template.avg_duration       # Average execution time
```

## Advanced Features

### 1. Plan Caching

```python
# Cache plans for similar tasks
agent.plan_cache = {
    'task_hash': plan
}

# Reuse cached plan
if task_hash in agent.plan_cache:
    plan = agent.plan_cache[task_hash]
```

### 2. Resource Economy

```python
# Track resource usage
step.required_resources = [
    Resource(resource_type='browser', allocation='agent_1'),
    Resource(resource_type='memory', allocation='shared')
]
```

### 3. Coordination Protocols

```python
# Prevent conflicts between agents
plan.assigned_agents = {'agent_1', 'agent_2'}

# Critical sections
step.metadata['critical_section'] = True
```

### 4. Progress Callbacks

```python
async def progress_handler(progress):
    print(f"Progress: {progress['percent']:.0f}%")
    print(f"Completed: {progress['completed']}/{progress['total']}")

result = await executor.execute(
    plan,
    progress_callback=progress_handler
)
```

## Best Practices

### 1. Plan Design

- Keep max_depth ≤ 3 for maintainability
- Use templates for common workflows
- Add fallbacks for risky operations
- Set appropriate retry limits (3-5 for most operations)

### 2. Validation

- Always validate plans before execution
- Review critic suggestions
- Require user approval for high-risk plans
- Check feasibility score > 0.7

### 3. Execution

- Use checkpoint_interval based on task duration
- Implement progress callbacks for long-running tasks
- Handle executor exceptions gracefully
- Store plan artifacts (screenshots, logs)

### 4. Error Recovery

- Use partial replanning for isolated failures
- Implement rollback for cascading failures
- Log all errors with context
- Create templates from successful recoveries

## Example: Complete Workflow

```python
from agent.planning_agent import PlanningAgent

async def my_action_handler(action, arguments):
    """Execute actions using Playwright/other tools"""
    if action == "playwright_navigate":
        await playwright.navigate(arguments['url'])
        return {'success': True}
    # ... other actions

async def main():
    # 1. Initialize
    agent = PlanningAgent(action_handler=my_action_handler)

    # 2. Create plan
    plan = await agent.plan(
        task="Find leads from Facebook Ads Library for 'CRM software'",
        context={'max_leads': 50},
        max_depth=3,
        use_templates=True
    )

    print(f"Created plan: {agent.get_plan_summary(plan)}")

    # 3. Validate
    evaluation = await agent.validate_plan(plan)

    print(f"Validation score: {evaluation['overall_score']:.2f}")
    print(f"Suggestions: {evaluation['suggestions']}")

    if not evaluation['approved']:
        print("Plan not approved - review suggestions")
        return

    # 4. Approve
    await agent.approve_plan(plan, user_approval=True)

    # 5. Execute with progress tracking
    async def progress(p):
        print(f"Progress: {p['percent']:.0f}% ({p['completed']}/{p['total']})")

    result = await agent.execute_plan(
        plan,
        checkpoint_interval=5,
        progress_callback=progress
    )

    # 6. Handle result
    if result['success']:
        print(f"✓ Task completed in {result['duration']:.0f}s")

        # Create template for reuse
        template = agent.create_template(
            name="FB Ads Lead Gen",
            description="Generate leads from Facebook Ads Library",
            category="SDR",
            plan=plan
        )
        print(f"Created template: {template.template_id}")
    else:
        print(f"✗ Task failed: {result['failed_steps']}")

        # Replan
        new_plan = await agent.replan(plan, result['failed_steps'][0])
        print(f"Created recovery plan: {new_plan.plan_id}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

## Troubleshooting

### Plan Validation Fails

```python
# Check evaluation details
if not evaluation['approved']:
    print("Feasibility:", evaluation['feasibility']['suggestions'])
    print("Efficiency:", evaluation['efficiency']['suggestions'])
    print("Risk:", evaluation['risk']['suggestions'])
    print("Completeness:", evaluation['completeness']['suggestions'])
```

### Execution Stalls

```python
# Check for blocked steps
blocked = [s for s in plan.steps.values() if s.status == StepStatus.BLOCKED]
print(f"Blocked steps: {[s.step_id for s in blocked]}")

# Check dependencies
for step in blocked:
    print(f"{step.step_id} depends on: {step.depends_on}")
```

### High Risk Score

```python
# Review risk factors
for step in plan.steps.values():
    if 'risk_factors' in step.metadata:
        print(f"{step.name}: {step.metadata['risk_factors']}")
```

## Future Enhancements

- [ ] LLM-based decomposition for better task understanding
- [ ] Learning from execution history to improve templates
- [ ] Multi-objective optimization (time vs. quality vs. cost)
- [ ] Distributed execution across multiple machines
- [ ] Real-time plan adaptation based on environment changes
- [ ] Visual plan editor and debugger
- [ ] Integration with monitoring/alerting systems
- [ ] Plan synthesis from natural language descriptions

## References

- AgentOrchestra: Hierarchical multi-agent coordination
- Devin: Autonomous AI software engineer
- HTN Planning: Classical AI planning techniques
- ReAct: Reasoning and Acting in language models
