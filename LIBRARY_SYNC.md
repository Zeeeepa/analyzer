# Dynamic Library Sync System

## Overview

The analyzer repository uses a **dynamic library sync system** to keep external libraries (autogenlib, serena, graph-sitter) up-to-date automatically.

Instead of using traditional git submodules or manual copying, this system:
- ✅ **Auto-detects changes** in source repositories
- ✅ **Syncs only what's needed** (Python source files)
- ✅ **Filters out tests and build artifacts**
- ✅ **Maintains sync state** for efficient updates
- ✅ **Works offline** once initially cloned

## Quick Start

### Sync All Libraries

```bash
# Initial sync or update all libraries
python sync_libraries.py

# Force sync even if no changes detected
python sync_libraries.py --force

# Check status without syncing
python sync_libraries.py --check
```

### Sync Specific Library

```bash
# Sync only autogenlib
python sync_libraries.py --library autogenlib

# Sync only serena
python sync_libraries.py --library serena

# Sync only graph-sitter
python sync_libraries.py --library graph_sitter
```

### Validate Modules

```bash
# Validate all modules and adapters
python validate_modules.py

# Quick validation (imports only)
python validate_modules.py --quick

# Verbose validation
python validate_modules.py --verbose
```

## Library Configuration

The sync system is configured in `sync_libraries.py`:

```python
LIBRARY_CONFIGS = {
    "autogenlib": {
        "repo_url": "https://github.com/Zeeeepa/autogenlib.git",
        "source_path": "autogenlib",
        "target_path": LIBRARIES_DIR / "autogenlib",
    },
    "serena": {
        "repo_url": "https://github.com/Zeeeepa/serena.git",
        "source_path": "src/serena",
        "target_path": LIBRARIES_DIR / "serena",
    },
    "graph_sitter": {
        "repo_url": "https://github.com/Zeeeepa/graph-sitter.git",
        "source_path": "src",
        "target_path": LIBRARIES_DIR / "graph_sitter_lib",
    },
}
```

## Directory Structure

```
analyzer/
├── Libraries/                    # Target directory for synced libraries
│   ├── autogenlib/              # Synced from Zeeeepa/autogenlib
│   ├── serena/                  # Synced from Zeeeepa/serena
│   ├── graph_sitter_lib/        # Synced from Zeeeepa/graph-sitter
│   ├── .sync_state.json         # Tracks last sync state
│   ├── analyzer.py              # Core analyzer
│   ├── autogenlib_adapter.py    # Autogenlib integration
│   ├── graph_sitter_adapter.py  # Graph-sitter integration
│   ├── lsp_adapter.py           # LSP integration
│   └── static_libs.py           # Utilities
├── .lib_sync_temp/              # Temporary clones (gitignored)
│   ├── autogenlib/
│   ├── serena/
│   └── graph_sitter/
├── sync_libraries.py            # Sync script
├── validate_modules.py          # Validation script
└── .gitignore                   # Excludes .lib_sync_temp/
```

## How It Works

### 1. Clone or Update

The script clones repositories to `.lib_sync_temp/` or pulls latest changes if already cloned.

### 2. Calculate Hashes

It calculates MD5 hashes of source and target directories to detect changes:

```python
def should_sync(self, source_dir: Path) -> bool:
    source_hash = self.calculate_directory_hash(source_dir)
    target_hash = self.calculate_directory_hash(self.target_path)
    return source_hash != target_hash
```

### 3. Filtered Copy

Only Python source files (`*.py`, `*.pyi`, `*.typed`) are copied, excluding:
- Test files (`*test*`)
- Bytecode (`__pycache__`, `*.pyc`)
- Build artifacts

### 4. State Tracking

Sync state is saved to `Libraries/.sync_state.json`:

```json
{
  "last_sync": "2025-10-15T15:27:51.826000",
  "results": {
    "autogenlib": true,
    "serena": true,
    "graph_sitter": true
  }
}
```

## Automated Sync

### Git Hooks (Recommended)

Create `.git/hooks/post-merge` to auto-sync after git pull:

```bash
#!/bin/bash
echo "Running library sync..."
python3 sync_libraries.py
```

Make it executable:

```bash
chmod +x .git/hooks/post-merge
```

### GitHub Actions (CI/CD)

Add to `.github/workflows/sync-libraries.yml`:

```yaml
name: Sync Libraries

on:
  schedule:
    - cron: '0 0 * * *'  # Daily at midnight
  workflow_dispatch:      # Manual trigger

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - name: Sync libraries
        run: python sync_libraries.py
      - name: Commit changes
        run: |
          git config user.name "Library Sync Bot"
          git config user.email "bot@analyzer.com"
          git add Libraries/
          git commit -m "chore: sync external libraries" || exit 0
          git push
```

### Cron Job (Server)

Add to crontab for automated syncing:

```bash
# Sync libraries every 6 hours
0 */6 * * * cd /path/to/analyzer && python3 sync_libraries.py
```

## Troubleshooting

### Issue: "No module named 'X'"

**Cause**: Missing Python dependencies  
**Solution**: Install required packages

```bash
pip install openai anthropic networkx pydantic fastapi
# or
pip install -r requirements.txt
```

### Issue: "Syntax error in static_libs.py"

**Cause**: File corruption during manual edit  
**Solution**: Re-sync the library

```bash
python sync_libraries.py --force --library autogenlib
```

### Issue: "Git pull failed"

**Cause**: Temp directory has uncommitted changes  
**Solution**: The script auto-handles this by re-cloning

### Issue: "Permission denied"

**Cause**: File permissions  
**Solution**: Ensure write permissions

```bash
chmod -R u+w Libraries/
```

## Best Practices

### 1. **Regular Syncing**

Run sync at least:
- After git pull
- Before starting new work
- Before running tests
- Before deployment

### 2. **Validate After Sync**

Always validate after syncing:

```bash
python sync_libraries.py && python validate_modules.py
```

### 3. **Check Status First**

Before syncing, check if updates are needed:

```bash
python sync_libraries.py --check
```

### 4. **Use Version Control**

The synced libraries in `Libraries/` are tracked in git, so:
- ✅ Changes are versioned
- ✅ Team members get same versions
- ✅ Can rollback if needed

### 5. **Monitor Sync State**

Check `.sync_state.json` to see when last synced:

```bash
cat Libraries/.sync_state.json
```

## Advanced Usage

### Custom Sync Configuration

Modify `LIBRARY_CONFIGS` in `sync_libraries.py` to:
- Change source paths
- Add new libraries
- Adjust file patterns
- Change target locations

### Programmatic Usage

```python
from sync_libraries import SyncManager

manager = SyncManager()

# Sync all
manager.sync_all(force=True)

# Sync one
manager.sync_one("autogenlib")

# Check status
statuses = manager.check_all()
for name, status in statuses.items():
    print(f"{name}: {status['needs_sync']}")
```

### Custom Filters

Add custom include/exclude patterns:

```python
"autogenlib": {
    # ...
    "include_patterns": ["*.py", "*.pyi", "*.json"],
    "exclude_patterns": ["*test*", "*__pycache__*", "*.pyc", "*deprecated*"],
}
```

## Contributing

When contributing changes to the sync system:

1. Test the sync script:
   ```bash
   python sync_libraries.py --check
   python sync_libraries.py --force
   ```

2. Validate all modules work:
   ```bash
   python validate_modules.py
   ```

3. Update documentation if changing:
   - Library configurations
   - Sync behavior
   - File patterns

4. Commit both script and synced libraries:
   ```bash
   git add sync_libraries.py Libraries/
   git commit -m "feat: update library sync system"
   ```

## FAQs

**Q: Why not use git submodules?**  
A: Submodules are complex, require specific git commands, and include unnecessary files (tests, docs, etc.).

**Q: Why copy instead of symlink?**  
A: Copying ensures:
- Cross-platform compatibility
- No broken links
- Clean git tracking
- Easier deployment

**Q: How big are the synced libraries?**  
A: Much smaller than full repos:
- autogenlib: ~8 files
- serena: ~37 files  
- graph-sitter: ~650 files

**Q: Can I manually edit synced files?**  
A: Not recommended. Changes will be overwritten on next sync. Instead, contribute to the source repositories.

**Q: How often should I sync?**  
A: Daily for active development, weekly for stable projects.

**Q: Does this work offline?**  
A: Yes, once initially cloned, it uses cached repos in `.lib_sync_temp/`.

---

**Version**: 1.0  
**Last Updated**: 2025-10-15  
**Maintainer**: Analyzer Team

