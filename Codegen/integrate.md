---
name: integrate
description: Safely integrate a new feature into the codebase using parallel analysis, contract-first design, staged implementation, and zero-regression verification
---

Integrate the requested feature into the codebase with zero regressions, full contract definition, and verified consistency with existing architecture. This command enforces a rigorous multi-phase process before a single line of production code is written.

**Usage**: Describe the feature to integrate. If no description is given, ask: *"What feature are you integrating? Describe its inputs, outputs, and expected behavior."*

Store the feature description as `$FEATURE_DESC`.

---

## Phase 1 — Pre-Integration Intelligence (Parallel, 5 Agents)

Spawn **5 parallel explore agents** in a single response before writing any code.

### Agent A — Codebase Impact Map
- Identify every file, module, and layer that the new feature will touch, extend, or depend on
- Find all existing patterns the feature must conform to (naming conventions, file organization, module boundaries)
- Identify the exact insertion points: where new code must be added, where existing code must be modified
- Flag any areas where the feature would introduce coupling that doesn't currently exist
- Output: `IMPACT.md` — list of files to create, files to modify, risk level per file (Low/Medium/High)

### Agent B — Contract & Interface Definition
- Define the complete interface contract for the feature BEFORE implementation:
  - Function/method signatures with full parameter types and return types
  - REST endpoint shape (method, path, request body schema, response schema, error responses)
  - Event/message schema if applicable
  - Data model changes (new fields, new tables, migrations required)
- Verify that proposed interfaces don't conflict with existing ones
- Define the feature's error contract: every possible failure mode and its error type/code
- Output: `CONTRACT.md` — machine-readable interface specification

### Agent C — Dependency & Compatibility Audit
- Determine if the feature requires new external dependencies
- For any new dependency: verify it's actively maintained (via WebSearch), check for license compatibility, check for conflicts with existing deps
- Check if any existing dependency already provides the required capability (avoid redundant deps)
- Identify any version constraint implications
- Output: list of required dependency changes with justification

### Agent D — Test Strategy Design
- Design the complete test plan for this feature before implementation:
  - Unit test cases: every function, every branch, every edge case
  - Integration test cases: every interaction with external systems (DB, APIs, queues)
  - E2E test cases: every user-facing flow the feature enables
  - Negative tests: invalid inputs, missing data, permission failures, network failures
  - Performance test considerations if the feature is on a hot path
- Identify which existing tests might be affected or need updating
- Output: `TEST_PLAN.md` — complete test case list with descriptions

### Agent E — Architecture Consistency Review
- Verify that the proposed integration follows the existing architectural patterns exactly:
  - Layer separation (does the feature respect existing boundaries?)
  - Dependency direction (does data flow in the established direction?)
  - Error propagation style (does it match how errors are handled elsewhere?)
  - Logging and observability patterns
  - Authentication/authorization patterns
- Flag any deviations from existing patterns and require explicit justification before proceeding
- Output: architecture compliance checklist

---

## Phase 2 — Integration Plan Review

**Before writing any production code**, synthesize Phase 1 outputs and present to the user:

```
INTEGRATION PLAN: [Feature Name]

Files to CREATE: [N files]
  - [path] — [purpose]

Files to MODIFY: [N files]
  - [path] — [what changes]

New dependencies: [list or "none"]

Contract summary:
  [brief interface description]

Test plan: [N unit, N integration, N E2E tests]

Architecture risks: [list or "none"]

Estimated complexity: [Low / Medium / High / Very High]
```

**Pause here.** Ask the user: *"Does this plan look correct? Shall I proceed with implementation?"*

---

## Phase 3 — Staged Implementation

Implement in this strict order. Do not skip stages. Do not combine stages.

### Stage 1: Data Layer
- Implement any new data models, schemas, migrations, or storage changes first
- Run existing data-layer tests to confirm no regressions
- Do not proceed if any existing test fails

### Stage 2: Core Business Logic
- Implement domain/service layer logic
- Write unit tests for every function as it's implemented (test-alongside, not test-after)
- Every function must have its error contract handled explicitly
- No silent failures, no bare `catch` blocks that swallow errors

### Stage 3: Interface Layer
- Implement the API endpoint, CLI command, or UI component that exposes the feature
- Wire to business logic only — no business logic in the interface layer
- Apply input validation at the interface boundary (not inside business logic)
- Add request/response logging consistent with existing patterns

### Stage 4: Integration Wiring
- Connect all layers end-to-end
- Add integration tests verifying the full path
- Verify the feature's behavior against the CONTRACT.md specification exactly

### Stage 5: Cross-Cutting Concerns
- Add observability: metrics, structured logs, traces — consistent with existing instrumentation
- Add any feature flags if the feature requires progressive rollout
- Update configuration handling if new env vars or config keys are required
- Update documentation: README, API docs, inline docstrings/JSDoc

---

## Phase 4 — Post-Integration Verification (Parallel, 3 Agents)

Spawn **3 parallel agents** after all stages complete.

### Verifier 1 — Regression Check
- Run the full existing test suite
- Report any failures with full error output
- Cross-reference failures against the IMPACT.md list — are all impacted files accounted for?

### Verifier 2 — Contract Compliance
- Verify the implementation matches CONTRACT.md exactly:
  - All defined inputs accepted and validated
  - All defined outputs produced correctly
  - All defined error cases return the correct error type/code
  - No undocumented behaviors introduced

### Verifier 3 — Consistency Audit
- Verify the new code follows all project conventions:
  - Naming conventions match existing code
  - File organization matches existing structure
  - Error handling style matches existing patterns
  - No linting or type errors introduced
  - No hardcoded values that should be config

---

## Phase 5 — Integration Report

Output a final `INTEGRATION_REPORT.md`:

```markdown
# Integration Report: [Feature Name]
Date: [date]
Status: [COMPLETE / PARTIAL / BLOCKED]

## What Was Built
[Description of what was implemented]

## Files Changed
| File | Change Type | Risk |
|------|------------|------|
| ...  | Created / Modified / Deleted | Low/Med/High |

## Tests Added
- Unit: [N] tests
- Integration: [N] tests
- E2E: [N] tests

## Regressions
[None / list of issues found and resolved]

## Deviations from Plan
[None / list of deviations with justifications]

## Known Limitations
[Any unimplemented edge cases or deferred work]

## How to Test This Feature
[Exact commands or steps]
```

---

## Integration Rules (Non-Negotiable)

1. **Contract first** — interfaces are defined and agreed before any code is written
2. **No side-channel modifications** — do not refactor unrelated code during integration
3. **Test alongside** — tests are written as each stage is implemented, never deferred
4. **Zero new linting errors** — the integration must leave lint/typecheck status no worse than it found it
5. **No silent failures** — every error path must be explicitly handled and logged
6. **Layer discipline** — business logic never lives in interface layer; data access never lives in business layer
7. **One feature per integration** — do not bundle multiple features; if scope creep is detected, stop and flag it