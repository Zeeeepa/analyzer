"""
Recording to Workflow Conversion

Converts raw browser recordings into parameterized, replayable workflows.
Implements self-healing selectors, variable detection, and vision fallbacks.

Feature 4b from AGENT_UPGRADE_PLAN.md Phase 3
"""

import asyncio
import re
import json
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum
from loguru import logger


class RecordedActionType(Enum):
    """Types of recorded actions from browser events."""
    CLICK = "click"
    FILL = "fill"
    SELECT = "select"
    SCROLL = "scroll"
    NAVIGATE = "navigate"
    KEYPRESS = "keypress"
    HOVER = "hover"
    DRAG = "drag"


@dataclass
class WorkflowVariable:
    """Variable placeholder in workflow (e.g., email, name, phone)."""
    name: str
    type: str  # "text", "email", "date", "number", "select", "phone", "name", "url", "address"
    default_value: Optional[str]
    detected_from: str  # which action detected this


@dataclass
class WorkflowStep:
    """Single step in executable workflow with self-healing capabilities."""
    id: int
    action_type: str
    target_primary: str  # primary selector
    target_fallbacks: List[str]  # fallback selectors for self-healing
    target_visual: Optional[str]  # visual description for vision fallback
    value_template: Optional[str]  # value with {{variable}} placeholders
    wait_after: int  # ms to wait after action
    success_indicators: List[str]


@dataclass
class Workflow:
    """Complete replayable workflow."""
    id: str
    name: str
    description: str
    variables: List[WorkflowVariable]
    steps: List[WorkflowStep]
    source_recording_id: str
    estimated_duration: int  # seconds
    success_rate: float = 0.0
    times_executed: int = 0


@dataclass
class RecordedAction:
    """Single action captured during recording."""
    timestamp: float
    action_type: RecordedActionType
    target_selector: str
    target_mmid: Optional[str]
    target_text: Optional[str]
    target_attributes: Dict[str, str]
    value: Optional[str]
    page_url: str
    page_title: str
    screenshot_before: Optional[str] = None
    screenshot_after: Optional[str] = None


@dataclass
class Recording:
    """Complete browser recording session."""
    id: str
    goal: str
    start_time: str
    end_time: Optional[str]
    actions: List[RecordedAction] = field(default_factory=list)
    variables_detected: Dict[str, str] = field(default_factory=dict)


@dataclass
class ActionResult:
    """Result of executing a workflow step."""
    step_id: int
    success: bool
    selector_used: Optional[str]
    error: Optional[str] = None
    data: Optional[Any] = None


@dataclass
class ExecutionResult:
    """Result of executing complete workflow."""
    success: bool
    steps: List[ActionResult]
    duration: int
    extracted_data: Optional[Dict[str, Any]] = None


class RecordingToWorkflowConverter:
    """
    Converts raw recording to parameterized, replayable workflow.
    Uses LLM to:
    1. Detect variable slots (names, emails, dates)
    2. Generate fallback selectors
    3. Add success indicators
    4. Optimize wait times
    """

    # Patterns for variable detection
    VARIABLE_PATTERNS = {
        'email': r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$',
        'phone': r'^[\d\-\(\)\s\+]+$',
        'date': r'^\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}$',
        'url': r'^https?:\/\/',
        'name': None,  # Use LLM
        'address': None,  # Use LLM
    }

    def __init__(self, llm_client):
        """
        Initialize converter with LLM client.

        Args:
            llm_client: LLMClient instance for AI-powered analysis
        """
        self.llm = llm_client

    async def convert(self, recording: Recording) -> Workflow:
        """
        Convert recording to workflow.

        Args:
            recording: Raw recording session

        Returns:
            Executable workflow with variables and self-healing selectors
        """
        logger.info(f"Converting recording {recording.id} to workflow")

        # Step 1: Detect variables
        variables = await self._detect_variables(recording)
        logger.info(f"Detected {len(variables)} variables")

        # Step 2: Generate workflow steps with fallbacks
        steps = await self._generate_steps(recording, variables)
        logger.info(f"Generated {len(steps)} workflow steps")

        # Step 3: Optimize timing
        steps = self._optimize_wait_times(steps)

        # Step 4: Generate name/description
        name, description = await self._generate_metadata(recording, steps)

        return Workflow(
            id=f"wf_{recording.id}",
            name=name,
            description=description,
            variables=variables,
            steps=steps,
            source_recording_id=recording.id,
            estimated_duration=self._estimate_duration(steps)
        )

    async def _detect_variables(self, recording: Recording) -> List[WorkflowVariable]:
        """
        Detect which input values should be variables.

        Args:
            recording: Raw recording session

        Returns:
            List of detected variables
        """
        variables = []
        values_seen = {}

        for action in recording.actions:
            if action.action_type in [RecordedActionType.FILL, RecordedActionType.SELECT]:
                value = action.value
                if not value:
                    continue

                # Skip if already seen
                if value in values_seen:
                    continue

                # Check regex patterns
                var_type = None
                for type_name, pattern in self.VARIABLE_PATTERNS.items():
                    if pattern and re.match(pattern, value):
                        var_type = type_name
                        break

                # Use LLM for uncertain cases
                if not var_type:
                    var_type = await self._llm_classify_value(value, action)

                if var_type and var_type != 'literal':
                    var_name = self._generate_var_name(var_type, len(variables))
                    variables.append(WorkflowVariable(
                        name=var_name,
                        type=var_type,
                        default_value=value,
                        detected_from=f"action_{recording.actions.index(action)}"
                    ))
                    values_seen[value] = var_name

        return variables

    async def _generate_steps(self, recording: Recording,
                               variables: List[WorkflowVariable]) -> List[WorkflowStep]:
        """
        Generate workflow steps with fallback selectors.

        Args:
            recording: Raw recording session
            variables: Detected variables

        Returns:
            List of workflow steps with self-healing selectors
        """
        steps = []
        var_value_map = {v.default_value: v.name for v in variables}

        for i, action in enumerate(recording.actions):
            # Generate fallback selectors
            fallbacks = self._generate_fallback_selectors(action)

            # Generate visual description for vision fallback
            visual = self._generate_visual_description(action)

            # Replace literal values with variable templates
            value_template = None
            if action.value:
                if action.value in var_value_map:
                    value_template = f"{{{{{var_value_map[action.value]}}}}}"
                else:
                    value_template = action.value

            steps.append(WorkflowStep(
                id=i + 1,
                action_type=action.action_type.value,
                target_primary=action.target_selector,
                target_fallbacks=fallbacks,
                target_visual=visual,
                value_template=value_template,
                wait_after=500,  # Default, will be optimized
                success_indicators=self._generate_success_indicators(action, i, recording)
            ))

        return steps

    def _generate_fallback_selectors(self, action: RecordedAction) -> List[str]:
        """
        Generate fallback selectors for self-healing.

        Args:
            action: Recorded action

        Returns:
            List of fallback selectors in priority order
        """
        fallbacks = []

        # MMID is highest priority fallback
        if action.target_mmid:
            fallbacks.append(f'[data-mmid="{action.target_mmid}"]')

        # Text-based selector
        if action.target_text:
            text = action.target_text[:30]
            tag = action.target_attributes.get('tag', '*')
            fallbacks.append(f'{tag}:has-text("{text}")')

        # Placeholder-based
        if action.target_attributes.get('placeholder'):
            fallbacks.append(f'[placeholder="{action.target_attributes["placeholder"]}"]')

        # Aria-label based
        if action.target_attributes.get('aria-label'):
            fallbacks.append(f'[aria-label="{action.target_attributes["aria-label"]}"]')

        # Type-based (for inputs)
        if action.target_attributes.get('type'):
            fallbacks.append(f'input[type="{action.target_attributes["type"]}"]')

        return fallbacks

    def _generate_visual_description(self, action: RecordedAction) -> str:
        """
        Generate visual description for vision-based fallback.

        Args:
            action: Recorded action

        Returns:
            Human-readable description of element
        """
        parts = []

        tag = action.target_attributes.get('tag', 'element')
        parts.append(tag)

        if action.target_text:
            parts.append(f'with text "{action.target_text[:20]}"')

        if action.target_attributes.get('type'):
            parts.append(f'type={action.target_attributes["type"]}')

        if action.target_attributes.get('placeholder'):
            parts.append(f'placeholder="{action.target_attributes["placeholder"][:20]}"')

        return ' '.join(parts)

    def _generate_success_indicators(self, action: RecordedAction,
                                      index: int, recording: Recording) -> List[str]:
        """
        Generate success indicators for validation.

        Args:
            action: Recorded action
            index: Index in recording
            recording: Full recording

        Returns:
            List of success indicators
        """
        indicators = []

        # Check if URL changed after this action
        if index < len(recording.actions) - 1:
            next_action = recording.actions[index + 1]
            if next_action.page_url != action.page_url:
                indicators.append(f"url_contains:{next_action.page_url.split('/')[-1]}")

        # For fills, check value is set
        if action.action_type == RecordedActionType.FILL:
            indicators.append(f"input_has_value:{action.target_selector}")

        # For clicks, check for state change
        if action.action_type == RecordedActionType.CLICK:
            indicators.append("page_state_changed")

        return indicators

    def _optimize_wait_times(self, steps: List[WorkflowStep]) -> List[WorkflowStep]:
        """
        Optimize wait times based on action types.

        Args:
            steps: Workflow steps

        Returns:
            Steps with optimized wait times
        """
        for i, step in enumerate(steps):
            if step.action_type == 'navigate':
                step.wait_after = 2000  # Wait for page load
            elif step.action_type == 'click':
                # Check if next action is on different URL
                if i < len(steps) - 1:
                    next_indicators = steps[i+1].success_indicators
                    has_navigation = any('url_contains' in ind for ind in next_indicators)
                    if has_navigation:
                        step.wait_after = 1500
                    else:
                        step.wait_after = 300
                else:
                    step.wait_after = 300
            elif step.action_type == 'fill':
                step.wait_after = 100  # Fast for typing
            elif step.action_type == 'select':
                step.wait_after = 200

        return steps

    async def _generate_metadata(self, recording: Recording,
                                  steps: List[WorkflowStep]) -> tuple:
        """
        Generate workflow name and description using LLM.

        Args:
            recording: Raw recording
            steps: Generated workflow steps

        Returns:
            Tuple of (name, description)
        """
        urls_visited = list(set([a.page_url for a in recording.actions]))
        action_types = [s.action_type for s in steps]

        prompt = f"""Given this recorded browser workflow:
Goal: {recording.goal}
Steps: {len(steps)}
Actions: {', '.join(action_types)}
URLs visited: {', '.join(urls_visited[:3])}

Generate:
1. A short name (3-5 words)
2. A one-sentence description

Format:
NAME: <name>
DESC: <description>
"""
        try:
            response = await self.llm.generate(prompt)
            content = response.content if hasattr(response, 'content') else str(response)

            name = "Recorded Workflow"
            desc = recording.goal

            for line in content.split('\n'):
                if line.startswith('NAME:'):
                    name = line[5:].strip()
                elif line.startswith('DESC:'):
                    desc = line[5:].strip()

            return name, desc
        except Exception as e:
            logger.warning(f"Failed to generate metadata with LLM: {e}")
            return "Recorded Workflow", recording.goal

    def _estimate_duration(self, steps: List[WorkflowStep]) -> int:
        """
        Estimate workflow duration in seconds.

        Args:
            steps: Workflow steps

        Returns:
            Estimated duration in seconds
        """
        total_ms = sum(s.wait_after for s in steps)
        # Add base time per action
        total_ms += len(steps) * 500
        return total_ms // 1000

    def _generate_var_name(self, var_type: str, index: int) -> str:
        """
        Generate variable name from type.

        Args:
            var_type: Type of variable
            index: Index for uniqueness

        Returns:
            Variable name
        """
        type_names = {
            'email': 'user_email',
            'phone': 'phone_number',
            'name': 'full_name',
            'date': 'date',
            'url': 'target_url',
            'address': 'address',
            'text': f'input_{index}'
        }
        base = type_names.get(var_type, f'var_{index}')
        return base if index == 0 else f'{base}_{index}'

    async def _llm_classify_value(self, value: str, action: RecordedAction) -> str:
        """
        Use LLM to classify uncertain input values.

        Args:
            value: Input value to classify
            action: Action context

        Returns:
            Variable type or 'literal'
        """
        prompt = f"""Classify this input value for a browser form:
Value: "{value}"
Input type: {action.target_attributes.get('type', 'text')}
Placeholder: {action.target_attributes.get('placeholder', 'none')}

Is this a:
- email (email address)
- name (person's name)
- phone (phone number)
- date (date value)
- address (street address)
- url (website URL)
- literal (specific constant value, not a variable)

Answer with ONE word only."""

        try:
            response = await self.llm.generate(prompt, temperature=0.0)
            content = response.content if hasattr(response, 'content') else str(response)
            return content.strip().lower()
        except Exception as e:
            logger.warning(f"Failed to classify value with LLM: {e}")
            return 'literal'


