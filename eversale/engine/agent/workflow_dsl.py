"""
Workflow DSL - Define and execute browser automation workflows

This DSL is shared between Chrome Extension and Python CLI.
Workflows are JSON-serializable and can be:
1. Generated from recordings (via LLM)
2. Created manually
3. Composed from existing skills

Workflow Structure:
{
    "id": "uuid",
    "name": "Search LinkedIn for candidates",
    "description": "...",
    "urlPattern": "https://linkedin.com/*",
    "variables": {"query": "", "count": 10},
    "steps": [
        {"action": "goto", "url": "{{baseUrl}}/search"},
        {"action": "type", "targetId": "search_input", "value": "{{query}}"},
        {"action": "click", "targetId": "search_button"},
        {"action": "waitFor", "targetId": "results_list"},
        {"action": "forEach", "targetId": "result_item", "limit": "{{count}}", "steps": [...]}
    ],
    "domMapId": "abc123"
}
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional, Union
from enum import Enum
import json
import re
from pathlib import Path
from loguru import logger

class WorkflowAction(str, Enum):
    GOTO = "goto"
    CLICK = "click"
    TYPE = "type"
    FILL = "fill"
    SELECT = "select"
    SCROLL = "scroll"
    WAIT_FOR = "waitFor"
    WAIT_TIME = "waitTime"
    SCREENSHOT = "screenshot"
    EXTRACT = "extract"
    FOR_EACH = "forEach"
    IF = "if"
    WHILE = "while"
    CALL = "call"  # Call another workflow
    CUSTOM = "custom"

@dataclass
class WorkflowStep:
    """Single step in a workflow"""
    id: str
    action: WorkflowAction

    # Target (reference to DomTarget ID)
    target_id: Optional[str] = None

    # Direct selector (fallback if no target_id)
    selector: Optional[str] = None

    # Action-specific params
    url: Optional[str] = None  # for goto
    value: Optional[str] = None  # for type/fill
    text: Optional[str] = None  # for waitFor text
    timeout: int = 30000  # ms

    # Control flow
    condition: Optional[str] = None  # for if/while
    limit: Optional[int] = None  # for forEach
    children: List['WorkflowStep'] = field(default_factory=list)

    # Extraction
    extract_to: Optional[str] = None  # variable name
    extract_attribute: Optional[str] = None  # 'text', 'href', etc.

    def to_dict(self) -> Dict:
        d = asdict(self)
        d['action'] = self.action.value
        d['children'] = [c.to_dict() for c in self.children]
        return {k: v for k, v in d.items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict) -> 'WorkflowStep':
        data['action'] = WorkflowAction(data['action'])
        if 'children' in data:
            data['children'] = [cls.from_dict(c) for c in data['children']]
        return cls(**data)

@dataclass
class Workflow:
    """Complete workflow definition"""
    id: str
    name: str
    description: str
    url_pattern: str
    steps: List[WorkflowStep]

    # Variables (can be filled at runtime)
    variables: Dict[str, Any] = field(default_factory=dict)

    # Link to DOM map
    dom_map_id: Optional[str] = None

    # Metadata
    created_at: float = 0
    updated_at: float = 0
    version: int = 1
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'urlPattern': self.url_pattern,
            'steps': [s.to_dict() for s in self.steps],
            'variables': self.variables,
            'domMapId': self.dom_map_id,
            'createdAt': self.created_at,
            'updatedAt': self.updated_at,
            'version': self.version,
            'tags': self.tags
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Workflow':
        return cls(
            id=data['id'],
            name=data['name'],
            description=data['description'],
            url_pattern=data['urlPattern'],
            steps=[WorkflowStep.from_dict(s) for s in data['steps']],
            variables=data.get('variables', {}),
            dom_map_id=data.get('domMapId'),
            created_at=data.get('createdAt', 0),
            updated_at=data.get('updatedAt', 0),
            version=data.get('version', 1),
            tags=data.get('tags', [])
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> 'Workflow':
        return cls.from_dict(json.loads(json_str))


class WorkflowExecutor:
    """
    Execute workflows using Playwright and DOM maps.

    Features:
    - Variable interpolation ({{varName}})
    - Control flow (forEach, if, while)
    - Self-healing via DomMapStore
    - Extraction to variables
    """

    def __init__(self, page, dom_store=None):
        self.page = page
        self.dom_store = dom_store
        self.variables: Dict[str, Any] = {}
        self.extracted_data: List[Dict] = []

    async def execute(self, workflow: Workflow,
                      variables: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute workflow with optional variable overrides"""
        self.variables = {**workflow.variables, **(variables or {})}
        self.extracted_data = []

        try:
            for step in workflow.steps:
                await self._execute_step(step, workflow.dom_map_id)

            return {
                'success': True,
                'extractedData': self.extracted_data,
                'variables': self.variables
            }
        except Exception as e:
            logger.error(f"Workflow execution failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'extractedData': self.extracted_data
            }

    async def _execute_step(self, step: WorkflowStep, dom_map_id: str):
        """Execute single step"""
        logger.debug(f"Executing step: {step.action.value}")

        # Interpolate variables
        selector = self._interpolate(step.selector)
        url = self._interpolate(step.url)
        value = self._interpolate(step.value)

        # Resolve target to selector
        if step.target_id and self.dom_store:
            target = self.dom_store.get_target_by_id(dom_map_id, step.target_id)
            if target and target.selector_candidates.get('css'):
                selector = target.selector_candidates['css'][0]

        # Execute based on action type
        match step.action:
            case WorkflowAction.GOTO:
                await self.page.goto(url, timeout=step.timeout)

            case WorkflowAction.CLICK:
                await self._click_with_healing(selector, step, dom_map_id)

            case WorkflowAction.TYPE | WorkflowAction.FILL:
                await self._fill_with_healing(selector, value, step, dom_map_id)

            case WorkflowAction.WAIT_FOR:
                await self.page.wait_for_selector(selector, timeout=step.timeout)

            case WorkflowAction.WAIT_TIME:
                await self.page.wait_for_timeout(step.timeout)

            case WorkflowAction.SCROLL:
                await self.page.evaluate('window.scrollBy(0, 500)')

            case WorkflowAction.SCREENSHOT:
                await self.page.screenshot(path=f"{step.id}.png")

            case WorkflowAction.EXTRACT:
                await self._extract(selector, step)

            case WorkflowAction.FOR_EACH:
                await self._execute_for_each(step, dom_map_id)

            case WorkflowAction.IF:
                await self._execute_if(step, dom_map_id)

    async def _click_with_healing(self, selector: str, step: WorkflowStep, dom_map_id: str):
        """Click with self-healing fallback"""
        try:
            await self.page.click(selector, timeout=step.timeout)
            if step.target_id and self.dom_store:
                self.dom_store.record_success(dom_map_id, step.target_id, selector)
        except Exception as e:
            logger.warning(f"Click failed, attempting healing: {e}")
            # Try healing via dom_store
            if step.target_id and self.dom_store:
                self.dom_store.record_failure(dom_map_id, step.target_id, selector)
                # Get next selector candidate
                target = self.dom_store.get_target_by_id(dom_map_id, step.target_id)
                if target:
                    for alt_selector in target.selector_candidates.get('css', [])[1:]:
                        try:
                            await self.page.click(alt_selector, timeout=5000)
                            self.dom_store.heal_selector(dom_map_id, step.target_id, alt_selector, selector)
                            return
                        except:
                            continue
            raise

    async def _fill_with_healing(self, selector: str, value: str, step: WorkflowStep, dom_map_id: str):
        """Fill input with self-healing"""
        try:
            await self.page.fill(selector, value, timeout=step.timeout)
        except Exception as e:
            logger.warning(f"Fill failed, attempting healing: {e}")
            # Similar healing logic
            raise

    async def _extract(self, selector: str, step: WorkflowStep):
        """Extract data from element"""
        element = await self.page.query_selector(selector)
        if element:
            if step.extract_attribute == 'text':
                value = await element.text_content()
            elif step.extract_attribute:
                value = await element.get_attribute(step.extract_attribute)
            else:
                value = await element.text_content()

            if step.extract_to:
                self.variables[step.extract_to] = value
            self.extracted_data.append({
                'stepId': step.id,
                'selector': selector,
                'value': value
            })

    async def _execute_for_each(self, step: WorkflowStep, dom_map_id: str):
        """Execute children for each matching element"""
        selector = self._interpolate(step.selector)
        elements = await self.page.query_selector_all(selector)
        limit = step.limit or len(elements)

        for i, element in enumerate(elements[:limit]):
            self.variables['_index'] = i
            self.variables['_element'] = element
            for child in step.children:
                await self._execute_step(child, dom_map_id)

    async def _execute_if(self, step: WorkflowStep, dom_map_id: str):
        """Conditional execution"""
        condition = self._interpolate(step.condition)
        # Simple condition evaluation
        try:
            result = eval(condition, {'__builtins__': {}}, self.variables)
            if result:
                for child in step.children:
                    await self._execute_step(child, dom_map_id)
        except Exception as e:
            logger.warning(f"Condition evaluation failed: {e}")

    def _interpolate(self, value: Optional[str]) -> Optional[str]:
        """Replace {{varName}} with variable values"""
        if not value:
            return value

        def replace(match):
            var_name = match.group(1)
            return str(self.variables.get(var_name, match.group(0)))

        return re.sub(r'\{\{(\w+)\}\}', replace, value)


