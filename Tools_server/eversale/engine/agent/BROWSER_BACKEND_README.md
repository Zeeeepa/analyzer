# Browser Backend Abstraction Layer

## Overview

The Browser Backend abstraction provides a unified interface for browser automation that works across different underlying technologies (Playwright, Chrome DevTools Protocol, etc.).

This enables:
- **Session Reuse**: Use existing Chrome sessions with saved logins via CDP
- **Incremental Migration**: Switch backends without rewriting high-level code
- **Testing Flexibility**: Compare different automation approaches
- **Technology Independence**: Swap implementations as better tools emerge

## Architecture

```
┌─────────────────────────────────────────┐
│      High-Level Agent Code              │
│   (SimpleAgent, EnhancedBrain, etc.)    │
└─────────────────┬───────────────────────┘
                  │
                  │ Uses abstract interface
                  ▼
┌─────────────────────────────────────────┐
│       BrowserBackend (ABC)              │
│                                         │
│  - navigate()                           │
│  - snapshot() → SnapshotResult          │
│  - click(ref) → InteractionResult       │
│  - type(ref, text) → InteractionResult  │
│  - scroll(), run_code(), observe()      │
└─────────────────┬───────────────────────┘
                  │
         ┌────────┴────────┐
         │                 │
         ▼                 ▼
┌──────────────┐   ┌──────────────┐
│ Playwright   │   │ CDP Backend  │
│ Backend      │   │              │
│              │   │ (Reuse       │
│ (Stealth,    │   │  existing    │
│  MMID refs)  │   │  Chrome)     │
└──────────────┘   └──────────────┘
```

## Core Concepts

### 1. BrowserBackend (Abstract Base Class)

All browser implementations must implement this interface:

```python
class BrowserBackend(ABC):
    async def connect() -> bool
    async def disconnect() -> None
    async def navigate(url) -> NavigationResult
    async def snapshot() -> SnapshotResult
    async def click(ref) -> InteractionResult
    async def type(ref, text) -> InteractionResult
    async def scroll(direction, amount) -> InteractionResult
    async def run_code(js) -> Any
    async def observe(network, console) -> ObserveResult
    async def screenshot(full_page) -> bytes
```

### 2. SnapshotResult - Structured Page State

Contains everything needed to understand and interact with a page:

```python
@dataclass
class SnapshotResult:
    url: str
    title: str
    elements: List[ElementRef]  # All actionable elements
    refs: Dict[str, ElementRef]  # Lookup by mmid
    accessibility_tree: Optional[str]
    summary: Optional[str]

    def get_by_mmid(mmid: str) -> Optional[ElementRef]
    def get_by_role(role: str, text: str = None) -> List[ElementRef]
```

### 3. ElementRef - Actionable Element Reference

Multiple targeting strategies for reliability:

```python
@dataclass
class ElementRef:
    mmid: str       # Unique marker (e.g., "mm123")
    ref: str        # Human-readable (e.g., "button:Submit")
    role: str       # ARIA role (button, link, textbox, etc.)
    text: str       # Visible text
    tag: str        # HTML tag
    selector: str   # CSS selector
    rect: Dict      # {x, y, width, height}
    # Optional: href, name, id, placeholder
```

### 4. InteractionResult - Action Outcome

```python
@dataclass
class InteractionResult:
    success: bool
    error: Optional[str]
    error_type: Optional[str]  # "timeout", "not_found", etc.
    url: Optional[str]
    url_changed: bool
    dom_changed: bool
    duration_ms: Optional[float]
    method: Optional[str]  # "mmid_selector", "coordinates", etc.
```

## Backend Implementations

### PlaywrightBackend

Wraps existing `playwright_direct.py` functionality:

- **Stealth Mode**: Uses patchright/rebrowser for bot detection bypass
- **MMID System**: Injects unique markers for reliable element targeting
- **Fallback Strategies**: Tries mmid → coordinates → selector
- **Full Featured**: All humanization, anti-detect, recovery features

