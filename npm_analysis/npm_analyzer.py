"""
NPM Package Analysis Script using Codegen API
==============================================

This script creates Codegen agent runs for multiple NPM packages sequentially.
Each agent run receives instructions loaded from ANALYSIS_RULES.md to:
1. Download the package compressed from npmjs.com
2. Extract the package
3. Run repomix on the package
4. Analyze its structure following comprehensive rules
5. Create a report in analyzer project npm_analysis/packages/<packagename>_analysis.md
6. Save to the 'analysis' branch (CRITICAL!)

Prerequisites:
- pip install codegen

Usage:
    # Full run
    python npm_analyzer.py
    
    # Test with first 5 packages
    python npm_analyzer.py --limit=5
    
    # Resume from a specific package
    python npm_analyzer.py --resume=50
    
    # Dry run (no actual API calls)
    python npm_analyzer.py --dry-run
"""

import time
import json
import os
import sys
import argparse
from datetime import datetime
from typing import List, Dict, Optional
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

# Codegen credentials - MUST be set via environment variables for security
ORG_ID = int(os.getenv("CODEGEN_ORG_ID", "0")) if os.getenv("CODEGEN_ORG_ID") else None
API_TOKEN = os.getenv("CODEGEN_API_TOKEN")

if not API_TOKEN:
    print("❌ ERROR: CODEGEN_API_TOKEN environment variable not set")
    print("   Please set: export CODEGEN_API_TOKEN='your-token'")
    sys.exit(1)

# Target location for analysis reports - CRITICAL: Use 'analysis' branch!
ANALYZER_REPO = "Zeeeepa/analyzer"
ANALYZER_BRANCH = "analysis"  # NOT npm_analysis, NOT main!
REPORTS_FOLDER = "npm_analysis/packages"

# Timing configuration
WAIT_BETWEEN_RUNS = 3  # seconds between creating agent runs

# Path to NPM package list and analysis rules
NPM_JSON_PATH = "../NPM.json"
ANALYSIS_RULES_PATH = "ANALYSIS_RULES.md"

# Progress file to resume from failures
PROGRESS_FILE = "npm_analysis_progress.json"

# ============================================================================
# LOAD ANALYSIS RULES FROM FILE
# ============================================================================

def load_analysis_rules() -> str:
    """
    Load comprehensive analysis rules from ANALYSIS_RULES.md
    
    Returns:
        Analysis rules content as string
    """
    rules_path = Path(__file__).parent / ANALYSIS_RULES_PATH
    
    try:
        with open(rules_path, 'r', encoding='utf-8') as f:
            rules = f.read()
        print(f"✅ Loaded analysis rules from {ANALYSIS_RULES_PATH}")
        print(f"   Rules size: {len(rules)} characters")
        return rules
    except FileNotFoundError:
        print(f"❌ ERROR: ANALYSIS_RULES.md not found at {rules_path}")
        print("   Please ensure ANALYSIS_RULES.md exists in npm_analysis/ directory")
        sys.exit(1)
    except Exception as e:
        print(f"❌ ERROR: Failed to load ANALYSIS_RULES.md: {e}")
        sys.exit(1)

# Load rules at module level
ANALYSIS_RULES = load_analysis_rules()

# ============================================================================
# ANALYSIS INSTRUCTIONS TEMPLATE
# ============================================================================

