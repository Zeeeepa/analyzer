import requests
import json
import base64
from datetime import datetime

# Configuration
GITHUB_TOKEN = "
USERNAME = "zeeeepa"
TARGET_REPO = "analyzer"
FILE_PATH = "GIT.json"
BRANCH = "main"

headers = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

def fetch_all_repos(username):
    """Fetch all repositories for a given GitHub username"""
    repos = []
    page = 1
    per_page = 100  # Maximum allowed by GitHub API
    
    print(f"Fetching repositories for user: {username}")
    
    while True:
        url = f"https://api.github.com/users/{username}/repos"
        params = {
            "per_page": per_page,
            "page": page,
            "type": "all",
            "sort": "updated"
        }
        
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code != 200:
            print(f"Error fetching repos: {response.status_code}")
            print(response.json())
            break
        
        page_repos = response.json()
        
        if not page_repos:
            break
        
        repos.extend(page_repos)
        print(f"Fetched page {page}: {len(page_repos)} repos (Total: {len(repos)})")
        page += 1
    
    return repos

def format_repo_data(repos):
    """Format repository data as name-description pairs"""
    formatted_repos = []
    
    for repo in repos:
        formatted_repos.append({
            "name": repo["name"],
            "description": repo["description"] if repo["description"] else ""
        })
    
    return formatted_repos

def get_file_sha(owner, repo, path, branch):
    """Get the SHA of an existing file (needed for updates)"""
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    params = {"ref": branch}
    
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        return response.json()["sha"]
    return None

def create_or_update_file(owner, repo, path, content, branch, message):
    """Create or update a file in a GitHub repository"""
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    
    # Encode content to base64
    content_bytes = content.encode('utf-8')
    content_base64 = base64.b64encode(content_bytes).decode('utf-8')
    
    # Check if file exists
    sha = get_file_sha(owner, repo, path, branch)
    
    data = {
        "message": message,
        "content": content_base64,
        "branch": branch
    }
    
    if sha:
        data["sha"] = sha
        print(f"Updating existing file...")
    else:
        print(f"Creating new file...")
    
    response = requests.put(url, headers=headers, json=data)
    
    if response.status_code in [200, 201]:
        print(f"Successfully {'updated' if sha else 'created'} {path}")
        return True
    else:
        print(f"Error: {response.status_code}")
        print(response.json())
        return False

def main():
    # Fetch all repositories
    all_repos = fetch_all_repos(USERNAME)
    
    if not all_repos:
        print("No repositories found or error occurred")
        return
    
    print(f"\nTotal repositories found: {len(all_repos)}")
    
    # Format the data
    formatted_data = format_repo_data(all_repos)
    
    # Create JSON content with metadata
    json_content = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total_count": len(formatted_data),
        "repositories": formatted_data
    }
    
    # Convert to JSON string with pretty formatting
    json_string = json.dumps(json_content, indent=2, ensure_ascii=False)
    
    # Create or update the file in the repository
    commit_message = f"Update GIT.json with {len(formatted_data)} repositories"
    
    success = create_or_update_file(
        owner=USERNAME,
        repo=TARGET_REPO,
        path=FILE_PATH,
        content=json_string,
        branch=BRANCH,
        message=commit_message
    )
    
    if success:
        print(f"\n✓ Successfully pushed GIT.json to {USERNAME}/{TARGET_REPO}")
        print(f"  File contains {len(formatted_data)} repositories")
        print(f"  View at: https://github.com/{USERNAME}/{TARGET_REPO}/blob/{BRANCH}/{FILE_PATH}")
    else:
        print("\n✗ Failed to push file to repository")

if __name__ == "__main__":
    main()