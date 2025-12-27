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
- **Package Maturity**: Release history, update frequency, stability indicators
- **Community Health**: GitHub stars, issues, PRs, contributors

---

### 2. Installation & Setup
- Installation commands
- Node.js version requirements
- Configuration steps
- Environment variables
- Quick start guide
- **Platform-Specific Instructions**: Windows/Linux/macOS considerations
- **Docker/Container Support**: Containerization examples if applicable

---

### 3. Architecture & Code Structure

#### 3.1 Directory Organization
- Map complete directory structure
- Identify key directories: `src/`, `lib/`, `dist/`, `test/`, `docs/`
- Document purpose of each major directory
- Identify build output vs source directories

#### 3.2 Module System
- **Type**: CommonJS, ESM, UMD, or hybrid
- **Module resolution**: How modules are resolved internally
- **Barrel exports**: Index files that re-export from multiple modules
- **Circular dependencies**: Identify and document any circular imports

#### 3.3 Design Patterns
- **Architectural patterns**: MVC, MVVM, Factory, Singleton, Observer, etc.
- **Code organization**: Layered architecture, feature-based, domain-driven
- **Separation of concerns**: How responsibilities are divided

---

### 4. Core Features & API

#### 4.1 Feature Inventory
Create a comprehensive list of ALL features with:
- Feature name and purpose
- API surface (functions/classes/methods)
- Input/output types
- Usage examples
- Edge cases and limitations

#### 4.2 API Documentation
For EACH exported function/class:
- **Signature**: Full type signature with parameters
- **Description**: What it does in detail
- **Parameters**: Type, description, required/optional, defaults
- **Return value**: Type and description
- **Throws**: Exceptions/errors that can be thrown
- **Examples**: Minimum 2-3 usage examples
- **Related APIs**: Other functions commonly used together

#### 4.3 Configuration API
- All configuration options
- Default values
- Validation rules
- Configuration file formats supported
- Runtime vs build-time configuration

---

### 5. Entry Points & Exports Analysis

#### 5.1 Package.json Entry Points
Analyze and document ALL entry points:

```json
{
  "main": "dist/index.js",        // CommonJS entry
  "module": "dist/index.mjs",     // ESM entry
  "types": "dist/index.d.ts",     // TypeScript types
  "exports": { ... }              // Modern exports map
}
```

**For EACH entry point, identify:**
- File path and existence
- Module format (CJS/ESM)
- What it exports
- Intended use case
- Browser vs Node.js compatibility

#### 5.2 Exports Map Analysis
If package uses `exports` field, analyze:

```json
{
  "exports": {
    ".": {
      "types": "./dist/index.d.ts",
      "import": "./dist/index.mjs",
      "require": "./dist/index.cjs",
      "default": "./dist/index.js"
    },
    "./utils": "./dist/utils.js",
    "./package.json": "./package.json"
  }
}
```

**Document:**
- Root export (`.`)
- Subpath exports (`./utils`, `./lib/*`)
- Conditional exports (import/require/types/default)
- Private paths (not exported)

#### 5.3 Exported Symbols Deep Dive

**Categorize ALL exports by type:**

##### Functions
- Function name
- Purpose and use case
- Full signature with types
- Side effects (if any)
- Async vs sync
- Error handling approach

##### Classes
- Class name and purpose
- Constructor parameters
- Public methods with signatures
- Static methods
- Properties (public/private)
- Inheritance hierarchy
- Implements interfaces

##### Constants/Enums
- Name and type
- All possible values
- Use cases
- Default exports

##### Types/Interfaces (TypeScript)
- Type name
- Properties and their types
- Generic parameters
- Extends/implements relationships

#### 5.4 Entry Point Execution Flow
**Trace what happens when package is imported:**

1. **Initial import**: What file is loaded first?
2. **Side effects**: Any code that runs on import?
3. **Initialization**: Setup code, global state, event listeners
4. **Dependencies loaded**: What other modules are required?
5. **Export resolution**: How are exported symbols created?

**Example:**
```javascript
// When you do: import pkg from 'package-name'
// 1. Loads dist/index.js
// 2. Runs initialization code (sets up logger, config)
// 3. Imports ./core/engine.js
// 4. Exports factory function createEngine()
```

#### 5.5 Multiple Entry Points Strategy
If package has multiple entry points:
- **Why multiple entries?** (Performance, tree-shaking, feature separation)
- **Relationship between entries**: Shared code, independence
- **Recommended usage**: When to use which entry point

---

### 6. Functionality Deep Dive

#### 6.1 Core Functionality Mapping
**Create a functional hierarchy:**

