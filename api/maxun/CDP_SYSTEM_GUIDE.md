# CDP WebSocket System - Complete Guide

## Chrome DevTools Protocol Browser Automation with OpenAI API

This system provides a **WebSocket server** using **Chrome DevTools Protocol (CDP)** to control 6 concurrent browser instances, with **OpenAI-compatible API** format for requests and responses.

---

## 🏗️ Architecture

```
┌─────────────────┐
│  Your Client    │
│  (OpenAI SDK)   │
└────────┬────────┘
         │ OpenAI API format
         │ (WebSocket)
         ▼
┌─────────────────────────────────┐
│   CDP WebSocket Server          │
│   (cdp_websocket_server.py)     │
├─────────────────────────────────┤
│  • Request Parser (OpenAI)      │
│  • Multi-Browser Manager        │
│  • Workflow Executor            │
│  • Response Generator (OpenAI)  │
└────────┬────────────────────────┘
         │ Chrome DevTools Protocol
         │ (WebSocket per browser)
         ▼
┌───────────────────────────────────────┐
│   6 Chrome Instances (Headless)       │
├───────────────────────────────────────┤
│ ┌─────────┬─────────┬─────────┐      │
│ │Discord  │ Slack   │ Teams   │      │
│ │:9222    │ :9223   │ :9224   │      │
│ └─────────┴─────────┴─────────┘      │
│ ┌─────────┬─────────┬─────────┐      │
│ │WhatsApp │Telegram │ Custom  │      │
│ │:9225    │ :9226   │ :9227   │      │
│ └─────────┴─────────┴─────────┘      │
└───────────────────────────────────────┘
```

---

## 📋 Prerequisites

### 1. Install Dependencies

```bash
# Python packages
pip install websockets aiohttp pyyaml

# Chrome/Chromium (headless capable)
# Ubuntu/Debian:
sudo apt-get install chromium-browser

# Mac:
brew install chromium

# Or use Google Chrome
```

### 2. Configure Credentials

```bash
# Copy template
cp config/platforms/credentials.yaml config/platforms/credentials.yaml.backup

# Edit with your ACTUAL credentials
nano config/platforms/credentials.yaml
```

**Example credentials.yaml**:
```yaml
platforms:
  discord:
    username: "yourname@gmail.com"  # ← YOUR ACTUAL EMAIL
    password: "YourSecurePass123"   # ← YOUR ACTUAL PASSWORD
    server_id: "123456789"           # ← YOUR SERVER ID
    channel_id: "987654321"          # ← YOUR CHANNEL ID
  
  slack:
    username: "yourname@company.com"
    password: "YourSlackPassword"
    workspace_id: "T12345678"
    channel_id: "C87654321"
  
  # ... fill in all 6 platforms
```

---

## 🚀 Quick Start

### Step 1: Start the CDP WebSocket Server

```bash
cd maxun

# Start server (will launch 6 Chrome instances)
python3 cdp_websocket_server.py
```

**Expected Output**:
```
2025-11-05 15:00:00 - INFO - Starting CDP WebSocket Server...
2025-11-05 15:00:01 - INFO - Initialized session for discord
2025-11-05 15:00:02 - INFO - Initialized session for slack
2025-11-05 15:00:03 - INFO - Initialized session for teams
2025-11-05 15:00:04 - INFO - Initialized session for whatsapp
2025-11-05 15:00:05 - INFO - Initialized session for telegram
2025-11-05 15:00:06 - INFO - Initialized session for custom
2025-11-05 15:00:07 - INFO - WebSocket server listening on ws://localhost:8765
```

### Step 2: Test All Endpoints

```bash
# In another terminal
python3 test_cdp_client.py
```

**Expected Output**:
```
████████████████████████████████████████████████████████████████████████████████
█  CDP WEBSOCKET SERVER - ALL ENDPOINTS TEST
█  Testing with ACTUAL CREDENTIALS from credentials.yaml
████████████████████████████████████████████████████████████████████████████████

================================================================================
TEST 1: Discord Message Sender
================================================================================
✅ SUCCESS
Response: {
  "id": "chatcmpl-1",
  "object": "chat.completion",
  "created": 1730822400,
  "model": "maxun-robot-discord",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "Message sent successfully to discord"
    },
    "finish_reason": "stop"
  }],
  "metadata": {
    "platform": "discord",
    "execution_time_ms": 2500,
    "authenticated": true
  }
}

... (tests for all 6 platforms)

================================================================================
TEST SUMMARY
================================================================================
Discord         ✅ PASS
Slack           ✅ PASS
Teams           ✅ PASS
Whatsapp        ✅ PASS
Telegram        ✅ PASS
Custom          ✅ PASS
================================================================================
TOTAL: 6/6 tests passed (100.0%)
================================================================================
```

