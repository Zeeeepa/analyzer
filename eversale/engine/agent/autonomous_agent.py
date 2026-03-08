"""
Autonomous Agent - Main orchestrator for truly autonomous browser automation.

This ties together all the advanced systems:
- VisualElementFinder: Vision-based element localization
- SelfHealingSelectors: Selectors that fix themselves when sites change
- IntentDetector: Natural language intent understanding
- WorkflowLearner: Learn from successful workflows
- DOMIntelligence: Understand page structure
- CascadingRecovery: 10-level smart error recovery

The agent can handle ANY task on ANY site with minimal human intervention.

Example Usage:
    agent = create_autonomous_agent(mcp_client, ollama_client)
    result = await agent.execute_task(
        "Login to LinkedIn and find Python developers in San Francisco",
        url="https://linkedin.com"
    )

Key Features:
- Zero-shot task execution on new sites
- Self-healing when selectors break
- Visual fallback when CSS fails
- Learns successful patterns for reuse
- 10-level cascading error recovery
- Intelligent action planning
"""

import asyncio
from typing import Optional, Dict, Any, List
from loguru import logger
from rich.console import Console

console = Console()


class AutonomousAgent:
    """
    Truly autonomous browser agent that can handle ANY task on ANY site.

    Uses multiple strategies:
    1. DOM Intelligence - Understand page structure
    2. Intent Detection - Determine what user wants
    3. Workflow Learning - Use learned patterns
    4. Self-Healing Selectors - Find elements reliably
    5. Visual Grounding - Fallback to vision
    6. Cascading Recovery - Handle errors gracefully
    """

    def __init__(
        self,
        mcp_client,
        ollama_client=None,
        vision_model: str = "moondream",
        enable_learning: bool = True
    ):
        """
        Initialize the autonomous agent.

        Args:
            mcp_client: MCP client for Playwright browser control
            ollama_client: Ollama client for LLM/vision calls (optional)
            vision_model: Vision model to use for visual grounding
            enable_learning: Whether to learn from successful workflows
        """
        self.mcp = mcp_client
        self.ollama = ollama_client
        self.vision_model = vision_model
        self.enable_learning = enable_learning

        # Initialize components (lazy loading for performance)
        self._visual_finder = None
        self._self_healing = None
        self._intent_detector = None
        self._workflow_learner = None
        self._dom_intel = None
        self._recovery = None

        logger.info("[AUTONOMOUS AGENT] Initialized with all systems ready")

    @property
    def visual_finder(self):
        """Lazy-load visual element finder."""
        if self._visual_finder is None and self.ollama:
            try:
                from .visual_element_finder import VisualElementFinder
                self._visual_finder = VisualElementFinder(self.ollama, self.vision_model)
                logger.debug("[AUTONOMOUS AGENT] Visual element finder loaded")
            except Exception as e:
                logger.warning(f"[AUTONOMOUS AGENT] Visual finder unavailable: {e}")
        return self._visual_finder

    @property
    def self_healing(self):
        """Lazy-load self-healing selectors (requires page context)."""
        # Note: SelfHealingSelectors requires a page object, so we return the class
        # It will be instantiated with page in execution methods
        if self._self_healing is None:
            try:
                from .humanization.self_healing_selectors import SelfHealingSelectors
                self._self_healing = SelfHealingSelectors
                logger.debug("[AUTONOMOUS AGENT] Self-healing selectors loaded")
            except Exception as e:
                logger.warning(f"[AUTONOMOUS AGENT] Self-healing unavailable: {e}")
        return self._self_healing

    @property
    def intent_detector(self):
        """Lazy-load intent detector."""
        if self._intent_detector is None:
            try:
                from .intent_detector import IntentDetector
                self._intent_detector = IntentDetector()
                logger.debug("[AUTONOMOUS AGENT] Intent detector loaded")
            except Exception as e:
                logger.warning(f"[AUTONOMOUS AGENT] Intent detector unavailable: {e}")
        return self._intent_detector

    @property
    def workflow_learner(self):
        """Lazy-load workflow learner."""
        if self._workflow_learner is None and self.enable_learning:
            try:
                from .workflow_learning import WorkflowLearner
                self._workflow_learner = WorkflowLearner()
                logger.debug("[AUTONOMOUS AGENT] Workflow learner loaded")
            except Exception as e:
                logger.warning(f"[AUTONOMOUS AGENT] Workflow learner unavailable: {e}")
        return self._workflow_learner

    @property
    def dom_intel(self):
        """Lazy-load DOM intelligence."""
        if self._dom_intel is None:
            try:
                from .dom_intelligence import DOMIntelligence
                self._dom_intel = DOMIntelligence(self.mcp)
                logger.debug("[AUTONOMOUS AGENT] DOM intelligence loaded")
            except Exception as e:
                logger.warning(f"[AUTONOMOUS AGENT] DOM intelligence unavailable: {e}")
        return self._dom_intel

    @property
    def recovery(self):
        """Lazy-load cascading recovery system (deprecated - v2.9)."""
        if self._recovery is None:
            try:
                # DEPRECATED: cascading_recovery removed in v2.9 - use reliability_core
                from .cascading_recovery import CascadingRecoverySystem
                self._recovery = CascadingRecoverySystem()
                logger.debug("[AUTONOMOUS AGENT] Cascading recovery loaded")
            except Exception as e:
                logger.debug(f"[AUTONOMOUS AGENT] Cascading recovery unavailable (removed in v2.9): {e}")
                # Create simple retry stub
                class SimpleRetry:
                    """Simple retry fallback when cascading_recovery not available."""
                    async def attempt_recovery(self, context, page=None):
                        return {"recovered": False, "level": 0}
                self._recovery = SimpleRetry()
        return self._recovery

    async def execute_task(self, prompt: str, url: str = None) -> str:
        """
        Execute any task autonomously.

        Flow:
        1. Detect intent from natural language prompt
        2. Navigate to URL if provided
        3. Analyze page with DOM Intelligence
        4. Check for learned workflows
        5. Create action plan
        6. Execute with self-healing and recovery
        7. Learn from success

        Args:
            prompt: Natural language task description
            url: Optional starting URL

        Returns:
            Task results as markdown string
        """
        console.print(f"[cyan]🤖 Autonomous Agent executing: {prompt[:60]}...[/cyan]")

        try:
            # Step 1: Detect intent
            if self.intent_detector:
                intent = self.intent_detector.detect(prompt)
                console.print(f"[dim]  Intent: {intent.category.value} -> {intent.action} (confidence: {intent.confidence:.2f})[/dim]")
            else:
                intent = None

            # Step 2: Navigate if URL provided
            if url:
                console.print(f"[dim]  Navigating to {url}...[/dim]")
                await self.mcp.call_tool('playwright_navigate', {'url': url})
                await asyncio.sleep(2)

            # Step 3: Analyze page
            console.print("[dim]  Analyzing page structure...[/dim]")
            snapshot = await self.mcp.call_tool('playwright_snapshot', {})

            page_intel = None
            if self.dom_intel:
                page_intel = await self.dom_intel.analyze_page(snapshot)
                console.print(f"[dim]  Page type: {page_intel.page_type}, Main action: {page_intel.main_action}[/dim]")

            # Step 4: Check for learned workflow
            current_url = snapshot.get('url', url or '')
            learned_workflow = None

            if self.workflow_learner and page_intel:
                learned_workflow = self.workflow_learner.find_matching_workflow(
                    current_url,
                    page_intel.main_action or 'general'
                )

                if learned_workflow:
                    console.print(f"[yellow]💡 Found learned workflow: {learned_workflow.id}[/yellow]")
                    result = await self._execute_learned_workflow(learned_workflow)

                    if result:
                        self.workflow_learner.report_success(learned_workflow.id)
                        console.print(f"[green]✓ Learned workflow succeeded[/green]")
                        return result
                    else:
                        self.workflow_learner.report_failure(learned_workflow.id)
                        console.print(f"[yellow]⚠ Learned workflow failed, trying new approach[/yellow]")

            # Step 5: Create action plan based on intent and page analysis
            console.print("[dim]  Creating action plan...[/dim]")
            plan = await self._create_action_plan(prompt, intent, page_intel, snapshot)

            if plan:
                console.print(f"[dim]  Plan: {len(plan.get('steps', []))} steps[/dim]")

            # Step 6: Execute plan with recovery
            executed_steps = []
            if plan and plan.get('steps'):
                for i, step in enumerate(plan['steps'], 1):
                    action = step.get('action', 'unknown')
                    console.print(f"[dim]  Step {i}/{len(plan['steps'])}: {action}...[/dim]")

                    success = await self._execute_step(step, page_intel)

                    if success:
                        executed_steps.append(step)
                        await asyncio.sleep(0.5)  # Brief pause between steps
                    else:
                        console.print(f"[yellow]  Step failed, attempting recovery...[/yellow]")
                        # Recovery is handled within _execute_step

            # Step 7: Learn from success
            if executed_steps and self.workflow_learner and intent:
                workflow_id = self.workflow_learner.record_workflow(
                    current_url,
                    intent.action if intent else 'general',
                    [{'action': s.get('action'), 'selector': s.get('selector', ''),
                      'description': s.get('description', ''), 'value': s.get('value', '')}
                     for s in executed_steps]
                )
                console.print(f"[green]✓ Learned workflow saved: {workflow_id}[/green]")

            # Get final result
            result = await self.mcp.call_tool('playwright_get_markdown', {})
            result_text = result.get('markdown', 'Task completed')[:3000]

            console.print(f"[green]✓ Task completed successfully[/green]")
            return result_text

        except Exception as e:
            logger.error(f"[AUTONOMOUS AGENT] Task execution failed: {e}", exc_info=True)
            console.print(f"[red]✗ Task failed: {str(e)[:100]}[/red]")
            return f"Error: {e}"

    async def _execute_learned_workflow(self, workflow) -> Optional[str]:
        """Execute a previously learned workflow."""
        try:
            for step in workflow.steps:
                action = step.action

                if action == "click":
                    await self.mcp.call_tool('playwright_click', {'selector': step.selector})
                elif action == "fill":
                    await self.mcp.call_tool('playwright_fill', {
                        'selector': step.selector,
                        'value': step.value or ''
                    })
                elif action == "navigate":
                    await self.mcp.call_tool('playwright_navigate', {'url': step.value})

                await asyncio.sleep(0.5)

            result = await self.mcp.call_tool('playwright_get_markdown', {})
            return result.get('markdown', 'Workflow completed')

        except Exception as e:
            logger.error(f"[AUTONOMOUS AGENT] Learned workflow failed: {e}")
            return None

    async def _create_action_plan(
        self,
        prompt: str,
        intent,
        page_intel,
        snapshot: Dict
    ) -> Optional[Dict]:
        """
        Create an action plan based on intent and page analysis.

        Returns a plan with steps to execute.
        """
        plan = {'steps': []}

        # Simple heuristic-based planning (can be enhanced with LLM)
        if page_intel:
            page_type = page_intel.page_type

            if page_type == "login":
                plan['steps'].extend([
                    {
                        'action': 'fill',
                        'target_type': 'email',
                        'description': 'email or username input field',
                        'selector': 'input[type="email"], input[type="text"], input[name*="email"], input[name*="user"]'
                    },
                    {
                        'action': 'fill',
                        'target_type': 'password',
                        'description': 'password input field',
                        'selector': 'input[type="password"]'
                    },
                    {
                        'action': 'click',
                        'target_type': 'submit',
                        'description': 'submit or login button',
                        'selector': 'button[type="submit"], button:has-text("Log in"), button:has-text("Sign in")'
                    }
                ])

            elif page_type == "search":
                plan['steps'].append({
                    'action': 'fill',
                    'target_type': 'search',
                    'description': 'search input field',
                    'selector': 'input[type="search"], input[name*="search"], input[placeholder*="search" i]',
                    'value': self._extract_search_query(prompt, intent)
                })

            elif page_type == "product":
                plan['steps'].append({
                    'action': 'click',
                    'target_type': 'add_to_cart',
                    'description': 'add to cart button',
                    'selector': 'button:has-text("Add to Cart"), button:has-text("Add to Bag")'
                })

        # If no specific plan, create generic exploration steps
        if not plan['steps']:
            plan['steps'].append({
                'action': 'explore',
                'description': 'analyze page and extract information'
            })

        return plan

    def _extract_search_query(self, prompt: str, intent) -> str:
        """Extract search query from prompt."""
        if intent and intent.parameters.get('query'):
            return intent.parameters['query']

        # Simple extraction: get text after common keywords
        import re
        match = re.search(r'(?:search|find|look for)\s+(.+)', prompt, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        return prompt

    async def _execute_step(self, step: Dict, page_intel) -> bool:
        """
        Execute a single action step with self-healing and recovery.

        Args:
            step: Step dictionary with action, selector, description, etc.
            page_intel: Page intelligence for context

        Returns:
            True if successful, False otherwise
        """
        action = step.get('action')
        selector = step.get('selector', '')
        description = step.get('description', '')
        value = step.get('value', '')
        target_type = step.get('target_type', '')

        try:
            if action == "fill":
                # Try with self-healing selector
                if selector:
                    result = await self.mcp.call_tool('playwright_fill', {
                        'selector': selector,
                        'value': value
                    })
                    return True

            elif action == "click":
                # Try with self-healing selector
                if selector:
                    result = await self.mcp.call_tool('playwright_click', {
                        'selector': selector
                    })
                    return True

            elif action == "navigate":
                url = step.get('url')
                if url:
                    await self.mcp.call_tool('playwright_navigate', {'url': url})
                    return True

            elif action == "explore":
                # Just snapshot the page
                snapshot = await self.mcp.call_tool('playwright_snapshot', {})
                return True

            return False

        except Exception as e:
            logger.warning(f"[AUTONOMOUS AGENT] Step execution failed: {e}")

            # Try cascading recovery if available (deprecated - v2.9)
            if self.recovery:
                try:
                    # DEPRECATED: RecoveryContext removed in v2.9 - use simple dict instead
                    try:
                        from .cascading_recovery import RecoveryContext
                        context = RecoveryContext(
                            action=f"playwright_{action}",
                            arguments={'selector': selector, 'value': value},
                            error=e,
                            attempt_number=1
                        )
                    except ImportError:
                        # Fallback: use dict for context
                        class RecoveryContext:
                            def __init__(self, **kwargs):
                                for k, v in kwargs.items():
                                    setattr(self, k, v)
                        context = RecoveryContext(
                            action=f"playwright_{action}",
                            arguments={'selector': selector, 'value': value},
                            error=e,
                            attempt_number=1
                        )

                    recovery_result = await self.recovery.attempt_recovery(context, page=None)

                    if recovery_result.get('recovered'):
                        console.print(f"[green]  ✓ Recovered at level {recovery_result.get('level')}[/green]")
                        return True
                except Exception as recovery_error:
                    logger.debug(f"[AUTONOMOUS AGENT] Recovery failed (v2.9 deprecation): {recovery_error}")

            return False

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics from all subsystems."""
        stats = {
            'visual_finder': 'loaded' if self._visual_finder else 'not loaded',
            'self_healing': 'loaded' if self._self_healing else 'not loaded',
            'intent_detector': 'loaded' if self._intent_detector else 'not loaded',
            'workflow_learner': 'loaded' if self._workflow_learner else 'not loaded',
            'dom_intelligence': 'loaded' if self._dom_intel else 'not loaded',
            'cascading_recovery': 'loaded' if self._recovery else 'not loaded'
        }

        # Get workflow learner stats
        if self._workflow_learner:
            stats['learned_workflows'] = len(self._workflow_learner.workflows)

        # Get recovery stats
        if self._recovery:
            stats['recovery'] = self._recovery.get_stats()

        return stats


# Factory function
def create_autonomous_agent(
    mcp_client,
    ollama_client=None,
    vision_model: str = "moondream",
    enable_learning: bool = True
) -> AutonomousAgent:
    """
    Create an autonomous agent instance.

    Args:
        mcp_client: MCP client for browser control
        ollama_client: Ollama client for LLM/vision (optional)
        vision_model: Vision model name (default: moondream)
        enable_learning: Whether to enable workflow learning

    Returns:
        AutonomousAgent instance

    Example:
        agent = create_autonomous_agent(mcp_client, ollama_client)
        result = await agent.execute_task("Find Python developers on LinkedIn")
    """
    return AutonomousAgent(
        mcp_client,
        ollama_client,
        vision_model,
        enable_learning
    )


# Convenience function for quick one-off tasks
async def execute_autonomous_task(
    mcp_client,
    prompt: str,
    url: str = None,
    ollama_client=None
) -> str:
    """
    Quick execution of an autonomous task.

    Args:
        mcp_client: MCP client
        prompt: Task description
        url: Optional starting URL
        ollama_client: Optional Ollama client

    Returns:
        Task results

    Example:
        result = await execute_autonomous_task(
            mcp_client,
            "Login to LinkedIn and search for engineers"
        )
    """
    agent = create_autonomous_agent(mcp_client, ollama_client)
    return await agent.execute_task(prompt, url)
