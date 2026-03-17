# Flash Mode / Fast Mode Conflict Analysis Report

## Executive Summary
Search reveals **MULTIPLE SPEED/SIMPLIFICATION MECHANISMS** already implemented in the codebase that could conflict with the new `flash_mode` in `simple_agent.py`:

1. **Fast Mode** (`fast_mode.py`) - Pattern-matching executor that bypasses LLM
2. **Flash Mode** (`simple_agent.py`) - Simplified prompt for fast reasoning
3. **Plan/Build Mode System** (`plan_mode.py`, `brain_config.py`) - Mode-based tool permission system
4. **Fast Model / Fast Mode Executor** (`brain_enhanced_v2.py`) - Optional LLM model switching

---

## CRITICAL CONFLICT 1: Fast Mode vs Flash Mode Naming

### Locations
- **Fast Mode**: `/mnt/c/ev29/cli/engine/agent/fast_mode.py` (entire module)
- **Flash Mode**: `/mnt/c/ev29/cli/engine/agent/simple_agent.py` (lines 86-103, 110, 115, 126-134, 154-158, 400, 423-431)

### The Conflict
Both are **execution speed optimization mechanisms** but operate at different layers:

#### Fast Mode (Lower Layer - Pattern Matching)
```python
# fast_mode.py - Bypasses LLM entirely
class FastModeExecutor:
    async def try_execute(self, prompt: str) -> FastModeResult:
        # 1. Pattern match the prompt
        # 2. If high confidence match -> execute directly via MCP
        # 3. Else -> return executed=False to fall back to LLM
```

**Characteristics:**
- Operates BEFORE LLM is called
- Skips reasoning entirely via pattern matching
- Returns `executed=False` for fallback
- Examples: "go to google.com", "click Login", "type hello in search"
- Success rate check: `confidence < 0.8` -> fallback

#### Flash Mode (Upper Layer - Simplified Prompt)
```python
# simple_agent.py - Uses simplified LLM prompt
def _call_llm(self, prompt: str) -> str:
    system_prompt = self.FLASH_MODE_PROMPT if self.flash_mode else self.SYSTEM_PROMPT
    # Both go through LLM, but FLASH_MODE_PROMPT is shorter

FLASH_MODE_PROMPT = '''No thinking, no evaluation, no explanation. Just action and memory.'''
```

**Characteristics:**
- Operates during LLM call (reduces tokens)
- Still uses LLM reasoning
- Shorter system prompt
- Better for simple single-action tasks

### The Problem
- **Same name would be confusing**: "flash_mode" vs "fast_mode" are semantically equivalent
- **Different execution paths**: Fast mode pattern match happens BEFORE any LLM call
- **Configuration conflict**:
  - `a11y_config.py:189` has `ENABLE_FLASH_MODE = False`
  - `fast_mode.py:336` checks `config.get('fast_mode', {})`
  - These are different config keys!

---

## CONFLICT 2: Auto-Detection Logic Overlap

### Locations
1. **Flash Mode Auto-Detection** (`simple_agent.py:126-134`)
   ```python
   def _should_use_flash_mode(self, goal: str) -> bool:
       simple_patterns = [
           "click", "type", "fill", "navigate to", "go to",
           "search for", "enter", "submit", "login"
       ]
       goal_lower = goal.lower()
       return any(p in goal_lower for p in simple_patterns) and len(goal.split()) < 15
   ```

2. **Fast Mode Auto-Detection** (`fast_mode.py:322-364`)
   ```python
   def should_use_fast_mode(prompt: str, config: Optional[Dict] = None) -> bool:
       complexity_indicators = [
           'and then', 'after that', 'followed by', 'if ', 'when ',
           'unless', 'extract all', 'scrape all', 'loop through',
           'for each', 'until', 'while',
       ]
   ```

### The Problem
- **Different detection criteria**: Flash checks for simple patterns, Fast checks for complexity keywords
- **No coordination**: Both can activate independently
- **Execution order unclear**: If both try to activate, what happens?
  - Does Fast mode intercept before Flash mode gets called?
  - Or does Flash mode prompt override Fast mode detection?

