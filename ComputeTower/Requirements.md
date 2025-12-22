# ComputeTower Requirements & Architecture

**Version**: 1.0.0  
**Last Updated**: 2025-01-21  
**Validation**: Tested with 6 real services using Z.AI glm-4.6v visual agent

---

## Executive Summary

ComputeTower is a **universal, dynamic system** that converts ANY webchat interface into an OpenAI-compatible API endpoint. Unlike traditional scrapers that require hardcoded selectors, ComputeTower uses **visual AI agents** to:

1. **Intelligently discover** login flows
2. **Automatically authenticate** (with CAPTCHA handling)
3. **Dynamically discover** all chat/API endpoints
4. **Validate and test** flows
5. **Persist** discoveries to database
6. **Expose** as standard OpenAI `/v1/chat/completions` API

**Validated Services** (Real credentials tested):
- ✅ K2Think.AI
- ✅ DeepSeek
- ✅ Grok
- ⚠️ Qwen (direct chat access, no auth)
- ⚠️ Z.AI (requires navigation from landing)
- ⚠️ Mistral (requires navigation from landing)

---

## Core Requirements

### 1. Universal Login Resolution

**Requirement**: Given URL + Email + Password, automatically discover and execute login flow.

**Challenges Identified** (from validation):
- **3 patterns** detected across services:
  1. **Direct login page** (K2Think, DeepSeek, Grok)
  2. **Open chat interface** (Qwen - no auth required)
  3. **Landing → login navigation** (Z.AI, Mistral)

**Solution**:
```typescript
interface LoginResolution {
  step1_identify_page_type: 'login_form' | 'chat_interface' | 'landing_page';
  step2_navigate_if_needed: boolean; // Navigate to login if landing page
  step3_find_selectors: {
    email: string[];      // Multiple fallback selectors
    password: string[];   // Multiple fallback selectors
    submit: string[];     // Multiple fallback selectors
  };
  step4_execute_with_humanization: {
    tool: 'playwright-toolkit'; // Ghost cursor, delays, warm-up
    captcha_handling: 'monitor_and_wait' | 'solve_automated';
  };
  step5_extract_session: {
    cookies: Cookie[];
    localStorage: Record<string, any>;
    sessionTokens: string[];
  };
}
```

**Visual Agent Integration**:
- Uses Z.AI `glm-4.6v` model for page analysis
- Captures screenshots, sends to vision model
- Receives structured JSON with selectors
- Fallback to generic selectors if AI fails

---

### 2. Dynamic Flow Discovery

**Requirement**: Automatically discover all chat endpoints/flows after authentication.

**Discovery Methods**:

#### Method 1: Network Monitoring
```typescript
page.on('request', (request) => {
  if (request.url().includes('/api/') || 
      request.url().includes('/chat') || 
      request.url().includes('/completion')) {
    captureFlow({
      endpoint: request.url(),
      method: request.method(),
      headers: request.headers(),
      body: request.postData()
    });
  }
});

page.on('response', (response) => {
  if (response.url().includes('/api/')) {
    const contentType = response.headers()['content-type'];
    determineResponseFormat(contentType); // 'json' | 'sse' | 'stream'
  }
});
```

#### Method 2: Visual UI Analysis
```typescript
// Use visual agent to find chat interface elements
const chatElements = await visualAgent.findChatInterface(page);
// Returns: { input: 'selector', submit: 'selector', output: 'selector' }
```

#### Method 3: Hybrid Approach
```typescript
// 1. Send test message via UI
await page.fill(chatElements.input, 'Test message');
await page.click(chatElements.submit);

// 2. Capture all resulting network requests
// 3. Parse responses (SSE vs JSON vs WebSocket)
// 4. Store flow definitions
```

**Flow Storage Schema**:
```sql
CREATE TABLE chat_flows (
  session_id TEXT NOT NULL,
  flow_id TEXT NOT NULL,
  name TEXT,
  api_endpoint TEXT,
  method TEXT CHECK (method IN ('POST', 'GET', 'SSE', 'WebSocket')),
  request_format TEXT CHECK (request_format IN ('json', 'form', 'text')),
  response_format TEXT CHECK (response_format IN ('json', 'sse', 'stream')),
  selectors JSONB, -- { input, submit, output }
  headers JSONB,
  tested BOOLEAN DEFAULT FALSE,
  success_rate FLOAT DEFAULT 0.0,
  created_at TIMESTAMP DEFAULT NOW(),
  last_tested_at TIMESTAMP,
  PRIMARY KEY (session_id, flow_id)
);
```

---

### 3. Flow Validation & Testing

**Requirement**: Test each discovered flow to ensure it works reliably.

