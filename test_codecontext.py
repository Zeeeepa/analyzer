import sys
sys.path.insert(0, 'scripts/git')
from CodeContext import CodeAnalyzer, load_repo_list

# Load first 5 repos
repos = load_repo_list("DATA/GIT/index_test.csv")
print(f"Testing with {len(repos)} repositories\n")

# Analyze
analyzer = CodeAnalyzer()
analyzer.analyze_repositories(repos, "DATA/GIT/code_context_test.csv")
