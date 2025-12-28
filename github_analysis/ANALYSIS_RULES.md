# GitHub Repository Analysis Rules & Instructions

## Overview
This document provides comprehensive instructions for analyzing GitHub repositories using automated tools and AI agents. The goal is to create detailed, evidence-based analysis reports for project indexing, understanding architecture, and assessing CI/CD suitability.

---

## Analysis Configuration

### Target Repository Information
- **Analyzer Repo**: `Zeeeepa/analyzer`
- **Target Branch**: `analysis`
- **Reports Location**: `repos/` directory
- **Report Format**: Markdown (`.md`)

### Data Sources
1. **GIT.json**: Located at root of `Zeeeepa/analyzer` repository
   - Contains repository names and descriptions
   - Generated metadata about all repositories
   - Use as the source of truth for repository list

2. **Repository Codebase**: Clone and analyze target repositories
   - Full source code access
   - Configuration files
   - Documentation

---

## Using Repomix for Code Analysis

### What is Repomix?
Repomix is a powerful tool that packs your entire repository into a single AI-friendly file, making it easy to feed your codebase to Large Language Models (LLMs) for analysis.

### Installation & Basic Usage

```bash
# Install repomix (npm required)
npm install -g repomix

# Basic usage - pack entire repository
cd /path/to/repository
repomix

# Generate specific output file
repomix -o output.txt

# With custom configuration
repomix --config repomix.config.json
```

### Repomix Configuration for Analysis

Create a `repomix.config.json` for standardized analysis:

```json
{
  "output": {
    "filePath": "repomix-output.txt",
    "style": "markdown",
    "removeComments": false,
    "showLineNumbers": true,
    "topFilesLength": 10
  },
  "include": ["**/*"],
  "ignore": {
    "useGitignore": true,
    "useDefaultPatterns": true,
    "customPatterns": [
      "node_modules/**",
      "**/*.log",
      "dist/**",
      "build/**",
      ".git/**",
      "**/*.min.js",
      "**/*.bundle.js",
      "coverage/**",
      "**/*.test.js",
      "**/*.spec.js"
    ]
  },
  "security": {
    "enableSecurityCheck": true
  }
}
```

### Effective Repomix Usage Patterns

#### 1. Full Repository Analysis
```bash
# Generate comprehensive repository snapshot
repomix --style markdown --output analysis/full-repo.txt

# Include file statistics
repomix --style markdown --includeEmptyDirectories
```

#### 2. Targeted Analysis (Specific Directories)
```bash
# Analyze only source code
repomix --include "src/**" --output analysis/src-only.txt

# Focus on configuration files
repomix --include "*.json,*.yaml,*.yml,*.toml" --output analysis/configs.txt

# CI/CD pipeline analysis
repomix --include ".github/**,.gitlab-ci.yml,Jenkinsfile" --output analysis/cicd.txt
```

#### 3. Architecture Discovery
```bash
# Entry points and main files
repomix --include "main.*,index.*,app.*,server.*" --output analysis/entrypoints.txt

# API definitions
repomix --include "**/api/**,**/routes/**,**/controllers/**" --output analysis/api.txt

# Database schemas
repomix --include "**/models/**,**/schemas/**,**/migrations/**" --output analysis/data.txt
```

#### 4. Documentation Extraction
```bash
# All documentation files
repomix --include "**/*.md,**/docs/**,README*" --output analysis/docs.txt
```

---

## Comprehensive Analysis Framework

### 1. Repository Overview Analysis

**Objective**: Understand the project's purpose, scope, and structure

**Key Areas to Analyze**:
- **Project Description**: What problem does it solve?
- **Primary Language(s)**: Programming languages used
- **Framework/Technology Stack**: Key technologies and dependencies
- **Repository Structure**: Directory organization and architecture patterns
- **License**: Open source license type
- **Community Metrics**: Stars, forks, contributors, activity level

**Analysis Steps**:
1. Read `README.md` and other documentation
2. Parse `package.json`, `requirements.txt`, `go.mod`, `Cargo.toml`, etc.
3. Analyze directory structure patterns
4. Extract metadata from GIT.json

**Output Section**: `## Repository Overview`

---

### 2. Architecture & Design Patterns

**Objective**: Map the architectural design and identify patterns

**Key Areas to Analyze**:
- **Architecture Pattern**: Monolithic, Microservices, Serverless, etc.
- **Design Patterns**: MVC, MVVM, Repository, Factory, Singleton, etc.
- **Module Organization**: How code is organized and separated
- **Data Flow**: How data moves through the application
- **State Management**: How application state is handled

