# Simple Workflow Executor

A **SIMPLE, RELIABLE** way to execute common browser workflows without complex cascading recovery or AI dependency.

## Philosophy

When complex systems fail, you need something SIMPLE and RELIABLE. This is it.

**Core Principles:**
- NO complex recovery - if step fails, return error or skip if optional
- NO AI dependency - purely deterministic
- NO cascading logic - linear execution
- CLEAR status - show each step as it runs
- FAST timeout - 10s per step max

## When to Use This

Use Simple Workflow Executor when you want:
- **Predictable execution** - Same inputs = same outputs
- **Fast execution** - No AI overhead, just browser actions
- **Clear debugging** - See exactly which step failed
- **Reliable automation** - For common, well-defined tasks

Use AI agent when you need:
- Dynamic decision making
- Complex error recovery
- Novel/unexpected scenarios
- Natural language understanding

## Quick Start

```python
from simple_workflow_executor import (
    SimpleWorkflowExecutor,
    GOOGLE_SEARCH,
    SIMPLE_NAVIGATE,
)
from mcp_tools import MCPTools

# Initialize
tools = MCPTools(headless=False)
await tools.launch()
executor = SimpleWorkflowExecutor(tools)

# Run pre-built workflow
result = await executor.execute(GOOGLE_SEARCH, {"query": "AI agents"})

if result.success:
    print(f"Success! Completed {result.completed_steps} steps in {result.total_time_ms}ms")
else:
    print(f"Failed at step {result.failed_step}: {result.error}")

await tools.close()
```

## Pre-built Workflows

The module includes common workflows ready to use:

| Workflow | Description | Variables |
|----------|-------------|-----------|
| `GOOGLE_SEARCH` | Search Google | `{query}` |
| `YOUTUBE_SEARCH` | Search YouTube | `{query}` |
| `AMAZON_SEARCH` | Search Amazon products | `{query}` |
| `SIMPLE_NAVIGATE` | Navigate and extract | `{url}` |
| `GITHUB_REPO_BROWSE` | Browse GitHub repo | `{owner}`, `{repo}` |
| `REDDIT_BROWSE` | Browse subreddit | `{subreddit}` |
| `HACKERNEWS_BROWSE` | Browse HackerNews | - |
| `LINKEDIN_LOGIN` | Log in to LinkedIn | `{email}`, `{password}` |
| `TWITTER_POST` | Post a tweet | `{tweet_text}` |
| `SIMPLE_FORM_FILL` | Fill simple form | `{form_url}`, `{name}`, `{email}` |

### Using Pre-built Workflows

```python
# Method 1: Direct import
from simple_workflow_executor import GOOGLE_SEARCH

result = await executor.execute(GOOGLE_SEARCH, {"query": "python"})

# Method 2: Registry
from simple_workflow_executor import get_workflow, list_workflows

# List all workflows
for name in list_workflows():
    print(f"- {name}")

# Get by name
workflow = get_workflow("google_search")
result = await executor.execute(workflow, {"query": "python"})
```

## Custom Workflows

Create your own workflows:

```python
from simple_workflow_executor import SimpleWorkflow, WorkflowStep

# Define workflow
my_workflow = SimpleWorkflow(
    name="custom_search",
    description="Search and extract results",
    steps=[
        WorkflowStep("navigate", "https://example.com"),
        WorkflowStep("type", "input[name='q']", "{query}"),
        WorkflowStep("press", value="Enter"),
        WorkflowStep("wait", value="2"),
        WorkflowStep("extract"),
    ]
)

# Execute
result = await executor.execute(my_workflow, {"query": "test"})
```

## Available Actions

| Action | Target | Value | Description |
|--------|--------|-------|-------------|
| `navigate` | URL | - | Navigate to URL |
| `click` | selector | - | Click element |
| `type` | selector | text | Type text into input |
| `press` | - | key | Press keyboard key |
| `wait` | - | seconds | Wait for time |
| `extract` | - | - | Extract page content |
| `screenshot` | - | - | Take screenshot |
| `scroll` | - | direction | Scroll page (up/down/top/bottom) |

