# Auto-Optimization Integration Guide

Guide for integrating the auto-optimization module into existing Eversale CLI agent code.

## Overview

The auto-optimization module provides a drop-in replacement for manual browser backend setup with all optimizations automatically enabled.

## Integration Methods

### Method 1: Direct Replacement

Replace manual backend creation with `get_optimized_agent()`:

#### Before
```python
from agent.playwright_direct import PlaywrightDirect
from agent.token_optimizer import TokenOptimizer
from agent.devtools_hooks import DevToolsHooks

# Manual setup
backend = PlaywrightDirect(headless=False)
await backend.connect()

optimizer = TokenOptimizer({'token_budget': 8000})
devtools = DevToolsHooks(backend.page)
await devtools.start_capture()

# Manual integration required...
```

#### After
```python
from agent.auto_optimize import get_optimized_agent

# Auto setup - everything wired automatically
agent = await get_optimized_agent()
await agent.connect()

# Use directly - optimizations automatic
snapshot = await agent.snapshot()  # Compressed & cached
errors = await agent.get_errors()  # Auto-captured
```

### Method 2: As Backend Wrapper

Use OptimizedAgent as a wrapper around existing backend:

```python
from agent.auto_optimize import OptimizedAgent, OptimizationConfig
from agent.token_optimizer import TokenOptimizer
from agent.devtools_hooks import DevToolsHooks

# Your existing backend
backend = YourBackend()

# Wrap with optimizations
config = OptimizationConfig(token_budget=8000)
optimizer = TokenOptimizer(config)
devtools = DevToolsHooks(backend.page)

agent = OptimizedAgent(backend, config, optimizer, devtools)
await agent.connect()
```

### Method 3: With Existing Agent Classes

Integrate into existing agent architecture:

```python
from agent.auto_optimize import get_optimized_agent

class YourAgent:
    def __init__(self):
        self.browser = None

    async def initialize(self):
        # Use optimized browser
        self.browser = await get_optimized_agent(
            token_budget=10000,
            capture_errors=True
        )
        await self.browser.connect()

    async def run_task(self, task):
        # Use optimized methods
        await self.browser.navigate(task.url)
        snapshot = await self.browser.snapshot()  # Auto-optimized
        links = await self.browser.extract_links()  # Fast extraction
        errors = await self.browser.get_errors()  # Auto-captured

        # Get stats
        stats = self.browser.get_optimization_stats()
        return stats
```

## Integration Points

### 1. Entry Points

The module is designed to be used at these entry points:

#### A. run_ultimate.py
```python
# In one_shot() or interactive mode
from agent.auto_optimize import get_optimized_agent

async def one_shot(prompt: str):
    # Replace brain creation with optimized agent
    agent = await get_optimized_agent()
    await agent.connect()

    try:
        # Run task with optimizations
        result = await agent.execute_task(prompt)
    finally:
        await agent.disconnect()
```

#### B. SimpleAgent
```python
# In SimpleAgent initialization
from agent.auto_optimize import get_optimized_agent

class SimpleAgent:
    async def __init__(self):
        self.browser = await get_optimized_agent()
        await self.browser.connect()
```

#### C. EnhancedBrain
```python
# In brain_enhanced_v2.py
from agent.auto_optimize import get_optimized_agent

async def create_enhanced_brain(config):
    browser = await get_optimized_agent(
        token_budget=config.get('token_budget', 8000),
        capture_errors=True
    )
    # Use browser with enhanced brain...
```

### 2. Main Usage Patterns

#### Pattern A: Task Execution
```python
async def execute_task(task: str):
    agent = await get_optimized_agent()
    await agent.connect()

    try:
        # Navigate
        await agent.navigate(get_url_from_task(task))

        # Get optimized snapshot
        snapshot = await agent.snapshot()

        # Extract data efficiently
        if 'find links' in task:
            links = await agent.extract_links()
            return links

        # Check for errors
        errors = await agent.get_errors()
        if errors:
            logger.warning(f"Page has {len(errors)} errors")

    finally:
        await agent.disconnect()
```

#### Pattern B: Research Workflow
```python
async def research_workflow(query: str):
    agent = await get_optimized_agent(
        token_budget=10000,  # Higher budget for research
        capture_errors=True
    )
    await agent.connect()

    try:
        # Navigate to search
        await agent.navigate(f"https://google.com/search?q={query}")

        # Extract results efficiently
        results = await agent.extract_links(limit=20)

        # Visit each result and extract data
        data = []
        for result in results:
            await agent.navigate(result['href'])

            # Snapshot is auto-cached if revisiting
            snapshot = await agent.snapshot()

            # Extract forms, buttons, etc.
            forms = await agent.extract_forms()
            data.append({
                'url': result['href'],
                'forms': forms
            })

        # Get optimization stats
        stats = agent.get_optimization_stats()
        logger.info(f"Tokens saved: {stats['token_optimizer']['tokens_saved']}")

        return data

    finally:
        await agent.disconnect()
```

