# Date Picker Handler - Integration Guide

This guide shows how to integrate the Date Picker Handler into the Eversale CLI agent workflows.

## Quick Integration

### For Agent Workflows

The date picker handler is automatically available in the agent namespace:

```python
from agent import DatePickerHandler, fill_date_simple

# In any workflow or task:
async def book_hotel(page, checkin_date, checkout_date):
    """Book a hotel with specific dates"""

    # Simple one-liner
    success = await fill_date_simple(page, "#checkin", checkin_date)

    if not success:
        return {"error": "Failed to set check-in date"}

    # Continue with booking...
```

### For Playwright MCP Tools

Add date picker capabilities to MCP tools:

```python
# In playwright_direct.py or similar

async def search_with_dates(url, start_date, end_date):
    """Search with date range (e.g., flights, hotels)"""
    from agent.date_picker_handler import fill_date_range_simple

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        await page.goto(url)

        # Auto-detect and fill dates
        success = await fill_date_range_simple(
            page,
            start_date=start_date,
            end_date=end_date
        )

        if success:
            # Continue with search...
            return {"status": "dates_set"}
        else:
            return {"error": "Failed to set dates"}
```

## Site-Specific Integration Examples

### Booking.com Workflow

```python
async def search_booking_com(destination, checkin, checkout, guests=2):
    """
    Search Booking.com for hotels with specific dates.

    Args:
        destination: City name (e.g., "London")
        checkin: Check-in date (e.g., "2025-12-15")
        checkout: Check-out date (e.g., "2025-12-20")
        guests: Number of guests
    """
    from agent.date_picker_handler import DatePickerHandler

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        # Navigate to Booking.com
        await page.goto("https://www.booking.com")

        # Fill destination
        await page.fill("[name='ss']", destination)

        # Create date picker handler
        handler = DatePickerHandler(page)

        # Set dates using auto-detection
        result1, result2 = await handler.select_date_range(
            start_date=checkin,
            end_date=checkout
        )

        if not (result1.success and result2.success):
            return {
                "error": "Failed to set dates",
                "checkin_error": result1.message,
                "checkout_error": result2.message
            }

        # Set guests
        await page.click("[data-testid='occupancy-config']")
        # ... guest selection logic

        # Search
        await page.click("[type='submit']")

        # Wait for results
        await page.wait_for_selector(".sr_item")

        # Extract results
        results = await page.query_selector_all(".sr_item")

        return {
            "status": "success",
            "destination": destination,
            "checkin": result1.date_set,
            "checkout": result2.date_set,
            "results_count": len(results)
        }
```

### Airbnb Workflow

```python
async def search_airbnb(location, checkin, checkout, guests=2):
    """Search Airbnb with date picker handling"""
    from agent.date_picker_handler import DatePickerHandler

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        await page.goto("https://www.airbnb.com")

        # Fill location
        await page.click("[data-testid='structured-search-input-field-query']")
        await page.fill("[data-testid='structured-search-input-field-query']", location)

        # Open date picker
        await page.click("[data-testid='structured-search-input-field-split-dates-0']")

        # Create handler
        handler = DatePickerHandler(page)

        # Set dates (Airbnb uses single calendar for range)
        result1, result2 = await handler.select_date_range(
            start_date=checkin,
            end_date=checkout
        )

        if result1.success and result2.success:
            # Set guests
            await page.click("[data-testid='structured-search-input-field-guests-button']")
            # ... guest selection

            # Search
            await page.click("[data-testid='structured-search-input-search-button']")

            return {"status": "success"}
        else:
            return {"error": "Date selection failed"}
```

### Generic Calendar Widget

```python
async def fill_any_calendar(page, selector, date):
    """
    Fill any calendar widget automatically.

    Works with:
    - jQuery UI
    - React-datepicker
    - Flatpickr
    - Custom calendars
    """
    from agent.date_picker_handler import DatePickerHandler

    handler = DatePickerHandler(page)

    # Auto-detect and handle
    result = await handler.auto_handle_date(selector, date)

    return {
        "success": result.success,
        "picker_type": result.type,
        "date_set": result.date_set,
        "message": result.message
    }
```

## Adding to Brain/ReAct Loop

### Integration with brain_enhanced_v2.py

Add date picker as a capability:

