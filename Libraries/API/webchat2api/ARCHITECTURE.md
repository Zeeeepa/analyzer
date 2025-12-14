# Universal Dynamic Web Chat Automation Framework - Architecture

## 🏗️ **System Architecture Overview**

```
┌─────────────────────────────────────────────────────────────────┐
│                        API Gateway Layer                         │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────┐ │
│  │ /v1/chat/        │  │ /v1/models       │  │ /admin/       │ │
│  │ completions      │  │                  │  │ providers     │ │
│  └────────┬─────────┘  └────────┬─────────┘  └───────┬───────┘ │
└───────────┼────────────────────┼─────────────────────┼──────────┘
            │                    │                     │
┌───────────▼────────────────────▼─────────────────────▼──────────┐
│                     Orchestration Layer                          │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │          Session Manager (Context Pooling)               │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │          Provider Registry (Dynamic Discovery)           │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
            │                    │                     │
┌───────────▼────────────────────▼─────────────────────▼──────────┐
│                     Discovery & Automation Layer                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ Vision Engine   │  │ Network         │  │ CAPTCHA Solver  │ │
│  │ (GLM-4.5v)      │  │ Interceptor     │  │ (2Captcha)      │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ Selector Cache  │  │ Response        │  │ DOM Observer    │ │
│  │ (SQLite)        │  │ Detector        │  │ (MutationObs)   │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
            │                    │                     │
┌───────────▼────────────────────▼─────────────────────▼──────────┐
│                        Browser Layer                             │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │          Playwright Browser Pool (Contexts)              │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │          Anti-Detection (Fingerprint Randomization)      │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
            │                    │                     │
            ▼                    ▼                     ▼
     ┌──────────┐         ┌──────────┐         ┌──────────┐
     │ Z.AI     │         │ ChatGPT  │         │ Claude   │
     └──────────┘         └──────────┘         └──────────┘
```

---

## 📦 **Component Descriptions**

### **1. API Gateway Layer**

**Purpose:** External interface for consumers (OpenAI SDK, HTTP clients)

**Components:**

**1.1 Chat Completions Handler (`pkg/api/chat_completions.go`)**
- Receives OpenAI-format requests
- Validates request format
- Routes to appropriate provider
- Streams responses back in real-time
- Handles errors and timeouts

**1.2 Models Handler (`pkg/api/models.go`)**
- Lists available models (discovered from providers)
- Returns model capabilities
- Maps internal provider names to OpenAI format

**1.3 Admin Handler (`pkg/api/admin.go`)**
- Provider registration
- Provider management (list, delete)
- Manual discovery trigger
- Cache invalidation

**Technologies:**
- Go `net/http` or Gin framework
- SSE streaming via `http.Flusher`
- JSON encoding/decoding

---

### **2. Orchestration Layer**

**Purpose:** Coordinates high-level workflows and resource management

**Components:**

**2.1 Session Manager (`pkg/session/manager.go`)**
- Browser context pooling
- Session lifecycle management
- Idle session recycling
- Health checks
- Load balancing across contexts

**Session Pool Strategy:**
```go
type SessionPool struct {
    Available   chan *Session  // Ready-to-use sessions
    Active      map[string]*Session  // In-use sessions
    MaxSessions int
    Provider    *Provider
}
```

**2.2 Provider Registry (`pkg/provider/registry.go`)**
- Store discovered provider configurations
- Manage provider lifecycle
- Cache selector mappings
- Track provider health

**Provider Model:**
```go
type Provider struct {
    ID            string
    URL           string
    Name          string
    Selectors     *SelectorCache
    AuthMethod    AuthMethod
    StreamMethod  StreamMethod
    LastValidated time.Time
    FailureCount  int
}
```

---

### **3. Discovery & Automation Layer**

**Purpose:** Vision-driven UI understanding and interaction

**Components:**

**3.1 Vision Engine (`pkg/vision/engine.go`)**

**Responsibilities:**
- Screenshot analysis
- Element detection (input, button, response area)
- CAPTCHA detection
- UI state understanding

**Vision Prompts:**
```
Prompt 1: "Identify the chat input field where users type messages."
Prompt 2: "Locate the submit/send button for sending messages."
Prompt 3: "Find the response area where AI messages appear."
Prompt 4: "Detect if there's a CAPTCHA challenge present."
```

**Integration:**
```go
type VisionEngine struct {
    APIEndpoint string  // GLM-4.5v API
    Cache       *ResultCache
}

func (v *VisionEngine) DetectElements(screenshot []byte) (*ElementMap, error)
func (v *VisionEngine) DetectCAPTCHA(screenshot []byte) (*CAPTCHAInfo, error)
func (v *VisionEngine) ValidateSelector(screenshot []byte, selector string) (bool, error)
```

**3.2 Network Interceptor (`pkg/browser/interceptor.go`)** ✅ IMPLEMENTED

