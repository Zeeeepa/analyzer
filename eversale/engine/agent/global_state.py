"""
Global State Manager for Eversale Agent

Provides centralized file system organization following XDG Base Directory spec.
Based on OpenCode's global/index.ts pattern.

Features:
- Immutable path configuration (GlobalPaths)
- Cross-platform directory management (XDG on Linux, AppData on Windows, Library on macOS)
- Thread-safe initialization
- Cache versioning and invalidation
- Auto-creation of required directories
"""

import json
import os
import sys
import shutil
import threading
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


def _get_package_version() -> str:
    """Read version from env var, version.txt, or package.json."""
    # First check env var (set by Node.js wrapper)
    env_version = os.environ.get('EVERSALE_VERSION')
    if env_version:
        return env_version

    # Second fallback - check ~/.eversale/version.txt (written by Node.js wrapper)
    try:
        eversale_home = os.environ.get('EVERSALE_HOME') or os.path.join(os.path.expanduser('~'), '.eversale')
        version_txt_path = Path(eversale_home) / 'version.txt'
        if version_txt_path.exists():
            version = version_txt_path.read_text().strip()
            if version:
                return version
    except Exception:
        pass

    # Third fallback - check package.json (dev environment)
    try:
        # CLI root is 2 levels up from engine/agent/
        cli_root = Path(__file__).parent.parent.parent
        package_json_path = cli_root / "package.json"
        if package_json_path.exists():
            with open(package_json_path, 'r') as f:
                package_data = json.load(f)
                return package_data.get('version', '0.1.0')
    except Exception:
        pass

    return '0.1.0'


__version__ = _get_package_version()


@dataclass(frozen=True)
class GlobalPaths:
    """
    Immutable paths configuration for the agent.

    All paths are created automatically on first access.
    Follows platform conventions:
    - Linux: XDG Base Directory spec (~/.eversale, ~/.cache/eversale, etc.)
    - Windows: AppData/Local/eversale
    - macOS: ~/Library/Application Support/eversale
    """

    home: Path
    data: Path
    bin: Path
    log: Path
    cache: Path
    config: Path
    state: Path

    def __post_init__(self):
        """Validate all paths are absolute."""
        for field_name, field_value in self.__dict__.items():
            if not isinstance(field_value, Path):
                raise TypeError(f"{field_name} must be a Path object")
            if not field_value.is_absolute():
                raise ValueError(f"{field_name} must be an absolute path: {field_value}")


