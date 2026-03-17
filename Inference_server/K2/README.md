# K2Think API Proxy v2.0 🚀

**OpenAI-compatible API proxy for MBZUAI K2-Think model with Interactive Port Selection & Auto Environment Management**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

---

## ✨ What's New in v2.0

- 🎯 **Interactive Port Selection** - Choose any available port or auto-detect conflicts
- 🔄 **Smart Port Conflict Resolution** - Automatically detects and helps resolve port issues
- 📦 **Auto Environment Activation** - One command to activate venv and change directory
- 🛠️ **Server Management Scripts** - Easy start/stop/restart/status/logs commands
- 🎨 **Beautiful CLI Interface** - Color-coded output with ASCII art banners
- 📊 **Deployment Logging** - Track all deployments with detailed logs
- 🔧 **Installation Management** - Upgrade or reinstall with preserved configurations
- 🗑️ **Clean Uninstall** - Complete removal script included

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Features](#features)
3. [Installation](#installation)
4. [Post-Installation](#post-installation)
5. [Server Management](#server-management)
6. [Configuration](#configuration)
7. [Using the API](#using-the-api)
8. [Troubleshooting](#troubleshooting)
9. [Advanced Topics](#advanced-topics)
10. [中文文档](#中文文档)

---

## Quick Start

### 🚀 One-Liner Deployment (New in v2.0!)

```bash
export K2_EMAIL="your@email.com" && \
export K2_PASSWORD="yourpassword" && \
curl -fsSL https://raw.githubusercontent.com/Zeeeepa/k2think2api3/codegen-bot/interactive-port-venv-cd-upgrade-1760647609/k2think_deploy_oneliner.sh | bash
```

**What happens:**
1. ✅ **Interactive port selection** with conflict detection
2. ✅ Repository cloned and configured
3. ✅ Virtual environment created
4. ✅ Dependencies installed
5. ✅ Server started and verified
6. ✅ Helper scripts generated

**Example interactive flow:**
```
Enter port number (default 7000): 8000
✅ Port 8000 is available!
...
✅ DEPLOYMENT SUCCESSFUL ✅
```

### 📦 Activate Your Environment

After deployment, activate the environment with:

```bash
source ~/k2think2api3/k2think_activate.sh
```

This will:
- ✅ Change to the k2think2api3 directory
- ✅ Activate the virtual environment
- ✅ Display server status
- ✅ Show available commands

### 🔧 Optional: Add Permanent Alias

For quick activation in future sessions:

**Bash:**
```bash
echo 'alias k2think="source ~/k2think2api3/k2think_activate.sh"' >> ~/.bashrc
source ~/.bashrc
```

**Zsh:**
```bash
echo 'alias k2think="source ~/k2think2api3/k2think_activate.sh"' >> ~/.zshrc
source ~/.zshrc
```

Then just run `k2think` anytime to activate!

---

## Features

```bash
curl -fsSL https://raw.githubusercontent.com/Zeeeepa/k2think2api3/main/scripts/all.sh | bash
```

**Smart features:**
- ✅ Auto-detects if you're in the project directory
- ✅ Searches common locations for existing installation
- ✅ Clones repository if not found
- ✅ Prompts for credentials if needed
- ✅ Installs all dependencies
- ✅ Starts the server
- ✅ Shows live API response
- ✅ Prints working examples with your localhost URL

---

## Installation Methods

### Method 1: Bash Process Substitution (Recommended)

**Most foolproof method - prevents URL mistakes:**

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Zeeeepa/k2think2api3/main/install.sh)
```

**Why this is better:**
- 🔒 Bash process substitution `<()` prevents file system errors
- 🎯 Single command = less room for mistakes
- 🚀 Cleaner, more professional
- ✅ Industry-standard pattern (used by Homebrew, rustup, nvm)

### Method 2: Download and Inspect First

If you want to review the script before running:

```bash
# Download
curl -fsSL https://raw.githubusercontent.com/Zeeeepa/k2think2api3/main/install.sh -o install.sh

# Review (optional)
cat install.sh

# Run
bash install.sh
```

### Method 3: Manual Step-by-Step

For those who prefer manual control:

```bash
# 1. Clone repository
git clone https://github.com/Zeeeepa/k2think2api3.git
cd k2think2api3

# 2. Setup environment
bash scripts/setup.sh

# 3. Start server
bash scripts/deploy.sh

# 4. Test API
bash scripts/send_request.sh
```

### Method 4: With Specific Branch

```bash
# Download deployment script
curl -fsSL https://raw.githubusercontent.com/Zeeeepa/k2think2api3/main/csds.sh -o csds.sh

# Deploy with main branch (default)
bash csds.sh

# Or deploy with specific branch
bash csds.sh your-branch-name
```

---

## Core Features

### 🧠 K2-Think Model Integration
- Full support for MBZUAI's K2-Think reasoning model
- Advanced AI capabilities with reasoning chains
- Optimized for complex problem-solving

### 🔄 OpenAI Compatibility
- **Drop-in replacement** for OpenAI API
- Compatible with all OpenAI SDKs and libraries
- Same API format and behavior
- Seamless migration from OpenAI

### ⚡ Streaming Support
- Real-time streaming chat responses
- Efficient token-by-token output
- Low latency for better user experience

### 🛠️ Function Calling
- Full OpenAI Function Calling support
- Tool use capabilities
- Structured data extraction
- Agent-ready architecture

### 📊 File Upload Support
- Image upload and analysis
- Document processing
- Multi-modal capabilities

### 🔐 Intelligent Token Management
- **Multi-token rotation** with automatic failover
- Smart failure detection
- Auto-refresh on consecutive failures
- Zero-downtime token updates
- Continuous health monitoring

### 🛡️ Self-Healing System
- Automatic token validation
- Intelligent retry mechanisms
- Robust error handling
- High availability

### 🚀 Performance
- Async/await architecture
- High concurrency support
- Efficient connection pooling
- Optimized for scale

---

## Project Structure

```
k2think2api3/
├── 📂 scripts/              # All deployment scripts
│   ├── all.sh              # 🎯 Smart all-in-one deployment
│   ├── setup.sh            # 🔧 Environment setup
│   ├── deploy.sh           # 🚀 Server deployment
│   ├── install.sh          # 📦 Interactive installer
│   ├── send_request.sh     # 🧪 API testing
│   └── export_env.sh       # 🔐 Environment variables
├── k2think_proxy.py        # Main proxy server
├── get_tokens.py           # Token management
├── requirements.txt        # Python dependencies
├── Dockerfile              # Docker support
├── README.md               # Main documentation
├── INSTALL.md              # Installation guide
├── QUICKSTART.md           # Quick start guide
├── README_NEW_SECTION.md   # Additional features
└── DOCUMENTATION.md        # This file
```

### Generated Files After Installation

```
k2think2api3/
├── .env                    # API key and configuration
├── accounts.txt            # Your K2 credentials (JSON format)
├── tokens.txt              # Auto-refreshing tokens
├── server.log              # Server logs
├── .server.pid             # Process ID for server management
└── venv/                   # Python virtual environment
    └── lib/                # Includes OpenAI SDK
```

---

## Deployment Scripts Guide

### 📋 scripts/all.sh - Complete One-Command Deployment

**The master script that handles everything:**

```bash
curl -fsSL https://raw.githubusercontent.com/Zeeeepa/k2think2api3/main/scripts/all.sh | bash
```

**Complete workflow:**
1. ✅ Auto-detects if you're in project directory
2. ✅ Searches common locations (~/k2think2api3, ~/projects/k2think2api3)
3. ✅ Clones repository if not found
4. ✅ Prompts for K2 credentials (if needed)
5. ✅ Runs setup (venv, dependencies, .env)
6. ✅ Starts server on port 7000
7. ✅ Tests with Python SDK
8. ✅ Shows live API response
9. ✅ Prints working examples with actual URLs
10. ✅ Exports environment variables

**With pre-set credentials:**
```bash
export K2_EMAIL="your@email.com"
export K2_PASSWORD="yourpassword"
curl -fsSL https://raw.githubusercontent.com/Zeeeepa/k2think2api3/main/scripts/all.sh | bash
```

---

### 🔧 scripts/setup.sh - Environment Setup

**For initial environment configuration:**

```bash
git clone https://github.com/Zeeeepa/k2think2api3
cd k2think2api3
bash scripts/setup.sh
```

**What it does:**
- Creates Python virtual environment (venv/)
- Installs all dependencies from requirements.txt
- Creates accounts.txt from credentials
- Generates .env configuration file
- Installs OpenAI Python package for testing
- Sets up token management system

**Required environment variables:**
- `K2_EMAIL` - Your K2Think account email
- `K2_PASSWORD` - Your K2Think password

**Features:**
- ✅ Handles externally-managed Python environments
- ✅ No root privileges required
- ✅ No system package modifications
- ✅ Isolated dependency management

---

### 🚀 scripts/deploy.sh - Server Deployment

**For starting or restarting the server:**

```bash
cd k2think2api3
bash scripts/deploy.sh
```

**What it does:**
- Activates virtual environment
- Starts server in background on port 7000
- Creates PID file (.server.pid) for management
- Waits for server initialization
- Shows server status and information
- Displays management commands

**Server features:**
- Detects if server is already running
- Provides kill command if needed
- Shows health check endpoint
- Logs all activity to server.log
- Graceful shutdown support

---

### 🧪 scripts/send_request.sh - API Testing

**For testing the deployed API:**

```bash
cd k2think2api3
bash scripts/send_request.sh
```

**What it does:**
- Checks if server is running
- Activates virtual environment
- Uses OpenAI Python SDK
- Sends test request to the API
- Shows formatted response
- Displays token usage statistics

**Example output:**
```
======================================================================
📥 RESPONSE RECEIVED
======================================================================
Model: MBZUAI-IFM/K2-Think
ID: chatcmpl-1760096305

Content:
----------------------------------------------------------------------
Hello! I'm K2-Think, an AI assistant.
----------------------------------------------------------------------

Token Usage:
  • Prompt tokens: 438
  • Completion tokens: 132
  • Total tokens: 570
======================================================================
```

---

### 🔐 scripts/export_env.sh - Environment Variables

**For exporting environment variables to your shell:**

```bash
source <(curl -fsSL https://raw.githubusercontent.com/Zeeeepa/k2think2api3/main/scripts/export_env.sh)
```

**What it does:**
- Reads API key from .env file
- Exports OPENAI_API_KEY variable
- Exports OPENAI_BASE_URL variable
- Shows usage example

**After sourcing:**
```python
from openai import OpenAI
client = OpenAI()  # Automatically uses environment variables
```

---

### 📦 scripts/install.sh - Interactive Installer

**For guided installation with prompts:**

```bash
cd k2think2api3
bash scripts/install.sh
```

**Features:**
- Interactive prompts for all configuration
- System requirements validation
- Dependency installation
- Account setup
- Environment configuration
- Installation testing
- User-friendly error messages

---

## Configuration

### Environment Variables

The `.env` file contains all configuration:

```bash
# API Configuration
PORT=7000
VALID_API_KEY=sk-k2think-proxy-xxxxxxxxxx

# Token Management
ENABLE_TOKEN_AUTO_UPDATE=true
TOKEN_UPDATE_INTERVAL=3600
MAX_CONSECUTIVE_FAILURES=3

# Logging
LOG_LEVEL=INFO
```

### Accounts Configuration

The `accounts.txt` file stores K2 credentials in JSON format:

```json
{"email": "your@email.com", "password": "yourpassword"}
```

**Security notes:**
- Never commit accounts.txt to version control
- Keep credentials secure
- Use environment variables for sensitive data

### Token Management

The `tokens.txt` file stores active tokens (managed automatically):

```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Auto-update features:**
- Automatic token refresh
- Multi-token rotation
- Failure detection
- Health monitoring
- Zero-downtime updates

---

## Using the API

### Quick Test with curl

```bash
curl http://localhost:7000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-k2think-proxy-xxxxxxxxxx" \
  -d '{
    "model": "MBZUAI-IFM/K2-Think",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### Python Examples

#### 1. Simple Example (Using Environment Variables)

```python
from openai import OpenAI

# Uses OPENAI_API_KEY and OPENAI_BASE_URL from environment
client = OpenAI()

response = client.chat.completions.create(
    model="MBZUAI-IFM/K2-Think",
    messages=[{"role": "user", "content": "What is your model name?"}]
)

print(response.choices[0].message.content)
```

#### 2. Explicit Configuration

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:7000/v1",
    api_key="sk-k2think-proxy-xxxxxxxxxx"  # Get from .env file
)

response = client.chat.completions.create(
    model="MBZUAI-IFM/K2-Think",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain quantum computing in simple terms."}
    ],
    temperature=0.7,
    max_tokens=500
)

print(response.choices[0].message.content)
```

#### 3. Streaming Response

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:7000/v1",
    api_key="sk-k2think-proxy-xxxxxxxxxx"
)

stream = client.chat.completions.create(
    model="MBZUAI-IFM/K2-Think",
    messages=[{"role": "user", "content": "Write a short poem about AI"}],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end='', flush=True)
print()
```

#### 4. Using Virtual Environment

```bash
# Activate the venv
source ~/k2think2api3/venv/bin/activate

# Run your script
python your_script.py

# Deactivate when done
deactivate
```

#### 5. Direct Execution with venv Python

```bash
~/k2think2api3/venv/bin/python your_script.py
```

---

## Server Management

### View Server Logs

```bash
tail -f ~/k2think2api3/server.log
```

### Stop the Server

```bash
kill $(cat ~/k2think2api3/.server.pid)
```

### Restart the Server

```bash
cd ~/k2think2api3
bash scripts/deploy.sh
```

### Check Server Status

```bash
curl http://localhost:7000/health
```

### Get Your API Key

```bash
grep VALID_API_KEY ~/k2think2api3/.env
```

### Export Environment Variables

```bash
cd ~/k2think2api3
export OPENAI_API_KEY=$(grep VALID_API_KEY .env | cut -d'=' -f2)
export OPENAI_BASE_URL="http://localhost:7000/v1"
```

---

## API Reference

### Chat Completions Endpoint

**Endpoint:** `/v1/chat/completions`  
**Method:** POST  
**Compatible with:** OpenAI Chat Completions API

**Request body:**
```json
{
  "model": "MBZUAI-IFM/K2-Think",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello!"}
  ],
  "temperature": 0.7,
  "max_tokens": 500,
  "stream": false
}
```

**Response:**
```json
{
  "id": "chatcmpl-xxxxx",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "MBZUAI-IFM/K2-Think",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! How can I help you today?"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 20,
    "completion_tokens": 10,
    "total_tokens": 30
  }
}
```

### Models List Endpoint

**Endpoint:** `/v1/models`  
**Method:** GET

**Response:**
```json
{
  "object": "list",
  "data": [
    {
      "id": "MBZUAI-IFM/K2-Think",
      "object": "model",
      "created": 1234567890,
      "owned_by": "k2think-proxy"
    }
  ]
}
```

### Health Check Endpoint

**Endpoint:** `/health`  
**Method:** GET

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime": "2h 15m 30s"
}
```

### Admin Endpoints

All admin endpoints require authentication via the API key.

#### Token Statistics

**Endpoint:** `/admin/tokens/stats`  
**Method:** GET

**Response:**
```json
{
  "total_tokens": 5,
  "active_tokens": 4,
  "failed_tokens": 1,
  "last_update": "2024-01-15T10:30:00Z"
}
```

#### Reload Tokens

**Endpoint:** `/admin/tokens/reload`  
**Method:** POST

Reloads tokens from the tokens.txt file.

#### Reset All Tokens

**Endpoint:** `/admin/tokens/reset-all`  
**Method:** POST

Resets the failure state of all tokens.

#### Auto-Updater Status

**Endpoint:** `/admin/tokens/updater/status`  
**Method:** GET

**Response:**
```json
{
  "enabled": true,
  "last_update": "2024-01-15T10:00:00Z",
  "next_update": "2024-01-15T11:00:00Z",
  "interval_seconds": 3600
}
```

#### Force Token Update

**Endpoint:** `/admin/tokens/updater/force-update`  
**Method:** POST

Triggers an immediate token refresh.

---

## Troubleshooting

### Server Won't Start

**Check if port 7000 is already in use:**
```bash
lsof -i :7000
```

**View server logs:**
```bash
cat ~/k2think2api3/server.log
```

**Ensure Python 3.8+ is installed:**
```bash
python3 --version
```

### "Command not found: bash"

**Problem:** You're probably on Windows.  
**Solution:** Use WSL or Git Bash.

### "Permission denied"

**Problem:** Script permissions or sudo requirement.  
**Solution:** The script doesn't need sudo. Run as your normal user.

### "curl: command not found"

**Solution:** Install curl first:

```bash
# Ubuntu/Debian
sudo apt-get install curl

# macOS
brew install curl

# CentOS/RHEL
sudo yum install curl
```

### "Module not found: openai"

**Solution:** Use the virtual environment:

```bash
source ~/k2think2api3/venv/bin/activate
python your_script.py
```

Or use venv Python directly:
```bash
~/k2think2api3/venv/bin/python your_script.py
```

### Token Auto-Update Not Working

1. **Verify accounts.txt exists and has correct format:**
   ```bash
   cat ~/k2think2api3/accounts.txt
   ```

2. **Check .env configuration:**
   ```bash
   grep ENABLE_TOKEN_AUTO_UPDATE ~/k2think2api3/.env
   ```

3. **View updater logs:**
   ```bash
   grep "token" ~/k2think2api3/server.log
   ```

### Server Not Responding

**Check if server is running:**
```bash
ps aux | grep k2think_proxy
```

**Check PID file:**
```bash
cat ~/k2think2api3/.server.pid
```

**Test health endpoint:**
```bash
curl http://localhost:7000/health
```

---

## Advanced Features

### Custom Port Configuration

Edit `.env` file:
```bash
PORT=8000  # Change from default 7000
```

Then restart the server:
```bash
cd ~/k2think2api3
kill $(cat .server.pid)
bash scripts/deploy.sh
```

### Enable/Disable Token Auto-Update

Edit `.env` file:
```bash
# Enable auto-update (requires accounts.txt)
ENABLE_TOKEN_AUTO_UPDATE=true

# Disable auto-update
ENABLE_TOKEN_AUTO_UPDATE=false
```

### Configure Update Interval

Edit `.env` file:
```bash
# Update tokens every hour (3600 seconds)
TOKEN_UPDATE_INTERVAL=3600

# Update every 30 minutes
TOKEN_UPDATE_INTERVAL=1800
```

### Production Deployment Recommendations

1. **Use a reverse proxy** (nginx, Apache)
2. **Set up SSL/TLS** for secure connections
3. **Configure rate limiting**
4. **Set up monitoring** and alerts
5. **Use a process manager** (systemd, PM2)
6. **Implement log rotation**
7. **Set up automated backups** for configuration

### Docker Deployment

```bash
# Build image
docker build -t k2think-api .

# Run container
docker run -d \
  -p 7000:7000 \
  -e K2_EMAIL="your@email.com" \
  -e K2_PASSWORD="yourpassword" \
  --name k2think-api \
  k2think-api
```

---

## Common Workflows

### First Time Setup
```bash
# One command does everything
curl -fsSL https://raw.githubusercontent.com/Zeeeepa/k2think2api3/main/scripts/all.sh | bash
```

### Daily Usage

```bash
# Check server status
curl http://localhost:7000/health

# View recent logs
tail -n 50 ~/k2think2api3/server.log

# Test API
cd ~/k2think2api3 && bash scripts/send_request.sh
```

### Updating the Server

```bash
cd ~/k2think2api3
git pull origin main
kill $(cat .server.pid)
bash scripts/deploy.sh
```

---

## 中文文档

<details>
<summary>点击展开完整中文文档 / Click to expand full Chinese documentation</summary>

### 基于 FastAPI 构建的 K2Think AI 模型代理服务

提供 OpenAI 兼容的 API 接口，支持本地和 Docker 部署。

### 核心功能特性

- 🧠 **MBZUAI K2-Think 模型**: 支持 MBZUAI 开发的 K2-Think 推理模型
- 🔄 **OpenAI 兼容**: 完全兼容 OpenAI API 格式，无缝对接现有应用
- ⚡ **流式响应**: 支持实时流式聊天响应
- 🛠️ **工具调用**: 支持 OpenAI Function Calling
- 📊 **文件上传**: 支持文件、图像上传
- 🔐 **令牌管理**: 自动令牌轮换和验证
- 🎯 **智能脚本**: 自动检测、自动配置、自动部署

### 🚀 一键部署

最简单的方式！使用自动化脚本：

```bash
curl -fsSL https://raw.githubusercontent.com/Zeeeepa/k2think2api3/main/scripts/all.sh | bash
```

### 特性说明

#### 自动创建虚拟环境

✅ 自动创建 Python 虚拟环境（解决系统管理的 Python 环境问题）  
✅ 自动安装所有依赖  
✅ 自动配置服务器  
✅ 自动启动并测试 API  
✅ 支持指定分支部署

#### 使用虚拟环境

脚本会自动处理 `externally-managed-environment` 错误：

- 所有依赖都安装在独立的虚拟环境中 (venv/)
- 不需要 root 权限
- 不需要 `--break-system-packages` 选项
- 完全隔离的依赖管理

### 快速命令

```bash
# 查看日志
tail -f ~/k2think2api3/server.log

# 停止服务器
kill $(cat ~/k2think2api3/.server.pid)

# 重启服务器
cd ~/k2think2api3 && bash scripts/deploy.sh

# 获取 API 密钥
grep VALID_API_KEY ~/k2think2api3/.env

# 测试 API
cd ~/k2think2api3 && bash scripts/send_request.sh
```

### Python 使用示例

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:7000/v1",
    api_key="<your-api-key>"  # 从 .env 文件获取
)

response = client.chat.completions.create(
    model="MBZUAI-IFM/K2-Think",
    messages=[{"role": "user", "content": "你好！"}]
)

print(response.choices[0].message.content)
```

### 高级配置

#### 启用/禁用令牌自动更新

编辑 `.env` 文件：

```bash
# 启用自动更新（需要 accounts.txt 文件）
ENABLE_TOKEN_AUTO_UPDATE=true

# 禁用自动更新
ENABLE_TOKEN_AUTO_UPDATE=false
```

#### 配置 K2 凭据

编辑 `accounts.txt` 文件：

```json
{"email": "your@email.com", "password": "yourpassword"}
```

#### 更改服务器端口

编辑 `.env` 文件：

```bash
PORT=8000  # 默认是 7000
```

然后重启服务器。

### 故障排除

#### 服务器无法启动

1. 检查端口 7000 是否被占用：
   ```bash
   lsof -i :7000
   ```

2. 查看服务器日志：
   ```bash
   cat ~/k2think2api3/server.log
   ```

3. 确保安装了 Python 3.8+：
   ```bash
   python3 --version
   ```

#### "找不到模块: openai"

使用虚拟环境：
```bash
source ~/k2think2api3/venv/bin/activate
python your_script.py
```

或直接使用 venv Python：
```bash
~/k2think2api3/venv/bin/python your_script.py
```

</details>

---

## Support & Contributing

### Getting Help

- 📖 [GitHub Repository](https://github.com/Zeeeepa/k2think2api3)
- 🐛 [Report Issues](https://github.com/Zeeeepa/k2think2api3/issues)
- 💬 Check server logs: `tail -f ~/k2think2api3/server.log`
- 🔍 Verify configuration: `cat ~/k2think2api3/.env`

### Pro Tips

1. **Keep credentials secure**: Never commit `accounts.txt` or `.env` to version control
2. **Monitor token usage**: Check `/admin/tokens/stats` regularly
3. **Use environment variables**: Easier than hardcoding API keys
4. **Always use venv**: For consistent Python dependencies
5. **Logs are your friend**: Check `server.log` when troubleshooting
6. **Health checks**: Monitor `/health` endpoint in production

---

## License

This project is provided as-is for educational and development purposes.

---

**Happy coding! 🎉**

---

*Last updated: 2024-01-15*  
*Version: 1.0.0*
