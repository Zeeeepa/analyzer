# CODEBASE ANALYSIS: Codegen Agent Manager v2.0 (Analyzer)
Generated: 2026-03-08
Analyst: Claude (parallel 9-agent exploration)

**Repository**: `Zeeeepa/analyzer`
**Primary Application**: `Codegen/codegen.py` (1,990 lines, 17 classes, 128 functions)
**Total Repository**: 883 files, 461 Python files, 322,057 Python LOC, 264 markdown files

---

## 1. Repository Topology

### Directory Tree (annotated)

```
analyzer/                                    # Root repository
├── Codegen/                               # PRIMARY: Agent manager GUI + templates
│   ├── codegen.py (1,990 lines)           # v2.0 main application (17 classes)
│   ├── codegen_clean.py (2,032 lines)     # v1 variant (legacy)
│   ├── analysis.md                        # Template: 9-agent codebase analysis
│   ├── verify.md                          # Template: 6-agent implementation verification
│   ├── test.md                            # Template: multi-layer test strategy
│   ├── integrate.md                       # Template: 5-phase feature integration
│   ├── modernize.md                       # Template: codebase modernization
│   ├── candy.md                           # Template: quick-win finder (5 agents)
│   ├── carrot.md                          # Template: best-practices verifier
│   ├── reflect.md                         # Template: structured retrospective
│   ├── research-it.md                     # Template: tool/dep research
│   ├── suitability.md                     # Template: codebase fit assessment
│   ├── setup-claude-md.md                 # Setup: CLAUDE.md generation
│   ├── setup-code-quality.md              # Setup: linting/typechecking
│   ├── setup-commits.md                   # Setup: commit conventions
│   ├── setup-tests.md                     # Setup: testing infrastructure
│   ├── setup-updates.md                   # Setup: dependency updates
│   ├── npx-research.md                    # Research: npx/claude-flow toolchain
│   └── REPO_NAME_OPERATE.md              # Template: repo-specific operations
├── Libraries/                             # Analysis toolchain (11,454 lines)
│   └── Analysis/
│       ├── analyzer.py (2,097 lines)      # Comprehensive code analysis engine
│       ├── graph_sitter_adapter.py (5,589)# Graph-sitter structural analysis
│       ├── lsp_adapter.py (563 lines)     # Language Server Protocol integration
│       ├── static_libs.py (2,075 lines)   # Static analysis tools (ruff/mypy/pylint)
│       └── autogenlib_adapter.py (1,130)  # AI-powered error fixing
├── eversale/                              # Agent infrastructure (~300+ Python files)
│   ├── engine/agent/                      # 250+ agent modules
│   │   ├── humanization/                  # Anti-detection (bezier cursor, fingerprints)
│   │   ├── training/                      # Self-play engine, task generator
│   │   ├── executors/                     # Admin, business, SDR, protection
│   │   ├── prompts/                       # Prompt templates
│   │   ├── utils/                         # Cache, error, text utilities
│   │   └── tool/                          # Scheduler tools
│   ├── engine/mcp_servers/                # MCP implementations (filesystem, memory, playwright)
│   ├── engine/ace/                        # Playbook/injection/reflector
│   └── bin/                               # CLI entry points (eversale.js, postinstall.js)
├── api/                                   # API documentation
│   ├── ALL.md (320 KB)                    # Complete API specification
│   ├── REQUIREMENTS.md (35 KB)            # WebChat2API requirements
│   ├── BrowserRequestManager.js (14 KB)   # Browser request automation
│   └── REPOS.md (80 KB)                   # Repository reference data
├── github_analysis/                       # Git analysis tools
│   ├── GIT_fetch.py (151 lines)           # Repository fetcher
│   └── codegen_analysis.py (421 lines)    # Codegen-specific analysis
├── npm_analysis/                          # NPM analysis
│   └── npm_analyzer.py (275 lines)        # Package analyzer
├── docker_analyzer/                       # Docker decomposition
│   ├── docker_decompose.sh                # Container analysis scripts (4 variants)
│   └── decompile_dockerfile4.sh
├── DATA/                                  # Data storage directories
│   ├── GIT/, KNOW/, NPM/                 # Git repos, knowledge base, NPM data
├── codegen.py (2,032 lines)              # v1.0 root-level (hardcoded Windows paths)
├── requirements.txt                       # Python dependencies (60+ packages)
├── README.md (280 lines)                  # System vision document (9 capabilities)
└── Pen.md                                 # Penetration testing reference notes
```

### Architectural Layers

| Layer | Location | Purpose | Classes/Methods |
|-------|----------|---------|-----------------|
| **Domain Models** | `Codegen/codegen.py` L85-171 | Data structures & enums | 5 dataclasses (StepType, FlowStep, FlowTemplate, Project, ExecutionEvent) |
| **Infrastructure** | `Codegen/codegen.py` L248-472 | API client, event log, persistence | EventLog (3), API (9), FlowStore (4), ProjectStore (2) |
| **Orchestration** | `Codegen/codegen.py` L479-770 | DAG execution engine | FlowOrchestrator (16 methods) |
| **UI Dialogs** | `Codegen/codegen.py` L776-1677 | Modal forms & editors | MdPickerDialog, FlowCreateDialog, FlowManagerDialog, CreateRunDialog, ProjectManagerDialog, RunDialog |
| **Dashboard** | `Codegen/codegen.py` L1683-1990 | Main window & orchestration | CodegenManager (23 methods) |
| **Agent Templates** | `Codegen/*.md` (17 files) | Instruction templates for agent runs | analysis, verify, test, integrate, modernize, candy, carrot, reflect, etc. |
| **Analysis Toolchain** | `Libraries/Analysis/` (5 files) | Code analysis with graph-sitter, LSP, static tools | analyzer.py, graph_sitter_adapter.py, lsp_adapter.py, static_libs.py |
| **Agent Engine** | `eversale/` (300+ files) | Browser automation, MCP servers, workflows | Autonomous agents, humanization, skill library, MCP |

### Layer Dependencies
```
Dashboard (CodegenManager) → UI Dialogs → Orchestration (FlowOrchestrator)
                                        → Infrastructure (API, EventLog, FlowStore)
                                        → Domain Models

Agent Templates (*.md) → Loaded by MdPickerDialog → Injected into CreateRunDialog prompts
Libraries/Analysis → NOT currently connected to GUI (standalone CLI tools)
eversale/ → NOT currently connected to GUI (separate agent engine)
```

### Ambiguous/Redundant Items
- `codegen.py` (root) vs `Codegen/codegen.py` — v1 vs v2; root version is obsolete
- `Codegen/codegen_clean.py` — Appears to be another v1 copy; purpose unclear
- `ITEMS.rar` — Binary archive at root; purpose unknown
- `Pen.md` — Penetration testing notes; no connection to agent manager
- `DATA/` directories — Referenced but may be empty in shallow clone


---

## 2. Entrypoints & Execution Flows

### Primary Entrypoint
**File**: `Codegen/codegen.py` lines 1985-1990
```python
if __name__ == "__main__":
    main()  # auto-installs deps → tk.Tk() → CodegenManager(root) → root.mainloop()
```

### Control Flow — Application Startup
```
main() [L1985]
  ├─ Auto-install missing deps (requests, plyer) via pip [L1985-1988]
  ├─ root = tk.Tk()
  └─ CodegenManager(root).__init__() [L1683]
      ├─ _load_stars() → reads ~/.codegen_manager_stars.json [L1694]
      ├─ _build() → creates all UI widgets [L1700]
      │   ├─ Toolbar: New Run, Projects, Flows, Refresh, Settings buttons
      │   ├─ Search bar with text filter
      │   ├─ Treeview with columns: star, id, status, created, summary, prs, source
      │   └─ Flow status bar showing active orchestrations
      └─ _poll_loop() → starts background polling every POLL_SEC (12s) [L1920]
```

