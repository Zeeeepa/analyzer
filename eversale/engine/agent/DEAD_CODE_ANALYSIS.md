# Dead Code Analysis Report
## CLI Engine Agent - Main Files

Analysis Date: 2025-12-13
Files Analyzed:
- `/mnt/c/ev29/cli/engine/agent/simple_agent.py` (557 lines)
- `/mnt/c/ev29/cli/engine/agent/a11y_browser.py` (3,479 lines)
- `/mnt/c/ev29/cli/engine/agent/playwright_direct.py` (10,158 lines)

## Summary

Found **29 truly dead functions** (zero references in code):
- simple_agent.py: 1 dead function
- a11y_browser.py: 10 dead functions
- playwright_direct.py: 18 dead functions

---

## 1. simple_agent.py

### Dead Functions (1 total)

**Line 533: `run_task()` - DEAD CODE**
```python
async def run_task(goal: str, llm_client=None, headless: bool = False,
                   flash_mode: bool = False) -> AgentResult:
    """Run a single task with the simple agent."""
    agent = SimpleAgent(llm_client=llm_client, headless=headless, flash_mode=flash_mode)
    return await agent.run(goal)
```
- Status: Convenience wrapper function, never called
- Recommendation: Remove or export if intended as public API

### Code Quality Notes
- Has well-documented `example()` function at line 541
- `if __name__ == "__main__"` block is appropriate for testing
- No large commented-out code blocks
- All other functions are properly documented

---

## 2. a11y_browser.py

### Dead Functions (10 total)

1. **Line 278: `find_ref()`** - Snapshot method
   - Purpose: Find element by ref string
   - Status: Defined but never called; no direct references

2. **Line 289: `find_by_name()`** - Snapshot method
   - Purpose: Find elements by name attribute
   - Status: Zero references in code

3. **Line 353: `to_compact_string()`** - Snapshot method
   - Purpose: Compact string representation
   - Status: No callers found

4. **Line 2122: `navigate_back()`** - Browser navigation
   - Purpose: Navigate to previous page
   - Status: Dead code - use `go_back()` instead

5. **Line 2131: `navigate_forward()`** - Browser navigation
   - Purpose: Navigate to next page
   - Status: Dead code - use `go_forward()` instead

6. **Line 2531: `get_url()`** - Browser API
   - Purpose: Get current page URL
   - Status: Never called; property/method duplication?

7. **Line 2535: `get_title()`** - Browser API
   - Purpose: Get page title
   - Status: Never called

8. **Line 2539: `get_metrics()`** - Performance metrics
   - Purpose: Get execution metrics
   - Status: No callers found

9. **Line 2572: `reset_metrics()`** - Metrics reset
   - Purpose: Clear performance metrics
   - Status: Never called

10. **Line 2582: `clear_cache()`** - Cache management
    - Purpose: Clear snapshot cache
    - Status: Dead code

### Patterns in a11y_browser.py
- Multiple overlapping navigation methods (`navigate_back` vs `go_back`)
- Metrics collection infrastructure that's never accessed
- Snapshot helper methods not integrated into main flow
- Cache management methods defined but unused

### Code Quality Notes
- Well-structured with clear sections
- Has proper example() at line 3426
- Good docstring coverage (83/85 public functions documented)
- 2 functions without docstrings: `executor()` (line 487) and `handler()` (line 2675) - both are local functions

---

## 3. playwright_direct.py (Most Issues)

### Dead Functions (18 total)

**Utility Functions (5):**
1. Line 213: `get_recent_errors()` - Error tracking (10 line limit)
2. Line 217: `clear_error_tracker()` - Error cleanup
3. Line 364: `get_data()` - Generic data getter
4. Line 383: `learn_pattern()` - Pattern learning
5. Line 390: `get_pattern()` - Pattern retrieval

**Session/Auth Functions (4):**
6. Line 1615: `load_session()` - Session loading
7. Line 1641: `get_saved_sessions()` - Session enumeration
8. Line 1650: `login_mode()` - Login state
9. Line 1708: `finish_login()` - Login completion

**Browser/Navigation (5):**
10. Line 572: `nav_delay()` - Navigation delay getter
11. Line 1008: `wait_for_selector_safe()` - Safe selector wait
12. Line 2012: `auto_handle_challenges()` - Challenge handling
13. Line 2989: `get_accessibility_snapshot()` - Snapshot generation
14. Line 4579: `build_page_dom_map()` - DOM mapping

**Tool/Execution (4):**
15. Line 395: `add_task()` - Task queue
16. Line 4679: `get_tools()` - Tool enumeration
17. Line 5206: `call_tool()` - Tool invocation
18. Line 9873: `parse_structured_output()` - Output parsing

