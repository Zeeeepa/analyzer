# SearchHandler Quick Reference

## Check Availability

```python
from a11y_browser import SEARCH_HANDLER_AVAILABLE

if SEARCH_HANDLER_AVAILABLE:
    print("SearchHandler is ready to use!")
```

## Four Main Methods

### 1. search_files() - Find files by pattern

```python
# Find all Python files
result = await browser.search_files("*.py", "/path/to/search")

# Find all TypeScript files in nested directories
result = await browser.search_files("**/*.ts", "./src")

# Include hidden files
result = await browser.search_files(".*", ".", include_hidden=True)
```

**Returns:**
- `data["files"]` - List of matching file paths
- `data["total_found"]` - Total count
- `data["truncated"]` - True if results were limited
- `data["formatted"]` - LLM-friendly formatted output

### 2. search_content() - Search inside files

```python
# Search for function definitions in Python files
result = await browser.search_content(
    "def ",
    path=".",
    file_pattern="*.py",
    context_lines=2
)

# Case-insensitive search
result = await browser.search_content(
    "TODO",
    path="./src",
    case_sensitive=False
)

# Search in specific file
result = await browser.search_content(
    "import.*playwright",
    path="./browser.py"
)
```

**Returns:**
- `data["matches"]` - List of match objects:
  - `file` - File path
  - `line` - Line number
  - `content` - Matching line
  - `context_before` - Lines before match
  - `context_after` - Lines after match
- `data["total_matches"]` - Total matches found
- `data["files_searched"]` - Number of files searched
- `data["formatted"]` - LLM-friendly formatted output

### 3. find_files() - Find by exact name

```python
# Find config.yaml anywhere in project
result = await browser.find_files("config.yaml", "./project")

# Find package.json files
result = await browser.find_files("package.json", ".")
```

**Returns:**
- `data["files"]` - List of matching file paths

### 4. find_files_containing() - Find files with content

```python
# Find files containing "SearchHandler"
result = await browser.find_files_containing("SearchHandler", ".")

# Find files with TODO comments
result = await browser.find_files_containing("TODO", "./src")
```

**Returns:**
- `data["files"]` - List of file paths containing the pattern

## Complete Example

```python
import asyncio
from a11y_browser import A11yBrowser

async def demo():
    browser = A11yBrowser()

    # 1. Find all Python files
    result = await browser.search_files("*.py", ".")
    print(f"Found {result.data['total_found']} Python files")

    # 2. Search for SearchHandler usage
    result = await browser.search_content("SearchHandler", ".", "*.py")
    if result.success:
        print(f"Found in {result.data['files_searched']} files:")
        for match in result.data['matches'][:3]:
            print(f"  {match['file']}:{match['line']}")

    # 3. Find specific file
    result = await browser.find_files("search_handler.py", ".")
    print(f"search_handler.py location: {result.data['files']}")

    # 4. Find all files with async functions
    result = await browser.find_files_containing("async def", ".")
    print(f"{len(result.data['files'])} files have async functions")

asyncio.run(demo())
```

## Error Handling

All methods return `ActionResult` with graceful failure:

```python
result = await browser.search_files("*.py", "/nonexistent/path")

if result.success:
    files = result.data["files"]
else:
    print(f"Error: {result.error}")
```

## Performance Tips

1. Use specific patterns to reduce search scope:
   - Good: `"*.py"` or `"src/**/*.ts"`
   - Avoid: `"*"` or `"**/*"`

2. Limit search paths when possible:
   - Good: `"./src"` or `"./engine/agent"`
   - Avoid: `"/"` or `"/home"`

3. Use file_pattern to filter content searches:
   ```python
   # Better performance
   result = await browser.search_content("def main", ".", "*.py")

   # Slower (searches all files)
   result = await browser.search_content("def main", ".")
   ```

4. Results are automatically limited to first 100 matches:
   - Check `data["truncated"]` to see if there are more
   - Use more specific patterns if truncated

## Integration Notes

- SearchHandler works WITHOUT browser launch
- Methods are async but don't require page navigation
- All file paths are absolute paths
- Results sorted by modification time (newest first)
- Uses singleton handler instance for efficiency
- Graceful fallback if SearchHandler not available
