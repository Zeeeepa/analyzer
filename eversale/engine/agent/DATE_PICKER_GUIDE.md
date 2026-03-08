# Date Picker Handler Module

Specialized date picker handling for the Eversale CLI browser automation agent.

## Features

✅ **Auto-detection** - Automatically detects date picker type on any page
✅ **Human-like interactions** - Uses Bezier cursor movements and realistic delays
✅ **Multiple formats** - Supports ISO, US, EU, and natural date formats
✅ **Site-specific handlers** - Optimized for Booking.com, Airbnb, Kayak, Expedia
✅ **Generic fallbacks** - Handles jQuery UI, React-datepicker, Flatpickr, HTML5
✅ **Range selection** - Check-in/check-out style date ranges
✅ **Calendar navigation** - Smart month/year navigation with limits
✅ **Production-ready** - Error handling, logging, type hints

## Quick Start

### Simple Usage

```python
from playwright.async_api import async_playwright
from agent.date_picker_handler import fill_date_simple, fill_date_range_simple

async with async_playwright() as p:
    browser = await p.chromium.launch()
    page = await browser.new_page()

    await page.goto("https://www.booking.com")

    # Fill single date - one line!
    await fill_date_simple(page, "#checkin", "2025-12-15")

    # Fill date range - one line!
    await fill_date_range_simple(
        page,
        start_date="2025-12-15",
        end_date="2025-12-20",
        start_selector="#checkin",
        end_selector="#checkout"
    )
```

### Advanced Usage

```python
from agent.date_picker_handler import DatePickerHandler

handler = DatePickerHandler(page)

# Auto-detect and fill
result = await handler.auto_handle_date("#date-input", "2025-12-15")
if result.success:
    print(f"Date set to {result.date_set}")
else:
    print(f"Failed: {result.message}")

# Manual type specification
result = await handler.fill_date(
    selector="#checkin",
    date_str="12/15/2025",
    picker_type="booking_com"
)

# Date range with auto-detection
result1, result2 = await handler.select_date_range(
    start_date="2025-12-15",
    end_date="2025-12-20"
)
```

## Supported Date Pickers

### HTML5 Date Input

Standard `<input type="date">` elements.

```python
await handler.fill_date("#mydate", "2025-12-15")
```

**How it works:**
- Sets value via JavaScript
- Dispatches `change` and `input` events
- Most reliable method for native inputs

### Booking.com

Specialized handler for Booking.com's calendar widget.

```python
result = await handler.fill_booking_com_date(
    date=datetime(2025, 12, 15),
    is_checkin=True
)
```

**Detects:**
- `.bui-calendar`
- `[data-bui-component='calendar']`
- `[data-bui-ref='input-check-in']`

**Features:**
- Navigates to correct month
- Clicks exact `[data-date]` attribute
- Handles both check-in and check-out

### Airbnb

Optimized for Airbnb's calendar application.

```python
result = await handler.fill_airbnb_date(
    date=datetime(2025, 12, 15),
    is_checkin=True
)
```

**Detects:**
- `[data-testid='calendar-application']`
- `._1h5uiygl`
- `.Calendar`

**Features:**
- Uses accessibility tree navigation
- Finds days via `data-testid`
- Handles split date inputs

### jQuery UI Datepicker

Classic jQuery UI datepicker plugin.

```python
result = await handler.fill_generic_calendar("#datepicker", date)
```

**Detects:**
- `.ui-datepicker`
- `#ui-datepicker-div`
- `.hasDatepicker` class

### React-datepicker

Popular React date picker component.

```python
result = await handler.fill_generic_calendar(".react-datepicker", date)
```

**Detects:**
- `.react-datepicker`
- `.react-datepicker-wrapper`

### Flatpickr

Lightweight datetime picker.

```python
result = await handler.fill_generic_calendar(".flatpickr-calendar", date)
```

**Detects:**
- `.flatpickr-calendar`
- `.flatpickr-input`
- `data-input` attribute

### Kayak / Expedia

Travel site date pickers.

```python
# Auto-detected
result = await handler.auto_handle_date(selector, "2025-12-15")
```

**Detects:**
- Kayak: `[data-cy='calendar']`, `.dateRangePickerCalendar`
- Expedia: `[data-stid='date-picker-graph']`, `.uitk-date-picker`

## Date Format Support

The module accepts dates in multiple formats:

| Format | Example | Notes |
|--------|---------|-------|
| **ISO 8601** | `2025-12-15` | Recommended, unambiguous |
| **US Format** | `12/15/2025` | Month/Day/Year |
| **EU Format** | `15/12/2025` | Day/Month/Year (only if day > 12) |
| **Natural** | `Dec 15, 2025` | Short month name |
| **Full Month** | `December 15, 2025` | Full month name |

```python
# All of these work:
await handler.fill_date("#date", "2025-12-15")
await handler.fill_date("#date", "12/15/2025")
await handler.fill_date("#date", "Dec 15, 2025")
await handler.fill_date("#date", "December 15, 2025")
```

## API Reference

### `DatePickerHandler`

Main class for handling date pickers.

#### Constructor

```python
handler = DatePickerHandler(page: Page)
```

**Parameters:**
- `page` - Playwright Page or Frame object

#### Methods

##### `detect_date_picker_type(selector=None)`

Auto-detect the type of date picker on the page.

```python
picker_type, selector = await handler.detect_date_picker_type("#date")
# Returns: ("booking_com", ".bui-calendar")
```

**Returns:** `Tuple[DatePickerType, Optional[str]]`

##### `fill_date(selector, date_str, picker_type=None)`

Fill a date into any date picker.

```python
result = await handler.fill_date(
    selector="#checkin",
    date_str="2025-12-15",
    picker_type="booking_com"  # Optional
)
```

**Parameters:**
- `selector` - CSS selector for the date input/picker
- `date_str` - Date as string (flexible formats)
- `picker_type` - Optional explicit type, otherwise auto-detected

**Returns:** `DatePickerResult`

##### `select_date_range(start_date, end_date, start_selector=None, end_selector=None)`

Select a date range (check-in/check-out style).

```python
result1, result2 = await handler.select_date_range(
    start_date="2025-12-15",
    end_date="2025-12-20",
    start_selector="#checkin",
    end_selector="#checkout"
)
```

**Returns:** `Tuple[DatePickerResult, DatePickerResult]`

##### `auto_handle_date(selector, date_str)`

Convenience method: Auto-detect and fill in one call.

```python
result = await handler.auto_handle_date("#date", "2025-12-15")
```

**Returns:** `DatePickerResult`

##### `navigate_calendar_to_month(target_date, calendar_selector, ...)`

Navigate a calendar widget to a specific month/year.

```python
success = await handler.navigate_calendar_to_month(
    target_date=datetime(2025, 12, 1),
    calendar_selector=".calendar",
    next_button="[class*='next']",
    prev_button="[class*='prev']",
    month_display="[class*='month']"
)
```

**Returns:** `bool`

##### `click_calendar_date(date, calendar_selector, day_selector_pattern=None)`

Click a specific day in a calendar widget.

```python
success = await handler.click_calendar_date(
    date=datetime(2025, 12, 15),
    calendar_selector=".calendar"
)
```

**Returns:** `bool`

### Helper Functions

#### `fill_date_simple(page, selector, date)`

Simple one-line function to fill a date.

```python
success = await fill_date_simple(page, "#date", "2025-12-15")
```

**Returns:** `bool`

#### `fill_date_range_simple(page, start_date, end_date, start_selector=None, end_selector=None)`

Simple function to fill a date range.

```python
success = await fill_date_range_simple(
    page,
    start_date="2025-12-15",
    end_date="2025-12-20",
    start_selector="#checkin",
    end_selector="#checkout"
)
```

**Returns:** `bool`

### Data Classes

#### `DatePickerResult`

Result of a date picker operation.

```python
@dataclass
class DatePickerResult:
    success: bool              # Whether operation succeeded
    type: DatePickerType       # Detected picker type
    message: str               # Human-readable message
    date_set: Optional[str]    # The date that was set (ISO format)
```

#### `DatePickerType`

Enum of supported picker types.

```python
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
```

## Examples

### Example 1: Booking.com Hotel Search

```python
from agent.date_picker_handler import DatePickerHandler
from datetime import datetime, timedelta

handler = DatePickerHandler(page)

# Set check-in (1 week from now)
checkin = datetime.now() + timedelta(days=7)
result1 = await handler.fill_booking_com_date(checkin, is_checkin=True)

# Set check-out (3 days later)
checkout = checkin + timedelta(days=3)
result2 = await handler.fill_booking_com_date(checkout, is_checkin=False)

if result1.success and result2.success:
    print(f"Dates set: {result1.date_set} to {result2.date_set}")
```

### Example 2: Generic Calendar Widget

```python
# Auto-detect and handle
result = await handler.auto_handle_date("#calendar", "2025-12-15")

if result.success:
    print(f"Set {result.type} picker to {result.date_set}")
else:
    print(f"Failed: {result.message}")
```

