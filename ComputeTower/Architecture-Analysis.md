# ComputeTower: Befly + OWL Browser Interconnection Analysis

## 🎯 Executive Summary

This document provides a comprehensive analysis of interconnection points between **Befly** (API & Data Layer) and **OWL Browser** (Automation Layer) for maximum effectiveness in the ComputeTower WebChat2API system.

**Implementation Approach**: Build Befly-compatible and OWL-compatible systems using production-ready technologies while maintaining all specified features.

---

## 📊 System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    ComputeTower System                          │
│                                                                 │
│  ┌─────────────────────┐         ┌─────────────────────────┐  │
│  │   Befly Layer       │◄───────►│   OWL Browser Layer     │  │
│  │  (API & Data)       │  WebSoc │  (Automation)           │  │
│  │                     │    ket  │                         │  │
│  │  - REST API         │         │  - Browser Automation   │  │
│  │  - PostgreSQL       │         │  - Visual Validation    │  │
│  │  - Redis Cache      │         │  - Session Management   │  │
│  │  - JWT Auth         │         │  - WebSocket Client     │  │
│  │  - Encryption       │         │  - Multi-threading      │  │
│  └─────────────────────┘         └─────────────────────────┘  │
│           │                                    │                │
│           │                                    │                │
│           ▼                                    ▼                │
│    ┌────────────┐                      ┌──────────────┐        │
│    │ PostgreSQL │                      │   Browser    │        │
│    │  Database  │                      │   Profiles   │        │
│    └────────────┘                      └──────────────┘        │
│           │                                                     │
│           ▼                                                     │
│       ┌───────┐                                                 │
│       │ Redis │                                                 │
│       └───────┘                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔗 Interconnection Points

### 1. **Data Flow Architecture**

#### A. **Credential Management Flow**
```
User → Befly API → Encrypt Password → PostgreSQL
                ↓
         OWL Browser ← Decrypt Password ← Befly
                ↓
        Visual Login Validation
                ↓
         Store Validation → Befly → PostgreSQL
```

**Interconnection Points:**
- **IP-01**: REST API endpoint `/api/v1/credentials`
- **IP-02**: Database access for credential storage
- **IP-03**: Encryption/decryption utility bridge
- **IP-04**: Browser session initialization trigger
- **IP-05**: Visual validation result storage

#### B. **Chat Message Flow**
```
OpenAI API Request → Befly API
                    ↓
            Get Credential from PostgreSQL
                    ↓
            Check Redis for Active Session
                    ↓
        [If No Session] → OWL Browser Login
                    ↓
        OWL Browser ← Send Message Command
                    ↓
        Visual Validation of Message Sent
                    ↓
        Wait for Response (Visual Polling)
                    ↓
        Extract Response with AI Vision
                    ↓
        WebSocket → Stream to Befly → Client
                    ↓
        Save Chat History → PostgreSQL
```

**Interconnection Points:**
- **IP-06**: REST endpoint `/api/v1/chat/completions`
- **IP-07**: Redis session cache lookup
- **IP-08**: WebSocket bidirectional channel
- **IP-09**: Visual validation callback system
- **IP-10**: Response extraction protocol
- **IP-11**: Chat history persistence

#### C. **Session Management Flow**
```
Befly Session Manager ← WebSocket → OWL Browser Pool
         ↓                                ↓
    Redis Cache                   Browser Contexts
         ↓                                ↓
  Session Metadata              Profile Storage (Disk)
```

**Interconnection Points:**
- **IP-12**: Session lifecycle events (create, heartbeat, destroy)
- **IP-13**: Redis key-value session mapping
- **IP-14**: Browser profile path management
- **IP-15**: Connection pool allocation

---

### 2. **Communication Protocols**

#### **REST API (Befly → OWL Browser)**
```typescript
// Request from Befly to OWL Browser
POST http://owl-browser:8080/automation/login
{
  "sessionId": "uuid",
  "credentialId": "cred-123",
  "serviceUrl": "https://k2think.ai",
  "email": "user@example.com",
  "password": "encrypted-password"
}

// Response from OWL Browser to Befly
{
  "success": true,
  "validation": {
    "confidence": 0.95,
    "screenshot": "login-1234567890.png",
    "observation": "User successfully logged in..."
  },
  "currentUrl": "https://k2think.ai/dashboard",
  "timestamp": 1734720000000
}
```