---

## 💻 Usage with OpenAI SDK

### Python Client

```python
import websockets
import asyncio
import json

async def send_message_discord():
    """Send message via CDP WebSocket with OpenAI format"""
    
    uri = "ws://localhost:8765"
    
    request = {
        "model": "maxun-robot-discord",
        "messages": [
            {"role": "system", "content": "Platform: discord"},
            {"role": "user", "content": "Hello from automation!"}
        ],
        "metadata": {
            "username": "your@email.com",
            "password": "your_password",
            "recipient": "#general"
        }
    }
    
    async with websockets.connect(uri) as websocket:
        # Send request
        await websocket.send(json.dumps(request))
        
        # Get response
        response = await websocket.recv()
        data = json.loads(response)
        
        print(f"Message sent! ID: {data['id']}")
        print(f"Content: {data['choices'][0]['message']['content']}")

asyncio.run(send_message_discord())
```

### Using OpenAI Python SDK (with adapter)

```python
# First, start a local HTTP adapter (converts HTTP to WebSocket)
# Then use OpenAI SDK normally:

from openai import OpenAI

client = OpenAI(
    api_key="dummy",  # Not used, but required by SDK
    base_url="http://localhost:8080/v1"  # HTTP adapter endpoint
)

response = client.chat.completions.create(
    model="maxun-robot-discord",
    messages=[
        {"role": "system", "content": "Platform: discord"},
        {"role": "user", "content": "Hello!"}
    ],
    metadata={
        "username": "your@email.com",
        "password": "your_password"
    }
)

print(response.choices[0].message.content)
```

---

## 📝 YAML Dataflow Configuration

### Platform Configuration Structure

```yaml
# config/platforms/{platform}.yaml

platform:
  name: discord
  base_url: https://discord.com
  requires_auth: true

workflows:
  login:
    steps:
      - type: navigate
        url: https://discord.com/login
      
      - type: type
        selector: "input[name='email']"
        field: username
      
      - type: type
        selector: "input[name='password']"
        field: password
      
      - type: click
        selector: "button[type='submit']"
        wait: 3
  
  send_message:
    steps:
      - type: navigate
        url: "https://discord.com/channels/{{server_id}}/{{channel_id}}"
      
      - type: click
        selector: "div[role='textbox']"
      
      - type: type
        selector: "div[role='textbox']"
        field: message
      
      - type: press_key
        key: Enter
  
  retrieve_messages:
    steps:
      - type: navigate
        url: "https://discord.com/channels/{{server_id}}/{{channel_id}}"
      
      - type: scroll
        direction: up
        amount: 500
      
      - type: extract
        selector: "[class*='message']"
        fields:
          text: "[class*='messageContent']"
          author: "[class*='username']"
          timestamp: "time"

selectors:
  login:
    email_input: "input[name='email']"
    password_input: "input[name='password']"
  chat:
    message_input: "div[role='textbox']"
```

### Supported Step Types

| Type | Description | Parameters |
|------|-------------|------------|
| `navigate` | Navigate to URL | `url` |
| `type` | Type text into element | `selector`, `field` or `text` |
| `click` | Click element | `selector`, `wait` (optional) |
| `press_key` | Press keyboard key | `key` |
| `wait` | Wait for duration | `duration` (ms) |
| `scroll` | Scroll page | `direction`, `amount` |
| `extract` | Extract data | `selector`, `fields` |

### Variable Substitution

Variables in workflows can be substituted at runtime:

```yaml
- type: navigate
  url: "https://discord.com/channels/{{server_id}}/{{channel_id}}"
```

Resolved from:
- Request metadata
- Credentials file
- Environment variables

---

## 🔧 Customizing for Your Platform

### Add a New Platform

1. **Create YAML config**: `config/platforms/myplatform.yaml`

```yaml
platform:
  name: myplatform
  base_url: https://myplatform.com
  requires_auth: true

workflows:
  login:
    steps:
      - type: navigate
        url: https://myplatform.com/login
      - type: type
        selector: "#email"
        field: username
      - type: type
        selector: "#password"
        field: password
      - type: click
        selector: "button[type='submit']"
  
  send_message:
    steps:
      - type: navigate
        url: "https://myplatform.com/chat/{{channel_id}}"
      - type: type
        selector: ".message-input"
        field: message
      - type: click
        selector: ".send-button"
```

2. **Add credentials**: `config/platforms/credentials.yaml`

```yaml
platforms:
  myplatform:
    username: "your_email@example.com"
    password: "your_password"
    channel_id: "12345"
```

3. **Update server**: Modify `cdp_websocket_server.py`

