"""
Interaction Validator - Ensure Actions Succeed

Pre-action validation:
1. Element exists and is interactable
2. No obstructions blocking element
3. Element is in viewport or scrollable
4. Correct element type for action

Post-action validation:
1. Action had expected effect
2. Page state changed appropriately
3. No errors occurred
4. Element state updated correctly

Integration:
- action_engine.py: Wrap all actions with validation
- browser_manager.py: Validate browser health before actions
- playwright_direct.py: Low-level validation hooks
"""

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from loguru import logger

try:
    from playwright.async_api import Page, ElementHandle, Error as PlaywrightError
except ImportError:
    try:
        from patchright.async_api import Page, ElementHandle, Error as PlaywrightError
    except ImportError:
        from rebrowser_playwright.async_api import Page, ElementHandle, Error as PlaywrightError


# ==============================================================================
# TYPES AND ENUMS
# ==============================================================================

class ActionType(Enum):
    """Supported action types."""
    CLICK = "click"
    TYPE = "type"
    SELECT = "select"
    HOVER = "hover"
    SCROLL = "scroll"
    NAVIGATE = "navigate"
    SUBMIT = "submit"
    CHECK = "check"
    UNCHECK = "uncheck"


class ExpectedOutcome(Enum):
    """Expected outcomes after action."""
    ANY = "any"
    NAVIGATION = "navigation"
    MODAL = "modal"
    STATE_CHANGE = "state_change"
    DOM_UPDATE = "dom_update"
    NETWORK_REQUEST = "network_request"
    NO_CHANGE = "no_change"


class ValidationIssue(Enum):
    """Common validation issues."""
    ELEMENT_NOT_FOUND = "element_not_found"
    NOT_VISIBLE = "not_visible"
    NOT_INTERACTABLE = "not_interactable"
    OBSTRUCTED = "obstructed"
    WRONG_TYPE = "wrong_type"
    DISABLED = "disabled"
    READONLY = "readonly"
    OUT_OF_VIEWPORT = "out_of_viewport"
    DETACHED = "detached"
    NO_EFFECT = "no_effect"
    ERROR_DETECTED = "error_detected"


# ==============================================================================
# DATA CLASSES
# ==============================================================================

@dataclass
class ElementState:
    """State of an element at a point in time."""
    exists: bool = False
    visible: bool = False
    enabled: bool = False
    interactable: bool = False
    in_viewport: bool = False
    tag_name: Optional[str] = None
    attributes: Dict[str, str] = field(default_factory=dict)
    rect: Optional[Dict[str, float]] = None
    computed_style: Dict[str, str] = field(default_factory=dict)
    text_content: Optional[str] = None
    value: Optional[str] = None
    obstructed_by: Optional[str] = None


@dataclass
class PreActionValidation:
    """Result of pre-action validation."""
    valid: bool
    issues: List[ValidationIssue]
    fixes_applied: List[str]
    element_state: ElementState
    warnings: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    def __bool__(self):
        return self.valid


@dataclass
class PostActionValidation:
    """Result of post-action validation."""
    success: bool
    expected_change_detected: bool
    actual_changes: List[str]
    errors_detected: List[str]
    element_state_after: Optional[ElementState] = None
    navigation_occurred: bool = False
    network_activity: bool = False
    timestamp: datetime = field(default_factory=datetime.now)

    def __bool__(self):
        return self.success


@dataclass
class ActionResult:
    """Overall result of a validated action."""
    success: bool
    action_type: ActionType
    selector: str
    pre_validation: Optional[PreActionValidation] = None
    post_validation: Optional[PostActionValidation] = None
    retries: int = 0
    total_duration_ms: float = 0
    error: Optional[str] = None
    changes_detected: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


# ==============================================================================
# ELEMENT STATE INSPECTION
# ==============================================================================

class ElementInspector:
    """Inspects element state for validation."""

    @staticmethod
    async def get_element_state(page: Page, selector: str) -> ElementState:
        """Get comprehensive state of an element."""
        state = ElementState()

        try:
            element = await page.query_selector(selector)
            if not element:
                return state

            state.exists = True

            # Basic properties
            state.tag_name = await element.evaluate("el => el.tagName.toLowerCase()")
            state.text_content = await element.text_content()

            # Visibility
            state.visible = await element.is_visible()
            state.enabled = await element.is_enabled()

            # Viewport check
            state.in_viewport = await ElementInspector._is_in_viewport(page, selector)

            # Bounding box
            box = await element.bounding_box()
            if box:
                state.rect = box

            # Attributes
            state.attributes = await element.evaluate("""
                el => {
                    const attrs = {};
                    for (const attr of el.attributes) {
                        attrs[attr.name] = attr.value;
                    }
                    return attrs;
                }
            """)

            # Value for inputs
            if state.tag_name in ['input', 'textarea', 'select']:
                state.value = await element.evaluate("el => el.value")

            # Computed style (key properties)
            state.computed_style = await element.evaluate("""
                el => {
                    const style = window.getComputedStyle(el);
                    return {
                        display: style.display,
                        visibility: style.visibility,
                        opacity: style.opacity,
                        pointerEvents: style.pointerEvents,
                        zIndex: style.zIndex
                    };
                }
            """)

            # Check if obstructed
            state.obstructed_by = await ElementInspector._check_obstruction(page, selector)

            # Interactability (Playwright's check)
            try:
                await element.click(timeout=100, trial=True)
                state.interactable = True
            except Exception:
                state.interactable = False

        except Exception as e:
            logger.debug(f"Error getting element state: {e}")

        return state

    @staticmethod
    async def _is_in_viewport(page: Page, selector: str) -> bool:
        """Check if element is in viewport."""
        try:
            return await page.evaluate(f"""
                () => {{
                    const el = document.querySelector('{selector}');
                    if (!el) return false;
                    const rect = el.getBoundingClientRect();
                    return (
                        rect.top >= 0 &&
                        rect.left >= 0 &&
                        rect.bottom <= window.innerHeight &&
                        rect.right <= window.innerWidth
                    );
                }}
            """)
        except Exception:
            return False

    @staticmethod
    async def _check_obstruction(page: Page, selector: str) -> Optional[str]:
        """Check if element is obstructed by another element."""
        try:
            obstructor = await page.evaluate(f"""
                () => {{
                    const el = document.querySelector('{selector}');
                    if (!el) return null;
                    const rect = el.getBoundingClientRect();
                    const centerX = rect.left + rect.width / 2;
                    const centerY = rect.top + rect.height / 2;
                    const topEl = document.elementFromPoint(centerX, centerY);
                    if (topEl && topEl !== el && !el.contains(topEl)) {{
                        return topEl.tagName + (topEl.id ? '#' + topEl.id : '') +
                               (topEl.className ? '.' + topEl.className.split(' ').join('.') : '');
                    }}
                    return null;
                }}
            """)
            return obstructor
        except Exception:
            return None


# ==============================================================================
# PRE-ACTION VALIDATORS
# ==============================================================================

class PreActionValidator:
    """Validates conditions before executing actions."""

    def __init__(self, auto_fix: bool = True):
        self.auto_fix = auto_fix
        self.inspector = ElementInspector()

    async def validate_before_click(
        self,
        page: Page,
        selector: str
    ) -> PreActionValidation:
        """Validate element before click action."""
        issues: List[ValidationIssue] = []
        fixes: List[str] = []
        warnings: List[str] = []

        # Get element state
        state = await self.inspector.get_element_state(page, selector)

        # 1. Element exists
        if not state.exists:
            issues.append(ValidationIssue.ELEMENT_NOT_FOUND)
            return PreActionValidation(
                valid=False,
                issues=issues,
                fixes_applied=fixes,
                element_state=state,
                warnings=warnings
            )

        # 2. Element visible
        if not state.visible:
            issues.append(ValidationIssue.NOT_VISIBLE)
            if self.auto_fix:
                try:
                    await self._scroll_into_view(page, selector)
                    fixes.append("Scrolled into view")
                    # Re-check visibility
                    state = await self.inspector.get_element_state(page, selector)
                    if state.visible:
                        issues.remove(ValidationIssue.NOT_VISIBLE)
                except Exception as e:
                    warnings.append(f"Failed to scroll into view: {e}")

        # 3. Element in viewport
        if not state.in_viewport:
            issues.append(ValidationIssue.OUT_OF_VIEWPORT)
            if self.auto_fix and ValidationIssue.NOT_VISIBLE not in issues:
                try:
                    await self._scroll_into_view(page, selector)
                    fixes.append("Scrolled into viewport")
                    state = await self.inspector.get_element_state(page, selector)
                    if state.in_viewport:
                        issues.remove(ValidationIssue.OUT_OF_VIEWPORT)
                except Exception as e:
                    warnings.append(f"Failed to scroll into viewport: {e}")

        # 4. Not obstructed
        if state.obstructed_by:
            issues.append(ValidationIssue.OBSTRUCTED)
            if self.auto_fix:
                dismissed = await self._dismiss_obstructions(page, state.obstructed_by)
                if dismissed:
                    fixes.append(f"Dismissed obstruction: {state.obstructed_by}")
                    # Re-check obstruction
                    state = await self.inspector.get_element_state(page, selector)
                    if not state.obstructed_by:
                        issues.remove(ValidationIssue.OBSTRUCTED)

        # 5. Interactable (enabled, not disabled)
        if not state.enabled:
            issues.append(ValidationIssue.DISABLED)
            warnings.append("Element is disabled - cannot click")

        if not state.interactable:
            issues.append(ValidationIssue.NOT_INTERACTABLE)
            if ValidationIssue.DISABLED not in issues:
                warnings.append("Element not interactable (may be covered or invisible)")

        # Valid if no blocking issues remain
        blocking_issues = {
            ValidationIssue.ELEMENT_NOT_FOUND,
            ValidationIssue.DISABLED,
            ValidationIssue.NOT_INTERACTABLE
        }
        valid = not any(issue in blocking_issues for issue in issues)

        return PreActionValidation(
            valid=valid,
            issues=issues,
            fixes_applied=fixes,
            element_state=state,
            warnings=warnings
        )

    async def validate_before_type(
        self,
        page: Page,
        selector: str,
        text: str
    ) -> PreActionValidation:
        """Validate before typing into element."""
        issues: List[ValidationIssue] = []
        fixes: List[str] = []
        warnings: List[str] = []

        state = await self.inspector.get_element_state(page, selector)

        if not state.exists:
            issues.append(ValidationIssue.ELEMENT_NOT_FOUND)
            return PreActionValidation(
                valid=False,
                issues=issues,
                fixes_applied=fixes,
                element_state=state,
                warnings=warnings
            )

        # Check it's an input/textarea
        if state.tag_name not in ['input', 'textarea']:
            issues.append(ValidationIssue.WRONG_TYPE)
            warnings.append(f"Expected input/textarea, got {state.tag_name}")

        # Check not readonly
        if state.attributes.get('readonly'):
            issues.append(ValidationIssue.READONLY)
            warnings.append("Element is readonly - cannot type")

        # Check not disabled
        if not state.enabled:
            issues.append(ValidationIssue.DISABLED)
            warnings.append("Element is disabled - cannot type")

        # Check maxlength if applicable
        if state.tag_name == 'input':
            maxlength = state.attributes.get('maxlength')
            if maxlength and len(text) > int(maxlength):
                warnings.append(f"Text exceeds maxlength ({maxlength})")

        # Ensure visible (same as click)
        if not state.visible:
            issues.append(ValidationIssue.NOT_VISIBLE)
            if self.auto_fix:
                try:
                    await self._scroll_into_view(page, selector)
                    fixes.append("Scrolled into view")
                    state = await self.inspector.get_element_state(page, selector)
                    if state.visible:
                        issues.remove(ValidationIssue.NOT_VISIBLE)
                except Exception as e:
                    warnings.append(f"Failed to scroll into view: {e}")

        blocking_issues = {
            ValidationIssue.ELEMENT_NOT_FOUND,
            ValidationIssue.WRONG_TYPE,
            ValidationIssue.READONLY,
            ValidationIssue.DISABLED
        }
        valid = not any(issue in blocking_issues for issue in issues)

        return PreActionValidation(
            valid=valid,
            issues=issues,
            fixes_applied=fixes,
            element_state=state,
            warnings=warnings
        )

    async def validate_before_select(
        self,
        page: Page,
        selector: str,
        value: str
    ) -> PreActionValidation:
        """Validate before selecting option."""
        issues: List[ValidationIssue] = []
        fixes: List[str] = []
        warnings: List[str] = []

        state = await self.inspector.get_element_state(page, selector)

        if not state.exists:
            issues.append(ValidationIssue.ELEMENT_NOT_FOUND)
            return PreActionValidation(
                valid=False,
                issues=issues,
                fixes_applied=fixes,
                element_state=state,
                warnings=warnings
            )

        # Must be a select element
        if state.tag_name != 'select':
            issues.append(ValidationIssue.WRONG_TYPE)
            warnings.append(f"Expected select, got {state.tag_name}")

        # Check option exists
        try:
            option_exists = await page.evaluate(f"""
                () => {{
                    const select = document.querySelector('{selector}');
                    if (!select) return false;
                    const options = Array.from(select.options);
                    return options.some(opt => opt.value === '{value}' || opt.text === '{value}');
                }}
            """)
            if not option_exists:
                warnings.append(f"Option '{value}' not found in select")
        except Exception as e:
            warnings.append(f"Could not verify option: {e}")

        # Check not disabled
        if not state.enabled:
            issues.append(ValidationIssue.DISABLED)

        blocking_issues = {
            ValidationIssue.ELEMENT_NOT_FOUND,
            ValidationIssue.WRONG_TYPE,
            ValidationIssue.DISABLED
        }
        valid = not any(issue in blocking_issues for issue in issues)

        return PreActionValidation(
            valid=valid,
            issues=issues,
            fixes_applied=fixes,
            element_state=state,
            warnings=warnings
        )

    # Helper methods

    async def _scroll_into_view(self, page: Page, selector: str):
        """Scroll element into view."""
        await page.evaluate(f"""
            () => {{
                const el = document.querySelector('{selector}');
                if (el) {{
                    el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                }}
            }}
        """)
        # Wait for scroll to complete
        await asyncio.sleep(0.3)

    async def _dismiss_obstructions(self, page: Page, obstructor: str) -> bool:
        """Try to dismiss common obstructions (modals, popups, etc)."""
        try:
            # Common dismissal patterns
            dismiss_selectors = [
                '.modal .close', '.modal-close', '[data-dismiss="modal"]',
                '.popup .close', '.overlay .close', '.cookie-banner .close',
                'button[aria-label*="close"]', 'button[aria-label*="dismiss"]'
            ]

            for sel in dismiss_selectors:
                try:
                    element = await page.query_selector(sel)
                    if element and await element.is_visible():
                        await element.click(timeout=1000)
                        await asyncio.sleep(0.2)
                        return True
                except Exception:
                    continue

            # Try pressing Escape
            await page.keyboard.press('Escape')
            await asyncio.sleep(0.2)
            return True

        except Exception as e:
            logger.debug(f"Failed to dismiss obstruction: {e}")
            return False


# ==============================================================================
# POST-ACTION VALIDATORS
# ==============================================================================

class PostActionValidator:
    """Validates results after executing actions."""

    def __init__(self):
        self.inspector = ElementInspector()

    async def validate_after_click(
        self,
        page: Page,
        selector: str,
        expected_outcome: ExpectedOutcome = ExpectedOutcome.ANY
    ) -> PostActionValidation:
        """Validate that click had expected effect."""
        changes: List[str] = []
        errors: List[str] = []

        # Wait a bit for effects to manifest
        await asyncio.sleep(0.5)

        # Check for navigation
        try:
            if await self._page_navigated(page):
                changes.append("navigation")
        except Exception as e:
            logger.debug(f"Navigation check failed: {e}")

        # Check for modal/popup
        if await self._modal_appeared(page):
            changes.append("modal")

        # Check for element state change
        if await self._element_state_changed(page, selector):
            changes.append("state_change")

        # Check for DOM updates
        if await self._dom_updated(page):
            changes.append("dom_update")

        # Check for errors
        errors = await self._detect_page_errors(page)

        # Determine success
        if expected_outcome == ExpectedOutcome.ANY:
            success = len(changes) > 0 and len(errors) == 0
            expected_detected = True
        elif expected_outcome == ExpectedOutcome.NO_CHANGE:
            success = len(changes) == 0 and len(errors) == 0
            expected_detected = len(changes) == 0
        else:
            expected_detected = expected_outcome.value in changes
            success = expected_detected and len(errors) == 0

        # Get element state after action
        element_state_after = await self.inspector.get_element_state(page, selector)

        return PostActionValidation(
            success=success,
            expected_change_detected=expected_detected,
            actual_changes=changes,
            errors_detected=errors,
            element_state_after=element_state_after,
            navigation_occurred="navigation" in changes,
            network_activity="dom_update" in changes
        )

    async def validate_after_type(
        self,
        page: Page,
        selector: str,
        expected_text: str
    ) -> PostActionValidation:
        """Validate text was entered correctly."""
        changes: List[str] = []
        errors: List[str] = []

        try:
            actual_value = await page.evaluate(f"""
                () => {{
                    const el = document.querySelector('{selector}');
                    return el ? el.value : null;
                }}
            """)

            if actual_value == expected_text:
                changes.append("text_entered")
                success = True
            else:
                errors.append(f"Expected '{expected_text}', got '{actual_value}'")
                success = False

        except Exception as e:
            errors.append(f"Could not verify typed text: {e}")
            success = False

        element_state_after = await self.inspector.get_element_state(page, selector)

        return PostActionValidation(
            success=success,
            expected_change_detected=success,
            actual_changes=changes,
            errors_detected=errors,
            element_state_after=element_state_after
        )

    async def validate_after_select(
        self,
        page: Page,
        selector: str,
        expected_value: str
    ) -> PostActionValidation:
        """Validate option was selected correctly."""
        changes: List[str] = []
        errors: List[str] = []

        try:
            actual_value = await page.evaluate(f"""
                () => {{
                    const el = document.querySelector('{selector}');
                    return el ? el.value : null;
                }}
            """)

            if actual_value == expected_value:
                changes.append("option_selected")
                success = True
            else:
                errors.append(f"Expected '{expected_value}', got '{actual_value}'")
                success = False

        except Exception as e:
            errors.append(f"Could not verify selection: {e}")
            success = False

        element_state_after = await self.inspector.get_element_state(page, selector)

        return PostActionValidation(
            success=success,
            expected_change_detected=success,
            actual_changes=changes,
            errors_detected=errors,
            element_state_after=element_state_after
        )

    async def validate_form_submission(
        self,
        page: Page,
        form_selector: str
    ) -> PostActionValidation:
        """Validate form was submitted successfully."""
        changes: List[str] = []
        errors: List[str] = []

        await asyncio.sleep(1)  # Wait for submission

        # Check for success indicators
        success_patterns = [
            '.success', '.alert-success', '[role="alert"][class*="success"]',
            'text=success', 'text=submitted', 'text=thank you'
        ]

        for pattern in success_patterns:
            try:
                element = await page.query_selector(pattern)
                if element and await element.is_visible():
                    changes.append("success_message")
                    break
            except Exception:
                continue

        # Check for error messages
        error_patterns = [
            '.error', '.alert-error', '.alert-danger',
            '[role="alert"][class*="error"]', '[role="alert"][class*="danger"]'
        ]

        for pattern in error_patterns:
            try:
                element = await page.query_selector(pattern)
                if element and await element.is_visible():
                    error_text = await element.text_content()
                    errors.append(f"Form error: {error_text}")
            except Exception:
                continue

        # Check for navigation (common after form submit)
        if await self._page_navigated(page):
            changes.append("navigation")

        success = len(changes) > 0 and len(errors) == 0

        return PostActionValidation(
            success=success,
            expected_change_detected="success_message" in changes or "navigation" in changes,
            actual_changes=changes,
            errors_detected=errors,
            navigation_occurred="navigation" in changes
        )

    # Helper methods

    async def _page_navigated(self, page: Page) -> bool:
        """Check if page navigated (URL changed)."""
        # This is called AFTER action, so we can't compare to previous URL
        # Instead, check for loading indicators
        try:
            # Check if page is loading
            loading = await page.evaluate("""
                () => document.readyState === 'loading'
            """)
            return loading
        except Exception:
            return False

    async def _modal_appeared(self, page: Page) -> bool:
        """Check if modal/popup appeared."""
        modal_selectors = [
            '.modal.show', '.modal[style*="display: block"]',
            '[role="dialog"][aria-hidden="false"]',
            '.popup.active', '.overlay.active'
        ]

        for sel in modal_selectors:
            try:
                element = await page.query_selector(sel)
                if element and await element.is_visible():
                    return True
            except Exception:
                continue

        return False

    async def _element_state_changed(self, page: Page, selector: str) -> bool:
        """Check if element state changed (class, style, etc)."""
        try:
            # Check for common state changes
            changed = await page.evaluate(f"""
                () => {{
                    const el = document.querySelector('{selector}');
                    if (!el) return false;
                    // Check for active/selected/checked state changes
                    return el.classList.contains('active') ||
                           el.classList.contains('selected') ||
                           el.checked ||
                           el.getAttribute('aria-selected') === 'true' ||
                           el.getAttribute('aria-pressed') === 'true';
                }}
            """)
            return changed
        except Exception:
            return False

    async def _dom_updated(self, page: Page) -> bool:
        """Check if DOM was updated (new elements, content changes)."""
        try:
            # Check for loading indicators or new content
            indicators = await page.evaluate("""
                () => {
                    const loading = document.querySelector('[class*="loading"], [class*="spinner"]');
                    return loading !== null;
                }
            """)
            return indicators
        except Exception:
            return False

    async def _detect_page_errors(self, page: Page) -> List[str]:
        """Detect common error patterns on page."""
        errors: List[str] = []

        # Check for error messages in DOM
        error_selectors = [
            '.error:visible', '.alert-error:visible', '.alert-danger:visible',
            '[role="alert"][class*="error"]:visible',
            '[role="alert"][class*="danger"]:visible'
        ]

        for sel in error_selectors:
            # Remove :visible pseudo-selector for Playwright
            sel_clean = sel.replace(':visible', '')
            try:
                elements = await page.query_selector_all(sel_clean)
                for el in elements:
                    if await el.is_visible():
                        text = await el.text_content()
                        if text:
                            errors.append(text.strip())
            except Exception:
                continue

        # Check console errors (if available)
        # Note: Would need to set up console listener during page creation

        return errors


