# Planning Agent Integration Guide

This guide shows how the HTN Planning Agent integrates with Eversale's existing systems.

## System Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                          User Input                                   │
└────────────────────────────┬─────────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    Capability Router                                  │
│  (capability_router.py)                                              │
│  - Detects if task matches capability A-O                           │
│  - Extracts parameters                                               │
└────────────────┬────────────────────────┬─────────────────────────────┘
                 │                        │
        Capability Match              No Match
                 │                        │
                 ▼                        ▼
┌─────────────────────────────┐  ┌──────────────────────────────────┐
│   Capability Executor       │  │    Planning Agent                │
│   (capabilities.py)         │  │    (planning_agent.py)           │
│   - Execute A-O workflows   │  │    - Hierarchical planning       │
└─────────────────────────────┘  │    - Task decomposition          │
                                  │    - Validation & execution      │
                                  └──────────┬───────────────────────┘
                                             │
                        ┌────────────────────┼─────────────────────┐
                        │                    │                     │
                        ▼                    ▼                     ▼
          ┌──────────────────────┐  ┌────────────────┐  ┌─────────────────┐
          │  Task Decomposer     │  │  Plan Critic   │  │  Plan Executor  │
          │ (task_decomposer.py) │  │  - Validate    │  │  - Execute      │
          │ - Atomic operations  │  │  - Score       │  │  - Checkpoint   │
          └──────────────────────┘  │  - Suggest     │  │  - Rollback     │
                                     └────────────────┘  └────────┬────────┘
                                                                  │
                                                                  ▼
                        ┌─────────────────────────────────────────────────┐
                        │           Action Handler                         │
                        │  - brain_enhanced_v2.py (main execution)        │
                        │  - playwright_direct.py (browser automation)    │
                        │  - business_tools.py (specialized tools)        │
                        └─────────────────────────────────────────────────┘
                                                                  │
                        ┌─────────────────────────────────────────┴───┐
                        │                                              │
                        ▼                                              ▼
          ┌──────────────────────────┐                  ┌────────────────────────┐
          │   Scheduler              │                  │   Mission Keeper       │
          │   (scheduler.py)         │                  │   (mission_keeper.py)  │
          │   - Scheduled execution  │                  │   - Persistent tasks   │
          └──────────────────────────┘                  └────────────────────────┘
```

## Integration Points

### 1. Capability Router → Planning Agent

When capability router doesn't match, task goes to planning agent:

```python
from agent.capability_router import route_to_capability
from agent.planning_agent import planning_agent

# Try capability routing first
match = route_to_capability(user_input)

if match:
    # Use capability executor
    result = await execute_capability(match)
else:
    # Use planning agent for complex/novel tasks
    plan = await planning_agent.plan(user_input, max_depth=3)
    evaluation = await planning_agent.validate_plan(plan)

    if evaluation['approved']:
        await planning_agent.approve_plan(plan)
        result = await planning_agent.execute_plan(plan)
```

### 2. Planning Agent → Task Decomposer

Planning agent uses task decomposer for atomic operation breakdown:

```python
from agent.task_decomposer import task_decomposer
from agent.planning_agent import PlanningAgent

class EnhancedPlanningAgent(PlanningAgent):
    async def _decompose_to_atomic(self, task: str) -> List[PlanStep]:
        """Use task_decomposer for atomic operations"""

        # Get atomic operations
        atomic_ops = task_decomposer.decompose(task)

        # Convert to plan steps
        steps = []
        for i, op in enumerate(atomic_ops):
            step = PlanStep(
                step_id=f"atomic_{i}",
                name=op.get('description', 'Unknown'),
                task_type=TaskType.PRIMITIVE,
                action=op['operations'][0]['function'],
                arguments=op['operations'][0].get('arguments', {}),
                estimated_duration=op.get('estimated_duration', 10.0)
            )
            steps.append(step)

        return steps
```

### 3. Planning Agent → Brain Enhanced V2

Brain acts as action handler for plan execution:

```python
from agent.brain_enhanced_v2 import EnhancedBrain
from agent.planning_agent import PlanningAgent

brain = EnhancedBrain()

async def brain_action_handler(action: str, arguments: dict):
    """Execute actions using brain"""

    # Map plan actions to brain methods
    if action == 'playwright_navigate':
        return await brain.playwright_navigate(**arguments)
    elif action == 'playwright_extract':
        return await brain.playwright_extract(**arguments)
    elif action == 'research':
        return await brain.research(**arguments)
    # ... other actions

    # Fallback: use brain's general execution
    return await brain.execute_action(action, arguments)