### Config Conflict
- **Flash mode config** (`a11y_config.py:189-190`)
  ```python
  ENABLE_FLASH_MODE = False
  FLASH_MODE_AUTO_DETECT = True
  ```
- **Fast mode config** (`fast_mode.py` has no corresponding config in `a11y_config.py`)
  - Uses config dict at runtime, not centralized config
  - No way to enable/disable from `a11y_config.py`

---

## CONFLICT 3: Multiple Mode Systems

### The Broader Mode Landscape
The codebase has **AT LEAST 4 mode systems**:

1. **Plan/Build/Review/Debug/Docs/Safe Modes** (`brain_config.py:126`)
   - Controls tool permissions
   - Not related to speed/simplification

2. **Agent Mode Enum** (`agentic_orchestrator.py:79`)
   - Various orchestration modes
   - Independent from speed optimization

3. **Plan Mode System** (`plan_mode.py`)
   - Read-only planning before execution
   - Tracks `PlanState` with `active` boolean

4. **Fast/Flash Speed Modes** (NEW)
   - Fast mode pattern matching
   - Flash mode simplified prompt

### The Hazard
- When adding flash_mode to simple_agent.py, you're introducing a **5th mode concept**
- The system already has complex mode-switching logic
- No unified mode selection/dispatch mechanism
- Prompts differ across modes (see system_prompts.py)

---

## CONFLICT 4: Prompt Selection Logic Inconsistency

### Locations
1. **system_prompts.py:268** - Mode-based prompt selection
   ```python
   def get_system_prompt(mode: str = "build", include_browser: bool = True) -> str:
       if mode == "plan":
           parts.append(PLAN_MODE_PROMPT)
       else:
           parts.append(BUILD_MODE_PROMPT)
   ```

2. **simple_agent.py:400** - Flash mode prompt selection
   ```python
   system_prompt = self.FLASH_MODE_PROMPT if self.flash_mode else self.SYSTEM_PROMPT
   ```

3. **fast_mode.py** - No prompt selection (uses MCP directly)

### The Problem
- **Simple_agent hardcodes prompts** - doesn't use `get_system_prompt()`
- **No integration with system_prompts.py** - new prompts not in unified location
- **Three different prompt selection mechanisms**:
  - system_prompts.py uses mode string parameter
  - simple_agent.py uses boolean flag
  - fast_mode.py doesn't use prompts

---

## CONFLICT 5: Brain Integration Point

### Location
`brain_enhanced_v2.py:1145-1153`

```python
if FAST_MODE_AVAILABLE and FastModeExecutor:
    self.fast_mode_executor = FastModeExecutor(
        mcp_client=self.mcp,
        enabled=True,  # Enable by default
        verbose=False
    )
```

### The Problem
- `fast_mode_executor` is created in brain but **NEVER CALLED**
  - Grep shows no `.try_execute()` calls in the codebase
  - Created as instance variable but unused
  - Dead code or leftover from refactoring?

- **Simple_agent doesn't know about brain's fast_mode_executor**
  - They operate independently
  - Could conflict if both are active

---

## Configuration File Analysis

### `a11y_config.py` (Lines 188-190)
```python
# Flash mode - skip reasoning for simple tasks (30-40% reduction)
ENABLE_FLASH_MODE = False  # Disabled by default, enable per-task
FLASH_MODE_AUTO_DETECT = True  # Auto-enable for simple goals
```

**Issues:**
- Only controls simple_agent flash mode
- No config for fast_mode.py (it reads from runtime dict)
- No unified on/off switch

---

## Detection Method Comparison

| Aspect | Fast Mode | Flash Mode |
|--------|-----------|-----------|
| Detection | Pattern matching on keywords | Pattern matching on keywords |
| Trigger | Multi-task keywords | Simple action keywords |
| Examples | "and then", "if ", "loop" | "click", "type", "navigate" |
| Config | Runtime dict | `a11y_config.ENABLE_FLASH_MODE` |
| Auto-detect | No auto-detect config | `FLASH_MODE_AUTO_DETECT = True` |
| Prompt impact | N/A (no LLM) | Reduced system prompt |
| Execution path | MCP direct call | LLM + action execution |

---

## Execution Path Divergence

