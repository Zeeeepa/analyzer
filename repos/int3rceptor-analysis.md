# Repository Analysis: int3rceptor

**Analysis Date**: 2025-12-27
**Repository**: Zeeeepa/int3rceptor
**Description**: ⚡ Rust-powered HTTP/HTTPS intercepting proxy for penetration testing. Modern Burp Suite alternative with Vue.js UI. Real-time traffic analysis, fuzzing & request repeater.

---

## Executive Summary

Int3rceptor is a proprietary, high-performance HTTP/HTTPS intercepting proxy designed for security professionals and penetration testers. Built with Rust for the backend and Vue.js 3 for the frontend, it provides a modern alternative to tools like Burp Suite. The project features TLS MITM capabilities, automated fuzzing (Intruder), a powerful rule engine, WebSocket interception, and real-time traffic analysis. The codebase is well-structured with a clean separation between core logic, API, CLI, and UI components, demonstrating professional software engineering practices with approximately 2,410 lines of Rust code.

## Repository Overview

- **Primary Language**: Rust (backend), TypeScript/JavaScript (frontend)
- **Framework**: Rust (Axum, Hyper, Tokio), Vue.js 3 (TypeScript, Vite)
- **License**: Proprietary (Free for personal/non-commercial use, commercial license required)
- **Architecture**: Monorepo with workspace structure (core, api, cli, ui)
- **Lines of Code**: ~2,410 LOC (Rust backend)
- **Last Analysis**: December 2025
- **Project Status**: Active development (v2.0 released)

### Key Technologies

**Backend Stack:**
```toml
- Tokio 1.35 (async runtime)
- Hyper 1.0 (HTTP)
- Axum 0.7 (web framework)
- Rustls 0.22 (TLS)
- SQLite via Rusqlite (storage)
- Regex 1.10 (pattern matching)
```

**Frontend Stack:**
```json
- Vue 3.4+ (UI framework)
- TypeScript 5.4 (type safety)
- Vite 5.0 (build tool)
- Axios 1.6.7 (HTTP client)
- Highlight.js 11.11 (syntax highlighting)
```


## Architecture & Design Patterns

### High-Level Architecture

Int3rceptor follows a **split architecture** with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────┐
│                    User Browser                          │
│                  (Proxy Traffic)                         │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────────────┐
│              Rust Proxy Server (core)                   │
│  ┌──────────────────────────────────────────────────┐  │
│  │  - TLS MITM (Certificate Manager)                │  │
│  │  - Connection Pool (HTTP/HTTPS)                  │  │
│  │  - Rule Engine (Traffic Modification)            │  │
│  │  - Scope Manager (Traffic Filtering)             │  │
│  │  - Capture Storage (SQLite)                      │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────────────┐
│              Axum API Server (api)                      │
│  ┌──────────────────────────────────────────────────┐  │
│  │  - RESTful API Endpoints                         │  │
│  │  - WebSocket for Real-time Updates               │  │
│  │  - Intruder Engine (Fuzzing)                     │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────────────┐
│              Vue.js Frontend (ui)                       │
│  ┌──────────────────────────────────────────────────┐  │
│  │  - Traffic Tab (Request/Response Viewer)         │  │
│  │  - Intruder Tab (Fuzzing UI)                     │  │
│  │  - Rules Tab (Traffic Modification)              │  │
│  │  - Scope Tab (Filtering)                         │  │
│  │  - Repeater Tab (Manual Request Replay)          │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

### Design Patterns Identified

1. **Workspace Pattern (Cargo)**: Monorepo structure with three workspace members
   ```toml
   [workspace]
   members = ["core", "api", "cli"]
   ```

2. **Shared State with Arc<RwLock>**: Thread-safe state management
   ```rust
   pub struct RuleEngine {
       rules: Arc<RwLock<Vec<Rule>>>,
       regex_cache: Arc<RwLock<HashMap<String, Regex>>>,
   }
   ```

