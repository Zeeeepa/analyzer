---
name: suitability
description: Analyze how effective, relevant, and helpful a codebase is as a foundation or reference for building a specified target program — producing a scored, evidence-based suitability report
---

Evaluate how well codebase `$CODEBASE` serves as a foundation, reference, or dependency for building `$TARGET`. Produce a structured, scored, evidence-based suitability assessment that answers: **should you build on this, adapt it, extract from it, or ignore it?**

**Usage**: `/suitability [codebase name or path] for [target program description]`

Example: `/suitability ./payments-sdk for a multi-tenant SaaS billing system`

If either argument is missing, ask:
1. *"Which codebase are you evaluating? (name, path, or describe it)"*
2. *"What are you building? Describe features, scale, and constraints."*

Store as `$CODEBASE` and `$TARGET_DESC`.

---

## Phase 1 — Dual Reconnaissance (Parallel, 2 Agents)

Spawn **2 parallel agents** to independently characterize both sides before any comparison.

### Agent A — Codebase Characterization
Produce an objective profile of `$CODEBASE`:
- **Capabilities**: what does it actually do? (read source, not just README)
- **Architecture**: layers, patterns, boundaries, dependencies
- **Exposed interfaces**: public APIs, extension points, configurable behaviors
- **Constraints**: hardcoded assumptions, fixed data models, non-negotiable design decisions
- **Quality indicators**: test coverage, documentation level, error handling maturity
- **Activity signals**: last commit date, open issues, dependency freshness
- **Identified risks**: known bugs, deprecated dependencies, architectural anti-patterns
- **Adaptability score**: how easily can this codebase be extended, modified, or composed?

### Agent B — Target Requirements Profile
Decompose `$TARGET_DESC` into concrete requirements:
- **Functional requirements**: every discrete capability the target program must have
- **Non-functional requirements**: scale, latency, throughput, availability, security, compliance
- **Integration requirements**: what external systems must it connect to?
- **Data requirements**: what data models are needed, what volume, what consistency guarantees?
- **Deployment requirements**: cloud, on-prem, edge, serverless, containerized?
- **Team/maintenance requirements**: how complex can the codebase be to maintain?
- **Timeline constraints**: is this a 2-week prototype or a 2-year production system?
- **Priority stack-rank**: order requirements by importance — what is non-negotiable vs. nice-to-have?

---

## Phase 2 — Multi-Dimensional Suitability Analysis (Parallel, 6 Agents)

Spawn **6 parallel agents**, each analyzing one suitability dimension. Each agent must produce a score (0–10) with specific evidence — no scores without justification.

### Agent 1 — Functional Coverage
**Question**: Does the codebase provide the building blocks needed for `$TARGET`?

For each requirement in Agent B's functional list:
- Does the codebase directly implement this? (score: 2 pts)
- Does the codebase partially implement this? (score: 1 pt)
- Is this completely absent? (score: 0 pts)
- Does the codebase do something that CONFLICTS with this requirement? (score: -1 pt)

```
Functional Coverage Score: [sum] / [max possible]
Coverage %: [%]
Directly covered: [list]
Partially covered: [list — what's missing]
Absent: [list]
Conflicting: [list — why it conflicts]
```

### Agent 2 — Architectural Compatibility
**Question**: Does the codebase's architecture work for `$TARGET`'s constraints?

Evaluate:
- **Layer alignment**: do the architectural layers match what `$TARGET` needs?
- **Scalability fit**: is the architecture suitable for `$TARGET`'s scale requirements?
- **Data model compatibility**: do the existing data models match or work against `$TARGET`'s needs?
- **Dependency compatibility**: do the codebase's dependencies conflict with `$TARGET`'s stack?
- **Pattern compatibility**: are the design patterns used compatible with how `$TARGET` needs to work?
- **Coupling exposure**: how much of the codebase would you be forced to take in order to use the parts you need?

