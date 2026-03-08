---
name: verify
description: Run a rigorous multi-dimensional verification of implementation correctness — contract compliance, regression, security, consistency, and behavioral accuracy
---

Perform a complete verification pass on the current state of the codebase or a specific recent change. This command answers one question with evidence: **does the implementation actually do what it's supposed to do?**

**Usage**:
- `/verify` — verify the entire codebase
- `/verify [feature or module name]` — verify a specific area
- `/verify after [change description]` — verify correctness after a specific change

Verification is a read-and-run operation. No new features are written. No refactoring. If issues are found, they are reported precisely and fixed minimally.

---

## Phase 1 — Scope Definition

Before any verification begins:

1. **Determine scope**: Are we verifying the full codebase, a module, or a recent change?
2. **Collect the specification**: What is this code supposed to do? Look for:
   - CONTRACT.md (if produced by `/integrate`)
   - README or docs describing expected behavior
   - Test descriptions (test names describe intended behavior)
   - Code comments describing intent
   - Git commit messages describing the purpose of changes
3. **Establish baseline**: Run the test suite now and record the result as the verification baseline
4. **List all claims**: Produce a list of behavioral claims the code is supposed to satisfy before running any check

---

## Phase 2 — Multi-Dimensional Verification (Parallel, 6 Agents)

Spawn **6 parallel agents** in a single response.

### Agent 1 — Contract Verification
Verify the implementation matches its specification exactly:
- Does every public function/endpoint accept exactly the inputs it claims to accept?
- Does every public function/endpoint produce exactly the outputs it claims to produce?
- Are all documented error conditions handled and producing the documented error type/code?
- Are all edge cases mentioned in comments or docs actually handled in code?
- Are there behaviors in the code that are NOT in the spec (undocumented side effects)?
- Report each deviation as: `[MISSING / EXTRA / WRONG] [what]` with file:line

### Agent 2 — Regression Verification
Verify that existing behavior has not been broken:
- Run the full test suite and capture complete output
- For every failing test: read the test, read the code it tests, determine if the test is wrong or the code is wrong
- Identify any test that was disabled, skipped, or deleted recently (check git history)
- Check for any behavior that was previously documented or tested that is now absent
- Report: test results, root cause for each failure, classification (test bug vs code bug)

### Agent 3 — Behavioral Accuracy Check
Verify that the code actually does what the implementation comments and variable names suggest:
- Read every function and compare its name/docstring against its actual behavior
- Find functions where the name says one thing and the code does another
- Find variables where the name is misleading (e.g., `isValid` that is actually a count)
- Find comments that describe behavior that no longer matches the code
- Trace the most critical business logic paths manually and verify correctness of each step
- Report: `[MISLEADING / INCORRECT / STALE]` with file:line and exact description

### Agent 4 — Input Validation & Boundary Verification
Verify robustness at all input boundaries:
- For every public API endpoint or function: what happens with null/undefined inputs?
- What happens with empty strings, empty arrays, empty objects?
- What happens with inputs at numeric limits (0, negative, overflow)?
- What happens with malformed data (wrong type, unexpected shape)?
- What happens with concurrent calls to stateful operations?
- What happens if an external dependency (DB, API) is unavailable?
- For each unhandled case: report `[UNHANDLED]` with file:line, input case, and current behavior

### Agent 5 — Security Verification
Verify that the implementation does not introduce security regressions:
- Are all user-provided inputs sanitized before use in queries, commands, or templates?
- Are authentication checks present on all routes/operations that require them?
- Are authorization checks present (not just authn — does the user have permission for this specific resource)?
- Are secrets/credentials loaded from environment, never hardcoded?
- Are sensitive values excluded from logs, error messages, and API responses?
- Are file paths constructed from user input validated against path traversal?
- Are SQL queries parameterized (no string concatenation into queries)?
- Report: `[CRITICAL / HIGH / MEDIUM]` severity with file:line and exact vulnerability

