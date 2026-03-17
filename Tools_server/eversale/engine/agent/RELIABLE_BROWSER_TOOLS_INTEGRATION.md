# Reliable Browser Tools - Integration Guide

How to integrate ReliableBrowser into existing agent code.

## Quick Start

### 1. Import and Initialize

```python
from reliable_browser_tools import ReliableBrowser

# In your agent initialization
self.browser = ReliableBrowser(self.mcp_client)
```

### 2. Replace Direct Tool Calls

**Before:**
```python
result = await self.mcp.call_tool("playwright_navigate", {"url": url})
```

**After:**
```python
result = await self.browser.navigate(url)
if not result.success:
    logger.error(f"Navigation failed: {result.error}")
```

## Integration Scenarios

### Scenario 1: Brain/Agent Loop

Replace direct MCP calls in main agent loop:

```python
# brain_enhanced_v2.py or similar

class Agent:
    def __init__(self, mcp_client):
        self.mcp = mcp_client
        self.browser = ReliableBrowser(mcp_client)  # Add this

    async def execute_action(self, action):
        """Execute action with reliability guarantees."""
        action_type = action.get("type")

        if action_type == "navigate":
            # OLD:
            # result = await self.mcp.call_tool("playwright_navigate", {"url": url})

            # NEW:
            result = await self.browser.navigate(action["url"])
            return result

        elif action_type == "click":
            result = await self.browser.click(action["target"])
            return result

        elif action_type == "type":
            result = await self.browser.type(action["target"], action["text"])
            return result
```

### Scenario 2: Workflow Automation

Use in deterministic workflows:

```python
# deterministic_workflows.py

async def login_workflow(browser, credentials):
    """Login workflow with reliable browser."""
    steps = [
        ("navigate", "https://app.example.com/login"),
        ("type", "#email", credentials["email"]),
        ("type", "#password", credentials["password"]),
        ("click", "button[type='submit']"),
        ("wait_for", "Dashboard")
    ]

    for step in steps:
        if step[0] == "navigate":
            result = await browser.navigate(step[1])
        elif step[0] == "type":
            result = await browser.type(step[1], step[2])
        elif step[0] == "click":
            result = await browser.click(step[1])
        elif step[0] == "wait_for":
            result = await browser.wait_for(step[1])

        if not result.success:
            logger.error(f"Step failed: {step[0]} - {result.error}")
            return False

    return True
```

### Scenario 3: Tool Registry Integration

Add to tool registry for LLM access:

```python
# tool_registry.py

from reliable_browser_tools import ReliableBrowser

class ToolRegistry:
    def __init__(self, mcp_client):
        self.mcp = mcp_client
        self.browser = ReliableBrowser(mcp_client)
        self._register_browser_tools()

    def _register_browser_tools(self):
        """Register reliable browser tools."""
        self.tools["navigate"] = {
            "fn": self.browser.navigate,
            "description": "Navigate to URL with validation and retry",
            "params": {"url": "string", "timeout": "int (optional)"}
        }

        self.tools["click"] = {
            "fn": self.browser.click,
            "description": "Click element by ref/selector/description",
            "params": {"target": "string", "timeout": "int (optional)"}
        }

        self.tools["type"] = {
            "fn": self.browser.type,
            "description": "Type text into element",
            "params": {"target": "string", "text": "string", "timeout": "int (optional)"}
        }

        self.tools["get_snapshot"] = {
            "fn": self.browser.get_snapshot,
            "description": "Get accessibility snapshot with mmid refs",
            "params": {"timeout": "int (optional)"}
        }

    async def call_tool(self, name, params):
        """Call tool by name."""
        if name not in self.tools:
            return {"error": f"Unknown tool: {name}"}

        tool = self.tools[name]
        result = await tool["fn"](**params)
        return result
```

### Scenario 4: Recovery System Integration

Use with cascading recovery:

```python
# cascading_recovery.py integration

from reliable_browser_tools import ReliableBrowser

class RecoverySystem:
    def __init__(self, mcp_client):
        self.browser = ReliableBrowser(mcp_client)

    async def execute_with_recovery(self, action):
        """Execute action with recovery on failure."""
        # Try action
        result = await self.browser.click(action["target"])

        if not result.success:
            # Level 1: Retry with different target
            if "ref=" in action["target"]:
                # Try CSS selector instead
                alt_target = self._convert_ref_to_css(action["target"])
                result = await self.browser.click(alt_target)

            # Level 2: Get fresh snapshot
            if not result.success:
                snapshot = await self.browser.get_snapshot()
                # Use snapshot to find element...

            # Level 3: Wait and retry
            if not result.success:
                await asyncio.sleep(2)
                result = await self.browser.click(action["target"])

        return result
```

## Migration Path

### Step 1: Add to Existing Agent

```python
# Add to __init__
from reliable_browser_tools import ReliableBrowser

class YourAgent:
    def __init__(self):
        # ... existing code ...
        self.browser = ReliableBrowser(self.mcp)
```

### Step 2: Migrate Critical Paths First

Start with critical operations that need reliability:

```python
# Login flows
async def login(self):
    # Use reliable browser for critical path
    await self.browser.navigate(self.login_url)
    await self.browser.type("#email", self.email)
    await self.browser.type("#password", self.password)
    await self.browser.click("button[type='submit']")

# Other operations can still use direct MCP
async def scrape_data(self):
    # Use direct MCP for bulk operations
    await self.mcp.call_tool("playwright_evaluate", {...})
```

