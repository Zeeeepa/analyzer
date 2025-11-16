# Git Repository Analysis Tools

Two-phase analysis system for GitHub repositories:

1. **sync.py** - Fast static index generation from GitHub API
2. **CodeContext.py** - Deep code analysis by cloning repos

## Phase 1: Static Index (`sync.py`)

Creates a lightweight index with GitHub metadata only (no cloning).

### Features
- Fetches all repository metadata from GitHub API
- No repository cloning (very fast)
- Includes stars, forks, topics, licenses, etc.
- ~3 minutes for 749 repos

### Usage

```bash
# Set GitHub token for higher rate limits
export GITHUB_TOKEN="your_token_here"

# Run static index generation
python scripts/git/sync.py
```

### Output: `DATA/GIT/index.csv`

**22 Fields:**
- Basic: `number`, `repository_name`, `full_name`, `description`
- GitHub Stats: `stars`, `forks`, `watchers`, `open_issues`
- Metadata: `language`, `created_at`, `updated_at`, `pushed_at`
- Info: `url`, `clone_url`, `homepage`, `topics`, `license`
- Size: `size` (KB from GitHub API)
- Branch: `default_branch`
- Flags: `is_fork`, `is_archived`, `is_template`

**Example:**
```csv
number,repository_name,full_name,language,stars,size,topics,license
1,athena-protocol,Zeeeepa/athena-protocol,TypeScript,1,489,,MIT
2,mcpb,Zeeeepa/mcpb,TypeScript,1,1961,,MIT
```

---

## Phase 2: Code Context (`CodeContext.py`)

Clones repositories and performs deep code analysis.

### Features
- Clones each repo (shallow depth=1)
- Language detection from actual files
- Code statistics (files, lines, extensions)
- Documentation analysis
- Module/package detection
- Test framework detection
- CI/CD system detection
- Build system detection
- ~30-60 minutes for 749 repos

### Usage

```bash
# Run after sync.py has created index.csv
python scripts/git/CodeContext.py
```

**Requires:** `DATA/GIT/index.csv` must exist (run `sync.py` first)

### Output: `DATA/GIT/code_context.csv`

**24 Fields:**

**Basic Info:**
- `number`, `repository_name`, `full_name`

**Language & Files:**
- `primary_language` - Detected from actual code files
- `total_files`, `total_directories`, `total_size_bytes`
- `code_files`, `code_lines`, `code_extensions` (pipe-separated)

**Documentation:**
- `doc_files`, `doc_types` (md, rst, txt, etc)

**Modules:**
- `modules_count` - Number of package managers detected
- `module_types` - python, npm, cargo, maven, etc

**Configuration:**
- `config_files`, `config_types` (json, yaml, toml, etc)

**Testing:**
- `test_files` - Number of test files found
- `test_frameworks` - pytest, jest, junit, etc

**CI/CD & Build:**
- `has_ci` - Boolean
- `ci_systems` - github-actions, gitlab-ci, etc
- `build_systems` - make, cmake, gradle, etc

**Structure:**
- `max_depth` - Maximum directory depth
- `largest_file` - Path to largest file
- `largest_file_size` - Size in bytes

**Example:**
```csv
number,repository_name,primary_language,code_files,code_lines,modules_count,test_files
1,athena-protocol,TypeScript,55,13324,1,0
2,mcpb,Python,40,7582,3,8
```

---

## Complete Workflow

### 1. Quick Index (3 minutes)
```bash
export GITHUB_TOKEN="your_token"
python scripts/git/sync.py
```

**Result:** `DATA/GIT/index.csv` with 747 repos

### 2. Deep Analysis (30-60 minutes)
```bash
python scripts/git/CodeContext.py
```

**Result:** `DATA/GIT/code_context.csv` with detailed code metrics

### 3. Analysis Complete!

You now have:
- **index.csv** - GitHub metadata (250 KB, instant queries)
- **code_context.csv** - Code analysis (deeper insights)

---

## Comparison: Old vs New

### Old System (`scripts/gitsync.py`)
- ❌ Combined both phases into one slow process
- ❌ Required cloning for every run
- ❌ Included categorization logic
- ⏱️ ~16 minutes for complete analysis

### New System (`scripts/git/`)
- ✅ Separated into two independent phases
- ✅ Fast index without cloning (3 min)
- ✅ Optional deep analysis (30-60 min)
- ✅ No categorization (pure data)
- ✅ More detailed code metrics
- ✅ Better organized (separate concerns)

---

## Data Examples

### Index.csv Sample
```csv
number,repository_name,language,stars,forks,size,license
1,athena-protocol,TypeScript,1,0,489,MIT
2,mcpb,TypeScript,1,0,1961,MIT
3,tokligence-gateway,Go,1,0,13483,Apache-2.0
```