```python
# In brain_enhanced_v2.py

class EnhancedBrain:
    def __init__(self):
        # ... existing init
        self.date_picker_handler = None

    async def handle_date_input(self, selector, date_str):
        """
        Handle date input on current page.

        This can be called from the ReAct loop when the agent
        needs to fill a date field.
        """
        if not self.date_picker_handler:
            from agent.date_picker_handler import DatePickerHandler
            self.date_picker_handler = DatePickerHandler(self.page)

        result = await self.date_picker_handler.auto_handle_date(
            selector,
            date_str
        )

        return {
            "action": "fill_date",
            "selector": selector,
            "date": date_str,
            "success": result.success,
            "picker_type": result.type,
            "message": result.message
        }
```

### Adding as MCP Tool

Create a new MCP tool for date handling:

```python
# In mcp_tools/ or tools/

@mcp.tool()
async def fill_date_picker(
    selector: str,
    date: str,
    picker_type: Optional[str] = None
) -> dict:
    """
    Fill a date picker on the current page.

    Args:
        selector: CSS selector for the date input/picker
        date: Date as string (formats: YYYY-MM-DD, MM/DD/YYYY, "Dec 15, 2025")
        picker_type: Optional explicit picker type

    Returns:
        Result with success status and details
    """
    from agent.date_picker_handler import DatePickerHandler

    # Get current page from browser context
    page = get_current_page()

    handler = DatePickerHandler(page)

    result = await handler.fill_date(
        selector,
        date,
        picker_type=picker_type
    )

    return {
        "success": result.success,
        "type": result.type,
        "date_set": result.date_set,
        "message": result.message
    }


@mcp.tool()
async def select_date_range_picker(
    start_date: str,
    end_date: str,
    start_selector: Optional[str] = None,
    end_selector: Optional[str] = None
) -> dict:
    """
    Select a date range (check-in/check-out style).

    Args:
        start_date: Start date as string
        end_date: End date as string
        start_selector: Optional selector for start date
        end_selector: Optional selector for end date

    Returns:
        Result with success status for both dates
    """
    from agent.date_picker_handler import DatePickerHandler

    page = get_current_page()
    handler = DatePickerHandler(page)

    result1, result2 = await handler.select_date_range(
        start_date,
        end_date,
        start_selector,
        end_selector
    )

    return {
        "success": result1.success and result2.success,
        "start_date": {
            "success": result1.success,
            "date_set": result1.date_set,
            "message": result1.message
        },
        "end_date": {
            "success": result2.success,
            "date_set": result2.date_set,
            "message": result2.message
        }
    }
```

## Workflow Examples

### Workflow E: E-commerce (Travel Booking)

```python
# In workflows_extended.py

async def workflow_e_travel_booking(task: str, context: dict) -> dict:
    """
    E-commerce workflow extended for travel bookings.

    Example: "Book flight from NYC to LAX on Dec 15-20"
    """
    from agent.date_picker_handler import fill_date_range_simple

    # Extract dates from task using LLM
    dates = await extract_dates_from_task(task)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        # Determine site (Kayak, Expedia, etc.)
        if "flight" in task.lower():
            await page.goto("https://www.kayak.com/flights")

            # Fill origin/destination
            # ...

            # Fill dates
            success = await fill_date_range_simple(
                page,
                start_date=dates["start"],
                end_date=dates["end"]
            )

            if success:
                # Search
                await page.click("[aria-label='Search']")
                # Extract results
                return {"status": "search_complete"}

    return {"error": "Booking failed"}
```

### Workflow AB: Travel

```python
async def workflow_ab_travel(task: str, context: dict) -> dict:
    """
    Travel workflow - monitor prices, build itineraries.

    Example: "Monitor flight prices to Tokyo for next month"
    """
    from agent.date_picker_handler import DatePickerHandler
    from datetime import datetime, timedelta

    # Parse destination and dates
    destination = extract_destination(task)
    start_date = datetime.now() + timedelta(days=30)
    end_date = start_date + timedelta(days=7)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        await page.goto("https://www.google.com/flights")

        handler = DatePickerHandler(page)

        # Fill departure/return dates
        result1, result2 = await handler.select_date_range(
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d")
        )

        if result1.success and result2.success:
            # Monitor prices over time
            return monitor_price_changes(page, destination)

    return {"error": "Failed to set dates"}
```

## Error Handling Best Practices

### Robust Error Handling

