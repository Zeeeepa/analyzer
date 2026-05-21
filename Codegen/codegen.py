#!/usr/bin/env python3
"""
Codegen Agent Manager v2.0 — Full Autonomous Dashboard
pip install requests plyer

New capabilities over v1:
  - Parallel flow execution (ThreadPoolExecutor)
  - Cyclic/everrunning flows with UI controls
  - Project & PRD management
  - Agent-calling-agent (hierarchical flows)
  - Setup commands integration (docs.codegen.com)
  - Event sourcing for crash recovery
  - Branch naming configuration
  - Environment variable configuration
  - Multi-flow status tracking
  - Execution graph visualization
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import threading, time, json, requests, os, webbrowser, queue, uuid
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any, Callable
from concurrent.futures import ThreadPoolExecutor, Future
from enum import Enum

# ══════════════════════════════════════════════════════════════════════════════
#  Configuration — Environment variables with fallback defaults
# ══════════════════════════════════════════════════════════════════════════════

API_BASE    = os.environ.get("CODEGEN_API_BASE", "https://api.codegen.com/v1")
ORG_ID      = int(os.environ.get("CODEGEN_ORG_ID", "323"))
API_TOKEN   = os.environ.get("CODEGEN_API_TOKEN", "sk-92083737-4e5b-4a48-a2a1-f870a3a096a6")
HEADERS     = {"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "application/json"}
POLL_SEC    = int(os.environ.get("CODEGEN_POLL_SEC", "12"))

# Cross-platform paths
_home = Path.home()
CODEGEN_DIR    = Path(os.environ.get("CODEGEN_DIR", str(_home / "Documents" / "Codegen")))
DEFAULT_TPL    = str(CODEGEN_DIR / "analysis.md")
FLOW_FILE      = _home / ".codegen_flows.json"
PROJECT_FILE   = _home / ".codegen_projects.json"
EVENT_LOG_FILE = _home / ".codegen_manager_events.jsonl"
STAR_FILE      = _home / ".codegen_manager_stars.json"

# External API endpoints (z.ai / Anthropic compatibility)
OPENAI_BASE_URL    = os.environ.get("OPENAI_BASE_URL", "")
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "")

MAX_PARALLEL_RUNS = int(os.environ.get("CODEGEN_MAX_PARALLEL", "5"))
MAX_CYCLE_ITERATIONS = int(os.environ.get("CODEGEN_MAX_CYCLES", "100"))
MAX_SUBFLOW_DEPTH = 3


# ── Palette ─────────────────────────────────────────────────────────────────
BG      = "#0b0b18"
PANEL   = "#12121f"
CARD    = "#1a1a2e"
BORDER  = "#2a2a4a"
ACCENT  = "#5c6bff"
HOT     = "#ff4d6d"
GREEN   = "#2ecc71"
TEXT    = "#dde1f0"
MUTED   = "#606080"
C_RUN   = "#2ecc71"
C_DONE  = "#5b9cf6"
C_FAIL  = "#ff4d6d"
C_PEND  = "#f39c12"
C_CYCLE = "#e056fd"
C_PARA  = "#00d2d3"

FONT        = ("Segoe UI", 10)
FONT_BOLD   = ("Segoe UI", 10, "bold")
FONT_SMALL  = ("Segoe UI", 8)
FONT_MONO   = ("Consolas", 9)
FONT_TITLE  = ("Segoe UI", 13, "bold")


# ══════════════════════════════════════════════════════════════════════════════
#  Domain Models
# ══════════════════════════════════════════════════════════════════════════════

class StepType(str, Enum):
    NORMAL = "normal"           # Resume existing run with prompt
    CREATE = "create"           # Create a new run
    SUB_FLOW = "sub_flow"       # Spawn a sub-flow (agent-calling-agent)
    SETUP_CMD = "setup_command" # Generate setup commands

@dataclass
class FlowStep:
    label: str = ""
    path: str = ""
    text: str = ""
    step_type: str = "normal"
    depends_on: List[str] = field(default_factory=list)
    parallel_group: str = ""
    sub_flow_name: str = ""
    branch_template: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "FlowStep":
        # Backward compatible: old steps missing new fields get defaults
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in d.items() if k in known}
        return cls(**filtered)

@dataclass
class FlowTemplate:
    name: str = ""
    steps: List[FlowStep] = field(default_factory=list)
    is_cyclic: bool = False
    max_cycles: int = 10
    branch_template: str = "codegen-bot/{project}/{flow}-{hash}"
    everrunning: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["steps"] = [s.to_dict() if isinstance(s, FlowStep) else s for s in self.steps]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "FlowTemplate":
        steps = [FlowStep.from_dict(s) if isinstance(s, dict) else s for s in d.get("steps", [])]
        return cls(
            name=d.get("name", ""),
            steps=steps,
            is_cyclic=d.get("is_cyclic", False),
            max_cycles=d.get("max_cycles", 10),
            branch_template=d.get("branch_template", "codegen-bot/{project}/{flow}-{hash}"),
            everrunning=d.get("everrunning", False),
        )

@dataclass
class Project:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    prd_text: str = ""
    flow_names: List[str] = field(default_factory=list)
    branch_template: str = "codegen-bot/{project}/{feature}-{hash}"
    setup_commands: List[str] = field(default_factory=list)
    repo_url: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in d.items() if k in known}
        return cls(**filtered)

@dataclass
class ExecutionEvent:
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    event_type: str = ""  # flow_started, step_started, step_completed, step_failed, cycle_iteration, flow_completed
    flow_name: str = ""
    run_id: int = 0
    step_label: str = ""
    cycle: int = 0
    depth: int = 0
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════════

def btn(parent, text, cmd, bg=ACCENT, fg="white", padx=14, pady=7, **kw):
    return tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg,
                     activebackground=HOT, activeforeground="white",
                     font=FONT, bd=0, padx=padx, pady=pady,
                     cursor="hand2", relief="flat", **kw)

def lbl(parent, text, fg=TEXT, font=FONT, bg=None, **kw):
    b = bg if bg is not None else BG
    return tk.Label(parent, text=text, fg=fg, font=font, bg=b, **kw)

def fmt_dt(s):
    return s[:19].replace("T", "  ") if s else ""

def attach_edit_menu(widget):
    """Attach right-click Cut/Copy/Paste/Select-All context menu."""
    is_text = isinstance(widget, (tk.Text,))
    def _cut():
        try: widget.event_generate("<<Cut>>")
        except Exception: pass
    def _copy():
        try: widget.event_generate("<<Copy>>")
        except Exception: pass
    def _paste():
        try: widget.event_generate("<<Paste>>")
        except Exception: pass
    def _select_all():
        try:
            if is_text:
                widget.tag_add("sel", "1.0", "end")
            else:
                widget.select_range(0, tk.END)
                widget.icursor(tk.END)
        except Exception: pass
    m = tk.Menu(widget, tearoff=0, bg=CARD, fg=TEXT,
                activebackground=ACCENT, activeforeground="white",
                font=FONT_SMALL, bd=0)
    m.add_command(label="Cut",        command=_cut)
    m.add_command(label="Copy",       command=_copy)
    m.add_command(label="Paste",      command=_paste)
    m.add_separator()
    m.add_command(label="Select All", command=_select_all)
    def _show(event):
        widget.focus_set()
        try: m.tk_popup(event.x_root, event.y_root)
        finally: m.grab_release()
    widget.bind("<Button-3>", _show)

def is_active(s):
    s = (s or "").lower()
    return "active" in s or "running" in s or "pending" in s

def is_done(s):
    s = (s or "").lower()
    return "complete" in s or "fail" in s or "error" in s or "cancel" in s

def status_tag(s):
    if is_active(s): return "running"
    s = (s or "").lower()
    if "complete" in s:             return "completed"
    if "fail" in s or "error" in s: return "failed"
    return "other"

def status_color(s):
    return {"running": C_RUN, "completed": C_DONE,
            "failed": C_FAIL}.get(status_tag(s), C_PEND)


# ══════════════════════════════════════════════════════════════════════════════
#  Event Log — Append-only journal for crash recovery
# ══════════════════════════════════════════════════════════════════════════════

class EventLog:
    """Append-only JSONL event log for execution history and crash recovery."""

    @staticmethod
    def append(event: ExecutionEvent):
        try:
            with open(EVENT_LOG_FILE, "a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(event.to_dict()) + "\n")
        except Exception:
            pass

    @staticmethod
    def read_all() -> List[ExecutionEvent]:
        events = []
        try:
            with open(EVENT_LOG_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        d = json.loads(line)
                        events.append(ExecutionEvent(**{k: v for k, v in d.items()
                                                        if k in ExecutionEvent.__dataclass_fields__}))
        except FileNotFoundError:
            pass
        except Exception:
            pass
        return events

    @staticmethod
    def get_incomplete_flows() -> List[str]:
        """Find flows that started but never completed (crash recovery)."""
        started = set()
        completed = set()
        for e in EventLog.read_all():
            key = f"{e.flow_name}:{e.run_id}"
            if e.event_type == "flow_started":
                started.add(key)
            elif e.event_type in ("flow_completed", "flow_failed"):
                completed.add(key)
        return list(started - completed)


# ══════════════════════════════════════════════════════════════════════════════
#  API layer — Enhanced with setup commands, retry, parallel support
# ══════════════════════════════════════════════════════════════════════════════

class API:
    _executor = ThreadPoolExecutor(max_workers=MAX_PARALLEL_RUNS)

    @staticmethod
    def _get(path, params=None, retries=2):
        for attempt in range(retries + 1):
            try:
                r = requests.get(f"{API_BASE}{path}", headers=HEADERS,
                                 params=params, timeout=20)
                r.raise_for_status()
                return r.json()
            except requests.RequestException as e:
                if attempt == retries:
                    raise
                time.sleep(2 ** attempt)

    @staticmethod
    def _post(path, body, retries=2):
        for attempt in range(retries + 1):
            try:
                r = requests.post(f"{API_BASE}{path}", headers=HEADERS,
                                  json=body, timeout=30)
                r.raise_for_status()
                return r.json()
            except requests.RequestException as e:
                if attempt == retries:
                    raise
                time.sleep(2 ** attempt)

    @classmethod
    def fetch_all_runs(cls):
        """Fetch the most recent 1000 runs (10 pages of 100)."""
        all_items, skip, limit, max_runs = [], 0, 100, 1000
        while len(all_items) < max_runs:
            data = cls._get(f"/organizations/{ORG_ID}/agent/runs",
                            {"limit": limit, "skip": skip})
            items = data.get("items", [])
            if not items:
                break
            all_items.extend(items)
            skip += len(items)
            total = data.get("total", 0)
            if skip >= total:
                break
        return all_items[:max_runs]

    @classmethod
    def fetch_all_logs(cls, run_id):
        """Paginate /alpha logs until all log entries are collected."""
        all_logs, skip, limit, run_info = [], 0, 100, None
        while True:
            data = cls._get(
                f"/alpha/organizations/{ORG_ID}/agent/run/{run_id}/logs",
                {"limit": limit, "skip": skip})
            if run_info is None:
                run_info = data
            logs = data.get("logs", [])
            all_logs.extend(logs)
            total = data.get("total_logs") or 0
            skip += len(logs)
            if skip >= total or not logs:
                break
        if run_info:
            run_info["logs"] = all_logs
        return run_info

    @classmethod
    def create_run(cls, prompt, model=None):
        body = {"prompt": prompt}
        if model:
            body["model"] = model
        return cls._post(f"/organizations/{ORG_ID}/agent/run", body)

    @classmethod
    def resume_run(cls, run_id, prompt):
        return cls._post(f"/organizations/{ORG_ID}/agent/run/resume",
                         {"agent_run_id": run_id, "prompt": prompt})

    @classmethod
    def generate_setup_commands(cls, repo_url: str) -> dict:
        """Call setup-commands endpoint (docs.codegen.com)."""
        return cls._post(f"/organizations/{ORG_ID}/setup-commands/generate",
                         {"repo_url": repo_url})

    @classmethod
    def create_run_async(cls, prompt, model=None) -> Future:
        """Submit run creation to thread pool for parallel execution."""
        return cls._executor.submit(cls.create_run, prompt, model)

    @classmethod
    def poll_run_status(cls, run_id) -> dict:
        """Get current status of a run."""
        return cls._get(f"/organizations/{ORG_ID}/agent/run/{run_id}")


# ══════════════════════════════════════════════════════════════════════════════
#  Data Stores
# ══════════════════════════════════════════════════════════════════════════════

class FlowStore:
    """Load/save flows with backward-compatible schema migration."""

    @staticmethod
    def load() -> Dict[str, FlowTemplate]:
        try:
            raw = json.loads(FLOW_FILE.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return {}
            result = {}
            for name, val in raw.items():
                if isinstance(val, list):
                    # Legacy format: list of step dicts
                    steps = [FlowStep.from_dict(s) if isinstance(s, dict) else s for s in val]
                    result[name] = FlowTemplate(name=name, steps=steps)
                elif isinstance(val, dict):
                    # New format: FlowTemplate dict
                    result[name] = FlowTemplate.from_dict({**val, "name": name})
                else:
                    continue
            return result
        except Exception:
            return {}

    @staticmethod
    def save(flows: Dict[str, FlowTemplate]):
        try:
            data = {}
            for name, ft in flows.items():
                if isinstance(ft, FlowTemplate):
                    data[name] = ft.to_dict()
                elif isinstance(ft, list):
                    # Legacy compatibility
                    data[name] = ft
                else:
                    data[name] = ft
            FLOW_FILE.write_text(json.dumps(data, indent=2, default=str),
                                 encoding="utf-8")
        except Exception:
            pass

    @staticmethod
    def load_legacy() -> dict:
        """Load in legacy format for backward compat with old dialogs."""
        try:
            raw = json.loads(FLOW_FILE.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def save_legacy(flows: dict):
        """Save in legacy format."""
        try:
            FLOW_FILE.write_text(json.dumps(flows, indent=2), encoding="utf-8")
        except Exception:
            pass


class ProjectStore:
    """Load/save projects from disk."""

    @staticmethod
    def load() -> Dict[str, Project]:
        try:
            raw = json.loads(PROJECT_FILE.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return {}
            return {k: Project.from_dict(v) for k, v in raw.items()}
        except Exception:
            return {}

    @staticmethod
    def save(projects: Dict[str, Project]):
        try:
            data = {k: v.to_dict() for k, v in projects.items()}
            PROJECT_FILE.write_text(json.dumps(data, indent=2, default=str),
                                     encoding="utf-8")
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
#  FlowOrchestrator — Parallel/Cycle/Hierarchical execution engine
# ══════════════════════════════════════════════════════════════════════════════

class FlowOrchestrator:
    """Replaces sequential FlowRunner with DAG-based parallel execution,
    cycle support, and agent-calling-agent via sub-flows.
    
    Thread-safe: all UI updates go through root.after().
    """

    def __init__(self, root: tk.Tk, run_id: int, flow: FlowTemplate,
                 on_status: Callable = None, depth: int = 0,
                 project_name: str = ""):
        self.root = root
        self.run_id = run_id
        self.flow = flow
        self.on_status = on_status or (lambda msg, color: None)
        self.depth = depth
        self.project_name = project_name
        self._stopped = False
        self._cycle_count = 0
        self._executor = ThreadPoolExecutor(max_workers=MAX_PARALLEL_RUNS)
        self._result_queue = queue.Queue()
        self._completed_steps = set()
        self._running = False

        # Start orchestration in background
        self._thread = threading.Thread(target=self._run_flow, daemon=True)
        self._thread.start()
        self._poll_results()

    def stop(self):
        self._stopped = True
        self._running = False

    def _poll_results(self):
        """Poll result queue from main thread for thread-safe UI updates."""
        try:
            while not self._result_queue.empty():
                callback, args = self._result_queue.get_nowait()
                callback(*args)
        except Exception:
            pass
        if self._running:
            self.root.after(200, self._poll_results)

    def _emit(self, msg, color=C_RUN):
        """Thread-safe status update."""
        self._result_queue.put((self.on_status, (msg, color)))

    def _log_event(self, event_type, step_label="", data=None):
        EventLog.append(ExecutionEvent(
            event_type=event_type,
            flow_name=self.flow.name,
            run_id=self.run_id,
            step_label=step_label,
            cycle=self._cycle_count,
            depth=self.depth,
            data=data or {}
        ))

    def _run_flow(self):
        """Main orchestration loop — runs in background thread."""
        self._running = True
        self._log_event("flow_started")
        self._emit(f"⛓ Flow '{self.flow.name}' started — "
                   f"{len(self.flow.steps)} steps, "
                   f"{'cyclic' if self.flow.is_cyclic else 'linear'}", C_RUN)

        try:
            while not self._stopped:
                self._cycle_count += 1
                self._completed_steps.clear()

                if self._cycle_count > 1:
                    self._log_event("cycle_iteration")
                    self._emit(f"🔄 Cycle {self._cycle_count}/{self.flow.max_cycles}", C_CYCLE)

                # Execute all steps respecting dependencies
                self._execute_steps()

                if self._stopped:
                    break

                # Check if we should cycle
                if not self.flow.is_cyclic and not self.flow.everrunning:
                    break

                if self._cycle_count >= self.flow.max_cycles and not self.flow.everrunning:
                    self._emit(f"⛓ Max cycles ({self.flow.max_cycles}) reached", C_PEND)
                    break

                if self.flow.everrunning:
                    self._emit(f"♾️ Everrunning — restarting cycle {self._cycle_count + 1}", C_CYCLE)
                    time.sleep(POLL_SEC)

            status = "stopped" if self._stopped else "completed"
            self._log_event(f"flow_{status}")
            self._emit(f"✅ Flow '{self.flow.name}' {status} "
                       f"({self._cycle_count} cycle(s))", GREEN if status == "completed" else C_PEND)
        except Exception as e:
            self._log_event("flow_failed", data={"error": str(e)})
            self._emit(f"❌ Flow error: {e}", C_FAIL)
        finally:
            self._running = False

    def _execute_steps(self):
        """Execute steps respecting dependencies and parallel groups."""
        steps = self.flow.steps
        if not steps:
            return

        # Group steps by parallel_group
        groups = {}
        sequential = []
        for i, step in enumerate(steps):
            if isinstance(step, dict):
                step = FlowStep.from_dict(step)
            if step.parallel_group:
                groups.setdefault(step.parallel_group, []).append((i, step))
            else:
                sequential.append((i, step))

        # Execute sequential steps first, then parallel groups
        for i, step in sequential:
            if self._stopped:
                return
            self._wait_for_dependencies(step)
            self._execute_single_step(i, step)

        # Execute parallel groups
        for group_name, group_steps in groups.items():
            if self._stopped:
                return
            self._emit(f"⚡ Parallel group '{group_name}' — {len(group_steps)} steps", C_PARA)
            futures = []
            for i, step in group_steps:
                if self._stopped:
                    return
                f = self._executor.submit(self._execute_single_step, i, step)
                futures.append((i, step, f))

            # Wait for all parallel steps
            for i, step, f in futures:
                try:
                    f.result(timeout=600)  # 10 min max per step
                except Exception as e:
                    self._emit(f"❌ Parallel step '{step.label}' failed: {e}", C_FAIL)

    def _wait_for_dependencies(self, step: FlowStep):
        """Wait until all dependencies are completed."""
        if not step.depends_on:
            return
        while not self._stopped:
            pending = [d for d in step.depends_on if d not in self._completed_steps]
            if not pending:
                return
            time.sleep(2)

    def _execute_single_step(self, index: int, step: FlowStep):
        """Execute a single step based on its type."""
        if self._stopped:
            return

        self._log_event("step_started", step.label)
        self._emit(f"▶ Step {index + 1}: '{step.label}' ({step.step_type})", C_RUN)

        try:
            if step.step_type == StepType.SUB_FLOW:
                self._execute_sub_flow(step)
            elif step.step_type == StepType.SETUP_CMD:
                self._execute_setup_command(step)
            elif step.step_type == StepType.CREATE:
                self._execute_create_step(step)
            else:
                self._execute_normal_step(step)

            self._completed_steps.add(step.label)
            self._log_event("step_completed", step.label)
            self._emit(f"✓ Step '{step.label}' completed", GREEN)
        except Exception as e:
            self._log_event("step_failed", step.label, {"error": str(e)})
            self._emit(f"✗ Step '{step.label}' failed: {e}", C_FAIL)

    def _execute_normal_step(self, step: FlowStep):
        """Resume existing run with prompt from step."""
        prompt = self._build_prompt(step)
        if not prompt:
            return

        # Wait for run to need input
        self._wait_for_input_needed()

        API.resume_run(self.run_id, prompt)
        self._wait_for_completion()

    def _execute_create_step(self, step: FlowStep):
        """Create a new run."""
        prompt = self._build_prompt(step)
        if not prompt:
            return
        res = API.create_run(prompt)
        new_id = res.get("id")
        if new_id:
            self._emit(f"🆕 Created run #{new_id} from step '{step.label}'", C_RUN)
            self.run_id = new_id  # Chain to new run

    def _execute_sub_flow(self, step: FlowStep):
        """Agent-calling-agent: spawn sub-flow."""
        if self.depth >= MAX_SUBFLOW_DEPTH:
            self._emit(f"⚠ Max sub-flow depth ({MAX_SUBFLOW_DEPTH}) — skipping", C_PEND)
            return

        flows = FlowStore.load()
        sub_flow = flows.get(step.sub_flow_name)
        if not sub_flow:
            self._emit(f"⚠ Sub-flow '{step.sub_flow_name}' not found", C_FAIL)
            return

        self._emit(f"🔗 Spawning sub-flow '{step.sub_flow_name}' (depth {self.depth + 1})", C_CYCLE)
        # Create a new run for the sub-flow
        prompt = self._build_prompt(step) or f"Execute sub-flow: {step.sub_flow_name}"
        res = API.create_run(prompt)
        sub_run_id = res.get("id")
        if not sub_run_id:
            return

        # Recursive orchestration
        sub_orch = FlowOrchestrator(
            self.root, sub_run_id, sub_flow,
            on_status=self.on_status,
            depth=self.depth + 1,
            project_name=self.project_name
        )
        # Wait for sub-flow to complete
        sub_orch._thread.join(timeout=3600)

    def _execute_setup_command(self, step: FlowStep):
        """Execute setup commands via API."""
        try:
            # Use repo URL from project or step text
            repo_url = step.text.strip() if step.text else ""
            if repo_url:
                result = API.generate_setup_commands(repo_url)
                self._emit(f"🔧 Setup commands generated for {repo_url}", GREEN)
        except Exception as e:
            self._emit(f"⚠ Setup command error: {e}", C_PEND)

    def _build_prompt(self, step: FlowStep) -> str:
        """Build prompt from step's file path and/or text."""
        parts = []
        if step.path and os.path.isfile(step.path):
            try:
                with open(step.path, encoding="utf-8") as f:
                    parts.append(f.read())
            except Exception:
                pass
        if step.text:
            parts.append(step.text)
        return "\n\n".join(parts).strip()

    def _wait_for_input_needed(self, timeout=600):
        """Wait for run to reach 'waiting_for_input' or similar state."""
        elapsed = 0
        while elapsed < timeout and not self._stopped:
            time.sleep(POLL_SEC)
            elapsed += POLL_SEC
            try:
                runs = API.fetch_all_runs()
                run = next((r for r in runs if r.get("id") == self.run_id), None)
                if not run:
                    continue
                s = (run.get("status") or "").lower()
                if "input" in s or "completed" in s or "failed" in s:
                    return
            except Exception:
                pass

    def _wait_for_completion(self, timeout=600):
        """Wait for current step to finish processing."""
        elapsed = 0
        while elapsed < timeout and not self._stopped:
            time.sleep(POLL_SEC)
            elapsed += POLL_SEC
            try:
                runs = API.fetch_all_runs()
                run = next((r for r in runs if r.get("id") == self.run_id), None)
                if not run:
                    continue
                s = (run.get("status") or "").lower()
                if "input" in s or is_done(s):
                    return
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════════
#  MdPickerDialog — Template file browser
# ══════════════════════════════════════════════════════════════════════════════