### Code Context Sample
```csv
number,repository_name,primary_language,code_files,code_lines,modules
1,athena-protocol,TypeScript,55,13324,npm
2,mcpb,Python,40,7582,npm|python|yarn
3,tokligence-gateway,TypeScript,70,14459,go|npm
```

---

## Configuration

### Hardcoded Settings

**sync.py:**
- Organization: `Zeeeepa`
- Output: `DATA/GIT/index.csv`

**CodeContext.py:**
- Input: `DATA/GIT/index.csv`
- Output: `DATA/GIT/code_context.csv`

### GitHub Token

Set via environment variable for both scripts:
```bash
export GITHUB_TOKEN="your_personal_access_token"
```

**Without token:** 60 requests/hour
**With token:** 5000 requests/hour

---

## Language Detection

### sync.py
Uses GitHub's reported primary language from API.

### CodeContext.py
Detects from actual file extensions:

**Supported:** Python, JavaScript, TypeScript, Java, C/C++, Go, Rust, Ruby, PHP, Swift, Kotlin, Scala, R, Julia, MATLAB, Vue, Svelte, Solidity, Zig, C#, F#, Elixir, Erlang, Haskell, OCaml, Dart, Lua, Perl, Shell, and more.

---

## Module Detection

Detects package managers by looking for:

- **Python:** setup.py, pyproject.toml, requirements.txt, Pipfile
- **Node.js:** package.json, yarn.lock, pnpm-lock.yaml
- **Rust:** Cargo.toml
- **Go:** go.mod
- **Java:** pom.xml, build.gradle
- **Ruby:** Gemfile
- **PHP:** composer.json
- **Elixir:** mix.exs
- **Swift:** Package.swift
- **Dart:** pubspec.yaml

---

## CI/CD Detection

Detects continuous integration systems:

- GitHub Actions (`.github/workflows/`)
- GitLab CI (`.gitlab-ci.yml`)
- Travis CI (`.travis.yml`)
- CircleCI (`.circleci/config.yml`)
- Azure Pipelines (`azure-pipelines.yml`)
- Jenkins (`Jenkinsfile`)
- Drone (`.drone.yml`)

---

## Build System Detection

Detects build systems:

- Make (`Makefile`)
- CMake (`CMakeLists.txt`)
- Gradle (`build.gradle`)
- Maven (`pom.xml`)
- Meson (`meson.build`)
- Bazel (`BUILD`, `WORKSPACE`)

---

## Test Framework Detection

Detects test files by patterns:

- pytest: `test_*.py`
- Go tests: `*_test.go`
- Jest: `*.test.js`, `*.test.ts`
- Jasmine/Mocha: `*.spec.js`, `*.spec.ts`
- JUnit: `*Test.java`
- NUnit: `*Tests.cs`

---

## Error Handling

Both scripts handle errors gracefully:
- API rate limits
- Network timeouts
- Clone failures
- Permission errors
- Invalid repositories

Failed repositories are skipped and logged.

---

## Output Structure

```
DATA/
└── GIT/
    ├── index.csv         # Static GitHub metadata
    └── code_context.csv  # Deep code analysis
```

---

## Performance

### sync.py
- **Speed:** ~0.24 seconds per repo
- **Total Time:** ~3 minutes for 749 repos
- **Network:** API calls only (no cloning)
- **Disk:** Minimal (CSV output only)

### CodeContext.py
- **Speed:** ~2-5 seconds per repo
- **Total Time:** 30-60 minutes for 749 repos
- **Network:** Clones each repo (shallow depth=1)
- **Disk:** Temporary (clones deleted after analysis)

---

## Dependencies

**Both scripts:**
- Python 3.7+
- `requests` library

**CodeContext.py only:**
- Git installed and in PATH
- Network access to GitHub
- Disk space for temporary clones (~10-20GB during execution)

Install dependencies:
```bash
pip install requests
```

---

## Troubleshooting

### "No repositories found"
- Check GitHub token
- Verify organization name
- Check network connectivity

### "API rate limit exceeded"
- Set `GITHUB_TOKEN` environment variable
- Wait for rate limit reset

### "Clone failed"
- Check Git installation
- Verify network connectivity
- Check disk space

### "Index file not found"
- Run `sync.py` first before `CodeContext.py`

---

## Future Enhancements

Potential improvements:
- Parallel processing for faster analysis
- Resume capability for interrupted runs
- Custom filters (language, size, etc)
- Dependency graph generation
- Security vulnerability scanning
- Code quality metrics
- Duplicate code detection

---

## License

MIT License - Free to use and modify

---

## Author

Generated by Codegen AI Agent

