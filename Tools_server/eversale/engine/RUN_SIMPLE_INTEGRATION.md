# run_simple.py - Integration Guide

**Version:** 2.9
**Date:** 2025-12-12

---

## Integration with Existing Codebase

### File Locations

```
/mnt/c/ev29/cli/engine/
    |
    +-- run_simple.py                    # NEW: Main entry point (16KB)
    +-- RUN_SIMPLE_QUICKSTART.md         # NEW: User guide (11KB)
    +-- RUN_SIMPLE_SUMMARY.md            # NEW: Implementation summary (9KB)
    +-- RUN_SIMPLE_INTEGRATION.md        # NEW: This file
    |
    +-- run_ultimate.py                  # EXISTING: Complex workflows
    |
    +-- agent/
        +-- llm_client.py                # USED: LLM integration
        +-- accessibility_element_finder.py  # USED: Element finding
        +-- (other modules...)
```

---

## Dependencies

### Python Modules (All Existing)

| Module | Usage | Location |
|--------|-------|----------|
| `agent.llm_client.LLMClient` | AI planning | `/mnt/c/ev29/cli/engine/agent/llm_client.py` |
| `agent.accessibility_element_finder.AccessibilityTreeParser` | Element parsing | `/mnt/c/ev29/cli/engine/agent/accessibility_element_finder.py` |
| `playwright.async_api` | Browser automation | Installed via npm/pip |
| `loguru` | Logging | Installed via pip |

### External Dependencies

```bash
# Python packages (all already installed)
pip install playwright loguru httpx pydantic pyyaml python-dotenv

# Playwright browser
playwright install chromium
```

---

## How to Integrate with npm CLI

### Current npm Entry Point

`/mnt/c/ev29/cli/bin/eversale.js` currently calls `run_ultimate.py`:

```javascript
// Current implementation (simplified)
const pythonPath = findPython();
const scriptPath = path.join(__dirname, '../engine/run_ultimate.py');
spawn(pythonPath, [scriptPath, userGoal], { stdio: 'inherit' });
```

### Proposed Integration (Option A: Make Default)

Replace `run_ultimate.py` with `run_simple.py` as default:

```javascript
// In bin/eversale.js

const scriptPath = path.join(__dirname, '../engine/run_simple.py');
const args = [scriptPath];

// Pass through CLI arguments
if (program.headless) args.push('--headless');
if (program.maxSteps) args.push('--max-steps', program.maxSteps);
if (program.noLlm) args.push('--no-llm');
if (program.verbose) args.push('--verbose');

args.push(userGoal);

spawn(pythonPath, args, { stdio: 'inherit' });
```

### Proposed Integration (Option B: Side-by-Side)

Keep both, add flag to choose:

```javascript
// In bin/eversale.js

program
  .option('--simple', 'Use simple agent (fast, reliable)')
  .option('--ultimate', 'Use ultimate agent (complex workflows)')
  // ... other options

// Determine which script to use
const scriptName = program.simple ? 'run_simple.py' :
                   program.ultimate ? 'run_ultimate.py' :
                   'run_simple.py'; // default to simple

const scriptPath = path.join(__dirname, '../engine', scriptName);
```

Usage:
```bash
eversale "Task"                    # Uses run_simple.py (default)
eversale --simple "Task"           # Explicitly use run_simple.py
eversale --ultimate "Complex task" # Use run_ultimate.py for complex
```

### Proposed Integration (Option C: Auto-Detect)

Try simple first, fallback to ultimate on failure:

```javascript
// In bin/eversale.js

async function runTask(goal) {
  // Try simple first
  const simpleResult = await runSimple(goal);

  if (simpleResult.success) {
    return simpleResult;
  }

  // Fallback to ultimate for complex cases
  console.log('Task failed with simple agent, trying ultimate...');
  return await runUltimate(goal);
}
```

---

## CLI Arguments Mapping

### run_simple.py Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `goal` | string | (interactive) | Task description |
| `--headless` | flag | false | Headless browser |
| `--max-steps` | int | 20 | Max steps |
| `--no-llm` | flag | false | Disable LLM |
| `--verbose` | flag | false | Verbose output |

### npm CLI Arguments (Proposed)

Add to `bin/eversale.js`:

```javascript
program
  .argument('[goal]', 'Task to perform')
  .option('--headless', 'Run browser in headless mode')
  .option('--max-steps <number>', 'Maximum steps', parseInt, 20)
  .option('--no-llm', 'Disable LLM, use fallback logic')
  .option('-v, --verbose', 'Verbose output')
  .option('--simple', 'Use simple agent (default)')
  .option('--ultimate', 'Use ultimate agent for complex workflows')
```

---

## Environment Variables