class GlobalState:
    """
    Thread-safe global state manager for the agent.

    Provides:
    - Singleton path configuration
    - Directory auto-creation
    - Version management
    - Cache invalidation

    Usage:
        state = GlobalState()
        paths = state.get_paths()
        print(f"Data directory: {paths.data}")
    """

    _instance: Optional['GlobalState'] = None
    _lock = threading.Lock()
    _paths: Optional[GlobalPaths] = None
    _initialized = False

    def __new__(cls):
        """Singleton pattern with thread safety."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize state manager (only once)."""
        if not self._initialized:
            with self._lock:
                if not self._initialized:
                    self._setup_paths()
                    GlobalState._initialized = True

    def _setup_paths(self) -> None:
        """
        Setup platform-specific paths.

        Platform-specific base directories:
        - Linux: ~/.eversale (data), ~/.cache/eversale (cache), ~/.config/eversale (config)
        - Windows: %LOCALAPPDATA%/eversale for all
        - macOS: ~/Library/Application Support/eversale (data), ~/Library/Caches/eversale (cache)
        """
        home = Path.home()
        platform = sys.platform

        if platform == "win32":
            # Windows: Use AppData/Local
            local_app_data = os.getenv("LOCALAPPDATA")
            if local_app_data:
                base = Path(local_app_data) / "eversale"
            else:
                base = home / "AppData" / "Local" / "eversale"

            data_dir = base
            cache_dir = base / "cache"
            config_dir = base / "config"
            state_dir = base / "state"

        elif platform == "darwin":
            # macOS: Use Library directories
            data_dir = home / "Library" / "Application Support" / "eversale"
            cache_dir = home / "Library" / "Caches" / "eversale"
            config_dir = home / "Library" / "Application Support" / "eversale" / "config"
            state_dir = home / "Library" / "Application Support" / "eversale" / "state"

        else:
            # Linux: Follow XDG Base Directory specification
            xdg_data_home = os.getenv("XDG_DATA_HOME")
            xdg_cache_home = os.getenv("XDG_CACHE_HOME")
            xdg_config_home = os.getenv("XDG_CONFIG_HOME")
            xdg_state_home = os.getenv("XDG_STATE_HOME")

            data_dir = Path(xdg_data_home) / "eversale" if xdg_data_home else home / ".local" / "share" / "eversale"
            cache_dir = Path(xdg_cache_home) / "eversale" if xdg_cache_home else home / ".cache" / "eversale"
            config_dir = Path(xdg_config_home) / "eversale" if xdg_config_home else home / ".config" / "eversale"
            state_dir = Path(xdg_state_home) / "eversale" if xdg_state_home else home / ".local" / "state" / "eversale"

        # Create paths object (immutable)
        GlobalState._paths = GlobalPaths(
            home=home,
            data=data_dir,
            bin=data_dir / "bin",
            log=data_dir / "logs",
            cache=cache_dir,
            config=config_dir,
            state=state_dir
        )

    def get_paths(self) -> GlobalPaths:
        """
        Get immutable paths configuration.

        Returns:
            GlobalPaths: Immutable paths object

        Example:
            >>> state = GlobalState()
            >>> paths = state.get_paths()
            >>> print(paths.data)
            PosixPath('/home/user/.local/share/eversale')
        """
        if self._paths is None:
            raise RuntimeError("GlobalState not initialized")
        return self._paths

    def initialize(self, create_dirs: bool = True) -> None:
        """
        Initialize required directories.

        Args:
            create_dirs: Whether to create directories (default: True)

        Creates all required directories with proper permissions.
        Safe to call multiple times (idempotent).

        Example:
            >>> state = GlobalState()
            >>> state.initialize()  # Creates all directories
        """
        if self._paths is None:
            raise RuntimeError("GlobalState not initialized")

        if not create_dirs:
            return

        with self._lock:
            # Create all directories
            for field_name, path in self._paths.__dict__.items():
                if field_name == 'home':
                    continue  # Don't create home directory

                try:
                    path.mkdir(parents=True, exist_ok=True)
                    # Set permissions (user rwx, group rx, other rx)
                    if sys.platform != "win32":
                        path.chmod(0o755)
                except Exception as e:
                    # Log but don't fail - directory might already exist
                    print(f"Warning: Could not create {field_name} directory at {path}: {e}")

    def get_version(self) -> str:
        """
        Get current version of the agent.

        Returns:
            str: Version string (e.g., "0.1.0")

        Example:
            >>> state = GlobalState()
            >>> print(state.get_version())
            0.1.0
        """
        return __version__

    def _get_version_file(self) -> Path:
        """Get path to version file in cache."""
        if self._paths is None:
            raise RuntimeError("GlobalState not initialized")
        return self._paths.cache / ".version"

    def _read_cached_version(self) -> Optional[str]:
        """Read version from cache file."""
        version_file = self._get_version_file()
        if version_file.exists():
            try:
                return version_file.read_text().strip()
            except Exception:
                return None
        return None

    def _write_cached_version(self) -> None:
        """Write current version to cache file."""
        version_file = self._get_version_file()
        try:
            version_file.parent.mkdir(parents=True, exist_ok=True)
            version_file.write_text(__version__)
        except Exception as e:
            print(f"Warning: Could not write version file: {e}")

    def invalidate_cache(self, force: bool = False) -> bool:
        """
        Invalidate and clear cache if version has changed.

        Args:
            force: Force cache invalidation even if version matches

        Returns:
            bool: True if cache was invalidated, False otherwise

        Clears the cache directory when:
        - Version has changed since last run
        - force=True is specified

        Example:
            >>> state = GlobalState()
            >>> state.invalidate_cache()  # Clear if version changed
            True
            >>> state.invalidate_cache(force=True)  # Always clear
            True
        """
        if self._paths is None:
            raise RuntimeError("GlobalState not initialized")

        cached_version = self._read_cached_version()
        current_version = self.get_version()

        should_invalidate = force or (cached_version != current_version)

        if should_invalidate:
            with self._lock:
                cache_dir = self._paths.cache

                if cache_dir.exists():
                    try:
                        # Remove all cache contents except version file
                        for item in cache_dir.iterdir():
                            if item.name == ".version":
                                continue

                            if item.is_dir():
                                shutil.rmtree(item)
                            else:
                                item.unlink()

                        print(f"Cache invalidated (version: {cached_version} -> {current_version})")
                    except Exception as e:
                        print(f"Warning: Could not clear cache: {e}")
                        return False

                # Write new version
                self._write_cached_version()
                return True

        return False

    def reset(self) -> None:
        """
        Reset the global state (for testing only).

        WARNING: This is intended for testing purposes only.
        Do not use in production code.
        """
        with self._lock:
            GlobalState._instance = None
            GlobalState._paths = None
            GlobalState._initialized = False


# Convenience function for quick access
def get_global_paths() -> GlobalPaths:
    """
    Get global paths configuration.

    Convenience function that creates GlobalState singleton and returns paths.

    Returns:
        GlobalPaths: Immutable paths configuration

    Example:
        >>> from global_state import get_global_paths
        >>> paths = get_global_paths()
        >>> print(f"Cache: {paths.cache}")
    """
    state = GlobalState()
    return state.get_paths()


