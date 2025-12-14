# CORE Libraries

This folder documents the core modules and libraries that form the foundation of the claude-flow ecosystem, providing orchestration, routing, compute, storage, and intelligence capabilities.

---

## Official NPM Packages by @ruvnet

The following packages are officially published and maintained by @ruvnet on NPM. These represent the production-ready, verified modules available for installation:

### 📦 Published Packages (11 total)

1. **[claude-flow](https://www.npmjs.com/package/claude-flow)** - v2.0.0-alpha.86
   - Enterprise-grade AI agent orchestration with ruv-swarm integration (Alpha Release)
   - Latest update: 12 days ago

2. **[ruv-swarm](https://www.npmjs.com/package/ruv-swarm)** - v1.0.18
   - High-performance neural network swarm orchestration in WebAssembly
   - Latest update: 1 month ago

3. **[cuda-wasm](https://www.npmjs.com/package/cuda-wasm)** - v1.1.1
   - High-performance CUDA to WebAssembly/WebGPU transpiler with Rust safety
   - Run GPU kernels in browsers and Node.js
   - Latest update: 1 month ago

4. **[@agentics.org/sparc2](https://www.npmjs.com/package/@agentics.org/sparc2)** - v2.0.25
   - SPARC 2.0 - Autonomous Vector Coding Agent + MCP
   - Vectorized AI code analysis and intelligent coding agent framework
   - Latest update: 2 months ago

5. **[qudag](https://www.npmjs.com/package/qudag)** - v1.2.1
   - QuDAG - Quantum-Resistant Distributed Communication Platform
   - Latest update: 2 months ago

6. **[create-sparc](https://www.npmjs.com/package/create-sparc)** - v1.2.4
   - NPX package to scaffold new projects with SPARC methodology structure
   - Latest update: 3 months ago

7. **[vscode-remote-mcp](https://www.npmjs.com/package/vscode-remote-mcp)** - v1.0.4
   - Enhanced MCP server for VSCode Remote integration
   - Latest update: 4 months ago

8. **[@agentics.org/agentic-mcp](https://www.npmjs.com/package/@agentics.org/agentic-mcp)** - v1.0.4
   - Agentic MCP Server with advanced AI capabilities
   - Includes web search, summarization, database querying, and customer support
   - Latest update: 5 months ago

9. **[dspy.ts](https://www.npmjs.com/package/dspy.ts)** - v0.1.3
   - DSPy.ts - Declarative Self-Learning TypeScript
   - Framework for compositional LM pipelines with self-improving prompt strategies
   - Latest update: 6 months ago

10. **[@ruv/sparc-ui](https://www.npmjs.com/package/@ruv/sparc-ui)** - v0.1.4
    - SPARC Framework UI Components
    - Specification, Pseudocode, Architecture, Refinement, and Completion
    - Latest update: 8 months ago

11. **[agenticsjs](https://www.npmjs.com/package/agenticsjs)** - v1.0.5
    - Powerful JavaScript library for intelligent interactive search with real-time results
    - Advanced visualization capabilities
    - Latest update: 1 year ago

### Installation

```bash
# Install claude-flow (primary orchestrator)
npm install claude-flow

# Install swarm orchestration
npm install ruv-swarm

# Install GPU/WASM compute
npm install cuda-wasm

# Install SPARC framework tools
npm install @agentics.org/sparc2 create-sparc @ruv/sparc-ui

# Install MCP servers
npm install @agentics.org/agentic-mcp vscode-remote-mcp

# Install DSPy framework
npm install dspy.ts

# Install quantum-resistant communication
npm install qudag

# Install search utilities
npm install agenticsjs
```

**Note**: These are the only verified packages published by @ruvnet on NPM. Other packages mentioned in following sections may be planned modules, experimental prototypes, or part of private repositories not yet published to the public NPM registry.

---

## Complete Package Catalog with claude-flow Integration

This section documents ALL packages in the ecosystem, including both published NPM packages and planned/private modules, with detailed explanations of how each integrates with claude-flow.

### 📋 Integration Status Legend

- ✅ **Published on NPM**: Available for installation via `npm install`
- 🔄 **Planned/Private**: In development or private repository
- 🔗 **Integration Level**: How deeply integrated with claude-flow
  - **Core**: Essential for basic claude-flow operation
  - **Enhanced**: Adds significant capabilities
  - **Optional**: Specialized use cases

---

### 🎯 Orchestration & Framework Layer

#### **claude-flow** ✅ Published | 🔗 Core
- **NPM**: `npm install claude-flow` (v2.0.0-alpha.86)
- **Purpose**: Primary orchestration framework for multi-agent AI workflows
- **Usage in claude-flow**: 
  - Acts as the main entry point and central coordinator
  - Manages the complete agent lifecycle from creation to termination
  - Orchestrates task distribution across all system layers
  - Coordinates workflow execution and handles inter-module communication
- **Integration Flow**:
  ```
  User Request → claude-flow → Task Planning → Agent Spawning (agentic-flow)
                              ↓
                       Route Tasks (@ruvector/router)
                              ↓
                       Execute on Compute Layer
                              ↓
                       Store Results (ruvector/agentdb)
  ```
- **Key Dependencies**: agentic-flow, ruvector, @ruvector/router, ruv-swarm

#### **agentic-flow** 🔄 Planned | 🔗 Core
- **Purpose**: Agent lifecycle and state management framework
- **Usage in claude-flow**:
  - Provides the agent runtime environment
  - Handles agent spawning, configuration, and monitoring
  - Manages state transitions and inter-agent communication protocols
  - Implements agent supervision and health checking
- **Integration Flow**:
  ```
  claude-flow creates workflow → agentic-flow spawns agents
                                       ↓
                         Registers with agentic-jujutsu for coordination
                                       ↓
                         Initializes state in agentdb
                                       ↓
                         Begins executing assigned tasks
  ```
- **Key Dependencies**: agentdb, agentic-jujutsu, @ruvector/router

#### **research-swarm** 🔄 Planned | 🔗 Enhanced
- **Purpose**: Multi-agent research and exploration framework
- **Usage in claude-flow**:
  - Enables distributed research workflows
  - Coordinates swarms of specialized research agents for parallel information gathering
  - Deployed when tasks require multi-source data synthesis
  - Implements swarm intelligence algorithms for optimal task distribution
- **Integration Flow**:
  ```
  Research Task → research-swarm creates agent swarm
                           ↓
           Agents query multiple sources in parallel
                           ↓
           Synthesis agent aggregates findings → ruvector storage
  ```
- **Key Dependencies**: agentic-flow, ruvector, agent-booster

---

### 🧠 Agent Intelligence & Capabilities

#### **agent-booster** 🔄 Planned | 🔗 Enhanced
- **Purpose**: Performance optimization and capability enhancement for AI agents
- **Usage in claude-flow**:
  - Provides runtime optimizations and intelligent caching strategies
  - Extends agent capabilities with performance enhancements
  - Implements response caching to reduce redundant LLM calls
  - Optimizes agent execution paths based on historical performance
- **Integration Flow**:
  ```
  Agent receives task → agent-booster checks cache
                              ↓
                    Cache hit? Return cached result
                              ↓
                    Cache miss? Execute + store in cache
  ```
- **Key Dependencies**: @ruvector/core, agentdb

#### **lean-agentic** 🔄 Planned | 🔗 Enhanced
- **Purpose**: Lightweight, resource-efficient agent implementation
- **Usage in claude-flow**:
  - Provides minimal-overhead agents for high-frequency, low-complexity tasks
  - Deployed for tasks requiring fast execution and low memory footprint
  - Alternative agent runtime optimized for efficiency over features
  - Used in edge deployments or resource-constrained environments
- **Integration Flow**:
  ```
  Simple task identified → claude-flow selects lean-agentic
                                     ↓
                         Spawns lightweight agent
                                     ↓
                         Fast execution with minimal resources
  ```
- **Key Dependencies**: @ruvector/rvlite, @ruvector/core

#### **agentic-jujutsu** 🔄 Planned | 🔗 Enhanced
- **Purpose**: Advanced agent coordination and conflict resolution
- **Usage in claude-flow**:
  - Manages complex multi-agent interactions
  - Prevents deadlocks when agents compete for shared resources
  - Implements resource arbitration and priority scheduling
  - Ensures smooth coordination when multiple agents have interdependent tasks
- **Integration Flow**:
  ```
  Multiple agents request same resource → agentic-jujutsu arbitrates
                                                   ↓
                                         Determines priority/scheduling
                                                   ↓
                                         Resolves conflicts in real-time
  ```
- **Key Dependencies**: agentic-flow, agentdb

#### **@agentic-robotics/self-learning** 🔄 Planned | 🔗 Optional
- **Purpose**: Self-improving agent capabilities through reinforcement learning
- **Usage in claude-flow**:
  - Enables agents to learn from execution history
  - Improves agent decision-making quality over time
  - Optional module for long-running deployments
  - Stores learned patterns and applies them to future tasks
- **Integration Flow**:
  ```
  Agent completes task → self-learning observes outcome
                                   ↓
                         Stores success/failure pattern in agentdb
                                   ↓
                         Updates agent model with learned behaviors
  ```
- **Key Dependencies**: agentdb, @ruvector/ruvllm

#### **agentic-robotics** 🔄 Planned | 🔗 Optional
- **Purpose**: Physical and virtual robotics agent framework
- **Usage in claude-flow**:
  - Provides specialized agents for robotic process automation (RPA)
  - Used when workflows require integration with hardware/IoT
  - Enables interaction with physical world through sensors/actuators
  - Extends agentic-flow with robotics-specific primitives
- **Key Dependencies**: agentic-flow, @ruvector/node

---

### 🚀 Routing, Clustering & Networking

#### **@ruvector/router** 🔄 Planned | 🔗 Core
- **Purpose**: High-performance request routing and load balancing
- **Usage in claude-flow**:
  - Distributes tasks across compute nodes
  - Ensures load balancing for optimal resource utilization
  - Routes agent requests to appropriate compute resources
  - Sits between orchestration layer and compute layer
- **Integration Flow**:
  ```
  Agent task → @ruvector/router analyzes load
                         ↓
           Selects optimal compute node (@ruvector/server)
                         ↓
           Routes request + monitors execution
  ```
- **Key Dependencies**: @ruvector/cluster, @ruvector/server

#### **@ruvector/router-wasm** 🔄 Planned | 🔗 Optional
- **Purpose**: WebAssembly-based router for edge deployments
- **Usage in claude-flow**:
  - Provides ultra-low-latency routing in browser and edge environments
  - Enables client-side routing for distributed deployments
  - Alternative to native router for edge/browser scenarios
  - Runs in @ruvector/wasm environment
- **Key Dependencies**: @ruvector/wasm, @ruvector/core

#### **@ruvector/cluster** 🔄 Planned | 🔗 Core
- **Purpose**: Distributed cluster management and coordination
- **Usage in claude-flow**:
  - Manages multi-node deployments
  - Implements consensus protocols and cluster health monitoring
  - Enables horizontal scaling of agent execution
  - Coordinates distributed agent execution across nodes
- **Integration Flow**:
  ```
  New node joins → @ruvector/cluster registers node
                              ↓
                   Distributes workload across cluster
                              ↓
                   Monitors health + rebalances on failures
  ```
- **Key Dependencies**: @ruvector/router, @ruvector/server

#### **@ruvector/server** 🔄 Planned | 🔗 Core
- **Purpose**: Core server runtime for agent execution nodes
- **Usage in claude-flow**:
  - Provides the execution environment for distributed agent workloads
  - Each compute node runs an instance
  - Executes agent tasks and manages local state
  - Reports status to cluster coordinator
- **Integration Flow**:
  ```
  Receives task from router → Executes agent code
                                     ↓
                         Updates local ruvector instance
                                     ↓
                         Reports completion to cluster
  ```
- **Key Dependencies**: ruvector, @ruvector/core

---

### ⚡ Compute & Processing Layer

#### **@ruvector/ruvllm** 🔄 Planned | 🔗 Core
- **Purpose**: High-performance LLM inference engine
- **Usage in claude-flow**:
  - Powers ALL LLM-based agent reasoning and generation tasks
  - Provides optimized language model execution
  - Optimized for multi-tenant usage with efficient batching
  - Core inference engine for claude-flow's AI capabilities
- **Integration Flow**:
  ```
  Agent needs LLM reasoning → Sends prompt to ruvllm
                                       ↓
                            Batches with other requests
                                       ↓
                            Returns generated response
  ```
- **Key Dependencies**: @ruvector/ruvllm-linux-x64-gnu (platform binary)

#### **@ruvector/ruvllm-linux-x64-gnu** 🔄 Planned | 🔗 Core
- **Purpose**: Linux-optimized LLM inference binary
- **Usage in claude-flow**:
  - Platform-specific build for production Linux deployments
  - Deployed on Linux servers for optimal performance
  - Binary dependency of @ruvector/ruvllm
  - Compiled with platform-specific optimizations

#### **@ruvector/rvlite** 🔄 Planned | 🔗 Optional
- **Purpose**: Lightweight inference engine for resource-constrained environments
- **Usage in claude-flow**:
  - Provides minimal LLM inference for edge and mobile deployments
  - Used in distributed edge deployments where resources are limited
  - Alternative to full ruvllm for specific deployment scenarios
  - Sacrifices some accuracy for significantly lower resource usage

#### **@ruvector/wasm** 🔄 Planned | 🔗 Enhanced
- **Purpose**: WebAssembly runtime and utilities
- **Usage in claude-flow**:
  - Provides WASM execution environment for portable compute kernels
  - Enables cross-platform compute operations
  - Host environment for all *-wasm modules
  - Allows claude-flow to run compute-intensive tasks in browsers
- **Integration Flow**:
  ```
  Need portable compute → Load WASM module in @ruvector/wasm
                                     ↓
                         Execute compute kernel
                                     ↓
                         Return results to calling agent
  ```

#### **@ruvector/tiny-dancer** 🔄 Planned | 🔗 Enhanced
- **Purpose**: Efficient small model inference
- **Usage in claude-flow**:
  - Optimized inference for small, fast models (embeddings, classifiers)
  - Handles high-frequency, low-complexity inference tasks
  - Complements ruvllm for specialized workloads
  - Used for embedding generation and fast classification
- **Integration Flow**:
  ```
  Need text embedding → tiny-dancer generates embedding
                                  ↓
                       Store in ruvector for semantic search
  ```

#### **@ruvector/tiny-dancer-wasm** 🔄 Planned | 🔗 Optional
- **Purpose**: WebAssembly build of tiny-dancer
- **Usage in claude-flow**:
  - Enables client-side embedding and classification
  - Portable small model inference for browser/edge
  - Runs in @ruvector/wasm environment

#### **@ruvector/graph-node** 🔄 Planned | 🔗 Enhanced
- **Purpose**: Graph computation engine for neural architectures
- **Usage in claude-flow**:
  - Executes graph-based neural network operations
  - Powers graph neural networks and structured reasoning
  - Provides computational backend for @ruvector/gnn
- **Integration Flow**:
  ```
  GNN model needs computation → graph-node executes operations
                                         ↓
                              Returns computed graph embeddings
  ```

#### **@ruvector/graph-wasm** 🔄 Planned | 🔗 Optional
- **Purpose**: WebAssembly graph computation kernels
- **Usage in claude-flow**:
  - Portable graph operations for cross-platform deployments
  - Enables graph computations in browser and edge environments
  - WASM alternative to @ruvector/graph-node

#### **@ruvector/gnn** 🔄 Planned | 🔗 Enhanced
- **Purpose**: Graph Neural Network framework
- **Usage in claude-flow**:
  - Enables reasoning over structured knowledge graphs and relational data
  - Used for knowledge graph reasoning and dependency analysis
  - Performs relational learning on code structures
  - Powers advanced code understanding through graph analysis
- **Integration Flow**:
  ```
  Analyze codebase structure → Build dependency graph
                                      ↓
                       GNN analyzes graph patterns
                                      ↓
                       Identifies architectural insights
  ```
- **Key Dependencies**: @ruvector/graph-node, agentdb

#### **@ruvector/gnn-wasm** 🔄 Planned | 🔗 Optional
- **Purpose**: WebAssembly GNN implementation
- **Usage in claude-flow**:
  - Client-side graph reasoning
  - Portable GNN inference
  - WASM build running in @ruvector/wasm

#### **@ruvector/attention-wasm** 🔄 Planned | 🔗 Enhanced
- **Purpose**: WebAssembly attention mechanism kernels
- **Usage in claude-flow**:
  - Efficient transformer attention operations in WASM
  - Accelerates attention computations in portable environments
  - Used by inference engines requiring attention mechanisms
  - Optimized for browser/edge deployments

#### **psycho-symbolic-integration** 🔄 Planned | 🔗 Optional
- **Purpose**: Hybrid neural-symbolic reasoning framework
- **Usage in claude-flow**:
  - Combines neural networks with symbolic logic for enhanced reasoning
  - Enables agents to perform both statistical learning and logical deduction
  - Augments agent reasoning capabilities beyond pure neural approaches
  - Used for tasks requiring formal logic and verifiable reasoning
- **Integration Flow**:
  ```
  Complex reasoning task → Neural component generates candidates
                                      ↓
                         Symbolic component validates logic
                                      ↓
                         Returns verified reasoning chain
  ```

#### **spiking-neural** 🔄 Planned | 🔗 Optional
- **Purpose**: Spiking neural network implementation
- **Usage in claude-flow**:
  - Energy-efficient neuromorphic computing for specialized tasks
  - Experimental module for low-power, event-driven processing
  - Alternative compute paradigm for specific agent behaviors
  - Used in research and experimental deployments only

---

### 💾 Data, Storage & Memory

#### **ruvector** 🔄 Planned | 🔗 Core
- **Purpose**: High-performance vector database and embedding store
- **Usage in claude-flow**:
  - **CENTRAL TO ENTIRE SYSTEM**: Stores agent knowledge, code embeddings, semantic memory
  - Enables RAG (Retrieval-Augmented Generation) workflows
  - Provides semantic search and similarity matching
  - Core dependency for virtually all agents
- **Integration Flow**:
  ```
  Agent generates code → Create embeddings via @ruvector/core
                                    ↓
                         Store in ruvector with metadata
                                    ↓
                         Later: Semantic search for similar patterns
  ```
- **Key Dependencies**: @ruvector/core, @ruvector/postgres-cli

#### **@ruvector/core** 🔄 Planned | 🔗 Core
- **Purpose**: Core vector operations and primitives
- **Usage in claude-flow**:
  - **FOUNDATIONAL LIBRARY**: Provides low-level vector operations used by higher-level modules
  - Implements distance metrics, indexing algorithms, and vector computations
  - Dependency of ruvector and all vector-related modules
  - Optimized implementations of HNSW, IVF, and other indexing strategies

#### **agentdb** 🔄 Planned | 🔗 Core
- **Purpose**: Specialized database for agent state, memory, and history
- **Usage in claude-flow**:
  - Persists agent configurations and execution history
  - Stores learned patterns and conversation context
  - Enables agent memory across sessions
  - Stores execution traces for debugging and learning
- **Integration Flow**:
  ```
  Agent starts → Loads state from agentdb
                         ↓
           Executes task + stores intermediate states
                         ↓
           Saves final state + execution trace to agentdb
  ```
- **Key Dependencies**: @ruvector/postgres-cli

#### **@ruvector/postgres-cli** 🔄 Planned | 🔗 Core
- **Purpose**: PostgreSQL integration and CLI tools
- **Usage in claude-flow**:
  - Provides PostgreSQL backend for structured data
  - Enables hybrid vector-relational queries
  - Stores structured metadata alongside vectors
  - Backend for ruvector and agentdb
- **Integration Flow**:
  ```
  Store vector + metadata → postgres-cli manages SQL storage
                                       ↓
                            Enables complex JOIN queries
                                       ↓
                            Returns combined vector + relational results
  ```

#### **ruvector-extensions** 🔄 Planned | 🔗 Optional
- **Purpose**: Plugin system and extensions for ruvector
- **Usage in claude-flow**:
  - Provides extensibility points for custom vector operations
  - Enables custom similarity metrics and indexing strategies
  - Allows integration with external vector stores
  - Loaded dynamically based on configuration
- **Key Dependencies**: ruvector, @ruvector/core

---

### 🌐 Interface & Integration Modules

#### **@ruvector/node** 🔄 Planned | 🔗 Core
- **Purpose**: Node.js bindings and runtime integration
- **Usage in claude-flow**:
  - Provides JavaScript/TypeScript interface to ruvector and related modules
  - Enables Node.js applications to use ruvector capabilities
  - Wraps native modules for JavaScript consumption
  - Used by all Node.js-based agents and services

#### **ruvector-sona** 🔄 Planned | 🔗 Optional
- **Purpose**: Audio and speech processing module
- **Usage in claude-flow**:
  - Provides speech recognition and synthesis
  - Generates audio embeddings for voice search
  - Enables voice-based agent interactions
  - Optional module for voice workflows
- **Integration Flow**:
  ```
  Voice input → ruvector-sona transcribes + embeds
                            ↓
                Store embedding in ruvector
                            ↓
                Agent processes voice command
  ```

#### **@foxruv/iris** 🔄 Planned | 🔗 Optional
- **Purpose**: Visual understanding and image processing module
- **Usage in claude-flow**:
  - Provides computer vision and image embeddings
  - Enables visual reasoning for multi-modal agents
  - Generates visual embeddings stored in ruvector
  - Used by agents that need to process images/screenshots
- **Integration Flow**:
  ```
  Image input → iris extracts visual features
                         ↓
            Generates image embedding
                         ↓
            Agent uses embedding for visual reasoning
  ```

#### **midstreamer** 🔄 Planned | 🔗 Enhanced
- **Purpose**: Real-time streaming and event processing
- **Usage in claude-flow**:
  - Provides streaming data pipelines
  - Enables reactive agents that respond to streaming events
  - Supports real-time dashboards and monitoring
  - Streams data between agents for real-time collaboration
- **Integration Flow**:
  ```
  Event occurs → midstreamer broadcasts to subscribed agents
                              ↓
                  Agents react in real-time
                              ↓
                  Results streamed to dashboard (ruvi)
  ```
- **Key Dependencies**: @ruvector/router

#### **ruvi** 🔄 Planned | 🔗 Enhanced
- **Purpose**: Visual interface and dashboard framework
- **Usage in claude-flow**:
  - Provides web-based UI for monitoring and interacting with claude-flow
  - Enables visualization of agent workflows and execution traces
  - Shows system health and performance metrics
  - Provides control interface for manual orchestration
- **Integration Flow**:
  ```
  User opens dashboard → ruvi queries agentdb + midstreamer
                                    ↓
                         Displays real-time agent status
                                    ↓
                         User can trigger workflows manually
  ```
- **Key Dependencies**: agentdb, midstreamer

---

### 🎨 Additional @ruvnet Packages (NPM Published)

These packages are published on NPM under @ruvnet but serve different purposes outside the core claude-flow architecture:

#### **ruv-swarm** ✅ Published | 🔗 Core
- **NPM**: `npm install ruv-swarm` (v1.0.18)
- **Purpose**: High-performance neural network swarm orchestration in WebAssembly
- **Usage in claude-flow**:
  - **DIRECTLY INTEGRATED**: claude-flow v2.0.0-alpha includes ruv-swarm integration
  - Powers the distributed agent swarm capabilities
  - Provides WASM-based high-performance parallel agent execution
  - Enables complex swarm behaviors and emergent intelligence
- **Integration**: Embedded within claude-flow as core swarm engine

#### **cuda-wasm** ✅ Published | 🔗 Optional
- **NPM**: `npm install cuda-wasm` (v1.1.1)
- **Purpose**: CUDA to WebAssembly/WebGPU transpiler
- **Usage in claude-flow**:
  - Enables GPU acceleration for compute-intensive agent tasks
  - Allows running GPU kernels in browsers via WebGPU
  - Optional: Used when GPU acceleration is available
  - Significantly speeds up vector operations and embeddings

#### **@agentics.org/sparc2** ✅ Published | 🔗 Enhanced
- **NPM**: `npm install @agentics.org/sparc2` (v2.0.25)
- **Purpose**: SPARC 2.0 - Autonomous Vector Coding Agent + MCP
- **Usage in claude-flow**:
  - Can be integrated as a specialized coding agent
  - Provides vectorized code analysis capabilities
  - Implements MCP (Model Context Protocol) for agent communication
  - Used for advanced code generation and analysis tasks

#### **create-sparc** ✅ Published | 🔗 Optional
- **NPM**: `npx create-sparc` (v1.2.4)
- **Purpose**: Project scaffolding tool for SPARC methodology
- **Usage in claude-flow**:
  - CLI tool for creating new projects with SPARC structure
  - Not directly integrated into runtime
  - Used by developers to bootstrap claude-flow-based projects

#### **@ruv/sparc-ui** ✅ Published | 🔗 Optional
- **NPM**: `npm install @ruv/sparc-ui` (v0.1.4)
- **Purpose**: UI components for SPARC framework
- **Usage in claude-flow**:
  - Can be used with ruvi for enhanced dashboard UI
  - Provides pre-built components for workflow visualization
  - Optional: Alternative to custom ruvi UI components

#### **vscode-remote-mcp** ✅ Published | 🔗 Optional
- **NPM**: `npm install vscode-remote-mcp` (v1.0.4)
- **Purpose**: MCP server for VSCode Remote integration
- **Usage in claude-flow**:
  - Enables claude-flow agents to interact with VSCode remotely
  - Allows agents to read/write code in VSCode workspaces
  - Used when agents need direct IDE integration

#### **@agentics.org/agentic-mcp** ✅ Published | 🔗 Enhanced
- **NPM**: `npm install @agentics.org/agentic-mcp` (v1.0.4)
- **Purpose**: Agentic MCP Server with advanced AI capabilities
- **Usage in claude-flow**:
  - Provides MCP tools for web search, summarization, database querying
  - Can be integrated as an MCP tool provider for agents
  - Extends agent capabilities with research and data access tools

#### **dspy.ts** ✅ Published | 🔗 Enhanced
- **NPM**: `npm install dspy.ts` (v0.1.3)
- **Purpose**: Declarative Self-Learning TypeScript framework
- **Usage in claude-flow**:
  - Framework for compositional LM pipelines
  - Can be used for self-improving prompt strategies
  - Implements DSPy concepts in TypeScript
  - Used for advanced prompt optimization within agents

#### **qudag** ✅ Published | 🔗 Optional
- **NPM**: `npm install qudag` (v1.2.1)
- **Purpose**: Quantum-Resistant Distributed Communication Platform
- **Usage in claude-flow**:
  - Optional: Provides quantum-resistant communication between nodes
  - Used when high security is required
  - Implements post-quantum cryptography for agent communication

#### **agenticsjs** ✅ Published | 🔗 Optional
- **NPM**: `npm install agenticsjs` (v1.0.5)
- **Purpose**: Intelligent interactive search library
- **Usage in claude-flow**:
  - Can be integrated for enhanced search capabilities
  - Provides real-time search with visualization
  - Optional: Used when agents need advanced search UI

---

## Complete System Flow: End-to-End Example

### Task: "Analyze this codebase and suggest improvements"

This example demonstrates how ALL the packages work together:

1. **Entry Point** (claude-flow ✅)
   - User submits task via ruvi dashboard
   - claude-flow receives and parses request
   - Creates workflow plan: parse → analyze → suggest

2. **Agent Orchestration** (agentic-flow 🔄 + agentic-jujutsu 🔄)
   - agentic-flow spawns specialized agents:
     - Code Parser Agent (lean-agentic for speed)
     - Analyzer Agent (full agent with GNN capabilities)
     - Suggestion Agent (with ruvllm for generation)
   - agentic-jujutsu registers agents and prevents conflicts

3. **Task Distribution** (@ruvector/router 🔄 + @ruvector/cluster 🔄)
   - Router analyzes current cluster load
   - Distributes tasks to optimal @ruvector/server nodes
   - Cluster manager ensures high availability

4. **Code Parsing** (Agent + Compute Layer)
   - Parser agent uses @ruvector/ruvllm 🔄 for code understanding
   - Generates code embeddings via @ruvector/tiny-dancer 🔄
   - Stores embeddings in ruvector 🔄 for semantic search
   - Updates state in agentdb 🔄

5. **Dependency Analysis** (@ruvector/gnn 🔄 + @ruvector/graph-node 🔄)
   - Builds dependency graph of codebase
   - GNN analyzes architectural patterns
   - Identifies code smells and structural issues
   - Uses psycho-symbolic-integration 🔄 for logical verification

6. **Pattern Matching** (ruvector 🔄 + @ruvector/core 🔄)
   - Analyzer queries ruvector for similar code patterns
   - Finds best practices from knowledge base
   - Uses agent-booster 🔄 to cache common queries
   - Leverages @agentic-robotics/self-learning 🔄 for improved suggestions

7. **Suggestion Generation** (@ruvector/ruvllm 🔄)
   - Suggestion agent synthesizes findings
   - Generates actionable improvements
   - Validates suggestions through psycho-symbolic-integration 🔄

8. **Real-time Streaming** (midstreamer 🔄)
   - Results streamed in real-time to ruvi 🔄 dashboard
   - User sees progress as agents work
   - Can provide feedback mid-execution

9. **Persistence** (agentdb 🔄 + ruvector 🔄)
   - Execution trace stored in agentdb
   - Learned patterns stored in ruvector
   - @agentic-robotics/self-learning analyzes for future improvements

10. **Optional Enhancements**:
    - If images in codebase: @foxruv/iris 🔄 analyzes diagrams
    - If voice command: ruvector-sona 🔄 processes audio
    - If GPU available: cuda-wasm ✅ accelerates computations
    - If VSCode integration: vscode-remote-mcp ✅ applies changes

---

## Installation Guide

### Minimal Setup (Core Only)

```bash
# Published packages (currently available)
npm install claude-flow          # Main orchestrator
npm install ruv-swarm           # Swarm engine (integrated in claude-flow)

# When other core packages are published:
# npm install agentic-flow
# npm install ruvector
# npm install agentdb
# npm install @ruvector/ruvllm
# npm install @ruvector/core
```

### Enhanced Setup (Recommended)

```bash
# Core + performance enhancements
npm install claude-flow
npm install ruv-swarm
npm install cuda-wasm            # GPU acceleration

# When published:
# npm install agent-booster
# npm install @ruvector/router
# npm install @ruvector/cluster
```

### Full Featured Setup

```bash
# All published packages
npm install claude-flow ruv-swarm cuda-wasm
npm install @agentics.org/sparc2 @agentics.org/agentic-mcp
npm install dspy.ts qudag agenticsjs
npm install vscode-remote-mcp
npm install create-sparc @ruv/sparc-ui

# When all planned packages publish:
# npm install agentic-flow agent-booster lean-agentic
# npm install ruvector @ruvector/core agentdb
# npm install @ruvector/ruvllm @ruvector/router
# npm install midstreamer ruvi
# ... and all others listed above
```

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


---

## 🔄 Complete System Initialization & Deployment Flows

This section provides comprehensive guidance on initializing, configuring, and deploying a fully-featured self-improving agentic system using the RuVector ecosystem.

### 🎯 Architecture Overview: Self-Improving Agentic System

The diagram below shows how all components interconnect in a production self-improving agentic system.

**[View Full Mermaid Diagram](https://mermaid.live)** - Copy the code below into Mermaid Live Editor for interactive viewing.

\`\`\`mermaid
graph TB
    subgraph "Entry Points"
        USER[User Request]
        NPX[NPX Commands]
    end
    
    subgraph "Orchestration"
        CF[claude-flow]
        AF[agentic-flow]
        RS[research-swarm]
    end
    
    subgraph "Intelligence"
        AJ[agentic-jujutsu]
        SONA[@ruvector/sona]
        IRIS[@foxruv/iris]
        RUVLLM[@ruvector/ruvllm]
    end
    
    subgraph "Routing"
        ROUTER[@ruvector/router]
        CLUSTER[@ruvector/cluster]
        SERVER[@ruvector/server]
    end
    
    subgraph "Storage"
        RUVEC[ruvector]
        CORE[@ruvector/core]
        AGENTDB[agentdb]
        PGCLI[@ruvector/postgres-cli]
    end
    
    subgraph "Learning"
        SELFLEARN[@agentic-robotics/self-learning]
        AGENTBOOST[agent-booster]
    end
    
    USER --> CF
    NPX --> CF
    CF --> AF
    CF --> RS
    AF --> SONA
    AF --> IRIS
    AF --> RUVLLM
    AF --> AGENTDB
    AJ --> ROUTER
    ROUTER --> CLUSTER
    RUVEC --> CORE
    AGENTDB --> PGCLI
    AGENTDB --> SELFLEARN
    SELFLEARN --> SONA
    RUVEC -.Feedback.-> SELFLEARN
\`\`\`

### 📦 NPX Quick Start Commands

\`\`\`bash
# 1. Create new project with SPARC methodology
npx create-sparc my-agentic-system
cd my-agentic-system

# 2. Initialize Flow Nexus (Gamified MCP Platform with 256 free credits)
npx flow-nexus

# 3. Initialize Ruvi CLI (Agentic Engineering Console)
npx ruvi init
npx ruvi start --mcp

# 4. Deploy Claude-Flow with full stack
npx claude-flow init --full-stack
npx claude-flow deploy --production

# 5. Start Research Swarm
npx research-swarm start --agents 10 --goap

# 6. Launch Agentics Hackathon Environment
npx agentics-hackathon init --gemini
\`\`\`

### 🔧 Step-by-Step Initialization

#### Step 1: Foundation Layer (Core + Storage)

\`\`\`bash
# Install foundation
npm install @ruvector/core ruvector agentdb @ruvector/postgres-cli
\`\`\`

\`\`\`javascript
//  init.js - Foundation Layer
const { Ruvector } = require('ruvector');
const { AgentDB } = require('agentdb');

// 1. Initialize RuVector
const vectorDb = new Ruvector({
  dimension: 1536,
  backend: '@ruvector/postgres-cli',
  connectionString: process.env.DATABASE_URL
});
await vectorDb.initialize();

// 2. Initialize AgentDB
const agentDb = new AgentDB({
  persistence: true,
  backend: vectorDb,
  causality: true,
  reflexion: true
});
await agentDb.initialize();

console.log('✅ Foundation layer ready');
\`\`\`

#### Step 2: LLM Inference Layer

\`\`\`bash
# Install LLM components
npm install @ruvector/ruvllm @ruvector/sona @foxruv/iris
\`\`\`

\`\`\`javascript
// 1. Initialize RuvLLM
const { RuvLLM } = require('@ruvector/ruvllm');
const llm = new RuvLLM({
  models: ['gpt-4', 'claude-3-opus'],
  reasoningMode: 'trm',
  cache: agentDb,
  vectorStore: vectorDb
});
await llm.initialize();

// 2. Initialize SONA
const { SONA } = require('@ruvector/sona');
const sona = new SONA({
  llm: llm,
  agentDb: agentDb,
  adaptiveLearning: true,
  reasoningBank: true
});
await sona.initialize();

// 3. Initialize Iris
const { Iris } = require('@foxruv/iris');
const iris = new Iris({
  llm: llm,
  sona: sona,
  driftDetection: true,
  autoRetrain: true
});
await iris.initialize();

console.log('✅ LLM layer ready');
\`\`\`

#### Step 3: Orchestration Layer

\`\`\`bash
# Install orchestration
npm install agentic-flow agentic-jujutsu research-swarm claude-flow
\`\`\`

\`\`\`javascript
// 1. Initialize Agentic-Flow
const { AgenticFlow } = require('agentic-flow');
const agenticFlow = new AgenticFlow({
  agentDb: agentDb,
  llm: llm,
  vectorDb: vectorDb,
  maxConcurrentAgents: 50
});
await agenticFlow.initialize();

// 2. Initialize Agentic-Jujutsu
const { AgenticJujutsu } = require('agentic-jujutsu');
const coordinator = new AgenticJujutsu({
  agenticFlow: agenticFlow,
  agentDb: agentDb,
  conflictResolution: 'priority-based'
});
await coordinator.initialize();

// 3. Initialize Claude-Flow
const { ClaudeFlow } = require('claude-flow');
const claudeFlow = new ClaudeFlow({
  agenticFlow: agenticFlow,
  coordinator: coordinator,
  llm: llm,
  sona: sona,
  iris: iris,
  vectorDb: vectorDb,
  agentDb: agentDb,
  reasoningBank: true
});
await claudeFlow.initialize();

console.log('✅ Orchestration layer ready');
\`\`\`

#### Step 4: Self-Learning Loop

\`\`\`bash
# Install self-learning
npm install @agentic-robotics/self-learning agent-booster
\`\`\`

\`\`\`javascript
const { SelfLearning } = require('@agentic-robotics/self-learning');
const selfLearning = new SelfLearning({
  agentDb: agentDb,
  vectorDb: vectorDb,
  reinforcementLearning: true,
  swarmIntelligence: true
});
await selfLearning.initialize();

// Connect feedback loop
selfLearning.on('pattern-learned', async (pattern) => {
  await agentDb.storePattern(pattern);
  await sona.updateModel(pattern);
});

agentDb.on('execution-complete', async (trace) => {
  await selfLearning.analyze(trace);
});

console.log('✅ Self-learning loop active');
\`\`\`

### 🚀 Complete Deployment Sequence Diagram

\`\`\`mermaid
sequenceDiagram
    participant Dev
    participant NPX
    participant CF as Claude-Flow
    participant AF as Agentic-Flow
    participant RV as RuVector
    participant ADB as AgentDB
    participant RL as RuvLLM
    participant SL as Self-Learning
    
    Dev->>NPX: npx claude-flow init
    NPX->>CF: Initialize
    CF->>RV: Setup vector DB
    RV-->>CF: Ready
    CF->>ADB: Setup agent DB
    ADB-->>CF: Ready
    CF->>RL: Setup LLM engine
    RL-->>CF: Ready
    CF->>AF: Setup agent lifecycle
    AF-->>CF: Ready
    CF->>SL: Setup learning loop
    SL-->>CF: Ready
    CF-->>Dev: System ready
    
    Dev->>CF: Submit task
    CF->>AF: Create agents
    AF->>RV: Query knowledge
    AF->>RL: Generate response
    AF->>ADB: Store results
    ADB->>SL: Trigger learning
    SL->>RL: Update model
    CF-->>Dev: Task complete
\`\`\`

### 🐳 Docker Compose Production Deployment

\`\`\`yaml
version: '3.8'

services:
  postgres:
    image: ankane/pgvector:latest
    environment:
      POSTGRES_DB: agentic
      POSTGRES_USER: ruvector
      POSTGRES_PASSWORD: \${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"
  
  claude-flow:
    image: ruvnet/claude-flow:latest
    environment:
      DATABASE_URL: postgres://ruvector:\${DB_PASSWORD}@postgres:5432/agentic
      OPENAI_API_KEY: \${OPENAI_API_KEY}
      ANTHROPIC_API_KEY: \${ANTHROPIC_API_KEY}
      REASONING_BANK: "true"
    depends_on:
      - postgres
    ports:
      - "3001:3001"
  
  ruvi:
    image: ruvnet/ruvi:latest
    environment:
      CLAUDE_FLOW_URL: http://claude-flow:3001
    ports:
      - "3000:3000"
    depends_on:
      - claude-flow

volumes:
  pgdata:
\`\`\`

**Deploy:**

\`\`\`bash
# Set environment variables
export DB_PASSWORD="secure_password"
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."

# Start services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f claude-flow
\`\`\`

### ✅ System Verification

\`\`\`javascript
// verify.js - Complete system test
const { ClaudeFlow } = require('claude-flow');

async function verify() {
  const flow = await ClaudeFlow.connect('http://localhost:3001');
  
  // Test vector DB
  const vecTest = await flow.vectorDb.insert({
    vector: new Array(1536).fill(0).map(() => Math.random()),
    metadata: { test: true }
  });
  console.log('✅ RuVector operational');
  
  // Test AgentDB
  const agent = await flow.agentDb.createAgent({
    name: 'test',
    capabilities: ['research']
  });
  console.log('✅ AgentDB operational');
  
  // Test LLM
  const response = await flow.llm.generate({
    prompt: 'Hello',
    maxTokens: 10
  });
  console.log('✅ RuvLLM operational');
  
  // Test workflow
  const result = await flow.execute({
    task: 'Test task',
    agents: 1
  });
  console.log('✅ Workflow operational');
  
  console.log('\n🎉 All systems operational!');
}

verify().catch(console.error);
\`\`\`

### 📚 Quick NPX Command Reference

| Command | Purpose |
|---------|---------|
| `npx create-sparc <name>` | Scaffold new project |
| `npx flow-nexus` | Start gamified MCP platform |
| `npx claude-flow init` | Initialize Claude-Flow |
| `npx ruvi start` | Start Ruvi dashboard |
| `npx research-swarm start` | Start research swarm |
| `npx @ruvector/cli query` | Query RuVector DB |
| `npx goalie research <topic>` | AI research assistant |

### 🔗 Self-Improving Cycle

\`\`\`mermaid
graph LR
    A[Execute Task] --> B[Store Trace<br/>in AgentDB]
    B --> C[Self-Learning<br/>Analyzes]
    C --> D[Update SONA<br/>Model]
    D --> E[Optimize<br/>Cache]
    E --> F[Deploy<br/>Improvement]
    F --> A
\`\`\`

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
## Complete NPM Package Registry (161 Packages)

This section documents ALL 161 packages published by @ruvnet on NPM, organized by category for easy reference.

**Last Updated**: 2025-12-09
**Total Packages**: 161

---

### Core Orchestration & Flow (4 packages)

#### **agentic-flow** v1.10.2
- Production-ready AI agent orchestration platform with 66 specialized agents, 213 MCP tools, ReasoningBank learning memory, and autonomous multi-agent ...
- `npm install agentic-flow`

#### **claude-flow** v2.7.47
- Enterprise-grade AI agent orchestration with WASM-powered ReasoningBank memory and AgentDB vector database (always uses latest agentic-flow)...
- `npm install claude-flow`

#### **flow-nexus** v0.1.128
- 🚀 AI-Powered Swarm Intelligence Platform - Gamified MCP Development with 70+ Tools...
- `npm install flow-nexus`

#### **ruv-swarm** v1.0.20
- High-performance neural network swarm orchestration in WebAssembly...
- `npm install ruv-swarm`

---

### Vector Database (RuVector Core) (12 packages)

#### **@ruvector/cli** v0.1.25
- Command-line interface for RuVector vector database...
- `npm install @ruvector/cli`

#### **@ruvector/cluster** v0.1.0
- Distributed clustering and coordination for RuVector - auto-sharding, Raft consensus integration...
- `npm install @ruvector/cluster`

#### **@ruvector/core** v0.1.28
- High-performance vector database with HNSW indexing - 50k+ inserts/sec, built in Rust for AI/ML similarity search and semantic search applications...
- `npm install @ruvector/core`

#### **@ruvector/node** v0.1.18
- High-performance Rust vector database for Node.js with HNSW indexing and SIMD optimizations...
- `npm install @ruvector/node`

#### **@ruvector/postgres-cli** v0.2.6
- Advanced AI vector database CLI for PostgreSQL - pgvector drop-in replacement with 53+ SQL functions, 39 attention mechanisms, GNN layers, hyperbolic ...
- `npm install @ruvector/postgres-cli`

#### **@ruvector/router** v0.1.25
- Semantic router for AI agents - vector-based intent matching with HNSW indexing and SIMD acceleration...
- `npm install @ruvector/router`

#### **@ruvector/rvlite** v0.2.4
- Standalone vector database with SQL, SPARQL, and Cypher - powered by RuVector WASM...
- `npm install @ruvector/rvlite`

#### **@ruvector/server** v0.1.0
- HTTP/gRPC server for RuVector - REST API with streaming support...
- `npm install @ruvector/server`

#### **ruvector** v0.1.35
- High-performance vector database for Node.js with automatic native/WASM fallback...
- `npm install ruvector`

#### **ruvector-core** v0.1.26
- High-performance vector database with HNSW indexing - 50k+ inserts/sec, built in Rust for AI/ML similarity search and semantic search applications...
- `npm install ruvector-core`

#### **ruvector-extensions** v0.1.0
- Advanced features for ruvector: embeddings, UI, exports, temporal tracking, and persistence...
- `npm install ruvector-extensions`

#### **ruvector-sona** v0.1.4
- Self-Optimizing Neural Architecture - Runtime-adaptive learning for LLM routers with two-tier LoRA, EWC++, and ReasoningBank...
- `npm install ruvector-sona`

---

### Neural Trading Suite (25 packages)

#### **@neural-trader/agentic-accounting-agents** v0.1.1
- Multi-agent swarm orchestration for autonomous accounting operations with ReasoningBank self-learning, distributed task coordination, and intelligent ...
- `npm install @neural-trader/agentic-accounting-agents`

#### **@neural-trader/agentic-accounting-cli** v0.1.1
- Command-line interface for neural-trader's agentic accounting system with interactive tax calculators, transaction management, compliance reports, and...
- `npm install @neural-trader/agentic-accounting-cli`

#### **@neural-trader/agentic-accounting-core** v0.1.1
- Core TypeScript library for autonomous cryptocurrency accounting with transaction management, compliance automation, fraud detection, and AgentDB-powe...
- `npm install @neural-trader/agentic-accounting-core`

#### **@neural-trader/agentic-accounting-rust-core** v0.1.1
- High-performance Rust native addon (NAPI) for cryptocurrency tax calculations with FIFO, LIFO, HIFO cost basis methods and optimized transaction proce...
- `npm install @neural-trader/agentic-accounting-rust-core`

#### **@neural-trader/agentic-accounting-types** v0.1.1
- Comprehensive TypeScript type definitions and interfaces for neural-trader's agentic accounting system with cryptocurrency tax calculations, cost basi...
- `npm install @neural-trader/agentic-accounting-types`

#### **@neural-trader/backend** v2.2.1
- High-performance Neural Trader backend with native Rust bindings via NAPI-RS...
- `npm install @neural-trader/backend`

#### **@neural-trader/backtesting** v2.6.0
- Neural Trader backtesting engine and historical simulation...
- `npm install @neural-trader/backtesting`

#### **@neural-trader/benchoptimizer** v2.1.1
- Comprehensive benchmarking, validation, and optimization tool for neural-trader packages...
- `npm install @neural-trader/benchoptimizer`

#### **@neural-trader/brokers** v2.1.1
- Broker integrations for Neural Trader - Alpaca, Interactive Brokers, TD Ameritrade...
- `npm install @neural-trader/brokers`

#### **@neural-trader/core** v2.0.0
- Ultra-low latency neural trading engine with Rust + Node.js bindings...
- `npm install @neural-trader/core`

#### **@neural-trader/e2b-strategies** v1.1.1
- Production-ready E2B sandbox trading strategies with 10-50x performance improvements, circuit breakers, and comprehensive observability...
- `npm install @neural-trader/e2b-strategies`

#### **@neural-trader/execution** v2.6.0
- Neural Trader trade execution and order management...
- `npm install @neural-trader/execution`

#### **@neural-trader/features** v2.1.2
- Technical indicators for Neural Trader - SMA, RSI, MACD, Bollinger Bands, and 150+ indicators...
- `npm install @neural-trader/features`

#### **@neural-trader/market-data** v2.1.1
- Market data providers for Neural Trader - Alpaca, Polygon, Yahoo Finance...
- `npm install @neural-trader/market-data`

#### **@neural-trader/neural** v2.6.0
- Neural Trader neural network training and prediction...
- `npm install @neural-trader/neural`

#### **@neural-trader/neuro-divergent** v2.1.1
- Neural forecasting library with 27+ models (NHITS, LSTM, Transformers) for time series prediction...
- `npm install @neural-trader/neuro-divergent`

#### **@neural-trader/news-trading** v2.1.1
- News-driven trading for Neural Trader - real-time sentiment analysis and event-driven strategies...
- `npm install @neural-trader/news-trading`

#### **@neural-trader/portfolio** v2.6.0
- Neural Trader portfolio management and optimization...
- `npm install @neural-trader/portfolio`

#### **@neural-trader/prediction-markets** v2.1.1
- Prediction markets for Neural Trader - Polymarket, Augur integration with expected value calculations...
- `npm install @neural-trader/prediction-markets`

#### **@neural-trader/predictor** v0.1.0
- Conformal prediction for neural trading with guaranteed intervals...
- `npm install @neural-trader/predictor`

#### **@neural-trader/risk** v2.6.0
- Neural Trader risk management and analysis...
- `npm install @neural-trader/risk`

#### **@neural-trader/sports-betting** v2.1.1
- Sports betting for Neural Trader - arbitrage detection, Kelly sizing, syndicate management...
- `npm install @neural-trader/sports-betting`

#### **@neural-trader/strategies** v2.6.0
- Neural Trader strategy management and backtesting functionality...
- `npm install @neural-trader/strategies`

#### **@neural-trader/syndicate** v2.1.1
- Investment syndicate management with Kelly Criterion allocation, voting, and performance tracking...
- `npm install @neural-trader/syndicate`

#### **neural-trader** v2.7.1
- High-performance neural trading system with native HNSW vector search + SIMD optimization (150x faster), complete NAPI API (178 functions), advanced C...
- `npm install neural-trader`

---

### Graph Neural Networks (2 packages)

#### **@ruvector/gnn** v0.1.22
- Graph Neural Network capabilities for Ruvector - Node.js bindings...
- `npm install @ruvector/gnn`

#### **@ruvector/graph-node** v0.1.25
- Native Node.js bindings for RuVector Graph Database with hypergraph support, Cypher queries, and persistence - 10x faster than WASM...
- `npm install @ruvector/graph-node`

---

### Attention Mechanisms (1 packages)

#### **@ruvector/attention** v0.1.3
- High-performance attention mechanisms for Node.js...
- `npm install @ruvector/attention`

---

### Agentic Systems & Robotics (15 packages)

#### **@agentic-robotics/cli** v0.2.3
- CLI tools for agentic robotics framework...
- `npm install @agentic-robotics/cli`

#### **@agentic-robotics/core** v0.2.1
- High-performance agentic robotics framework - Core bindings...
- `npm install @agentic-robotics/core`

#### **@agentic-robotics/linux-x64-gnu** v0.2.0
- agentic-robotics native bindings for Linux x64 (GNU)...
- `npm install @agentic-robotics/linux-x64-gnu`

#### **@agentic-robotics/self-learning** v1.0.0
- AI-powered self-learning optimization system with swarm intelligence, PSO, NSGA-II, evolutionary algorithms for autonomous robotics, multi-agent syste...
- `npm install @agentic-robotics/self-learning`

#### **@agentics.org/sparc2** v2.0.25
- SPARC 2.0 - Autonomous Vector Coding Agent + MCP. SPARC 2.0, vectorized AI code analysis, is an intelligent coding agent framework built to automate a...
- `npm install @agentics.org/sparc2`

#### **@foxruv/iris-agentic-synth** v1.0.5
- ⚡ High-performance synthetic prompt generation with genetic evolution, streaming, and multi-model routing. 90%+ cache hit rate, <15ms P99 latency, no ...
- `npm install @foxruv/iris-agentic-synth`

#### **@ruvector/agentic-synth** v0.1.6
- High-performance synthetic data generator for AI/ML training, RAG systems, and agentic workflows with DSPy.ts, Gemini, OpenRouter, and vector database...
- `npm install @ruvector/agentic-synth`

#### **agent-booster** v0.2.2
- Ultra-fast code editing engine - 52x faster than Morph LLM at $0 cost...
- `npm install agent-booster`

#### **agentdb** v1.6.1
- AgentDB - Frontier Memory Features with MCP Integration and Direct Vector Search: Causal reasoning, reflexion memory, skill library, automated learnin...
- `npm install agentdb`

#### **agentic-jujutsu** v2.3.6
- AI agent coordination for Jujutsu VCS with quantum-ready architecture, QuantumDAG consensus, AgentDB learning, and zero-dependency deployment...
- `npm install agentic-jujutsu`

#### **agentic-payments** v0.1.13
- Dual-protocol payment infrastructure for autonomous AI commerce (AP2 + ACP)...
- `npm install agentic-payments`

#### **agentic-robotics** v0.2.4
- High-performance agentic robotics framework with ROS2 compatibility - Complete toolkit...
- `npm install agentic-robotics`

#### **agentics-hackathon** v1.3.4
- CLI and MCP server for the Agentics Foundation TV5 Hackathon - Build the future of agentic AI with Google Cloud, Gemini, Claude, and open-source tools...
- `npm install agentics-hackathon`

#### **agenticsjs** v1.0.5
- AgenticJS is a powerful and flexible JavaScript library designed to provide an intelligent and interactive search experience with real-time results an...
- `npm install agenticsjs`

#### **lean-agentic** v0.3.2
- High-performance WebAssembly theorem prover with dependent types, hash-consing (150x faster), Ed25519 proof signatures, MCP support for Claude Code, A...
- `npm install lean-agentic`

---

### Model Context Protocol (MCP) Servers (9 packages)

#### **@agentic-robotics/mcp** v0.2.2
- Model Context Protocol server for agentic robotics with AgentDB integration...
- `npm install @agentic-robotics/mcp`

#### **@agentics.org/agentic-mcp** v1.0.4
- Agentic MCP Server with advanced AI capabilities including web search, summarization, database querying, and customer support. Built by the Agentics F...
- `npm install @agentics.org/agentic-mcp`

#### **@neural-trader/agentic-accounting-mcp** v0.1.1
- Model Context Protocol (MCP) server for Claude Desktop integration, exposing intelligent accounting tools, tax calculators, and autonomous agents for ...
- `npm install @neural-trader/agentic-accounting-mcp`

#### **@neural-trader/mcp** v2.1.0
- Model Context Protocol (MCP) server for Neural Trader with 87+ trading tools...
- `npm install @neural-trader/mcp`

#### **@neural-trader/mcp-protocol** v2.0.0
- Model Context Protocol (MCP) JSON-RPC 2.0 protocol types for Neural Trader...
- `npm install @neural-trader/mcp-protocol`

#### **@qudag/mcp-sse** v0.1.0
- QuDAG MCP Server with Streamable HTTP transport for web integration...
- `npm install @qudag/mcp-sse`

#### **@qudag/mcp-stdio** v0.1.0
- QuDAG MCP server with STDIO transport for Claude Desktop integration...
- `npm install @qudag/mcp-stdio`

#### **strange-loops-mcp** v1.0.0
- MCP server for Strange Loops framework - nano-agent swarm with temporal consciousness...
- `npm install strange-loops-mcp`

#### **vscode-remote-mcp** v1.0.4
- Enhanced MCP server for VSCode Remote integration...
- `npm install vscode-remote-mcp`

---

### WebAssembly (WASM) Modules (9 packages)

#### **@ruvector/attention-wasm** v0.1.0
- WebAssembly bindings for ruvector-attention - high-performance attention mechanisms...
- `npm install @ruvector/attention-wasm`

#### **@ruvector/gnn-wasm** v0.1.0
- WebAssembly bindings for ruvector-gnn - Graph Neural Network layers for browsers...
- `npm install @ruvector/gnn-wasm`

#### **@ruvector/graph-wasm** v0.1.25
- WebAssembly bindings for RuVector graph database with Neo4j-inspired API and Cypher support...
- `npm install @ruvector/graph-wasm`

#### **@ruvector/router-wasm** v0.1.0
- WebAssembly bindings for ruvector-router - Semantic router with HNSW vector search for browsers...
- `npm install @ruvector/router-wasm`

#### **@ruvector/tiny-dancer-wasm** v0.1.0
- WebAssembly bindings for Tiny Dancer - FastGRNN neural inference for AI routing in browsers...
- `npm install @ruvector/tiny-dancer-wasm`

#### **@ruvector/wasm** v0.1.16
- High-performance Rust vector database for browsers via WASM...
- `npm install @ruvector/wasm`

#### **bmssp-wasm** v1.0.0
- Blazing fast graph pathfinding SDK powered by WebAssembly. 10-15x faster than JavaScript implementations....
- `npm install bmssp-wasm`

#### **cuda-wasm** v1.1.1
- High-performance CUDA to WebAssembly/WebGPU transpiler with Rust safety - Run GPU kernels in browsers and Node.js...
- `npm install cuda-wasm`

#### **ruvector-attention-wasm** v0.1.0
- High-performance attention mechanisms for WebAssembly - Transformer, Hyperbolic, Flash, MoE, and Graph attention...
- `npm install ruvector-attention-wasm`

---

### Self-Learning & Optimization (4 packages)

#### **@ruvector/ruvllm** v0.2.3
- Self-learning LLM orchestration with TRM recursive reasoning, SONA adaptive learning, HNSW memory, FastGRNN routing, and SIMD inference...
- `npm install @ruvector/ruvllm`

#### **@ruvector/sona** v0.1.4
- Self-Optimizing Neural Architecture (SONA) - Runtime-adaptive learning with LoRA, EWC++, and ReasoningBank for LLM routers and AI systems. Sub-millise...
- `npm install @ruvector/sona`

#### **@ruvector/sona-linux-x64-musl** v0.1.4
- No description...
- `npm install @ruvector/sona-linux-x64-musl`

#### **@ruvector/tiny-dancer** v0.1.15
- Neural router for AI agent orchestration - FastGRNN-based intelligent routing with circuit breaker, uncertainty estimation, and hot-reload...
- `npm install @ruvector/tiny-dancer`

---

### CLI & Developer Tools (1 packages)

#### **@qudag/cli** v0.1.0
- Command-line interface for QuDAG quantum-resistant DAG operations...
- `npm install @qudag/cli`

---

### Example Implementations (12 packages)

#### **@neural-trader/example-dynamic-pricing** v1.0.0
- Self-learning dynamic pricing with RL optimization and swarm strategy exploration...
- `npm install @neural-trader/example-dynamic-pricing`

#### **@neural-trader/example-energy-forecasting** v1.0.0
- Self-learning energy forecasting with conformal prediction and swarm-based ensemble models...
- `npm install @neural-trader/example-energy-forecasting`

#### **@neural-trader/example-energy-grid-optimization** v0.1.0
- Self-learning energy grid optimization with load forecasting, unit commitment, and swarm scheduling...
- `npm install @neural-trader/example-energy-grid-optimization`

#### **@neural-trader/example-evolutionary-game-theory** v1.0.0
- Self-learning evolutionary game theory with multi-agent tournaments, replicator dynamics, and ESS calculation...
- `npm install @neural-trader/example-evolutionary-game-theory`

#### **@neural-trader/example-healthcare-optimization** v1.0.0
- Healthcare optimization with self-learning patient forecasting and swarm-based staff scheduling...
- `npm install @neural-trader/example-healthcare-optimization`

#### **@neural-trader/example-logistics-optimization** v1.0.0
- Self-learning vehicle routing optimization with multi-agent swarm coordination...
- `npm install @neural-trader/example-logistics-optimization`

#### **@neural-trader/example-market-microstructure** v1.0.0
- Self-learning market microstructure analysis with AI-powered order book prediction, swarm-based feature engineering, and real-time liquidity optimizat...
- `npm install @neural-trader/example-market-microstructure`

#### **@neural-trader/example-neuromorphic-computing** v1.0.0
- Neuromorphic computing with Spiking Neural Networks, STDP learning, and reservoir computing for ultra-low-power ML...
- `npm install @neural-trader/example-neuromorphic-computing`

#### **@neural-trader/example-portfolio-optimization** v1.0.0
- Self-learning portfolio optimization with benchmark swarms and multi-objective optimization...
- `npm install @neural-trader/example-portfolio-optimization`

#### **@neural-trader/example-quantum-optimization** v1.0.0
- Quantum-inspired optimization algorithms with swarm-based circuit exploration for combinatorial and constraint problems...
- `npm install @neural-trader/example-quantum-optimization`

#### **@neural-trader/example-supply-chain-prediction** v1.0.0
- Self-learning demand forecasting and swarm-based inventory optimization with uncertainty quantification...
- `npm install @neural-trader/example-supply-chain-prediction`

#### **@ruvector/agentic-synth-examples** v0.1.6
- Production-ready examples for @ruvector/agentic-synth - DSPy training, multi-model benchmarking, and advanced synthetic data generation patterns...
- `npm install @ruvector/agentic-synth-examples`

---

### Native Platform Bindings (41 packages)

#### **@ruvector/attention-darwin-arm64** v0.1.1
- No description...
- `npm install @ruvector/attention-darwin-arm64`

#### **@ruvector/attention-darwin-x64** v0.1.1
- No description...
- `npm install @ruvector/attention-darwin-x64`

#### **@ruvector/attention-linux-arm64-gnu** v0.1.1
- No description...
- `npm install @ruvector/attention-linux-arm64-gnu`

#### **@ruvector/attention-linux-x64-gnu** v0.1.1
- No description...
- `npm install @ruvector/attention-linux-x64-gnu`

#### **@ruvector/attention-win32-x64-msvc** v0.1.1
- No description...
- `npm install @ruvector/attention-win32-x64-msvc`

#### **@ruvector/gnn-darwin-arm64** v0.1.19
- Graph Neural Network capabilities for Ruvector - darwin-arm64 platform...
- `npm install @ruvector/gnn-darwin-arm64`

#### **@ruvector/gnn-darwin-x64** v0.1.19
- Graph Neural Network capabilities for Ruvector - darwin-x64 platform...
- `npm install @ruvector/gnn-darwin-x64`

#### **@ruvector/gnn-linux-arm64-gnu** v0.1.19
- Graph Neural Network capabilities for Ruvector - linux-arm64-gnu platform...
- `npm install @ruvector/gnn-linux-arm64-gnu`

#### **@ruvector/gnn-linux-x64-gnu** v0.1.22
- Graph Neural Network capabilities for Ruvector - linux-x64-gnu platform...
- `npm install @ruvector/gnn-linux-x64-gnu`

#### **@ruvector/gnn-win32-x64-msvc** v0.1.19
- Graph Neural Network capabilities for Ruvector - win32-x64-msvc platform...
- `npm install @ruvector/gnn-win32-x64-msvc`

#### **@ruvector/graph-node-darwin-arm64** v0.1.15
- RuVector Graph Node.js bindings - darwin-arm64 platform...
- `npm install @ruvector/graph-node-darwin-arm64`

#### **@ruvector/graph-node-darwin-x64** v0.1.15
- RuVector Graph Node.js bindings - darwin-x64 platform...
- `npm install @ruvector/graph-node-darwin-x64`

#### **@ruvector/graph-node-linux-arm64-gnu** v0.1.15
- RuVector Graph Node.js bindings - linux-arm64-gnu platform...
- `npm install @ruvector/graph-node-linux-arm64-gnu`

#### **@ruvector/graph-node-linux-x64-gnu** v0.1.15
- RuVector Graph Node.js bindings - linux-x64-gnu platform...
- `npm install @ruvector/graph-node-linux-x64-gnu`

#### **@ruvector/graph-node-win32-x64-msvc** v0.1.15
- RuVector Graph Node.js bindings - win32-x64-msvc platform...
- `npm install @ruvector/graph-node-win32-x64-msvc`

#### **@ruvector/node-darwin-arm64** v0.1.18
- High-performance Rust vector database for Node.js - darwin-arm64 platform...
- `npm install @ruvector/node-darwin-arm64`

#### **@ruvector/node-darwin-x64** v0.1.18
- High-performance Rust vector database for Node.js - darwin-x64 platform...
- `npm install @ruvector/node-darwin-x64`

#### **@ruvector/node-linux-arm64-gnu** v0.1.18
- High-performance Rust vector database for Node.js - linux-arm64-gnu platform...
- `npm install @ruvector/node-linux-arm64-gnu`

#### **@ruvector/node-linux-x64-gnu** v0.1.18
- High-performance Rust vector database for Node.js - linux-x64-gnu platform...
- `npm install @ruvector/node-linux-x64-gnu`

#### **@ruvector/node-win32-x64-msvc** v0.1.18
- High-performance Rust vector database for Node.js - win32-x64-msvc platform...
- `npm install @ruvector/node-win32-x64-msvc`

#### **@ruvector/router-darwin-arm64** v0.1.25
- macOS ARM64 (Apple Silicon) native bindings for @ruvector/router...
- `npm install @ruvector/router-darwin-arm64`

#### **@ruvector/router-linux-arm64-gnu** v0.1.25
- Linux ARM64 (glibc) native bindings for @ruvector/router...
- `npm install @ruvector/router-linux-arm64-gnu`

#### **@ruvector/router-linux-x64-gnu** v0.1.25
- Linux x64 (glibc) native bindings for @ruvector/router...
- `npm install @ruvector/router-linux-x64-gnu`

#### **@ruvector/router-win32-x64-msvc** v0.1.25
- Windows x64 native bindings for @ruvector/router...
- `npm install @ruvector/router-win32-x64-msvc`

#### **@ruvector/ruvllm-darwin-arm64** v0.2.3
- RuvLLM native SIMD acceleration - darwin-arm64 (Apple Silicon) platform...
- `npm install @ruvector/ruvllm-darwin-arm64`

#### **@ruvector/ruvllm-darwin-x64** v0.2.3
- RuvLLM native SIMD acceleration - darwin-x64 (Intel Mac) platform...
- `npm install @ruvector/ruvllm-darwin-x64`

#### **@ruvector/ruvllm-linux-arm64-gnu** v0.2.3
- RuvLLM native SIMD acceleration - linux-arm64-gnu platform...
- `npm install @ruvector/ruvllm-linux-arm64-gnu`

#### **@ruvector/ruvllm-linux-x64-gnu** v0.2.3
- RuvLLM native SIMD acceleration - linux-x64-gnu platform...
- `npm install @ruvector/ruvllm-linux-x64-gnu`

#### **@ruvector/ruvllm-win32-x64-msvc** v0.2.3
- RuvLLM native SIMD acceleration - win32-x64-msvc (Windows) platform...
- `npm install @ruvector/ruvllm-win32-x64-msvc`

#### **@ruvector/sona-darwin-arm64** v0.1.4
- No description...
- `npm install @ruvector/sona-darwin-arm64`

#### **@ruvector/sona-darwin-x64** v0.1.4
- No description...
- `npm install @ruvector/sona-darwin-x64`

#### **@ruvector/sona-linux-arm64-gnu** v0.1.4
- No description...
- `npm install @ruvector/sona-linux-arm64-gnu`

#### **@ruvector/sona-linux-x64-gnu** v0.1.4
- SONA Linux x64 GNU native binding...
- `npm install @ruvector/sona-linux-x64-gnu`

#### **@ruvector/sona-win32-arm64-msvc** v0.1.4
- No description...
- `npm install @ruvector/sona-win32-arm64-msvc`

#### **@ruvector/sona-win32-x64-msvc** v0.1.4
- No description...
- `npm install @ruvector/sona-win32-x64-msvc`

#### **@ruvector/tiny-dancer-linux-x64-gnu** v0.1.15
- Linux x64 (glibc) native bindings for @ruvector/tiny-dancer...
- `npm install @ruvector/tiny-dancer-linux-x64-gnu`

#### **ruvector-core-darwin-arm64** v0.1.25
- macOS ARM64 (Apple Silicon M1/M2/M3) native binding for ruvector-core - High-performance vector database with HNSW indexing built in Rust...
- `npm install ruvector-core-darwin-arm64`

#### **ruvector-core-darwin-x64** v0.1.25
- macOS x64 (Intel) native binding for ruvector-core - High-performance vector database with HNSW indexing built in Rust...
- `npm install ruvector-core-darwin-x64`

#### **ruvector-core-linux-arm64-gnu** v0.1.25
- Linux ARM64 GNU native binding for ruvector-core - High-performance vector database with HNSW indexing built in Rust...
- `npm install ruvector-core-linux-arm64-gnu`

#### **ruvector-core-linux-x64-gnu** v0.1.26
- Linux x64 GNU native binding for ruvector-core - High-performance vector database with HNSW indexing built in Rust...
- `npm install ruvector-core-linux-x64-gnu`

#### **ruvector-core-win32-x64-msvc** v0.1.25
- Windows x64 MSVC native binding for ruvector-core - High-performance vector database with HNSW indexing built in Rust...
- `npm install ruvector-core-win32-x64-msvc`

---

### Specialized AI Tools (26 packages)

#### **@foxruv/e2b-runner** v2.0.1
- Production-grade E2B sandbox orchestration with agentic-flow swarms and AgentDB caching for distributed AI agent execution...
- `npm install @foxruv/e2b-runner`

#### **@foxruv/iris** v1.8.19
- AI-guided LLM optimization. Install → Tell Claude 'Read .claude/agents/iris.md' → Claude becomes your optimization guide. DSPy prompts, Ax hyperparame...
- `npm install @foxruv/iris`

#### **@foxruv/iris-core** v1.0.0
- Intelligent AI orchestration with multi-provider LM management, drift detection, auto-retraining, and performance tracking for production AI systems...
- `npm install @foxruv/iris-core`

#### **@foxruv/iris-ultrathink** v1.0.0
- Standalone MCP server with agentic-flow and agentdb integration...
- `npm install @foxruv/iris-ultrathink`

#### **@foxruv/nova-medicina** v1.0.0
- AI-powered medical analysis system with anti-hallucination safeguards - supplement to professional healthcare...
- `npm install @foxruv/nova-medicina`

#### **@qudag/napi-core** v0.1.0
- N-API bindings for QuDAG quantum-resistant DAG and cryptography...
- `npm install @qudag/napi-core`

#### **@ruv/sparc-ui** v0.1.4
- SPARC (Specification, Pseudocode, Architecture, Refinement, and Completion) Framework UI Components...
- `npm install @ruv/sparc-ui`

#### **@ruvnet/bmssp** v1.0.0
- Blazing fast graph pathfinding SDK powered by WebAssembly. 10-15x faster than JavaScript implementations....
- `npm install @ruvnet/bmssp`

#### **@ruvnet/strange-loop** v0.3.1
- Hyper-optimized strange loops with temporal consciousness and quantum-classical hybrid computing. NPX: npx strange-loops...
- `npm install @ruvnet/strange-loop`

#### **aidefence** v2.1.1
- AI Defence - Production-ready adversarial defense system for AI applications...
- `npm install aidefence`

#### **aidefense** v2.1.1
- AI Defense - Wrapper for aidefence (American spelling). Production-ready adversarial defense system for AI applications with real-time threat detectio...
- `npm install aidefense`

#### **consciousness-explorer** v1.1.1
- Advanced consciousness exploration SDK with genuine emergence detection, entity communication, and MCP tools...
- `npm install consciousness-explorer`

#### **create-sparc** v1.2.4
- NPX package to scaffold new projects with SPARC methodology structure...
- `npm install create-sparc`

#### **dspy.ts** v2.1.1
- DSPy.ts 2.1 - 100% DSPy Python compliant TypeScript framework with multi-agent orchestration, self-learning capabilities, MIPROv2 optimizer, and compr...
- `npm install dspy.ts`

#### **goalie** v1.3.1
- AI-powered research assistant with REAL Ed25519 cryptographic signatures, GOAP planning, and Perplexity API integration...
- `npm install goalie`

#### **midstreamer** v0.2.4
- WebAssembly-powered temporal analysis toolkit - DTW, LCS, scheduling, and meta-learning...
- `npm install midstreamer`

#### **psycho-symbolic-integration** v0.2.0
- Unified integration layer combining ultra-fast symbolic AI reasoning with intelligent synthetic data generation for context-aware applications...
- `npm install psycho-symbolic-integration`

#### **psycho-symbolic-reasoner** v1.0.7
- A psycho-symbolic reasoning framework combining symbolic AI with psychological context using Rust WASM and FastMCP integration...
- `npm install psycho-symbolic-reasoner`

#### **qudag** v1.2.1
- QuDAG - Quantum-Resistant Distributed Communication Platform...
- `npm install qudag`

#### **research-swarm** v1.2.2
- 🔬 Local SQLite-based AI research agent swarm with GOAP planning, multi-perspective analysis, long-horizon recursive framework, AgentDB self-learning, ...
- `npm install research-swarm`

#### **ruvi** v1.1.0
- rUv CLI - Agentic Engineering Console with MCP integration...
- `npm install ruvi`

#### **spiking-neural** v1.0.1
- High-performance Spiking Neural Network (SNN) with SIMD optimization - CLI & SDK...
- `npm install spiking-neural`

#### **strange-loops** v1.0.3
- Emergent intelligence through temporal consciousness - thousands of nano-agents collaborating in real-time with 500K+ ops/sec...
- `npm install strange-loops`

#### **sublinear-time-solver** v1.5.0
- The Ultimate Mathematical & AI Toolkit: Sublinear algorithms, consciousness exploration, psycho-symbolic reasoning, chaos analysis, and temporal predi...
- `npm install sublinear-time-solver`

#### **temporal-lead-solver** v0.1.0
- Achieve temporal computational lead through sublinear-time algorithms for diagonally dominant systems...
- `npm install temporal-lead-solver`

#### **temporal-neural-solver** v0.1.3
- ⚡ Ultra-fast neural network inference in WebAssembly - sub-microsecond latency...
- `npm install temporal-neural-solver`

---

