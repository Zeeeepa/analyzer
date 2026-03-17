# Multi-Agent System Quick Start

Get started with the Multi-Agent Coordination system in 5 minutes.

## Installation

No additional dependencies required beyond Eversale's base requirements.

## Basic Usage

### 1. Simple Task Execution

Execute a single task with auto-managed swarm:

```python
from agent.multi_agent import execute_task_with_swarm

# Simplest usage - everything is automatic
result = await execute_task_with_swarm("Research Stripe payment API")
print(result)
```

### 2. Create and Manage Swarm

Create a persistent swarm for multiple tasks:

```python
from agent.multi_agent import AgentOrchestrator, TaskPriority

# Create orchestrator
orchestrator = AgentOrchestrator(
    orchestrator_id="my_swarm",
    max_agents=5
)

# Start the swarm
await orchestrator.start()

# Submit tasks
task1 = await orchestrator.submit_task(
    "Research Stripe",
    priority=TaskPriority.HIGH
)

task2 = await orchestrator.submit_task(
    "Extract contact information"
)

# Get results
result1 = await orchestrator.get_task_result(task1, timeout=60)
result2 = await orchestrator.get_task_result(task2, timeout=60)

print(f"Task 1: {result1}")
print(f"Task 2: {result2}")

# Check status
status = orchestrator.get_status()
print(f"Agents: {status['total_agents']}")
print(f"Tasks completed: {status['total_tasks_processed']}")

# Stop when done
await orchestrator.stop()
```

### 3. Parallel Processing

Process multiple items in parallel:

```python
from agent.multi_agent import AgentOrchestrator, AgentRole

orchestrator = AgentOrchestrator(max_agents=10)
await orchestrator.start()

# Submit many tasks
companies = ["Stripe", "Shopify", "Square", "PayPal", "Braintree"]

task_ids = []
for company in companies:
    task_id = await orchestrator.submit_task(
        f"Research {company}",
        required_role=AgentRole.RESEARCHER
    )
    task_ids.append(task_id)

# Collect results
results = []
for task_id in task_ids:
    result = await orchestrator.get_task_result(task_id, timeout=60)
    results.append(result)

print(f"Processed {len(results)} companies")

await orchestrator.stop()
```

### 4. Complex Workflow with Planning

Use hierarchical planning for complex tasks:

```python
from agent.multi_agent_integration import CoordinatedOrchestrator

orchestrator = CoordinatedOrchestrator(max_agents=5)
await orchestrator.start()

# Execute complex workflow
# PlannerAgent creates plan, ExecutorAgent executes it
result = await orchestrator.execute_complex_workflow(
    workflow_description="Build lead list: find top 10 SaaS companies in SF, extract contacts, validate emails",
    use_planning=True  # Uses planning_agent.py
)

print(f"Workflow status: {result['status']}")
print(f"Plan: {result['results']['plan']}")
print(f"Execution: {result['results']['execution']}")

await orchestrator.stop()
```

### 5. Custom Agent

Create a specialized agent for your use case:

```python
from agent.multi_agent import AgentWorker, AgentRole, AgentTask

class MyCustomAgent(AgentWorker):
    def __init__(self, agent_id, broker, shared_memory):
        super().__init__(agent_id, AgentRole.EXECUTOR, broker, shared_memory)
        self.capabilities = {"my_special_skill"}

    async def execute_task(self, task: AgentTask):
        # Your custom logic here
        print(f"Executing: {task.description}")

        # Do work
        await asyncio.sleep(1)

        # Return result
        return {
            "status": "success",
            "result": "Custom work completed",
            "data": {"foo": "bar"}
        }

# Register and use
orchestrator = AgentOrchestrator(max_agents=3)
orchestrator.agent_types[AgentRole.EXECUTOR] = MyCustomAgent

await orchestrator.start()

# Will use your custom agent
task_id = await orchestrator.submit_task(
    "Custom task",
    required_role=AgentRole.EXECUTOR
)

result = await orchestrator.get_task_result(task_id, timeout=30)
print(result)

await orchestrator.stop()
```

## Common Patterns

### Pattern: Batch Processing

```python
async def batch_process(items, batch_size=10):
    orchestrator = AgentOrchestrator(max_agents=batch_size)
    await orchestrator.start()

    try:
        # Submit all items
        task_ids = [
            await orchestrator.submit_task(f"Process {item}")
            for item in items
        ]

        # Collect results
        results = [
            await orchestrator.get_task_result(tid, timeout=60)
            for tid in task_ids
        ]

        return results
    finally:
        await orchestrator.stop()

# Use it
items = ["item1", "item2", "item3", ..., "item100"]
results = await batch_process(items, batch_size=20)
```

### Pattern: Pipeline Processing

```python
async def pipeline(data):
    orchestrator = AgentOrchestrator(max_agents=5)
    await orchestrator.start()

    try:
        # Stage 1: Research
        research_task = await orchestrator.submit_task(
            f"Research {data}",
            required_role=AgentRole.RESEARCHER
        )
        research_result = await orchestrator.get_task_result(research_task)

        # Stage 2: Extract (depends on research)
        extract_task = await orchestrator.submit_task(
            f"Extract contacts from research",
            required_role=AgentRole.EXTRACTOR,
            metadata={"research_data": research_result}
        )
        extract_result = await orchestrator.get_task_result(extract_task)

        # Stage 3: Validate (depends on extraction)
        validate_task = await orchestrator.submit_task(
            f"Validate extracted data",
            required_role=AgentRole.VALIDATOR,
            metadata={"extracted_data": extract_result}
        )
        validate_result = await orchestrator.get_task_result(validate_task)

        return validate_result
    finally:
        await orchestrator.stop()
```

