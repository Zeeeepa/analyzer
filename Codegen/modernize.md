---
name: modernize_upgrade
description: Modernize a codebase toward a user-defined trajectory — replace hand-rolled code with best-in-class libraries, eliminate wheel-reinvention, and upgrade all specified contextual targets with verified 2025-2026 ecosystem intelligence
---

Modernize this codebase toward `$TRAJECTORY`. Eliminate hand-rolled implementations where battle-tested libraries exist. Replace outdated patterns with current idioms. Upgrade every specified context to match the target trajectory.

**Usage**: `/modernize_upgrade [trajectory description]`

Examples:
- `/modernize_upgrade toward a production-grade REST API with full observability`
- `/modernize_upgrade to modern TypeScript with strict types and edge-ready runtime`
- `/modernize_upgrade toward event-driven microservices architecture`
- `/modernize_upgrade to 2026 Python async stack with full type safety`

If no trajectory is provided, ask:
*"What direction are you modernizing toward? Describe your target architecture, runtime, scale, or quality bar."*

Store as `$TRAJECTORY`.

---

## Phase 1 — Modernization Intelligence Gathering (Parallel, 4 Agents)

Spawn **4 parallel agents** in a single response before any code changes.

### Agent 1 — Wheel Reinvention Audit
Hunt for every instance where custom code duplicates functionality that a well-maintained library provides better.

**Scan for these patterns:**
- Custom HTTP clients instead of `axios`, `got`, `ky`, `httpx`, `aiohttp`
- Custom date/time parsing instead of `date-fns`, `dayjs`, `Temporal`, `arrow`, `pendulum`
- Custom validation schemas instead of `zod`, `valibot`, `pydantic`, `joi`, `yup`
- Custom environment/config parsing instead of `dotenv-safe`, `envalid`, `pydantic-settings`, `viper`
- Custom retry/backoff logic instead of `p-retry`, `tenacity`, `backoff`, `resilience4j`
- Custom queue/job processing instead of `BullMQ`, `bee-queue`, `celery`, `arq`, `temporal`
- Custom rate limiting instead of `bottleneck`, `limiter`, `slowapi`, `ratelimit`
- Custom deep clone/merge instead of `structuredClone`, `lodash/cloneDeep`, `immer`
- Custom UUID/ID generation instead of `uuid`, `nanoid`, `ulid`, `cuid2`
- Custom CSV/JSON/YAML parsing instead of `papaparse`, `fast-csv`, `pyyaml`, `orjson`
- Custom auth flows instead of `passport`, `lucia`, `better-auth`, `authjs`, `python-jose`
- Custom caching layers instead of `node-cache`, `lru-cache`, `cachetools`, `dogpile.cache`
- Custom test factories/fixtures instead of `faker`, `fishery`, `factory-boy`, `polyfactory`
- Custom logging instead of `pino`, `winston`, `structlog`, `loguru`, `zerolog`
- Custom metric collection instead of `prom-client`, `opentelemetry`, `statsd`, `micrometer`
- Custom migration tooling instead of `knex`, `drizzle`, `alembic`, `flyway`, `goose`
- Custom ORM queries instead of using the ORM's built-in advanced features
- Custom cryptography instead of `bcrypt`, `argon2`, `nacl`, `cryptography` (Python)
- Any `for` loop doing what `.map()`, `.filter()`, `.reduce()`, `itertools`, or stream APIs handle
- Any regex-based router or template engine instead of a proper framework feature
- Any hand-written state machine instead of `xstate`, `stately`, `transitions`, `robot3`

For each finding:
```
[REINVENTION] file:line
What it does: [description]
Replace with: [library name + version]
Benefit: [what the library provides that custom code doesn't — e.g., edge cases handled, battle-tested, maintained]
Migration complexity: [Drop-in / Low / Medium / High]
```

### Agent 2 — Trajectory Gap Analysis
Map the current codebase against `$TRAJECTORY` and identify every gap.

