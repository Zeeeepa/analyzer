"""
NPM Package Analysis Script using Codegen API
==============================================

This script creates Codegen agent runs for multiple NPM packages sequentially.
Each agent run receives instructions to:
1. Download the package compressed from npmjs.com
2. Extract the package
3. Run repomix on the package
4. Analyze its structure
5. Create a report in analyzer project npm_analysis/packages/<packagename>_analysis.md

Prerequisites:
- pip install codegen

Usage:
    python npm_analyzer.py
"""

import time
import json
import os
from datetime import datetime
from typing import List, Dict
from codegen.agents.agent import Agent

# ============================================================================
# CONFIGURATION
# ============================================================================

# Codegen credentials - MUST be set via environment variables for security
ORG_ID = int(os.getenv("CODEGEN_ORG_ID", "0")) if os.getenv("CODEGEN_ORG_ID") else None
API_TOKEN = os.getenv("CODEGEN_API_TOKEN")

if not API_TOKEN:
    print("❌ ERROR: CODEGEN_API_TOKEN environment variable not set")
    print("   Please set: export CODEGEN_API_TOKEN='your-token'")
    import sys
    sys.exit(1)

# Target location for analysis reports
ANALYZER_REPO = "analyzer"
ANALYZER_BRANCH = "npm_analysis"
REPORTS_FOLDER = "npm_analysis/packages"

# Timing configuration
WAIT_BETWEEN_RUNS = 2  # seconds between creating agent runs

# Path to NPM package list
NPM_JSON_PATH = "../NPM.json"

# ============================================================================
# ANALYSIS INSTRUCTIONS TEMPLATE
# ============================================================================

ANALYSIS_INSTRUCTIONS = """
Please analyze the NPM package "{package_name}" following these steps:

**IMPORTANT: You are analyzing an NPM package, not a GitHub repository!**

## Analysis Steps:

1. **Download Package**
   - Visit https://www.npmjs.com/package/{package_name}
   - Download the compressed package (tarball) using npm pack or direct registry URL
   - URL format: https://registry.npmjs.org/{package_name}/-/{package_name}-latest.tgz

2. **Extract Package**
   - Extract the downloaded tarball to a working directory
   - The package contents are typically in a 'package/' subfolder

3. **Run Repomix Analysis**
   - Install repomix if not available: `npm install -g repomix`
   - Run repomix on the extracted package directory
   - Generate a comprehensive structure analysis

4. **Create Analysis Report**
   - Analyze the package structure, dependencies, and code patterns
   - Create a detailed markdown report at:
     `{analyzer_repo}/npm_analysis/packages/{package_name}_analysis.md`
   - Commit changes to the `{branch}` branch
   
## Report Structure:

The analysis report should include:
- Package overview (name, version, description, author)
- Package.json analysis (dependencies, scripts, configuration)
- Directory structure
- Key files and their purposes
- Code architecture and patterns
- Entry points and exports
- Dependencies analysis
- Notable features or patterns
- Security considerations
- Repomix output summary

## Important Notes:
- This is an NPM package analysis, not a GitHub repo
- Focus on the published package structure
- Include package.json details
- Analyze the built/published code, not source repository
- Save the report to: `{analyzer_repo}/npm_analysis/packages/{package_name}_analysis.md`
- Commit to branch: `{branch}`

Package: {package_name}
NPM URL: https://www.npmjs.com/package/{package_name}
Registry URL: https://registry.npmjs.org/{package_name}

Begin analysis now!
"""

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def load_npm_packages(json_path: str) -> List[str]:
    """
    Load NPM package names from JSON file.
    
    Args:
        json_path: Path to NPM.json file
        
    Returns:
        List of package names
    """
    try:
        with open(json_path, 'r') as f:
            packages = json.load(f)
        
        if not isinstance(packages, list):
            raise ValueError("NPM.json must contain an array of package names")
        
        print(f"✅ Loaded {len(packages)} NPM packages from {json_path}")
        return packages
    except FileNotFoundError:
        print(f"❌ Error: NPM.json not found at {json_path}")
        print(f"   Current directory: {os.getcwd()}")
        print(f"   Please ensure NPM.json exists in the repository root")
        raise
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in {json_path}")
        print(f"   {str(e)}")
        raise