```
User Input
    |
    +-- Fast Mode Detection? (fast_mode.py:322)
    |       |
    |       +--YES (high confidence pattern) -> Direct MCP call -> Result
    |       |
    |       +--NO (low confidence) -> fallback to LLM path
    |
    +-- Flash Mode Detection? (simple_agent.py:126-134)
            |
            +--YES (simple patterns + <15 words) -> Auto-enable flash_mode
            |       |
            |       +-- LLM call with FLASH_MODE_PROMPT (simplified)
            |
            +--NO (complex task) -> Auto-disable flash_mode
                    |
                    +-- LLM call with SYSTEM_PROMPT (full)
```

**Problem:** If Fast Mode returns `executed=False`, does it then check Flash Mode? Or does it go straight to full LLM?

---

## Summary of Conflicts

| # | Conflict | Severity | Impact |
|---|----------|----------|--------|
| 1 | Fast Mode vs Flash Mode naming | HIGH | Confusion, similar functionality |
| 2 | Auto-detection logic overlap | MEDIUM | Unknown which activates first |
| 3 | Multiple mode systems | MEDIUM | No unified dispatch, scattered logic |
| 4 | Prompt selection inconsistency | MEDIUM | Three different selection mechanisms |
| 5 | Unused fast_mode_executor in brain | LOW | Dead code or integration bug |
| 6 | Config key mismatch | MEDIUM | `fast_mode` vs `ENABLE_FLASH_MODE` |
| 7 | No execution order definition | MEDIUM | Unclear which system runs first |

---

## Recommendations

1. **Clarify naming**: Decide if this should be "flash" or "fast" mode
   - Suggest: Use existing "fast_mode.py" naming for consistency
   - Or rename: "fast_mode" -> "pattern_mode" and new system -> "flash_mode"

2. **Unify configuration**:
   - Add `ENABLE_FAST_MODE` to `a11y_config.py` (currently missing)
   - Merge fast_mode config lookup to use centralized config

3. **Define execution order**:
   - Fast mode (pattern matching) -> Flash mode (LLM) -> Full LLM
   - Document in comments which layer runs first

4. **Consolidate prompts**:
   - Move FLASH_MODE_PROMPT to `prompts/system_prompts.py`
   - Use `get_system_prompt()` consistently

5. **Investigate brain integration**:
   - Confirm if `fast_mode_executor` in brain should be called
   - If unused, remove it (clean up dead code)

6. **Test both systems together**:
   - Add test case: simple task that triggers both auto-detections
   - Verify only one executes, verify correct result

---

## Files Involved

| File | Issue | Lines |
|------|-------|-------|
| `fast_mode.py` | Existing system, unused in brain | 1-467 |
| `simple_agent.py` | NEW system, naming conflict | 86-103, 110, 115, 126-134, 154-158 |
| `a11y_config.py` | Flash config exists, fast config missing | 189-190 |
| `brain_enhanced_v2.py` | Fast executor created but not called | 1145-1153 |
| `brain_config.py` | Unrelated AgentMode system | 126-205 |
| `plan_mode.py` | Unrelated mode system | 1-500+ |
| `system_prompts.py` | Prompt selection for build/plan | 268-293 |

---

## Search Results Snapshot

**Files containing FLASH_MODE or flash_mode (24 total):**
- brain_enhanced_v2.py
- simple_agent.py
- orchestration.py
- a11y_config.py
- organism_core.py
- world_model.py
- web_shortcuts.py
- tool_executor.py
- stealth_utils.py
- siao_core.py
- react_loop.py
- llm_extractor.py
- llm_client.py
- goal_hierarchy.py
- fast_mode_example.py
- fast_mode.py (not flash mode!)
- execution_coordinator.py
- episode_compressor.py
- curiosity_engine.py
- config_validator.py
- config_loader.py
- cognitive_organism.py
- brain_utils.py
- brain_config.py

**Auto-detection mechanisms found:**
- `/mnt/c/ev29/cli/engine/agent/a11y_config.py:190` - FLASH_MODE_AUTO_DETECT = True
- `/mnt/c/ev29/cli/engine/agent/simple_agent.py:154-158` - Auto-detection in run()
- `/mnt/c/ev29/cli/engine/agent/fast_mode.py:322-364` - should_use_fast_mode() function
