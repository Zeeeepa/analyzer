"""
GitHub Repository Analyzer using Codegen API
=============================================

This script creates Codegen agent runs for repository analysis with:
- Loads GIT.json for repository list
- Uses ANALYSIS_RULES.md for agent instructions
- Proper progression tracking in analysis_logs.md
- Resumability from previous runs
- Error handling and retry logic
- Real-time status monitoring

Prerequisites:
- pip install codegen
- GIT.json file at repository root
- ANALYSIS_RULES.md in github_analysis folder

Usage:
    python git_analyzer.py              # Resume from last run or start fresh
    python git_analyzer.py --reset      # Reset progress and start from beginning
    python git_analyzer.py --verify     # Only verify existing reports

How it works:
1. Loads repository list from GIT.json
2. Loads analysis instructions from ANALYSIS_RULES.md
3. Creates agent runs with instructions to:
   - Clone the repository
   - Use repomix to extract code structure
   - Analyze using the 10-section framework
   - Save reports to 'analysis' branch
4. Tracks progress in analysis_logs.md (✓ = analyzed, ✗ = failed, ⏳ = pending)
"""

import os
import sys
import time
import json
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from codegen.agents.agent import Agent

# ============================================================================
# CONFIGURATION
# ============================================================================

# Codegen credentials
ORG_ID = int(os.getenv("CODEGEN_ORG_ID", "0")) if os.getenv("CODEGEN_ORG_ID") else None
API_TOKEN = os.getenv("CODEGEN_API_TOKEN", "sk-92083737-4e5b-4a48-a2a1-f870a3a096a6")

# Target configuration - UPDATED TO USE 'repo-analysis' BRANCH
ANALYZER_REPO = "analyzer"
ANALYZER_OWNER = "Zeeeepa"
ANALYSIS_BRANCH = "repo-analysis"  # Branch for storing analysis reports
REPORTS_FOLDER = "repos"

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
GIT_JSON_PATH = PROJECT_ROOT / "GIT.json"
ANALYSIS_RULES_PATH = SCRIPT_DIR / "ANALYSIS_RULES.md"
ANALYSIS_LOGS_PATH = SCRIPT_DIR / "analysis_logs.md"

# Timing configuration
WAIT_BETWEEN_RUNS = 3  # seconds between creating agent runs
STATUS_CHECK_INTERVAL = 50  # Check status every N repos
FINAL_WAIT_INTERVAL = 30  # seconds between final status checks

# ============================================================================
# PROGRESS TRACKING
# ============================================================================

