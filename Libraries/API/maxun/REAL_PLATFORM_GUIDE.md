# Real Platform Integration Guide

## Using Maxun with Actual Credentials and Live Chat Platforms

This guide shows you how to use Maxun's browser automation to interact with real web chat interfaces using your actual credentials.

---

## 🚀 Quick Start

### Step 1: Deploy Maxun Locally

```bash
cd maxun

# Start all services
docker-compose -f docker-compose.test.yml up -d

# Wait for services to be healthy (~30 seconds)
docker-compose ps

# Access the UI
open http://localhost:5173
```

### Step 2: Create Your First Recording

1. **Open Maxun UI** at http://localhost:5173
2. **Click "New Recording"**
3. **Enter the chat platform URL** (e.g., https://discord.com/login)
4. **Click "Start Recording"**
5. **Perform your workflow**:
   - Enter username/email
   - Enter password
   - Click login
   - Navigate to channel
   - Type a message
   - Click send
6. **Click "Stop Recording"**
7. **Save with a name** (e.g., "Discord Message Sender")

---

## 💻 Supported Platforms

### ✅ Discord

**URL**: https://discord.com/app

**Recording Steps**:
```python
steps = [
    {"type": "navigate", "url": "https://discord.com/login"},
    {"type": "type", "selector": "input[name='email']", "text": "{{username}}"},
    {"type": "type", "selector": "input[name='password']", "text": "{{password}}"},
    {"type": "click", "selector": "button[type='submit']"},
    {"type": "wait", "duration": 3000},
    {"type": "navigate", "url": "{{channel_url}}"},
    {"type": "type", "selector": "div[role='textbox']", "text": "{{message}}"},
    {"type": "press", "key": "Enter"}
]
```

**Execute with API**:
```python
from demo_real_chat_automation import MaxunChatAutomation

client = MaxunChatAutomation("http://localhost:8080")

result = client.execute_recording(
    recording_id="your-discord-recording-id",
    parameters={
        "username": "your_email@example.com",
        "password": "your_password",
        "channel_url": "https://discord.com/channels/SERVER_ID/CHANNEL_ID",
        "message": "Hello from Maxun!"
    }
)
```

---

### ✅ Slack

**URL**: https://slack.com/signin

**Recording Steps**:
```python
steps = [
    {"type": "navigate", "url": "https://slack.com/signin"},
    {"type": "type", "selector": "input[type='email']", "text": "{{username}}"},
    {"type": "click", "selector": "button[type='submit']"},
    {"type": "wait", "duration": 2000},
    {"type": "type", "selector": "input[type='password']", "text": "{{password}}"},
    {"type": "click", "selector": "button[type='submit']"},
    {"type": "wait", "duration": 5000},
    {"type": "navigate", "url": "{{workspace_url}}"},
    {"type": "click", "selector": "[data-qa='composer_primary']"},
    {"type": "type", "selector": "[data-qa='message_input']", "text": "{{message}}"},
    {"type": "press", "key": "Enter"}
]
```

**Execute with API**:
```python
result = client.execute_recording(
    recording_id="your-slack-recording-id",
    parameters={
        "username": "your_email@example.com",
        "password": "your_password",
        "workspace_url": "https://app.slack.com/client/WORKSPACE_ID/CHANNEL_ID",
        "message": "Automated message from Maxun"
    }
)
```

---

### ✅ WhatsApp Web

**URL**: https://web.whatsapp.com

**Recording Steps**:
```python
steps = [
    {"type": "navigate", "url": "https://web.whatsapp.com"},
    # Wait for QR code or existing session
    {"type": "wait_for", "selector": "[data-testid='conversation-panel-wrapper']", "timeout": 60000},
    # Search for contact
    {"type": "click", "selector": "[data-testid='search']"},
    {"type": "type", "selector": "[data-testid='chat-list-search']", "text": "{{contact_name}}"},
    {"type": "wait", "duration": 2000},
    {"type": "click", "selector": "[data-testid='cell-frame-container']"},
    # Type and send message
    {"type": "type", "selector": "[data-testid='conversation-compose-box-input']", "text": "{{message}}"},
    {"type": "press", "key": "Enter"}
]
```

**Note**: WhatsApp Web requires QR code scan on first use or persistent session.

**Execute with API**:
```python
result = client.execute_recording(
    recording_id="your-whatsapp-recording-id",
    parameters={
        "contact_name": "John Doe",
        "message": "Hello from automation!"
    }
)
```

---

### ✅ Microsoft Teams

**URL**: https://teams.microsoft.com

**Recording Steps**:
```python
steps = [
    {"type": "navigate", "url": "https://teams.microsoft.com"},
    {"type": "type", "selector": "input[type='email']", "text": "{{username}}"},
    {"type": "click", "selector": "input[type='submit']"},
    {"type": "wait", "duration": 2000},
    {"type": "type", "selector": "input[type='password']", "text": "{{password}}"},
    {"type": "click", "selector": "input[type='submit']"},
    {"type": "wait", "duration": 5000},
    # Navigate to specific team/channel
    {"type": "navigate", "url": "{{channel_url}}"},
    # Click in compose box
    {"type": "click", "selector": "[data-tid='ckeditor']"},
    {"type": "type", "selector": "[data-tid='ckeditor']", "text": "{{message}}"},
    {"type": "click", "selector": "[data-tid='send-button']"}
]
```

**Execute with API**:
```python
result = client.execute_recording(
    recording_id="your-teams-recording-id",
    parameters={
        "username": "your_email@company.com",
        "password": "your_password",
        "channel_url": "https://teams.microsoft.com/_#/conversations/TEAM_ID?threadId=THREAD_ID",
        "message": "Meeting reminder at 2pm"
    }
)
```

---

### ✅ Telegram Web

**URL**: https://web.telegram.org

**Recording Steps**:
```python
steps = [
    {"type": "navigate", "url": "https://web.telegram.org"},
    # Login with phone number
    {"type": "type", "selector": "input.phone-number", "text": "{{phone_number}}"},
    {"type": "click", "selector": "button.btn-primary"},
    # Wait for code input (manual or via SMS)
    {"type": "wait_for", "selector": "input.verification-code", "timeout": 60000},
    {"type": "type", "selector": "input.verification-code", "text": "{{verification_code}}"},
    {"type": "click", "selector": "button.btn-primary"},
    # Search and send
    {"type": "click", "selector": ".tgico-search"},
    {"type": "type", "selector": "input.search-input", "text": "{{contact_name}}"},
    {"type": "wait", "duration": 1000},
    {"type": "click", "selector": ".chatlist-chat"},
    {"type": "type", "selector": "#message-input", "text": "{{message}}"},
    {"type": "press", "key": "Enter"}
]
```

**Execute with API**:
```python
result = client.execute_recording(
    recording_id="your-telegram-recording-id",
    parameters={
        "phone_number": "+1234567890",
        "verification_code": "12345",  # From SMS
        "contact_name": "John Smith",
        "message": "Automated message"
    }
)
```

---

## 🔐 Credential Management

### Option 1: Environment Variables

```bash
# .env file
DISCORD_USERNAME=your_email@example.com
DISCORD_PASSWORD=your_secure_password
SLACK_USERNAME=your_email@example.com
SLACK_PASSWORD=your_secure_password
```

```python
import os

credentials = {
    "username": os.getenv("DISCORD_USERNAME"),
    "password": os.getenv("DISCORD_PASSWORD"),
}

result = client.execute_recording(recording_id, credentials)
```

### Option 2: Encrypted Configuration

```python
import json
from cryptography.fernet import Fernet

# Generate key once
key = Fernet.generate_key()
cipher = Fernet(key)

# Encrypt credentials
credentials = {
    "discord": {
        "username": "your_email@example.com",
        "password": "your_password"
    }
}

encrypted = cipher.encrypt(json.dumps(credentials).encode())

# Save encrypted
with open("credentials.enc", "wb") as f:
    f.write(encrypted)

# Later: decrypt and use
with open("credentials.enc", "rb") as f:
    encrypted = f.read()

decrypted = cipher.decrypt(encrypted)
creds = json.loads(decrypted.decode())
```

### Option 3: HashiCorp Vault

```python
import hvac

# Connect to Vault
vault_client = hvac.Client(url='http://localhost:8200', token='your-token')

# Read credentials
secret = vault_client.secrets.kv.v2.read_secret_version(path='chat-credentials')
credentials = secret['data']['data']

result = client.execute_recording(
    recording_id,
    parameters={
        "username": credentials["discord_username"],
        "password": credentials["discord_password"],
        "message": "Secure automated message"
    }
)
```

### Option 4: AWS Secrets Manager

```python
import boto3
import json

# Create a Secrets Manager client
session = boto3.session.Session()
client = boto3.client('secretsmanager', region_name='us-east-1')

# Retrieve secret
secret_value = client.get_secret_value(SecretId='chat-platform-credentials')
credentials = json.loads(secret_value['SecretString'])

result = maxun_client.execute_recording(
    recording_id,
    parameters={
        "username": credentials["username"],
        "password": credentials["password"]
    }
)
```

---

## 📊 Message Retrieval

### Creating a Message Retriever

**Recording Steps**:
```python
retriever_steps = [
    # Login (same as sender)
    {"type": "navigate", "url": "{{chat_url}}"},
    {"type": "type", "selector": "input[type='email']", "text": "{{username}}"},
    {"type": "type", "selector": "input[type='password']", "text": "{{password}}"},
    {"type": "click", "selector": "button[type='submit']"},
    {"type": "wait", "duration": 3000},
    
    # Navigate to conversation
    {"type": "navigate", "url": "{{conversation_url}}"},
    {"type": "wait", "duration": 2000},
    
    # Scroll to load more messages
    {"type": "scroll", "direction": "up", "amount": 500},
    {"type": "wait", "duration": 2000},
    
    # Extract message data
    {
        "type": "extract",
        "name": "messages",
        "selector": ".message-container, [data-message-id]",
        "fields": {
            "text": {"selector": ".message-text", "attribute": "textContent"},
            "author": {"selector": ".author-name", "attribute": "textContent"},
            "timestamp": {"selector": ".timestamp", "attribute": "textContent"},
            "id": {"selector": "", "attribute": "data-message-id"}
        }
    },
    
    # Take screenshot
    {"type": "screenshot", "name": "messages_captured"}
]
```

**Execute Retrieval**:
```python
result = client.execute_recording(
    recording_id="message-retriever-id",
    parameters={
        "chat_url": "https://discord.com/login",
        "username": "your_email@example.com",
        "password": "your_password",
        "conversation_url": "https://discord.com/channels/SERVER/CHANNEL"
    }
)

# Get results
status = client.get_execution_status(result["execution_id"])
messages = status["extracted_data"]["messages"]

for msg in messages:
    print(f"[{msg['timestamp']}] {msg['author']}: {msg['text']}")
```

---

## 🔄 Batch Operations

### Send Multiple Messages

```python
# Batch send to multiple channels
channels = [
    {"name": "#general", "url": "https://discord.com/channels/123/456"},
    {"name": "#announcements", "url": "https://discord.com/channels/123/789"},
    {"name": "#random", "url": "https://discord.com/channels/123/012"}
]

message = "Important update: Server maintenance at 10pm"

for channel in channels:
    result = client.execute_recording(
        recording_id="discord-sender",
        parameters={
            "username": os.getenv("DISCORD_USERNAME"),
            "password": os.getenv("DISCORD_PASSWORD"),
            "channel_url": channel["url"],
            "message": message
        }
    )
    print(f"✓ Sent to {channel['name']}: {result['execution_id']}")
    time.sleep(2)  # Rate limiting
```

---

## 🎯 Advanced Use Cases

### 1. Scheduled Messages

```python
import schedule
import time

def send_daily_standup():
    client.execute_recording(
        recording_id="slack-sender",
        parameters={
            "username": os.getenv("SLACK_USERNAME"),
            "password": os.getenv("SLACK_PASSWORD"),
            "workspace_url": "https://app.slack.com/client/T123/C456",
            "message": "Good morning team! Daily standup in 15 minutes."
        }
    )

# Schedule daily at 9:45 AM
schedule.every().day.at("09:45").do(send_daily_standup)

while True:
    schedule.run_pending()
    time.sleep(60)
```

### 2. Message Monitoring

```python
import time

def monitor_messages():
    """Monitor for new messages and respond"""
    
    while True:
        # Retrieve messages
        result = client.execute_recording(
            recording_id="message-retriever",
            parameters=credentials
        )
        
        status = client.get_execution_status(result["execution_id"])
        messages = status["extracted_data"]["messages"]
        
        # Check for keywords
        for msg in messages:
            if "urgent" in msg["text"].lower():
                # Send notification
                send_notification(msg)
        
        time.sleep(60)  # Check every minute
```

### 3. Cross-Platform Sync

```python
def sync_message_across_platforms(message_text):
    """Send the same message to multiple platforms"""
    
    platforms = {
        "discord": {
            "recording_id": "discord-sender",
            "params": {
                "username": os.getenv("DISCORD_USERNAME"),
                "password": os.getenv("DISCORD_PASSWORD"),
                "channel_url": "https://discord.com/channels/123/456",
                "message": message_text
            }
        },
        "slack": {
            "recording_id": "slack-sender",
            "params": {
                "username": os.getenv("SLACK_USERNAME"),
                "password": os.getenv("SLACK_PASSWORD"),
                "workspace_url": "https://app.slack.com/client/T123/C456",
                "message": message_text
            }
        },
        "teams": {
            "recording_id": "teams-sender",
            "params": {
                "username": os.getenv("TEAMS_USERNAME"),
                "password": os.getenv("TEAMS_PASSWORD"),
                "channel_url": "https://teams.microsoft.com/...",
                "message": message_text
            }
        }
    }
    
    results = {}
    for platform, config in platforms.items():
        result = client.execute_recording(
            recording_id=config["recording_id"],
            parameters=config["params"]
        )
        results[platform] = result["execution_id"]
        print(f"✓ Sent to {platform}: {result['execution_id']}")
    
    return results
```

---

## ⚠️ Important Security Notes

### DO:
✅ Use environment variables for credentials
✅ Encrypt sensitive data at rest
✅ Use secure credential vaults
✅ Implement rate limiting
✅ Log execution without passwords
✅ Use HTTPS for all communications
✅ Rotate credentials regularly

### DON'T:
❌ Hardcode credentials in source code
❌ Commit credentials to version control
❌ Share credentials in plain text
❌ Use the same password everywhere
❌ Ignore rate limits
❌ Run without monitoring

---

## 🔧 Troubleshooting

### Issue: Login Fails

**Solution**:
- Check if credentials are correct
- Verify platform hasn't changed login UI
- Check for CAPTCHA requirements
- Look for 2FA prompts
- Update recording with new selectors

### Issue: Message Not Sent

**Solution**:
- Verify message input selector
- Check for character limits
- Look for blocked content
- Ensure proper waits between steps
- Check network connection

### Issue: Messages Not Retrieved

**Solution**:
- Update extraction selectors
- Scroll more to load messages
- Wait longer for page load
- Check for lazy loading
- Verify conversation URL

---

## 📈 Performance Optimization

### Headless Mode (Production)

```python
# Enable headless mode for faster execution
result = client.execute_recording(
    recording_id=recording_id,
    parameters={
        **credentials,
        "headless": True  # No browser UI
    }
)
```

### Parallel Execution

```python
from concurrent.futures import ThreadPoolExecutor

def send_message(channel):
    return client.execute_recording(recording_id, channel)

with ThreadPoolExecutor(max_workers=5) as executor:
    futures = [executor.submit(send_message, ch) for ch in channels]
    results = [f.result() for f in futures]
```

### Caching Sessions

```python
# Reuse authenticated sessions
session_recording = client.create_recording(
    name="Persistent Session",
    url="https://discord.com",
    steps=[
        # Login once
        {"type": "navigate", "url": "https://discord.com/login"},
        {"type": "type", "selector": "input[name='email']", "text": "{{username}}"},
        {"type": "type", "selector": "input[name='password']", "text": "{{password}}"},
        {"type": "click", "selector": "button[type='submit']"},
        # Save session
        {"type": "save_cookies", "name": "discord_session"}
    ]
)

# Later: load session
send_recording = client.create_recording(
    name="Send with Cached Session",
    url="https://discord.com",
    steps=[
        {"type": "load_cookies", "name": "discord_session"},
        {"type": "navigate", "url": "{{channel_url}}"},
        # Send message without login
        {"type": "type", "selector": "div[role='textbox']", "text": "{{message}}"},
        {"type": "press", "key": "Enter"}
    ]
)
```

---

## 📚 Additional Resources

- **Maxun Documentation**: https://github.com/getmaxun/maxun
- **Browser Automation Best Practices**: See `docs/best-practices.md`
- **API Reference**: http://localhost:8080/api/docs
- **Example Recordings**: `examples/recordings/`

---

## 🎓 Next Steps

1. **Create your first recording** using the Maxun UI
2. **Test with a simple platform** (like a demo chat)
3. **Add error handling** for production use
4. **Implement credential encryption**
5. **Set up monitoring and alerts**
6. **Scale to multiple platforms**

---

**Need Help?**
- Check the troubleshooting section above
- Review example recordings in `examples/`
- See `demo-real-chat-automation.py` for working code
- Open an issue on GitHub

**Ready to automate!** 🚀