3. **Service Layer Pattern**: Clear separation between proxy logic, API layer, and UI

4. **Strategy Pattern**: Multiple attack types in Intruder
   ```rust
   pub enum AttackType {
       Sniper,      // One payload set, iterate through each position
       Battering,   // One payload set, same payload in all positions
       Pitchfork,   // Multiple payload sets, iterate in parallel
       ClusterBomb, // Multiple payload sets, all combinations
   }
   ```

5. **Caching Pattern**: Regex compilation caching for performance
   ```rust
   fn get_regex(&self, pattern: &str) -> Option<Regex> {
       // Check cache first, compile and cache if not found
   }
   ```

6. **Connection Pool Pattern**: Reusable HTTP client connections
   ```rust
   pub struct ConnectionPool {
       // Manages HTTP client instances
   }
   ```

### Module Organization

**Core Module (`interceptor/core/src/`):**
- `proxy.rs` - Main proxy server logic with TLS MITM
- `cert_manager.rs` - Dynamic certificate generation
- `rules.rs` - Traffic modification engine with regex support
- `intruder.rs` - Automated fuzzing engine
- `scope.rs` - Traffic filtering logic
- `capture.rs` - Request/response capture
- `storage.rs` - SQLite persistence
- `websocket.rs` - WebSocket frame interception
- `tls.rs` - TLS handshake handling
- `connection_pool.rs` - HTTP client pooling

**API Module (`interceptor/api/src/`):**
- `main.rs` - Entry point with state initialization
- `routes.rs` - RESTful API endpoints
- `websocket.rs` - Real-time WebSocket communication
- `auth.rs` - Optional API token authentication
- `models.rs` - Request/response DTOs

**CLI Module (`interceptor/cli/src/`):**
- `main.rs` - Command-line interface

**UI Module (`interceptor/ui/src/`):**
- Component-based Vue.js architecture
- TypeScript composables for API integration


## Core Features & Functionalities

### 1. **HTTP/HTTPS Proxy with TLS MITM**
- Full HTTP and HTTPS proxy server on port 8080
- Dynamic certificate generation using rcgen
- Automatic CA certificate management
- CONNECT method handling for SSL tunneling

### 2. **Intruder/Fuzzer Engine**
Four automated attack modes:
- **Sniper**: Iterates one payload through each position
- **Battering Ram**: Uses same payload in all positions
- **Pitchfork**: Multiple payloads in parallel
- **Cluster Bomb**: All payload combinations

### 3. **Rule Engine with Regex**
Advanced traffic modification:
- URL/Header/Body pattern matching (substring and regex)
- Replace/Set/Remove actions
- Regex capture groups support ($1, $2, etc.)
- Intelligent regex compilation caching

### 4. **WebSocket Interception (v2.0)**
- Full frame capture (Text, Binary, Ping/Pong)
- Bidirectional monitoring
- Connection tracking

### 5. **Request Repeater**
- Manual request replay with modifications
- Header, body, URL, method customization
- Response capture and display

### 6. **Scope Management**
- Include/Exclude URL patterns
- Traffic filtering based on domain/path

### 7. **Real-time UI (Vue.js)**
- Live traffic viewing via WebSocket
- Syntax-highlighted request/response viewer
- Interactive configuration panels

## Entry Points & Initialization

### Main Entry Point: `interceptor/api/src/main.rs`

```rust
#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt().with_env_filter("info").init();

    // 1. Database initialization
    let storage = Arc::new(CaptureStorage::new(db_path)?);
    let capture = Arc::new(RequestCapture::with_storage(10_000, Some(storage.clone())));

    // 2. Core components
    let cert_manager = Arc::new(CertManager::new()?);
    let rules = Arc::new(RuleEngine::new());
    let scope = Arc::new(ScopeManager::new());
    let intruder = Arc::new(Intruder::new());
    let ws_capture = Arc::new(WsCapture::new(10_000));

    // 3. Configuration from environment
    let api_token = std::env::var("INTERCEPTOR_API_TOKEN").ok().map(Arc::new);
    let max_body_bytes = std::env::var("INTERCEPTOR_MAX_BODY_BYTES")
        .ok().and_then(|v| v.parse().ok()).unwrap_or(2 * 1024 * 1024);

    // 4. State assembly
    let state = AppState { capture, cert_manager, pool: ConnectionPool::new(), 
                           rules, scope, intruder, ws_capture, api_token, ... };

    // 5. Start API server
    serve(state, addr).await
}
```

