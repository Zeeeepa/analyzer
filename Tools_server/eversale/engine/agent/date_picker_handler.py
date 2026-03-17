"""
Date Picker Handler - Specialized handling for date pickers across multiple platforms

This module handles common date picker patterns found across the web:
- Booking.com style (calendar popup with month navigation)
- Airbnb style (inline calendar)
- Standard HTML5 date inputs
- jQuery UI datepicker
- React-datepicker
- Flatpickr
- Kayak, Expedia, and other travel sites

Uses humanization module for realistic interactions with proper delays and cursor movements.

Example:
    from agent.date_picker_handler import DatePickerHandler

    handler = DatePickerHandler(page)

    # Fill single date
    await handler.fill_date("#checkin", "2025-12-15")

    # Select date range
    await handler.select_date_range(
        start_date="2025-12-15",
        end_date="2025-12-20",
        start_selector="#checkin",
        end_selector="#checkout"
    )

    # Auto-detect and handle any date picker
    await handler.auto_handle_date("#date-input", "2025-12-15")
"""

import asyncio
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, List, Literal
from dataclasses import dataclass
from loguru import logger

try:
    from playwright.async_api import Page, ElementHandle, Locator
except ImportError:
    # Fallback for development
    Page = ElementHandle = Locator = None

try:
    from .humanization import BezierCursor, HumanTyper, get_cursor, get_typer
except ImportError:
    # Fallback if humanization not available
    BezierCursor = HumanTyper = None
    get_cursor = lambda: None
    get_typer = lambda: None


DatePickerType = Literal[
    "html5",
    "booking_com",
    "airbnb",
    "jquery_ui",
    "react_datepicker",
    "flatpickr",
    "kayak",
    "expedia",
    "calendar_generic",
    "unknown"
]


@dataclass
class DatePickerSignature:
    """Signatures for detecting date picker types"""
    type: DatePickerType
    selectors: List[str]
    attributes: List[str]
    class_patterns: List[str]
    js_objects: List[str]


# Known date picker signatures
DATEPICKER_SIGNATURES: List[DatePickerSignature] = [
    # HTML5 native
    DatePickerSignature(
        type="html5",
        selectors=["input[type='date']"],
        attributes=["type"],
        class_patterns=[],
        js_objects=[]
    ),

    # Booking.com
    DatePickerSignature(
        type="booking_com",
        selectors=[
            ".bui-calendar",
            "[data-bui-component='calendar']",
            ".c2-calendar-wrapper"
        ],
        attributes=["data-bui-component"],
        class_patterns=["bui-calendar", "c2-calendar"],
        js_objects=["window.booking"]
    ),

    # Airbnb
    DatePickerSignature(
        type="airbnb",
        selectors=[
            "[data-testid='calendar-application']",
            "._1h5uiygl",
            ".Calendar"
        ],
        attributes=["data-testid", "data-visible"],
        class_patterns=["_1h5uiygl", "Calendar"],
        js_objects=[]
    ),

    # jQuery UI
    DatePickerSignature(
        type="jquery_ui",
        selectors=[
            ".ui-datepicker",
            "#ui-datepicker-div"
        ],
        attributes=["data-handler"],
        class_patterns=["ui-datepicker", "hasDatepicker"],
        js_objects=["jQuery.datepicker"]
    ),

    # React-datepicker
    DatePickerSignature(
        type="react_datepicker",
        selectors=[
            ".react-datepicker",
            ".react-datepicker-wrapper"
        ],
        attributes=["data-testid"],
        class_patterns=["react-datepicker"],
        js_objects=[]
    ),

    # Flatpickr
    DatePickerSignature(
        type="flatpickr",
        selectors=[
            ".flatpickr-calendar",
            ".flatpickr-input"
        ],
        attributes=["data-input"],
        class_patterns=["flatpickr"],
        js_objects=["flatpickr"]
    ),

    # Kayak
    DatePickerSignature(
        type="kayak",
        selectors=[
            ".c3F-t-r",
            ".dateRangePickerCalendar",
            "[data-cy='calendar']"
        ],
        attributes=["data-cy"],
        class_patterns=["dateRangePickerCalendar"],
        js_objects=[]
    ),

    # Expedia
    DatePickerSignature(
        type="expedia",
        selectors=[
            "[data-stid='date-picker-graph']",
            ".uitk-date-picker",
            "[data-testid='date-picker']"
        ],
        attributes=["data-stid", "data-testid"],
        class_patterns=["uitk-date-picker"],
        js_objects=[]
    ),
]


