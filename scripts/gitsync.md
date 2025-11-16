# GitSync - Repository Synchronization and Analysis Tool

## Overview

GitSync is a comprehensive Python tool for analyzing GitHub repositories and generating detailed metadata about their structure, code content, and categorization. It performs deep analysis of repositories including file counts, code statistics, module detection, and intelligent categorization.

## Features

### Core Capabilities

1. **Repository Cloning & Analysis**
   - Shallow cloning for efficiency (depth=1)
   - Support for both organizational and individual repository analysis
   - Automatic retry and error handling

2. **Code Statistics**
   - Total file count
   - Unpacked repository size
   - Code file detection (25+ programming languages)
   - Line counting for code files
   - Documentation file counting
   - Module/package detection

3. **Intelligent Categorization**
   - Pre-configured category mappings (see `categories.json`)
   - Automatic tag generation
   - Support for 30+ categories including:
     - AI Agents & Frameworks
     - Code Analysis Tools (LSP, RAG, Static Analysis)
     - MCP Servers
     - Security & Penetration Testing
     - Browser Automation
     - And many more...

4. **GitHub API Integration**
   - Repository metadata fetching
   - Star counts and language detection
   - Update timestamps
   - Support for authentication tokens

## Installation

### Prerequisites

```bash
# System requirements
- Python 3.8+
- Git 2.x+
- 2GB+ available disk space (for temporary clones)

# Python packages
pip install requests
```

### Setup

```bash
# Clone or copy the scripts
cd /path/to/analyzer
ls scripts/
# Should see: gitsync.py, gitsync.md, categories.json

# Make executable (optional)
chmod +x scripts/gitsync.py

# Set GitHub token (recommended for API rate limits)
export GITHUB_TOKEN=your_github_personal_access_token
```

## Usage

### Basic Commands

#### 1. Analyze Entire Organization

```bash
python scripts/gitsync.py --org Zeeeepa
```

This will:
- Fetch all repositories from the Zeeeepa organization
- Clone each repository (shallow)
- Analyze file structure and code
- Generate `DATA/GIT/git.csv` with results

#### 2. Analyze Specific Repositories

```bash
python scripts/gitsync.py --repos Zeeeepa/codegen Zeeeepa/analyzer Zeeeepa/agents
```

#### 3. Custom Output Location

```bash
python scripts/gitsync.py --org Zeeeepa --output results/analysis.csv
```

#### 4. Using GitHub Token

```bash
# Method 1: Environment variable
export GITHUB_TOKEN=ghp_xxxxxxxxxxxx
python scripts/gitsync.py --org Zeeeepa

# Method 2: Command line argument
python scripts/gitsync.py --org Zeeeepa --token ghp_xxxxxxxxxxxx
```

### Advanced Usage

#### Batch Processing with Custom Categories

```python
from scripts.gitsync import GitSync
from pathlib import Path

# Initialize
syncer = GitSync(github_token="your_token")

# Analyze custom list
repos = [
    ("Zeeeepa", "codegen"),
    ("Zeeeepa", "analyzer"),
    # ... more repos
]

output_path = Path("DATA/GIT/custom_analysis.csv")
syncer.sync_repositories(repos, output_path)
```

#### Integration with AI for Enhanced Categorization

The script is designed to be extended with AI-powered inference for better categorization:

```python
# Future enhancement example
class AIEnhancedGitSync(GitSync):
    def __init__(self, *args, ai_model=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.ai_model = ai_model
    
    def _get_repo_category(self, repo_name: str) -> Tuple[str, List[str]]:
        # First try manual categorization
        category, tags = super()._get_repo_category(repo_name)
        
        # If uncategorized, use AI inference
        if category == 'Other' and self.ai_model:
            # Analyze README, description, code structure
            category, tags = self.ai_model.infer_category(repo_name)
        
        return category, tags
```

## Output Format

### CSV Structure

The generated CSV file contains the following columns:

| Column | Description | Example |
|--------|-------------|---------|
| `number` | Sequential repository number | 1 |
| `repository_name` | Repository name | codegen |
| `full_name` | Full repository path | Zeeeepa/codegen |
| `description` | Repository description | Python SDK for Codegen |
| `language` | Primary programming language | Python |
| `origin_repo_stars` | Star count from GitHub | 42 |
| `updated_at` | Last update timestamp | 2025-11-15T12:00:00Z |
| `url` | Repository URL | https://github.com/... |
| `file_number` | Total file count | 153 |
| `unpacked_size` | Repository size in bytes | 2547890 |
| `total_code_files` | Number of code files | 87 |
| `total_code_lines` | Total lines of code | 12450 |
| `module_number` | Number of modules/packages | 5 |
| `total_doc_files` | Number of documentation files | 12 |
| `category` | Assigned category | Codegen |
| `tags` | Pipe-separated tags | codegen\|sdk\|python |

### Example Output

```csv
number,repository_name,full_name,description,language,origin_repo_stars,updated_at,url,file_number,unpacked_size,total_code_files,total_code_lines,module_number,total_doc_files,category,tags
1,codegen,Zeeeepa/codegen,Python SDK to Interact with Intelligent Code Generation Agents,Python,15,2025-11-15T10:30:00Z,https://github.com/Zeeeepa/codegen,153,2547890,87,12450,5,12,Codegen,codegen|sdk|python|agent
```

## Code Structure

### Main Components

#### 1. `RepoMetadata` (Data Class)
```python
@dataclass
class RepoMetadata:
    number: int
    repository_name: str
    full_name: str
    # ... all fields
```

Represents analyzed repository data.

#### 2. `GitSync` (Main Class)

**Key Methods:**

- `analyze_repository(owner, repo, number)` - Complete repository analysis
- `sync_repositories(repos, output_file)` - Batch processing
- `_shallow_clone_repo(url, temp_dir)` - Efficient cloning
- `_analyze_local_repo(path)` - File system analysis
- `_get_repo_category(repo_name)` - Category assignment
- `_get_github_repo_info(owner, repo)` - API calls

**Configuration Constants:**

```python
CODE_EXTENSIONS = {'.py', '.js', '.ts', ...}  # 20+ languages
DOC_EXTENSIONS = {'.md', '.rst', '.txt', ...}
MODULE_FILES = {
    'python': ['__init__.py', 'setup.py', ...],
    'node': ['package.json', ...],
    # ... more languages
}
```

### Analysis Pipeline

```
1. Fetch GitHub Metadata (API)
   ↓
2. Clone Repository (shallow)
   ↓
3. Analyze File System
   ├── Count files
   ├── Calculate size
   ├── Identify code files
   ├── Count lines
   ├── Detect modules
   └── Find documentation
   ↓
4. Assign Category & Tags
   ↓
5. Generate RepoMetadata
   ↓
6. Write to CSV
```

## Categorization System

### Category Definition (categories.json)

```json
{
  "categories": {
    "Codegen": {
      "description": "Core Codegen ecosystem tools and SDKs",
      "repos": ["codegen", "codegen-api-client", ...]
    },
    "AI Agents": {
      "description": "General-purpose AI agents and frameworks",
      "repos": ["AutoGPT", "agent-framework", ...]
    },
    // ... more categories
  }
}
```

### Automatic Tag Generation

Tags are automatically generated based on:
1. Category name (lowercased, hyphenated)
2. Keyword detection in description:
   - `agent` → adds "agent" tag
   - `mcp` → adds "mcp" tag
   - `claude` → adds "claude" tag
   - `security`/`penetration` → adds "security" tag
   - `api` → adds "api" tag

### Supported Categories

1. **Codegen** - Core ecosystem
2. **Testing & Fix** - Test frameworks
3. **Code Analysis** - LSP, RAG, Static Analysis, Indexing
4. **Sandboxing** - Code execution isolation
5. **Evolution & Intelligence** - Meta-learning systems
6. **Claude Code** - Claude enhancements
7. **CLI Agents** - Command-line agents
8. **IDE** - AI-powered editors
9. **AI Agents** - General frameworks
10. **APIs & Proxies** - API tools
11. **Enterprise** - Enterprise automation
12. **UI & Chat** - Interface components
13. **MCP Servers** - Model Context Protocol
14. **Browser Automation** - Web interaction
15. **Penetration & Security** - Security tools
16. **Vision & Multimodal** - Computer vision
17. **Knowledge Base** - Knowledge management
18. **Research** - Research tools
19. **Data & Analytics** - Data processing
20. **Infrastructure & DevOps** - Deployment
21. **Trading & Finance** - Financial tools
22. **Gaming** - Game development
23. **Productivity** - Automation tools
24. **Communication** - Messaging
25. **Other** - Miscellaneous