### Control Flow — Create & Execute Agent Run
```
User clicks "🚀 New Run" → CreateRunDialog [L1195]
  ├─ User selects Project (combobox) [L1211]
  ├─ User loads .md Template (file picker) [L1268]
  ├─ User edits Prompt (ScrolledText) [L1245]
  ├─ User selects Flow (combobox) [L1276]
  └─ User clicks "🚀 Launch Run" → _launch() [L1344]
      ├─ Thread: API.create_run(prompt) [L1350]
      │   └─ POST /organizations/{ORG_ID}/agent/run [L294-380]
      │       └─ Returns {"id": 12345, "status": "pending", ...}
      └─ _done(response) [L1361]
          ├─ Displays "✅ Run #12345 created!"
          └─ If flow selected: parent._start_flow_runner(run_id, flow) [L1910]
              └─ FlowOrchestrator.__init__(root, run_id, flow, ...) [L479]
                  ├─ _run_flow() in background thread [L536]
                  │   ├─ EventLog.append(flow_started) [L545]
                  │   ├─ While not self._stopped: [L549]
                  │   │   ├─ _execute_steps() [L585]
                  │   │   │   ├─ Sequential steps: wait_for_deps → execute_single_step
                  │   │   │   └─ Parallel groups: ThreadPoolExecutor.submit() per step
                  │   │   └─ Check: is_cyclic/max_cycles/everrunning → continue or break
                  │   └─ EventLog.append(flow_completed/flow_failed)
                  └─ _poll_results() in main thread (every 200ms) [L515]
                      └─ Process queue.Queue() callbacks for status updates
```

### Control Flow — Step Execution Dispatch
```
_execute_single_step(index, step) [L628]
  ├─ If step.step_type == "sub_flow": _execute_sub_flow(step) [L683]
  │   ├─ Depth check: depth < MAX_SUBFLOW_DEPTH (3) [L685]
  │   ├─ FlowStore.load() → get sub-flow template [L690]
  │   ├─ API.create_run(prompt) → new run for sub-flow [L697]
  │   └─ FlowOrchestrator(root, sub_run_id, sub_flow, depth+1) [L704]
  │       └─ sub_orch._thread.join(timeout=3600) [L709]
  ├─ Elif step.step_type == "setup_command": _execute_setup_command(step) [L713]
  │   └─ API.generate_setup_commands(repo_url) [L717]
  │       └─ POST /organizations/{ORG_ID}/setup-commands/generate
  ├─ Elif step.step_type == "create": _execute_create_step(step) [L669]
  │   └─ API.create_run(prompt) → updates self.run_id [L674]
  └─ Else: _execute_normal_step(step) [L641]
      ├─ _wait_for_input_needed(run_id) → polls ALL runs until status matches [L744]
      ├─ API.resume_run(run_id, prompt) [L657]
      └─ _wait_for_completion(run_id) → polls ALL runs until done [L761]
```

### Middleware/Lifecycle Hooks
- **Event Sourcing**: Every flow start, step completion, cycle iteration, and flow completion is logged via EventLog.append() (JSONL at `~/.codegen_manager_events.jsonl`)
- **Crash Recovery**: EventLog.get_incomplete_flows() finds started-but-not-completed flows on restart [L276]
- **Retry**: API._get()/_post() retry 3 times with exponential backoff (1s, 2s, 4s) [L298-325]

### Dead/Unreachable Entrypoints
- `codegen.py` (root) — v1 entrypoint, superseded by `Codegen/codegen.py`
- `Libraries/Analysis/analyzer.py` — Has `__main__` block but never called from GUI
- `eversale/engine/run_simple.py`, `run_ultimate.py`, `run_mcp.py` — Standalone runners, not integrated


---

## 3. Data Flows & Architecture Diagrams

### 3a. Component Diagram (text)

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        EXTERNAL SYSTEMS                                  │
├──────────────────────────────────────────────────────────────────────────┤
│  Codegen API                GitHub API           docs.codegen.com        │
│  (api.codegen.com/v1)      (branches/PRs)       (setup-commands)        │
└──────┬───────────────────────┬────────────────────┬──────────────────────┘
       │ HTTP (retry+auth)     │ (NOT CONNECTED)    │ HTTP
       │                       │                    │
┌──────▼───────────────────────▼────────────────────▼──────────────────────┐
│                    INFRASTRUCTURE LAYER                                   │
│  ┌───────────┐  ┌───────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │ API       │  │ EventLog      │  │ FlowStore    │  │ ProjectStore │   │
│  │ 9 methods │  │ JSONL journal │  │ JSON + migr. │  │ JSON file    │   │
│  │ L294-387  │  │ L248-287      │  │ L393-449     │  │ L452-472     │   │
│  └─────┬─────┘  └───────┬───────┘  └──────┬───────┘  └──────┬───────┘   │
└────────┼────────────────┼──────────────────┼─────────────────┼───────────┘
         │                │                  │                 │
┌────────▼────────────────▼──────────────────▼─────────────────▼───────────┐
│                    ORCHESTRATION LAYER                                    │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │ FlowOrchestrator (L479-770, 16 methods)                           │  │
│  │ ├─ DAG execution with parallel groups (ThreadPoolExecutor)        │  │
│  │ ├─ Cyclic flows (is_cyclic + max_cycles)                          │  │
│  │ ├─ Everrunning loops (everrunning flag)                           │  │
│  │ ├─ Sub-flow recursion (depth-limited to 3)                        │  │
│  │ ├─ Dependency graph resolution (wait_for_dependencies)            │  │
│  │ └─ Event sourcing (every action logged)                           │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────┬────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼────────────────────────────────────────────┐
│                    UI / PRESENTATION LAYER                                │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐    │
│  │ CodegenMgr   │ │ CreateRun    │ │ FlowCreate   │ │ ProjectMgr   │    │
│  │ 23 methods   │ │ Dialog       │ │ Dialog       │ │ Dialog       │    │
│  │ L1683-1990   │ │ L1195-1389   │ │ L852-1106    │ │ L1392-1549   │    │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘    │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                     │
│  │ RunDialog    │ │ FlowMgr      │ │ MdPicker     │                     │
│  │ L1552-1677   │ │ L1109-1192   │ │ L776-849     │                     │
│  └──────────────┘ └──────────────┘ └──────────────┘                     │
└──────────────────────────────────────────────────────────────────────────┘