class MdPickerDialog(tk.Toplevel):
    """Modal dialog to pick a .md template file from CODEGEN_DIR."""
    def __init__(self, parent):
        super().__init__(parent)
        self.result = None
        self.title("Select Template")
        self.geometry("620x480")
        self.configure(bg=BG)
        self.grab_set()
        self.lift()
        self._build()

    def _build(self):
        tk.Frame(self, bg=HOT, height=3).pack(fill=tk.X)
        hdr = tk.Frame(self, bg=PANEL)
        hdr.pack(fill=tk.X)
        lbl(hdr, "📋  Select a Template", fg=HOT, font=FONT_TITLE, bg=PANEL
            ).pack(side=tk.LEFT, padx=20, pady=10)
        btn(hdr, "✕", self.destroy, CARD, fg=MUTED).pack(
            side=tk.RIGHT, padx=12, pady=8)

        body = tk.Frame(self, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        # Scan directory for .md files
        self._files = []
        codegen_dir = CODEGEN_DIR
        if codegen_dir.exists():
            for f in sorted(codegen_dir.iterdir()):
                if f.suffix.lower() in (".md", ".txt") and f.is_file():
                    self._files.append(f)

        self._lb = tk.Listbox(body, bg=PANEL, fg=TEXT, font=FONT,
                               selectbackground=ACCENT, bd=0, relief="flat",
                               selectforeground="white", activestyle="none")
        self._lb.pack(fill=tk.BOTH, expand=True)
        for f in self._files:
            self._lb.insert(tk.END, f.name)

        self._preview = scrolledtext.ScrolledText(
            body, bg=CARD, fg=TEXT, font=FONT_MONO, height=6,
            bd=0, wrap=tk.WORD, relief="flat", state="disabled")
        self._preview.pack(fill=tk.X, pady=(8, 0))
        self._lb.bind("<<ListboxSelect>>", self._on_select)
        self._lb.bind("<Double-1>", lambda e: self._pick())

        foot = tk.Frame(self, bg=PANEL)
        foot.pack(fill=tk.X)
        btn(foot, "Cancel", self.destroy, CARD).pack(side=tk.RIGHT, padx=8, pady=10)
        btn(foot, "Select", self._pick, ACCENT).pack(side=tk.RIGHT, padx=4, pady=10)

    def _on_select(self, _event=None):
        sel = self._lb.curselection()
        if not sel:
            return
        path = self._files[sel[0]]
        try:
            content = path.read_text(encoding="utf-8")[:2000]
            self._preview.config(state="normal")
            self._preview.delete("1.0", tk.END)
            self._preview.insert("1.0", content)
            self._preview.config(state="disabled")
        except Exception:
            pass

    def _pick(self):
        sel = self._lb.curselection()
        if sel:
            self.result = str(self._files[sel[0]])
        self.destroy()


# ══════════════════════════════════════════════════════════════════════════════
#  FlowCreateDialog — Enhanced with parallel groups, cycles, step types
# ══════════════════════════════════════════════════════════════════════════════

class FlowCreateDialog(tk.Toplevel):
    """Create/edit a flow with parallel groups, cycles, and step type selection."""

    def __init__(self, parent, on_saved=None, edit_name=None, edit_steps=None,
                 edit_template=None):
        super().__init__(parent)
        self.on_saved = on_saved
        self._edit_name = edit_name
        self._steps = []
        self._template = edit_template  # FlowTemplate if editing
        self.title("Edit Flow" if edit_name else "New Flow")
        self.geometry("820x680")
        self.configure(bg=BG)
        self.grab_set()
        self.lift()
        self._build()
        if edit_steps:
            self._load_steps(edit_steps)
        if edit_template:
            self._load_template(edit_template)

    def _build(self):
        tk.Frame(self, bg=HOT, height=3).pack(fill=tk.X)
        hdr = tk.Frame(self, bg=PANEL)
        hdr.pack(fill=tk.X)
        title_text = "✏️  Edit Flow" if self._edit_name else "⛓  New Flow"
        lbl(hdr, title_text, fg=HOT, font=FONT_TITLE, bg=PANEL
            ).pack(side=tk.LEFT, padx=20, pady=10)

        body = tk.Frame(self, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)

        # Flow name
        row0 = tk.Frame(body, bg=BG)
        row0.pack(fill=tk.X, pady=(0, 6))
        lbl(row0, "Flow Name:", fg=MUTED, font=FONT_SMALL).pack(side=tk.LEFT)
        self._name_var = tk.StringVar(value=self._edit_name or "")
        ttk.Entry(row0, textvariable=self._name_var, width=30).pack(side=tk.LEFT, padx=8)

        # Cycle controls
        cycle_row = tk.Frame(body, bg=BG)
        cycle_row.pack(fill=tk.X, pady=(0, 6))
        self._cyclic_var = tk.BooleanVar(value=False)
        tk.Checkbutton(cycle_row, text="🔄 Cyclic", variable=self._cyclic_var,
                       bg=BG, fg=C_CYCLE, selectcolor=CARD, font=FONT,
                       activebackground=BG, activeforeground=C_CYCLE
                       ).pack(side=tk.LEFT)
        lbl(cycle_row, "Max cycles:", fg=MUTED, font=FONT_SMALL).pack(side=tk.LEFT, padx=(16, 4))
        self._max_cycles_var = tk.StringVar(value="10")
        ttk.Entry(cycle_row, textvariable=self._max_cycles_var, width=5).pack(side=tk.LEFT)

        self._everrun_var = tk.BooleanVar(value=False)
        tk.Checkbutton(cycle_row, text="♾️ Everrunning", variable=self._everrun_var,
                       bg=BG, fg=C_CYCLE, selectcolor=CARD, font=FONT,
                       activebackground=BG, activeforeground=C_CYCLE
                       ).pack(side=tk.LEFT, padx=(16, 0))

        # Branch template
        br_row = tk.Frame(body, bg=BG)
        br_row.pack(fill=tk.X, pady=(0, 8))
        lbl(br_row, "Branch template:", fg=MUTED, font=FONT_SMALL).pack(side=tk.LEFT)
        self._branch_var = tk.StringVar(value="codegen-bot/{project}/{flow}-{hash}")
        ttk.Entry(br_row, textvariable=self._branch_var, width=40).pack(side=tk.LEFT, padx=8)

        # Steps area
        tk.Frame(body, bg=BORDER, height=1).pack(fill=tk.X, pady=4)
        lbl(body, "Steps", fg=MUTED, font=FONT_BOLD).pack(anchor="w")

        self._steps_frame = tk.Frame(body, bg=BG)
        self._steps_frame.pack(fill=tk.BOTH, expand=True)

        # Canvas with scrollbar for steps
        canvas_frame = tk.Frame(self._steps_frame, bg=BG)
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        self._canvas = tk.Canvas(canvas_frame, bg=BG, bd=0, highlightthickness=0)
        sb = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._inner = tk.Frame(self._canvas, bg=BG)
        self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._inner.bind("<Configure>",
                         lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))

        # Add step button
        btn_row = tk.Frame(body, bg=BG)
        btn_row.pack(fill=tk.X, pady=(8, 0))
        btn(btn_row, "➕ Add Step", self._add_step_row, CARD).pack(side=tk.LEFT)
        btn(btn_row, "📋 Add from Template", self._add_from_template, CARD).pack(side=tk.LEFT, padx=8)

        # Footer
        foot = tk.Frame(self, bg=PANEL)
        foot.pack(fill=tk.X)
        self._msg = lbl(foot, "", fg=MUTED, font=FONT_SMALL, bg=PANEL)
        self._msg.pack(side=tk.LEFT, padx=16, pady=10)
        btn(foot, "Cancel", self.destroy, CARD).pack(side=tk.RIGHT, padx=8, pady=10)
        btn(foot, "💾 Save Flow", self._save, HOT).pack(side=tk.RIGHT, padx=4, pady=10)

        # Add initial step
        self._add_step_row()

    def _add_step_row(self):
        idx = len(self._steps)
        frame = tk.Frame(self._inner, bg=CARD, padx=8, pady=6)
        frame.pack(fill=tk.X, pady=3, padx=2)

        # Step number and label
        lbl(frame, f"Step {idx + 1}", fg=ACCENT, font=FONT_BOLD, bg=CARD).pack(anchor="w")

        r1 = tk.Frame(frame, bg=CARD)
        r1.pack(fill=tk.X, pady=2)
        lbl(r1, "Label:", fg=MUTED, font=FONT_SMALL, bg=CARD).pack(side=tk.LEFT)
        label_var = tk.StringVar()
        ttk.Entry(r1, textvariable=label_var, width=20).pack(side=tk.LEFT, padx=4)

        lbl(r1, "Type:", fg=MUTED, font=FONT_SMALL, bg=CARD).pack(side=tk.LEFT, padx=(12, 0))
        type_var = tk.StringVar(value="normal")
        type_combo = ttk.Combobox(r1, textvariable=type_var, width=14, state="readonly",
                                   values=["normal", "create", "sub_flow", "setup_command"])
        type_combo.pack(side=tk.LEFT, padx=4)

        lbl(r1, "Parallel group:", fg=MUTED, font=FONT_SMALL, bg=CARD).pack(side=tk.LEFT, padx=(12, 0))
        par_var = tk.StringVar()
        ttk.Entry(r1, textvariable=par_var, width=10).pack(side=tk.LEFT, padx=4)

        r2 = tk.Frame(frame, bg=CARD)
        r2.pack(fill=tk.X, pady=2)
        lbl(r2, "File:", fg=MUTED, font=FONT_SMALL, bg=CARD).pack(side=tk.LEFT)
        path_var = tk.StringVar()
        ttk.Entry(r2, textvariable=path_var, width=35).pack(side=tk.LEFT, padx=4)
        btn(r2, "📁", lambda pv=path_var: self._browse_step(pv), CARD, padx=4, pady=2).pack(side=tk.LEFT)

        # Sub-flow name (only for sub_flow type)
        lbl(r2, "Sub-flow:", fg=MUTED, font=FONT_SMALL, bg=CARD).pack(side=tk.LEFT, padx=(8, 0))
        subflow_var = tk.StringVar()
        ttk.Entry(r2, textvariable=subflow_var, width=15).pack(side=tk.LEFT, padx=4)

        r3 = tk.Frame(frame, bg=CARD)
        r3.pack(fill=tk.X, pady=2)
        lbl(r3, "Extra text:", fg=MUTED, font=FONT_SMALL, bg=CARD).pack(side=tk.LEFT)
        text_var = tk.StringVar()
        ttk.Entry(r3, textvariable=text_var, width=50).pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)

        # Delete button
        btn(frame, "🗑", lambda f=frame, i=idx: self._remove_step(f, i),
            CARD, fg=C_FAIL, padx=4, pady=2).pack(anchor="e")

        self._steps.append({
            "frame": frame,
            "label": label_var,
            "path": path_var,
            "text": text_var,
            "type": type_var,
            "parallel_group": par_var,
            "sub_flow_name": subflow_var,
        })

    def _browse_step(self, path_var):
        p = filedialog.askopenfilename(
            filetypes=[("Markdown", "*.md"), ("Text", "*.txt"), ("All", "*.*")])
        if p:
            path_var.set(p)

    def _add_from_template(self):
        dlg = MdPickerDialog(self)
        self.wait_window(dlg)
        if dlg.result:
            if self._steps:
                last = self._steps[-1]
                last["path"].set(dlg.result)
                last["label"].set(Path(dlg.result).stem)
            else:
                self._add_step_row()
                self._steps[-1]["path"].set(dlg.result)
                self._steps[-1]["label"].set(Path(dlg.result).stem)

    def _remove_step(self, frame, idx):
        frame.destroy()
        if idx < len(self._steps):
            self._steps.pop(idx)

    def _load_steps(self, steps):
        """Load steps from legacy format (list of dicts)."""
        for s in steps:
            self._add_step_row()
            row = self._steps[-1]
            if isinstance(s, dict):
                row["label"].set(s.get("label", ""))
                row["path"].set(s.get("path", ""))
                row["text"].set(s.get("text", ""))
                row["type"].set(s.get("step_type", "normal"))
                row["parallel_group"].set(s.get("parallel_group", ""))
                row["sub_flow_name"].set(s.get("sub_flow_name", ""))

    def _load_template(self, template: FlowTemplate):
        """Load from FlowTemplate object."""
        self._name_var.set(template.name)
        self._cyclic_var.set(template.is_cyclic)
        self._max_cycles_var.set(str(template.max_cycles))
        self._everrun_var.set(template.everrunning)
        self._branch_var.set(template.branch_template)
        for step in template.steps:
            if isinstance(step, FlowStep):
                self._add_step_row()
                row = self._steps[-1]
                row["label"].set(step.label)
                row["path"].set(step.path)
                row["text"].set(step.text)
                row["type"].set(step.step_type)
                row["parallel_group"].set(step.parallel_group)
                row["sub_flow_name"].set(step.sub_flow_name)

    def _save(self):
        name = self._name_var.get().strip()
        if not name:
            self._msg.config(text="⚠ Enter a flow name", fg=C_FAIL)
            return

        steps = []
        for row in self._steps:
            if row["frame"].winfo_exists():
                steps.append(FlowStep(
                    label=row["label"].get().strip() or f"Step {len(steps) + 1}",
                    path=row["path"].get().strip(),
                    text=row["text"].get().strip(),
                    step_type=row["type"].get(),
                    parallel_group=row["parallel_group"].get().strip(),
                    sub_flow_name=row["sub_flow_name"].get().strip(),
                ))

        if not steps:
            self._msg.config(text="⚠ Add at least one step", fg=C_FAIL)
            return

        template = FlowTemplate(
            name=name,
            steps=steps,
            is_cyclic=self._cyclic_var.get(),
            max_cycles=int(self._max_cycles_var.get() or 10),
            branch_template=self._branch_var.get().strip(),
            everrunning=self._everrun_var.get(),
        )

        flows = FlowStore.load()
        flows[name] = template
        FlowStore.save(flows)

        self._msg.config(text=f"✅ Flow '{name}' saved ({len(steps)} steps)", fg=GREEN)
        if self.on_saved:
            self.on_saved(name)
        self.after(1000, self.destroy)