**Analysis Steps**:
1. Use repomix to extract source code structure
2. Identify entry points (`main.*`, `index.*`, `app.*`)
3. Map import/dependency graphs
4. Identify architectural layers (presentation, business logic, data access)
5. Document design patterns observed in code

**Repomix Command**:
```bash
repomix --include "src/**,lib/**,app/**" --style markdown --output architecture.txt
```

**Output Section**: `## Architecture & Design Patterns`

---

### 3. Core Features & Functionalities

**Objective**: Document what the application actually does

**Key Areas to Analyze**:
- **Primary Features**: Main capabilities of the application
- **API Endpoints**: REST, GraphQL, gRPC endpoints (if applicable)
- **User Interfaces**: Web UI, CLI, Desktop, Mobile
- **Integrations**: External services and APIs used
- **Authentication/Authorization**: Security mechanisms

**Analysis Steps**:
1. Extract API definitions and route configurations
2. Identify UI components and pages
3. Document external API calls and integrations
4. Map authentication flows

**Repomix Commands**:
```bash
# API analysis
repomix --include "**/api/**,**/routes/**,**/controllers/**,**/endpoints/**" --output features-api.txt

# UI analysis
repomix --include "**/components/**,**/pages/**,**/views/**" --output features-ui.txt
```

**Output Section**: `## Core Features & Functionalities`

---

### 4. Entry Points Analysis

**Objective**: Identify how the application is started and initialized

**Key Areas to Analyze**:
- **Main Entry Point**: Primary file that starts the application
- **Initialization Sequence**: Order of component initialization
- **Configuration Loading**: How environment and config are loaded
- **Dependency Injection**: How dependencies are wired together
- **Bootstrap Process**: Application startup sequence

**Analysis Steps**:
1. Locate main entry files (`main.py`, `index.js`, `main.go`, `Program.cs`, etc.)
2. Trace initialization code
3. Document configuration files loaded
4. Map dependency setup

**Repomix Command**:
```bash
repomix --include "main.*,index.*,app.*,server.*,__init__.py,bootstrap.*" --output entrypoints.txt
```

**Output Section**: `## Entry Points & Initialization`

---

### 5. Data Flow Analysis

**Objective**: Understand how data moves through the system

**Key Areas to Analyze**:
- **Data Sources**: Databases, APIs, file systems, message queues
- **Data Transformations**: How data is processed and transformed
- **Data Persistence**: How and where data is stored
- **Caching Strategies**: Redis, in-memory, CDN caching
- **Data Validation**: Input validation and sanitization

**Analysis Steps**:
1. Identify database connections and ORM usage
2. Map data models and schemas
3. Trace data flow from input to storage
4. Document API data contracts

**Repomix Commands**:
```bash
# Database and models
repomix --include "**/models/**,**/schemas/**,**/entities/**,**/db/**" --output dataflow-models.txt

# Data access layer
repomix --include "**/repositories/**,**/dao/**,**/services/**" --output dataflow-access.txt
```

**Output Section**: `## Data Flow Architecture`

---

### 6. CI/CD Pipeline Analysis

**Objective**: Assess automated testing, building, and deployment capabilities

**Key Areas to Analyze**:
- **CI/CD Platform**: GitHub Actions, GitLab CI, Jenkins, CircleCI, etc.
- **Pipeline Stages**: Build, test, deploy stages
- **Test Coverage**: Unit tests, integration tests, e2e tests
- **Deployment Targets**: Production, staging, preview environments
- **Automation Level**: Fully automated vs manual steps
- **Security Scans**: SAST, DAST, dependency scanning
- **Containerization**: Docker, Kubernetes usage

**Analysis Steps**:
1. Locate CI/CD configuration files
2. Parse pipeline definitions
3. Identify test frameworks and coverage tools
4. Document deployment strategies
5. Check for security scanning integration

**Repomix Command**:
```bash
repomix --include ".github/workflows/**,.gitlab-ci.yml,Jenkinsfile,.circleci/**,azure-pipelines.yml,bitbucket-pipelines.yml" --output cicd.txt
```

**CI/CD Suitability Assessment Criteria**:

| Criterion | Good | Needs Improvement | Poor |
|-----------|------|-------------------|------|
| **Automated Testing** | >80% coverage | 50-80% coverage | <50% coverage |
| **Build Automation** | Fully automated | Semi-automated | Manual |
| **Deployment** | CD enabled | CI only | No automation |
| **Environment Management** | Multi-env with IaC | Basic env config | No env separation |
| **Security Scanning** | Integrated in pipeline | Manual scans | None |

**Output Section**: `## CI/CD Pipeline Assessment`

---

### 7. Dependencies & Technology Stack

**Objective**: Map all dependencies and assess technology choices

