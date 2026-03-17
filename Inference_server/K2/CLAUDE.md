# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

K2Think API Proxy v2.0 is an OpenAI-compatible API proxy that provides a gateway to MBZUAI's K2-Think reasoning model. The system acts as a drop-in replacement for OpenAI API calls, enabling applications to use the K2-Think model with minimal code changes.

## Development Commands

### **Primary Development Commands**

```bash
# Complete one-command deployment (for new setups)
bash scripts/all.sh

# Setup environment and dependencies
bash scripts/setup.sh

# Start server (manually after setup)
bash scripts/start.sh

# Test API functionality
bash scripts/send_request.sh

# Stop server
kill $(cat .server.pid)

# View server logs
tail -f server.log

# Generate tokens (when needed)
python3 get_tokens.py
```

### **Virtual Environment Requirements**

This project requires the use of a Python virtual environment:

```bash
# Activate venv before any Python operations
source venv/bin/activate

# OR use the Python wrapper script (recommended)
./python-k2 your_script.py

# OR use venv Python directly
venv/bin/python your_script.py
```

**Note:** Running `python` directly without the virtual environment will fail due to `externally-managed-environment` errors.

## Architecture

### **Core Application Structure**

- **`k2think_proxy.py`** - Main FastAPI application entry point (UTF-8 encoding configured)
- **`src/`** - Modular source code directory
  - **`api_handler.py`** (25,855 lines) - Main API request processing and routing
  - **`config.py`** - Centralized configuration management
  - **`token_manager.py`** - Token rotation and authentication logic
  - **`token_updater.py`** - Automatic token refresh service
  - **`response_processor.py`** - Response formatting and processing
  - **`tool_handler.py`** - Function/tool calling implementation
  - **`models.py`** - Pydantic models for API requests/responses
  - **`utils.py`** - Utility functions
  - **`constants.py`** - Application constants
  - **`exceptions.py`** - Custom exception handling

### **Key Components**

1. **Token Management System**
   - Automatic token rotation with failover
   - Multi-token support in `data/tokens.txt`
   - Smart failure detection and recovery
   - Configurable auto-refresh via `ENABLE_TOKEN_AUTO_UPDATE`

2. **Configuration System**
   - Environment-based configuration in `.env` file
   - Default credentials: `developer@pixelium.uk` / `developer123`
   - Port configuration (default: 7000)
   - Token management settings

3. **API Proxy Layer**
   - OpenAI-compatible endpoints (`/v1/chat/completions`, `/v1/models`, `/health`)
   - Streaming response support
   - Function/tool calling capabilities
   - File upload support (multi-modal)

### **Data Management**

- **`accounts.txt`** - K2Think credentials (JSON format, auto-generated)
- **`data/tokens.txt`** - Active authentication tokens (managed automatically)
- **`.env`** - Runtime configuration
- **`server.log`** - Application logs
- **`.server.pid`** - Process ID for server management

### **Deployment Scripts**

- **`scripts/all.sh`** - Master deployment orchestrator (setup → tokens → start → test)
- **`scripts/setup.sh`** - Environment setup with system dependencies and venv creation
- **`scripts/start.sh`** - Server startup with virtual environment activation
- **`scripts/send_request.sh`** - API testing with OpenAI SDK
- **`k2think_activate.sh`** - Environment activation helper
- **`k2think_deploy_oneliner.sh`** - One-command deployment

## Configuration

### **Environment Variables**

Key settings in `.env`:
```bash
# Server Configuration
PORT=7000
SERVER_PORT=7000  # Alternative port setting

# Authentication
VALID_API_KEY=sk-k2think-proxy-xxxxxxxxxx
ALLOW_ANY_API_KEY=true  # Accept any key in development

# Token Management
ENABLE_TOKEN_AUTO_UPDATE=true
TOKEN_UPDATE_INTERVAL=3600
TOKENS_FILE=data/tokens.txt
```

### **Credentials Setup**

The system automatically creates `accounts.txt` with default credentials. Override with:
```bash
export K2_EMAIL="your@email.com"
export K2_PASSWORD="yourpassword"
```

## Development Workflow

### **Local Development**

1. **Environment Setup**:
   ```bash
   bash scripts/setup.sh  # Creates venv and installs dependencies
   ```

2. **Token Generation** (if needed):
   ```bash
   python3 get_tokens.py
   ```

3. **Server Start**:
   ```bash
   bash scripts/start.sh
   ```

4. **Testing**:
   ```bash
   bash scripts/send_request.sh
   ```

### **Code Development**

- All source code is in the `src/` directory
- Use the virtual environment for all Python development
- The main entry point is `k2think_proxy.py` which imports from `src/`
- Configuration changes require server restart to take effect

### **Key Considerations**

1. **Virtual Environment is Mandatory**: Never run Python directly - always use `venv/bin/python` or activate the venv first
2. **UTF-8 Encoding**: The application is configured for UTF-8 output to handle international characters
3. **Token Management**: Tokens are automatically managed, but manual refresh can be triggered via admin endpoints
4. **Server Management**: Use PID file (.server.pid) for process management
5. **Logging**: All activity is logged to `server.log`

## API Integration

### **OpenAI SDK Usage**

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:7000/v1",
    api_key="sk-k2think-proxy-xxxxxxxxxx"
)

response = client.chat.completions.create(
    model="MBZUAI-IFM/K2-Think",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

### **curl Testing**

```bash
curl http://localhost:7000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-k2think-proxy-xxxxxxxxxx" \
  -d '{
    "model": "MBZUAI-IFM/K2-Think",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```