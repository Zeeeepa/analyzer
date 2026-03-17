#!/usr/bin/env python3
"""
Hierarchical Task Network (HTN) Planning Agent for Eversale

Provides enterprise-grade planning capabilities based on AgentOrchestra, Devin, and
advanced multi-agent research. Supports hierarchical task decomposition, plan validation,
multi-agent coordination, and robust execution with checkpointing.

Architecture:
- PlanningAgent: Main orchestrator for hierarchical planning
- Plan: Immutable plan representation with versioning
- PlanStep: Individual step in a plan with dependencies
- PlanCritic: Validates and scores plans before execution
- PlanExecutor: Executes plans with checkpointing and rollback
- PlanTemplate: Reusable templates for common workflows
"""

import asyncio
import hashlib
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
from loguru import logger
from collections import defaultdict

# Storage for plans
PLANS_DIR = Path("memory/plans")
PLANS_DIR.mkdir(parents=True, exist_ok=True)

TEMPLATES_DIR = Path("memory/plan_templates")
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


class PlanStatus(Enum):
    """Plan execution status"""
    DRAFT = "draft"
    VALIDATED = "validated"
    APPROVED = "approved"
    EXECUTING = "executing"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(Enum):
    """Individual step status"""
    PENDING = "pending"
    READY = "ready"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class TaskType(Enum):
    """Types of tasks in the HTN"""
    PRIMITIVE = "primitive"  # Atomic action
    COMPOSITE = "composite"  # Decomposable task
    PARALLEL = "parallel"  # Can run in parallel
    SEQUENTIAL = "sequential"  # Must run sequentially
    CONDITIONAL = "conditional"  # Conditional execution


@dataclass
class Resource:
    """Resource required for task execution"""
    resource_type: str  # "browser", "api", "file", "memory", "cpu"
    name: str
    required: bool = True
    available: bool = False
    allocation: Optional[str] = None  # Which agent/instance has it


@dataclass
class PlanStep:
    """
    Individual step in a hierarchical plan
    """
    step_id: str
    name: str
    description: str
    task_type: TaskType
    action: str  # Function/tool to call
    arguments: Dict[str, Any] = field(default_factory=dict)

    # Hierarchy
    parent_id: Optional[str] = None
    children: List[str] = field(default_factory=list)
    depth: int = 0

    # Dependencies
    depends_on: List[str] = field(default_factory=list)
    blocks: List[str] = field(default_factory=list)

    # Execution
    status: StepStatus = StepStatus.PENDING
    assigned_to: Optional[str] = None  # Agent instance ID
    retry_count: int = 0
    max_retries: int = 3

    # Resources
    required_resources: List[Resource] = field(default_factory=list)

    # Timing
    estimated_duration: float = 0.0  # seconds
    actual_duration: float = 0.0
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    # Results
    result: Any = None
    error: Optional[str] = None

    # Contingency
    fallback_steps: List[str] = field(default_factory=list)
    rollback_action: Optional[str] = None

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        data = asdict(self)
        data['task_type'] = self.task_type.value
        data['status'] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: Dict) -> 'PlanStep':
        """Create from dictionary"""
        data['task_type'] = TaskType(data['task_type'])
        data['status'] = StepStatus(data['status'])
        data['required_resources'] = [
            Resource(**r) if isinstance(r, dict) else r
            for r in data.get('required_resources', [])
        ]
        return cls(**data)

    def is_ready(self) -> bool:
        """Check if step is ready to execute"""
        if self.status != StepStatus.PENDING:
            return False

        # Check dependencies
        return len(self.depends_on) == 0

    def is_blocked(self) -> bool:
        """Check if step is blocked"""
        return self.status == StepStatus.BLOCKED or len(self.depends_on) > 0

    def can_run_parallel(self) -> bool:
        """Check if this step can run in parallel with others"""
        return self.task_type == TaskType.PARALLEL


