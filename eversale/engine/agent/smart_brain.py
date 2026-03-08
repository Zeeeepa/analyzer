"""
Smart Brain - Unified Integration Layer for LocalLLaMA Architecture
====================================================================

Auto-wires all new components and makes them work together seamlessly.
Natural language in -> intelligent browser automation out.

Components Integrated:
- DualLLMOrchestrator (vision plans once, executor runs per-step)
- WebDaemon (isolated web fetching with caching)
- WorkerLoop (task-based execution)
- ToolWrappers (validation, retry, lockout)
- CompressedDOM (efficient DOM for LLMs)
- BrowserToolSchemas (strict tool definitions)

Usage:
    brain = await SmartBrain.create()
    result = await brain.run("Find the CEO's email on stripe.com")
"""

import asyncio
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from loguru import logger

# Import all new components
try:
    from .llm_client import LLMClient, get_llm_client
    LLM_CLIENT_AVAILABLE = True
except ImportError:
    LLM_CLIENT_AVAILABLE = False
    logger.warning("LLM client not available")

try:
    from .dual_llm_orchestrator import (
        DualLLMOrchestrator,
        ExecutionPlan,
        PlanStep,
        JobResult as OrchestratorJobResult
    )
    DUAL_LLM_AVAILABLE = True
except ImportError:
    DUAL_LLM_AVAILABLE = False
    logger.warning("Dual LLM orchestrator not available")

try:
    from .web_daemon import WebDaemon, WebResult
    WEB_DAEMON_AVAILABLE = True
except ImportError:
    WEB_DAEMON_AVAILABLE = False
    logger.warning("Web daemon not available")

try:
    from .worker_loop import (
        WorkerLoop,
        WorkerJob,
        JobResult,
        SafetyConstraints,
        SharedState
    )
    WORKER_LOOP_AVAILABLE = True
except ImportError:
    WORKER_LOOP_AVAILABLE = False
    logger.warning("Worker loop not available")

try:
    from .tool_wrappers import (
        ToolRegistry,
        ToolWrapper,
        ToolStatus,
        CommonValidationRules
    )
    TOOL_WRAPPERS_AVAILABLE = True
except ImportError:
    TOOL_WRAPPERS_AVAILABLE = False
    logger.warning("Tool wrappers not available")

try:
    from .compressed_dom import DOMCompressor, CompressedDOM
    COMPRESSED_DOM_AVAILABLE = True
except ImportError:
    COMPRESSED_DOM_AVAILABLE = False
    logger.warning("Compressed DOM not available")

try:
    from .browser_tool_schemas import (
        BROWSER_TOOL_SCHEMAS,
        build_tools_prompt,
        validate_tool_call
    )
    TOOL_SCHEMAS_AVAILABLE = True
except ImportError:
    TOOL_SCHEMAS_AVAILABLE = False
    logger.warning("Browser tool schemas not available")

try:
    from .agent_roles import AgentRole, get_role_manager, SafetyConfig, ROLE_PROMPTS
    AGENT_ROLES_AVAILABLE = True
except ImportError:
    AGENT_ROLES_AVAILABLE = False
    logger.warning("Agent roles not available")


class TaskType(Enum):
    """Detected task type from natural language."""
    WEB_AUTOMATION = "web_automation"      # Browser tasks
    WEB_RESEARCH = "web_research"          # Search and fetch info
    DATA_EXTRACTION = "data_extraction"    # Extract structured data
    FORM_FILLING = "form_filling"          # Fill forms
    NAVIGATION = "navigation"              # Simple navigation
    VISION = "vision"                      # Screenshot/image analysis
    COMPLEX_REASONING = "complex_reasoning" # Multi-step logic
    UNKNOWN = "unknown"


class ModelType(Enum):
    """Which LLM model to use."""
    PRIMARY = "primary"       # 0000/ui-tars-1.5-7b:latest - default for most tasks
    VISION = "vision"         # UI-TARS - screenshot/image analysis
    COMPLEX = "complex"       # Kimi API - complex reasoning


@dataclass
class IntentAnalysis:
    """Result of analyzing user's natural language input."""
    task_type: TaskType
    goal: str
    target_url: Optional[str] = None
    search_query: Optional[str] = None
    extract_fields: List[str] = field(default_factory=list)
    form_data: Dict[str, str] = field(default_factory=dict)
    confidence: float = 0.0
    raw_input: str = ""
    model_type: ModelType = ModelType.PRIMARY  # Auto-selected model
    complexity_score: float = 0.0  # 0-1 score for task complexity


@dataclass
class SmartResult:
    """Unified result from SmartBrain."""
    success: bool
    answer: Optional[str] = None
    output: Optional[str] = None  # Alias for answer (for compatibility)
    data: Optional[Dict[str, Any]] = None
    steps_taken: int = 0
    execution_time_seconds: float = 0.0
    error: Optional[str] = None
    trace_id: Optional[str] = None
    task_type: Optional[TaskType] = None
    model_used: Optional[str] = None  # Which model was used (qwen3/ui-tars/kimi)

    def __post_init__(self):
        # Sync answer and output
        if self.answer and not self.output:
            self.output = self.answer
        elif self.output and not self.answer:
            self.answer = self.output


