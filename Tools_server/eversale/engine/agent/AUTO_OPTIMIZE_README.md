# Auto-Optimization Module

**One-line setup for a fully optimized browser agent.**

## Overview

The auto-optimization module provides a zero-configuration entry point for creating browser agents with all optimizations automatically enabled:

- **Backend Auto-Detection**: Tries CDP (existing Chrome) first, falls back to Playwright
- **Token Optimization**: Snapshot compression, caching, and budget tracking
- **DevTools Hooks**: Network monitoring, console capture, error tracking
- **Extraction Shortcuts**: Fast JavaScript-based data extraction
- **Performance Tracking**: Comprehensive optimization statistics

## Quick Start

### Basic Usage

```python
from agent.auto_optimize import get_optimized_agent

# One line to get fully optimized agent
agent = await get_optimized_agent()

# Connect and start using
await agent.connect()
await agent.navigate("https://example.com")

# Auto-wired extraction shortcuts
links = await agent.extract_links(contains_text='signup')
forms = await agent.extract_forms()

# Get optimization stats
stats = agent.get_optimization_stats()
print(f"Tokens saved: {stats['token_optimizer']['tokens_saved']}")

# Cleanup
await agent.disconnect()
```

### With Custom Options

```python
agent = await get_optimized_agent(
    prefer_cdp=True,           # Try CDP first (reuse existing Chrome)
    headless=False,            # Show browser (default: False)
    capture_errors=True,       # Enable DevTools error capture
    token_budget=8000,         # Max tokens for context
    max_snapshot_elements=100, # Max elements in snapshot
)
```

## Features

### 1. Backend Auto-Detection

The module automatically selects the best browser backend:

1. **CDP Backend** (if Chrome running with debug port):
   - Reuses existing Chrome session with saved logins
   - Connects via Chrome DevTools Protocol
   - Fastest startup (no new browser launch)

2. **Playwright Backend** (fallback):
   - Launches new browser instance
   - Full control and stealth features
   - Works without existing Chrome

```python
# Will use CDP if Chrome is running with --remote-debugging-port=9222
# Otherwise uses Playwright
agent = await get_optimized_agent(prefer_cdp=True)
```

### 2. Token Optimization

Automatically enabled optimizations:

- **Snapshot Compression**: Reduces snapshot size by 50-80%
  - Removes non-interactive elements
  - Truncates long text
  - Limits tree depth
  - Collapses repetitive structures

- **Snapshot Caching**: Reuses snapshots when page hasn't changed
  - Cache TTL: 30 seconds (configurable)
  - Skips snapshots after non-DOM-changing actions (scroll, hover)
  - Automatic cache invalidation

- **Budget Tracking**: Monitors token usage
  - Warns when approaching budget
  - Auto-compression if over threshold
  - Detailed statistics

```python
# Snapshots are automatically compressed and cached
snapshot1 = await agent.snapshot()  # Fresh snapshot
snapshot2 = await agent.snapshot()  # Uses cache (if valid)

# Force fresh snapshot
snapshot3 = await agent.snapshot(force=True)

# Check token budget
context = "your prompt here"
within_budget, tokens, message = agent.check_token_budget(context)
print(f"{message}")  # "Token usage: 5234/8000 (65.4%)"
```

### 3. DevTools Hooks

Automatically captures browser events:

- **Network Requests**: All requests/responses with timing
- **Console Messages**: All console.log, warn, error
- **Page Errors**: Uncaught exceptions with stack traces
- **Failed Requests**: Network failures, timeouts, CORS errors

```python
# Get captured errors
errors = await agent.get_errors()
for error in errors:
    print(f"{error['timestamp']}: {error['message']}")

# Get failed network requests
failed = await agent.get_failed_requests()
for req in failed:
    print(f"{req['url']}: {req['failure_reason']}")

# Get console errors
console_errors = await agent.get_console_errors()

# Get full DevTools summary
summary = agent.get_devtools_summary()
print(f"Network requests: {summary['network']['total_requests']}")
print(f"Failed requests: {summary['network']['failed_requests']}")
print(f"Console errors: {summary['console']['errors']}")
```

### 4. Extraction Shortcuts

Fast JavaScript-based extraction without LLM analysis:

```python
# Extract links with filtering
signup_links = await agent.extract_links(
    contains_text='sign up',
    limit=10
)

# Extract links from specific domain
github_links = await agent.extract_links(
    domain='github.com'
)

# Extract all forms
forms = await agent.extract_forms()
for form in forms:
    print(f"Form: {form['action']}")
    for field in form['fields']:
        print(f"  - {field['name']} ({field['type']})")

# Extract clickable elements
buttons = await agent.extract_clickable(
    role='button',
    contains_text='submit'
)
```

### 5. Optimization Statistics

Comprehensive performance tracking:

```python
stats = agent.get_optimization_stats()

# Returns:
{
    "backend": {
        "type": "PlaywrightBackend",
        "connected": True,
        "connection_time_ms": 1234.5
    },
    "token_optimizer": {
        "tokens_saved": 15000,
        "cache_hits": 45,
        "cache_misses": 12,
        "cache_hit_rate": "78.9%",
        "auto_compressions": 3
    },
    "devtools": {
        "errors_captured": 2,
        "failed_requests": 0,
        "console_errors": 1
    },
    "performance": {
        "snapshots_taken": 12,
        "snapshots_cached": 45,
        "screenshots_skipped": 0,
        "avg_snapshot_time_ms": 234.5
    }
}

# Reset stats
agent.reset_stats()
```

## Configuration Options

### OptimizationConfig

All configuration options with defaults:

```python
from agent.auto_optimize import OptimizationConfig

config = OptimizationConfig(
    # Backend selection
    prefer_cdp=True,              # Try CDP first
    headless=False,               # Show browser

    # Token optimizer
    enable_token_optimizer=True,  # Enable compression/caching
    token_budget=8000,            # Max tokens for context
    max_snapshot_elements=100,    # Max elements in snapshot
    max_text_length=200,          # Max length for text fields
    cache_ttl_seconds=30,         # Cache validity duration

    # DevTools hooks
    enable_devtools=True,         # Enable error capture
    capture_network=True,         # Capture network requests
    capture_console=True,         # Capture console messages
    max_network_entries=500,      # Max requests to store
    max_console_entries=200,      # Max console logs to store

    # Performance
    enable_snapshot_caching=True, # Enable snapshot cache
    auto_compress_threshold=0.8,  # Auto-compress at 80% of budget
)
```

## Core Browser Methods

The `OptimizedAgent` wraps a `BrowserBackend` and provides all standard methods:

```python
# Navigation
result = await agent.navigate("https://example.com")
result = await agent.navigate("https://example.com", wait_until='networkidle')

# Snapshot (compressed and cached)
snapshot = await agent.snapshot()
snapshot = await agent.snapshot(force=True)  # Force fresh

# Interactions
await agent.click(ref='mm123')
await agent.type(ref='mm456', text='hello', clear=True)
await agent.scroll(direction='down', amount=500)

# JavaScript execution
result = await agent.run_code('return document.title')

# Observation
observe_result = await agent.observe(network=True, console=True)

# Screenshots
screenshot_bytes = await agent.screenshot(full_page=True)

# Connection management
await agent.connect()
await agent.disconnect()
```

## Integration Examples

### Example 1: Simple Task

```python
from agent.auto_optimize import get_optimized_agent

async def simple_task():
    agent = await get_optimized_agent()
    await agent.connect()

    try:
        # Navigate
        await agent.navigate("https://github.com")

        # Extract links
        signup_links = await agent.extract_links(contains_text='sign up', limit=5)
        print(f"Found {len(signup_links)} signup links")

        # Get errors
        errors = await agent.get_errors()
        if errors:
            print(f"Warning: {len(errors)} page errors")

        # Stats
        stats = agent.get_optimization_stats()
        print(f"Tokens saved: {stats['token_optimizer']['tokens_saved']}")

    finally:
        await agent.disconnect()

asyncio.run(simple_task())
```

### Example 2: With Error Handling

```python
from agent.auto_optimize import get_optimized_agent

async def robust_task():
    agent = await get_optimized_agent(
        prefer_cdp=True,
        capture_errors=True,
        token_budget=10000
    )

    connected = await agent.connect()
    if not connected:
        print("Failed to connect to browser")
        return

    try:
        # Navigate with error checking
        nav_result = await agent.navigate("https://example.com")

        # Check for network errors
        failed_requests = await agent.get_failed_requests()
        if failed_requests:
            print(f"Warning: {len(failed_requests)} failed requests")
            for req in failed_requests:
                print(f"  - {req['url']}: {req['failure_reason']}")

        # Check for JavaScript errors
        js_errors = await agent.get_console_errors()
        if js_errors:
            print(f"Warning: {len(js_errors)} JavaScript errors")

        # Get snapshot with budget check
        snapshot = await agent.snapshot()

        # Do work...
        links = await agent.extract_links(limit=20)

        # Final stats
        stats = agent.get_optimization_stats()
        print(f"\nOptimization Results:")
        print(f"  Tokens saved: {stats['token_optimizer']['tokens_saved']}")
        print(f"  Cache hit rate: {stats['token_optimizer']['cache_hit_rate']}")
        print(f"  Avg snapshot time: {stats['performance']['avg_snapshot_time_ms']:.1f}ms")

    finally:
        await agent.disconnect()

asyncio.run(robust_task())
```

### Example 3: Using with Existing Code

```python
from agent.auto_optimize import get_optimized_agent

async def integrate_with_existing():
    # Replace your existing backend creation with this
    agent = await get_optimized_agent()
    await agent.connect()

    # Use agent.backend for BrowserBackend interface
    backend = agent.backend

    # Or use agent directly (same interface)
    snapshot = await agent.snapshot()

    # Get optimization benefits automatically
    stats = agent.get_optimization_stats()

    await agent.disconnect()
```

## Comparison

### Before (Manual Setup)