### Configuration Sources
- **Environment Variables**: `INTERCEPTOR_DB_PATH`, `INTERCEPTOR_API_TOKEN`, `INTERCEPTOR_MAX_BODY_BYTES`, `INTERCEPTOR_MAX_CONCURRENCY`, `API_ADDR`
- **Defaults**: Database at `data/interceptor.sqlite`, API on `127.0.0.1:3000`, Proxy on port 8080

## Data Flow Architecture

### Request Interception Flow

```
Browser → Proxy Server (8080) → TLS Interceptor (MITM)
   ↓
Scope Filter → Rule Engine (modify request) → Connection Pool
   ↓
Internet → Response → Rule Engine (modify response)
   ↓
Capture Storage (SQLite) + WebSocket → Vue.js UI
```

### Data Storage

**SQLite Database Schema:**
- Captured requests (method, URL, headers, body, timestamp)
- Captured responses (status, headers, body, duration)
- Indexed by request ID for fast retrieval

**In-Memory Storage:**
- Recent 10,000 requests in ring buffer (LRU eviction)
- WebSocket frames (10,000 limit)
- Active rules and scope configuration

### Data Transformations

1. **Capture**: HTTP/HTTPS → `CapturedRequest` struct
2. **Storage**: Struct → SQLite row
3. **Query**: SQLite → JSON (API endpoint)
4. **WebSocket**: Real-time events → JSON stream
5. **Repeater**: JSON → Modified HTTP request

## CI/CD Pipeline Assessment

**Suitability Score**: 6/10

### Current Pipeline (GitHub Actions)

```yaml
# .github/workflows/ci.yml
jobs:
  test-backend:
    - cargo fmt --check
    - cargo clippy --all-targets --all-features -- -D warnings
    - cargo test --verbose
    - cargo build --release

  test-frontend:
    - npm ci (in ui/)
    - npm run type-check
    - npm run build

  security-audit:
    - cargo audit (continue-on-error: true)
```

### Strengths ✅
- Automated formatting checks (rustfmt)
- Linter integration (clippy with -D warnings)
- Separate backend and frontend workflows
- Security audit with cargo-audit
- Release builds tested

### Weaknesses ❌
- **No Test Coverage Reporting**: Only 1 test file found (`core/tests/https_example.rs`)
- **No Integration Tests**: No end-to-end testing of proxy functionality
- **Security Audit Non-Blocking**: `continue-on-error: true` allows vulnerabilities to pass
- **No Deployment Automation**: Manual release process
- **Missing Docker CI**: Docker images not built in CI
- **No Performance Benchmarks**: No automated perf testing

### Recommendations
1. Add comprehensive test suite (unit + integration)
2. Enable test coverage reporting (tarpaulin/grcov)
3. Make security audit blocking
4. Add Docker build and push to registry
5. Implement automated releases with changelogs
6. Add performance regression tests

## Dependencies & Technology Stack

### Backend Dependencies (Rust)

**Core Dependencies:**
| Package | Version | Purpose |
|---------|---------|---------|
| tokio | 1.35 | Async runtime |
| hyper | 1.0 | HTTP/1.1 and HTTP/2 |
| axum | 0.7 | Web framework |
| rustls | 0.22 | Pure Rust TLS |
| rcgen | 0.12 | Certificate generation |
| rusqlite | 0.29 | SQLite bindings |
| regex | 1.10 | Pattern matching |
| serde/serde_json | 1.0 | Serialization |
| tracing | 0.1 | Logging |
| anyhow/thiserror | 1.0 | Error handling |