```
Package: awesome-lib
├─ Authentication
│  ├─ login(username, password)
│  ├─ logout()
│  └─ refreshToken()
├─ Data Processing
│  ├─ transform(data, options)
│  ├─ validate(schema, data)
│  └─ serialize(data, format)
└─ Utilities
   ├─ logger
   ├─ retry(fn, attempts)
   └─ cache
```

#### 6.2 Feature Analysis (For EACH Feature)

**Feature Template:**

**Feature Name**: [Name]

**Purpose**: [What problem does it solve?]

**Entry Point**: [How to access this feature]
```javascript
import { featureName } from 'package';
```

**API Surface**:
- Functions: List all
- Classes: List all
- Types: List all

**Data Flow**:
1. Input: What data enters
2. Processing: Transformation steps
3. Output: What data leaves
4. Side effects: External impacts (file writes, API calls, etc.)

**Dependencies**:
- Internal: Other package features used
- External: Third-party packages required

**Use Cases**:
1. Primary use case with example
2. Secondary use case with example
3. Advanced use case with example

**Limitations**:
- Known issues
- Performance constraints
- Compatibility restrictions

**Examples**:
```javascript
// Basic usage
const result = featureName(input);

// Advanced usage
const result = featureName(input, {
  option1: true,
  option2: 'value'
});

// Error handling
try {
  const result = featureName(input);
} catch (error) {
  console.error('Feature failed:', error);
}
```

#### 6.3 Data Flow Analysis

**Trace data through the package:**

1. **Input Sources**:
   - Function parameters
   - Configuration files
   - Environment variables
   - External APIs/databases
   - File system

2. **Processing Stages**:
   - Validation
   - Transformation
   - Computation
   - Caching
   - Optimization

3. **Output Destinations**:
   - Return values
   - Console output
   - File writes
   - Network requests
   - Events emitted

**Create flow diagrams for major features:**
```
Input → Validation → Transform → Cache Check → Process → Output
          ↓             ↓            ↓          ↓         ↓
       Error Log    Normalize    Cache Hit   Execute   Success
```

#### 6.4 State Management
If package maintains state:
- **State location**: Where is state stored? (Memory, file, database)
- **State structure**: What does the state look like?
- **State mutations**: How is state changed?
- **State persistence**: Is state saved between sessions?
- **State cleanup**: How is state cleaned up?

#### 6.5 Event System
If package uses events:
- **Event types**: List all event names
- **Event payloads**: Data structure for each event
- **Event emitters**: What triggers each event
- **Event handlers**: How to listen for events
- **Event flow**: Order of event firing

---

### 7. Dependencies & Data Flow

#### 7.1 Dependency Analysis
- **Production dependencies**: List with purpose
- **Dev dependencies**: Build/test tools
- **Peer dependencies**: Required by consumer
- **Optional dependencies**: Enhanced features
- **Bundled dependencies**: Included in package

#### 7.2 Dependency Graph
Create visual representation:
```
package-name
├─ dependency-1 (v1.0.0) - Used for: ...
│  └─ sub-dep-1 (v2.0.0)
├─ dependency-2 (v3.0.0) - Used for: ...
└─ dependency-3 (v1.5.0) - Used for: ...
```

#### 7.3 Bundle Size Impact
- Total package size
- Size breakdown by dependency
- Tree-shaking effectiveness
- Bundle size optimization opportunities

---

### 8. Build & CI/CD Pipeline
- Build scripts
- Test framework
- Linting and formatting
- CI/CD configuration
- Publishing workflow

---

### 9. Quality & Maintainability
- TypeScript support
- Test coverage
- Documentation quality
- Maintenance status
- Code complexity

---

### 10. Security Assessment
- Known vulnerabilities
- Security advisories
- License compliance
- Maintainer verification

---

### 11. Integration & Usage Guidelines
- Framework compatibility
- Platform support
- Module system compatibility
- Integration examples
- Common use cases

---

## Advanced Analysis Techniques

### Deep Code Analysis with Repomix

#### Strategy 1: Layer-by-Layer Analysis
Analyze package in layers for complete understanding:

```bash
# Layer 1: Entry points and exports
repomix --include "index.js,index.ts,main.js,**/*.d.ts" -o analysis/layer1-entry.txt

# Layer 2: Core business logic
repomix --include "src/core/**,lib/core/**" -o analysis/layer2-core.txt

# Layer 3: Utilities and helpers
repomix --include "src/utils/**,src/helpers/**,lib/utils/**" -o analysis/layer3-utils.txt

# Layer 4: Configuration and types
repomix --include "**/*.config.js,**/types/**,**/*.d.ts" -o analysis/layer4-config.txt

# Layer 5: Tests (to understand usage patterns)
repomix --include "**/*.test.js,**/*.spec.ts,test/**" -o analysis/layer5-tests.txt
```

#### Strategy 2: Feature-Based Analysis
If package has clear feature separation:

```bash
# Analyze each feature independently
repomix --include "src/auth/**" -o analysis/feature-auth.txt
repomix --include "src/validation/**" -o analysis/feature-validation.txt
repomix --include "src/transform/**" -o analysis/feature-transform.txt
```

#### Strategy 3: Dependency Analysis
Understand internal dependencies:

```bash
# Find all import statements
grep -r "import\|require" src/ > analysis/imports.txt

# Analyze package.json
repomix --include "package.json,package-lock.json" -o analysis/dependencies.txt
```

### Entry Point Discovery Process

#### Step 1: Identify ALL Entry Points
Look in multiple locations:

1. **package.json**:
   ```json
   {
     "main": "./dist/index.js",
     "module": "./dist/index.mjs", 
     "types": "./dist/index.d.ts",
     "exports": { ... },
     "bin": { "cli-name": "./bin/cli.js" }
   }
   ```

2. **Root-level files**:
   - `index.js`, `index.ts`
   - `main.js`, `main.ts`
   - Files referenced in package.json

3. **CLI Entry Points**:
   - Files in `bin/` directory
   - Files referenced in `"bin"` field

4. **Browser Entry Points**:
   - Files referenced in `"browser"` field
   - Webpack/Rollup configs

#### Step 2: Analyze Each Entry Point

For each entry point file, document:

**File Analysis Template:**
```markdown
#### Entry Point: {filename}

**Location**: `{path/to/file}`
**Type**: {CommonJS|ESM|UMD}
**Purpose**: {What this entry is for}

**Imports**:
- Internal: [list internal imports]
- External: [list external imports]

**Exports**:
```javascript
// List ALL exports with types
export function feature1(param: Type): ReturnType { }
export class Feature2 { }
export const CONSTANT = value;
export type TypeName = { };
```

**Side Effects on Import**:
- [ ] None (pure module)
- [ ] Modifies global objects
- [ ] Registers event listeners
- [ ] Starts background processes
- [ ] Initializes singletons

**Execution Flow**:
1. Import dependencies
2. Initialize internal state
3. Register/setup components
4. Export public API

**Code Example**:
```javascript
// What happens when user imports this entry
import { feature1 } from 'package-name';
// 1. Loads dist/index.js
// 2. Imports ./internal/core.js
// 3. Initializes logger singleton
// 4. Returns feature1 function
```
```

#### Step 3: Map Export Dependencies

Create a dependency graph showing how exports relate:

```
Entry Point: index.js
├─ export function processData()
│  ├─ Uses: validateInput() from ./validators
│  ├─ Uses: transformData() from ./transformers
│  └─ Uses: Logger from ./utils/logger
├─ export class DataProcessor
│  ├─ Constructor uses: ConfigLoader
│  └─ Methods use: Cache, EventEmitter
└─ export const VERSION
   └─ Imported from: ./version
```

### Functionality Analysis Deep Dive

#### Technique 1: Trace Function Call Chains

For each exported function, trace its complete call chain:

**Example:**
```javascript
// Exported function
export function processDocument(doc) {
  // Trace: Level 1
  const validated = validateDocument(doc);  // → validators/document.js
  
  // Trace: Level 2
  const parsed = parseContent(validated);   // → parsers/content.js
  
  // Trace: Level 3
  const transformed = transform(parsed);    // → transformers/index.js
  
  // Trace: Level 4
  return serialize(transformed);           // → serializers/json.js
}
```

**Documentation Format:**
```markdown
**Function**: processDocument(doc)

**Call Chain**:
1. `validateDocument(doc)` → validators/document.js:15
   - Validates: doc.type, doc.content, doc.metadata
   - Throws: ValidationError if invalid
   
2. `parseContent(validated)` → parsers/content.js:42
   - Parses: markdown, html, plain text
   - Returns: AST (Abstract Syntax Tree)
   
3. `transform(parsed)` → transformers/index.js:8
   - Applies: plugins, filters, mappings
   - Returns: transformed AST
   
4. `serialize(transformed)` → serializers/json.js:23
   - Converts: AST to JSON
   - Returns: serialized output

**Total Depth**: 4 levels
**Files Touched**: 4 files
**External Calls**: None
**Side Effects**: Logging only
```

#### Technique 2: Identify Hidden Features

Features not immediately obvious from exports:

1. **Plugin Systems**:
   - Look for: `register()`, `use()`, `plugin()` methods
   - Check: Plugin interfaces, hooks, lifecycle methods

2. **Event Emitters**:
   - Look for: EventEmitter extends, `.on()`, `.emit()`
   - Document: All event types, payloads, timing

3. **Middleware/Interceptors**:
   - Look for: Middleware chains, interceptor patterns
   - Document: Execution order, context passing

4. **Decorators/Metadata**:
   - Look for: `@decorator` syntax, Reflect.metadata
   - Document: Available decorators, usage

