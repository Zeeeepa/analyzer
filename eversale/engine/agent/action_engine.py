"""
Action Engine - Main text-to-action interface.

Takes natural language input and:
1. Detects intent
2. Extracts parameters
3. Checks requirements (login, missing params)
4. Executes the action
5. Returns structured results

This is the primary interface for the universal agent.

NEW (2025-12-07): Advanced pre-action validation
- Visibility checks (element exists, non-zero dimensions, opacity)
- Viewport checks (scroll into view if needed)
- Obstruction detection (elementFromPoint to detect blockers)
- Interactability checks (disabled, readonly, pointer-events)
- Auto-dismiss overlays (cookie banners, modals, chat widgets)
"""

import asyncio
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger

from .intent_detector import IntentDetector, DetectedIntent, IntentCategory
from .executors.base import ActionResult, ActionStatus
from .executors.sdr import get_sdr_executor, SDR_EXECUTORS
from .executors.admin import get_admin_executor, ADMIN_EXECUTORS
from .executors.business import get_business_executor, BUSINESS_EXECUTORS
from .executors.workflows_a_to_o import get_workflow_executor, WORKFLOW_EXECUTORS
from .executors import ALL_EXECUTORS
from .cache import get_cached_research, cache_research, TTL_DAY
from .login_manager import LoginManager, SERVICES


@dataclass
class ActionRequest:
    """A request to perform an action."""
    text: str
    intent: DetectedIntent
    executor: Any = None
    validation_result: Any = None
    ready_to_execute: bool = False
    missing_params: List[str] = field(default_factory=list)
    missing_logins: List[str] = field(default_factory=list)


@dataclass
class EngineResponse:
    """Response from the action engine."""
    success: bool
    message: str
    intent: Optional[DetectedIntent] = None
    result: Optional[ActionResult] = None
    needs_input: bool = False
    input_prompts: List[str] = field(default_factory=list)
    needs_login: bool = False
    login_prompts: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)


