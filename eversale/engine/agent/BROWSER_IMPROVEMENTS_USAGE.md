# Browser Improvements Usage Guide

This guide demonstrates how to use the new browser improvement modules exported from the agent package.

## Quick Start - Optimized Browser

The easiest way to get a fully optimized browser instance:

```python
from agent import get_optimized_browser

# Create an optimized browser with all features enabled
browser = await get_optimized_browser(backend_type='playwright', headless=False)

# Navigate and interact
await browser.navigate('https://example.com')
snapshot = await browser.snapshot()
await browser.interact('button', 'click', 'Submit')
```

## Individual Module Usage

### 1. DOM First Browser

DOM-driven browser automation with element tree structure:

```python
from agent import DOMFirstBrowser, ElementNode

browser = DOMFirstBrowser()
await browser.launch(headless=False)
await browser.navigate('https://example.com')

# Get DOM snapshot
snapshot = await browser.snapshot()
print(f"Found {len(snapshot.elements)} elements")

# Interact with elements
await browser.interact('button#submit', 'click')

# Observe changes
observe_result = await browser.observe(wait_for='page-loaded', timeout=5.0)
print(f"Changes detected: {observe_result.changed}")
```

### 2. CDP Browser Connector

Reuse existing Chrome sessions via Chrome DevTools Protocol:

```python
from agent import CDPBrowserConnector, connect_to_existing_chrome, auto_connect_chrome

# Auto-connect to running Chrome
instance = await auto_connect_chrome()

# Or manually connect
connector = CDPBrowserConnector()
instance = await connector.connect(port=9222)

# Use the connected instance
await instance.navigate('https://example.com')
snapshot = await instance.snapshot()
```

### 3. Extraction Helpers

Fast DOM extraction utilities for common tasks:

```python
from agent import (
    extract_links, extract_clickable, extract_forms,
    extract_inputs, extract_tables, QuickExtractor
)

# Extract links from page
links = await extract_links(page, limit=50)
for link in links:
    print(f"{link['text']} -> {link['url']}")

# Extract forms
forms = await extract_forms(page)
for form in forms:
    print(f"Form action: {form['action']}, fields: {form['field_count']}")

# Use QuickExtractor for common patterns
extractor = QuickExtractor(page)
await extractor.prepare()

# Quick extractions
contact_forms = await extractor.contact_forms()
nav_links = await extractor.navigation_links(limit=20)
all_links = await extractor.all_links()
```

### 4. DevTools Hooks

Inspect browser internals and debug issues:

```python
from agent import DevToolsHooks, quick_devtools_summary

# Create hooks instance
hooks = DevToolsHooks()

# Attach to page
await hooks.attach(page)

# Get console logs
logs = await hooks.get_console_logs(level='error')
for log in logs:
    print(f"Console error: {log['text']}")

# Get network requests
requests = await hooks.get_network_requests(failed_only=True)
for req in requests:
    print(f"Failed request: {req['url']} - {req['status']}")

# Quick summary
summary = await quick_devtools_summary(page)
print(f"Errors: {summary['error_count']}, Failed requests: {summary['failed_requests']}")
```

### 5. Token Optimizer

Reduce token usage and context size:

```python
from agent import TokenOptimizer, create_optimizer, optimize_snapshot

# Create optimizer
optimizer = create_optimizer()

# Optimize snapshot before sending to LLM
raw_snapshot = await browser.snapshot()
optimized = optimizer.optimize(raw_snapshot)

print(f"Token reduction: {raw_snapshot['estimated_tokens']} -> {optimized['estimated_tokens']}")

# Or use convenience function
optimized_snapshot = await optimize_snapshot(page, aggressive=True)
```

### 6. Browser Backend (Unified Abstraction)

Use the same API for both Playwright and CDP:

```python
from agent import BrowserBackend, create_backend, PlaywrightBackend, CDPBackend

# Auto-detect best backend
backend = await create_backend(backend_type='auto')

# Or specify explicitly
playwright_backend = await create_backend(backend_type='playwright', headless=False)
cdp_backend = await create_backend(backend_type='cdp', port=9222)

# Unified API works the same for both
await backend.navigate('https://example.com')
snapshot = await backend.snapshot()
result = await backend.interact('button', 'click', 'Submit')

# Check interaction success
if result.success:
    print(f"Clicked successfully: {result.message}")
else:
    print(f"Click failed: {result.error}")
```

## Combined Usage Example

Putting it all together for a powerful automation workflow:

```python
from agent import (
    get_optimized_browser,
    QuickExtractor,
    DevToolsHooks,
    optimize_snapshot
)

async def scrape_with_full_optimization():
    # Create optimized browser
    browser = await get_optimized_browser(backend_type='playwright', headless=False)

    # Attach devtools for debugging
    devtools = DevToolsHooks()
    await devtools.attach(browser.page)

    # Navigate
    await browser.navigate('https://example.com/products')

    # Quick extraction
    extractor = QuickExtractor(browser.page)
    await extractor.prepare()

    # Extract data
    links = await extractor.all_links()
    forms = await extractor.contact_forms()

    # Get optimized snapshot for LLM
    snapshot = await optimize_snapshot(browser.page, aggressive=True)

    # Check for errors
    console_errors = await devtools.get_console_logs(level='error')
    if console_errors:
        print(f"Found {len(console_errors)} console errors")

    # Clean up
    await browser.close()

    return {
        'links': links,
        'forms': forms,
        'snapshot': snapshot,
        'errors': console_errors
    }
```

## Error Handling

All modules use try/except blocks for graceful degradation:

```python
from agent import (
    DOMFirstBrowser,
    QuickExtractor,
    TokenOptimizer
)

# Check if modules are available
if DOMFirstBrowser is None:
    print("DOM First Browser not available - falling back to standard browser")

if QuickExtractor is None:
    print("Extraction Helpers not available - using manual extraction")

if TokenOptimizer is None:
    print("Token Optimizer not available - using raw snapshots")
```

## Best Practices

1. **Use get_optimized_browser()** for most cases - it includes all optimizations automatically
2. **Check module availability** before using (they may not be installed)
3. **Use QuickExtractor** for common extraction tasks - faster than manual JS execution
4. **Enable DevToolsHooks** when debugging - invaluable for troubleshooting
5. **Optimize snapshots** before sending to LLM - saves tokens and costs
6. **Prefer unified backend** over direct Playwright/CDP usage - easier to switch later

## Module Dependencies

| Module | Required Dependencies |
|--------|----------------------|
| DOMFirstBrowser | playwright, beautifulsoup4 |
| CDPBrowserConnector | playwright, websockets |
| ExtractionHelpers | playwright |
| DevToolsHooks | playwright |
| TokenOptimizer | tiktoken (optional) |
| BrowserBackend | playwright (Playwright mode), pychrome (CDP mode) |

## Performance Tips

1. **Reuse browser instances** - don't create new instances for each task
2. **Use CDP backend** when connecting to existing Chrome sessions
3. **Enable aggressive token optimization** for long pages
4. **Batch extractions** with QuickExtractor instead of multiple calls
5. **Disable devtools hooks** in production - only use when debugging