**Responsibilities:**
- Capture HTTP/HTTPS traffic
- Intercept SSE streams
- Monitor WebSocket connections
- Log network patterns

**Current Implementation:**
- Route-based interception
- Response body capture
- Thread-safe storage
- Pattern matching

**3.3 Response Detector (`pkg/response/detector.go`)**

**Responsibilities:**
- Auto-detect streaming method (SSE, WebSocket, XHR, DOM)
- Parse response format
- Detect completion signals
- Assemble chunked responses

**Detection Flow:**
```
1. Analyze network traffic patterns
2. Check for SSE (text/event-stream)
3. Check for WebSocket upgrade
4. Check for XHR polling
5. Fall back to DOM observation
6. Return detected method + config
```

**3.4 Selector Cache (`pkg/cache/selector_cache.go`)**

**Responsibilities:**
- Store discovered selectors
- Calculate stability scores
- Manage TTL and invalidation
- Provide fallback selectors

**Cache Structure:**
```go
type SelectorCache struct {
    Domain       string
    Selectors    map[string]*Selector
    LastUpdated  time.Time
    ValidationCount int
    FailureCount int
}

type Selector struct {
    CSS       string
    XPath     string
    Fallbacks []string
    Stability float64
}
```

**3.5 CAPTCHA Solver (`pkg/captcha/solver.go`)**

**Responsibilities:**
- Detect CAPTCHA type (reCAPTCHA, hCaptcha, Cloudflare)
- Submit to 2Captcha API
- Poll for solution
- Apply solution to page

**Integration:**
```go
type CAPTCHASolver struct {
    APIKey       string
    SolveTimeout time.Duration
}

func (c *CAPTCHASolver) Solve(captchaType string, siteKey string, pageURL string) (string, error)
```

**3.6 DOM Observer (`pkg/dom/observer.go`)**

**Responsibilities:**
- Set up MutationObserver on response container
- Detect text additions
- Detect typing indicators
- Fallback response capture method

---

### **4. Browser Layer**

**Purpose:** Headless browser management with anti-detection

**Components:**

**4.1 Browser Pool (`pkg/browser/pool.go`)** ✅ PARTIAL IMPLEMENTATION

**Current Features:**
- Playwright-Go integration
- Anti-detection measures
- User-Agent rotation
- GPU randomization

**Enhancements Needed:**
- Context pooling (currently conceptual)
- Session isolation
- Resource limits

**4.2 Anti-Detection (`pkg/browser/stealth.go`)**

**Techniques:**
- WebDriver property masking
- Canvas fingerprint randomization
- WebGL vendor/renderer spoofing
- Navigator properties override
- Battery API masking
- Screen resolution variation

**Based on:** `Zeeeepa/example` bot-detection bypass research

---

## 🔄 **Data Flow Examples**

### **Flow 1: New Provider Registration**

```
1. User calls: POST /admin/providers
   {
     "url": "https://chat.z.ai",
     "email": "user@example.com",
     "password": "pass123"
   }

2. Orchestration Layer:
   - Create new Provider record
   - Allocate browser context from pool
   
3. Discovery Layer:
   - Navigate to URL
   - Take screenshot
   - Vision Engine: Detect login form
   - Fill credentials
   - Handle CAPTCHA if present
   - Navigate to chat interface
   
4. Discovery Layer (continued):
   - Take screenshot of chat interface
   - Vision Engine: Detect input, submit, response area
   - Test send/receive flow
   - Network Interceptor: Detect streaming method
   
5. Orchestration Layer:
   - Save selectors to cache
   - Mark provider as active
   - Return provider ID
   
6. Response: { "provider_id": "z-ai-123", "status": "active" }
```

### **Flow 2: Chat Completion Request (Cached)**

```
1. Client: POST /v1/chat/completions
   {
     "model": "z-ai-gpt",
     "messages": [{"role": "user", "content": "Hello!"}]
   }

2. API Gateway:
   - Validate request
   - Resolve model → provider (z-ai-123)
   
3. Session Manager:
   - Get available session from pool
   - Or create new session from cached selectors
   
4. Automation:
   - Fill input (cached selector)
   - Click submit (cached selector)
   - Network Interceptor: Capture response
   
5. Response Detector:
   - Parse SSE stream (detected method)
   - Transform to OpenAI format
   - Stream back to client
   
6. Session Manager:
   - Return session to pool (idle)
   
7. Client receives:
   data: {"choices":[{"delta":{"content":"Hello"}}]}
   data: {"choices":[{"delta":{"content":" there!"}}]}
   data: [DONE]
```

### **Flow 3: Selector Failure & Recovery**

```
1. Automation attempts to click submit
2. Selector fails (element not found)
3. Session Manager:
   - Increment failure count
   - Check if threshold reached (3 failures)
   
4. If threshold reached:
   - Trigger re-discovery
   - Vision Engine: Take screenshot
   - Vision Engine: Find submit button
   - Update selector cache
   - Retry automation
   
5. If retry succeeds:
   - Reset failure count
   - Mark selector as validated
   
6. If retry fails:
   - Mark provider as unhealthy
   - Notify admin
   - Use fallback selector
```