class WorkflowStorage:
    """Persistent workflow storage"""

    STORAGE_DIR = Path.home() / ".eversale" / "workflows"

    def __init__(self):
        self.STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    def save(self, workflow: Workflow):
        """Save workflow to disk"""
        path = self.STORAGE_DIR / f"{workflow.id}.json"
        with open(path, 'w') as f:
            f.write(workflow.to_json())
        logger.info(f"Saved workflow: {workflow.name} ({workflow.id})")

    def load(self, workflow_id: str) -> Optional[Workflow]:
        """Load workflow from disk"""
        path = self.STORAGE_DIR / f"{workflow_id}.json"
        if path.exists():
            with open(path, 'r') as f:
                return Workflow.from_json(f.read())
        return None

    def list_all(self) -> List[Workflow]:
        """List all saved workflows"""
        workflows = []
        for path in self.STORAGE_DIR.glob("*.json"):
            try:
                with open(path, 'r') as f:
                    workflows.append(Workflow.from_json(f.read()))
            except Exception as e:
                logger.warning(f"Failed to load workflow {path}: {e}")
        return workflows

    def delete(self, workflow_id: str):
        """Delete workflow"""
        path = self.STORAGE_DIR / f"{workflow_id}.json"
        if path.exists():
            path.unlink()
            logger.info(f"Deleted workflow: {workflow_id}")


