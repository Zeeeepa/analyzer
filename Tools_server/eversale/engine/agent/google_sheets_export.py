"""
Google Sheets Export - Write data to Google Sheets with human-like patterns

This module provides automated Google Sheets export capabilities with:
- Creating new sheets or opening existing ones
- Writing data from lists of dictionaries or 2D arrays
- Support for append and overwrite modes
- Cell formatting (text, numbers, dates, currency, percent)
- Realistic human-like interactions to avoid bot detection

Key Components:
- WriteMode: OVERWRITE (clear and replace) or APPEND (add to end)
- CellFormat: TEXT, NUMBER, DATE, CURRENCY, PERCENT
- SheetData: Container for data to export with metadata
- ExportResult: Result of export operation with diagnostics
- GoogleSheetsExporter: Main class for exporting data

Usage:
    from agent.google_sheets_export import (
        GoogleSheetsExporter, export_to_sheets,
        WriteMode, CellFormat, SheetData
    )

    # Export list of dictionaries
    data = [
        {"name": "Alice", "age": 30, "salary": 75000},
        {"name": "Bob", "age": 25, "salary": 65000}
    ]
    result = await export_to_sheets(page, data, sheet_name="Employees")

    # Export with custom configuration
    exporter = GoogleSheetsExporter()
    sheet_data = SheetData(
        headers=["Name", "Age", "Salary"],
        rows=[["Alice", 30, 75000], ["Bob", 25, 65000]],
        sheet_name="Employees",
        write_mode=WriteMode.APPEND
    )
    result = await exporter.export_data(page, sheet_data)
"""

import asyncio
import re
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union
from loguru import logger

from .stealth_utils import human_delay


class WriteMode(Enum):
    """How to write data to the sheet"""
    OVERWRITE = "overwrite"  # Clear existing data and replace
    APPEND = "append"  # Add to end of existing data


class CellFormat(Enum):
    """Cell formatting options"""
    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    CURRENCY = "currency"
    PERCENT = "percent"


@dataclass
class SheetData:
    """
    Container for data to export to Google Sheets.

    Args:
        headers: Column headers (list of strings)
        rows: Data rows (list of lists)
        sheet_name: Name for the sheet/tab
        start_cell: Starting cell reference (e.g., "A1", "B5")
        write_mode: OVERWRITE or APPEND
        format_columns: Optional dict mapping column index to CellFormat
    """
    headers: List[str]
    rows: List[List[Any]]
    sheet_name: str = "Sheet1"
    start_cell: str = "A1"
    write_mode: WriteMode = WriteMode.OVERWRITE
    format_columns: Optional[Dict[int, CellFormat]] = None


@dataclass
class ExportResult:
    """
    Result of a Google Sheets export operation.

    Args:
        success: Whether export succeeded
        sheet_url: URL of the Google Sheet
        sheet_name: Name of the sheet/tab
        rows_written: Number of rows written (including header)
        error: Error message if failed
    """
    success: bool
    sheet_url: str = ""
    sheet_name: str = ""
    rows_written: int = 0
    error: str = ""