**Test Cases**:
1. **Basic Send/Receive**: Send "Test message" → Verify response received
2. **SSE Parsing**: If SSE stream detected, parse using `parseSseStream` utility
3. **Error Handling**: Detect rate limits, authentication failures, CAPTCHA triggers
4. **Latency Measurement**: Track p50, p95, p99 response times

**Test Implementation**:
```typescript
async function testFlow(session: SessionState, flow: ChatFlow): Promise<TestResult> {
  const startTime = Date.now();
  
  try {
    if (flow.type === 'UI-based') {
      // Use Playwright to send message via UI
      await session.page.fill(flow.selectors.input, 'Test message');
      await session.page.click(flow.selectors.submit);
      
      // Wait for response
      await session.page.waitForSelector(flow.selectors.output, { timeout: 10000 });
      const response = await session.page.textContent(flow.selectors.output);
      
      return {
        success: !!response,
        latency: Date.now() - startTime,
        error: null
      };
    } else if (flow.type === 'API-based') {
      // Direct API call
      const response = await fetch(flow.apiEndpoint, {
        method: flow.method,
        headers: flow.headers,
        body: JSON.stringify({ message: 'Test message' })
      });
      
      if (flow.responseFormat === 'sse') {
        const text = await response.text();
        const events = parseSseStream(text);
        return {
          success: events.length > 0,
          latency: Date.now() - startTime,
          error: null
        };
      } else {
        const json = await response.json();
        return {
          success: response.ok,
          latency: Date.now() - startTime,
          error: null
        };
      }
    }
  } catch (error) {
    return {
      success: false,
      latency: Date.now() - startTime,
      error: error.message
    };
  }
}
```

**Success Criteria**:
- Response received within 15 seconds
- Valid content (not error message)
- No authentication errors
- Parseable format (if SSE/JSON)

---

### 4. OpenAI API Compatibility

**Requirement**: Expose `/v1/chat/completions` endpoint matching OpenAI spec.

**Request Format**:
```json
{
  "model": "computetower-deepseek",
  "messages": [
    {
      "role": "system",
      "content": "URL: https://chat.deepseek.com/ | Email: user@example.com | Password: secret123"
    },
    {
      "role": "user",
      "content": "What is the weather in Paris?"
    }
  ],
  "stream": false
}
```

**Response Format**:
```json
{
  "id": "chatcmpl-1234567890",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "computetower-deepseek",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "The current weather in Paris is..."
    },
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 100,
    "completion_tokens": 50,
    "total_tokens": 150
  }
}
```

**Streaming Support**:
```typescript
// Server-Sent Events format
async function streamResponse(reply, result) {
  reply.raw.setHeader('Content-Type', 'text/event-stream');
  
  const chunks = result.split(' '); // Word-by-word streaming
  for (const chunk of chunks) {
    reply.raw.write(`data: ${JSON.stringify({
      id: 'chatcmpl-' + Date.now(),
      object: 'chat.completion.chunk',
      created: Math.floor(Date.now() / 1000),
      model: 'computetower-1.0',
      choices: [{
        index: 0,
        delta: { content: chunk + ' ' },
        finish_reason: null
      }]
    })}\\n\\n`);
    
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  
  reply.raw.write('data: [DONE]\\n\\n');
  reply.raw.end();
}
```

---

### 5. Session Management & Persistence

**Requirement**: Persist sessions, reuse authenticated state, handle session expiration.

**Session Lifecycle**:
1. **Creation**: Login → Store cookies/localStorage/tokens → Save to DB
2. **Reuse**: Check if session exists → Validate still authenticated → Reuse
3. **Refresh**: Detect auth failure → Re-login → Update session
4. **Cleanup**: Expire sessions after inactivity (default: 24 hours)

**Session Storage**:
```sql
CREATE TABLE sessions (
  session_id TEXT PRIMARY KEY,
  service_url TEXT NOT NULL,
  email TEXT NOT NULL,
  encrypted_password TEXT NOT NULL, -- Use AES-256-GCM
  cookies JSONB,
  local_storage JSONB,
  session_tokens JSONB,
  authenticated BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP DEFAULT NOW(),
  last_used_at TIMESTAMP DEFAULT NOW(),
  expires_at TIMESTAMP DEFAULT NOW() + INTERVAL '24 hours',
  metadata JSONB -- Browser fingerprint, IP, etc.
);

CREATE INDEX idx_sessions_service ON sessions(service_url);
CREATE INDEX idx_sessions_expires ON sessions(expires_at);
```