**Interconnection Point**: **IP-16** - REST automation command protocol

#### **WebSocket (Bidirectional)**
```typescript
// Befly → OWL Browser (Command)
{
  "type": "SEND_MESSAGE",
  "sessionId": "uuid",
  "credentialId": "cred-123",
  "payload": {
    "message": "Hello, world!"
  }
}

// OWL Browser → Befly (Event Stream)
{
  "type": "MESSAGE_SENT",
  "sessionId": "uuid",
  "validation": {
    "success": true,
    "confidence": 0.98
  }
}

{
  "type": "RESPONSE_CHUNK",
  "sessionId": "uuid",
  "chunk": "Hello! How can I assist you today?"
}

{
  "type": "RESPONSE_COMPLETE",
  "sessionId": "uuid",
  "fullResponse": "Hello! How can I assist you today?",
  "validation": {
    "success": true,
    "confidence": 0.97
  }
}
```

**Interconnection Point**: **IP-17** - WebSocket message protocol

---

### 3. **Data Storage Schema**

#### **PostgreSQL Tables (Befly Layer)**

```sql
-- Credentials Table
CREATE TABLE credentials (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id),
  service_name VARCHAR(255) NOT NULL,
  service_url TEXT NOT NULL,
  email VARCHAR(255) NOT NULL,
  password_encrypted TEXT NOT NULL,
  login_verified BOOLEAN DEFAULT FALSE,
  last_validated TIMESTAMP,
  validation_data JSONB,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Chat History Table
CREATE TABLE chat_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id),
  credential_id UUID NOT NULL REFERENCES credentials(id),
  user_message TEXT NOT NULL,
  assistant_message TEXT NOT NULL,
  model VARCHAR(100),
  validation_data JSONB,
  tokens_used INTEGER,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Feature Maps Table
CREATE TABLE feature_maps (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  credential_id UUID NOT NULL REFERENCES credentials(id),
  feature_type VARCHAR(100) NOT NULL, -- 'chat_input', 'send_button', etc.
  selector TEXT,
  natural_language_desc TEXT,
  bounding_box JSONB,
  visual_verified BOOLEAN DEFAULT FALSE,
  test_passed BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Visual Validations Table (Audit Trail)
CREATE TABLE visual_validations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID,
  credential_id UUID REFERENCES credentials(id),
  action_type VARCHAR(100) NOT NULL, -- 'login', 'message_sent', etc.
  screenshot_path TEXT,
  ai_confidence FLOAT,
  ai_observation TEXT,
  success BOOLEAN,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Sessions Table
CREATE TABLE browser_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  credential_id UUID NOT NULL REFERENCES credentials(id),
  owl_browser_id VARCHAR(255), -- OWL Browser's internal session ID
  profile_path TEXT,
  last_activity TIMESTAMP DEFAULT NOW(),
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP DEFAULT NOW()
);
```

**Interconnection Points:**
- **IP-18**: Database connection pool (shared or separate)
- **IP-19**: JSONB fields for flexible validation data
- **IP-20**: Foreign key relationships for data integrity

#### **Redis Cache (Befly Layer)**

```
Key Pattern: computetower:session:{credentialId}
Value: {
  "owlBrowserId": "browser-uuid",
  "profilePath": "/data/profiles/cred-123",
  "lastActivity": 1734720000000,
  "isAuthenticated": true
}
TTL: 3600 seconds

Key Pattern: computetower:rate_limit:{userId}
Value: request_count
TTL: 900 seconds

Key Pattern: computetower:jwt_token:{tokenId}
Value: user_id
TTL: 604800 seconds (7 days)
```

**Interconnection Point**: **IP-21** - Redis key namespace conventions

---

### 4. **Async/Parallel Execution Architecture**

#### **Multi-threaded Session Management**