**Shared workspace dependencies ensure version consistency across modules.**

### Frontend Dependencies (Vue.js)

| Package | Version | Purpose |
|---------|---------|---------|
| vue | ^3.4.0 | UI framework |
| axios | ^1.6.7 | HTTP client |
| highlight.js | ^11.11.1 | Syntax highlighting |
| vite | ^5.0.0 | Build tool |
| typescript | ^5.4.0 | Type safety |
| vue-tsc | ^2.0.0 | Type checking |

### Dependency Health
- All dependencies use modern, actively maintained versions
- No known critical vulnerabilities detected
- Rust dependencies benefit from memory safety
- Vue 3 composition API provides better TypeScript support

## Security Assessment

### Security Features ✅
1. **Optional API Authentication**: `INTERCEPTOR_API_TOKEN` environment variable
2. **TLS Certificate Management**: Dynamic cert generation with rcgen
3. **Security Documentation**: Comprehensive SECURITY.md file
4. **Vulnerability Reporting**: Dedicated email for security issues
5. **Input Validation**: Request size limits (`INTERCEPTOR_MAX_BODY_BYTES`)
6. **Concurrency Limits**: `INTERCEPTOR_MAX_CONCURRENCY` to prevent DoS

### Security Concerns ⚠️

1. **TLS MITM by Design**: All HTTPS traffic is decrypted
   - Requires CA certificate trust
   - Captured data includes sensitive information

2. **Plaintext Storage**: SQLite database stores full request/response bodies
   - No encryption at rest by default
   - Sensitive tokens and credentials stored

3. **Default No Authentication**: API server has no auth by default
   - Must manually set `INTERCEPTOR_API_TOKEN`
   - Localhost binding recommended

4. **WebSocket Security**: Real-time updates via WebSocket
   - No authentication documented for WS connections

### Security Best Practices (from SECURITY.md)

```markdown
1. Certificate Management
   - Keep CA private key secure
   - Rotate certificates periodically

2. API Authentication
   - Always set INTERCEPTOR_API_TOKEN in production
   - Use strong, random tokens (32+ characters)

3. Network Security
   - Run on localhost or isolated network
   - Use firewall rules to restrict access

4. Database Security
   - Encrypt SQLite database at rest
   - Restrict file system permissions
```

## Performance & Scalability

### Performance Characteristics

1. **Async/Await with Tokio**: Non-blocking I/O for high concurrency
2. **Connection Pooling**: Reuses HTTP client connections
3. **Regex Caching**: Compiled patterns cached in HashMap
4. **Ring Buffer**: LRU eviction for in-memory capture (10,000 limit)
5. **Streaming**: Hyper's streaming body handling for large payloads

### Scalability Considerations

**Horizontal Scaling**: ❌ Not supported
- Single-process architecture
- Shared state via Arc<RwLock> (single-node only)

**Vertical Scaling**: ✅ Supported
- Configurable concurrency limit
- Tokio runtime scales with CPU cores
- Memory-efficient with bounded capture storage

### Performance Bottlenecks

1. **SQLite Writes**: Sequential writes may bottleneck under high load
2. **Regex Compilation**: First-time regex compilation adds latency
3. **Body Buffering**: Large request/response bodies held in memory

### Optimization Opportunities

1. Replace SQLite with PostgreSQL for concurrent writes
2. Pre-compile common regex patterns at startup
3. Implement streaming storage for large payloads
4. Add Redis for distributed caching

## Documentation Quality

### Documentation Score: 8/10

### Strengths ✅

1. **Comprehensive README**: Clear project overview, quick start, features
2. **Architecture Documentation**: `docs/ARCHITECTURE.md` with diagrams
3. **Feature Guides**: Separate docs for Traffic, Intruder, Rules, Scope, Repeater
4. **Security Policy**: Detailed SECURITY.md with best practices
5. **Contributing Guide**: CONTRIBUTING.md for contributors
6. **Changelog**: CHANGELOG.md tracks version history
7. **API Documentation**: `docs/API.md` for REST endpoints
8. **Commercial Licensing**: Clear LICENSE_COMMERCIAL.md