For each dimension of `$TRAJECTORY`:
- What does the trajectory require?
- What does the codebase currently have?
- What is the gap?
- What is the specific library, pattern, or change that closes the gap?

**Trajectory dimensions to evaluate** (filter to those relevant to `$TRAJECTORY`):

| Dimension | Questions to Answer |
|-----------|-------------------|
| **Runtime/Platform** | Is the runtime (Node version, Python version, Go version) current for the trajectory? |
| **Type Safety** | Is there full type coverage? Are `any`/untyped patterns present? |
| **Async Patterns** | Are async patterns modern? (callbacks→promises→async/await→streaming) |
| **API Design** | REST/GraphQL/tRPC/gRPC — does the current shape match the trajectory? |
| **Data Layer** | Is the ORM/query layer appropriate for the trajectory's data needs? |
| **Auth & Security** | Does auth match modern standards (JWTs, OAuth2, PKCE, passkeys)? |
| **Observability** | Are logs structured? Are traces distributed? Are metrics exported? |
| **Error Handling** | Are errors typed, propagated cleanly, and user-safe? |
| **Build Pipeline** | Is the build system modern for the trajectory (ESM, Turbopack, Rye, etc.)? |
| **Testing Stack** | Does the test framework match the trajectory's requirements? |
| **Deployment Target** | Is code shaped for the target deployment (edge, serverless, container, monolith)? |
| **Performance** | Are bottlenecks present that the trajectory would expose at scale? |
| **Developer Experience** | Hot reload, type-checking, linting — are they fast enough for the trajectory? |

For each gap:
```
[GAP] Dimension: [name]
Current state: [what exists]
Trajectory requires: [what's needed]
Library/change: [specific recommendation — verified via WebSearch]
Priority: [Blocking / High / Medium / Low]
```

### Agent 3 — Ecosystem Intelligence (WebSearch Required)
For every library identified by Agents 1 and 2, verify currency using WebSearch. No assumptions from training data.

For each candidate library:
1. Search: `"[library name] latest version 2025"` or `"[library name] changelog"`
2. Verify: latest stable version number
3. Verify: last commit date / release date (is it actively maintained?)
4. Verify: any known breaking changes between current installed version and latest
5. Verify: whether a newer alternative has overtaken it (e.g., `moment` → `date-fns` → `Temporal`)
6. Check: GitHub stars trajectory (growing/stable/declining)
7. Check: any security advisories (CVEs) against the library

Output per library:
```
Library: [name]
Current best version: [X.Y.Z] (verified [date])
Maintained: [yes/no — last release: date]
Migration notes: [any breaking changes from older versions]
Verdict: [ADOPT / ADOPT_WITH_MIGRATION / SUPERSEDED_BY: name / AVOID: reason]
Source: [URL]
```

### Agent 4 — Dead Code & Modernization Blockers
Identify what must be cleaned up BEFORE modernization can proceed safely:

- **Circular dependencies** that would make library injection hard
- **God files** that mix concerns and will need splitting before a library swap makes sense
- **Implicit global state** that would break when switching to a stateless/functional library
- **Type `any` / untyped surfaces** that would cause silent failures after library migration
- **Hardcoded magic values** that need extracting before config libraries can manage them
- **Dead imports** that inflate dependency surface unnecessarily
- **Duplicate implementations** of the same thing across files (consolidate before replacing)
- **Test coverage gaps** on code that will be replaced (needs tests first so replacement is safe)

For each blocker:
```
[BLOCKER] file:line
Type: [Circular / GodFile / GlobalState / Untyped / Magic / Dead / Duplicate / NoTest]
Description: [what the problem is]
Must fix before: [which modernization step this blocks]
Fix: [minimal pre-flight change]
```

---

## Phase 2 — Modernization Plan

Synthesize Phase 1 findings into a structured plan. Present to the user before executing:

```
MODERNIZATION PLAN
Trajectory: [user's $TRAJECTORY]
Date: [date]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHEEL REINVENTIONS TO REPLACE: [N]
  Drop-in replacements:  [N] (no logic change required)
  Low-effort migrations: [N] (< 2 hours each)
  Medium migrations:     [N] (2–8 hours each)
  High-effort rewrites:  [N] (flag for separate planning)

TRAJECTORY GAPS TO CLOSE: [N]
  Blocking gaps: [N] (must fix before trajectory is achievable)
  High priority: [N]
  Medium/Low:    [N]

PRE-FLIGHT BLOCKERS: [N]
  [list each — these run FIRST]

LIBRARIES TO ADD: [N]
  [list with versions]

LIBRARIES TO REMOVE: [N]
  [list — replaced by above]

ESTIMATED TOTAL EFFORT: [Trivial / Small / Medium / Large / Very Large]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Pause.** Ask the user: *"Does this modernization plan match your intent? Any items to skip, reprioritize, or add before I proceed?"*

---

## Phase 3 — Pre-Flight Cleanup

Before ANY library swaps or trajectory changes, resolve all blockers from Agent 4.

Each blocker is fixed minimally — do not over-engineer. The goal is to make modernization safe, not to refactor the entire codebase.

After all pre-flight fixes:
- Run the full test suite — must pass at baseline before continuing
- Run lint/typecheck — must pass at baseline before continuing
- If either fails, stop and fix before proceeding

---

## Phase 4 — Staged Modernization (Parallel per Domain)

Group modernization items into non-conflicting domains. Spawn **parallel agents per domain** so independent changes don't conflict.

**Recommended domain groupings** (adapt based on actual codebase):

### Domain A — Type System Hardening
If trajectory involves type safety:
- Enable strict TypeScript (`strict: true`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`)
- Replace all `any` with proper types, `unknown`, or type guards
- Add Zod/Valibot schemas at all I/O boundaries (API inputs, env vars, config files, DB results)
- Generate types from schemas rather than maintaining parallel type definitions

### Domain B — Library Swap — Drop-in Replacements
Handle all `Migration complexity: Drop-in` items from Agent 1:
- Remove the custom implementation
- Install the library
- Replace usages (API is compatible — this is near-mechanical)
- Run tests after each swap to catch any behavioral difference
- Remove the now-dead custom code

### Domain C — Library Swap — Behavioral Migrations
Handle `Low` and `Medium` complexity migrations:
- For each: write characterization tests against the OLD implementation first (capture current behavior)
- Install new library
- Implement new version alongside old (do not delete yet)
- Verify characterization tests pass with new implementation
- Switch call sites to new implementation
- Delete old implementation
- Run full test suite

### Domain D — Trajectory-Specific Upgrades
Implement the gaps identified by Agent 2, in priority order:
- Blocking gaps first
- Each gap gets its own sub-task with: implement → test → verify approach
- Apply the library or pattern recommended in the gap analysis
- Update all affected files to use the new approach
- Do not leave hybrid states (half old, half new) — complete each gap fully

### Domain E — Observability & Production Readiness
If trajectory includes production-grade requirements:
- Add structured logging (replace `console.log` / `print` with `pino`/`structlog`/`zerolog`)
- Add OpenTelemetry instrumentation (traces, metrics, logs)
- Add health check endpoints (`/health`, `/ready`, `/live`)
- Add graceful shutdown handling
- Ensure all errors are logged with context (request ID, user ID, trace ID)
- Ensure no secrets appear in logs or error responses

---

## Phase 5 — Post-Modernization Verification (Parallel, 3 Agents)

Spawn **3 parallel agents** after all domain changes complete.

### Verifier 1 — Regression Suite
- Run the full test suite
- Every failure must be triaged: is this a test that needs updating (behavior intentionally changed) or a regression (behavior was broken)?
- Report: pass/fail delta vs. pre-flight baseline

