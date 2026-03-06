"""
Complex Form Handler - Specialized module for handling complex web forms

Handles advanced form patterns that standard Playwright actions struggle with:
- Multi-step forms (wizards)
- Forms with conditional fields
- Autocomplete/typeahead inputs (Google Places, location search)
- Dropdown menus (native select and custom)
- Radio button groups
- Checkbox groups
- File uploads
- Slider inputs
- Dynamic form fields

Site-specific handlers:
- indeed.com: Job search with location autocomplete
- yelp.com: Business search with location
- zillow.com: Property search filters
- target.com: Store selector
- linkedin.com: Job search filters
- airbnb.com: Date pickers and location search

Dependencies:
- Playwright for browser automation
- Humanization module for realistic interactions (bezier cursor, human typing)
- Self-healing selectors for robustness
"""

import asyncio
import os
import re
from typing import Any, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum
from loguru import logger


# Import humanization for realistic interactions
HUMANIZATION_AVAILABLE = False
try:
    from .humanization import BezierCursor, HumanTyper, get_cursor, get_typer
    HUMANIZATION_AVAILABLE = True
except ImportError:
    logger.warning("Humanization module not available, using basic interactions")


class FormType(Enum):
    """Form complexity classification"""
    SIMPLE = "simple"  # Basic input fields, no dynamic behavior
    AUTOCOMPLETE = "autocomplete"  # Has typeahead/autocomplete inputs
    CONDITIONAL = "conditional"  # Fields appear/disappear based on selections
    MULTI_STEP = "multi_step"  # Wizard-style with next/previous
    DYNAMIC = "dynamic"  # AJAX-loaded fields
    COMPLEX = "complex"  # Combination of above


class InputType(Enum):
    """Form input types"""
    TEXT = "text"
    EMAIL = "email"
    PASSWORD = "password"
    NUMBER = "number"
    AUTOCOMPLETE = "autocomplete"
    SELECT_NATIVE = "select_native"
    SELECT_CUSTOM = "select_custom"
    RADIO = "radio"
    CHECKBOX = "checkbox"
    FILE = "file"
    SLIDER = "slider"
    DATE_PICKER = "date_picker"
    LOCATION = "location"


@dataclass
class FormField:
    """Represents a form field to fill"""
    selector: str
    value: Any
    input_type: InputType = InputType.TEXT
    wait_for_selector: Optional[str] = None  # Conditional field prerequisite
    validate_selector: Optional[str] = None  # Validation check
    retry_count: int = 3


@dataclass
class FormStep:
    """Represents a step in a multi-step form"""
    step_number: int
    fields: List[FormField]
    next_button_selector: Optional[str] = None
    validation_selector: Optional[str] = None  # Element that appears when step valid