class ActionEngine:
    """
    Main engine for converting text to actions.

    Usage:
        engine = ActionEngine()
        await engine.connect()  # Start browser

        response = await engine.process("Research Stripe for outreach")

        if response.needs_input:
            # Ask user for missing info
            pass

        if response.success:
            print(response.result)

        await engine.disconnect()
    """

    def __init__(self, headless: bool = False, chrome_profile: str = None):
        self.intent_detector = IntentDetector()
        self.login_manager = LoginManager()
        self.browser = None
        self.headless = headless
        self.chrome_profile = chrome_profile
        self.context: Dict[str, Any] = {}
        self.history: List[ActionResult] = []

    async def connect(self):
        """Start the browser."""
        from .playwright_direct import PlaywrightClient

        self.browser = PlaywrightClient(
            headless=self.headless,
            user_data_dir=self.chrome_profile
        )
        await self.browser.connect()
        logger.info("Action engine connected")

    async def disconnect(self):
        """Stop the browser."""
        if self.browser:
            await self.browser.disconnect()
        logger.info("Action engine disconnected")

    async def process(self, text: str) -> EngineResponse:
        """
        Process natural language input and execute action.

        Returns EngineResponse with results or prompts for more info.
        """
        # Step 1: Detect intent
        intent = self.intent_detector.detect(text)

        if intent.capability == "UNKNOWN":
            return EngineResponse(
                success=False,
                message="I'm not sure what you'd like me to do. Could you be more specific?",
                intent=intent,
                suggestions=[
                    "Research [company name]",
                    "Build a lead list from FB Ads",
                    "Write a cold email to [company]",
                    "Check my inbox",
                ]
            )

        logger.info(f"Detected intent: {intent.capability} - {intent.action} (confidence: {intent.confidence:.2f})")

        # Step 2: Get executor
        executor = self._get_executor(intent.capability)

        if not executor:
            return EngineResponse(
                success=False,
                message=f"Action {intent.capability} is not yet implemented.",
                intent=intent,
                suggestions=["Try: Research, Lead list, Cold email"]
            )

        # Step 3: Check login requirements
        missing_logins = self._check_login_requirements(executor.requires_login)

        if missing_logins:
            login_prompts = []
            for svc_id in missing_logins:
                svc = SERVICES.get(svc_id)
                if svc:
                    login_prompts.append(f"- {svc.name}: {svc.login_url}")

            return EngineResponse(
                success=False,
                message="Please log in to continue.",
                intent=intent,
                needs_login=True,
                login_prompts=login_prompts
            )

        # Step 4: Check required parameters
        missing_params = self._check_params(executor, intent.parameters)

        if missing_params:
            prompts = self._generate_param_prompts(intent.capability, missing_params)
            return EngineResponse(
                success=False,
                message="I need a bit more information.",
                intent=intent,
                needs_input=True,
                input_prompts=prompts
            )

        # Step 5: Check cache for research tasks
        if intent.capability == "D1" and intent.parameters.get("company"):
            cached = get_cached_research(intent.parameters["company"])
            if cached:
                logger.info(f"Using cached research for {intent.parameters['company']}")
                return EngineResponse(
                    success=True,
                    message=f"(From cache) {cached.get('message', 'Research found')}",
                    intent=intent,
                    result=ActionResult(
                        status=ActionStatus.SUCCESS,
                        action_id="cached",
                        capability=intent.capability,
                        action=intent.action,
                        data=cached,
                        message="Retrieved from cache"
                    )
                )

        # Step 6: Execute!
        executor_instance = executor(browser=self.browser, context=self.context)
        result = await executor_instance.execute(intent.parameters)

        # Step 7: Cache research results
        if intent.capability == "D1" and result.status == ActionStatus.SUCCESS:
            company = intent.parameters.get("company")
            if company:
                cache_research(company, result.data, TTL_DAY)

        # Step 8: Update history and context
        self.history.append(result)
        self._update_context(result)

        # Step 9: Generate response
        return EngineResponse(
            success=result.status == ActionStatus.SUCCESS,
            message=result.message,
            intent=intent,
            result=result,
            suggestions=result.next_actions if result.next_actions else []
        )

    async def process_with_params(self, text: str, params: Dict[str, Any]) -> EngineResponse:
        """Process with additional parameters (for follow-up)."""
        # Merge params into text analysis
        intent = self.intent_detector.detect(text)
        intent.parameters.update(params)

        # Re-process with merged params
        return await self._execute_intent(intent)

    async def _execute_intent(self, intent: DetectedIntent) -> EngineResponse:
        """Execute a pre-parsed intent."""
        executor = self._get_executor(intent.capability)

        if not executor:
            return EngineResponse(
                success=False,
                message=f"Action {intent.capability} is not implemented.",
                intent=intent
            )

        executor_instance = executor(browser=self.browser, context=self.context)
        result = await executor_instance.execute(intent.parameters)

        self.history.append(result)
        self._update_context(result)

        return EngineResponse(
            success=result.status == ActionStatus.SUCCESS,
            message=result.message,
            intent=intent,
            result=result,
            suggestions=result.next_actions if result.next_actions else []
        )

    def _get_executor(self, capability: str):
        """Get executor class for capability."""
        # Check combined registry first (fastest lookup)
        if capability in ALL_EXECUTORS:
            return ALL_EXECUTORS[capability]

        # Fallback to individual registries for flexibility
        if capability in SDR_EXECUTORS:
            return SDR_EXECUTORS[capability]
        if capability in ADMIN_EXECUTORS:
            return ADMIN_EXECUTORS[capability]
        if capability in BUSINESS_EXECUTORS:
            return BUSINESS_EXECUTORS[capability]
        if capability in WORKFLOW_EXECUTORS:
            return WORKFLOW_EXECUTORS[capability]

        logger.warning(f"No executor found for capability: {capability}")
        return None

    def _check_login_requirements(self, required: List[str]) -> List[str]:
        """Check which required logins are missing."""
        missing = []
        for svc_id in required:
            if not self.login_manager.is_logged_in(svc_id):
                missing.append(svc_id)
        return missing

    def _check_params(self, executor_class, params: Dict) -> List[str]:
        """Check which required params are missing."""
        missing = []
        for param in executor_class.required_params:
            if param not in params or not params[param]:
                missing.append(param)
        return missing

    def _generate_param_prompts(self, capability: str, missing: List[str]) -> List[str]:
        """Generate prompts for missing parameters."""
        prompts = {
            "company": "What company should I research?",
            "recipient": "Who should I address the email to?",
            "value_prop": "What value proposition should I highlight?",
            "industry": "What industry are you targeting?",
            "query": "What should I search for?",
            "attendee": "Who should I schedule the meeting with?",
        }

        return [prompts.get(p, f"Please provide: {p}") for p in missing]

    def _update_context(self, result: ActionResult):
        """Update context with result data for follow-up actions."""
        if result.status == ActionStatus.SUCCESS:
            # Store last action info
            self.context["last_action"] = result.action
            self.context["last_capability"] = result.capability

            # Store specific data for chaining
            if result.capability == "D1" and result.data:
                self.context["last_research"] = result.data
                if result.data.get("company_name"):
                    self.context["current_company"] = result.data["company_name"]

            if result.capability == "D5" and result.data:
                self.context["last_leads"] = result.data.get("leads", [])

    async def confirm_login(self, service_id: str) -> bool:
        """Verify and mark a service as logged in."""
        if self.browser:
            logged_in = await self.login_manager.verify_login(service_id, self.browser)
            return logged_in
        return False

    def get_suggestions(self) -> List[str]:
        """Get suggested next actions based on context."""
        suggestions = []

        if self.context.get("current_company"):
            company = self.context["current_company"]
            suggestions.append(f"Write a cold email to {company}")

        if self.context.get("last_leads"):
            suggestions.append("Research the top leads")
            suggestions.append("Qualify leads")

        if not suggestions:
            suggestions = [
                "Build a lead list from FB Ads",
                "Research [company name]",
                "Check my inbox",
            ]

        return suggestions

    # ==============================================================================
    # ADVANCED PRE-ACTION VALIDATION (2025-12-07)
    # ==============================================================================
    # Ensures click/type actions ALWAYS succeed by checking for obstructions BEFORE executing

    @staticmethod
    async def validate_element_interactable(
        page,
        selector: str
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Comprehensive pre-action validation for click/type operations.

        Returns:
            (is_interactable, reason_if_not, fix_suggestion)

        fix_suggestion dict may contain:
            - scroll_needed: bool
            - scroll_coords: {'x': int, 'y': int}
            - obstruction_selector: str (element blocking target)
            - obstruction_type: str (cookie_banner, modal, chat_widget, fixed_header)
            - suggested_action: str (dismiss, scroll, wait)
        """
        try:
            # Step 1: Element existence check
            element = await page.query_selector(selector)
            if not element:
                return (False, "Element not found in DOM", {
                    "suggested_action": "retry_with_alternative_selector"
                })

            # Step 2: Visibility check (dimensions, display, visibility, opacity)
            is_visible = await element.is_visible()
            if not is_visible:
                style = await page.evaluate("""(selector) => {
                    const el = document.querySelector(selector);
                    if (!el) return null;
                    const computed = window.getComputedStyle(el);
                    return {
                        display: computed.display,
                        visibility: computed.visibility,
                        opacity: computed.opacity,
                        width: el.offsetWidth,
                        height: el.offsetHeight
                    };
                }""", selector)

                reason = "Element not visible: "
                if style:
                    if style.get('display') == 'none':
                        reason += "display: none"
                    elif style.get('visibility') == 'hidden':
                        reason += "visibility: hidden"
                    elif float(style.get('opacity', 1)) == 0:
                        reason += "opacity: 0"
                    elif style.get('width', 0) == 0 or style.get('height', 0) == 0:
                        reason += f"zero dimensions ({style.get('width')}x{style.get('height')})"
                    else:
                        reason += "unknown reason"
                else:
                    reason += "element not in DOM"

                return (False, reason, {
                    "suggested_action": "wait_for_visible",
                    "style_info": style
                })

            # Step 3: Viewport check
            box = await element.bounding_box()
            if not box:
                return (False, "Element has no bounding box", {
                    "suggested_action": "scroll_into_view"
                })

            viewport_size = await page.evaluate("""() => ({
                width: window.innerWidth,
                height: window.innerHeight
            })""")

            in_viewport = (
                box['x'] >= 0 and
                box['y'] >= 0 and
                box['x'] + box['width'] <= viewport_size['width'] and
                box['y'] + box['height'] <= viewport_size['height']
            )

            if not in_viewport:
                return (False, "Element outside viewport", {
                    "scroll_needed": True,
                    "scroll_coords": {
                        "x": int(box['x'] + box['width'] / 2),
                        "y": int(box['y'] + box['height'] / 2)
                    },
                    "suggested_action": "scroll_into_view"
                })

            # Step 4: Obstruction check (CRITICAL - elementFromPoint)
            center_x = box['x'] + box['width'] / 2
            center_y = box['y'] + box['height'] / 2

            obstruction_info = await page.evaluate("""({selector, x, y}) => {
                const targetEl = document.querySelector(selector);
                if (!targetEl) return {obstructed: true, reason: 'target_not_found'};

                const topEl = document.elementFromPoint(x, y);
                if (!topEl) return {obstructed: true, reason: 'no_element_at_point'};

                // Check if topEl is the target or contains the target
                if (topEl === targetEl || topEl.contains(targetEl) || targetEl.contains(topEl)) {
                    return {obstructed: false};
                }

                // Element is obstructed - identify the blocker
                const blocker = topEl;
                const blockerInfo = {
                    obstructed: true,
                    blocker_tag: blocker.tagName,
                    blocker_id: blocker.id,
                    blocker_class: blocker.className,
                    blocker_text: blocker.innerText?.substring(0, 50),
                    blocker_selector: null,
                    blocker_type: 'unknown'
                };

                // Build a selector for the blocker
                if (blocker.id) {
                    blockerInfo.blocker_selector = `#${blocker.id}`;
                } else if (blocker.className) {
                    const classes = blocker.className.split(' ').filter(c => c);
                    if (classes.length > 0) {
                        blockerInfo.blocker_selector = `.${classes[0]}`;
                    }
                }

                // Identify blocker type by common patterns
                const blockerLower = (blocker.className + ' ' + blocker.id + ' ' + blocker.innerText).toLowerCase();
                if (blockerLower.includes('cookie') || blockerLower.includes('consent') || blockerLower.includes('gdpr')) {
                    blockerInfo.blocker_type = 'cookie_banner';
                } else if (blockerLower.includes('modal') || blockerLower.includes('dialog') || blockerLower.includes('popup')) {
                    blockerInfo.blocker_type = 'modal';
                } else if (blockerLower.includes('chat') || blockerLower.includes('intercom') || blockerLower.includes('drift')) {
                    blockerInfo.blocker_type = 'chat_widget';
                } else if (blockerLower.includes('header') && window.getComputedStyle(blocker).position === 'fixed') {
                    blockerInfo.blocker_type = 'fixed_header';
                } else if (blockerLower.includes('banner') || blockerLower.includes('notification')) {
                    blockerInfo.blocker_type = 'banner';
                }

                return blockerInfo;
            }""", {"selector": selector, "x": center_x, "y": center_y})

            if obstruction_info.get('obstructed'):
                blocker_type = obstruction_info.get('blocker_type', 'unknown')
                blocker_selector = obstruction_info.get('blocker_selector')

                reason = f"Element obstructed by {blocker_type}"
                if obstruction_info.get('blocker_text'):
                    reason += f": {obstruction_info.get('blocker_text')[:30]}"

                return (False, reason, {
                    "obstruction_selector": blocker_selector,
                    "obstruction_type": blocker_type,
                    "obstruction_info": obstruction_info,
                    "suggested_action": "dismiss_obstruction"
                })

            # Step 5: Interactability check (disabled, readonly, pointer-events)
            interactability = await page.evaluate("""(selector) => {
                const el = document.querySelector(selector);
                if (!el) return {interactable: false, reason: 'not_found'};

                const computed = window.getComputedStyle(el);
                const issues = [];

                if (el.disabled) {
                    issues.push('disabled');
                }
                if (el.readOnly) {
                    issues.push('readonly');
                }
                if (computed.pointerEvents === 'none') {
                    issues.push('pointer-events: none');
                }
                if (el.hasAttribute('aria-disabled') && el.getAttribute('aria-disabled') === 'true') {
                    issues.push('aria-disabled');
                }

                return {
                    interactable: issues.length === 0,
                    issues: issues
                };
            }""", selector)

            if not interactability.get('interactable'):
                issues = interactability.get('issues', [])
                return (False, f"Element not interactable: {', '.join(issues)}", {
                    "suggested_action": "wait_for_enabled",
                    "interactability_issues": issues
                })

            # All checks passed!
            return (True, "Element is interactable", None)

        except Exception as e:
            logger.error(f"Validation error for selector '{selector}': {e}")
            return (False, f"Validation error: {str(e)}", {
                "suggested_action": "retry"
            })

    @staticmethod
    async def dismiss_obstructions(page) -> bool:
        """
        Attempt to dismiss common page obstructions (cookie banners, modals, chat widgets).

        Returns:
            True if obstruction was cleared, False otherwise
        """
        try:
            # Strategy 1: Try ESC key (dismisses most modals)
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.3)

            # Strategy 2: Look for common dismiss buttons and click them
            dismiss_selectors = [
                # Cookie banners
                "button[id*='accept']", "button[class*='accept']",
                "button[id*='cookie']", "button[class*='cookie']",
                "button[id*='consent']", "button[class*='consent']",
                "a[id*='accept']", "a[class*='accept']",
                "#onetrust-accept-btn-handler",  # OneTrust
                ".cookie-consent-accept",
                "[data-testid*='accept']", "[data-testid*='cookie']",

                # Modal close buttons
                "button[aria-label*='close' i]", "button[aria-label*='dismiss' i]",
                "button[class*='close']", "button[class*='dismiss']",
                "[data-dismiss='modal']",
                ".modal-close", ".dialog-close",
                "button.close", "a.close",

                # Chat widgets
                "button[aria-label*='minimize' i]", "button[aria-label*='close chat' i]",
                "#intercom-container button[aria-label*='close' i]",
                ".drift-widget-controller-icon",

                # Generic overlays
                "[role='dialog'] button", "[role='alertdialog'] button",
                ".overlay button", ".popup button",
            ]

            for selector in dismiss_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element and await element.is_visible():
                        await element.click()
                        logger.info(f"Dismissed obstruction using selector: {selector}")
                        await asyncio.sleep(0.3)
                        return True
                except Exception:
                    continue

            # Strategy 3: Click outside modal (backdrop click)
            try:
                backdrop = await page.query_selector(".modal-backdrop, .overlay-backdrop, [class*='backdrop']")
                if backdrop and await backdrop.is_visible():
                    await backdrop.click()
                    await asyncio.sleep(0.3)
                    logger.info("Dismissed obstruction by clicking backdrop")
                    return True
            except Exception:
                pass

            # Strategy 4: Execute JavaScript to remove fixed overlays
            removed = await page.evaluate("""() => {
                const overlays = document.querySelectorAll('[class*="cookie"], [class*="modal"], [class*="popup"], [id*="cookie"], [id*="modal"]');
                let removed = 0;
                overlays.forEach(el => {
                    const style = window.getComputedStyle(el);
                    if (style.position === 'fixed' && (style.zIndex > 1000 || el.offsetHeight > 100)) {
                        el.remove();
                        removed++;
                    }
                });
                return removed;
            }""")

            if removed > 0:
                logger.info(f"Removed {removed} overlay elements via JavaScript")
                return True

            return False

        except Exception as e:
            logger.error(f"Error dismissing obstructions: {e}")
            return False

    @staticmethod
    async def scroll_element_into_view(page, selector: str) -> bool:
        """
        Scroll element into center of viewport with human-like animation.

        Returns:
            True if scroll succeeded, False otherwise
        """
        try:
            element = await page.query_selector(selector)
            if not element:
                return False

            # Scroll into view with smooth animation
            await page.evaluate("""(selector) => {
                const el = document.querySelector(selector);
                if (el) {
                    el.scrollIntoView({
                        behavior: 'smooth',
                        block: 'center',
                        inline: 'center'
                    });
                }
            }""", selector)

            # Wait for scroll animation to complete
            await asyncio.sleep(0.5)

            # Verify element is now in viewport
            box = await element.bounding_box()
            if box:
                viewport_size = await page.evaluate("""() => ({
                    width: window.innerWidth,
                    height: window.innerHeight
                })""")

                in_viewport = (
                    box['x'] >= 0 and
                    box['y'] >= 0 and
                    box['x'] + box['width'] <= viewport_size['width'] and
                    box['y'] + box['height'] <= viewport_size['height']
                )

                return in_viewport

            return False

        except Exception as e:
            logger.error(f"Error scrolling element into view: {e}")
            return False

    @staticmethod
    async def hover_before_action(page, selector: str) -> bool:
        """
        Human-like hover simulation before click/type action.

        Returns:
            True if hover succeeded, False otherwise
        """
        try:
            element = await page.query_selector(selector)
            if not element:
                return False

            # Hover over element
            await element.hover()

            # Brief human-like pause
            await asyncio.sleep(0.05 + (0.05 * asyncio.get_event_loop().time() % 1))

            return True

        except Exception as e:
            logger.debug(f"Error hovering element: {e}")
            return False

    async def validate_and_prepare_action(
        self,
        selector: str,
        action_type: str = "click"
    ) -> Tuple[bool, Optional[str]]:
        """
        High-level validation and preparation for click/type actions.

        Performs all validation checks and auto-fixes common issues:
        - Scrolls element into view if needed
        - Dismisses obstructions (cookie banners, modals)
        - Hovers before action (human-like)

        Args:
            selector: CSS selector for target element
            action_type: "click" or "type"

        Returns:
            (ready, error_message)
            ready: True if element is ready for action
            error_message: Description of why element is not ready (if ready=False)
        """
        if not self.browser or not self.browser.page:
            return (False, "Browser not connected")

        page = self.browser.page

        # Step 1: Initial validation
        is_interactable, reason, fix_suggestion = await self.validate_element_interactable(page, selector)

        if is_interactable:
            # Element is ready - just hover before action
            await self.hover_before_action(page, selector)
            return (True, None)

        # Step 2: Try to fix issues based on suggestions
        if not fix_suggestion:
            return (False, reason)

        suggested_action = fix_suggestion.get("suggested_action")

        # Handle scroll needed
        if suggested_action == "scroll_into_view" or fix_suggestion.get("scroll_needed"):
            logger.info(f"Scrolling element into view: {selector}")
            scroll_success = await self.scroll_element_into_view(page, selector)

            if not scroll_success:
                return (False, f"Failed to scroll element into view: {reason}")

            # Re-validate after scroll
            is_interactable, reason, fix_suggestion = await self.validate_element_interactable(page, selector)
            if is_interactable:
                await self.hover_before_action(page, selector)
                return (True, None)

            # Update suggested_action after re-validation
            suggested_action = fix_suggestion.get("suggested_action") if fix_suggestion else None

        # Handle obstruction
        if suggested_action == "dismiss_obstruction":
            logger.info(f"Attempting to dismiss obstruction: {fix_suggestion.get('obstruction_type')}")
            dismiss_success = await self.dismiss_obstructions(page)

            if dismiss_success:
                # Re-validate after dismissal
                is_interactable, reason, fix_suggestion = await self.validate_element_interactable(page, selector)
                if is_interactable:
                    await self.hover_before_action(page, selector)
                    return (True, None)

            return (False, f"Could not dismiss obstruction: {reason}")

        # Handle wait scenarios
        if suggested_action in ["wait_for_visible", "wait_for_enabled"]:
            logger.info(f"Waiting for element to become {suggested_action.split('_')[-1]}")
            try:
                await page.wait_for_selector(selector, state="visible" if "visible" in suggested_action else "attached", timeout=5000)

                # Re-validate after wait
                is_interactable, reason, _ = await self.validate_element_interactable(page, selector)
                if is_interactable:
                    await self.hover_before_action(page, selector)
                    return (True, None)

            except Exception as e:
                return (False, f"Timeout waiting for element: {reason}")

        # Could not fix the issue
        return (False, reason)


# Convenience functions
async def quick_action(text: str, chrome_profile: str = None) -> EngineResponse:
    """Quick one-off action execution."""
    engine = ActionEngine(headless=False, chrome_profile=chrome_profile)

    try:
        await engine.connect()
        response = await engine.process(text)
        return response
    finally:
        await engine.disconnect()


# Example usage
async def demo():
    """Demo the action engine."""
    # NOTE: chrome_profile=None uses isolated profile at ~/.eversale/browser-profile
    # This prevents corrupting the user's normal Chrome profile
    engine = ActionEngine(
        headless=False,
        chrome_profile=None  # Uses isolated profile - never use user's real Chrome profile!
    )

    try:
        await engine.connect()

        # Test various inputs
        tests = [
            "Research Stripe",
            "Build a lead list from FB Ads for SaaS companies",
            "Write a cold email to Acme Corp",
        ]

        for text in tests:
            print(f"\n{'='*50}")
            print(f"Input: {text}")
            print("="*50)

            response = await engine.process(text)

            print(f"Success: {response.success}")
            print(f"Message: {response.message}")

            if response.intent:
                print(f"Intent: {response.intent.capability} - {response.intent.action}")
                print(f"Confidence: {response.intent.confidence:.2f}")

            if response.needs_input:
                print(f"Needs input: {response.input_prompts}")

            if response.needs_login:
                print(f"Needs login: {response.login_prompts}")

            if response.suggestions:
                print(f"Suggestions: {response.suggestions}")

    finally:
        await engine.disconnect()


if __name__ == "__main__":
    asyncio.run(demo())
