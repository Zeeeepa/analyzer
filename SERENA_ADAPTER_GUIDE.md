# SerenaAdapter Complete Guide

## Table of Contents
1. [Overview](#overview)
2. [Installation](#installation)
3. [Quick Start](#quick-start)
4. [Core Features](#core-features)
5. [API Reference](#api-reference)
6. [Runtime Error Monitoring](#runtime-error-monitoring)
7. [Performance](#performance)
8. [Integration Examples](#integration-examples)
9. [Troubleshooting](#troubleshooting)

---

## Overview

**SerenaAdapter** is a production-ready facade over the Serena library, providing:

- ✅ **All 20+ Serena tools** via clean, simple API
- ✅ **Runtime error monitoring** (Python, JavaScript, React)
- ✅ **Error history and analytics** (frequency, patterns, trends)
- ✅ **Symbol-aware operations** (find, references, definitions)
- ✅ **File operations** (read, search, create, edit)
- ✅ **Memory management** (persistent key-value storage)
- ✅ **Workflow execution** (safe command execution)
- ✅ **Performance instrumentation** (< 5ms overhead per call)

### Architecture

SerenaAdapter uses a **Facade + Delegation + Monitoring** pattern:

```
┌────────────────────────────────────────────┐
│         SerenaAdapter (Your API)           │
│  ┌──────────────────────────────────────┐  │
│  │   Tool.apply_ex() Delegation         │  │
│  │   (Preserves Serena architecture)    │  │
│  └──────────────────────────────────────┘  │
│  ┌──────────────────────────────────────┐  │
│  │   RuntimeErrorCollector              │  │
│  │   (Production monitoring)            │  │
│  └──────────────────────────────────────┘  │
│  ┌──────────────────────────────────────┐  │
│  │   Error Analytics                    │  │
│  │   (History, frequency, stats)        │  │
│  └──────────────────────────────────────┘  │
└────────────────────────────────────────────┘
```

---

## Installation

### Prerequisites

```bash
# Python 3.8+ required
python --version
```

### Install from Repository

```bash
# Clone repository
git clone https://github.com/Zeeeepa/analyzer.git
cd analyzer

# Install in development mode
pip install -e .
```

This installs:
- `serena` - Core LSP and agent functionality
- `autogenlib` - AI-powered code analysis
- `graph-sitter` - Parser and AST analysis
- All dependencies (50+ packages)

### Verify Installation

```python
from Libraries.serena_adapter import SerenaAdapter

adapter = SerenaAdapter("/path/to/project")
print("✅ SerenaAdapter ready!")
```

---

## Quick Start

### Basic Usage

```python
from Libraries.serena_adapter import SerenaAdapter

# Initialize adapter
adapter = SerenaAdapter(
    project_root="/path/to/your/project",
    enable_error_collection=True  # Enable runtime monitoring
)

# Find symbols
symbols = adapter.find_symbol("MyClass")
for symbol in symbols:
    print(f"Found: {symbol['name']} at {symbol['file']}:{symbol['line']}")

# Read files
content = adapter.read_file("src/main.py")
print(content)

# Search across files
results = adapter.search_files(
    query="TODO",
    patterns=["*.py", "*.js"],
    case_sensitive=False
)

# Get error statistics
stats = adapter.get_error_statistics()
print(f"Total errors: {stats['total_errors']}")
print(f"Resolution rate: {stats['resolution_rate']}")
```

---

## Core Features

### 1. Symbol Operations

#### Find Symbol by Name

```python
# Find all occurrences of a symbol
symbols = adapter.find_symbol(
    name="calculate_total",
    kind=None,  # Optional: filter by SymbolKind
    file_path=None,  # Optional: search within specific file
    case_sensitive=True
)

for symbol in symbols:
    print(f"{symbol['name']}: {symbol['file']}:{symbol['line']}")
```

#### Get Symbol References

```python
# Find all references to symbol at position
references = adapter.get_symbol_references(
    file_path="src/main.py",
    line=42,  # 0-indexed
    column=10  # 0-indexed
)

print(f"Found {len(references)} references")
```

#### Get Symbol Definition

```python
# Jump to definition
definition = adapter.get_symbol_definition(
    file_path="src/utils.py",
    line=25,
    column=15
)

if definition:
    print(f"Defined at: {definition['file']}:{definition['line']}")
```

#### File Symbols Overview

```python
# Get all symbols in a file
overview = adapter.get_file_symbols_overview("src/service.py")

print(f"Functions: {len(overview['functions'])}")
print(f"Classes: {len(overview['classes'])}")
print(f"Variables: {len(overview['variables'])}")
```

### 2. File Operations

#### Read Files

```python
# Read entire file
content = adapter.read_file("src/main.py")

# Read specific line range
content = adapter.read_file(
    file_path="src/main.py",
    start_line=10,  # 1-indexed
    end_line=20     # 1-indexed
)
```

#### Search Files

```python
# Text search
results = adapter.search_files(
    query="import logging",
    patterns=["*.py"],  # Glob patterns
    regex=False,
    case_sensitive=False
)

# Regex search
results = adapter.search_files(
    query=r"def\s+\w+\(.*\):",
    regex=True
)

for match in results:
    print(f"{match['file']}:{match['line']}: {match['context']}")
```

#### List Directory

```python
# List files
files = adapter.list_directory(
    directory_path="src",
    recursive=True,
    include_gitignore=True  # Respect .gitignore
)

print(f"Found {len(files)} files")
```

#### Create Files

```python
# Create new file
success = adapter.create_file(
    file_path="src/new_module.py",
    content="""
def hello():
    print("Hello, World!")
""",
    overwrite=False  # Don't overwrite if exists
)
```

#### Edit Files

```python
# Replace text in file
replacements = adapter.replace_in_files(
    file_path="src/config.py",
    old_text="DEBUG = False",
    new_text="DEBUG = True",
    count=1  # Replace first occurrence only
)

print(f"Made {replacements} replacements")
```

### 3. Memory Operations

Persistent key-value storage for agent memory:

```python
# Save memory
adapter.save_memory("context", "Important information about the codebase...")
adapter.save_memory("last_action", "Fixed login bug in auth.py")

# Load memory
context = adapter.load_memory("context")
print(context)

# List all memories
keys = adapter.list_memories()
print(f"Stored memories: {keys}")

# Delete memory
adapter.delete_memory("old_context")
```

### 4. Workflow Tools

#### Execute Commands Safely

```python
# Run shell command
result = adapter.run_command(
    command="pytest tests/",
    timeout=60,  # seconds
    capture_output=True
)

print(f"Exit code: {result['returncode']}")
print(f"Output: {result['stdout']}")

if result['stderr']:
    print(f"Errors: {result['stderr']}")
```

---

## Runtime Error Monitoring

### Enable Error Collection

```python
adapter = SerenaAdapter(
    "/project",
    enable_error_collection=True  # Enable monitoring
)

# Set codebase for enhanced context
from graph_sitter import Codebase
codebase = Codebase.from_directory("/project", extensions=[".py"])
adapter.set_codebase(codebase)
```

### Collect Python Runtime Errors

```python
# Collect from log file
diagnostics = adapter.get_diagnostics(
    runtime_log_path="/var/log/app.log",
    merge_runtime_errors=True
)

# Errors are automatically parsed and categorized
```

**Supported Python Error Formats:**
```python
# Tracebacks are automatically parsed
Traceback (most recent call last):
  File "/app/main.py", line 42, in process_data
    result = data['value']
KeyError: 'value'
```

### Collect JavaScript/React Errors

```python
# Collect UI errors
diagnostics = adapter.get_diagnostics(
    ui_log_path="/var/log/ui.log",
    merge_runtime_errors=True
)
```

**Supported JavaScript Error Formats:**
```javascript
// TypeError
TypeError: Cannot read property 'name' of undefined at App.js:25:10

// React errors
Error: Invalid hook call in UserProfile (at UserProfile.tsx:42:8)

// Console errors
console.error: Network request failed
```

### Error Analytics

```python
# Get comprehensive error statistics
stats = adapter.get_error_statistics()

print(f"Total errors: {stats['total_errors']}")
print(f"Errors by tool: {stats['errors_by_tool']}")
print(f"Resolution rate: {stats['resolution_rate']}")
print(f"Most frequent: {stats['most_frequent_errors']}")

# Recent errors
for error in stats['recent_errors']:
    print(f"{error['tool']}: {error['error']}")
```

### Clear Error History

```python
# Clear all error tracking
cleared = adapter.clear_error_history()
print(f"Cleared {cleared} errors")
```

---

## Performance

### Benchmarks

SerenaAdapter is optimized for production use:

| Operation | Average Time | Overhead |
|-----------|-------------|----------|
| `find_symbol()` | < 5ms | < 1ms |
| `read_file()` | < 5ms | < 1ms |
| `save_memory()` | < 5ms | < 1ms |
| `get_error_statistics()` | < 10ms (1000 errors) | - |
| Error tracking | - | < 1ms per call |

### Performance Stats

```python
# Get performance metrics
stats = adapter.get_performance_stats()

for tool_name, metrics in stats.items():
    print(f"{tool_name}:")
    print(f"  Calls: {metrics['count']}")
    print(f"  Avg: {metrics['avg_ms']:.2f}ms")
    print(f"  Min: {metrics['min_ms']:.2f}ms")
    print(f"  Max: {metrics['max_ms']:.2f}ms")
```

---

## Integration Examples

### With AutoGenLib (AI Fixes)

```python
from Libraries.serena_adapter import SerenaAdapter
from Libraries.autogenlib_adapter import resolve_diagnostic_with_ai

# Get diagnostics
adapter = SerenaAdapter("/project")
diagnostics = adapter.get_diagnostics()

# Resolve with AI
for diagnostic in diagnostics:
    fix = resolve_diagnostic_with_ai(diagnostic, codebase)
    if fix:
        print(f"AI suggested fix: {fix['code']}")
```

### With Graph-Sitter (AST Analysis)

```python
from Libraries.serena_adapter import SerenaAdapter
from graph_sitter import Codebase

# Initialize with codebase
codebase = Codebase.from_directory("/project", extensions=[".py"])
adapter = SerenaAdapter("/project")
adapter.set_codebase(codebase)

# Enhanced symbol search with AST context
symbols = adapter.find_symbol("MyClass")
```

### Complete Workflow

```python
# 1. Initialize
adapter = SerenaAdapter("/project", enable_error_collection=True)

# 2. Find problematic code
symbols = adapter.find_symbol("buggy_function")

# 3. Read file context
for symbol in symbols:
    content = adapter.read_file(symbol['file'])
    print(f"Found in: {symbol['file']}")

# 4. Collect runtime errors
diagnostics = adapter.get_diagnostics(
    runtime_log_path="/var/log/app.log"
)

# 5. Analyze error patterns
stats = adapter.get_error_statistics()
print(f"Resolution rate: {stats['resolution_rate']}")

# 6. Save context for later
adapter.save_memory("analysis", "Found 3 issues in authentication module")
```

---

## Troubleshooting

### Common Issues

#### Import Errors

```python
# Error: Cannot import SerenaAdapter
# Solution: Ensure proper installation
pip install -e .

# Verify installation
python -c "from Libraries.serena_adapter import SerenaAdapter; print('✅ OK')"
```

#### Serena Not Available

```python
# Error: Serena library not available
# Solution: Check serena installation
pip install git+https://github.com/Zeeeepa/serena.git

# Or reinstall dependencies
pip install -e . --force-reinstall
```

#### Tool Execution Failures

```python
# Error: Tool execution failed
# Solution: Check error history
stats = adapter.get_error_statistics()
print(stats['errors_by_tool'])
print(stats['recent_errors'])

# Common causes:
# 1. Invalid file paths (use relative to project root)
# 2. Serena agent not initialized (check SerenaConfig)
# 3. Project structure issues (verify project_root)
```

#### Performance Issues

```python
# Check performance stats
perf = adapter.get_performance_stats()

# If operations are slow:
# 1. Check codebase size (large projects take longer)
# 2. Disable error collection temporarily
adapter_fast = SerenaAdapter("/project", enable_error_collection=False)

# 3. Clear error history periodically
adapter.clear_error_history()
```

### Debug Mode

```python
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# SerenaAdapter will log all operations
adapter = SerenaAdapter("/project")
```

### Getting Help

1. **Check error statistics**: `adapter.get_error_statistics()`
2. **Review recent errors**: Look at `error_history`
3. **Run tests**: `pytest tests/test_serena_adapter.py -v`
4. **Check integration**: `pytest tests/test_integration.py -v`

---

## API Reference Summary

### Initialization
- `SerenaAdapter(project_root, config=None, enable_error_collection=True)`
- `set_codebase(codebase)`

### Symbol Operations
- `find_symbol(name, kind=None, file_path=None, case_sensitive=True)`
- `get_file_symbols_overview(file_path)`
- `get_symbol_references(file_path, line, column)`
- `get_symbol_definition(file_path, line, column)`

### File Operations
- `read_file(file_path, start_line=None, end_line=None)`
- `search_files(query, patterns=None, regex=False, case_sensitive=False)`
- `list_directory(directory_path=".", recursive=False, include_gitignore=True)`
- `create_file(file_path, content, overwrite=False)`
- `replace_in_files(file_path, old_text, new_text, count=-1)`

### Memory Operations
- `save_memory(key, value)`
- `load_memory(key)`
- `list_memories()`
- `delete_memory(key)`

### Workflow Tools
- `run_command(command, timeout=30, capture_output=True)`

### Error Monitoring
- `get_diagnostics(runtime_log_path=None, ui_log_path=None, merge_runtime_errors=True)`
- `get_error_statistics()`
- `clear_error_history()`

### Performance
- `get_performance_stats()`

---

## License

This project is part of the analyzer repository. See main repository for license details.

## Contributing

Contributions welcome! Please see the main repository for contribution guidelines.