5. **Factory Functions**:
   - Look for: `create*()`, `build*()`, `make*()` functions
   - Document: What they create, configuration options

#### Technique 3: API Usage Patterns

Analyze test files to understand intended usage:

```bash
# Extract all test cases
repomix --include "**/*.test.ts,**/*.spec.js" -o analysis/test-patterns.txt
```

**Document patterns found:**
- **Setup patterns**: How to initialize
- **Common workflows**: Typical usage sequences
- **Edge cases**: Unusual but valid usage
- **Anti-patterns**: What NOT to do

### Code Flow Visualization

#### Create ASCII Diagrams

**For Synchronous Functions:**
```
Input → Validate → Transform → Process → Output
         ↓           ↓          ↓         ↓
       Error?     Cache?    Execute    Success
         ↓           ↓          ↓         ↓
       Throw      Return    Continue   Return
```

**For Async Functions:**
```
async function process(data)
  ↓
await validate(data)
  ↓
await fetchConfig()
  ↓
Promise.all([
  task1(data),
  task2(data),
  task3(data)
])
  ↓
await save(results)
  ↓
return results
```

**For Event-Driven Code:**
```
User Action
    ↓
emit('start')
    ↓
Listener 1 → Process → emit('processed')
    ↓                        ↓
Listener 2 → Transform → emit('transformed')
                             ↓
                        Final Handler
```

### Integration Point Discovery

Identify HOW package integrates with other systems:

#### 1. File System Integration
```javascript
// Find all file operations
grep -rn "fs\." src/
grep -rn "readFile\|writeFile\|mkdir" src/
```

Document:
- What files are read/written
- Configuration file locations
- Temp file usage
- File watching

#### 2. Network Integration
```javascript
// Find all network calls
grep -rn "http\|fetch\|axios\|request" src/
```

Document:
- API endpoints called
- Request/response formats
- Authentication methods
- Retry/timeout handling

#### 3. Database Integration
```javascript
// Find database operations
grep -rn "query\|exec\|find\|save" src/
```

Document:
- Database types supported
- Query patterns
- Connection management
- Migration support

#### 4. Process Integration
```javascript
// Find process interactions
grep -rn "process\.\|child_process\|spawn\|exec" src/
```

Document:
- Environment variables used
- Child processes spawned
- Signal handling
- Exit behavior

### Performance Characteristics

Analyze and document:

#### 1. Computational Complexity
For key functions:
- Time complexity: O(n), O(log n), O(n²), etc.
- Space complexity: Memory usage patterns
- Bottlenecks: Identified slow operations

#### 2. Async Patterns
- Promises vs callbacks vs async/await
- Concurrency limits
- Batching strategies
- Queue management

#### 3. Caching Strategies
- What is cached
- Cache invalidation
- Cache size limits
- Cache storage (memory, disk, redis)

#### 4. Resource Usage
- Memory footprint
- CPU usage patterns
- I/O operations
- Network bandwidth

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

### Basic Requirements
- [ ] All 11 sections present and complete
- [ ] Package metadata accurate and verified
- [ ] Installation instructions clear and tested
- [ ] Saved to correct location (`npm_analysis/packages/`)
- [ ] Correct naming convention (`{package-name}_analysis.md`)
- [ ] Valid markdown formatting

### Entry Points & Exports (Section 5)
- [ ] ALL entry points identified from package.json
- [ ] Each entry point analyzed (main, module, types, exports)
- [ ] Conditional exports documented (import/require/types)
- [ ] Subpath exports listed
- [ ] Entry point execution flow traced
- [ ] Side effects on import documented
- [ ] ALL exported symbols categorized (functions/classes/constants/types)
- [ ] Function signatures with full type information
- [ ] Class structures with methods and properties

### Functionality Analysis (Section 6)
- [ ] Functional hierarchy created
- [ ] Each major feature analyzed with template
- [ ] API usage examples provided (minimum 2-3 per feature)
- [ ] Data flow traced through package
- [ ] Call chains documented for key functions
- [ ] Hidden features identified (plugins, events, middleware)
- [ ] State management documented (if applicable)
- [ ] Event system documented (if applicable)
- [ ] Integration points discovered (file system, network, database, process)

### Code Quality
- [ ] Code snippets included throughout
- [ ] Real examples from package code
- [ ] ASCII diagrams for complex flows
- [ ] Dependency graphs created
- [ ] Performance characteristics analyzed

### Documentation Quality
- [ ] Evidence-based (not speculative)
- [ ] Comprehensive API documentation
- [ ] Dependencies listed with purposes
- [ ] Security assessed
- [ ] Quality score provided (X/10)
- [ ] Integration guidelines with examples
- [ ] Common use cases documented
- [ ] Limitations and edge cases noted

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