@dataclass
class Plan:
    """
    Hierarchical Task Network Plan
    Immutable after approval - create new version for changes
    """
    plan_id: str
    name: str
    description: str
    version: int = 1
    parent_plan_id: Optional[str] = None  # For partial replanning

    # Steps
    steps: Dict[str, PlanStep] = field(default_factory=dict)
    root_steps: List[str] = field(default_factory=list)  # Top-level steps

    # Status
    status: PlanStatus = PlanStatus.DRAFT

    # Planning metadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    created_by: str = "planning_agent"
    validated_at: Optional[str] = None
    approved_at: Optional[str] = None

    # Execution
    execution_started_at: Optional[str] = None
    execution_completed_at: Optional[str] = None
    checkpoints: List[Dict] = field(default_factory=list)

    # Estimates
    estimated_total_duration: float = 0.0
    actual_total_duration: float = 0.0

    # Metrics
    critic_score: float = 0.0
    feasibility_score: float = 0.0
    efficiency_score: float = 0.0
    risk_score: float = 0.0

    # Coordination
    assigned_agents: Set[str] = field(default_factory=set)
    resource_requirements: List[Resource] = field(default_factory=list)

    # Metadata
    tags: List[str] = field(default_factory=list)
    template_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            'plan_id': self.plan_id,
            'name': self.name,
            'description': self.description,
            'version': self.version,
            'parent_plan_id': self.parent_plan_id,
            'steps': {k: v.to_dict() for k, v in self.steps.items()},
            'root_steps': self.root_steps,
            'status': self.status.value,
            'created_at': self.created_at,
            'created_by': self.created_by,
            'validated_at': self.validated_at,
            'approved_at': self.approved_at,
            'execution_started_at': self.execution_started_at,
            'execution_completed_at': self.execution_completed_at,
            'checkpoints': self.checkpoints,
            'estimated_total_duration': self.estimated_total_duration,
            'actual_total_duration': self.actual_total_duration,
            'critic_score': self.critic_score,
            'feasibility_score': self.feasibility_score,
            'efficiency_score': self.efficiency_score,
            'risk_score': self.risk_score,
            'assigned_agents': list(self.assigned_agents),
            'resource_requirements': [asdict(r) for r in self.resource_requirements],
            'tags': self.tags,
            'template_id': self.template_id,
            'metadata': self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Plan':
        """Create from dictionary"""
        data['status'] = PlanStatus(data['status'])
        data['steps'] = {k: PlanStep.from_dict(v) for k, v in data.get('steps', {}).items()}
        data['assigned_agents'] = set(data.get('assigned_agents', []))
        data['resource_requirements'] = [
            Resource(**r) if isinstance(r, dict) else r
            for r in data.get('resource_requirements', [])
        ]
        return cls(**data)

    def save(self):
        """Persist plan to disk"""
        path = PLANS_DIR / f"{self.plan_id}_v{self.version}.json"
        path.write_text(json.dumps(self.to_dict(), indent=2))
        logger.debug(f"Saved plan {self.plan_id} v{self.version}")

    @classmethod
    def load(cls, plan_id: str, version: Optional[int] = None) -> Optional['Plan']:
        """Load plan from disk"""
        if version:
            path = PLANS_DIR / f"{plan_id}_v{version}.json"
        else:
            # Load latest version
            versions = list(PLANS_DIR.glob(f"{plan_id}_v*.json"))
            if not versions:
                return None
            path = sorted(versions, key=lambda p: int(p.stem.split('_v')[1]))[-1]

        if path.exists():
            data = json.loads(path.read_text())
            return cls.from_dict(data)
        return None

    def get_ready_steps(self) -> List[PlanStep]:
        """Get all steps that are ready to execute"""
        ready = []
        for step in self.steps.values():
            if step.is_ready():
                ready.append(step)
        return ready

    def get_parallel_steps(self) -> List[List[PlanStep]]:
        """Get groups of steps that can run in parallel"""
        parallel_groups = []
        ready_steps = self.get_ready_steps()

        # Group by parent and task type
        groups = defaultdict(list)
        for step in ready_steps:
            if step.can_run_parallel():
                key = (step.parent_id, step.depth)
                groups[key].append(step)

        return list(groups.values())

    def mark_step_completed(self, step_id: str, result: Any = None):
        """Mark a step as completed and update dependencies"""
        if step_id not in self.steps:
            return

        step = self.steps[step_id]
        step.status = StepStatus.COMPLETED
        step.completed_at = datetime.now().isoformat()
        step.result = result

        # Update dependent steps
        for other_step in self.steps.values():
            if step_id in other_step.depends_on:
                other_step.depends_on.remove(step_id)
                if len(other_step.depends_on) == 0:
                    other_step.status = StepStatus.READY

    def mark_step_failed(self, step_id: str, error: str):
        """Mark a step as failed"""
        if step_id not in self.steps:
            return

        step = self.steps[step_id]
        step.status = StepStatus.FAILED
        step.error = error

        # Mark dependent steps as blocked
        for other_step in self.steps.values():
            if step_id in other_step.depends_on:
                other_step.status = StepStatus.BLOCKED

    def create_checkpoint(self, checkpoint_data: Dict = None):
        """Create a checkpoint of current plan state"""
        checkpoint = {
            'timestamp': datetime.now().isoformat(),
            'completed_steps': [
                step_id for step_id, step in self.steps.items()
                if step.status == StepStatus.COMPLETED
            ],
            'failed_steps': [
                step_id for step_id, step in self.steps.items()
                if step.status == StepStatus.FAILED
            ],
            'data': checkpoint_data or {}
        }
        self.checkpoints.append(checkpoint)
        self.save()

    def get_progress(self) -> Dict[str, Any]:
        """Get plan execution progress"""
        total_steps = len(self.steps)
        if total_steps == 0:
            return {'percent': 0, 'completed': 0, 'total': 0}

        completed = sum(1 for s in self.steps.values() if s.status == StepStatus.COMPLETED)
        failed = sum(1 for s in self.steps.values() if s.status == StepStatus.FAILED)
        executing = sum(1 for s in self.steps.values() if s.status == StepStatus.EXECUTING)
        pending = sum(1 for s in self.steps.values() if s.status == StepStatus.PENDING)

        return {
            'percent': (completed / total_steps) * 100,
            'completed': completed,
            'failed': failed,
            'executing': executing,
            'pending': pending,
            'total': total_steps
        }


@dataclass
class PlanTemplate:
    """Reusable plan template for common workflows"""
    template_id: str
    name: str
    description: str
    category: str  # SDR, support, e-commerce, etc.

    # Template structure
    step_templates: List[Dict[str, Any]] = field(default_factory=list)
    required_params: List[str] = field(default_factory=list)
    optional_params: List[str] = field(default_factory=list)

    # Metadata
    usage_count: int = 0
    success_rate: float = 0.0
    avg_duration: float = 0.0

    def instantiate(self, params: Dict[str, Any]) -> Plan:
        """Create a plan instance from this template"""
        # Validate required params
        missing = [p for p in self.required_params if p not in params]
        if missing:
            raise ValueError(f"Missing required parameters: {missing}")

        # Generate plan ID
        plan_id = hashlib.md5(
            f"{self.template_id}_{datetime.now().isoformat()}".encode()
        ).hexdigest()[:16]

        plan = Plan(
            plan_id=plan_id,
            name=params.get('plan_name', self.name),
            description=self.description,
            template_id=self.template_id,
            tags=[self.category]
        )

        # Create steps from templates
        step_id_map = {}
        for i, step_template in enumerate(self.step_templates):
            step_id = f"{plan_id}_step_{i}"
            step_id_map[step_template.get('template_id', i)] = step_id

            # Substitute parameters in action and arguments
            action = step_template['action']
            arguments = self._substitute_params(step_template.get('arguments', {}), params)

            step = PlanStep(
                step_id=step_id,
                name=step_template['name'],
                description=step_template.get('description', ''),
                task_type=TaskType(step_template.get('task_type', 'primitive')),
                action=action,
                arguments=arguments,
                depth=step_template.get('depth', 0),
                estimated_duration=step_template.get('estimated_duration', 0.0),
                max_retries=step_template.get('max_retries', 3)
            )

            plan.steps[step_id] = step

        # Set up dependencies
        for i, step_template in enumerate(self.step_templates):
            template_id = step_template.get('template_id', i)
            step_id = step_id_map[template_id]
            step = plan.steps[step_id]

            # Map template dependencies to actual step IDs
            if 'depends_on' in step_template:
                step.depends_on = [
                    step_id_map[dep] for dep in step_template['depends_on']
                    if dep in step_id_map
                ]

            # Set parent
            if 'parent_id' in step_template and step_template['parent_id'] in step_id_map:
                step.parent_id = step_id_map[step_template['parent_id']]
                parent = plan.steps[step.parent_id]
                parent.children.append(step_id)
            else:
                plan.root_steps.append(step_id)

        return plan

    def _substitute_params(self, arguments: Dict, params: Dict) -> Dict:
        """Substitute template variables with actual parameters"""
        result = {}
        for key, value in arguments.items():
            if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
                param_name = value[2:-1]
                result[key] = params.get(param_name, value)
            elif isinstance(value, dict):
                result[key] = self._substitute_params(value, params)
            elif isinstance(value, list):
                result[key] = [
                    self._substitute_params(item, params) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                result[key] = value
        return result

    def save(self):
        """Save template to disk"""
        path = TEMPLATES_DIR / f"{self.template_id}.json"
        data = asdict(self)
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, template_id: str) -> Optional['PlanTemplate']:
        """Load template from disk"""
        path = TEMPLATES_DIR / f"{template_id}.json"
        if path.exists():
            data = json.loads(path.read_text())
            return cls(**data)
        return None


