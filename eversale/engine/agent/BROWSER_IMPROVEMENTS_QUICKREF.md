# Browser Improvements Quick Reference

One-page reference for all browser improvement modules.

## Quick Start

```python
from agent import get_optimized_browser

# Get browser with all optimizations
browser = await get_optimized_browser(backend_type='playwright', headless=False)
await browser.navigate('https://example.com')
snapshot = await browser.snapshot()
```

## Module Cheat Sheet

| Module | Main Classes | Key Functions | Use When |
|--------|-------------|---------------|----------|
| **DOM First Browser** | `DOMFirstBrowser` | - | Need DOM tree structure |
| **CDP Connector** | `CDPBrowserConnector` | `auto_connect_chrome()` | Reuse existing Chrome |
| **Extraction** | `QuickExtractor` | `extract_links()`, `extract_forms()` | Fast data extraction |
| **DevTools** | `DevToolsHooks` | `get_console_logs()` | Debug browser issues |
| **Token Optimizer** | `TokenOptimizer` | `optimize_snapshot()` | Reduce LLM costs |
| **Backend** | `BrowserBackend` | `create_backend()` | Unified browser API |

## Common Patterns

### Pattern 1: Quick Data Extraction

```python
from agent import QuickExtractor

extractor = QuickExtractor(page)
await extractor.prepare()

links = await extractor.all_links()
forms = await extractor.contact_forms()
nav = await extractor.navigation_links()
```

### Pattern 2: Connect to Existing Chrome

```python
from agent import auto_connect_chrome

instance = await auto_connect_chrome()
await instance.navigate('https://example.com')
snapshot = await instance.snapshot()
```

### Pattern 3: Debug with DevTools

```python
from agent import DevToolsHooks

hooks = DevToolsHooks()
await hooks.attach(page)

errors = await hooks.get_console_logs(level='error')
failed_requests = await hooks.get_network_requests(failed_only=True)
```

### Pattern 4: Optimize for LLM

```python
from agent import optimize_snapshot

# Get optimized snapshot (reduced tokens)
optimized = await optimize_snapshot(page, aggressive=True)
response = await llm.chat(optimized)
```

### Pattern 5: Unified Backend

```python
from agent import create_backend

# Auto-detect best backend
backend = await create_backend(backend_type='auto')

# Or specify
playwright = await create_backend(backend_type='playwright')
cdp = await create_backend(backend_type='cdp', port=9222)

# Same API for both
await backend.navigate('https://example.com')
result = await backend.interact('button', 'click', 'Submit')
```

### Pattern 6: Full Optimization Stack

```python
from agent import get_optimized_browser, QuickExtractor, DevToolsHooks

# Create optimized browser
browser = await get_optimized_browser()

# Attach debugging
devtools = DevToolsHooks()
await devtools.attach(browser.page)

# Navigate and extract
await browser.navigate('https://example.com')
extractor = QuickExtractor(browser.page)
data = await extractor.all_links()

# Check for errors
errors = await devtools.get_console_logs(level='error')

# Get optimized snapshot for LLM
snapshot = await browser.snapshot()  # Already optimized!
```

## Extraction Functions Reference

| Function | Returns | Parameters |
|----------|---------|------------|
| `extract_links(page, limit)` | List of links | `page`, `limit=100` |
| `extract_clickable(page, limit)` | Clickable elements | `page`, `limit=100` |
| `extract_forms(page)` | Form elements | `page` |
| `extract_inputs(page)` | Input fields | `page` |
| `extract_tables(page)` | Table data | `page` |
| `extract_contact_forms(page)` | Contact forms | `page` |
| `extract_navigation_links(page, limit)` | Nav links | `page`, `limit=20` |

## Backend API Reference

| Method | Description | Returns |
|--------|-------------|---------|
| `navigate(url)` | Navigate to URL | `NavigationResult` |
| `snapshot()` | Get page snapshot | `SnapshotResult` |
| `interact(element, action, value)` | Interact with element | `InteractionResult` |
| `observe(wait_for, timeout)` | Wait for changes | `ObserveResult` |
| `close()` | Close browser | None |

## Checking Module Availability

```python
from agent import DOMFirstBrowser, QuickExtractor, TokenOptimizer

# Check if modules are available
if DOMFirstBrowser is None:
    print("DOM First Browser not installed")

if QuickExtractor is None:
    print("Extraction Helpers not installed")

if TokenOptimizer is None:
    print("Token Optimizer not installed")
```

## Error Handling

```python
from agent import get_optimized_browser

try:
    browser = await get_optimized_browser()
    if browser is None:
        raise RuntimeError("Failed to create browser")

    await browser.navigate('https://example.com')
    snapshot = await browser.snapshot()

except Exception as e:
    print(f"Error: {e}")
finally:
    if browser:
        await browser.close()
```

## Performance Tips

1. **Reuse browser instances** - Don't create new for each task
2. **Use CDP backend** when connecting to existing Chrome
3. **Enable aggressive optimization** for long pages
4. **Batch extractions** with QuickExtractor
5. **Disable DevTools** in production - only for debugging

## Import Shortcuts

### Minimal (Just Browser)
```python
from agent import get_optimized_browser
```

### Data Extraction
```python
from agent import QuickExtractor, extract_links, extract_forms
```

### Debugging
```python
from agent import DevToolsHooks, quick_devtools_summary
```

### Full Suite
```python
from agent import (
    get_optimized_browser,
    QuickExtractor,
    DevToolsHooks,
    TokenOptimizer,
    create_backend,
)
```

## Common Issues

| Issue | Solution |
|-------|----------|
| `ImportError: No module 'agent'` | Add `sys.path.insert(0, 'engine')` |
| Module is `None` | Install missing dependencies (playwright, etc.) |
| Browser won't start | Check Playwright installation |
| CDP connection fails | Ensure Chrome running with `--remote-debugging-port` |
| High token usage | Use `optimize_snapshot(aggressive=True)` |

## See Also

- `BROWSER_IMPROVEMENTS_USAGE.md` - Detailed usage guide
- `BROWSER_IMPROVEMENTS_EXPORTS.md` - Complete export list
- Individual module files for advanced usage