---

## 🗄️ **Data Models**

### **Provider Model**
```go
type Provider struct {
    ID            string    `json:"id"`
    URL           string    `json:"url"`
    Name          string    `json:"name"`
    CreatedAt     time.Time `json:"created_at"`
    LastValidated time.Time `json:"last_validated"`
    Status        string    `json:"status"` // active, unhealthy, disabled
    Credentials   *Credentials `json:"-"` // encrypted
    Selectors     *SelectorCache `json:"selectors"`
    StreamMethod  string    `json:"stream_method"` // sse, websocket, xhr, dom
    AuthMethod    string    `json:"auth_method"` // email_password, oauth, none
}
```

### **Session Model**
```go
type Session struct {
    ID            string
    ProviderID    string
    BrowserContext playwright.BrowserContext
    Page          playwright.Page
    Cookies       []*http.Cookie
    CreatedAt     time.Time
    LastUsedAt    time.Time
    Status        string // idle, active, expired
}
```

### **Selector Cache Model**
```go
type SelectorCache struct {
    Domain          string
    DiscoveredAt    time.Time
    LastValidated   time.Time
    ValidationCount int
    FailureCount    int
    StabilityScore  float64
    Selectors       map[string]*Selector
}

type Selector struct {
    Name      string   // "input", "submit", "response"
    CSS       string
    XPath     string
    Stability float64
    Fallbacks []string
}
```

---

## 🔐 **Security Architecture**

### **Credential Encryption**
```go
// AES-256-GCM encryption
func EncryptCredentials(plaintext string, key []byte) ([]byte, error)
func DecryptCredentials(ciphertext []byte, key []byte) (string, error)
```

### **Secrets Management**
- Master key from environment variable
- Rotate keys every 90 days
- No plaintext storage
- Secure memory zeroing

### **Browser Sandboxing**
- Each context isolated
- No cross-context data leakage
- Process-level isolation via Playwright
- Resource limits (CPU, memory)

---

## 📊 **Monitoring & Observability**

### **Metrics (Prometheus)**
```
# Request metrics
http_requests_total{endpoint, status}
http_request_duration_seconds{endpoint}

# Provider metrics
provider_discovery_duration_seconds{provider}
provider_selector_cache_hits_total{provider}
provider_selector_cache_misses_total{provider}
provider_failure_count{provider}

# Session metrics
active_sessions{provider}
session_pool_size{provider}
session_creation_duration_seconds{provider}

# Vision metrics
vision_api_calls_total{operation}
vision_api_latency_seconds{operation}
```

### **Logging (Structured JSON)**
```json
{
  "timestamp": "2024-12-05T20:00:00Z",
  "level": "info",
  "component": "session_manager",
  "provider_id": "z-ai-123",
  "action": "session_created",
  "session_id": "sess-abc-123",
  "duration_ms": 1234
}
```

---

## 🚀 **Deployment Architecture**

### **Single Instance**
```
┌─────────────────────┐
│  Gateway Server     │
│  (Go Binary)        │
│  ├─ API Layer       │
│  ├─ Browser Pool    │
│  └─ SQLite DB       │
└─────────────────────┘
```

### **Horizontally Scaled**
```
         ┌─────────────┐
         │ Load Balancer│
         └──────┬──────┘
                │
    ┌───────────┼───────────┐
    │           │           │
┌───▼───┐   ┌───▼───┐   ┌───▼───┐
│Gateway│   │Gateway│   │Gateway│
│  #1   │   │  #2   │   │  #3   │
└───┬───┘   └───┬───┘   └───┬───┘
    │           │           │
    └───────────┼───────────┘
                │
         ┌──────▼──────┐
         │  PostgreSQL │
         │  (Shared DB)│
         └─────────────┘
```

### **Container Deployment (Docker)**
```dockerfile
FROM golang:1.22-alpine AS builder
# Build Go binary

FROM mcr.microsoft.com/playwright:v1.52.0-focal
# Install Playwright browsers
COPY --from=builder /app/gateway /usr/local/bin/
CMD ["gateway"]
```

---

## 🔄 **Failover & Recovery**

### **Provider Failure**
1. Detect failure (3 consecutive errors)
2. Mark provider as unhealthy
3. Trigger re-discovery
4. Retry with new selectors
5. If still fails, disable provider

### **Session Failure**
1. Detect session expired
2. Destroy browser context
3. Create new session
4. Re-authenticate
5. Resume chat

### **Network Failure**
1. Detect network timeout
2. Retry with exponential backoff
3. Max 3 retries
4. Return error to client

---

**Version:** 1.0  
**Last Updated:** 2024-12-05  
**Status:** Draft

