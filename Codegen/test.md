---
name: test
description: Design and execute a comprehensive, multi-layer test strategy with parallel agents — covering unit, integration, E2E, regression, performance, and security dimensions
---

Design and execute a complete test strategy for this codebase. This command goes beyond running existing tests — it audits test coverage, identifies gaps, writes missing tests, and produces a verified, reproducible test suite.

**Usage**: Run against the full codebase, a specific module (`/test src/payments`), or a specific feature (`/test after integrating checkout flow`).

---

## Phase 1 — Test Landscape Audit (Parallel, 3 Agents)

Spawn **3 parallel agents** before writing any new tests.

### Agent 1 — Existing Test Inventory
- Locate ALL existing test files: unit, integration, E2E, fixtures, factories, mocks
- For each test file: what module does it cover, what percentage of that module's functions are tested, what cases are present?
- Identify the current test framework, runner, and coverage tooling
- Run the existing test suite and capture full output: passes, failures, skips, and coverage report
- Output: complete test inventory with pass/fail status and per-module coverage estimate

### Agent 2 — Coverage Gap Analysis
- Cross-reference every non-test source file against the test inventory
- Identify functions, classes, and modules with ZERO test coverage
- Identify tested functions with INCOMPLETE coverage (missing branches, missing error paths, missing edge cases)
- Prioritize gaps by risk:
  - `CRITICAL` — business logic, money handling, auth, data mutations with no tests
  - `HIGH` — core algorithms, API handlers, data validation with partial coverage
  - `MEDIUM` — utilities and helpers with partial coverage
  - `LOW` — config loading, simple getters, pure constants
- Output: prioritized gap list with file paths and specific uncovered paths

### Agent 3 — Test Quality Audit
- Review existing tests for quality problems:
  - Tests that never assert anything (no `expect`/`assert` calls)
  - Tests that only test the happy path and ignore all error paths
  - Tests tightly coupled to implementation details (will break on any refactor)
  - Tests with no isolation (shared mutable state, order-dependent tests)
  - Mocks that misrepresent actual dependency behavior
  - Flaky tests (timeouts, async race conditions, non-deterministic assertions)
- Output: list of test quality issues with severity ratings

---

## Phase 2 — Test Strategy Definition

Based on Phase 1 findings, define the test strategy for this specific project:

```
TEST STRATEGY: [Project Name]

Framework: [detected test framework]
Coverage tool: [detected or recommended]
Coverage target: [% based on project type — prototype: 60%, MVP: 75%, production: 90%]

Layers to implement:
  □ Unit tests — [N gaps to fill, estimated N new test cases]
  □ Integration tests — [N gaps to fill]
  □ E2E tests — [applicable: yes/no, N critical flows]
  □ Contract tests — [applicable if microservices/APIs]
  □ Performance tests — [applicable if hot paths identified]
  □ Security tests — [applicable if auth/data handling present]

Priority order: [ordered list of what to test first]
```

---

## Phase 3 — Test Implementation (Parallel, 4 Agents)

Spawn **4 parallel agents** based on the strategy. Assign work by module domain, not by test type, to avoid file conflicts.

Each agent receives: their assigned module list, the gap analysis for those modules, and the quality standards below.

### Quality Standards Every Agent Must Follow:

**Structure**
- One test file per source file (co-located or in mirrored `/tests` directory)
- Test file name mirrors source: `payments.ts` → `payments.test.ts`
- Group tests with `describe` blocks matching the function/class being tested
- Test names must be full sentences: `"should return 404 when user does not exist"` not `"user 404"`

**Coverage Requirements per Function**
- Happy path: the expected successful case
- All distinct failure modes: each error condition tested separately
- Boundary values: empty, null, zero, max, min where applicable
- Type coercion edge cases (if dynamically typed language)
- Async error handling: rejected promises, thrown errors in async context

**Test Isolation**
- Every test must be independently runnable — no shared mutable state
- All external dependencies must be mocked/stubbed at the layer boundary
- Database tests use transactions rolled back after each test, or isolated test DB
- File system tests use temp directories cleaned up in `afterEach`
- Time-dependent tests mock the clock — never use `Date.now()` or `new Date()` directly

