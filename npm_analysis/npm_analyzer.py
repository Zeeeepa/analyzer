"""
NPM Package Analysis Script using Codegen API
==============================================

This script creates Codegen agent runs for multiple NPM packages with:
- Progress tracking in analysis_logs.md
- Resume capability from last successful package
- Proper error handling and logging
- Reports saved to 'analysis' branch

Prerequisites:
- pip install codegen

Usage:
    # Full run
    python npm_analyzer.py
    
    # Test with first 5 packages
    python npm_analyzer.py --limit=5
    
    # Resume from logs (automatic)
    python npm_analyzer.py
    
    # Force restart from beginning
    python npm_analyzer.py --restart
"""

import time
import json
import os
import sys
import argparse
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from pathlib import Path

try:
    from codegen.agents.agent import Agent
except ImportError:
    print("❌ ERROR: codegen package not installed")
    print("   Please run: pip install codegen")
    sys.exit(1)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Codegen credentials
ORG_ID = int(os.getenv("CODEGEN_ORG_ID", "0")) if os.getenv("CODEGEN_ORG_ID") else None
API_TOKEN = os.getenv("CODEGEN_API_TOKEN")

if not API_TOKEN:
    print("❌ ERROR: CODEGEN_API_TOKEN environment variable not set")
    print("   Please set: export CODEGEN_API_TOKEN='your-token'")
    sys.exit(1)

# Target configuration
ANALYZER_REPO = "Zeeeepa/analyzer"
ANALYZER_BRANCH = "analysis"  # CRITICAL: Must be 'analysis' branch!
REPORTS_FOLDER = "npm_analysis/packages"

# Timing
WAIT_BETWEEN_RUNS = 3  # seconds

# Files
NPM_JSON_PATH = "../NPM.json"
ANALYSIS_RULES_PATH = "ANALYSIS_RULES.md"
ANALYSIS_LOGS_PATH = "analysis_logs.md"

# ============================================================================
# ANALYSIS LOGS MANAGEMENT
# ============================================================================

def init_analysis_logs(packages: List[Dict]) -> None:
    """
    Initialize or create analysis_logs.md with all packages.
    
    Args:
        packages: List of package dictionaries
    """
    logs_path = Path(ANALYSIS_LOGS_PATH)
    
    # If logs exist, don't recreate
    if logs_path.exists():
        print(f"✅ Found existing {ANALYSIS_LOGS_PATH}")
        return
    
    # Create logs directory if needed
    logs_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create initial logs file
    content = f"""# NPM Package Analysis Logs

**Repository**: {ANALYZER_REPO}
**Target Branch**: {ANALYZER_BRANCH}
**Reports Location**: {REPORTS_FOLDER}

## Analysis Status

Total Packages: {len(packages)}

### Legend
- ✓ = Agent run created successfully
- ✗ = Failed to create agent run
- ⏳ = Pending analysis

---

## Package Status

| # | Package Name | Status | Agent Run ID | Timestamp |
|---|--------------|--------|--------------|-----------|
"""
    
    # Add all packages as pending
    for idx, package in enumerate(packages, 1):
        pkg_name = package.get("name", package) if isinstance(package, dict) else package
        content += f"| {idx} | `{pkg_name}` | ⏳ | - | - |\n"
    
    content += f"""
---

**Last Updated**: {datetime.now().isoformat()}
**Status Summary**: 0 completed, 0 failed, {len(packages)} pending
"""
    
    logs_path.write_text(content, encoding='utf-8')
    print(f"✅ Created {ANALYSIS_LOGS_PATH} with {len(packages)} packages")

def read_analysis_logs() -> Tuple[Dict[str, Dict], int]:
    """
    Read analysis_logs.md and parse status.
    
    Returns:
        Tuple of (status_dict, last_completed_index)
        status_dict: {package_name: {status, run_id, timestamp}}
        last_completed_index: Index of last successfully completed package
    """
    logs_path = Path(ANALYSIS_LOGS_PATH)
    
    if not logs_path.exists():
        return {}, 0
    
    content = logs_path.read_text(encoding='utf-8')
    status_dict = {}
    last_completed_index = 0
    
    # Parse table rows
    lines = content.split('\n')
    in_table = False
    
    for line in lines:
        if line.startswith('|') and '|' in line[1:]:
            parts = [p.strip() for p in line.split('|')[1:-1]]  # Remove empty first/last
            
            if len(parts) >= 5 and parts[0].isdigit():
                index = int(parts[0])
                pkg_name = parts[1].strip('`')
                status = parts[2].strip()
                run_id = parts[3].strip()
                timestamp = parts[4].strip()
                
                status_dict[pkg_name] = {
                    'index': index,
                    'status': status,
                    'run_id': run_id if run_id != '-' else None,
                    'timestamp': timestamp if timestamp != '-' else None
                }
                
                # Track last completed
                if status == '✓' and index > last_completed_index:
                    last_completed_index = index
    
    completed = sum(1 for s in status_dict.values() if s['status'] == '✓')
    failed = sum(1 for s in status_dict.values() if s['status'] == '✗')
    
    print(f"✅ Loaded analysis logs:")
    print(f"   - Completed: {completed}")
    print(f"   - Failed: {failed}")
    print(f"   - Last completed index: {last_completed_index}")
    
    return status_dict, last_completed_index

def update_analysis_logs(package: Dict, status: str, run_id: Optional[str] = None, 
                        error: Optional[str] = None) -> None:
    """
    Update analysis_logs.md for a specific package.
    
    Args:
        package: Package dict with name and index
        status: '✓' for success, '✗' for failure
        run_id: Agent run ID if successful
        error: Error message if failed
    """
    logs_path = Path(ANALYSIS_LOGS_PATH)
    
    if not logs_path.exists():
        print(f"⚠️  Warning: {ANALYSIS_LOGS_PATH} not found, cannot update")
        return
    
    content = logs_path.read_text(encoding='utf-8')
    lines = content.split('\n')
    
    pkg_name = package.get("name", package) if isinstance(package, dict) else package
    pkg_index = package.get("index", 0)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Find and update the package line
    updated = False
    for i, line in enumerate(lines):
        if line.startswith('|') and f'`{pkg_name}`' in line:
            parts = [p.strip() for p in line.split('|')[1:-1]]
            if len(parts) >= 5:
                # Rebuild line with new status
                run_id_str = run_id if run_id else '-'
                lines[i] = f"| {parts[0]} | `{pkg_name}` | {status} | {run_id_str} | {timestamp} |"
                updated = True
                break
    
    if not updated:
        print(f"⚠️  Warning: Could not find package {pkg_name} in logs")
        return
    
    # Update summary line
    for i, line in enumerate(lines):
        if line.startswith('**Status Summary**'):
            # Count statuses
            completed = sum(1 for l in lines if '| ✓ |' in l)
            failed = sum(1 for l in lines if '| ✗ |' in l)
            pending = sum(1 for l in lines if '| ⏳ |' in l)
            lines[i] = f"**Status Summary**: {completed} completed, {failed} failed, {pending} pending"
            break
    
    # Update timestamp
    for i, line in enumerate(lines):
        if line.startswith('**Last Updated**'):
            lines[i] = f"**Last Updated**: {datetime.now().isoformat()}"
            break
    
    # Write back
    logs_path.write_text('\n'.join(lines), encoding='utf-8')

def get_pending_packages(all_packages: List[Dict], status_dict: Dict) -> List[Dict]:
    """
    Get list of packages that haven't been analyzed yet.
    
    Args:
        all_packages: Full list of packages
        status_dict: Status dictionary from logs
        
    Returns:
        List of pending packages with index
    """
    pending = []
    
    for idx, package in enumerate(all_packages, 1):
        pkg_name = package.get("name", package) if isinstance(package, dict) else package
        
        # Check if already successfully processed
        if pkg_name in status_dict:
            if status_dict[pkg_name]['status'] == '✓':
                continue  # Skip completed (but not failed - allow retry)
        
        # Add with index
        pkg_dict = package if isinstance(package, dict) else {"name": package}
        pkg_dict['index'] = idx
        pending.append(pkg_dict)
    
    return pending

# ============================================================================
# LOAD ANALYSIS RULES
# ============================================================================

def load_analysis_rules() -> str:
    """Load comprehensive analysis rules from ANALYSIS_RULES.md"""
    rules_path = Path(__file__).parent / ANALYSIS_RULES_PATH
    
    try:
        with open(rules_path, 'r', encoding='utf-8') as f:
            rules = f.read()
        print(f"✅ Loaded analysis rules from {ANALYSIS_RULES_PATH}")
        print(f"   Rules size: {len(rules)} characters")
        return rules
    except FileNotFoundError:
        print(f"❌ ERROR: ANALYSIS_RULES.md not found at {rules_path}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ ERROR: Failed to load ANALYSIS_RULES.md: {e}")
        sys.exit(1)