class PlanCritic:
    """
    Evaluates plans before execution
    Scores plans by feasibility, efficiency, and risk
    """

    def __init__(self):
        self.weights = {
            'feasibility': 0.4,
            'efficiency': 0.3,
            'risk': 0.3
        }

    async def evaluate(self, plan: Plan) -> Dict[str, Any]:
        """Evaluate a plan and return scores + suggestions"""
        logger.info(f"Evaluating plan {plan.plan_id}")

        # Run all evaluations in parallel
        results = await asyncio.gather(
            self._evaluate_feasibility(plan),
            self._evaluate_efficiency(plan),
            self._evaluate_risk(plan),
            self._check_completeness(plan)
        )

        feasibility_result, efficiency_result, risk_result, completeness_result = results

        # Calculate overall score
        overall_score = (
            self.weights['feasibility'] * feasibility_result['score'] +
            self.weights['efficiency'] * efficiency_result['score'] +
            self.weights['risk'] * (1.0 - risk_result['score'])  # Lower risk is better
        )

        # Update plan scores
        plan.critic_score = overall_score
        plan.feasibility_score = feasibility_result['score']
        plan.efficiency_score = efficiency_result['score']
        plan.risk_score = risk_result['score']

        # Aggregate suggestions
        suggestions = (
            feasibility_result.get('suggestions', []) +
            efficiency_result.get('suggestions', []) +
            risk_result.get('suggestions', []) +
            completeness_result.get('suggestions', [])
        )

        return {
            'overall_score': overall_score,
            'feasibility': feasibility_result,
            'efficiency': efficiency_result,
            'risk': risk_result,
            'completeness': completeness_result,
            'suggestions': suggestions,
            'approved': overall_score >= 0.7 and completeness_result['complete']
        }

    async def _evaluate_feasibility(self, plan: Plan) -> Dict[str, Any]:
        """Evaluate if plan is feasible to execute"""
        score = 1.0
        suggestions = []

        # Check resource availability
        required_resources = set()
        for step in plan.steps.values():
            for resource in step.required_resources:
                required_resources.add(resource.resource_type)

        # Check for impossible dependencies
        if self._has_circular_dependencies(plan):
            score *= 0.5
            suggestions.append("Circular dependencies detected - plan may deadlock")

        # Check step actions are valid
        invalid_actions = []
        for step in plan.steps.values():
            if not step.action or step.action == "unknown":
                invalid_actions.append(step.step_id)

        if invalid_actions:
            score *= 0.7
            suggestions.append(f"Invalid actions in steps: {invalid_actions[:3]}")

        return {
            'score': score,
            'suggestions': suggestions,
            'required_resources': list(required_resources)
        }

    async def _evaluate_efficiency(self, plan: Plan) -> Dict[str, Any]:
        """Evaluate plan efficiency"""
        score = 1.0
        suggestions = []

        # Check for parallel opportunities
        parallel_groups = plan.get_parallel_steps()
        total_steps = len(plan.steps)
        parallel_potential = sum(len(g) for g in parallel_groups if len(g) > 1)

        if parallel_potential > 0:
            parallelization_ratio = parallel_potential / total_steps
            if parallelization_ratio < 0.2:
                suggestions.append(
                    f"Only {parallelization_ratio*100:.0f}% of steps can run in parallel - "
                    "consider breaking down sequential steps"
                )

        # Check for redundant steps
        action_counts = defaultdict(int)
        for step in plan.steps.values():
            action_counts[step.action] += 1

        redundant = {action: count for action, count in action_counts.items() if count > 3}
        if redundant:
            score *= 0.9
            suggestions.append(f"Potentially redundant actions: {list(redundant.keys())[:3]}")

        # Check depth - overly deep plans are inefficient
        max_depth = max((s.depth for s in plan.steps.values()), default=0)
        if max_depth > 5:
            score *= 0.95
            suggestions.append(f"Plan depth is {max_depth} - consider flattening hierarchy")

        return {
            'score': score,
            'suggestions': suggestions,
            'parallelization_ratio': parallel_potential / total_steps if total_steps > 0 else 0
        }

    async def _evaluate_risk(self, plan: Plan) -> Dict[str, Any]:
        """Evaluate plan execution risks"""
        score = 0.0  # Start at 0, add risk factors
        suggestions = []

        # Check for steps without fallbacks
        no_fallback = []
        for step in plan.steps.values():
            if step.task_type != TaskType.PRIMITIVE and not step.fallback_steps:
                no_fallback.append(step.step_id)

        if no_fallback:
            score += 0.3
            suggestions.append(
                f"{len(no_fallback)} complex steps have no fallback plans"
            )

        # Check for steps with low retry counts
        low_retries = [
            step.step_id for step in plan.steps.values()
            if step.max_retries < 2 and step.task_type != TaskType.PRIMITIVE
        ]

        if low_retries:
            score += 0.2
            suggestions.append(f"{len(low_retries)} steps have insufficient retry limits")

        # Check for external dependencies
        external_deps = [
            step.step_id for step in plan.steps.values()
            if 'external' in step.action.lower() or 'api' in step.action.lower()
        ]

        if external_deps:
            score += 0.1 * min(len(external_deps) / len(plan.steps), 1.0)
            suggestions.append(
                f"{len(external_deps)} steps depend on external services - "
                "ensure proper error handling"
            )

        return {
            'score': min(score, 1.0),
            'suggestions': suggestions,
            'high_risk_steps': no_fallback[:5]
        }

    async def _check_completeness(self, plan: Plan) -> Dict[str, Any]:
        """Check if plan is complete and well-formed"""
        complete = True
        suggestions = []

        # Check for orphaned steps
        all_step_ids = set(plan.steps.keys())
        referenced_ids = set(plan.root_steps)
        for step in plan.steps.values():
            referenced_ids.update(step.children)
            referenced_ids.update(step.depends_on)

        orphaned = all_step_ids - referenced_ids
        if orphaned:
            complete = False
            suggestions.append(f"Orphaned steps detected: {list(orphaned)[:3]}")

        # Check all dependencies exist
        for step in plan.steps.values():
            missing_deps = [
                dep for dep in step.depends_on
                if dep not in plan.steps
            ]
            if missing_deps:
                complete = False
                suggestions.append(
                    f"Step {step.step_id} has missing dependencies: {missing_deps}"
                )

        # Check root steps exist
        if not plan.root_steps:
            complete = False
            suggestions.append("No root steps defined - plan cannot start")

        return {
            'complete': complete,
            'suggestions': suggestions
        }

    def _has_circular_dependencies(self, plan: Plan) -> bool:
        """Detect circular dependencies using DFS"""
        visited = set()
        rec_stack = set()

        def visit(step_id: str) -> bool:
            if step_id in rec_stack:
                return True  # Circular dependency found
            if step_id in visited:
                return False

            visited.add(step_id)
            rec_stack.add(step_id)

            step = plan.steps.get(step_id)
            if step:
                for dep in step.depends_on:
                    if visit(dep):
                        return True

            rec_stack.remove(step_id)
            return False

        for step_id in plan.steps.keys():
            if visit(step_id):
                return True

        return False