### Existing (from llm_client.py)

```bash
# LLM Configuration
EVERSALE_LLM_MODE=remote|local    # Default: remote
EVERSALE_LLM_URL=https://...      # LLM API endpoint
EVERSALE_LLM_TOKEN=xxx            # License key
EVERSALE_LICENSE_KEY=xxx          # Alternative to LLM_TOKEN

# Kimi API (complex reasoning)
KIMI_API_KEY=xxx
```

### No New Environment Variables Required

`run_simple.py` uses the existing LLM configuration from `config.yaml` and environment variables.

---

## Return Value Integration

### Python Return (run_simple.py)

```python
@dataclass
class AgentResult:
    success: bool
    goal: str
    steps_taken: int
    final_url: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
```

### Node.js Integration

```javascript
// Capture Python output
const result = await new Promise((resolve, reject) => {
  let stdout = '';
  let stderr = '';

  const proc = spawn(pythonPath, [scriptPath, ...args]);

  proc.stdout.on('data', (data) => {
    stdout += data.toString();
  });

  proc.stderr.on('data', (data) => {
    stderr += data.toString();
  });

  proc.on('close', (code) => {
    resolve({
      success: code === 0,
      output: stdout,
      error: stderr
    });
  });
});

// Display result
if (result.success) {
  console.log(chalk.green('SUCCESS'));
  console.log(result.output);
} else {
  console.log(chalk.red('FAILED'));
  console.log(result.error);
}
```

---

## Testing Integration

### Unit Tests

```bash
# Test imports
cd /mnt/c/ev29/cli/engine
python3 -c "from run_simple import SimpleAgent; print('OK')"

# Test CLI
python3 run_simple.py --version
python3 run_simple.py --help
```

### Integration Tests

```bash
# Test with npm CLI (after integration)
npm link  # Link local package
eversale --version
eversale --help
eversale "Test task"
```

### End-to-End Tests

```javascript
// In tests/e2e/run_simple.test.js

describe('run_simple.py integration', () => {
  it('should run simple task successfully', async () => {
    const result = await runTask('Navigate to google.com');
    expect(result.success).toBe(true);
    expect(result.final_url).toContain('google.com');
  });

  it('should handle --no-llm flag', async () => {
    const result = await runTask('Test task', { noLlm: true });
    expect(result.success).toBe(true);
  });

  it('should respect --max-steps', async () => {
    const result = await runTask('Complex task', { maxSteps: 5 });
    expect(result.steps_taken).toBeLessThanOrEqual(5);
  });
});
```

---

## Backwards Compatibility

### Maintaining run_ultimate.py

Keep `run_ultimate.py` for:
- Complex multi-step workflows
- Production-critical automation
- Tasks requiring advanced recovery
- Existing scripts/integrations

**No breaking changes required.**

### Migration Strategy

1. **Phase 1: Soft Launch (v2.9)**
   - Add run_simple.py alongside run_ultimate.py
   - Default to run_ultimate.py (no behavior change)
   - Users can opt-in with `--simple` flag

2. **Phase 2: Testing (v2.9.1)**
   - Collect feedback on run_simple.py
   - Fix bugs and edge cases
   - Document use cases for each

3. **Phase 3: Switch Default (v3.0)**
   - Make run_simple.py the default
   - Keep run_ultimate.py available with `--ultimate` flag
   - Update documentation

4. **Phase 4: Optimize (v3.1+)**
   - Auto-detection: Try simple, fallback to ultimate
   - Intelligent routing based on task complexity
   - User preference setting

---

## Configuration File Integration

### config.yaml (Existing)

```yaml
llm:
  mode: remote
  remote_url: https://eversale.io/api/llm
  main_model: qwen3:8b
  vision_model: 0000/ui-tars-1.5-7b:latest
  temperature: 0.1
  max_tokens: 4096
  timeout_seconds: 120
```

### No Changes Required

`run_simple.py` uses the same `LLMClient` as `run_ultimate.py`, so it inherits all configuration from `config.yaml`.

---

## Logging Integration

### Current Logging (loguru)

Both `run_simple.py` and `run_ultimate.py` use `loguru` for logging.

### Log Levels

```python
from loguru import logger

logger.debug("Browser initialized")    # DEBUG
logger.info("Starting agent")          # INFO
logger.warning("Max steps reached")    # WARNING
logger.error("Action failed")          # ERROR
```

### Configure Logging

```bash
# Set log level via environment
export LOGURU_LEVEL=DEBUG
python run_simple.py "Task"

# Or in code
import sys
from loguru import logger

logger.remove()
logger.add(sys.stderr, level="INFO")
```

---

## Error Handling

### Python Side (run_simple.py)