ANALYSIS_RULES = load_analysis_rules()

# ============================================================================
# CREATE ANALYSIS PROMPT
# ============================================================================

def create_analysis_prompt(package: Dict) -> str:
    """Create comprehensive analysis prompt with rules."""
    
    pkg_name = package.get("name", package) if isinstance(package, dict) else package
    pkg_desc = package.get("description", "") if isinstance(package, dict) else ""
    
    prompt = f"""# NPM Package Analysis Task

## Package Information
- **Package Name**: {pkg_name}
- **NPM URL**: https://www.npmjs.com/package/{pkg_name}
- **Registry URL**: https://registry.npmjs.org/{pkg_name}
"""
    
    if pkg_desc:
        prompt += f"- **Description**: {pkg_desc}\n"
    
    prompt += f"""
## Your Mission

Analyze NPM package "{pkg_name}" and create a comprehensive analysis report.

**CRITICAL INSTRUCTIONS:**
1. This is an NPM PACKAGE analysis, NOT a GitHub repository
2. You MUST save the report to the **`{ANALYZER_BRANCH}`** branch  
3. Repository: `{ANALYZER_REPO}`
4. Report path: `{REPORTS_FOLDER}/{pkg_name}_analysis.md`
5. Follow ALL analysis rules below

## Steps to Complete

### Step 1: Download Package
```bash
npm pack {pkg_name}
# OR
wget https://registry.npmjs.org/{pkg_name}/-/{pkg_name}-latest.tgz
```

### Step 2: Extract Package
```bash
tar -xzf {pkg_name}-*.tgz
cd package/
```

### Step 3: Run Repomix Analysis
```bash
npm install -g repomix
repomix --style markdown --output analysis/full-package.txt
```

### Step 4: Create Comprehensive Report

**SAVE TO:**
- Repository: `{ANALYZER_REPO}`
- Branch: **`{ANALYZER_BRANCH}`** (NOT main!)
- Path: `{REPORTS_FOLDER}/{pkg_name}_analysis.md`

---

# ANALYSIS RULES

{ANALYSIS_RULES}

---

## FINAL CHECKLIST

✅ Repository: `{ANALYZER_REPO}`
✅ Branch: **`{ANALYZER_BRANCH}`**
✅ Path: `{REPORTS_FOLDER}/{pkg_name}_analysis.md`
✅ All 11 sections present
✅ Evidence-based analysis
✅ Code examples included

BEGIN ANALYSIS NOW!
"""
    
    return prompt

# ============================================================================
# PACKAGE LOADING
# ============================================================================

def load_npm_packages(json_path: str) -> List[Dict]:
    """Load NPM packages from JSON file."""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if isinstance(data, list):
            if all(isinstance(item, str) for item in data):
                packages = [{"name": name, "description": ""} for name in data]
            elif all(isinstance(item, dict) for item in data):
                packages = data
            else:
                raise ValueError("NPM.json must contain array of strings or objects")
        elif isinstance(data, dict):
            packages = [{"name": name, "description": desc} for name, desc in data.items()]
        else:
            raise ValueError("NPM.json must contain an array or object")
        
        print(f"✅ Loaded {len(packages)} packages from {json_path}")
        return packages
    except Exception as e:
        print(f"❌ Error loading packages: {e}")
        sys.exit(1)

# ============================================================================
# AGENT RUN CREATION
# ============================================================================

def create_agent_run(package: Dict) -> Dict:
    """
    Create Codegen agent run for package analysis.
    
    Args:
        package: Package dict with name, description, index
        
    Returns:
        Result dictionary with status
    """
    pkg_name = package.get("name", package) if isinstance(package, dict) else package
    
    try:
        # Initialize agent
        agent = Agent(token=API_TOKEN, org_id=ORG_ID)
        
        # Create prompt
        prompt = create_analysis_prompt(package)
        
        # Create run
        run = agent.run(prompt=prompt)
        
        # Wait for initialization
        time.sleep(1)
        
        result = {
            "package": pkg_name,
            "run_id": run.id,
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "url": f"https://codegen.com/runs/{run.id}"
        }
        
        # Update logs immediately
        update_analysis_logs(package, '✓', run_id=run.id)
        
        return result
        
    except Exception as e:
        error_msg = str(e)
        print(f"  ❌ Error: {error_msg}")
        
        result = {
            "package": pkg_name,
            "run_id": None,
            "status": "error",
            "error": error_msg,
            "timestamp": datetime.now().isoformat()
        }
        
        # Update logs with failure
        update_analysis_logs(package, '✗', error=error_msg)
        
        return result

# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main execution function."""
    
    parser = argparse.ArgumentParser(description="NPM Package Analyzer")
    parser.add_argument("--limit", type=int, help="Limit packages to process")
    parser.add_argument("--restart", action="store_true", help="Restart from beginning (ignore logs)")
    args = parser.parse_args()
    
    print("=" * 80)
    print("NPM Package Analysis - Smart Resume with Logging")
    print("=" * 80)
    print(f"\nConfiguration:")
    print(f"  - Repository: {ANALYZER_REPO}")
    print(f"  - Target Branch: **{ANALYZER_BRANCH}** (CRITICAL!)")
    print(f"  - Reports: {REPORTS_FOLDER}")
    print(f"  - Logs: {ANALYSIS_LOGS_PATH}")
    if args.limit:
        print(f"  - Limit: {args.limit} packages")
    if args.restart:
        print(f"  - Mode: RESTART (ignoring existing logs)")
    print("=" * 80)
    
    # Load packages
    all_packages = load_npm_packages(NPM_JSON_PATH)
    
    # Initialize or read logs
    if args.restart or not Path(ANALYSIS_LOGS_PATH).exists():
        init_analysis_logs(all_packages)
        status_dict = {}
    else:
        status_dict, _ = read_analysis_logs()
    
    # Get pending packages
    pending = get_pending_packages(all_packages, status_dict)
    
    if args.limit:
        pending = pending[:args.limit]
    
    total = len(pending)
    
    if total == 0:
        print("\n✅ All packages already processed!")
        print(f"   Check logs: {ANALYSIS_LOGS_PATH}")
        print(f"   Check reports: git fetch origin {ANALYZER_BRANCH}")
        return
    
    print(f"\n🚀 Processing {total} pending packages")
    print(f"   Already completed: {len(all_packages) - len(get_pending_packages(all_packages, {}))}")
    print(f"⏱️  Estimated time: {(total * (WAIT_BETWEEN_RUNS + 2)) / 60:.1f} minutes")
    print("=" * 80)
    
    # Process packages
    success = 0
    failed = 0
    
    for idx, package in enumerate(pending, 1):
        pkg_name = package.get("name")
        pkg_index = package.get("index")
        
        print(f"\n[{pkg_index}/{len(all_packages)}] Processing: {pkg_name}")
        print(f"  NPM: https://www.npmjs.com/package/{pkg_name}")
        
        result = create_agent_run(package)
        
        if result["status"] == "success":
            success += 1
            print(f"  ✅ Run created: {result['run_id']}")
            print(f"  🔗 {result['url']}")
        else:
            failed += 1
            print(f"  ❌ Failed: {result.get('error', 'Unknown error')}")
        
        print(f"  📊 Session: {success} success, {failed} failed")
        
        if idx < total:
            print(f"  ⏳ Waiting {WAIT_BETWEEN_RUNS}s...")
            time.sleep(WAIT_BETWEEN_RUNS)
    
    # Summary
    print("\n" + "=" * 80)
    print("🎉 BATCH COMPLETE")
    print("=" * 80)
    print(f"Session processed: {total}")
    print(f"✅ Successful: {success}")
    print(f"❌ Failed: {failed}")
    if total > 0:
        print(f"Success rate: {(success/total)*100:.1f}%")
    
    print(f"\n📄 View logs: {ANALYSIS_LOGS_PATH}")
    print(f"🔍 Check reports:")
    print(f"   git fetch origin {ANALYZER_BRANCH}")
    print(f"   git checkout {ANALYZER_BRANCH}")
    print(f"   ls {REPORTS_FOLDER}/")
    print(f"\n💡 To continue: python npm_analyzer.py")
    print("=" * 80)

if __name__ == "__main__":
    main()