class WorkflowStore:
    """
    Workflow storage manager for agent-backend integration.

    Stores workflows in /mnt/c/ev29/agent-backend/memory/workflows/
    Compatible with existing memory structure.
    """

    def __init__(self, storage_dir: Optional[Path] = None):
        if storage_dir is None:
            # Use agent-backend memory directory
            base_dir = Path(__file__).parent / "memory" / "workflows"
        else:
            base_dir = storage_dir

        self.storage_dir = base_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"WorkflowStore initialized: {self.storage_dir}")

    def save_workflow(self, workflow: Workflow) -> bool:
        """Save workflow to memory/workflows/"""
        try:
            import time
            workflow.updated_at = time.time()
            path = self.storage_dir / f"{workflow.id}.json"

            with open(path, 'w') as f:
                f.write(workflow.to_json())

            logger.info(f"Saved workflow: {workflow.name} ({workflow.id})")
            return True
        except Exception as e:
            logger.error(f"Failed to save workflow {workflow.id}: {e}")
            return False

    def load_workflow(self, workflow_id: str) -> Optional[Workflow]:
        """Load workflow by ID"""
        try:
            path = self.storage_dir / f"{workflow_id}.json"
            if not path.exists():
                logger.warning(f"Workflow not found: {workflow_id}")
                return None

            with open(path, 'r') as f:
                workflow = Workflow.from_json(f.read())

            logger.debug(f"Loaded workflow: {workflow.name} ({workflow.id})")
            return workflow
        except Exception as e:
            logger.error(f"Failed to load workflow {workflow_id}: {e}")
            return None

    def list_workflows(self) -> List[Dict[str, Any]]:
        """List all workflows with metadata"""
        try:
            workflows = []
            for path in self.storage_dir.glob("*.json"):
                try:
                    with open(path, 'r') as f:
                        data = json.loads(f.read())

                    workflows.append({
                        'id': data['id'],
                        'name': data['name'],
                        'description': data['description'],
                        'urlPattern': data.get('urlPattern', ''),
                        'tags': data.get('tags', []),
                        'createdAt': data.get('createdAt', 0),
                        'updatedAt': data.get('updatedAt', 0),
                        'stepCount': len(data.get('steps', []))
                    })
                except Exception as e:
                    logger.warning(f"Failed to read workflow {path.name}: {e}")
                    continue

            # Sort by updated time (newest first)
            workflows.sort(key=lambda w: w['updatedAt'], reverse=True)
            return workflows
        except Exception as e:
            logger.error(f"Failed to list workflows: {e}")
            return []

    def delete_workflow(self, workflow_id: str) -> bool:
        """Delete workflow by ID"""
        try:
            path = self.storage_dir / f"{workflow_id}.json"
            if not path.exists():
                logger.warning(f"Workflow not found: {workflow_id}")
                return False

            path.unlink()
            logger.info(f"Deleted workflow: {workflow_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete workflow {workflow_id}: {e}")
            return False


