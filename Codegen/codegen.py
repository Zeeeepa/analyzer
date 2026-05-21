#!/usr/bin/env python3
"""
Codegen Agent Manager  ·  Single-view edition
pip install requests plyer
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import threading, time, json, requests, os, webbrowser
from datetime import datetime
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────────
API_BASE    = "https://api.codegen.com/v1"
ORG_ID      = 323
API_TOKEN   = "sk-92083737-4e5b-4a48-a2a1-f870a3a096a6"
HEADERS     = {"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "application/json"}
POLL_SEC    = 15
DEFAULT_TPL    = r"C:\Users\L\Documents\Codegen\analysis.md"
CODEGEN_DIR   = r"C:\Users\L\Documents\Codegen"

# ── Palette ─────────────────────────────────────────────────────────────────────
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

FONT        = ("Segoe UI", 10)
FONT_BOLD   = ("Segoe UI", 10, "bold")
FONT_SMALL  = ("Segoe UI", 8)
FONT_MONO   = ("Consolas", 9)
FONT_TITLE  = ("Segoe UI", 13, "bold")


# ════════════════════════════════════════════════════════════════════════════════
#  Helpers
# ════════════════════════════════════════════════════════════════════════════════

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
    """Attach a right-click Cut/Copy/Paste/Select-All context menu to any text widget."""
    is_text = isinstance(widget, (tk.Text,))   # ScrolledText is a subclass of tk.Text

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


# ════════════════════════════════════════════════════════════════════════════════
#  API layer
# ════════════════════════════════════════════════════════════════════════════════

class API:
    @staticmethod
    def _get(path, params=None):
        r = requests.get(f"{API_BASE}{path}", headers=HEADERS,
                         params=params, timeout=20)
        r.raise_for_status()
        return r.json()

    @staticmethod
    def _post(path, body):
        r = requests.post(f"{API_BASE}{path}", headers=HEADERS,
                          json=body, timeout=20)
        r.raise_for_status()
        return r.json()

    @classmethod
    def fetch_all_runs(cls):
        """Fetch the most recent 1000 runs (10 pages of 100)."""
        all_items, skip, limit, max_runs = [], 0, 100, 1000
        while len(all_items) < max_runs:
            data  = cls._get(f"/organizations/{ORG_ID}/agent/runs",
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
            logs  = data.get("logs", [])
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




# ════════════════════════════════════════════════════════════════════════════════
#  MdPickerDialog  —  pick an .md file from the Codegen folder
# ════════════════════════════════════════════════════════════════════════════════

class MdPickerDialog(tk.Toplevel):
    """
    Lists every .md / .txt file under CODEGEN_DIR.
    Returns the selected full path via self.result (set before destroy).
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.result   = None
        self.title("Select Instruction File")
        self.geometry("480x440")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.grab_set()
        self.lift()
        self._build()
        self._scan()

    def _build(self):
        tk.Frame(self, bg=ACCENT, height=3).pack(fill=tk.X)
        hdr = tk.Frame(self, bg=PANEL)
        hdr.pack(fill=tk.X)
        lbl(hdr, "📄  Select File", fg=ACCENT, font=FONT_TITLE, bg=PANEL
            ).pack(side=tk.LEFT, padx=18, pady=12)
        btn(hdr, "✕", self.destroy, CARD, fg=MUTED).pack(
            side=tk.RIGHT, padx=10, pady=8)

        # Search / filter
        sf = tk.Frame(self, bg=BG)
        sf.pack(fill=tk.X, padx=14, pady=(8, 4))
        lbl(sf, "Filter:", fg=MUTED, font=FONT_SMALL).pack(side=tk.LEFT, padx=(0,6))
        self._filter_var = tk.StringVar()
        self._filter_var.trace_add("write", lambda *_: self._apply_filter())
        fe = ttk.Entry(sf, textvariable=self._filter_var, width=30)
        fe.pack(side=tk.LEFT)
        attach_edit_menu(fe)
        fe.focus()

        self._dir_lbl = lbl(self, "", fg=MUTED, font=FONT_SMALL)
        self._dir_lbl.pack(anchor="w", padx=14, pady=(0, 2))

        # File list
        lf = tk.Frame(self, bg=BG)
        lf.pack(fill=tk.BOTH, expand=True, padx=14)
        vsb = ttk.Scrollbar(lf)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._lb = tk.Listbox(lf, bg=PANEL, fg=TEXT, font=FONT,
                              selectbackground=ACCENT, bd=0, relief="flat",
                              yscrollcommand=vsb.set, activestyle="none",
                              height=16, cursor="hand2")
        self._lb.pack(fill=tk.BOTH, expand=True)
        vsb.config(command=self._lb.yview)
        self._lb.bind("<Double-1>", lambda _: self._select())
        self._lb.bind("<Return>",   lambda _: self._select())

        # Browse button (fallback)
        foot = tk.Frame(self, bg=PANEL)
        foot.pack(fill=tk.X)
        self._count_lbl = lbl(foot, "", fg=MUTED, font=FONT_SMALL, bg=PANEL)
        self._count_lbl.pack(side=tk.LEFT, padx=14, pady=10)
        btn(foot, "Browse…",  self._browse,  CARD).pack(side=tk.RIGHT, padx=4,  pady=8)
        btn(foot, "Select",   self._select,  HOT ).pack(side=tk.RIGHT, padx=4,  pady=8)
        btn(foot, "Cancel",   self.destroy,  CARD).pack(side=tk.RIGHT, padx=4,  pady=8)

    def _scan(self):
        """Collect all .md and .txt files under CODEGEN_DIR."""
        self._all_files = []   # list of (display_name, full_path)
        base = Path(CODEGEN_DIR)
        self._dir_lbl.config(text=f"  {CODEGEN_DIR}")
        if base.is_dir():
            for ext in ("*.md", "*.txt"):
                for p in sorted(base.rglob(ext)):
                    # Display: relative path without extension
                    try:
                        rel = p.relative_to(base)
                    except ValueError:
                        rel = p
                    name = str(rel.with_suffix(""))
                    self._all_files.append((name, str(p)))
        self._apply_filter()

    def _apply_filter(self):
        q = self._filter_var.get().lower()
        self._lb.delete(0, tk.END)
        self._shown = []
        for name, path in self._all_files:
            if not q or q in name.lower():
                self._lb.insert(tk.END, f"  {name}")
                self._shown.append((name, path))
        n = len(self._shown)
        self._count_lbl.config(text=f"{n} file{'s' if n != 1 else ''}")
        if self._shown:
            self._lb.selection_set(0)

    def _select(self):
        sel = self._lb.curselection()
        if not sel:
            return
        _, path = self._shown[sel[0]]
        self.result = path
        self.destroy()

    def _browse(self):
        """Fallback: open native file picker if needed."""
        p = filedialog.askopenfilename(
            parent=self,
            initialdir=CODEGEN_DIR,
            title="Select instruction file",
            filetypes=[("Markdown", "*.md"), ("Text", "*.txt"), ("All", "*.*")])
        if p:
            self.result = p
            self.destroy()

# ════════════════════════════════════════════════════════════════════════════════
#  Flow  —  data model + persistence
# ════════════════════════════════════════════════════════════════════════════════

FLOW_FILE = Path.home() / ".codegen_manager_flows.json"