# ══════════════════════════════════════════════════════════════════════════════
#  FlowManagerDialog — CRUD for flows
# ══════════════════════════════════════════════════════════════════════════════

class FlowManagerDialog(tk.Toplevel):
    def __init__(self, parent, on_changed=None):
        super().__init__(parent)
        self.on_changed = on_changed
        self.title("Flow Manager")
        self.geometry("560x440")
        self.configure(bg=BG)
        self.grab_set()
        self.lift()
        self._build()

    def _build(self):
        tk.Frame(self, bg=HOT, height=3).pack(fill=tk.X)
        hdr = tk.Frame(self, bg=PANEL)
        hdr.pack(fill=tk.X)
        lbl(hdr, "⛓  Flow Manager", fg=HOT, font=FONT_TITLE, bg=PANEL
            ).pack(side=tk.LEFT, padx=20, pady=10)

        body = tk.Frame(self, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)

        self._lb = tk.Listbox(body, bg=PANEL, fg=TEXT, font=FONT,
                               selectbackground=ACCENT, bd=0,
                               selectforeground="white", activestyle="none")
        self._lb.pack(fill=tk.BOTH, expand=True)

        btn_row = tk.Frame(body, bg=BG)
        btn_row.pack(fill=tk.X, pady=(8, 0))
        btn(btn_row, "➕ New", self._new_flow, ACCENT).pack(side=tk.LEFT, padx=2)
        btn(btn_row, "✏️ Edit", self._edit, CARD).pack(side=tk.LEFT, padx=2)
        btn(btn_row, "🗑 Delete", self._delete, CARD, fg=C_FAIL).pack(side=tk.LEFT, padx=2)

        self._info = lbl(body, "", fg=MUTED, font=FONT_SMALL)
        self._info.pack(anchor="w", pady=(4, 0))

        self._refresh()

    def _refresh(self):
        self._lb.delete(0, tk.END)
        flows = FlowStore.load()
        for name, ft in sorted(flows.items()):
            if isinstance(ft, FlowTemplate):
                n_steps = len(ft.steps)
                flags = []
                if ft.is_cyclic: flags.append("🔄")
                if ft.everrunning: flags.append("♾️")
                extra = " ".join(flags)
                self._lb.insert(tk.END, f"{name}  ({n_steps} steps) {extra}")
            else:
                self._lb.insert(tk.END, f"{name}  (legacy)")
        if self.on_changed:
            self.on_changed()

    def _new_flow(self):
        FlowCreateDialog(self, on_saved=lambda _: self._refresh())

    def _edit(self):
        sel = self._lb.curselection()
        if not sel:
            return
        name = self._lb.get(sel[0]).split("  (")[0]
        flows = FlowStore.load()
        ft = flows.get(name)
        if isinstance(ft, FlowTemplate):
            FlowCreateDialog(self, on_saved=lambda _: self._refresh(),
                            edit_name=name, edit_template=ft)
        elif isinstance(ft, list):
            FlowCreateDialog(self, on_saved=lambda _: self._refresh(),
                            edit_name=name, edit_steps=ft)

    def _delete(self):
        sel = self._lb.curselection()
        if not sel:
            return
        name = self._lb.get(sel[0]).split("  (")[0]
        if messagebox.askyesno("Delete Flow", f"Delete flow '{name}'?"):
            flows = FlowStore.load()
            flows.pop(name, None)
            FlowStore.save(flows)
            self._refresh()


