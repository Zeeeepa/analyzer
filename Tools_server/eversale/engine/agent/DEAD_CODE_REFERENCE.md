# Dead Code Reference - Quick Cleanup Guide

## All 29 Dead Functions by File

### simple_agent.py (1 function)

```
LINE 533-536: run_task()
async def run_task(goal: str, llm_client=None, headless: bool = False, flash_mode: bool = False) -> AgentResult:
    """Run a single task with the simple agent."""
    agent = SimpleAgent(llm_client=llm_client, headless=headless, flash_mode=flash_mode)
    return await agent.run(goal)

STATUS: Pure dead code - convenience wrapper that's never called
ACTION: DELETE (use SimpleAgent().run() directly instead)
```

---

### a11y_browser.py (10 functions)

#### Snapshot Helper Methods

```
LINE 278-282: find_ref()
def find_ref(self, ref: str) -> Optional[ElementRef]:
    """Find element by ref."""
    for el in self.elements:
        if el.ref == ref:
            return el

STATUS: Dead code - Snapshot method never referenced
ACTION: DELETE
```

```
LINE 289-294: find_by_name()
def find_by_name(self, name: str, partial: bool = True) -> List[ElementRef]:
    """Find elements by name attribute."""
    return [
        el for el in self.elements
        if partial and name.lower() in el.name.lower() or el.name == name
    ]

STATUS: Dead code - Snapshot helper never called
ACTION: DELETE
```

```
LINE 353-363: to_compact_string()
def to_compact_string(self) -> str:
    """Compact representation for token-limited LLM contexts."""
    lines = []
    for el in self.elements[:100]:
        lines.append(f"[{el.ref}] {el.role}: {el.name}")
    return "\n".join(lines)

STATUS: Dead code - Formatting method never used
ACTION: DELETE
```

#### Browser Navigation (Duplicates)

```
LINE 2122-2129: navigate_back()
async def navigate_back(self) -> ActionResult:
    """Navigate to previous page in history."""
    try:
        await self.page.go_back()
        return ActionResult(success=True, action="navigate_back")
    except Exception as e:
        return ActionResult(success=False, action="navigate_back", error=str(e))

STATUS: DUPLICATE - use go_back() instead (line 2100)
ACTION: DELETE
```

```
LINE 2131-2138: navigate_forward()
async def navigate_forward(self) -> ActionResult:
    """Navigate to next page in history."""
    try:
        await self.page.go_forward()
        return ActionResult(success=True, action="navigate_forward")
    except Exception as e:
        return ActionResult(success=False, action="navigate_forward", error=str(e))

STATUS: DUPLICATE - use go_forward() instead (line 2110)
ACTION: DELETE
```

#### Browser API Methods

```
LINE 2531-2533: get_url()
async def get_url(self) -> str:
    """Get current page URL."""
    return self.page.url

STATUS: Dead code - may duplicate existing property access
ACTION: CHECK if used elsewhere before deleting
```

```
LINE 2535-2537: get_title()
async def get_title(self) -> str:
    """Get current page title."""
    return await self.page.title()

STATUS: Dead code - similar methods may exist
ACTION: CHECK if used elsewhere before deleting
```

#### Metrics & Cache Management

```
LINE 2539-2570: get_metrics()
def get_metrics(self) -> Dict[str, Any]:
    """Get performance metrics..."""
    # ~32 lines of metrics collection logic
    return metrics

STATUS: Dead code - metrics infrastructure never accessed
ACTION: DELETE unless metrics are being collected elsewhere
```

```
LINE 2572-2580: reset_metrics()
def reset_metrics(self) -> None:
    """Reset performance metrics to zero."""
    self._metrics = {
        "snapshots_taken": 0,
        "cache_hits": 0,
        "actions_executed": 0,
        "action_failures": 0,
        "total_action_time": 0.0,
    }

STATUS: Dead code - paired with get_metrics(), never called
ACTION: DELETE
```

```
LINE 2582-2584: clear_cache()
def clear_cache(self) -> None:
    """Clear snapshot cache."""
    self._snapshot_cache.clear()

STATUS: Dead code - cache exists but reset never called
ACTION: DELETE or integrate into lifecycle
```

---

### playwright_direct.py (18 functions)

#### Error Tracking (Lines 200-225)

```
LINE 213-215: get_recent_errors()
def get_recent_errors(limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent errors for debugging."""
    return _ERROR_TRACKER[-limit:]

STATUS: Dead code - error tracker infrastructure not integrated
ACTION: DELETE
```

```
LINE 217-218: clear_error_tracker()
def clear_error_tracker():
    """Clear error tracking."""
    _ERROR_TRACKER.clear()

STATUS: Dead code - paired with get_recent_errors()
ACTION: DELETE
```

#### Data/Pattern Storage (Lines 351-395)

```
LINE 364-366: get_data()
def get_data(key: str) -> Any:
    """Get stored data."""
    return _DATA_STORE.get(key)

STATUS: Dead code - generic data getter never used
ACTION: DELETE
```

```
LINE 383-387: learn_pattern()
def learn_pattern(name: str, pattern: Dict[str, Any]):
    """Learn a new pattern for future use."""
    if "patterns" not in _DATA_STORE:
        _DATA_STORE["patterns"] = {}
    _DATA_STORE["patterns"][name] = pattern

STATUS: Dead code - unused ML pattern learning
ACTION: DELETE
```

```
LINE 390-393: get_pattern()
def get_pattern(name: str) -> Optional[Dict[str, Any]]:
    """Get a learned pattern."""
    patterns = _DATA_STORE.get("patterns", {})
    return patterns.get(name)

STATUS: Dead code - paired with learn_pattern()
ACTION: DELETE
```

#### Session/Auth Management (Lines 1615-1750)

```
LINE 1615-1625: load_session()
def load_session(domain: str, profile_name: str = "default"):
    """Load a saved browser session for a domain."""
    session_file = _SESSION_DIR / f"{domain}_{profile_name}.json"
    # ~10 lines of session loading logic

STATUS: Dead code - auth system remnant, possibly replaced by external auth
ACTION: CHECK if session management is used elsewhere, then DELETE
```

```
LINE 1641-1647: get_saved_sessions()
def get_saved_sessions() -> List[str]:
    """Get list of saved session profiles."""
    if not _SESSION_DIR.exists():
        return []
    return [f.stem for f in _SESSION_DIR.glob("*.json")]

STATUS: Dead code - session enumeration
ACTION: DELETE with load_session()
```

```
LINE 1650-1660: login_mode()
def login_mode(interactive: bool = False):
    """Set login mode for browser context."""
    global _LOGIN_MODE
    _LOGIN_MODE = "interactive" if interactive else "token"
    logger.debug(f"Login mode set to: {_LOGIN_MODE}")

STATUS: Dead code - login state management
ACTION: DELETE
```

```
LINE 1708-1720: finish_login()
async def finish_login(auth_token: str = None):
    """Complete login process and save session."""
    if auth_token:
        _SESSION_DATA["auth_token"] = auth_token
    # ~10 lines of session completion logic

STATUS: Dead code - login completion handler
ACTION: DELETE
```

#### Navigation/Browser Control (Lines 572-2012)

```
LINE 572-573: nav_delay()
def nav_delay() -> float:
    """Get navigation delay setting."""

STATUS: Dead code - config getter never used
ACTION: DELETE
```

```
LINE 1008-1015: wait_for_selector_safe()
async def wait_for_selector_safe(selector: str, timeout: int = 5000) -> bool:
    """Wait for selector with timeout, returns false on timeout."""
    try:
        await self.page.locator(selector).first.wait_for(timeout=timeout)
        return True
    except Exception:
        return False

STATUS: Dead code - wrapped wait method
ACTION: DELETE (use standard wait methods instead)
```

```
LINE 2012-2030: auto_handle_challenges()
async def auto_handle_challenges(self) -> bool:
    """Automatically detect and handle Cloudflare/hCaptcha challenges."""
    # ~20 lines of challenge detection logic
    return False

STATUS: Dead code - replaced by separate challenge_handler module
ACTION: DELETE (use ChallengeHandler class instead)
```

#### Page Analysis (Lines 2989-4679)

```
LINE 2989-3000: get_accessibility_snapshot()
async def get_accessibility_snapshot(self) -> Dict[str, Any]:
    """Get accessibility tree of current page."""
    # ~10 lines of snapshot extraction
    return snapshot

STATUS: Dead code - may duplicate accessibility functionality
ACTION: CHECK if A11yBrowser is the primary accessibility API, then DELETE
```

```
LINE 4579-4610: build_page_dom_map()
async def build_page_dom_map(self) -> Dict[str, Any]:
    """Build complete DOM map with references."""
    # ~30 lines of DOM mapping logic
    return dom_map

STATUS: Dead code - unused DOM abstraction
ACTION: DELETE
```

#### Tool/Execution System (Lines 395-9873)

```
LINE 395-398: add_task()
def add_task(task_name: str, **kwargs):
    """Add task to execution queue."""
    _TASK_QUEUE.append({"task": task_name, "params": kwargs})

STATUS: Dead code - old task queue system
ACTION: DELETE (check if replaced by goal_sequencer or similar)
```

```
LINE 4679-4710: get_tools()
async def get_tools(self) -> List[Dict[str, Any]]:
    """Get available tools for execution."""
    # ~30 lines of tool enumeration
    return tools

STATUS: Dead code - tool discovery mechanism never used
ACTION: DELETE
```

```
LINE 5206-5240: call_tool()
async def call_tool(self, tool_name: str, **kwargs) -> Any:
    """Call a tool by name with arguments."""
    # ~30 lines of tool invocation logic
    return result

STATUS: Dead code - old tool invocation system
ACTION: DELETE (check orchestration.py for current tool system)
```

```
LINE 9873-9920: parse_structured_output()
def parse_structured_output(response: str) -> Dict[str, Any]:
    """Parse structured tool responses."""
    # ~45 lines of parsing logic
    return parsed

STATUS: Dead code - output parsing that's not called
ACTION: DELETE or consolidate with current parser
```

---

## Summary Table

| File | Line | Function | Type | Priority |
|------|------|----------|------|----------|
| simple_agent.py | 533 | run_task() | Wrapper | HIGH |
| a11y_browser.py | 278 | find_ref() | Helper | MEDIUM |
| a11y_browser.py | 289 | find_by_name() | Helper | MEDIUM |
| a11y_browser.py | 353 | to_compact_string() | Formatter | MEDIUM |
| a11y_browser.py | 2122 | navigate_back() | Duplicate | HIGH |
| a11y_browser.py | 2131 | navigate_forward() | Duplicate | HIGH |
| a11y_browser.py | 2531 | get_url() | API | MEDIUM |
| a11y_browser.py | 2535 | get_title() | API | MEDIUM |
| a11y_browser.py | 2539 | get_metrics() | Infrastructure | MEDIUM |
| a11y_browser.py | 2572 | reset_metrics() | Infrastructure | MEDIUM |
| a11y_browser.py | 2582 | clear_cache() | Management | MEDIUM |
| playwright_direct.py | 213 | get_recent_errors() | Debug | HIGH |
| playwright_direct.py | 217 | clear_error_tracker() | Debug | HIGH |
| playwright_direct.py | 364 | get_data() | Generic | HIGH |
| playwright_direct.py | 383 | learn_pattern() | ML | HIGH |
| playwright_direct.py | 390 | get_pattern() | ML | HIGH |
| playwright_direct.py | 395 | add_task() | Queue | MEDIUM |
| playwright_direct.py | 572 | nav_delay() | Config | HIGH |
| playwright_direct.py | 1008 | wait_for_selector_safe() | Wrapper | MEDIUM |
| playwright_direct.py | 1615 | load_session() | Auth | MEDIUM |
| playwright_direct.py | 1641 | get_saved_sessions() | Auth | MEDIUM |
| playwright_direct.py | 1650 | login_mode() | Auth | MEDIUM |
| playwright_direct.py | 1708 | finish_login() | Auth | MEDIUM |
| playwright_direct.py | 2012 | auto_handle_challenges() | Challenge | MEDIUM |
| playwright_direct.py | 2989 | get_accessibility_snapshot() | Analysis | MEDIUM |
| playwright_direct.py | 4579 | build_page_dom_map() | Analysis | MEDIUM |
| playwright_direct.py | 4679 | get_tools() | System | MEDIUM |
| playwright_direct.py | 5206 | call_tool() | System | MEDIUM |
| playwright_direct.py | 9873 | parse_structured_output() | Parsing | MEDIUM |

---

## Cleanup Checklist

### Phase 1: High Priority (Easy Wins)
- [ ] Remove simple_agent.py:533 `run_task()`
- [ ] Remove a11y_browser.py:2122 `navigate_back()`
- [ ] Remove a11y_browser.py:2131 `navigate_forward()`
- [ ] Remove playwright_direct.py:213 `get_recent_errors()`
- [ ] Remove playwright_direct.py:217 `clear_error_tracker()`
- [ ] Remove playwright_direct.py:364 `get_data()`
- [ ] Remove playwright_direct.py:383 `learn_pattern()`
- [ ] Remove playwright_direct.py:390 `get_pattern()`
- [ ] Remove playwright_direct.py:572 `nav_delay()`

### Phase 2: Medium Priority (Verify First)
- [ ] Review & delete a11y_browser.py:278 `find_ref()`
- [ ] Review & delete a11y_browser.py:289 `find_by_name()`
- [ ] Review & delete a11y_browser.py:353 `to_compact_string()`
- [ ] Review & delete a11y_browser.py:2531 `get_url()`
- [ ] Review & delete a11y_browser.py:2535 `get_title()`
- [ ] Review & delete a11y_browser.py:2539 `get_metrics()`
- [ ] Review & delete a11y_browser.py:2572 `reset_metrics()`
- [ ] Review & delete a11y_browser.py:2582 `clear_cache()`

### Phase 3: Medium Priority (Auth/Sessions)
- [ ] Review & delete playwright_direct.py:1615 `load_session()`
- [ ] Review & delete playwright_direct.py:1641 `get_saved_sessions()`
- [ ] Review & delete playwright_direct.py:1650 `login_mode()`
- [ ] Review & delete playwright_direct.py:1708 `finish_login()`

### Phase 4: Lower Priority (Old Systems)
- [ ] Review & delete playwright_direct.py:395 `add_task()`
- [ ] Review & delete playwright_direct.py:1008 `wait_for_selector_safe()`
- [ ] Review & delete playwright_direct.py:2012 `auto_handle_challenges()`
- [ ] Review & delete playwright_direct.py:2989 `get_accessibility_snapshot()`
- [ ] Review & delete playwright_direct.py:4579 `build_page_dom_map()`
- [ ] Review & delete playwright_direct.py:4679 `get_tools()`
- [ ] Review & delete playwright_direct.py:5206 `call_tool()`
- [ ] Review & delete playwright_direct.py:9873 `parse_structured_output()`