class FlowStore:
    """Load / save named flows from disk."""

    @staticmethod
    def load():
        try:
            raw = json.loads(FLOW_FILE.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def save(flows: dict):
        try:
            FLOW_FILE.write_text(json.dumps(flows, indent=2), encoding="utf-8")
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════════════════════
#  FlowCreateDialog  —  create / edit a flow
# ════════════════════════════════════════════════════════════════════════════════

class FlowCreateDialog(tk.Toplevel):
    """
    A flow is a named list of steps.
    Each step has:  label (str), file_path (str|None), extra_text (str)
    """

    def __init__(self, parent, on_saved, edit_name=None):
        super().__init__(parent)
        self.on_saved   = on_saved
        self._edit_name = edit_name
        self._steps     = []          # list of dicts: {label, path, text}
        self._step_frames = []

        flows = FlowStore.load()
        if edit_name and edit_name in flows:
            self._steps = [dict(s) for s in flows[edit_name]]

        title_str = f"Edit Flow: {edit_name}" if edit_name else "Create New Flow"
        self.title(title_str)
        self.geometry("780x640")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.grab_set()
        self.lift()
        self._build()

    # ── UI ───────────────────────────────────────────────────────────────────────

    def _build(self):
        tk.Frame(self, bg=ACCENT, height=3).pack(fill=tk.X)
        hdr = tk.Frame(self, bg=PANEL)
        hdr.pack(fill=tk.X)
        lbl(hdr, "⛓  Flow Builder", fg=ACCENT, font=FONT_TITLE, bg=PANEL
            ).pack(side=tk.LEFT, padx=20, pady=14)
        btn(hdr, "✕", self.destroy, CARD, fg=MUTED).pack(
            side=tk.RIGHT, padx=12, pady=8)

        body = tk.Frame(self, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=18, pady=10)

        # Flow name
        name_row = tk.Frame(body, bg=BG)
        name_row.pack(fill=tk.X, pady=(0, 10))
        lbl(name_row, "Flow Name:", fg=MUTED, font=FONT_SMALL).pack(
            side=tk.LEFT, padx=(0, 8))
        self._name_var = tk.StringVar(value=self._edit_name or "")
        ttk.Entry(name_row, textvariable=self._name_var, width=36).pack(
            side=tk.LEFT)

        # Steps list in a scrollable canvas
        lbl(body, "Steps  (each step is sent as a sequential follow-up resume)",
            fg=MUTED, font=FONT_SMALL).pack(anchor="w", pady=(0, 4))

        canvas_frame = tk.Frame(body, bg=BG)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        self._canvas = tk.Canvas(canvas_frame, bg=BG, bd=0,
                                 highlightthickness=0)
        vsb = ttk.Scrollbar(canvas_frame, orient="vertical",
                            command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._steps_frame = tk.Frame(self._canvas, bg=BG)
        self._cwin = self._canvas.create_window(
            (0, 0), window=self._steps_frame, anchor="nw")
        self._canvas.bind("<Configure>",
            lambda e: self._canvas.itemconfig(self._cwin, width=e.width))
        self._steps_frame.bind("<Configure>",
            lambda e: self._canvas.configure(
                scrollregion=self._canvas.bbox("all")))

        # Render existing steps
        for step in self._steps:
            self._add_step_ui(step)

        # Footer
        foot = tk.Frame(self, bg=PANEL)
        foot.pack(fill=tk.X)
        btn(foot, "＋  Add Step", self._add_step, CARD).pack(
            side=tk.LEFT, padx=(12, 4), pady=10)
        self._msg = lbl(foot, "", fg=MUTED, font=FONT_SMALL, bg=PANEL)
        self._msg.pack(side=tk.LEFT, padx=8)
        btn(foot, "Cancel",    self.destroy,  CARD).pack(
            side=tk.RIGHT, padx=8,  pady=10)
        btn(foot, "💾  Save Flow", self._save, ACCENT).pack(
            side=tk.RIGHT, padx=4,  pady=10)

    # ── Step management ──────────────────────────────────────────────────────────

    def _add_step(self):
        picker = MdPickerDialog(self)
        self.wait_window(picker)
        path = picker.result or ""
        self._add_step_ui({"label": "", "path": path, "text": ""})

    def _add_step_ui(self, step_data):
        idx = len(self._step_frames)
        sf  = tk.Frame(self._steps_frame, bg=CARD, pady=2)
        sf.pack(fill=tk.X, pady=4, padx=2)

        # Step header row
        hrow = tk.Frame(sf, bg=CARD)
        hrow.pack(fill=tk.X, padx=8, pady=(6, 2))
        step_num = lbl(hrow, f"Step {idx + 1}", fg=ACCENT,
                       font=FONT_BOLD, bg=CARD)
        step_num.pack(side=tk.LEFT, padx=(0, 10))

        label_var = tk.StringVar(value=step_data.get("label", ""))
        _label_entry = ttk.Entry(hrow, textvariable=label_var, width=28)
        _label_entry.pack(side=tk.LEFT, padx=(0, 6))
        attach_edit_menu(_label_entry)
        lbl(hrow, "label (optional)", fg=MUTED, font=FONT_SMALL, bg=CARD
            ).pack(side=tk.LEFT)

        # Delete button
        def _remove(f=sf, i=idx):
            f.destroy()
            self._step_frames = [x for x in self._step_frames if x["frame"].winfo_exists()]
            self._renumber()
        btn(hrow, "✕", _remove, CARD, fg=MUTED, pady=2, padx=6).pack(
            side=tk.RIGHT)

        # Up / Down
        def _move_up(f=sf):
            self._move_step(f, -1)
        def _move_down(f=sf):
            self._move_step(f, +1)
        btn(hrow, "↑", _move_up,   CARD, fg=MUTED, pady=2, padx=6).pack(side=tk.RIGHT)
        btn(hrow, "↓", _move_down, CARD, fg=MUTED, pady=2, padx=6).pack(side=tk.RIGHT)

        # ── File section ──────────────────────────────────────────────────────
        file_outer = tk.Frame(sf, bg=PANEL)
        file_outer.pack(fill=tk.X, padx=8, pady=(2, 0))

        frow = tk.Frame(file_outer, bg=PANEL)
        frow.pack(fill=tk.X, padx=6, pady=(6, 2))
        lbl(frow, "📄 File:", fg=MUTED, font=FONT_SMALL, bg=PANEL
            ).pack(side=tk.LEFT, padx=(0, 6))
        path_var   = tk.StringVar(value=step_data.get("path", ""))
        path_entry = ttk.Entry(frow, textvariable=path_var, width=40)
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        attach_edit_menu(path_entry)

        file_status = lbl(frow, "", fg=MUTED, font=FONT_SMALL, bg=PANEL)
        file_status.pack(side=tk.LEFT, padx=4)

        # preview widget (initially hidden)
        prev_frame = tk.Frame(file_outer, bg=PANEL)
        prev_frame.pack(fill=tk.X, padx=6, pady=(0, 4))
        file_prev = scrolledtext.ScrolledText(
            prev_frame, bg="#0e0e22", fg="#88ccff",
            insertbackground=TEXT, font=FONT_MONO,
            height=4, bd=0, wrap=tk.WORD, relief="flat",
            padx=6, pady=4)
        # don't pack yet — shown only after a file is loaded
        file_prev.config(state=tk.DISABLED)

        def _load_file(pv=path_var, fs=file_status, fp=file_prev, pf=prev_frame):
            p = pv.get().strip()
            if not p:
                return
            if not os.path.isfile(p):
                fs.config(text="File not found", fg=C_FAIL)
                pf.pack_forget()
                return
            try:
                content = open(p, encoding="utf-8").read()
                fs.config(
                    text=f"✓ {os.path.basename(p)} ({len(content):,} chars)",
                    fg=GREEN)
                fp.config(state=tk.NORMAL)
                fp.delete("1.0", tk.END)
                fp.insert("1.0",
                    content[:1200] + ("\n…(truncated)" if len(content) > 1200 else ""))
                fp.config(state=tk.DISABLED)
                pf.pack(fill=tk.X)
            except Exception as e:
                fs.config(text=f"Error: {e}", fg=C_FAIL)

        def _browse_step(pv=path_var, load=_load_file, dlg=self):
            p = filedialog.askopenfilename(
                parent=dlg,
                title="Select file for this step",
                filetypes=[("Markdown","*.md"),("Text","*.txt"),("All","*.*")])
            if p:
                pv.set(p)
                load()

        btn(frow, "Browse",       _browse_step, CARD).pack(side=tk.LEFT, padx=2)
        btn(frow, "Load Preview", _load_file,   CARD).pack(side=tk.LEFT, padx=2)

        # Auto-load if path already set
        if step_data.get("path"):
            self.after(50, _load_file)

        # ── Additional text ────────────────────────────────────────────────────
        trow = tk.Frame(sf, bg=CARD)
        trow.pack(fill=tk.X, padx=8, pady=(4, 8))
        lbl(trow, "✏ Additional Text:", fg=MUTED, font=FONT_SMALL, bg=CARD
            ).pack(side=tk.LEFT, anchor="n", padx=(0, 6))
        text_box = scrolledtext.ScrolledText(
            trow, bg=PANEL, fg=TEXT, insertbackground=TEXT,
            font=FONT, height=3, bd=0, wrap=tk.WORD,
            relief="flat", padx=6, pady=4)
        text_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
        attach_edit_menu(text_box)
        if step_data.get("text"):
            text_box.insert("1.0", step_data["text"])

        entry = {"frame": sf, "label": label_var,
                 "path": path_var, "text_box": text_box,
                 "num_lbl": step_num}
        self._step_frames.append(entry)

    def _move_step(self, frame_widget, direction):
        frames = [e["frame"] for e in self._step_frames
                  if e["frame"].winfo_exists()]
        try:
            idx = frames.index(frame_widget)
        except ValueError:
            return
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(frames):
            return
        # Re-pack in new order
        frames.insert(new_idx, frames.pop(idx))
        for f in frames:
            f.pack_forget()
        for f in frames:
            f.pack(fill=tk.X, pady=4, padx=2)
        self._step_frames = [e for f in frames
                             for e in self._step_frames if e["frame"] is f]
        self._renumber()

    def _renumber(self):
        for i, e in enumerate(self._step_frames):
            if e["frame"].winfo_exists():
                e["num_lbl"].config(text=f"Step {i + 1}")

    def _collect_steps(self):
        steps = []
        for e in self._step_frames:
            if not e["frame"].winfo_exists():
                continue
            steps.append({
                "label": e["label"].get().strip(),
                "path":  e["path"].get().strip(),
                "text":  e["text_box"].get("1.0", tk.END).strip(),
            })
        return steps

    def _save(self):
        name = self._name_var.get().strip()
        if not name:
            self._msg.config(text="⚠  Enter a flow name.", fg=C_PEND)
            return
        steps = self._collect_steps()
        if not steps:
            self._msg.config(text="⚠  Add at least one step.", fg=C_PEND)
            return
        for i, s in enumerate(steps):
            if not s["path"] and not s["text"]:
                self._msg.config(
                    text=f"⚠  Step {i+1} has no file or text.", fg=C_PEND)
                return
        flows = FlowStore.load()
        if self._edit_name and self._edit_name != name:
            flows.pop(self._edit_name, None)
        flows[name] = steps
        FlowStore.save(flows)
        self._msg.config(text=f"✅  Saved '{name}'", fg=GREEN)
        self.on_saved()
        self.after(900, self.destroy)


# ════════════════════════════════════════════════════════════════════════════════
#  FlowRunner  —  background sequencer
# ════════════════════════════════════════════════════════════════════════════════

class FlowRunner:
    """
    Monitors a run and, when it completes each step, sends the next resume.
    Runs entirely in a daemon thread; posts UI callbacks via root.after().
    """
    POLL = 12   # seconds between status checks

    def __init__(self, root, run_id, steps, on_status):
        self.root      = root
        self.run_id    = run_id
        self.steps     = list(steps)   # remaining steps (index 0 is next)
        self.on_status = on_status     # callable(msg, colour)
        self._current_run_id = run_id
        self._stop    = False
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._stop = True

    @staticmethod
    def _step_prompt(step):
        parts = []
        path = step.get("path", "")
        if path and os.path.isfile(path):
            try:
                parts.append(open(path, encoding="utf-8").read())
            except Exception:
                pass
        text = step.get("text", "").strip()
        if text:
            parts.append(text)
        return "\n\n".join(parts).strip()

    def _loop(self):
        total = len(self.steps)
        sent  = 0
        self._post(f"Flow started — {total} step(s) queued", C_RUN)

        while not self._stop and self.steps:
            # Poll until current run is done
            while not self._stop:
                time.sleep(self.POLL)
                try:
                    data = API._get(
                        f"/organizations/{ORG_ID}/agent/run/{self._current_run_id}")
                    status = data.get("status") or ""
                    if is_done(status):
                        break
                    self._post(
                        f"Flow [{sent}/{total}] — waiting for #{self._current_run_id}"
                        f" ({status})", MUTED)
                except Exception as e:
                    self._post(f"Flow poll error: {e}", C_FAIL)
                    time.sleep(self.POLL)

            if self._stop:
                break

            # Send next step
            step   = self.steps.pop(0)
            sent  += 1
            prompt = self._step_prompt(step)
            label  = step.get("label") or f"Step {sent}"
            if not prompt:
                self._post(f"Flow: skipping empty step {sent}", MUTED)
                continue

            self._post(f"Flow: sending {label} ({sent}/{total})…", C_PEND)
            try:
                result = API.resume_run(self._current_run_id, prompt)
                self._current_run_id = result.get("id", self._current_run_id)
                self._post(
                    f"Flow: {label} sent → run #{self._current_run_id}", C_RUN)
            except Exception as e:
                self._post(f"Flow error on {label}: {e}", C_FAIL)
                break

        if not self._stop:
            self._post(f"✅  Flow complete — all {total} step(s) sent", GREEN)

    def _post(self, msg, colour):
        self.root.after(0, lambda m=msg, c=colour: self.on_status(m, c))



# ════════════════════════════════════════════════════════════════════════════════
#  FlowViewDialog  —  read-only preview of a single flow's steps
# ════════════════════════════════════════════════════════════════════════════════

class FlowViewDialog(tk.Toplevel):
    """Shows a flow's steps in read-only form with file preview."""

    def __init__(self, parent, name, steps, on_edit):
        super().__init__(parent)
        self.name    = name
        self.steps   = steps
        self.on_edit = on_edit
        self.title(f"Flow: {name}")
        self.geometry("720x580")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.grab_set()
        self.lift()
        self._build()

    def _build(self):
        tk.Frame(self, bg=ACCENT, height=3).pack(fill=tk.X)
        hdr = tk.Frame(self, bg=PANEL)
        hdr.pack(fill=tk.X)
        lbl(hdr, f"⛓  {self.name}", fg=ACCENT, font=FONT_TITLE, bg=PANEL
            ).pack(side=tk.LEFT, padx=20, pady=14)
        btn(hdr, "✕", self.destroy, CARD, fg=MUTED).pack(
            side=tk.RIGHT, padx=12, pady=8)
        btn(hdr, "✏  Edit", self._edit, HOT).pack(
            side=tk.RIGHT, padx=4, pady=8)

        lbl(self, f"  {len(self.steps)} step(s)  —  double-click a step to preview its file",
            fg=MUTED, font=FONT_SMALL).pack(anchor="w", padx=14, pady=(6, 2))

        # Steps treeview
        tree_f = tk.Frame(self, bg=BG)
        tree_f.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 4))

        cols = ("#", "Label", "File", "Text Preview")
        self._tree = ttk.Treeview(tree_f, columns=cols,
                                  show="headings", selectmode="browse")
        ws = {"#": 36, "Label": 160, "File": 200, "Text Preview": 0}
        for c in cols:
            self._tree.heading(c, text=c)
            self._tree.column(c, width=ws.get(c, 120),
                              anchor="w", stretch=(c == "Text Preview"))
        vsb = ttk.Scrollbar(tree_f, orient=tk.VERTICAL,
                            command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._tree.tag_configure("has_file", foreground=C_DONE)
        self._tree.tag_configure("text_only", foreground=TEXT)

        for i, s in enumerate(self.steps):
            path    = s.get("path", "") or ""
            fname   = os.path.basename(path) if path else "—"
            text    = (s.get("text") or "").replace("\n", " ")[:80]
            label   = s.get("label") or f"Step {i+1}"
            tag     = "has_file" if path and os.path.isfile(path) else "text_only"
            self._tree.insert("", tk.END, iid=str(i),
                              values=(i + 1, label, fname, text), tags=(tag,))

        self._tree.bind("<Double-1>", self._preview_step)

        # Preview pane
        lbl(self, "  File Preview", fg=MUTED, font=FONT_SMALL
            ).pack(anchor="w", padx=14, pady=(2, 1))
        self._preview = scrolledtext.ScrolledText(
            self, bg=PANEL, fg="#88ccff", insertbackground=TEXT,
            font=FONT_MONO, height=8, bd=0, wrap=tk.WORD,
            relief="flat", padx=10, pady=6)
        self._preview.pack(fill=tk.X, padx=14, pady=(0, 4))
        self._preview.insert("1.0", "Select a step above to preview its file content.")
        self._preview.config(state=tk.DISABLED)

        foot = tk.Frame(self, bg=PANEL)
        foot.pack(fill=tk.X)
        btn(foot, "Close", self.destroy, CARD).pack(
            side=tk.RIGHT, padx=12, pady=8)

    def _preview_step(self, _event=None):
        sel = self._tree.selection()
        if not sel:
            return
        idx  = int(sel[0])
        step = self.steps[idx]
        path = step.get("path", "") or ""
        self._preview.config(state=tk.NORMAL)
        self._preview.delete("1.0", tk.END)
        if path and os.path.isfile(path):
            try:
                content = open(path, encoding="utf-8").read()
                self._preview.insert("1.0", content[:3000] +
                                     ("\n…(truncated)" if len(content) > 3000 else ""))
            except Exception as e:
                self._preview.insert("1.0", f"Could not read file: {e}")
        elif path:
            self._preview.insert("1.0", f"File not found:\n{path}")
        else:
            text = step.get("text", "") or "(no text)"
            self._preview.insert("1.0", text[:3000])
        self._preview.config(state=tk.DISABLED)

    def _edit(self):
        self.destroy()
        self.on_edit()


# ════════════════════════════════════════════════════════════════════════════════
#  FlowManagerDialog  —  list / edit / delete flows
# ════════════════════════════════════════════════════════════════════════════════

class FlowManagerDialog(tk.Toplevel):
    def __init__(self, parent, on_changed=None):
        super().__init__(parent)
        self.on_changed = on_changed
        self.title("Flows")
        self.geometry("620x500")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.grab_set()
        self.lift()
        self._flows = {}
        self._build()
        self._reload()

    def _build(self):
        tk.Frame(self, bg=ACCENT, height=3).pack(fill=tk.X)

        # Header
        hdr = tk.Frame(self, bg=PANEL)
        hdr.pack(fill=tk.X)
        lbl(hdr, "⛓  Flows", fg=ACCENT, font=FONT_TITLE, bg=PANEL
            ).pack(side=tk.LEFT, padx=20, pady=14)
        btn(hdr, "✕", self.destroy, CARD, fg=MUTED).pack(
            side=tk.RIGHT, padx=12, pady=8)

        # Sub-toolbar
        tb = tk.Frame(self, bg=PANEL)
        tb.pack(fill=tk.X)
        btn(tb, "＋  New Flow",  self._new,    HOT  ).pack(side=tk.LEFT, padx=(12,4), pady=8)
        btn(tb, "✏  Edit",       self._edit,   CARD ).pack(side=tk.LEFT, padx=4,     pady=8)
        btn(tb, "🗑  Delete",    self._delete, CARD ).pack(side=tk.LEFT, padx=4,     pady=8)
        self._tb_msg = lbl(tb, "", fg=MUTED, font=FONT_SMALL, bg=PANEL)
        self._tb_msg.pack(side=tk.LEFT, padx=12)

        # Flow list treeview
        tree_f = tk.Frame(self, bg=BG)
        tree_f.pack(fill=tk.BOTH, expand=True, padx=14, pady=10)

        cols = ("Flow Name", "Steps", "Step Labels")
        self._tree = ttk.Treeview(tree_f, columns=cols,
                                  show="headings", selectmode="browse")
        self._tree.heading("Flow Name",   text="Flow Name")
        self._tree.heading("Steps",       text="Steps")
        self._tree.heading("Step Labels", text="Step Labels")
        self._tree.column("Flow Name",   width=180, anchor="w")
        self._tree.column("Steps",       width=52,  anchor="center")
        self._tree.column("Step Labels", width=0,   anchor="w", stretch=True)

        vsb = ttk.Scrollbar(tree_f, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._tree.bind("<Double-1>",  lambda _: self._view())
        self._tree.bind("<Return>",    lambda _: self._view())
        self._tree.bind("<Button-3>",  self._ctx)

        # Hint
        lbl(self, "  Double-click to preview  ·  Right-click for options",
            fg=MUTED, font=FONT_SMALL).pack(anchor="w", padx=14, pady=(0, 4))

        # Footer
        foot = tk.Frame(self, bg=PANEL)
        foot.pack(fill=tk.X)
        btn(foot, "Close", self.destroy, CARD).pack(
            side=tk.RIGHT, padx=12, pady=8)

    def _reload(self):
        for row in self._tree.get_children():
            self._tree.delete(row)
        self._flows = FlowStore.load()
        for name, steps in self._flows.items():
            labels = ", ".join(
                s.get("label") or f"Step {i+1}"
                for i, s in enumerate(steps))
            self._tree.insert("", tk.END, iid=name,
                              values=(name, len(steps), labels))
        count = len(self._flows)
        self._tb_msg.config(
            text=f"{count} flow{'s' if count != 1 else ''}")

    def _selected_name(self):
        sel = self._tree.selection()
        return sel[0] if sel else None

    def _view(self):
        name = self._selected_name()
        if not name or name not in self._flows:
            return
        FlowViewDialog(self, name, self._flows[name],
                       on_edit=lambda n=name: self._edit_named(n))

    def _new(self):
        FlowCreateDialog(self, on_saved=self._on_saved)

    def _edit(self):
        name = self._selected_name()
        if name:
            self._edit_named(name)
        else:
            self._tb_msg.config(text="Select a flow first", fg=C_PEND)

    def _edit_named(self, name):
        FlowCreateDialog(self, on_saved=self._on_saved, edit_name=name)

    def _delete(self):
        name = self._selected_name()
        if not name:
            self._tb_msg.config(text="Select a flow first", fg=C_PEND)
            return
        if messagebox.askyesno("Delete Flow",
                               f'Delete flow "{name}"?',
                               parent=self):
            flows = FlowStore.load()
            flows.pop(name, None)
            FlowStore.save(flows)
            self._on_saved()

    def _ctx(self, event):
        row = self._tree.identify_row(event.y)
        if not row:
            return
        self._tree.selection_set(row)
        m = tk.Menu(self, tearoff=0, bg=CARD, fg=TEXT,
                    activebackground=ACCENT, activeforeground="white",
                    font=FONT, bd=0)
        m.add_command(label="🔍  Preview",   command=self._view)
        m.add_command(label="✏  Edit",       command=self._edit)
        m.add_separator()
        m.add_command(label="🗑  Delete",    command=self._delete)
        m.post(event.x_root, event.y_root)

    def _on_saved(self):
        self._reload()
        if self.on_changed:
            self.on_changed()

# ════════════════════════════════════════════════════════════════════════════════
#  Create Run Dialog
# ════════════════════════════════════════════════════════════════════════════════

class CreateRunDialog(tk.Toplevel):
    def __init__(self, parent, on_created, on_flow_runner=None):
        super().__init__(parent)
        self.on_created    = on_created
        self.on_flow_runner = on_flow_runner  # callback(runner) when flow starts
        self._tpl_text     = None
        self.title("New Agent Run")
        self.geometry("760x600")
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

        lbl(body, "Template File  (optional)", fg=MUTED, font=FONT_SMALL
            ).pack(anchor="w", pady=(0, 3))
        tr = tk.Frame(body, bg=BG)
        tr.pack(fill=tk.X)
        self._tpl_var = tk.StringVar(value=DEFAULT_TPL)
        ttk.Entry(tr, textvariable=self._tpl_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        btn(tr, "Browse", self._browse, CARD).pack(side=tk.LEFT, padx=2)
        btn(tr, "Load",   self._load,   ACCENT).pack(side=tk.LEFT, padx=2)

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

        # ── Flow selector ────────────────────────────────────────────────────
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
        btn(foot, "Cancel",        self.destroy,  CARD).pack(
            side=tk.RIGHT, padx=8,  pady=10)
        btn(foot, "🚀  Launch Run", self._launch, HOT).pack(
            side=tk.RIGHT, padx=4,  pady=10)

    def _browse(self):
        p = filedialog.askopenfilename(
            filetypes=[("Markdown","*.md"),("Text","*.txt"),("All","*.*")])
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
        steps = flows.get(name, [])
        self._flow_info.config(
            text=f"{len(steps)} step(s)", fg=ACCENT)

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
            msg += f"  ⛓ flow ({len(flow)} steps) queued"
        self._foot_msg.config(text=msg, fg=GREEN)
        self.on_created(res)
        if flow and self.on_flow_runner:
            self.on_flow_runner(rid, flow)
        self.after(1400, self.destroy)


# ════════════════════════════════════════════════════════════════════════════════
#  Run Detail / Conversation Dialog
# ════════════════════════════════════════════════════════════════════════════════

class RunDialog(tk.Toplevel):
    def __init__(self, parent, run, on_refreshed, on_start_flow=None):
        super().__init__(parent)
        self.run         = run
        self.on_refreshed = on_refreshed
        self.on_start_flow = on_start_flow
        rid    = run["id"]
        status = run.get("status", "")
        self.title(f"Run #{rid}  ·  {status}")
        self.geometry("900x700")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.grab_set()
        self.lift()
        self._build(status)
        self._load_logs()

    def _build(self, status):
        sc = status_color(status)

        # Coloured accent bar
        tk.Frame(self, bg=sc, height=3).pack(fill=tk.X)

        # Header
        hdr = tk.Frame(self, bg=PANEL)
        hdr.pack(fill=tk.X)

        lh = tk.Frame(hdr, bg=PANEL)
        lh.pack(side=tk.LEFT, fill=tk.X, expand=True)
        lbl(lh, f"Run #{self.run['id']}", fg=TEXT, font=FONT_TITLE, bg=PANEL
            ).pack(side=tk.LEFT, padx=18, pady=(12, 4))
        lbl(lh, (status or "").upper(), fg=sc, font=FONT_BOLD, bg=PANEL
            ).pack(side=tk.LEFT, padx=6)

        rh = tk.Frame(hdr, bg=PANEL)
        rh.pack(side=tk.RIGHT)
        if self.run.get("web_url"):
            btn(rh, "🌐 Web", lambda: webbrowser.open(self.run["web_url"]),
                CARD).pack(side=tk.LEFT, padx=4, pady=8)
        btn(rh, "✕", self.destroy, CARD, fg=MUTED).pack(
            side=tk.LEFT, padx=10, pady=8)

        # Meta
        meta = tk.Frame(hdr, bg=PANEL)
        meta.pack(fill=tk.X, padx=18, pady=(0, 10))
        lbl(meta, fmt_dt(self.run.get("created_at")),
            fg=MUTED, font=FONT_SMALL, bg=PANEL).pack(side=tk.LEFT)
        for pr in (self.run.get("github_pull_requests") or [])[:4]:
            lk = tk.Label(meta, text=f"  🔗 PR #{pr['id']}",
                          fg=ACCENT, font=FONT_SMALL, bg=PANEL, cursor="hand2")
            lk.pack(side=tk.LEFT)
            lk.bind("<Button-1>",
                    lambda e, u=pr.get("url",""): webbrowser.open(u))

        # Summary / result strip
        summary = (self.run.get("summary") or self.run.get("result") or "").strip()
        if summary:
            sf = tk.Frame(self, bg=CARD)
            sf.pack(fill=tk.X, padx=14, pady=(4, 0))
            lbl(sf, "Summary", fg=MUTED, font=FONT_SMALL, bg=CARD
                ).pack(anchor="w", padx=12, pady=(6, 1))
            st = tk.Text(sf, bg=CARD, fg=TEXT, font=FONT_SMALL,
                         height=3, bd=0, wrap=tk.WORD, relief="flat",
                         padx=10, pady=4)
            st.pack(fill=tk.X, padx=10, pady=(0, 8))
            st.insert("1.0", summary)
            st.config(state=tk.DISABLED)

        # Conversation view
        lbl(self, "  Conversation Log", fg=MUTED, font=FONT_SMALL
            ).pack(anchor="w", padx=14, pady=(8, 2))

        self._conv = scrolledtext.ScrolledText(
            self, bg=PANEL, fg=TEXT, insertbackground=TEXT,
            font=FONT_MONO, bd=0, wrap=tk.WORD, relief="flat",
            padx=12, pady=10)
        self._conv.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 4))
        self._conv.tag_configure("ts",      foreground=MUTED,    font=FONT_SMALL)
        self._conv.tag_configure("tool",    foreground="#88aaff", font=("Consolas",9,"bold"))
        self._conv.tag_configure("thought", foreground="#c0a0ff")
        self._conv.tag_configure("inp",     foreground="#80d8c0")
        self._conv.tag_configure("out",     foreground=TEXT)
        self._conv.tag_configure("div",     foreground=BORDER)
        self._conv.insert(tk.END, "Loading logs…", "ts")
        self._conv.config(state=tk.DISABLED)

        # Resume panel — shown for all done runs
        if is_done(status):
            rf = tk.Frame(self, bg=CARD)
            rf.pack(fill=tk.X, padx=14, pady=(2, 4))
            tk.Frame(rf, bg=BORDER, height=1).pack(fill=tk.X)

            # --- Single prompt resume (existing) ---
            lbl(rf, "  Follow‑up prompt (single message)",
                fg=MUTED, font=FONT_SMALL, bg=CARD
                ).pack(anchor="w", padx=10, pady=(8, 3))
            row = tk.Frame(rf, bg=CARD)
            row.pack(fill=tk.X, padx=10, pady=(0, 10))
            self._resume_box = scrolledtext.ScrolledText(
                row, bg=PANEL, fg=TEXT, insertbackground=TEXT,
                font=FONT, height=4, bd=0, wrap=tk.WORD,
                relief="flat", padx=8, pady=6)
            self._resume_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            self._resume_box.focus()
            sb = tk.Frame(row, bg=CARD)
            sb.pack(side=tk.LEFT, padx=(8, 0), fill=tk.Y)
            btn(sb, "▶  Send", self._resume, HOT).pack(fill=tk.X, pady=2)
            self._res_msg = lbl(sb, "", fg=MUTED, font=FONT_SMALL, bg=CARD)
            self._res_msg.pack(pady=2)
            self._resume_box.bind("<Control-Return>", lambda _: self._resume())

            # ⭐ NEW: Flow resume section
            tk.Frame(rf, bg=BORDER, height=1).pack(fill=tk.X, padx=10, pady=(8, 4))
            flow_row = tk.Frame(rf, bg=CARD)
            flow_row.pack(fill=tk.X, padx=10, pady=(0, 10))

            lbl(flow_row, "⛓  Run a flow instead:",
                fg=MUTED, font=FONT_SMALL, bg=CARD
                ).pack(anchor="w", padx=0, pady=(0, 4))

            flow_sel_row = tk.Frame(flow_row, bg=CARD)
            flow_sel_row.pack(fill=tk.X)
            lbl(flow_sel_row, "Flow:", fg=MUTED, font=FONT_SMALL, bg=CARD
                ).pack(side=tk.LEFT, padx=(0, 6))
            self._flow_var = tk.StringVar(value="None")
            self._flow_combo = ttk.Combobox(
                flow_sel_row, textvariable=self._flow_var,
                width=26, state="readonly")
            self._flow_combo.pack(side=tk.LEFT, padx=(0, 6))
            self._flow_combo.bind("<<ComboboxSelected>>", self._on_flow_selected)
            btn(flow_sel_row, "Manage Flows", self._open_flow_manager,
                CARD).pack(side=tk.LEFT, padx=2)
            self._flow_info = lbl(flow_sel_row, "", fg=MUTED, font=FONT_SMALL, bg=CARD)
            self._flow_info.pack(side=tk.LEFT, padx=8)

            run_flow_btn = btn(flow_sel_row, "▶  Run Flow", self._run_flow, ACCENT)
            run_flow_btn.pack(side=tk.LEFT, padx=4)

            self._refresh_flow_combo()
        else:
            self._resume_box = None
            self._flow_combo = None

        # Footer
        foot = tk.Frame(self, bg=PANEL)
        foot.pack(fill=tk.X)
        self._log_lbl = lbl(foot, "", fg=MUTED, font=FONT_SMALL, bg=PANEL)
        self._log_lbl.pack(side=tk.LEFT, padx=16, pady=8)
        btn(foot, "Close", self.destroy, CARD).pack(
            side=tk.RIGHT, padx=12, pady=8)

    # ── Logs ────────────────────────────────────────────────────────────────────

    def _load_logs(self):
        rid = self.run["id"]
        def _bg():
            try:
                data = API.fetch_all_logs(rid)
                self.after(0, lambda d=data: self._render(d))
            except Exception as e:
                self.after(0, lambda: self._render_err(str(e)))
        threading.Thread(target=_bg, daemon=True).start()

    def _render_err(self, msg):
        """Display an error message in the conversation pane."""
        if not self._conv.winfo_exists():
            return
        self._conv.config(state=tk.NORMAL)
        self._conv.delete("1.0", tk.END)
        self._conv.insert(tk.END, f"⚠  {msg}", "ts")
        self._conv.config(state=tk.DISABLED)

    def _render(self, data):
        """Render the logs in the conversation text widget."""
        if not self._conv.winfo_exists():
            return
        logs = (data or {}).get("logs", [])
        self._conv.config(state=tk.NORMAL)
        self._conv.delete("1.0", tk.END)

        if not logs:
            self._conv.insert(tk.END, "(No log entries found)\n", "ts")
        else:
            for lg in logs:
                ts      = fmt_dt(lg.get("created_at"))
                tool    = lg.get("tool_name") or ""
                mtype   = lg.get("message_type") or ""
                thought = (lg.get("thought") or "").strip()
                inp     = lg.get("tool_input")
                out     = lg.get("tool_output")
                obs     = lg.get("observation")

                # timestamp + tool header
                self._conv.insert(tk.END, f"[{ts}]  ", "ts")
                if tool:
                    self._conv.insert(tk.END, f"⚙ {tool}", "tool")
                if mtype:
                    self._conv.insert(tk.END, f"  ({mtype})", "ts")
                self._conv.insert(tk.END, "\n")

                if thought:
                    preview = thought[:400] + ("…" if len(thought) > 400 else "")
                    self._conv.insert(tk.END, f"  💭 {preview}\n", "thought")
                if inp:
                    raw = json.dumps(inp, indent=2) if isinstance(inp, (dict,list)) else str(inp)
                    preview = raw[:500] + ("…" if len(raw) > 500 else "")
                    self._conv.insert(tk.END, f"  ▸ {preview}\n", "inp")
                if out:
                    raw = json.dumps(out, indent=2) if isinstance(out, (dict,list)) else str(out)
                    preview = raw[:500] + ("…" if len(raw) > 500 else "")
                    self._conv.insert(tk.END, f"  ◂ {preview}\n", "out")
                if obs and obs not in (inp, out):
                    raw = json.dumps(obs, indent=2) if isinstance(obs, (dict,list)) else str(obs)
                    self._conv.insert(tk.END,
                        f"  👁 {raw[:200]}{'…' if len(raw)>200 else ''}\n", "ts")

                self._conv.insert(tk.END, "─" * 66 + "\n", "div")

            self._conv.see(tk.END)

        self._conv.config(state=tk.DISABLED)
        self._log_lbl.config(text=f"{len(logs)} log entries")

    # ── Resume ──────────────────────────────────────────────────────────────────

    def _resume(self):
        if not self._resume_box:
            return
        prompt = self._resume_box.get("1.0", tk.END).strip()
        if not prompt:
            self._res_msg.config(text="Enter a prompt", fg=C_PEND)
            return
        self._res_msg.config(text="Sending…", fg=C_PEND)

        rid = self.run["id"]
        def _bg():
            try:
                res = API.resume_run(rid, prompt)
                new_id = res.get("id", rid)
                self.after(0, lambda: self._resumed(new_id))
            except Exception as e:
                self.after(0, lambda: self._res_msg.config(
                    text=f"Error: {e}", fg=C_FAIL))

        threading.Thread(target=_bg, daemon=True).start()

    def _resumed(self, new_id):
        self._res_msg.config(text=f"✅ #{new_id} resumed!", fg=GREEN)
        self.on_refreshed()
        self.after(1500, self.destroy)


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
        steps = flows.get(name, [])
        self._flow_info.config(text=f"{len(steps)} step(s)", fg=ACCENT)

    def _open_flow_manager(self):
        FlowManagerDialog(self, on_changed=self._refresh_flow_combo)

    def _run_flow(self):
        """Start a flow runner for the selected flow."""
        if not self.on_start_flow:
            self._res_msg.config(text="Flow runner not available", fg=C_FAIL)
            return
        name = self._flow_var.get()
        if name == "None":
            self._res_msg.config(text="Select a flow", fg=C_PEND)
            return
        flows = FlowStore.load()
        steps = flows.get(name)
        if not steps:
            self._res_msg.config(text="Flow not found", fg=C_FAIL)
            return
        # Call the main app to start the flow runner
        self.on_start_flow(self.run["id"], steps)
        self._res_msg.config(text=f"✅ Flow '{name}' started", fg=GREEN)
        self.after(1200, self.destroy)

# ════════════════════════════════════════════════════════════════════════════════
#  Main Application
# ════════════════════════════════════════════════════════════════════════════════

class CodegenManager:
    def __init__(self, root: tk.Tk):
        self.root           = root
        self.root.title("Codegen Agent Manager")
        self.root.geometry("1240x760")
        self.root.minsize(900, 580)
        self.root.configure(bg=BG)

        self._runs          = []
        self._prev_statuses = {}
        self._polling       = True
        self._sort_col      = "Created At"
        self._sort_rev      = True
        self._star_file     = Path.home() / ".codegen_manager_stars.json"
        self._starred       = self._load_stars()
        self._flow_runners  = {}   # run_id -> FlowRunner

        self._style()
        self._build()
        threading.Thread(target=self._poll_loop, daemon=True).start()
        self.root.after(300, self._refresh)

    # ── Styles ──────────────────────────────────────────────────────────────────

    def _style(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=TEXT, font=FONT, borderwidth=0)
        s.configure("TFrame", background=BG)
        s.configure("TScrollbar", background=CARD, troughcolor=BG, arrowcolor=MUTED)
        s.configure("Treeview", background=PANEL, foreground=TEXT,
                    fieldbackground=PANEL, rowheight=34)
        s.configure("Treeview.Heading", background=CARD, foreground=MUTED,
                    font=("Segoe UI", 9, "bold"), relief="flat")
        s.map("Treeview",
              background=[("selected", ACCENT)],
              foreground=[("selected", "white")])
        s.configure("TCombobox", fieldbackground=PANEL, background=PANEL,
                    foreground=TEXT, selectbackground=ACCENT, arrowcolor=MUTED)
        s.configure("TEntry", fieldbackground=PANEL, foreground=TEXT,
                    insertcolor=TEXT)

    # ── Build ────────────────────────────────────────────────────────────────────

    def _build(self):
        self._topbar()
        self._toolbar()
        self._split_tables()
        self._flow_statusbar()
        self._statusbar()

    def _topbar(self):
        bar = tk.Frame(self.root, bg=PANEL, height=56)
        bar.pack(fill=tk.X)
        bar.pack_propagate(False)
        tk.Frame(bar, bg=ACCENT, width=4).pack(side=tk.LEFT, fill=tk.Y)
        lbl(bar, "⚡  Codegen Agent Manager", fg=HOT, font=FONT_TITLE,
            bg=PANEL).pack(side=tk.LEFT, padx=18)

        # right side
        self._last_upd = lbl(bar, "", fg=MUTED, font=FONT_SMALL, bg=PANEL)
        self._last_upd.pack(side=tk.RIGHT, padx=16)
        lbl(bar, "● LIVE", fg=GREEN, font=FONT_SMALL, bg=PANEL
            ).pack(side=tk.RIGHT, padx=4)

        # Active-runs badge  ── hover → dropdown, click item → RunDialog
        tk.Frame(bar, bg=BORDER, width=1).pack(
            side=tk.RIGHT, fill=tk.Y, pady=10, padx=8)
        badge_frame = tk.Frame(bar, bg=PANEL)
        badge_frame.pack(side=tk.RIGHT, padx=4)
        lbl(badge_frame, "ACTIVE", fg=MUTED, font=FONT_SMALL, bg=PANEL
            ).pack(side=tk.LEFT, padx=(0, 4))
        self._active_badge = tk.Label(
            badge_frame, text="—", bg="#0d2a1a", fg=C_RUN,
            font=("Segoe UI", 13, "bold"), padx=10, pady=4,
            cursor="hand2", relief="flat")
        self._active_badge.pack(side=tk.LEFT)
        self._active_badge.bind("<Enter>",   self._badge_hover)
        self._active_badge.bind("<Leave>",   self._badge_leave)
        self._active_badge.bind("<Button-1>", self._badge_click)
        self._dropdown_win = None

    def _update_active_badge(self, runs):
        active_runs = [r for r in runs if is_active(r.get("status"))]
        self._active_runs = active_runs
        count = len(active_runs)
        self._active_badge.config(
            text=str(count) if count else "0",
            bg="#0d2a1a" if count else CARD,
            fg=C_RUN if count else MUTED)

    # ── Active-runs dropdown ─────────────────────────────────────────────────────

    def _badge_hover(self, event):
        self._dropdown_show()

    def _badge_leave(self, event):
        # Only hide if mouse didn't move into the dropdown window
        self.root.after(200, self._maybe_hide_dropdown)

    def _badge_click(self, event):
        if self._dropdown_win and self._dropdown_win.winfo_exists():
            self._dropdown_hide()
        else:
            self._dropdown_show()

    def _dropdown_show(self):
        if self._dropdown_win and self._dropdown_win.winfo_exists():
            return
        active = getattr(self, "_active_runs", [])

        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=BORDER)
        self._dropdown_win = win

        # Position below badge
        self._active_badge.update_idletasks()
        bx = self._active_badge.winfo_rootx()
        by = self._active_badge.winfo_rooty() + self._active_badge.winfo_height() + 2
        win.geometry(f"+{bx}+{by}")

        inner = tk.Frame(win, bg=CARD, padx=1, pady=1)
        inner.pack(fill=tk.BOTH, expand=True)

        if not active:
            lbl(inner, "  No active runs  ", fg=MUTED, font=FONT_SMALL, bg=CARD
                ).pack(pady=10, padx=10)
        else:
            lbl(inner, f"  {len(active)} active run(s) — click to inspect",
                fg=MUTED, font=FONT_SMALL, bg=CARD
                ).pack(anchor="w", padx=10, pady=(8, 4))
            tk.Frame(inner, bg=BORDER, height=1).pack(fill=tk.X, padx=8)
            for run in active:
                rid  = run["id"]
                stat = run.get("status") or ""
                ts   = fmt_dt(run.get("created_at"))
                summ = (run.get("summary") or run.get("result") or "(no summary)")
                summ = summ.replace("\n", " ")[:60]
                row  = tk.Frame(inner, bg=CARD, cursor="hand2")
                row.pack(fill=tk.X, padx=0)
                tk.Frame(row, bg=CARD, height=1).pack(fill=tk.X)
                ri = tk.Frame(row, bg=CARD)
                ri.pack(fill=tk.X, padx=12, pady=6)
                lbl(ri, f"#{rid}", fg=C_RUN, font=FONT_BOLD, bg=CARD
                    ).pack(side=tk.LEFT, padx=(0, 8))
                lbl(ri, stat, fg=C_RUN, font=FONT_SMALL, bg=CARD
                    ).pack(side=tk.LEFT, padx=(0, 10))
                lbl(ri, ts, fg=MUTED, font=FONT_SMALL, bg=CARD
                    ).pack(side=tk.LEFT, padx=(0, 10))
                lbl(ri, summ + "…", fg=TEXT, font=FONT_SMALL, bg=CARD
                    ).pack(side=tk.LEFT)

                def _on_enter(e, r=row):  r.config(bg="#1e2a3a"); [c.config(bg="#1e2a3a") for c in r.winfo_children() + [w for c in r.winfo_children() for w in (c.winfo_children() if hasattr(c,"winfo_children") else [])]]
                def _on_leave(e, r=row):  r.config(bg=CARD); [c.config(bg=CARD) for c in r.winfo_children() + [w for c in r.winfo_children() for w in (c.winfo_children() if hasattr(c,"winfo_children") else [])]]
                def _on_click(e, run=run): self._dropdown_hide(); self._open_run_by(run)
                for w in [row, ri] + ri.winfo_children():
                    w.bind("<Enter>",   _on_enter)
                    w.bind("<Leave>",   _on_leave)
                    w.bind("<Button-1>", _on_click)

        tk.Frame(inner, bg=BORDER, height=1).pack(fill=tk.X, padx=8)
        lbl(inner, "  Click to open logs & resume", fg=MUTED, font=FONT_SMALL, bg=CARD
            ).pack(anchor="w", padx=10, pady=(4, 8))

        win.bind("<Leave>", lambda e: self.root.after(250, self._maybe_hide_dropdown))
        win.update_idletasks()
        # Clamp to screen
        sw = self.root.winfo_screenwidth()
        ww = win.winfo_width()
        if bx + ww > sw:
            bx = sw - ww - 10
        win.geometry(f"+{bx}+{by}")

    def _dropdown_hide(self):
        if self._dropdown_win and self._dropdown_win.winfo_exists():
            self._dropdown_win.destroy()
        self._dropdown_win = None

    def _maybe_hide_dropdown(self):
        if not self._dropdown_win or not self._dropdown_win.winfo_exists():
            return
        # Check if mouse is over badge or dropdown
        x, y = self.root.winfo_pointerx(), self.root.winfo_pointery()
        try:
            wx = self._dropdown_win.winfo_rootx()
            wy = self._dropdown_win.winfo_rooty()
            ww = self._dropdown_win.winfo_width()
            wh = self._dropdown_win.winfo_height()
            bx = self._active_badge.winfo_rootx()
            by = self._active_badge.winfo_rooty()
            bw = self._active_badge.winfo_width()
            bh = self._active_badge.winfo_height()
            over_win   = wx <= x <= wx+ww and wy <= y <= wy+wh
            over_badge = bx <= x <= bx+bw and by <= y <= by+bh
            if not over_win and not over_badge:
                self._dropdown_hide()
        except Exception:
            self._dropdown_hide()

    def _toolbar(self):
        tb = tk.Frame(self.root, bg=PANEL)
        tb.pack(fill=tk.X, padx=14, pady=(0, 6))
        btn(tb, "＋  New Run",  self._open_create,     HOT   ).pack(
            side=tk.LEFT, padx=(8, 4), pady=8)
        btn(tb, "⛓  Flows",    self._open_flows,      CARD  ).pack(
            side=tk.LEFT, padx=4, pady=8)
        btn(tb, "⟳  Refresh",  self._refresh,         ACCENT).pack(
            side=tk.LEFT, padx=4, pady=8)

        tk.Frame(tb, bg=BORDER, width=1).pack(
            side=tk.LEFT, fill=tk.Y, pady=8, padx=10)

        lbl(tb, "Status:", fg=MUTED, font=FONT_SMALL, bg=PANEL).pack(
            side=tk.LEFT)
        self._filt = ttk.Combobox(
            tb, values=["All","ACTIVE","COMPLETE","FAILED"],
            width=11, state="readonly")
        self._filt.set("All")
        self._filt.pack(side=tk.LEFT, padx=6)
        self._filt.bind("<<ComboboxSelected>>", lambda _: self._repopulate())

        lbl(tb, "  Search:", fg=MUTED, font=FONT_SMALL, bg=PANEL).pack(
            side=tk.LEFT)
        self._svar = tk.StringVar()
        self._svar.trace_add("write", lambda *_: self._repopulate())
        ttk.Entry(tb, textvariable=self._svar, width=24).pack(
            side=tk.LEFT, padx=6)

        self._cnt_lbl = lbl(tb, "", fg=MUTED, font=FONT_SMALL, bg=PANEL)
        self._cnt_lbl.pack(side=tk.RIGHT, padx=16)

    def _make_tree(self, parent):
        """Build a styled Treeview with scrollbars inside parent frame."""
        cols    = ("★", "ID", "Status", "Created At", "Summary", "PRs", "Source")
        widths  = {"★": 28, "ID": 68, "Status": 112, "Created At": 162,
                   "Summary": 0, "PRs": 38, "Source": 90}
        anchors = {"★": "center", "ID": "center", "Status": "center", "PRs": "center"}

        tree = ttk.Treeview(parent, columns=cols, show="headings",
                            selectmode="browse")
        for c in cols:
            tree.heading(c, text=c,
                         command=lambda cc=c: self._sort(cc))
            tree.column(c, width=widths.get(c, 110),
                        anchor=anchors.get(c, "w"),
                        stretch=(c == "Summary"),
                        minwidth=widths.get(c, 40))

        vsb = ttk.Scrollbar(parent, orient=tk.VERTICAL,   command=tree.yview)
        hsb = ttk.Scrollbar(parent, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side=tk.RIGHT,  fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        for tag, bg in (("running",   "#0c2218"), ("completed", "#0b1a33"),
                        ("failed",    "#280b0b"), ("other",     PANEL),
                        ("starred",   "#1e1a08"), ("star_run",  "#0d2218")):
            tree.tag_configure(tag, background=bg)

        tree.bind("<Double-1>", lambda e, t=tree: self._open_from_tree(t))
        tree.bind("<Return>",   lambda e, t=tree: self._open_from_tree(t))
        tree.bind("<Button-3>", self._ctx_menu)
        return tree

    def _split_tables(self):
        pw = tk.PanedWindow(self.root, orient=tk.VERTICAL, bg=BG,
                            sashwidth=6, sashrelief="flat", sashpad=2)
        pw.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 2))

        # ── Top pane: Pinned & Active ────────────────────────────────────────
        top_pane = tk.Frame(pw, bg=BG)
        pw.add(top_pane, height=200, minsize=60)

        top_hdr = tk.Frame(top_pane, bg=PANEL, height=26)
        top_hdr.pack(fill=tk.X)
        top_hdr.pack_propagate(False)
        lbl(top_hdr, "  ★  Pinned & Active", fg="#f0c040",
            font=FONT_BOLD, bg=PANEL).pack(side=tk.LEFT, padx=6)
        self._top_cnt = lbl(top_hdr, "", fg=MUTED, font=FONT_SMALL, bg=PANEL)
        self._top_cnt.pack(side=tk.RIGHT, padx=10)

        top_tree_frame = tk.Frame(top_pane, bg=BG)
        top_tree_frame.pack(fill=tk.BOTH, expand=True)
        self._top_tree = self._make_tree(top_tree_frame)

        # ── Bottom pane: Past Runs ───────────────────────────────────────────
        bot_pane = tk.Frame(pw, bg=BG)
        pw.add(bot_pane, minsize=80)

        bot_hdr = tk.Frame(bot_pane, bg=PANEL, height=26)
        bot_hdr.pack(fill=tk.X)
        bot_hdr.pack_propagate(False)
        lbl(bot_hdr, "  ☰  Past Runs", fg=MUTED,
            font=FONT_BOLD, bg=PANEL).pack(side=tk.LEFT, padx=6)
        self._bot_cnt = lbl(bot_hdr, "", fg=MUTED, font=FONT_SMALL, bg=PANEL)
        self._bot_cnt.pack(side=tk.RIGHT, padx=10)

        bot_tree_frame = tk.Frame(bot_pane, bg=BG)
        bot_tree_frame.pack(fill=tk.BOTH, expand=True)
        self._bot_tree = self._make_tree(bot_tree_frame)

        # Keep a ref so _open_run() still works for backward compat
        self._tree = self._bot_tree

        lbl(self.root, "  Double-click to view logs & resume  ·  Right-click to star/unstar",
            fg=MUTED, font=FONT_SMALL).pack(anchor="w", padx=14)

    def _flow_statusbar(self):
        self._fsb = tk.Frame(self.root, bg="#0d1a0d", height=22)
        self._fsb.pack(fill=tk.X, side=tk.BOTTOM)
        self._fsb.pack_propagate(False)
        self._flow_sv  = tk.StringVar(value="")
        self._flow_clr = C_RUN
        self._flow_msg_lbl = tk.Label(
            self._fsb, textvariable=self._flow_sv,
            fg=C_RUN, font=FONT_SMALL, bg="#0d1a0d")
        self._flow_msg_lbl.pack(side=tk.LEFT, padx=12)
        self._fsb.pack_forget()   # hidden until a flow is active

    def _statusbar(self):
        sb = tk.Frame(self.root, bg=PANEL, height=22)
        sb.pack(fill=tk.X, side=tk.BOTTOM)
        sb.pack_propagate(False)
        self._sv = tk.StringVar(value="Initialising…")
        lbl(sb, "", fg=MUTED, font=FONT_SMALL, bg=PANEL,
            textvariable=self._sv).pack(side=tk.LEFT, padx=12)

    # ── Poll ─────────────────────────────────────────────────────────────────────

    def _poll_loop(self):
        while self._polling:
            time.sleep(POLL_SEC)
            try:
                runs = API.fetch_all_runs()
                self.root.after(0, lambda r=runs: self._apply(r))
            except Exception as e:
                self.root.after(0, lambda msg=str(e): self._sv.set(f"Poll error: {msg}"))

    def _refresh(self):
        self._sv.set("Fetching all runs (paginating)…")
        def _bg():
            try:
                runs = API.fetch_all_runs()
                self.root.after(0, lambda r=runs: self._apply(r))
            except Exception as e:
                self.root.after(0, lambda msg=str(e): self._sv.set(f"Error: {msg}"))
        threading.Thread(target=_bg, daemon=True).start()

    def _apply(self, runs):
        for run in runs:
            rid = run.get("id")
            new = run.get("status") or ""
            old = self._prev_statuses.get(rid)
            if old and old != new and is_active(old) and is_done(new):
                self._notify(f"Run #{rid} finished", f"{old} → {new}")
            self._prev_statuses[rid] = new

        self._runs = runs
        self._update_active_badge(runs)
        self._repopulate()
        now = datetime.now().strftime("%H:%M:%S")
        self._last_upd.config(text=f"Updated {now}")
        self._sv.set(f"Loaded {len(runs)} run(s)  ·  paginated")



    # ── Table ────────────────────────────────────────────────────────────────────

    def _row_values(self, run):
        """Build treeview value tuple for a run."""
        rid     = run["id"]
        s       = run.get("status") or ""
        summary = (run.get("summary") or run.get("result") or "").replace("\n", " ")
        prs     = len(run.get("github_pull_requests") or [])
        star    = "★" if rid in self._starred else ""
        return (star, rid, s, fmt_dt(run.get("created_at")),
                summary[:130], prs or "", run.get("source_type") or "")

    def _row_tag(self, run):
        rid = run["id"]
        s   = run.get("status") or ""
        if rid in self._starred and is_active(s): return "star_run"
        if rid in self._starred:                  return "starred"
        return status_tag(s)

    def _repopulate(self):
        filt  = self._filt.get()
        query = self._svar.get().lower()

        for t in (self._top_tree, self._bot_tree):
            for row in t.get_children():
                t.delete(row)

        top_n = bot_n = 0
        for run in self._runs:
            rid = run["id"]
            s   = run.get("status") or ""
            summary = (run.get("summary") or run.get("result") or "").replace("\n", " ")

            # Apply filter & search (filter only applies to bottom pane)
            if query and query not in str(rid).lower() \
                     and query not in s.lower() \
                     and query not in summary.lower():
                continue

            starred  = rid in self._starred
            active   = is_active(s)
            filt_ok  = (filt == "All" or filt.lower() in s.lower())

            if starred or active:
                # Always shown in top pane regardless of filter
                self._top_tree.insert("", tk.END, iid=f"t_{rid}",
                                      values=self._row_values(run),
                                      tags=(self._row_tag(run),))
                top_n += 1
            
            if not active and filt_ok:
                # Past runs go to bottom — starred ones still appear here too (dimmed)
                self._bot_tree.insert("", tk.END, iid=f"b_{rid}",
                                      values=self._row_values(run),
                                      tags=(self._row_tag(run),))
                bot_n += 1

        self._top_cnt.config(text=f"{top_n} shown")
        self._bot_cnt.config(text=f"{bot_n} shown")
        total = len(self._runs)
        self._cnt_lbl.config(text=f"{top_n + bot_n} / {total}")

    def _sort(self, col):
        if self._sort_col == col:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_col, self._sort_rev = col, False
        key_map = {
            "ID":         lambda r: r.get("id", 0),
            "Status":     lambda r: r.get("status") or "",
            "Created At": lambda r: r.get("created_at") or "",
            "Summary":    lambda r: r.get("summary") or "",
            "PRs":        lambda r: len(r.get("github_pull_requests") or []),
            "Source":     lambda r: r.get("source_type") or "",
        }
        self._runs.sort(key=key_map.get(col, lambda r: ""),
                        reverse=self._sort_rev)
        self._repopulate()

    # ── Dialogs ──────────────────────────────────────────────────────────────────

    def _open_create(self):
        CreateRunDialog(
            self.root,
            on_created=lambda _: self._refresh(),
            on_flow_runner=self._start_flow_runner)

    def _open_flows(self):
        FlowManagerDialog(self.root)

    def _start_flow_runner(self, run_id, steps):
        runner = FlowRunner(
            self.root, run_id, steps,
            on_status=self._on_flow_status)
        self._flow_runners[run_id] = runner
        self._fsb.pack(fill=tk.X, side=tk.BOTTOM)
        self._on_flow_status(
            f"⛓ Flow attached to run #{run_id} — {len(steps)} steps", C_RUN)

    def _on_flow_status(self, msg, colour):
        self._flow_sv.set(f"⛓  {msg}")
        self._flow_msg_lbl.config(fg=colour)
        self._fsb.pack(fill=tk.X, side=tk.BOTTOM)
        # Auto-hide "complete" messages after 8s
        if "complete" in msg.lower() or "✅" in msg:
            self.root.after(8000, self._maybe_hide_flow_bar)

    def _maybe_hide_flow_bar(self):
        if "complete" in self._flow_sv.get().lower() or "✅" in self._flow_sv.get():
            self._fsb.pack_forget()

    def _iid_to_rid(self, iid):
        """Strip t_/b_ prefix and return int run id."""
        return int(str(iid).lstrip("tb_").replace("_",""))

    def _open_from_tree(self, tree):
        sel = tree.selection()
        if not sel:
            return
        try:
            rid = self._iid_to_rid(sel[0])
        except Exception:
            return
        run = next((r for r in self._runs if r["id"] == rid), None)
        if run:
            RunDialog(self.root, run,
                    on_refreshed=self._refresh,
                    on_start_flow=self._start_flow_runner) 

    def _open_run(self):
        # Try both trees
        for tree in (self._top_tree, self._bot_tree):
            sel = tree.selection()
            if sel:
                self._open_from_tree(tree)
                return

    def _open_run_by(self, run):
        RunDialog(self.root, run,
                on_refreshed=self._refresh,
                on_start_flow=self._start_flow_runner)

    def _toggle_star(self, rid):
        if rid in self._starred:
            self._starred.discard(rid)
        else:
            self._starred.add(rid)
        self._save_stars()
        self._repopulate()

    def _load_stars(self):
        try:
            data = json.loads(self._star_file.read_text(encoding="utf-8"))
            return set(data)
        except Exception:
            return set()

    def _save_stars(self):
        try:
            self._star_file.write_text(
                json.dumps(list(self._starred)), encoding="utf-8")
        except Exception:
            pass

    def _ctx_menu(self, event):
        # Figure out which tree was right-clicked
        widget = event.widget
        row = widget.identify_row(event.y)
        if not row:
            return
        widget.selection_set(row)
        try:
            rid = self._iid_to_rid(row)
        except Exception:
            return
        run = next((r for r in self._runs if r["id"] == rid), None)
        if not run:
            return
        starred = rid in self._starred
        star_label = "☆  Remove Star" if starred else "★  Star this Run"
        m = tk.Menu(self.root, tearoff=0, bg=CARD, fg=TEXT,
                    activebackground=ACCENT, activeforeground="white",
                    font=FONT, bd=0)
        m.add_command(label="🔍  View / Resume",
                      command=lambda: self._open_run_by(run))
        m.add_separator()
        m.add_command(label=star_label,
                      command=lambda: self._toggle_star(rid))
        m.add_separator()
        if run.get("web_url"):
            m.add_command(label="🌐  Open in Browser",
                          command=lambda: webbrowser.open(run["web_url"]))
        m.add_command(label="📋  Copy Run ID",
                      command=lambda: (self.root.clipboard_clear(),
                                       self.root.clipboard_append(str(rid)),
                                       self._sv.set(f"Copied #{rid}")))
        m.post(event.x_root, event.y_root)

    # ── Notifications ────────────────────────────────────────────────────────────

    def _notify(self, title, message):
        try:
            from plyer import notification
            notification.notify(title=title, message=message,
                                app_name="Codegen Manager", timeout=6)
        except Exception:
            pass
        self.root.after(0, lambda: self._toast(title, message))

    def _toast(self, title, msg):
        t = tk.Toplevel(self.root)
        t.overrideredirect(True)
        t.attributes("-topmost", True)
        t.configure(bg=ACCENT)
        inner = tk.Frame(t, bg=CARD)
        inner.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        lbl(inner, f"🔔  {title}", fg=HOT, font=FONT_BOLD, bg=CARD
            ).pack(anchor="w", padx=14, pady=(10, 2))
        lbl(inner, msg, fg=TEXT, font=FONT, bg=CARD
            ).pack(anchor="w", padx=14, pady=(0, 10))
        t.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        t.geometry(f"340x74+{sw-356}+{sh-110}")
        t.after(5000, t.destroy)


# ════════════════════════════════════════════════════════════════════════════════
#  Entry point
# ════════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import subprocess, sys
    for pkg in ("requests", "plyer"):
        try:
            __import__(pkg)
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip",
                                   "install", pkg, "-q"])
    root = tk.Tk()
    try:
        root.iconbitmap(default="")
    except Exception:
        pass
    CodegenManager(root)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass