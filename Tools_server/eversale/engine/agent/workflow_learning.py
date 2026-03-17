import json
import hashlib
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Optional
from datetime import datetime

@dataclass
class WorkflowStep:
    action: str  # "navigate", "fill", "click", "extract"
    selector: str
    value: Optional[str] = None
    description: str = ""

@dataclass
class LearnedWorkflow:
    id: str
    site_pattern: str  # e.g., "*.shopify.com", "login page"
    task_type: str  # "checkout", "login", "search"
    steps: List[WorkflowStep]
    success_count: int = 0
    fail_count: int = 0
    last_used: str = ""

class WorkflowLearner:
    def __init__(self, storage_path: str = "~/.eversale/learned_workflows.json"):
        self.storage_path = Path(storage_path).expanduser()
        self.workflows: List[LearnedWorkflow] = []
        self._load()

    def _load(self):
        if self.storage_path.exists():
            data = json.loads(self.storage_path.read_text())
            self.workflows = [LearnedWorkflow(**w) for w in data]

    def _save(self):
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = [asdict(w) for w in self.workflows]
        self.storage_path.write_text(json.dumps(data, indent=2))

    def record_workflow(self, site_url: str, task_type: str, steps: List[dict]) -> str:
        """Record a successful workflow."""
        workflow_id = hashlib.md5(f"{site_url}:{task_type}".encode()).hexdigest()[:12]

        workflow_steps = [WorkflowStep(**s) for s in steps]
        site_pattern = self._extract_site_pattern(site_url)

        workflow = LearnedWorkflow(
            id=workflow_id,
            site_pattern=site_pattern,
            task_type=task_type,
            steps=workflow_steps,
            success_count=1,
            last_used=datetime.now().isoformat()
        )

        # Update existing or add new
        existing = next((w for w in self.workflows if w.id == workflow_id), None)
        if existing:
            existing.success_count += 1
            existing.last_used = workflow.last_used
        else:
            self.workflows.append(workflow)

        self._save()
        return workflow_id

    def find_matching_workflow(self, site_url: str, task_type: str) -> Optional[LearnedWorkflow]:
        """Find a workflow that matches the current site/task."""
        site_pattern = self._extract_site_pattern(site_url)

        # Exact match first
        for w in self.workflows:
            if w.site_pattern == site_pattern and w.task_type == task_type:
                if w.success_count > w.fail_count:  # Only use successful ones
                    return w

        # Fuzzy match by task type
        for w in self.workflows:
            if w.task_type == task_type and w.success_count > 2:
                return w

        return None

    def report_success(self, workflow_id: str):
        for w in self.workflows:
            if w.id == workflow_id:
                w.success_count += 1
                self._save()
                break

    def report_failure(self, workflow_id: str):
        for w in self.workflows:
            if w.id == workflow_id:
                w.fail_count += 1
                self._save()
                break

    def _extract_site_pattern(self, url: str) -> str:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc
