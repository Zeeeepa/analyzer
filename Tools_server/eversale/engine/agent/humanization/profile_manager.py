"""
Browser Profile Manager - Use persistent profiles with real session data

This enables using YOUR logged-in browser sessions (Gmail, LinkedIn, Facebook)
instead of fresh browser instances that require login.

Key features:
- Discovers existing Chrome/Edge profiles on the system
- Uses persistent user data directories
- Preserves cookies, localStorage, and session data
- Supports multiple profile switching
- Cookie management with import/export
- localStorage persistence
- Session health monitoring and auto-refresh
- Multi-instance profile sync with locking

Based on Playwright's launchPersistentContext feature.

WARNING: Anti-bot systems can detect profile inconsistencies.
Best practice is to use a dedicated profile created by this system,
not your main browsing profile.
"""

import os
import platform
import json
import asyncio
import time
import fcntl
from pathlib import Path
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from loguru import logger


@dataclass
class SessionState:
    """Tracks session state for a specific domain"""
    domain: str
    logged_in: bool = False
    last_verified: Optional[str] = None
    cookie_count: int = 0
    session_expires: Optional[str] = None
    needs_refresh: bool = False


@dataclass
class BrowserProfile:
    """Represents a browser profile with session tracking"""
    name: str
    path: str
    browser_type: str  # chrome, edge, firefox
    created_at: Optional[str] = None
    last_used: Optional[str] = None
    is_primary: bool = False
    notes: str = ""
    # Session tracking (domain -> SessionState)
    sessions: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class ProfileManagerConfig:
    """Configuration for profile management"""
    # Where to store Eversale's profiles
    profiles_dir: str = ""  # Auto-detected if empty

    # Default browser preferences
    preferred_browser: str = "chrome"

    # Session limits
    max_profiles: int = 10

    # Security
    auto_create_profile: bool = True  # Create fresh profile if none exists

    # Cookie/session management
    enable_cookie_persistence: bool = True
    enable_localstorage_persistence: bool = True
    cookie_export_on_login: bool = True  # Auto-export cookies after successful login
    session_health_check_interval: int = 3600  # Check session health every hour
    cookie_expiry_warning_days: int = 7  # Warn if cookies expire within N days

    # Multi-instance safety
    enable_profile_locking: bool = True  # Lock profiles during use
    lock_timeout_seconds: int = 300  # Max time to hold a lock


class ProfileManager:
    """
    Manages browser profiles for persistent sessions.

    Example:
        manager = ProfileManager()

        # Get default profile (creates if needed)
        profile = manager.get_default_profile()

        # Use with Playwright
        browser = await playwright.chromium.launch_persistent_context(
            user_data_dir=profile.path,
            channel="chrome"
        )
    """

    def __init__(self, config: Optional[ProfileManagerConfig] = None):
        self.config = config or ProfileManagerConfig()
        self._profiles: Dict[str, BrowserProfile] = {}

        # Auto-detect profiles directory
        if not self.config.profiles_dir:
            self.config.profiles_dir = self._get_default_profiles_dir()

        # Ensure directory exists
        Path(self.config.profiles_dir).mkdir(parents=True, exist_ok=True)

        # Profile locks (for multi-instance safety)
        self._locks: Dict[str, Any] = {}

        # Load existing profiles
        self._load_profiles()

    def _get_default_profiles_dir(self) -> str:
        """Get default directory for Eversale profiles."""
        system = platform.system()

        if system == "Windows":
            base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
            return os.path.join(base, "Eversale", "browser_profiles")
        elif system == "Darwin":  # macOS
            return os.path.expanduser("~/Library/Application Support/Eversale/browser_profiles")
        else:  # Linux
            return os.path.expanduser("~/.config/eversale/browser_profiles")

    def _get_chrome_profiles_dir(self) -> Optional[str]:
        """Get Chrome's default profiles directory (for discovery)."""
        system = platform.system()

        if system == "Windows":
            return os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data")
        elif system == "Darwin":
            return os.path.expanduser("~/Library/Application Support/Google/Chrome")
        else:
            return os.path.expanduser("~/.config/google-chrome")

    def _get_edge_profiles_dir(self) -> Optional[str]:
        """Get Edge's default profiles directory."""
        system = platform.system()

        if system == "Windows":
            return os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "User Data")
        elif system == "Darwin":
            return os.path.expanduser("~/Library/Application Support/Microsoft Edge")
        else:
            return os.path.expanduser("~/.config/microsoft-edge")

    def _load_profiles(self):
        """Load saved profiles from disk."""
        profiles_file = Path(self.config.profiles_dir) / "profiles.json"

        if profiles_file.exists():
            try:
                with open(profiles_file) as f:
                    data = json.load(f)
                    for name, profile_data in data.items():
                        # Handle sessions dict if present
                        if 'sessions' not in profile_data:
                            profile_data['sessions'] = {}
                        self._profiles[name] = BrowserProfile(**profile_data)
            except Exception as e:
                logger.warning(f"Failed to load profiles: {e}")

    def _save_profiles(self):
        """Save profiles to disk with atomic write."""
        profiles_file = Path(self.config.profiles_dir) / "profiles.json"
        temp_file = profiles_file.with_suffix('.tmp')

        try:
            data = {
                name: {
                    'name': p.name,
                    'path': p.path,
                    'browser_type': p.browser_type,
                    'created_at': p.created_at,
                    'last_used': p.last_used,
                    'is_primary': p.is_primary,
                    'notes': p.notes,
                    'sessions': p.sessions
                }
                for name, p in self._profiles.items()
            }

            # Atomic write: write to temp file then rename
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2)
            temp_file.replace(profiles_file)

        except Exception as e:
            logger.warning(f"Failed to save profiles: {e}")
            if temp_file.exists():
                temp_file.unlink()

    def create_profile(
        self,
        name: str,
        browser_type: str = "chrome",
        is_primary: bool = False,
        notes: str = ""
    ) -> BrowserProfile:
        """
        Create a new browser profile.

        Args:
            name: Profile name
            browser_type: chrome, edge, or firefox
            is_primary: Whether this is the default profile
            notes: Optional notes

        Returns:
            Created profile
        """
        if name in self._profiles:
            raise ValueError(f"Profile '{name}' already exists")

        if len(self._profiles) >= self.config.max_profiles:
            raise ValueError(f"Maximum profiles ({self.config.max_profiles}) reached")

        # Create profile directory
        profile_path = os.path.join(self.config.profiles_dir, name)
        Path(profile_path).mkdir(parents=True, exist_ok=True)

        # If setting as primary, clear existing primary
        if is_primary:
            for p in self._profiles.values():
                p.is_primary = False

        profile = BrowserProfile(
            name=name,
            path=profile_path,
            browser_type=browser_type,
            created_at=datetime.now().isoformat(),
            is_primary=is_primary,
            notes=notes
        )

        self._profiles[name] = profile
        self._save_profiles()

        logger.info(f"Created browser profile: {name} at {profile_path}")
        return profile

    def get_profile(self, name: str) -> Optional[BrowserProfile]:
        """Get a profile by name."""
        return self._profiles.get(name)

    def get_default_profile(self) -> BrowserProfile:
        """
        Get the default profile, creating one if needed.
        """
        # Look for primary profile
        for p in self._profiles.values():
            if p.is_primary:
                p.last_used = datetime.now().isoformat()
                self._save_profiles()
                return p

        # No primary, look for any profile
        if self._profiles:
            profile = next(iter(self._profiles.values()))
            profile.last_used = datetime.now().isoformat()
            self._save_profiles()
            return profile

        # No profiles exist, create default
        if self.config.auto_create_profile:
            return self.create_profile(
                name="default",
                browser_type=self.config.preferred_browser,
                is_primary=True,
                notes="Auto-created default profile"
            )

        raise ValueError("No profiles exist and auto_create_profile is disabled")

    def list_profiles(self) -> List[BrowserProfile]:
        """List all profiles."""
        return list(self._profiles.values())

    def delete_profile(self, name: str, delete_data: bool = False):
        """
        Delete a profile.

        Args:
            name: Profile name
            delete_data: Also delete the profile directory
        """
        if name not in self._profiles:
            raise ValueError(f"Profile '{name}' not found")

        profile = self._profiles[name]

        if delete_data:
            import shutil
            try:
                shutil.rmtree(profile.path)
                logger.info(f"Deleted profile data: {profile.path}")
            except Exception as e:
                logger.warning(f"Failed to delete profile data: {e}")

        del self._profiles[name]
        self._save_profiles()
        logger.info(f"Deleted profile: {name}")

    def discover_system_profiles(self) -> List[Dict]:
        """
        Discover existing Chrome/Edge profiles on the system.
        NOTE: Using main browser profiles may cause issues.
        """
        discovered = []

        # Check Chrome
        chrome_dir = self._get_chrome_profiles_dir()
        if chrome_dir and os.path.exists(chrome_dir):
            default_profile = os.path.join(chrome_dir, "Default")
            if os.path.exists(default_profile):
                discovered.append({
                    'name': 'Chrome Default',
                    'path': chrome_dir,
                    'browser_type': 'chrome',
                    'warning': 'Using main Chrome profile may cause conflicts'
                })

            # Look for additional profiles (Profile 1, Profile 2, etc.)
            for item in os.listdir(chrome_dir):
                if item.startswith("Profile "):
                    discovered.append({
                        'name': f'Chrome {item}',
                        'path': chrome_dir,
                        'profile_dir': item,
                        'browser_type': 'chrome',
                        'warning': 'Using main Chrome profile may cause conflicts'
                    })

        # Check Edge
        edge_dir = self._get_edge_profiles_dir()
        if edge_dir and os.path.exists(edge_dir):
            default_profile = os.path.join(edge_dir, "Default")
            if os.path.exists(default_profile):
                discovered.append({
                    'name': 'Edge Default',
                    'path': edge_dir,
                    'browser_type': 'edge',
                    'warning': 'Using main Edge profile may cause conflicts'
                })

        return discovered

    def import_from_system(self, source_path: str, name: str, browser_type: str) -> BrowserProfile:
        """
        Create a profile that references a system browser profile.
        WARNING: This can cause issues if the browser is also running.
        """
        if not os.path.exists(source_path):
            raise ValueError(f"Source path does not exist: {source_path}")

        profile = BrowserProfile(
            name=name,
            path=source_path,
            browser_type=browser_type,
            created_at=datetime.now().isoformat(),
            notes=f"Imported from {source_path}"
        )

        self._profiles[name] = profile
        self._save_profiles()

        logger.warning(
            f"Imported system profile '{name}'. "
            "Ensure the browser is closed when using this profile."
        )

        return profile

    # =========================================================================
    # Cookie Management
    # =========================================================================

    def _get_cookies_dir(self, profile_name: str) -> Path:
        """Get directory for cookie storage."""
        profile = self._profiles.get(profile_name)
        if not profile:
            raise ValueError(f"Profile '{profile_name}' not found")
        cookies_dir = Path(profile.path) / "eversale_cookies"
        cookies_dir.mkdir(parents=True, exist_ok=True)
        return cookies_dir

    def _get_cookie_file(self, profile_name: str, domain: str) -> Path:
        """Get cookie file path for a specific domain."""
        cookies_dir = self._get_cookies_dir(profile_name)
        # Sanitize domain for filename
        safe_domain = domain.replace('/', '_').replace(':', '_')
        return cookies_dir / f"{safe_domain}.json"

    async def export_cookies(
        self,
        profile_name: str,
        page,
        domain: Optional[str] = None
    ) -> bool:
        """
        Export cookies from browser to JSON files.

        Args:
            profile_name: Profile to export cookies for
            page: Playwright page object
            domain: Optional domain to filter cookies (exports all if None)

        Returns:
            True if successful, False otherwise
        """
        if not self.config.enable_cookie_persistence:
            return False

        try:
            # Get all cookies
            cookies = await page.context.cookies()

            if domain:
                # Filter by domain
                cookies = [c for c in cookies if domain in c.get('domain', '')]
                cookie_file = self._get_cookie_file(profile_name, domain)

                with open(cookie_file, 'w') as f:
                    json.dump(cookies, f, indent=2)

                logger.info(f"Exported {len(cookies)} cookies for {domain} to {cookie_file}")
            else:
                # Export all cookies, grouped by domain
                cookies_by_domain: Dict[str, List] = {}
                for cookie in cookies:
                    cookie_domain = cookie.get('domain', 'unknown')
                    if cookie_domain not in cookies_by_domain:
                        cookies_by_domain[cookie_domain] = []
                    cookies_by_domain[cookie_domain].append(cookie)

                # Save each domain separately
                for cookie_domain, domain_cookies in cookies_by_domain.items():
                    cookie_file = self._get_cookie_file(profile_name, cookie_domain)
                    with open(cookie_file, 'w') as f:
                        json.dump(domain_cookies, f, indent=2)

                logger.info(f"Exported cookies for {len(cookies_by_domain)} domains")

            # Update session state
            self._update_session_state(profile_name, domain or 'all', len(cookies))
            return True

        except Exception as e:
            logger.error(f"Failed to export cookies: {e}")
            return False

    async def import_cookies(
        self,
        profile_name: str,
        page,
        domain: Optional[str] = None
    ) -> bool:
        """
        Import cookies from JSON files to browser.

        Args:
            profile_name: Profile to import cookies for
            page: Playwright page object
            domain: Optional domain to filter cookies (imports all if None)

        Returns:
            True if successful, False otherwise
        """
        if not self.config.enable_cookie_persistence:
            return False

        try:
            cookies_dir = self._get_cookies_dir(profile_name)

            if domain:
                # Import specific domain
                cookie_file = self._get_cookie_file(profile_name, domain)
                if not cookie_file.exists():
                    logger.debug(f"No saved cookies for {domain}")
                    return False

                with open(cookie_file) as f:
                    cookies = json.load(f)

                # Check for expired cookies
                cookies = self._filter_expired_cookies(cookies, domain)

                if cookies:
                    await page.context.add_cookies(cookies)
                    logger.info(f"Imported {len(cookies)} cookies for {domain}")
                    return True
            else:
                # Import all cookie files
                cookie_files = list(cookies_dir.glob("*.json"))
                total_imported = 0

                for cookie_file in cookie_files:
                    try:
                        with open(cookie_file) as f:
                            cookies = json.load(f)

                        # Filter expired
                        cookies = self._filter_expired_cookies(
                            cookies,
                            cookie_file.stem
                        )

                        if cookies:
                            await page.context.add_cookies(cookies)
                            total_imported += len(cookies)
                    except Exception as e:
                        logger.debug(f"Failed to import {cookie_file}: {e}")

                logger.info(f"Imported {total_imported} cookies from {len(cookie_files)} domains")
                return total_imported > 0

        except Exception as e:
            logger.error(f"Failed to import cookies: {e}")
            return False

    def _filter_expired_cookies(self, cookies: List[Dict], domain: str) -> List[Dict]:
        """Filter out expired cookies and warn if expiring soon."""
        now = time.time()
        valid_cookies = []
        expiring_soon = []

        for cookie in cookies:
            expires = cookie.get('expires', -1)

            # -1 means session cookie (no expiry)
            if expires == -1:
                valid_cookies.append(cookie)
                continue

            # Check if expired
            if expires < now:
                logger.debug(f"Skipping expired cookie: {cookie.get('name')} for {domain}")
                continue

            # Check if expiring soon
            days_until_expiry = (expires - now) / 86400
            if days_until_expiry < self.config.cookie_expiry_warning_days:
                expiring_soon.append((cookie.get('name'), days_until_expiry))

            valid_cookies.append(cookie)

        if expiring_soon:
            logger.warning(
                f"Cookies expiring soon for {domain}: "
                f"{', '.join(f'{name} ({days:.1f} days)' for name, days in expiring_soon)}"
            )

        return valid_cookies

    def clear_cookies(self, profile_name: str, domain: Optional[str] = None):
        """
        Clear saved cookies for a profile.

        Args:
            profile_name: Profile name
            domain: Optional domain (clears all if None)
        """
        try:
            if domain:
                cookie_file = self._get_cookie_file(profile_name, domain)
                if cookie_file.exists():
                    cookie_file.unlink()
                    logger.info(f"Cleared cookies for {domain}")
            else:
                cookies_dir = self._get_cookies_dir(profile_name)
                for cookie_file in cookies_dir.glob("*.json"):
                    cookie_file.unlink()
                logger.info(f"Cleared all cookies for profile {profile_name}")
        except Exception as e:
            logger.error(f"Failed to clear cookies: {e}")

    # =========================================================================
    # localStorage Management
    # =========================================================================

    def _get_localstorage_file(self, profile_name: str, domain: str) -> Path:
        """Get localStorage file path for a specific domain."""
        profile = self._profiles.get(profile_name)
        if not profile:
            raise ValueError(f"Profile '{profile_name}' not found")

        storage_dir = Path(profile.path) / "eversale_storage"
        storage_dir.mkdir(parents=True, exist_ok=True)

        safe_domain = domain.replace('/', '_').replace(':', '_')
        return storage_dir / f"{safe_domain}.json"

    async def export_localstorage(
        self,
        profile_name: str,
        page,
        domain: Optional[str] = None
    ) -> bool:
        """
        Export localStorage from browser to JSON files.

        Args:
            profile_name: Profile to export storage for
            page: Playwright page object
            domain: Optional domain (uses current page domain if None)

        Returns:
            True if successful, False otherwise
        """
        if not self.config.enable_localstorage_persistence:
            return False

        try:
            # Get current domain if not specified
            if not domain:
                domain = await page.evaluate('() => window.location.hostname')

            # Extract localStorage
            storage_data = await page.evaluate('''() => {
                const data = {};
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    data[key] = localStorage.getItem(key);
                }
                return data;
            }''')

            if not storage_data:
                logger.debug(f"No localStorage data for {domain}")
                return False

            # Save to file
            storage_file = self._get_localstorage_file(profile_name, domain)
            with open(storage_file, 'w') as f:
                json.dump({
                    'domain': domain,
                    'exported_at': datetime.now().isoformat(),
                    'data': storage_data
                }, f, indent=2)

            logger.info(f"Exported localStorage ({len(storage_data)} items) for {domain}")
            return True

        except Exception as e:
            logger.error(f"Failed to export localStorage: {e}")
            return False

    async def import_localstorage(
        self,
        profile_name: str,
        page,
        domain: Optional[str] = None
    ) -> bool:
        """
        Import localStorage from JSON files to browser.

        Args:
            profile_name: Profile to import storage for
            page: Playwright page object
            domain: Optional domain (uses current page domain if None)

        Returns:
            True if successful, False otherwise
        """
        if not self.config.enable_localstorage_persistence:
            return False

        try:
            # Get current domain if not specified
            if not domain:
                domain = await page.evaluate('() => window.location.hostname')

            storage_file = self._get_localstorage_file(profile_name, domain)
            if not storage_file.exists():
                logger.debug(f"No saved localStorage for {domain}")
                return False

            # Load data
            with open(storage_file) as f:
                saved_data = json.load(f)

            storage_data = saved_data.get('data', {})
            if not storage_data:
                return False

            # Inject into page
            await page.evaluate('''(data) => {
                for (const [key, value] of Object.entries(data)) {
                    try {
                        localStorage.setItem(key, value);
                    } catch (e) {
                        console.warn('Failed to set localStorage item:', key, e);
                    }
                }
            }''', storage_data)

            logger.info(f"Imported localStorage ({len(storage_data)} items) for {domain}")
            return True

        except Exception as e:
            logger.error(f"Failed to import localStorage: {e}")
            return False

    def clear_localstorage(self, profile_name: str, domain: Optional[str] = None):
        """
        Clear saved localStorage for a profile.

        Args:
            profile_name: Profile name
            domain: Optional domain (clears all if None)
        """
        try:
            profile = self._profiles.get(profile_name)
            if not profile:
                return

            storage_dir = Path(profile.path) / "eversale_storage"

            if domain:
                storage_file = self._get_localstorage_file(profile_name, domain)
                if storage_file.exists():
                    storage_file.unlink()
                    logger.info(f"Cleared localStorage for {domain}")
            else:
                if storage_dir.exists():
                    for storage_file in storage_dir.glob("*.json"):
                        storage_file.unlink()
                    logger.info(f"Cleared all localStorage for profile {profile_name}")
        except Exception as e:
            logger.error(f"Failed to clear localStorage: {e}")

    # =========================================================================
    # Session State Management
    # =========================================================================

    def _update_session_state(
        self,
        profile_name: str,
        domain: str,
        cookie_count: int,
        logged_in: bool = True,
        expires: Optional[datetime] = None
    ):
        """Update session state for a domain."""
        profile = self._profiles.get(profile_name)
        if not profile:
            return

        profile.sessions[domain] = {
            'domain': domain,
            'logged_in': logged_in,
            'last_verified': datetime.now().isoformat(),
            'cookie_count': cookie_count,
            'session_expires': expires.isoformat() if expires else None,
            'needs_refresh': False
        }
        self._save_profiles()

    def get_session_state(self, profile_name: str, domain: str) -> Optional[SessionState]:
        """Get session state for a domain."""
        profile = self._profiles.get(profile_name)
        if not profile or domain not in profile.sessions:
            return None

        session_data = profile.sessions[domain]
        return SessionState(**session_data)

    def mark_session_needs_refresh(self, profile_name: str, domain: str):
        """Mark a session as needing refresh/re-authentication."""
        profile = self._profiles.get(profile_name)
        if profile and domain in profile.sessions:
            profile.sessions[domain]['needs_refresh'] = True
            profile.sessions[domain]['logged_in'] = False
            self._save_profiles()
            logger.warning(f"Session for {domain} marked as needing refresh")

    async def verify_session_health(
        self,
        profile_name: str,
        page,
        domain: str
    ) -> bool:
        """
        Verify session is still valid by checking cookies and page response.

        Args:
            profile_name: Profile name
            page: Playwright page object
            domain: Domain to check

        Returns:
            True if session is healthy, False if needs refresh
        """
        try:
            # Get cookies for this domain
            cookies = await page.context.cookies()
            domain_cookies = [c for c in cookies if domain in c.get('domain', '')]

            if not domain_cookies:
                logger.warning(f"No cookies found for {domain}")
                self.mark_session_needs_refresh(profile_name, domain)
                return False

            # Check for auth-related cookies (common patterns)
            auth_cookie_patterns = ['session', 'token', 'auth', 'sid', 'login']
            has_auth_cookie = any(
                any(pattern in c.get('name', '').lower() for pattern in auth_cookie_patterns)
                for c in domain_cookies
            )

            if not has_auth_cookie:
                logger.debug(f"No auth cookies detected for {domain}")

            # Update session state
            self._update_session_state(
                profile_name,
                domain,
                len(domain_cookies),
                logged_in=has_auth_cookie
            )

            return has_auth_cookie

        except Exception as e:
            logger.error(f"Failed to verify session health: {e}")
            return False

    def get_sessions_needing_refresh(self, profile_name: str) -> List[str]:
        """Get list of domains that need session refresh."""
        profile = self._profiles.get(profile_name)
        if not profile:
            return []

        return [
            domain for domain, state in profile.sessions.items()
            if state.get('needs_refresh', False)
        ]

    # =========================================================================
    # Profile Locking (Multi-Instance Safety)
    # =========================================================================

    def acquire_profile_lock(self, profile_name: str) -> bool:
        """
        Acquire exclusive lock on a profile.

        Args:
            profile_name: Profile to lock

        Returns:
            True if lock acquired, False if already locked
        """
        if not self.config.enable_profile_locking:
            return True

        profile = self._profiles.get(profile_name)
        if not profile:
            return False

        lock_file = Path(profile.path) / ".eversale.lock"

        try:
            # Try to create lock file with exclusive access
            lock_fd = os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)

            # Write lock info
            lock_info = {
                'pid': os.getpid(),
                'locked_at': datetime.now().isoformat(),
                'timeout': self.config.lock_timeout_seconds
            }
            os.write(lock_fd, json.dumps(lock_info).encode())
            os.close(lock_fd)

            # Store lock file reference
            self._locks[profile_name] = lock_file

            logger.debug(f"Acquired lock on profile {profile_name}")
            return True

        except FileExistsError:
            # Lock already exists - check if stale
            try:
                with open(lock_file) as f:
                    lock_info = json.load(f)

                locked_at = datetime.fromisoformat(lock_info['locked_at'])
                timeout = lock_info.get('timeout', 300)

                # Check if lock is stale
                if (datetime.now() - locked_at).total_seconds() > timeout:
                    logger.warning(f"Stale lock detected on {profile_name}, removing")
                    lock_file.unlink()
                    return self.acquire_profile_lock(profile_name)

                logger.warning(f"Profile {profile_name} is locked by PID {lock_info.get('pid')}")
                return False

            except Exception as e:
                logger.error(f"Failed to check lock file: {e}")
                return False

        except Exception as e:
            logger.error(f"Failed to acquire profile lock: {e}")
            return False

    def release_profile_lock(self, profile_name: str):
        """Release lock on a profile."""
        if not self.config.enable_profile_locking:
            return

        lock_file = self._locks.get(profile_name)
        if lock_file and lock_file.exists():
            try:
                lock_file.unlink()
                del self._locks[profile_name]
                logger.debug(f"Released lock on profile {profile_name}")
            except Exception as e:
                logger.error(f"Failed to release lock: {e}")

    def __del__(self):
        """Clean up locks on destruction."""
        for profile_name in list(self._locks.keys()):
            self.release_profile_lock(profile_name)

    # =========================================================================
    # High-Level Session Management
    # =========================================================================

    async def on_successful_login(
        self,
        profile_name: str,
        page,
        domain: str
    ):
        """
        Called after successful login to a service.
        Automatically exports cookies and localStorage.

        Args:
            profile_name: Profile name
            page: Playwright page object
            domain: Domain that was logged into
        """
        logger.info(f"Saving session for {domain} in profile {profile_name}")

        # Export cookies
        if self.config.cookie_export_on_login:
            await self.export_cookies(profile_name, page, domain)

        # Export localStorage
        await self.export_localstorage(profile_name, page, domain)

        # Update session state
        cookies = await page.context.cookies()
        domain_cookies = [c for c in cookies if domain in c.get('domain', '')]

        self._update_session_state(
            profile_name,
            domain,
            len(domain_cookies),
            logged_in=True
        )

        logger.success(f"Session saved for {domain}")

    async def restore_session(
        self,
        profile_name: str,
        page,
        domain: str
    ) -> bool:
        """
        Restore session for a domain (cookies + localStorage).

        Args:
            profile_name: Profile name
            page: Playwright page object
            domain: Domain to restore session for

        Returns:
            True if session restored, False if no session found
        """
        logger.info(f"Restoring session for {domain}")

        # Import cookies
        cookies_restored = await self.import_cookies(profile_name, page, domain)

        # Import localStorage
        storage_restored = await self.import_localstorage(profile_name, page, domain)

        if cookies_restored or storage_restored:
            logger.success(f"Session restored for {domain}")
            return True
        else:
            logger.warning(f"No saved session found for {domain}")
            return False


# Global manager instance
_global_manager: Optional[ProfileManager] = None


def get_profile_manager() -> ProfileManager:
    """Get or create global profile manager."""
    global _global_manager
    if _global_manager is None:
        _global_manager = ProfileManager()
    return _global_manager


def get_default_profile() -> BrowserProfile:
    """Get the default browser profile."""
    return get_profile_manager().get_default_profile()


def get_profile_path(name: str = "default") -> str:
    """Get path to a profile's user data directory."""
    manager = get_profile_manager()
    profile = manager.get_profile(name)

    if profile:
        return profile.path

    # Create if doesn't exist
    profile = manager.create_profile(name)
    return profile.path


# Helper for Playwright integration
def get_persistent_context_args(profile_name: str = "default") -> Dict:
    """
    Get arguments for playwright.chromium.launch_persistent_context().

    Example:
        args = get_persistent_context_args()
        browser = await playwright.chromium.launch_persistent_context(**args)
    """
    manager = get_profile_manager()

    try:
        profile = manager.get_profile(profile_name) or manager.get_default_profile()
    except Exception:
        profile = manager.create_profile(profile_name, is_primary=True)

    return {
        'user_data_dir': profile.path,
        'channel': 'chrome' if profile.browser_type == 'chrome' else None,
        'headless': False,  # Persistent contexts work better headed
        'no_viewport': True,  # Use native resolution
    }
