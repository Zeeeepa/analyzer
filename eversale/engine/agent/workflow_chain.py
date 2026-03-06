from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


class ChainCondition(Enum):
    ALWAYS = "always"
    ON_SUCCESS = "on_success"
    ON_FAILURE = "on_failure"
    IF_CONTAINS = "if_contains"
    IF_NOT_EMPTY = "if_not_empty"


@dataclass
class DataMapping:
    """Maps output from one workflow to input of another."""
    source_workflow: str
    source_output: str  # e.g., "extracted_email", "result.data[0].name"
    target_variable: str


@dataclass
class ChainStep:
    workflow_id: str
    condition: ChainCondition
    condition_value: Optional[str] = None  # For IF_CONTAINS
    data_mappings: Optional[List[DataMapping]] = None
    on_error: str = "stop"  # "stop", "continue", "retry"


@dataclass
class WorkflowChain:
    id: str
    name: str
    description: str
    steps: List[ChainStep]
    global_variables: Dict[str, str] = field(default_factory=dict)
    max_iterations: int = 1  # For loops


@dataclass
class ChainResult:
    success: bool
    context: Dict[str, Any]
    failed_at: Optional[str] = None
    total_workflows: int = 0
    successful_workflows: int = 0


class WorkflowChainExecutor:
    """
    Executes chains of workflows with data passing and conditional logic.
    """

    def __init__(self, workflow_executor, workflow_store: Dict[str, Any]):
        self.executor = workflow_executor
        self.workflows = workflow_store
        self.execution_context: Dict[str, Any] = {}

    async def execute_chain(self, chain: WorkflowChain,
                            initial_variables: Dict[str, str]) -> ChainResult:
        """Execute workflow chain with data passing."""

        self.execution_context = {
            'variables': {**chain.global_variables, **initial_variables},
            'outputs': {},
            'step_results': []
        }

        for iteration in range(chain.max_iterations):
            for step in chain.steps:
                # Check condition
                if not self._check_condition(step):
                    continue

                # Get workflow
                workflow = self.workflows.get(step.workflow_id)
                if not workflow:
                    raise ValueError(f"Workflow not found: {step.workflow_id}")

                # Map data from previous outputs
                step_variables = self._map_data(step)

                # Merge with context variables
                final_variables = {
                    **self.execution_context['variables'],
                    **step_variables
                }

                # Execute
                try:
                    result = await self.executor.execute(workflow, final_variables)

                    # Store outputs
                    self.execution_context['outputs'][step.workflow_id] = {
                        'success': result.success,
                        'data': getattr(result, 'extracted_data', {}),
                        'duration': getattr(result, 'duration', 0)
                    }
                    self.execution_context['step_results'].append({
                        'workflow': step.workflow_id,
                        'success': result.success,
                        'iteration': iteration
                    })

                    if not result.success and step.on_error == 'stop':
                        return ChainResult(
                            success=False,
                            failed_at=step.workflow_id,
                            context=self.execution_context
                        )

                except Exception as e:
                    if step.on_error == 'stop':
                        raise
                    elif step.on_error == 'retry':
                        # Retry once
                        result = await self.executor.execute(workflow, final_variables)

        return ChainResult(
            success=True,
            context=self.execution_context,
            total_workflows=len(chain.steps),
            successful_workflows=len([
                r for r in self.execution_context['step_results']
                if r['success']
            ])
        )

    def _check_condition(self, step: ChainStep) -> bool:
        """Check if step condition is met."""
        if step.condition == ChainCondition.ALWAYS:
            return True

        if step.condition == ChainCondition.ON_SUCCESS:
            # Check previous step succeeded
            if self.execution_context['step_results']:
                return self.execution_context['step_results'][-1]['success']
            return True

        if step.condition == ChainCondition.ON_FAILURE:
            if self.execution_context['step_results']:
                return not self.execution_context['step_results'][-1]['success']
            return False

        if step.condition == ChainCondition.IF_CONTAINS:
            # Check if output contains value
            for output in self.execution_context['outputs'].values():
                if step.condition_value in str(output.get('data', '')):
                    return True
            return False

        if step.condition == ChainCondition.IF_NOT_EMPTY:
            # Check if specified output is not empty
            output = self.execution_context['outputs'].get(step.condition_value, {})
            return bool(output.get('data'))

        return True

    def _map_data(self, step: ChainStep) -> Dict[str, str]:
        """Map data from previous workflow outputs."""
        mapped = {}

        if not step.data_mappings:
            return mapped

        for mapping in step.data_mappings:
            source = self.execution_context['outputs'].get(mapping.source_workflow, {})

            # Navigate to source output (supports dot notation)
            value = source.get('data', {})
            for key in mapping.source_output.split('.'):
                if isinstance(value, dict):
                    value = value.get(key, '')
                elif isinstance(value, list) and key.isdigit():
                    value = value[int(key)] if int(key) < len(value) else ''
                else:
                    value = ''
                    break

            mapped[mapping.target_variable] = str(value)

        return mapped


# Example chain definition
EXAMPLE_CHAIN = WorkflowChain(
    id="lead_enrichment_chain",
    name="Lead Enrichment Pipeline",
    description="Find lead on LinkedIn, extract email, send outreach",
    steps=[
        ChainStep(
            workflow_id="linkedin_search",
            condition=ChainCondition.ALWAYS,
            data_mappings=[]
        ),
        ChainStep(
            workflow_id="extract_email",
            condition=ChainCondition.ON_SUCCESS,
            data_mappings=[
                DataMapping(
                    source_workflow="linkedin_search",
                    source_output="profile_url",
                    target_variable="linkedin_url"
                )
            ]
        ),
        ChainStep(
            workflow_id="send_email",
            condition=ChainCondition.IF_NOT_EMPTY,
            condition_value="extract_email",
            data_mappings=[
                DataMapping(
                    source_workflow="extract_email",
                    source_output="email",
                    target_variable="recipient_email"
                ),
                DataMapping(
                    source_workflow="linkedin_search",
                    source_output="name",
                    target_variable="recipient_name"
                )
            ]
        )
    ],
    global_variables={
        "sender_name": "{{user.name}}",
        "company": "{{user.company}}"
    }
)