# Create planning agent with brain as executor
planner = PlanningAgent(action_handler=brain_action_handler)

# Now plans execute through brain
plan = await planner.plan("Research Stripe")
await planner.approve_plan(plan, user_approval=False)
result = await planner.execute_plan(plan)
```

### 4. Planning Agent → Scheduler

Schedule plans for recurring execution:

```python
from agent.scheduler import TaskScheduler
from agent.planning_agent import planning_agent

scheduler = TaskScheduler(agent=brain)

# Create plan
plan = await planning_agent.plan(
    task="Weekly lead generation from Facebook Ads",
    max_depth=3
)

# Validate and approve
evaluation = await planning_agent.validate_plan(plan)
if evaluation['approved']:
    await planning_agent.approve_plan(plan)

    # Schedule execution
    scheduler.add_task(
        name=f"plan_{plan.plan_id}",
        cron="0 9 * * 1",  # Every Monday at 9am
        prompt=f"Execute plan {plan.plan_id}"
    )

    # Start scheduler
    await scheduler.start()
```

### 5. Planning Agent → Mission Keeper

Persist critical plans as missions:

```python
from agent.mission_keeper import MissionKeeper
from agent.planning_agent import planning_agent

# Create important plan
plan = await planning_agent.plan(
    task="Monitor inbox and respond to urgent emails",
    max_depth=3
)

# Add to mission keeper
mission = {
    'name': f'mission_{plan.plan_id}',
    'schedule': '0 * * * *',  # Every hour
    'prompt': plan.description,
    'metadata': {
        'plan_id': plan.plan_id,
        'version': plan.version,
        'critical': True
    }
}

# Mission keeper ensures it survives restarts
keeper = MissionKeeper(scheduler)
keeper.missions.append(mission)
keeper._write_missions()
```

## Complete Integration Example

```python
#!/usr/bin/env python3
"""
Complete Eversale integration with Planning Agent
"""

import asyncio
from agent.capability_router import route_to_capability
from agent.planning_agent import PlanningAgent
from agent.task_decomposer import task_decomposer
from agent.brain_enhanced_v2 import EnhancedBrain
from agent.scheduler import TaskScheduler
from agent.mission_keeper import MissionKeeper

class EversaleWithPlanning:
    """Eversale with integrated planning capabilities"""

    def __init__(self):
        self.brain = EnhancedBrain()
        self.planner = PlanningAgent(action_handler=self._brain_action_handler)
        self.scheduler = TaskScheduler(agent=self)
        self.mission_keeper = MissionKeeper(self.scheduler)

    async def _brain_action_handler(self, action: str, arguments: dict):
        """Route plan actions to brain methods"""

        # Map actions
        action_map = {
            'navigate': self.brain.playwright_navigate,
            'extract': self.brain.playwright_extract,
            'search': self.brain.search,
            'research': self.brain.research,
            'save_results': self.brain.save_results,
        }

        if action in action_map:
            return await action_map[action](**arguments)

        # Generic execution
        return await self.brain.execute_action(action, arguments)

    async def run(self, user_input: str) -> dict:
        """
        Main execution pipeline:
        1. Try capability routing
        2. If no match, use planning agent
        3. Execute plan
        4. Return results
        """

        # Step 1: Capability routing
        match = route_to_capability(user_input)

        if match:
            # Use capability executor
            return await self._execute_capability(match)

        # Step 2: Planning agent
        plan = await self.planner.plan(
            task=user_input,
            context={},
            max_depth=3,
            use_templates=True
        )

        # Step 3: Validate
        evaluation = await self.planner.validate_plan(plan)

        if not evaluation['approved']:
            # Plan failed validation - try simpler approach
            plan = await self.planner.plan(
                task=user_input,
                max_depth=2,  # Reduce complexity
                use_templates=False
            )
            evaluation = await self.planner.validate_plan(plan)

        if not evaluation['approved']:
            return {
                'success': False,
                'error': 'Could not create valid plan',
                'suggestions': evaluation['suggestions']
            }

        # Step 4: Approve and execute
        await self.planner.approve_plan(plan, user_approval=False)

        result = await self.planner.execute_plan(
            plan,
            checkpoint_interval=5,
            progress_callback=self._progress_callback
        )

        # Step 5: Learn from execution
        if result['success']:
            # Create template for future use
            if plan.critic_score >= 0.8:
                template = self.planner.create_template(
                    name=f"Template: {plan.name}",
                    description=plan.description,
                    category="learned",
                    plan=plan
                )

        return {
            'success': result['success'],
            'plan_id': plan.plan_id,
            'evaluation': evaluation,
            'execution': result
        }

    async def _execute_capability(self, match):
        """Execute using capability executor"""
        # Use existing capability system
        from agent.capabilities import execute_capability
        return await execute_capability(
            match.capability,
            match.extracted_params
        )

    async def _progress_callback(self, progress):
        """Handle execution progress"""
        print(f"Progress: {progress['percent']:.0f}% "
              f"({progress['completed']}/{progress['total']})")

    async def schedule_task(self, task: str, schedule: str):
        """Schedule task for recurring execution"""

        # Create plan
        plan = await self.planner.plan(task, max_depth=3)

        # Validate
        evaluation = await self.planner.validate_plan(plan)

        if not evaluation['approved']:
            raise ValueError("Plan validation failed")

        await self.planner.approve_plan(plan)

        # Add to scheduler
        self.scheduler.add_task(
            name=f"scheduled_{plan.plan_id}",
            cron=self.scheduler.parse_schedule(schedule),
            prompt=f"Execute plan {plan.plan_id}"
        )

        return plan

    async def add_mission(self, task: str, schedule: str):
        """Add critical mission that persists"""

        plan = await self.schedule_task(task, schedule)

        # Add to mission keeper
        mission = {
            'name': f'mission_{plan.plan_id}',
            'schedule': self.scheduler.parse_schedule(schedule),
            'prompt': plan.description,
            'metadata': {
                'plan_id': plan.plan_id,
                'critical': True
            }
        }

        self.mission_keeper.missions.append(mission)
        self.mission_keeper._write_missions()

        return mission


