# Browser Automation for Chat Interfaces

This guide demonstrates how to use Maxun API for browser automation to interact with web-based chat interfaces, including authentication, sending messages, and retrieving responses.

## Table of Contents
- [Quick Start](#quick-start)
- [Deployment](#deployment)
- [API Authentication](#api-authentication)
- [Creating Chat Automation Robots](#creating-chat-automation-robots)
- [Workflow Examples](#workflow-examples)
- [Best Practices](#best-practices)

## Quick Start

### Prerequisites
- Docker and Docker Compose installed
- Node.js 16+ (for local development)
- Basic understanding of web automation concepts

### 1. Deploy Maxun

```bash
# Clone the repository
git clone https://github.com/getmaxun/maxun
cd maxun

# Copy environment example
cp ENVEXAMPLE .env

# Edit .env file with your configuration
# Generate secure secrets:
openssl rand -hex 32  # for JWT_SECRET
openssl rand -hex 32  # for ENCRYPTION_KEY

# Start services
docker-compose up -d

# Verify deployment
curl http://localhost:8080/health
```

Access the UI at http://localhost:5173 and API at http://localhost:8080

### 2. Get API Key

1. Open http://localhost:5173
2. Create an account
3. Navigate to Settings → API Keys
4. Generate a new API key
5. Save it securely (format: `your-api-key-here`)

## Deployment

### Docker Compose (Recommended)

The `docker-compose.yml` includes all required services:
- **postgres**: Database for storing robots and runs
- **minio**: Object storage for screenshots
- **backend**: Maxun API server
- **frontend**: Web interface

```yaml
# Key environment variables in .env
BACKEND_PORT=8080
FRONTEND_PORT=5173
BACKEND_URL=http://localhost:8080
PUBLIC_URL=http://localhost:5173
DB_NAME=maxun
DB_USER=postgres
DB_PASSWORD=your_secure_password
MINIO_ACCESS_KEY=your_minio_key
MINIO_SECRET_KEY=your_minio_secret
```

### Production Deployment

For production, update URLs in `.env`:
```bash
BACKEND_URL=https://api.yourdomain.com
PUBLIC_URL=https://app.yourdomain.com
VITE_BACKEND_URL=https://api.yourdomain.com
VITE_PUBLIC_URL=https://app.yourdomain.com
```

Consider using:
- Reverse proxy (nginx/traefik)
- SSL certificates
- External database for persistence
- Backup strategy for PostgreSQL and MinIO

## API Authentication

All API requests require authentication via API key in the `x-api-key` header:

```bash
curl -H "x-api-key: YOUR_API_KEY" \
     http://localhost:8080/api/robots
```

## Creating Chat Automation Robots

### Method 1: Using the Web Interface (Recommended for First Robot)

1. **Open the Web UI**: Navigate to http://localhost:5173
2. **Create New Robot**: Click "New Robot"
3. **Record Actions**:
   - Navigate to the chat interface URL
   - Enter login credentials if required
   - Perform actions: type message, click send, etc.
   - Capture the response text
4. **Save Robot**: Give it a name like "slack-message-sender"
5. **Get Robot ID**: Copy from the URL or API

### Method 2: Using the API (Programmatic)

Robots are created by recording browser interactions. The workflow is stored as JSON:

```javascript
// Example robot workflow structure
{
  "recording_meta": {
    "id": "uuid-here",
    "name": "Chat Interface Automation",
    "createdAt": "2024-01-01T00:00:00Z"
  },
  "recording": {
    "workflow": [
      {
        "action": "navigate",
        "where": {
          "url": "https://chat.example.com/login"
        }
      },
      {
        "action": "type",
        "where": {
          "selector": "input[name='username']"
        },
        "what": {
          "value": "${USERNAME}"
        }
      },
      {
        "action": "type",
        "where": {
          "selector": "input[name='password']"
        },
        "what": {
          "value": "${PASSWORD}"
        }
      },
      {
        "action": "click",
        "where": {
          "selector": "button[type='submit']"
        }
      },
      {
        "action": "wait",
        "what": {
          "duration": 2000
        }
      },
      {
        "action": "type",
        "where": {
          "selector": "textarea.message-input"
        },
        "what": {
          "value": "${MESSAGE}"
        }
      },
      {
        "action": "click",
        "where": {
          "selector": "button.send-message"
        }
      },
      {
        "action": "capture_text",
        "where": {
          "selector": ".message-response"
        },
        "what": {
          "label": "response"
        }
      }
    ]
  }
}
```

## Workflow Examples

### Example 1: Basic Chat Message Sender

```python
import requests
import time

API_URL = "http://localhost:8080/api"
API_KEY = "your-api-key-here"
ROBOT_ID = "your-robot-id"

headers = {
    "x-api-key": API_KEY,
    "Content-Type": "application/json"
}

def send_message(username, password, message):
    """Send a message using the chat automation robot"""
    
    # Start robot run
    payload = {
        "parameters": {
            "originUrl": "https://chat.example.com",
            "USERNAME": username,
            "PASSWORD": password,
            "MESSAGE": message
        }
    }
    
    response = requests.post(
        f"{API_URL}/robots/{ROBOT_ID}/runs",
        json=payload,
        headers=headers
    )
    
    if response.status_code != 200:
        raise Exception(f"Failed to start run: {response.text}")
    
    run_data = response.json()
    run_id = run_data.get("runId")
    
    print(f"Started run: {run_id}")
    
    # Poll for completion
    max_attempts = 60
    for attempt in range(max_attempts):
        time.sleep(2)
        
        status_response = requests.get(
            f"{API_URL}/robots/{ROBOT_ID}/runs/{run_id}",
            headers=headers
        )
        
        if status_response.status_code != 200:
            continue
        
        status_data = status_response.json()
        run_status = status_data.get("run", {}).get("status")
        
        print(f"Status: {run_status}")
        
        if run_status == "success":
            # Extract captured response
            interpretation = status_data.get("interpretation", {})
            captured_data = interpretation.get("capturedTexts", {})
            
            return {
                "success": True,
                "response": captured_data.get("response", ""),
                "run_id": run_id
            }
        
        elif run_status == "failed":
            error = status_data.get("error", "Unknown error")
            return {
                "success": False,
                "error": error,
                "run_id": run_id
            }
    
    return {
        "success": False,
        "error": "Timeout waiting for run completion",
        "run_id": run_id
    }

# Usage
result = send_message(
    username="user@example.com",
    password="secure_password",
    message="Hello from automation!"
)

print(result)
```

### Example 2: Retrieve Chat Messages

```python
def get_chat_messages(username, password, chat_room_url):
    """Retrieve messages from a chat interface"""
    
    payload = {
        "parameters": {
            "originUrl": chat_room_url,
            "USERNAME": username,
            "PASSWORD": password
        }
    }
    
    response = requests.post(
        f"{API_URL}/robots/{MESSAGE_RETRIEVER_ROBOT_ID}/runs",
        json=payload,
        headers=headers
    )
    
    run_id = response.json().get("runId")
    
    # Wait and check status
    time.sleep(5)
    
    status_response = requests.get(
        f"{API_URL}/robots/{MESSAGE_RETRIEVER_ROBOT_ID}/runs/{run_id}",
        headers=headers
    )
    
    if status_response.status_code == 200:
        data = status_response.json()
        interpretation = data.get("interpretation", {})
        
        # Extract captured list of messages
        messages = interpretation.get("capturedLists", {}).get("messages", [])
        
        return messages
    
    return []

# Usage
messages = get_chat_messages(
    username="user@example.com",
    password="secure_password",
    chat_room_url="https://chat.example.com/room/123"
)

for msg in messages:
    print(f"{msg.get('author')}: {msg.get('text')}")
```

### Example 3: Node.js Implementation

```javascript
const axios = require('axios');

const API_URL = 'http://localhost:8080/api';
const API_KEY = 'your-api-key-here';
const ROBOT_ID = 'your-robot-id';

const headers = {
  'x-api-key': API_KEY,
  'Content-Type': 'application/json'
};

async function sendChatMessage(username, password, message) {
  try {
    // Start robot run
    const runResponse = await axios.post(
      `${API_URL}/robots/${ROBOT_ID}/runs`,
      {
        parameters: {
          originUrl: 'https://chat.example.com',
          USERNAME: username,
          PASSWORD: password,
          MESSAGE: message
        }
      },
      { headers }
    );

    const runId = runResponse.data.runId;
    console.log(`Started run: ${runId}`);

    // Poll for completion
    for (let i = 0; i < 60; i++) {
      await new Promise(resolve => setTimeout(resolve, 2000));

      const statusResponse = await axios.get(
        `${API_URL}/robots/${ROBOT_ID}/runs/${runId}`,
        { headers }
      );

      const status = statusResponse.data.run?.status;
      console.log(`Status: ${status}`);

      if (status === 'success') {
        const capturedData = statusResponse.data.interpretation?.capturedTexts || {};
        return {
          success: true,
          response: capturedData.response || '',
          runId
        };
      } else if (status === 'failed') {
        return {
          success: false,
          error: statusResponse.data.error || 'Run failed',
          runId
        };
      }
    }

    return {
      success: false,
      error: 'Timeout',
      runId
    };

  } catch (error) {
    console.error('Error:', error.message);
    throw error;
  }
}

// Usage
sendChatMessage('user@example.com', 'password', 'Hello!')
  .then(result => console.log('Result:', result))
  .catch(err => console.error('Error:', err));
```

### Example 4: Bash Script with curl

```bash
#!/bin/bash

API_URL="http://localhost:8080/api"
API_KEY="your-api-key-here"
ROBOT_ID="your-robot-id"

# Function to send message
send_message() {
    local username="$1"
    local password="$2"
    local message="$3"
    
    # Start run
    run_response=$(curl -s -X POST "${API_URL}/robots/${ROBOT_ID}/runs" \
        -H "x-api-key: ${API_KEY}" \
        -H "Content-Type: application/json" \
        -d "{
            \"parameters\": {
                \"originUrl\": \"https://chat.example.com\",
                \"USERNAME\": \"${username}\",
                \"PASSWORD\": \"${password}\",
                \"MESSAGE\": \"${message}\"
            }
        }")
    
    run_id=$(echo "$run_response" | jq -r '.runId')
    echo "Started run: $run_id"
    
    # Poll for completion
    for i in {1..30}; do
        sleep 2
        
        status_response=$(curl -s "${API_URL}/robots/${ROBOT_ID}/runs/${run_id}" \
            -H "x-api-key: ${API_KEY}")
        
        status=$(echo "$status_response" | jq -r '.run.status')
        echo "Status: $status"
        
        if [ "$status" = "success" ]; then
            echo "Run completed successfully"
            echo "$status_response" | jq '.interpretation.capturedTexts'
            exit 0
        elif [ "$status" = "failed" ]; then
            echo "Run failed"
            echo "$status_response" | jq '.error'
            exit 1
        fi
    done
    
    echo "Timeout waiting for completion"
    exit 1
}

# Usage
send_message "user@example.com" "password" "Hello from bash!"
```

## Best Practices

### 1. Security

- **Never hardcode credentials**: Use environment variables or secure vaults
- **Rotate API keys**: Regenerate keys periodically
- **Encrypt sensitive data**: Use HTTPS for all API calls
- **Use proxy settings**: Configure proxies in robot settings for anonymity

```python
import os

USERNAME = os.getenv('CHAT_USERNAME')
PASSWORD = os.getenv('CHAT_PASSWORD')
API_KEY = os.getenv('MAXUN_API_KEY')
```

### 2. Error Handling

```python
def robust_send_message(username, password, message, max_retries=3):
    for attempt in range(max_retries):
        try:
            result = send_message(username, password, message)
            if result['success']:
                return result
            
            # Wait before retry
            time.sleep(5 * (attempt + 1))
            
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                raise
    
    return {"success": False, "error": "Max retries exceeded"}
```

### 3. Rate Limiting

```python
import time
from collections import deque

class RateLimiter:
    def __init__(self, max_calls, time_window):
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = deque()
    
    def wait_if_needed(self):
        now = time.time()
        
        # Remove old calls outside time window
        while self.calls and self.calls[0] < now - self.time_window:
            self.calls.popleft()
        
        if len(self.calls) >= self.max_calls:
            sleep_time = self.calls[0] + self.time_window - now
            if sleep_time > 0:
                time.sleep(sleep_time)
        
        self.calls.append(time.time())

# Usage: max 10 calls per minute
limiter = RateLimiter(max_calls=10, time_window=60)

for message in messages:
    limiter.wait_if_needed()
    send_message(username, password, message)
```

### 4. Logging and Monitoring

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('chat_automation.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def send_message_with_logging(username, password, message):
    logger.info(f"Sending message for user: {username}")
    
    try:
        result = send_message(username, password, message)
        
        if result['success']:
            logger.info(f"Message sent successfully. Run ID: {result['run_id']}")
        else:
            logger.error(f"Failed to send message: {result.get('error')}")
        
        return result
        
    except Exception as e:
        logger.exception(f"Exception while sending message: {e}")
        raise
```

### 5. Parameterized Workflows

Design robots to accept dynamic parameters:

```python
def create_flexible_chat_bot(action_type, **kwargs):
    """
    Flexible chat bot for different actions
    
    action_type: 'send', 'retrieve', 'delete', etc.
    """
    robot_map = {
        'send': 'send-message-robot-id',
        'retrieve': 'get-messages-robot-id',
        'delete': 'delete-message-robot-id'
    }
    
    robot_id = robot_map.get(action_type)
    if not robot_id:
        raise ValueError(f"Unknown action type: {action_type}")
    
    payload = {
        "parameters": {
            "originUrl": kwargs.get('url'),
            **kwargs
        }
    }
    
    # Execute robot...
```

### 6. Screenshot Debugging

When a robot fails, retrieve the screenshot:

```python
def get_run_screenshot(robot_id, run_id):
    """Download screenshot from failed run"""
    
    response = requests.get(
        f"{API_URL}/robots/{robot_id}/runs/{run_id}",
        headers=headers
    )
    
    if response.status_code == 200:
        data = response.json()
        screenshot_url = data.get("run", {}).get("screenshotUrl")
        
        if screenshot_url:
            img_response = requests.get(screenshot_url)
            with open(f"debug_{run_id}.png", "wb") as f:
                f.write(img_response.content)
            print(f"Screenshot saved: debug_{run_id}.png")
```

## API Reference

### List All Robots

```bash
GET /api/robots
Headers:
  x-api-key: YOUR_API_KEY
```

### Get Robot Details

```bash
GET /api/robots/{robotId}
Headers:
  x-api-key: YOUR_API_KEY
```

### Run Robot

```bash
POST /api/robots/{robotId}/runs
Headers:
  x-api-key: YOUR_API_KEY
  Content-Type: application/json
Body:
{
  "parameters": {
    "originUrl": "https://example.com",
    "PARAM1": "value1",
    "PARAM2": "value2"
  }
}
```

### Get Run Status

```bash
GET /api/robots/{robotId}/runs/{runId}
Headers:
  x-api-key: YOUR_API_KEY
```

### List Robot Runs

```bash
GET /api/robots/{robotId}/runs
Headers:
  x-api-key: YOUR_API_KEY
```

## Troubleshooting

### Robot Fails to Login

1. Check if credentials are correct
2. Verify selector accuracy (inspect element in browser)
3. Increase wait time after navigation
4. Check for CAPTCHA or 2FA requirements

### Rate Limiting Issues

1. Implement exponential backoff
2. Use multiple API keys
3. Add delays between requests
4. Monitor run queue status

### Browser Timeout

1. Increase timeout in robot settings
2. Optimize workflow steps
3. Check network connectivity
4. Monitor server resources

## Advanced Topics

### Using Proxies

Configure proxy in robot settings:

```json
{
  "proxy": {
    "enabled": true,
    "host": "proxy.example.com",
    "port": 8080,
    "username": "proxy_user",
    "password": "proxy_pass"
  }
}
```

### Scheduled Runs

Use external scheduler (cron, systemd timer, etc.):

```cron
# Send daily report at 9 AM
0 9 * * * /usr/bin/python3 /path/to/send_message.py
```

### Webhooks Integration

Configure webhook URL in Maxun to receive notifications:

```python
from flask import Flask, request

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    data = request.json
    run_id = data.get('runId')
    status = data.get('status')
    
    print(f"Run {run_id} completed with status: {status}")
    
    return {"status": "ok"}

app.run(port=5000)
```

## Support and Resources

- **Documentation**: https://docs.maxun.dev
- **GitHub**: https://github.com/getmaxun/maxun
- **Discord**: https://discord.gg/5GbPjBUkws
- **YouTube Tutorials**: https://www.youtube.com/@MaxunOSS

## License

This documentation is part of the Maxun project, licensed under AGPLv3.

