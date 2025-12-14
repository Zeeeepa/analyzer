# 📦 Complete Package Reference - RuVector Ecosystem

> **Ultimate technical reference for all 161 packages**  
> Last Updated: December 2024  
> Total Packages: 161

---

## 📖 About This Reference

This document provides comprehensive technical specifications for every package in the RuVector ecosystem, including:

- ✅ **Entrypoints**: CLI commands, NPX usage, module imports
- ⚙️ **Configuration**: All parameters, options, and settings
- 🔗 **Dependencies**: Core, enhanced, and optional dependencies  
- 📊 **Usage Examples**: Real-world integration patterns
- 🎯 **When to Use**: Decision guidance for each package

---

## 🎯 Quick Navigation

- [Core Orchestration](#core-orchestration)
- [Vector Database](#vector-database)  
- [LLM & Intelligence](#llm--intelligence)
- [Agent Management](#agent-management)
- [Neural Trading](#neural-trading)
- [Graph Neural Networks](#graph-neural-networks)
- [Self-Learning](#self-learning)
- [MCP Servers](#mcp-servers)
- [CLI Tools](#cli-tools)
- [Complete Package Index](#complete-package-index)

---

## 🔥 Core Orchestration

### claude-flow

**Version**: v2.7.47  
**Status**: 🟢 Production  
**Type**: 🔌 CLI + Library

**Description**: Enterprise-grade AI agent orchestration with WASM-powered ReasoningBank memory and AgentDB vector database.

#### Installation
```bash
npm install claude-flow
# or
npx claude-flow@latest
```

#### Entrypoints

**CLI**: `npx claude-flow`
```bash
npx claude-flow init [name] [--template basic|full|minimal]
npx claude-flow deploy [--env prod|dev|staging] [--docker] [--k8s]
npx claude-flow start [--port 3001] [--workers 4]
npx claude-flow agent:create --name <name> --type <type>
npx claude-flow agent:list [--status all|active|inactive]
npx claude-flow workflow:run --id <id> [--data <json>]
npx claude-flow health [--verbose]
npx claude-flow logs [--follow] [--lines 100]
```

**Module Import**:
```javascript
const { ClaudeFlow } = require('claude-flow');
// or
import { ClaudeFlow } from 'claude-flow';
```

#### Dependencies

**Core** (Required):
- `agentic-flow@^1.10.0` - Agent lifecycle management
- `agentdb@^1.6.0` - Agent state persistence  
- `ruvector@^0.1.35` - Vector database

**Enhanced** (Recommended):
- `ruv-swarm@^1.0.20` - Neural swarm orchestration
- `@ruvector/ruvllm@^0.2.3` - LLM inference  
- `@ruvector/router@^0.1.25` - Semantic routing

**Optional**:
- `@ruvector/sona@^0.1.4` - Adaptive learning
- `@foxruv/iris@^1.8.19` - LLM optimization
- `research-swarm@^1.2.2` - Research agents

#### Configuration

```javascript
const flow = new ClaudeFlow({
  // Core Configuration
  maxAgents: 50,                     // Max concurrent agents (1-1000)
  reasoningBank: true,               // Enable ReasoningBank
  swarmIntelligence: true,           // Enable swarm coordination
  
  // Agent Lifecycle
  agentLifecycle: {
    maxLifetime: 3600000,            // Max lifetime ms (default: 1hr)
    healthCheckInterval: 5000,        // Health check ms  
    supervision: 'hierarchical',      // hierarchical|flat|peer
    autoRestart: true,               // Auto-restart failed agents
    gracefulShutdown: 30000          // Shutdown grace period ms
  },
  
  // LLM Configuration  
  llm: {
    provider: 'openai',              // openai|anthropic|azure|local
    model: 'gpt-4',                  // Model identifier
    apiKey: process.env.OPENAI_KEY, // API key
    temperature: 0.7,                // 0.0-2.0
    maxTokens: 8192,                 // Max tokens per request
    streaming: true,                 // Enable streaming
    timeout: 30000,                  // Request timeout ms
    retries: 3                       // Retry attempts
  },
  
  // Storage
  storage: {
    vectorDb: vectorDbInstance,      // RuVector instance (required)
    agentDb: agentDbInstance,        // AgentDB instance (required)
    caching: true,                   // Enable result caching
    persistence: true,               // Persist to disk
    ttl: 86400                       // Cache TTL seconds (24hrs)
  },
  
  // MCP Integration
  mcp: {
    servers: [                       // MCP server URLs
      'http://localhost:3002'
    ],
    timeout: 30000,                  // MCP timeout ms
    retries: 3,                      // Retry attempts
    tools: ['web-search', 'db-query'] // Enabled tools
  },
  
  // Monitoring  
  monitoring: {
    enabled: true,                   // Enable metrics
    prometheus: {
      port: 9090,                    // Prometheus port
      path: '/metrics'               // Metrics path
    },
    logging: {
      level: 'info',                 // error|warn|info|debug
      format: 'json',                // json|text
      destination: './logs'          // Log directory
    }
  },
  
  // Security
  security: {
    authentication: true,            // Require auth
    rateLimit: {
      requests: 100,                 // Max requests
      window: 60000                  // Time window ms
    },
    cors: {
      origin: '*',                   // CORS origin
      credentials: true              // Allow credentials
    }
  }
});
```

#### Usage Examples

**Basic Workflow**:
```javascript
const { ClaudeFlow } = require('claude-flow');

const flow = new ClaudeFlow({
  maxAgents: 20,
  reasoningBank: true
});

await flow.initialize();

const result = await flow.execute({
  task: 'Analyze repository',
  context: { repo: 'https://github.com/user/repo' },
  agents: { min: 3, max: 10 }
});

console.log(result.summary);
```

**Advanced Multi-Agent**:
```javascript
const workflow = await flow.createWorkflow({
  name: 'Code Analysis',
  stages: [
    { name: 'parse', agents: 2, type: 'parser' },
    { name: 'analyze', agents: 5, type: 'analyzer' },
    { name: 'suggest', agents: 3, type: 'suggester' }
  ],
  learningEnabled: true
});

const result = await workflow.execute({
  repository: 'https://github.com/user/repo',
  branch: 'main'
});
```

#### When to Use

✅ **Use claude-flow when**:
- Building multi-agent AI systems
- Need enterprise-grade orchestration
- Require ReasoningBank memory
- Want integrated MCP tool access
- Need production monitoring

❌ **Don't use when**:
- Single-agent scenarios (use agentic-flow)
- Simple LLM calls (use @ruvector/ruvllm directly)  
- Prototyping (too heavyweight)

---

### agentic-flow

**Version**: v1.10.2
**Status**: 🟢 Production
**Type**: 📦 Library Only

**Description**: Agent lifecycle management with 66 specialized agents, 213 MCP tools, and AgentDB integration.

#### Installation
```bash
npm install agentic-flow
```

#### Entrypoint
```javascript
const { AgenticFlow } = require('agentic-flow');
import { AgenticFlow } from 'agentic-flow';
```

#### Dependencies

**Core**:
- `agentdb@^1.6.0` - State persistence
- `ruvector@^0.1.35` - Vector storage

**Enhanced**:
- `@ruvector/router@^0.1.25` - Request routing
- `agentic-jujutsu@^2.3.6` - Coordination

**Optional**:
- `@agentic-robotics/self-learning@^1.0.0` - Self-optimization

#### Configuration

```javascript
const flow = new AgenticFlow({
  // Agent Settings
  maxConcurrentAgents: 50,          // Max parallel agents
  agentTypes: [                     // Available types
    'research', 'analysis', 'coding', 
    'review', 'docs', 'testing'
  ],
  
  // Supervision
  supervision: 'hierarchical',      // hierarchical|flat|peer
  supervisorRatio: 0.1,            // Supervisors per 10 agents
  
  // Lifecycle
  lifecycle: {
    spawnTimeout: 10000,            // Spawn timeout ms
    maxLifetime: 3600000,           // Max lifetime ms
    gracefulShutdown: 30000,        // Shutdown grace ms
    healthCheck: {
      interval: 5000,               // Check interval ms
      timeout: 3000,                // Check timeout ms
      retries: 3                    // Retry count
    }
  },
  
  // State Management
  stateManagement: {
    agentDb: agentDbInstance,       // AgentDB instance
    snapshotInterval: 60000,        // Snapshot interval ms
    recoveryEnabled: true,          // Enable recovery
    maxHistorySize: 1000            // Max history entries
  },
  
  // Communication
  communication: {
    protocol: 'message-queue',      // message-queue|pubsub|rpc
    buffer: 1000,                   // Message buffer size
    timeout: 10000,                 // Message timeout ms
    compression: true               // Enable compression
  },
  
  // Resource Management
  resources: {
    cpuLimit: 80,                   // CPU limit %
    memoryLimit: 2048,              // Memory limit MB
    diskLimit: 10240,               // Disk limit MB
    throttling: true                // Enable throttling
  }
});
```

---

## 📊 Vector Database

### ruvector

**Version**: v0.1.35
**Status**: 🟢 Production  
**Type**: 📦 Library

**Description**: High-performance vector database with HNSW indexing, supporting 50k+ inserts/sec.

#### Installation
```bash
npm install ruvector
```

#### Entrypoint
```javascript
const { Ruvector } = require('ruvector');
```

#### Dependencies

**Core**:
- `@ruvector/core@^0.1.28` - Core operations

**Optional**:
- `@ruvector/postgres-cli@^0.2.6` - PostgreSQL backend
- `ruvector-extensions@^0.1.0` - Additional features

#### Configuration

```javascript
const db = new Ruvector({
  // Core Settings
  dimension: 1536,                  // Vector dimension
  indexType: 'hnsw',               // hnsw|ivf|flat
  metric: 'cosine',                // cosine|euclidean|dot
  
  // Performance
  performance: {
    maxConnections: 100,            // Max connections
    queryTimeout: 30000,            // Query timeout ms
    batchSize: 1000,                // Batch insert size
    parallelQueries: 10             // Parallel query limit
  },
  
  // Storage Backend
  backend: '@ruvector/postgres-cli',
  connectionString: process.env.DB_URL,
  poolSize: 20,                     // Connection pool size
  
  // HNSW Parameters  
  hnsw: {
    m: 16,                          // Max connections per element
    efConstruction: 200,             // Construction ef
    efSearch: 50                    // Search ef
  },
  
  // Caching
  cache: {
    enabled: true,                  // Enable caching
    maxSize: 10000,                 // Max cached vectors
    ttl: 3600                       // Cache TTL seconds
  }
});
```

---

## 🧠 Complete Package Index


### All Packages (161 total)

| Package | Version | Type | Status | Description |
|---------|---------|------|--------|-------------|
| `@agentic-robotics/cli` | 0.2.3 | 🔌 CLI | 🟢 | CLI tools for agentic robotics framework... |
| `@agentic-robotics/core` | 0.2.1 | 📦 Lib | 🟢 | High-performance agentic robotics framework - Core bindings... |
| `@agentic-robotics/linux-x64-gnu` | 0.2.0 | 📦 Lib | 🟢 | agentic-robotics native bindings for Linux x64 (GNU)... |
| `@agentic-robotics/mcp` | 0.2.2 | 📦 Lib | 🟢 | Model Context Protocol server for agentic robotics with AgentDB integration... |
| `@agentic-robotics/self-learning` | 1.0.0 | 📦 Lib | 🟢 | AI-powered self-learning optimization system with swarm intelligence, PSO, NSGA-... |
| `@agentics.org/agentic-mcp` | 1.0.4 | 📦 Lib | 🟢 | Agentic MCP Server with advanced AI capabilities including web search, summariza... |
| `@agentics.org/sparc2` | 2.0.25 | 📦 Lib | 🟢 | SPARC 2.0 - Autonomous Vector Coding Agent + MCP. SPARC 2.0, vectorized AI code ... |
| `@foxruv/e2b-runner` | 2.0.1 | 📦 Lib | 🟢 | Production-grade E2B sandbox orchestration with agentic-flow swarms and AgentDB ... |
| `@foxruv/iris` | 1.8.19 | 📦 Lib | 🟢 | AI-guided LLM optimization. Install → Tell Claude 'Read .claude/agents/iris.md' ... |
| `@foxruv/iris-agentic-synth` | 1.0.5 | 📦 Lib | 🟢 | ⚡ High-performance synthetic prompt generation with genetic evolution, streaming... |
| `@foxruv/iris-core` | 1.0.0 | 📦 Lib | 🟢 | Intelligent AI orchestration with multi-provider LM management, drift detection,... |
| `@foxruv/iris-ultrathink` | 1.0.0 | 📦 Lib | 🟢 | Standalone MCP server with agentic-flow and agentdb integration... |
| `@foxruv/nova-medicina` | 1.0.0 | 📦 Lib | 🟢 | AI-powered medical analysis system with anti-hallucination safeguards - suppleme... |
| `@neural-trader/agentic-accounting-agents` | 0.1.1 | 📦 Lib | 🟢 | Multi-agent swarm orchestration for autonomous accounting operations with Reason... |
| `@neural-trader/agentic-accounting-cli` | 0.1.1 | 🔌 CLI | 🟢 | Command-line interface for neural-trader's agentic accounting system with intera... |
| `@neural-trader/agentic-accounting-core` | 0.1.1 | 📦 Lib | 🟢 | Core TypeScript library for autonomous cryptocurrency accounting with transactio... |
| `@neural-trader/agentic-accounting-mcp` | 0.1.1 | 📦 Lib | 🟢 | Model Context Protocol (MCP) server for Claude Desktop integration, exposing int... |
| `@neural-trader/agentic-accounting-rust-core` | 0.1.1 | 📦 Lib | 🟢 | High-performance Rust native addon (NAPI) for cryptocurrency tax calculations wi... |
| `@neural-trader/agentic-accounting-types` | 0.1.1 | 📦 Lib | 🟢 | Comprehensive TypeScript type definitions and interfaces for neural-trader's age... |
| `@neural-trader/backend` | 2.2.1 | 📦 Lib | 🟢 | High-performance Neural Trader backend with native Rust bindings via NAPI-RS... |
| `@neural-trader/backtesting` | 2.6.0 | 📦 Lib | 🟢 | Neural Trader backtesting engine and historical simulation... |
| `@neural-trader/benchoptimizer` | 2.1.1 | 📦 Lib | 🟢 | Comprehensive benchmarking, validation, and optimization tool for neural-trader ... |
| `@neural-trader/brokers` | 2.1.1 | 📦 Lib | 🟢 | Broker integrations for Neural Trader - Alpaca, Interactive Brokers, TD Ameritra... |
| `@neural-trader/core` | 2.0.0 | 📦 Lib | 🟢 | Ultra-low latency neural trading engine with Rust + Node.js bindings... |
| `@neural-trader/e2b-strategies` | 1.1.1 | 📦 Lib | 🟢 | Production-ready E2B sandbox trading strategies with 10-50x performance improvem... |
| `@neural-trader/example-dynamic-pricing` | 1.0.0 | 📦 Lib | 🟢 | Self-learning dynamic pricing with RL optimization and swarm strategy exploratio... |
| `@neural-trader/example-energy-forecasting` | 1.0.0 | 📦 Lib | 🟢 | Self-learning energy forecasting with conformal prediction and swarm-based ensem... |
| `@neural-trader/example-energy-grid-optimization` | 0.1.0 | 📦 Lib | 🟢 | Self-learning energy grid optimization with load forecasting, unit commitment, a... |
| `@neural-trader/example-evolutionary-game-theory` | 1.0.0 | 📦 Lib | 🟢 | Self-learning evolutionary game theory with multi-agent tournaments, replicator ... |
| `@neural-trader/example-healthcare-optimization` | 1.0.0 | 📦 Lib | 🟢 | Healthcare optimization with self-learning patient forecasting and swarm-based s... |
| `@neural-trader/example-logistics-optimization` | 1.0.0 | 📦 Lib | 🟢 | Self-learning vehicle routing optimization with multi-agent swarm coordination... |
| `@neural-trader/example-market-microstructure` | 1.0.0 | 📦 Lib | 🟢 | Self-learning market microstructure analysis with AI-powered order book predicti... |
| `@neural-trader/example-neuromorphic-computing` | 1.0.0 | 📦 Lib | 🟢 | Neuromorphic computing with Spiking Neural Networks, STDP learning, and reservoi... |
| `@neural-trader/example-portfolio-optimization` | 1.0.0 | 📦 Lib | 🟢 | Self-learning portfolio optimization with benchmark swarms and multi-objective o... |
| `@neural-trader/example-quantum-optimization` | 1.0.0 | 📦 Lib | 🟢 | Quantum-inspired optimization algorithms with swarm-based circuit exploration fo... |
| `@neural-trader/example-supply-chain-prediction` | 1.0.0 | 📦 Lib | 🟢 | Self-learning demand forecasting and swarm-based inventory optimization with unc... |
| `@neural-trader/execution` | 2.6.0 | 📦 Lib | 🟢 | Neural Trader trade execution and order management... |
| `@neural-trader/features` | 2.1.2 | 📦 Lib | 🟢 | Technical indicators for Neural Trader - SMA, RSI, MACD, Bollinger Bands, and 15... |
| `@neural-trader/market-data` | 2.1.1 | 📦 Lib | 🟢 | Market data providers for Neural Trader - Alpaca, Polygon, Yahoo Finance... |
| `@neural-trader/mcp` | 2.1.0 | 📦 Lib | 🟢 | Model Context Protocol (MCP) server for Neural Trader with 87+ trading tools... |
| `@neural-trader/mcp-protocol` | 2.0.0 | 📦 Lib | 🟢 | Model Context Protocol (MCP) JSON-RPC 2.0 protocol types for Neural Trader... |
| `@neural-trader/neural` | 2.6.0 | 📦 Lib | 🟢 | Neural Trader neural network training and prediction... |
| `@neural-trader/neuro-divergent` | 2.1.1 | 📦 Lib | 🟢 | Neural forecasting library with 27+ models (NHITS, LSTM, Transformers) for time ... |
| `@neural-trader/news-trading` | 2.1.1 | 📦 Lib | 🟢 | News-driven trading for Neural Trader - real-time sentiment analysis and event-d... |
| `@neural-trader/portfolio` | 2.6.0 | 📦 Lib | 🟢 | Neural Trader portfolio management and optimization... |
| `@neural-trader/prediction-markets` | 2.1.1 | 📦 Lib | 🟢 | Prediction markets for Neural Trader - Polymarket, Augur integration with expect... |
| `@neural-trader/predictor` | 0.1.0 | 📦 Lib | 🟢 | Conformal prediction for neural trading with guaranteed intervals... |
| `@neural-trader/risk` | 2.6.0 | 📦 Lib | 🟢 | Neural Trader risk management and analysis... |
| `@neural-trader/sports-betting` | 2.1.1 | 📦 Lib | 🟢 | Sports betting for Neural Trader - arbitrage detection, Kelly sizing, syndicate ... |
| `@neural-trader/strategies` | 2.6.0 | 📦 Lib | 🟢 | Neural Trader strategy management and backtesting functionality... |

*... and 111 more packages. See sections above for detailed specifications.*


---

## 📚 Additional Resources

- **Main Documentation**: See CORE/README.md for architecture and deployment
- **GitHub Repository**: https://github.com/ruvnet/
- **NPM Registry**: https://www.npmjs.com/~ruvnet
- **Flow Nexus Platform**: https://flow-nexus.ruv.io

---

**Last Updated**: December 14, 2024  
**Maintainer**: @ruvnet  
**License**: MIT (most packages)