@dataclass
class DatePickerResult:
    """Result of date picker operation"""
    success: bool
    type: DatePickerType
    message: str
    date_set: Optional[str] = None


class DatePickerHandler:
    """
    Handles all common date picker types with human-like interactions.

    Automatically detects picker type and uses appropriate strategy.
    Integrates with humanization module for realistic cursor/typing patterns.
    """

    def __init__(self, page: Page):
        self.page = page
        self.cursor = get_cursor() if BezierCursor else None
        self.typer = get_typer() if HumanTyper else None

    async def detect_date_picker_type(
        self,
        selector: Optional[str] = None
    ) -> Tuple[DatePickerType, Optional[str]]:
        """
        Detect what kind of date picker is on the page or at a selector.

        Args:
            selector: Optional CSS selector to check. If None, scans whole page.

        Returns:
            Tuple of (picker_type, actual_selector_found)
        """
        logger.debug(f"Detecting date picker type for selector: {selector}")

        # If specific selector provided, check its type
        if selector:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    # Check HTML5 date input
                    input_type = await element.get_attribute("type")
                    if input_type == "date":
                        return ("html5", selector)

                    # Check classes and attributes
                    class_attr = await element.get_attribute("class") or ""

                    for sig in DATEPICKER_SIGNATURES:
                        for pattern in sig.class_patterns:
                            if pattern in class_attr:
                                return (sig.type, selector)
            except Exception as e:
                logger.warning(f"Error checking selector {selector}: {e}")

        # Scan page for known signatures
        for sig in DATEPICKER_SIGNATURES:
            for sel in sig.selectors:
                try:
                    element = await self.page.query_selector(sel)
                    if element:
                        is_visible = await element.is_visible()
                        if is_visible or sig.type == "html5":
                            logger.info(f"Detected {sig.type} date picker: {sel}")
                            return (sig.type, sel)
                except Exception as e:
                    logger.debug(f"Selector {sel} not found: {e}")
                    continue

        # Check for generic calendar patterns
        generic_patterns = [
            "[class*='calendar']",
            "[class*='datepicker']",
            "[class*='date-picker']",
            "[id*='calendar']",
            "[id*='datepicker']"
        ]

        for pattern in generic_patterns:
            try:
                element = await self.page.query_selector(pattern)
                if element and await element.is_visible():
                    logger.info(f"Detected generic calendar: {pattern}")
                    return ("calendar_generic", pattern)
            except:
                continue

        return ("unknown", None)

    async def parse_date(self, date_str: str) -> datetime:
        """
        Parse date string in various formats.

        Supports:
            - ISO: 2025-12-15
            - US: 12/15/2025
            - EU: 15/12/2025
            - Natural: Dec 15, 2025
        """
        date_str = date_str.strip()

        # ISO format (YYYY-MM-DD)
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            return datetime.strptime(date_str, "%Y-%m-%d")

        # US format (MM/DD/YYYY)
        if re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', date_str):
            return datetime.strptime(date_str, "%m/%d/%Y")

        # EU format (DD/MM/YYYY)
        # Ambiguous - default to US unless day > 12
        parts = date_str.split('/')
        if len(parts) == 3 and int(parts[0]) > 12:
            return datetime.strptime(date_str, "%d/%m/%Y")

        # Natural format (Dec 15, 2025)
        try:
            return datetime.strptime(date_str, "%b %d, %Y")
        except:
            pass

        # Try full month name
        try:
            return datetime.strptime(date_str, "%B %d, %Y")
        except:
            pass

        raise ValueError(f"Unable to parse date: {date_str}")

    async def fill_html5_date(
        self,
        selector: str,
        date: datetime
    ) -> DatePickerResult:
        """Fill HTML5 <input type="date"> element."""
        try:
            # HTML5 date inputs expect YYYY-MM-DD format
            date_str = date.strftime("%Y-%m-%d")

            element = await self.page.query_selector(selector)
            if not element:
                return DatePickerResult(
                    success=False,
                    type="html5",
                    message=f"Element not found: {selector}"
                )

            # Focus the input
            await element.focus()
            await asyncio.sleep(0.1)

            # Fill using JavaScript (more reliable for HTML5 date inputs)
            await self.page.evaluate(f"""
                document.querySelector('{selector}').value = '{date_str}';
                document.querySelector('{selector}').dispatchEvent(new Event('change', {{ bubbles: true }}));
                document.querySelector('{selector}').dispatchEvent(new Event('input', {{ bubbles: true }}));
            """)

            logger.info(f"Filled HTML5 date input {selector} with {date_str}")

            return DatePickerResult(
                success=True,
                type="html5",
                message="Date set successfully",
                date_set=date_str
            )

        except Exception as e:
            logger.error(f"Error filling HTML5 date: {e}")
            return DatePickerResult(
                success=False,
                type="html5",
                message=f"Error: {str(e)}"
            )

    async def navigate_calendar_to_month(
        self,
        target_date: datetime,
        calendar_selector: str,
        next_button: str = "[class*='next']",
        prev_button: str = "[class*='prev']",
        month_display: str = "[class*='month']",
        max_clicks: int = 24  # Don't click more than 24 times (2 years)
    ) -> bool:
        """
        Navigate a calendar widget to a specific month/year.

        Args:
            target_date: The date to navigate to
            calendar_selector: Base selector for the calendar
            next_button: Selector for next month button (relative to calendar)
            prev_button: Selector for previous month button (relative to calendar)
            month_display: Selector showing current month/year
            max_clicks: Maximum navigation clicks to prevent infinite loops

        Returns:
            True if navigation successful, False otherwise
        """
        try:
            target_month = target_date.month
            target_year = target_date.year

            clicks = 0
            while clicks < max_clicks:
                # Get current month/year from display
                month_text = await self.page.text_content(f"{calendar_selector} {month_display}")
                if not month_text:
                    logger.warning("Could not read month display")
                    return False

                # Parse current month/year
                current_date = self._parse_month_display(month_text)
                if not current_date:
                    logger.warning(f"Could not parse month display: {month_text}")
                    return False

                # Check if we're at the target month
                if current_date.month == target_month and current_date.year == target_year:
                    logger.info(f"Navigated to target month: {target_date.strftime('%B %Y')}")
                    return True

                # Determine direction
                if (target_year > current_date.year or
                    (target_year == current_date.year and target_month > current_date.month)):
                    # Click next
                    button_sel = f"{calendar_selector} {next_button}"
                else:
                    # Click prev
                    button_sel = f"{calendar_selector} {prev_button}"

                # Click with human-like behavior
                if self.cursor:
                    await self.cursor.click_at(self.page, selector=button_sel)
                else:
                    await self.page.click(button_sel)

                await asyncio.sleep(0.3)  # Wait for animation
                clicks += 1

            logger.warning(f"Reached max navigation clicks ({max_clicks})")
            return False

        except Exception as e:
            logger.error(f"Error navigating calendar: {e}")
            return False

    def _parse_month_display(self, text: str) -> Optional[datetime]:
        """Parse month display text like 'December 2025' or 'Dec 2025'."""
        text = text.strip()

        # Try various formats
        formats = [
            "%B %Y",      # December 2025
            "%b %Y",      # Dec 2025
            "%B, %Y",     # December, 2025
            "%b, %Y",     # Dec, 2025
            "%Y %B",      # 2025 December
            "%Y %b",      # 2025 Dec
        ]

        for fmt in formats:
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue

        return None

    async def click_calendar_date(
        self,
        date: datetime,
        calendar_selector: str,
        day_selector_pattern: str = "[data-date]"
    ) -> bool:
        """
        Click a specific day in a calendar widget.

        Args:
            date: The date to click
            calendar_selector: Base selector for the calendar
            day_selector_pattern: Pattern to find day elements

        Returns:
            True if click successful, False otherwise
        """
        try:
            day = date.day

            # Common patterns for finding day cells
            patterns = [
                f"{calendar_selector} [data-date*='{date.strftime('%Y-%m-%d')}']",
                f"{calendar_selector} [data-day='{day}']",
                f"{calendar_selector} [aria-label*='{date.strftime('%B')}'][aria-label*='{day}']",
                f"{calendar_selector} td:has-text('{day}'):not([class*='disabled'])",
                f"{calendar_selector} div:has-text('{day}'):not([class*='disabled'])",
            ]

            for pattern in patterns:
                try:
                    elements = await self.page.query_selector_all(pattern)

                    # Filter for visible, clickable elements
                    for elem in elements:
                        is_visible = await elem.is_visible()
                        is_disabled = await elem.get_attribute("disabled")
                        class_attr = await elem.get_attribute("class") or ""

                        if (is_visible and
                            not is_disabled and
                            "disabled" not in class_attr.lower()):

                            # Click with human-like behavior
                            if self.cursor:
                                await self.cursor.click_at(self.page, element=elem)
                            else:
                                await elem.click()

                            logger.info(f"Clicked day {day} in calendar")
                            await asyncio.sleep(0.2)
                            return True

                except Exception as e:
                    logger.debug(f"Pattern {pattern} failed: {e}")
                    continue

            logger.warning(f"Could not find clickable day {day} in calendar")
            return False

        except Exception as e:
            logger.error(f"Error clicking calendar date: {e}")
            return False

    async def fill_booking_com_date(
        self,
        date: datetime,
        is_checkin: bool = True
    ) -> DatePickerResult:
        """Handle Booking.com specific date picker."""
        try:
            # Booking.com uses data-date attributes
            calendar_sel = ".bui-calendar, [data-bui-component='calendar'], .c2-calendar-wrapper"

            # First, ensure calendar is open
            calendar = await self.page.query_selector(calendar_sel)
            if not calendar or not await calendar.is_visible():
                # Try to open by clicking the date input
                input_sel = "[data-bui-ref='input-check-in']" if is_checkin else "[data-bui-ref='input-check-out']"
                try:
                    await self.page.click(input_sel)
                    await asyncio.sleep(0.5)
                except:
                    pass

            # Navigate to the correct month
            success = await self.navigate_calendar_to_month(
                date,
                calendar_sel,
                next_button="[data-bui-ref='calendar-next']",
                prev_button="[data-bui-ref='calendar-previous']",
                month_display=".bui-calendar__month"
            )

            if not success:
                return DatePickerResult(
                    success=False,
                    type="booking_com",
                    message="Failed to navigate to target month"
                )

            # Click the specific day
            date_str = date.strftime("%Y-%m-%d")
            day_selector = f"{calendar_sel} [data-date='{date_str}']"

            if self.cursor:
                await self.cursor.click_at(self.page, selector=day_selector)
            else:
                await self.page.click(day_selector)

            logger.info(f"Set Booking.com date to {date_str}")

            return DatePickerResult(
                success=True,
                type="booking_com",
                message="Date set successfully",
                date_set=date_str
            )

        except Exception as e:
            logger.error(f"Error filling Booking.com date: {e}")
            return DatePickerResult(
                success=False,
                type="booking_com",
                message=f"Error: {str(e)}"
            )

    async def fill_airbnb_date(
        self,
        date: datetime,
        is_checkin: bool = True
    ) -> DatePickerResult:
        """Handle Airbnb specific date picker."""
        try:
            calendar_sel = "[data-testid='calendar-application'], ._1h5uiygl, .Calendar"

            # Airbnb calendar is usually visible, just navigate
            success = await self.navigate_calendar_to_month(
                date,
                calendar_sel,
                next_button="[aria-label*='Next']",
                prev_button="[aria-label*='Previous']",
                month_display="[data-testid='calendar-month-heading']"
            )

            if not success:
                return DatePickerResult(
                    success=False,
                    type="airbnb",
                    message="Failed to navigate to target month"
                )

            # Click the day
            success = await self.click_calendar_date(
                date,
                calendar_sel,
                day_selector_pattern="[data-testid*='day']"
            )

            if not success:
                return DatePickerResult(
                    success=False,
                    type="airbnb",
                    message="Failed to click day"
                )

            date_str = date.strftime("%Y-%m-%d")
            logger.info(f"Set Airbnb date to {date_str}")

            return DatePickerResult(
                success=True,
                type="airbnb",
                message="Date set successfully",
                date_set=date_str
            )

        except Exception as e:
            logger.error(f"Error filling Airbnb date: {e}")
            return DatePickerResult(
                success=False,
                type="airbnb",
                message=f"Error: {str(e)}"
            )

    async def fill_generic_calendar(
        self,
        selector: str,
        date: datetime
    ) -> DatePickerResult:
        """Handle generic calendar widget (jQuery UI, React-datepicker, etc)."""
        try:
            # Try to navigate to month
            success = await self.navigate_calendar_to_month(
                date,
                selector,
                next_button="[class*='next'], [title*='Next'], [aria-label*='Next']",
                prev_button="[class*='prev'], [title*='Prev'], [aria-label*='Prev']",
                month_display="[class*='month'], [class*='header']"
            )

            if not success:
                logger.warning("Could not navigate calendar, attempting direct click")

            # Click the day
            success = await self.click_calendar_date(date, selector)

            if not success:
                return DatePickerResult(
                    success=False,
                    type="calendar_generic",
                    message="Failed to click day in calendar"
                )

            date_str = date.strftime("%Y-%m-%d")
            logger.info(f"Set generic calendar to {date_str}")

            return DatePickerResult(
                success=True,
                type="calendar_generic",
                message="Date set successfully",
                date_set=date_str
            )

        except Exception as e:
            logger.error(f"Error filling generic calendar: {e}")
            return DatePickerResult(
                success=False,
                type="calendar_generic",
                message=f"Error: {str(e)}"
            )

    async def fill_date(
        self,
        selector: str,
        date_str: str,
        picker_type: Optional[DatePickerType] = None
    ) -> DatePickerResult:
        """
        Fill a date into any date picker.

        Args:
            selector: CSS selector for the date input/picker
            date_str: Date as string (various formats supported)
            picker_type: Optional explicit picker type, otherwise auto-detect

        Returns:
            DatePickerResult with success status and details
        """
        try:
            # Parse the date
            date = await self.parse_date(date_str)
            logger.info(f"Filling date: {date.strftime('%Y-%m-%d')}")

            # Detect picker type if not provided
            if not picker_type:
                picker_type, detected_selector = await self.detect_date_picker_type(selector)
                if detected_selector:
                    selector = detected_selector

            # Route to appropriate handler
            if picker_type == "html5":
                return await self.fill_html5_date(selector, date)

            elif picker_type == "booking_com":
                return await self.fill_booking_com_date(date, is_checkin=True)

            elif picker_type == "airbnb":
                return await self.fill_airbnb_date(date, is_checkin=True)

            elif picker_type in ["jquery_ui", "react_datepicker", "flatpickr", "calendar_generic"]:
                return await self.fill_generic_calendar(selector, date)

            else:
                # Fallback: try typing the date
                logger.warning(f"Unknown picker type, attempting to type date")

                try:
                    await self.page.fill(selector, date.strftime("%m/%d/%Y"))
                    return DatePickerResult(
                        success=True,
                        type="unknown",
                        message="Date typed as fallback",
                        date_set=date.strftime("%m/%d/%Y")
                    )
                except Exception as e:
                    return DatePickerResult(
                        success=False,
                        type="unknown",
                        message=f"No handler available and typing failed: {str(e)}"
                    )

        except Exception as e:
            logger.error(f"Error in fill_date: {e}")
            return DatePickerResult(
                success=False,
                type=picker_type or "unknown",
                message=f"Error: {str(e)}"
            )

    async def select_date_range(
        self,
        start_date: str,
        end_date: str,
        start_selector: Optional[str] = None,
        end_selector: Optional[str] = None
    ) -> Tuple[DatePickerResult, DatePickerResult]:
        """
        Select a date range (check-in/check-out style).

        Args:
            start_date: Start date as string
            end_date: End date as string
            start_selector: Optional selector for start date input
            end_selector: Optional selector for end date input

        Returns:
            Tuple of (start_result, end_result)
        """
        logger.info(f"Selecting date range: {start_date} to {end_date}")

        # Parse dates
        start = await self.parse_date(start_date)
        end = await self.parse_date(end_date)

        # Detect picker type
        picker_type, detected_selector = await self.detect_date_picker_type(
            start_selector if start_selector else None
        )

        # For some pickers (Booking.com, Airbnb), clicking start then end works
        if picker_type in ["booking_com", "airbnb"]:
            # These sites handle range selection in one calendar
            result1 = await self.fill_date(
                start_selector or detected_selector,
                start_date,
                picker_type=picker_type
            )

            await asyncio.sleep(0.3)

            result2 = await self.fill_date(
                end_selector or detected_selector,
                end_date,
                picker_type=picker_type
            )

            return (result1, result2)

        # For separate inputs, fill each independently
        else:
            result1 = await self.fill_date(
                start_selector or detected_selector,
                start_date,
                picker_type=picker_type
            )

            await asyncio.sleep(0.5)

            if end_selector:
                # Detect picker type for end date
                end_picker_type, end_detected = await self.detect_date_picker_type(end_selector)

                result2 = await self.fill_date(
                    end_selector,
                    end_date,
                    picker_type=end_picker_type
                )
            else:
                result2 = DatePickerResult(
                    success=False,
                    type="unknown",
                    message="No end selector provided"
                )

            return (result1, result2)

    async def auto_handle_date(
        self,
        selector: str,
        date_str: str
    ) -> DatePickerResult:
        """
        Convenience method: Auto-detect picker and fill date.

        This is the simplest interface - just provide a selector and date.

        Example:
            result = await handler.auto_handle_date("#checkin", "2025-12-15")
            if result.success:
                print(f"Date set to {result.date_set}")
        """
        return await self.fill_date(selector, date_str)


# Convenience functions for quick usage

async def fill_date_simple(
    page: Page,
    selector: str,
    date: str
) -> bool:
    """
    Simple function to fill a date picker.

    Args:
        page: Playwright page
        selector: CSS selector for date input
        date: Date as string (flexible formats)

    Returns:
        True if successful, False otherwise
    """
    handler = DatePickerHandler(page)
    result = await handler.auto_handle_date(selector, date)
    return result.success


async def fill_date_range_simple(
    page: Page,
    start_date: str,
    end_date: str,
    start_selector: Optional[str] = None,
    end_selector: Optional[str] = None
) -> bool:
    """
    Simple function to fill a date range.

    Args:
        page: Playwright page
        start_date: Start date as string
        end_date: End date as string
        start_selector: Optional selector for start date
        end_selector: Optional selector for end date

    Returns:
        True if both dates set successfully, False otherwise
    """
    handler = DatePickerHandler(page)
    result1, result2 = await handler.select_date_range(
        start_date,
        end_date,
        start_selector,
        end_selector
    )
    return result1.success and result2.success


# Export main classes and functions
__all__ = [
    'DatePickerHandler',
    'DatePickerResult',
    'DatePickerType',
    'fill_date_simple',
    'fill_date_range_simple',
]