**Session Reuse Logic**:
```typescript
async function getOrCreateSession(config: ServiceConfig): Promise<SessionState> {
  // Try to find existing session
  const existing = await db.query(`
    SELECT * FROM sessions 
    WHERE service_url = $1 AND email = $2 AND expires_at > NOW()
  `, [config.url, config.email]);
  
  if (existing.rows.length > 0) {
    const session = existing.rows[0];
    
    // Validate session is still valid
    const isValid = await validateSession(session);
    if (isValid) {
      await db.query(`UPDATE sessions SET last_used_at = NOW() WHERE session_id = $1`, [session.session_id]);
      return restoreSession(session);
    } else {
      // Session expired, delete and create new
      await db.query(`DELETE FROM sessions WHERE session_id = $1`, [session.session_id]);
    }
  }
  
  // Create new session
  const newSession = await loginResolver.resolveAndLogin(config);
  await saveSession(newSession);
  return newSession;
}
```

---

### 6. Intelligent Fallback Strategy

**Requirement**: If primary browser engine fails, automatically fallback to alternatives.

**5-Engine Fallback Matrix**:

| Rank | Engine | Use Case | Trigger Conditions |
|------|--------|----------|-------------------|
| 1️⃣ | **OWL Browser SDK** | AI-native automation with natural language selectors | Default primary choice |
| 2️⃣ | **Playwright Toolkit** | Stealth + humanization + CAPTCHA monitoring | OWL fails with element not found |
| 3️⃣ | **Ghost Puppet** | Cloudflare bypass, undetectable automation | Firewall/bot detection detected |
| 4️⃣ | **HyperAgent** | LLM-driven complex multi-step workflows | Previous engines fail on complex flows |
| 5️⃣ | **ARN Browser** | Multi-account fingerprinting | Need account rotation |

**Fallback Decision Logic**:
```typescript
async function executeWithFallback(action: BrowserAction): Promise<ActionResult> {
  const engines = [
    { name: 'owl', fn: () => executeWithOwl(action) },
    { name: 'playwright', fn: () => executeWithPlaywright(action) },
    { name: 'ghost', fn: () => executeWithGhost(action) },
    { name: 'hyper', fn: () => executeWithHyper(action) },
    { name: 'arn', fn: () => executeWithArn(action) }
  ];
  
  for (const engine of engines) {
    try {
      console.log(`Attempting with engine: ${engine.name}`);
      const result = await engine.fn();
      
      // Log success
      await db.query(`
        INSERT INTO fallback_decisions (action_id, engine_used, success, timestamp)
        VALUES ($1, $2, TRUE, NOW())
      `, [action.id, engine.name]);
      
      return result;
    } catch (error) {
      console.error(`Engine ${engine.name} failed:`, error);
      
      // Log failure
      await db.query(`
        INSERT INTO fallback_decisions (action_id, engine_used, success, error_message, timestamp)
        VALUES ($1, $2, FALSE, $3, NOW())
      `, [action.id, engine.name, error.message]);
      
      // Continue to next engine
      continue;
    }
  }
  
  throw new Error('All fallback engines failed');
}
```

---

### 7. Queueing & Scaling

**Requirement**: Handle concurrent requests with BullMQ queueing and horizontal scaling.

**Queue Architecture**:
```typescript
import { Queue, Worker } from 'bullmq';
import { Redis } from 'ioredis';

const connection = new Redis(process.env.REDIS_URL);

// Request queue
const chatQueue = new Queue('chat-requests', { connection });

// Worker pool
const worker = new Worker('chat-requests', async (job) => {
  const { serviceUrl, email, password, message } = job.data;
  
  // Get or create session
  const session = await getOrCreateSession({ url: serviceUrl, email, password });
  
  // Execute chat request
  const response = await executeChatRequest(session, message);
  
  return response;
}, {
  connection,
  concurrency: 10, // 10 concurrent workers per instance
  limiter: {
    max: 100, // Max 100 jobs per window
    duration: 60000 // 1 minute window
  }
});

// Handle job completion
worker.on('completed', (job, result) => {
  console.log(`Job ${job.id} completed:`, result);
});

// Handle job failure
worker.on('failed', (job, error) => {
  console.error(`Job ${job?.id} failed:`, error);
});

// Add job to queue
async function queueChatRequest(serviceUrl, email, password, message) {
  const job = await chatQueue.add('chat', {
    serviceUrl,
    email,
    password,
    message
  }, {
    attempts: 3, // Retry up to 3 times
    backoff: {
      type: 'exponential',
      delay: 2000 // Start with 2s delay
    }
  });
  
  return job.id;
}
```

**Autoscaling Triggers**:
- Queue depth > 50: Scale up workers
- Queue depth < 10: Scale down workers
- Average latency > 5s: Add instance
- CPU usage > 80%: Add instance