```python
try:
    result = await agent.run(goal)
    return 0 if result.success else 1
except Exception as e:
    logger.error(f"Fatal error: {e}")
    return 1
```

### Node.js Side (bin/eversale.js)

```javascript
proc.on('close', (code) => {
  if (code === 0) {
    console.log(chalk.green('Task completed successfully'));
  } else {
    console.log(chalk.red('Task failed'));
    process.exit(code);
  }
});

proc.on('error', (err) => {
  console.error(chalk.red('Failed to start agent:'), err.message);
  process.exit(1);
});
```

---

## Performance Monitoring

### Metrics to Track

```javascript
// In npm CLI
const startTime = Date.now();

// ... run task ...

const duration = Date.now() - startTime;
console.log(`Task completed in ${duration}ms`);

// Log to analytics
analytics.track('task_completed', {
  agent: 'simple',
  duration,
  steps: result.steps_taken,
  success: result.success
});
```

### Comparison Dashboard

Track metrics for both agents:

| Metric | run_simple.py | run_ultimate.py |
|--------|---------------|-----------------|
| Avg duration | 5-15s | 15-45s |
| Success rate | 85% | 90% |
| LLM calls | 3-8 | 10-30 |
| Use cases | Simple tasks | Complex workflows |

---

## Documentation Updates

### Files to Update

1. **README.md** - Add run_simple.py to quick start
2. **CAPABILITY_REPORT.md** - Add v2.9 section
3. **package.json** - Bump version to 2.9.0
4. **CHANGELOG.md** - Document new entry point

### Example README Update

```markdown
## Quick Start

### Simple Tasks (Fast)

```bash
eversale "Search Google for AI news"
eversale --headless "Navigate to github.com"
```

Uses `run_simple.py` - Fast, reliable, accessibility-first approach.

### Complex Workflows

```bash
eversale --ultimate "Multi-step complex workflow"
```

Uses `run_ultimate.py` - Advanced recovery, memory, multi-agent support.
```

---

## Rollout Plan

### Week 1: Internal Testing

- Test run_simple.py with common tasks
- Fix bugs and edge cases
- Gather performance metrics

### Week 2: Beta Release

- Publish v2.9.0-beta with run_simple.py
- Keep run_ultimate.py as default
- Allow opt-in with `--simple` flag
- Collect user feedback

### Week 3: Stability

- Fix reported issues
- Optimize performance
- Update documentation

### Week 4: General Availability

- Publish v2.9.0 stable
- Make run_simple.py default
- Keep run_ultimate.py available with `--ultimate` flag
- Announce in release notes

---

## Success Metrics

### Targets for v2.9

- [ ] 50% faster average task completion
- [ ] 90%+ success rate on simple tasks
- [ ] 80% of users don't need to use --ultimate flag
- [ ] Zero breaking changes for existing users
- [ ] Positive user feedback on simplicity

### Monitoring

```javascript
// Track which agent is being used
analytics.track('agent_used', {
  agent: isSimple ? 'simple' : 'ultimate',
  task_type: classifyTask(goal),
  success: result.success,
  duration: taskDuration
});

// Alert if run_simple.py failure rate > 15%
if (simpleFailureRate > 0.15) {
  alert('run_simple.py failure rate high, investigate');
}
```

---

## Troubleshooting Integration

### Issue: Python script not found

**Cause:** Incorrect path in npm CLI

**Fix:**
```javascript
const scriptPath = path.resolve(__dirname, '../engine/run_simple.py');
if (!fs.existsSync(scriptPath)) {
  console.error('Script not found:', scriptPath);
  process.exit(1);
}
```

---

### Issue: Arguments not passing through

**Cause:** Incorrect argument parsing

**Fix:**
```javascript
// Debug argument passing
console.log('Python args:', args);

// Ensure args are strings
args = args.map(arg => String(arg));
```

---

### Issue: Output not showing

**Cause:** Missing stdio: 'inherit'

**Fix:**
```javascript
// Use stdio: 'inherit' for real-time output
spawn(pythonPath, args, { stdio: 'inherit' });

// Or capture and display
proc.stdout.on('data', (data) => {
  process.stdout.write(data);
});
```

---

## See Also

- `/mnt/c/ev29/cli/engine/RUN_SIMPLE_QUICKSTART.md` - User guide
- `/mnt/c/ev29/cli/engine/RUN_SIMPLE_SUMMARY.md` - Implementation details
- `/mnt/c/ev29/cli/CAPABILITY_REPORT.md` - Full capabilities
- `/mnt/c/ev29/cli/CLAUDE.md` - Development guide

---

**Integration Status:** Ready for beta testing
**Next Step:** Integrate with npm CLI (bin/eversale.js)
