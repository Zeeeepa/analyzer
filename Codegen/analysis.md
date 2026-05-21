---
name: analysis
description: Spawn parallel agents to produce a deep, comprehensive, multi-dimensional codebase analysis — architecture, flows, APIs, quality, and onboarding
---

Perform a complete, exhaustive analysis of this codebase. Spawn **9 parallel agents** using the Task tool (subagent_type: Explore) in a **single response**. Each agent owns one analytical dimension. No agent may speculate — every finding must reference actual file paths, line numbers, or content read from the repository.

---

## Agent Assignments

### Agent 1 — Repository Topology & Module Map
- List every top-level directory with its precise purpose
- Identify sub-modules, workspaces, packages, or monorepo members
- Identify major architectural layers (e.g., API, domain, data access, UI, infrastructure, scripts, shared libs) and describe how they relate to one another
- Produce a text tree of the repo at 2–3 levels deep with inline annotations
- Flag any directories whose purpose is ambiguous or redundant

### Agent 2 — Entrypoints & Execution Flows
- Find ALL entrypoints: CLIs, HTTP servers, background workers, schedulers, event listeners, framework bootstraps (main(), app factories, WSGI/ASGI apps, server start scripts, lambda handlers)
- For each entrypoint, trace the high-level control flow from external trigger → request parsing → business logic dispatch → response/side effect
- Note middleware chains, plugin hooks, and lifecycle hooks involved
- Identify startup/teardown sequences and what they initialize or release
- Flag any entrypoints that are dead, unreachable, or unregistered

### Agent 3 — Data Flows & Transformation Paths
- Trace all major data flows: where data enters (HTTP, CLI args, message queues, files, DB reads, environment), how it is transformed, and where it exits (HTTP response, DB write, file write, queue publish, external API call)
- Identify every read/write path to persistent stores (databases, caches, files, object storage)
- Summarize key data transformation steps: parsing, validation, enrichment, serialization
- Produce text descriptions ready to render as:
  - **Component Diagram**: list every major module/service and its named dependencies
  - **Sequence Diagram (primary use-case)**: step-by-step actor→system message flow for the single most important operation (e.g., core API endpoint or main CLI command)
  - **Sequence Diagram (secondary use-case)**: next most important operation
- Flag any data that flows without validation, sanitization, or error handling

### Agent 4 — APIs, Interfaces & Public Contracts
- Enumerate ALL public interfaces: exported functions, classes, REST endpoints, gRPC services, CLI commands, WebSocket events, plugin extension points, SDK entry surfaces
- For each, document: purpose, parameters (name + type), return type/shape, side effects, error conditions, and expected caller behavior
- Identify which interfaces are versioned, deprecated, or unstable
- Identify interfaces that lack documentation, input validation, or error contracts
- Flag any breaking changes risk between layers (e.g., internal API used externally)

### Agent 5 — Core Files, Functions & Data Structures
- List the 15–25 most central files in the codebase (highest dependency, most critical logic)
- For each critical function or class, summarize: inputs, outputs, algorithm, and side effects
- Enumerate all core domain models, entities, DTOs, schemas, and database models — including their fields, types, relationships, and validation constraints
- Identify shared utilities, helpers, and constants that are used across 3+ modules
- Document configuration loading: which files, env vars, feature flags, and secrets are read — and when
- Flag any god files, god classes, or functions with excessive cyclomatic complexity

### Agent 6 — Frameworks, Libraries & Tech Stack
- Identify all programming languages, runtimes, and their versions (from lock files, toolchain files, or manifests)
- List all major frameworks (web, ORM, CLI, testing, auth, queuing, etc.) with versions
- Document the full build pipeline: package manager, bundler/compiler, transpilation steps, asset pipeline
- Document how to run the project locally: all required commands from zero to running
- Document how tests are run, and what coverage tooling is present
- Identify containerization (Docker, Compose, K8s manifests) and CI/CD scripts
- Flag any dependency version conflicts, unresolved peer deps, or critically outdated packages