---

### 8. Database Schema (Complete)

```sql
-- Sessions
CREATE TABLE sessions (
  session_id TEXT PRIMARY KEY,
  service_url TEXT NOT NULL,
  email TEXT NOT NULL,
  encrypted_password TEXT NOT NULL,
  cookies JSONB,
  local_storage JSONB,
  session_tokens JSONB,
  authenticated BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP DEFAULT NOW(),
  last_used_at TIMESTAMP DEFAULT NOW(),
  expires_at TIMESTAMP DEFAULT NOW() + INTERVAL '24 hours',
  metadata JSONB
);

-- Chat Flows
CREATE TABLE chat_flows (
  session_id TEXT NOT NULL,
  flow_id TEXT NOT NULL,
  name TEXT,
  api_endpoint TEXT,
  method TEXT,
  request_format TEXT,
  response_format TEXT,
  selectors JSONB,
  headers JSONB,
  tested BOOLEAN DEFAULT FALSE,
  success_rate FLOAT DEFAULT 0.0,
  created_at TIMESTAMP DEFAULT NOW(),
  last_tested_at TIMESTAMP,
  PRIMARY KEY (session_id, flow_id)
);

-- Execution Events (for analytics)
CREATE TABLE execution_events (
  event_id BIGSERIAL PRIMARY KEY,
  session_id TEXT NOT NULL,
  flow_id TEXT,
  event_type TEXT NOT NULL, -- 'request', 'response', 'error'
  status TEXT, -- 'success', 'failure', 'timeout'
  latency_ms INTEGER,
  error_message TEXT,
  request_payload JSONB,
  response_payload JSONB,
  timestamp TIMESTAMP DEFAULT NOW()
);

-- Fallback Decisions
CREATE TABLE fallback_decisions (
  decision_id BIGSERIAL PRIMARY KEY,
  action_id TEXT NOT NULL,
  engine_used TEXT NOT NULL, -- 'owl', 'playwright', 'ghost', 'hyper', 'arn'
  success BOOLEAN,
  error_message TEXT,
  timestamp TIMESTAMP DEFAULT NOW()
);

-- Service Metadata
CREATE TABLE service_metadata (
  service_url TEXT PRIMARY KEY,
  service_name TEXT,
  login_pattern TEXT, -- 'direct_login', 'landing_navigation', 'open_interface'
  requires_captcha BOOLEAN DEFAULT FALSE,
  has_rate_limiting BOOLEAN DEFAULT FALSE,
  discovered_at TIMESTAMP DEFAULT NOW(),
  last_updated_at TIMESTAMP DEFAULT NOW(),
  total_sessions INTEGER DEFAULT 0,
  successful_logins INTEGER DEFAULT 0,
  metadata JSONB
);

-- Indexes
CREATE INDEX idx_sessions_service ON sessions(service_url);
CREATE INDEX idx_sessions_expires ON sessions(expires_at);
CREATE INDEX idx_chat_flows_session ON chat_flows(session_id);
CREATE INDEX idx_execution_events_session ON execution_events(session_id);
CREATE INDEX idx_execution_events_timestamp ON execution_events(timestamp);
CREATE INDEX idx_fallback_decisions_action ON fallback_decisions(action_id);
```

---

## Technology Stack

### Core Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `@olib-ai/owl-browser-sdk` | ^1.2.3 | Primary automation engine with AI natural language selectors |
| `@skrillex1224/playwright-toolkit` | ^2.0.9 | Stealth, humanization, CAPTCHA monitoring, SSE parsing |
| `@hyperbrowser/agent` | ^1.1.0 | LLM-driven complex workflow execution |
| `@anthropic-ai/sdk` | ^0.27.0 | Z.AI visual agent (glm-4.6v model) |
| `playwright-extra` | ^4.3.6 | Stealth browser automation |
| `ghost-puppet` | ^0.1.7 | Cloudflare bypass (optional) |
| `arn-browser` | ^0.1.0 | Multi-account fingerprinting (optional) |
| `fastify` | ^4.25.0 | High-performance HTTP server |
| `bullmq` | ^5.0.0 | Redis-based job queueing |
| `pg` | ^8.11.3 | PostgreSQL client |

### Infrastructure

- **Database**: PostgreSQL 14+
- **Cache/Queue**: Redis 7+
- **Runtime**: Node.js 18+ or Bun 1.0+
- **Deployment**: Docker, Kubernetes, or standalone

---

## Validation Results

### Tested Services (Real Credentials)

