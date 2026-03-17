# Browser Optimization Configuration Usage

This document shows how to use the browser optimization configuration system in your agent modules.

## Configuration Files

- `/mnt/c/ev29/cli/engine/agent/config/browser_optimizations.yaml` - Browser optimization settings
- `/mnt/c/ev29/cli/engine/agent/config_loader.py` - Configuration loader with helper functions

## Basic Usage

### Import the config loader

```python
from config_loader import (
    is_optimization_enabled,
    is_snapshot_first_enabled,
    is_token_optimizer_enabled,
    is_devtools_enabled,
    is_cdp_enabled,
    get_token_budget,
    get_cdp_port,
    get_optimization_setting,
    matches_trigger
)
```

### Check if optimizations are enabled

```python
# Check master switch
if is_optimization_enabled():
    # Run optimizations
    pass

# Check specific features
if is_snapshot_first_enabled():
    # Use snapshot-first instead of screenshots
    pass

if is_token_optimizer_enabled():
    # Apply token compression
    pass

if is_devtools_enabled():
    # Capture console/network errors
    pass

if is_cdp_enabled():
    # Try to connect to existing Chrome
    pass
```

### Get configuration values

```python
# Get token budget
budget = get_token_budget()  # Returns 8000 by default

# Get CDP port
port = get_cdp_port()  # Returns 9222 by default

# Get any setting by path
max_depth = get_optimization_setting('optimization.token_optimizer.max_tree_depth', 5)
cache_ttl = get_optimization_setting('optimization.snapshot_first.cache_ttl_seconds', 30)
```

### Natural language trigger matching

```python
# Check if user wants to use CDP
user_input = "use my chrome with my logins"
if matches_trigger(user_input, 'use_cdp'):
    # Connect to existing Chrome via CDP
    pass

# Check for extraction requests
user_input = "extract all links from this page"
if matches_trigger(user_input, 'extract_links'):
    # Use quick extraction without LLM
    pass

# Check for error debugging
user_input = "show me what failed"
if matches_trigger(user_input, 'show_errors'):
    # Display DevTools logs
    pass
```

## Environment Variable Overrides

Users can override settings via environment variables:

```bash
# Disable all optimizations
export EVERSALE_OPTIMIZATION_ENABLED=false

# Disable snapshot-first only
export EVERSALE_SNAPSHOT_FIRST=false

# Lower token budget
export EVERSALE_TOKEN_BUDGET=4000

# Use different CDP port
export EVERSALE_CDP_PORT=9333

# Disable DevTools hooks
export EVERSALE_DEVTOOLS_ENABLED=false
```

## Example: Snapshot-First Module

```python
from config_loader import is_snapshot_first_enabled, get_optimization_setting

class SnapshotFirst:
    def __init__(self):
        self.enabled = is_snapshot_first_enabled()
        self.cache_ttl = get_optimization_setting('optimization.snapshot_first.cache_ttl_seconds', 30)
        self.max_elements = get_optimization_setting('optimization.snapshot_first.max_elements', 100)

    async def capture(self, page):
        if not self.enabled:
            return await page.screenshot()  # Fallback to screenshot

        # Use snapshot instead
        snapshot = await page.accessibility.snapshot()
        return self._compress_snapshot(snapshot)
```

## Example: Token Optimizer Module

```python
from config_loader import is_token_optimizer_enabled, get_token_budget, get_optimization_setting

class TokenOptimizer:
    def __init__(self):
        self.enabled = is_token_optimizer_enabled()
        self.token_budget = get_token_budget()
        self.max_text_length = get_optimization_setting('optimization.token_optimizer.max_text_length', 200)
        self.max_tree_depth = get_optimization_setting('optimization.token_optimizer.max_tree_depth', 5)

    def compress(self, snapshot):
        if not self.enabled:
            return snapshot  # No compression

        # Apply compression rules
        return self._compress_tree(snapshot, max_depth=self.max_tree_depth)
```

## Example: DevTools Module

```python
from config_loader import is_devtools_enabled, get_optimization_setting

class DevToolsHooks:
    def __init__(self):
        self.enabled = is_devtools_enabled()
        self.capture_network = get_optimization_setting('optimization.devtools.capture_network', True)
        self.capture_console = get_optimization_setting('optimization.devtools.capture_console', True)
        self.max_log_size = get_optimization_setting('optimization.devtools.max_log_size', 500)

    async def attach(self, page):
        if not self.enabled:
            return

        if self.capture_console:
            page.on('console', self._handle_console)

        if self.capture_network:
            page.on('requestfailed', self._handle_network_error)
```

## Example: CDP Connection Module

```python
from config_loader import is_cdp_enabled, get_cdp_port, get_optimization_setting, matches_trigger

class CDPConnector:
    def __init__(self):
        self.enabled = is_cdp_enabled()
        self.port = get_cdp_port()
        self.prefer_existing = get_optimization_setting('optimization.cdp.prefer_existing', True)

    async def connect(self, user_input: str = None):
        if not self.enabled:
            return None

        # Check if user explicitly wants CDP
        if user_input and matches_trigger(user_input, 'use_cdp'):
            return await self._connect_to_chrome(self.port)

        # Auto-detect if preferred
        if self.prefer_existing:
            try:
                return await self._connect_to_chrome(self.port)
            except:
                return None  # Fall back to new browser

        return None
```

## Reloading Configuration

If you need to reload configuration at runtime (e.g., after user changes settings):

```python
from config_loader import reload_config

# Reload all configs
reload_config()
```

## Adding New Settings

To add new optimization settings:

1. Add to `/mnt/c/ev29/cli/engine/agent/config/browser_optimizations.yaml`:

```yaml
optimization:
  my_new_feature:
    enabled: true
    threshold: 100
    mode: 'aggressive'
```

2. Add helper functions in `config_loader.py`:

```python
def is_my_feature_enabled() -> bool:
    if not is_optimization_enabled():
        return False
    return get_optimization_setting('optimization.my_new_feature.enabled', True)

def get_my_feature_threshold() -> int:
    return get_optimization_setting('optimization.my_new_feature.threshold', 100)
```

3. Use in your module:

```python
from config_loader import is_my_feature_enabled, get_my_feature_threshold

if is_my_feature_enabled():
    threshold = get_my_feature_threshold()
    # Your logic here
```

## Best Practices

1. **Always check master switch**: Use `is_optimization_enabled()` before running optimizations
2. **Provide sensible defaults**: Use default parameter in `get_optimization_setting()`
3. **Respect user overrides**: Environment variables always win
4. **Fall back gracefully**: If optimization fails, fall back to standard behavior
5. **Log decisions**: Use logger to show which optimizations are active

```python
from loguru import logger
from config_loader import is_snapshot_first_enabled

if is_snapshot_first_enabled():
    logger.info("Snapshot-first mode enabled - reducing screenshot usage by 85%")
else:
    logger.info("Snapshot-first disabled - using standard screenshot mode")
```
