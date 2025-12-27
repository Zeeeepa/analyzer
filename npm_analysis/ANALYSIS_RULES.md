# NPM Package Analysis Rules & Instructions

## Overview
This document provides comprehensive instructions for analyzing NPM packages using automated tools and AI agents. The goal is to create detailed, evidence-based analysis reports for package indexing, understanding architecture, assessing quality, and evaluating integration suitability.

---

## Analysis Configuration

### Target Repository Information
- **Analyzer Repo**: `Zeeeepa/analyzer`
- **Target Branch**: `npm_analysis`
- **Reports Location**: `npm_analysis/packages/` directory
- **Report Format**: Markdown (`.md`)
- **Naming Convention**: `{package-name}_analysis.md`

### Data Sources
1. **NPM.json**: Located at root of `Zeeeepa/analyzer` repository
   - Contains package names and descriptions
   - Use as the source of truth for package list
   - Package descriptions provide context for analysis

2. **NPM Registry**: https://registry.npmjs.org/
   - Download tarballs directly
   - Extract package contents
   - Analyze published package structure

3. **NPM Website**: https://www.npmjs.com/package/{package-name}
   - Package metadata
   - README and documentation
   - Download statistics
   - Dependencies information

---

## Using Repomix for Package Analysis

### What is Repomix?
Repomix is a powerful tool that packs your entire repository/package into a single AI-friendly file, making it easy to feed your codebase to Large Language Models (LLMs) for analysis.

### Installation & Basic Usage

```bash
# Install repomix (npm required)
npm install -g repomix

# Basic usage - pack entire package
cd /path/to/package
repomix

# Generate specific output file
repomix -o output.txt

# With custom configuration
repomix --config repomix.config.json
```

### Effective Repomix Usage for NPM Packages

#### 1. Full Package Analysis
```bash
# Generate comprehensive package snapshot
repomix --style markdown --output analysis/full-package.txt

# Include file statistics
repomix --style markdown --output analysis/package-stats.txt
```

#### 2. Targeted Analysis

```bash
# Analyze only source code (most important for packages)
repomix --include "src/**,lib/**,index.js,*.ts" --output analysis/src-only.txt

# Configuration files (package.json, tsconfig, etc.)
repomix --include "package.json,tsconfig.json,*.config.js,*.config.ts" --output analysis/configs.txt

# Types and interfaces
repomix --include "**/*.d.ts,**/*.ts,types/**" --output analysis/types.txt

# Documentation
repomix --include "README.md,**/*.md,docs/**" --output analysis/docs.txt
```

---

## Comprehensive NPM Package Analysis Framework

This framework provides 10 key sections for thorough package analysis:

### 1. Package Overview
- Package name, version, description
- Author/maintainer information
- License type
- NPM statistics (downloads, dependents)
- Repository and homepage links

### 2. Installation & Setup
- Installation commands
- Node.js version requirements
- Configuration steps
- Environment variables
- Quick start guide

### 3. Architecture & Code Structure
- Directory organization
- Module system (CommonJS vs ESM)
- Build system and tooling
- Design patterns
- Code organization principles

### 4. Core Features & API
- Main functionality
- Public API surface
- Usage examples
- Configuration options
- CLI commands (if applicable)

### 5. Entry Points & Exports
- package.json main/module/types fields
- Exports map
- Conditional exports
- Tree-shaking support

### 6. Dependencies & Data Flow
- Production dependencies
- Dev dependencies
- Peer dependencies
- Bundle size impact
- Dependency security

### 7. Build & CI/CD Pipeline
- Build scripts
- Test framework
- Linting and formatting
- CI/CD configuration
- Publishing workflow

### 8. Quality & Maintainability
- TypeScript support
- Test coverage
- Documentation quality
- Maintenance status
- Code complexity

### 9. Security Assessment
- Known vulnerabilities
- Security advisories
- License compliance
- Maintainer verification

### 10. Integration & Usage Guidelines
- Framework compatibility
- Platform support
- Module system compatibility
- Integration examples
- Common use cases

---

## Report Template

```markdown
# Package Analysis: {PACKAGE_NAME}

**Analysis Date**: {DATE}
**Package**: {PACKAGE_NAME}
**Version**: {VERSION}
**NPM URL**: https://www.npmjs.com/package/{PACKAGE_NAME}

---

## Executive Summary
[2-3 paragraph overview]

## Package Overview
- **Name**: {NAME}
- **Version**: {VERSION}
- **License**: {LICENSE}
- **Downloads/Week**: {DOWNLOADS}

## Installation & Setup
### Installation
\`\`\`bash
npm install {PACKAGE_NAME}
\`\`\`

## Architecture & Code Structure
[Structure details]

## Core Features & API
[Features and API documentation]

## Entry Points & Exports
[Entry point configuration]

## Dependencies & Data Flow
[Dependencies analysis]

## Build & CI/CD Pipeline  
[Build and test setup]

## Quality & Maintainability
**Quality Score**: {SCORE}/10
[Quality assessment]

## Security Assessment
[Security analysis]

## Integration & Usage Guidelines
[Integration guide]

## Recommendations
1. [Recommendation 1]
2. [Recommendation 2]
3. [Recommendation 3]

## Conclusion
[Final assessment]

---
**Generated by**: Codegen NPM Analysis Agent
```

---

## Quality Checklist

Before finalizing each report:

- [ ] All 10 sections present
- [ ] Package metadata accurate
- [ ] Code snippets included
- [ ] Installation instructions clear
- [ ] API documented
- [ ] Dependencies listed
- [ ] Security assessed
- [ ] Quality score provided
- [ ] Integration guidelines included
- [ ] Saved to correct location
- [ ] Correct naming convention
- [ ] Valid markdown formatting

---

## Common Pitfalls

1. ❌ Confusing NPM package with GitHub repo
2. ❌ Guessing package structure
3. ❌ Skipping package.json analysis
4. ❌ Ignoring build artifacts
5. ❌ Over-generalizing findings
6. ❌ Missing code examples
7. ❌ Incomplete dependency analysis
8. ❌ Ignoring security issues

---

## Summary

Follow this framework to produce:
✅ Evidence-based package analysis
✅ Comprehensive 10-section reports
✅ Actionable recommendations
✅ Quality assessments
✅ Security evaluations
✅ Integration guidelines

Use repomix for efficient code analysis and ensure all reports meet quality standards.