#### Pattern C: Interactive Mode
```python
async def interactive_mode():
    agent = await get_optimized_agent()
    await agent.connect()

    try:
        while True:
            command = input(">>> ")

            if command == "quit":
                break

            # Execute command
            if command.startswith("go "):
                url = command[3:]
                await agent.navigate(url)

            elif command == "snapshot":
                snapshot = await agent.snapshot()
                print(f"Elements: {len(snapshot.elements)}")

            elif command == "links":
                links = await agent.extract_links(limit=10)
                for link in links:
                    print(f"- {link['text']}: {link['href']}")

            elif command == "errors":
                errors = await agent.get_errors()
                print(f"Errors: {len(errors)}")

            elif command == "stats":
                stats = agent.get_optimization_stats()
                print(json.dumps(stats, indent=2))

    finally:
        await agent.disconnect()
```

## Configuration Management

### Centralized Configuration

Create a configuration module:

```python
# config/browser_config.py
from agent.auto_optimize import OptimizationConfig

def get_browser_config(mode='default'):
    configs = {
        'default': OptimizationConfig(
            prefer_cdp=True,
            headless=False,
            token_budget=8000,
            capture_errors=True
        ),
        'headless': OptimizationConfig(
            prefer_cdp=False,
            headless=True,
            token_budget=5000,
            capture_errors=False
        ),
        'debug': OptimizationConfig(
            prefer_cdp=True,
            headless=False,
            token_budget=10000,
            capture_errors=True,
            capture_network=True,
            capture_console=True
        ),
        'production': OptimizationConfig(
            prefer_cdp=True,
            headless=True,
            token_budget=6000,
            capture_errors=True
        )
    }
    return configs.get(mode, configs['default'])

# Usage
from agent.auto_optimize import get_optimized_agent
from config.browser_config import get_browser_config

agent = await get_optimized_agent(**vars(get_browser_config('debug')))
```

## Migration Checklist

When migrating existing code to use auto-optimization:

- [ ] Import `get_optimized_agent` from `agent.auto_optimize`
- [ ] Replace backend creation with `await get_optimized_agent()`
- [ ] Remove manual token optimizer setup (now automatic)
- [ ] Remove manual DevTools setup (now automatic)
- [ ] Update snapshot calls to use `agent.snapshot()` (caching automatic)
- [ ] Add error checking with `agent.get_errors()` (free)
- [ ] Add stats reporting with `agent.get_optimization_stats()` (valuable)
- [ ] Use extraction shortcuts where applicable (faster)
- [ ] Test with different configurations (headless, token budgets)
- [ ] Update documentation to reflect auto-optimization

## Best Practices

### 1. Always Check Stats

Monitor optimization effectiveness:

```python
stats = agent.get_optimization_stats()
if stats['token_optimizer']['cache_hit_rate'] < 20:
    logger.warning("Low cache hit rate - consider tuning")
```

### 2. Use Extraction Shortcuts

Replace manual snapshot analysis with fast extraction:

```python
# SLOW - full snapshot + LLM analysis
snapshot = await agent.snapshot()
links = analyze_snapshot_for_links(snapshot)

# FAST - direct JS extraction
links = await agent.extract_links(contains_text='signup')
```

### 3. Monitor Errors Proactively

Check for errors after each navigation:

```python
await agent.navigate(url)

errors = await agent.get_errors()
if errors:
    logger.error(f"Page has errors: {errors}")

failed_requests = await agent.get_failed_requests()
if failed_requests:
    logger.warning(f"Failed requests: {failed_requests}")
```

### 4. Tune for Use Case

Adjust configuration based on needs:

```python
# Research: Higher budget, more elements
research_agent = await get_optimized_agent(
    token_budget=12000,
    max_snapshot_elements=150
)

# Form filling: Lower budget, fewer elements
form_agent = await get_optimized_agent(
    token_budget=5000,
    max_snapshot_elements=50
)
```

### 5. Reset Stats Between Tasks

Clear stats when starting new task:

```python
agent.reset_stats()
await run_task(task)
stats = agent.get_optimization_stats()
report_task_stats(task, stats)
```

## Troubleshooting

### Issue: Backend not connecting

**Solution**: Ensure either Playwright installed or Chrome running with debug port:

```python
# Check which backend will be used
import socket

def is_chrome_available():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', 9222))
        sock.close()
        return result == 0
    except:
        return False

if is_chrome_available():
    print("Will use CDP backend")
else:
    print("Will use Playwright backend (install if needed)")
```

### Issue: High memory usage

**Solution**: Reduce buffer sizes:

```python
agent = await get_optimized_agent(
    max_snapshot_elements=50,
    max_network_entries=200,
    max_console_entries=100
)
```

### Issue: Stats showing zero savings

**Solution**: Ensure multiple operations to see caching benefits:

```python
# First snapshot - no savings yet
snapshot1 = await agent.snapshot()

# Scroll (doesn't change DOM)
await agent.scroll()

# Second snapshot - should use cache
snapshot2 = await agent.snapshot()  # Cache hit!

stats = agent.get_optimization_stats()
print(f"Cache hits: {stats['token_optimizer']['cache_hits']}")
```

## Examples

See `auto_optimize_example.py` for complete working examples:
- Basic usage
- Extraction shortcuts
- Error monitoring
- Token optimization
- Comprehensive workflow

## See Also

- [AUTO_OPTIMIZE_README.md](AUTO_OPTIMIZE_README.md) - Full documentation
- [AUTO_OPTIMIZE_QUICKREF.md](AUTO_OPTIMIZE_QUICKREF.md) - Quick reference
- [AUTO_OPTIMIZE_SUMMARY.md](AUTO_OPTIMIZE_SUMMARY.md) - Technical summary
- [auto_optimize_example.py](auto_optimize_example.py) - Usage examples