class IntentDetector:
    """
    Detects user intent from natural language.

    Uses pattern matching + LLM fallback for complex queries.
    Auto-selects the best model based on task type and complexity.
    """

    # URL patterns
    URL_PATTERN = re.compile(
        r'https?://[^\s<>"{}|\\^`\[\]]+|'
        r'(?:www\.)?[a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}(?:/[^\s]*)?'
    )

    # Vision task patterns - use UI-TARS
    VISION_PATTERNS = [
        r'\b(?:screenshot|screen\s*shot|capture|image|picture|photo)\b',
        r'\b(?:look\s+at|analyze|examine)\s+(?:the|this)\s+(?:screen|page|image)\b',
        r'\b(?:what\s+do\s+you\s+see|describe\s+what)\b',
        r'\b(?:visual|visually|appearance|looks?\s+like)\b',
        r'\b(?:find|locate|identify)\s+(?:the|a)\s+(?:button|element|icon)\s+(?:on|in)\s+(?:the\s+)?(?:screen|page)\b',
    ]

    # Complex reasoning patterns - use Kimi API
    COMPLEX_PATTERNS = [
        r'\b(?:analyze|compare|evaluate|assess|synthesize)\b.*\b(?:and|then|after)\b',
        r'\b(?:step\s*by\s*step|multi-?step|complex)\b',
        r'\b(?:create|write|generate)\s+(?:a\s+)?(?:detailed|comprehensive|full)\b',
        r'\b(?:explain|reason|think\s+through)\s+(?:why|how|the)\b',
        r'\b(?:plan|strategy|approach)\s+for\b',
        r'\b(?:considering|given\s+that|assuming|if.*then)\b',
        r'\b(?:best|optimal|most\s+effective)\s+(?:way|approach|method)\b',
    ]

    # Complexity indicators (each adds to complexity score)
    COMPLEXITY_INDICATORS = [
        (r'\band\s+(?:then|also|additionally)\b', 0.2),  # Multiple steps
        (r'\b(?:if|when|unless|until)\b', 0.15),         # Conditionals
        (r'\b(?:all|every|each|multiple)\b', 0.1),       # Iteration
        (r'\b(?:compare|versus|vs\.?|between)\b', 0.2),  # Comparison
        (r'\b(?:analyze|evaluate|assess)\b', 0.25),      # Analysis
        (r'\b(?:why|how\s+does|explain)\b', 0.15),       # Explanation needed
        (r'\b(?:best|optimal|most)\b', 0.1),             # Optimization
        (r'\b(?:ensure|verify|confirm|check\s+that)\b', 0.1),  # Verification
    ]

    # Task type patterns - ORDER MATTERS (more specific first)
    PATTERNS = {
        # Data extraction - specific patterns for extracting structured data
        TaskType.DATA_EXTRACTION: [
            r'\b(?:extract|scrape|pull|grab|collect)\b.*\b(?:email|phone|contact|price|name|address|data)\b',
            r'\b(?:find|get)\s+(?:all|the|every)\s+\w*\s*(?:emails?|contacts?|phones?|links?|prices?|names?)\b',
            r'\b(?:find|get)\b.*\b(?:email|contact|phone)\b.*\b(?:from|on|at)\b',
            r'\bscrape\b',
            r'\b(?:emails?|contacts?)\s+from\b',
        ],
        # Web automation - clicking, interacting with elements (before form_filling to catch "click the login button")
        TaskType.WEB_AUTOMATION: [
            r'\b(?:click|tap|press|select|choose|pick)\s+(?:on\s+)?(?:the|a)?\s*\w+\s*(?:button|link|element|option|item)\b',
            r'\b(?:click|tap|press)\s+(?:on\s+)?(?:the|a)?\s*(?:button|link|element)\b',
            r'\b(?:click|tap|press)\s+(?:on\s+)?["\'][^"\']+["\']',  # click on "Submit"
            r'\b(?:scroll|drag|hover|type|input)\b',
        ],
        # Form filling - login, signup, forms
        TaskType.FORM_FILLING: [
            r'\b(?:fill|complete|submit)\s+(?:the|this|a|out)?\s*(?:form|fields?)\b',
            r'\bfill\s+(?:in|out)?\s*(?:the|this|a)?\s*\w*\s*form\b',
            r'\b(?:sign up|signup|register|log ?in|sign ?in)\s+(?:for|to|on)?\b',
            r'\benter\s+(?:my|the|your)\s+(?:info|information|details|data|credentials)\b',
            r'\bwith\s+my\s+(?:info|information|details)\b',
        ],
        # Navigation - going to URLs
        TaskType.NAVIGATION: [
            r'\b(?:go\s+to|open|visit|navigate\s+to|browse\s+to)\b',
            r'\b(?:take\s+me\s+to|show\s+me)\b',
        ],
        # Web research - searching for information
        TaskType.WEB_RESEARCH: [
            r'\b(?:search|research|google|look\s+up)\b',
            r'\b(?:what\s+is|who\s+is|tell\s+me\s+about|find\s+info)\b',
            r'\b(?:information|info|details)\s+(?:on|about|for)\b',
        ],
    }

    # Field extraction patterns
    FIELD_PATTERNS = {
        'email': r'\b(?:email|e-mail|mail)\b',
        'phone': r'\b(?:phone|tel|telephone|mobile|cell)\b',
        'name': r'\b(?:name|names|person|people|ceo|founder|owner)\b',
        'address': r'\b(?:address|location|office)\b',
        'price': r'\b(?:price|cost|pricing|rate)\b',
        'link': r'\b(?:link|url|href|website)\b',
    }

    def __init__(self, llm_client: Optional[Any] = None):
        self.llm_client = llm_client

    def detect(self, user_input: str, has_image: bool = False) -> IntentAnalysis:
        """
        Detect intent from natural language input.

        Auto-selects the best model based on task type and complexity:
        - Vision tasks -> UI-TARS
        - Complex reasoning -> Kimi API
        - Everything else -> 0000/ui-tars-1.5-7b:latest

        Args:
            user_input: Raw user input string
            has_image: Whether the input includes an image/screenshot

        Returns:
            IntentAnalysis with detected task type, model selection, and parameters
        """
        user_input = user_input.strip()
        input_lower = user_input.lower()

        # Extract URL if present
        url_match = self.URL_PATTERN.search(user_input)
        target_url = url_match.group(0) if url_match else None

        # Normalize URL
        if target_url and not target_url.startswith('http'):
            target_url = 'https://' + target_url

        # Calculate complexity score
        complexity_score = self._calculate_complexity(input_lower)

        # Check for vision task first (highest priority)
        is_vision = has_image or self._is_vision_task(input_lower)

        # Check for complex reasoning task
        is_complex = complexity_score > 0.5 or self._is_complex_task(input_lower)

        # Detect task type
        task_type = TaskType.UNKNOWN
        confidence = 0.0

        # Vision tasks override other types
        if is_vision:
            task_type = TaskType.VISION
            confidence = 0.9
        elif is_complex:
            task_type = TaskType.COMPLEX_REASONING
            confidence = 0.85
        else:
            # Standard task type detection
            for t_type, patterns in self.PATTERNS.items():
                for pattern in patterns:
                    if re.search(pattern, input_lower):
                        task_type = t_type
                        confidence = 0.8
                        break
                if task_type != TaskType.UNKNOWN:
                    break

        # Default to web automation if URL present but no specific type
        if task_type == TaskType.UNKNOWN and target_url:
            task_type = TaskType.WEB_AUTOMATION
            confidence = 0.6

        # Extract fields to look for
        extract_fields = []
        for field_name, pattern in self.FIELD_PATTERNS.items():
            if re.search(pattern, input_lower):
                extract_fields.append(field_name)

        # If extracting fields, likely data extraction
        if extract_fields and task_type == TaskType.UNKNOWN:
            task_type = TaskType.DATA_EXTRACTION
            confidence = 0.7

        # Extract search query (remove URLs and action words)
        search_query = None
        if task_type == TaskType.WEB_RESEARCH:
            # Remove URLs and common action words
            query = re.sub(self.URL_PATTERN, '', user_input)
            query = re.sub(r'\b(?:search|find|look up|research|google|what is|who is|tell me about)\b', '', query, flags=re.I)
            query = re.sub(r'\b(?:information|info|details|data)\s+(?:on|about|for)\b', '', query, flags=re.I)
            search_query = query.strip()

        # Select the best model
        model_type = self._select_model(task_type, is_vision, is_complex, complexity_score)

        # Build goal description
        goal = self._build_goal(user_input, task_type, target_url, extract_fields)

        return IntentAnalysis(
            task_type=task_type,
            goal=goal,
            target_url=target_url,
            search_query=search_query,
            extract_fields=extract_fields,
            confidence=confidence,
            raw_input=user_input,
            model_type=model_type,
            complexity_score=complexity_score
        )

    def _is_vision_task(self, input_lower: str) -> bool:
        """Check if input requires vision model (UI-TARS)."""
        for pattern in self.VISION_PATTERNS:
            if re.search(pattern, input_lower):
                return True
        return False

    def _is_complex_task(self, input_lower: str) -> bool:
        """Check if input requires complex reasoning (Kimi API)."""
        for pattern in self.COMPLEX_PATTERNS:
            if re.search(pattern, input_lower):
                return True
        return False

    def _calculate_complexity(self, input_lower: str) -> float:
        """
        Calculate complexity score (0-1) based on task indicators.

        Score > 0.5 suggests using Kimi API for better results.
        """
        score = 0.0
        for pattern, weight in self.COMPLEXITY_INDICATORS:
            if re.search(pattern, input_lower):
                score += weight

        # Also factor in input length (longer = more complex)
        word_count = len(input_lower.split())
        if word_count > 50:
            score += 0.2
        elif word_count > 30:
            score += 0.1

        return min(score, 1.0)  # Cap at 1.0

    def _select_model(
        self,
        task_type: TaskType,
        is_vision: bool,
        is_complex: bool,
        complexity_score: float
    ) -> ModelType:
        """
        Select the best model for the task.

        Model selection priority:
        1. Vision (UI-TARS) - for screenshot/image analysis
        2. Complex (Kimi) - for multi-step reasoning
        3. Primary (0000/ui-tars-1.5-7b:latest) - for everything else
        """
        if is_vision or task_type == TaskType.VISION:
            return ModelType.VISION
        elif is_complex or task_type == TaskType.COMPLEX_REASONING or complexity_score > 0.5:
            return ModelType.COMPLEX
        else:
            return ModelType.PRIMARY

    def _build_goal(
        self,
        user_input: str,
        task_type: TaskType,
        target_url: Optional[str],
        extract_fields: List[str]
    ) -> str:
        """Build a clear goal statement for the worker."""
        # Use user input as-is if it's already clear
        if len(user_input) < 100:
            return user_input

        # Build structured goal
        parts = []

        if task_type == TaskType.DATA_EXTRACTION and extract_fields:
            parts.append(f"Extract {', '.join(extract_fields)}")
        elif task_type == TaskType.WEB_RESEARCH:
            parts.append("Research and find information")
        elif task_type == TaskType.FORM_FILLING:
            parts.append("Fill out the form")
        elif task_type == TaskType.NAVIGATION:
            parts.append("Navigate")
        else:
            parts.append("Complete the task")

        if target_url:
            parts.append(f"on {target_url}")

        return ' '.join(parts)