### Verifier 2 — Wheel Reinvention Rescan
- Re-run the Agent 1 scan patterns on the updated codebase
- Confirm every identified reinvention was replaced
- Flag any NEW reinventions introduced during modernization (they sometimes appear during refactors)
- Confirm removed custom implementations have zero remaining references

### Verifier 3 — Trajectory Compliance Check
- For each gap identified in Agent 2, verify the gap is now closed
- Verify the codebase demonstrably moves toward `$TRAJECTORY` — not just that changes were made
- Produce a before/after comparison per trajectory dimension
- Identify any remaining gaps that were scoped out (document them as deferred)

---

## Phase 6 — Dependency Audit & Lock

After all changes:

```bash
# Confirm no unused dependencies remain
# [npm: depcheck | Python: deptry | Go: go mod tidy | Rust: cargo machete]

# Confirm no duplicate packages at different versions
# [npm: npm dedupe | Python: pip check]

# Confirm no security vulnerabilities introduced
# [npm: npm audit | Python: pip-audit | Go: govulncheck | Rust: cargo audit]

# Update lockfile to reflect final state
# [appropriate lock command for the detected package manager]
```

Fix any audit findings before completing.

---

## Phase 7 — Modernization Report

Write `MODERNIZATION_REPORT.md`:

```markdown
# Modernization Report
Trajectory: [user's $TRAJECTORY]
Date: [date]

## Before State
- Wheel reinventions found: [N]
- Trajectory gaps found: [N]
- Libraries replaced: [N]
- Test suite baseline: [N passing / N failing]

## Changes Made

### Wheel Reinventions Replaced
| Was | Replaced With | Version | Complexity |
|-----|--------------|---------|-----------|
| [custom code description] | [library] | [ver] | Drop-in/Low/Med |

### Trajectory Gaps Closed
| Dimension | Was | Now | Library/Change |
|-----------|-----|-----|---------------|
| [name] | [before] | [after] | [what was added] |

### Libraries Added
| Package | Version | Purpose |
|---------|---------|---------|

### Libraries Removed
| Package | Replaced By | Reason |
|---------|------------|--------|

## After State
- Test suite: [N passing / N failing]
- Lint/typecheck: [clean / N issues]
- Security audit: [clean / N findings]
- Unused deps: [none / N removed]

## Deferred Items
[Anything scoped out with justification — forms the next modernization backlog]

## Trajectory Progress
| Dimension | Before | After | Complete? |
|-----------|--------|-------|-----------|
| [each trajectory dimension] | [rating] | [rating] | ✅ / ⚠️ partial / ❌ deferred |

## Overall Trajectory Alignment
[Before: X% → After: Y%]
[One paragraph: what the codebase can now do that it couldn't before]

---
*Modernization verified by parallel rescan. All replaced libraries confirmed absent.*
```

---

## Modernization Rules (Non-Negotiable)

1. **Trajectory is the north star** — every change must move toward `$TRAJECTORY`, not just improve code generally
2. **Verify before recommending** — every library recommendation must be confirmed current via WebSearch; no training-data version assumptions
3. **Characterization tests before replacement** — any behavioral migration must have tests capturing current behavior before the swap
4. **Complete each swap** — do not leave codebases in hybrid states; each replacement is fully done before the next begins
5. **Drop-ins first** — execute no-risk drop-in replacements before tackling complex behavioral migrations
6. **Zero new reinventions** — do not introduce new hand-rolled code that a library could provide during the modernization itself
7. **Library not bloat** — only add a library if it replaces more code than it introduces; a 3-line utility does not justify a new dependency
8. **Blockers before modernization** — pre-flight cleanup always runs before library swaps; never swap into unstable ground
9. **Audit before lock** — dependency security audit always runs after all changes, before reporting complete
10. **Deferred is documented** — any item scoped out must appear in the MODERNIZATION_REPORT deferred section with specific justification; nothing is silently dropped