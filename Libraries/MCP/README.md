# MCP (Model Context Protocol)

This directory contains resources and references for integrating Model Context Protocol (MCP) capabilities into autonomous coding systems.

## Key Resource

### [AIRIS MCP Gateway](https://github.com/agiletec-inc/airis-mcp-gateway)

**Unified entrypoint for 25+ MCP servers. One command, zero manual provisioning.**

## Overview

AIRIS MCP Gateway is a comprehensive infrastructure solution that provides a unified access point to multiple MCP servers through a single gateway. It eliminates the complexity of manually provisioning and configuring individual MCP servers by providing:

### Core Features

- **Single Entry Point** - One gateway endpoint serving 25+ MCP servers
- **Zero-Config Setup** - Automated provisioning and configuration with `make init`
- **Multi-Editor Support** - Pre-configured for Codex CLI, Claude Code, Cursor, and Zed
- **Containerized Architecture** - Docker-based deployment with no local dependencies
- **Secrets Management** - Encrypted credential storage with Fernet encryption
- **Web UI** - Settings interface for managing servers and credentials at `http://ui.gateway.localhost:5273`

### Bundled MCP Servers (Enabled by Default)

- **filesystem** - Read-only workspace access
- **context7** - Code context and documentation
- **serena** - Semantic code analysis
- **mindbase** - Knowledge persistence and retrieval
- **sequential-thinking** - Reasoning workflow support
- **time**, **fetch**, **git**, **memory** - Utility servers
- **Self-Management** - Dynamic enable/disable orchestration

### Available Servers (Toggle via UI)

Supabase, Tavily, Notion, Stripe, Twilio, GitHub, Puppeteer, SQLite, and more can be enabled through the settings UI after providing credentials.

## Architecture

### Endpoints

- **Codex Streamable HTTP MCP** - `http://api.gateway.localhost:9400/api/v1/mcp`
- **Gateway SSE** - `http://api.gateway.localhost:9400/api/v1/mcp/sse`
- **FastAPI Docs** - `http://api.gateway.localhost:9400/docs`
- **Settings UI** - `http://ui.gateway.localhost:5273`

### Transport Layer

The gateway supports multiple transport mechanisms:
- **HTTP MCP** - RESTful API access with bearer token authentication
- **Server-Sent Events (SSE)** - Real-time streaming for Claude/Cursor
- **STDIO Bridge** - Automatic fallback using `mcp-proxy` for STDIO-based tools

### Configuration

All configuration is centralized through `.env`:
- Container listen ports
- Public domains and URLs
- Database credentials
- Encryption master key
- Workspace directory mappings

## Integration with Autonomous CI/CD

The MCP Gateway fits into the autonomous coding pipeline as a **capabilities layer**:

1. **Discovery Phase** - MCP servers provide tool discovery and capability enumeration
2. **Planning Phase** - Sequential thinking and memory servers support reasoning
3. **Analysis Phase** - Context7, Serena, and filesystem servers supply code intelligence
4. **Execution Phase** - Git, Puppeteer, and other action servers enable changes
5. **Validation Phase** - Multiple servers verify correctness and completeness
6. **Deployment Phase** - Integrated deployment tools push changes to production

### Key Benefits for Autonomous Systems

- **Unified Tool Access** - Single gateway eliminates per-tool authentication and discovery
- **Persistent Memory** - MindBase server maintains context across agent sessions
- **Self-Management** - Dynamic server orchestration based on task requirements
- **Credential Security** - Centralized, encrypted secrets management
- **Scalability** - Containerized architecture supports horizontal scaling
- **Observability** - Unified logging and monitoring through FastAPI

## Quick Start

```bash
git clone https://github.com/agiletec-inc/airis-mcp-gateway.git
cd airis-mcp-gateway
cp .env.example .env
make hosts-add  # Configure localhost DNS entries
make init       # Build, start, and register with editors
```

The `make init` command:
- Registers Codex CLI, Claude Code, and Cursor
- Imports existing MCP configs from editors
- Generates configuration from templates
- Builds all services and MCP servers
- Seeds databases and runs migrations
- Starts all services in background

## Development Workflow

| Command | Purpose |
|---------|---------|
| `make init` | Full clean install with editor registration |
| `make restart` | Stop/start cycle without editor import |
| `make up` | Start services only |
| `make down` | Stop containers, keep volumes |
| `make logs` | Stream logs from all services |
| `make dev` | Run Vite dev server for Settings UI |

## Integration with Analysis and Research

- **Analysis Modules** provide code understanding (AST, LSP, static analysis)
- **MCP Gateway** provides tool execution and external system integration
- **Research Frameworks** (ATLAS, research-swarm) provide task orchestration

Together, these create a complete autonomous development environment where:
- Analysis modules understand *what* the code does
- MCP servers enable *actions* to be taken
- Research frameworks determine *which* actions to perform

This three-tier architecture (Understanding → Capability → Orchestration) forms the foundation of truly autonomous coding agents.

## License

MIT - See [LICENSE](https://github.com/agiletec-inc/airis-mcp-gateway/blob/main/LICENSE)

