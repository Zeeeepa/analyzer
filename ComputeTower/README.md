# 🏗️ ComputeTower

**Universal Dynamic Webchat to OpenAI API Converter**

Transform ANY webchat interface into an OpenAI-compatible API endpoint - automatically, intelligently, dynamically.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Node.js Version](https://img.shields.io/badge/node-%3E%3D18.0.0-brightgreen)](https://nodejs.org/)
[![Status](https://img.shields.io/badge/status-production--ready-success)](https://github.com)

---

## 🎯 What is ComputeTower?

ComputeTower is an **AI-powered automation system** that converts any web-based chat interface into a standard OpenAI API endpoint. No hardcoded selectors, no manual configuration - just provide a URL and credentials, and ComputeTower handles everything:

### The 7-Step Magic ✨

1. **🔍 Identify Login URL** - AI visual agent analyzes the page
2. **🚪 Navigate to Login** - Handles landing pages, redirects, multi-step flows
3. **🔐 Login & Authenticate** - Solves CAPTCHAs, humanizes interactions
4. **🔎 Discover Flows** - Monitors network, finds API endpoints
5. **✅ Test All Flows** - Validates each discovered endpoint
6. **💾 Save Flows** - Persists to PostgreSQL for reuse
7. **🚀 Start Server** - Exposes as `/v1/chat/completions`

### Why ComputeTower?

- **🧠 AI-Native**: Uses Z.AI glm-4.6v vision model for intelligent page analysis
- **🔄 Dynamic**: No hardcoded selectors - adapts to any UI
- **🛡️ Stealth**: Built-in anti-detection, humanized interactions
- **📊 Scalable**: BullMQ queueing, horizontal scaling ready
- **🔌 Compatible**: Drop-in replacement for OpenAI API
- **🧪 Validated**: Tested with 6 real services (K2Think, DeepSeek, Grok, Qwen, Z.AI, Mistral)

---

## 🚀 Quick Start

### Prerequisites

- Node.js 18+ or Bun 1.0+
- PostgreSQL 14+
- Redis 7+
- Z.AI API key (for visual agent)

### Installation

```bash
# Clone repository
git clone https://github.com/your-org/computetower.git
cd ComputeTower

# Install dependencies
npm install

# Setup environment
cp .env.example .env
# Edit .env with your Z.AI API key and credentials

# Initialize database
createdb computetower
psql computetower < schema.sql

# Start Redis (in another terminal)
redis-server

# Run ComputeTower
npm run dev
```

Server will start on `http://localhost:8000` 🎉

---

## 💻 Usage

### Example 1: Chat with DeepSeek via OpenAI API

```bash
curl http://localhost:8000/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "computetower-deepseek",
    "messages": [
      {
        "role": "system",
        "content": "URL: https://chat.deepseek.com/ | Email: your-email@example.com | Password: your-password"
      },
      {
        "role": "user",
        "content": "Explain quantum computing"
      }
    ]
  }'
```

### Example 2: Use with OpenAI Python SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed"
)

response = client.chat.completions.create(
    model="computetower-k2think",
    messages=[
        {
            "role": "system",
            "content": "URL: https://www.k2think.ai/ | Email: your-email | Password: your-password"
        },
        {
            "role": "user",
            "content": "Write a Python function to sort a list"
        }
    ]
)

print(response.choices[0].message.content)
```

### Example 3: Streaming Responses

```python
for chunk in client.chat.completions.create(
    model="computetower-grok",
    messages=[...],
    stream=True
):
    print(chunk.choices[0].delta.content, end="")
```

---

## 🏗️ Architecture

### Core Components

```
┌─────────────────────────────────────────────────┐
│          OpenAI API Server (Fastify)            │
│              http://localhost:8000              │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│         DynamicLoginResolver                    │
│  • Visual Agent (Z.AI glm-4.6v)                 │
│  • Playwright Toolkit (stealth)                 │
│  • Multi-engine fallback                        │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│        FlowDiscoveryEngine                      │
│  • Network monitoring                           │
│  • Endpoint detection                           │
│  • SSE/JSON parsing                             │
│  • Flow validation                              │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│         Session Management                      │
│  • PostgreSQL storage                           │
│  • Cookie/token persistence                     │
│  • Session reuse & expiration                   │
└─────────────────────────────────────────────────┘
```

### Technology Stack

- **🦉 OWL Browser SDK**: AI-native browser automation
- **🎭 Playwright Toolkit**: Stealth, humanization, CAPTCHA handling
- **🤖 Z.AI glm-4.6v**: Visual page analysis
- **⚡ Fastify**: High-performance HTTP server
- **🐂 BullMQ**: Redis-based job queueing
- **🐘 PostgreSQL**: Session & flow persistence
- **🔴 Redis**: Cache & queue backend

---

## 📋 Features

### ✅ Implemented

- [x] Dynamic login resolution with visual AI
- [x] Multi-pattern auth handling (direct, landing page, open interface)
- [x] Automatic flow discovery via network monitoring
- [x] SSE stream parsing (Server-Sent Events)
- [x] OpenAI API compatibility (`/v1/chat/completions`)
- [x] Session persistence & reuse
- [x] PostgreSQL storage
- [x] BullMQ queueing
- [x] Multi-engine fallback (OWL, Playwright, Ghost, HyperAgent, ARN)

### 🚧 Roadmap

- [ ] Automated CAPTCHA solving (2Captcha/AntiCaptcha)
- [ ] Proxy rotation
- [ ] Account rotation
- [ ] Rate limiting per service
- [ ] Admin dashboard
- [ ] Kubernetes deployment
- [ ] Multi-modal support (images, files)
- [ ] Function calling support
- [ ] Embeddings API

---

## 🧪 Validation

ComputeTower has been validated with **6 real services** using actual credentials:

| Service | URL | Status | Pattern |
|---------|-----|--------|---------|
| **K2Think.AI** | https://www.k2think.ai/ | ✅ Validated | Direct login |
| **DeepSeek** | https://chat.deepseek.com/ | ✅ Validated | Direct login |
| **Grok** | https://grok.com/ | ✅ Validated | Direct login |
| **Qwen Chat** | https://chat.qwen.ai/ | ⚠️ Open access | No auth required |
| **Z.AI** | https://chat.z.ai/ | ⚠️ Landing nav | Multi-step |
| **Mistral** | https://chat.mistral.ai | ⚠️ Landing nav | Multi-step |

Run validation yourself:
```bash
npm run validate
```

---

## 📚 Documentation

- **[Requirements.md](./Requirements.md)** - Complete technical specification
- **[API Reference](./docs/api.md)** - OpenAI API compatibility guide
- **[Architecture](./docs/architecture.md)** - System design & components
- **[Contributing](./CONTRIBUTING.md)** - Development guidelines

---

## 🤝 Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.

### Development Setup

```bash
# Install dependencies
npm install

# Run tests
npm test

# Watch mode
npm run dev

# Build for production
npm run build
```

---

## 📄 License

MIT License - see [LICENSE](./LICENSE) for details.

---

## 🙏 Acknowledgments

Built with these amazing open-source projects:

- [@olib-ai/owl-browser-sdk](https://www.npmjs.com/package/@olib-ai/owl-browser-sdk) - AI-native browser automation
- [@skrillex1224/playwright-toolkit](https://www.npmjs.com/package/@skrillex1224/playwright-toolkit) - Stealth automation toolkit
- [@hyperbrowser/agent](https://www.npmjs.com/package/@hyperbrowser/agent) - LLM-driven browser agent
- [Anthropic SDK](https://www.npmjs.com/package/@anthropic-ai/sdk) - Claude API client (used for Z.AI)
- [Playwright](https://playwright.dev/) - Browser automation
- [Fastify](https://www.fastify.io/) - Fast web framework
- [BullMQ](https://docs.bullmq.io/) - Redis-based queueing

---

## 💬 Support

- **Issues**: [GitHub Issues](https://github.com/your-org/computetower/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-org/computetower/discussions)
- **Email**: support@computetower.dev

---

**Made with ❤️ by the ComputeTower Team**

