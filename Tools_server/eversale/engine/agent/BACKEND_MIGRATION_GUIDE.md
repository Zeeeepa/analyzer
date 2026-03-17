# Browser Backend Migration Guide

## Quick Start - Use It Now

No migration needed to start using the backend abstraction:

```python
# New code - use the abstraction
from browser_backend import create_backend

async def my_new_automation():
    backend = await create_backend('auto')
    if backend:
        await backend.navigate('https://example.com')
        snapshot = await backend.snapshot()
        # Use snapshot.elements for automation
        await backend.disconnect()
```

**Old code keeps working unchanged!**

## Migration Benefits

| Before | After |
|--------|-------|
| Tightly coupled to Playwright | Can swap backends |
| No session reuse | CDP reuses Chrome logins |
| Hard to test | Easy mocking |
| Playwright-specific code | Clean interface |

## Gradual Migration Path

### Step 1: New Code Uses Backend

**Before:**
```python
from playwright_direct import DirectPlaywright

async def new_feature():
    pw = DirectPlaywright()
    await pw.launch()
    await pw.navigate('https://example.com')
    result = await pw.browser_snapshot()
    elements = result['elements']
```

**After:**
```python
from browser_backend import create_backend

async def new_feature():
    backend = await create_backend('auto')
    await backend.navigate('https://example.com')
    snapshot = await backend.snapshot()
    elements = snapshot.elements  # Typed ElementRef objects
```

**Benefits:**
- Same functionality
- Cleaner interface
- Can use CDP for session reuse
- Easier testing

### Step 2: Wrap Existing Classes

**SimpleAgent - Before:**
```python
class SimpleAgent:
    def __init__(self):
        from playwright_direct import DirectPlaywright
        self.pw = DirectPlaywright()
        self.page = None

    async def start(self):
        await self.pw.launch()
        self.page = self.pw.page

    async def execute(self, task):
        await self.pw.navigate(url)
        snapshot_result = await self.pw.browser_snapshot()
        # ... work with snapshot_result dict
```

**SimpleAgent - After:**
```python
class SimpleAgent:
    def __init__(self, backend_type='auto'):
        self.backend_type = backend_type
        self.backend = None

    async def start(self):
        from browser_backend import create_backend
        self.backend = await create_backend(self.backend_type)
        if not self.backend:
            raise RuntimeError("Failed to create browser backend")

    async def execute(self, task):
        await self.backend.navigate(url)
        snapshot = await self.backend.snapshot()
        # ... work with snapshot (SnapshotResult object)
```

**Backwards Compatibility:**
```python
# Old code still works
agent = SimpleAgent()  # Uses auto-detection
await agent.start()

# New flexibility
agent_cdp = SimpleAgent(backend_type='cdp')  # Reuse Chrome session
agent_pw = SimpleAgent(backend_type='playwright')  # Isolated browser
```

### Step 3: Update Internal Methods

**Before:**
```python
async def click_element(self, element_dict):
    mmid = element_dict['mmid']
    result = await self.pw.click_by_mmid(mmid)
    return result.get('success', False)
```

**After:**
```python
async def click_element(self, element: ElementRef):
    result = await self.backend.click(element.mmid)
    return result.success  # Typed boolean
```

**Benefits:**
- Type safety (ElementRef, InteractionResult)
- Consistent error handling
- Backend-agnostic

### Step 4: Enhance with Backend Selection

```python
class EnhancedAgent:
    def __init__(self, prefer_session_reuse=True):
        # Auto-select best backend
        self.backend_type = 'auto' if prefer_session_reuse else 'playwright'

    async def start(self):
        self.backend = await create_backend(self.backend_type)
        if isinstance(self.backend, CDPBackend):
            logger.info("Reusing existing Chrome session")
        else:
            logger.info("Starting fresh Playwright browser")
```

## Specific Integration Examples

### agentic_browser.py Integration

**Current:**
```python
class AgenticBrowser:
    def __init__(self):
        from playwright_direct import DirectPlaywright
        self.browser = DirectPlaywright()

    async def start(self):
        await self.browser.launch()
```

