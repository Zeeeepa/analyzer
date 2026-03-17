"""
Workflow Recorder/Replay System

Records and replays browser automation workflows similar to browser-use's recorded workflows.
Captures tool calls, timing, page state, and enables replay with variable substitution.
"""

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from enum import Enum
import asyncio
from dataclasses import dataclass, asdict


class RecordingState(Enum):
    """Recording state enum"""
    IDLE = "idle"
    RECORDING = "recording"
    PAUSED = "paused"


class ReplayMode(Enum):
    """Replay execution modes"""
    NORMAL = "normal"  # Execute all steps sequentially
    STEP = "step"  # Pause after each step
    PAUSE = "pause"  # Paused state


@dataclass
class WorkflowStep:
    """Single workflow step"""
    step: int
    tool: str
    args: Dict[str, Any]
    page_state: Dict[str, Any]
    timestamp: float
    duration: float
    result: Optional[Any] = None
    error: Optional[str] = None


@dataclass
class Workflow:
    """Complete workflow definition"""
    name: str
    recorded_at: str
    steps: List[Dict[str, Any]]
    variables: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "recorded_at": self.recorded_at,
            "steps": self.steps,
            "variables": self.variables,
            "metadata": self.metadata or {}
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Workflow':
        """Create from dictionary"""
        return cls(
            name=data["name"],
            recorded_at=data["recorded_at"],
            steps=data["steps"],
            variables=data.get("variables", {}),
            metadata=data.get("metadata", {})
        )