**Key Areas to Analyze**:
- **Direct Dependencies**: Packages explicitly required
- **Transitive Dependencies**: Indirect dependencies
- **Development Dependencies**: Tools for development only
- **Outdated Packages**: Security vulnerabilities and updates needed
- **License Compatibility**: Dependency license analysis

**Analysis Steps**:
1. Parse dependency manifests (`package.json`, `requirements.txt`, etc.)
2. Run dependency audit tools
3. Check for security vulnerabilities
4. Document major frameworks and libraries

**Repomix Command**:
```bash
repomix --include "package.json,requirements.txt,Gemfile,Cargo.toml,go.mod,pom.xml,build.gradle,composer.json" --output dependencies.txt
```

**Output Section**: `## Dependencies & Technology Stack`

---

### 8. Security Analysis

**Objective**: Identify security considerations and vulnerabilities

**Key Areas to Analyze**:
- **Authentication Mechanisms**: JWT, OAuth, Session-based
- **Authorization Patterns**: RBAC, ABAC, ACL
- **Input Validation**: SQL injection, XSS prevention
- **Secrets Management**: How API keys and credentials are handled
- **Security Headers**: CORS, CSP, HSTS
- **Known Vulnerabilities**: CVEs in dependencies

**Analysis Steps**:
1. Scan for hardcoded secrets
2. Review authentication/authorization code
3. Check for security best practices
4. Run vulnerability scanners on dependencies

**Output Section**: `## Security Assessment`

---

### 9. Performance Characteristics

**Objective**: Assess performance and scalability

**Key Areas to Analyze**:
- **Caching Strategies**: Redis, CDN, in-memory caching
- **Database Optimization**: Indexing, query optimization
- **Async/Concurrency**: Async operations, worker threads
- **Resource Management**: Memory, CPU, connection pooling
- **Scalability Patterns**: Horizontal vs vertical scaling

**Analysis Steps**:
1. Identify caching implementations
2. Review database query patterns
3. Check for async/await or concurrent processing
4. Document scalability considerations

**Output Section**: `## Performance & Scalability`

---

### 10. Documentation Quality

**Objective**: Evaluate documentation completeness

**Key Areas to Analyze**:
- **README Quality**: Completeness, clarity, examples
- **API Documentation**: Swagger/OpenAPI, JSDoc, etc.
- **Code Comments**: Inline documentation quality
- **Architecture Diagrams**: Visual documentation
- **Setup Instructions**: Getting started guide
- **Contribution Guidelines**: CONTRIBUTING.md

**Analysis Steps**:
1. Review all `.md` files
2. Check for API documentation
3. Assess inline code comments
4. Verify setup instructions

**Repomix Command**:
```bash
repomix --include "**/*.md,**/docs/**,README*,CONTRIBUTING*,CHANGELOG*" --output documentation.txt
```

**Output Section**: `## Documentation Quality`

---

## Report Generation Guidelines

### Report Structure Template

```markdown
# Repository Analysis: {REPO_NAME}

**Analysis Date**: {DATE}
**Repository**: {OWNER}/{REPO_NAME}
**Description**: {DESCRIPTION}

---

## Executive Summary
[Brief 2-3 paragraph overview of the repository]

## Repository Overview
- **Primary Language**: {LANGUAGE}
- **Framework**: {FRAMEWORK}
- **License**: {LICENSE}
- **Stars**: {STARS}
- **Last Updated**: {DATE}

## Architecture & Design Patterns
[Architectural analysis]

## Core Features & Functionalities
[Feature documentation]

## Entry Points & Initialization
[Entry point analysis]

## Data Flow Architecture
[Data flow documentation]

## CI/CD Pipeline Assessment
**Suitability Score**: {SCORE}/10
[Detailed CI/CD analysis]

## Dependencies & Technology Stack
[Dependency analysis]

## Security Assessment
[Security findings]

## Performance & Scalability
[Performance characteristics]

## Documentation Quality
[Documentation assessment]

## Recommendations
1. [Recommendation 1]
2. [Recommendation 2]
3. [Recommendation 3]

## Conclusion
[Final assessment]

---

**Generated by**: Codegen Analysis Agent
**Analysis Tool Version**: 1.0
```

### Report Naming Convention
- Format: `{repo-name}-analysis.md`
- Location: `analyzer/repos/{repo-name}-analysis.md`
- Branch: `analysis`

### Evidence-Based Analysis Requirements
1. **Quote Code Snippets**: Include relevant code examples
2. **Reference Files**: Link to specific files analyzed
3. **Use Metrics**: Provide quantitative data where possible
4. **Document Assumptions**: Clearly state any assumptions made
5. **Cite Sources**: Reference configuration files, documentation

---

## Automation Workflow

### Step-by-Step Process