**Enhanced:**
```python
class AgenticBrowser:
    def __init__(self, backend_type='auto'):
        from browser_backend import create_backend
        self.backend_type = backend_type
        self.backend = None

    async def start(self):
        self.backend = await create_backend(self.backend_type)

    async def navigate(self, url):
        return await self.backend.navigate(url)

    async def get_page_state(self):
        return await self.backend.snapshot()

    async def perform_action(self, action_type, ref, **kwargs):
        if action_type == 'click':
            return await self.backend.click(ref)
        elif action_type == 'type':
            return await self.backend.type(ref, kwargs.get('text', ''))
```

### simple_agent.py Integration

**Current:**
```python
async def run_task(task: str):
    from playwright_direct import DirectPlaywright
    pw = DirectPlaywright()
    await pw.launch()

    # AI loop
    for step in range(max_steps):
        snapshot = await pw.browser_snapshot()
        action = await ai_decide(task, snapshot)
        await pw.click_by_mmid(action['mmid'])

    await pw.close()
```

**Enhanced:**
```python
async def run_task(task: str, backend_type='auto'):
    from browser_backend import create_backend

    async with await create_backend(backend_type) as backend:
        if not backend:
            return {"error": "Failed to create backend"}

        # AI loop
        for step in range(max_steps):
            snapshot = await backend.snapshot()
            action = await ai_decide(task, snapshot)
            result = await backend.click(action['mmid'])

            if not result.success:
                logger.error(f"Action failed: {result.error}")
                break

        return {"success": True}
```

### brain_enhanced_v2.py Integration

**Wrapper Adapter:**
```python
class BrowserBackendAdapter:
    """Adapts BrowserBackend to EnhancedBrain's expected interface."""

    def __init__(self, backend: BrowserBackend):
        self.backend = backend

    async def navigate(self, url):
        nav_result = await self.backend.navigate(url)
        # Convert to brain's expected format
        return {
            'success': nav_result.success,
            'url': nav_result.url,
            'error': nav_result.error
        }

    async def snapshot(self):
        snap = await self.backend.snapshot()
        # Convert SnapshotResult to dict for brain
        return snap.to_dict()

    async def click(self, ref):
        result = await self.backend.click(ref)
        return result.to_dict()
```

**Usage in EnhancedBrain:**
```python
class EnhancedBrain:
    def __init__(self, backend_type='auto'):
        self.backend_type = backend_type

    async def initialize(self):
        from browser_backend import create_backend
        backend = await create_backend(self.backend_type)
        self.browser = BrowserBackendAdapter(backend)

    async def execute_plan(self, plan):
        await self.browser.navigate(plan['start_url'])
        snapshot = await self.browser.snapshot()
        # ... rest of logic unchanged
```

## Testing Improvements

### Before - Hard to Test

```python
# Hard to test without real browser
async def test_agent():
    agent = SimpleAgent()
    await agent.start()  # Launches real browser
    result = await agent.execute('test task')
    await agent.stop()
    assert result.success
```

### After - Easy Mocking

```python
from browser_backend import BrowserBackend, SnapshotResult, InteractionResult

class MockBackend(BrowserBackend):
    async def connect(self): return True
    async def disconnect(self): pass
    async def navigate(self, url):
        return NavigationResult(success=True, url=url)
    async def snapshot(self):
        return SnapshotResult(
            url='mock', title='Mock Page',
            elements=[ElementRef(mmid='mm0', ref='button:Test', ...)]
        )
    async def click(self, ref):
        return InteractionResult(success=True)
    # ... etc

# Test without real browser
async def test_agent():
    agent = SimpleAgent()
    agent.backend = MockBackend()
    await agent.backend.connect()

    result = await agent.execute('test task')
    assert result.success  # Fast, no browser needed!
```

## CDP Session Reuse Pattern

### Workflow

```bash
# Terminal 1: Start Chrome with debug port
google-chrome --remote-debugging-port=9222

# Manually log into sites you need (Gmail, Twitter, etc.)
# Leave Chrome running
```

```python
# Terminal 2: Run automation
from browser_backend import create_backend

async def daily_automation():
    # Connects to existing Chrome - keeps all logins!
    backend = await create_backend('cdp')

    # Already logged into Gmail
    await backend.navigate('https://mail.google.com')
    snapshot = await backend.snapshot()

    # Already logged into Twitter
    await backend.navigate('https://twitter.com/home')
    # ... automation using existing session
```

### Agent with CDP Preference