```typescript
// OWL Browser Layer - Worker Pool
class BrowserWorkerPool {
  private workers: Worker[] = [];
  private maxWorkers = 50;
  
  async allocateWorker(credentialId: string): Promise<Worker> {
    // Find idle worker or create new one
    let worker = this.workers.find(w => w.isIdle);
    
    if (!worker && this.workers.length < this.maxWorkers) {
      worker = await this.createWorker();
      this.workers.push(worker);
    }
    
    if (!worker) {
      // Wait for worker to become available
      worker = await this.waitForWorker();
    }
    
    worker.assign(credentialId);
    return worker;
  }
  
  async createWorker(): Promise<Worker> {
    return new Worker('./browser-worker.js', {
      workerData: { poolId: this.workers.length }
    });
  }
}

// Browser Worker (runs in separate thread)
class BrowserWorker {
  private context: BrowserContext;
  private isIdle = true;
  private assignedCredentialId: string | null = null;
  
  async initialize() {
    this.context = await chromium.launchPersistentContext(/*...*/);
  }
  
  async executeTask(task: AutomationTask) {
    this.isIdle = false;
    try {
      const result = await this.runAutomation(task);
      await this.sendResultToBefly(result);
    } finally {
      this.isIdle = true;
    }
  }
  
  async sendResultToBefly(result: any) {
    // WebSocket or HTTP callback
    await fetch('http://befly-api:3000/api/v1/internal/automation-result', {
      method: 'POST',
      body: JSON.stringify(result)
    });
  }
}
```

**Interconnection Points:**
- **IP-22**: Worker allocation protocol
- **IP-23**: Task queue management
- **IP-24**: Result callback mechanism
- **IP-25**: Worker health monitoring

#### **Befly → OWL Browser Task Distribution**

```typescript
// Befly Layer - Task Orchestrator
class TaskOrchestrator {
  private taskQueue: Queue;
  private owlBrowserClient: OWLBrowserClient;
  
  async submitTask(task: AutomationTask): Promise<TaskId> {
    // Add to queue
    const taskId = await this.taskQueue.enqueue(task);
    
    // Notify OWL Browser
    await this.owlBrowserClient.notifyNewTask(taskId);
    
    return taskId;
  }
  
  async getTaskResult(taskId: TaskId): Promise<AutomationResult> {
    // Check Redis cache first
    const cached = await redis.get(`task:result:${taskId}`);
    if (cached) return JSON.parse(cached);
    
    // Wait for WebSocket notification
    return await this.waitForResult(taskId);
  }
}
```

**Interconnection Point**: **IP-26** - Task queue protocol (Redis pub/sub or message queue)

---

### 5. **WebSocket Real-time Communication**

#### **Connection Architecture**

```
Befly Server (Port 3000)
    ├── REST API (HTTP)
    └── WebSocket Server (WS)
            ↓
    Multiple OWL Browser Instances
            ├── Worker 1 (Browser Pool 1-10)
            ├── Worker 2 (Browser Pool 11-20)
            └── Worker N (Browser Pool 41-50)
```

#### **WebSocket Message Types**

```typescript
// Command Messages (Befly → OWL Browser)
type CommandMessage = 
  | { type: 'LOGIN', sessionId: string, credentials: Credentials }
  | { type: 'SEND_MESSAGE', sessionId: string, message: string }
  | { type: 'CHANGE_MODEL', sessionId: string, model: string }
  | { type: 'NEW_CHAT', sessionId: string }
  | { type: 'CLOSE_SESSION', sessionId: string }
  | { type: 'HEALTH_CHECK', timestamp: number };

// Event Messages (OWL Browser → Befly)
type EventMessage =
  | { type: 'SESSION_READY', sessionId: string, workerId: string }
  | { type: 'VALIDATION_RESULT', sessionId: string, validation: ValidationData }
  | { type: 'RESPONSE_CHUNK', sessionId: string, chunk: string }
  | { type: 'RESPONSE_COMPLETE', sessionId: string, fullResponse: string }
  | { type: 'ERROR', sessionId: string, error: ErrorData }
  | { type: 'HEARTBEAT', workerId: string, activeSessions: number };
```