class PlannerNode:
    """
    Planner node that decides next action.

    Uses LLM to analyze current state and decide what to do next.
    """

    PLANNER_PROMPT = """You are a web automation planner. Given the current state, decide the next action.

Goal: {goal}
Current URL: {current_url}
Page Title: {page_title}

Recent Actions:
{recent_actions}

Current DOM (compressed):
{dom_snapshot}

Respond with JSON:
{{
  "mode": "tool_call" | "dom_navigate" | "final_answer",
  "tool_name": "click" | "type_text" | "scroll" | "navigate" | "extract_text" | null,
  "parameters": {{}},
  "reasoning": "brief explanation",
  "answer": "final answer if mode is final_answer"
}}

Rules:
1. Use element IDs from DOM (e1, e2, etc.)
2. One action at a time
3. Return final_answer when goal is achieved
4. Be concise in reasoning
"""

    def __init__(self, llm_client):
        self.llm_client = llm_client

    async def plan(
        self,
        goal: str,
        context: Dict[str, Any],
        shared_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate next action plan."""
        # Format recent actions
        recent_steps = context.get('recent_steps', [])
        recent_actions = '\n'.join([
            f"- Step {s.step_number}: {s.tool_name or 'none'} -> {'success' if s.success else 'failed'}"
            for s in recent_steps[-3:]
        ]) if recent_steps else "None yet"

        prompt = self.PLANNER_PROMPT.format(
            goal=goal,
            current_url=shared_state.get('current_url', 'unknown'),
            page_title=shared_state.get('page_title', 'unknown'),
            recent_actions=recent_actions,
            dom_snapshot=context.get('current_dom', 'Not available')[:2000]
        )

        try:
            response = await self.llm_client.generate(
                prompt=prompt,
                temperature=0.1,
                max_tokens=512
            )

            # Parse JSON from response
            content = response.content

            # Try to extract JSON
            import json
            if '```json' in content:
                json_start = content.find('```json') + 7
                json_end = content.find('```', json_start)
                content = content[json_start:json_end].strip()
            elif '```' in content:
                json_start = content.find('```') + 3
                json_end = content.find('```', json_start)
                content = content[json_start:json_end].strip()

            return json.loads(content)

        except Exception as e:
            logger.error(f"Planner error: {e}")
            return {
                "mode": "final_answer",
                "answer": f"Planning error: {str(e)}"
            }


class DOMNavigatorNode:
    """
    DOM Navigator that generates actions from compressed DOM.
    """

    NAVIGATOR_PROMPT = """Given this compressed DOM and goal, select the best element to interact with.

Goal: {goal}
Current State: {state}

DOM Elements:
{dom}

Respond with JSON:
{{
  "actions": [
    {{"type": "click", "id": "e5"}},
    {{"type": "type_text", "id": "e3", "text": "search query"}}
  ],
  "reasoning": "brief explanation"
}}

Rules:
1. Use element IDs (e1, e2, etc.)
2. Maximum 3 actions per response
3. Prioritize visible, interactive elements
"""

    def __init__(self, llm_client):
        self.llm_client = llm_client

    async def navigate(
        self,
        goal: str,
        dom: str,
        state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate navigation actions."""
        prompt = self.NAVIGATOR_PROMPT.format(
            goal=goal,
            state=str(state)[:500],
            dom=dom[:3000]
        )

        try:
            response = await self.llm_client.generate(
                prompt=prompt,
                temperature=0.0,
                max_tokens=256
            )

            import json
            content = response.content

            if '```json' in content:
                json_start = content.find('```json') + 7
                json_end = content.find('```', json_start)
                content = content[json_start:json_end].strip()

            return json.loads(content)

        except Exception as e:
            logger.error(f"Navigator error: {e}")
            return {"actions": [], "error": str(e)}


class SelfHealingNode:
    """
    Self-healing node that recovers from errors.
    """

    HEALING_PROMPT = """An action failed. Suggest a fix.

Error: {error}
Failed Action: {action}
Current DOM: {dom}

Respond with JSON:
{{
  "can_retry": true/false,
  "modified_action": {{...}},
  "reason": "explanation"
}}
"""

    def __init__(self, llm_client):
        self.llm_client = llm_client

    async def heal(
        self,
        error: str,
        action: Dict[str, Any],
        dom: str
    ) -> Dict[str, Any]:
        """Attempt to heal from error."""
        prompt = self.HEALING_PROMPT.format(
            error=error,
            action=str(action),
            dom=dom[:2000]
        )

        try:
            response = await self.llm_client.generate(
                prompt=prompt,
                temperature=0.0,
                max_tokens=256
            )

            import json
            content = response.content

            if '```json' in content:
                json_start = content.find('```json') + 7
                json_end = content.find('```', json_start)
                content = content[json_start:json_end].strip()

            return json.loads(content)

        except Exception as e:
            logger.error(f"Healing error: {e}")
            return {"can_retry": False, "reason": str(e)}


class BrowserExecutor:
    """
    Executes browser actions via MCP or Playwright.
    """

    def __init__(self, mcp_client=None, page=None):
        self.mcp = mcp_client
        self.page = page
        self._element_map: Dict[str, str] = {}  # e1 -> actual selector

    async def navigate(self, url: str):
        """Navigate to URL."""
        if self.mcp:
            await self.mcp.call_tool('playwright_navigate', {'url': url})
        elif self.page:
            await self.page.goto(url)

    async def get_compressed_dom(self) -> Optional[str]:
        """Get compressed DOM representation."""
        if COMPRESSED_DOM_AVAILABLE and self.page:
            compressor = DOMCompressor()
            dom = await compressor.compress(self.page)

            # Build element map
            self._element_map = {elem.id: elem.selector for elem in dom.elements if hasattr(elem, 'selector')}

            return compressor.to_prompt_format(dom)
        elif self.mcp:
            result = await self.mcp.call_tool('playwright_snapshot', {})
            return str(result)[:3000] if result else None
        return None

    async def get_current_url(self) -> Optional[str]:
        """Get current page URL."""
        if self.page:
            return self.page.url
        elif self.mcp:
            result = await self.mcp.call_tool('playwright_snapshot', {})
            return result.get('url') if isinstance(result, dict) else None
        return None

    async def get_page_title(self) -> Optional[str]:
        """Get current page title."""
        if self.page:
            return await self.page.title()
        return None

    async def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single tool."""
        try:
            # Map element ID to selector if needed
            if 'id' in params and params['id'].startswith('e'):
                element_id = params['id']
                if element_id in self._element_map:
                    params['selector'] = self._element_map[element_id]
                else:
                    # Fallback: try to find by data attribute
                    params['selector'] = f'[data-element-id="{element_id}"]'

            # Map tool names
            tool_mapping = {
                'click': 'playwright_click',
                'type_text': 'playwright_fill',
                'scroll': 'playwright_scroll',
                'navigate': 'playwright_navigate',
                'extract_text': 'playwright_get_text',
            }

            actual_tool = tool_mapping.get(tool_name, tool_name)

            if self.mcp:
                result = await self.mcp.call_tool(actual_tool, params)
                return {'success': True, 'data': result}
            elif self.page:
                # Direct Playwright execution
                if tool_name == 'click':
                    selector = params.get('selector', params.get('id', ''))
                    await self.page.click(selector)
                elif tool_name == 'type_text':
                    selector = params.get('selector', params.get('id', ''))
                    text = params.get('text', '')
                    if params.get('clear_first', True):
                        await self.page.fill(selector, text)
                    else:
                        await self.page.type(selector, text)
                elif tool_name == 'scroll':
                    direction = params.get('direction', 'down')
                    amount = params.get('amount', 500)
                    if direction == 'down':
                        await self.page.evaluate(f'window.scrollBy(0, {amount})')
                    elif direction == 'up':
                        await self.page.evaluate(f'window.scrollBy(0, -{amount})')
                elif tool_name == 'navigate':
                    await self.page.goto(params.get('url', ''))
                elif tool_name == 'extract_text':
                    selector = params.get('selector', params.get('id', 'body'))
                    text = await self.page.inner_text(selector)
                    return {'success': True, 'data': {'text': text}}

                return {'success': True, 'data': {}}

            return {'success': False, 'error': 'No browser available'}

        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return {'success': False, 'error': str(e)}

    async def execute_actions(self, actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute multiple actions in sequence."""
        results = []
        for action in actions:
            action_type = action.get('type', action.get('tool', ''))
            action_params = {k: v for k, v in action.items() if k not in ('type', 'tool')}

            result = await self.execute_tool(action_type, action_params)
            results.append(result)

            if not result.get('success'):
                return {'success': False, 'error': result.get('error'), 'partial_results': results}

            # Small delay between actions
            await asyncio.sleep(0.3)

        return {'success': True, 'data': results}


class SmartBrain:
    """
    Unified brain that auto-wires all components.

    Natural language in -> intelligent automation out.
    """

    def __init__(
        self,
        llm_client=None,
        mcp_client=None,
        page=None,
        config: Optional[Dict] = None
    ):
        self.config = config or {}

        # Initialize LLM client
        if llm_client:
            self.llm_client = llm_client
        elif LLM_CLIENT_AVAILABLE:
            self.llm_client = get_llm_client(config)
        else:
            raise RuntimeError("LLM client not available")

        # Initialize components
        self.intent_detector = IntentDetector(self.llm_client)
        self.web_daemon = WebDaemon() if WEB_DAEMON_AVAILABLE else None
        self.tool_registry = ToolRegistry() if TOOL_WRAPPERS_AVAILABLE else None

        # Browser execution
        self.mcp = mcp_client
        self.page = page
        self.executor = BrowserExecutor(mcp_client, page)

        # LLM nodes
        self.planner = PlannerNode(self.llm_client)
        self.dom_navigator = DOMNavigatorNode(self.llm_client)
        self.self_healer = SelfHealingNode(self.llm_client)

        # Dual LLM orchestrator (optional, for complex tasks)
        self.orchestrator = None
        if DUAL_LLM_AVAILABLE:
            self.orchestrator = DualLLMOrchestrator(
                self.llm_client,
                browser_manager=None,
                mcp=mcp_client
            )

        # Stats
        self.stats = {
            'tasks_completed': 0,
            'tasks_failed': 0,
            'total_steps': 0,
        }

        logger.info("SmartBrain initialized")
        logger.info(f"  Components: LLM={LLM_CLIENT_AVAILABLE}, WebDaemon={WEB_DAEMON_AVAILABLE}, "
                   f"DualLLM={DUAL_LLM_AVAILABLE}, WorkerLoop={WORKER_LOOP_AVAILABLE}")

    @classmethod
    async def create(
        cls,
        mcp_client=None,
        page=None,
        config: Optional[Dict] = None
    ) -> 'SmartBrain':
        """Factory method to create SmartBrain."""
        brain = cls(
            mcp_client=mcp_client,
            page=page,
            config=config
        )

        # Start web daemon background tasks if available
        if brain.web_daemon:
            await brain.web_daemon.start_background_tasks()

        return brain

    async def run(self, user_input: str, image: Optional[str] = None) -> SmartResult:
        """
        Main entry point - process natural language input.

        Automatically selects the best model based on task type:
        - Vision tasks -> UI-TARS
        - Complex reasoning -> Kimi API
        - Everything else -> 0000/ui-tars-1.5-7b:latest

        Args:
            user_input: Natural language task description
            image: Optional base64-encoded image for vision tasks

        Returns:
            SmartResult with execution outcome
        """
        start_time = datetime.now()
        trace_id = str(uuid.uuid4())[:8]

        logger.info(f"[{trace_id}] Processing: {user_input[:100]}...")

        try:
            # Step 1: Detect intent (with model selection)
            intent = self.intent_detector.detect(user_input, has_image=bool(image))

            # Log the auto-selected model
            model_name = self._get_model_name(intent.model_type)
            logger.info(f"[{trace_id}] Detected: type={intent.task_type.value}, "
                       f"model={model_name}, complexity={intent.complexity_score:.2f}, "
                       f"confidence={intent.confidence:.2f}")

            # Step 2: Route to appropriate handler based on task type AND model
            if intent.task_type == TaskType.VISION or intent.model_type == ModelType.VISION:
                result = await self._handle_vision_task(intent, trace_id, image)
            elif intent.task_type == TaskType.COMPLEX_REASONING or intent.model_type == ModelType.COMPLEX:
                result = await self._handle_complex_task(intent, trace_id)
            elif intent.task_type == TaskType.WEB_RESEARCH and self.web_daemon:
                result = await self._handle_web_research(intent, trace_id)
            elif intent.task_type in (TaskType.WEB_AUTOMATION, TaskType.DATA_EXTRACTION,
                                      TaskType.FORM_FILLING, TaskType.NAVIGATION):
                result = await self._handle_browser_task(intent, trace_id)
            else:
                # Fallback to general task handling
                result = await self._handle_general_task(intent, trace_id)

            # Update stats
            if result.success:
                self.stats['tasks_completed'] += 1
            else:
                self.stats['tasks_failed'] += 1
            self.stats['total_steps'] += result.steps_taken

            # Add timing, trace ID, task type, and model used
            result.execution_time_seconds = (datetime.now() - start_time).total_seconds()
            result.trace_id = trace_id
            result.task_type = intent.task_type
            result.model_used = model_name

            logger.info(f"[{trace_id}] Completed: success={result.success}, "
                       f"model={model_name}, steps={result.steps_taken}, "
                       f"time={result.execution_time_seconds:.2f}s")

            return result

        except Exception as e:
            logger.error(f"[{trace_id}] Error: {e}", exc_info=True)
            return SmartResult(
                success=False,
                error=str(e),
                trace_id=trace_id,
                execution_time_seconds=(datetime.now() - start_time).total_seconds()
            )

    def _get_model_name(self, model_type: ModelType) -> str:
        """Get human-readable model name."""
        if model_type == ModelType.VISION:
            return "ui-tars"
        elif model_type == ModelType.COMPLEX:
            return "kimi"
        else:
            return "qwen3"

    async def _handle_vision_task(self, intent: IntentAnalysis, trace_id: str, image: Optional[str] = None) -> SmartResult:
        """
        Handle vision tasks using UI-TARS model.

        Used for:
        - Screenshot analysis
        - Visual element identification
        - Image-based automation
        """
        logger.info(f"[{trace_id}] Vision task (UI-TARS): {intent.goal[:50]}...")

        try:
            # Use vision model for analysis
            prompt = f"""Analyze this screen/image and help with the following task:

Task: {intent.goal}

Provide:
1. What you see on the screen
2. Relevant elements for the task
3. Suggested actions to complete the task

Be specific about element locations and types."""

            # Use vision model
            images = [image] if image else None
            response = await self.llm_client.generate(
                prompt=prompt,
                model=self.llm_client.vision_model,
                images=images,
                temperature=0.1,
                max_tokens=1024
            )

            return SmartResult(
                success=True,
                answer=response.content,
                steps_taken=1
            )

        except Exception as e:
            logger.error(f"[{trace_id}] Vision task error: {e}")
            return SmartResult(success=False, error=str(e), steps_taken=1)

    async def _handle_complex_task(self, intent: IntentAnalysis, trace_id: str) -> SmartResult:
        """
        Handle complex reasoning tasks using Kimi API.

        Used for:
        - Multi-step planning
        - Complex analysis
        - Tasks requiring deep reasoning
        """
        logger.info(f"[{trace_id}] Complex task (Kimi): {intent.goal[:50]}...")

        try:
            # Use Kimi API for complex reasoning
            prompt = f"""You are an expert assistant helping with a complex task.

Task: {intent.goal}

Think through this step by step:
1. Break down the task into subtasks
2. Analyze requirements and constraints
3. Provide a detailed solution or plan

Be thorough and precise."""

            response = await self.llm_client.generate_complex(
                prompt=prompt,
                temperature=0.3,
                max_tokens=2048
            )

            return SmartResult(
                success=True,
                answer=response.content,
                steps_taken=1
            )

        except Exception as e:
            logger.error(f"[{trace_id}] Complex task error: {e}")
            return SmartResult(success=False, error=str(e), steps_taken=1)

    async def _handle_web_research(self, intent: IntentAnalysis, trace_id: str) -> SmartResult:
        """Handle web research tasks using WebDaemon."""
        query = intent.search_query or intent.goal

        logger.info(f"[{trace_id}] Web research: {query}")

        try:
            # Use web daemon to search and fetch
            results = await self.web_daemon.web_search_and_fetch(
                query=query,
                fetch_top_n=3
            )

            # Summarize results using LLM
            content_summary = "\n\n".join([
                f"Source: {r['url']}\n{r['content'][:1000]}"
                for r in results.get('results', [])
                if r.get('success')
            ])

            if content_summary:
                # Ask LLM to synthesize answer
                prompt = f"""Based on the following web research results, answer the user's question.

Question: {intent.goal}

Research Results:
{content_summary}

Provide a concise, accurate answer:"""

                response = await self.llm_client.generate(
                    prompt=prompt,
                    temperature=0.3,
                    max_tokens=1024
                )

                return SmartResult(
                    success=True,
                    answer=response.content,
                    data={'sources': [r['url'] for r in results.get('results', [])]},
                    steps_taken=1
                )
            else:
                return SmartResult(
                    success=False,
                    error="Could not fetch research results",
                    steps_taken=1
                )

        except Exception as e:
            return SmartResult(success=False, error=str(e), steps_taken=1)

    async def _handle_browser_task(self, intent: IntentAnalysis, trace_id: str) -> SmartResult:
        """Handle browser automation tasks."""
        # Use WorkerLoop if available for full task execution
        if WORKER_LOOP_AVAILABLE:
            return await self._run_worker_loop(intent, trace_id)

        # Otherwise use simple loop
        return await self._run_simple_loop(intent, trace_id)

    async def _run_worker_loop(self, intent: IntentAnalysis, trace_id: str) -> SmartResult:
        """Run full worker loop for complex tasks."""
        job = WorkerJob(
            job_id=trace_id,
            goal=intent.goal,
            start_url=intent.target_url or 'about:blank',
            max_steps=20,
            safety=SafetyConstraints(
                max_retries_per_step=3,
                timeout_per_step=30
            )
        )

        worker = WorkerLoop(
            planner_node=self.planner,
            dom_navigator_node=self.dom_navigator,
            browser_executor=self.executor,
            self_healing_node=self.self_healer
        )

        result = await worker.run(job)

        return SmartResult(
            success=result.status.value == 'success',
            answer=result.final_answer,
            data=result.shared_state,
            steps_taken=result.total_steps,
            error=result.error
        )

    async def _run_simple_loop(self, intent: IntentAnalysis, trace_id: str) -> SmartResult:
        """Run simple execution loop for basic tasks."""
        max_steps = 15
        steps_taken = 0
        shared_state = SharedState() if WORKER_LOOP_AVAILABLE else {}

        # Navigate to start URL if provided
        if intent.target_url:
            await self.executor.navigate(intent.target_url)
            if isinstance(shared_state, SharedState):
                shared_state.current_url = intent.target_url
            steps_taken += 1

        # Main loop
        for step in range(max_steps):
            steps_taken += 1

            # Get current DOM
            dom = await self.executor.get_compressed_dom()

            # Get current state
            state_dict = shared_state.to_dict() if isinstance(shared_state, SharedState) else shared_state

            # Ask planner for next action
            decision = await self.planner.plan(
                goal=intent.goal,
                context={'current_dom': dom, 'recent_steps': []},
                shared_state=state_dict
            )

            # Check for final answer
            if decision.get('mode') == 'final_answer':
                return SmartResult(
                    success=True,
                    answer=decision.get('answer'),
                    data=state_dict,
                    steps_taken=steps_taken
                )

            # Execute action
            tool_name = decision.get('tool_name')
            params = decision.get('parameters', {})

            if tool_name:
                result = await self.executor.execute_tool(tool_name, params)

                if not result.get('success'):
                    # Try self-healing
                    heal_result = await self.self_healer.heal(
                        error=result.get('error', 'Unknown error'),
                        action=decision,
                        dom=dom or ''
                    )

                    if heal_result.get('can_retry'):
                        modified = heal_result.get('modified_action', {})
                        result = await self.executor.execute_tool(
                            modified.get('tool_name', tool_name),
                            modified.get('parameters', params)
                        )

            # Update state
            if isinstance(shared_state, SharedState):
                shared_state.current_url = await self.executor.get_current_url()
                shared_state.page_title = await self.executor.get_page_title()

            await asyncio.sleep(0.5)

        return SmartResult(
            success=False,
            error=f"Max steps ({max_steps}) reached without completing goal",
            steps_taken=steps_taken
        )

    async def _handle_general_task(self, intent: IntentAnalysis, trace_id: str) -> SmartResult:
        """Handle general/unknown tasks."""
        # Use LLM to determine best approach
        prompt = f"""User wants to: {intent.goal}

Determine the best way to help. If this requires web browsing, say "BROWSE: <url>".
If this is a question that can be answered directly, provide the answer.
If more information is needed, ask a clarifying question.

Response:"""

        response = await self.llm_client.generate(
            prompt=prompt,
            temperature=0.3,
            max_tokens=512
        )

        content = response.content

        # Check if LLM wants to browse
        if 'BROWSE:' in content:
            url_match = re.search(r'BROWSE:\s*(\S+)', content)
            if url_match:
                intent.target_url = url_match.group(1)
                intent.task_type = TaskType.WEB_AUTOMATION
                return await self._handle_browser_task(intent, trace_id)

        # Direct answer
        return SmartResult(
            success=True,
            answer=content,
            steps_taken=1
        )

    async def close(self):
        """Clean up resources."""
        if self.web_daemon:
            await self.web_daemon.close()
        if self.llm_client:
            await self.llm_client.close()
        logger.info("SmartBrain closed")

    def get_stats(self) -> Dict[str, Any]:
        """Get brain statistics."""
        return {
            **self.stats,
            'web_daemon_stats': self.web_daemon.get_stats() if self.web_daemon else None,
            'orchestrator_stats': self.orchestrator.get_stats() if self.orchestrator else None,
        }


# Convenience functions
async def run_task(task: str, mcp_client=None, page=None) -> SmartResult:
    """
    Convenience function to run a single task.

    Args:
        task: Natural language task description
        mcp_client: Optional MCP client
        page: Optional Playwright page

    Returns:
        SmartResult
    """
    brain = await SmartBrain.create(mcp_client=mcp_client, page=page)
    try:
        return await brain.run(task)
    finally:
        await brain.close()


# CLI entry point
if __name__ == "__main__":
    import sys

    async def main():
        if len(sys.argv) < 2:
            print("Usage: python smart_brain.py 'your task here'")
            return

        task = ' '.join(sys.argv[1:])
        result = await run_task(task)

        print(f"\nSuccess: {result.success}")
        if result.answer:
            print(f"Answer: {result.answer}")
        if result.error:
            print(f"Error: {result.error}")
        print(f"Steps: {result.steps_taken}")
        print(f"Time: {result.execution_time_seconds:.2f}s")

    asyncio.run(main())