class PlanExecutor:
    """
    Executes plans with checkpoint support and rollback capability
    """

    def __init__(self, action_handler: Optional[Callable] = None):
        """
        Args:
            action_handler: Async function that executes actions
                           Should have signature: async def handler(action, arguments) -> result
        """
        self.action_handler = action_handler
        self.executing_plans: Dict[str, Plan] = {}

    async def execute(
        self,
        plan: Plan,
        checkpoint_interval: int = 5,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Execute a plan with checkpointing

        Args:
            plan: Plan to execute
            checkpoint_interval: Create checkpoint every N completed steps
            progress_callback: Optional callback for progress updates

        Returns:
            Execution results
        """
        logger.info(f"Starting execution of plan {plan.plan_id}")

        plan.status = PlanStatus.EXECUTING
        plan.execution_started_at = datetime.now().isoformat()
        self.executing_plans[plan.plan_id] = plan

        completed_count = 0
        failed_steps = []

        try:
            # Execute steps in dependency order
            while True:
                ready_steps = plan.get_ready_steps()

                if not ready_steps:
                    # Check if all steps are done
                    pending = [s for s in plan.steps.values() if s.status == StepStatus.PENDING]
                    blocked = [s for s in plan.steps.values() if s.status == StepStatus.BLOCKED]

                    if pending and not blocked:
                        # All pending steps are actually ready
                        for step in pending:
                            step.status = StepStatus.READY
                        continue
                    elif blocked:
                        # Cannot proceed - steps are blocked
                        logger.warning(f"Plan execution blocked: {len(blocked)} steps blocked")
                        break
                    else:
                        # No more pending steps - execution complete
                        break

                # Execute ready steps (with parallelization support)
                parallel_groups = self._group_parallel_steps(ready_steps)

                for group in parallel_groups:
                    if len(group) == 1:
                        # Execute single step
                        result = await self._execute_step(plan, group[0])
                        if result['success']:
                            completed_count += 1
                        else:
                            failed_steps.append(group[0].step_id)
                    else:
                        # Execute parallel steps
                        results = await asyncio.gather(
                            *[self._execute_step(plan, step) for step in group],
                            return_exceptions=True
                        )
                        for i, result in enumerate(results):
                            if isinstance(result, Exception):
                                failed_steps.append(group[i].step_id)
                            elif result.get('success'):
                                completed_count += 1
                            else:
                                failed_steps.append(group[i].step_id)

                    # Checkpoint if needed
                    if completed_count % checkpoint_interval == 0:
                        plan.create_checkpoint({'completed_count': completed_count})
                        logger.debug(f"Checkpoint created at {completed_count} steps")

                    # Progress callback
                    if progress_callback:
                        await progress_callback(plan.get_progress())

            # Final status
            if failed_steps:
                plan.status = PlanStatus.FAILED
            else:
                plan.status = PlanStatus.COMPLETED

            plan.execution_completed_at = datetime.now().isoformat()

            # Calculate actual duration
            if plan.execution_started_at:
                start = datetime.fromisoformat(plan.execution_started_at)
                end = datetime.fromisoformat(plan.execution_completed_at)
                plan.actual_total_duration = (end - start).total_seconds()

            plan.save()

            return {
                'success': len(failed_steps) == 0,
                'completed_steps': completed_count,
                'failed_steps': failed_steps,
                'total_steps': len(plan.steps),
                'duration': plan.actual_total_duration
            }

        except Exception as e:
            logger.error(f"Plan execution failed: {e}")
            plan.status = PlanStatus.FAILED
            plan.save()
            raise

        finally:
            if plan.plan_id in self.executing_plans:
                del self.executing_plans[plan.plan_id]

    async def _execute_step(self, plan: Plan, step: PlanStep) -> Dict[str, Any]:
        """Execute a single step"""
        logger.info(f"Executing step {step.step_id}: {step.name}")

        step.status = StepStatus.EXECUTING
        step.started_at = datetime.now().isoformat()

        start_time = time.time()

        try:
            # Execute action
            if self.action_handler:
                result = await self.action_handler(step.action, step.arguments)
            else:
                # No handler - just mark as completed
                result = {'success': True, 'message': 'No action handler configured'}

            # Record duration
            step.actual_duration = time.time() - start_time

            # Check if action actually succeeded
            action_success = result.get('success', False) if isinstance(result, dict) else False

            if action_success:
                # Update step status
                plan.mark_step_completed(step.step_id, result)
                logger.info(f"Step {step.step_id} completed in {step.actual_duration:.2f}s")
                return {'success': True, 'result': result}
            else:
                # Action failed - treat like an exception for retry/fallback handling
                error_msg = result.get('error', 'Action returned failure') if isinstance(result, dict) else 'Unknown error'
                logger.warning(f"Step {step.step_id} action failed: {error_msg}")
                raise RuntimeError(error_msg)

        except Exception as e:
            logger.error(f"Step {step.step_id} failed: {e}")

            step.retry_count += 1

            # Retry if under limit
            if step.retry_count < step.max_retries:
                logger.info(f"Retrying step {step.step_id} ({step.retry_count}/{step.max_retries})")
                step.status = StepStatus.PENDING
                return await self._execute_step(plan, step)
            else:
                # Try fallback steps
                if step.fallback_steps:
                    logger.info(f"Attempting fallback for step {step.step_id}")
                    return await self._execute_fallback(plan, step)
                else:
                    # Mark as failed
                    plan.mark_step_failed(step.step_id, str(e))
                    return {'success': False, 'error': str(e)}

    async def _execute_fallback(self, plan: Plan, failed_step: PlanStep) -> Dict[str, Any]:
        """Execute fallback steps for a failed step"""
        for fallback_id in failed_step.fallback_steps:
            if fallback_id in plan.steps:
                fallback_step = plan.steps[fallback_id]
                logger.info(f"Executing fallback step {fallback_id}")

                result = await self._execute_step(plan, fallback_step)
                if result['success']:
                    # Fallback succeeded - mark original step as completed
                    plan.mark_step_completed(failed_step.step_id, result)
                    return result

        # All fallbacks failed
        plan.mark_step_failed(failed_step.step_id, "All fallbacks failed")
        return {'success': False, 'error': 'All fallbacks failed'}

    def _group_parallel_steps(self, steps: List[PlanStep]) -> List[List[PlanStep]]:
        """Group steps that can run in parallel"""
        groups = []
        parallel_steps = [s for s in steps if s.can_run_parallel()]
        sequential_steps = [s for s in steps if not s.can_run_parallel()]

        if parallel_steps:
            groups.append(parallel_steps)

        for step in sequential_steps:
            groups.append([step])

        return groups

    async def pause(self, plan_id: str):
        """Pause plan execution"""
        if plan_id in self.executing_plans:
            plan = self.executing_plans[plan_id]
            plan.status = PlanStatus.PAUSED
            plan.create_checkpoint({'action': 'paused'})
            logger.info(f"Plan {plan_id} paused")

    async def resume(self, plan_id: str):
        """Resume paused plan"""
        plan = Plan.load(plan_id)
        if plan and plan.status == PlanStatus.PAUSED:
            plan.status = PlanStatus.EXECUTING
            logger.info(f"Resuming plan {plan_id}")
            return await self.execute(plan)

    async def rollback(self, plan_id: str, checkpoint_index: int = -1):
        """Rollback plan to a checkpoint"""
        plan = Plan.load(plan_id)
        if not plan or not plan.checkpoints:
            return False

        checkpoint = plan.checkpoints[checkpoint_index]
        completed_steps = checkpoint['completed_steps']

        # Reset steps that came after checkpoint
        for step_id, step in plan.steps.items():
            if step_id not in completed_steps:
                step.status = StepStatus.PENDING
                step.result = None
                step.error = None
                step.retry_count = 0

        plan.save()
        logger.info(f"Plan {plan_id} rolled back to checkpoint {checkpoint_index}")
        return True


class PlanningAgent:
    """
    Main Hierarchical Task Network Planning Agent
    Orchestrates task analysis, decomposition, planning, validation, and execution
    """

    def __init__(self, action_handler: Optional[Callable] = None):
        self.critic = PlanCritic()
        self.executor = PlanExecutor(action_handler)
        self.templates: Dict[str, PlanTemplate] = {}
        self.plan_cache: Dict[str, Plan] = {}  # Cache for similar tasks

        # Load templates
        self._load_templates()

    def _load_templates(self):
        """Load plan templates from disk"""
        for template_file in TEMPLATES_DIR.glob("*.json"):
            template_id = template_file.stem
            template = PlanTemplate.load(template_id)
            if template:
                self.templates[template_id] = template

        logger.info(f"Loaded {len(self.templates)} plan templates")

    async def plan(
        self,
        task: str,
        context: Dict[str, Any] = None,
        max_depth: int = 3,
        use_templates: bool = True
    ) -> Plan:
        """
        Create a hierarchical plan for a task

        Pipeline:
        1. Task Analysis - Understand what needs to be done
        2. Resource Check - Verify required resources
        3. Template Matching - Check if template exists
        4. Decomposition - Break into hierarchical sub-tasks
        5. Dependency Graph - Build execution order
        6. Risk Assessment - Identify failure points
        7. Contingency Plans - Add fallbacks

        Args:
            task: Task description
            context: Additional context (files, data, etc.)
            max_depth: Maximum decomposition depth
            use_templates: Whether to use plan templates

        Returns:
            Plan ready for validation
        """
        logger.info(f"Planning task: {task}")

        context = context or {}

        # Step 1: Task Analysis
        task_analysis = await self._analyze_task(task, context)

        # Step 2: Resource Check
        resources = await self._check_resources(task_analysis)

        # Step 3: Template Matching
        if use_templates:
            template = self._find_matching_template(task_analysis)
            if template:
                logger.info(f"Using template: {template.name}")
                plan = template.instantiate({
                    'plan_name': task,
                    'task': task,
                    **context
                })
                plan.resource_requirements = resources
                return plan

        # Step 4: Hierarchical Decomposition
        plan_id = hashlib.md5(f"{task}_{datetime.now().isoformat()}".encode()).hexdigest()[:16]
        plan = Plan(
            plan_id=plan_id,
            name=task,
            description=task_analysis.get('description', task),
            resource_requirements=resources
        )

        await self._decompose_task(plan, task, task_analysis, depth=0, max_depth=max_depth)

        # Step 5: Build Dependency Graph
        self._build_dependencies(plan)

        # Step 6: Risk Assessment
        await self._assess_risks(plan)

        # Step 7: Add Contingency Plans
        await self._add_contingencies(plan)

        # Estimate total duration
        plan.estimated_total_duration = sum(s.estimated_duration for s in plan.steps.values())

        plan.save()

        logger.info(
            f"Created plan with {len(plan.steps)} steps, "
            f"depth {max((s.depth for s in plan.steps.values()), default=0)}"
        )

        return plan

    async def _analyze_task(self, task: str, context: Dict) -> Dict[str, Any]:
        """Analyze task to understand requirements"""
        # Extract key information from task
        task_lower = task.lower()

        analysis = {
            'description': task,
            'type': 'generic',
            'complexity': 'medium',
            'requires_browser': False,
            'requires_api': False,
            'requires_files': False,
            'estimated_steps': 5
        }

        # Detect task type
        if any(kw in task_lower for kw in ['research', 'find', 'search', 'look up']):
            analysis['type'] = 'research'
            analysis['requires_browser'] = True
            analysis['estimated_steps'] = 8
        elif any(kw in task_lower for kw in ['extract', 'scrape', 'collect']):
            analysis['type'] = 'extraction'
            analysis['requires_browser'] = True
            analysis['estimated_steps'] = 6
        elif any(kw in task_lower for kw in ['clean', 'process', 'transform']):
            analysis['type'] = 'processing'
            analysis['requires_files'] = True
            analysis['estimated_steps'] = 4
        elif any(kw in task_lower for kw in ['monitor', 'watch', 'track']):
            analysis['type'] = 'monitoring'
            analysis['complexity'] = 'high'
            analysis['estimated_steps'] = 10

        # Detect complexity
        if any(kw in task_lower for kw in ['complex', 'multiple', 'all', 'every']):
            analysis['complexity'] = 'high'
            analysis['estimated_steps'] *= 2
        elif any(kw in task_lower for kw in ['simple', 'quick', 'just']):
            analysis['complexity'] = 'low'
            analysis['estimated_steps'] = max(3, analysis['estimated_steps'] // 2)

        return analysis

    async def _check_resources(self, task_analysis: Dict) -> List[Resource]:
        """Check and allocate required resources"""
        resources = []

        if task_analysis.get('requires_browser'):
            resources.append(Resource(
                resource_type='browser',
                name='playwright',
                required=True,
                available=True  # Assume available for now
            ))

        if task_analysis.get('requires_files'):
            resources.append(Resource(
                resource_type='file',
                name='filesystem',
                required=True,
                available=True
            ))

        if task_analysis.get('requires_api'):
            resources.append(Resource(
                resource_type='api',
                name='external_api',
                required=True,
                available=False  # Need to check
            ))

        # Always need memory and CPU
        resources.extend([
            Resource(resource_type='memory', name='working_memory', required=True, available=True),
            Resource(resource_type='cpu', name='compute', required=True, available=True)
        ])

        return resources

    def _find_matching_template(self, task_analysis: Dict) -> Optional[PlanTemplate]:
        """Find matching plan template for task"""
        task_type = task_analysis.get('type', 'generic')

        # Look for templates matching task type
        for template in self.templates.values():
            if task_type in template.category.lower():
                return template

        return None

    async def _decompose_task(
        self,
        plan: Plan,
        task: str,
        analysis: Dict,
        parent_id: Optional[str] = None,
        depth: int = 0,
        max_depth: int = 3
    ):
        """Recursively decompose task into hierarchical steps"""
        if depth >= max_depth:
            # Hit max depth - create primitive step
            step_id = f"{plan.plan_id}_step_{len(plan.steps)}"
            step = PlanStep(
                step_id=step_id,
                name=task[:50],
                description=task,
                task_type=TaskType.PRIMITIVE,
                action="execute_task",
                arguments={'task': task},
                parent_id=parent_id,
                depth=depth,
                estimated_duration=30.0  # Default 30s
            )
            plan.steps[step_id] = step

            if parent_id:
                plan.steps[parent_id].children.append(step_id)
            else:
                plan.root_steps.append(step_id)

            return

        # Decompose based on task type
        task_type = analysis.get('type', 'generic')

        if task_type == 'research':
            await self._decompose_research_task(plan, task, parent_id, depth, max_depth)
        elif task_type == 'extraction':
            await self._decompose_extraction_task(plan, task, parent_id, depth, max_depth)
        elif task_type == 'processing':
            await self._decompose_processing_task(plan, task, parent_id, depth, max_depth)
        elif task_type == 'monitoring':
            await self._decompose_monitoring_task(plan, task, parent_id, depth, max_depth)
        else:
            await self._decompose_generic_task(plan, task, parent_id, depth, max_depth)

    async def _decompose_research_task(
        self, plan: Plan, task: str, parent_id: Optional[str], depth: int, max_depth: int
    ):
        """Decompose research task"""
        # Create composite step for research
        composite_id = f"{plan.plan_id}_step_{len(plan.steps)}"
        composite = PlanStep(
            step_id=composite_id,
            name="Research Task",
            description=task,
            task_type=TaskType.COMPOSITE,
            action="research",
            parent_id=parent_id,
            depth=depth
        )
        plan.steps[composite_id] = composite

        if parent_id:
            plan.steps[parent_id].children.append(composite_id)
        else:
            plan.root_steps.append(composite_id)

        # Decompose into sub-steps
        sub_tasks = [
            ("Navigate to target", "navigate", 15.0),
            ("Search for information", "search", 30.0),
            ("Extract relevant data", "extract", 45.0),
            ("Verify accuracy", "verify", 20.0),
            ("Save results", "save_results", 10.0)
        ]

        for name, action, duration in sub_tasks:
            step_id = f"{plan.plan_id}_step_{len(plan.steps)}"
            step = PlanStep(
                step_id=step_id,
                name=name,
                description=f"{name} for: {task}",
                task_type=TaskType.SEQUENTIAL,
                action=action,
                arguments={'task': task},
                parent_id=composite_id,
                depth=depth + 1,
                estimated_duration=duration
            )
            plan.steps[step_id] = step
            composite.children.append(step_id)

    async def _decompose_extraction_task(
        self, plan: Plan, task: str, parent_id: Optional[str], depth: int, max_depth: int
    ):
        """Decompose data extraction task"""
        composite_id = f"{plan.plan_id}_step_{len(plan.steps)}"
        composite = PlanStep(
            step_id=composite_id,
            name="Data Extraction",
            description=task,
            task_type=TaskType.COMPOSITE,
            action="extract",
            parent_id=parent_id,
            depth=depth
        )
        plan.steps[composite_id] = composite

        if parent_id:
            plan.steps[parent_id].children.append(composite_id)
        else:
            plan.root_steps.append(composite_id)

        sub_tasks = [
            ("Prepare extraction", "prepare", 10.0),
            ("Extract data batch 1", "extract_batch", 60.0),
            ("Extract data batch 2", "extract_batch", 60.0),
            ("Validate extracted data", "validate", 30.0),
            ("Export to file", "export", 15.0)
        ]

        for name, action, duration in sub_tasks:
            step_id = f"{plan.plan_id}_step_{len(plan.steps)}"
            step = PlanStep(
                step_id=step_id,
                name=name,
                description=f"{name} for: {task}",
                task_type=TaskType.PARALLEL if "batch" in name else TaskType.SEQUENTIAL,
                action=action,
                arguments={'task': task},
                parent_id=composite_id,
                depth=depth + 1,
                estimated_duration=duration
            )
            plan.steps[step_id] = step
            composite.children.append(step_id)

    async def _decompose_processing_task(
        self, plan: Plan, task: str, parent_id: Optional[str], depth: int, max_depth: int
    ):
        """Decompose data processing task"""
        composite_id = f"{plan.plan_id}_step_{len(plan.steps)}"
        composite = PlanStep(
            step_id=composite_id,
            name="Data Processing",
            description=task,
            task_type=TaskType.COMPOSITE,
            action="process",
            parent_id=parent_id,
            depth=depth
        )
        plan.steps[composite_id] = composite

        if parent_id:
            plan.steps[parent_id].children.append(composite_id)
        else:
            plan.root_steps.append(composite_id)

        sub_tasks = [
            ("Load data", "load", 10.0),
            ("Clean data", "clean", 30.0),
            ("Transform data", "transform", 40.0),
            ("Validate output", "validate", 20.0),
            ("Save processed data", "save", 10.0)
        ]

        for name, action, duration in sub_tasks:
            step_id = f"{plan.plan_id}_step_{len(plan.steps)}"
            step = PlanStep(
                step_id=step_id,
                name=name,
                description=f"{name} for: {task}",
                task_type=TaskType.SEQUENTIAL,
                action=action,
                arguments={'task': task},
                parent_id=composite_id,
                depth=depth + 1,
                estimated_duration=duration
            )
            plan.steps[step_id] = step
            composite.children.append(step_id)

    async def _decompose_monitoring_task(
        self, plan: Plan, task: str, parent_id: Optional[str], depth: int, max_depth: int
    ):
        """Decompose monitoring task"""
        composite_id = f"{plan.plan_id}_step_{len(plan.steps)}"
        composite = PlanStep(
            step_id=composite_id,
            name="Monitoring Task",
            description=task,
            task_type=TaskType.COMPOSITE,
            action="monitor",
            parent_id=parent_id,
            depth=depth
        )
        plan.steps[composite_id] = composite

        if parent_id:
            plan.steps[parent_id].children.append(composite_id)
        else:
            plan.root_steps.append(composite_id)

        sub_tasks = [
            ("Initialize monitoring", "init_monitor", 15.0),
            ("Collect metrics", "collect", 120.0),
            ("Analyze patterns", "analyze", 60.0),
            ("Detect anomalies", "detect_anomalies", 45.0),
            ("Generate alerts", "alert", 20.0),
            ("Create report", "report", 30.0)
        ]

        for name, action, duration in sub_tasks:
            step_id = f"{plan.plan_id}_step_{len(plan.steps)}"
            step = PlanStep(
                step_id=step_id,
                name=name,
                description=f"{name} for: {task}",
                task_type=TaskType.SEQUENTIAL,
                action=action,
                arguments={'task': task},
                parent_id=composite_id,
                depth=depth + 1,
                estimated_duration=duration
            )
            plan.steps[step_id] = step
            composite.children.append(step_id)

    async def _decompose_generic_task(
        self, plan: Plan, task: str, parent_id: Optional[str], depth: int, max_depth: int
    ):
        """Decompose generic task"""
        composite_id = f"{plan.plan_id}_step_{len(plan.steps)}"
        composite = PlanStep(
            step_id=composite_id,
            name="Generic Task",
            description=task,
            task_type=TaskType.COMPOSITE,
            action="execute",
            parent_id=parent_id,
            depth=depth
        )
        plan.steps[composite_id] = composite

        if parent_id:
            plan.steps[parent_id].children.append(composite_id)
        else:
            plan.root_steps.append(composite_id)

        # Simple decomposition
        sub_tasks = [
            ("Prepare", "prepare", 10.0),
            ("Execute main task", "execute", 60.0),
            ("Verify results", "verify", 20.0),
            ("Finalize", "finalize", 10.0)
        ]

        for name, action, duration in sub_tasks:
            step_id = f"{plan.plan_id}_step_{len(plan.steps)}"
            step = PlanStep(
                step_id=step_id,
                name=name,
                description=f"{name} for: {task}",
                task_type=TaskType.SEQUENTIAL,
                action=action,
                arguments={'task': task},
                parent_id=composite_id,
                depth=depth + 1,
                estimated_duration=duration
            )
            plan.steps[step_id] = step
            composite.children.append(step_id)

    def _build_dependencies(self, plan: Plan):
        """Build dependency graph between steps"""
        # Build dependencies based on parent-child relationships
        for step_id, step in plan.steps.items():
            if step.parent_id and step.parent_id in plan.steps:
                parent = plan.steps[step.parent_id]

                # If parent has multiple children, make them depend on previous sibling
                # (except for parallel tasks)
                if len(parent.children) > 1 and step.task_type == TaskType.SEQUENTIAL:
                    step_index = parent.children.index(step_id)
                    if step_index > 0:
                        prev_sibling = parent.children[step_index - 1]
                        step.depends_on.append(prev_sibling)

    async def _assess_risks(self, plan: Plan):
        """Assess risks in the plan"""
        # Identify high-risk steps
        for step in plan.steps.values():
            risk_factors = []

            # Browser operations are risky
            if 'navigate' in step.action or 'browser' in step.action:
                risk_factors.append('browser_dependency')

            # External API calls are risky
            if 'api' in step.action or 'external' in step.action:
                risk_factors.append('external_dependency')

            # Complex extraction is risky
            if step.task_type == TaskType.COMPOSITE and 'extract' in step.action:
                risk_factors.append('complex_extraction')

            # Store risk factors in metadata
            if risk_factors:
                step.metadata['risk_factors'] = risk_factors
                step.max_retries = 5  # Increase retries for risky steps

    async def _add_contingencies(self, plan: Plan):
        """Add fallback plans for risky steps"""
        # Create list of steps to avoid modifying dict during iteration
        steps_to_process = list(plan.steps.values())

        for step in steps_to_process:
            risk_factors = step.metadata.get('risk_factors', [])

            if 'browser_dependency' in risk_factors:
                # Add screenshot fallback
                fallback_id = f"{plan.plan_id}_fallback_{len(plan.steps)}"
                fallback = PlanStep(
                    step_id=fallback_id,
                    name=f"Fallback: {step.name}",
                    description=f"Alternative approach for {step.name}",
                    task_type=TaskType.PRIMITIVE,
                    action="screenshot_fallback",
                    arguments=step.arguments.copy(),
                    parent_id=step.parent_id,
                    depth=step.depth
                )
                plan.steps[fallback_id] = fallback
                step.fallback_steps.append(fallback_id)

    async def validate_plan(self, plan: Plan) -> Dict[str, Any]:
        """
        Validate plan using critic agent

        Returns validation results with approval decision
        """
        logger.info(f"Validating plan {plan.plan_id}")

        evaluation = await self.critic.evaluate(plan)

        if evaluation['approved']:
            plan.status = PlanStatus.VALIDATED
            plan.validated_at = datetime.now().isoformat()
            logger.info(f"Plan {plan.plan_id} validated (score: {evaluation['overall_score']:.2f})")
        else:
            logger.warning(
                f"Plan {plan.plan_id} validation failed (score: {evaluation['overall_score']:.2f})"
            )

        plan.save()

        return evaluation

    async def approve_plan(self, plan: Plan, user_approval: bool = True):
        """
        Approve plan for execution (optionally require user approval)
        """
        if plan.status != PlanStatus.VALIDATED:
            raise ValueError("Plan must be validated before approval")

        if user_approval:
            # In production, this would prompt user
            logger.info(f"Plan {plan.plan_id} approved by user")

        plan.status = PlanStatus.APPROVED
        plan.approved_at = datetime.now().isoformat()
        plan.save()

    async def execute_plan(
        self,
        plan: Plan,
        checkpoint_interval: int = 5,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Execute an approved plan
        """
        if plan.status not in [PlanStatus.APPROVED, PlanStatus.PAUSED]:
            raise ValueError(f"Cannot execute plan in status {plan.status}")

        return await self.executor.execute(plan, checkpoint_interval, progress_callback)

    async def replan(
        self,
        original_plan: Plan,
        failed_step_id: str,
        partial: bool = True
    ) -> Plan:
        """
        Create new plan to recover from failure

        Args:
            original_plan: Plan that failed
            failed_step_id: ID of step that failed
            partial: If True, only replan failed portion. If False, replan entire task
        """
        logger.info(f"Replanning after failure at step {failed_step_id}")

        if not partial:
            # Full replan - create entirely new plan
            return await self.plan(
                original_plan.description,
                context=original_plan.metadata
            )

        # Partial replan - only revise affected portion
        failed_step = original_plan.steps[failed_step_id]

        # Create new plan for failed subtree
        new_plan_id = f"{original_plan.plan_id}_replan_{len(original_plan.checkpoints)}"
        new_plan = Plan(
            plan_id=new_plan_id,
            name=f"Replan: {failed_step.name}",
            description=failed_step.description,
            parent_plan_id=original_plan.plan_id,
            version=original_plan.version + 1
        )

        # Decompose failed step into new approach
        await self._decompose_task(
            new_plan,
            failed_step.description,
            {'type': 'generic', 'complexity': 'medium'},
            depth=0,
            max_depth=2
        )

        self._build_dependencies(new_plan)
        await self._assess_risks(new_plan)
        await self._add_contingencies(new_plan)

        new_plan.save()

        return new_plan

    def create_template(
        self,
        name: str,
        description: str,
        category: str,
        plan: Plan
    ) -> PlanTemplate:
        """
        Create a reusable template from a successful plan
        """
        template_id = hashlib.md5(f"{name}_{category}".encode()).hexdigest()[:16]

        # Extract step templates
        step_templates = []
        for step in plan.steps.values():
            step_template = {
                'template_id': step.step_id.split('_')[-1],
                'name': step.name,
                'description': step.description,
                'task_type': step.task_type.value,
                'action': step.action,
                'arguments': step.arguments,
                'depth': step.depth,
                'estimated_duration': step.actual_duration or step.estimated_duration,
                'max_retries': step.max_retries
            }

            # Add relationships
            if step.parent_id:
                step_template['parent_id'] = step.parent_id.split('_')[-1]
            if step.depends_on:
                step_template['depends_on'] = [d.split('_')[-1] for d in step.depends_on]

            step_templates.append(step_template)

        template = PlanTemplate(
            template_id=template_id,
            name=name,
            description=description,
            category=category,
            step_templates=step_templates,
            avg_duration=plan.actual_total_duration
        )

        template.save()
        self.templates[template_id] = template

        logger.info(f"Created template {name} ({template_id})")

        return template

    def get_plan_summary(self, plan: Plan) -> str:
        """Get human-readable plan summary"""
        lines = [
            f"Plan: {plan.name}",
            f"Status: {plan.status.value}",
            f"Steps: {len(plan.steps)}",
            f"Estimated duration: {plan.estimated_total_duration:.0f}s",
        ]

        if plan.critic_score > 0:
            lines.append(f"Quality score: {plan.critic_score:.2f}")

        progress = plan.get_progress()
        if progress['total'] > 0:
            lines.append(
                f"Progress: {progress['completed']}/{progress['total']} "
                f"({progress['percent']:.0f}%)"
            )

        return "\n".join(lines)


# Singleton instance
planning_agent = PlanningAgent()


# Example usage and helper functions
async def quick_plan_and_execute(task: str, action_handler: Callable = None) -> Dict:
    """
    Quick helper to plan, validate, and execute a task
    """
    agent = PlanningAgent(action_handler)

    # Create plan
    plan = await agent.plan(task)

    # Validate
    evaluation = await agent.validate_plan(plan)

    if not evaluation['approved']:
        return {
            'success': False,
            'error': 'Plan validation failed',
            'evaluation': evaluation
        }

    # Auto-approve
    await agent.approve_plan(plan, user_approval=False)

    # Execute
    result = await agent.execute_plan(plan)

    return {
        'success': result['success'],
        'plan': plan,
        'evaluation': evaluation,
        'execution': result
    }


if __name__ == "__main__":
    # Example: Create and save some default templates

    # SDR Lead Generation Template
    sdr_template = PlanTemplate(
        template_id="sdr_lead_gen",
        name="SDR Lead Generation",
        description="Generate sales leads from target sources",
        category="SDR",
        required_params=['target_keyword', 'source'],
        optional_params=['max_leads', 'output_file'],
        step_templates=[
            {
                'template_id': 0,
                'name': "Navigate to source",
                'description': "Open target website",
                'task_type': 'primitive',
                'action': 'playwright_navigate',
                'arguments': {'url': '${source}'},
                'depth': 0,
                'estimated_duration': 10.0,
                'max_retries': 3
            },
            {
                'template_id': 1,
                'name': "Search for keyword",
                'description': "Search for target keyword",
                'task_type': 'sequential',
                'action': 'playwright_fill_and_submit',
                'arguments': {'keyword': '${target_keyword}'},
                'depends_on': [0],
                'depth': 0,
                'estimated_duration': 15.0,
                'max_retries': 3
            },
            {
                'template_id': 2,
                'name': "Extract leads",
                'description': "Extract contact information",
                'task_type': 'parallel',
                'action': 'playwright_extract_contacts',
                'arguments': {},
                'depends_on': [1],
                'depth': 0,
                'estimated_duration': 60.0,
                'max_retries': 5
            },
            {
                'template_id': 3,
                'name': "Save results",
                'description': "Export leads to file",
                'task_type': 'primitive',
                'action': 'save_to_csv',
                'arguments': {'output': '${output_file}'},
                'depends_on': [2],
                'depth': 0,
                'estimated_duration': 5.0,
                'max_retries': 2
            }
        ]
    )
    sdr_template.save()

    print(f"Created SDR template: {sdr_template.template_id}")