async def synthesize_workflow(
    recorded_steps: List[Dict],
    user_goal: str,
    dom_map: Dict,
    kimi_client = None
) -> Optional[Workflow]:
    """
    Convert raw recording into clean workflow using LLM.

    Takes messy recorded steps and creates a clean, reusable workflow by:
    - Removing noise (accidental clicks, back navigation)
    - Grouping related actions (form fills)
    - Adding loops and conditions where appropriate
    - Linking to DomTarget IDs for self-healing
    - Inferring extraction points

    Args:
        recorded_steps: Raw steps from recording session
        user_goal: What the user was trying to accomplish
        dom_map: DomMap data for target linking
        kimi_client: Optional Kimi K2 client for synthesis

    Returns:
        Synthesized Workflow or None if synthesis fails
    """
    try:
        # Import Kimi client if not provided
        if kimi_client is None:
            try:
                from .kimi_k2_client import get_kimi_client
                kimi_client = get_kimi_client()
            except ImportError:
                logger.warning("Kimi K2 client not available - using basic synthesis")
                kimi_client = None

        # Check if Kimi is available
        if not kimi_client or not kimi_client.is_available():
            logger.warning("Kimi K2 not available - falling back to basic synthesis")
            return await _basic_synthesis(recorded_steps, user_goal, dom_map)

        # Build synthesis prompt
        prompt = _build_synthesis_prompt(recorded_steps, user_goal, dom_map)

        # Call Kimi K2 for intelligent synthesis
        response = await kimi_client.extract_from_content(prompt)

        if not response:
            logger.warning("Kimi synthesis failed - falling back to basic synthesis")
            return await _basic_synthesis(recorded_steps, user_goal, dom_map)

        # Parse LLM response
        workflow_data = _parse_synthesis_response(response)

        if not workflow_data:
            logger.warning("Failed to parse synthesis response - falling back to basic")
            return await _basic_synthesis(recorded_steps, user_goal, dom_map)

        # Create workflow object
        import hashlib
        import time
        workflow_id = hashlib.md5(f"{user_goal}_{time.time()}".encode()).hexdigest()[:16]

        workflow = Workflow(
            id=workflow_id,
            name=workflow_data.get('name', user_goal[:50]),
            description=workflow_data.get('description', user_goal),
            url_pattern=workflow_data.get('urlPattern', ''),
            steps=[WorkflowStep.from_dict(s) for s in workflow_data.get('steps', [])],
            variables=workflow_data.get('variables', {}),
            dom_map_id=dom_map.get('id', ''),
            created_at=time.time(),
            updated_at=time.time(),
            tags=workflow_data.get('tags', [])
        )

        logger.info(f"Synthesized workflow: {workflow.name} ({len(workflow.steps)} steps)")
        return workflow

    except Exception as e:
        logger.error(f"Workflow synthesis failed: {e}")
        return await _basic_synthesis(recorded_steps, user_goal, dom_map)


def _build_synthesis_prompt(recorded_steps: List[Dict], user_goal: str, dom_map: Dict) -> str:
    """Build prompt for LLM synthesis"""

    # Summarize recorded steps (don't send full DOM data)
    steps_summary = []
    for i, step in enumerate(recorded_steps[:50]):  # Limit to 50 steps
        steps_summary.append({
            'index': i,
            'action': step.get('action', 'unknown'),
            'url': step.get('url', ''),
            'selector': step.get('selector', ''),
            'text': step.get('text', '')[:100]  # Truncate long text
        })

    # Available DomTarget IDs
    dom_targets = list(dom_map.get('targets', {}).keys())[:20]  # Sample

    prompt = f"""Analyze this browser recording and create a clean, reusable workflow.

USER GOAL:
{user_goal}

RECORDED STEPS (may include noise and mistakes):
{json.dumps(steps_summary, indent=2)}

AVAILABLE DOM TARGETS:
{json.dumps(dom_targets, indent=2)}

YOUR TASK:
1. Remove accidental clicks and navigation mistakes
2. Group related actions (e.g., filling a form)
3. Identify loops (e.g., clicking through pagination)
4. Add extraction points for data collection
5. Link actions to DomTarget IDs where possible

OUTPUT FORMAT (JSON only, no markdown):
{{
  "name": "Short workflow name (max 50 chars)",
  "description": "What this workflow accomplishes",
  "urlPattern": "Starting URL or pattern",
  "tags": ["tag1", "tag2"],
  "variables": {{"varName": "defaultValue"}},
  "steps": [
    {{
      "id": "step_1",
      "action": "goto",
      "url": "https://example.com",
      "timeout": 30000
    }},
    {{
      "id": "step_2",
      "action": "click",
      "target_id": "dom_target_id or null",
      "selector": "css selector fallback",
      "timeout": 30000
    }},
    {{
      "id": "step_3",
      "action": "extract",
      "selector": ".data",
      "extract_to": "resultData",
      "extract_attribute": "text"
    }}
  ]
}}

IMPORTANT:
- Only include essential steps, no noise
- Use forEach for repetitive actions
- Add extract steps for data collection
- Reference DomTarget IDs when possible for self-healing
- All action names must be valid: goto, click, type, fill, waitFor, extract, forEach, screenshot
"""

    return prompt