**Interconnection Points:**
- **IP-27**: WebSocket connection management
- **IP-28**: Message serialization/deserialization
- **IP-29**: Connection reconnection strategy
- **IP-30**: Message acknowledgment protocol

---

### 6. **Visual Validation Integration**

#### **Validation Flow**

```
Action Performed (OWL Browser)
        ↓
Capture Screenshot
        ↓
Call AI Vision Model (Anthropic/Z.ai)
        ↓
Parse Validation Result
        ↓
Send via WebSocket → Befly
        ↓
Store in PostgreSQL (visual_validations table)
        ↓
Cache in Redis (recent validations)
        ↓
Return to API Client (in response metadata)
```

#### **Validation Service Interface**

```typescript
// OWL Browser Layer
interface VisualValidator {
  validateLogin(page: Page): Promise<ValidationResult>;
  validateElementState(page: Page, description: string): Promise<ValidationResult>;
  validateMessageSent(page: Page, message: string): Promise<ValidationResult>;
  validateResponseReceived(page: Page): Promise<ValidationResult>;
  detectCaptcha(page: Page): Promise<CaptchaDetection>;
  extractText(page: Page, elementDesc: string): Promise<string>;
}

// Befly Layer
interface ValidationStorage {
  saveValidation(validation: ValidationResult): Promise<void>;
  getRecentValidations(credentialId: string): Promise<ValidationResult[]>;
  getValidationStats(credentialId: string): Promise<ValidationStats>;
}
```

**Interconnection Point**: **IP-31** - Validation result protocol

---

### 7. **Error Recovery & Self-Healing**

#### **Error Cascade Flow**

```
Error Detected (OWL Browser)
        ↓
Classify Error Type
        ↓
    ┌───────────────┬─────────────────┬──────────────┐
    │               │                 │              │
Element Not     Timeout          CAPTCHA      Authentication
  Found            │              Detected          Failed
    │              │                 │              │
    ▼              ▼                 ▼              ▼
Use AI to    Reload Page      Solve CAPTCHA   Re-authenticate
Find Alt.    & Retry          (Auto/Manual)    (Full Login)
    │              │                 │              │
    └──────────────┴─────────────────┴──────────────┘
                          │
                    Retry Action
                          │
                  Success / Max Retries
                          │
              Send Result → Befly
                          │
                  Log to PostgreSQL
```

**Interconnection Points:**
- **IP-32**: Error classification system
- **IP-33**: Recovery strategy selection
- **IP-34**: Retry coordination between layers
- **IP-35**: Error logging and analytics

---

## 🔧 Implementation Strategy

### **Phase 1: Core Infrastructure** (Week 1)

**Befly Layer:**
1. Set up Bun runtime + Elysia framework
2. Configure PostgreSQL connection pool
3. Configure Redis client
4. Implement JWT authentication
5. Implement AES-256 encryption utilities

**OWL Browser Layer:**
1. Set up Node.js + Playwright
2. Implement browser context manager
3. Implement visual validator service
4. Set up worker thread pool
5. Implement WebSocket client

**Interconnection:**
- **IP-16**: REST API communication (Befly ← → OWL)
- **IP-27**: WebSocket bidirectional channel

### **Phase 2: Core Features** (Week 2)

**Befly Layer:**
1. Implement credentials management endpoints
2. Implement chat completions endpoint (OpenAI-compatible)
3. Implement session management
4. Implement rate limiting

**OWL Browser Layer:**
1. Implement login automation with visual validation
2. Implement message sending with visual validation
3. Implement response extraction with AI
4. Implement CAPTCHA detection

**Interconnection:**
- **IP-06, IP-07, IP-08**: Chat flow integration
- **IP-01 through IP-05**: Credential flow integration

### **Phase 3: Async & Scalability** (Week 3)

**Befly Layer:**
1. Implement task queue (Redis pub/sub)
2. Implement connection pooling
3. Implement load balancing