class ComplexFormHandler:
    """
    Handles complex form interactions with human-like behavior.

    Example:
        handler = ComplexFormHandler(page)

        # Simple autocomplete
        await handler.fill_autocomplete(
            selector="input[name='location']",
            value="San Francisco, CA"
        )

        # Multi-step form
        await handler.fill_multi_step_form({
            'step1': [
                FormField('input[name="email"]', 'test@example.com'),
                FormField('input[name="password"]', 'SecurePass123', InputType.PASSWORD)
            ],
            'step2': [
                FormField('select[name="country"]', 'United States', InputType.SELECT_NATIVE)
            ]
        })
    """

    # Timeouts
    DEFAULT_TIMEOUT = 10000  # 10 seconds
    AUTOCOMPLETE_SUGGESTION_TIMEOUT = 5000  # 5 seconds for suggestions to appear
    AJAX_LOAD_TIMEOUT = 3000  # 3 seconds for AJAX content

    # Delays (human-like timing)
    TYPING_DELAY_MS = (50, 150)  # Random delay between keystrokes
    CLICK_DELAY_MS = (100, 300)  # Delay after click
    FORM_FIELD_DELAY_MS = (200, 500)  # Delay between form fields
    STEP_TRANSITION_DELAY_MS = (500, 1000)  # Delay between wizard steps

    def __init__(self, page, use_humanization: bool = True):
        """
        Initialize the form handler.

        Args:
            page: Playwright page object
            use_humanization: Use human-like interactions (cursor, typing)
        """
        self.page = page
        self.use_humanization = use_humanization and HUMANIZATION_AVAILABLE

        # Initialize humanization if available
        if self.use_humanization:
            self.cursor = get_cursor()
            self.typer = get_typer()
        else:
            self.cursor = None
            self.typer = None

        # Track form state
        self.current_step = 0
        self.filled_fields = []

    async def _human_delay(self, delay_range: Tuple[int, int]):
        """Add human-like delay"""
        import random
        delay = random.randint(*delay_range) / 1000.0
        await asyncio.sleep(delay)

    async def _wait_for_stable(self, timeout: int = 2000):
        """Wait for page to stabilize (no network activity)"""
        try:
            await self.page.wait_for_load_state('networkidle', timeout=timeout)
        except Exception as e:
            logger.debug(f"Network not idle, continuing anyway: {e}")

    async def detect_form_type(self) -> FormType:
        """
        Analyze page and detect form complexity.

        Returns:
            FormType enum indicating complexity
        """
        try:
            # Check for multi-step indicators
            multi_step_indicators = [
                'button:has-text("Next")',
                'button:has-text("Continue")',
                'button:has-text("Previous")',
                '.wizard-step',
                '.step-indicator',
                '[role="progressbar"]'
            ]

            for selector in multi_step_indicators:
                if await self.page.locator(selector).count() > 0:
                    logger.info("Detected multi-step form")
                    return FormType.MULTI_STEP

            # Check for autocomplete inputs
            autocomplete_selectors = [
                'input[role="combobox"]',
                'input[autocomplete="off"][type="text"]',
                '.autocomplete',
                'input[aria-autocomplete="list"]'
            ]

            has_autocomplete = False
            for selector in autocomplete_selectors:
                if await self.page.locator(selector).count() > 0:
                    has_autocomplete = True
                    break

            # Check for custom dropdowns
            custom_dropdown_selectors = [
                '.dropdown',
                '[role="listbox"]',
                '.select2',
                '.chosen-container'
            ]

            has_custom_dropdown = False
            for selector in custom_dropdown_selectors:
                if await self.page.locator(selector).count() > 0:
                    has_custom_dropdown = True
                    break

            # Determine complexity
            if has_autocomplete or has_custom_dropdown:
                logger.info("Detected autocomplete/custom dropdown form")
                return FormType.AUTOCOMPLETE

            # Check for conditional fields (data-show-if, data-depends-on)
            conditional_indicators = await self.page.evaluate("""
                () => {
                    const elements = document.querySelectorAll('[data-show-if], [data-depends-on], [data-conditional]');
                    return elements.length > 0;
                }
            """)

            if conditional_indicators:
                logger.info("Detected conditional form")
                return FormType.CONDITIONAL

            logger.info("Detected simple form")
            return FormType.SIMPLE

        except Exception as e:
            logger.warning(f"Error detecting form type: {e}")
            return FormType.SIMPLE

    async def wait_for_form_ready(self, timeout: int = 10000) -> bool:
        """
        Wait for dynamic form elements to fully load.

        Returns:
            True if form is ready, False on timeout
        """
        try:
            # Wait for common form ready indicators
            await self.page.wait_for_selector(
                'form, input[type="text"], input[type="email"]',
                timeout=timeout,
                state='visible'
            )

            # Wait for network idle
            await self._wait_for_stable(timeout=2000)

            # Check if any loading spinners are gone
            loading_selectors = [
                '.loading',
                '.spinner',
                '[aria-busy="true"]',
                '.skeleton'
            ]

            for selector in loading_selectors:
                try:
                    await self.page.wait_for_selector(
                        selector,
                        state='hidden',
                        timeout=3000
                    )
                except Exception:
                    pass  # Selector might not exist

            logger.debug("Form is ready")
            return True

        except Exception as e:
            logger.error(f"Timeout waiting for form ready: {e}")
            return False

    async def fill_autocomplete(
        self,
        selector: str,
        value: str,
        suggestion_selector: Optional[str] = None,
        exact_match: bool = True,
        clear_first: bool = True
    ) -> bool:
        """
        Fill an autocomplete/typeahead input.

        Args:
            selector: Input field selector
            value: Value to type
            suggestion_selector: Optional selector for suggestion dropdown
            exact_match: Wait for exact text match in suggestions
            clear_first: Clear field before typing

        Returns:
            True if successful
        """
        try:
            logger.info(f"Filling autocomplete: {selector} = {value}")

            # Wait for input to be visible
            await self.page.wait_for_selector(selector, state='visible', timeout=self.DEFAULT_TIMEOUT)

            # Focus the input
            await self.page.focus(selector)
            await self._human_delay(self.CLICK_DELAY_MS)

            # Clear if needed
            if clear_first:
                await self.page.fill(selector, '')
                await self._human_delay((50, 100))

            # Type with human-like behavior
            if self.use_humanization and self.typer:
                await self.typer.type_text(self.page, value, selector=selector)
            else:
                # Fallback: type character by character with delays
                for char in value:
                    await self.page.type(selector, char)
                    await self._human_delay((50, 150))

            # Wait for suggestions to appear
            await self._human_delay((300, 600))

            # Auto-detect suggestion dropdown if not provided
            if not suggestion_selector:
                # Try common autocomplete dropdown selectors
                suggestion_selectors = [
                    '[role="listbox"]',
                    '.autocomplete-results',
                    '.suggestions',
                    '[class*="suggestion"]',
                    '[class*="dropdown"]',
                    'ul[role="listbox"]',
                    '.pac-container',  # Google Places
                    '[id*="listbox"]'
                ]

                for sel in suggestion_selectors:
                    try:
                        await self.page.wait_for_selector(sel, state='visible', timeout=2000)
                        suggestion_selector = sel
                        logger.debug(f"Found suggestion dropdown: {sel}")
                        break
                    except Exception:
                        continue

            if suggestion_selector:
                # Wait for suggestions to load
                await self.page.wait_for_selector(
                    suggestion_selector,
                    state='visible',
                    timeout=self.AUTOCOMPLETE_SUGGESTION_TIMEOUT
                )

                # Find and click the matching suggestion
                if exact_match:
                    # Click suggestion with exact text match
                    suggestion_item_selector = f'{suggestion_selector} >> text="{value}"'
                    try:
                        await self.page.click(suggestion_item_selector, timeout=3000)
                    except Exception:
                        # Try case-insensitive match
                        logger.debug(f"Exact match failed, trying first suggestion")
                        first_item = f'{suggestion_selector} >> nth=0'
                        await self.page.click(first_item, timeout=3000)
                else:
                    # Click first suggestion
                    first_item = f'{suggestion_selector} >> nth=0'
                    await self.page.click(first_item, timeout=3000)

                await self._human_delay(self.CLICK_DELAY_MS)
                logger.debug("Clicked autocomplete suggestion")
            else:
                # No dropdown appeared, press Enter
                logger.debug("No suggestions appeared, pressing Enter")
                await self.page.press(selector, 'Enter')
                await self._human_delay((200, 400))

            self.filled_fields.append(selector)
            return True

        except Exception as e:
            logger.error(f"Error filling autocomplete {selector}: {e}")
            return False

    async def fill_location_input(
        self,
        selector: str,
        location: str,
        wait_for_coordinates: bool = False
    ) -> bool:
        """
        Fill a location autocomplete input (Google Places style).

        Args:
            selector: Input field selector
            location: Location string (e.g., "San Francisco, CA")
            wait_for_coordinates: Wait for geocoding to complete

        Returns:
            True if successful
        """
        logger.info(f"Filling location input: {location}")

        # Google Places specific suggestion selector
        suggestion_selector = '.pac-container'

        success = await self.fill_autocomplete(
            selector=selector,
            value=location,
            suggestion_selector=suggestion_selector,
            exact_match=False  # Location names might have variations
        )

        if success and wait_for_coordinates:
            # Wait for geocoding to populate hidden fields
            await self._human_delay((500, 1000))

        return success

    async def select_dropdown(
        self,
        selector: str,
        value: str,
        is_native: bool = None
    ) -> bool:
        """
        Select an option from dropdown (handles both native and custom).

        Args:
            selector: Dropdown selector
            value: Value or text to select
            is_native: True for <select>, False for custom, None to auto-detect

        Returns:
            True if successful
        """
        try:
            logger.info(f"Selecting dropdown: {selector} = {value}")

            # Auto-detect if native or custom
            if is_native is None:
                tag_name = await self.page.evaluate(
                    f"document.querySelector('{selector}')?.tagName.toLowerCase()"
                )
                is_native = (tag_name == 'select')

            if is_native:
                # Native <select> element
                await self.page.select_option(selector, label=value)
                await self._human_delay(self.CLICK_DELAY_MS)
                logger.debug(f"Selected native option: {value}")
            else:
                # Custom dropdown - need to click to open
                await self.page.click(selector)
                await self._human_delay((200, 400))

                # Try various option selectors
                option_selectors = [
                    f'[role="option"]:has-text("{value}")',
                    f'li:has-text("{value}")',
                    f'[class*="option"]:has-text("{value}")',
                    f'div:has-text("{value}")'
                ]

                clicked = False
                for opt_sel in option_selectors:
                    try:
                        await self.page.click(opt_sel, timeout=2000)
                        clicked = True
                        logger.debug(f"Clicked custom option: {value}")
                        break
                    except Exception:
                        continue

                if not clicked:
                    logger.warning(f"Could not find option: {value}")
                    return False

                await self._human_delay(self.CLICK_DELAY_MS)

            self.filled_fields.append(selector)
            return True

        except Exception as e:
            logger.error(f"Error selecting dropdown {selector}: {e}")
            return False

    async def fill_radio_group(
        self,
        name: str,
        value: str
    ) -> bool:
        """
        Select a radio button by name and value.

        Args:
            name: Radio group name attribute
            value: Value to select

        Returns:
            True if successful
        """
        try:
            selector = f'input[type="radio"][name="{name}"][value="{value}"]'
            await self.page.check(selector)
            await self._human_delay(self.CLICK_DELAY_MS)

            logger.debug(f"Selected radio: {name} = {value}")
            self.filled_fields.append(selector)
            return True

        except Exception as e:
            logger.error(f"Error selecting radio {name}: {e}")
            return False

    async def fill_checkbox_group(
        self,
        selectors: List[str],
        check: bool = True
    ) -> bool:
        """
        Check/uncheck multiple checkboxes.

        Args:
            selectors: List of checkbox selectors
            check: True to check, False to uncheck

        Returns:
            True if all successful
        """
        try:
            for selector in selectors:
                if check:
                    await self.page.check(selector)
                else:
                    await self.page.uncheck(selector)

                await self._human_delay(self.CLICK_DELAY_MS)
                logger.debug(f"{'Checked' if check else 'Unchecked'}: {selector}")

            self.filled_fields.extend(selectors)
            return True

        except Exception as e:
            logger.error(f"Error with checkbox group: {e}")
            return False

    async def set_slider_value(
        self,
        selector: str,
        value: int,
        min_value: int = 0,
        max_value: int = 100
    ) -> bool:
        """
        Set a slider/range input to a specific value.

        Args:
            selector: Slider selector
            value: Target value
            min_value: Minimum slider value
            max_value: Maximum slider value

        Returns:
            True if successful
        """
        try:
            # Calculate percentage
            percentage = (value - min_value) / (max_value - min_value)

            # Get slider bounding box
            box = await self.page.locator(selector).bounding_box()
            if not box:
                raise Exception("Could not get slider bounding box")

            # Calculate target position
            target_x = box['x'] + (box['width'] * percentage)
            target_y = box['y'] + (box['height'] / 2)

            # Click at position to set value
            await self.page.mouse.click(target_x, target_y)
            await self._human_delay(self.CLICK_DELAY_MS)

            logger.debug(f"Set slider {selector} to {value}")
            self.filled_fields.append(selector)
            return True

        except Exception as e:
            logger.error(f"Error setting slider {selector}: {e}")
            return False

    async def upload_file(
        self,
        selector: str,
        file_path: str
    ) -> bool:
        """
        Upload a file to file input.

        Args:
            selector: File input selector
            file_path: Absolute path to file

        Returns:
            True if successful
        """
        try:
            await self.page.set_input_files(selector, file_path)
            await self._human_delay((500, 1000))

            logger.debug(f"Uploaded file: {file_path}")
            self.filled_fields.append(selector)
            return True

        except Exception as e:
            logger.error(f"Error uploading file {selector}: {e}")
            return False

    async def fill_field(self, field: FormField) -> bool:
        """
        Fill a single form field based on its type.

        Args:
            field: FormField object with selector, value, type

        Returns:
            True if successful
        """
        # Wait for conditional field prerequisite
        if field.wait_for_selector:
            try:
                await self.page.wait_for_selector(
                    field.wait_for_selector,
                    state='visible',
                    timeout=5000
                )
            except Exception as e:
                logger.warning(f"Prerequisite not met: {field.wait_for_selector}")
                return False

        # Retry logic
        for attempt in range(field.retry_count):
            try:
                success = False

                if field.input_type == InputType.TEXT:
                    await self.page.fill(field.selector, str(field.value))
                    success = True

                elif field.input_type == InputType.AUTOCOMPLETE:
                    success = await self.fill_autocomplete(field.selector, str(field.value))

                elif field.input_type == InputType.LOCATION:
                    success = await self.fill_location_input(field.selector, str(field.value))

                elif field.input_type == InputType.SELECT_NATIVE:
                    success = await self.select_dropdown(field.selector, str(field.value), is_native=True)

                elif field.input_type == InputType.SELECT_CUSTOM:
                    success = await self.select_dropdown(field.selector, str(field.value), is_native=False)

                elif field.input_type == InputType.RADIO:
                    # Extract name from selector
                    name_match = re.search(r'name=["\']([^"\']+)["\']', field.selector)
                    if name_match:
                        success = await self.fill_radio_group(name_match.group(1), str(field.value))

                elif field.input_type == InputType.CHECKBOX:
                    success = await self.fill_checkbox_group([field.selector], check=bool(field.value))

                elif field.input_type == InputType.FILE:
                    success = await self.upload_file(field.selector, str(field.value))

                elif field.input_type == InputType.SLIDER:
                    # Value should be tuple (value, min, max)
                    if isinstance(field.value, tuple):
                        success = await self.set_slider_value(field.selector, *field.value)

                if success:
                    await self._human_delay(self.FORM_FIELD_DELAY_MS)

                    # Validate if selector provided
                    if field.validate_selector:
                        try:
                            await self.page.wait_for_selector(
                                field.validate_selector,
                                state='visible',
                                timeout=2000
                            )
                            logger.debug(f"Field validation passed: {field.selector}")
                        except Exception:
                            logger.warning(f"Field validation failed: {field.selector}")
                            continue  # Retry

                    return True

            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed for {field.selector}: {e}")
                if attempt < field.retry_count - 1:
                    await self._human_delay((500, 1000))

        return False

    async def fill_multi_step_form(
        self,
        steps: List[FormStep],
        submit_button_selector: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Fill a multi-step wizard form.

        Args:
            steps: List of FormStep objects
            submit_button_selector: Final submit button selector

        Returns:
            Dict with success status and filled fields
        """
        logger.info(f"Filling multi-step form with {len(steps)} steps")

        result = {
            'success': False,
            'steps_completed': 0,
            'failed_fields': [],
            'filled_fields': []
        }

        try:
            for step in steps:
                logger.info(f"Processing step {step.step_number}")
                self.current_step = step.step_number

                # Wait for step to be visible
                await self._wait_for_stable()

                # Fill all fields in this step
                for field in step.fields:
                    success = await self.fill_field(field)

                    if success:
                        result['filled_fields'].append(field.selector)
                    else:
                        result['failed_fields'].append(field.selector)
                        logger.error(f"Failed to fill field: {field.selector}")

                # Validate step if selector provided
                if step.validation_selector:
                    try:
                        await self.page.wait_for_selector(
                            step.validation_selector,
                            state='visible',
                            timeout=3000
                        )
                        logger.debug(f"Step {step.step_number} validation passed")
                    except Exception as e:
                        logger.error(f"Step {step.step_number} validation failed: {e}")
                        return result

                # Click next button if not last step
                if step.next_button_selector:
                    await self.page.click(step.next_button_selector)
                    await self._human_delay(self.STEP_TRANSITION_DELAY_MS)
                    logger.debug(f"Clicked next button for step {step.step_number}")

                result['steps_completed'] += 1

            # Click final submit button if provided
            if submit_button_selector:
                await self.page.click(submit_button_selector)
                await self._human_delay((500, 1000))
                logger.info("Clicked final submit button")

            result['success'] = (len(result['failed_fields']) == 0)
            return result

        except Exception as e:
            logger.error(f"Error in multi-step form: {e}")
            result['error'] = str(e)
            return result


# Site-specific form handlers
class SiteSpecificHandlers:
    """Pre-configured handlers for popular websites"""

    @staticmethod
    async def indeed_job_search(page, job_title: str, location: str) -> bool:
        """
        Fill Indeed.com job search form.

        Args:
            page: Playwright page
            job_title: Job title to search
            location: Location string

        Returns:
            True if successful
        """
        handler = ComplexFormHandler(page)

        try:
            # Navigate if needed
            if 'indeed.com' not in page.url:
                await page.goto('https://www.indeed.com')

            await handler.wait_for_form_ready()

            # Fill job title (simple input)
            await page.fill('input[name="q"]', job_title)
            await handler._human_delay((200, 400))

            # Fill location (autocomplete)
            success = await handler.fill_location_input(
                selector='input[name="l"]',
                location=location
            )

            if success:
                # Click search button
                await page.click('button[type="submit"]')
                logger.info(f"Indeed search submitted: {job_title} in {location}")
                return True

            return False

        except Exception as e:
            logger.error(f"Indeed job search error: {e}")
            return False

    @staticmethod
    async def yelp_business_search(page, business: str, location: str) -> bool:
        """
        Fill Yelp.com business search form.

        Args:
            page: Playwright page
            business: Business type or name
            location: Location string

        Returns:
            True if successful
        """
        handler = ComplexFormHandler(page)

        try:
            if 'yelp.com' not in page.url:
                await page.goto('https://www.yelp.com')

            await handler.wait_for_form_ready()

            # Fill business/keyword
            await handler.fill_autocomplete(
                selector='input[id="search_description"]',
                value=business,
                exact_match=False
            )

            # Fill location
            await handler.fill_location_input(
                selector='input[id="search_location"]',
                location=location
            )

            # Submit
            await page.click('button[type="submit"]')
            logger.info(f"Yelp search submitted: {business} in {location}")
            return True

        except Exception as e:
            logger.error(f"Yelp search error: {e}")
            return False

    @staticmethod
    async def zillow_property_search(
        page,
        location: str,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        bedrooms: Optional[int] = None
    ) -> bool:
        """
        Fill Zillow.com property search form with filters.

        Args:
            page: Playwright page
            location: Location to search
            min_price: Minimum price
            max_price: Maximum price
            bedrooms: Number of bedrooms

        Returns:
            True if successful
        """
        handler = ComplexFormHandler(page)

        try:
            if 'zillow.com' not in page.url:
                await page.goto('https://www.zillow.com')

            await handler.wait_for_form_ready()

            # Fill location search
            await handler.fill_location_input(
                selector='input[id="search-box-input"]',
                location=location
            )

            await handler._human_delay((500, 1000))

            # Apply filters if provided
            if min_price or max_price or bedrooms:
                # Click filters button
                try:
                    await page.click('button:has-text("More")')
                    await handler._human_delay((300, 600))

                    if min_price:
                        await handler.select_dropdown(
                            selector='select[id="min-price"]',
                            value=str(min_price),
                            is_native=True
                        )

                    if max_price:
                        await handler.select_dropdown(
                            selector='select[id="max-price"]',
                            value=str(max_price),
                            is_native=True
                        )

                    if bedrooms:
                        await page.click(f'button:has-text("{bedrooms}")')

                    # Apply filters
                    await page.click('button:has-text("Apply")')

                except Exception as e:
                    logger.warning(f"Could not apply filters: {e}")

            logger.info(f"Zillow search submitted: {location}")
            return True

        except Exception as e:
            logger.error(f"Zillow search error: {e}")
            return False

    @staticmethod
    async def target_store_selector(page, zip_code: str) -> bool:
        """
        Select a Target store by ZIP code.

        Args:
            page: Playwright page
            zip_code: ZIP code to search

        Returns:
            True if successful
        """
        handler = ComplexFormHandler(page)

        try:
            # Find store locator
            await page.click('button:has-text("Store")')
            await handler._human_delay((300, 600))

            # Fill ZIP code
            await handler.fill_autocomplete(
                selector='input[placeholder*="ZIP"]',
                value=zip_code,
                exact_match=False
            )

            # Select first store
            await page.click('button:has-text("Select store")')
            logger.info(f"Target store selected for ZIP: {zip_code}")
            return True

        except Exception as e:
            logger.error(f"Target store selector error: {e}")
            return False


# Convenience function
async def create_form_handler(page, use_humanization: bool = True) -> ComplexFormHandler:
    """
    Factory function to create a ComplexFormHandler.

    Args:
        page: Playwright page object
        use_humanization: Enable human-like interactions

    Returns:
        ComplexFormHandler instance
    """
    return ComplexFormHandler(page, use_humanization)


# Export main classes
__all__ = [
    'ComplexFormHandler',
    'FormType',
    'InputType',
    'FormField',
    'FormStep',
    'SiteSpecificHandlers',
    'create_form_handler'
]