### Pattern: Distributed Processing

```python
# Multiple orchestrators coordinating
async def distributed_processing():
    # Orchestrator 1: Research
    orch1 = AgentOrchestrator(orchestrator_id="research_team", max_agents=5)
    await orch1.start()

    # Orchestrator 2: Extraction
    orch2 = AgentOrchestrator(orchestrator_id="extraction_team", max_agents=5)
    await orch2.start()

    try:
        # They share memory
        shared = orch1.shared_memory

        # Orchestrator 1 does research
        task1 = await orch1.submit_task("Research companies")
        result1 = await orch1.get_task_result(task1)
        await shared.set("research_complete", result1)

        # Orchestrator 2 waits and extracts
        research_data, _ = await shared.get("research_complete")
        task2 = await orch2.submit_task(
            "Extract contacts",
            metadata={"research": research_data}
        )
        result2 = await orch2.get_task_result(task2)

        return result2
    finally:
        await orch1.stop()
        await orch2.stop()
```

## Monitoring

### Real-time Status

```python
# Get status
status = orchestrator.get_status()

print(f"""
Orchestrator Status:
- Total agents: {status['total_agents']}
- Idle agents: {status['agents_by_status']['idle']}
- Busy agents: {status['agents_by_status']['busy']}
- Tasks processed: {status['total_tasks_processed']}
- Tasks failed: {status['total_tasks_failed']}
""")

# Per-agent details
for agent in status['agents']:
    print(f"{agent['agent_id']} ({agent['role']}): {agent['status']}")
    print(f"  Completed: {agent['metrics']['tasks_completed']}")
    print(f"  Success rate: {agent['metrics']['success_rate']:.1%}")
```

### Queue Monitoring

```python
queue_sizes = orchestrator.task_distributor.get_queue_sizes()
print("Task queues:")
for priority, size in queue_sizes.items():
    print(f"  {priority}: {size} tasks")
```

## Error Handling

### Handling Task Failures

```python
task_id = await orchestrator.submit_task("Risky task")

try:
    result = await orchestrator.get_task_result(task_id, timeout=60)
    print(f"Success: {result}")
except TimeoutError:
    print("Task timed out")
    # Check status
    task = await orchestrator.task_distributor.get_task_status(task_id)
    print(f"Task status: {task.status}")
except Exception as e:
    print(f"Task failed: {e}")
    # Task failed, get error details
    task = await orchestrator.task_distributor.get_task_status(task_id)
    print(f"Error: {task.error}")
    print(f"Retries: {task.retry_count}")
```

### Graceful Shutdown

```python
orchestrator = AgentOrchestrator(max_agents=5)

try:
    await orchestrator.start()

    # Your work here
    ...

except KeyboardInterrupt:
    print("Interrupted, shutting down...")
except Exception as e:
    print(f"Error: {e}")
finally:
    # Always cleanup
    await orchestrator.stop()
    print("Cleanup complete")
```

## Performance Tips

1. **Set appropriate max_agents** - More isn't always better
   ```python
   # For I/O bound tasks (web scraping)
   orchestrator = AgentOrchestrator(max_agents=20)

   # For CPU bound tasks
   orchestrator = AgentOrchestrator(max_agents=4)
   ```

2. **Use priorities** - Critical tasks first
   ```python
   await orchestrator.submit_task(
       "Urgent task",
       priority=TaskPriority.CRITICAL  # Executes immediately
   )
   ```

3. **Specify roles** - Route to specialized agents
   ```python
   await orchestrator.submit_task(
       "Research task",
       required_role=AgentRole.RESEARCHER  # Only researcher agents
   )
   ```

4. **Enable auto-scaling** - For variable workloads
   ```python
   orchestrator = AgentOrchestrator(
       min_agents=2,
       max_agents=20,
       auto_scale=True  # Scales based on queue
   )
   ```

5. **Batch similar tasks** - Reduce overhead
   ```python
   # Better: Submit all at once
   task_ids = [
       await orchestrator.submit_task(f"Task {i}")
       for i in range(100)
   ]

   # Then collect results
   results = [
       await orchestrator.get_task_result(tid)
       for tid in task_ids
   ]
   ```

## Testing

Run your implementation:

```python
# Test basic functionality
python agent/multi_agent.py

# Run integration examples
python agent/multi_agent_integration.py

# Run test suite
python agent/test_multi_agent.py
```

## Next Steps

- Read the full documentation: `MULTI_AGENT_README.md`
- Study integration examples: `agent/multi_agent_integration.py`
- Look at test suite for patterns: `agent/test_multi_agent.py`
- Create custom agents for your use cases
- Integrate with existing Eversale components

## Getting Help

Common issues:

**Q: Tasks not executing?**
A: Check if agents are idle: `orchestrator.get_status()['agents_by_status']['idle']`

**Q: Memory usage high?**
A: Lower `max_agents` or disable auto-scaling

**Q: Tasks timing out?**
A: Increase timeout or check agent implementation

**Q: How to debug?**
A: Enable logging:
```python
from loguru import logger
logger.add("multi_agent.log", level="DEBUG")
```

## Examples Repository

Find more examples in:
- `agent/multi_agent_integration.py` - Integration patterns
- `agent/test_multi_agent.py` - Usage patterns
- `MULTI_AGENT_README.md` - Complete documentation