### Example 3: HTML5 Date Range

```python
# Simple helper for HTML5 inputs
success = await fill_date_range_simple(
    page,
    start_date="2025-12-15",
    end_date="2025-12-20",
    start_selector="#start",
    end_selector="#end"
)

print("Success!" if success else "Failed")
```

### Example 4: Date Format Flexibility

```python
# All of these work on the same input:
await handler.fill_date("#date", "2025-12-15")       # ISO
await handler.fill_date("#date", "12/15/2025")       # US
await handler.fill_date("#date", "Dec 15, 2025")     # Natural
await handler.fill_date("#date", "December 15, 2025") # Full
```

### Example 5: Error Handling

```python
result = await handler.fill_date("#checkin", "2025-12-15")

if result.success:
    print(f"✓ Date set to {result.date_set}")
else:
    print(f"✗ Failed: {result.message}")
    print(f"   Picker type: {result.type}")
    # Fallback logic here
```

## Integration with Humanization Module

The date picker handler automatically uses the humanization module for realistic interactions:

- **Bezier cursor movements** - Natural mouse paths when clicking dates
- **Human typing** - If fallback to typing is needed
- **Random delays** - Between month navigation and day clicks

To customize behavior:

```python
from agent.humanization import BezierCursor, CursorConfig

# Create custom cursor config
config = CursorConfig(
    min_duration_ms=100,
    max_duration_ms=500,
    overshoot_chance=0.2
)

cursor = BezierCursor(config)

# Pass to handler (if implementing custom handlers)
handler = DatePickerHandler(page)
handler.cursor = cursor
```

## Troubleshooting

### Date picker not detected

```python
# Try explicit type
result = await handler.fill_date(
    "#date",
    "2025-12-15",
    picker_type="calendar_generic"
)
```

### Calendar navigation fails

```python
# Use manual navigation with custom selectors
success = await handler.navigate_calendar_to_month(
    target_date=datetime(2025, 12, 1),
    calendar_selector=".your-calendar",
    next_button=".custom-next-btn",
    prev_button=".custom-prev-btn",
    month_display=".custom-month-display"
)
```

### Day click fails

```python
# Try manual click with custom pattern
success = await handler.click_calendar_date(
    date=datetime(2025, 12, 15),
    calendar_selector=".calendar",
    day_selector_pattern="[data-custom-date]"
)
```

### Fallback to typing

If auto-detection fails, the module falls back to typing:

```python
# This will type "12/15/2025" if picker not recognized
result = await handler.fill_date("#unknown-input", "2025-12-15")
# Result type will be "unknown" with message about fallback
```

## Performance

- **Auto-detection**: ~100-300ms (scans page for signatures)
- **Month navigation**: ~300ms per month (with human delays)
- **Day click**: ~200ms (Bezier curve movement + click)
- **Total for range**: ~1-3 seconds depending on months to navigate

All delays include humanization (realistic interaction speed).

## Browser Compatibility

✅ Chromium
✅ Firefox
✅ WebKit

Works with both Playwright and Playwright's frame API (for iframes).

## Dependencies

- `playwright` - Browser automation
- `loguru` - Logging
- `agent.humanization` - Human-like interactions (optional but recommended)

## Testing

Run the example file to test all functionality:

```bash
python agent/date_picker_example.py
```

This will test:
- HTML5 date inputs
- Date format parsing
- Simple helpers
- Auto-detection on real sites (optional)

## Future Enhancements

Potential additions:

- [ ] Time picker support (datetime-local)
- [ ] Month/year only pickers
- [ ] Date range with single calendar (Material UI style)
- [ ] Keyboard navigation (arrow keys)
- [ ] Mobile date pickers (touch events)
- [ ] Custom date validators
- [ ] Blackout dates handling
- [ ] Min/max date constraints

## License

Part of the Eversale CLI project. See main LICENSE file.

## Contributing

When adding new site-specific handlers:

1. Add signature to `DATEPICKER_SIGNATURES`
2. Implement `fill_<site>_date()` method
3. Add detection logic to `detect_date_picker_type()`
4. Add test to `date_picker_example.py`
5. Update this README

## Support

For issues or questions:
- Check the example file first
- Enable debug logging: `logger.enable("agent.date_picker_handler")`
- Review Playwright documentation for selector strategies
- Check site's DOM structure with DevTools

## Credits

Built for Eversale CLI by the Eversale team.

Integrates with:
- Playwright (Microsoft)
- Humanization module (Emunium, HumanCursor research)
- Loguru (logging)