class WorkflowRecorder:
    """
    Workflow Recorder/Replay System

    Records browser automation workflows and replays them with variable substitution.
    """

    def __init__(self, storage_dir: str = "memory/workflows"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # Recording state
        self._state = RecordingState.IDLE
        self._current_workflow: Optional[str] = None
        self._steps: List[WorkflowStep] = []
        self._start_time: float = 0.0
        self._variables: Dict[str, Any] = {}

        # Replay state
        self._replay_mode = ReplayMode.NORMAL
        self._replay_paused = False
        self._current_step_index = 0

    # ==================== Recording API ====================

    def start_recording(self, name: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Start recording a new workflow

        Args:
            name: Workflow name
            variables: Initial variables for the workflow

        Returns:
            Status dictionary
        """
        if self._state == RecordingState.RECORDING:
            return {
                "success": False,
                "error": "Already recording workflow: {}".format(self._current_workflow)
            }

        self._state = RecordingState.RECORDING
        self._current_workflow = name
        self._steps = []
        self._start_time = time.time()
        self._variables = variables or {}

        return {
            "success": True,
            "workflow": name,
            "started_at": datetime.utcnow().isoformat() + "Z"
        }

    def record_step(
        self,
        tool: str,
        args: Dict[str, Any],
        result: Optional[Any] = None,
        page_state: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Record a single workflow step

        Args:
            tool: Tool name (e.g., "playwright_navigate")
            args: Tool arguments
            result: Tool execution result
            page_state: Current page state (URL, title, etc.)
            error: Error message if step failed

        Returns:
            Status dictionary
        """
        if self._state != RecordingState.RECORDING:
            return {
                "success": False,
                "error": "Not currently recording"
            }

        current_time = time.time()
        timestamp = current_time - self._start_time

        step = WorkflowStep(
            step=len(self._steps) + 1,
            tool=tool,
            args=self._sanitize_args(args),
            page_state=page_state or {},
            timestamp=timestamp,
            duration=0.0,  # Will be updated on next step or stop
            result=result,
            error=error
        )

        # Update duration of previous step
        if self._steps:
            prev_step = self._steps[-1]
            prev_step.duration = timestamp - prev_step.timestamp

        self._steps.append(step)

        return {
            "success": True,
            "step": step.step,
            "tool": tool
        }

    def stop_recording(self) -> Dict[str, Any]:
        """
        Stop recording and return the workflow

        Returns:
            Workflow dictionary
        """
        if self._state != RecordingState.RECORDING:
            return {
                "success": False,
                "error": "Not currently recording"
            }

        # Update duration of last step
        if self._steps:
            current_time = time.time()
            last_step = self._steps[-1]
            last_step.duration = current_time - self._start_time - last_step.timestamp

        workflow = Workflow(
            name=self._current_workflow,
            recorded_at=datetime.utcnow().isoformat() + "Z",
            steps=[asdict(step) for step in self._steps],
            variables=self._variables,
            metadata={
                "total_duration": time.time() - self._start_time,
                "total_steps": len(self._steps)
            }
        )

        # Reset state
        self._state = RecordingState.IDLE
        self._current_workflow = None
        self._steps = []

        return {
            "success": True,
            "workflow": workflow.to_dict()
        }

    def pause_recording(self) -> Dict[str, Any]:
        """Pause current recording"""
        if self._state != RecordingState.RECORDING:
            return {"success": False, "error": "Not currently recording"}

        self._state = RecordingState.PAUSED
        return {"success": True, "state": "paused"}

    def resume_recording(self) -> Dict[str, Any]:
        """Resume paused recording"""
        if self._state != RecordingState.PAUSED:
            return {"success": False, "error": "Recording not paused"}

        self._state = RecordingState.RECORDING
        return {"success": True, "state": "recording"}

    def get_recording_status(self) -> Dict[str, Any]:
        """
        Get current recording status

        Returns:
            Status dictionary with recording state
        """
        return {
            "state": self._state.value,
            "workflow": self._current_workflow,
            "steps_recorded": len(self._steps),
            "elapsed_time": time.time() - self._start_time if self._state == RecordingState.RECORDING else 0
        }

    # ==================== Storage API ====================

    def save_workflow(self, workflow: Union[Workflow, Dict[str, Any]], path: Optional[str] = None) -> Dict[str, Any]:
        """
        Save workflow to file

        Args:
            workflow: Workflow object or dictionary
            path: Optional custom path (defaults to storage_dir/{name}.workflow.json)

        Returns:
            Status dictionary with file path
        """
        if isinstance(workflow, dict):
            workflow = Workflow.from_dict(workflow)

        if path is None:
            # Generate filename from workflow name
            safe_name = re.sub(r'[^\w\s-]', '', workflow.name).strip().replace(' ', '_')
            path = str(self.storage_dir / "{}.workflow.json".format(safe_name))

        try:
            with open(path, 'w') as f:
                json.dump(workflow.to_dict(), f, indent=2)

            return {
                "success": True,
                "path": path,
                "workflow": workflow.name
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def load_workflow(self, path: str) -> Dict[str, Any]:
        """
        Load workflow from file

        Args:
            path: Path to workflow file (can be name or full path)

        Returns:
            Status dictionary with workflow data
        """
        # If path doesn't exist, try in storage_dir
        if not os.path.exists(path):
            # Try with .workflow.json extension
            if not path.endswith('.workflow.json'):
                path = str(self.storage_dir / "{}.workflow.json".format(path))
            else:
                path = str(self.storage_dir / path)

        if not os.path.exists(path):
            return {
                "success": False,
                "error": "Workflow file not found: {}".format(path)
            }

        try:
            with open(path, 'r') as f:
                data = json.load(f)

            workflow = Workflow.from_dict(data)

            return {
                "success": True,
                "workflow": workflow.to_dict(),
                "path": path
            }
        except Exception as e:
            return {
                "success": False,
                "error": "Failed to load workflow: {}".format(str(e))
            }

    def list_workflows(self) -> Dict[str, Any]:
        """
        List all available workflows

        Returns:
            Dictionary with list of workflows
        """
        try:
            workflows = []
            for file_path in self.storage_dir.glob("*.workflow.json"):
                try:
                    with open(file_path, 'r') as f:
                        data = json.load(f)
                    workflows.append({
                        "name": data.get("name"),
                        "path": str(file_path),
                        "recorded_at": data.get("recorded_at"),
                        "steps": len(data.get("steps", [])),
                        "variables": list(data.get("variables", {}).keys())
                    })
                except Exception:
                    continue

            return {
                "success": True,
                "workflows": workflows,
                "count": len(workflows)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def delete_workflow(self, path: str) -> Dict[str, Any]:
        """Delete a workflow file"""
        if not os.path.exists(path):
            path = str(self.storage_dir / "{}.workflow.json".format(path))

        try:
            os.remove(path)
            return {"success": True, "deleted": path}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ==================== Replay API ====================

    async def replay_workflow(
        self,
        workflow: Union[Workflow, Dict[str, Any], str],
        variables: Optional[Dict[str, Any]] = None,
        tool_executor: Optional[Any] = None,
        mode: ReplayMode = ReplayMode.NORMAL,
        start_step: int = 1,
        end_step: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Replay a recorded workflow

        Args:
            workflow: Workflow object, dictionary, or path to workflow file
            variables: Variables to substitute in workflow (overrides recorded variables)
            tool_executor: Tool executor instance for executing steps
            mode: Replay mode (normal, step, pause)
            start_step: Step number to start from
            end_step: Step number to end at (None for all steps)

        Returns:
            Replay results dictionary
        """
        # Load workflow if path provided
        if isinstance(workflow, str):
            result = self.load_workflow(workflow)
            if not result["success"]:
                return result
            workflow = Workflow.from_dict(result["workflow"])
        elif isinstance(workflow, dict):
            workflow = Workflow.from_dict(workflow)

        # Merge variables
        merged_variables = {**workflow.variables, **(variables or {})}

        # Set replay state
        self._replay_mode = mode
        self._replay_paused = (mode == ReplayMode.PAUSE)
        self._current_step_index = start_step - 1

        results = {
            "workflow": workflow.name,
            "started_at": datetime.utcnow().isoformat() + "Z",
            "steps_executed": 0,
            "steps_failed": 0,
            "step_results": [],
            "success": True
        }

        start_time = time.time()
        steps_to_execute = workflow.steps[start_step - 1:end_step]

        for i, step_data in enumerate(steps_to_execute):
            self._current_step_index = start_step + i

            # Check pause state
            if self._replay_paused:
                results["paused_at_step"] = self._current_step_index
                results["status"] = "paused"
                break

            # Execute step
            step_result = await self._execute_step(
                step_data,
                merged_variables,
                tool_executor
            )

            results["step_results"].append(step_result)

            if step_result["success"]:
                results["steps_executed"] += 1
            else:
                results["steps_failed"] += 1
                # Stop on error unless configured otherwise
                if mode != ReplayMode.STEP:
                    results["success"] = False
                    results["error"] = "Step {} failed: {}".format(
                        self._current_step_index,
                        step_result.get("error")
                    )
                    break

            # Pause in step mode
            if mode == ReplayMode.STEP:
                self._replay_paused = True
                results["paused_at_step"] = self._current_step_index + 1
                results["status"] = "paused"
                break

        results["duration"] = time.time() - start_time
        results["completed_at"] = datetime.utcnow().isoformat() + "Z"

        if not self._replay_paused:
            results["status"] = "completed"

        return results

    async def _execute_step(
        self,
        step_data: Dict[str, Any],
        variables: Dict[str, Any],
        tool_executor: Optional[Any]
    ) -> Dict[str, Any]:
        """Execute a single workflow step with variable substitution"""
        try:
            # Substitute variables in args
            substituted_args = self._substitute_variables(step_data["args"], variables)

            # Execute tool if executor provided
            if tool_executor:
                result = await self._execute_tool(
                    tool_executor,
                    step_data["tool"],
                    substituted_args
                )
            else:
                result = {
                    "simulated": True,
                    "tool": step_data["tool"],
                    "args": substituted_args
                }

            return {
                "step": step_data["step"],
                "tool": step_data["tool"],
                "success": True,
                "result": result
            }
        except Exception as e:
            return {
                "step": step_data["step"],
                "tool": step_data["tool"],
                "success": False,
                "error": str(e)
            }

    async def _execute_tool(self, tool_executor: Any, tool: str, args: Dict[str, Any]) -> Any:
        """Execute a tool using the tool executor"""
        # Try to execute the tool
        if hasattr(tool_executor, 'execute_tool'):
            return await tool_executor.execute_tool(tool, args)
        elif hasattr(tool_executor, tool):
            tool_func = getattr(tool_executor, tool)
            if asyncio.iscoroutinefunction(tool_func):
                return await tool_func(**args)
            else:
                return tool_func(**args)
        else:
            raise ValueError("Tool executor does not support tool: {}".format(tool))

    def pause_replay(self) -> Dict[str, Any]:
        """Pause replay execution"""
        self._replay_paused = True
        return {
            "success": True,
            "status": "paused",
            "current_step": self._current_step_index
        }

    def resume_replay(self) -> Dict[str, Any]:
        """Resume paused replay"""
        self._replay_paused = False
        return {
            "success": True,
            "status": "resumed",
            "current_step": self._current_step_index
        }

    def step_forward(self) -> Dict[str, Any]:
        """Execute next step in step mode"""
        if self._replay_mode != ReplayMode.STEP:
            return {"success": False, "error": "Not in step mode"}

        self._replay_paused = False
        return {
            "success": True,
            "status": "stepping",
            "next_step": self._current_step_index + 1
        }

    # ==================== Workflow Editor API ====================

    def add_step(
        self,
        workflow: Union[Workflow, Dict[str, Any]],
        tool: str,
        args: Dict[str, Any],
        page_state: Optional[Dict[str, Any]] = None,
        index: Optional[int] = None
    ) -> Dict[str, Any]:
        """Add a step to workflow"""
        if isinstance(workflow, dict):
            workflow = Workflow.from_dict(workflow)

        new_step = {
            "step": len(workflow.steps) + 1,
            "tool": tool,
            "args": args,
            "page_state": page_state or {},
            "timestamp": 0.0,
            "duration": 0.0
        }

        if index is None:
            workflow.steps.append(new_step)
        else:
            workflow.steps.insert(index, new_step)
            # Renumber steps
            for i, step in enumerate(workflow.steps):
                step["step"] = i + 1

        return {
            "success": True,
            "workflow": workflow.to_dict(),
            "step_added": new_step["step"]
        }

    def remove_step(
        self,
        workflow: Union[Workflow, Dict[str, Any]],
        index: int
    ) -> Dict[str, Any]:
        """Remove a step from workflow"""
        if isinstance(workflow, dict):
            workflow = Workflow.from_dict(workflow)

        if index < 0 or index >= len(workflow.steps):
            return {"success": False, "error": "Invalid step index"}

        removed = workflow.steps.pop(index)

        # Renumber remaining steps
        for i, step in enumerate(workflow.steps):
            step["step"] = i + 1

        return {
            "success": True,
            "workflow": workflow.to_dict(),
            "removed_step": removed["step"]
        }

    def modify_step(
        self,
        workflow: Union[Workflow, Dict[str, Any]],
        index: int,
        changes: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Modify a workflow step"""
        if isinstance(workflow, dict):
            workflow = Workflow.from_dict(workflow)

        if index < 0 or index >= len(workflow.steps):
            return {"success": False, "error": "Invalid step index"}

        workflow.steps[index].update(changes)

        return {
            "success": True,
            "workflow": workflow.to_dict(),
            "modified_step": index + 1
        }

    def reorder_steps(
        self,
        workflow: Union[Workflow, Dict[str, Any]],
        new_order: List[int]
    ) -> Dict[str, Any]:
        """Reorder workflow steps"""
        if isinstance(workflow, dict):
            workflow = Workflow.from_dict(workflow)

        if len(new_order) != len(workflow.steps):
            return {"success": False, "error": "New order must include all steps"}

        if sorted(new_order) != list(range(len(workflow.steps))):
            return {"success": False, "error": "Invalid step indices in new order"}

        workflow.steps = [workflow.steps[i] for i in new_order]

        # Renumber steps
        for i, step in enumerate(workflow.steps):
            step["step"] = i + 1

        return {
            "success": True,
            "workflow": workflow.to_dict()
        }

    # ==================== Utility Methods ====================

    def _sanitize_args(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize arguments to remove sensitive data"""
        sanitized = {}
        sensitive_keys = {'password', 'secret', 'token', 'key', 'api_key', 'auth'}

        for key, value in args.items():
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                sanitized[key] = "***REDACTED***"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_args(value)
            else:
                sanitized[key] = value

        return sanitized

    def _substitute_variables(self, obj: Any, variables: Dict[str, Any]) -> Any:
        """
        Recursively substitute variables in object using ${var} syntax

        Args:
            obj: Object to substitute variables in
            variables: Dictionary of variable values

        Returns:
            Object with variables substituted
        """
        if isinstance(obj, str):
            # Replace ${var} with variable value
            pattern = r'\$\{(\w+)\}'

            def replacer(match):
                var_name = match.group(1)
                return str(variables.get(var_name, match.group(0)))

            return re.sub(pattern, replacer, obj)
        elif isinstance(obj, dict):
            return {k: self._substitute_variables(v, variables) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._substitute_variables(item, variables) for item in obj]
        else:
            return obj


# ==================== Singleton Pattern ====================

_workflow_recorder_instance: Optional[WorkflowRecorder] = None


def get_workflow_recorder(storage_dir: str = "memory/workflows") -> WorkflowRecorder:
    """
    Get or create the singleton WorkflowRecorder instance

    Args:
        storage_dir: Directory for storing workflows

    Returns:
        WorkflowRecorder instance
    """
    global _workflow_recorder_instance

    if _workflow_recorder_instance is None:
        _workflow_recorder_instance = WorkflowRecorder(storage_dir)

    return _workflow_recorder_instance


# ==================== Test Code ====================

async def test_workflow_recorder():
    """Test the workflow recorder functionality"""
    print("Testing Workflow Recorder...")
    print("-" * 50)

    # Initialize recorder
    recorder = get_workflow_recorder("test_workflows")

    # Test 1: Recording workflow
    print("\n1. Testing workflow recording...")
    result = recorder.start_recording("Login workflow", {"username": "testuser"})
    print("Start recording:", result)
    assert result["success"], "Failed to start recording"

    # Record some steps
    recorder.record_step(
        "playwright_navigate",
        {"url": "https://example.com"},
        page_state={"url": "https://example.com", "title": "Example Domain"}
    )

    recorder.record_step(
        "playwright_click",
        {"selector": "#login-button"},
        page_state={"url": "https://example.com/login", "title": "Login"}
    )

    recorder.record_step(
        "playwright_fill",
        {"selector": "#username", "value": "${username}"},
        page_state={"url": "https://example.com/login", "title": "Login"}
    )

    status = recorder.get_recording_status()
    print("Recording status:", status)
    assert status["steps_recorded"] == 3, "Expected 3 steps recorded"

    result = recorder.stop_recording()
    print("Stop recording:", result["success"])
    assert result["success"], "Failed to stop recording"

    workflow = result["workflow"]
    print("Recorded {} steps".format(len(workflow["steps"])))

    # Test 2: Save workflow
    print("\n2. Testing workflow save...")
    result = recorder.save_workflow(workflow)
    print("Save result:", result)
    assert result["success"], "Failed to save workflow"

    # Test 3: Load workflow
    print("\n3. Testing workflow load...")
    result = recorder.load_workflow("Login_workflow")
    print("Load result:", result["success"])
    assert result["success"], "Failed to load workflow"
    loaded_workflow = result["workflow"]
    assert len(loaded_workflow["steps"]) == 3, "Expected 3 steps in loaded workflow"

    # Test 4: List workflows
    print("\n4. Testing workflow listing...")
    result = recorder.list_workflows()
    print("Found {} workflows".format(result["count"]))
    assert result["success"], "Failed to list workflows"

    # Test 5: Workflow editing
    print("\n5. Testing workflow editing...")
    result = recorder.add_step(
        loaded_workflow,
        "playwright_click",
        {"selector": "#submit"},
        index=None
    )
    print("Add step:", result["success"])
    assert result["success"], "Failed to add step"

    result = recorder.modify_step(
        result["workflow"],
        0,
        {"args": {"url": "https://newexample.com"}}
    )
    print("Modify step:", result["success"])
    assert result["success"], "Failed to modify step"

    # Test 6: Variable substitution
    print("\n6. Testing variable substitution...")
    test_obj = {
        "url": "${base_url}/login",
        "credentials": {
            "username": "${username}",
            "password": "${password}"
        },
        "list": ["${item1}", "static", "${item2}"]
    }

    variables = {
        "base_url": "https://example.com",
        "username": "john",
        "password": "secret123",
        "item1": "first",
        "item2": "second"
    }

    substituted = recorder._substitute_variables(test_obj, variables)
    print("Substituted:", json.dumps(substituted, indent=2))
    assert substituted["url"] == "https://example.com/login", "URL substitution failed"
    assert substituted["credentials"]["username"] == "john", "Username substitution failed"
    assert substituted["list"][0] == "first", "List item substitution failed"

    # Test 7: Replay workflow (simulated)
    print("\n7. Testing workflow replay (simulated)...")
    result = await recorder.replay_workflow(
        loaded_workflow,
        variables={"username": "john_doe"},
        tool_executor=None  # No executor, will simulate
    )
    print("Replay result:", result["success"])
    print("Steps executed:", result["steps_executed"])
    assert result["success"], "Failed to replay workflow"

    # Test 8: Pause/Resume
    print("\n8. Testing pause/resume recording...")
    recorder.start_recording("Pause test")
    recorder.record_step("tool1", {"arg": "value1"})
    result = recorder.pause_recording()
    print("Pause:", result["success"])
    assert result["success"], "Failed to pause"

    result = recorder.resume_recording()
    print("Resume:", result["success"])
    assert result["success"], "Failed to resume"

    recorder.record_step("tool2", {"arg": "value2"})
    recorder.stop_recording()

    # Test 9: Delete workflow
    print("\n9. Testing workflow deletion...")
    result = recorder.delete_workflow("Login_workflow")
    print("Delete result:", result["success"])
    assert result["success"], "Failed to delete workflow"

    print("\n" + "-" * 50)
    print("All tests passed!")


if __name__ == "__main__":
    # Run tests
    asyncio.run(test_workflow_recorder())