### Patterns in playwright_direct.py
- **Incomplete refactoring**: Multiple overlapping tool/execution methods
- **Abandoned features**: Session/login management (replaced by external auth?)
- **Dead infrastructure**: Error tracking and pattern learning system
- **Unused abstractions**: Challenge auto-handling, DOM mapping

### Functions Without Docstrings (14)
Lines: 459, 472, 483, 488, 565, 567, 569, 633, 661, 851, 901, 906, 937, 982, 1573
- These are mostly helper functions but lack documentation
- `async_wrapper()` and `sync_wrapper()` at lines 633, 661 are decorator wrappers

---

## Dead Code Categories

### Category A: Pure Dead Code (Can be deleted)
- `simple_agent.run_task()` - convenience wrapper
- `a11y_browser.find_ref()` - helper method never used
- `a11y_browser.find_by_name()` - snapshot helper
- `a11y_browser.to_compact_string()` - string formatter
- `playwright_direct.get_recent_errors()` - unused debugging
- `playwright_direct.clear_error_tracker()` - error tracking
- `playwright_direct.learn_pattern()` - unused ML
- `playwright_direct.get_pattern()` - unused ML

### Category B: Duplicate/Redundant Methods
- `a11y_browser.navigate_back()` vs `go_back()` - duplicated
- `a11y_browser.navigate_forward()` vs `go_forward()` - duplicated
- `a11y_browser.get_url()` vs property - possible duplication
- `a11y_browser.get_title()` - unused getter

### Category C: Incomplete Refactoring
- `playwright_direct.load_session()`, `get_saved_sessions()` - auth system remnants
- `playwright_direct.add_task()`, `call_tool()` - old execution model
- `playwright_direct.auto_handle_challenges()` - replaced by challenge_handler module

### Category D: Infrastructure Not Integrated
- `a11y_browser` metrics collection (`get_metrics()`, `reset_metrics()`)
- `a11y_browser.clear_cache()` - cache exists but reset never called
- `playwright_direct.build_page_dom_map()` - DOM abstraction
- `playwright_direct.wait_for_selector_safe()` - wrapped wait method

---

## Recommendations for Cleanup

### High Priority (Remove Immediately)
1. **simple_agent.py, line 533**: Remove `run_task()` - use `SimpleAgent().run()` directly
2. **a11y_browser.py, lines 2122, 2131**: Remove duplicate `navigate_back()`, `navigate_forward()`
3. **a11y_browser.py, lines 2531, 2535**: Remove `get_url()`, `get_title()` if duplicating existing APIs
4. **playwright_direct.py, lines 213, 217**: Remove error tracker functions (not integrated)

### Medium Priority (Review & Consolidate)
5. **a11y_browser.py, lines 278, 289, 353**: Remove Snapshot helper methods or integrate them
6. **a11y_browser.py, lines 2539, 2572, 2582**: Metrics infrastructure - remove or fully integrate
7. **playwright_direct.py, lines 1615, 1641, 1650, 1708**: Remove session/auth remnants
8. **playwright_direct.py, lines 383, 390**: Remove ML pattern functions

### Low Priority (Document or Future Use)
9. **playwright_direct.py, lines 1008, 2012, 2989, 4579, 4679, 5206, 9873**: Document as reserved for future use or remove

---

## Code Health Score

| File | Lines | Functions | Dead | Coverage | Quality |
|------|-------|-----------|------|----------|---------|
| simple_agent.py | 557 | 15 | 1 (6.7%) | 94% | Good |
| a11y_browser.py | 3,479 | 85 | 10 (11.8%) | 98% | Good |
| playwright_direct.py | 10,158 | 116 | 18 (15.5%) | 88% | Fair |
| **TOTAL** | **14,194** | **216** | **29 (13.4%)** | **93%** | **Good** |

---

## Notes

1. **No Large Commented Blocks**: Unlike many legacy codebases, these files don't have large commented-out code sections. Good practice.

2. **Example Functions**: All files have proper `if __name__ == "__main__"` blocks with examples. Good for documentation.

3. **No Syntax/Unreachable Code Issues**: AST analysis found no unreachable code after returns or syntax errors.

4. **Docstring Coverage**: 83/85 (97.6%) in a11y_browser, 102/116 (87.9%) in playwright_direct.

5. **Import Availability**: Graceful fallbacks for optional dependencies (stealth, challenge_handler, reddit_handler).

---

## Code Cleanup Impact

Removing 29 dead functions would:
- Reduce codebase by ~400-500 lines (~3.5% reduction)
- Improve maintainability by removing unclear/duplicate methods
- Reduce API surface area confusion (e.g., `navigate_back` vs `go_back`)
- Make metrics/session systems either fully removed or fully integrated

Estimated cleanup time: 1-2 hours with proper testing.