**When to use:**
- Starting fresh automation
- Need stealth/anti-detect features
- Self-contained browser needed

### CDPBackend

Connects to existing Chrome via Chrome DevTools Protocol:

- **Session Reuse**: Keep existing logins across automation runs
- **Lightweight**: No browser launch overhead
- **Same Interface**: Uses same MMID injection as Playwright
- **Live Debugging**: Can manually interact while automation runs

**When to use:**
- Want to reuse logged-in sessions
- Manual + automated workflow
- Debugging automation issues

**Setup:**
```bash
# Start Chrome with debug port
google-chrome --remote-debugging-port=9222

# Or on macOS
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
```

## Usage Examples

### Basic Auto-Detection

```python
from browser_backend import create_backend

async def automate():
    # Auto-selects CDP if Chrome running, else Playwright
    backend = await create_backend('auto', headless=False)

    try:
        await backend.navigate('https://example.com')
        snapshot = await backend.snapshot()

        # Find and click button
        buttons = snapshot.get_by_role('button', text='Submit')
        if buttons:
            result = await backend.click(buttons[0].mmid)
            print(f"Clicked: {result.success}")
    finally:
        await backend.disconnect()
```

### Explicit Backend Choice

```python
# Force Playwright
backend = await create_backend('playwright', headless=True)

# Force CDP (existing Chrome session)
backend = await create_backend('cdp', cdp_url='http://localhost:9222')
```

### Context Manager (Auto Cleanup)

```python
async with await create_backend('auto') as backend:
    if backend:
        await backend.navigate('https://github.com')
        snapshot = await backend.snapshot()
        # ... automation code
    # Automatically disconnects
```

### Reusing Login Sessions (CDP)

```python
# 1. Start Chrome with debug port
# 2. Manually log into sites you need
# 3. Run automation - it reuses your logins!

backend = await create_backend('cdp')
if backend:
    await backend.navigate('https://twitter.com/home')
    # Already logged in from manual session!
```

### Migration from Direct Playwright

**Before (tightly coupled):**
```python
from playwright_direct import DirectPlaywright

pw = DirectPlaywright()
await pw.launch()
await pw.navigate('https://example.com')
result = await pw.browser_snapshot()
elements = result['elements']
```

**After (backend abstraction):**
```python
from browser_backend import create_backend

backend = await create_backend('auto')  # or 'playwright'
await backend.navigate('https://example.com')
snapshot = await backend.snapshot()
elements = snapshot.elements  # List[ElementRef]
```

**Benefits:**
- Can switch to CDP without code changes
- Easier testing (mock the backend)
- Clearer separation of concerns

## Integration with Existing Code

### SimpleAgent Integration

```python
# In simple_agent.py or similar
from browser_backend import create_backend

class SimpleAgent:
    async def initialize(self):
        # Use auto-detection
        self.backend = await create_backend('auto', headless=False)
        if not self.backend:
            raise RuntimeError("Failed to create browser backend")

    async def execute_task(self, instruction: str):
        # Navigate
        await self.backend.navigate(url)

        # Get page state
        snapshot = await self.backend.snapshot()

        # AI decides what to click based on snapshot.elements
        target = self._ai_choose_element(snapshot.elements, instruction)

        # Execute action
        result = await self.backend.click(target.mmid)

        return result
```

### EnhancedBrain Integration

```python
# Can wrap backend in brain's existing interface
class BrainWithBackend:
    def __init__(self, backend_type='auto'):
        self.backend_type = backend_type
        self.backend = None

    async def start(self):
        self.backend = await create_backend(self.backend_type)
        return self.backend is not None

    async def run_action(self, action_dict):
        if action_dict['type'] == 'click':
            return await self.backend.click(action_dict['ref'])
        elif action_dict['type'] == 'type':
            return await self.backend.type(
                action_dict['ref'],
                action_dict['text']
            )
        # ... etc
```

## Backend Auto-Detection Logic