### Documentation Files

```
docs/
├── API.md - REST API reference
├── ARCHITECTURE.md - System design
├── CONFIG.md - Configuration options
├── DEVELOPMENT.md - Developer setup
├── INTRUDER.md - Fuzzing guide
├── REPEATER.md - Request repeater
├── RULES.md - Traffic modification
├── SCOPE.md - Filtering
├── TRAFFIC.md - Traffic tab usage
└── UI_DESIGN_SPEC.md - UI specifications
```

### Weaknesses ❌

1. **No API Examples**: Missing curl/Postman examples
2. **Limited Code Comments**: Sparse inline documentation
3. **No Deployment Guide**: Missing production deployment instructions
4. **No Troubleshooting**: No FAQ or common issues section
5. **Video Tutorials Incomplete**: `docs/video-tutorials/` directory exists but empty

### Inline Code Comments

**Quality**: Moderate
- Core algorithms (Intruder, Rules) have explanatory comments
- Public API methods lack doc comments
- Missing rustdoc documentation for public interfaces

## Recommendations

### High Priority 🔴

1. **Expand Test Coverage**: Add comprehensive unit and integration tests
   - Current coverage is minimal (1 test file)
   - Target: >70% code coverage

2. **Add API Examples**: Include curl/Postman collections in documentation

3. **Implement Encryption at Rest**: Encrypt SQLite database by default
   - Use sqlcipher or similar

4. **Make Security Audit Blocking**: Remove `continue-on-error: true` from CI

5. **Add WebSocket Authentication**: Secure real-time connections

### Medium Priority 🟡

6. **Add Performance Benchmarks**: Automated perf testing in CI

7. **Implement Horizontal Scaling**: Consider Redis-backed state for multi-instance deployment

8. **Add Deployment Guide**: Docker Compose, Kubernetes, cloud deployment docs

9. **Create Troubleshooting Guide**: FAQ and common issues section

10. **Improve Code Documentation**: Add rustdoc comments to public APIs

### Low Priority 🟢

11. **Video Tutorials**: Record feature walkthrough videos

12. **Add Metrics/Monitoring**: Prometheus/Grafana integration

13. **Implement Rate Limiting**: Per-IP rate limiting for API

14. **Add Request Diffing**: Compare multiple requests side-by-side

15. **Export Formats**: Support HAR, Postman collection export

## Conclusion

Int3rceptor is a **well-architected, modern HTTP/HTTPS intercepting proxy** that demonstrates professional Rust development practices. The clear separation between core logic, API, and UI components shows thoughtful design. The use of modern async Rust (Tokio, Hyper, Axum) and Vue.js 3 positions it as a credible alternative to established tools like Burp Suite.

**Strengths:**
- Clean, modular architecture
- High-performance Rust backend
- Modern, reactive Vue.js frontend
- Comprehensive feature set (MITM, fuzzing, rules, WebSocket)
- Good documentation structure

**Areas for Improvement:**
- Test coverage is critically low
- Security audit should be blocking
- Database encryption should be default
- Horizontal scaling not supported
- More API usage examples needed

**CI/CD Suitability**: Currently at 6/10, but could easily reach 8/10 with:
- Expanded test suite
- Blocking security checks
- Automated Docker builds
- Test coverage reporting

**Recommended Use Cases:**
- ✅ Security testing and penetration testing
- ✅ API debugging and development
- ✅ Traffic analysis and inspection
- ⚠️ Production security monitoring (needs encryption at rest)
- ❌ High-scale enterprise deployment (needs horizontal scaling)

---

**Generated by**: Codegen Analysis Agent  
**Analysis Tool Version**: 1.0  
**Analysis Date**: December 27, 2025