Score: 0–10 with specific evidence for each sub-point.

### Agent 3 — Adaptability & Extension Cost
**Question**: How much work is required to make this codebase serve `$TARGET`?

For each gap between the codebase and `$TARGET` requirements, estimate:
- Is this gap fillable by **extension** (adding new code without changing existing code)?
- Is this gap fillable by **configuration** (changing settings, flags, environment)?
- Does this gap require **modification** (changing existing code with regression risk)?
- Does this gap require **replacement** (ripping out and rewriting core components)?

```
Extension items: [N] — [list]
Configuration items: [N] — [list]
Modification items: [N] — [list — with regression risk assessment]
Replacement items: [N] — [list — with estimated effort]
```

Produce a total adaptation effort estimate:
- `TRIVIAL` — <1 day, configuration or minor additions only
- `LOW` — 1–5 days, extension only, no core modifications
- `MEDIUM` — 1–3 weeks, some core modifications, some replacement
- `HIGH` — 1–3 months, significant replacement of core components
- `PROHIBITIVE` — rewriting from scratch would be faster

Score: 0–10 (10 = trivial, 0 = prohibitive)

### Agent 4 — Risk & Reliability Assessment
**Question**: Does building on this codebase introduce risks into `$TARGET`?

Evaluate:
- **Maintenance risk**: is this codebase actively maintained? What's the bus factor?
- **Dependency risk**: does it rely on deprecated, abandoned, or vulnerable packages?
- **Security risk**: are there known vulnerabilities, exposed attack surfaces, or insecure defaults?
- **Stability risk**: are there known bugs or edge cases that would affect `$TARGET`?
- **License risk**: is the license compatible with `$TARGET`'s intended use and distribution?
- **Coupling risk**: if you depend on this, how locked in are you? What's the exit cost?
- **Versioning risk**: does this codebase have a stable API contract, or does it break between versions?

Score: 0–10 (10 = zero risk, 0 = high risk across multiple dimensions)

### Agent 5 — Quality & Maintainability Fit
**Question**: Is the code quality level appropriate for `$TARGET`'s production requirements?

Evaluate:
- **Test coverage**: is the coverage sufficient for `$TARGET`'s reliability requirements?
- **Documentation**: is it documented well enough for `$TARGET`'s team to work with it?
- **Code clarity**: will `$TARGET`'s development team be able to read, debug, and modify this?
- **Error handling**: is error handling robust enough for `$TARGET`'s production environment?
- **Observability**: does it support the logging/metrics/tracing `$TARGET` requires?
- **Performance baseline**: is performance acceptable for `$TARGET`'s requirements, or will it be a bottleneck?

Score: 0–10

### Agent 6 — Strategic Fit Assessment
**Question**: Does using this codebase align with `$TARGET`'s longer-term trajectory?

Evaluate:
- **Direction alignment**: is this codebase moving in the same direction `$TARGET` needs to go?
- **Community & ecosystem**: is there a community, ecosystem, and knowledge base that will benefit `$TARGET`?
- **Build vs. buy vs. adapt tradeoff**: compared to alternatives (building from scratch, using a different library, commercial solution), how does this codebase compare in total cost of ownership?
- **Vendor/author dependency**: what is the risk of the original authors abandoning, pivoting, or breaking this?
- **Team fit**: does the codebase's language, framework, and style match the team that will build `$TARGET`?

Score: 0–10

---

## Phase 3 — Weighted Suitability Score

Compute a weighted composite score. Default weights — adjust based on `$TARGET` priorities:

| Dimension | Score (0-10) | Default Weight | Weighted Score |
|-----------|-------------|----------------|----------------|
| Functional Coverage | [score] | 30% | [calc] |
| Architectural Compatibility | [score] | 20% | [calc] |
| Adaptability & Extension Cost | [score] | 20% | [calc] |
| Risk & Reliability | [score] | 15% | [calc] |
| Quality & Maintainability | [score] | 10% | [calc] |
| Strategic Fit | [score] | 5% | [calc] |
| **TOTAL** | | **100%** | **[weighted avg]** |