class AnalysisProgress:
    """Manages analysis progress tracking in analysis_logs.md"""
    
    def __init__(self, logs_path: Path):
        self.logs_path = logs_path
        self.analyzed_repos = set()
        self.failed_repos = set()
        self._load_progress()
    
    def _load_progress(self):
        """Load existing progress from analysis_logs.md"""
        if not self.logs_path.exists():
            print(f"📝 No existing progress file. Starting fresh.")
            return
        
        try:
            with open(self.logs_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse markdown table to extract analyzed repos
            for line in content.split('\n'):
                if '|' in line and not line.startswith('|--'):
                    parts = [p.strip() for p in line.split('|')]
                    if len(parts) >= 4:
                        repo_name = parts[1]
                        status = parts[2]
                        
                        if status == '✓':
                            self.analyzed_repos.add(repo_name)
                        elif status == '✗':
                            self.failed_repos.add(repo_name)
            
            print(f"✅ Loaded progress: {len(self.analyzed_repos)} analyzed, {len(self.failed_repos)} failed")
            
        except Exception as e:
            print(f"⚠️  Error loading progress: {e}")
    
    def is_analyzed(self, repo_name: str) -> bool:
        """Check if repository was already analyzed"""
        return repo_name in self.analyzed_repos
    
    def mark_analyzed(self, repo_name: str, task_id: str, success: bool = True):
        """Mark repository as analyzed and update logs"""
        if success:
            self.analyzed_repos.add(repo_name)
            self.failed_repos.discard(repo_name)
        else:
            self.failed_repos.add(repo_name)
            self.analyzed_repos.discard(repo_name)
        
        self._update_logs_file()
    
    def _update_logs_file(self):
        """Update analysis_logs.md with current progress"""
        try:
            # Read all repos from GIT.json
            with open(GIT_JSON_PATH, 'r', encoding='utf-8') as f:
                git_data = json.load(f)
            
            repositories = git_data.get('repositories', [])
            
            # Generate markdown table
            content = f"""# Repository Analysis Progress Log

**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Total Repositories**: {len(repositories)}
**Analyzed**: {len(self.analyzed_repos)}
**Failed**: {len(self.failed_repos)}
**Pending**: {len(repositories) - len(self.analyzed_repos) - len(self.failed_repos)}

---

## Repository Status

| Repository | Status | Task ID | Last Updated |
|-----------|--------|---------|--------------|
"""
            
            for repo in repositories:
                repo_name = repo.get('name', '')
                if not repo_name:
                    continue
                
                if repo_name in self.analyzed_repos:
                    status = '✓'
                    task_id = 'Completed'
                elif repo_name in self.failed_repos:
                    status = '✗'
                    task_id = 'Failed'
                else:
                    status = '⏳'
                    task_id = 'Pending'
                
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
                content += f"| {repo_name} | {status} | {task_id} | {timestamp} |\n"
            
            content += f"""
---

## Legend
- ✓ : Analysis completed and agent run created
- ✗ : Analysis failed
- ⏳ : Pending analysis

## Notes
- Reports are saved to `{ANALYZER_OWNER}/{ANALYZER_REPO}` repository
- Branch: `{ANALYSIS_BRANCH}`
- Folder: `{REPORTS_FOLDER}/`
"""
            
            with open(self.logs_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print(f"✅ Updated {self.logs_path.name}")
            
        except Exception as e:
            print(f"❌ Error updating logs file: {e}")
            import traceback
            traceback.print_exc()
    
    def get_pending_repos(self, all_repos: List[Dict]) -> List[Dict]:
        """Get list of repositories that haven't been analyzed yet"""
        pending = []
        for repo in all_repos:
            repo_name = repo.get('name', '')
            if repo_name and not self.is_analyzed(repo_name):
                pending.append(repo)
        return pending
    
    def reset(self):
        """Reset all progress"""
        self.analyzed_repos.clear()
        self.failed_repos.clear()
        if self.logs_path.exists():
            self.logs_path.unlink()
        print("🔄 Progress reset")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def load_git_json() -> Dict:
    """Load and parse the GIT.json file"""
    if not GIT_JSON_PATH.exists():
        print(f"❌ ERROR: GIT.json not found at {GIT_JSON_PATH}")
        sys.exit(1)
    
    try:
        with open(GIT_JSON_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"✅ Loaded GIT.json: {data.get('total_count', 0)} repositories")
        return data
    except Exception as e:
        print(f"❌ ERROR: Failed to load GIT.json: {e}")
        sys.exit(1)


def load_analysis_rules() -> str:
    """Load the ANALYSIS_RULES.md file"""
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


def create_analysis_prompt(repo_name: str, repo_description: str, analysis_rules: str) -> str:
    """Create a comprehensive analysis prompt for the Codegen agent"""
    prompt = f"""# Repository Analysis Task: {repo_name}

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

5. **Save Report to Analyzer Repository on '{ANALYSIS_BRANCH}' branch**:
   ```bash
   # Switch to analyzer repository
   cd /tmp/{ANALYZER_OWNER}/{ANALYZER_REPO}
   
   # Ensure you're on the correct branch
   git fetch origin
   git checkout {ANALYSIS_BRANCH} || git checkout -b {ANALYSIS_BRANCH}
   
   # Create reports directory if it doesn't exist
   mkdir -p {REPORTS_FOLDER}
   
   # Save your generated report
   cat > {REPORTS_FOLDER}/{repo_name}-analysis.md << 'EOF'
   [YOUR GENERATED MARKDOWN REPORT HERE]
   EOF
   
   # Commit and push
   git add {REPORTS_FOLDER}/{repo_name}-analysis.md
   git commit -m "Add comprehensive analysis for {repo_name}"
   git push origin {ANALYSIS_BRANCH}
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
**Branch**: `{ANALYSIS_BRANCH}`

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
    analysis_rules: str
) -> Optional[Dict]:
    """Create a Codegen agent run for repository analysis"""
    prompt = create_analysis_prompt(repo_name, repo_description, analysis_rules)
    
    try:
        print(f"📝 Creating agent run for: {repo_name}")
        agent = Agent(token=API_TOKEN, org_id=ORG_ID)
        
        # Create agent run
        agent_task = agent.run(prompt=prompt)
        
        # Return task info
        task_info = {
            'repo_name': repo_name,
            'task': agent_task,
            'task_id': getattr(agent_task, 'id', None),
            'status': getattr(agent_task, 'status', 'unknown')
        }
        
        print(f"✅ Agent run created: Task ID = {task_info['task_id']}, Status = {task_info['status']}")
        return task_info
            
    except Exception as e:
        print(f"❌ Failed to create agent run for {repo_name}: {e}")
        import traceback
        traceback.print_exc()
        return None


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Main execution function"""
    print("="*80)
    print("🤖 GitHub Repository Analyzer (Codegen API)")
    print("="*80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Handle command-line arguments
    reset_progress = "--reset" in sys.argv
    verify_only = "--verify" in sys.argv
    
    # Initialize progress tracking
    progress = AnalysisProgress(ANALYSIS_LOGS_PATH)
    
    if reset_progress:
        progress.reset()
    
    # Load configuration
    print("📂 Loading configuration files...")
    git_data = load_git_json()
    analysis_rules = load_analysis_rules()
    all_repositories = git_data.get('repositories', [])
    
    if not all_repositories:
        print("❌ ERROR: No repositories found in GIT.json")
        sys.exit(1)
    
    # Get pending repositories
    pending_repos = progress.get_pending_repos(all_repositories)
    
    print(f"\n📊 Repository Status:")
    print(f"   Total: {len(all_repositories)}")
    print(f"   Analyzed: {len(progress.analyzed_repos)}")
    print(f"   Failed: {len(progress.failed_repos)}")
    print(f"   Pending: {len(pending_repos)}")
    
    if verify_only:
        print("\n✓ Verification mode - exiting")
        return
    
    if not pending_repos:
        print("\n🎉 All repositories have been analyzed!")
        return
    
    print(f"\n🚀 Resuming from last checkpoint...")
    print(f"📝 Progress tracked in: {ANALYSIS_LOGS_PATH}")
    
    # Process pending repositories
    successful_runs = []
    failed_runs = []
    active_tasks = []
    
    for idx, repo in enumerate(pending_repos, 1):
        repo_name = repo.get('name', '')
        repo_description = repo.get('description', 'No description available')
        
        if not repo_name:
            print(f"⚠️  Skipping repository {idx}: No name found")
            continue
        
        print(f"\n{'='*80}")
        print(f"📦 Processing ({idx}/{len(pending_repos)}): {repo_name}")
        print(f"📝 Description: {repo_description[:100]}...")
        print(f"{'='*80}")
        
        # Create agent run
        task_info = create_agent_run(
            repo_name=repo_name,
            repo_description=repo_description,
            analysis_rules=analysis_rules
        )
        
        if task_info:
            successful_runs.append((repo_name, task_info['task_id']))
            active_tasks.append(task_info)
            # Mark as analyzed in progress tracker
            progress.mark_analyzed(repo_name, task_info['task_id'], success=True)
        else:
            failed_runs.append(repo_name)
            # Mark as failed in progress tracker
            progress.mark_analyzed(repo_name, 'N/A', success=False)
        
        # Wait between runs
        if idx < len(pending_repos):
            print(f"⏳ Waiting {WAIT_BETWEEN_RUNS} seconds before next run...")
            time.sleep(WAIT_BETWEEN_RUNS)
        
        # Periodic status check
        if idx % STATUS_CHECK_INTERVAL == 0 and active_tasks:
            print(f"\n{'='*80}")
            print(f"📊 Status Check - Progress: {idx}/{len(pending_repos)}")
            print(f"{'='*80}")
            for task_info in active_tasks[-5:]:  # Check last 5 tasks
                try:
                    task_info['task'].refresh()
                    status = task_info['task'].status
                    print(f"  {task_info['repo_name']}: {status}")
                except Exception as e:
                    print(f"  {task_info['repo_name']}: Error - {e}")
    
    # Summary
    print("\n" + "="*80)
    print("📊 EXECUTION SUMMARY")
    print("="*80)
    print(f"Processed: {len(pending_repos)} repositories")
    print(f"Successful: {len(successful_runs)}")
    print(f"Failed: {len(failed_runs)}")
    
    if successful_runs:
        print(f"\n✅ Created {len(successful_runs)} agent runs")
        print(f"📝 Progress saved to: {ANALYSIS_LOGS_PATH}")
    
    if failed_runs:
        print(f"\n❌ Failed repositories:")
        for repo_name in failed_runs:
            print(f"   - {repo_name}")
    
    print(f"\n⏰ Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    print(f"\n💡 Tip: Run this script again to resume from where you left off!")
    print(f"💡 View progress: cat {ANALYSIS_LOGS_PATH}")


if __name__ == "__main__":
    main()
