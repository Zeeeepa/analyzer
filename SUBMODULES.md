# Git Submodules Setup

This repository uses **Git submodules** to link external libraries without copying their code. The submodules appear as folder links (like in the image you shared) that point to specific commits in external repositories.

## 📦 Submodules Included

| Library | Path | Repository |
|---------|------|------------|
| **autogenlib** | `Libraries/autogenlib` | https://github.com/Zeeeepa/autogenlib |
| **serena** | `Libraries/serena` | https://github.com/Zeeeepa/serena |
| **graph-sitter** | `Libraries/graph-sitter` | https://github.com/Zeeeepa/graph-sitter |

## 🚀 Quick Start

### First Time Clone

When cloning this repository, you need to initialize and update the submodules:

```bash
# Option 1: Clone with submodules in one command
git clone --recursive https://github.com/Zeeeepa/analyzer.git

# Option 2: Clone then initialize submodules
git clone https://github.com/Zeeeepa/analyzer.git
cd analyzer
git submodule init
git submodule update
```

### Update Submodules to Latest

To pull the latest changes from the linked repositories:

```bash
# Update all submodules to their latest commits
git submodule update --remote

# Or update specific submodule
git submodule update --remote Libraries/autogenlib
```

### Commit Submodule Updates

After updating submodules, commit the new references:

```bash
git submodule update --remote
git add Libraries/autogenlib Libraries/serena Libraries/graph-sitter
git commit -m "chore: update submodules to latest versions"
git push
```

## 🔧 Common Commands

### Check Submodule Status
```bash
git submodule status
```

### Pull Latest Changes (Including Submodules)
```bash
git pull --recurse-submodules
```

### Work Inside a Submodule
```bash
cd Libraries/autogenlib
git checkout main
git pull
# Make changes, commit, push
cd ../..
git add Libraries/autogenlib
git commit -m "chore: update autogenlib submodule"
```

### Remove a Submodule
```bash
# 1. Remove from .gitmodules
git config -f .gitmodules --remove-section submodule.Libraries/autogenlib

# 2. Remove from .git/config
git config -f .git/config --remove-section submodule.Libraries/autogenlib

# 3. Remove cached entry
git rm --cached Libraries/autogenlib

# 4. Remove directory
rm -rf Libraries/autogenlib

# 5. Commit
git commit -m "chore: remove autogenlib submodule"
```

## 📁 Directory Structure

```
analyzer/
├── Libraries/
│   ├── autogenlib/          # → https://github.com/Zeeeepa/autogenlib @ commit_hash
│   ├── serena/              # → https://github.com/Zeeeepa/serena @ commit_hash
│   └── graph-sitter/        # → https://github.com/Zeeeepa/graph-sitter @ commit_hash
├── .gitmodules              # Submodule configuration
└── SUBMODULES.md            # This file
```

## 🎯 How It Works

### On GitHub
- Submodules appear as **folder links** with commit hashes (like in your image)
- Clicking them takes you to the external repository at that specific commit
- The actual code is NOT stored in your repository

### Locally
- After `git submodule update`, the full code is cloned into each submodule folder
- Each submodule is a separate git repository
- You can work inside submodules and push changes back to their origin

### Commit Tracking
- The main repository tracks which **commit hash** of each submodule to use
- When you update a submodule, you're changing which commit the main repo points to
- Others must run `git submodule update` to get the new commits

## ⚙️ Configuration

The `.gitmodules` file contains the submodule configuration:

```ini
[submodule "Libraries/autogenlib"]
    path = Libraries/autogenlib
    url = https://github.com/Zeeeepa/autogenlib.git

[submodule "Libraries/serena"]
    path = Libraries/serena
    url = https://github.com/Zeeeepa/serena.git

[submodule "Libraries/graph-sitter"]
    path = Libraries/graph-sitter
    url = https://github.com/Zeeeepa/graph-sitter.git
```

## 🔄 Automated Updates

### GitHub Actions

Create `.github/workflows/update-submodules.yml`:

```yaml
name: Update Submodules

on:
  schedule:
    - cron: '0 0 * * 0'  # Weekly on Sunday
  workflow_dispatch:      # Manual trigger

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
        with:
          submodules: true
          token: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Update submodules
        run: |
          git submodule update --remote
          git config user.name "GitHub Actions"
          git config user.email "actions@github.com"
          git add Libraries/
          git diff --staged --quiet || git commit -m "chore: update submodules"
          git push
```

### Git Hook

Create `.git/hooks/post-merge`:

```bash
#!/bin/bash
echo "Updating submodules..."
git submodule update --init --recursive
```

Make it executable:
```bash
chmod +x .git/hooks/post-merge
```

## 🆚 Submodules vs Copied Code

### Git Submodules (This Approach)
✅ No code duplication  
✅ Always links to specific commit  
✅ Smaller repository size  
✅ Easy to see which version is used  
❌ Requires `git submodule` commands  
❌ More complex workflow  

### Copied Code (Previous Approach)
✅ Simpler workflow  
✅ All code in one place  
✅ No submodule commands needed  
❌ Code duplication  
❌ Larger repository  
❌ Manual syncing required  

## 📚 Resources

- [Git Submodules Documentation](https://git-scm.com/book/en/v2/Git-Tools-Submodules)
- [GitHub Submodules Guide](https://github.blog/2016-02-01-working-with-submodules/)
- [Atlassian Submodules Tutorial](https://www.atlassian.com/git/tutorials/git-submodule)

## 🔍 Troubleshooting

### Submodule directory is empty
```bash
git submodule init
git submodule update
```

### Submodule is in detached HEAD state
This is normal! Submodules track specific commits, not branches.

To work on a submodule:
```bash
cd Libraries/autogenlib
git checkout main
git pull
# Make changes and push
```

### Accidentally committed submodule as regular files
```bash
# Remove from index
git rm -rf --cached Libraries/autogenlib

# Delete directory
rm -rf Libraries/autogenlib

# Re-add as submodule
git submodule add https://github.com/Zeeeepa/autogenlib.git Libraries/autogenlib
```

### Update all submodules recursively
```bash
git submodule update --init --recursive --remote
```

---

**Need help?** Check the [Git Submodules Documentation](https://git-scm.com/book/en/v2/Git-Tools-Submodules) or create an issue!