# ══════════════════════════════════════════════════════════════════════════════
#  CreateRunDialog — Enhanced with project selector, flow attachment
# ══════════════════════════════════════════════════════════════════════════════

class CreateRunDialog(tk.Toplevel):
    def __init__(self, parent, on_created, on_flow_runner=None):
        super().__init__(parent)
        self.on_created = on_created
        self.on_flow_runner = on_flow_runner
        self._tpl_text = None
        self.title("New Agent Run")
        self.geometry("780x640")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.grab_set()
        self.lift()
        self._build()
        self.after(200, self._try_default_tpl)

    def _build(self):
        tk.Frame(self, bg=HOT, height=3).pack(fill=tk.X)
        hdr = tk.Frame(self, bg=PANEL)
        hdr.pack(fill=tk.X)
        lbl(hdr, "🚀  New Agent Run", fg=HOT, font=FONT_TITLE, bg=PANEL
            ).pack(side=tk.LEFT, padx=20, pady=14)
        btn(hdr, "✕", self.destroy, CARD, fg=MUTED).pack(
            side=tk.RIGHT, padx=12, pady=8)

        body = tk.Frame(self, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        # Project selector
        proj_row = tk.Frame(body, bg=BG)
        proj_row.pack(fill=tk.X, pady=(0, 6))
        lbl(proj_row, "📁 Project:", fg=MUTED, font=FONT_SMALL).pack(side=tk.LEFT)
        self._proj_var = tk.StringVar(value="None")
        self._proj_combo = ttk.Combobox(proj_row, textvariable=self._proj_var,
                                         width=24, state="readonly")
        self._proj_combo.pack(side=tk.LEFT, padx=8)
        self._proj_combo.bind("<<ComboboxSelected>>", self._on_project_selected)
        self._refresh_projects()

        # Template file
        lbl(body, "Template File  (optional)", fg=MUTED, font=FONT_SMALL
            ).pack(anchor="w", pady=(0, 3))
        tr = tk.Frame(body, bg=BG)
        tr.pack(fill=tk.X)
        self._tpl_var = tk.StringVar(value=DEFAULT_TPL)
        ttk.Entry(tr, textvariable=self._tpl_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        btn(tr, "Browse", self._browse, CARD).pack(side=tk.LEFT, padx=2)
        btn(tr, "Load", self._load, ACCENT).pack(side=tk.LEFT, padx=2)

        self._tpl_info = lbl(body, "", fg=MUTED, font=FONT_SMALL)
        self._tpl_info.pack(anchor="w", pady=(4, 8))

        lbl(body, "Prompt / Instructions", fg=MUTED, font=FONT_SMALL
            ).pack(anchor="w", pady=(0, 3))
        self._prompt = scrolledtext.ScrolledText(
            body, bg=PANEL, fg=TEXT, insertbackground=TEXT,
            font=FONT, height=8, bd=0, wrap=tk.WORD, relief="flat",
            padx=10, pady=8)
        self._prompt.pack(fill=tk.BOTH, expand=True)
        self._prompt.focus()
        attach_edit_menu(self._prompt)

        # Flow selector
        tk.Frame(body, bg=BORDER, height=1).pack(fill=tk.X, pady=(10, 6))
        flow_row = tk.Frame(body, bg=BG)
        flow_row.pack(fill=tk.X)
        lbl(flow_row, "⛓  Flow  (optional):", fg=MUTED, font=FONT_SMALL
            ).pack(side=tk.LEFT, padx=(0, 8))
        self._flow_var = tk.StringVar(value="None")
        self._flow_combo = ttk.Combobox(
            flow_row, textvariable=self._flow_var,
            width=26, state="readonly")
        self._flow_combo.pack(side=tk.LEFT, padx=(0, 6))
        self._flow_combo.bind("<<ComboboxSelected>>", self._on_flow_selected)
        btn(flow_row, "⛓ Manage Flows", self._open_flow_manager,
            CARD).pack(side=tk.LEFT, padx=4)
        self._flow_info = lbl(flow_row, "", fg=MUTED, font=FONT_SMALL)
        self._flow_info.pack(side=tk.LEFT, padx=8)
        self._refresh_flow_combo()

        foot = tk.Frame(self, bg=PANEL)
        foot.pack(fill=tk.X)
        self._foot_msg = lbl(foot, "", fg=MUTED, font=FONT_SMALL, bg=PANEL)
        self._foot_msg.pack(side=tk.LEFT, padx=16, pady=12)
        btn(foot, "Cancel", self.destroy, CARD).pack(
            side=tk.RIGHT, padx=8, pady=10)
        btn(foot, "🚀  Launch Run", self._launch, HOT).pack(
            side=tk.RIGHT, padx=4, pady=10)

    def _refresh_projects(self):
        projects = ProjectStore.load()
        names = ["None"] + sorted(projects.keys())
        self._proj_combo["values"] = names

    def _on_project_selected(self, _event=None):
        name = self._proj_var.get()
        if name == "None":
            return
        projects = ProjectStore.load()
        proj = projects.get(name)
        if proj and proj.prd_text:
            self._prompt.delete("1.0", tk.END)
            self._prompt.insert("1.0", proj.prd_text)

    def _browse(self):
        p = filedialog.askopenfilename(
            filetypes=[("Markdown", "*.md"), ("Text", "*.txt"), ("All", "*.*")])
        if p:
            self._tpl_var.set(p)
            self._load()

    def _refresh_flow_combo(self):
        flows = FlowStore.load()
        names = ["None"] + sorted(flows.keys())
        self._flow_combo["values"] = names
        if self._flow_var.get() not in names:
            self._flow_var.set("None")
        self._on_flow_selected()

    def _on_flow_selected(self, _event=None):
        name = self._flow_var.get()
        if name == "None":
            self._flow_info.config(text="", fg=MUTED)
            return
        flows = FlowStore.load()
        ft = flows.get(name)
        if isinstance(ft, FlowTemplate):
            flags = []
            if ft.is_cyclic: flags.append("🔄")
            if ft.everrunning: flags.append("♾️")
            self._flow_info.config(
                text=f"{len(ft.steps)} step(s) {' '.join(flags)}", fg=ACCENT)

    def _open_flow_manager(self):
        FlowManagerDialog(self, on_changed=self._refresh_flow_combo)

    def _try_default_tpl(self):
        if os.path.isfile(DEFAULT_TPL):
            self._load()

    def _load(self):
        path = self._tpl_var.get()
        if not path or not os.path.isfile(path):
            self._tpl_info.config(text="File not found", fg=C_FAIL)
            return
        try:
            with open(path, encoding="utf-8") as f:
                self._tpl_text = f.read()
            self._tpl_info.config(
                text=f"✓  {os.path.basename(path)}  ({len(self._tpl_text):,} chars)",
                fg=GREEN)
        except Exception as e:
            self._tpl_info.config(text=f"Error: {e}", fg=C_FAIL)

    def _launch(self):
        extra = self._prompt.get("1.0", tk.END).strip()
        parts = [p for p in [self._tpl_text, extra] if p and p.strip()]
        prompt = "\n\n".join(parts).strip()
        if not prompt:
            self._foot_msg.config(text="⚠  Enter a prompt or load a template.",
                                  fg=C_PEND)
            return

        flow_name = self._flow_var.get()
        self._selected_flow = None
        if flow_name != "None":
            flows = FlowStore.load()
            self._selected_flow = flows.get(flow_name)

        self._foot_msg.config(text="Launching…", fg=C_PEND)

        def _bg():
            try:
                res = API.create_run(prompt, model="claude-opus-4-6")
                self.after(0, lambda: self._done(res))
            except Exception as e:
                self.after(0, lambda: self._foot_msg.config(
                    text=f"Error: {e}", fg=C_FAIL))
        threading.Thread(target=_bg, daemon=True).start()

    def _done(self, res):
        rid = res.get("id", "?")
        flow = getattr(self, "_selected_flow", None)
        msg = f"✅  Run #{rid} created!"
        if flow:
            msg += f"  ⛓ flow ({len(flow.steps) if isinstance(flow, FlowTemplate) else len(flow)} steps) queued"
        self._foot_msg.config(text=msg, fg=GREEN)
        self.on_created(res)
        if flow and self.on_flow_runner:
            self.on_flow_runner(rid, flow)
        self.after(1400, self.destroy)


# ══════════════════════════════════════════════════════════════════════════════
#  ProjectManagerDialog — PRD editor, project CRUD
# ══════════════════════════════════════════════════════════════════════════════

class ProjectManagerDialog(tk.Toplevel):
    def __init__(self, parent, on_changed=None):
        super().__init__(parent)
        self.on_changed = on_changed
        self.title("Project Manager")
        self.geometry("740x560")
        self.configure(bg=BG)
        self.grab_set()
        self.lift()
        self._build()

    def _build(self):
        tk.Frame(self, bg=HOT, height=3).pack(fill=tk.X)
        hdr = tk.Frame(self, bg=PANEL)
        hdr.pack(fill=tk.X)
        lbl(hdr, "📁  Project Manager", fg=HOT, font=FONT_TITLE, bg=PANEL
            ).pack(side=tk.LEFT, padx=20, pady=10)

        body = tk.Frame(self, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)

        # Left: project list
        left = tk.Frame(body, bg=BG, width=200)
        left.pack(side=tk.LEFT, fill=tk.Y)
        self._lb = tk.Listbox(left, bg=PANEL, fg=TEXT, font=FONT,
                               selectbackground=ACCENT, bd=0,
                               selectforeground="white", activestyle="none",
                               width=22)
        self._lb.pack(fill=tk.BOTH, expand=True)
        self._lb.bind("<<ListboxSelect>>", self._on_select)

        btn_row = tk.Frame(left, bg=BG)
        btn_row.pack(fill=tk.X, pady=(4, 0))
        btn(btn_row, "➕", self._new_project, ACCENT, padx=6).pack(side=tk.LEFT)
        btn(btn_row, "🗑", self._delete_project, CARD, fg=C_FAIL, padx=6).pack(side=tk.LEFT, padx=4)

        # Right: editor
        right = tk.Frame(body, bg=BG)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0))

        lbl(right, "Project Name:", fg=MUTED, font=FONT_SMALL).pack(anchor="w")
        self._name_var = tk.StringVar()
        ttk.Entry(right, textvariable=self._name_var, width=30).pack(anchor="w", pady=(0, 6))

        lbl(right, "Repo URL:", fg=MUTED, font=FONT_SMALL).pack(anchor="w")
        self._repo_var = tk.StringVar()
        ttk.Entry(right, textvariable=self._repo_var, width=40).pack(anchor="w", pady=(0, 6))

        lbl(right, "Branch Template:", fg=MUTED, font=FONT_SMALL).pack(anchor="w")
        self._branch_var = tk.StringVar(value="codegen-bot/{project}/{feature}-{hash}")
        ttk.Entry(right, textvariable=self._branch_var, width=40).pack(anchor="w", pady=(0, 6))

        lbl(right, "PRD / Requirements:", fg=MUTED, font=FONT_SMALL).pack(anchor="w")
        self._prd = scrolledtext.ScrolledText(
            right, bg=PANEL, fg=TEXT, font=FONT, height=10,
            bd=0, wrap=tk.WORD, relief="flat", insertbackground=TEXT)
        self._prd.pack(fill=tk.BOTH, expand=True, pady=(0, 6))
        attach_edit_menu(self._prd)

        # Flow binding
        lbl(right, "Attached Flows:", fg=MUTED, font=FONT_SMALL).pack(anchor="w")
        self._flow_list = tk.Listbox(right, bg=CARD, fg=TEXT, font=FONT_SMALL,
                                      height=3, bd=0, selectbackground=ACCENT)
        self._flow_list.pack(fill=tk.X, pady=(0, 6))

        flow_btn_row = tk.Frame(right, bg=BG)
        flow_btn_row.pack(fill=tk.X)
        btn(flow_btn_row, "➕ Attach Flow", self._attach_flow, CARD, padx=6).pack(side=tk.LEFT)
        btn(flow_btn_row, "💾 Save", self._save, HOT).pack(side=tk.RIGHT)

        self._msg = lbl(right, "", fg=MUTED, font=FONT_SMALL)
        self._msg.pack(anchor="w", pady=(4, 0))

        self._refresh()

    def _refresh(self):
        self._lb.delete(0, tk.END)
        for name in sorted(ProjectStore.load().keys()):
            self._lb.insert(tk.END, name)

    def _on_select(self, _event=None):
        sel = self._lb.curselection()
        if not sel:
            return
        name = self._lb.get(sel[0])
        projects = ProjectStore.load()
        proj = projects.get(name)
        if not proj:
            return
        self._name_var.set(proj.name)
        self._repo_var.set(proj.repo_url)
        self._branch_var.set(proj.branch_template)
        self._prd.delete("1.0", tk.END)
        self._prd.insert("1.0", proj.prd_text)
        self._flow_list.delete(0, tk.END)
        for fn in proj.flow_names:
            self._flow_list.insert(tk.END, fn)

    def _new_project(self):
        name = f"project-{uuid.uuid4().hex[:6]}"
        projects = ProjectStore.load()
        projects[name] = Project(name=name)
        ProjectStore.save(projects)
        self._refresh()
        # Select the new one
        items = self._lb.get(0, tk.END)
        if name in items:
            idx = list(items).index(name)
            self._lb.selection_set(idx)
            self._on_select()

    def _delete_project(self):
        sel = self._lb.curselection()
        if not sel:
            return
        name = self._lb.get(sel[0])
        if messagebox.askyesno("Delete", f"Delete project '{name}'?"):
            projects = ProjectStore.load()
            projects.pop(name, None)
            ProjectStore.save(projects)
            self._refresh()

    def _attach_flow(self):
        flows = FlowStore.load()
        if not flows:
            messagebox.showinfo("No Flows", "Create flows first in Flow Manager.")
            return
        # Simple selection dialog
        names = sorted(flows.keys())
        # Add first available not already attached
        existing = set(self._flow_list.get(0, tk.END))
        for n in names:
            if n not in existing:
                self._flow_list.insert(tk.END, n)
                break

    def _save(self):
        name = self._name_var.get().strip()
        if not name:
            self._msg.config(text="⚠ Enter a name", fg=C_FAIL)
            return
        projects = ProjectStore.load()
        proj = projects.get(name, Project(name=name))
        proj.name = name
        proj.repo_url = self._repo_var.get().strip()
        proj.branch_template = self._branch_var.get().strip()
        proj.prd_text = self._prd.get("1.0", tk.END).strip()
        proj.flow_names = list(self._flow_list.get(0, tk.END))
        projects[name] = proj
        ProjectStore.save(projects)
        self._msg.config(text=f"✅ Saved '{name}'", fg=GREEN)
        self._refresh()
        if self.on_changed:
            self.on_changed()


