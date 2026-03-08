# Config Validator - Quick Reference

**Purpose:** Validate Eversale configuration on startup with helpful error messages and auto-fix capabilities.

## Quick Start

```bash
# Full validation with auto-fix (recommended first time)
python3 -m agent.config_validator --auto-fix

# Quick validation (for startup)
python3 -m agent.config_validator --quick

# Full validation without auto-fix
python3 -m agent.config_validator
```

## What It Validates

✅ **Config file** - Exists, valid YAML, correct values
✅ **Environment** - .env file, variables, paths
✅ **Dependencies** - Python packages, Ollama, Playwright
✅ **Network** - LLM endpoint, internet connectivity
✅ **Permissions** - Output directory, config directory

## Example Output

### ✓ All Pass
```
============================================================
CONFIGURATION VALIDATION SUMMARY
============================================================
✓ 30 checks passed
============================================================
All validation checks passed! ✨
```

### ✗ With Issues
```
============================================================
CONFIGURATION VALIDATION SUMMARY
============================================================
✓ 27 checks passed

✗ 2 errors found (MUST FIX)
  • Required model 'moondream' not found in Ollama
    Fix: ollama pull moondream
  • Playwright browsers not installed
    Fix: python3 -m playwright install
============================================================
Cannot start Eversale due to configuration errors.
```

## Auto-Fix Capabilities

| Issue | Auto-Fix Action |
|-------|-----------------|
| Missing Ollama model | `ollama pull <model>` |
| Missing Playwright browsers | `python3 -m playwright install` |
| Missing directories | `mkdir -p <path>` |

## Python API

```python
from agent.config_validator import validate_on_startup

# In brain __init__
def __init__(self, config: dict, mcp_client):
    # Validate on startup
    if not validate_on_startup():
        raise RuntimeError("Validation failed")
    # Continue...
```

## Skip Validation

```bash
# For testing/debugging
export EVERSALE_SKIP_VALIDATION=true
```

## Files

- **`config_validator.py`** (912 lines) - Main implementation
- **`CONFIG_VALIDATOR_GUIDE.md`** - Full documentation
- **`test_config_validator.py`** - Test suite

## Common Fixes

```bash
# Missing config
cp config/config.yaml.example config/config.yaml

# Ollama not running
ollama serve

# Missing model
ollama pull moondream

# Missing browsers
python3 -m playwright install

# Missing env file
cp .env.example .env
```

See **CONFIG_VALIDATOR_GUIDE.md** for full documentation.