```python
async def fill_date_robust(page, selector, date_str):
    """Fill date with comprehensive error handling"""
    from agent.date_picker_handler import DatePickerHandler

    handler = DatePickerHandler(page)

    try:
        result = await handler.auto_handle_date(selector, date_str)

        if result.success:
            return {
                "success": True,
                "date": result.date_set,
                "method": result.type
            }
        else:
            # Try fallback: direct typing
            try:
                await page.fill(selector, date_str)
                return {
                    "success": True,
                    "date": date_str,
                    "method": "fallback_typing"
                }
            except:
                return {
                    "success": False,
                    "error": result.message,
                    "fallback_failed": True
                }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "exception": True
        }
```

### Retry Logic

```python
async def fill_date_with_retry(page, selector, date_str, max_retries=3):
    """Fill date with retry logic"""
    from agent.date_picker_handler import DatePickerHandler
    import asyncio

    handler = DatePickerHandler(page)

    for attempt in range(max_retries):
        try:
            result = await handler.auto_handle_date(selector, date_str)

            if result.success:
                return result

            # Wait before retry
            await asyncio.sleep(1 + attempt * 0.5)

        except Exception as e:
            if attempt == max_retries - 1:
                return DatePickerResult(
                    success=False,
                    type="unknown",
                    message=f"Failed after {max_retries} attempts: {str(e)}"
                )

    return DatePickerResult(
        success=False,
        type="unknown",
        message=f"Failed after {max_retries} attempts"
    )
```

## Performance Optimization

### Pre-detect Picker Type

If you know you'll fill multiple dates on the same page:

```python
async def fill_multiple_dates_optimized(page, dates_dict):
    """Fill multiple dates efficiently by detecting picker type once"""
    from agent.date_picker_handler import DatePickerHandler

    handler = DatePickerHandler(page)

    # Detect once
    picker_type, _ = await handler.detect_date_picker_type()

    results = {}
    for selector, date_str in dates_dict.items():
        # Use detected type for all subsequent fills
        result = await handler.fill_date(
            selector,
            date_str,
            picker_type=picker_type
        )
        results[selector] = result

    return results
```

### Parallel Date Filling

For independent date inputs:

```python
async def fill_dates_parallel(page, dates_list):
    """Fill multiple independent dates in parallel"""
    from agent.date_picker_handler import DatePickerHandler
    import asyncio

    handler = DatePickerHandler(page)

    tasks = [
        handler.fill_date(selector, date_str)
        for selector, date_str in dates_list
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    return results
```

## Testing Integration

### Unit Test Example

```python
import pytest
from agent.date_picker_handler import DatePickerHandler

@pytest.mark.asyncio
async def test_booking_com_integration(page):
    """Test Booking.com date picker integration"""
    await page.goto("https://www.booking.com")

    handler = DatePickerHandler(page)

    # Detect picker
    picker_type, selector = await handler.detect_date_picker_type()
    assert picker_type == "booking_com"

    # Fill dates
    result1, result2 = await handler.select_date_range(
        start_date="2025-12-15",
        end_date="2025-12-20"
    )

    assert result1.success
    assert result2.success
    assert result1.date_set == "2025-12-15"
    assert result2.date_set == "2025-12-20"
```

## Logging and Debugging

### Enable Debug Logging

```python
from loguru import logger

# Enable debug logging for date picker
logger.enable("agent.date_picker_handler")

# Use in workflow
handler = DatePickerHandler(page)
result = await handler.auto_handle_date("#date", "2025-12-15")

# Logs will show:
# - Picker type detection
# - Navigation steps
# - Click attempts
# - Success/failure
```

### Custom Logging

```python
async def fill_date_with_logging(page, selector, date_str):
    """Fill date with custom logging"""
    from agent.date_picker_handler import DatePickerHandler
    from loguru import logger

    handler = DatePickerHandler(page)

    logger.info(f"Attempting to fill date: {selector} = {date_str}")

    result = await handler.auto_handle_date(selector, date_str)

    if result.success:
        logger.success(f"✓ Date set via {result.type}: {result.date_set}")
    else:
        logger.error(f"✗ Failed to set date: {result.message}")

    return result
```

## Summary

The date picker handler integrates seamlessly into Eversale CLI:

✅ **Import and use** - `from agent import DatePickerHandler`
✅ **MCP tools** - Add as new tools for agent to use
✅ **Workflows** - Enhance travel/booking workflows
✅ **Error handling** - Comprehensive result reporting
✅ **Performance** - Optimized for common patterns
✅ **Testing** - Easy to unit test and validate

For more details, see:
- `DATE_PICKER_GUIDE.md` - Full API documentation
- `date_picker_example.py` - Usage examples
- `date_picker_handler.py` - Implementation

