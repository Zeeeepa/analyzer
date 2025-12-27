# NPM Package Analysis

This folder contains tools and results for automated NPM package analysis using Codegen agents.

## Structure

```
npm_analysis/
├── ANALYSIS_RULES.md        # Comprehensive analysis framework and guidelines
├── npm_analyzer.py          # Main script to trigger analysis runs  
├── packages/                # Analysis reports for each package
│   └── <package-name>_analysis.md
└── README.md               # This file
```

## Overview

The NPM analyzer creates individual Codegen agent runs for each package listed in `NPM.json` at the repository root. Each agent:

1. **Downloads** the package from NPM registry
2. **Extracts** the compressed tarball
3. **Runs repomix** to analyze structure and code
4. **Follows** comprehensive analysis framework from ANALYSIS_RULES.md
5. **Creates** a detailed markdown report with 10 analysis sections
6. **Saves** the report to `packages/<package-name>_analysis.md`

## Key Features

- ✅ **Comprehensive Analysis**: 10-section framework covering all aspects
- ✅ **Evidence-Based**: Code snippets, metrics, and concrete examples
- ✅ **Security Conscious**: API tokens via environment variables
- ✅ **Repomix Integration**: Advanced code analysis with multiple passes
- ✅ **Flexible Configuration**: Support for descriptions in NPM.json
- ✅ **Progress Tracking**: Real-time console updates and JSON results
- ✅ **Error Handling**: Graceful failure tracking and retry support

## Usage

### Prerequisites

```bash
# Install dependencies
pip install codegen

# Install repomix globally (optional but recommended)
npm install -g repomix

# Set environment variables (REQUIRED for security)
export CODEGEN_API_TOKEN='your-api-token'
export CODEGEN_ORG_ID='your-org-id'  # Optional, defaults to your org
```

### Run Analysis

```bash
cd npm_analysis

# Full analysis of all packages
python npm_analyzer.py

# Dry run (test without creating runs)
python npm_analyzer.py --dry-run

# Limit to first N packages (testing)
python npm_analyzer.py --limit=5

# With verification (wait and verify reports)
python npm_analyzer.py --verify
```

### Configuration

Set these environment variables (REQUIRED):

```bash
export CODEGEN_API_TOKEN='sk-your-token-here'
export CODEGEN_ORG_ID='323'  # Your organization ID (optional)
```

**Security Note**: API token is NO LONGER hardcoded in the script. You MUST set the environment variable or the script will exit with an error.

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
- Each agent commits to the **`analysis`** branch (CRITICAL!)
- Reports appear in `packages/` as agents complete
- Verify reports with: `git fetch origin analysis && git checkout analysis`

## Statistics

- **Total Packages**: 861 (from NPM.json)
- **Estimated Time**: ~43 minutes (at 3s/package)
- **Reports Location**: `npm_analysis/packages/`
- **Target Branch**: **`analysis`** (NOT npm_analysis, NOT main!)
- **Repository**: `Zeeeepa/analyzer`

## Notes

- This analyzes NPM packages, not GitHub repositories
- Focuses on published package structure
- Uses repomix for code analysis
- Each agent runs independently
- Results are committed to a separate branch