1. **Load Repository List**
   - Read `GIT.json` from root of analyzer repository
   - Extract repository names and descriptions

2. **For Each Repository**:
   
   a. **Clone Repository**
   ```bash
   git clone https://github.com/{OWNER}/{REPO_NAME}.git /tmp/{REPO_NAME}
   cd /tmp/{REPO_NAME}
   ```
   
   b. **Run Repomix Analysis**
   ```bash
   # Full repo analysis
   repomix --style markdown --output /tmp/analysis/{REPO_NAME}-full.txt
   
   # Architecture analysis
   repomix --include "src/**,lib/**,app/**" --output /tmp/analysis/{REPO_NAME}-arch.txt
   
   # CI/CD analysis
   repomix --include ".github/**,.gitlab-ci.yml" --output /tmp/analysis/{REPO_NAME}-cicd.txt
   
   # Dependencies analysis
   repomix --include "package.json,requirements.txt,go.mod" --output /tmp/analysis/{REPO_NAME}-deps.txt
   ```
   
   c. **Analyze with AI Agent**
   - Load repomix outputs
   - Follow analysis framework (sections 1-10)
   - Generate comprehensive markdown report
   
   d. **Save Report**
   ```bash
   # Checkout analysis branch
   cd /path/to/analyzer
   git checkout analysis
   
   # Save report
   cp /tmp/analysis/{REPO_NAME}-analysis.md repos/{REPO_NAME}-analysis.md
   
   # Commit and push
   git add repos/{REPO_NAME}-analysis.md
   git commit -m "Add analysis report for {REPO_NAME}"
   git push origin analysis
   ```

3. **Verify All Reports Created**
   - Check that each repository has a corresponding report
   - Validate report completeness
   - Generate summary index

---

## Quality Assurance Checklist

Before finalizing each report, verify:

- [ ] All 10 analysis sections are present
- [ ] Code snippets are included as evidence
- [ ] CI/CD suitability is clearly assessed
- [ ] Dependencies are documented
- [ ] Security considerations are addressed
- [ ] Performance characteristics are noted
- [ ] Recommendations are actionable
- [ ] Report is saved to correct location
- [ ] Report follows naming convention
- [ ] Markdown formatting is correct

---

## Common Pitfalls to Avoid

1. **Don't Guess**: If information is not available, state "Not Found" rather than making assumptions
2. **Don't Over-Generalize**: Be specific about findings
3. **Don't Skip Evidence**: Always include code snippets or config examples
4. **Don't Ignore Errors**: Document any analysis limitations or errors encountered
5. **Don't Miss Repomix Flags**: Use appropriate include/exclude patterns for accurate analysis

---

## Advanced Repomix Techniques

### Custom Output Styles
```bash
# XML format (useful for parsing)
repomix --style xml --output analysis.xml

# Plain text (simplest format)
repomix --style plain --output analysis.txt

# Markdown with metadata (recommended)
repomix --style markdown --output analysis.md
```

### Security-Conscious Analysis
```bash
# Enable security checks
repomix --config security.config.json

# Security config example:
{
  "security": {
    "enableSecurityCheck": true
  },
  "ignore": {
    "customPatterns": [
      "**/*.key",
      "**/*.pem",
      "**/.env",
      "**/secrets/**"
    ]
  }
}
```

### Performance Optimization
```bash
# Large repositories: exclude non-essential files
repomix --include "src/**,lib/**" --ignore "node_modules/**,dist/**,build/**"

# Fast analysis: skip binary files
repomix --ignore "**/*.png,**/*.jpg,**/*.pdf,**/*.zip"
```

---

## Integration with Codegen Analysis Script

The `codegen_analysis.py` script should:

1. Load `GIT.json` from repository root
2. Parse repository names and descriptions
3. For each repository:
   - Create Codegen agent run
   - Pass repository metadata
   - Instruct agent to follow ANALYSIS_RULES.md
   - Wait for completion
4. Verify all reports are created
5. Generate summary report

---

## Troubleshooting

### Repomix Not Found
```bash
# Install repomix globally
npm install -g repomix

# Verify installation
repomix --version
```

### Large Repository Timeouts
- Use targeted include patterns
- Exclude build artifacts and dependencies
- Process in chunks (by directory)

### Missing Dependencies
- Ensure Node.js and npm are installed
- Check file permissions
- Verify repository access credentials

---

## Summary

This comprehensive guide provides everything needed to:
1. ✅ Use repomix effectively for code extraction
2. ✅ Analyze repositories across 10 key dimensions
3. ✅ Generate evidence-based, professional reports
4. ✅ Assess CI/CD suitability accurately
5. ✅ Automate the entire analysis workflow

Follow these rules systematically to produce high-quality, actionable repository analysis reports.