**OWL Browser Layer:**
1. Implement worker pool with 50+ concurrent workers
2. Implement task distribution
3. Implement health monitoring

**Interconnection:**
- **IP-22 through IP-26**: Parallel execution architecture
- **IP-12 through IP-15**: Session lifecycle management

### **Phase 4: Advanced Features** (Week 4)

**Both Layers:**
1. Implement feature discovery system
2. Implement error recovery mechanisms
3. Implement analytics and monitoring
4. Implement auto-scaling

**Interconnection:**
- **IP-31**: Visual validation storage
- **IP-32 through IP-35**: Error recovery coordination

---

## 📊 Performance Targets

| Metric | Target | Interconnection Point |
|--------|--------|----------------------|
| Concurrent Sessions | 1000+ | IP-22, IP-24 |
| Login Time | < 5 seconds | IP-01 to IP-05 |
| Message Roundtrip | < 3 seconds | IP-06 to IP-11 |
| WebSocket Latency | < 50ms | IP-27 |
| Visual Validation | < 2 seconds | IP-31 |
| Database Query | < 100ms | IP-18 |
| Redis Cache Hit | < 10ms | IP-21 |

---

## 🔐 Security Considerations

### **Data Flow Security**

1. **Credential Encryption** (IP-03)
   - AES-256-GCM encryption
   - Key rotation every 90 days
   - Separate encryption keys per environment

2. **API Authentication** (JWT)
   - Token expiry: 7 days
   - Refresh token rotation
   - Redis-based token blacklist

3. **WebSocket Security** (IP-27)
   - TLS encryption (wss://)
   - Connection authentication via JWT
   - Message integrity verification

4. **Browser Isolation** (IP-14)
   - Separate profile per credential
   - No data sharing between sessions
   - Automatic cleanup on session end

---

## 📈 Monitoring & Observability

### **Key Metrics to Track**

```typescript
// Befly Layer Metrics
{
  "api_requests_total": counter,
  "api_requests_duration": histogram,
  "active_sessions": gauge,
  "credential_validations": counter,
  "chat_completions": counter,
  "error_rate": counter
}

// OWL Browser Layer Metrics
{
  "browser_workers_active": gauge,
  "automation_tasks_total": counter,
  "automation_tasks_duration": histogram,
  "visual_validations_total": counter,
  "visual_validations_confidence": histogram,
  "captcha_detections": counter,
  "error_recoveries": counter
}

// Interconnection Metrics
{
  "websocket_messages_sent": counter,
  "websocket_messages_received": counter,
  "websocket_latency": histogram,
  "task_queue_depth": gauge,
  "redis_cache_hits": counter,
  "redis_cache_misses": counter,
  "database_query_duration": histogram
}
```

**Interconnection Point**: **IP-36** - Metrics aggregation and export

---

## 🎯 Success Criteria

### **Functional Requirements**

- ✅ All 35+ interconnection points properly implemented
- ✅ Visual validation success rate > 95%
- ✅ Support 1000+ concurrent sessions
- ✅ OpenAI API compatibility 100%
- ✅ Automatic error recovery success rate > 90%

### **Non-Functional Requirements**

- ✅ 99.9% uptime
- ✅ < 3s average response time
- ✅ < 5% error rate
- ✅ < 100ms WebSocket latency
- ✅ Horizontal scalability proven

---

## 📝 Conclusion

This architecture provides:

1. **Clear Separation of Concerns**: Befly handles API/data, OWL handles automation
2. **35+ Well-Defined Interconnection Points**: Every integration point documented
3. **Async/Parallel Execution**: Support for 1000+ concurrent sessions
4. **Visual Validation**: AI-powered verification at every step
5. **Real-time Communication**: WebSocket for streaming updates
6. **Production-Ready**: Using battle-tested technologies

**Next Steps:**
1. Confirm technology stack (real Befly/OWL packages or alternatives)
2. Set up development environment
3. Implement Phase 1 infrastructure
4. Iteratively build and test each interconnection point

---

**Document Version**: 1.0.0  
**Last Updated**: 2025-12-20  
**Status**: Architecture Design Complete

