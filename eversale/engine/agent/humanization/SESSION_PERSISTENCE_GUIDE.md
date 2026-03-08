# Session Persistence Guide

This guide explains how to use the enhanced session/cookie persistence features in `profile_manager.py`.

## Overview

The ProfileManager now provides comprehensive session management:

1. **Cookie Management** - Export/import cookies to JSON files per domain
2. **localStorage Persistence** - Save/restore localStorage data
3. **Session Health Monitoring** - Track login state and cookie expiry
4. **Multi-Instance Safety** - Profile locking prevents conflicts
5. **Auto-Export on Login** - Automatically save sessions after successful login

## Architecture

```
ProfileManager
├── Cookie Management
│   ├── Export cookies (per-domain JSON files)
│   ├── Import cookies (with expiry checking)
│   └── Clear cookies
├── localStorage Management
│   ├── Export localStorage (per-domain)
│   ├── Import localStorage
│   └── Clear localStorage
├── Session State Tracking
│   ├── Track login state per domain
│   ├── Monitor cookie expiry
│   └── Flag sessions needing refresh
├── Profile Locking
│   ├── Exclusive locks per profile
│   ├── Stale lock detection
│   └── Auto-cleanup on exit
└── Integration Hooks
    ├── LoginManager - auto-export on login
    └── BrowserManager - session helpers
```

## File Structure

For a profile named "default", session data is stored as:

```
~/.config/eversale/browser_profiles/default/
├── eversale_cookies/
│   ├── gmail.com.json
│   ├── linkedin.com.json
│   └── facebook.com.json
├── eversale_storage/
│   ├── gmail.com.json
│   ├── linkedin.com.json
│   └── facebook.com.json
├── .eversale.lock (while profile is in use)
└── Default/ (Chrome user data)
```

## Usage Examples

### 1. Basic Cookie Export/Import

```python
from agent.humanization import get_profile_manager

# Get manager
manager = get_profile_manager()

# After successful login to Gmail
profile_name = "default"
domain = "gmail.com"

# Export cookies
await manager.export_cookies(profile_name, page, domain)

# Later, restore cookies
await manager.import_cookies(profile_name, page, domain)
```

### 2. localStorage Persistence

```python
# Export localStorage after login
await manager.export_localstorage(profile_name, page)

# Restore on next browser session
await manager.import_localstorage(profile_name, page)
```

### 3. Automatic Session Saving (LoginManager Integration)

The LoginManager automatically saves sessions after successful login:

```python
from agent.login_manager import LoginManager
from agent.humanization import get_profile_manager

# Initialize with profile manager
profile_mgr = get_profile_manager()
login_mgr = LoginManager(profile_manager=profile_mgr)

# Login and auto-save session
await login_mgr.verify_login("gmail", browser, profile_name="default")
# Cookies and localStorage are automatically exported!
```

### 4. Session Health Monitoring

```python
# Check if session is still valid
is_healthy = await manager.verify_session_health(
    profile_name="default",
    page=page,
    domain="linkedin.com"
)

if not is_healthy:
    print("Session expired, need to re-login")

# Get sessions needing refresh
sessions_to_refresh = manager.get_sessions_needing_refresh("default")
print(f"Sessions needing refresh: {sessions_to_refresh}")
```

### 5. Profile Locking (Multi-Instance Safety)

```python
# Acquire lock before using profile
if manager.acquire_profile_lock("default"):
    try:
        # Use profile safely
        await do_browser_work()
    finally:
        # Always release lock
        manager.release_profile_lock("default")
else:
    print("Profile is locked by another process")
```

### 6. High-Level Session Management

```python
# Complete session save (cookies + localStorage)
await manager.on_successful_login(
    profile_name="default",
    page=page,
    domain="facebook.com"
)

# Complete session restore
restored = await manager.restore_session(
    profile_name="default",
    page=page,
    domain="facebook.com"
)

if restored:
    print("Session restored successfully")
else:
    print("No saved session found")
```

### 7. BrowserManager Integration

```python
from agent.browser_manager import BrowserManager
from agent.humanization import get_profile_manager

# Initialize browser manager with profile manager
profile_mgr = get_profile_manager()
browser_mgr = BrowserManager(
    mcp_client=mcp,
    profile_manager=profile_mgr
)

# Save session for current domain
await browser_mgr.save_session_for_current_domain("default")

# Restore session before navigating
await browser_mgr.restore_session_for_domain("linkedin.com", "default")

# Check session health
is_healthy = await browser_mgr.verify_domain_session_health("linkedin.com")
```

## Configuration

Customize session persistence behavior:

```python
from agent.humanization.profile_manager import ProfileManagerConfig, ProfileManager

config = ProfileManagerConfig(
    # Enable/disable features
    enable_cookie_persistence=True,
    enable_localstorage_persistence=True,
    cookie_export_on_login=True,  # Auto-export after login

    # Health monitoring
    session_health_check_interval=3600,  # Check every hour
    cookie_expiry_warning_days=7,  # Warn if expiring in 7 days

    # Multi-instance safety
    enable_profile_locking=True,
    lock_timeout_seconds=300  # 5 minutes
)

manager = ProfileManager(config=config)
```

## Session State Tracking

The manager tracks session state per domain:

```python
# Get session state
session = manager.get_session_state("default", "gmail.com")

if session:
    print(f"Domain: {session.domain}")
    print(f"Logged in: {session.logged_in}")
    print(f"Last verified: {session.last_verified}")
    print(f"Cookie count: {session.cookie_count}")
    print(f"Expires: {session.session_expires}")
    print(f"Needs refresh: {session.needs_refresh}")
```

## Cookie Expiry Handling

The manager automatically filters expired cookies and warns about expiring ones:

```python
# When importing cookies, expired ones are skipped
await manager.import_cookies(profile_name, page, domain)

# Logs will show:
# [WARNING] Cookies expiring soon for gmail.com: SID (6.5 days), HSID (4.2 days)
# [DEBUG] Skipping expired cookie: old_session for gmail.com
```

## Clearing Sessions

```python
# Clear cookies for a specific domain
manager.clear_cookies("default", "gmail.com")

# Clear all cookies for profile
manager.clear_cookies("default")

# Clear localStorage for a domain
manager.clear_localstorage("default", "linkedin.com")

# Clear all localStorage
manager.clear_localstorage("default")
```

## Integration Flow

### Complete Login Flow with Session Persistence

```python
from agent.login_manager import LoginManager
from agent.humanization import get_profile_manager
from agent.browser_manager import BrowserManager

# 1. Initialize managers
profile_mgr = get_profile_manager()
login_mgr = LoginManager(profile_manager=profile_mgr)
browser_mgr = BrowserManager(mcp_client=mcp, profile_manager=profile_mgr)

# 2. Set current profile
browser_mgr.set_current_profile("default")

# 3. Try to restore existing session
await browser_mgr.restore_session_for_domain("gmail.com", "default")

# 4. Verify login (LoginManager auto-restores if needed)
is_logged_in = await login_mgr.verify_login(
    "gmail",
    browser,
    profile_name="default"
)

# 5. If login successful, session is auto-saved
# LoginManager.mark_logged_in() calls profile_mgr.on_successful_login()
```

## Best Practices

### 1. Always Use Try-Finally for Locks

```python
if manager.acquire_profile_lock("default"):
    try:
        await do_work()
    finally:
        manager.release_profile_lock("default")
```

### 2. Check Session Health Periodically

```python
# Every hour, verify sessions are still valid
for domain in ["gmail.com", "linkedin.com", "facebook.com"]:
    is_healthy = await manager.verify_session_health(
        "default",
        page,
        domain
    )

    if not is_healthy:
        # Trigger re-login
        await login_mgr.verify_login(service_id, browser)
```

### 3. Handle Quota Errors in localStorage

The manager handles quota errors gracefully:

```python
# localStorage.setItem() may fail if quota exceeded
# The manager catches these and logs warnings
await manager.import_localstorage(profile_name, page, domain)
# Individual items that fail are skipped, others succeed
```

### 4. Use Domain-Specific Cookie Files

Each domain gets its own cookie file, which:
- Reduces file size
- Enables selective restore
- Prevents cross-domain cookie leaks
- Makes debugging easier

### 5. Monitor Expiring Cookies

Enable expiry warnings to proactively re-authenticate:

```python
config = ProfileManagerConfig(
    cookie_expiry_warning_days=7  # Warn if < 7 days
)
```