DISCONNECTED MODULES (available but not wired):
┌─────────────────────┐ ┌─────────────────────┐ ┌──────────────────────┐
│ Libraries/Analysis  │ │ eversale/engine/    │ │ github_analysis/    │
│ - analyzer.py       │ │ - 300+ agent files  │ │ npm_analysis/       │
│ - graph_sitter      │ │ - MCP servers       │ │ docker_analyzer/    │
│ - LSP adapter       │ │ - Browser automation│ │                     │
│ - Static analysis   │ │ - Skill library     │ │                     │
└─────────────────────┘ └─────────────────────┘ └──────────────────────┘
```

### 3b. Sequence Diagram — Primary Use-Case: "Create Run and Execute Flow"

```
User          CreateRunDialog    API(Remote)    FlowOrchestrator    EventLog
 │                │                  │                │                │
 ├─ click New ───►│                  │                │                │
 │                ├─ select project  │                │                │
 │                ├─ load template   │                │                │
 │                ├─ edit prompt     │                │                │
 │                ├─ select flow     │                │                │
 │                ├─ click Launch ──►│                │                │
 │                │   (thread)       │                │                │
 │                │                  ├─ POST /agent/run               │
 │                │                  │   {prompt: "..."}              │
 │                │                  ├──►return {id:123, status:pending}
 │                │◄─ _done() ──────┤                │                │
 │                │  "✅ Run #123"   │                │                │
 │                │                  │                │                │
 │                ├─ _start_flow_runner(123, flow) ──►│                │
 │                │                  │                ├─ append(started)►│
 │                │                  │                │                │
 │                │                  │     ┌──────────┤ _run_flow() (bg thread)
 │                │                  │     │ CYCLE 1  │                │
 │                │                  │     │          │                │
 │                │                  │     │ ┌─ Step 1 (sequential)    │
 │                │                  │◄────┤ │ _wait_for_input_needed()│
 │                │                  ├────►│ │ resume_run(123, prompt) │
 │                │                  │◄────┤ │ _wait_for_completion()  │
 │                │                  │     │ └─ append(step_done) ────►│
 │                │                  │     │                          │
 │                │                  │     │ ┌─ Steps 2,3 (parallel)  │
 │                │                  │◄────┤ │ submit(step2)           │
 │                │                  │◄────┤ │ submit(step3)           │
 │                │                  ├────►│ │ futures.result()        │
 │                │                  │     │ └─ append(steps_done) ──►│
 │                │                  │     │                          │
 │                │                  │     │ is_cyclic? → loop again  │
 │                │                  │     └──────────┤                │
 │                │                  │                ├─ append(done) ►│
 │◄─ status bar ──┤◄─ _poll_results()◄──────────────┤                │
```

### 3c. Sequence Diagram — Secondary Use-Case: "Sub-Flow Execution (Agent Calling Agent)"

```
FlowOrchestrator(depth=0)    API(Remote)    FlowOrchestrator(depth=1)    EventLog
         │                      │                    │                      │
         ├─ step.type="sub_flow"│                    │                      │
         ├─ check depth < 3 ────┤                    │                      │
         ├─ load sub-flow ──────┤                    │                      │
         ├─ create_run(prompt) ─►│                    │                      │
         │                      ├─ POST /agent/run   │                      │
         │                      ├──► {id:456}        │                      │
         ├─ new FlowOrchestrator(456, sub_flow, depth=1)──►│               │
         │                      │                    ├─ append(started) ───►│
         │                      │                    │                      │
         │                      │      ┌─────────────┤ _run_flow()          │
         │  (thread.join        │      │ Execute sub │                      │
         │   timeout=3600)      │◄─────┤ steps...    │                      │
         │                      ├─────►│             │                      │
         │                      │      └─────────────┤                      │
         │                      │                    ├─ append(done) ──────►│
         ├◄─── join returns ────┤                    │                      │
         ├─ append(sub_done) ──►│                    │                      │
         │  continue to next    │                    │                      │
         │  step...             │                    │                      │
```

### Data Flows Without Validation
- **API responses** (`L304, L317, L329`): `.json()` called without schema validation; if API format changes, silent data corruption
- **FlowStore JSON loading** (`L399-414`): Bare `json.load()` with generic try/except; malformed data produces empty dict silently
- **_wait_for_input_needed** (`L744-758`): Fetches ALL runs to find one by ID — no input validation on run_id format
- **Branch templates** (`L118, L144`): Stored as raw strings, no validation of format/placeholders


---

## 4. APIs, Interfaces & Public Contracts

### API Class — HTTP Client Interface (L294-387)

| Method | Endpoint | Parameters | Return | Side Effects |
|--------|----------|------------|--------|-------------|
| `_get(url, params)` | Any GET | url: str, params: dict | dict/list | Retry 3x with backoff |
| `_post(url, payload)` | Any POST | url: str, payload: dict | dict | Retry 3x with backoff |
| `fetch_all_runs()` | GET `/agent/runs` | limit=100, paginated to 1000 | list[dict] | None |
| `fetch_all_logs(run_id)` | GET `/agent/runs/{id}/logs` | run_id: int, paginated | list[dict] | None |
| `create_run(prompt)` | POST `/agent/run` | prompt: str | dict {id, status, ...} | Creates remote agent run |
| `resume_run(run_id, msg)` | POST `/agent/runs/{id}/resume` | run_id: int, msg: str | dict | Resumes paused run |
| `generate_setup_commands(repo_url)` | POST `/setup-commands/generate` | repo_url: str | dict | Generates repo setup cmds |
| `create_run_async(prompt)` | POST `/agent/run` | prompt: str | dict | Same as create_run (async wrapper) |
| `poll_run_status(run_id)` | GET `/agent/runs/{id}` | run_id: int | dict | Single-run status check |

**Error Contract**: All methods return `{}` on failure (empty dict). No exception propagation to callers. Errors logged to console via `print()`.

**Auth**: Bearer token via `CODEGEN_API_TOKEN` env var (L35). Fallback to hardcoded test token.

### Domain Model Interfaces

**FlowStep** (L92-111) — Single step in an execution flow:
```python
@dataclass
class FlowStep:
    label: str           # Human-readable step name
    path: str            # Path to .md template file
    step_type: str       # "normal" | "create" | "sub_flow" | "setup_command"
    parallel_group: str  # Group name for parallel execution (empty = sequential)
    depends_on: list     # List of step labels this depends on
    sub_flow_name: str   # Name of sub-flow (only for step_type="sub_flow")
    branch_template: str # Branch naming template (STORED BUT NOT USED)
    prompt_override: str # Custom prompt override
```

**FlowTemplate** (L113-137) — Complete flow definition:
```python
@dataclass
class FlowTemplate:
    name: str                 # Flow identifier
    steps: list[FlowStep]    # Ordered list of steps
    is_cyclic: bool = False   # Repeat after completion
    max_cycles: int = 10      # Max repetitions (if cyclic)
    branch_template: str = "" # Default branch naming pattern
    everrunning: bool = False # Loop forever until user stops
```

**Project** (L139-157) — Project with PRD and flow attachments:
```python
@dataclass
class Project:
    id: str              # UUID
    name: str            # Project name
    prd_text: str        # Product Requirements Document text
    flow_names: list     # Attached flow names
    branch_template: str # Branch pattern (STORED BUT NOT USED)
    setup_commands: list # Setup commands (from API)
    repo_url: str        # Repository URL
    created_at: str      # ISO timestamp