class GoogleSheetsExporter:
    """
    Export data to Google Sheets with human-like automation.

    This class handles all aspects of writing data to Google Sheets,
    including creating new sheets, navigating to tabs, and writing
    data with realistic human timing patterns.

    Example:
        exporter = GoogleSheetsExporter()
        data = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
        result = await exporter.export_data(page, data, sheet_name="People")
    """

    SHEETS_HOME = "https://sheets.google.com"
    SHEETS_NEW = "https://docs.google.com/spreadsheets/create"

    def __init__(self):
        """Initialize the Google Sheets exporter."""
        self._current_sheet_url = None
        self._current_tab_name = None

    async def export_data(
        self,
        page,
        data: Union[List[Dict[str, Any]], List[List[Any]], SheetData],
        sheet_url: Optional[str] = None,
        sheet_name: str = "Sheet1",
        write_mode: WriteMode = WriteMode.OVERWRITE,
        format_columns: Optional[Dict[int, CellFormat]] = None
    ) -> ExportResult:
        """
        Export data to Google Sheets.

        This is the main entry point for exporting data. It handles
        all the complexity of normalizing data, navigating to sheets,
        and writing with human-like patterns.

        Args:
            page: Playwright page object
            data: Data to export (list of dicts, 2D array, or SheetData)
            sheet_url: URL of existing sheet (creates new if None)
            sheet_name: Name for the sheet tab
            write_mode: OVERWRITE or APPEND
            format_columns: Optional column formatting

        Returns:
            ExportResult with success status and details
        """
        try:
            logger.info(f"Starting Google Sheets export to '{sheet_name}'")

            # Normalize data to SheetData format
            if isinstance(data, SheetData):
                sheet_data = data
            else:
                sheet_data = self._normalize_data(
                    data,
                    sheet_name,
                    write_mode,
                    format_columns
                )

            # Verify we're logged into Google
            if not await self._verify_google_login(page):
                return ExportResult(
                    success=False,
                    error="Not logged into Google account"
                )

            # Create new sheet or open existing
            if sheet_url:
                logger.info(f"Opening existing sheet: {sheet_url}")
                final_url = await self._open_existing_sheet(page, sheet_url)
            else:
                logger.info("Creating new Google Sheet")
                final_url = await self._create_new_sheet(page)

            if not final_url:
                return ExportResult(
                    success=False,
                    error="Failed to create/open Google Sheet"
                )

            self._current_sheet_url = final_url

            # Rename sheet if needed (new sheets default to "Untitled spreadsheet")
            if not sheet_url:
                await self._rename_sheet(page, sheet_data.sheet_name)

            # Navigate to the correct tab (or create it)
            await self._navigate_to_tab(page, sheet_data.sheet_name)

            # Handle write mode
            if sheet_data.write_mode == WriteMode.APPEND:
                # Find last row and update start cell
                last_row = await self._find_last_row(page)
                sheet_data.start_cell = f"A{last_row + 1}"
                logger.info(f"Append mode: Starting at row {last_row + 1}")

            # Navigate to starting cell
            await self._navigate_to_cell(page, sheet_data.start_cell)

            # Write the data
            rows_written = await self._write_data(page, sheet_data)

            logger.info(f"Successfully wrote {rows_written} rows to Google Sheets")

            return ExportResult(
                success=True,
                sheet_url=final_url,
                sheet_name=sheet_data.sheet_name,
                rows_written=rows_written
            )

        except Exception as e:
            error_msg = f"Export failed: {str(e)}"
            logger.error(error_msg)
            return ExportResult(
                success=False,
                error=error_msg
            )

    def _normalize_data(
        self,
        data: Union[List[Dict[str, Any]], List[List[Any]]],
        sheet_name: str,
        write_mode: WriteMode,
        format_columns: Optional[Dict[int, CellFormat]]
    ) -> SheetData:
        """
        Normalize various data formats to SheetData.

        Handles both list of dictionaries and 2D arrays.

        Args:
            data: Input data in various formats
            sheet_name: Name for the sheet
            write_mode: OVERWRITE or APPEND
            format_columns: Optional column formatting

        Returns:
            SheetData object
        """
        if not data:
            return SheetData(
                headers=[],
                rows=[],
                sheet_name=sheet_name,
                write_mode=write_mode,
                format_columns=format_columns
            )

        # Check if it's a list of dictionaries
        if isinstance(data[0], dict):
            # Extract headers from first row keys
            headers = list(data[0].keys())

            # Convert each dict to a row
            rows = []
            for item in data:
                row = [item.get(header, "") for header in headers]
                rows.append(row)

            return SheetData(
                headers=headers,
                rows=rows,
                sheet_name=sheet_name,
                write_mode=write_mode,
                format_columns=format_columns
            )

        # It's a 2D array - assume first row is headers
        elif isinstance(data[0], list):
            if len(data) > 1:
                headers = [str(h) for h in data[0]]
                rows = data[1:]
            else:
                headers = [str(h) for h in data[0]]
                rows = []

            return SheetData(
                headers=headers,
                rows=rows,
                sheet_name=sheet_name,
                write_mode=write_mode,
                format_columns=format_columns
            )

        else:
            raise ValueError(f"Unsupported data format: {type(data[0])}")

    async def _verify_google_login(self, page) -> bool:
        """
        Verify that user is logged into Google account.

        Checks for presence of "Recent" or "Owned by me" text
        which indicates active Google session.

        Args:
            page: Playwright page object

        Returns:
            True if logged in, False otherwise
        """
        try:
            # Navigate to Google Sheets home
            await page.goto(self.SHEETS_HOME, wait_until="networkidle")
            await human_delay(500, 1000)

            # Check for login indicators
            indicators = [
                'text=Recent',
                'text=Owned by me',
                'text=Shared with me',
                '[aria-label*="Google Account"]'
            ]

            for indicator in indicators:
                element = await page.query_selector(indicator)
                if element:
                    logger.info("Verified Google login")
                    return True

            logger.warning("Not logged into Google")
            return False

        except Exception as e:
            logger.error(f"Login verification failed: {e}")
            return False

    async def _create_new_sheet(self, page) -> Optional[str]:
        """
        Create a new Google Sheet.

        Navigates to the create URL and waits for the sheet to load.

        Args:
            page: Playwright page object

        Returns:
            URL of the new sheet, or None if failed
        """
        try:
            logger.info("Creating new Google Sheet")

            # Navigate to create page
            await page.goto(self.SHEETS_NEW, wait_until="networkidle")
            await human_delay(1000, 2000)

            # Wait for sheet to be ready (check for cell A1)
            await page.wait_for_selector('[data-sheets-cell-id="A1"]', timeout=10000)
            await human_delay(500, 1000)

            # Get the final URL
            current_url = page.url
            logger.info(f"Created new sheet: {current_url}")

            return current_url

        except Exception as e:
            logger.error(f"Failed to create sheet: {e}")
            return None

    async def _open_existing_sheet(self, page, sheet_url: str) -> Optional[str]:
        """
        Open an existing Google Sheet by URL.

        Args:
            page: Playwright page object
            sheet_url: URL of the sheet to open

        Returns:
            URL of the opened sheet, or None if failed
        """
        try:
            logger.info(f"Opening existing sheet: {sheet_url}")

            # Navigate to the sheet
            await page.goto(sheet_url, wait_until="networkidle")
            await human_delay(1000, 2000)

            # Wait for sheet to be ready
            await page.wait_for_selector('[data-sheets-cell-id="A1"]', timeout=10000)
            await human_delay(500, 1000)

            return page.url

        except Exception as e:
            logger.error(f"Failed to open sheet: {e}")
            return None

    async def _rename_sheet(self, page, new_name: str) -> bool:
        """
        Rename the Google Sheet document.

        Clicks the title, selects all text, and types the new name.

        Args:
            page: Playwright page object
            new_name: New name for the sheet

        Returns:
            True if renamed successfully
        """
        try:
            logger.info(f"Renaming sheet to: {new_name}")

            # Find and click the title area
            title_selectors = [
                '[id="docs-title-widget"]',
                '[aria-label*="Rename"]',
                '.docs-title-input'
            ]

            title_element = None
            for selector in title_selectors:
                title_element = await page.query_selector(selector)
                if title_element:
                    break

            if not title_element:
                logger.warning("Could not find title element to rename")
                return False

            # Click to focus
            await title_element.click()
            await human_delay(200, 400)

            # Select all text
            await page.keyboard.press('Control+a')
            await human_delay(100, 200)

            # Type new name
            await page.keyboard.type(new_name, delay=50)
            await human_delay(100, 200)

            # Press Enter to confirm
            await page.keyboard.press('Enter')
            await human_delay(500, 1000)

            logger.info(f"Renamed sheet to: {new_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to rename sheet: {e}")
            return False

    async def _navigate_to_tab(self, page, tab_name: str) -> bool:
        """
        Navigate to a specific tab (sheet) within the spreadsheet.

        If the tab doesn't exist, it will be created.

        Args:
            page: Playwright page object
            tab_name: Name of the tab to navigate to

        Returns:
            True if navigation successful
        """
        try:
            logger.info(f"Navigating to tab: {tab_name}")

            # Look for existing tab
            tab_selector = f'[aria-label*="{tab_name}"]'
            tab_element = await page.query_selector(tab_selector)

            if tab_element:
                # Tab exists, click it
                await tab_element.click()
                await human_delay(300, 600)
                logger.info(f"Switched to existing tab: {tab_name}")
            else:
                # Tab doesn't exist, create it
                logger.info(f"Tab '{tab_name}' not found, creating new tab")
                await self._create_tab(page, tab_name)

            self._current_tab_name = tab_name
            return True

        except Exception as e:
            logger.error(f"Failed to navigate to tab: {e}")
            return False

    async def _create_tab(self, page, tab_name: str) -> bool:
        """
        Create a new tab (sheet) in the spreadsheet.

        Args:
            page: Playwright page object
            tab_name: Name for the new tab

        Returns:
            True if creation successful
        """
        try:
            logger.info(f"Creating new tab: {tab_name}")

            # Find the "Add sheet" button
            add_sheet_selectors = [
                '[aria-label="Add sheet"]',
                '[title="Add sheet"]',
                '.docs-sheet-add-button'
            ]

            add_button = None
            for selector in add_sheet_selectors:
                add_button = await page.query_selector(selector)
                if add_button:
                    break

            if not add_button:
                logger.warning("Could not find 'Add sheet' button")
                return False

            # Click to add new sheet
            await add_button.click()
            await human_delay(500, 1000)

            # The new sheet is now active, rename it
            # Right-click on the new tab to get context menu
            new_tab_selector = '.docs-sheet-tab-name'
            new_tab = await page.query_selector(new_tab_selector)

            if new_tab:
                await new_tab.click(button='right')
                await human_delay(200, 400)

                # Click "Rename" in context menu
                rename_option = await page.query_selector('text=Rename')
                if rename_option:
                    await rename_option.click()
                    await human_delay(200, 400)

                    # Type the new name
                    await page.keyboard.type(tab_name, delay=50)
                    await page.keyboard.press('Enter')
                    await human_delay(500, 1000)

            logger.info(f"Created new tab: {tab_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to create tab: {e}")
            return False

    async def _find_last_row(self, page) -> int:
        """
        Find the last row with data in the current sheet.

        Uses Ctrl+End to jump to the last used cell.

        Args:
            page: Playwright page object

        Returns:
            Row number of last used row (0 if empty)
        """
        try:
            logger.info("Finding last row")

            # Click cell A1 first
            await self._navigate_to_cell(page, "A1")

            # Press Ctrl+End to go to last used cell
            await page.keyboard.press('Control+End')
            await human_delay(300, 600)

            # Try to get the active cell reference
            # Look for the name box (shows current cell like "A15")
            name_box_selectors = [
                '[aria-label*="Name box"]',
                '#t-name-box',
                '.docs-namedb-widget-hover'
            ]

            for selector in name_box_selectors:
                name_box = await page.query_selector(selector)
                if name_box:
                    cell_ref = await name_box.text_content()
                    if cell_ref:
                        # Extract row number from cell reference (e.g., "A15" -> 15)
                        match = re.search(r'(\d+)', cell_ref)
                        if match:
                            row_num = int(match.group(1))
                            logger.info(f"Last row is: {row_num}")
                            return row_num

            # Fallback: assume empty sheet
            logger.info("Could not determine last row, assuming empty sheet")
            return 0

        except Exception as e:
            logger.error(f"Failed to find last row: {e}")
            return 0

    async def _navigate_to_cell(self, page, cell_ref: str) -> bool:
        """
        Navigate to a specific cell by reference.

        Clicks the name box and types the cell reference.

        Args:
            page: Playwright page object
            cell_ref: Cell reference (e.g., "A1", "B15")

        Returns:
            True if navigation successful
        """
        try:
            logger.info(f"Navigating to cell: {cell_ref}")

            # Find the name box
            name_box_selectors = [
                '[aria-label*="Name box"]',
                '#t-name-box',
                '.docs-namedb-widget-hover'
            ]

            name_box = None
            for selector in name_box_selectors:
                name_box = await page.query_selector(selector)
                if name_box:
                    break

            if not name_box:
                logger.warning("Could not find name box, using fallback")
                # Fallback: just click the cell directly
                cell_selector = f'[data-sheets-cell-id="{cell_ref}"]'
                cell = await page.query_selector(cell_selector)
                if cell:
                    await cell.click()
                    await human_delay(200, 400)
                    return True
                return False

            # Click name box
            await name_box.click()
            await human_delay(100, 200)

            # Clear and type cell reference
            await page.keyboard.press('Control+a')
            await human_delay(50, 100)
            await page.keyboard.type(cell_ref, delay=30)
            await human_delay(50, 100)

            # Press Enter to navigate
            await page.keyboard.press('Enter')
            await human_delay(200, 400)

            logger.info(f"Navigated to cell: {cell_ref}")
            return True

        except Exception as e:
            logger.error(f"Failed to navigate to cell: {e}")
            return False

    async def _write_data(self, page, sheet_data: SheetData) -> int:
        """
        Write data to the current sheet starting at current cell.

        Writes headers first, then all data rows.

        Args:
            page: Playwright page object
            sheet_data: Data to write

        Returns:
            Number of rows written (including header)
        """
        try:
            logger.info(f"Writing {len(sheet_data.rows)} rows to sheet")

            rows_written = 0

            # Write headers first
            if sheet_data.headers:
                await self._write_row(page, sheet_data.headers)
                rows_written += 1
                await human_delay(100, 300)

            # Write data rows
            for i, row in enumerate(sheet_data.rows):
                await self._write_row(page, row, sheet_data.format_columns)
                rows_written += 1

                # Occasional pause (like human checking data)
                if i % 10 == 0 and i > 0:
                    await human_delay(300, 600)
                else:
                    await human_delay(50, 150)

            logger.info(f"Finished writing {rows_written} rows")
            return rows_written

        except Exception as e:
            logger.error(f"Failed to write data: {e}")
            return 0

    async def _write_row(
        self,
        page,
        row: List[Any],
        format_columns: Optional[Dict[int, CellFormat]] = None
    ) -> bool:
        """
        Write a single row of data.

        Tabs between cells and presses Enter at the end to move to next row.

        Args:
            page: Playwright page object
            row: List of cell values
            format_columns: Optional formatting for columns

        Returns:
            True if row written successfully
        """
        try:
            for col_idx, value in enumerate(row):
                # Format the value
                formatted_value = self._format_cell_value(
                    value,
                    format_columns.get(col_idx) if format_columns else None
                )

                # Type the value
                if formatted_value:
                    await page.keyboard.type(str(formatted_value), delay=20)

                # Tab to next cell (except on last column)
                if col_idx < len(row) - 1:
                    await page.keyboard.press('Tab')
                    await human_delay(30, 80)

            # Press Enter to move to next row
            await page.keyboard.press('Enter')
            await human_delay(30, 80)

            return True

        except Exception as e:
            logger.error(f"Failed to write row: {e}")
            return False

    def _format_cell_value(
        self,
        value: Any,
        cell_format: Optional[CellFormat] = None
    ) -> str:
        """
        Format a cell value according to specified format.

        Args:
            value: Raw value to format
            cell_format: Optional formatting to apply

        Returns:
            Formatted string value
        """
        # Handle None/empty
        if value is None or value == "":
            return ""

        # Handle booleans
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"

        # Apply specific formatting
        if cell_format == CellFormat.CURRENCY:
            try:
                return f"${float(value):,.2f}"
            except (ValueError, TypeError):
                return str(value)

        elif cell_format == CellFormat.PERCENT:
            try:
                return f"{float(value) * 100:.2f}%"
            except (ValueError, TypeError):
                return str(value)

        elif cell_format == CellFormat.NUMBER:
            try:
                num = float(value)
                # Return integer if it's a whole number
                if num == int(num):
                    return str(int(num))
                return str(num)
            except (ValueError, TypeError):
                return str(value)

        elif cell_format == CellFormat.DATE:
            # Expect ISO format or datetime object
            if hasattr(value, 'strftime'):
                return value.strftime('%Y-%m-%d')
            return str(value)

        # Default: convert to string
        return str(value)


# Convenience function for quick exports
async def export_to_sheets(
    page,
    data: Union[List[Dict[str, Any]], List[List[Any]], SheetData],
    sheet_url: Optional[str] = None,
    sheet_name: str = "Sheet1",
    write_mode: WriteMode = WriteMode.OVERWRITE
) -> ExportResult:
    """
    Convenience function to export data to Google Sheets.

    This is a quick way to export data without creating an
    exporter instance explicitly.

    Args:
        page: Playwright page object
        data: Data to export (list of dicts, 2D array, or SheetData)
        sheet_url: URL of existing sheet (creates new if None)
        sheet_name: Name for the sheet tab
        write_mode: OVERWRITE or APPEND

    Returns:
        ExportResult with success status and details

    Example:
        data = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25}
        ]
        result = await export_to_sheets(page, data, sheet_name="People")
        if result.success:
            print(f"Exported to: {result.sheet_url}")
    """
    exporter = GoogleSheetsExporter()
    return await exporter.export_data(
        page,
        data,
        sheet_url=sheet_url,
        sheet_name=sheet_name,
        write_mode=write_mode
    )