### Step 3: Gradually Expand

Move more operations over time:

```python
# Week 1: Login/auth flows
# Week 2: Form submissions
# Week 3: Navigation
# Week 4: All interactions
```

### Step 4: Monitor and Tune

```python
# Add metrics
class MetricsCollector:
    def __init__(self):
        self.operations = []

    def record(self, operation, result):
        self.operations.append({
            "op": operation,
            "success": result.success,
            "retries": result.retries,
            "error": result.error
        })

    def report(self):
        total = len(self.operations)
        successes = sum(1 for op in self.operations if op["success"])
        retries = sum(op["retries"] for op in self.operations)

        print(f"Success rate: {successes/total*100:.1f}%")
        print(f"Average retries: {retries/total:.2f}")
```

## Configuration Best Practices

### Development Mode

```python
# Fast iteration, minimal retry
browser = ReliableBrowser(mcp_client)
browser.set_retry_config(max_retries=1, retry_delay=0.5)
```

### Production Mode

```python
# Robust, handles transient failures
browser = ReliableBrowser(mcp_client)
browser.set_retry_config(max_retries=3, retry_delay=1.0)
```

### Critical Operations

```python
# High-value operations, aggressive retry
browser.set_retry_config(max_retries=5, retry_delay=2.0)
await browser.navigate(critical_url)

# Reset to normal
browser.set_retry_config(max_retries=2, retry_delay=1.0)
```

## Error Handling Patterns

### Pattern 1: Early Return

```python
async def workflow(browser):
    result = await browser.navigate(url)
    if not result.success:
        return {"error": f"Navigation failed: {result.error}"}

    result = await browser.click(target)
    if not result.success:
        return {"error": f"Click failed: {result.error}"}

    return {"success": True}
```

### Pattern 2: Continue on Error

```python
async def scrape_multiple(browser, urls):
    results = []

    for url in urls:
        result = await browser.navigate(url)
        if result.success:
            data = await extract_data(browser)
            results.append(data)
        else:
            logger.warning(f"Skipping {url}: {result.error}")

    return results
```

### Pattern 3: Fallback Strategy

```python
async def robust_click(browser, targets):
    """Try multiple targets until one works."""
    for target in targets:
        result = await browser.click(target)
        if result.success:
            return result

    return ToolResult(success=False, error="All targets failed")
```

## Testing Integration

### Unit Test

```python
# test_integration.py

import pytest
from reliable_browser_tools import ReliableBrowser

@pytest.mark.asyncio
async def test_navigation():
    mcp = MockMCPClient()
    browser = ReliableBrowser(mcp)

    result = await browser.navigate("https://example.com")
    assert result.success
    assert result.retries >= 0
```

### Integration Test

```python
@pytest.mark.asyncio
async def test_workflow():
    mcp = create_test_mcp_client()
    browser = ReliableBrowser(mcp)

    # Full workflow
    assert (await browser.navigate("https://app.test")).success
    assert (await browser.click("#submit")).success
    assert (await browser.wait_for("Success")).success
```

## Performance Considerations

### Validation Overhead
- Input validation: ~0.01ms per operation
- Health checking: ~3ms (cached for 5s)
- Total overhead: <5ms for typical operations

### Retry Impact
- No retry: Operation time only
- 1 retry: +1s (default retry_delay)
- 2 retries: +3s (exponential backoff)

### Optimization Tips

1. **Use health check caching**: Default 5s is good for most cases
2. **Tune retry config**: Set based on operation criticality
3. **Batch operations**: Group non-dependent operations
4. **Use direct MCP for bulk**: Reserve ReliableBrowser for critical paths

## Troubleshooting

### Import Error

```python
# Ensure tool_wrappers.py is available
from tool_wrappers import ToolResult

# If missing, copy ToolResult definition locally
```

### Rich Not Available

```python
# Install Rich for colored output
pip install rich

# Or run without - falls back to plain print
```

### Health Check Failures

```python
# Increase cache interval to reduce checks
browser.health_checker._health_check_interval = 10.0

# Or disable by checking manually
healthy, error = await browser.health_checker.check()
if not healthy:
    # Restart browser
    await restart_browser()
```

## Complete Example: Replacing Existing Agent

**Before:**

```python
class Agent:
    async def run_task(self, task):
        # Direct MCP calls
        await self.mcp.call_tool("playwright_navigate", {"url": task.url})
        await self.mcp.call_tool("playwright_click", {"selector": ".submit"})
        # No validation, retry, or logging
```

**After:**

```python
from reliable_browser_tools import ReliableBrowser

class Agent:
    def __init__(self, mcp_client):
        self.mcp = mcp_client
        self.browser = ReliableBrowser(mcp_client)

    async def run_task(self, task):
        # Validated, retried, logged
        result = await self.browser.navigate(task.url)
        if not result.success:
            logger.error(f"Navigation failed: {result.error}")
            return False

        result = await self.browser.click(".submit")
        if not result.success:
            logger.error(f"Click failed: {result.error}")
            return False

        return True
```

## Next Steps

1. Review your existing browser operations
2. Identify critical paths that need reliability
3. Add ReliableBrowser to agent initialization
4. Migrate one operation at a time
5. Monitor success rates and tune retry config
6. Expand to all browser operations

For questions or issues, see:
- RELIABLE_BROWSER_TOOLS_README.md - Full documentation
- RELIABLE_BROWSER_TOOLS_QUICKREF.md - Quick reference
- reliable_browser_tools_example.py - Working examples
