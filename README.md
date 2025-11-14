# Enterprise WrtnLabs Deployment System

**Production-grade deployment orchestrator with advanced automation and validation**

[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://python.org)
[![Node.js](https://img.shields.io/badge/node-%3E%3D18.0.0-brightgreen.svg)](https://nodejs.org)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Enterprise](https://img.shields.io/badge/grade-enterprise-purple.svg)]()

---

## 🚀 Quick Start

```bash
# Validate system prerequisites
python3 enterprise_setup.py validate

# Run full installation
python3 enterprise_setup.py install

# Run in test mode (CI/CD friendly)
python3 enterprise_setup.py test

# Create configuration backup
python3 enterprise_setup.py backup --name my_backup

# Restore from backup
python3 enterprise_setup.py restore my_backup
```

---

## 📋 Features

### ✅ Full argparse CLI
- **5 Commands:** validate, install, backup, restore, test
- **Global Options:** --verbose, --timeout
- **Subcommand Arguments:** Custom backup names, specific restore points
- **Default Command:** Runs validation if no command specified

### ✅ Type Hints Throughout
- Full type annotations with `typing` module
- `@dataclass` for structured validation results
- `Optional`, `Dict`, `List`, `Tuple`, `Any` types
- Type-safe return values

### ✅ Comprehensive Error Handling
- Try-catch blocks at all critical operations
- Timeout handling (5-second default, configurable)
- Graceful degradation for optional features
- Detailed error messages with suggestions
- Exception logging to file

### ✅ Modular Class Design
- **SystemChecker** - Pre-flight validation
- **DependencyInstaller** - Auto-detection & installation
- **BackupManager** - Backup/restore operations
- **EnterpriseSetup** - Main orchestrator

### ✅ Beautiful Colored Output
- 10 ANSI color codes (red, green, yellow, blue, magenta, cyan, white, bold, dim, underline)
- Status indicators: ✓ (success), ✗ (error), ⚠ (warning), → (info)
- Progress tracking with clear visual separation
- Color-coded command results

### ✅ Detailed Logging
- Timestamped logs to `logs/setup_YYYYMMDD_HHMMSS.log`
- Log levels: DEBUG (verbose), INFO (normal)
- Structured logging with module names
- Exception stack traces
- Automatic log directory creation

### ✅ 5-Second Timeouts
- Configurable timeout for all subprocess calls
- Prevents hanging on network issues
- Can be adjusted via `--timeout` flag
- Separate timeout for dependency installation (300s)

### ✅ Non-Interactive Test Mode
- CI/CD friendly test command
- Runs validation without user interaction
- Returns proper exit codes (0=success, 1=failure, 130=interrupted)
- Compatible with automated testing

---

## 🏗️ Architecture

### Class Structure

```
EnterpriseSetup (Main Orchestrator)
├── SystemChecker (Validation)
│   ├── check_node()
│   ├── check_package_manager()
│   ├── check_git()
│   ├── check_docker()
│   ├── check_disk_space()
│   └── check_python()
│
├── DependencyInstaller (Installation)
│   ├── detect_package_manager()
│   ├── install_repo(repo)
│   └── install_all()
│
└── BackupManager (Backup/Restore)
    ├── create_backup(name?)
    ├── list_backups()
    └── restore_backup(name)
```

### Data Flow

```
CLI Arguments → EnterpriseSetup.__init__()
                       ↓
              _setup_logging()
                       ↓
              SystemChecker (timeout=5s)
                       ↓
              BackupManager (script_dir)
                       ↓
              DependencyInstaller (auto-detect PM)
                       ↓
              Command Router (validate/install/backup/restore/test)
                       ↓
              Exit Code (0=success, 1=error, 130=interrupt)
```

---

## 💻 CLI Commands

### 1. Validate

**Check system prerequisites without making changes**

```bash
python3 enterprise_setup.py validate

# With verbose logging
python3 enterprise_setup.py --verbose validate

# With custom timeout
python3 enterprise_setup.py --timeout 10 validate
```

**Checks:**
- ✓ Node.js v18+
- ✓ Package manager (pnpm/npm)
- ✓ Git installation
- ✓ Python 3.8+
- ✓ Disk space (2GB+)
- ✓ Docker daemon (optional)

**Exit Codes:**
- `0` - All checks passed
- `1` - One or more checks failed

### 2. Install

**Run full installation with validation and backup**

```bash
python3 enterprise_setup.py install

# With verbose output
python3 enterprise_setup.py --verbose install
```

**Steps:**
1. **Validation** - Run all prerequisite checks
2. **Backup** - Create .env backup if exists
3. **Installation** - Install dependencies for all repos

**Exit Codes:**
- `0` - Installation successful
- `1` - Validation failed or installation errors

### 3. Backup

**Create configuration backup**

```bash
# Auto-generated timestamp name
python3 enterprise_setup.py backup

# Custom backup name
python3 enterprise_setup.py backup --name pre_upgrade

# Short form
python3 enterprise_setup.py backup -n production_config
```

**Backup Location:** `.backups/`

**Exit Codes:**
- `0` - Backup created
- `1` - No .env file or backup failed

### 4. Restore

**Restore configuration from backup**

```bash
# List available backups
python3 enterprise_setup.py restore

# Restore specific backup
python3 enterprise_setup.py restore env_backup_20251114_153000

# Restore custom named backup
python3 enterprise_setup.py restore pre_upgrade
```

**Safety:** Creates `pre_restore` backup before restoring

**Exit Codes:**
- `0` - Restore successful
- `1` - Backup not found or restore failed

### 5. Test

**Non-interactive test mode for CI/CD**

```bash
python3 enterprise_setup.py test
```

**Behavior:**
- Runs validation checks
- No user interaction required
- Proper exit codes for automation
- CI/CD friendly

---

## 🎨 Output Examples

### Validation Success

```
══════════════════════════════════════════════════════════════════
  Enterprise WrtnLabs Deployment System
  
  AutoBE + AutoView + Agentica + Vector Store
  Powered by Z.ai GLM-4.6 / GLM-4.5V
══════════════════════════════════════════════════════════════════

System Validation
──────────────────────────────────────────────────────────────────

✓ Node.js: Node.js 22.14.0
  Version requirement satisfied
✓ Package Manager: pnpm 10.15.0
  Package manager available
✓ Git: git version 2.43.0
  Git available
✓ Python: Python 3.11.5
  Version 3.8+ satisfied
✓ Disk Space: 45.2 GB available
  Exceeds 2.0 GB requirement
✓ Docker: Docker version 25.0.3, build 4debf41
  Docker daemon running

✓ All checks passed!
```

### Installation Progress

```
Step 3: Dependencies
──────────────────────────────────────────────────────────────────

Dependency Installation
============================================================

📦 Installing autobe...
✓ autobe complete

📦 Installing autoview...
✓ autoview complete

📦 Installing agentica...
✓ agentica complete

📦 Installing vector-store...
✓ vector-store complete

📦 Installing backend...
✓ backend complete

📦 Installing connectors...
✓ connectors complete

Results: 6 success, 0 failed

✓ Installation complete!
```

### Backup Operation

```
Creating Backup
──────────────────────────────────────────────────────────────────

✓ Backup created: env_backup_20251114_153000
```

### Restore Operation

```
Available Backups
──────────────────────────────────────────────────────────────────

1. pre_restore (2025-11-14 15:30:45)
2. pre_upgrade (2025-11-14 14:20:30)
3. env_backup_20251114_120000 (2025-11-14 12:00:00)

✓ Backup created: pre_restore
✓ Restored from: pre_upgrade
```

---

## 🔧 Configuration

### Global Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--verbose` | `-v` | flag | False | Enable verbose output |
| `--timeout` | `-t` | int | 5 | Command timeout in seconds |

### Command-Specific Options

**backup:**
- `--name` / `-n` - Custom backup name (default: timestamp)

**restore:**
- `backup_name` - Backup to restore (positional, optional for listing)

---

## 📊 Validation Details

### SystemChecker Class

**Pre-flight validation with intelligent checks**

```python
checker = SystemChecker(timeout=5)
result = checker.check_node()

# ValidationResult dataclass
result.success  # bool
result.message  # str (version or error)
result.details  # Optional[str] (additional info)
```

**Validation Checks:**

1. **Node.js Check**
   - Runs: `node --version`
   - Requires: v18+
   - Parses version, extracts major number

2. **Package Manager Check**
   - Tests: pnpm, npm (in order)
   - Returns: First available
   - Suggests: `npm install -g pnpm`

3. **Git Check**
   - Runs: `git --version`
   - Verifies: Installation exists

4. **Python Check**
   - Uses: `sys.version`
   - Requires: 3.8+

5. **Disk Space Check**
   - Uses: `shutil.disk_usage('/')`
   - Requires: 2GB+
   - Reports: Available space in GB

6. **Docker Check** (Optional)
   - Runs: `docker --version`
   - Tests: `docker ps` (daemon running)
   - Non-blocking: Doesn't fail validation

---

## 🗂️ File Structure

```
analyzer/
├── enterprise_setup.py       ← Main script (647 lines)
├── README_ENTERPRISE.md       ← This file
├── logs/                      ← Auto-generated logs
│   └── setup_YYYYMMDD_HHMMSS.log
├── .backups/                  ← Configuration backups
│   ├── env_backup_YYYYMMDD_HHMMSS
│   └── pre_restore
├── autobe/                    ← Repositories
├── autoview/
├── agentica/
├── vector-store/
├── backend/
└── connectors/
```

---

## 🔒 Security Features

### Backup System
- **Automatic backup** before restore operations
- **Timestamped backups** for version control
- **Custom names** for important configurations
- **Isolated directory** (.backups/)

### Logging
- **Secure log directory** with proper permissions
- **Timestamped log files** for audit trail
- **Exception stack traces** for debugging
- **No sensitive data** in logs (designed carefully)

### Error Handling
- **Timeout protection** prevents hanging
- **Graceful degradation** for optional features
- **Clear error messages** without exposing internals
- **Exit codes** for automation safety

---

## 🧪 Testing

### Unit Testing

```bash
# Run in test mode
python3 enterprise_setup.py test

# Test with verbose logging
python3 enterprise_setup.py --verbose test

# Test with custom timeout
python3 enterprise_setup.py --timeout 10 test
```

### CI/CD Integration

```yaml
# GitHub Actions example
- name: Validate environment
  run: python3 enterprise_setup.py test
  timeout-minutes: 2

- name: Install dependencies
  run: python3 enterprise_setup.py install
  timeout-minutes: 15
  if: steps.validate.outcome == 'success'
```

### Exit Code Handling

```bash
# Bash script example
if python3 enterprise_setup.py validate; then
    echo "Validation passed"
    python3 enterprise_setup.py install
else
    echo "Validation failed" >&2
    exit 1
fi
```

---

## 📚 Advanced Usage

### Custom Timeout

```bash
# For slow networks
python3 enterprise_setup.py --timeout 30 validate

# For fast systems
python3 enterprise_setup.py --timeout 2 validate
```

### Verbose Mode

```bash
# See all subprocess output
python3 enterprise_setup.py --verbose install

# Debug logging to file + console
python3 enterprise_setup.py -v validate
```

### Backup Management

```bash
# Create named backup before major changes
python3 enterprise_setup.py backup --name pre_v2_upgrade

# List all backups
python3 enterprise_setup.py restore

# Restore after testing
python3 enterprise_setup.py restore pre_v2_upgrade
```

### Automation Scripts

```bash
#!/bin/bash
# deployment.sh

set -e

echo "Step 1: Validation"
python3 enterprise_setup.py test || exit 1

echo "Step 2: Backup"
python3 enterprise_setup.py backup --name pre_deploy

echo "Step 3: Install"
python3 enterprise_setup.py --timeout 60 install || {
    echo "Installation failed, restoring backup"
    python3 enterprise_setup.py restore pre_deploy
    exit 1
}

echo "Deployment complete!"
```

---

## 🐛 Troubleshooting

### "Command timed out after 5s"

**Solution:** Increase timeout
```bash
python3 enterprise_setup.py --timeout 30 validate
```

### "No package manager found"

**Solution:** Install pnpm
```bash
npm install -g pnpm
```

### "Node.js not found"

**Solution:** Install Node.js v18+
```bash
# macOS
brew install node@22

# Ubuntu
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y nodejs
```

### "Backup not found"

**Solution:** List available backups
```bash
python3 enterprise_setup.py restore
```

### Installation errors

**Solution:** Run with verbose mode
```bash
python3 enterprise_setup.py --verbose install
```

Check logs:
```bash
cat logs/setup_*.log | tail -100
```

---

## 🤝 Contributing

### Code Style

- **PEP 8** compliant
- **Type hints** throughout
- **Docstrings** for all classes and methods
- **4-space indentation**
- **Class-based design**

### Adding New Checks

```python
def check_new_tool(self) -> ValidationResult:
    """Check new tool installation"""
    self.logger.info("Checking new tool...")
    code, stdout, stderr = self.run_command(['newtool', '--version'])
    
    if code == 0:
        return ValidationResult(True, stdout.strip(), "Tool available")
    
    return ValidationResult(
        False,
        "Tool not found",
        "Install from: https://newtool.example.com"
    )
```

Add to `run_all_checks()`:
```python
checks = [
    # ... existing checks ...
    ("New Tool", self.check_new_tool),
]
```

---

## 📄 License

MIT License - See LICENSE file

---

## 🙏 Acknowledgments

- **WrtnLabs** - AutoBE ecosystem
- **Z.ai** - GLM-4.6/4.5V models
- **Python** - argparse, typing, pathlib

---

## 🔗 Links

- **Repository:** https://github.com/Zeeeepa/analyzer
- **AutoBE:** https://github.com/wrtnlabs/autobe
- **Documentation:** https://autobe.dev/docs

---

**Made with ❤️ for enterprise deployments**