### Suitability Rating:

| Score | Rating | Meaning |
|-------|--------|---------|
| 8.5–10 | ✅ **STRONGLY RECOMMENDED** | Build directly on this. It covers most needs and adapts cleanly. |
| 7.0–8.4 | ✅ **RECOMMENDED** | Good fit with manageable gaps. Adaptation cost is justified. |
| 5.0–6.9 | ⚠️ **CONDITIONAL** | Useful for specific parts but requires significant adaptation. Extract selectively. |
| 3.0–4.9 | ⚠️ **MARGINAL** | More work to adapt than to build fresh in key areas. Consider alternatives. |
| 0–2.9 | ❌ **NOT RECOMMENDED** | Fundamental misalignment. Building on this creates more problems than it solves. |

---

## Phase 4 — Actionable Recommendation

Based on the score, produce one of these recommendations:

### If STRONGLY RECOMMENDED or RECOMMENDED:
```
RECOMMENDATION: Use as foundation
Strategy: [exactly how to adopt — full dependency, fork, vendored copy]
Start with: [specific modules/packages to integrate first]
Configuration needed: [list]
Extensions to build: [list of gaps to fill]
Estimated onboarding: [time estimate]
First step: [single concrete action]
```

### If CONDITIONAL:
```
RECOMMENDATION: Extract selectively
Use: [specific modules/components worth taking]
Ignore: [parts that don't fit and why]
Build fresh: [what should be written from scratch instead]
Integration approach: [how to use the extracted parts]
Alternative to consider: [if a better fit exists]
First step: [single concrete action]
```

### If MARGINAL or NOT RECOMMENDED:
```
RECOMMENDATION: Do not adopt
Primary blockers: [top 3 reasons with evidence]
What you'd lose: [genuine value that exists in the codebase]
Alternative path: [what to do instead — build from scratch, find another library, etc.]
Parts worth studying: [if any design patterns or approaches are worth referencing]
First step: [single concrete action on the alternative path]
```

---

## Output: SUITABILITY_REPORT.md

Write all findings to `SUITABILITY_REPORT.md`:

```markdown
# Suitability Report
Codebase: [name/path]
Target: [description]
Date: [date]

## Codebase Profile
[Agent A findings — objective characterization]

## Target Requirements
[Agent B findings — prioritized requirement list]

## Dimensional Analysis

### Functional Coverage [score/10]
[Agent 1 findings]

### Architectural Compatibility [score/10]
[Agent 2 findings]

### Adaptability & Extension Cost [score/10]
[Agent 3 findings — including effort estimate]

### Risk & Reliability [score/10]
[Agent 4 findings]

### Quality & Maintainability Fit [score/10]
[Agent 5 findings]

### Strategic Fit [score/10]
[Agent 6 findings]

## Weighted Suitability Score
[Phase 3 table]
**Rating: [STRONGLY RECOMMENDED / RECOMMENDED / CONDITIONAL / MARGINAL / NOT RECOMMENDED]**

## Recommendation
[Phase 4 structured recommendation]

---
*Analysis produced by parallel codebase exploration and target decomposition.*
```

Tell the user: report is complete, overall rating, and the single first step.

---

## Suitability Rules (Non-Negotiable)

1. **Evidence-based scores** — every score requires specific file path, pattern, or capability evidence
2. **No wishful thinking** — score what the codebase IS, not what it could be with heavy modification
3. **Requirement completeness** — every target requirement must be explicitly addressed in the functional coverage analysis
4. **Honest adaptation cost** — if core components need replacing, call it replacement, not "modification"
5. **One recommendation** — the output produces a single decisive recommendation with a single first step
6. **Weight transparency** — if weights are adjusted from defaults, document why