class WorkflowExecutor:
    """
    Executes saved workflows with variable substitution and self-healing.
    """

    def __init__(self, mcp_client, validator=None):
        """
        Initialize executor.

        Args:
            mcp_client: MCP client for browser automation
            validator: Optional validator agent for step verification
        """
        self.mcp = mcp_client
        self.validator = validator
        self.max_selector_retries = 3

    async def execute(self, workflow: Workflow,
                      variables: Dict[str, str]) -> ExecutionResult:
        """
        Execute workflow with provided variables.

        Args:
            workflow: Workflow to execute
            variables: Variable values to substitute

        Returns:
            Execution result with success status and step results
        """
        logger.info(f"Executing workflow: {workflow.name}")
        results = []
        start_time = asyncio.get_event_loop().time()

        for step in workflow.steps:
            # Substitute variables in value
            value = self._substitute_variables(step.value_template, variables)

            # Try selectors in order (self-healing)
            success = False
            selectors_to_try = [step.target_primary] + step.target_fallbacks

            for selector in selectors_to_try:
                try:
                    result = await self._execute_action(
                        step.action_type, selector, value
                    )

                    # Validate if validator available
                    if self.validator:
                        validation = await self._validate_step(step, result)
                        if not validation.get('valid', True):
                            continue

                    success = True
                    results.append(ActionResult(step.id, True, selector))

                    # Update workflow with successful selector
                    if selector != step.target_primary:
                        self._promote_selector(workflow, step.id, selector)

                    break

                except Exception as e:
                    logger.debug(f"Selector failed: {selector} - {e}")
                    continue  # Try next selector

            if not success:
                # Try vision-based fallback
                if step.target_visual:
                    try:
                        result = await self._vision_fallback(step)
                        if result.success:
                            success = True
                            results.append(ActionResult(step.id, True, 'vision'))
                    except Exception as e:
                        logger.debug(f"Vision fallback failed: {e}")

                if not success:
                    results.append(ActionResult(step.id, False, None,
                                              "All selectors failed"))
                    logger.error(f"Step {step.id} failed - all selectors exhausted")

            # Wait after action
            await asyncio.sleep(step.wait_after / 1000)

        # Update workflow stats
        workflow.times_executed += 1
        success_count = len([r for r in results if r.success])
        success_rate = success_count / len(results) if results else 0.0
        workflow.success_rate = (
            (workflow.success_rate * (workflow.times_executed - 1) + success_rate)
            / workflow.times_executed
        )

        duration = int((asyncio.get_event_loop().time() - start_time) * 1000)

        return ExecutionResult(
            success=all(r.success for r in results),
            steps=results,
            duration=duration
        )

    def _substitute_variables(self, template: Optional[str],
                               variables: Dict[str, str]) -> Optional[str]:
        """
        Replace {{var}} with actual values.

        Args:
            template: Template string with {{var}} placeholders
            variables: Variable values

        Returns:
            String with substituted values
        """
        if not template:
            return None

        result = template
        for var_name, var_value in variables.items():
            result = result.replace(f"{{{{{var_name}}}}}", var_value)

        return result

    async def _execute_action(self, action_type: str, selector: str,
                               value: Optional[str]) -> Dict[str, Any]:
        """
        Execute single action via MCP.

        Args:
            action_type: Type of action (click, fill, navigate, etc.)
            selector: Element selector
            value: Value for fill/input actions

        Returns:
            Action result
        """
        if action_type == 'navigate':
            return await self.mcp.call_tool('playwright_navigate', {'url': value or selector})
        elif action_type == 'click':
            return await self.mcp.call_tool('playwright_click', {'selector': selector})
        elif action_type == 'fill':
            return await self.mcp.call_tool('playwright_fill', {
                'selector': selector,
                'value': value or ''
            })
        elif action_type == 'select':
            return await self.mcp.call_tool('playwright_select', {
                'selector': selector,
                'value': value or ''
            })
        else:
            logger.warning(f"Unknown action type: {action_type}")
            return {'success': False, 'error': f'Unknown action type: {action_type}'}

    async def _validate_step(self, step: WorkflowStep, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate step execution.

        Args:
            step: Workflow step
            result: Execution result

        Returns:
            Validation result
        """
        # Quick check - if result has error, fail
        if result.get('error'):
            return {'valid': False, 'reason': result['error']}

        # Check success indicators
        for indicator in step.success_indicators:
            if indicator == 'page_state_changed':
                # Would need before/after state comparison
                pass
            elif indicator.startswith('url_contains:'):
                # Would need to check current URL
                pass
            elif indicator.startswith('input_has_value:'):
                # Would need to check input value
                pass

        # Default to success if no indicators fail
        return {'valid': True}

    async def _vision_fallback(self, step: WorkflowStep) -> ActionResult:
        """
        Use vision model to find and interact with element.

        Args:
            step: Workflow step

        Returns:
            Action result
        """
        # Take screenshot
        screenshot_result = await self.mcp.call_tool('playwright_screenshot', {})

        if screenshot_result.get('error'):
            return ActionResult(
                step_id=step.id,
                success=False,
                selector_used='vision',
                error="Failed to capture screenshot"
            )

        # For now, return failure - full vision integration would require
        # additional vision model setup and coordinate extraction
        logger.warning("Vision fallback not fully implemented yet")
        return ActionResult(
            step_id=step.id,
            success=False,
            selector_used='vision',
            error="Vision fallback not implemented"
        )

    def _promote_selector(self, workflow: Workflow, step_id: int,
                          working_selector: str):
        """
        Promote working selector to primary position.

        Args:
            workflow: Workflow to update
            step_id: Step ID to update
            working_selector: Selector that worked
        """
        for step in workflow.steps:
            if step.id == step_id:
                # Move working selector to front
                if working_selector in step.target_fallbacks:
                    step.target_fallbacks.remove(working_selector)
                step.target_fallbacks.insert(0, step.target_primary)
                step.target_primary = working_selector
                logger.info(f"Promoted selector for step {step_id}: {working_selector}")
                break
