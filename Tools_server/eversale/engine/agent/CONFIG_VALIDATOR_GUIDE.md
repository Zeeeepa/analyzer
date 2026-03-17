# Config Validator Guide

The Config Validator is a comprehensive startup validation system for Eversale that checks configuration, dependencies, network connectivity, and more.

## Features

### 1. **Config File Validation**
- Checks if `config/config.yaml` exists and is valid YAML
- Validates required sections (agent, llm, browser, timing, logging)
- Checks value ranges (timeouts > 0, temperature 0-2, etc.)

### 2. **Environment Validation**
- Checks if `.env` file exists
- Validates environment variables (URLs, paths)
- Detects local vs remote mode (.eversale-local marker)

### 3. **Dependency Checks**
- **Python Packages**: Verifies all required packages are importable
- **Ollama**: Checks if running and has required models
- **Playwright**: Verifies browsers are installed

### 4. **Network Checks**
- Tests connectivity to LLM endpoint (Ollama or eversale.io)
- Verifies general internet connectivity

### 5. **Permission Checks**
- Validates write access to output directory
- Checks config directory permissions

### 6. **Helpful Error Messages**
Each validation issue includes:
- Clear description of the problem
- Fix command (e.g., `ollama pull moondream`)
- Fix description (what the command does)

### 7. **Auto-Fix Mode**
Automatically attempts to fix issues:
- Pull missing Ollama models
- Install Playwright browsers
- Create missing directories

## Usage

### Command Line

```bash
# Quick validation (startup check)
python3 -m agent.config_validator --quick

# Full validation
python3 -m agent.config_validator

# Full validation with auto-fix
python3 -m agent.config_validator --auto-fix

# Don't exit on errors (for testing)
python3 -m agent.config_validator --no-exit
```

### Python API

```python
from agent.config_validator import (
    validate_config,
    quick_validate,
    validate_on_startup,
    ConfigValidator
)

# Quick validation (async)
import asyncio
success = asyncio.run(quick_validate())

# Startup hook (sync - for brain initialization)
success = validate_on_startup(skip=False)

# Full validation with auto-fix
success, report = asyncio.run(validate_config(
    auto_fix=True,
    exit_on_error=False
))

# Custom validation
validator = ConfigValidator()
report = asyncio.run(validator.validate_all(auto_fix=False))

print(f"Passed: {len(report.passed)}")
print(f"Errors: {len(report.errors)}")
print(f"Warnings: {len(report.warnings)}")
```

### Integration with Brain

To integrate validation into the EnhancedBrain startup:

```python
# In brain_enhanced_v2.py __init__ method
from .config_validator import validate_on_startup

def __init__(self, config: dict, mcp_client):
    # Run startup validation
    if not validate_on_startup(skip=False):
        logger.error("Validation failed - cannot start brain")
        raise RuntimeError("Configuration validation failed")

    # Continue with normal initialization...
    self.config = config
    # ...
```

### Environment Variable

Skip validation entirely (for testing/debugging):

```bash
export EVERSALE_SKIP_VALIDATION=true
```

## Validation Report Structure

```python
@dataclass
class ValidationReport:
    passed: List[str]           # List of passing checks
    issues: List[ValidationIssue]  # All issues found

    @property
    def errors(self) -> List[ValidationIssue]      # Critical errors

    @property
    def warnings(self) -> List[ValidationIssue]    # Should fix

    @property
    def infos(self) -> List[ValidationIssue]       # Optional

    @property
    def has_errors(self) -> bool

    @property
    def has_warnings(self) -> bool
```

### ValidationIssue Structure

```python
@dataclass
class ValidationIssue:
    type: ValidationType        # CONFIG, ENVIRONMENT, DEPENDENCY, NETWORK, PERMISSION
    severity: Severity          # ERROR, WARNING, INFO
    message: str                # Description of the problem
    fix_command: Optional[str]  # Command to fix (e.g., "ollama pull model")
    fix_description: Optional[str]  # What the fix does
    auto_fixable: bool          # Can auto-fix attempt to fix this?
```

## Severity Levels

| Severity | Meaning | Action Required |
|----------|---------|-----------------|
| **ERROR** | Must be fixed before running | Blocks startup |
| **WARNING** | Should be fixed but not blocking | Agent can run but may have issues |
| **INFO** | Optional improvements | Nice to have |

## Validation Types

| Type | Checks |
|------|--------|
| **CONFIG** | YAML syntax, required sections, value ranges |
| **ENVIRONMENT** | .env file, environment variables, paths |
| **DEPENDENCY** | Python packages, Ollama, Playwright browsers |
| **NETWORK** | LLM endpoint, internet connectivity |
| **PERMISSION** | Output directory, config directory |

## Example Output

### Quick Validation (Startup)
```
2025-12-07 19:27:46.496 | SUCCESS | Quick validation passed ✓
```

### Full Validation (With Issues)
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

⚠ 1 warning (SHOULD FIX)
  • .env file not found (using defaults)
    Fix: cp .env.example .env