# ==============================================================================
# MAIN VALIDATOR - ORCHESTRATES PRE + POST VALIDATION
# ==============================================================================

class InteractionValidator:
    """
    Main validator that orchestrates pre/post validation with auto-retry.

    Usage:
        validator = InteractionValidator(auto_fix=True, max_retries=3)
        result = await validator.validated_click(page, ".submit-btn")
        if result.success:
            print(f"Clicked successfully with {result.retries} retries")
    """

    def __init__(self, auto_fix: bool = True, max_retries: int = 3):
        self.auto_fix = auto_fix
        self.max_retries = max_retries
        self.pre_validator = PreActionValidator(auto_fix=auto_fix)
        self.post_validator = PostActionValidator()

    async def validated_click(
        self,
        page: Page,
        selector: str,
        expected_outcome: ExpectedOutcome = ExpectedOutcome.ANY,
        timeout: int = 30000
    ) -> ActionResult:
        """Execute click with full validation and retry."""
        return await self._validated_action(
            page=page,
            action_type=ActionType.CLICK,
            selector=selector,
            expected_outcome=expected_outcome,
            timeout=timeout
        )

    async def validated_type(
        self,
        page: Page,
        selector: str,
        text: str,
        timeout: int = 30000
    ) -> ActionResult:
        """Execute type with full validation and retry."""
        return await self._validated_action(
            page=page,
            action_type=ActionType.TYPE,
            selector=selector,
            value=text,
            timeout=timeout
        )

    async def validated_select(
        self,
        page: Page,
        selector: str,
        value: str,
        timeout: int = 30000
    ) -> ActionResult:
        """Execute select with full validation and retry."""
        return await self._validated_action(
            page=page,
            action_type=ActionType.SELECT,
            selector=selector,
            value=value,
            timeout=timeout
        )

    async def validated_submit(
        self,
        page: Page,
        form_selector: str,
        timeout: int = 30000
    ) -> ActionResult:
        """Execute form submit with full validation."""
        return await self._validated_action(
            page=page,
            action_type=ActionType.SUBMIT,
            selector=form_selector,
            expected_outcome=ExpectedOutcome.NAVIGATION,
            timeout=timeout
        )

    async def _validated_action(
        self,
        page: Page,
        action_type: ActionType,
        selector: str,
        value: Any = None,
        expected_outcome: ExpectedOutcome = ExpectedOutcome.ANY,
        timeout: int = 30000
    ) -> ActionResult:
        """
        Execute action with pre/post validation and auto-retry.

        Flow:
        1. Pre-validation (with auto-fix if enabled)
        2. Execute action
        3. Post-validation
        4. Retry with different strategy if failed
        """
        start_time = datetime.now()
        pre_validation: Optional[PreActionValidation] = None
        post_validation: Optional[PostActionValidation] = None
        last_error: Optional[str] = None

        for attempt in range(self.max_retries):
            try:
                # PRE-VALIDATION
                if action_type == ActionType.CLICK:
                    pre_validation = await self.pre_validator.validate_before_click(page, selector)
                elif action_type == ActionType.TYPE:
                    pre_validation = await self.pre_validator.validate_before_type(page, selector, value)
                elif action_type == ActionType.SELECT:
                    pre_validation = await self.pre_validator.validate_before_select(page, selector, value)
                elif action_type == ActionType.SUBMIT:
                    # For submit, validate the form exists
                    pre_validation = await self.pre_validator.validate_before_click(page, selector)
                else:
                    # Generic validation for other types
                    pre_validation = await self.pre_validator.validate_before_click(page, selector)

                if not pre_validation.valid:
                    logger.warning(f"Pre-validation failed (attempt {attempt + 1}): {pre_validation.issues}")
                    last_error = f"Pre-validation failed: {', '.join(str(i.value) for i in pre_validation.issues)}"
                    await self._apply_retry_strategy(page, attempt)
                    continue

                # EXECUTE ACTION
                try:
                    if action_type == ActionType.CLICK:
                        await page.click(selector, timeout=timeout)
                    elif action_type == ActionType.TYPE:
                        await page.fill(selector, value, timeout=timeout)
                    elif action_type == ActionType.SELECT:
                        await page.select_option(selector, value, timeout=timeout)
                    elif action_type == ActionType.SUBMIT:
                        await page.click(selector, timeout=timeout)  # Click submit button
                    else:
                        raise ValueError(f"Unsupported action type: {action_type}")

                except PlaywrightError as e:
                    logger.warning(f"Action execution failed (attempt {attempt + 1}): {e}")
                    last_error = str(e)
                    await self._apply_retry_strategy(page, attempt)
                    continue

                # POST-VALIDATION
                if action_type == ActionType.CLICK:
                    post_validation = await self.post_validator.validate_after_click(
                        page, selector, expected_outcome
                    )
                elif action_type == ActionType.TYPE:
                    post_validation = await self.post_validator.validate_after_type(
                        page, selector, value
                    )
                elif action_type == ActionType.SELECT:
                    post_validation = await self.post_validator.validate_after_select(
                        page, selector, value
                    )
                elif action_type == ActionType.SUBMIT:
                    post_validation = await self.post_validator.validate_form_submission(
                        page, selector
                    )

                if not post_validation.success:
                    logger.warning(f"Post-validation failed (attempt {attempt + 1}): {post_validation.errors_detected}")
                    last_error = f"Post-validation failed: {', '.join(post_validation.errors_detected)}"
                    await self._apply_retry_strategy(page, attempt)
                    continue

                # SUCCESS!
                duration = (datetime.now() - start_time).total_seconds() * 1000
                return ActionResult(
                    success=True,
                    action_type=action_type,
                    selector=selector,
                    pre_validation=pre_validation,
                    post_validation=post_validation,
                    retries=attempt,
                    total_duration_ms=duration,
                    changes_detected=post_validation.actual_changes
                )

            except Exception as e:
                logger.error(f"Unexpected error during validated action (attempt {attempt + 1}): {e}")
                last_error = str(e)
                await self._apply_retry_strategy(page, attempt)

        # MAX RETRIES EXCEEDED
        duration = (datetime.now() - start_time).total_seconds() * 1000
        return ActionResult(
            success=False,
            action_type=action_type,
            selector=selector,
            pre_validation=pre_validation,
            post_validation=post_validation,
            retries=self.max_retries,
            total_duration_ms=duration,
            error=f"Max retries ({self.max_retries}) exceeded. Last error: {last_error}"
        )

    async def _apply_retry_strategy(self, page: Page, attempt: int):
        """Apply different retry strategies based on attempt number."""
        if attempt == 0:
            # First retry: just wait a bit
            await asyncio.sleep(0.5)
        elif attempt == 1:
            # Second retry: try reloading page state
            await page.evaluate("() => {}")  # Force page evaluation
            await asyncio.sleep(1)
        else:
            # Later retries: longer wait
            await asyncio.sleep(2)


# ==============================================================================
# CONVENIENCE FUNCTIONS
# ==============================================================================

async def quick_validated_click(
    page: Page,
    selector: str,
    auto_fix: bool = True,
    max_retries: int = 3
) -> bool:
    """Quick validated click with default settings."""
    validator = InteractionValidator(auto_fix=auto_fix, max_retries=max_retries)
    result = await validator.validated_click(page, selector)
    return result.success


async def quick_validated_type(
    page: Page,
    selector: str,
    text: str,
    auto_fix: bool = True,
    max_retries: int = 3
) -> bool:
    """Quick validated type with default settings."""
    validator = InteractionValidator(auto_fix=auto_fix, max_retries=max_retries)
    result = await validator.validated_type(page, selector, text)
    return result.success


async def quick_validated_select(
    page: Page,
    selector: str,
    value: str,
    auto_fix: bool = True,
    max_retries: int = 3
) -> bool:
    """Quick validated select with default settings."""
    validator = InteractionValidator(auto_fix=auto_fix, max_retries=max_retries)
    result = await validator.validated_select(page, selector, value)
    return result.success