## Security Considerations

### 1. Cookie File Permissions

Cookie files contain sensitive auth tokens. The manager stores them in user-only directories:

- Linux/macOS: `~/.config/eversale/` (mode 700)
- Windows: `%LOCALAPPDATA%\Eversale\`

### 2. Lock Files Prevent Conflicts

Profile locks prevent multiple browser instances from corrupting the same profile:

```python
# Process A acquires lock
manager.acquire_profile_lock("default")  # Success

# Process B tries to acquire
manager.acquire_profile_lock("default")  # Fails - already locked
```

### 3. Stale Lock Detection

If a process crashes with a lock held, the lock becomes stale after the timeout:

```python
# Lock held for > 5 minutes (default timeout)
# Next process detects stale lock and clears it
manager.acquire_profile_lock("default")  # Success after clearing stale lock
```

## Troubleshooting

### Session Not Restoring

```python
# Enable debug logging
import logging
logging.getLogger("agent.humanization.profile_manager").setLevel(logging.DEBUG)

# Check if cookie files exist
cookies_dir = manager._get_cookies_dir("default")
print(f"Cookie files: {list(cookies_dir.glob('*.json'))}")

# Verify domain matching
# "gmail.com" != "mail.google.com" - use exact domain
```

### Profile Locked Error

```python
# Check who holds the lock
profile = manager.get_profile("default")
lock_file = Path(profile.path) / ".eversale.lock"

if lock_file.exists():
    with open(lock_file) as f:
        lock_info = json.load(f)
    print(f"Locked by PID: {lock_info['pid']}")
    print(f"Locked at: {lock_info['locked_at']}")

    # Force clear if needed (use carefully!)
    lock_file.unlink()
```

### Cookies Expired

```python
# Check cookie expiry
session = manager.get_session_state("default", "gmail.com")
if session and session.needs_refresh:
    print("Session marked for refresh")

# Re-authenticate
await login_mgr.verify_login("gmail", browser)
```

## Advanced: Custom Session Validation

You can extend session health checks with custom logic:

```python
async def verify_gmail_session(manager, profile_name, page):
    """Custom Gmail session verification."""

    # 1. Check cookies
    cookies = await page.context.cookies()
    gmail_cookies = [c for c in cookies if 'google.com' in c.get('domain', '')]

    # 2. Look for specific auth cookies
    has_sid = any(c.get('name') == 'SID' for c in gmail_cookies)
    has_hsid = any(c.get('name') == 'HSID' for c in gmail_cookies)

    if not (has_sid and has_hsid):
        manager.mark_session_needs_refresh(profile_name, "gmail.com")
        return False

    # 3. Verify by navigating
    await page.goto("https://mail.google.com")
    await page.wait_for_timeout(2000)

    # 4. Check for login indicators
    page_text = await page.evaluate('() => document.body.innerText')
    is_logged_in = 'inbox' in page_text.lower()

    if is_logged_in:
        manager._update_session_state(profile_name, "gmail.com", len(gmail_cookies))
    else:
        manager.mark_session_needs_refresh(profile_name, "gmail.com")

    return is_logged_in
```

## Performance Tips

### 1. Batch Cookie Import

```python
# Import all cookies at once (faster than per-domain)
await manager.import_cookies(profile_name, page)  # domain=None
```

### 2. Skip localStorage for Large Data

If localStorage contains large data (e.g., cached API responses):

```python
config = ProfileManagerConfig(
    enable_localstorage_persistence=False  # Disable if causing issues
)
```

### 3. Profile Lock Timeouts

Adjust timeout based on expected session duration:

```python
config = ProfileManagerConfig(
    lock_timeout_seconds=600  # 10 minutes for long tasks
)
```

## Summary

The enhanced ProfileManager provides enterprise-grade session persistence:

✅ **Cookie management** - Export/import with expiry checking
✅ **localStorage persistence** - Full state preservation
✅ **Session health** - Track login state and auto-refresh
✅ **Multi-instance safety** - Profile locking prevents conflicts
✅ **Auto-export** - Automatic session save after login
✅ **Integration hooks** - Works seamlessly with LoginManager and BrowserManager

This enables truly persistent browser sessions, reducing the need for repeated logins and improving the user experience.
