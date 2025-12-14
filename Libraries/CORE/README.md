# CORE Libraries

This folder documents the core modules and libraries that form the foundation of the claude-flow ecosystem, providing orchestration, routing, compute, storage, and intelligence capabilities.

---

## System Architecture Overview

**claude-flow** is a multi-agent AI development framework that orchestrates complex workflows through a layered architecture:

```
┌─────────────────────────────────────────────────────┐
│              Orchestration Layer                    │
│  (claude-flow, agentic-flow, research-swarm)       │
└─────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────┐
│              Agent Intelligence Layer                │
│  (agent-booster, lean-agentic, agentic-jujutsu)    │
└─────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────┐
│         Routing & Streaming Layer                   │
│  (@ruvector/router, @ruvector/cluster)             │
└─────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────┐
│         Compute & Processing Layer                  │
│  (WASM kernels, neural processors, LLM engines)    │
└─────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────┐
│              Data & Storage Layer                   │
│  (agentdb, @ruvector/postgres-cli, ruvector)       │
└─────────────────────────────────────────────────────┘
```

---

## Module Catalog

### 🎯 Orchestration & Framework Layer

#### **claude-flow**
- **Purpose**: Primary orchestration framework for multi-agent AI workflows
- **Role in System**: Central coordinator that manages agent lifecycle, task distribution, and workflow execution
- **Usage in claude-flow**: Acts as the main entry point; orchestrates all other modules to execute complex AI-driven development tasks
- **Integration Points**: Coordinates with agentic-flow for agent management, ruvector for data operations, and all compute modules for processing

#### **agentic-flow**
- **Purpose**: Agent lifecycle and state management framework
- **Role in System**: Manages agent creation, configuration, state transitions, and inter-agent communication
- **Usage in claude-flow**: Provides the agent runtime environment; handles agent spawning, monitoring, and coordination
- **Integration Points**: Works with claude-flow for orchestration; uses agentdb for persistence; communicates via @ruvector/router

#### **research-swarm**
- **Purpose**: Multi-agent research and exploration framework
- **Role in System**: Coordinates swarms of specialized research agents for parallel information gathering and analysis
- **Usage in claude-flow**: Enables distributed research workflows; deployed when tasks require multi-source data synthesis
- **Integration Points**: Integrates with agentic-flow for agent management; uses ruvector for knowledge storage

---

### 🧠 Agent Intelligence & Capabilities

#### **agent-booster**
- **Purpose**: Performance optimization and capability enhancement for AI agents
- **Role in System**: Provides runtime optimizations, caching strategies, and agent capability extensions
- **Usage in claude-flow**: Enhances agent performance through intelligent caching and optimization strategies
- **Integration Points**: Works with all agent types; interfaces with @ruvector/core for accelerated operations

#### **lean-agentic**
- **Purpose**: Lightweight, resource-efficient agent implementation
- **Role in System**: Provides minimal-overhead agents for high-frequency, low-complexity tasks
- **Usage in claude-flow**: Deployed for tasks requiring fast execution and low memory footprint
- **Integration Points**: Alternative agent runtime; integrates with same orchestration layer but optimized for efficiency

#### **agentic-jujutsu**
- **Purpose**: Advanced agent coordination and conflict resolution
- **Role in System**: Manages complex multi-agent interactions, deadlock prevention, and resource arbitration
- **Usage in claude-flow**: Ensures smooth coordination when multiple agents compete for resources or have interdependent tasks
- **Integration Points**: Works with agentic-flow; monitors agent interactions; resolves conflicts in real-time

#### **@agentic-robotics/self-learning**
- **Purpose**: Self-improving agent capabilities through reinforcement learning
- **Role in System**: Enables agents to learn from execution history and improve performance over time
- **Usage in claude-flow**: Optional module for long-running deployments; improves agent decision-making quality
- **Integration Points**: Observes agent actions; stores learning data in agentdb; updates agent models

#### **agentic-robotics**
- **Purpose**: Physical and virtual robotics agent framework
- **Role in System**: Provides specialized agents for robotic process automation and physical world interactions
- **Usage in claude-flow**: Used when workflows require RPA capabilities or integration with hardware/IoT
- **Integration Points**: Extends agentic-flow with robotics-specific primitives

---

### 🚀 Routing, Clustering & Networking

#### **@ruvector/router**
- **Purpose**: High-performance request routing and load balancing
- **Role in System**: Distributes tasks across compute nodes and manages request routing
- **Usage in claude-flow**: Routes agent requests to appropriate compute resources; ensures load balancing
- **Integration Points**: Sits between orchestration layer and compute layer; integrates with @ruvector/cluster

#### **@ruvector/router-wasm**
- **Purpose**: WebAssembly-based router for edge deployments
- **Role in System**: Provides ultra-low-latency routing in browser and edge environments
- **Usage in claude-flow**: Enables client-side routing for distributed deployments
- **Integration Points**: Alternative to native router for edge/browser scenarios

#### **@ruvector/cluster**
- **Purpose**: Distributed cluster management and coordination
- **Role in System**: Manages multi-node deployments, consensus, and cluster health
- **Usage in claude-flow**: Enables horizontal scaling; coordinates distributed agent execution
- **Integration Points**: Works with @ruvector/router for load distribution; manages @ruvector/server instances

#### **@ruvector/server**
- **Purpose**: Core server runtime for agent execution nodes
- **Role in System**: Provides the execution environment for distributed agent workloads
- **Usage in claude-flow**: Each compute node runs an instance; executes agent tasks and manages local state
- **Integration Points**: Receives tasks from @ruvector/router; reports to @ruvector/cluster; uses local ruvector instance

---

### ⚡ Compute & Processing Layer

#### **@ruvector/ruvllm**
- **Purpose**: High-performance LLM inference engine
- **Role in System**: Provides optimized language model execution for agent reasoning
- **Usage in claude-flow**: Powers all LLM-based agent reasoning and generation tasks
- **Integration Points**: Used by all agents requiring LLM capabilities; optimized for multi-tenant usage

#### **@ruvector/ruvllm-linux-x64-gnu**
- **Purpose**: Linux-optimized LLM inference binary
- **Role in System**: Platform-specific build for production Linux deployments
- **Usage in claude-flow**: Deployed on Linux servers for optimal performance
- **Integration Points**: Binary dependency of @ruvector/ruvllm

#### **@ruvector/rvlite**
- **Purpose**: Lightweight inference engine for resource-constrained environments
- **Role in System**: Provides minimal LLM inference for edge and mobile deployments
- **Usage in claude-flow**: Used in distributed edge deployments where resources are limited
- **Integration Points**: Alternative to full ruvllm for specific deployment scenarios

#### **@ruvector/wasm**
- **Purpose**: WebAssembly runtime and utilities
- **Role in System**: Provides WASM execution environment for portable compute kernels
- **Usage in claude-flow**: Enables cross-platform compute operations; runs specialized WASM modules
- **Integration Points**: Host environment for all *-wasm modules

#### **@ruvector/tiny-dancer**
- **Purpose**: Efficient small model inference
- **Role in System**: Optimized inference for small, fast models (e.g., embeddings, classifiers)
- **Usage in claude-flow**: Handles high-frequency, low-complexity inference tasks
- **Integration Points**: Complements ruvllm; used for embedding generation and fast classification

#### **@ruvector/tiny-dancer-wasm**
- **Purpose**: WebAssembly build of tiny-dancer
- **Role in System**: Portable small model inference for browser/edge
- **Usage in claude-flow**: Enables client-side embedding and classification
- **Integration Points**: Runs in @ruvector/wasm environment

#### **@ruvector/graph-node**
- **Purpose**: Graph computation engine for neural architectures
- **Role in System**: Executes graph-based neural network operations
- **Usage in claude-flow**: Powers graph neural networks and structured reasoning
- **Integration Points**: Used by @ruvector/gnn; provides computational backend

#### **@ruvector/graph-wasm**
- **Purpose**: WebAssembly graph computation kernels
- **Role in System**: Portable graph operations for cross-platform deployments
- **Usage in claude-flow**: Enables graph computations in browser and edge environments
- **Integration Points**: WASM alternative to @ruvector/graph-node

#### **@ruvector/gnn**
- **Purpose**: Graph Neural Network framework
- **Role in System**: Enables reasoning over structured knowledge graphs and relational data
- **Usage in claude-flow**: Used for knowledge graph reasoning, dependency analysis, and relational learning
- **Integration Points**: Works with @ruvector/graph-node; queries data from agentdb

#### **@ruvector/gnn-wasm**
- **Purpose**: WebAssembly GNN implementation
- **Role in System**: Portable GNN inference
- **Usage in claude-flow**: Client-side graph reasoning
- **Integration Points**: WASM build running in @ruvector/wasm

#### **@ruvector/attention-wasm**
- **Purpose**: WebAssembly attention mechanism kernels
- **Role in System**: Efficient transformer attention operations in WASM
- **Usage in claude-flow**: Accelerates attention computations in portable environments
- **Integration Points**: Used by inference engines requiring attention; optimized for browser/edge