# ══════════════════════════════════════════════════════════════════════════════
#  RunDialog — View logs, resume, attach flows
# ══════════════════════════════════════════════════════════════════════════════

class RunDialog(tk.Toplevel):
    def __init__(self, parent, run_data, on_flow_runner=None):
        super().__init__(parent)
        self.run_data = run_data
        self.on_flow_runner = on_flow_runner
        self._rid = run_data.get("id", "?")
        self.title(f"Run #{self._rid}")
        self.geometry("780x620")
        self.configure(bg=BG)
        self._build()
        self.after(300, self._fetch_logs)

    def _build(self):
        status = self.run_data.get("status", "")
        color = status_color(status)
        tk.Frame(self, bg=color, height=3).pack(fill=tk.X)

        hdr = tk.Frame(self, bg=PANEL)
        hdr.pack(fill=tk.X)
        lbl(hdr, f"📋  Run #{self._rid}  —  {status}",
            fg=color, font=FONT_TITLE, bg=PANEL
            ).pack(side=tk.LEFT, padx=20, pady=12)
        btn(hdr, "✕", self.destroy, CARD, fg=MUTED).pack(
            side=tk.RIGHT, padx=12, pady=8)

        info = tk.Frame(self, bg=BG)
        info.pack(fill=tk.X, padx=20, pady=4)
        created = fmt_dt(self.run_data.get("created_at", ""))
        lbl(info, f"Created: {created}", fg=MUTED, font=FONT_SMALL).pack(side=tk.LEFT)
        web = self.run_data.get("web_url", "")
        if web:
            btn(info, "🌐 Open", lambda: webbrowser.open(web), CARD, padx=6
                ).pack(side=tk.RIGHT)

        body = tk.Frame(self, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=20, pady=6)

        lbl(body, "Conversation Log", fg=MUTED, font=FONT_SMALL).pack(anchor="w")
        self._log = scrolledtext.ScrolledText(
            body, bg=PANEL, fg=TEXT, font=FONT_MONO,
            bd=0, wrap=tk.WORD, relief="flat", state="disabled",
            padx=8, pady=6)
        self._log.pack(fill=tk.BOTH, expand=True)
        attach_edit_menu(self._log)

        # Resume prompt
        tk.Frame(body, bg=BORDER, height=1).pack(fill=tk.X, pady=(8, 4))
        lbl(body, "Resume with prompt:", fg=MUTED, font=FONT_SMALL).pack(anchor="w")
        self._resume = scrolledtext.ScrolledText(
            body, bg=CARD, fg=TEXT, font=FONT, height=3,
            bd=0, wrap=tk.WORD, relief="flat", insertbackground=TEXT)
        self._resume.pack(fill=tk.X)
        attach_edit_menu(self._resume)

        foot = tk.Frame(self, bg=PANEL)
        foot.pack(fill=tk.X)
        self._msg = lbl(foot, "", fg=MUTED, font=FONT_SMALL, bg=PANEL)
        self._msg.pack(side=tk.LEFT, padx=16, pady=10)

        # Flow controls
        flow_row = tk.Frame(foot, bg=PANEL)
        flow_row.pack(side=tk.LEFT, padx=(20, 0))
        lbl(flow_row, "⛓ Flow:", fg=MUTED, font=FONT_SMALL, bg=PANEL).pack(side=tk.LEFT)
        self._flow_var = tk.StringVar(value="None")
        flows = FlowStore.load()
        names = ["None"] + sorted(flows.keys())
        self._flow_combo = ttk.Combobox(flow_row, textvariable=self._flow_var,
                                         width=16, state="readonly", values=names)
        self._flow_combo.pack(side=tk.LEFT, padx=4)
        btn(flow_row, "▶ Run Flow", self._start_flow, ACCENT, padx=6).pack(side=tk.LEFT, padx=4)

        btn(foot, "▶ Resume", self._do_resume, HOT).pack(
            side=tk.RIGHT, padx=8, pady=10)
        btn(foot, "🔄 Refresh", self._fetch_logs, CARD).pack(
            side=tk.RIGHT, padx=4, pady=10)

    def _fetch_logs(self):
        self._msg.config(text="Loading…", fg=C_PEND)
        def _bg():
            try:
                data = API.fetch_all_logs(self._rid)
                self.after(0, lambda: self._show_logs(data))
            except Exception as e:
                self.after(0, lambda: self._msg.config(
                    text=f"Error: {e}", fg=C_FAIL))
        threading.Thread(target=_bg, daemon=True).start()

    def _show_logs(self, data):
        self._log.config(state="normal")
        self._log.delete("1.0", tk.END)
        logs = data.get("logs", []) if data else []
        for entry in logs:
            role = entry.get("role", "").upper()
            msg = entry.get("content", "")[:5000]
            self._log.insert(tk.END, f"[{role}] {msg}\n\n")
        self._log.see(tk.END)
        self._log.config(state="disabled")
        self._msg.config(text=f"✓ {len(logs)} log entries", fg=GREEN)

    def _do_resume(self):
        prompt = self._resume.get("1.0", tk.END).strip()
        if not prompt:
            self._msg.config(text="⚠ Enter a prompt", fg=C_PEND)
            return
        self._msg.config(text="Resuming…", fg=C_PEND)
        def _bg():
            try:
                API.resume_run(self._rid, prompt)
                self.after(0, lambda: self._msg.config(
                    text="✅ Resumed!", fg=GREEN))
                self.after(2000, self._fetch_logs)
            except Exception as e:
                self.after(0, lambda: self._msg.config(
                    text=f"Error: {e}", fg=C_FAIL))
        threading.Thread(target=_bg, daemon=True).start()

    def _start_flow(self):
        fname = self._flow_var.get()
        if fname == "None":
            return
        flows = FlowStore.load()
        flow = flows.get(fname)
        if flow and self.on_flow_runner:
            self.on_flow_runner(self._rid, flow)
            self._msg.config(text=f"⛓ Flow '{fname}' started!", fg=C_CYCLE)


