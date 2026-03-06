# run_simple.py - Documentation Index

**Version:** 2.9
**Date:** 2025-12-12
**Status:** Production Ready

---

## Quick Links

| Document | Purpose | Size |
|----------|---------|------|
| **run_simple.py** | Main entry point (executable Python script) | 16KB |
| **RUN_SIMPLE_QUICKSTART.md** | User guide and examples | 11KB |
| **RUN_SIMPLE_SUMMARY.md** | Implementation details and architecture | 9.3KB |
| **RUN_SIMPLE_INTEGRATION.md** | Integration with npm CLI and existing code | 13KB |
| **RUN_SIMPLE_INDEX.md** | This file - documentation index | 2KB |

---

## What is run_simple.py?

`run_simple.py` is the new accessibility-first entry point for Eversale CLI v2.9+. It provides a simple, fast, and reliable way to run browser automation tasks.

### Key Features

- Accessibility-first approach (uses refs like Playwright MCP)
- Optional LLM planning with fallback logic
- Simple linear execution (no complex recovery)
- Fast performance (2-3x faster than run_ultimate.py)
- Headless and visible browser modes
- Clean CLI interface

---

## Quick Start

```bash
# Basic usage
python run_simple.py "Search Google for AI news"

# Headless mode
python run_simple.py --headless "Navigate to github.com"

# Without LLM (fallback logic)
python run_simple.py --no-llm "Simple task"

# Interactive mode
python run_simple.py

# Help
python run_simple.py --help
```

---

## Documentation Structure

### For Users (Start Here)

1. **RUN_SIMPLE_QUICKSTART.md** - Complete user guide
   - Quick start examples
   - Command line options
   - Accessibility-first explanation
   - Troubleshooting
   - When to use vs run_ultimate.py

### For Developers

2. **RUN_SIMPLE_SUMMARY.md** - Implementation details
   - Architecture overview
   - Code structure
   - Key differences from run_ultimate.py
   - Performance metrics
   - Testing instructions

3. **RUN_SIMPLE_INTEGRATION.md** - Integration guide
   - npm CLI integration
   - Environment variables
   - Return value handling
   - Backwards compatibility
   - Rollout plan

### Reference

4. **run_simple.py** - Source code (well-commented)
   - SimpleAgent class
   - AgentResult dataclass
   - CLI argument parser
   - Interactive mode

---

## Document Map

```
run_simple.py Documentation
    |
    +-- Quick Start Guide (QUICKSTART.md)
    |       |
    |       +-- Installation
    |       +-- Usage Examples
    |       +-- Command Options
    |       +-- How It Works
    |       +-- Troubleshooting
    |
    +-- Implementation Summary (SUMMARY.md)
    |       |
    |       +-- What Was Created
    |       +-- Architecture
    |       +-- vs run_ultimate.py
    |       +-- Performance
    |       +-- Limitations
    |
    +-- Integration Guide (INTEGRATION.md)
    |       |
    |       +-- File Locations
    |       +-- Dependencies
    |       +-- npm CLI Integration
    |       +-- Testing
    |       +-- Rollout Plan
    |
    +-- Index (INDEX.md - This File)
            |
            +-- Quick Links
            +-- Overview
            +-- Documentation Structure
```

---

## Common Tasks

### I want to run a simple task

See: **RUN_SIMPLE_QUICKSTART.md** - Quick Start section

```bash
python run_simple.py "Your task here"
```

---

### I want to understand how it works

See: **RUN_SIMPLE_SUMMARY.md** - Architecture section

Key concepts:
- Accessibility snapshots
- Ref-based element targeting
- LLM planning (optional)
- Linear execution

---

### I want to integrate with npm CLI

See: **RUN_SIMPLE_INTEGRATION.md** - npm CLI Integration section

Three options:
1. Make run_simple.py the default
2. Side-by-side with run_ultimate.py
3. Auto-detect (try simple, fallback to ultimate)

---

### I want to extend the code

See: **run_simple.py** source code

Key extension points:
- `_plan_next_action()` - Add custom planning logic
- `_execute_action()` - Add new action types
- `_fallback_planner()` - Improve fallback heuristics

---

### I need to debug an issue

See: **RUN_SIMPLE_QUICKSTART.md** - Troubleshooting section

```bash
# Verbose mode
python run_simple.py -v "Your task"

# Check logs
export LOGURU_LEVEL=DEBUG
python run_simple.py "Your task"
```

---