## Optional vs Required Steps

Steps can be **required** (default) or **optional**:

```python
workflow = SimpleWorkflow(
    name="robust_workflow",
    steps=[
        WorkflowStep("navigate", "https://example.com"),
        # Optional - won't fail if popup doesn't exist
        WorkflowStep("click", "button.close-popup", required=False),
        # Required - workflow fails if this fails
        WorkflowStep("type", "input[name='search']", "query"),
    ]
)
```

**Required steps:**
- If fails, workflow stops immediately
- Returns `WorkflowResult` with `success=False`
- Remaining steps don't execute

**Optional steps:**
- If fails, workflow continues
- Failure logged but doesn't stop execution
- Useful for dismissing popups, closing banners, etc.

## Variable Substitution

Use `{placeholders}` in workflow steps:

```python
workflow = SimpleWorkflow(
    name="search",
    steps=[
        WorkflowStep("navigate", "{base_url}/search"),
        WorkflowStep("type", "{input_selector}", "{query}"),
    ]
)

variables = {
    "base_url": "https://example.com",
    "input_selector": "input[name='q']",
    "query": "test search",
}

result = await executor.execute(workflow, variables)
```

Variables are replaced in both `target` and `value` fields.

## Result Structure

```python
@dataclass
class WorkflowResult:
    success: bool                      # Overall success
    workflow_name: str                 # Workflow name
    step_results: List[StepResult]     # Results for each step
    failed_step: Optional[int] = None  # Which step failed (if any)
    error: Optional[str] = None        # Error message (if failed)
    extracted_data: Optional[str] = None  # Data from extract step
    total_time_ms: int = 0            # Total execution time
    completed_steps: int = 0          # How many steps completed
    total_steps: int = 0              # Total steps in workflow
```

Each `StepResult` contains:
```python
@dataclass
class StepResult:
    step_number: int              # Step position (1-indexed)
    step: WorkflowStep            # The step definition
    success: bool                 # Step success
    message: str                  # Status message
    time_ms: int                  # Step execution time
    screenshot_b64: Optional[str] # Screenshot (base64)
    extracted_data: Optional[str] # Extracted data (if extract step)
    error: Optional[str]          # Error message (if failed)
```

## Error Handling

Workflows have built-in error handling:

```python
result = await executor.execute(workflow, variables)

if not result.success:
    print(f"Workflow failed!")
    print(f"Failed at step: {result.failed_step}")
    print(f"Error: {result.error}")
    print(f"Completed {result.completed_steps}/{result.total_steps} steps")

    # Inspect individual step results
    for step_result in result.step_results:
        if not step_result.success:
            print(f"Step {step_result.step_number} failed: {step_result.error}")
```

## Running Multiple Workflows

Execute workflows in sequence:

```python
workflows = [
    (GOOGLE_SEARCH, {"query": "AI"}),
    (YOUTUBE_SEARCH, {"query": "Python"}),
    (SIMPLE_NAVIGATE, {"url": "https://news.ycombinator.com"}),
]

for workflow, variables in workflows:
    result = await executor.execute(workflow, variables)
    print(f"{workflow.name}: {'SUCCESS' if result.success else 'FAILED'}")
```

## Testing

Run tests with pytest:

```bash
pytest test_simple_workflow.py -v
```

Tests include:
- Successful workflow execution
- Variable substitution
- Required step failure handling
- Optional step failure handling
- Pre-built workflows
- Workflow registry
- Step timing
- Data extraction
- Error handling

## Examples

See `simple_workflow_example.py` for complete examples:

```bash
python simple_workflow_example.py
```

Examples include:
1. Pre-built workflows
2. Custom workflows
3. Optional steps
4. Workflow registry
5. Error handling
6. Multi-workflow sequences

## Architecture