```python
class SessionAwareAgent(SimpleAgent):
    def __init__(self):
        super().__init__(backend_type='auto')

    async def start(self):
        await super().start()

        # Check if we're using CDP
        from browser_backend import CDPBackend
        if isinstance(self.backend, CDPBackend):
            logger.info("Using existing Chrome session - logins preserved")
            self.has_session = True
        else:
            logger.info("Fresh browser - will need to login")
            self.has_session = False

    async def ensure_logged_in(self, site):
        if self.has_session:
            return  # Already logged in via CDP

        # Need to login with fresh browser
        await self.login_flow(site)
```

## Error Handling Improvements

### Before - Exception-Based

```python
try:
    await pw.navigate(url)
except Exception as e:
    logger.error(f"Navigation failed: {e}")
    return
```

### After - Result-Based

```python
nav_result = await backend.navigate(url)
if not nav_result.success:
    logger.error(f"Navigation failed: {nav_result.error}")
    return

# Success path
logger.info(f"Loaded {nav_result.title} in {nav_result.load_time_ms}ms")
```

**Benefits:**
- No exception handling needed
- Richer error context
- Performance metrics included

## Performance Optimization

### Choose Backend Based on Task

```python
async def run_automation(task, needs_login=False):
    # If task needs login, prefer CDP (session reuse)
    backend_type = 'cdp' if needs_login else 'playwright'

    backend = await create_backend(backend_type)
    if not backend and backend_type == 'cdp':
        # CDP failed, fallback to Playwright
        logger.warning("CDP unavailable, using Playwright (will need login)")
        backend = await create_backend('playwright')

    # ... run task
```

### Benchmark Different Backends

```python
import time

async def benchmark_backend(backend_type, url):
    backend = await create_backend(backend_type)
    if not backend:
        return None

    start = time.time()
    await backend.navigate(url)
    snapshot = await backend.snapshot()
    duration = time.time() - start

    await backend.disconnect()

    return {
        'backend': backend_type,
        'duration': duration,
        'elements': len(snapshot.elements)
    }

# Compare
pw_result = await benchmark_backend('playwright', 'https://example.com')
cdp_result = await benchmark_backend('cdp', 'https://example.com')

print(f"Playwright: {pw_result['duration']:.2f}s")
print(f"CDP: {cdp_result['duration']:.2f}s")
```

## Migration Checklist

- [ ] Identify files using `playwright_direct.py`
- [ ] Start using `create_backend()` in new code
- [ ] Add backend parameter to agent classes
- [ ] Create adapter if needed for legacy interfaces
- [ ] Update tests to use mock backends
- [ ] Document which code uses which backend
- [ ] Test CDP session reuse workflow
- [ ] Add backend selection to CLI flags (optional)

## Common Patterns

### Pattern: Fallback Chain

```python
async def get_backend_with_fallbacks():
    # Try CDP first (fastest, preserves sessions)
    backend = await create_backend('cdp')
    if backend:
        return backend

    # Fallback to Playwright
    backend = await create_backend('playwright')
    if backend:
        return backend

    raise RuntimeError("No browser backend available")
```

### Pattern: Backend Pool

```python
class BackendPool:
    def __init__(self, size=3, backend_type='playwright'):
        self.size = size
        self.backend_type = backend_type
        self.pool = []

    async def initialize(self):
        for _ in range(self.size):
            backend = await create_backend(self.backend_type)
            if backend:
                self.pool.append(backend)

    async def get(self):
        if not self.pool:
            return await create_backend(self.backend_type)
        return self.pool.pop()

    async def release(self, backend):
        self.pool.append(backend)
```

### Pattern: Context Manager with Auto-Fallback

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def auto_backend(prefer='cdp'):
    backend = await create_backend(prefer)
    if not backend and prefer != 'playwright':
        backend = await create_backend('playwright')

    try:
        yield backend
    finally:
        if backend:
            await backend.disconnect()

# Usage
async with auto_backend(prefer='cdp') as backend:
    if backend:
        await backend.navigate(url)
```

## Summary

**No Breaking Changes Required**

You can adopt the backend abstraction incrementally:

1. **Today**: Use `create_backend()` in new code
2. **This Week**: Add backend params to agent classes
3. **This Month**: Migrate core workflows
4. **Eventually**: Full abstraction (optional)

**Old code keeps working throughout!**

The abstraction is ready to use now while being designed for gradual adoption.