def create_analysis_prompt(package_name: str, package_description: str = "") -> str:
    """
    Create comprehensive analysis prompt using ANALYSIS_RULES.md
    
    Args:
        package_name: Name of NPM package
        package_description: Description from NPM.json (optional)
        
    Returns:
        Formatted prompt with rules and package details
    """
    
    prompt = f"""# NPM Package Analysis Task

## Package Information
- **Package Name**: {package_name}
- **NPM URL**: https://www.npmjs.com/package/{package_name}
- **Registry URL**: https://registry.npmjs.org/{package_name}
"""
    
    if package_description:
        prompt += f"- **Description**: {package_description}\n"
    
    prompt += f"""
## Your Mission

You are analyzing the NPM package "{package_name}" and creating a comprehensive analysis report.

**CRITICAL INSTRUCTIONS:**
1. This is an NPM PACKAGE analysis, NOT a GitHub repository
2. You MUST save the report to the **`{ANALYZER_BRANCH}`** branch
3. Report location: `{ANALYZER_REPO}/{REPORTS_FOLDER}/{package_name}_analysis.md`
4. Follow ALL analysis rules provided below

## Analysis Steps

### Step 1: Download Package
```bash
# Download from NPM registry
npm pack {package_name}
# OR use direct registry URL
wget https://registry.npmjs.org/{package_name}/-/{package_name}-latest.tgz
```

### Step 2: Extract Package
```bash
tar -xzf {package_name}-*.tgz
cd package/
```

### Step 3: Run Repomix Analysis
```bash
# Install if needed
npm install -g repomix

# Run comprehensive analysis
repomix --style markdown --output analysis/full-package.txt

# Targeted analyses (as per rules)
repomix --include "src/**,lib/**,index.js,*.ts" --output analysis/src-only.txt
repomix --include "package.json,tsconfig.json,*.config.js" --output analysis/configs.txt
```

### Step 4: Create Comprehensive Report

**REPORT LOCATION (CRITICAL!):**
- Repository: `{ANALYZER_REPO}`
- Branch: `{ANALYZER_BRANCH}` (NOT main, NOT npm_analysis!)
- File: `{REPORTS_FOLDER}/{package_name}_analysis.md`

Use the analysis rules below to create a thorough, evidence-based report.

---

# COMPREHENSIVE ANALYSIS RULES

{ANALYSIS_RULES}

---

## FINAL CHECKLIST BEFORE SAVING

Before you commit the report, verify:

✅ Report saved to repository: `{ANALYZER_REPO}`
✅ Report saved to branch: `{ANALYZER_BRANCH}` (CRITICAL!)
✅ Report location: `{REPORTS_FOLDER}/{package_name}_analysis.md`
✅ All 11 sections present
✅ Entry points analyzed (Section 5)
✅ Functionality documented (Section 6)
✅ Code examples included
✅ Evidence-based (not speculative)
✅ Proper markdown formatting

## BEGIN ANALYSIS NOW

Package: **{package_name}**
Target Branch: **{ANALYZER_BRANCH}**
Report Path: **{REPORTS_FOLDER}/{package_name}_analysis.md**

Start your comprehensive analysis following the rules above!
"""
    
    return prompt

# ============================================================================
# PROGRESS TRACKING
# ============================================================================

def load_progress() -> Dict:
    """Load progress from file if it exists."""
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r') as f:
                progress = json.load(f)
            print(f"✅ Loaded progress from {PROGRESS_FILE}")
            print(f"   Last processed: {progress.get('last_processed_index', 0)} packages")
            return progress
        except Exception as e:
            print(f"⚠️  Warning: Could not load progress file: {e}")
            return {"results": [], "last_processed_index": 0}
    return {"results": [], "last_processed_index": 0}

def save_progress(progress: Dict):
    """Save progress to file."""
    try:
        with open(PROGRESS_FILE, 'w') as f:
            json.dump(progress, f, indent=2)
    except Exception as e:
        print(f"⚠️  Warning: Could not save progress: {e}")

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def load_npm_packages(json_path: str) -> List[Dict[str, str]]:
    """
    Load NPM package names and descriptions from JSON file.
    
    Args:
        json_path: Path to NPM.json file
        
    Returns:
        List of package dictionaries with 'name' and optional 'description'
    """
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Handle different formats
        if isinstance(data, list):
            # If list of strings, convert to dict format
            if all(isinstance(item, str) for item in data):
                packages = [{"name": name, "description": ""} for name in data]
            # If list of dicts, use as is
            elif all(isinstance(item, dict) for item in data):
                packages = data
            else:
                raise ValueError("NPM.json must contain array of strings or objects")
        elif isinstance(data, dict):
            # If dict, convert to list of dicts
            packages = [{"name": name, "description": desc} for name, desc in data.items()]
        else:
            raise ValueError("NPM.json must contain an array or object")
        
        print(f"✅ Loaded {len(packages)} NPM packages from {json_path}")
        return packages
    except FileNotFoundError:
        print(f"❌ Error: NPM.json not found at {json_path}")
        print(f"   Current directory: {os.getcwd()}")
        print(f"   Please ensure NPM.json exists in the repository root")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in {json_path}")
        print(f"   {str(e)}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error loading NPM packages: {e}")
        sys.exit(1)

