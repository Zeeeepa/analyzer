# State Cleanup Implementation - Orchestration.py

## Problem Solved
State was persisting between goal runs causing incorrect behavior. Cached plans, execution logs, and other state would bleed from one goal to the next, causing:
- Wrong plans being reused
- Steering input listener left running
- Stats accumulating across goals
- Forever mode flags not resetting

## Solution Implemented

### 1. Added `cleanup_state()` Method
Location: Lines 154-212

Comprehensive state cleanup that resets:
- **Steering**: Stops `_steering` input listener if running
- **Plan caches**: Deletes `_last_plan_prompt` and `_cached_plan`
- **Execution logs**: Clears `_execution_log` array
- **Issue tracking**: Resets `_last_issues` and `_preflight_details`
- **Stats**: Resets `self.stats` dictionary
- **Forever mode**: Clears `_forever_mode` and `_last_checkpoint_time`
- **Fast mode**: Calls `fast_mode_executor.reset()` if available

All operations wrapped in try-except to prevent cleanup failures from breaking execution.

### 2. Added Async Context Manager Support
Location: Lines 214-221

Methods:
- `__aenter__()`: Returns self for context manager entry
- `__aexit__()`: Calls cleanup_state() on exit

Allows using OrchestrationMixin with:
```python
async with agent:
    result = await agent.run("do something")
# cleanup_state() called automatically
```

### 3. Integrated Cleanup into `_run_goal_sequence()`
Location: Lines 479-692

Changes:
- Wrapped entire method body in `try-finally` block
- Finally block calls `await self.cleanup_state()` at line 692
- Ensures cleanup happens even if exceptions occur
- Return statement inside try block (line 687)

## Impact

### Before
```python
# Goal 1 runs
self._steering.start()
self._cached_plan = "old plan"
self.stats = {"goal1": "data"}

# Goal 2 runs
# BUG: _steering still running from goal 1
# BUG: _cached_plan contains stale data
# BUG: stats includes goal 1 data
```

### After
```python
# Goal 1 runs
self._steering.start()
self._cached_plan = "old plan"
self.stats = {"goal1": "data"}

# Cleanup runs in finally block
await self.cleanup_state()
# _steering.stop() called
# _cached_plan deleted
# stats reset to {}

# Goal 2 runs with clean state
```

## Testing Checklist

- [x] Syntax check passes (py_compile)
- [ ] Multi-goal sequence executes without state bleed
- [ ] Cleanup runs on success
- [ ] Cleanup runs on error (finally block)
- [ ] Steering properly stops between goals
- [ ] Stats reset between goals
- [ ] No crashes from missing attributes

## Files Modified

- `/mnt/c/ev29/cli/engine/agent/orchestration.py`
  - Added cleanup_state() method (70 lines)
  - Added __aenter__/__aexit__ methods (8 lines)
  - Modified _run_goal_sequence() with try-finally wrapper

## Notes

- All cleanup operations are defensive (hasattr checks, try-except wrappers)
- Cleanup uses debug-level logging to avoid noise
- Compatible with existing code - no breaking changes
- Async-compatible throughout