ℹ 1 info items (OPTIONAL)
  • Optional package 'patchright' not found (enhanced features disabled)
    Fix: pip install patchright
============================================================
Cannot start Eversale due to configuration errors. Fix the issues above and try again.
```

### Full Validation (All Pass)
```
============================================================
CONFIGURATION VALIDATION SUMMARY
============================================================
✓ 30 checks passed
============================================================
All validation checks passed! ✨
```

## Auto-Fix Capabilities

The auto-fix mode can automatically fix:

1. **Missing Ollama Models**
   - Runs: `ollama pull <model_name>`
   - Timeout: 5 minutes per model

2. **Missing Playwright Browsers**
   - Runs: `python3 -m playwright install chromium`
   - Timeout: 5 minutes

3. **Missing Directories**
   - Creates directories with proper permissions
   - Example: Output directory

Auto-fix **cannot** fix:
- Missing Ollama installation (needs manual install)
- Network connectivity issues
- Invalid config file syntax (needs manual editing)
- Permission errors (needs manual chmod/chown)

## Checks Performed

### Config File Checks
- ✓ Config file exists
- ✓ Valid YAML syntax
- ✓ Required sections present (agent, llm, browser, timing, logging)
- ✓ Timeout values > 0
- ✓ Temperature in range 0-2
- ✓ Model names specified

### Environment Checks
- ✓ .env file exists (warning if missing)
- ✓ OLLAMA_BASE_URL is valid URL
- ✓ EVERSALE_BROWSER_PROFILE exists (if set)
- ✓ EVERSALE_OUTPUT_DIR writable (if set)

### Python Package Checks

**Required:**
- ✓ pyyaml
- ✓ httpx
- ✓ playwright
- ✓ loguru
- ✓ python-dotenv
- ✓ rich
- ✓ psutil

**Optional (info warnings):**
- ✓ patchright (undetected Playwright)
- ✓ curl_cffi (TLS fingerprinting)
- ✓ scipy (Bezier curves)
- ✓ numpy (required by scipy)

### Ollama Checks (Local Mode Only)
- ✓ Ollama installed
- ✓ Ollama running and accessible
- ✓ Required models available:
  - `llm.main_model` (e.g., llama3.1:8b)
  - `llm.fast_model` (e.g., qwen2.5:3b-instruct)
  - `llm.vision_model` (e.g., moondream)

### Playwright Checks
- ✓ Playwright CLI available
- ✓ Chromium browser installed

### Network Checks
- ✓ Can reach LLM endpoint (Ollama or eversale.io)
- ✓ Can reach google.com (internet test)

### Permission Checks
- ✓ Output directory writable
- ✓ Config directory accessible

## Tips

### Development Workflow

```bash
# 1. First time setup - auto-fix everything
python3 -m agent.config_validator --auto-fix

# 2. Quick health check
python3 -m agent.config_validator --quick

# 3. Full check without auto-fix
python3 -m agent.config_validator --no-exit
```

### CI/CD Integration

```bash
# In CI pipeline
python3 -m agent.config_validator --quick --no-exit
if [ $? -ne 0 ]; then
  echo "Configuration validation failed"
  exit 1
fi
```

### Docker Integration

```dockerfile
# Add to Dockerfile
RUN python3 -m agent.config_validator --auto-fix

# Or add as healthcheck
HEALTHCHECK --interval=30s --timeout=10s \
  CMD python3 -m agent.config_validator --quick || exit 1
```

## Troubleshooting

### "Config file not found"
```bash
# Fix: Create from template
cp config/config.yaml.example config/config.yaml
```

### "Ollama not running"
```bash
# Fix: Start Ollama
ollama serve
```

### "Required model 'moondream' not found"
```bash
# Fix: Pull model
ollama pull moondream
```

### "Playwright browsers not installed"
```bash
# Fix: Install browsers
python3 -m playwright install
```

### "Cannot connect to eversale.io"
```bash
# Check internet connectivity
curl -I https://eversale.io

# Or switch to local mode
touch .eversale-local
```

### Validation takes too long
```bash
# Use quick validation instead
python3 -m agent.config_validator --quick
```

### Skip validation for testing
```bash
# Set environment variable
export EVERSALE_SKIP_VALIDATION=true

# Or in code
validate_on_startup(skip=True)
```

## Future Enhancements

Potential additions:
- [ ] GPU availability check
- [ ] Disk space check
- [ ] Port availability check (11434 for Ollama)
- [ ] Browser profile validation
- [ ] MCP server connectivity check
- [ ] License validation (for CLI users)
- [ ] Config file auto-repair (not just validation)
- [ ] Performance benchmarking
- [ ] Security audit (check for exposed credentials)

## Related Files

- `/mnt/c/ev29/agent/config_validator.py` - Main validator implementation
- `/mnt/c/ev29/agent/config_loader.py` - Configuration loading utilities
- `/mnt/c/ev29/config/config.yaml` - Main configuration file
- `/mnt/c/ev29/.env.example` - Environment variable template
- `/mnt/c/ev29/test_config_validator.py` - Comprehensive test suite