```python
platforms = ["discord", "slack", "teams", "whatsapp", "telegram", "myplatform"]
```

4. **Restart server and test**

---

## 🔐 Security Best Practices

### 1. Never Commit Credentials

```bash
# Add to .gitignore
echo "config/platforms/credentials.yaml" >> .gitignore
```

### 2. Use Environment Variables (Alternative)

```bash
export DISCORD_USERNAME="your@email.com"
export DISCORD_PASSWORD="your_password"
```

Then in code:
```python
import os
username = os.getenv("DISCORD_USERNAME")
```

### 3. Encrypt Credentials File

```bash
# Encrypt
gpg --symmetric --cipher-algo AES256 credentials.yaml

# Decrypt
gpg --decrypt credentials.yaml.gpg > credentials.yaml
```

### 4. Use Vault for Production

```python
import hvac

vault_client = hvac.Client(url='http://vault:8200')
secret = vault_client.secrets.kv.v2.read_secret_version(path='credentials')
credentials = secret['data']['data']
```

---

## 🐛 Troubleshooting

### Issue: Chrome won't start

**Solution**:
```bash
# Check if Chrome is installed
which google-chrome chromium-browser chromium

# Kill existing Chrome processes
pkill -9 chrome

# Try with visible browser (remove headless flag)
# Edit cdp_websocket_server.py:
# Remove "--headless=new" from cmd list
```

### Issue: CDP connection fails

**Solution**:
```bash
# Check if port is already in use
lsof -i :9222

# Use different port range
# Edit cdp_websocket_server.py:
base_port = 10000  # Instead of 9222
```

### Issue: Login fails

**Solution**:
1. Check credentials are correct
2. Check for CAPTCHA (may require manual intervention)
3. Check for 2FA (add 2FA token to workflow)
4. Update selectors if platform UI changed

### Issue: Selectors not found

**Solution**:
```bash
# Test selectors manually with Chrome DevTools:
# 1. Open target platform
# 2. Press F12
# 3. Console: document.querySelector("your selector")
# 4. Update YAML config with correct selectors
```

---

## 📊 Monitoring & Logging

### View Logs

```bash
# Real-time logs
tail -f cdp_server.log

# Filter by platform
grep "discord" cdp_server.log

# Filter by level
grep "ERROR" cdp_server.log
```

### Enable Debug Logging

```python
# In cdp_websocket_server.py
logging.basicConfig(level=logging.DEBUG)
```

---

## 🚀 Production Deployment

### 1. Use Supervisor/Systemd

```ini
# /etc/supervisor/conf.d/cdp-server.conf
[program:cdp-server]
command=/usr/bin/python3 /path/to/cdp_websocket_server.py
directory=/path/to/maxun
user=maxun
autostart=true
autorestart=true
stderr_logfile=/var/log/cdp-server.err.log
stdout_logfile=/var/log/cdp-server.out.log
```

### 2. Add Health Checks

```python
# Add to server
async def health_check(websocket, path):
    if path == "/health":
        await websocket.send(json.dumps({"status": "healthy"}))
```

### 3. Add Metrics

```python
from prometheus_client import Counter, Histogram

message_count = Counter('messages_sent_total', 'Total messages sent')
execution_time = Histogram('execution_duration_seconds', 'Execution time')
```

---

## 📚 API Reference

### OpenAI Request Format

```json
{
  "model": "maxun-robot-{platform}",
  "messages": [
    {"role": "system", "content": "Platform: {platform}"},
    {"role": "user", "content": "{your_message}"}
  ],
  "stream": false,
  "metadata": {
    "username": "your@email.com",
    "password": "your_password",
    "recipient": "#channel",
    "server_id": "123",
    "channel_id": "456"
  }
}
```

### OpenAI Response Format

```json
{
  "id": "chatcmpl-123",
  "object": "chat.completion",
  "created": 1730822400,
  "model": "maxun-robot-discord",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "Message sent successfully"
    },
    "finish_reason": "stop"
  }],
  "metadata": {
    "platform": "discord",
    "execution_time_ms": 2500,
    "authenticated": true,
    "screenshots": ["base64..."]
  }
}
```

---

## 🎯 Next Steps

1. **Fill in your credentials** in `config/platforms/credentials.yaml`
2. **Start the server**: `python3 cdp_websocket_server.py`
3. **Run tests**: `python3 test_cdp_client.py`
4. **Integrate with your application** using OpenAI SDK format
5. **Monitor and scale** based on your needs

---

## 📞 Support

- **Issues**: Open GitHub issue
- **Documentation**: See `docs/`
- **Examples**: See `examples/`

---

**Ready to automate!** 🚀