#### **psycho-symbolic-integration**
- **Purpose**: Hybrid neural-symbolic reasoning framework
- **Role in System**: Combines neural networks with symbolic logic for enhanced reasoning
- **Usage in claude-flow**: Enables agents to perform both statistical learning and logical deduction
- **Integration Points**: Augments agent reasoning capabilities; works with @ruvector/gnn and ruvllm

#### **spiking-neural**
- **Purpose**: Spiking neural network implementation
- **Role in System**: Energy-efficient neuromorphic computing for specialized tasks
- **Usage in claude-flow**: Experimental module for low-power, event-driven processing
- **Integration Points**: Alternative compute paradigm for specific agent behaviors

---

### 💾 Data, Storage & Memory

#### **ruvector**
- **Purpose**: High-performance vector database and embedding store
- **Role in System**: Provides semantic search, similarity matching, and vector operations
- **Usage in claude-flow**: Stores agent knowledge, code embeddings, and semantic memory; enables RAG workflows
- **Integration Points**: Core dependency for all agents; integrates with @ruvector/postgres-cli for hybrid storage

#### **@ruvector/core**
- **Purpose**: Core vector operations and primitives
- **Role in System**: Foundational library for vector computations, distance metrics, and indexing
- **Usage in claude-flow**: Provides low-level vector operations used by higher-level modules
- **Integration Points**: Dependency of ruvector and all vector-related modules

#### **agentdb**
- **Purpose**: Specialized database for agent state, memory, and history
- **Role in System**: Persists agent configurations, execution history, learned patterns, and conversation context
- **Usage in claude-flow**: Enables agent memory across sessions; stores execution traces for debugging and learning
- **Integration Points**: Used by agentic-flow for state management; accessed by all agents for memory operations

#### **@ruvector/postgres-cli**
- **Purpose**: PostgreSQL integration and CLI tools
- **Role in System**: Provides PostgreSQL backend for structured data and hybrid vector-relational queries
- **Usage in claude-flow**: Stores structured metadata alongside vectors; enables complex queries combining vector and relational data
- **Integration Points**: Backend for ruvector and agentdb; provides SQL interface

#### **ruvector-extensions**
- **Purpose**: Plugin system and extensions for ruvector
- **Role in System**: Provides extensibility points for custom vector operations and integrations
- **Usage in claude-flow**: Enables custom similarity metrics, indexing strategies, and integration with external vector stores
- **Integration Points**: Extends ruvector functionality; loaded dynamically based on configuration

---

### 🌐 Interface & Integration Modules

#### **@ruvector/node**
- **Purpose**: Node.js bindings and runtime integration
- **Role in System**: Provides JavaScript/TypeScript interface to ruvector and related modules
- **Usage in claude-flow**: Enables Node.js applications to use ruvector capabilities
- **Integration Points**: Wraps native modules; used by all Node.js-based agents and services

#### **ruvector-sona**
- **Purpose**: Audio and speech processing module
- **Role in System**: Provides speech recognition, synthesis, and audio embeddings
- **Usage in claude-flow**: Enables voice-based agent interactions and audio content analysis
- **Integration Points**: Works with ruvector for audio embeddings; optional module for voice workflows

#### **@foxruv/iris**
- **Purpose**: Visual understanding and image processing module
- **Role in System**: Provides computer vision, image embeddings, and visual reasoning
- **Usage in claude-flow**: Enables agents to process and understand visual content
- **Integration Points**: Generates visual embeddings stored in ruvector; used by multi-modal agents

#### **midstreamer**
- **Purpose**: Real-time streaming and event processing
- **Role in System**: Provides streaming data pipelines and real-time event handling
- **Usage in claude-flow**: Enables reactive agents that respond to streaming events; supports real-time dashboards
- **Integration Points**: Streams data between agents; integrates with @ruvector/router for event distribution

#### **ruvi**
- **Purpose**: Visual interface and dashboard framework
- **Role in System**: Provides web-based UI for monitoring and interacting with claude-flow
- **Usage in claude-flow**: Enables visualization of agent workflows, execution traces, and system health
- **Integration Points**: Consumes data from agentdb and midstreamer; provides control interface for claude-flow

---

## System Flow: End-to-End Example

### Task: "Analyze this codebase and suggest improvements"

1. **Orchestration** (claude-flow)
   - Receives task from user
   - Creates workflow plan: parse code → analyze → generate suggestions
   - Spawns specialized agents via agentic-flow

