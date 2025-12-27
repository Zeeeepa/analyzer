---
context_type: root
priority: 0
---

# Project AI Guide - Root Context

This is the root CLAUDE.md file. Subdirectories may have their own CLAUDE.md files with context-specific information.

## Context System

This project uses **hierarchical context merging**:
- Subdirectory CLAUDE.md files EXTEND this root context
- They don't replace it - contexts are additive
- More specific contexts have higher priority

## FoxRuv Intelligence

This project uses @foxruv/iris for:
- **AgentDB** - Learning and memory
- **MCP Skills** - On-demand tool loading
- **Iris** - Autonomous optimization

## Available Contexts

Check subdirectories for domain-specific CLAUDE.md files:
- database/CLAUDE.md - Database schemas and tools
- api/CLAUDE.md - API specifications and tools
- ml/CLAUDE.md - ML model specifications

See .iris/config/claude-contexts.json for active contexts.



## Optimization Engine
Reference 
.iris/learning/skills/optimization.md` for optimization instructions (Ax/DSPy).
