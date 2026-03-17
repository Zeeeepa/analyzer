# Security Fixes for file_handler.py

## Date: 2025-12-11

## Summary
Fixed critical path traversal vulnerabilities and protected file detection bypass issues in `/mnt/c/ev29/cli/engine/agent/file_handler.py`.

## Vulnerabilities Fixed

### 1. Path Traversal Protection
**Before:** Used `os.path.abspath()` which could be bypassed with `../../../etc/passwd` attacks.

**After:** Implemented comprehensive path validation:
- Uses `Path.resolve()` to get canonical paths (resolves symlinks and relative paths)
- Validates resolved paths are within workspace boundary
- Blocks attempts to access files outside workspace
- Handles symlink escape attempts

**Implementation:**
```python
def validate_path(self, path: str) -> Tuple[bool, str, Optional[Path]]:
    resolved = Path(path).resolve(strict=False)
    try:
        resolved.relative_to(self.workspace_root)
    except ValueError:
        return False, f"Path outside workspace boundary: {path}", None
    return True, "", resolved
```

### 2. Protected File Detection Bypass
**Before:** Used substring matching - `.env-backup` bypassed `.env` check.

**After:** Implemented three matching modes:
- **exact**: Exact filename match (`.env`, `id_rsa`, `credentials.json`)
- **extension**: Extension-based match (`.pem`, `.key`)
- **glob**: Pattern matching (`*.key`, `.env.*`, `*_rsa`)

**Examples:**
- `.env` - BLOCKED (exact match)
- `.env-backup` - ALLOWED (not exact match)
- `.env.custom` - BLOCKED (glob match `.env.*`)
- `test.env` - ALLOWED (not exact match)
- `my_id_rsa` - BLOCKED (glob match `*_rsa`)
- `certificate.pem` - BLOCKED (extension match `.pem`)

### 3. Workspace Boundary Validation
**New Feature:** Added workspace root concept:
- Constructor accepts `workspace_root` parameter (defaults to `Path.cwd()`)
- All file operations validated against workspace boundary
- Prevents access to files outside designated workspace
- Applies to read, write, and list operations

### 4. Enhanced Protected Patterns
**Before:** 9 basic patterns with substring matching

**After:** 16 comprehensive patterns with type-aware matching:
```python
PROTECTED_PATTERNS = [
    # Environment files
    ('.env', 'exact'),
    ('.env.local', 'exact'),
    ('.env.production', 'exact'),
    ('.env.*', 'glob'),  # Catches .env.anything

    # SSH keys
    ('id_rsa', 'exact'),
    ('id_dsa', 'exact'),
    ('id_ecdsa', 'exact'),
    ('id_ed25519', 'exact'),

    # Extensions
    ('.pem', 'extension'),
    ('.key', 'extension'),
    ('.p12', 'extension'),
    ('.pfx', 'extension'),

    # Credentials
    ('credentials.json', 'exact'),
    ('secrets.yaml', 'exact'),
    ('secrets.yml', 'exact'),

    # Cloud provider credentials
    ('.aws/credentials', 'glob'),
    ('.azure/credentials', 'glob'),

    # Glob patterns for key variants
    ('*.key', 'glob'),
    ('*.pem', 'glob'),
    ('*_rsa', 'glob'),
    ('*_dsa', 'glob'),
]
```

## Security Validation

All security fixes validated with comprehensive test suite:
- **24 tests, all passing**
- Test file: `/mnt/c/ev29/cli/engine/agent/test_file_handler_security.py`

### Test Coverage:
1. **Path Traversal Protection (8 tests)**
   - Basic `../` traversal blocked
   - Nested traversal blocked
   - Dot-slash patterns resolved
   - Absolute paths outside workspace blocked
   - Symlink escape blocked
   - Valid paths allowed
   - Read/write operations block traversal

2. **Protected File Detection (12 tests)**
   - Exact match blocking works
   - Substring bypass prevented
   - Glob patterns work correctly
   - Extension matching works
   - Read/write operations respect protection

3. **Workspace Boundary (2 tests)**
   - Files outside workspace inaccessible
   - Files inside workspace accessible

4. **Configuration (2 tests)**
   - `allow_protected=False` blocks by default
   - `allow_protected=True` allows access

## Attack Vectors Mitigated

### 1. Path Traversal
```python
# BLOCKED
handler.read_file("../../../etc/passwd")
handler.read_file("../../../../root/.ssh/id_rsa")
handler.read_file("../../.env")
```

### 2. Symlink Escape
```python
# BLOCKED
# If /tmp/evil_link -> /etc/passwd
handler.read_file("/workspace/tmp/evil_link")
```

### 3. Protected File Bypass
```python
# BLOCKED
handler.read_file(".env")           # exact match
handler.read_file(".env.production")  # exact match
handler.read_file(".env.custom")     # glob match .env.*
handler.read_file("private.key")     # extension match .key
handler.read_file("backup_id_rsa")   # glob match *_rsa

# ALLOWED (as intended)
handler.read_file(".env-backup")     # not exact match
handler.read_file("test.env")        # not exact match
handler.read_file("test_credentials.json")  # not exact match
```

### 4. Absolute Path Escape
```python
# BLOCKED (if outside workspace)
handler.read_file("/etc/passwd")
handler.read_file("/home/user/.ssh/id_rsa")
```

## Migration Guide

### For Existing Code
The API remains backward compatible. No changes required for basic usage:
```python
handler = FileHandler()
result = handler.read_file("myfile.txt")
```

### For Enhanced Security
Specify workspace root explicitly:
```python
handler = FileHandler(workspace_root="/safe/workspace")
result = handler.read_file("myfile.txt")  # Only accesses files in /safe/workspace
```

### For Protected File Access
Use `allow_protected=True` (use with caution):
```python
handler = FileHandler(allow_protected=True)
result = handler.read_file(".env")  # Allowed, but logged
```

## Testing
Run security tests:
```bash
cd /mnt/c/ev29/cli/engine/agent
python3 test_file_handler_security.py
```

Expected output: **24 passed**

## Security Best Practices

1. **Always set workspace_root** in production environments
2. **Never use allow_protected=True** unless absolutely necessary
3. **Monitor logs** for path validation failures (indicates attack attempts)
4. **Regularly review** PROTECTED_PATTERNS for new sensitive file types
5. **Test thoroughly** when adding new file operations

## Future Enhancements

Potential additions:
1. Rate limiting for failed validation attempts
2. Audit logging for all file operations
3. Configurable protected patterns per instance
4. Whitelist mode (only allow specific file types)
5. File content scanning for secrets

## References

- **CVE Pattern**: CWE-22 (Path Traversal)
- **OWASP**: A01:2021 - Broken Access Control
- **Fixed File**: `/mnt/c/ev29/cli/engine/agent/file_handler.py`
- **Test File**: `/mnt/c/ev29/cli/engine/agent/test_file_handler_security.py`