## Recommended Packages

### For Basic Functionality

```bash
pip install requests  # GitHub API calls
```

### For Enhanced Analysis (Optional)

```bash
# Code quality analysis
pip install radon  # Code complexity metrics
pip install lizard  # Code complexity analyzer

# Language-specific parsers
pip install pygments  # Syntax highlighting & analysis
pip install tree-sitter  # Multi-language parsing

# Performance
pip install aiohttp  # Async HTTP requests
pip install asyncio  # Async operations

# AI Integration
pip install openai  # For AI-powered categorization
pip install anthropic  # Claude API
```

### External Tools

```bash
# Code statistics
sudo apt-get install cloc  # Count lines of code

# Repository analysis
sudo apt-get install tokei  # Fast code counter (Rust-based)

# Advanced Git operations
sudo apt-get install git-lfs  # Large file support
```

## Performance Considerations

### Optimization Strategies

1. **Shallow Cloning**
   - Uses `--depth 1` for speed
   - Saves ~70% bandwidth and time

2. **Temporary Storage**
   - Uses system temp directory
   - Automatic cleanup after analysis

3. **Error Handling**
   - Graceful failure for individual repos
   - Continues batch processing on errors
   - 5-minute timeout per repository

4. **API Rate Limits**
   - Unauthenticated: 60 requests/hour
   - Authenticated: 5,000 requests/hour
   - Recommendation: Always use token

### Performance Metrics

- **Single Repository**: ~5-30 seconds (depends on size)
- **100 Repositories**: ~10-50 minutes
- **737 Repositories (full org)**: ~2-6 hours

Memory usage: ~50-200 MB per repository (temporary)

## Extending GitSync

### Adding New File Types

```python
# In GitSync class
CODE_EXTENSIONS.update({'.dart', '.lua', '.nim'})
DOC_EXTENSIONS.update({'.asciidoc', '.wiki'})
```

### Adding New Module Detectors

```python
MODULE_FILES['elixir'] = ['mix.exs', 'mix.lock']
MODULE_FILES['dart'] = ['pubspec.yaml', 'pubspec.lock']
```

### Custom Analysis Functions

```python
def _analyze_test_coverage(self, repo_path: Path) -> float:
    """Calculate test coverage percentage"""
    # Implementation
    pass

# Add to analyze_local_repo
stats['test_coverage'] = self._analyze_test_coverage(repo_path)
```

### AI-Powered Enhancements

Future integration points for AI inference:

1. **Description Enhancement**
   - Generate better descriptions from code analysis
   - Summarize README content

2. **Smart Categorization**
   - Use LLM to categorize uncategorized repos
   - Analyze code patterns for category inference

3. **Tag Generation**
   - Extract keywords from code and docs
   - Identify technology stack automatically

4. **Quality Metrics**
   - Code quality scoring
   - Documentation completeness
   - Best practices compliance

## Troubleshooting

### Common Issues

#### 1. Git Clone Failures

```bash
# Error: "fatal: unable to access..."
# Solution: Check network and repository permissions
git config --global http.postBuffer 524288000
```

#### 2. API Rate Limit

```
Error: API rate limit exceeded
Solution: Use GitHub token or wait for limit reset
```

#### 3. Permission Denied

```bash
# Error: "permission denied"
# Solution: Make script executable
chmod +x scripts/gitsync.py
```

#### 4. Module Not Found

```bash
# Error: "ModuleNotFoundError: No module named 'requests'"
# Solution: Install dependencies
pip install requests
```

### Debug Mode

```python
# Enable verbose logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Run analysis
syncer = GitSync(github_token="token")
# ... analysis will show detailed logs
```

## Contributing

### Adding New Categories

1. Edit `scripts/categories.json`
2. Add repository names to appropriate category
3. Test with: `python scripts/gitsync.py --repos Zeeeepa/your-repo`

### Reporting Issues

Include:
- Python version
- Git version
- Error message
- Repository being analyzed
- Command used

## License

MIT License - See repository LICENSE file

## Support

- **GitHub Issues**: Report bugs and request features
- **Documentation**: This file and inline code comments
- **Examples**: See `examples/` directory (if available)

---

**Last Updated**: 2025-11-16  
**Version**: 1.0.0  
**Maintainer**: Codegen Team