```

### UI Dialog Public Contracts

| Dialog | Opens From | Produces | Side Effects |
|--------|-----------|----------|-------------|
| `MdPickerDialog` | CreateRunDialog | Selected .md file path | None |
| `FlowCreateDialog` | FlowManagerDialog | FlowTemplate (saved to FlowStore) | Writes ~/.codegen_flows.json |
| `FlowManagerDialog` | CodegenManager toolbar | Flow selection or modification | Reads/writes FlowStore |
| `CreateRunDialog` | CodegenManager toolbar | Agent run creation + optional flow execution | API calls, starts FlowOrchestrator |
| `ProjectManagerDialog` | CodegenManager toolbar | Project CRUD | Writes ~/.codegen_projects.json |
| `RunDialog` | Double-click treeview row | Log viewing, run resumption, flow attachment | API calls, starts FlowOrchestrator |

### Agent Template Interface (17 .md files in Codegen/)

Each template follows this contract:
```yaml
---
name: <template_name>           # Unique identifier
description: <one-line purpose>  # What this template does
---
<Full agent instructions>        # Markdown body injected as prompt
```

**Template Categories:**
- **Analysis**: `analysis.md` (9-agent), `candy.md` (5-agent quick wins), `suitability.md` (fit assessment)
- **Verification**: `verify.md` (6-agent), `carrot.md` (best practices), `test.md` (test strategy)
- **Implementation**: `integrate.md` (feature integration), `modernize.md` (code modernization)
- **Reflection**: `reflect.md` (retrospective)
- **Research**: `research-it.md` (tools/deps), `npx-research.md` (npx toolchain)
- **Setup**: `setup-claude-md.md`, `setup-code-quality.md`, `setup-commits.md`, `setup-tests.md`, `setup-updates.md`

### Interfaces Lacking Documentation or Validation
- All API methods return empty dict on failure — callers cannot distinguish "no data" from "error"
- FlowStep.branch_template has no format validation (e.g., required `{hash}` placeholder)
- No versioning on any interface — FlowStore has v1→v2 migration but no version field
- EventLog has no schema for event_type — any string accepted
- No input validation on user-provided prompts before API submission


---

## 5. Core Files, Functions & Data Structures

### Most Central Files (by dependency/criticality)

| Rank | File | Lines | Purpose | Criticality |
|------|------|-------|---------|-------------|
| 1 | `Codegen/codegen.py` | 1,990 | v2.0 main application — ALL business logic | **CRITICAL** — single point of everything |
| 2 | `Libraries/Analysis/graph_sitter_adapter.py` | 5,589 | Structural code analysis via graph-sitter | HIGH — most complex analysis logic |
| 3 | `Libraries/Analysis/analyzer.py` | 2,097 | Comprehensive analysis orchestrator | HIGH — coordinates all analysis tools |
| 4 | `Libraries/Analysis/static_libs.py` | 2,075 | Static analysis (ruff, mypy, pylint integration) | MEDIUM — analysis backend |
| 5 | `Libraries/Analysis/autogenlib_adapter.py` | 1,130 | AI-powered error fixing | MEDIUM — auto-fix pipeline |
| 6 | `Libraries/Analysis/lsp_adapter.py` | 563 | Language Server Protocol integration | MEDIUM — real-time diagnostics |
| 7 | `codegen.py` (root) | 2,032 | v1.0 legacy application | LOW — superseded by v2 |
| 8 | `github_analysis/codegen_analysis.py` | 421 | Codegen-specific GitHub analysis | LOW — standalone tool |
| 9 | `npm_analysis/npm_analyzer.py` | 275 | NPM package analysis | LOW — standalone tool |
| 10 | `github_analysis/GIT_fetch.py` | 151 | Repository fetcher utility | LOW — utility |
| 11 | `Codegen/analysis.md` | 160 | 9-agent analysis template | HIGH — most used template |
| 12 | `api/ALL.md` | ~11,473 | Complete API documentation | REFERENCE — docs only |
| 13 | `api/REQUIREMENTS.md` | ~1,000 | WebChat2API requirements | REFERENCE — docs only |
| 14 | `README.md` | 280 | System vision (9 capabilities) | HIGH — defines project direction |
| 15 | `api/BrowserRequestManager.js` | ~400 | Browser request automation | MEDIUM — browser tooling |

### Critical Functions

**FlowOrchestrator._run_flow()** (L536-580) — Main orchestration loop:
- **Input**: FlowTemplate (via self), run_id (via self)
- **Algorithm**: While not stopped → execute_steps() → check cyclic/everrunning → repeat or exit
- **Output**: Status updates via queue, events via EventLog
- **Side Effects**: Creates API runs, polls API, writes JSONL events

**FlowOrchestrator._execute_steps()** (L585-625) — DAG step executor:
- **Input**: self._flow.steps (list of FlowStep)
- **Algorithm**: Group by parallel_group → execute sequential first → execute parallel groups via ThreadPoolExecutor
- **Output**: Updated _completed_steps set
- **Side Effects**: Each step may create runs, resume runs, spawn sub-flows

**API.create_run()** (L339-356) — Creates a new Codegen agent run:
- **Input**: prompt (str)
- **Output**: dict with {id, status, ...} or {} on failure
- **Side Effects**: Creates a remote agent run that executes code changes

**FlowStore.load()** (L395-420) — Loads flows with schema migration:
- **Input**: None (reads from FLOWS_FILE path)
- **Algorithm**: json.load() → detect format (legacy list vs new FlowTemplate dict) → convert if legacy
- **Output**: dict[str, FlowTemplate]
- **Side Effects**: Reads filesystem

**EventLog.get_incomplete_flows()** (L276-287) — Crash recovery:
- **Input**: None (reads from EVENT_FILE)
- **Algorithm**: Read all events → find flow_started without matching flow_completed/flow_failed
- **Output**: list of incomplete flow names
- **Side Effects**: Reads filesystem

### Core Domain Models

**StepType** (L85-89) — Enum with 4 values:
```
NORMAL = "normal"           # Resume existing run with prompt
CREATE = "create"           # Create new run
SUB_FLOW = "sub_flow"       # Execute another flow recursively
SETUP_COMMAND = "setup_command"  # Generate setup commands via API
```

### Configuration Loading

| Source | Variable | Default | Loaded At |
|--------|----------|---------|-----------|
| `CODEGEN_API_BASE` env | API_BASE | `https://api.codegen.com/v1` | Module load (L33) |
| `CODEGEN_ORG_ID` env | ORG_ID | `323` | Module load (L34) |
| `CODEGEN_API_TOKEN` env | API_TOKEN | `sk-92083...` (⚠️ hardcoded fallback) | Module load (L35) |
| `CODEGEN_POLL_SEC` env | POLL_SEC | `12` | Module load (L37) |
| `CODEGEN_DIR` env | CODEGEN_DIR | `~/Documents/Codegen` | Module load (L39-46) |
| `CODEGEN_MAX_PARALLEL` env | MAX_PARALLEL_RUNS | `5` | Module load (L52) |
| `CODEGEN_MAX_CYCLES` env | MAX_CYCLES | `100` | Module load (L53) |
| `MAX_SUBFLOW_DEPTH` | Constant | `3` | Module load (L54) |
| `OPENAI_BASE_URL` env | Optional | None | Module load (L48) |
| `ANTHROPIC_BASE_URL` env | Optional | None | Module load (L49) |

### Shared Utilities Used Across 3+ Modules
- `API._get()` / `API._post()` — Used by all 7 public API methods
- `EventLog.append()` — Used by all FlowOrchestrator event points (8+ call sites)
- `FlowStep.to_dict()` / `from_dict()` — Used by FlowStore, FlowCreateDialog, FlowOrchestrator
- `FlowTemplate.to_dict()` / `from_dict()` — Used by FlowStore, FlowManagerDialog, FlowOrchestrator

### God File Warning
⚠️ `Codegen/codegen.py` at 1,990 lines contains ALL 17 classes and ALL business logic. This is a **god file** — every change requires touching this single file. Recommend splitting into separate modules per architectural layer.


---

## 6. Frameworks, Libraries & Tech Stack

### Languages & Runtimes
| Language | Version | Usage |
|----------|---------|-------|
| Python 3.x | 3.8+ (uses dataclasses, f-strings, walrus operator) | Primary — all application code |
| JavaScript | Node.js | eversale CLI (`eversale/bin/eversale.js`) |
| Bash | POSIX | Docker analysis scripts |

### Major Frameworks & Libraries

**Core Application (`Codegen/codegen.py`):**
| Library | Version | Purpose |
|---------|---------|---------|
| `tkinter` | stdlib | GUI framework — all windows, dialogs, treeviews |
| `requests` | auto-installed | HTTP client for Codegen API |
| `plyer` | auto-installed | Desktop notifications |
| `threading` | stdlib | Background execution |
| `concurrent.futures` | stdlib | ThreadPoolExecutor for parallel flows |
| `queue` | stdlib | Thread-safe UI update channel |
| `json` | stdlib | FlowStore/ProjectStore persistence |
| `dataclasses` | stdlib | Domain models |
| `enum` | stdlib | StepType enum |

