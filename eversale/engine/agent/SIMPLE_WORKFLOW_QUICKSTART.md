# Simple Workflow Executor - Quick Start Guide

Get started with Simple Workflow Executor in 5 minutes.

## Why Use This?

When you need **fast, reliable, predictable** browser automation WITHOUT AI overhead.

**Use Simple Workflows when:**
- Task is well-defined and repeatable
- Speed matters (workflows are 5-10x faster than AI)
- You want guaranteed behavior
- Debugging needs to be simple

**Use AI Agent when:**
- Task is novel or unexpected
- You need adaptive decision-making
- Page structure is unknown
- Complex error recovery needed

## 30-Second Example

```python
from simple_workflow_executor import SimpleWorkflowExecutor, GOOGLE_SEARCH
from mcp_tools import MCPTools

# Initialize
tools = MCPTools(headless=False)
await tools.launch()
executor = SimpleWorkflowExecutor(tools)

# Run workflow
result = await executor.execute(GOOGLE_SEARCH, {"query": "AI agents"})

# Check result
if result.success:
    print(f"Success! Got: {result.extracted_data[:100]}")
else:
    print(f"Failed: {result.error}")

await tools.close()
```

## Pre-built Workflows

Just import and use:

```python
from simple_workflow_executor import (
    GOOGLE_SEARCH,      # Search Google
    YOUTUBE_SEARCH,     # Search YouTube
    AMAZON_SEARCH,      # Search Amazon
    SIMPLE_NAVIGATE,    # Navigate to URL
    GITHUB_REPO_BROWSE, # Browse GitHub repo
    REDDIT_BROWSE,      # Browse subreddit
    HACKERNEWS_BROWSE,  # Browse HN
)

# Use any of them
result = await executor.execute(YOUTUBE_SEARCH, {"query": "python"})
result = await executor.execute(SIMPLE_NAVIGATE, {"url": "https://example.com"})
result = await executor.execute(GITHUB_REPO_BROWSE, {
    "owner": "microsoft",
    "repo": "playwright"
})
```

## Create Custom Workflow

```python
from simple_workflow_executor import SimpleWorkflow, WorkflowStep

my_workflow = SimpleWorkflow(
    name="my_task",
    description="What it does",
    steps=[
        WorkflowStep("navigate", "https://example.com"),
        WorkflowStep("type", "input[name='search']", "{query}"),
        WorkflowStep("press", value="Enter"),
        WorkflowStep("wait", value="2"),
        WorkflowStep("extract"),
    ]
)

result = await executor.execute(my_workflow, {"query": "test"})
```

## Available Actions

| Action | Example |
|--------|---------|
| Navigate | `WorkflowStep("navigate", "https://example.com")` |
| Click | `WorkflowStep("click", "button.submit")` |
| Type | `WorkflowStep("type", "input[name='q']", "text")` |
| Press Key | `WorkflowStep("press", value="Enter")` |
| Wait | `WorkflowStep("wait", value="2")` |
| Extract | `WorkflowStep("extract")` |
| Screenshot | `WorkflowStep("screenshot")` |
| Scroll | `WorkflowStep("scroll", value="down")` |

## Optional Steps

Make steps optional so workflow continues on failure:

```python
workflow = SimpleWorkflow(
    name="robust",
    steps=[
        WorkflowStep("navigate", "https://example.com"),
        # Optional - won't fail workflow if popup doesn't exist
        WorkflowStep("click", "button.close-popup", required=False),
        # Required - workflow stops if this fails
        WorkflowStep("type", "input", "text"),
    ]
)
```

## Workflow Registry

Get workflows by name:

```python
from simple_workflow_executor import get_workflow, list_workflows

# List all
print(list_workflows())
# ['google_search', 'youtube_search', 'simple_navigate', ...]

# Get by name
workflow = get_workflow("google_search")
result = await executor.execute(workflow, {"query": "test"})
```

## Error Handling

Check success and handle failures:

```python
result = await executor.execute(workflow, variables)

if result.success:
    print(f"Completed {result.completed_steps} steps")
    print(f"Time: {result.total_time_ms}ms")
    if result.extracted_data:
        print(f"Data: {result.extracted_data}")
else:
    print(f"Failed at step {result.failed_step}")
    print(f"Error: {result.error}")
    print(f"Only {result.completed_steps}/{result.total_steps} completed")
```