def create_agent_run(package_name: str) -> Dict:
    """
    Create a Codegen agent run for analyzing an NPM package.
    
    Args:
        package_name: Name of the NPM package to analyze
        
    Returns:
        Dictionary containing run information
    """
    try:
        # Initialize agent
        agent = Agent(token=API_TOKEN, org_id=ORG_ID)
        
        # Format instructions with package details
        instructions = ANALYSIS_INSTRUCTIONS.format(
            package_name=package_name,
            analyzer_repo=ANALYZER_REPO,
            branch=ANALYZER_BRANCH
        )
        
        # Create agent run
        run = agent.create_run(
            message=instructions,
            repo=ANALYZER_REPO
        )
        
        return {
            "package": package_name,
            "run_id": run.id,
            "status": "created",
            "timestamp": datetime.now().isoformat(),
            "url": f"https://codegen.com/runs/{run.id}"
        }
        
    except Exception as e:
        return {
            "package": package_name,
            "run_id": None,
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """
    Main execution function - processes all NPM packages sequentially.
    """
    print("=" * 80)
    print("NPM Package Analysis - Batch Processing")
    print("=" * 80)
    print(f"\nConfiguration:")
    print(f"  - Organization ID: {ORG_ID}")
    print(f"  - Target Repo: {ANALYZER_REPO}")
    print(f"  - Target Branch: {ANALYZER_BRANCH}")
    print(f"  - Reports Folder: {REPORTS_FOLDER}")
    print(f"  - Wait Between Runs: {WAIT_BETWEEN_RUNS}s")
    print(f"  - NPM JSON Path: {NPM_JSON_PATH}")
    print("=" * 80)
    
    # Load NPM packages
    try:
        packages = load_npm_packages(NPM_JSON_PATH)
    except Exception as e:
        print(f"\n❌ Failed to load NPM packages: {e}")
        return
    
    # Statistics
    total_packages = len(packages)
    successful_runs = 0
    failed_runs = 0
    results = []
    
    print(f"\n🚀 Starting analysis for {total_packages} NPM packages...")
    print(f"⏱️  Estimated time: {(total_packages * WAIT_BETWEEN_RUNS) / 60:.1f} minutes")
    print("=" * 80)
    
    # Process each package
    for idx, package_name in enumerate(packages, 1):
        print(f"\n[{idx}/{total_packages}] Processing: {package_name}")
        print(f"  NPM URL: https://www.npmjs.com/package/{package_name}")
        
        # Create agent run
        result = create_agent_run(package_name)
        results.append(result)
        
        # Update statistics
        if result["status"] == "created":
            successful_runs += 1
            print(f"  ✅ Agent run created: {result['run_id']}")
            print(f"  🔗 View at: {result['url']}")
        else:
            failed_runs += 1
            print(f"  ❌ Failed: {result.get('error', 'Unknown error')}")
        
        # Progress update
        print(f"  📊 Progress: {successful_runs} successful, {failed_runs} failed")
        
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
    print(f"Success rate: {(successful_runs/total_packages)*100:.1f}%")
    
    # Save results to JSON
    results_file = f"npm_analysis_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(results_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "total_packages": total_packages,
            "successful_runs": successful_runs,
            "failed_runs": failed_runs,
            "results": results
        }, f, indent=2)
    
    print(f"\n📄 Results saved to: {results_file}")
    print("\n✨ All agent runs have been created!")
    print("   Monitor progress at: https://codegen.com/runs")
    print("=" * 80)

if __name__ == "__main__":
    main()