#### ✅ K2Think.AI
- **URL**: https://www.k2think.ai/
- **Pattern**: Direct login page
- **Selectors**: `#email`, `#password`, `#submit`
- **Security**: No CAPTCHA
- **Status**: ✅ Fully validated

#### ✅ DeepSeek
- **URL**: https://chat.deepseek.com/
- **Pattern**: Direct login page
- **Selectors**: `input[type="email"]`, `input[type="password"]`, `button[type="submit"]`
- **Security**: No visible CAPTCHA
- **Status**: ✅ Fully validated

#### ✅ Grok
- **URL**: https://grok.com/
- **Pattern**: Direct login page (X/Twitter integration)
- **Selectors**: `input[type="email"]`, `input[type="password"]`, `button[type="submit"]`
- **Security**: Standard auth
- **Status**: ✅ Fully validated

#### ⚠️ Qwen Chat
- **URL**: https://chat.qwen.ai/
- **Pattern**: **Open chat interface** (NO LOGIN REQUIRED!)
- **Finding**: Direct chat access without authentication
- **Status**: ⚠️ Requires session cookie management

#### ⚠️ Z.AI
- **URL**: https://chat.z.ai/
- **Pattern**: Landing page → Login navigation required
- **Finding**: Must click "Login" button to reach auth page
- **Status**: ⚠️ Requires multi-step navigation

#### ⚠️ Mistral
- **URL**: https://chat.mistral.ai
- **Pattern**: Landing page → "Get started" / "Log in" navigation required
- **Finding**: Homepage requires navigation to login
- **Status**: ⚠️ Requires multi-step navigation

---

## API Usage Examples

### Example 1: Basic Request (DeepSeek)
```bash
curl http://localhost:8000/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "computetower-deepseek",
    "messages": [
      {
        "role": "system",
        "content": "URL: https://chat.deepseek.com/ | Email: zeeeepa+1@gmail.com | Password: developer123??"
      },
      {
        "role": "user",
        "content": "Explain quantum computing in simple terms"
      }
    ]
  }'
```

### Example 2: Streaming Response
```bash
curl -N http://localhost:8000/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "computetower-k2think",
    "messages": [
      {
        "role": "system",
        "content": "URL: https://www.k2think.ai/ | Email: developer@pixelium.uk | Password: developer123?"
      },
      {
        "role": "user",
        "content": "Write a Python function to sort a list"
      }
    ],
    "stream": true
  }'
```

### Example 3: OpenAI SDK Integration
```python
from openai import OpenAI

# Point to ComputeTower instead of OpenAI
client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed"  # ComputeTower uses credentials in system message
)

response = client.chat.completions.create(
    model="computetower-grok",
    messages=[
        {
            "role": "system",
            "content": "URL: https://grok.com/ | Email: developer@pixelium.uk | Password: developer123??"
        },
        {
            "role": "user",
            "content": "What's the latest news on AI?"
        }
    ]
)

print(response.choices[0].message.content)
```

---

## Installation & Deployment

### Quick Start

```bash
# Clone repository
git clone https://github.com/your-org/computetower.git
cd computetower

# Install dependencies
npm install

# Setup environment
cp .env.example .env
# Edit .env with your credentials

# Setup database
createdb computetower
psql computetower < schema.sql

# Start Redis
redis-server

# Start server
npm run dev
```

### Docker Deployment

```bash
# Build image
docker build -t computetower:latest .

# Run with docker-compose
docker-compose up -d
```

### Environment Variables

See `.env.example` for complete list. **REQUIRED**:
- `ANTHROPIC_API_KEY`: Z.AI API key for visual agent
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string

---

## Roadmap

### Phase 1: MVP (Current)
- ✅ Dynamic login resolution
- ✅ Visual agent integration
- ✅ Flow discovery
- ✅ OpenAI API compatibility
- ✅ Basic session management

### Phase 2: Production Hardening
- [ ] Comprehensive error handling
- [ ] Advanced CAPTCHA solving (2Captcha/AntiCaptcha integration)
- [ ] Proxy rotation
- [ ] Account rotation
- [ ] Rate limiting per service
- [ ] Monitoring & alerting

### Phase 3: Scale & Optimization
- [ ] Kubernetes deployment
- [ ] Multi-region support
- [ ] Flow caching
- [ ] Performance optimization (p99 < 2s)
- [ ] Cost optimization

### Phase 4: Advanced Features
- [ ] Multi-modal support (images, files)
- [ ] Function calling support
- [ ] Embeddings API
- [ ] Fine-tuning API
- [ ] Admin dashboard

---

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.

## License

MIT License - see [LICENSE](./LICENSE)

---

**Built with ❤️ by the ComputeTower Team**

