# eversale-cli v2.1.218 → Z.AI Personal API Key Integration

## ✅ Status: FULLY OPERATIONAL

Successfully patched eversale-cli to work with Z.AI personal API keys. The agent loop runs end-to-end: browser automation → LLM reasoning → action execution → completion tracking.

---

## Quick Start (3 Environment Variables)

```bash
export OPENAI_API_KEY="your-z-ai-api-key"
export OPENAI_BASE_URL="https://api.z.ai/api/coding/paas/v4"
export OPENAI_MODEL="glm-5"

eversale "Research fluxy-bot"
```

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│  Node.js CLI (bin/eversale.js)                      │
│  ├─ findPython() → python3.11/3.12                  │
│  ├─ arg parsing, version, env inheritance           │
│  └─ spawn python3.X -m agent.agentic_browser        │
├─────────────────────────────────────────────────────┤
│  Python Engine (engine/agent/)                       │
│  ┌─────────────────┐  ┌──────────────────────────┐  │
│  │ config_loader.py│→ │ gpu_llm_client.py        │  │
│  │ load_config()   │  │ GPULLMClient (singleton)  │  │
│  │  • base_url     │  │  • chat() / chat_async()  │  │
│  │  • mode         │  │  • retry (5x exp backoff) │  │
│  │  • model maps   │  │  • auth header builder    │  │
│  └────────┬────────┘  └──────────┬───────────────┘  │
│           │                      │                   │
│  ┌────────▼────────┐  ┌─────────▼──────────────┐   │
│  │agentic_browser  │  │ llm_client.py          │   │
│  │  • Playwright   │  │  (fallback LLM chain)  │   │
│  │  • AXTree snap  │  │  • Ollama local        │   │
│  │  • DevTools     │  │  • OpenAI remote       │   │
│  │  • Action exec  │  │  • model routing       │   │
│  └─────────────────┘  └────────────────────────┘   │
│                                                      │
│  ┌──────────────────┐  ┌──────────────────────────┐ │
│  │brain_enhanced_v2 │  │ strategic_planner.py     │ │
│  │  • Task decomp   │  │  • Multi-step planning   │ │
│  │  • Self-healing   │  │  • Recovery thresholds   │ │
│  │  • Embeddings     │  │  • Failure strategies    │ │
│  └──────────────────┘  └──────────────────────────┘ │
│                                                      │
│  ┌──────────────────┐  ┌──────────────────────────┐ │
│  │ site_router.py   │  │ kimi_k2_client.py       │ │
│  │  • Domain-spec   │  │  • Strategic planner LLM │ │
│  │  • LinkedIn/GH   │  │  • Moonshot/OpenRouter   │ │
│  │  • Twitter/etc   │  │  • Budget tracking       │ │
│  └──────────────────┘  └──────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

---

## Patched Files (5 files, 15 surgical changes)

### 1. `gpu_llm_client.py` — Primary LLM Client (4 patches)

| # | Location | Change | Purpose |
|---|----------|--------|---------|
| 1 | L26-32 (GPU_LLM_URL) | Added `OPENAI_BASE_URL` at top of env chain | URL resolution priority |
| 2 | L79-84 (api_token) | Added `OPENAI_API_KEY` at top of token chain | Auth token priority |
| 3 | L127-133 (_get_headers) | New `OPENAI_API_KEY` guard before proxy check | Override license_key when personal key set |
| 4 | L145+ (_build_chat_endpoint) | New method + 4 call-site replacements | Auto-detect `/v4` in base URL, avoid `/v4/v1/chat/completions` |

### 2. `config_loader.py` — Configuration Cascade (3 patches)

| # | Location | Change | Purpose |
|---|----------|--------|---------|
| 1 | L72 (local mode) | Added `OPENAI_BASE_URL` to env_url chain | Local dev picks up personal API key |
| 2 | L99 (CLI mode) | Added `OPENAI_BASE_URL` to env_url chain | CLI mode picks up personal API key |
| 3 | L111 (fallback) | Added `OPENAI_BASE_URL` to fallback default | Last-resort still respects env vars |

### 3. `llm_client.py` — Fallback LLM Client (6 patches, prior session)

| # | Location | Change | Purpose |
|---|----------|--------|---------|
| 1 | Remote mode detection | Check `OPENAI_*` env vars | Force remote when personal key set |
| 2 | URL resolution | Prioritize `OPENAI_BASE_URL` | Correct endpoint |
| 3 | Auth resolution | Prioritize `OPENAI_API_KEY` | Correct authentication |
| 4 | Model resolution | Prioritize `OPENAI_MODEL` | Correct model selection |
| 5 | API path detection | Auto-detect versioned URLs | `/v4/chat/completions` not `/v4/v1/...` |
| 6 | Response parsing | Handle `reasoning_content` | glm-5 extended thinking field |

### 4. `startup_health_check.py` — Pre-flight Checks (1 patch, prior session)

Bypass ollama health check when `OPENAI_BASE_URL` is set (unnecessary for remote API usage).

### 5. `brain_enhanced_v2.py` — Multi-agent Brain (1 patch, prior session)

Wrap `import ollama` in try-except to prevent crash when ollama not installed.

---

## Configuration Resolution Order (After Patches)