**Analysis Toolchain (`Libraries/Analysis/`):**
| Library | Purpose |
|---------|---------|
| `graph_sitter` / `codegen` | Structural code analysis (import graph, class hierarchy, etc.) |
| `openai` | LLM integration for AI-powered analysis |
| `rich` | Terminal UI (tables, trees, progress bars, syntax highlighting) |
| `sqlite3` | Analysis results persistence |
| `yaml` | Configuration parsing |
| `ruff` | Python linting (via subprocess) |
| `mypy` | Type checking (via subprocess) |
| `pylint` | Code quality (via subprocess) |

**Agent Engine (`eversale/`):**
| Library | Purpose |
|---------|---------|
| `playwright` | Browser automation |
| `fastapi` | Local API server |
| `anthropic` / `openai` | LLM clients |
| `redis` | Caching/pub-sub (optional) |
| `chromadb` | Vector storage |

### Build Pipeline
- **Package Manager**: pip (no pyproject.toml, no setup.py — `requirements.txt` only)
- **No bundler/compiler**: Pure Python, no transpilation
- **No asset pipeline**: tkinter uses built-in widget rendering
- **Auto-install**: `main()` in codegen.py auto-installs `requests` and `plyer` via `pip install`

### Running Locally
```bash
# Prerequisites: Python 3.8+
# Set environment variables:
export CODEGEN_API_TOKEN="your-api-token"
export CODEGEN_ORG_ID=323

# Run the application:
cd Codegen/
python codegen.py

# Run analysis tools (standalone):
cd Libraries/Analysis/
python analyzer.py --target /path/to/project --comprehensive
```

### Testing
- **No test framework configured** for the main application
- `eversale/` has 60+ test files but uses ad-hoc `test_*.py` naming without pytest/unittest integration
- **No coverage tooling** detected
- **No CI/CD scripts** in repository root

### Containerization
- `docker_analyzer/` contains Docker analysis scripts (for analyzing OTHER Docker images)
- **No Dockerfile for this project** — no containerization of the agent manager itself
- **No docker-compose.yml**
- **No Kubernetes manifests**

### Dependency Concerns
- ⚠️ `requirements.txt` lists 60+ packages but many are for `eversale/` and `Libraries/`, not the main app
- ⚠️ No version pinning on auto-installed deps (`requests`, `plyer`)
- ⚠️ `graph_sitter` import uses try/except fallback — may silently degrade
- ⚠️ No lock file (`requirements.txt` has no hashes)


---

## 7. Capabilities, Features & Use-Cases

### Core Value Proposition
Codegen Agent Manager v2.0 is a **desktop orchestration dashboard** for managing Codegen AI agent runs. It provides a GUI to create, monitor, and chain agent runs into complex workflows with parallel execution, cyclic repetition, and recursive sub-flow composition.

### Feature Inventory

| Feature | Status | Lines |
|---------|--------|-------|
| Create agent runs with prompts | ✅ Complete | L1195-1389 |
| Monitor run status with polling | ✅ Complete | L1920-1960 |
| View run logs (paginated) | ✅ Complete | L1552-1620 |
| Resume paused runs | ✅ Complete | L1625-1645 |
| Star/bookmark runs | ✅ Complete | L1694-1710 |
| Search/filter runs | ✅ Complete | L1770-1800 |
| Load .md templates as prompts | ✅ Complete | L776-849 |
| Create/edit/delete flows | ✅ Complete | L852-1192 |
| Parallel step execution | ✅ Complete | L607-624 |
| Sequential dependency resolution | ✅ Complete | L626-640 |
| Cyclic flow repetition | ✅ Complete | L549-567 |
| Everrunning flows | ✅ Complete | L567-570 |
| Sub-flow execution (agent→agent) | ✅ Complete | L683-711 |
| Setup command generation | ✅ Complete | L713-722 |
| Project/PRD management | ✅ Complete | L1392-1549 |
| Event sourcing (crash recovery) | ✅ Complete | L248-287 |
| Schema migration (v1→v2) | ✅ Complete | L393-449 |
| Branch template storage | ⚠️ Stored, NOT USED | L118, L144 |
| PRD decomposition | ❌ Not implemented | — |
| DAG visualization | ❌ Not implemented | — |
| MCP server integration | ❌ Not implemented | — |
| Browsing/LSP integration | ❌ Not implemented | — |

### 5 Concrete Use-Cases

**Use-case 1: Analyze a Repository**
- Trigger: User clicks "🚀 New Run" → loads `analysis.md` template
- Flow: CreateRunDialog → load template → edit prompt → API.create_run() → run executes remotely
- Output: Agent produces ANALYSIS.md in target repo

**Use-case 2: Execute Multi-Step Implementation Flow**
- Trigger: User creates a flow with steps: analyze → implement → test → verify
- Flow: FlowCreateDialog → save → attach to run → FlowOrchestrator executes steps sequentially
- Output: Each step produces code changes via separate agent runs

**Use-case 3: Run Parallel Analysis with Multiple Agents**
- Trigger: User creates a flow with 3 steps in same parallel_group
- Flow: FlowOrchestrator → ThreadPoolExecutor.submit() × 3 → futures.result()
- Output: 3 agent runs execute simultaneously, all must complete before next phase

**Use-case 4: Continuous Monitoring via Everrunning Flow**
- Trigger: User creates a flow with everrunning=True
- Flow: FlowOrchestrator loops forever: execute_steps() → wait → repeat
- Output: Agent continuously monitors/updates until user clicks "⏹ Stop"

**Use-case 5: Agent Orchestrating Sub-Agents**
- Trigger: User creates a flow with step_type="sub_flow" pointing to another flow
- Flow: FlowOrchestrator → _execute_sub_flow() → new FlowOrchestrator(depth+1) → recursive execution
- Output: Parent agent delegates work to child agents, waits for completion

### Partially Implemented / Stubbed Features
- Branch templates: Data model exists (FlowStep.branch_template, Project.branch_template) but no code creates actual branches
- `create_run_async` method exists but just wraps synchronous create_run
- `poll_run_status` method exists but `_wait_for_completion` still fetches ALL runs instead of using it

### Capability Gaps vs README Promises
The README.md describes 9 major capabilities. Gap analysis:

| README Capability | Implementation Status |
|---|---|
| 1. Research (continuous, evolving) | ❌ No research engine; only `research-it.md` template |
| 2. Data Source Streaming | ❌ No streaming; github_analysis/npm_analysis are standalone |
| 3. Comprehensive Repository Analysis | ⚠️ Libraries/Analysis exists but disconnected from GUI |
| 4. Plan Board / PRD-driven Orchestration | ⚠️ Project dialog exists but no decomposition/validation |
| 5. Memory Modules | ❌ No memory system (eversale has one, not connected) |
| 6. Evolution / Self-Improvement | ❌ No reflection loops (eversale has meta_learner, not connected) |
| 7. Repo2Skill | ❌ No skill extraction from repos |
| 8. Benchmarking | ❌ No benchmarking framework |
| 9. Web2API Automation | ❌ api/REQUIREMENTS.md describes it but no implementation |

---

## 8. Code Quality & Onboarding Assessment

