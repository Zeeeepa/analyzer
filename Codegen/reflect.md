---
name: reflect
description: Perform a structured retrospective on recent work — what was built, what was decided, what went wrong, what was learned, and what must change before continuing
---

Perform a deep, honest retrospective on the work done in this session or on the current state of the codebase. This command forces a full stop — no new code, no new features — until the reflection is complete and its outputs are recorded.

**Usage**:
- Run after completing a feature, fixing a bug, or finishing a work session
- Run when something broke unexpectedly and you need to understand why
- Run when the codebase feels messy, confusing, or hard to reason about
- Run before starting a new phase of work to clear accumulated confusion

---

## Phase 1 — Work Inventory

Spawn **2 parallel agents**:

### Agent 1 — What Was Actually Built
- Read git log, diff, or recent file modifications to catalog all changes made
- For each changed file: what was the intent, what was actually done, do they match?
- Identify any work that was started but not finished (partial implementations, TODOs added, commented-out code)
- Identify any work that was done but not committed or documented
- Output: exact list of changes with intent vs. reality comparison

### Agent 2 — Decision Log Reconstruction
- Identify all architectural, implementation, and design decisions made during this work
- For each decision: what alternatives were available, why was this choice made, what assumptions does it rely on?
- Flag any decisions that were made under time pressure, uncertainty, or incomplete information
- Flag any decisions that contradict earlier decisions in the same codebase
- Output: decision log with risk ratings

---

## Phase 2 — Failure & Friction Analysis

Answer these questions honestly. Read actual code and git history — do not rely on memory.

### What Broke?
- List every bug introduced, every test that failed, every unexpected behavior
- For each: what was the root cause — logic error, wrong assumption, missing edge case, dependency issue?
- Classify root cause type:
  - `ASSUMPTION` — the code was based on a false assumption about inputs, state, or behavior
  - `COMPLEXITY` — the logic was too complex and a case was missed
  - `COUPLING` — a change in one place unexpectedly broke another place
  - `MISSING_CONTEXT` — the right information wasn't available at decision time
  - `RUSHED` — the decision was made too quickly without sufficient analysis

### What Was Harder Than Expected?
- Identify every place where progress stalled, required rework, or took longer than it should
- For each: was the difficulty inherent in the problem, or was it caused by the codebase's structure?
- Identify any areas where the existing code made the work unnecessarily hard

### What Was Confusing?
- Identify any part of the codebase that was misunderstood during this work
- Identify any naming, structure, or behavior that was misleading
- Identify any documentation that was missing or wrong

---

## Phase 3 — Quality Delta Assessment

Compare the codebase state before and after the work on these dimensions:

| Dimension | Before | After | Direction |
|-----------|--------|-------|-----------|
| Test coverage | [%/description] | [%/description] | ↑ / ↓ / → |
| Lint/type errors | [count] | [count] | ↑ / ↓ / → |
| Architectural clarity | [rating] | [rating] | ↑ / ↓ / → |
| Documentation completeness | [rating] | [rating] | ↑ / ↓ / → |
| Technical debt | [rating] | [rating] | ↑ / ↓ / → |

**Rule**: If any dimension went in the wrong direction (↓), it must be listed as a remediation item.

---

## Phase 4 — Learnings Extraction

Produce concrete, actionable learnings — not vague observations. Each learning must be a rule that changes future behavior.

### Format for each learning:
```
LEARNING [N]
Observation: [What happened]
Root cause: [Why it happened]
Rule: [The specific behavior change this requires going forward]
Applies to: [This project only / All projects / This language / This pattern]
Priority: [Must apply immediately / Apply next session / Good to know]
```

**Minimum 3 learnings required.** If fewer than 3 genuine learnings exist, the reflection is not deep enough — dig further.

---

## Phase 5 — Debt Register Update

Identify all technical debt created or discovered during this work. Classify each item:

```
DEBT [N]
File: [path:line]
Type: [Shortcut / Missing test / Missing docs / Architectural compromise / Hardcoded value / TODO]
Description: [What the problem is]
Risk if left: [Low / Medium / High / Critical]
Estimated effort to fix: [Trivial / Small / Medium / Large]
Fix before: [Next commit / Next feature / Next sprint / Someday]
```

---

## Phase 6 — Pre-Continuation Checklist

Before any new work begins, verify each item:

```
□ All broken tests are fixed (or explicitly deferred with documented reason)
□ No new lint or type errors were introduced
□ All TODOs added during this work are registered in the debt register
□ All partial implementations are documented (not left as silent dead code)
□ Decision log is written and justified
□ At least 3 learnings are extracted and written as rules
□ Any confusion about the codebase is resolved (re-read confusing code, add comments, ask questions)
□ The next step is clearly defined (not "continue working" — a specific, bounded task)
```

**Do not continue to new work until all boxes are checked or explicitly deferred with written justification.**

---

## Output: REFLECTION.md

Write all findings to `REFLECTION.md` (append if file exists, do not overwrite history):

```markdown
# Reflection — [date] [session/feature name]

## Work Inventory
[Agent 1 output]

## Decisions Made
[Agent 2 output]

## What Broke & Why
[Phase 2 findings]

## Quality Delta
[Phase 3 table]

## Learnings
[Phase 4 — each learning in structured format]

## Debt Register
[Phase 5 — each debt item]

## Pre-Continuation Checklist
[Phase 6 — with check/defer status]

## Next Step
[Single, specific, bounded task to start next]

---
```

Tell the user: reflection is complete, summary of key findings, and the single next step.

---

## Reflection Rules (Non-Negotiable)

1. **Full stop** — no new implementation work until reflection is written to file
2. **Evidence-based** — every finding must reference actual code, actual errors, or actual git history
3. **No minimization** — do not soften failures or debt; name them precisely
4. **Forward-looking learnings** — every observation must convert to a behavioral rule, not just an acknowledgment
5. **Debt is permanent record** — debt items are never deleted from REFLECTION.md, only marked resolved
6. **One next step** — reflection ends with exactly one bounded, specific next action — not a list of things to do