```python
class BackendFactory:
    @staticmethod
    async def create_and_connect(backend_type='auto'):
        if backend_type == 'auto':
            # 1. Try CDP first (best for session reuse)
            cdp = CDPBackend()
            if cdp.cdp_url and await cdp.connect():
                return cdp

            # 2. Fallback to Playwright
            pw = PlaywrightBackend()
            if await pw.connect():
                return pw

            return None

        # Explicit backend type
        backend = create(backend_type)
        if await backend.connect():
            return backend
        return None
```

## MMID System (Shared Across Backends)

Both Playwright and CDP backends use the same MMID injection:

```javascript
// Injected into page on snapshot()
const MMID_ATTR = 'data-mmid';
let mmidCounter = 0;

// Clear old markers
document.querySelectorAll('[data-mmid]').forEach(el => {
    el.removeAttribute('data-mmid');
});

// Mark all interactive elements
document.querySelectorAll('a, button, input, ...').forEach(el => {
    const mmid = 'mm' + (mmidCounter++);
    el.setAttribute('data-mmid', mmid);

    // Collect element data for snapshot
    elements.push({
        mmid,
        ref: `${role}:${text}`,
        role, text, tag, selector,
        rect: el.getBoundingClientRect()
    });
});
```

**Why MMID?**
- Survives dynamic content changes
- More reliable than CSS selectors
- Unique per snapshot
- Works with coordinates fallback

## Performance Comparison

| Feature | PlaywrightBackend | CDPBackend |
|---------|------------------|------------|
| Launch time | ~2-5s (browser start) | <100ms (reuse) |
| Session persistence | New each time | Keeps logins |
| Stealth features | Full (patchright) | Browser-dependent |
| Memory overhead | ~200-500MB | ~50MB (connection only) |
| Best for | Fresh automation | Session reuse |

## Error Handling

All methods return structured results, not exceptions:

```python
# Navigation
nav = await backend.navigate('https://example.com')
if not nav.success:
    print(f"Failed: {nav.error}")
    return

# Interaction
click = await backend.click('mm123')
if not click.success:
    print(f"Click failed: {click.error}")
    print(f"Error type: {click.error_type}")
    # Could retry, fallback, etc.
```

## Future Backends

The abstraction makes it easy to add new backends:

- **Selenium Backend**: For WebDriver compatibility
- **Puppeteer Backend**: For Node.js interop
- **BrowserStack/Sauce**: For cloud testing
- **Record/Replay**: For debugging/testing

Just implement the `BrowserBackend` interface!

## Testing

Mock the backend for unit tests:

```python
class MockBackend(BrowserBackend):
    async def connect(self): return True
    async def navigate(self, url):
        return NavigationResult(success=True, url=url)
    async def snapshot(self):
        return SnapshotResult(
            url='mock',
            title='Mock Page',
            elements=[
                ElementRef(mmid='mm0', ref='button:Test', ...)
            ]
        )
    # ... etc

# Use in tests
async def test_agent():
    agent = SimpleAgent(backend=MockBackend())
    result = await agent.execute_task("click submit")
    assert result.success
```

## Migration Path

### Phase 1: Dual Support (Current)
- Keep `playwright_direct.py` as-is
- `PlaywrightBackend` wraps it
- New code can use backend abstraction
- Old code keeps working

### Phase 2: Gradual Migration
- Update `SimpleAgent` to use backend
- Update workflows to use backend
- Keep `playwright_direct.py` for compatibility

### Phase 3: Full Abstraction
- All code uses `BrowserBackend` interface
- `playwright_direct.py` becomes implementation detail
- Easy to add/swap backends

## Files

| File | Purpose |
|------|---------|
| `browser_backend.py` | Core abstraction (ABC, implementations, factory) |
| `browser_backend_example.py` | Usage examples |
| `BROWSER_BACKEND_README.md` | This documentation |

## See Also

- `playwright_direct.py` - Existing Playwright implementation
- `a11y_browser.py` - Accessibility-first browser automation
- `simple_agent.py` - High-level agent that could use backends