### Naming Consistency
- **Files**: Inconsistent — `codegen.py` (v1 and v2), `codegen_clean.py` (purpose unclear), mixed casing in .md files
- **Classes**: Consistent PascalCase — `FlowOrchestrator`, `CreateRunDialog`, `CodegenManager`
- **Methods**: Consistent snake_case with underscore-prefix for "private" — `_run_flow`, `_execute_steps`, `_poll_loop`
- **Constants**: Consistent UPPER_SNAKE — `API_BASE`, `POLL_SEC`, `MAX_PARALLEL_RUNS`
- **Variables**: Consistent snake_case — `run_id`, `flow_name`, `step_type`
- **Rating**: 8/10 — conventions are followed within v2; cross-file naming is inconsistent

### Modularity Assessment
- **Single Responsibility**: VIOLATED — `codegen.py` is a god file with ALL 17 classes
- **Coupling**: MODERATE — UI dialogs depend directly on API and FlowStore; no dependency injection
- **Cohesion**: GOOD within classes — each class has a clear purpose
- **Circular Dependencies**: NONE detected — clean top-down dependency graph
- **Rating**: 5/10 — good class design trapped in a monolithic file

### Test Coverage
- **Main application**: 0% — zero test files for `Codegen/codegen.py`
- **Libraries/Analysis**: 0% — no tests for analyzer, graph_sitter_adapter, etc.
- **eversale**: ~60+ test files exist but are integration/example tests, not unit tests
- **Riskiest untested paths**:
  1. FlowOrchestrator._run_flow() — main loop with cyclic/everrunning/parallel/sub-flow logic
  2. API retry logic — exponential backoff correctness
  3. FlowStore schema migration — v1→v2 data conversion
  4. EventLog crash recovery — incomplete flow detection
  5. Thread safety — queue-based UI updates from background threads

### Documentation Level
- **Inline comments**: MODERATE — key sections have comments, but many methods have none
- **Docstrings**: MINIMAL — only module-level docstring; no class/method docstrings
- **README**: EXISTS but describes vision, not actual implementation state
- **Architecture docs**: This ANALYSIS.md (being created)
- **API docs**: `api/ALL.md` is comprehensive but for a different system (WebChat2API)
- **Rating**: 4/10 — vision docs exist but no implementation docs

### Error Handling Consistency
- **API layer**: Catches all exceptions, returns `{}` — consistent but loses error context
- **FlowOrchestrator**: Catches exceptions in `_run_flow` and `_execute_single_step` — logs via EventLog
- **UI layer**: Uses `messagebox.showerror()` for user-facing errors — consistent
- **Persistence**: Generic try/except on file operations — returns defaults silently
- **Pattern**: Errors are swallowed rather than propagated — **fail-silent philosophy**
- **Rating**: 5/10 — consistent pattern but loses diagnostic information

### Onboarding Difficulty: **Hard**

**Justification:**
1. 1,990-line god file requires reading the entire file to understand any part
2. No docstrings — must read implementation to understand class purposes
3. v1/v2/clean variants create confusion about which file to use
4. Environment variable configuration has no setup guide
5. No tests — no executable specification to learn from
6. README describes a vision far beyond actual implementation — misleading
7. eversale/ with 300+ files is overwhelming without an index

### Top 5 Most Confusing Parts for New Developers
1. **Three codegen.py variants** — which one is authoritative? (Answer: `Codegen/codegen.py`)
2. **Branch templates stored but unused** — looks like a feature but does nothing
3. **_wait_for_input_needed fetches ALL runs** — looks like a bug but is intentional design
4. **eversale/ relationship** — 300+ files with no clear connection to the main app
5. **README promises vs reality** — 9 major capabilities described, ~2 actually implemented

---

## 9. Strengths, Risks & Strategic Assessment

### Top 5 Architectural Strengths

1. **Event Sourcing for Crash Recovery** (L248-287)
   - JSONL append-only journal enables recovering incomplete flows after crashes
   - Clean separation: EventLog knows nothing about flows, just writes events
   - Evidence: `get_incomplete_flows()` finds started-but-not-completed flows

2. **DAG-Based Parallel Execution** (L585-625)
   - Parallel groups allow concurrent step execution within a flow
   - Dependency resolution via `wait_for_dependencies()` prevents premature execution
   - ThreadPoolExecutor with configurable max_workers
   - Evidence: Steps with same `parallel_group` are submitted simultaneously

3. **Recursive Sub-Flow Composition** (L683-711)
   - Agent runs can spawn other agent runs via sub_flow step type
   - Depth-limited to prevent runaway recursion (MAX_SUBFLOW_DEPTH=3)
   - Each sub-flow gets its own FlowOrchestrator instance
   - Evidence: `_execute_sub_flow()` creates new FlowOrchestrator with `depth+1`

4. **Backward-Compatible Schema Migration** (L393-449)
   - FlowStore.load() auto-detects v1 (list) vs v2 (FlowTemplate) format
   - Transparently converts legacy data on read — no migration scripts needed
   - Evidence: `if isinstance(raw_val, list)` branch in FlowStore.load()

5. **Thread-Safe UI Architecture** (L515-530)
   - queue.Queue() bridges background threads and tkinter main loop
   - root.after(200ms) polls queue for pending UI updates
   - Correct pattern that avoids tkinter thread-safety violations
   - Evidence: `_poll_results()` with `self._queue.get_nowait()`

### Top 5 Technical Risks

1. **God File (1,990 lines, 17 classes)** — All business logic in one file. Any change risks merge conflicts. Cannot be worked on by multiple developers. Refactoring is high-risk without tests.

2. **Zero Test Coverage** — No safety net for any changes. Regression detection is manual. The most critical paths (flow orchestration, API retry, schema migration) have no automated verification.

3. **Hardcoded API Token Fallback** (L35) — `sk-92083737-4e5b-4a48-a2a1-f870a3a096a6` in source code. If this is a real token, it's a credential leak. Even as a test token, it's bad practice.

4. **N+1 API Polling** (L744, L761) — `_wait_for_input_needed()` and `_wait_for_completion()` fetch ALL runs to find one. With many runs, this creates O(n) API calls per poll cycle. The `poll_run_status(run_id)` method exists but isn't used.

5. **No Persistent Everrunning State** — If the app crashes during an everrunning flow, the flow is lost. EventLog records events but the restart logic doesn't auto-resume everrunning flows.

### Anti-Patterns Present

| Anti-Pattern | Location | Impact |
|---|---|---|
| **God File** | `Codegen/codegen.py` (ALL classes) | Unmaintainable, merge conflicts |
| **Fail-Silent Error Handling** | API returns `{}` on error | Debugging blind spots |
| **Unused Abstractions** | Branch templates, create_run_async | False promises in API |
| **Polling Instead of Webhooks** | _wait_for_input_needed, _poll_loop | Wasted API calls, latency |
| **Hardcoded Credentials** | L35 API_TOKEN fallback | Security risk |

### Implementation Comprehensiveness Rating

**Rating: 3 — MVP**

**Justification:**
- ✅ Primary use-cases work end-to-end (create runs, execute flows, monitor status)
- ✅ Advanced orchestration features exist (parallel, cyclic, sub-flows, everrunning)
- ✅ Event sourcing provides crash recovery
- ❌ Many edge cases missing (branch creation, PRD decomposition, MCP integration)
- ❌ Zero test coverage
- ❌ No documentation beyond this analysis
- ❌ README promises 9 capabilities; ~2 are actually implemented
- ❌ God file architecture limits scalability

### Suitability Assessment

**Best suited for:**
- Personal developer dashboard for managing Codegen agent runs
- Prototyping complex agent orchestration workflows
- Template-driven batch agent execution
- Single-user desktop tool with moderate run volumes