```
SimpleWorkflowExecutor
    |
    +-- execute(workflow, variables)
            |
            +-- _apply_variables(step, variables)
            +-- _execute_step(step)
                    |
                    +-- MCP Tools (browser automation)
                            |
                            +-- navigate()
                            +-- click()
                            +-- fill()
                            +-- press_key()
                            +-- extract_content()
                            +-- screenshot()
                            +-- scroll()
```

## Performance

Typical workflow execution times:
- Simple navigate: 2-3 seconds
- Form fill: 3-5 seconds
- Search workflow: 4-6 seconds

Times depend on:
- Network speed
- Page load time
- Number of steps
- Wait times

## Debugging Tips

**See step-by-step progress:**
- Console shows each step as it runs
- Green = success, Red = failure, Yellow = optional failure

**Inspect screenshots:**
- Each step result includes `screenshot_b64`
- Decode and view to see what browser saw

**Check timing:**
- `step_result.time_ms` shows how long each step took
- Identify slow steps for optimization

**Review extracted data:**
- `result.extracted_data` contains page content
- Verify you're getting expected data

## Integration

Use with other systems:

```python
# With AI agent (fallback pattern)
try:
    # Try simple workflow first (fast, reliable)
    result = await executor.execute(GOOGLE_SEARCH, {"query": query})
    if result.success:
        return result.extracted_data
except Exception:
    pass

# Fall back to AI agent (slower, more capable)
return await ai_agent.search(query)
```

```python
# With logging
import logging

logger = logging.getLogger(__name__)

result = await executor.execute(workflow, variables)

if result.success:
    logger.info(f"Workflow {workflow.name} completed in {result.total_time_ms}ms")
else:
    logger.error(f"Workflow {workflow.name} failed: {result.error}")
```

## Limitations

**What this CAN do:**
- Execute predefined sequences
- Handle simple conditional logic (optional steps)
- Variable substitution
- Basic error handling

**What this CANNOT do:**
- Make dynamic decisions
- Handle complex recovery scenarios
- Adapt to unexpected page structures
- Understand natural language
- Learn from failures

For those use cases, use the full AI agent.

## Files

| File | Description |
|------|-------------|
| `simple_workflow_executor.py` | Main module |
| `simple_workflow_example.py` | Usage examples |
| `test_simple_workflow.py` | Unit tests |
| `SIMPLE_WORKFLOW_README.md` | This file |

## API Reference

### SimpleWorkflow

```python
@dataclass
class SimpleWorkflow:
    name: str                    # Workflow name
    steps: List[WorkflowStep]    # Steps to execute
    timeout_per_step: int = 10   # Timeout per step (seconds)
    description: str = ""        # Optional description
```

### WorkflowStep

```python
@dataclass
class WorkflowStep:
    action: str                  # Action type (navigate, click, etc.)
    target: Optional[str] = None # Target (URL, selector)
    value: Optional[str] = None  # Value (text, time, key)
    required: bool = True        # If False, continue on failure
    timeout: int = 10           # Step timeout (seconds)
```

### SimpleWorkflowExecutor

```python
class SimpleWorkflowExecutor:
    def __init__(self, mcp_tools):
        """Initialize with MCP tools instance."""

    async def execute(
        self,
        workflow: SimpleWorkflow,
        variables: Optional[Dict[str, str]] = None
    ) -> WorkflowResult:
        """Execute workflow with optional variable substitution."""
```

### Registry Functions

```python
def get_workflow(name: str) -> Optional[SimpleWorkflow]:
    """Get pre-built workflow by name."""

def list_workflows() -> List[str]:
    """List all available pre-built workflows."""
```

## Contributing

To add new pre-built workflows:

1. Define the workflow:
```python
MY_WORKFLOW = SimpleWorkflow(
    name="my_workflow",
    description="What it does",
    steps=[
        WorkflowStep("navigate", "{url}"),
        # ... more steps
    ]
)
```

2. Add to registry:
```python
WORKFLOW_REGISTRY["my_workflow"] = MY_WORKFLOW
```

3. Test it:
```python
result = await executor.execute(MY_WORKFLOW, {"url": "https://example.com"})
assert result.success
```

## License

Part of eversale-cli. See main LICENSE file.