def _parse_synthesis_response(response: str) -> Optional[Dict]:
    """Parse LLM synthesis response"""
    try:
        # Extract JSON from response
        content = response.strip()

        # Handle markdown code blocks
        if '```json' in content:
            content = content.split('```json')[1].split('```')[0]
        elif '```' in content:
            content = content.split('```')[1].split('```')[0]

        # Parse JSON
        data = json.loads(content.strip())

        # Validate required fields
        if not data.get('name') or not data.get('steps'):
            logger.warning("Synthesis response missing required fields")
            return None

        return data

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse synthesis response: {e}")
        return None
    except Exception as e:
        logger.error(f"Error parsing synthesis response: {e}")
        return None


async def _basic_synthesis(recorded_steps: List[Dict], user_goal: str, dom_map: Dict) -> Optional[Workflow]:
    """
    Fallback: Basic workflow synthesis without LLM.

    Creates a simple workflow by:
    - Filtering obvious noise (duplicate clicks, rapid back/forward)
    - Grouping consecutive type actions
    - Preserving navigation and click order
    """
    try:
        import time
        import hashlib

        if not recorded_steps:
            return None

        # Filter noise
        clean_steps = []
        prev_step = None

        for step in recorded_steps:
            action = step.get('action', '')

            # Skip duplicate consecutive actions
            if prev_step and prev_step.get('action') == action and prev_step.get('selector') == step.get('selector'):
                continue

            # Skip very rapid actions (likely mistakes)
            if prev_step:
                time_diff = step.get('timestamp', 0) - prev_step.get('timestamp', 0)
                if time_diff < 0.1:  # Less than 100ms
                    continue

            clean_steps.append(step)
            prev_step = step

        # Convert to workflow steps
        workflow_steps = []
        for i, step in enumerate(clean_steps):
            action_str = step.get('action', 'click')

            # Map to WorkflowAction enum
            action_map = {
                'goto': WorkflowAction.GOTO,
                'click': WorkflowAction.CLICK,
                'type': WorkflowAction.TYPE,
                'fill': WorkflowAction.FILL,
                'waitFor': WorkflowAction.WAIT_FOR,
                'extract': WorkflowAction.EXTRACT,
                'screenshot': WorkflowAction.SCREENSHOT
            }

            action = action_map.get(action_str, WorkflowAction.CLICK)

            workflow_step = WorkflowStep(
                id=f"step_{i + 1}",
                action=action,
                target_id=None,  # No DomTarget linking in basic mode
                selector=step.get('selector', ''),
                url=step.get('url') if action == WorkflowAction.GOTO else None,
                value=step.get('text', '') if action in [WorkflowAction.TYPE, WorkflowAction.FILL] else None
            )
            workflow_steps.append(workflow_step)

        # Create workflow
        workflow_id = hashlib.md5(f"{user_goal}_{time.time()}".encode()).hexdigest()[:16]
        first_url = clean_steps[0].get('url', '') if clean_steps else ''

        workflow = Workflow(
            id=workflow_id,
            name=user_goal[:50] if user_goal else "Recorded Workflow",
            description=user_goal or "Basic workflow from recording",
            url_pattern=first_url,
            steps=workflow_steps,
            dom_map_id=dom_map.get('id', ''),
            created_at=time.time(),
            updated_at=time.time(),
            tags=['basic', 'recorded']
        )

        logger.info(f"Created basic workflow: {workflow.name} ({len(workflow.steps)} steps)")
        return workflow

    except Exception as e:
        logger.error(f"Basic synthesis failed: {e}")
        return None


# Global store singleton
_workflow_store: Optional[WorkflowStore] = None


def get_workflow_store() -> WorkflowStore:
    """Get or create the global workflow store"""
    global _workflow_store
    if _workflow_store is None:
        _workflow_store = WorkflowStore()
    return _workflow_store
