# AutoBE Complete Deployment & Usage Guide

**Complete Step-by-Step Instructions for Terminal and WebUI**

---

## Table of Contents

1. [Quick Start (Easiest - StackBlitz)](#1-quick-start-stackblitz)
2. [Local Development Deployment](#2-local-development-deployment)
3. [Production Server Deployment](#3-production-server-deployment)
4. [VSCode Extension Installation](#4-vscode-extension-installation)
5. [Usage Guide - WebUI](#5-usage-guide-webui)
6. [Usage Guide - Terminal/CLI](#6-usage-guide-terminal-cli)
7. [Advanced Configuration](#7-advanced-configuration)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. Quick Start (Easiest - StackBlitz)

### 🚀 Zero Installation Required

**Option A: Direct Browser Access**

```
Step 1: Open your browser
Step 2: Visit: https://stackblitz.com/github/wrtnlabs/autobe-playground-stackblitz
Step 3: Wait for environment to load (2-3 minutes)
Step 4: Configure API key in UI
Step 5: Start coding!
```

**What you get:**
- ✅ No installation needed
- ✅ Works in any modern browser
- ✅ Full AutoBE playground environment
- ✅ Instant access to UI

**Limitations:**
- Requires internet connection
- Session data not persisted locally
- Limited to playground features

---

## 2. Local Development Deployment

### 📦 Prerequisites

**System Requirements:**
- **Node.js**: v18.0.0 or higher
- **pnpm**: v8.0.0 or higher (package manager)
- **Git**: For cloning repository
- **RAM**: Minimum 4GB (8GB recommended)
- **OS**: Windows, macOS, or Linux

### Step-by-Step Installation

#### Step 1: Install Node.js

**macOS (using Homebrew):**
```bash
# Install Homebrew if not installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Node.js
brew install node@18

# Verify installation
node --version  # Should show v18.x.x or higher
```

**Ubuntu/Debian Linux:**
```bash
# Update package list
sudo apt update

# Install Node.js 18
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Verify installation
node --version
```

**Windows:**
```powershell
# Download installer from: https://nodejs.org/en/download/
# Run the .msi installer
# Follow installation wizard

# Verify in PowerShell
node --version
```

#### Step 2: Install pnpm

```bash
# Install pnpm globally
npm install -g pnpm

# Verify installation
pnpm --version  # Should show 8.x.x or higher
```

#### Step 3: Clone AutoBE Repository

```bash
# Clone the repository
git clone https://github.com/wrtnlabs/autobe.git

# Navigate into directory
cd autobe

# Check repository status
ls -la
# You should see: packages/, apps/, README.md, etc.
```

#### Step 4: Install Dependencies

```bash
# This will install all dependencies for all packages
pnpm install

# Wait for installation to complete (3-5 minutes)
# You'll see progress bars and package installations
```

**Expected Output:**
```
Progress: resolved 1234, reused 1200, downloaded 34, added 1234
Done in 180s
```

#### Step 5: Start Playground

```bash
# Start both server and UI simultaneously
pnpm run playground
```

**What happens:**
```
✓ Starting playground-server on port 5713...
✓ Starting playground-ui on port 3000...
✓ WebSocket server listening...
✓ React dev server ready...

Server running at: http://localhost:5713
UI running at: http://localhost:3000
```

#### Step 6: Access Web UI

```bash
# Open your browser and navigate to:
http://localhost:3000
```

**First Time Setup in UI:**

1. **Select AI Vendor**
   - Click on "Settings" (gear icon)
   - Choose: OpenAI, OpenRouter, or Local LLM

2. **Enter API Key**
   - For OpenAI: `sk-...` (from https://platform.openai.com/api-keys)
   - For OpenRouter: `sk-or-...` (from https://openrouter.ai/keys)

3. **Select Model**
   - OpenAI: `gpt-4`, `gpt-4-turbo`, `gpt-3.5-turbo`
   - OpenRouter: `anthropic/claude-3-opus`, `meta-llama/llama-3-70b`

4. **Configure Locale (Optional)**
   - Language: `en-US`, `ko-KR`, `ja-JP`, etc.
   - Timezone: Auto-detected or manual selection

5. **Start New Conversation**
   - Click "New Chat"
   - Begin describing your backend requirements

---

## 3. Production Server Deployment

### 🏗️ Full Production Setup

#### Prerequisites

**Required Services:**
- PostgreSQL 14+ (for session storage)
- OpenAI/OpenRouter API access
- Linux server (Ubuntu 20.04+ recommended)
- Domain name (optional, for HTTPS)

#### Step 1: Install PostgreSQL

**Ubuntu/Debian:**
```bash
# Update package list
sudo apt update

# Install PostgreSQL
sudo apt install postgresql postgresql-contrib

# Start PostgreSQL service
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Verify installation
sudo -u postgres psql --version
```

#### Step 2: Create Database

```bash
# Switch to postgres user
sudo -u postgres psql

# Inside PostgreSQL shell:
CREATE DATABASE autobe;
CREATE USER autobe WITH PASSWORD 'your_secure_password_here';
GRANT ALL PRIVILEGES ON DATABASE autobe TO autobe;

# Create schema
\c autobe
CREATE SCHEMA wrtnlabs;
GRANT ALL ON SCHEMA wrtnlabs TO autobe;

# Exit PostgreSQL
\q
```

#### Step 3: Clone and Install AutoBE

```bash
# Clone repository
git clone https://github.com/wrtnlabs/autobe.git
cd autobe

# Install dependencies
pnpm install

# Build all packages
pnpm run build
```

#### Step 4: Configure Environment Variables

```bash
# Navigate to hackathon-server directory
cd apps/hackathon-server

# Create environment file
nano .env.local
```

**Paste the following configuration:**

```bash
# Server Configuration
HACKATHON_API_PORT=5888
HACKATHON_COMPILERS=4
HACKATHON_SEMAPHORE=4
HACKATHON_TIMEOUT=NULL

# PostgreSQL Configuration
HACKATHON_POSTGRES_HOST=127.0.0.1
HACKATHON_POSTGRES_PORT=5432
HACKATHON_POSTGRES_DATABASE=autobe
HACKATHON_POSTGRES_SCHEMA=wrtnlabs
HACKATHON_POSTGRES_USERNAME=autobe
HACKATHON_POSTGRES_PASSWORD=your_secure_password_here
HACKATHON_POSTGRES_URL=postgresql://autobe:your_secure_password_here@127.0.0.1:5432/autobe?schema=wrtnlabs

# JWT Authentication (generate random strings)
HACKATHON_JWT_SECRET_KEY=$(openssl rand -base64 32)
HACKATHON_JWT_REFRESH_KEY=$(openssl rand -base64 32)

# AI Provider API Keys
OPENAI_API_KEY=sk-proj-your-openai-key-here
OPENROUTER_API_KEY=sk-or-your-openrouter-key-here
```

**Save and exit** (Ctrl+X, Y, Enter in nano)

#### Step 5: Run Database Migrations

```bash
# Navigate back to root
cd ../..

# Run Prisma migrations
pnpm --filter @autobe/hackathon-server prisma migrate deploy
```

#### Step 6: Start Production Server

**Option A: Direct Start (for testing)**
```bash
cd apps/hackathon-server
pnpm run start
```

**Option B: Using PM2 (recommended for production)**
```bash
# Install PM2 globally
npm install -g pm2

# Create PM2 ecosystem file
cat > ecosystem.config.js << 'EOF'
module.exports = {
  apps: [
    {
      name: 'autobe-server',
      cwd: './apps/hackathon-server',
      script: 'pnpm',
      args: 'run start',
      env: {
        NODE_ENV: 'production'
      },
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '2G'
    }
  ]
};
EOF

# Start with PM2
pm2 start ecosystem.config.js

# Enable startup on boot
pm2 startup
pm2 save

# Monitor logs
pm2 logs autobe-server
```

#### Step 7: Configure Reverse Proxy (Nginx)

**Install Nginx:**
```bash
sudo apt install nginx
```

**Create Nginx configuration:**
```bash
sudo nano /etc/nginx/sites-available/autobe
```

**Paste configuration:**
```nginx
upstream autobe_backend {
    server 127.0.0.1:5888;
}

server {
    listen 80;
    server_name your-domain.com;  # Replace with your domain

    # WebSocket support
    location /ws {
        proxy_pass http://autobe_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }

    # API endpoints
    location /api {
        proxy_pass http://autobe_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Health check
    location /health {
        proxy_pass http://autobe_backend;
    }
}
```

**Enable site and restart Nginx:**
```bash
# Create symbolic link
sudo ln -s /etc/nginx/sites-available/autobe /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Restart Nginx
sudo systemctl restart nginx
```

#### Step 8: Setup SSL (Optional but Recommended)

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx

# Obtain SSL certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal is configured automatically
# Test renewal:
sudo certbot renew --dry-run
```

#### Step 9: Verify Production Deployment

```bash
# Check server status
pm2 status

# Check Nginx status
sudo systemctl status nginx

# Check PostgreSQL
sudo systemctl status postgresql

# Test API endpoint
curl http://localhost:5888/health

# Expected response: {"status": "ok"}
```

---

## 4. VSCode Extension Installation

### 📝 IDE Integration Setup

#### Step 1: Install Extension

**Option A: VSCode Marketplace (when available)**
```
1. Open VSCode
2. Click Extensions icon (or Ctrl+Shift+X)
3. Search: "AutoBE"
4. Click "Install"
```

**Option B: Manual Installation from Source**
```bash
# Clone repository if not already
git clone https://github.com/wrtnlabs/autobe.git
cd autobe

# Navigate to extension directory
cd apps/vscode-extension

# Install dependencies
pnpm install

# Build extension
pnpm run build

# Package as VSIX
pnpm run package
```

**Install VSIX file:**
```
1. Open VSCode
2. Press Ctrl+Shift+P (Cmd+Shift+P on Mac)
3. Type: "Extensions: Install from VSIX..."
4. Select the generated .vsix file
5. Reload VSCode
```

#### Step 2: Configure Extension

**Open Command Palette (Ctrl+Shift+P / Cmd+Shift+P):**
```
1. Type: "AutoBE: Configure"
2. Enter OpenAI or OpenRouter API key
3. Select model (e.g., gpt-4)
4. Set locale (optional)
5. Set timezone (optional)
```

**Alternative: Settings UI**
```
1. Open Settings (Ctrl+,)
2. Search: "AutoBE"
3. Fill in:
   - API Key
   - Model
   - Locale
   - Timezone
```

#### Step 3: Use Extension

**Start AutoBE chat:**
```
1. Open any workspace folder
2. Press Ctrl+Shift+P
3. Type: "AutoBE: Start Chat"
4. Begin describing your backend in the chat panel
```

**Generate from selection:**
```
1. Select text describing requirements
2. Right-click → "AutoBE: Generate from Selection"
3. View generated code in output panel
```

---

## 5. Usage Guide - WebUI

### 💬 Conversation-Driven Development

#### Basic Workflow

**Step 1: Start New Project**

```
1. Open http://localhost:3000
2. Click "New Chat" button
3. Enter project name (e.g., "Todo List API")
```

**Step 2: Requirements Phase**

**Type in chat:**
```
I want to create a todo list API with the following features:
- Users can register and login
- Each user has their own todo lists
- Todo items have title, description, due date, and status
- Users can mark todos as complete
- Support for tags/categories
```

**AutoBE Response:**
```
✓ Analyzing requirements...
✓ Identified 2 actors: User, System
✓ Identified 8 use cases
✓ Generated requirements document

Would you like me to design the database schema?
```

**Step 3: Database Design**

**Type:**
```
Yes, design the database schema
```

**What happens:**
```
✓ Generating Prisma schema...
✓ Creating tables: users, todo_lists, todos, tags
✓ Defining relationships and constraints
✓ Compiling schema... ✓ Success!
✓ Generated ERD diagram

Preview the schema at: /preview/prisma
```

**Step 4: API Specification**

**Type:**
```
Create the API specification
```

**AutoBE generates:**
```
✓ Generating OpenAPI 3.1 spec...
✓ Defining endpoints:
  - POST /api/auth/signup
  - POST /api/auth/login
  - GET /api/todos
  - POST /api/todos
  - PUT /api/todos/:id
  - DELETE /api/todos/:id
  [... more endpoints]
✓ Validating against Prisma schema... ✓ Success!

View specification at: /preview/openapi
```

**Step 5: Test Generation**

**Type:**
```
Generate E2E tests
```

**Result:**
```
✓ Generating test suite...
✓ Created 24 test scenarios
✓ 100% endpoint coverage
✓ Type-safe test validation

Tests available at: /preview/tests
```

**Step 6: Implementation**

**Type:**
```
Implement the API
```

**AutoBE creates:**
```
✓ Generating NestJS controllers...
✓ Generating service providers...
✓ Generating DTOs...
✓ Compiling TypeScript... ✓ Success!
✓ All 156 files generated

Download project: /download/project.zip
```

#### Advanced Features

**Incremental Updates:**
```
User: "Add a priority field to todos"

AutoBE:
✓ Updating Prisma schema...
✓ Updating OpenAPI spec...
✓ Updating tests...
✓ Updating implementation...
✓ Recompilation successful!
```

**Preview Code:**
```
1. Click "Preview" button
2. Browse generated file tree
3. Click any file to view contents
4. Syntax highlighting included
```

**Download Project:**
```
1. Click "Download" button
2. Choose format: .zip or .tar.gz
3. Save to local machine
4. Extract and run:
   - cd project-name
   - npm install
   - npm run start
```

**Replay Conversations:**
```
1. Go to http://localhost:5713/replay/
2. Select saved conversation
3. Watch step-by-step generation
4. Useful for understanding process
```

**Export Artifacts:**
```
Individual downloads:
- Prisma Schema → /download/schema.prisma
- OpenAPI Spec → /download/openapi.json
- Tests → /download/tests.zip
- Full Project → /download/full.zip
```

---

## 6. Usage Guide - Terminal / CLI

### 🖥️ Programmatic API Usage

#### Create Node.js Project

```bash
# Create new project
mkdir my-autobe-project
cd my-autobe-project

# Initialize package.json
npm init -y

# Install AutoBE agent
npm install @autobe/agent @autobe/compiler @autobe/filesystem
npm install openai prisma
```

#### Example Script - Basic Usage

**Create `generate.js`:**

```javascript
const { AutoBeAgent } = require('@autobe/agent');
const { AutoBeCompiler } = require('@autobe/compiler');
const { AutoBeFilesystem } = require('@autobe/filesystem');
const OpenAI = require('openai');

async function main() {
  // Initialize agent
  const agent = new AutoBeAgent({
    vendor: {
      api: new OpenAI({
        apiKey: process.env.OPENAI_API_KEY || 'sk-...'
      }),
      model: 'gpt-4',
      semaphore: 16
    },
    compiler: async () => new AutoBeCompiler(),
    config: {
      locale: 'en-US',
      timezone: 'UTC',
      timeout: null,
      retry: 4
    }
  });

  // Listen to all events
  agent.addEventListener('*', (event) => {
    console.log(`[${event.type}]`, event.data || '');
  });

  // Requirements phase
  console.log('\n=== Phase 1: Requirements Analysis ===');
  await agent.talk(`
    Create a blog platform with:
    - User authentication
    - Posts with title, content, and tags
    - Comments on posts
    - Like/unlike functionality
  `);

  // Database design
  console.log('\n=== Phase 2: Database Design ===');
  await agent.talk('Design the database schema');

  // API specification
  console.log('\n=== Phase 3: API Specification ===');
  await agent.talk('Create the OpenAPI specification');

  // Test generation
  console.log('\n=== Phase 4: Test Generation ===');
  await agent.talk('Generate E2E tests');

  // Implementation
  console.log('\n=== Phase 5: Implementation ===');
  await agent.talk('Implement the API');

  // Save to disk
  console.log('\n=== Saving project to disk ===');
  const files = agent.getFiles();
  await files.write('./output/blog-platform');

  console.log('\n✓ Complete! Project saved to ./output/blog-platform');
}

main().catch(console.error);
```

**Run the script:**
```bash
# Set API key
export OPENAI_API_KEY="sk-..."

# Run script
node generate.js
```

**Expected output:**
```
=== Phase 1: Requirements Analysis ===
[analyze.start]
[analyze.progress] Analyzing user requirements...
[analyze.complete] Analysis document generated

=== Phase 2: Database Design ===
[prisma.start]
[prisma.schema.generated] Schema created
[prisma.compile.success] Validation passed

=== Phase 3: API Specification ===
[interface.start]
[interface.openapi.generated] OpenAPI spec created
[interface.compile.success] Validation passed

=== Phase 4: Test Generation ===
[test.start]
[test.generated] 32 tests created

=== Phase 5: Implementation ===
[realize.start]
[realize.complete] 124 files generated

=== Saving project to disk ===
✓ Complete! Project saved to ./output/blog-platform
```

#### Advanced: Resume from History

```javascript
const fs = require('fs');

// Save conversation history
const history = agent.getHistories();
fs.writeFileSync('history.json', JSON.stringify(history, null, 2));

// Resume later
const savedHistory = JSON.parse(fs.readFileSync('history.json'));
const resumedAgent = new AutoBeAgent({
  vendor: { /* ... */ },
  compiler: async () => new AutoBeCompiler(),
  histories: savedHistory  // Resume from saved state
});

// Continue conversation
await resumedAgent.talk('Add pagination to the posts endpoint');
```

#### Token Usage Tracking

```javascript
const { AutoBeTokenUsage } = require('@autobe/agent');

const tokenUsage = new AutoBeTokenUsage();

const agent = new AutoBeAgent({
  vendor: { /* ... */ },
  compiler: async () => new AutoBeCompiler(),
  tokenUsage: tokenUsage
});

// After generation
console.log('Token Usage:');
console.log('- Prompt tokens:', tokenUsage.prompt);
console.log('- Completion tokens:', tokenUsage.completion);
console.log('- Total tokens:', tokenUsage.total);
console.log('- Estimated cost:', tokenUsage.estimateCost());
```

---

## 7. Advanced Configuration

### 🔧 Custom Compiler Configuration

```javascript
const agent = new AutoBeAgent({
  vendor: { /* ... */ },
  compiler: async (listener) => {
    const compiler = new AutoBeCompiler();
    
    // Custom compiler listeners
    listener.realize.test.onOperation = async (operation) => {
      console.log('Test operation:', operation);
    };
    
    return compiler;
  }
});
```

### 🌍 Multi-Language Support

```javascript
const agent = new AutoBeAgent({
  vendor: { /* ... */ },
  config: {
    locale: 'ko-KR',  // Korean
    timezone: 'Asia/Seoul'
  }
});

await agent.talk('사용자 인증 시스템을 만들어주세요');
```

### ⏱️ Timeout Configuration

```javascript
const agent = new AutoBeAgent({
  vendor: { /* ... */ },
  config: {
    timeout: 10 * 60 * 1000,  // 10 minutes per phase
    retry: 5  // Retry up to 5 times on failure
  }
});
```

### 🔄 Custom Backoff Strategy

```javascript
const agent = new AutoBeAgent({
  vendor: { /* ... */ },
  config: {
    backoffStrategy: ({ count, error }) => {
      // Exponential backoff with jitter
      const baseDelay = 1000;
      const maxDelay = 30000;
      const exponential = Math.min(baseDelay * Math.pow(2, count), maxDelay);
      const jitter = Math.random() * 1000;
      return exponential + jitter;
    }
  }
});
```

### 📊 Event Filtering

```javascript
// Listen to specific events only
agent.addEventListener('prisma.compile.success', (event) => {
  console.log('✓ Database schema validated');
});

agent.addEventListener('error', (event) => {
  console.error('✗ Error:', event.data);
});

// Listen to all phase completions
const phaseEvents = [
  'analyze.complete',
  'prisma.complete',
  'interface.complete',
  'test.complete',
  'realize.complete'
];

phaseEvents.forEach(eventType => {
  agent.addEventListener(eventType, () => {
    console.log(`✓ ${eventType} phase finished`);
  });
});
```

---

## 8. Troubleshooting

### Common Issues and Solutions

#### Issue: "Port 3000 already in use"

**Solution:**
```bash
# Find process using port 3000
lsof -i :3000

# Kill the process
kill -9 <PID>

# Or use different port
PORT=3001 pnpm run playground
```

#### Issue: "pnpm: command not found"

**Solution:**
```bash
# Install pnpm
npm install -g pnpm

# Verify
pnpm --version
```

#### Issue: PostgreSQL connection failed

**Solution:**
```bash
# Check if PostgreSQL is running
sudo systemctl status postgresql

# Start if not running
sudo systemctl start postgresql

# Check connection
psql -h localhost -U autobe -d autobe
```

#### Issue: "Module not found" errors

**Solution:**
```bash
# Clean install
rm -rf node_modules pnpm-lock.yaml
pnpm install

# Rebuild packages
pnpm run build
```

#### Issue: TypeScript compilation errors

**Solution:**
```bash
# Clear TypeScript cache
rm -rf apps/*/lib packages/*/lib

# Rebuild
pnpm run build
```

#### Issue: API key not working

**Solution:**
```bash
# Verify API key format
echo $OPENAI_API_KEY  # Should start with 'sk-'

# Test API key
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"

# Should return list of models
```

#### Issue: Agent gets stuck

**Solution:**
```javascript
// Add timeout to config
const agent = new AutoBeAgent({
  config: {
    timeout: 5 * 60 * 1000,  // 5 minutes
    retry: 3
  }
});
```

#### Issue: High memory usage

**Solution:**
```bash
# Increase Node.js memory limit
export NODE_OPTIONS="--max-old-space-size=4096"

# Run with increased memory
node --max-old-space-size=4096 generate.js
```

### Debug Mode

**Enable verbose logging:**
```bash
# Terminal
DEBUG=autobe:* pnpm run playground

# Or in code
process.env.DEBUG = 'autobe:*';
```

### Check System Requirements

```bash
# Node.js version
node --version  # Should be ≥18.0.0

# pnpm version
pnpm --version  # Should be ≥8.0.0

# Available memory
free -h  # Linux
sysctl hw.memsize  # macOS

# Disk space
df -h
```

---

## 9. Z.ai GLM Deployment (Alternative to OpenAI)

### 🌟 Using Z.ai's GLM Models

AutoBE can use Z.ai's GLM models as a drop-in replacement for OpenAI!

#### Quick Z.ai Deployment

```bash
# Clone AutoBE
git clone https://github.com/wrtnlabs/autobe.git
cd autobe && pnpm install

# Set Z.ai environment variables
export ANTHROPIC_AUTH_TOKEN="your-zai-token"
export ANTHROPIC_BASE_URL="https://api.z.ai/api/anthropic"
export MODEL="glm-4.6"
export API_TIMEOUT_MS="3000000"
```

#### Create Z.ai Demo Script

```javascript
const { AutoBeAgent } = require('@autobe/agent');
const { AutoBeCompiler } = require('@autobe/compiler');
const OpenAI = require('openai');

const agent = new AutoBeAgent({
    vendor: {
        api: new OpenAI({
            apiKey: process.env.ANTHROPIC_AUTH_TOKEN,
            baseURL: process.env.ANTHROPIC_BASE_URL,
            timeout: parseInt(process.env.API_TIMEOUT_MS)
        }),
        model: process.env.MODEL || 'glm-4.6'
    },
    compiler: async () => new AutoBeCompiler()
});

agent.addEventListener('*', (e) => console.log(`[${e.type}]`));

// Generate API
await agent.talk('Create a todo API with user auth');
await agent.talk('Design database');
await agent.talk('Create OpenAPI spec');
await agent.talk('Generate tests');
await agent.talk('Implement with NestJS');

// Save
const files = agent.getFiles();
await files.write('./output/todo-api');
console.log('✅ Generated to ./output/todo-api');
```

#### Available Z.ai Models

- `glm-4.6` - Latest GLM model (recommended)
- `glm-4.5-air` - Lighter, faster variant
- Full OpenAI API compatibility

#### Benefits of Z.ai

- ✅ Lower cost than OpenAI
- ✅ Fast response times
- ✅ No geographic restrictions
- ✅ Drop-in OpenAI replacement
- ✅ Excellent for Chinese language

---

## Summary: Quick Command Reference

### Local Development
```bash
# Clone and install
git clone https://github.com/wrtnlabs/autobe.git
cd autobe && pnpm install

# Start playground
pnpm run playground
# Access: http://localhost:3000
```

### Z.ai Deployment
```bash
# With Z.ai GLM models
export ANTHROPIC_AUTH_TOKEN="your-token"
export ANTHROPIC_BASE_URL="https://api.z.ai/api/anthropic"
export MODEL="glm-4.6"

# Use in any AutoBE script
node your-script.js
```

### Production Deployment
```bash
# Setup PostgreSQL
sudo apt install postgresql
sudo -u postgres createdb autobe

# Configure environment
cd apps/hackathon-server
nano .env.local

# Start with PM2
pm2 start ecosystem.config.js
pm2 save
```

### Programmatic Usage
```bash
# Install
npm install @autobe/agent

# Use in code
const agent = new AutoBeAgent({ /* config */ });
await agent.talk("Create a blog API");
```

---

**Need Help?**
- 📖 Documentation: https://autobe.dev/docs
- 💬 Discord: https://discord.gg/aMhRmzkqCx
- 🐛 Issues: https://github.com/wrtnlabs/autobe/issues
- 📧 Email: support@autobe.dev

---

**Generated by**: Codegen AI Analysis System  
**Date**: November 14, 2025  
**Repository**: https://github.com/Zeeeepa/analyzer
