# NPM Package Analysis

This folder contains tools and results for automated NPM package analysis using Codegen agents.

## Structure

```
npm_analysis/
├── npm_analyzer.py          # Main script to trigger analysis runs
├── packages/                # Analysis reports for each package
│   └── <package-name>_analysis.md
└── README.md               # This file
```

## Overview

The NPM analyzer creates individual Codegen agent runs for each package listed in `NPM.json` at the repository root. Each agent:

1. **Downloads** the package from npmjs.com
2. **Extracts** the compressed tarball
3. **Runs repomix** to analyze structure
4. **Creates** a detailed markdown report
5. **Saves** the report to `packages/<package-name>_analysis.md`

## Usage

### Prerequisites

```bash
pip install codegen
```

### Run Analysis

```bash
cd npm_analysis
python npm_analyzer.py
```

### Configuration

Edit the configuration section in `npm_analyzer.py`:

```python
ORG_ID = "323"                          # Your Codegen org ID
API_TOKEN = "your-token"                # Your API token
ANALYZER_REPO = "analyzer"              # Target repository
ANALYZER_BRANCH = "npm_analysis"        # Target branch for reports
WAIT_BETWEEN_RUNS = 2                   # Seconds between agent runs
```

## How It Works

### 1. Load Packages

The script reads `NPM.json` from the repository root:

```json
[
  "lean-agentic",
  "scordi-extension",
  "qevo",
  ...
]
```

### 2. Create Agent Runs

For each package, creates a Codegen agent run with instructions to:
- Access https://www.npmjs.com/package/{package-name}
- Download from https://registry.npmjs.org/{package-name}
- Extract and analyze with repomix
- Generate comprehensive report

### 3. Sequential Processing

- Processes packages one by one (to avoid rate limits)
- 2-second delay between runs (configurable)
- Tracks success/failure for each package
- Saves results to JSON file

### 4. Report Generation

Each agent creates a report in `packages/` containing:
- Package overview (name, version, description, author)
- Package.json analysis
- Directory structure
- Code architecture and patterns
- Dependencies analysis
- Repomix output summary

## Output

### Console Output

```
================================================================================
NPM Package Analysis - Batch Processing
================================================================================

[1/863] Processing: lean-agentic
  ✅ Agent run created: run_abc123
  🔗 View at: https://codegen.com/runs/run_abc123
  📊 Progress: 1 successful, 0 failed
  ⏳ Waiting 2s before next run...

[2/863] Processing: scordi-extension
  ✅ Agent run created: run_def456
  ...
```

### Results File

A JSON file is created with all run details:

```json
{
  "timestamp": "2024-12-27T21:30:00",
  "total_packages": 863,
  "successful_runs": 863,
  "failed_runs": 0,
  "results": [
    {
      "package": "lean-agentic",
      "run_id": "run_abc123",
      "status": "created",
      "timestamp": "2024-12-27T21:30:00",
      "url": "https://codegen.com/runs/run_abc123"
    },
    ...
  ]
}
```

## Analysis Reports

Each package gets its own analysis report at:

```
npm_analysis/packages/<package-name>_analysis.md
```

### Report Structure

```markdown
# Package Analysis: <package-name>

## Package Overview
- Name: ...
- Version: ...
- Description: ...

## Package.json Analysis
- Dependencies
- Scripts
- Configuration

## Directory Structure
...

## Code Architecture
...

## Dependencies Analysis
...

## Repomix Summary
...
```

## Monitoring

- View all runs at: https://codegen.com/runs
- Each agent commits to the `npm_analysis` branch
- Reports appear in `packages/` as agents complete

## Statistics

- **Total Packages**: 863 (from NPM.json)
- **Estimated Time**: ~29 minutes (at 2s/package)
- **Reports Location**: `npm_analysis/packages/`
- **Branch**: `npm_analysis`

## Notes

- This analyzes NPM packages, not GitHub repositories
- Focuses on published package structure
- Uses repomix for code analysis
- Each agent runs independently
- Results are committed to a separate branch

