# CDP Browser Connector

Connect to existing Chrome browser sessions via Chrome DevTools Protocol (CDP), preserving all login sessions, cookies, and localStorage.

## Why Use CDP Connector?

**Problem**: Fresh Playwright instances lose all login sessions, triggering CAPTCHAs and requiring re-authentication.

**Solution**: Connect to user's existing Chrome browser where they're already logged in.

### Benefits

1. **Preserve login sessions** - All existing logins intact (Gmail, LinkedIn, Facebook, etc.)
2. **No CAPTCHA challenges** - Real browser fingerprint, not a fresh automation profile
3. **No bot detection** - Genuine user profile with real browsing history
4. **Faster startup** - Browser already running, instant connection
5. **User extensions** - All installed extensions work (ad blockers, password managers, etc.)
6. **Familiar environment** - Users see automation in their actual browser

## Quick Start

### 1. Launch Chrome with debugging enabled

**Windows:**
```cmd
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
```

**macOS:**
```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9222 &
```

**Linux:**
```bash
google-chrome --remote-debugging-port=9222 &
```

### 2. Connect from Python

```python
from agent.cdp_browser_connector import connect_to_existing_chrome

# Connect to existing Chrome
browser = await connect_to_existing_chrome(port=9222)

# Navigate (already logged in to all sites!)
await browser.goto("https://mail.google.com")

# Get interactive elements
snapshot = await browser.browser_snapshot()
print(f"Found {snapshot['count']} elements")

# Click button
await browser.click("mm0")  # Click first element

# Type into input
await browser.type("mm1", "Search query")

# Run JavaScript
result = await browser.run_code("document.title")
print(result['result'])
```

## Usage Patterns

### Pattern 1: Simple connection

```python
from agent.cdp_browser_connector import connect_to_existing_chrome

browser = await connect_to_existing_chrome()
await browser.goto("https://example.com")
```

### Pattern 2: Auto-discover Chrome

```python
from agent.cdp_browser_connector import CDPBrowserConnector

# Try common ports: 9222, 9223, 9224, 9229
connector = await CDPBrowserConnector.auto_discover()
if connector:
    browser = await connector.connect()
```

### Pattern 3: Auto-launch if not running

```python
from agent.cdp_browser_connector import auto_connect_chrome

# Launches Chrome automatically if not running
browser = await auto_connect_chrome(auto_launch=True)
```

### Pattern 4: Custom port and profile

```python
from agent.cdp_browser_connector import CDPBrowserConnector

connector = CDPBrowserConnector(
    port=9223,
    user_data_dir="/path/to/chrome/profile"
)
browser = await connector.connect()
```

## API Reference

### CDPBrowserConnector

Main connector class for managing CDP connections.

```python
connector = CDPBrowserConnector(
    port=9222,              # Chrome debugging port
    host="localhost",       # Chrome debugging host
    auto_launch=False,      # Auto-launch Chrome if not running
    user_data_dir=None      # Optional Chrome profile directory
)
```

#### Methods

