# WrtnLabs Full-Stack Deployment Requirements

**Complete Configuration Guide for Terminal & WebUI Deployment**

---

## Table of Contents

1. [System Requirements](#1-system-requirements)
2. [Environment Variables](#2-environment-variables)
3. [Database Configuration](#3-database-configuration)
4. [AI/LLM Configuration](#4-aillm-configuration)
5. [Backend Configuration](#5-backend-configuration)
6. [Frontend Configuration](#6-frontend-configuration)
7. [Security & Authentication](#7-security--authentication)
8. [Terminal Deployment](#8-terminal-deployment)
9. [WebUI Deployment](#9-webui-deployment)
10. [Real-Time Progression Tracking](#10-real-time-progression-tracking)

---

## 1. System Requirements

### 1.1 Required Software

| Software | Minimum Version | Recommended | Purpose |
|----------|----------------|-------------|---------|
| **Node.js** | v18.0.0 | v20.0.0+ | Runtime environment |
| **pnpm** | v8.0.0 | v10.0.0+ | Package manager |
| **PostgreSQL** | v13.0 | v15.0+ | Database |
| **Git** | v2.30 | Latest | Version control |
| **TypeScript** | v5.0 | v5.9+ | Language |

### 1.2 Hardware Requirements

**Minimum:**
- CPU: 2 cores
- RAM: 4GB
- Disk: 10GB free space
- Network: Stable internet connection

**Recommended:**
- CPU: 4+ cores
- RAM: 8GB+
- Disk: 20GB+ SSD
- Network: High-speed broadband

---

## 2. Environment Variables

### 2.1 Core AutoBE Variables

```bash
# ===== LLM PROVIDER CONFIGURATION =====
# Choose ONE provider and configure accordingly

# Option 1: OpenAI (GPT-4, GPT-5, etc.)
OPENAI_API_KEY="sk-proj-..."
OPENAI_BASE_URL="https://api.openai.com/v1"  # Optional, default is OpenAI
OPENAI_MODEL="gpt-4.1"                        # or "gpt-5-mini", "gpt-5"

# Option 2: Anthropic (Claude)
ANTHROPIC_API_KEY="sk-ant-..."
ANTHROPIC_BASE_URL="https://api.anthropic.com"  # Optional
ANTHROPIC_MODEL="claude-sonnet-4.5"              # or "claude-haiku-4.5"

# Option 3: Z.ai (GLM models - OpenAI compatible)
ANTHROPIC_AUTH_TOKEN="your-zai-token"
ANTHROPIC_BASE_URL="https://api.z.ai/api/anthropic"
MODEL="glm-4.6"                                   # or "glm-4.5-air"
API_TIMEOUT_MS="3000000"                          # 50 minutes

# Option 4: OpenRouter (Multi-model gateway)
OPENROUTER_API_KEY="sk-or-..."
OPENROUTER_BASE_URL="https://openrouter.ai/api/v1"
OPENROUTER_MODEL="qwen/qwen3-next-80b-a3b-instruct"

# Option 5: Local LLM (Ollama, etc.)
LOCAL_LLM_BASE_URL="http://localhost:11434/v1"
LOCAL_LLM_MODEL="qwen2.5:32b"

# ===== AUTOBE AGENT CONFIGURATION =====
AUTOBE_COMPILERS=4              # Number of parallel compilers (1-8)
AUTOBE_SEMAPHORE=4              # Concurrent operations (1-16)
AUTOBE_TIMEOUT=NULL             # Agent timeout (ms, NULL for unlimited)
AUTOBE_OUTPUT_DIR="./output"    # Where to save generated projects

# ===== MODEL FALLBACK CONFIGURATION =====
# Defaults when MODEL not specified
ANTHROPIC_DEFAULT_OPUS_MODEL="gpt-5"
ANTHROPIC_DEFAULT_SONNET_MODEL="gpt-4.1"
ANTHROPIC_DEFAULT_HAIKU_MODEL="gpt-4.1-mini"
```

### 2.2 Database Variables

```bash
# ===== POSTGRESQL CONFIGURATION =====
# For AutoBE-generated applications

POSTGRES_HOST="127.0.0.1"              # Database host
POSTGRES_PORT="5432"                    # Database port
POSTGRES_DATABASE="autobe"              # Database name
POSTGRES_SCHEMA="public"                # Schema name (can be custom)
POSTGRES_USERNAME="autobe"              # Database user
POSTGRES_PASSWORD="your-secure-password" # Database password

# Constructed connection string
DATABASE_URL="postgresql://${POSTGRES_USERNAME}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DATABASE}?schema=${POSTGRES_SCHEMA}"

# ===== PRISMA CONFIGURATION =====
# Used by AutoBE for schema validation
PRISMA_ENGINES_MIRROR="https://prisma-builds.s3-eu-west-1.amazonaws.com"  # Optional
```

### 2.3 WebUI/Playground Variables

```bash
# ===== HACKATHON/PLAYGROUND SERVER =====
# For running the AutoBE WebUI

HACKATHON_API_PORT=5888                # WebUI API port
HACKATHON_UI_PORT=5713                 # WebUI frontend port
HACKATHON_COMPILERS=4                  # Compilers for WebUI
HACKATHON_SEMAPHORE=4                  # Concurrent sessions

# Database for WebUI (stores chat sessions)
HACKATHON_POSTGRES_HOST=127.0.0.1
HACKATHON_POSTGRES_PORT=5432
HACKATHON_POSTGRES_DATABASE=autobe_playground
HACKATHON_POSTGRES_SCHEMA=wrtnlabs
HACKATHON_POSTGRES_USERNAME=autobe
HACKATHON_POSTGRES_PASSWORD=autobe

# JWT for WebUI authentication
HACKATHON_JWT_SECRET_KEY="generate-random-32-char-string"
HACKATHON_JWT_REFRESH_KEY="generate-random-16-char-string"

# Storage for generated files
HACKATHON_STORAGE_PATH="./storage/playground"
```

### 2.4 AutoView Variables

```bash
# ===== AUTOVIEW CONFIGURATION =====
# For frontend component generation

# Same LLM configuration as AutoBE (reuse above)
OPENAI_API_KEY="..."
# OR
ANTHROPIC_API_KEY="..."

# AutoView-specific
AUTOVIEW_MODEL="gpt-5-mini"            # Recommended for AutoView
AUTOVIEW_EXPERIMENTAL_ALL_IN_ONE=true  # Faster generation
AUTOVIEW_THINKING_ENABLED=true         # Enable o3-mini thinking mode
AUTOVIEW_OUTPUT_DIR="./output/frontend"
```

### 2.5 Optional: Vision & Embeddings

```bash
# ===== VISION MODEL (Optional) =====
# For image-based UI generation
VISION_MODEL_ENDPOINT="https://api.openai.com/v1/chat/completions"
VISION_MODEL_API_KEY="your-vision-api-key"
VISION_MODEL_NAME="gpt-4-vision-preview"

# ===== EMBEDDINGS (Optional) =====
# For semantic search in documentation
EMBEDDINGS_ENDPOINT="https://api.openai.com/v1/embeddings"
EMBEDDINGS_API_KEY="your-embeddings-api-key"
EMBEDDINGS_MODEL="text-embedding-3-large"
EMBEDDINGS_DIMENSIONS=1536

# ===== VECTOR DATABASE (Optional) =====
# If using RAG for documentation
PINECONE_API_KEY="your-pinecone-key"
PINECONE_ENVIRONMENT="us-east-1-aws"
PINECONE_INDEX="autobe-docs"
```

---

## 3. Database Configuration

### 3.1 PostgreSQL Setup

**Option 1: Docker (Recommended)**

```bash
# Using provided script
cd /root/autobe-zai-deployment
bash postgres.sh

# OR manually
docker run -d \
  --name autobe-postgres \
  -e POSTGRES_USER=autobe \
  -e POSTGRES_PASSWORD=autobe \
  -e POSTGRES_DB=autobe \
  -p 5432:5432 \
  postgres:15-alpine
```

**Option 2: Native Installation**

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install postgresql postgresql-contrib

# macOS
brew install postgresql@15
brew services start postgresql@15

# Create database
psql postgres
CREATE DATABASE autobe;
CREATE USER autobe WITH PASSWORD 'autobe';
GRANT ALL PRIVILEGES ON DATABASE autobe TO autobe;
\q
```

### 3.2 Database Initialization

```bash
# For AutoBE-generated projects
cd output/your-project
npx prisma migrate dev --name init

# For WebUI/Playground
cd apps/hackathon-server
npx prisma migrate deploy
```

### 3.3 Multiple Database Support

```bash
# Development
DEV_DATABASE_URL="postgresql://autobe:autobe@localhost:5432/autobe_dev?schema=public"

# Production
PROD_DATABASE_URL="postgresql://user:pass@prod-host:5432/autobe_prod?schema=public"

# Testing
TEST_DATABASE_URL="postgresql://autobe:autobe@localhost:5432/autobe_test?schema=public"
```

---

## 4. AI/LLM Configuration

### 4.1 Supported Providers & Models

| Provider | Models | Best For | Cost |
|----------|--------|----------|------|
| **OpenAI** | gpt-4.1, gpt-5, gpt-5-mini | Full-stack (backend+frontend) | $$$ |
| **Anthropic** | claude-sonnet-4.5, claude-haiku-4.5 | Complex reasoning | $$$ |
| **Z.ai** | glm-4.6, glm-4.5-air | Cost-effective, Chinese | $ |
| **OpenRouter** | qwen3-next-80b, deepseek-v3 | Budget-friendly | $$ |
| **Local** | qwen2.5, llama3 | Privacy, offline | FREE |

### 4.2 Provider-Specific Configuration

**OpenAI Setup:**
```bash
export OPENAI_API_KEY="sk-proj-your-key-here"
export OPENAI_MODEL="gpt-4.1"  # or gpt-5, gpt-5-mini

# Optional: Use custom endpoint
export OPENAI_BASE_URL="https://your-proxy.com/v1"
```

**Anthropic Setup:**
```bash
export ANTHROPIC_API_KEY="sk-ant-your-key-here"
export ANTHROPIC_MODEL="claude-sonnet-4.5"
```

**Z.ai Setup (OpenAI-compatible):**
```bash
export ANTHROPIC_AUTH_TOKEN="your-zai-token"
export ANTHROPIC_BASE_URL="https://api.z.ai/api/anthropic"
export MODEL="glm-4.6"
export API_TIMEOUT_MS="3000000"
```

**OpenRouter Setup:**
```bash
export OPENROUTER_API_KEY="sk-or-your-key"
export OPENROUTER_MODEL="qwen/qwen3-next-80b-a3b-instruct"
export OPENROUTER_BASE_URL="https://openrouter.ai/api/v1"
```

**Local LLM Setup:**
```bash
# Install Ollama
curl https://ollama.ai/install.sh | sh

# Pull model
ollama pull qwen2.5:32b

# Configure
export LOCAL_LLM_BASE_URL="http://localhost:11434/v1"
export LOCAL_LLM_MODEL="qwen2.5:32b"
```

### 4.3 Model Selection Guide

**For Backend Generation (AutoBE):**
- ✅ Best: `gpt-4.1`, `gpt-5`, `claude-sonnet-4.5`
- ⚠️ Good: `qwen3-next-80b`, `glm-4.6`
- ❌ Not Recommended: Mini models (insufficient for complex backend)

**For Frontend Generation (AutoView):**
- ✅ Best: `gpt-5-mini`, `claude-haiku-4.5`, `glm-4.5-air`
- ⚠️ Good: `gpt-4.1-mini`
- ℹ️ Frontend is simpler, lighter models work well

### 4.4 API Rate Limits & Quotas

```bash
# OpenAI
# Tier 1: 500 RPM, 30K TPM
# Tier 5: 10,000 RPM, 10M TPM

# Anthropic  
# Standard: 50 RPM
# Scale: 1000 RPM

# Z.ai
# Check your plan limits

# Configure rate limiting
MAX_REQUESTS_PER_MINUTE=50
TOKEN_BUCKET_SIZE=10000
```

---

## 5. Backend Configuration

### 5.1 AutoBE Project Settings

```bash
# ===== PROJECT STRUCTURE =====
PROJECT_NAME="my-backend-api"
PROJECT_OUTPUT_DIR="./output/${PROJECT_NAME}"
PROJECT_DESCRIPTION="E-commerce API backend"

# ===== CODE GENERATION =====
TARGET_FRAMEWORK="nestjs"        # Fixed for AutoBE
TARGET_ORM="prisma"               # Fixed for AutoBE
TARGET_LANGUAGE="typescript"      # Fixed for AutoBE
TARGET_RUNTIME="node"             # Fixed for AutoBE

# ===== API CONFIGURATION =====
API_PORT=3000                     # Backend port
API_PREFIX="/api"                 # API route prefix
API_VERSION="v1"                  # API version
CORS_ORIGIN="*"                   # CORS configuration

# ===== SWAGGER/OPENAPI =====
SWAGGER_ENABLED=true
SWAGGER_PATH="/api-docs"
SWAGGER_TITLE="My Backend API"
SWAGGER_VERSION="1.0.0"
SWAGGER_DESCRIPTION="Generated by AutoBE"
```

### 5.2 Runtime Configuration

```bash
# ===== NODE.JS SETTINGS =====
NODE_ENV="development"            # or "production", "test"
NODE_OPTIONS="--max-old-space-size=4096"  # Memory limit

# ===== LOGGING =====
LOG_LEVEL="info"                  # debug, info, warn, error
LOG_FORMAT="json"                 # or "pretty"
LOG_OUTPUT="./logs/backend.log"

# ===== PERFORMANCE =====
WORKER_THREADS=4                  # For CPU-intensive tasks
MAX_CONNECTIONS=100               # Database connection pool
REQUEST_TIMEOUT=30000             # 30 seconds
```

---

## 6. Frontend Configuration

### 6.1 AutoView Settings

```bash
# ===== AUTOVIEW GENERATION =====
AUTOVIEW_INPUT_TYPE="openapi"     # or "json-schema", "typescript"
AUTOVIEW_INPUT_SOURCE="./backend/swagger.json"
AUTOVIEW_OUTPUT_DIR="./frontend/components"

# ===== UI FRAMEWORK =====
UI_FRAMEWORK="react"              # Fixed for AutoView
UI_LIBRARY="@autoview/ui"         # AutoView components
UI_STYLING="tailwind"             # or "css", "styled-components"

# ===== COMPONENT GENERATION =====
GENERATE_FORMS=true
GENERATE_LISTS=true
GENERATE_DETAILS=true
GENERATE_API_CLIENT=true
```

### 6.2 Frontend Build Configuration

```bash
# ===== VITE CONFIGURATION =====
VITE_PORT=3001
VITE_HOST="0.0.0.0"
VITE_OPEN_BROWSER=false

# ===== API CONNECTION =====
VITE_API_URL="http://localhost:3000"
VITE_API_TIMEOUT=10000

# ===== PRODUCTION BUILD =====
BUILD_OUTPUT_DIR="./dist"
BUILD_MINIFY=true
BUILD_SOURCEMAP=false
```

---

## 7. Security & Authentication

### 7.1 JWT Configuration

```bash
# ===== JWT TOKENS =====
JWT_SECRET_KEY="generate-with-openssl-rand-base64-32"
JWT_REFRESH_KEY="generate-with-openssl-rand-base64-16"
JWT_EXPIRES_IN="1h"
JWT_REFRESH_EXPIRES_IN="7d"
JWT_ALGORITHM="HS256"

# Generate secure keys:
# openssl rand -base64 32  # for JWT_SECRET_KEY
# openssl rand -base64 16  # for JWT_REFRESH_KEY
```

### 7.2 API Security

```bash
# ===== RATE LIMITING =====
RATE_LIMIT_WINDOW="15m"
RATE_LIMIT_MAX_REQUESTS=100

# ===== CORS =====
CORS_ORIGIN="https://yourdomain.com"
CORS_CREDENTIALS=true
CORS_METHODS="GET,POST,PUT,DELETE,PATCH"

# ===== SECURITY HEADERS =====
HELMET_ENABLED=true
CSP_ENABLED=true
```

---

## 8. Terminal Deployment

### 8.1 Quick Start (Terminal Only)

```bash
# ===== 1. INSTALL AUTOBE =====
git clone https://github.com/wrtnlabs/autobe.git
cd autobe
pnpm install
pnpm run build

# ===== 2. CONFIGURE ENVIRONMENT =====
cat > .env.local << EOF
OPENAI_API_KEY="your-key"
OPENAI_MODEL="gpt-4.1"
POSTGRES_HOST="127.0.0.1"
POSTGRES_PORT="5432"
POSTGRES_DATABASE="autobe"
POSTGRES_USERNAME="autobe"
POSTGRES_PASSWORD="autobe"
DATABASE_URL="postgresql://autobe:autobe@localhost:5432/autobe"
EOF

# ===== 3. SETUP DATABASE =====
docker run -d --name autobe-postgres \
  -e POSTGRES_USER=autobe \
  -e POSTGRES_PASSWORD=autobe \
  -e POSTGRES_DB=autobe \
  -p 5432:5432 \
  postgres:15-alpine

# ===== 4. RUN AUTOBE (TERMINAL) =====
node examples/terminal-demo.js
```

### 8.2 Complete Terminal Script

```javascript
// terminal-demo.js
const { AutoBeAgent } = require('@autobe/agent');
const { AutoBeCompiler } = require('@autobe/compiler');
const OpenAI = require('openai');
require('dotenv').config();

const agent = new AutoBeAgent({
  vendor: {
    api: new OpenAI({
      apiKey: process.env.OPENAI_API_KEY,
      baseURL: process.env.OPENAI_BASE_URL
    }),
    model: process.env.OPENAI_MODEL || 'gpt-4.1'
  },
  compiler: async () => new AutoBeCompiler()
});

// Track progression in real-time
agent.addEventListener('*', (event) => {
  console.log(`[${event.type}] ${event.message || ''}`);
});

(async () => {
  // Step 1: Requirements
  await agent.talk('Create a blog API with posts and comments');
  
  // Step 2: Database
  await agent.talk('Design database schema');
  
  // Step 3: API
  await agent.talk('Create OpenAPI specification');
  
  // Step 4: Tests
  await agent.talk('Generate E2E tests');
  
  // Step 5: Implementation
  await agent.talk('Implement with NestJS');
  
  // Save output
  const files = agent.getFiles();
  await files.write('./output/blog-api');
  
  console.log('✅ Generated backend at: ./output/blog-api');
})();
```

### 8.3 Running in Terminal

```bash
# With environment variables
export OPENAI_API_KEY="your-key"
export OPENAI_MODEL="gpt-4.1"
node terminal-demo.js

# Or inline
OPENAI_API_KEY="your-key" OPENAI_MODEL="gpt-4.1" node terminal-demo.js

# With progress output
node terminal-demo.js 2>&1 | tee generation.log
```

---

## 9. WebUI Deployment

### 9.1 Playground Setup

```bash
# ===== OPTION 1: LOCAL PLAYGROUND =====
cd autobe
pnpm install
pnpm run playground

# Access at: http://localhost:5713

# ===== OPTION 2: STACKBLITZ (ONLINE) =====
# Visit: https://stackblitz.com/github/wrtnlabs/autobe-playground-stackblitz
# No installation needed!
```

### 9.2 Hackathon Server Configuration

```bash
# ===== CONFIGURE HACKATHON SERVER =====
cd apps/hackathon-server

cat > .env.local << EOF
HACKATHON_API_PORT=5888
HACKATHON_UI_PORT=5713
HACKATHON_COMPILERS=4
HACKATHON_SEMAPHORE=4

HACKATHON_POSTGRES_HOST=127.0.0.1
HACKATHON_POSTGRES_PORT=5432
HACKATHON_POSTGRES_DATABASE=autobe_playground
HACKATHON_POSTGRES_USERNAME=autobe
HACKATHON_POSTGRES_PASSWORD=autobe

HACKATHON_JWT_SECRET_KEY="$(openssl rand -base64 32)"
HACKATHON_JWT_REFRESH_KEY="$(openssl rand -base64 16)"

OPENAI_API_KEY="your-openai-key"
EOF

# ===== INITIALIZE DATABASE =====
npx prisma migrate deploy

# ===== START SERVER =====
pnpm run dev
```

### 9.3 WebUI Features

**Available at http://localhost:5713:**
- Chat interface for AutoBE
- Real-time code generation visualization
- Multi-session management
- Code preview and download
- Replay previous sessions

---

## 10. Real-Time Progression Tracking

### 10.1 Event Types

AutoBE emits 65+ event types during generation:

```typescript
// Phase-level events
'analyze.start'              // Requirements analysis started
'analyze.progress'           // Progress update
'analyze.complete'           // Analysis finished

'prisma.start'              // Database design started
'prisma.schema.generated'   // Schema AST created
'prisma.compile.success'    // Schema validated
'prisma.complete'           // Database design finished

'interface.start'           // API design started
'interface.openapi.generated' // OpenAPI spec created
'interface.compile.success' // OpenAPI validated
'interface.complete'        // API design finished

'test.start'               // Test generation started
'test.function.generated'  // Each test function created
'test.compile.success'     // Tests validated
'test.complete'            // Testing finished

'realize.start'            // Implementation started
'realize.function.generated' // Each API function created
'realize.compile.success'  // Code validated
'realize.complete'         // Implementation finished
```

### 10.2 Progress Monitoring Script

```javascript
// monitor-progress.js
const { AutoBeAgent } = require('@autobe/agent');

const agent = new AutoBeAgent({
  vendor: { /* ... */ },
  compiler: async () => new AutoBeCompiler()
});

// Track all events
const progress = {
  phase: null,
  totalSteps: 0,
  completedSteps: 0,
  startTime: null,
  errors: []
};

agent.addEventListener('*', (event) => {
  const timestamp = new Date().toISOString();
  
  // Phase tracking
  if (event.type.endsWith('.start')) {
    progress.phase = event.type.replace('.start', '');
    progress.startTime = Date.now();
    console.log(`\n📍 [${timestamp}] Phase: ${progress.phase}`);
  }
  
  // Progress updates
  if (event.type.includes('.progress')) {
    progress.completedSteps++;
    const elapsed = ((Date.now() - progress.startTime) / 1000).toFixed(1);
    console.log(`   ⏱️  ${elapsed}s - ${event.message}`);
  }
  
  // Completion
  if (event.type.endsWith('.complete')) {
    const elapsed = ((Date.now() - progress.startTime) / 1000).toFixed(1);
    console.log(`   ✅ Phase completed in ${elapsed}s`);
  }
  
  // Errors
  if (event.type.includes('.error') || event.type.includes('.failed')) {
    progress.errors.push(event);
    console.error(`   ❌ Error: ${event.message}`);
  }
});

// Run generation
(async () => {
  await agent.talk('Create a todo API');
  await agent.talk('Design database');
  await agent.talk('Create API spec');
  await agent.talk('Generate tests');
  await agent.talk('Implement code');
  
  const files = agent.getFiles();
  await files.write('./output/todo-api');
  
  console.log('\n📊 Generation Summary:');
  console.log(`   Total Steps: ${progress.completedSteps}`);
  console.log(`   Errors: ${progress.errors.length}`);
})();
```

### 10.3 Visual Progress Bar

```javascript
// progress-bar.js
const cliProgress = require('cli-progress');

const agent = new AutoBeAgent({ /* ... */ });

const bar = new cliProgress.SingleBar({
  format: '{phase} |{bar}| {percentage}% | {value}/{total} steps',
  barCompleteChar: '\u2588',
  barIncompleteChar: '\u2591',
  hideCursor: true
});

const phases = ['analyze', 'prisma', 'interface', 'test', 'realize'];
let currentPhaseIndex = 0;
let phaseSteps = 0;

agent.addEventListener('*', (event) => {
  if (event.type.endsWith('.start')) {
    currentPhaseIndex++;
    bar.start(100, 0, { phase: phases[currentPhaseIndex - 1] });
    phaseSteps = 0;
  }
  
  if (event.type.includes('.progress')) {
    phaseSteps += 20; // Arbitrary increment
    bar.update(Math.min(phaseSteps, 100));
  }
  
  if (event.type.endsWith('.complete')) {
    bar.update(100);
    bar.stop();
  }
});
```

### 10.4 WebUI Progress View

The WebUI (`http://localhost:5713`) provides:
- Real-time phase visualization
- Code diff viewer
- AST tree viewer
- Compilation status
- Token usage statistics
- Time estimates

---

## 11. Complete Deployment Checklist

### 11.1 Pre-Deployment

- [ ] Node.js v18+ installed
- [ ] pnpm v8+ installed
- [ ] PostgreSQL v13+ running
- [ ] Git configured
- [ ] LLM API key obtained
- [ ] Environment variables set

### 11.2 AutoBE Setup

- [ ] Repository cloned
- [ ] Dependencies installed (`pnpm install`)
- [ ] Packages built (`pnpm run build`)
- [ ] Database initialized
- [ ] `.env.local` configured
- [ ] Test generation successful

### 11.3 AutoView Setup (Optional)

- [ ] AutoView repository cloned
- [ ] Dependencies installed
- [ ] LLM API key configured
- [ ] OpenAPI spec available
- [ ] Test component generation

### 11.4 Production Readiness

- [ ] HTTPS enabled
- [ ] Database backups configured
- [ ] Monitoring enabled
- [ ] Log rotation setup
- [ ] Rate limiting configured
- [ ] Security headers enabled

---

## 12. Quick Reference

### 12.1 Essential Environment Variables

```bash
# Minimum required for terminal deployment
export OPENAI_API_KEY="your-key"
export OPENAI_MODEL="gpt-4.1"
export DATABASE_URL="postgresql://user:pass@localhost:5432/db"

# Run AutoBE
node your-script.js
```

### 12.2 Common Commands

```bash
# Build packages
pnpm run build

# Run playground
pnpm run playground

# Generate backend (terminal)
node examples/terminal-demo.js

# Initialize database
npx prisma migrate dev

# Start backend
cd output/your-project && npm run start:dev

# View API docs
open http://localhost:3000/api-docs
```

### 12.3 Troubleshooting

**Issue: "Cannot find module '@autobe/agent'"**
```bash
cd autobe && pnpm install && pnpm run build
```

**Issue: "Database connection failed"**
```bash
# Check PostgreSQL is running
docker ps | grep postgres
# Check credentials
psql "postgresql://autobe:autobe@localhost:5432/autobe"
```

**Issue: "API key invalid"**
```bash
# Verify key format
echo $OPENAI_API_KEY
# Should start with "sk-proj-" for OpenAI
```

---

## 13. Full Example: E-Commerce Deployment

```bash
# ===== COMPLETE E-COMMERCE SETUP =====

# 1. Environment setup
cat > .env.local << EOF
OPENAI_API_KEY="sk-proj-your-key"
OPENAI_MODEL="gpt-4.1"
DATABASE_URL="postgresql://ecommerce:securepass@localhost:5432/ecommerce"
API_PORT=3000
EOF

# 2. Database
docker run -d --name ecommerce-db \
  -e POSTGRES_USER=ecommerce \
  -e POSTGRES_PASSWORD=securepass \
  -e POSTGRES_DB=ecommerce \
  -p 5432:5432 \
  postgres:15-alpine

# 3. Generate backend
node << 'EOFSCRIPT'
const { AutoBeAgent } = require('@autobe/agent');
const { AutoBeCompiler } = require('@autobe/compiler');
const OpenAI = require('openai');

const agent = new AutoBeAgent({
  vendor: {
    api: new OpenAI({ apiKey: process.env.OPENAI_API_KEY }),
    model: 'gpt-4.1'
  },
  compiler: async () => new AutoBeCompiler()
});

(async () => {
  await agent.talk('Create e-commerce API with products, cart, orders, payments');
  await agent.talk('Design database');
  await agent.talk('Create OpenAPI spec');
  await agent.talk('Generate E2E tests');
  await agent.talk('Implement with NestJS');
  
  const files = agent.getFiles();
  await files.write('./ecommerce-backend');
  console.log('✅ E-commerce backend generated!');
})();
EOFSCRIPT

# 4. Initialize and run
cd ecommerce-backend
npm install
npx prisma migrate dev
npm run start:dev

# 5. Backend running at http://localhost:3000
# API docs at http://localhost:3000/api-docs
```

---

**Document Version**: 1.0  
**Last Updated**: November 14, 2025  
**Maintained By**: Codegen Analysis System  
**Repository**: https://github.com/Zeeeepa/analyzer
