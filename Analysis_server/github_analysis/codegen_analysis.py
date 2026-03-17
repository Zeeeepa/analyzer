"""
Batch Repository Analysis Script using Codegen API
==================================================

This script creates Codegen agent runs for multiple repositories sequentially.
Each agent run receives instructions to analyze a repository using the comprehensive
ANALYSIS_RULES.md framework and save results to the analyzer repo's github_analysis branch.

Prerequisites:
- pip install codegen
- GIT.json file at repository root
- ANALYSIS_RULES.md in github_analysis folder
- npm install -g repomix (for repository packing)

Usage:
    python codegen_analysis.py
"""

import os
import sys
import time
import json
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path
from codegen.agents.agent import Agent

# ============================================================================
# CONFIGURATION
# ============================================================================

# Codegen credentials - set via environment variables or update here
ORG_ID = int(os.getenv("CODEGEN_ORG_ID", "0")) if os.getenv("CODEGEN_ORG_ID") else None
API_TOKEN = os.getenv("CODEGEN_API_TOKEN", "sk-92083737-4e5b-4a48-a2a1-f870a3a096a6")

# Target location for analysis reports (instructions for the agent)
ANALYZER_REPO = "analyzer"
ANALYZER_OWNER = "Zeeeepa"
ANALYZER_BRANCH = "github_analysis"
REPORTS_FOLDER = "repos"

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
GIT_JSON_PATH = PROJECT_ROOT / "GIT.json"
ANALYSIS_RULES_PATH = SCRIPT_DIR / "ANALYSIS_RULES.md"

# Timing configuration
WAIT_BETWEEN_RUNS = 3  # seconds between creating agent runs
AGENT_TIMEOUT = 600  # 10 minutes per repository analysis

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def load_git_json() -> Dict:
    """
    Load and parse the GIT.json file from repository root.
    
    Returns:
        Dict containing repository metadata
    """
    if not GIT_JSON_PATH.exists():
        print(f"❌ ERROR: GIT.json not found at {GIT_JSON_PATH}")
        sys.exit(1)
    
    try:
        with open(GIT_JSON_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"✅ Loaded GIT.json: {data.get('total_count', 0)} repositories")
        return data
    except json.JSONDecodeError as e:
        print(f"❌ ERROR: Failed to parse GIT.json: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ ERROR: Failed to load GIT.json: {e}")
        sys.exit(1)


