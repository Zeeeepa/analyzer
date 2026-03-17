# Browser Optimization Configuration

This directory contains the browser optimization configuration system for the Eversale CLI agent.

## Files

| File | Purpose |
|------|---------|
| `browser_optimizations.yaml` | Browser optimization settings (snapshot-first, token optimizer, DevTools, CDP) |
| `OPTIMIZATION_USAGE.md` | Developer guide for using the optimization config |
| `README.md` | This file |

## Quick Start

### Loading Configuration

```python
from config_loader import (
    is_optimization_enabled,
    is_snapshot_first_enabled,
    get_token_budget,
    matches_trigger
)

# Check if feature is enabled
if is_snapshot_first_enabled():
    # Use snapshot instead of screenshot
    pass

# Get configuration value
budget = get_token_budget()  # Returns 8000 by default

# Match natural language triggers
if matches_trigger(user_input, 'use_cdp'):
    # User wants to use existing Chrome
    pass
```

### Environment Overrides

Users can override settings without editing the config file:

```bash
export EVERSALE_OPTIMIZATION_ENABLED=false  # Disable all optimizations
export EVERSALE_SNAPSHOT_FIRST=false        # Disable snapshot-first only
export EVERSALE_TOKEN_BUDGET=4000           # Lower token budget
export EVERSALE_CDP_PORT=9333               # Use different CDP port
export EVERSALE_DEVTOOLS_ENABLED=false      # Disable DevTools hooks
```

## Configuration Structure

```yaml
optimization:
  enabled: true  # Master switch

  snapshot_first:
    enabled: true
    cache_ttl_seconds: 30
    max_elements: 100

  token_optimizer:
    enabled: true
    token_budget: 8000
    max_text_length: 200

  devtools:
    enabled: true
    capture_network: true

  cdp:
    auto_detect: true
    default_port: 9222

triggers:
  use_cdp:
    - 'use my chrome'
    - 'existing chrome'
  extract_links:
    - 'extract links'
    - 'get all links'
```

## API Reference

### Feature Flags

- `is_optimization_enabled()` - Master switch for all optimizations
- `is_snapshot_first_enabled()` - Check if snapshot-first mode is on
- `is_token_optimizer_enabled()` - Check if token optimizer is on
- `is_devtools_enabled()` - Check if DevTools hooks are on
- `is_cdp_enabled()` - Check if CDP/session reuse is on

### Value Getters

- `get_token_budget()` - Get token budget (default: 8000)
- `get_cdp_port()` - Get CDP port (default: 9222)
- `get_optimization_setting(key, default)` - Get any setting by path

### Trigger Matching

- `matches_trigger(user_input, category)` - Check if input matches trigger

### Advanced

- `load_browser_optimizations()` - Load full config dict
- `reload_config()` - Clear cache and reload all configs

## Testing

Run the test script to verify configuration loading:

```bash
cd /mnt/c/ev29/cli
python3 test_optimization_config.py
```

Test with environment overrides:

```bash
EVERSALE_TOKEN_BUDGET=4000 python3 test_optimization_config.py
```

## Default Settings

All optimizations are **enabled by default** with sensible settings:

- Snapshot-first: ON (85% fewer screenshots)
- Token optimizer: ON (70% token reduction)
- DevTools hooks: ON (auto error capture)
- CDP auto-detect: ON (reuse existing Chrome)
- Token budget: 8000
- CDP port: 9222

Users can disable features via environment variables or by editing the YAML file.

## See Also

- `OPTIMIZATION_USAGE.md` - Detailed usage guide with examples
- `../config_loader.py` - Python implementation
- `../snapshot_first.py` - Example optimization module (if exists)
- `../token_optimizer.py` - Example optimization module (if exists)