**Mock Discipline**
- Mocks must match the actual interface of the real dependency (use type-safe mocks)
- Never mock internal implementation details — only mock at module/service boundaries
- Document why each mock exists: `// Mock: isolate from DB, tested in integration layer`
- Integration tests use real implementations, not mocks

**Assertion Quality**
- Assert specific values, not just truthy/falsy
- For objects, assert the specific fields that matter — not `toEqual(entireObject)` for partial checks
- For errors, assert both the error type AND the error message
- For async flows, assert the final state AND any side effects (calls made, events emitted)

---

## Phase 4 — Integration & E2E Test Layer

For integration tests:
- Test the full stack from API boundary to database (or real service)
- Use a dedicated test database that is seeded with known fixtures before each test run
- Test the exact HTTP request/response shape (status codes, headers, body schema)
- Test authentication and authorization: authenticated requests, unauthenticated requests, wrong-role requests
- Test pagination, filtering, sorting if applicable
- Test rate limiting and request size limits if applicable

For E2E tests (if applicable):
- Cover ONLY the critical user journeys — not every permutation
- Critical journeys are: user onboarding, core value delivery, payment/subscription, error recovery
- E2E tests run against a deployed instance (staging or local with real services)
- E2E tests must be deterministic: seed known state before each test, clean up after
- E2E tests must have explicit wait conditions — never fixed `sleep()` calls

---

## Phase 5 — Test Verification & Hardening

After all agents complete:

1. **Run full test suite** — capture output
2. **Check coverage report** — verify target met per module
3. **Fix any failures** — agents must fix their own failures before reporting done
4. **Flakiness check** — run the suite 3 times; flag any test that produces different results across runs
5. **Performance check** — flag any test that takes >500ms (unit), >2s (integration), >30s (E2E) without justification

---

## Phase 6 — Test Infrastructure Files

Create or update these files:

### `.claude/commands/test.md` — project-specific test runner command
```markdown
---
name: test
description: Run tests for [Project Name]
---

## Run All Tests
```bash
[exact command]
```

## Watch Mode
```bash
[exact command]
```

## Coverage Report
```bash
[exact command]
```

## Filter by Module
```bash
[exact command with filter flag]
```

## On Failure
If tests fail, spawn parallel agents grouped by failure domain:
- Spawn one agent per failing test file
- Each agent reads the error, reads the source, fixes the test or the source (whichever is wrong)
- Re-run after all agents complete
```

### `tests/README.md` — test organization guide
Document: test structure, how to add tests, how to run subsets, how to write mocks, how to add fixtures.

---

## Phase 7 — Test Report

Output `TEST_REPORT.md`:

```markdown
# Test Report: [Project Name]
Date: [date]

## Summary
- Total tests: [N]
- Passing: [N]
- Failing: [N]
- Skipped: [N]
- Overall coverage: [%]

## Coverage by Module
| Module | Before | After | Gap Status |
|--------|--------|-------|------------|
| ...    | [%]    | [%]   | ✅ / ⚠️ / ❌ |

## New Tests Added
- Unit: [N]
- Integration: [N]
- E2E: [N]

## Remaining Gaps
[Any coverage gaps below target with justification for deferral]

## Flaky Tests
[List or "none"]

## Test Quality Issues Resolved
[List of issues found in Phase 1 and how they were fixed]
```

---

## Testing Rules (Non-Negotiable)

1. **Test intent, not implementation** — tests must survive refactors that don't change behavior
2. **One reason to fail** — each test asserts exactly one behavior; split multi-concern tests
3. **No test skips without comments** — `skip`/`xit`/`xtest` must have a comment explaining why
4. **Tests are production code** — apply the same naming, structure, and review standards as source code
5. **Red before green** — when adding a test for a known bug, verify it fails before fixing the bug
6. **Test the contract, not the mock** — if a test only proves the mock works, it provides zero value
7. **Coverage is a floor, not a goal** — 90% coverage with bad assertions is worse than 70% with precise ones