```python
from agent.browser_backend import PlaywrightBackend
from agent.token_optimizer import TokenOptimizer
from agent.devtools_hooks import DevToolsHooks

# Create backend
backend = PlaywrightBackend(headless=False)
await backend.connect()

# Create token optimizer
token_optimizer = TokenOptimizer({
    'token_budget': 8000,
    'max_snapshot_elements': 100,
})

# Create DevTools hooks
devtools = DevToolsHooks(backend.page)
await devtools.start_capture()

# Manual integration...
snapshot = await backend.snapshot()
compressed = token_optimizer.compress_snapshot(snapshot)
errors = devtools.get_errors()

# Manual cleanup
await devtools.stop_capture()
await backend.disconnect()
```

### After (Auto-Optimization)

```python
from agent.auto_optimize import get_optimized_agent

# One line setup
agent = await get_optimized_agent()
await agent.connect()

# Everything is automatic
snapshot = await agent.snapshot()  # Already compressed and cached
errors = await agent.get_errors()  # Already captured

# Automatic cleanup
await agent.disconnect()
```

## Performance Impact

Expected improvements with auto-optimization:

| Metric | Improvement |
|--------|-------------|
| Token usage | -50% to -80% (compression) |
| Snapshot calls | -30% to -60% (caching) |
| Context size | -40% to -70% (optimization) |
| Error detection | +100% (DevTools capture) |
| Extraction speed | +200% to +500% (JS-based) |

## Requirements

- Python 3.8+
- Playwright (for PlaywrightBackend)
- Chrome with debug port (optional, for CDP)
- Dependencies: `token_optimizer`, `devtools_hooks`, `extraction_helpers`

## Starting Chrome with Debug Port

To enable CDP backend:

```bash
# Windows
chrome.exe --remote-debugging-port=9222

# macOS
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222

# Linux
google-chrome --remote-debugging-port=9222
```

The agent will automatically detect and connect to this Chrome instance.

## Troubleshooting

### Issue: Backend not connecting

**Solution**: Check that either Chrome is running with debug port OR Playwright is installed:

```bash
# Install Playwright
pip install playwright
playwright install chromium
```

### Issue: DevTools not capturing

**Solution**: Ensure `capture_errors=True` in config and backend has `page` object:

```python
agent = await get_optimized_agent(capture_errors=True)
```

### Issue: Extraction helpers not working

**Solution**: Ensure page has mmid attributes injected (automatic in most backends).

### Issue: High memory usage

**Solution**: Reduce buffer sizes:

```python
agent = await get_optimized_agent(
    max_snapshot_elements=50,    # Reduce from 100
    max_network_entries=200,     # Reduce from 500
    max_console_entries=100,     # Reduce from 200
)
```

## API Reference

### get_optimized_agent()

```python
async def get_optimized_agent(
    prefer_cdp: bool = True,
    headless: bool = False,
    capture_errors: bool = True,
    token_budget: int = 8000,
    max_snapshot_elements: int = 100,
    **kwargs
) -> OptimizedAgent
```

**Args**:
- `prefer_cdp`: Try CDP backend first (reuse existing Chrome)
- `headless`: Run browser in headless mode
- `capture_errors`: Enable DevTools error capture
- `token_budget`: Max tokens for context
- `max_snapshot_elements`: Max elements in snapshot
- `**kwargs`: Additional backend-specific options

**Returns**: `OptimizedAgent` instance

### OptimizedAgent

Main methods:

```python
# Connection
await connect() -> bool
await disconnect() -> None

# Navigation
await navigate(url, wait_until='load') -> NavigationResult

# Snapshot (compressed and cached)
await snapshot(force=False) -> SnapshotResult

# Interactions
await click(ref, **kwargs) -> InteractionResult
await type(ref, text, clear=True, **kwargs) -> InteractionResult
await scroll(direction='down', amount=500) -> InteractionResult

# JavaScript
await run_code(js) -> Any

# Observation
await observe(network=False, console=False) -> ObserveResult

# Screenshots
await screenshot(full_page=False) -> bytes

# Extraction shortcuts
await extract_links(contains_text=None, domain=None, limit=50) -> List[Dict]
await extract_forms() -> List[Dict]
await extract_clickable(contains_text=None, role=None, limit=50) -> List[Dict]

# DevTools shortcuts
await get_errors() -> List[Dict]
await get_failed_requests() -> List[Dict]
await get_console_errors() -> List[Dict]
get_devtools_summary() -> Dict

# Optimization
get_optimization_stats() -> Dict
reset_stats() -> None
compress_snapshot(snapshot) -> Any
estimate_tokens(text) -> int
check_token_budget(context) -> Tuple[bool, int, str]
```

## See Also

- [Token Optimizer README](TOKEN_OPTIMIZER_README.md) - Detailed token optimization
- [DevTools Hooks README](DEVTOOLS_HOOKS_README.md) - DevTools capture details
- [Extraction Helpers README](EXTRACTION_HELPERS_README.md) - Fast extraction methods
- [Browser Backend README](BROWSER_BACKEND_README.md) - Backend abstraction layer

## License

Part of the Eversale CLI agent package.
