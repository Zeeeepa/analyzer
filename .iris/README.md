# .iris - FoxRuv Intelligence Backend

This folder contains all FoxRuv agent learning infrastructure.

## Structure

.iris/
├── config/          # Configuration files
├── agentdb/         # AgentDB storage (learning/memory)
├── cache/           # Cached MCP responses and embeddings
├── logs/            # MCP calls, Claude sessions, Iris evaluations
├── learning/        # Discovered patterns and optimizations
├── mcp/             # MCP installations and wrappers
└── tmp/             # Temporary execution artifacts

## Key Files

- **config/settings.json** - User preferences and settings
- **config/mcp-servers.json** - MCP server configurations
- **config/claude-contexts.json** - Active CLAUDE.md contexts
- **mcp/registry.json** - Available MCPs catalog

## Usage

This folder is managed by npx iris CLI. Do not edit manually unless you know what you're doing.

See docs/guides/FOXRUV_FOLDER_GUIDE.md for details.

