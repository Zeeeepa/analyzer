# Python Files Analysis

## Overview

This directory contains a comprehensive analysis of **ALL Python files** found in the Modal sandbox environment running the Codegen agent.

## Files

### `allfiles.py`

A Python module containing:
- **Complete inventory** of 4,510 Python files
- **Utility functions** to access and analyze files
- **Categorization** by location (stdlib, site-packages, codegen, etc.)

## Statistics

```
Total Python Files: 4,510

Breakdown by Location:
├── Python 3.13 Standard Library → ~3,000 files
├── Site Packages (pip-installed) → ~800 files
├── Codegen Repository           → 167 files
├── Homebrew Python              → ~300 files
├── Node.js/npm Tools            → ~200 files
├── System Python 3.12           → ~500 files
└── Debug Tools                  → ~100 files
```

## Usage

### Load the module:

```python
from ANALYSIS_PY_FILES import allfiles

# Print summary
allfiles.print_summary()

# Get all file contents
contents = allfiles.get_file_contents()

# Search for specific files
anthropic_files = allfiles.search_files('anthropic')
print(f"Found {len(anthropic_files)} Anthropic-related files")

# Get Codegen repository files only
codegen_files = allfiles.get_codegen_files()
for filepath in codegen_files[:10]:
    print(filepath)

# Access specific file content
if allfiles.ALL_PYTHON_FILES:
    first_file = allfiles.ALL_PYTHON_FILES[0]
    content = contents[first_file]
    print(f"\nFirst file: {first_file}")
    print(f"Content length: {len(content)} characters")
```

## Categories

### 1. **Standard Library** (3,000+ files)
- Complete Python 3.13 standard library
- Modules: asyncio, typing, collections, json, http, etc.

### 2. **Site Packages** (800+ files)
Installed pip packages including:
- **AI/ML:** anthropic, openai, transformers, torch
- **Web:** requests, urllib3, fastapi, flask, starlette
- **Data:** pydantic, sqlalchemy, pandas, numpy
- **Git:** gitpython, pygithub, gitdb
- **CLI:** typer, click, rich, textual
- **Testing:** pytest, coverage

### 3. **Codegen Repository** (167 files)
The complete Codegen SDK:
- `src/codegen/agents/` - Agent implementation
- `src/codegen/cli/` - CLI tools (92 files)
- `src/codegen/git/` - Git integration (21 files)
- `src/codegen/configs/` - Configuration management
- `src/codegen/shared/` - Shared utilities
- `tests/` - Test suite

### 4. **System & Tools** (500+ files)
- Python 3.12 system installation
- GDB Python helpers
- Perf profiling scripts
- node-gyp build tools

## Environment Details

- **Platform:** Modal (serverless containers)
- **Cloud:** Oracle Cloud Infrastructure (OCI)
- **Region:** us-phoenix-1
- **Runtime:** gVisor (secure sandbox)
- **Python Version:** 3.13.0
- **Repository:** https://github.com/Zeeeepa/codegen
- **Branch:** develop

## Key Python Packages

### AI & LLM
- anthropic==0.39.0
- openai==1.56.2
- litellm
- transformers

### Web Frameworks
- fastapi==0.115.6
- flask==3.1.0
- starlette==0.41.3

### Git Tools
- GitPython==3.1.44
- PyGithub==2.6.1

### CLI & UI
- typer==0.12.5
- rich==13.7.1
- textual==0.91.0

### Data & Validation
- pydantic==2.9.2
- sqlalchemy==2.0.36

### Observability
- opentelemetry-api==1.26.0
- sentry-sdk==2.29.1

## Generated

- **Date:** 2025-10-16
- **Time:** 11:05 UTC
- **Task ID:** ta-01K7MXV0HVXWASEYNYV3SS5APB
- **Sandbox ID:** sb-DUySn1tkrGf44OeGL4GwUQ

## Notes

- All file paths are absolute within the Modal sandbox
- The `get_file_contents()` function reads files dynamically
- Some files may be read-only or require special permissions
- Total size of all Python files: ~200 MB