## Common Patterns

### Pattern 1: Search

```python
result = await executor.execute(GOOGLE_SEARCH, {"query": "your search"})
if result.success:
    data = result.extracted_data
```

### Pattern 2: Navigate and Extract

```python
result = await executor.execute(SIMPLE_NAVIGATE, {"url": "https://example.com"})
if result.success:
    content = result.extracted_data
```

### Pattern 3: Form Fill

```python
from simple_workflow_executor import SIMPLE_FORM_FILL

result = await executor.execute(SIMPLE_FORM_FILL, {
    "form_url": "https://example.com/contact",
    "name": "John Doe",
    "email": "john@example.com"
})
```

### Pattern 4: Multi-Step Task

```python
workflow = SimpleWorkflow(
    name="multi_step",
    steps=[
        WorkflowStep("navigate", "https://site.com/login"),
        WorkflowStep("type", "input[name='user']", "{username}"),
        WorkflowStep("type", "input[name='pass']", "{password}"),
        WorkflowStep("click", "button[type='submit']"),
        WorkflowStep("wait", value="3"),
        WorkflowStep("navigate", "https://site.com/dashboard"),
        WorkflowStep("extract"),
    ]
)

result = await executor.execute(workflow, {
    "username": "user@example.com",
    "password": "secret123"
})
```

### Pattern 5: Try Workflow, Fall Back to AI

```python
# Fast path - try workflow first
result = await executor.execute(GOOGLE_SEARCH, {"query": query})

if result.success:
    return result.extracted_data
else:
    # Slow path - use AI agent
    return await ai_agent.search(query)
```

## Testing

Test with mock tools:

```python
# See test_simple_workflow.py for examples
pytest test_simple_workflow.py -v
```

Or test live:

```python
# See simple_workflow_example.py for examples
python simple_workflow_example.py
```

## Performance

Typical execution times:

| Workflow | Time |
|----------|------|
| Simple navigate | 2-3s |
| Google search | 4-6s |
| Form fill | 3-5s |
| Multi-step (5 steps) | 8-12s |

Compare to AI agent:
- Simple workflow: 2-10s
- AI agent: 10-60s

**Speedup: 5-10x faster**

## Debugging

Each step shows status:

```
Step 1/5: navigate
Success (234ms)

Step 2/5: type
Success (156ms)

Step 3/5: click
Step failed (required): Element not found
```

Inspect results:

```python
for i, step_result in enumerate(result.step_results, 1):
    print(f"Step {i}: {step_result.success}")
    if not step_result.success:
        print(f"  Error: {step_result.error}")
    print(f"  Time: {step_result.time_ms}ms")
```

## Integration

Use with existing systems:

```python
# In your agent code
from simple_workflow_executor import SimpleWorkflowExecutor, get_workflow

class MyAgent:
    def __init__(self):
        self.workflow_executor = SimpleWorkflowExecutor(self.tools)

    async def execute_task(self, task: str):
        # Try known workflow first
        workflow = self._match_workflow(task)
        if workflow:
            result = await self.workflow_executor.execute(workflow, vars)
            if result.success:
                return result.extracted_data

        # Fall back to AI
        return await self.ai_execute(task)
```

## Next Steps

- **Read full docs:** `SIMPLE_WORKFLOW_README.md`
- **See examples:** `simple_workflow_example.py`
- **Check integration:** `simple_workflow_integration_example.py`
- **Run tests:** `pytest test_simple_workflow.py -v`

## Files

| File | Purpose |
|------|---------|
| `simple_workflow_executor.py` | Main module |
| `simple_workflow_example.py` | Basic examples |
| `simple_workflow_integration_example.py` | Integration patterns |
| `test_simple_workflow.py` | Unit tests |
| `SIMPLE_WORKFLOW_README.md` | Full documentation |
| `SIMPLE_WORKFLOW_QUICKSTART.md` | This file |

## Key Takeaways

1. **Simple workflows are FAST** - 5-10x faster than AI
2. **Pre-built workflows available** - Common tasks ready to use
3. **Easy to create custom** - Just define steps
4. **Optional steps** - Continue on non-critical failures
5. **Variable substitution** - Reuse workflows with different data
6. **Clear error handling** - Know exactly what failed
7. **Integration ready** - Works with existing agent systems

**Make it work first. Make it work always. Workflows earn their keep.**