### Base URL
```
OPENAI_BASE_URL → ANTHROPIC_BASE_URL → GPU_LLM_URL → 
SUPPORT_AGENT_LLM_CHAIN_REMOTE_ORIGIN → hardcoded default
```

### API Token
```
OPENAI_API_KEY → ANTHROPIC_API_KEY → RUNPOD_API_KEY → 
EVERSALE_LLM_TOKEN → GPU_LLM_TOKEN
```

### Auth Header Logic
```
if OPENAI_API_KEY set → use api_token (personal key)
elif _is_eversale_proxy() → use license_key (subscription)
elif _is_runpod_serverless() → use RUNPOD_API_KEY
else → api_token or license_key
```

### Endpoint Path Construction
```
if base_url ends with /v\d+ (e.g., /v4) → append /chat/completions
else → append /v1/chat/completions
```

---

## Strongest Suites for Building a Windows Native Assistant Orchestrator

### 1. 🧠 Hierarchical Task Decomposition Engine
- `brain_enhanced_v2.py` (4,480 lines): Full task breakdown with self-healing strategies
- `strategic_planner.py`: Multi-step planning with recovery thresholds
- **Use for**: Decomposing user requests into sub-agent tasks

### 2. 🌐 Browser-as-Tool Automation
- `agentic_browser.py` (7,200+ lines): Production-grade Playwright integration
- AXTree snapshot-first mode for token optimization
- DevTools hooks for network/console capture
- **Use for**: Web research agents, data extraction agents

### 3. 🔄 Multi-LLM Orchestration with Graceful Fallback
- `gpu_llm_client.py`: Primary high-performance client
- `llm_client.py`: Fallback chain (Ollama → OpenAI → custom)
- `kimi_k2_client.py`: Strategic planning specialist
- **Use for**: Routing different sub-tasks to appropriate models

### 4. 🛡️ Self-Healing & Recovery
- SQLite-backed strategy database
- Failure pattern detection and automatic fallback
- Rate limiting detection and cooldown management
- **Use for**: Resilient long-running agent operations

### 5. 🏗️ Singleton Pattern for Resource Management
- `get_gpu_client()` singleton ensures one LLM connection
- Browser pool with session persistence
- **Use for**: Efficient resource sharing across sub-agents

---

## Building the Control Plane / Mission Control

### Architecture Proposal

```
┌──────────────────────────────────────────────────┐
│  MISSION CONTROL (Windows Native / Electron)      │
│  ┌────────────────────────────────────────────┐  │
│  │ Task Decomposer                             │  │
│  │ User request → [sub-task₁, sub-task₂, ...]  │  │
│  │ (based on brain_enhanced_v2.py patterns)     │  │
│  └────────────────┬───────────────────────────┘  │
│                   │                               │
│  ┌────────────────▼───────────────────────────┐  │
│  │ Agent Spawner / Pool Manager                │  │
│  │ For each sub-task:                          │  │
│  │   spawn_agent(task, tools, context, mcp)    │  │
│  │   → Isolated Python subprocess              │  │
│  │   → Own browser context                     │  │
│  │   → Own LLM conversation thread             │  │
│  └────────────────┬───────────────────────────┘  │
│                   │                               │
│  ┌────────────────▼───────────────────────────┐  │
│  │ Temporal Completion Tracker                  │  │
│  │ • Agent status: running/complete/failed      │  │
│  │ • Token usage per agent                      │  │
│  │ • Time elapsed / estimated                   │  │
│  │ • Result aggregation                         │  │
│  │ • Inter-agent messaging                      │  │
│  └────────────────┬───────────────────────────┘  │
│                   │                               │
│  ┌────────────────▼───────────────────────────┐  │
│  │ Result Synthesizer                          │  │
│  │ Merge sub-task results → final response     │  │
│  │ (reuses agentic_browser summary patterns)   │  │
│  └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

### Key Integration Points

| Component | eversale Source | Adaptation Needed |
|-----------|----------------|-------------------|
| Task decomposition | `brain_enhanced_v2.py` | Extract decomposition logic into standalone module |
| Agent subprocess | `bin/eversale.js` spawn pattern | Replicate in orchestrator, add IPC |
| LLM routing | `gpu_llm_client.py` + `llm_client.py` | Add model-per-task routing |
| Browser automation | `agentic_browser.py` | Per-agent browser context isolation |
| MCP tool calling | `tool_calling_engine.py` | Extend with custom MCP server registry |
| Skill context | `config/` + `training/` | Add skill discovery and injection |
| Completion tracking | `strategic_planner.py` | Add real-time status streaming |
| Self-healing | `self_healing.db` pattern | Shared healing database across agents |

---

## Python Dependencies for Local Windows Deployment

```
pip install loguru rich httpx pydantic pyyaml python-dotenv apscheduler aiofiles playwright aiohttp psutil aiosqlite numpy
playwright install chromium
```

## Verified Working Configuration

```
[GPU LLM] Initialized with endpoint: https://api.z.ai/api/coding/paas/v4
[GPU LLM] API token loaded from env
[GPU LLM] Request to https://api.z.ai/api/coding/paas/v4/chat/completions with model glm-5
[GPU LLM] Response: 65 chars, 536 tokens, 3958ms  ← SUCCESS
```