**Ill-suited for:**
- Multi-user/team collaboration (no auth, no multi-tenancy)
- High-volume production orchestration (polling architecture, no webhooks)
- Headless/server deployment (tkinter requires display)
- Projects requiring > 5 parallel runs (ThreadPoolExecutor limit)
- Systems requiring audit trails (event log is local-only, no backup)


---

## 10. Upgrade Reflection — v3.0 Autonomous Dashboard

### 10a. Everrunning Cycles — Persistent & Controllable

**Current State**: `FlowTemplate.everrunning` boolean (L137) loops in `_run_flow()` while loop (L549-570). If app closes, flow is lost.

**Upgrade Design**:
```
┌─────────────────────────────────────────────────────────────┐
│ EVERRUNNING CYCLE ARCHITECTURE                               │
│                                                             │
│ UI Layer:                                                   │
│   ☑ Everrunning checkbox in FlowCreateDialog (EXISTS)       │
│   + NEW: "▶ Resume Cycles" button on startup                │
│   + NEW: Per-flow toggle switch in flow status bar           │
│   + NEW: Cycle counter display (Cycle 47/∞)                 │
│                                                             │
│ Persistence Layer:                                          │
│   EventLog.append({                                         │
│     event_type: "everrunning_checkpoint",                   │
│     flow_name: "my-flow",                                   │
│     cycle: 47,                                              │
│     run_id: 12345,                                          │
│     state: "running" | "paused" | "stopped",                │
│     last_step_completed: "step-3"                           │
│   })                                                        │
│                                                             │
│ Startup Recovery:                                           │
│   on app launch:                                            │
│     incomplete = EventLog.get_incomplete_flows()             │
│     for flow in incomplete:                                 │
│       if flow.everrunning and flow.state != "stopped":      │
│         show_resume_dialog(flow) → user confirms            │
│         FlowOrchestrator.resume_from_checkpoint(flow)       │
│                                                             │
│ Graceful Shutdown:                                          │
│   on app close:                                             │
│     for orch in active_orchestrators:                       │
│       orch.checkpoint() → saves state to EventLog           │
│       orch.stop()                                           │
└─────────────────────────────────────────────────────────────┘
```

**Implementation**: ~150 lines — extend EventLog with checkpoint events, add resume_from_checkpoint() to FlowOrchestrator, add startup recovery dialog.

### 10b. Branch Naming & Parallel Multi-Branch Implementation

**Current State**: `FlowStep.branch_template` and `Project.branch_template` store patterns (L118, L144) but are never used to create actual branches.

**Upgrade Design**:
```
Branch Template System:
  Pattern: "codegen-bot/{project}/{feature}-{hash}"
  Variables:
    {project}  → Project.name (slugified)
    {feature}  → FlowStep.label (slugified)
    {hash}     → random 6-char hex
    {date}     → YYYY-MM-DD
    {cycle}    → cycle number (for everrunning)

Branch Creation Flow:
  FlowOrchestrator._execute_single_step(step):
    if step.branch_template:
      branch_name = resolve_template(step.branch_template, context)
      API.create_branch(repo_url, branch_name, base_branch="main")
      # OR: GitHub API → POST /repos/{owner}/{repo}/git/refs
      step_prompt = f"{step.prompt}\n\n[Branch: {branch_name}]"

Parallel Multi-Branch Strategy:
  Given: PRD with 5 features (F1...F5)
  
  Flow "implement-prd":
    Step 1: "analyze-prd" (sequential, create)
      → Agent reads PRD, outputs feature list
    
    Step 2-6: Parallel group "features"
      Step 2: "implement-F1" (parallel_group="features")
        branch: "codegen-bot/myproject/feature-1-a8f3"
      Step 3: "implement-F2" (parallel_group="features")
        branch: "codegen-bot/myproject/feature-2-b7c2"
      Step 4: "implement-F3" (parallel_group="features")
        branch: "codegen-bot/myproject/feature-3-c6d1"
      Step 5: "implement-F4" (parallel_group="features")
        branch: "codegen-bot/myproject/feature-4-d5e0"
      Step 6: "implement-F5" (parallel_group="features")
        branch: "codegen-bot/myproject/feature-5-e4f9"
    
    Step 7: "merge-all" (sequential, depends_on all)
      → Creates PRs for each branch → reviews → merges
    
    Step 8: "validate" (sequential)
      → Runs test suite on merged main
```

**Implementation**: ~200 lines — add `API.create_branch()`, template resolution in orchestrator, merge orchestration step type.

### 10c. Multi-Flow Composition & Agent Runs Calling Agent Runs

**Current State**: Sub-flow support exists (L683-711) with depth-limited recursion. But only one flow can be attached per run.

**Upgrade Design**:
```
Multi-Flow Composition Patterns:

1. SEQUENTIAL CHAIN (Flow A → Flow B → Flow C):
   Flow "full-pipeline":
     Step 1: sub_flow → "analyze"    (depth 0)
     Step 2: sub_flow → "implement"  (depth 0)  
     Step 3: sub_flow → "test"       (depth 0)
     Step 4: sub_flow → "deploy"     (depth 0)

2. FAN-OUT (Flow A spawns B, C, D in parallel):
   Flow "parallel-analysis":
     Step 1: sub_flow → "security-audit"   (parallel_group="audit")
     Step 2: sub_flow → "performance-test" (parallel_group="audit")
     Step 3: sub_flow → "code-quality"     (parallel_group="audit")
     Step 4: sub_flow → "merge-reports"    (depends_on: 1,2,3)

3. RECURSIVE DECOMPOSITION (Agent decides what to spawn):
   Flow "autonomous":
     Step 1: "analyze" (create) → agent reads PRD
     Step 2: "plan" (normal) → agent outputs sub-task list
     Step 3: NEW STEP TYPE "dynamic_fan_out":
       → Parse agent output for task list
       → Create one sub-flow per task
       → Execute all in parallel
     Step 4: "validate" (normal) → agent checks all tasks done

4. EVERRUNNING SUPERVISOR (Monitors and re-spawns):
   Flow "supervisor" (everrunning=True):
     Step 1: "check-status" (normal)
     Step 2: "decide-action" (normal) → agent decides what to do
     Step 3: sub_flow → varies based on agent decision
     [cycle repeats every N minutes]

New Step Type: "dynamic_fan_out"
  - Reads previous step's output
  - Parses it for a list of tasks (JSON array)
  - Creates a sub-flow per task
  - Executes all sub-flows in parallel
  - Collects results
```

**Implementation**: ~300 lines — add dynamic_fan_out step type, output parsing, dynamic sub-flow creation.

### 10d. Setup-Command-Creation Endpoint Integration

**API Endpoint** (from docs.codegen.com):
```
POST /v1/organizations/{org_id}/setup-commands/generate
Headers:
  Authorization: Bearer {api_token}
  Content-Type: application/json
Body:
  {
    "repo_url": "https://github.com/owner/repo"
  }
Response:
  {
    "commands": [
      "npm install",
      "npm run build", 
      "npm test"
    ],
    "language": "javascript",
    "framework": "next.js"
  }
```

**Current Implementation** (L373-376):
```python
def generate_setup_commands(self, repo_url: str) -> dict:
    return self._post(
        f"{API_BASE}/organizations/{ORG_ID}/setup-commands/generate",
        {"repo_url": repo_url}
    )
```

**Upgrade — UI Integration**:
```
ProjectManagerDialog enhancements:
  1. Add "repo_url" text field (EXISTS in Project model, L146)
  2. Add "🔧 Generate Setup Commands" button
  3. On click:
     → API.generate_setup_commands(project.repo_url)
     → Display results in scrolled text widget
     → Store in Project.setup_commands
     → Show in flow step context (auto-prepend to prompts)
  
  4. In FlowOrchestrator, before executing any step:
     → If project has setup_commands:
       → Prepend to step prompt:
         "## Environment Setup\n{commands}\n\n## Task\n{original_prompt}"
```