### Agent 6 — Consistency & Standards Verification
Verify that the new code is consistent with the existing codebase:
- Naming conventions: does new code follow the same naming patterns as existing code?
- Error handling style: does new code handle errors the same way as existing code?
- Logging: does new code log with the same structure/format/level conventions?
- Response shapes: do new API responses follow the same schema patterns as existing ones?
- Module boundaries: does new code respect the same layer separation as existing code?
- Config handling: does new code load config/env the same way as existing code?
- Report: `[INCONSISTENT]` with file:line and what it should match

---

## Phase 3 — Verification Matrix

After all agents complete, produce a verification matrix:

```
VERIFICATION MATRIX: [scope]
Run date: [date]

Dimension                | Status  | Issues Found
-------------------------|---------|-------------
Contract compliance      | ✅/⚠️/❌ | [N issues]
Regression               | ✅/⚠️/❌ | [N failures]
Behavioral accuracy      | ✅/⚠️/❌ | [N mismatches]
Input/boundary handling  | ✅/⚠️/❌ | [N gaps]
Security                 | ✅/⚠️/❌ | [N findings]
Consistency              | ✅/⚠️/❌ | [N deviations]

Overall: [PASS / PASS WITH WARNINGS / FAIL]
```

**Overall PASS** = no Critical/High issues, ≤3 Medium issues, no test regressions
**Overall PASS WITH WARNINGS** = no Critical issues, ≤2 High issues, all regressions explained
**Overall FAIL** = any Critical security issue, any unexplained regression, >2 High issues

---

## Phase 4 — Issue Resolution

For each issue found, apply this resolution protocol:

### Classification
```
ISSUE [N]
Dimension: [which agent found it]
Severity: [Critical / High / Medium / Low]
File: [path:line]
Description: [exact description of the problem]
Evidence: [what the code does vs. what it should do]
Fix: [minimal change required — do not over-engineer]
```

### Fix Priority Order
1. Critical security issues — fix immediately, do not proceed until resolved
2. Test regressions caused by code bugs — fix the code
3. Test regressions caused by test bugs — fix the test, document why
4. Contract violations — fix the implementation to match spec, or update spec with justification
5. Unhandled boundaries — add explicit handling
6. Consistency issues — bring new code in line with existing patterns
7. Low severity / misleading names — fix or defer with debt entry

### Fix Rules
- Fix only what is broken — do not opportunistically refactor
- Each fix must be verifiable: re-run the specific check that found the issue after fixing
- If a fix for one issue could affect another area, re-run the full suite for that area

---

## Phase 5 — Re-Verification

After all fixes are applied:

1. Re-run the full test suite — must match or exceed the baseline pass count
2. Re-run agents for any dimension that had Critical or High issues
3. Produce updated verification matrix
4. Confirm: Overall status is PASS or PASS WITH WARNINGS with all warnings documented

---

## Phase 6 — Verification Report

Write `VERIFICATION_REPORT.md` (append, do not overwrite):

```markdown
# Verification Report
Date: [date]
Scope: [what was verified]
Baseline: [test suite state at start]

## Verification Matrix
[Phase 3 table]

## Issues Found
[Each issue in Phase 4 classification format]

## Issues Resolved
[Each fix applied, minimal description]

## Issues Deferred
[Any issues not fixed, with justification and debt reference]

## Final Test Suite Status
- Passing: [N]
- Failing: [N]
- Coverage: [%]

## Outcome
[PASS / PASS WITH WARNINGS / FAIL]
[One paragraph summary of what was verified and confidence level]

---
```

---

## Verification Rules (Non-Negotiable)

1. **Evidence required** — every finding must reference a file path, line number, and exact behavior
2. **No false positives** — do not report style preferences or hypothetical risks as verification failures
3. **Minimal fixes** — verification fixes the specific problem found; it does not refactor, optimize, or improve
4. **Re-verify after fix** — a fix is not complete until the specific check that found the issue passes
5. **Security is blocking** — any Critical security issue blocks all other work until resolved
6. **Honest matrix** — the verification matrix must reflect reality; do not mark ✅ for dimensions not fully checked
7. **Baseline preservation** — the final test suite pass count must equal or exceed the baseline; any reduction is a FAIL