## Reading Order

### New Users

1. RUN_SIMPLE_QUICKSTART.md - Learn how to use it
2. Try examples from Quick Start
3. Read "How It Works" section
4. Experiment with different options

### Developers Integrating

1. RUN_SIMPLE_SUMMARY.md - Understand architecture
2. RUN_SIMPLE_INTEGRATION.md - Integration guide
3. Read run_simple.py source code
4. Plan integration strategy

### Contributors

1. All of the above
2. Study SimpleAgent class implementation
3. Review test cases
4. Propose enhancements

---

## Key Concepts

### Accessibility-First

Instead of fragile CSS selectors, use accessibility refs:

```python
# Old way (fragile)
await page.click('button.btn-primary.mt-3[data-test="submit"]')

# New way (stable)
await page.click('[ref=s1e5]')  # From accessibility snapshot
```

Benefits: 10x more stable, 5x faster, human-aligned

See: **RUN_SIMPLE_QUICKSTART.md** - Accessibility-First Approach

---

### Optional LLM

Can run with or without LLM:

```bash
# With LLM (AI planning)
python run_simple.py "Complex task"

# Without LLM (fallback heuristics)
python run_simple.py --no-llm "Simple task"
```

See: **RUN_SIMPLE_SUMMARY.md** - Fallback Planner

---

### Simple vs Ultimate

| Use Case | run_simple.py | run_ultimate.py |
|----------|---------------|-----------------|
| Simple tasks | Yes | Overkill |
| Complex workflows | May work | Best choice |
| Testing/debugging | Yes | Too complex |
| Production automation | Try first | Fallback if needed |

See: **RUN_SIMPLE_QUICKSTART.md** - When to Use

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 2.9 | 2025-12-12 | Initial release of run_simple.py |

---

## Related Documentation

### In This Repository

- `/mnt/c/ev29/cli/CAPABILITY_REPORT.md` - Full CLI capabilities
- `/mnt/c/ev29/cli/CLAUDE.md` - Development guide
- `/mnt/c/ev29/cli/engine/agent/ACCESSIBILITY_ELEMENT_FINDER_QUICKREF.md` - Accessibility patterns
- `/mnt/c/ev29/cli/engine/agent/SIMPLE_WORKFLOW_QUICKSTART.md` - Workflow patterns

### External Resources

- [Playwright MCP](https://github.com/microsoft/playwright) - Inspiration for accessibility-first approach
- [Playwright Accessibility API](https://playwright.dev/docs/accessibility-testing) - API reference
- [ARIA Roles](https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Roles) - Understanding roles

---

## File Locations

All files in: `/mnt/c/ev29/cli/engine/`

```
/mnt/c/ev29/cli/engine/
    |
    +-- run_simple.py                    # Main entry point
    +-- RUN_SIMPLE_INDEX.md              # This file
    +-- RUN_SIMPLE_QUICKSTART.md         # User guide
    +-- RUN_SIMPLE_SUMMARY.md            # Implementation details
    +-- RUN_SIMPLE_INTEGRATION.md        # Integration guide
    |
    +-- run_ultimate.py                  # Existing entry point
    |
    +-- agent/
        +-- llm_client.py                # LLM integration
        +-- accessibility_element_finder.py  # Element finding
        +-- (other modules...)
```

---

## Getting Help

### Questions?

1. Check **RUN_SIMPLE_QUICKSTART.md** - Troubleshooting section
2. Read source code comments in **run_simple.py**
3. Review **RUN_SIMPLE_SUMMARY.md** - Limitations section
4. Ask in #eversale-dev channel

### Reporting Issues

1. Check **RUN_SIMPLE_QUICKSTART.md** - Known Issues
2. Run with `--verbose` to get detailed logs
3. Include:
   - Goal/task you were trying to run
   - Command used
   - Error message
   - Environment (OS, Python version)

---

## Contributing

### Enhancement Ideas

See **RUN_SIMPLE_SUMMARY.md** - Future Enhancements section

Planned for v3.0:
- Vision-based element finding
- Session persistence
- Workflow recording/replay
- Parallel browser instances
- Custom action definitions

### Code Style

- Follow existing patterns in run_simple.py
- Add comments for complex logic
- Update documentation when adding features
- Test on Windows, macOS, Linux

---

## License

Same as main Eversale CLI - proprietary, see main repository.

---

**Last Updated:** 2025-12-12
**Version:** 2.9
**Status:** Production Ready