### Agent 7 — Capabilities, Features & Use-Cases
- Summarize what this program does from an end-user perspective — its core value proposition
- List every discrete user-facing feature or capability
- Produce 5 concrete example use-cases in this format:
  ```
  Use-case N: [User goal]
  Trigger: [How user initiates]
  Flow: [Modules A → B → C involved]
  Output: [What the user gets]
  ```
- Identify features that are partially implemented, stubbed out, or marked TODO
- Identify any capability gaps relative to what the README or documentation promises

### Agent 8 — Code Quality, Consistency & Onboarding
- Assess naming consistency: files, functions, variables, constants, types — are conventions followed uniformly?
- Assess modularity: single-responsibility adherence, coupling/cohesion balance, circular dependency presence
- Assess test coverage: what is tested vs. what is untested; identify the riskiest untested paths
- Assess documentation level: inline comments, JSDoc/docstrings, README completeness, architecture docs
- Assess error handling consistency: are errors caught, typed, logged, and propagated uniformly?
- Rate onboarding difficulty (Easy / Medium / Hard / Very Hard) with specific justification
- Identify the top 5 most confusing or undiscoverable parts of the codebase for a new developer

### Agent 9 — Strengths, Risks & Strategic Assessment
- Identify the top 5 architectural strengths with specific evidence (file/pattern references)
- Identify the top 5 technical risks: scalability bottlenecks, single points of failure, security exposure, maintainability debt
- Identify any anti-patterns present (e.g., anemic domain model, leaky abstractions, spaghetti dependencies)
- Rate overall implementation comprehensiveness on this scale — with justification:
  - `1 — Skeleton`: scaffolding only, nothing functional
  - `2 — Prototype`: core path works, major gaps elsewhere
  - `3 — MVP`: primary use-cases work end-to-end, many edge cases missing
  - `4 — Solid`: production-capable, tested, documented
  - `5 — Production-Grade`: hardened, observable, fully documented, extensible
- State explicitly: what is this codebase best suited for, and where would it be ill-suited?

---

## Agent Rules

1. Read actual source files — no assumptions about what code probably does
2. Every claim must reference a specific file path or line number
3. If a file cannot be read, note it explicitly and skip rather than guess
4. Do not report opinions or preferences — only structural facts and verified patterns
5. Agents 1–8 are purely descriptive; Agent 9 is the only agent permitted to make evaluative judgments

---

## Synthesis & Output

After all 9 agents complete, synthesize their findings into a single `ANALYSIS.md` file at the project root using this exact structure:

```markdown
# CODEBASE ANALYSIS: [Project Name]
Generated: [date]
Analyst: Claude (parallel 9-agent exploration)

---

## 1. Repository Topology

[From Agent 1 — tree + layer map]

## 2. Entrypoints & Execution Flows

[From Agent 2 — each entrypoint with control flow]

## 3. Data Flows & Architecture Diagrams

### 3a. Component Diagram (text)
### 3b. Sequence Diagram — [Primary Use-Case Name]
### 3c. Sequence Diagram — [Secondary Use-Case Name]

[From Agent 3]

## 4. APIs, Interfaces & Public Contracts

[From Agent 4 — full enumeration with signatures]

## 5. Core Files, Functions & Data Structures

[From Agent 5 — central files, critical functions, domain models]

## 6. Frameworks, Libraries & Tech Stack

[From Agent 6 — full stack + run instructions]

## 7. Capabilities, Features & Use-Cases

[From Agent 7 — feature list + 5 use-cases]

## 8. Code Quality & Onboarding Assessment

[From Agent 8 — quality metrics + onboarding rating]

## 9. Strengths, Risks & Strategic Assessment

[From Agent 9 — strengths, risks, comprehensiveness rating, suitability]

---
*Analysis produced by parallel codebase exploration. All findings reference actual source files.*
```

Write the file, then tell the user it's ready and how many files were analyzed.