- `connect()` - Connect to Chrome, returns CDPBrowserInstance
- `disconnect()` - Disconnect from Chrome (doesn't close it)
- `auto_discover(ports)` - Static method to find Chrome on common ports
- `get_launch_instructions()` - Static method for platform-specific instructions

### CDPBrowserInstance

Browser wrapper implementing PlaywrightAgent-compatible interface.

#### Navigation
```python
await browser.goto(url, wait_until="domcontentloaded")
```

#### Snapshots
```python
# Simple snapshot
snapshot = await browser.snapshot()

# Interactive elements with mmid references
snapshot = await browser.browser_snapshot()
# Returns: {"elements": [...], "count": 10, "url": "...", "title": "..."}
```

#### Interaction
```python
# Click by mmid or selector
await browser.click("mm0")           # Click by mmid
await browser.click("#submit-btn")   # Click by CSS selector

# Type text
await browser.type("mm1", "text", clear=True)

# Execute JavaScript
result = await browser.run_code("return document.title")
print(result['result'])
```

#### Cleanup
```python
await browser.close()  # Disconnect (doesn't close Chrome)
```

### Convenience Functions

```python
# Quick connect to default port
browser = await connect_to_existing_chrome(port=9222)

# Auto-discover and connect
browser = await auto_connect_chrome(auto_launch=True)
```

## Element References (mmid)

The connector uses the same mmid (marker ID) system as Playwright MCP:

```python
# Get snapshot with mmid markers
snapshot = await browser.browser_snapshot()

# Each element has:
# - mmid: Unique marker (e.g., "mm0", "mm1")
# - role: Element role (button, link, input)
# - text: Visible text content
# - selector: CSS selector fallback
# - rect: Bounding box {x, y, width, height}

# Click by mmid
await browser.click("mm0")

# Or iterate elements
for el in snapshot['elements']:
    if 'submit' in el['text'].lower():
        await browser.click(el['mmid'])
        break
```

## Integration with PlaywrightAgent

The CDP connector implements the same interface as PlaywrightAgent, making it a drop-in replacement:

```python
# Standard PlaywrightAgent
from agent.playwright_direct import PlaywrightAgent
agent = PlaywrightAgent(headless=False)
await agent.connect()

# CDP Browser Connector (preserves logins!)
from agent.cdp_browser_connector import auto_connect_chrome
agent = await auto_connect_chrome(auto_launch=True)

# Both support the same methods:
await agent.goto("https://example.com")
await agent.browser_snapshot()
await agent.click("mm0")
await agent.type("mm1", "text")
```

## Common Use Cases

### Use Case 1: Gmail automation with existing login

```python
browser = await connect_to_existing_chrome()

# Navigate to Gmail (already logged in!)
await browser.goto("https://mail.google.com/mail/u/0/#inbox")

# Get emails
snapshot = await browser.browser_snapshot()
emails = [el for el in snapshot['elements'] if el['role'] == 'link']
```

### Use Case 2: LinkedIn scraping with authenticated session

```python
browser = await connect_to_existing_chrome()

# Navigate to LinkedIn (already logged in!)
await browser.goto("https://www.linkedin.com/feed/")

# Search companies
search_box = snapshot['elements'][0]  # Assuming first input
await browser.type(search_box['mmid'], "AI companies")
```

### Use Case 3: Facebook Ads Library research

```python
browser = await connect_to_existing_chrome()

# Facebook Ads Library (no login wall!)
await browser.goto("https://www.facebook.com/ads/library/")

# Search for ads
snapshot = await browser.browser_snapshot()
search_inputs = [el for el in snapshot['elements'] if el['role'] == 'input']
await browser.type(search_inputs[0]['mmid'], "fitness")
```

## Troubleshooting

### Chrome not connecting

```python
# Check if Chrome is running
connector = CDPBrowserConnector(port=9222)
is_running = await connector._is_chrome_running()
print(f"Chrome running: {is_running}")

# If not, print launch instructions
if not is_running:
    print(CDPBrowserConnector.get_launch_instructions())
```

### Multiple Chrome instances

If you have multiple Chrome instances, use different ports:

```bash
# Instance 1
chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-profile-1

# Instance 2
chrome --remote-debugging-port=9223 --user-data-dir=/tmp/chrome-profile-2
```

### Element not found

```python
# Refresh snapshot if elements change
snapshot = await browser.browser_snapshot()

# Check if mmid exists
if 'mm0' in snapshot['elements']:
    await browser.click('mm0')
else:
    # Fallback to CSS selector
    await browser.click('#submit-button')
```

### Reconnection after Chrome restart

```python
# The connector doesn't auto-reconnect
# You need to create a new connection

try:
    await browser.goto("https://example.com")
except Exception as e:
    # Chrome might have restarted
    connector = CDPBrowserConnector(port=9222)
    browser = await connector.connect()
    await browser.goto("https://example.com")
```

## Advanced Usage

### Custom reconnection logic

```python
class ReconnectingCDPBrowser:
    def __init__(self, port=9222):
        self.port = port
        self.connector = None
        self.browser = None

    async def ensure_connected(self):
        if not self.browser:
            self.connector = CDPBrowserConnector(port=self.port)
            self.browser = await self.connector.connect()
        return self.browser

    async def goto(self, url):
        browser = await self.ensure_connected()
        try:
            return await browser.goto(url)
        except Exception as e:
            # Reconnect and retry
            self.browser = None
            browser = await self.ensure_connected()
            return await browser.goto(url)
```

### Monitoring console logs

```python
# Use ConsoleMonitor from browser_mcp_features.py
from agent.browser_mcp_features import ConsoleMonitor

browser = await connect_to_existing_chrome()
console = ConsoleMonitor()
await console.attach(browser.page)

# Navigate and interact
await browser.goto("https://example.com")

# Get console logs
logs = console.get_logs()
errors = console.get_errors()
```

### Network capture

```python
# Use NetworkCapture from browser_mcp_features.py
from agent.browser_mcp_features import NetworkCapture

browser = await connect_to_existing_chrome()
network = NetworkCapture()
await network.attach(browser.page)

# Navigate
await browser.goto("https://example.com")

# Get network requests
api_calls = network.get_api_calls()
for call in api_calls:
    print(f"{call.method} {call.url}: {call.status}")
```

## Security Considerations

1. **Port exposure**: CDP port (9222) allows full browser control. Only run on localhost.
2. **User data**: Connecting to user's Chrome means access to all cookies and sessions.
3. **Automation detection**: Some sites detect CDP connection. Use stealth mode if needed.
4. **Profile isolation**: Consider using separate Chrome profiles for automation vs. personal use.

## Comparison with Standard Playwright

| Feature | Standard Playwright | CDP Connector |
|---------|-------------------|---------------|
| Login sessions | Lost on restart | Preserved |
| CAPTCHA challenges | Common | Rare (real fingerprint) |
| Bot detection | High risk | Lower risk |
| Startup time | 2-5 seconds | Instant (browser running) |
| Extensions | Not supported | Fully supported |
| User profile | Fresh/isolated | User's actual profile |
| Setup complexity | Simple (just code) | Medium (launch Chrome first) |

## Examples

See `/mnt/c/ev29/cli/examples/cdp_connector_example.py` for full working examples:

```bash
# Run example 1: Basic connection
python examples/cdp_connector_example.py 1

# Run example 2: Auto-discovery
python examples/cdp_connector_example.py 2

# Run example 3: Auto-launch
python examples/cdp_connector_example.py 3

# Run example 4: Page interaction
python examples/cdp_connector_example.py 4

# Run example 5: Preserve login demo
python examples/cdp_connector_example.py 5
```

## Testing

Test the connector directly:

```bash
# Make sure Chrome is running with CDP enabled first
cd /mnt/c/ev29/cli/engine/agent
python cdp_browser_connector.py
```

## Related Modules

- `browser_mcp_features.py` - Console monitoring, network capture, Lighthouse audits
- `playwright_direct.py` - Standard Playwright automation
- `a11y_browser.py` - Accessibility-first browser automation

## License

Part of the Eversale Desktop Agent CLI.
