# Analysis

This directory contains code analysis tools and adapters for static analysis, type checking, AST parsing, and LSP integration.

## Code Analysis & Quality (10)

### AST & Parsing
- **[graph-sitter](https://github.com/graph-sitter/graph-sitter)** (19.5k ⭐) - AST analysis with multi-language support
- **[tree-sitter](https://github.com/tree-sitter/tree-sitter)** (18k ⭐) - Incremental parsing system for building syntax trees
- **[jedi](https://github.com/davidhalter/jedi)** (5.8k ⭐) - Static analysis tool for Python autocompletion and analysis

### Python Linting & Code Quality
- **[ruff](https://github.com/astral-sh/ruff)** (35k ⭐) - Extremely fast Python linter written in Rust
- **[pylint](https://github.com/pylint-dev/pylint)** (5.3k ⭐) - Comprehensive Python code analysis
- **[vulture](https://github.com/jendrikseipp/vulture)** (3.5k ⭐) - Dead code detector for Python

### Type Checking & Inference
- **[mypy](https://github.com/python/mypy)** (19k ⭐) - Static type checker for Python
- **[pytype](https://github.com/google/pytype)** (4.9k ⭐) - Type inference and checking
- **[pyre-check](https://github.com/facebook/pyre-check)** (7k ⭐) - Performant type checker from Facebook

### Security & Metrics
- **[bandit](https://github.com/PyCQA/bandit)** (6.5k ⭐) - Security vulnerability scanner for Python
- **[radon](https://github.com/rubik/radon)** (1.7k ⭐) - Code complexity and maintainability metrics

### Refactoring
- **[rope](https://github.com/python-rope/rope)** (2k ⭐) - Python refactoring library

## LSP & Language Servers (2)

- **SolidLSP** - Robust LSP server implementation
- **[Serena](https://github.com/Zeeeepa/serena)** - Enhanced LSP framework with semantic analysis (see submodule)

## AI-Powered Tools (2)

- **[AutoGenLib](https://github.com/Zeeeepa/autogenlib)** - AI-powered automatic code fixes (see submodule)
- **Type Inference Stack** - Combined pytype + pyre-check for advanced type inference

## Modules in This Directory

### `analyzer.py`
Comprehensive Python code analysis orchestrator that combines:
- Graph-Sitter AST parsing
- LSP server integration
- Static analysis and diagnostics
- AI-powered fix generation

**Usage:**
```bash
python Libraries/Analysis/analyzer.py --target <file_or_directory> [options]
```

**Options:**
- `--verbose` - Detailed output
- `--comprehensive` - Run full analysis suite
- `--fix-errors` - Apply AI-powered fixes
- `--interactive` - Start interactive session
- `--format {terminal,json,html}` - Output format
- `--output <path>` - Save results to file

### `graph_sitter_adapter.py`
Adapter for tree-sitter/graph-sitter AST parsing:
- Multi-language syntax tree construction
- Symbol extraction and indexing
- Scope analysis
- Pattern matching across AST nodes

### `lsp_adapter.py`
Language Server Protocol integration:
- Diagnostics aggregation
- Symbol resolution
- Hover information
- Code actions and quick fixes

### `autogenlib_adapter.py`
AI-powered code fixes using AutoGenLib:
- Context-aware fix generation
- Diagnostic resolution
- Code transformation suggestions

### `static_libs.py`
Static analysis utilities:
- Code metrics calculation
- Dependency analysis
- Import graph construction
- Dead code detection

## Submodules

- **`autogenlib/`** - [AutoGenLib](https://github.com/Zeeeepa/autogenlib) - AI code fix generation
- **`graph-sitter/`** - [Graph-Sitter](https://github.com/Zeeeepa/graph-sitter) - Enhanced AST analysis
- **`serena/`** - [Serena](https://github.com/Zeeeepa/serena) - LSP framework

## Integration with CI/CD Pipeline

These analysis tools power the **Analysis Phase** of the autonomous coding pipeline:

1. **Discovery** - Research frameworks identify what needs analysis
2. **Planning** - ATLAS determines analysis scope and priorities
3. **Analysis** ← **THIS LAYER**
   - Parse code with tree-sitter/graph-sitter
   - Run static analysis (ruff, mypy, pylint, bandit)
   - Collect LSP diagnostics
   - Calculate code metrics (radon)
   - Detect dead code (vulture)
4. **Change Synthesis** - AI agents use analysis results to generate fixes
5. **Validation** - Re-run analysis to verify improvements
6. **Deployment** - Changes verified by analysis are committed

### Key Capabilities

- **Comprehensive Understanding** - Multi-layered analysis from syntax to semantics
- **Error Detection** - Security, type, style, and logic issues
- **Fix Generation** - AI-powered automatic corrections
- **Metrics & Insights** - Quantitative code quality measurements
- **Real-time Feedback** - LSP integration for live analysis

## Quick Start

### Basic Analysis
```bash
# Analyze a single file
python Libraries/Analysis/analyzer.py --target myfile.py

# Analyze entire directory
python Libraries/Analysis/analyzer.py --target ./src --comprehensive
```

### With AI Fixes
```bash
# Analyze and apply fixes automatically
python Libraries/Analysis/analyzer.py --target ./src --fix-errors --verbose
```

### Interactive Mode
```bash
# Start interactive analysis session
python Libraries/Analysis/analyzer.py --target ./src --interactive
```

### Custom Output
```bash
# Generate JSON report
python Libraries/Analysis/analyzer.py --target ./src --format json --output report.json

# Generate HTML report
python Libraries/Analysis/analyzer.py --target ./src --format html --output report.html
```

## Architecture

```
Analysis Layer
├── AST Parsing (tree-sitter, graph-sitter)
├── Static Analysis (ruff, pylint, mypy, bandit)
├── LSP Integration (SolidLSP, Serena)
├── Metrics & Quality (radon, vulture)
└── AI Enhancement (AutoGenLib, type inference)
```

This modular architecture allows autonomous agents to:
- Understand code at multiple abstraction levels
- Detect issues across security, style, types, and logic
- Generate context-aware fixes automatically
- Provide quantitative quality metrics
- Integrate seamlessly with development tools via LSP

## Related Directories

- **[../Research/](../Research/)** - Task orchestration with ATLAS and research-swarm
- **[../MCP/](../MCP/)** - Tool execution via AIRIS MCP Gateway

Together, these form the foundation of autonomous coding: **Research** determines *what* to do, **Analysis** understands *how* code works, and **MCP** executes *actions* to improve it.