# Usage
async def main():
    eversale = EversaleWithPlanning()

    # Example 1: One-shot task
    result = await eversale.run(
        "Research Stripe and extract contact information"
    )

    if result['success']:
        print(f"✓ Task completed: {result['plan_id']}")
    else:
        print(f"✗ Task failed: {result['error']}")

    # Example 2: Scheduled task
    plan = await eversale.schedule_task(
        task="Generate leads from Facebook Ads Library for 'CRM software'",
        schedule="every monday at 9am"
    )
    print(f"✓ Scheduled task: {plan.plan_id}")

    # Example 3: Critical mission
    mission = await eversale.add_mission(
        task="Monitor inbox and respond to urgent emails",
        schedule="every hour"
    )
    print(f"✓ Added mission: {mission['name']}")

    # Start scheduler
    await eversale.scheduler.start()


if __name__ == "__main__":
    asyncio.run(main())
```

## Action Mapping

Map plan actions to Eversale functions:

| Plan Action | Eversale Function | Module |
|-------------|-------------------|--------|
| `navigate` | `playwright_navigate` | playwright_direct.py |
| `click` | `playwright_click` | playwright_direct.py |
| `fill` | `playwright_fill` | playwright_direct.py |
| `extract` | `playwright_extract_contacts` | playwright_direct.py |
| `extract_fb_ads` | `playwright_extract_fb_ads` | playwright_direct.py |
| `screenshot` | `playwright_screenshot` | playwright_direct.py |
| `research` | `research_company` | business_tools.py |
| `clean_data` | `clean_spreadsheet` | business_tools.py |
| `categorize` | `categorize_transactions` | business_tools.py |
| `save_results` | `save_to_csv` | output_generators.py |

## Template Integration

Use Eversale's workflow knowledge to create templates:

```python
# SDR Lead Generation
sdr_template = PlanTemplate(
    template_id="sdr_fb_ads",
    name="Facebook Ads Lead Generation",
    category="SDR",
    required_params=['keyword', 'max_results'],
    step_templates=[
        {
            'name': "Navigate to FB Ads Library",
            'action': 'playwright_navigate',
            'arguments': {'url': 'https://facebook.com/ads/library'}
        },
        {
            'name': "Search for keyword",
            'action': 'playwright_fill_and_submit',
            'arguments': {'keyword': '${keyword}'}
        },
        {
            'name': "Extract advertisers",
            'action': 'playwright_extract_fb_ads',
            'arguments': {'max_results': '${max_results}'}
        },
        {
            'name': "Visit advertiser websites",
            'action': 'playwright_batch_extract',
            'arguments': {'urls': 'from_previous_step'}
        },
        {
            'name': "Save leads",
            'action': 'save_to_csv',
            'arguments': {'filename': 'leads.csv'}
        }
    ]
)
```

## Error Handling

Integrate planning agent's error recovery:

```python
async def robust_execution(user_input: str):
    """Execute with full error recovery"""

    eversale = EversaleWithPlanning()

    try:
        # Create and execute plan
        result = await eversale.run(user_input)

        if result['success']:
            return result

        # Plan failed - try replan
        if 'plan_id' in result:
            plan = Plan.load(result['plan_id'])
            failed_steps = result['execution']['failed_steps']

            if failed_steps:
                # Replan for first failure
                new_plan = await eversale.planner.replan(
                    original_plan=plan,
                    failed_step_id=failed_steps[0],
                    partial=True
                )

                # Execute recovery plan
                await eversale.planner.approve_plan(new_plan)
                result = await eversale.planner.execute_plan(new_plan)

                return result

    except Exception as e:
        # Last resort: use brain's self-healing
        return await eversale.brain.self_heal_and_retry(user_input)