2. **Agent Creation** (agentic-flow)
   - Creates code-parser agent, analyzer agent, suggestion agent
   - Registers agents with agentic-jujutsu for coordination
   - Initializes agent state in agentdb

3. **Task Routing** (@ruvector/router)
   - Routes code-parsing task to available compute node
   - Load-balances across @ruvector/server instances
   - Coordinates with @ruvector/cluster for optimal placement

4. **Code Analysis** (agents + compute)
   - Parser agent uses @ruvector/ruvllm for code understanding
   - Generates code embeddings via @ruvector/core
   - Stores embeddings in ruvector for semantic search
   - Analyzer agent queries similar patterns from ruvector
   - Uses @ruvector/gnn for dependency graph analysis

5. **Suggestion Generation** (agents + reasoning)
   - Suggestion agent retrieves relevant patterns from ruvector
   - Uses psycho-symbolic-integration for logical reasoning
   - Generates suggestions via @ruvector/ruvllm
   - Validates suggestions through agent-booster optimization

6. **Results Delivery** (streaming + UI)
   - Streams results via midstreamer to user interface
   - Updates ruvi dashboard with progress
   - Stores execution trace in agentdb for learning
   - @agentic-robotics/self-learning analyzes for future improvements

---

## Module Status & Maturity

| Module | Status | Recommended For |
|--------|--------|-----------------|
| claude-flow | ✅ Production | All deployments |
| agentic-flow | ✅ Production | Core workflows |
| ruvector | ✅ Production | All deployments |
| @ruvector/ruvllm | ✅ Production | LLM inference |
| @ruvector/router | ✅ Production | Distributed setups |
| agentdb | ✅ Production | All deployments |
| agent-booster | ✅ Stable | Performance-critical |
| research-swarm | 🟡 Beta | Research workflows |
| agentic-jujutsu | 🟡 Beta | Complex multi-agent |
| psycho-symbolic-integration | 🔬 Experimental | Advanced reasoning |
| spiking-neural | 🔬 Experimental | Research only |
| @agentic-robotics/* | 🟡 Beta | RPA workflows |

**Legend**: ✅ Production-ready | 🟡 Beta/Stable | 🔬 Experimental

---

## Getting Started

### Minimal claude-flow Setup

```bash
# Core dependencies
npm install claude-flow agentic-flow ruvector agentdb
npm install @ruvector/ruvllm @ruvector/core

# For distributed deployments
npm install @ruvector/router @ruvector/cluster @ruvector/server

# Optional enhancements
npm install agent-booster lean-agentic midstreamer
```

### Configuration Example

```javascript
const { ClaudeFlow } = require('claude-flow');
const { Ruvector } = require('ruvector');
const { AgentDB } = require('agentdb');

const flow = new ClaudeFlow({
  orchestration: {
    framework: 'agentic-flow',
    coordinator: 'agentic-jujutsu'
  },
  compute: {
    llm: '@ruvector/ruvllm',
    router: '@ruvector/router',
    distributed: true
  },
  storage: {
    vector: new Ruvector({ backend: '@ruvector/postgres-cli' }),
    agentState: new AgentDB({ persistence: true })
  },
  enhancements: {
    optimization: 'agent-booster',
    learning: '@agentic-robotics/self-learning'
  }
});

await flow.initialize();
```

---

## Development Guidelines

### When to Use Which Module

- **Need orchestration?** → Start with `claude-flow`
- **Building custom agents?** → Use `agentic-flow`
- **Need vector search?** → Use `ruvector` + `@ruvector/core`
- **LLM inference?** → Use `@ruvector/ruvllm`
- **Distributed deployment?** → Add `@ruvector/router` + `@ruvector/cluster`
- **Agent persistence?** → Use `agentdb`
- **Performance optimization?** → Add `agent-booster`
- **Multi-modal (vision/audio)?** → Use `@foxruv/iris` or `ruvector-sona`
- **Advanced reasoning?** → Consider `psycho-symbolic-integration`
- **Real-time streaming?** → Use `midstreamer`
- **Web dashboard?** → Use `ruvi`

### Dependency Management

Most modules depend on `@ruvector/core` and `ruvector`. Start with these, then add specialized modules as needed.

---

## Resources

- **claude-flow Documentation**: See main repository for detailed guides
- **Module-Specific Docs**: Each @ruvector/* package has dedicated README
- **Community**: Join Discord for architecture discussions and best practices

---

## Maintenance Notes

This architecture is modular and extensible. As new modules are added or roles evolve, update this documentation to reflect current system design. Always verify integration points when upgrading dependencies.

**Last Updated**: December 2024