# Auto-initialize on module import
_global_state = GlobalState()
_global_state.initialize()


# ============================================================================
# TESTS
# ============================================================================

if __name__ == "__main__":
    print("Running GlobalState tests...\n")

    # Test 1: Singleton pattern
    print("Test 1: Singleton pattern")
    state1 = GlobalState()
    state2 = GlobalState()
    assert state1 is state2, "Failed: GlobalState should be singleton"
    print("PASS: Singleton pattern works\n")

    # Test 2: Path configuration
    print("Test 2: Path configuration")
    paths = state1.get_paths()
    assert paths.home == Path.home(), "Failed: home path mismatch"
    assert paths.data.is_absolute(), "Failed: data path not absolute"
    assert paths.cache.is_absolute(), "Failed: cache path not absolute"
    assert paths.config.is_absolute(), "Failed: config path not absolute"
    assert paths.log.is_absolute(), "Failed: log path not absolute"
    assert paths.bin.is_absolute(), "Failed: bin path not absolute"
    assert paths.state.is_absolute(), "Failed: state path not absolute"
    print(f"PASS: All paths are absolute")
    print(f"  Home: {paths.home}")
    print(f"  Data: {paths.data}")
    print(f"  Cache: {paths.cache}")
    print(f"  Config: {paths.config}")
    print(f"  Log: {paths.log}")
    print(f"  Bin: {paths.bin}")
    print(f"  State: {paths.state}\n")

    # Test 3: Platform-specific paths
    print("Test 3: Platform-specific paths")
    platform = sys.platform
    if platform == "linux":
        # On Linux, should follow XDG or use ~/.local/share
        expected_in_path = [".local", ".cache", ".config"]
        assert any(part in str(paths.data) for part in expected_in_path), \
            f"Failed: Linux paths don't follow XDG spec: {paths.data}"
    elif platform == "darwin":
        # On macOS, should use Library
        assert "Library" in str(paths.data), \
            f"Failed: macOS paths don't use Library: {paths.data}"
    elif platform == "win32":
        # On Windows, should use AppData
        assert "AppData" in str(paths.data) or "eversale" in str(paths.data), \
            f"Failed: Windows paths don't use AppData: {paths.data}"
    print(f"PASS: Platform-specific paths ({platform})\n")

    # Test 4: Directory creation
    print("Test 4: Directory creation")
    state1.initialize(create_dirs=True)
    assert paths.data.exists(), "Failed: data directory not created"
    assert paths.cache.exists(), "Failed: cache directory not created"
    assert paths.config.exists(), "Failed: config directory not created"
    assert paths.log.exists(), "Failed: log directory not created"
    assert paths.bin.exists(), "Failed: bin directory not created"
    assert paths.state.exists(), "Failed: state directory not created"
    print("PASS: All directories created\n")

    # Test 5: Version management
    print("Test 5: Version management")
    version = state1.get_version()
    assert version == __version__, f"Failed: version mismatch {version} != {__version__}"
    print(f"PASS: Version is {version}\n")

    # Test 6: Cache invalidation
    print("Test 6: Cache invalidation")
    # Create a test file in cache
    test_file = paths.cache / "test.txt"
    test_file.write_text("test content")
    assert test_file.exists(), "Failed: test file not created"

    # Force invalidation
    result = state1.invalidate_cache(force=True)
    assert result, "Failed: cache invalidation returned False"
    assert not test_file.exists(), "Failed: test file still exists after invalidation"
    print("PASS: Cache invalidation works\n")

    # Test 7: Immutability
    print("Test 7: Path immutability")
    try:
        paths.data = Path("/tmp/new")
        print("FAIL: Paths should be immutable")
    except Exception:
        print("PASS: Paths are immutable (frozen dataclass)\n")

    # Test 8: Thread safety
    print("Test 8: Thread safety")
    import threading
    instances = []

    def create_instance():
        instances.append(GlobalState())

    threads = [threading.Thread(target=create_instance) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All instances should be the same object
    assert all(inst is state1 for inst in instances), "Failed: thread safety broken"
    print("PASS: Thread-safe singleton creation\n")

    # Test 9: Convenience function
    print("Test 9: Convenience function")
    paths2 = get_global_paths()
    assert paths2 == paths, "Failed: convenience function returns different paths"
    print("PASS: Convenience function works\n")

    # Test 10: Multiple initializations (idempotent)
    print("Test 10: Idempotent initialization")
    state1.initialize()
    state1.initialize()
    state1.initialize()
    print("PASS: Multiple initializations are safe\n")

    print("=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
    print("\nGlobal State Manager ready for use!")
    print(f"Data directory: {paths.data}")
    print(f"Cache directory: {paths.cache}")
    print(f"Version: {version}")