```

## Benefits of Integration

### 1. Hierarchical Planning
- Complex tasks broken into manageable sub-goals
- Better than flat task lists
- Easier to reason about and debug

### 2. Validation Before Execution
- Catch impossible plans early
- Get suggestions for improvement
- Reduce wasted execution time

### 3. Reusable Templates
- Learn from successful executions
- Instant planning for common tasks
- Consistent quality

### 4. Better Coordination
- Multiple agents can execute different parts
- Parallel execution for speed
- Resource allocation prevents conflicts

### 5. Robust Recovery
- Automatic checkpointing
- Rollback on failure
- Replanning for recovery

### 6. Persistence
- Plans survive crashes
- Resume from checkpoints
- Mission-critical tasks guaranteed

## Migration Path

### Phase 1: Parallel Operation
- Planning agent runs alongside existing system
- Use for new/complex tasks only
- Existing workflows unchanged

### Phase 2: Template Creation
- Convert successful plans to templates
- Build template library
- Gradually use templates for common tasks

### Phase 3: Full Integration
- Planning agent as default for all tasks
- Capability router feeds into planning
- Brain becomes action executor

### Phase 4: Learning & Optimization
- Analyze plan execution metrics
- Improve templates based on data
- Auto-generate templates from patterns

## Testing Integration

```python
import pytest
from agent.planning_agent import PlanningAgent
from agent.brain_enhanced_v2 import EnhancedBrain

@pytest.mark.asyncio
async def test_planning_agent_integration():
    """Test planning agent with brain"""

    brain = EnhancedBrain()
    planner = PlanningAgent(action_handler=brain.execute_action)

    # Create plan
    plan = await planner.plan("Research test company", max_depth=2)

    assert len(plan.steps) > 0
    assert plan.status == PlanStatus.DRAFT

    # Validate
    evaluation = await planner.validate_plan(plan)

    assert evaluation['overall_score'] > 0
    assert 'suggestions' in evaluation

    # Approve and execute (with mock)
    await planner.approve_plan(plan, user_approval=False)
    result = await planner.execute_plan(plan)

    assert 'success' in result
    assert 'completed_steps' in result
```

## Monitoring & Metrics

Track planning agent performance:

```python
class PlanningMetrics:
    """Collect metrics on planning performance"""

    def __init__(self):
        self.plans_created = 0
        self.plans_approved = 0
        self.plans_executed = 0
        self.plans_failed = 0
        self.total_duration = 0
        self.avg_critic_score = 0

    async def track_plan(self, plan: Plan, result: dict):
        """Track plan execution"""

        self.plans_created += 1

        if plan.status == PlanStatus.APPROVED:
            self.plans_approved += 1

        if result.get('success'):
            self.plans_executed += 1
            self.total_duration += result.get('duration', 0)
        else:
            self.plans_failed += 1

        # Update average score
        self.avg_critic_score = (
            (self.avg_critic_score * (self.plans_created - 1) + plan.critic_score)
            / self.plans_created
        )

    def report(self):
        """Generate metrics report"""
        return {
            'plans_created': self.plans_created,
            'approval_rate': self.plans_approved / self.plans_created if self.plans_created else 0,
            'success_rate': self.plans_executed / self.plans_approved if self.plans_approved else 0,
            'avg_duration': self.total_duration / self.plans_executed if self.plans_executed else 0,
            'avg_quality': self.avg_critic_score
        }
```

## Future Enhancements

- LLM-powered task analysis for better decomposition
- Visual plan editor for debugging
- Multi-objective optimization (time vs quality vs cost)
- Distributed execution across machines
- Real-time plan adaptation
- Integration with Eversale's training system