def create_agent_run(package: Dict[str, str], dry_run: bool = False) -> Dict:
    """
    Create a Codegen agent run for analyzing an NPM package.
    
    Args:
        package: Dictionary with 'name' and optional 'description'
        dry_run: If True, don't actually create the run
        
    Returns:
        Dictionary containing run information
    """
    package_name = package.get("name", package) if isinstance(package, dict) else package
    package_desc = package.get("description", "") if isinstance(package, dict) else ""
    
    try:
        if dry_run:
            print(f"  🔍 DRY RUN: Would create agent run for {package_name}")
            return {
                "package": package_name,
                "run_id": "dry_run",
                "status": "dry_run",
                "timestamp": datetime.now().isoformat(),
                "url": "https://codegen.com/runs/dry_run"
            }
        
        # Initialize agent
        agent = Agent(token=API_TOKEN, org_id=ORG_ID)
        
        # Create comprehensive prompt with rules
        prompt = create_analysis_prompt(package_name, package_desc)
        
        # Create agent run
        run = agent.run(prompt=prompt)
        
        # Wait a moment for run to initialize
        time.sleep(1)
        
        result = {
            "package": package_name,
            "run_id": run.id,
            "status": "created",
            "timestamp": datetime.now().isoformat(),
            "url": f"https://codegen.com/runs/{run.id}",
            "description": package_desc
        }
        
        return result
        
    except Exception as e:
        error_msg = str(e)
        print(f"  ❌ Error details: {error_msg}")
        
        return {
            "package": package_name,
            "run_id": None,
            "status": "error",
            "error": error_msg,
            "timestamp": datetime.now().isoformat(),
            "description": package_desc
        }

# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """
    Main execution function - processes all NPM packages sequentially.
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="NPM Package Analysis Batch Processor")
    parser.add_argument("--limit", type=int, help="Limit number of packages to process")
    parser.add_argument("--resume", type=int, help="Resume from package index (0-based)")
    parser.add_argument("--dry-run", action="store_true", help="Dry run - don't create actual runs")
    parser.add_argument("--verify", action="store_true", help="Verify existing runs")
    args = parser.parse_args()
    
    print("=" * 80)
    print("NPM Package Analysis - Batch Processing with Comprehensive Rules")
    print("=" * 80)
    print(f"\nConfiguration:")
    print(f"  - Organization ID: {ORG_ID}")
    print(f"  - Target Repo: {ANALYZER_REPO}")
    print(f"  - Target Branch: {ANALYZER_BRANCH} (CRITICAL!)")
    print(f"  - Reports Folder: {REPORTS_FOLDER}")
    print(f"  - Wait Between Runs: {WAIT_BETWEEN_RUNS}s")
    print(f"  - NPM JSON Path: {NPM_JSON_PATH}")
    print(f"  - Analysis Rules: {ANALYSIS_RULES_PATH}")
    if args.dry_run:
        print(f"  - Mode: DRY RUN (no actual API calls)")
    if args.limit:
        print(f"  - Limit: {args.limit} packages")
    if args.resume is not None:
        print(f"  - Resume from: index {args.resume}")
    print("=" * 80)
    
    # Load NPM packages
    all_packages = load_npm_packages(NPM_JSON_PATH)
    
    # Load progress
    progress = load_progress()
    
    # Determine starting point
    start_index = args.resume if args.resume is not None else progress.get("last_processed_index", 0)
    
    # Determine packages to process
    if args.limit:
        packages_to_process = all_packages[start_index:start_index + args.limit]
    else:
        packages_to_process = all_packages[start_index:]
    
    total_packages = len(packages_to_process)
    
    if total_packages == 0:
        print("\n✅ All packages already processed!")
        return
    
    # Statistics
    successful_runs = 0
    failed_runs = 0
    results = progress.get("results", [])
    
    print(f"\n🚀 Starting analysis for {total_packages} NPM packages...")
    print(f"   Starting from index: {start_index}")
    print(f"   Total in NPM.json: {len(all_packages)}")
    print(f"⏱️  Estimated time: {(total_packages * (WAIT_BETWEEN_RUNS + 2)) / 60:.1f} minutes")
    print("=" * 80)
    
    # Process each package
    for idx, package in enumerate(packages_to_process, start=1):
        global_idx = start_index + idx
        package_name = package.get("name", package) if isinstance(package, dict) else package
        
        print(f"\n[{global_idx}/{len(all_packages)}] Processing: {package_name}")
        print(f"  NPM URL: https://www.npmjs.com/package/{package_name}")
        
        # Create agent run
        result = create_agent_run(package, dry_run=args.dry_run)
        results.append(result)
        
        # Update statistics
        if result["status"] in ["created", "dry_run"]:
            successful_runs += 1
            print(f"  ✅ Agent run created: {result['run_id']}")
            print(f"  🔗 View at: {result['url']}")
        else:
            failed_runs += 1
            print(f"  ❌ Failed: {result.get('error', 'Unknown error')}")
        
        # Progress update
        print(f"  📊 Progress: {successful_runs} successful, {failed_runs} failed")
        
        # Save progress after each package
        progress["results"] = results
        progress["last_processed_index"] = global_idx
        progress["timestamp"] = datetime.now().isoformat()
        save_progress(progress)
        
        # Wait before next run (except for the last one)
        if idx < total_packages:
            print(f"  ⏳ Waiting {WAIT_BETWEEN_RUNS}s before next run...")
            time.sleep(WAIT_BETWEEN_RUNS)
    
    # Final summary
    print("\n" + "=" * 80)
    print("🎉 BATCH PROCESSING COMPLETE")
    print("=" * 80)
    print(f"Total packages processed: {total_packages}")
    print(f"✅ Successful runs: {successful_runs}")
    print(f"❌ Failed runs: {failed_runs}")
    if total_packages > 0:
        print(f"Success rate: {(successful_runs/total_packages)*100:.1f}%")
    
    # Save final results
    results_file = f"npm_analysis_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(results_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "total_packages": len(all_packages),
            "processed_packages": total_packages,
            "successful_runs": successful_runs,
            "failed_runs": failed_runs,
            "results": results,
            "target_branch": ANALYZER_BRANCH,
            "target_repo": ANALYZER_REPO
        }, f, indent=2)
    
    print(f"\n📄 Results saved to: {results_file}")
    print(f"📄 Progress saved to: {PROGRESS_FILE}")
    print("\n✨ All agent runs have been created!")
    print(f"   Monitor progress at: https://codegen.com/runs")
    print(f"   Reports will be saved to branch: {ANALYZER_BRANCH}")
    print(f"   Reports location: {ANALYZER_REPO}/{REPORTS_FOLDER}/")
    print("=" * 80)
    
    print("\n🔍 NEXT STEPS:")
    print(f"1. Monitor agent runs at https://codegen.com/runs")
    print(f"2. Check branch '{ANALYZER_BRANCH}' for created reports")
    print(f"3. Verify reports in {REPORTS_FOLDER}/ directory")
    print(f"4. Run 'git fetch origin {ANALYZER_BRANCH}' to see results")

if __name__ == "__main__":
    main()