# ══════════════════════════════════════════════════════════════════════════════
#  CodegenManager — Main Dashboard Window
# ══════════════════════════════════════════════════════════════════════════════

class CodegenManager:
    """Main application window — multi-panel dashboard with flow status."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("⚡ Codegen Agent Manager v2.0")
        self.root.geometry("1100x760")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)
        self._runs = []
        self._flow_orchestrators = []
        self._stars = self._load_stars()
        self._build()
        self._poll_loop()

    # ── Stars persistence ──
    def _load_stars(self):
        try:
            return set(json.loads(STAR_FILE.read_text(encoding="utf-8")))
        except Exception:
            return set()

    def _save_stars(self):
        try:
            STAR_FILE.write_text(json.dumps(list(self._stars)), encoding="utf-8")
        except Exception:
            pass

    def _toggle_star(self, rid):
        rid = str(rid)
        if rid in self._stars:
            self._stars.discard(rid)
        else:
            self._stars.add(rid)
        self._save_stars()
        self._repopulate()

    # ── Build UI ──
    def _build(self):
        # Top accent bar
        tk.Frame(self.root, bg=HOT, height=3).pack(fill=tk.X)

        # Toolbar
        toolbar = tk.Frame(self.root, bg=PANEL, padx=8, pady=6)
        toolbar.pack(fill=tk.X)

        # Live indicator
        self._live = tk.Label(toolbar, text="⚡ LIVE", fg=GREEN, bg=PANEL,
                               font=FONT_BOLD, padx=8)
        self._live.pack(side=tk.LEFT)
        lbl(toolbar, "Codegen Agent Manager v2.0", fg=TEXT, font=FONT_TITLE,
            bg=PANEL).pack(side=tk.LEFT, padx=12)

        # Toolbar buttons
        btn_frame = tk.Frame(toolbar, bg=PANEL)
        btn_frame.pack(side=tk.RIGHT)
        btn(btn_frame, "🚀 New Run", self._new_run, HOT).pack(side=tk.RIGHT, padx=4)
        btn(btn_frame, "📁 Projects", self._open_projects, CARD).pack(side=tk.RIGHT, padx=4)
        btn(btn_frame, "⛓ Flows", self._open_flows, CARD).pack(side=tk.RIGHT, padx=4)
        btn(btn_frame, "🔄 Refresh", self._manual_refresh, CARD).pack(side=tk.RIGHT, padx=4)
        btn(btn_frame, "⚙ Settings", self._open_settings, CARD, fg=MUTED).pack(side=tk.RIGHT, padx=4)

        # Search
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._repopulate())
        ttk.Entry(toolbar, textvariable=self._search_var, width=20).pack(
            side=tk.RIGHT, padx=8)
        lbl(toolbar, "🔍", bg=PANEL, fg=MUTED).pack(side=tk.RIGHT)

        # Main content area with three sections
        content = tk.Frame(self.root, bg=BG)
        content.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)

        # Treeview for runs
        tree_frame = tk.Frame(content, bg=BG)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("star", "id", "status", "created", "summary", "prs", "source")
        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                                   selectmode="browse", height=20)
        self._tree.heading("star", text="★")
        self._tree.heading("id", text="ID")
        self._tree.heading("status", text="Status")
        self._tree.heading("created", text="Created")
        self._tree.heading("summary", text="Summary")
        self._tree.heading("prs", text="PRs")
        self._tree.heading("source", text="Source")

        self._tree.column("star", width=30, anchor="center")
        self._tree.column("id", width=70, anchor="center")
        self._tree.column("status", width=100)
        self._tree.column("created", width=140)
        self._tree.column("summary", width=350)
        self._tree.column("prs", width=60, anchor="center")
        self._tree.column("source", width=100)

        sb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.pack(fill=tk.BOTH, expand=True)
        self._tree.bind("<Double-1>", self._open_run)
        self._tree.bind("<Button-3>", self._context_menu)

        # Configure tags
        style = ttk.Style()
        style.configure("Treeview", background=PANEL, foreground=TEXT,
                         fieldbackground=PANEL, font=FONT, rowheight=28)
        style.configure("Treeview.Heading", background=CARD, foreground=TEXT,
                         font=FONT_BOLD)
        style.map("Treeview", background=[("selected", ACCENT)])
        self._tree.tag_configure("running", foreground=C_RUN)
        self._tree.tag_configure("completed", foreground=C_DONE)
        self._tree.tag_configure("failed", foreground=C_FAIL)
        self._tree.tag_configure("starred", foreground="#f1c40f")

        # Bottom status bar — flow status
        self._status_bar = tk.Frame(self.root, bg=CARD, height=32)
        self._status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        self._status_lbl = lbl(self._status_bar, "Ready", fg=MUTED,
                                font=FONT_SMALL, bg=CARD)
        self._status_lbl.pack(side=tk.LEFT, padx=12, pady=4)

        # Flow status indicators
        self._flow_status_frame = tk.Frame(self._status_bar, bg=CARD)
        self._flow_status_frame.pack(side=tk.RIGHT, padx=12)

    # ── Context menu ──
    def _context_menu(self, event):
        sel = self._tree.identify_row(event.y)
        if not sel:
            return
        self._tree.selection_set(sel)
        run = self._get_selected_run()
        if not run:
            return

        m = tk.Menu(self.root, tearoff=0, bg=CARD, fg=TEXT,
                     activebackground=ACCENT, activeforeground="white",
                     font=FONT_SMALL, bd=0)
        rid = str(run.get("id", ""))
        star_text = "☆ Unstar" if rid in self._stars else "★ Star"
        m.add_command(label=star_text, command=lambda: self._toggle_star(rid))
        m.add_command(label="📋 View Logs", command=lambda: self._open_run_data(run))
        m.add_command(label="▶ Resume", command=lambda: self._quick_resume(run))
        m.add_separator()
        m.add_command(label="📋 Copy ID", command=lambda: self._copy_id(run))
        web = run.get("web_url", "")
        if web:
            m.add_command(label="🌐 Open in Browser",
                         command=lambda: webbrowser.open(web))
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    def _copy_id(self, run):
        rid = str(run.get("id", ""))
        self.root.clipboard_clear()
        self.root.clipboard_append(rid)

    def _get_selected_run(self):
        sel = self._tree.selection()
        if not sel:
            return None
        item = self._tree.item(sel[0])
        rid = item["values"][1] if item["values"] else None
        if rid:
            return next((r for r in self._runs if str(r.get("id")) == str(rid)), None)
        return None

    # ── Actions ──
    def _new_run(self):
        CreateRunDialog(self.root, self._on_created, self._start_flow_runner)

    def _open_projects(self):
        ProjectManagerDialog(self.root)

    def _open_flows(self):
        FlowManagerDialog(self.root)

    def _open_settings(self):
        messagebox.showinfo("Settings",
                            f"API Base: {API_BASE}\n"
                            f"Org ID: {ORG_ID}\n"
                            f"Poll Interval: {POLL_SEC}s\n"
                            f"Max Parallel: {MAX_PARALLEL_RUNS}\n"
                            f"Max Cycles: {MAX_CYCLE_ITERATIONS}\n"
                            f"Codegen Dir: {CODEGEN_DIR}\n\n"
                            f"Configure via environment variables.")

    def _manual_refresh(self):
        self._status_lbl.config(text="Refreshing…", fg=C_PEND)
        self._do_poll()

    def _open_run(self, _event=None):
        run = self._get_selected_run()
        if run:
            self._open_run_data(run)

    def _open_run_data(self, run):
        RunDialog(self.root, run, on_flow_runner=self._start_flow_runner)

    def _quick_resume(self, run):
        rid = run.get("id")
        if rid:
            RunDialog(self.root, run, on_flow_runner=self._start_flow_runner)

    def _on_created(self, res):
        self._do_poll()

    def _start_flow_runner(self, run_id, flow):
        """Start a FlowOrchestrator for the given run and flow."""
        if isinstance(flow, FlowTemplate):
            ft = flow
        elif isinstance(flow, list):
            ft = FlowTemplate(name="manual", steps=[
                FlowStep.from_dict(s) if isinstance(s, dict) else s for s in flow
            ])
        else:
            return

        def on_status(msg, color):
            self._update_flow_status(ft.name, msg, color)

        orch = FlowOrchestrator(self.root, run_id, ft,
                                 on_status=on_status)
        self._flow_orchestrators.append(orch)
        self._update_flow_status(ft.name, f"⛓ Starting '{ft.name}'…", C_CYCLE)

    def _update_flow_status(self, name, msg, color):
        """Update flow status in the bottom bar."""
        self._status_lbl.config(text=f"⛓ {name}: {msg}", fg=color)

    # ── Polling ──
    def _poll_loop(self):
        self._do_poll()
        self.root.after(POLL_SEC * 1000, self._poll_loop)

    def _do_poll(self):
        def _bg():
            try:
                runs = API.fetch_all_runs()
                self.root.after(0, lambda: self._update_runs(runs))
            except Exception as e:
                self.root.after(0, lambda: self._status_lbl.config(
                    text=f"❌ Poll error: {e}", fg=C_FAIL))
        threading.Thread(target=_bg, daemon=True).start()

    def _update_runs(self, runs):
        self._runs = runs
        self._repopulate()
        active = sum(1 for r in runs if is_active(r.get("status")))
        self._live.config(
            text=f"⚡ LIVE — {active} active",
            fg=GREEN if active else MUTED)
        self._status_lbl.config(
            text=f"✓ {len(runs)} runs loaded", fg=GREEN)

    def _repopulate(self):
        self._tree.delete(*self._tree.get_children())
        search = self._search_var.get().lower()
        for run in self._runs:
            rid = str(run.get("id", ""))
            status = run.get("status", "")
            created = fmt_dt(run.get("created_at", ""))
            prompt = run.get("prompt", "")[:80]
            prs = len(run.get("pull_requests", []))
            source = run.get("source", "")
            tag = status_tag(status)
            starred = "★" if rid in self._stars else ""

            # Filter
            if search:
                text = f"{rid} {status} {prompt} {source}".lower()
                if search not in text:
                    continue

            self._tree.insert("", tk.END,
                              values=(starred, rid, status, created, prompt, prs, source),
                              tags=(tag, "starred" if starred else ""))


# ══════════════════════════════════════════════════════════════════════════════
#  Entry Point
# ══════════════════════════════════════════════════════════════════════════════

def main():
    """Main entry point — install deps if needed, launch GUI."""
    # Auto-install missing deps
    for pkg in ("requests", "plyer"):
        try:
            __import__(pkg)
        except ImportError:
            import subprocess
            subprocess.check_call(["pip", "install", pkg])

    root = tk.Tk()
    try:
        root.iconbitmap(default="")
    except Exception:
        pass

    app = CodegenManager(root)
    root.mainloop()


if __name__ == "__main__":
    main()
