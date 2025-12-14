# Universal Dynamic Web Chat Automation Framework - Requirements

**Version:** 2.0  
**Last Updated:** 2024-12-14  
**Status:** Production-Ready Specification

---

## 🎯 **Core Mission**

Build a **vision-driven, fully dynamic web chat automation gateway** that can:
- Work with ANY web chat interface (existing and future)
- Auto-discover UI elements using multimodal AI
- Detect and adapt to different response streaming methods
- Provide OpenAI-compatible API for universal integration
- Cache discoveries for performance while maintaining adaptability

---

## 📋 **Functional Requirements**

### **FR1: Universal Provider Support**

**FR1.1: Dynamic Provider Registration**
- Accept URL + optional credentials (email/password)
- Automatically navigate to chat interface
- No hardcoded provider-specific logic
- Support for both authenticated and unauthenticated chats

**FR1.2: Target Providers (Examples, Not Exhaustive)**
- ✅ Z.AI (https://chat.z.ai)
- ✅ ChatGPT (https://chat.openai.com)
- ✅ Claude (https://claude.ai)
- ✅ Mistral (https://chat.mistral.ai)
- ✅ DeepSeek (https://chat.deepseek.com)
- ✅ Gemini (https://gemini.google.com)
- ✅ AI Studio (https://aistudio.google.com)
- ✅ Qwen (https://qwen.ai)
- ✅ K2Think (https://k2think.ai)
- ✅ Grok (https://grok.com)
- ✅ Any future chat interface

**FR1.3: Provider Lifecycle**
```
1. Registration → 2. Discovery → 3. Validation → 4. Caching → 5. Active Use
```

---

### **FR2: Vision-Based UI Discovery**

**FR2.1: Element Detection**
Using GLM-4.5v or compatible vision models, automatically detect:

**Primary Elements (Required):**
- Chat input field (textarea, contenteditable, input)
- Submit button (send, enter, arrow icon)
- Response area (message container, output div)
- New chat button (start new conversation)

**Secondary Elements (Optional):**
- Model selector dropdown
- Temperature/parameter controls
- System prompt input
- File upload button
- Image generation controls
- Plugin/skill/MCP selectors
- Settings panel

**Tertiary Elements (Advanced):**
- File tree structure (AI Studio example)
- Code editor contents
- Chat history sidebar
- Context window indicator
- Token counter
- Export/share buttons

**FR2.2: CAPTCHA Handling**
- Automatic detection of CAPTCHA challenges
- Integration with 2Captcha API for solving
- Support for: reCAPTCHA v2/v3, hCaptcha, Cloudflare Turnstile
- Fallback: Pause and log for manual intervention
- ML-based CAPTCHA solving (95% free alternative)

**FR2.3: Login Flow Automation**
- Vision-based detection of login forms
- Email/password field identification
- OAuth button detection (Google, GitHub, etc.)
- 2FA/MFA handling (pause and wait for code)
- Session cookie persistence

---

### **FR3: Response Capture & Streaming**

**FR3.1: Auto-Detect Streaming Method**

Analyze network traffic and DOM to detect:

**Method A: Server-Sent Events (SSE)**
- Monitor for `text/event-stream` content-type
- Intercept SSE connections
- Parse `data:` fields and detect `[DONE]` markers
- Example: ChatGPT, many OpenAI-compatible APIs

**Method B: WebSocket**
- Detect WebSocket upgrade requests
- Intercept `ws://` or `wss://` connections
- Capture bidirectional messages
- Example: Claude, some real-time chats

**Method C: XHR Polling**
- Monitor repeated XHR requests to same endpoint
- Detect polling patterns (intervals)
- Aggregate responses
- Example: Older chat interfaces

**Method D: DOM Mutation Observation**
- Set up MutationObserver on response container
- Detect text node additions/changes
- Fallback for client-side rendering
- Example: SPA frameworks with no network streams

**Method E: Hybrid Detection**
- Use multiple methods simultaneously
- Choose most reliable signal
- Graceful degradation

**FR3.2: Streaming Response Assembly**
- Capture partial responses as they arrive
- Detect completion signals:
  - `[DONE]` marker (SSE)
  - Connection close (WebSocket)
  - Button re-enable (DOM)
  - Typing indicator disappear (visual)
- Handle incomplete chunks (buffer and reassemble)
- Deduplicate overlapping content

---

### **FR4: Selector Caching & Stability**

**FR4.1: Selector Storage**
```json
{
  "domain": "chat.z.ai",
  "discovered_at": "2024-12-05T20:00:00Z",
  "last_validated": "2024-12-05T21:30:00Z",
  "validation_count": 150,
  "failure_count": 2,
  "stability_score": 0.987,
  "selectors": {
    "input": {
      "css": "textarea[data-testid='chat-input']",
      "xpath": "//textarea[@placeholder='Message']",
      "stability": 0.95,
      "fallbacks": ["textarea.chat-input", "#message-input"]
    },
    "submit": {
      "css": "button[aria-label='Send message']",
      "xpath": "//button[contains(@class, 'send')]",
      "stability": 0.90,
      "fallbacks": ["button[type='submit']"]
    }
  }
}
```

**FR4.2: Cache Invalidation Strategy**
- TTL: 7 days by default
- Validate on every 10th request
- Auto-invalidate on 3 consecutive failures
- Manual invalidation via API

**FR4.3: Selector Stability Scoring**
Based on Samelogic research:
- ID selectors: 95% stability
- data-test attributes: 90%
- Unique class combinations: 65-85%
- Position-based (nth-child): 40%
- Basic tags: 30%

**Scoring Formula:**
```
stability_score = (successful_validations / total_attempts) * selector_type_weight
```

---

### **FR5: OpenAI API Compatibility**

**FR5.1: Supported Endpoints**
- `POST /v1/chat/completions` - Primary chat endpoint
- `GET /v1/models` - List available models (discovered)
- `POST /admin/providers` - Register new provider
- `GET /admin/providers` - List registered providers
- `DELETE /admin/providers/{id}` - Remove provider

**FR5.2: Request Format**
```json
{
  "model": "gpt-4", 
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello!"}
  ],
  "stream": true,
  "temperature": 0.7,
  "max_tokens": 2000
}
```

**FR5.3: Response Format (Streaming)**
```
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1702000000,"model":"gpt-4","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1702000000,"model":"gpt-4","choices":[{"index":0,"delta":{"content":" there"},"finish_reason":null}]}

data: [DONE]
```

**FR5.4: Response Format (Non-Streaming)**
```json
{
  "id": "chatcmpl-123",
  "object": "chat.completion",
  "created": 1702000000,
  "model": "gpt-4",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello there! How can I help you?"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 15,
    "total_tokens": 25
  }
}
```

**FR5.5: Tool Calling Support**
- Detection of provider tool calling support
- Native tool injection (GPT-4, Claude, Gemini formats)
- System message injection in code format
- Tool result handling (message continuations)
- Auto-detection of provider response format
- Format mapping to OpenAI standard
- Support for Claude, Gemini, and other formats

---

### **FR6: Session Management**

**FR6.1: Multi-Session Support**
- Concurrent sessions per provider
- Session isolation (separate browser contexts)
- Session pooling (reuse idle sessions)
- Max sessions per provider (configurable)

**FR6.2: Session Lifecycle**
```
Created → Authenticated → Active → Idle → Expired → Destroyed
```

**FR6.3: Session Persistence**
- Save cookies to SQLite
- Store localStorage/sessionStorage data
- Persist IndexedDB (if needed)
- Session health checks (periodic validation)

**FR6.4: New Chat Functionality**
- Detect "new chat" button
- Click to start fresh conversation
- Clear context window
- Maintain session authentication

---

### **FR7: Error Handling & Recovery**

**FR7.1: Error Categories**

**Category A: Network Errors**
- Timeout (30s default)
- Connection refused
- DNS resolution failed
- SSL certificate invalid
- **Recovery:** Retry with exponential backoff (3 attempts)

**Category B: Authentication Errors**
- Invalid credentials
- Session expired
- CAPTCHA required
- Rate limited
- **Recovery:** Re-authenticate, solve CAPTCHA, wait for rate limit

**Category C: Discovery Errors**
- Vision API timeout
- No elements found
- Ambiguous elements (multiple matches)
- Selector invalid
- **Recovery:** Re-run discovery with refined prompts, use fallback selectors

**Category D: Automation Errors**
- Element not interactable
- Element not visible
- Click intercepted
- Navigation failed
- **Recovery:** Wait and retry, scroll into view, use JavaScript click

**Category E: Response Errors**
- No response detected
- Partial response
- Malformed response
- Stream interrupted
- **Recovery:** Re-send message, use fallback detection method

---

### **FR8: Browser Automation & Anti-Detection**

**FR8.1: Three-Tier Anti-Detection Strategy**

**Tier 1 (Native Stealth):**
- Built-in browser stealth features
- No automation signals
- Natural browser behavior

**Tier 2 (Fingerprints):**
- Real Chrome fingerprints (10,000+ pool)
- Dynamic fingerprint generation
- OS-specific patterns
- Browser version matching

**Tier 3 (Headers/UA):**
- User-agent rotation (100+ patterns)
- Consistent header sets
- Viewport and screen resolution matching
- Language and timezone consistency

**FR8.2: Browser Profile Management**
- Consistent browser properties
- Canvas fingerprinting bypass
- WebGL vendor/renderer spoofing
- Navigator property override
- Plugin and MIME type handling

**FR8.3: Behavioral Mimicry**
- Human-like mouse movements
- Realistic typing delays (50-150ms per character)
- Random scroll patterns
- Natural page interaction timing

---

### **FR9: Multi-Platform Support**

**FR9.1: Social Media Platforms**
- Discord (login flow, message sending)
- Slack (authentication, workspace navigation)
- WhatsApp Web (QR code handling, contacts)
- Microsoft Teams (email login, channel navigation)
- Telegram Web (phone verification, messaging)

**FR9.2: AI Chat Platforms**
- K2Think.ai
- Qwen (chat.qwen.ai)
- DeepSeek (chat.deepseek.com)
- Grok (grok.com)
- Z.ai (chat.z.ai)
- Mistral AI (chat.mistral.ai)

**FR9.3: Platform Extensibility**
- Custom platform framework
- YAML workflow configuration
- Step types: navigate, type, click, press_key, wait, scroll, extract
- Variable substitution mechanism

---

### **FR10: Advanced Management Features**

**FR10.1: WebUI Dashboard**
- Real-time request monitoring
- Browser viewport streaming (15-30fps)
- Network traffic visualization
- Console logs in real-time
- Manual debugging controls

**FR10.2: Configuration Management**
- Global settings (API, scaling, browser, CAPTCHA)
- Per-endpoint settings (URL, auth, discovery mode)
- Model mapping configuration
- Rate limiting rules
- Proxy and timeout controls

**FR10.3: Analytics Dashboard**
- Total requests, success rate, failures
- Request volume graphs (24h, 7d, 30d)
- Response time distribution
- Top endpoints by traffic
- Error breakdown by category
- Export capabilities (CSV, JSON)

---

## 🔧 **Non-Functional Requirements**

### **NFR1: Performance**
- First token latency: <3 seconds (vision-based)
- First token latency: <500ms (cached selectors)
- Selector cache hit rate: >90%
- Vision API calls: <10% of requests
- Concurrent sessions: 100+ per instance
- Request throughput: 1000+ requests/hour

### **NFR2: Reliability**
- Uptime: 99.5%
- Error recovery success rate: >95%
- Selector stability: >85%
- Auto-heal from failures: <30 seconds
- Session failure rate: <5%

### **NFR3: Scalability**
- Horizontal scaling via browser context pooling
- Stateless API (sessions in database)
- Support 1000+ concurrent chat conversations
- Provider registration: unlimited
- Auto-scaling based on load (1-100 sessions per endpoint)

### **NFR4: Security**
- Credentials encrypted at rest (AES-256)
- HTTPS only for external communication
- No logging of user messages (opt-in only)
- Sandbox browser processes
- Regular security audits
- JWT-based authentication
- API key management

### **NFR5: Maintainability**
- Modular architecture (easy to add providers)
- Comprehensive logging (structured JSON)
- Metrics and monitoring (Prometheus)
- Documentation (inline + external)
- Self-healing capabilities
- Code coverage >80%

### **NFR6: Observability**
- Distributed tracing (OpenTelemetry)
- Metrics collection (request/response times)
- Log aggregation (ELK stack compatible)
- Health check endpoints
- Real-time monitoring dashboards

### **NFR7: Cost Optimization**
- Session pooling and reuse
- CAPTCHA optimization (95% free ML model)
- Vision caching (7-day TTL)
- Headless mode efficiency (30% CPU reduction)
- Batch vision requests
- Target: <$2 per 1,000 requests (vs $8+ without optimization)

---

## 🚀 **Success Criteria**

### **MVP Success:**
- ✅ Register 3 different providers (Z.AI, ChatGPT, Claude)
- ✅ Auto-discover UI elements with >90% accuracy
- ✅ Capture streaming responses correctly
- ✅ OpenAI SDK works transparently
- ✅ Handle authentication flows
- ✅ Cache selectors for performance

### **Production Success:**
- ✅ Support 10+ providers without code changes
- ✅ 95% selector cache hit rate
- ✅ <2s average response time
- ✅ Handle CAPTCHA automatically
- ✅ 99.5% uptime
- ✅ Self-heal from 95% of errors
- ✅ Process 10,000+ requests/day

---

## 📦 **Out of Scope (Future Work)**

- ❌ Voice input/output
- ❌ Video chat automation
- ❌ Mobile app automation (iOS/Android)
- ❌ Desktop app automation (Electron, etc.)
- ❌ Multi-user collaboration features
- ❌ Fine-tuning provider models
- ❌ Custom plugin development UI

---

## 🔗 **Integration Points**

### **Upstream Dependencies:**
- Playwright (browser automation)
- GLM-4.5v API (vision/CAPTCHA detection)
- 2Captcha API (CAPTCHA solving)
- SQLite (session storage)
- Redis (caching layer)

### **Downstream Consumers:**
- OpenAI Python SDK
- OpenAI Node.js SDK
- Any HTTP client supporting SSE
- cURL, Postman, etc.
- Custom API integrations

---

## 📊 **Technical Specifications**

### **Supported Programming Languages:**
- Primary: Python (DrissionPage, backend services)
- Secondary: Go (high-performance services, RPC layer)
- TypeScript (web dashboard, browser extensions)

### **Database Requirements:**
- SQLite: Session persistence, selector cache
- Redis: Real-time caching, rate limiting
- PostgreSQL: Production deployment (optional)

### **Browser Requirements:**
- Chrome/Chromium 120+
- Playwright-compatible browsers
- Headless mode support
- CDP (Chrome DevTools Protocol) access

### **API Requirements:**
- RESTful HTTP/1.1
- Server-Sent Events (SSE) support
- WebSocket support
- OpenAPI 3.0 specification

---

**Document Control:**
- **Created:** 2024-12-05
- **Updated:** 2024-12-14
- **Version:** 2.0
- **Status:** Production-Ready Specification
- **Approval:** Pending Implementation