def load_analysis_rules() -> str:
    """
    Load the ANALYSIS_RULES.md file containing comprehensive analysis instructions.
    
    Returns:
        String containing the markdown content
    """
    if not ANALYSIS_RULES_PATH.exists():
        print(f"❌ ERROR: ANALYSIS_RULES.md not found at {ANALYSIS_RULES_PATH}")
        sys.exit(1)
    
    try:
        with open(ANALYSIS_RULES_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
        print(f"✅ Loaded ANALYSIS_RULES.md ({len(content)} characters)")
        return content
    except Exception as e:
        print(f"❌ ERROR: Failed to load ANALYSIS_RULES.md: {e}")
        sys.exit(1)


def extract_repositories(git_data: Dict) -> List[Dict[str, str]]:
    """
    Extract repository names and descriptions from GIT.json.
    
    Args:
        git_data: Parsed GIT.json data
        
    Returns:
        List of dicts with 'name' and 'description' keys
    """
    repositories = git_data.get('repositories', [])
    if not repositories:
        print("❌ ERROR: No repositories found in GIT.json")
        sys.exit(1)
    
    return repositories


def create_analysis_prompt(repo_name: str, repo_description: str, analysis_rules: str) -> str:
    """
    Create a comprehensive analysis prompt for the Codegen agent.
    
    Args:
        repo_name: Name of the repository to analyze
        repo_description: Description from GIT.json
        analysis_rules: Content from ANALYSIS_RULES.md
        
    Returns:
        Formatted prompt string
    """
    prompt = f"""
# Repository Analysis Task: {repo_name}

You are a senior software architect tasked with conducting a comprehensive analysis of the GitHub repository: **{ANALYZER_OWNER}/{repo_name}**

## Repository Information
- **Name**: {repo_name}
- **Description**: {repo_description}
- **Owner**: {ANALYZER_OWNER}

## Your Mission

Analyze this repository following the **COMPREHENSIVE ANALYSIS RULES** provided below, and generate a detailed markdown report.

---

{analysis_rules}

---

## Specific Instructions for This Analysis

1. **Clone and Analyze**:
   ```bash
   git clone https://github.com/{ANALYZER_OWNER}/{repo_name}.git /tmp/{repo_name}
   cd /tmp/{repo_name}
   ```

2. **Use Repomix** (if available and helpful):
   ```bash
   # Install if needed: npm install -g repomix
   repomix --style markdown --output /tmp/{repo_name}-analysis.txt
   ```
   Note: If repomix is not available, analyze the repository using file reading tools.

3. **Follow the 10-Section Framework**:
   - Repository Overview
   - Architecture & Design Patterns
   - Core Features & Functionalities
   - Entry Points & Initialization
   - Data Flow Architecture
   - CI/CD Pipeline Assessment
   - Dependencies & Technology Stack
   - Security Assessment
   - Performance & Scalability
   - Documentation Quality

4. **Generate Evidence-Based Report**:
   - Include code snippets as evidence
   - Reference specific files
   - Provide quantitative metrics where possible
   - Be honest about limitations or missing information

5. **Save Report to Analyzer Repository**:
   ```bash
   # Switch to analyzer repository
   cd /tmp/{ANALYZER_OWNER}/{ANALYZER_REPO}
   
   # Ensure you're on the correct branch
   git fetch origin
   git checkout {ANALYZER_BRANCH} || git checkout -b {ANALYZER_BRANCH}
   
   # Create reports directory if it doesn't exist
   mkdir -p {REPORTS_FOLDER}
   
   # Save your generated report
   cat > {REPORTS_FOLDER}/{repo_name}-analysis.md << 'EOF'
   [YOUR GENERATED MARKDOWN REPORT HERE]
   EOF
   
   # Commit and push
   git add {REPORTS_FOLDER}/{repo_name}-analysis.md
   git commit -m "Add comprehensive analysis for {repo_name}"
   git push origin {ANALYZER_BRANCH}
   ```

## Quality Requirements

✅ **Required**:
- All 10 analysis sections must be present
- Include at least 3-5 code snippets as evidence
- Provide clear CI/CD suitability assessment (score 1-10)
- List all major dependencies with versions
- Include actionable recommendations (minimum 3)

❌ **Avoid**:
- Speculation without evidence
- Generic statements without specifics
- Skipping sections due to lack of information (state "Not Available" instead)
- Formatting errors in markdown

## Expected Output Location

**File**: `{ANALYZER_OWNER}/{ANALYZER_REPO}/{REPORTS_FOLDER}/{repo_name}-analysis.md`
**Branch**: `{ANALYZER_BRANCH}`

## Success Criteria

✅ Report file created and pushed to GitHub
✅ All 10 sections completed
✅ Evidence-based analysis with code examples
✅ Professional markdown formatting
✅ Actionable recommendations provided

---

**Begin your analysis now. Good luck! 🚀**
"""
    return prompt


def create_agent_run(
    repo_name: str,
    repo_description: str,
    analysis_rules: str,
    dry_run: bool = False
) -> Optional[str]:
    """
    Create a Codegen agent run for a specific repository analysis.
    
    Args:
        repo_name: Repository name
        repo_description: Repository description
        analysis_rules: Analysis rules markdown content
        dry_run: If True, print prompt without creating agent run
        
    Returns:
        Agent run ID if successful, None otherwise
    """
    prompt = create_analysis_prompt(repo_name, repo_description, analysis_rules)
    
    if dry_run:
        print("\n" + "="*80)
        print(f"DRY RUN - Prompt for {repo_name}")
        print("="*80)
        print(prompt[:500] + "...\n[truncated]")
        return None
    
    try:
        print(f"📝 Creating agent run for: {repo_name}")
        agent = Agent(token=API_TOKEN, org_id=ORG_ID)
        
        # Create agent run with comprehensive prompt
        agent_task = agent.run(prompt=prompt)
        
        # Get task/run information
        if hasattr(agent_task, 'id'):
            run_id = agent_task.id
            print(f"✅ Agent run created: {run_id}")
            return run_id
        elif hasattr(agent_task, '__dict__'):
            print(f"✅ Agent task created: {agent_task.__dict__}")
            return str(agent_task)
        else:
            print(f"⚠️  Agent run created but format unknown: {agent_task}")
            return str(agent_task)
            
    except Exception as e:
        print(f"❌ Failed to create agent run for {repo_name}: {e}")
        return None


def verify_report_exists(repo_name: str) -> bool:
    """
    Verify that a report file exists for the given repository.
    
    Args:
        repo_name: Repository name
        
    Returns:
        True if report exists, False otherwise
    """
    report_path = PROJECT_ROOT / REPORTS_FOLDER / f"{repo_name}-analysis.md"
    exists = report_path.exists()
    
    if exists:
        print(f"✅ Report verified: {repo_name}")
    else:
        print(f"❌ Report missing: {repo_name}")
    
    return exists


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """
    Main execution function.
    """
    print("="*80)
    print("🤖 Codegen Repository Analysis Automation")
    print("="*80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Load configuration
    print("📂 Loading configuration files...")
    git_data = load_git_json()
    analysis_rules = load_analysis_rules()
    repositories = extract_repositories(git_data)
    
    total_repos = len(repositories)
    print(f"\n📊 Found {total_repos} repositories to analyze\n")
    
    # Optional: Dry run mode for testing
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("⚠️  DRY RUN MODE - No agent runs will be created\n")
    
    # Optional: Limit number of repos for testing
    limit = None
    for arg in sys.argv:
        if arg.startswith("--limit="):
            limit = int(arg.split("=")[1])
            print(f"⚠️  LIMIT MODE - Processing only {limit} repositories\n")
    
    if limit:
        repositories = repositories[:limit]
    
    # Process each repository
    successful_runs = []
    failed_runs = []
    
    for idx, repo in enumerate(repositories, 1):
        repo_name = repo.get('name', '')
        repo_description = repo.get('description', 'No description available')
        
        if not repo_name:
            print(f"⚠️  Skipping repository {idx}: No name found")
            continue
        
        print(f"\n{'='*80}")
        print(f"📦 Processing ({idx}/{total_repos}): {repo_name}")
        print(f"📝 Description: {repo_description[:100]}...")
        print(f"{'='*80}")
        
        # Create agent run
        run_id = create_agent_run(
            repo_name=repo_name,
            repo_description=repo_description,
            analysis_rules=analysis_rules,
            dry_run=dry_run
        )
        
        if run_id:
            successful_runs.append((repo_name, run_id))
        else:
            failed_runs.append(repo_name)
        
        # Wait between runs to avoid rate limiting
        if idx < total_repos and not dry_run:
            print(f"⏳ Waiting {WAIT_BETWEEN_RUNS} seconds before next run...")
            time.sleep(WAIT_BETWEEN_RUNS)
    
    # Summary
    print("\n" + "="*80)
    print("📊 EXECUTION SUMMARY")
    print("="*80)
    print(f"Total Repositories: {total_repos}")
    print(f"Successful Runs: {len(successful_runs)}")
    print(f"Failed Runs: {len(failed_runs)}")
    
    if successful_runs:
        print("\n✅ Successful Agent Runs:")
        for repo_name, run_id in successful_runs:
            print(f"   - {repo_name}: {run_id}")
    
    if failed_runs:
        print("\n❌ Failed Agent Runs:")
        for repo_name in failed_runs:
            print(f"   - {repo_name}")
    
    print(f"\n⏰ Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    # Optional: Verify reports after completion
    if "--verify" in sys.argv and not dry_run:
        print("\n🔍 Verifying report creation...")
        time.sleep(60)  # Wait for agents to complete
        
        verified_count = 0
        for repo_name, _ in successful_runs:
            if verify_report_exists(repo_name):
                verified_count += 1
        
        print(f"\n📊 Verification Results: {verified_count}/{len(successful_runs)} reports found")


if __name__ == "__main__":
    main()