**Implementation**: ~100 lines — UI button, API call, prompt augmentation.


---

## 11. Full Autonomous Dashboard — v3.0 Blueprint

### Vision
A dashboard where users select a project, write/paste a PRD, and the system **autonomously decomposes it into features, creates branches, implements each in parallel via Codegen agent runs** (using tools/skills/MCP/browsing/LSP), monitors progress, handles failures with retry/escalation, and produces merged PRs — all while the user watches.

### Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                    AUTONOMOUS DASHBOARD v3.0                        │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐ │
│  │ PROJECT      │  │ PRD EDITOR   │  │ PIPELINE MONITOR         │ │
│  │ SELECTOR     │  │ + AI Assist  │  │ (Real-time DAG view)     │ │
│  │              │  │              │  │                          │ │
│  │ ▼ MyProject  │  │ ┌──────────┐│  │  [analyze] ─┐            │ │
│  │   Repo: ...  │  │ │ Feature 1││  │  [feat-1] ──┤            │ │
│  │   Branch: .. │  │ │ Feature 2││  │  [feat-2] ──┼→[merge]→✅  │ │
│  │   Flows: 3   │  │ │ Feature 3││  │  [feat-3] ──┤            │ │
│  │              │  │ │ Feature 4││  │  [test] ────┘            │ │
│  │ [+ New]      │  │ │ Feature 5││  │                          │ │
│  │ [⚙ Settings] │  │ └──────────┘│  │  ☑ Everrunning: ON      │ │
│  └──────────────┘  │              │  │  Cycle: 3/∞             │ │
│                    │ [🤖 Decompose]│  │  [⏸ Pause] [⏹ Stop]    │ │
│                    │ [🚀 Execute] │  │  [📊 Logs] [🔄 Retry]   │ │
│                    └──────────────┘  └──────────────────────────┘ │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ AGENT RUN TIMELINE                                          │  │
│  │ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │  │
│  │ │ Run #101 │→│ Run #102 │→│ Run #103 │→│ Run #104 │→...   │  │
│  │ │ analyze  │ │ feat-1   │ │ feat-2   │ │ feat-3   │       │  │
│  │ │ ✅ Done  │ │ ⏳ Active│ │ ⏳ Active│ │ 📋 Queued│       │  │
│  │ └──────────┘ └──────────┘ └──────────┘ └──────────┘       │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ FLOW LIBRARY                                                │  │
│  │ [analyze] [implement] [test] [verify] [modernize] [deploy]  │  │
│  │ [+ Create Flow] [📁 Import] [📤 Export]                     │  │
│  └──────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
```

### PRD → Parallel Implementation Pipeline

```
Phase 1: PRD DECOMPOSITION (automated)
  Input: Raw PRD text from user
  Agent: "prd-decomposer" (new template)
  Output: JSON array of features:
    [
      {"name": "auth-system", "description": "...", "priority": 1},
      {"name": "dashboard-ui", "description": "...", "priority": 2},
      {"name": "api-endpoints", "description": "...", "priority": 1},
    ]

Phase 2: FLOW GENERATION (automated)
  For each feature:
    Create FlowStep with:
      label: feature.name
      step_type: "create"
      branch_template: "codegen-bot/{project}/{feature}-{hash}"
      parallel_group: f"priority-{feature.priority}"
      prompt: f"Implement {feature.name}: {feature.description}"

Phase 3: PARALLEL EXECUTION
  FlowOrchestrator executes:
    Priority 1 features → parallel (ThreadPoolExecutor)
    Wait for all priority 1 to complete
    Priority 2 features → parallel
    Wait for all priority 2 to complete
    ... etc

Phase 4: MERGE & VALIDATE
  Step: "merge-orchestrator" (new template)
    → For each completed feature branch:
      → Create PR via Codegen API
      → Run tests via agent
      → Merge if passing
    → Run full test suite on merged main
    → Report results back to dashboard

Phase 5: EVERRUNNING MONITORING (optional)
  If everrunning enabled:
    → Continuously check for issues
    → Agent monitors logs, metrics
    → Auto-creates fix runs for failures
    → Cycle repeats until user stops
```

### Codegen API Integration for Agent Capabilities

The Codegen agent runs already have access to tools/skills/MCP/browsing/LSP through the remote execution environment. The dashboard's role is orchestration:

```
Dashboard (orchestrator)
  ├── Codegen API creates runs
  │     └── Remote agent has:
  │           ├── Tools (file read/write, search, git operations)
  │           ├── Skills (code analysis, refactoring, testing)
  │           ├── MCP servers (filesystem, memory, browser)
  │           ├── Browsing (web research, docs lookup)
  │           └── LSP (real-time diagnostics, completions)
  │
  ├── Dashboard monitors via polling/webhooks
  │     ├── Status updates (pending → running → completed)
  │     ├── Log streaming (paginated fetch)
  │     └── PR creation events
  │
  └── Dashboard makes decisions
        ├── Retry failed steps (auto or manual)
        ├── Escalate to user (input_needed status)
        ├── Branch management (create, merge, delete)
        └── Cycle control (continue, pause, stop)
```

### Implementation Roadmap

| Tier | Feature | Effort | Impact | Priority |
|------|---------|--------|--------|----------|
| **T1** | Activate branch templates in orchestrator | 2h | HIGH | P0 |
| **T1** | Everrunning checkpoint/resume | 4h | HIGH | P0 |
| **T1** | Use poll_run_status instead of fetch_all | 1h | MEDIUM | P0 |
| **T1** | Remove hardcoded API token | 0.5h | HIGH | P0 |
| **T2** | PRD decomposition agent template | 4h | HIGH | P1 |
| **T2** | Dynamic fan-out step type | 6h | HIGH | P1 |
| **T2** | Setup-command UI integration | 3h | MEDIUM | P1 |
| **T2** | DAG visualization in flow status | 6h | MEDIUM | P1 |
| **T3** | Parallel multi-branch creation | 8h | HIGH | P2 |
| **T3** | Merge orchestration step type | 8h | HIGH | P2 |
| **T3** | Webhook-based status updates | 6h | MEDIUM | P2 |
| **T3** | Split god file into modules | 12h | HIGH | P2 |
| **T4** | Full autonomous pipeline (PRD→deploy) | 20h | CRITICAL | P3 |
| **T4** | Agent-to-agent communication protocol | 12h | HIGH | P3 |
| **T4** | Test framework + 80% coverage | 16h | HIGH | P3 |
| **T4** | Web UI migration (FastAPI + React) | 40h | MEDIUM | P3 |

### docs.codegen.com Integration Points

Based on the Codegen API documentation:

1. **Agent Runs**: `POST /organizations/{org_id}/agent/run` — Create runs with prompts
2. **Run Management**: `GET/POST /organizations/{org_id}/agent/runs/{id}` — Status, logs, resume
3. **Setup Commands**: `POST /organizations/{org_id}/setup-commands/generate` — Auto-detect repo setup
4. **Organizations**: `GET /organizations` — List orgs for multi-org support
5. **Webhooks** (if available): Real-time status updates instead of polling

---

*Analysis produced by parallel codebase exploration. All findings reference actual source files in the `Zeeeepa/analyzer` repository.*
*883 files analyzed across 461 Python files (322,057 LOC), 264 markdown files, 7 shell scripts, and 3 JavaScript files.*
*Primary application: `Codegen/codegen.py` — 1,990 lines, 17 classes, 128 functions across 5 architectural layers.*

