"""
Security tests for file_handler.py

Tests for:
1. Path traversal protection
2. Workspace boundary validation
3. Protected file detection (exact matching vs substring bypass)
4. Symlink resolution
"""

import os
import sys
import tempfile
from pathlib import Path
import pytest

# Add parent directory to path to import file_handler
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.file_handler import FileHandler


class TestPathTraversalProtection:
    """Test path traversal vulnerability fixes."""

    def setup_method(self):
        """Create a temporary workspace for testing."""
        self.workspace = tempfile.mkdtemp()
        self.handler = FileHandler(workspace_root=self.workspace)

        # Create test files
        self.test_file = Path(self.workspace) / "test.txt"
        self.test_file.write_text("safe content")

        # Create a file outside workspace
        self.outside_workspace = tempfile.mkdtemp()
        self.outside_file = Path(self.outside_workspace) / "outside.txt"
        self.outside_file.write_text("outside content")

    def teardown_method(self):
        """Clean up temporary files."""
        import shutil
        if Path(self.workspace).exists():
            shutil.rmtree(self.workspace)
        if Path(self.outside_workspace).exists():
            shutil.rmtree(self.outside_workspace)

    def test_basic_path_traversal_blocked(self):
        """Test that basic ../ path traversal is blocked."""
        evil_path = os.path.join(self.workspace, "../../../etc/passwd")

        is_valid, error, _ = self.handler.validate_path(evil_path)
        assert not is_valid, "Path traversal should be blocked"
        assert "outside workspace boundary" in error.lower()

    def test_nested_path_traversal_blocked(self):
        """Test that nested path traversal attempts are blocked."""
        evil_path = os.path.join(self.workspace, "subdir/../../../../../../etc/passwd")

        is_valid, error, _ = self.handler.validate_path(evil_path)
        assert not is_valid, "Nested path traversal should be blocked"

    def test_dot_slash_traversal_resolved(self):
        """Test that ./././ patterns are resolved correctly."""
        tricky_path = os.path.join(self.workspace, "./././test.txt")

        is_valid, error, resolved = self.handler.validate_path(tricky_path)
        assert is_valid, f"Valid path should be allowed: {error}"
        assert resolved == self.test_file.resolve()

    def test_absolute_path_outside_workspace_blocked(self):
        """Test that absolute paths outside workspace are blocked."""
        is_valid, error, _ = self.handler.validate_path(str(self.outside_file))
        assert not is_valid, "Absolute path outside workspace should be blocked"
        assert "outside workspace boundary" in error.lower()

    def test_symlink_escape_blocked(self):
        """Test that symlinks pointing outside workspace are blocked."""
        # Create symlink inside workspace pointing outside
        symlink_path = Path(self.workspace) / "evil_link"
        try:
            symlink_path.symlink_to(self.outside_file)

            is_valid, error, _ = self.handler.validate_path(str(symlink_path))
            assert not is_valid, "Symlink escape should be blocked"
            assert "outside workspace boundary" in error.lower()
        except OSError:
            # Skip test if symlinks not supported (Windows without admin)
            pytest.skip("Symlinks not supported on this system")

    def test_valid_path_allowed(self):
        """Test that valid paths within workspace are allowed."""
        is_valid, error, resolved = self.handler.validate_path(str(self.test_file))
        assert is_valid, f"Valid path should be allowed: {error}"
        assert resolved == self.test_file.resolve()

    def test_read_file_blocks_traversal(self):
        """Test that read_file blocks path traversal attempts."""
        evil_path = os.path.join(self.workspace, "../../../etc/passwd")

        result = self.handler.read_file(evil_path)
        assert not result.success, "Read should fail for path traversal"
        assert "path validation failed" in result.error.lower()

    def test_write_file_blocks_traversal(self):
        """Test that write_file blocks path traversal attempts."""
        evil_path = os.path.join(self.workspace, "../../../tmp/evil.txt")

        success, message = self.handler.write_file(evil_path, "evil content")
        assert not success, "Write should fail for path traversal"
        assert "path validation failed" in message.lower()


class TestProtectedFileDetection:
    """Test protected file detection with exact matching."""

    def setup_method(self):
        """Create a temporary workspace for testing."""
        self.workspace = tempfile.mkdtemp()
        self.handler = FileHandler(workspace_root=self.workspace, allow_protected=False)

    def teardown_method(self):
        """Clean up temporary files."""
        import shutil
        if Path(self.workspace).exists():
            shutil.rmtree(self.workspace)

    def test_env_exact_match_blocked(self):
        """Test that .env is blocked (exact match)."""
        env_file = Path(self.workspace) / ".env"
        env_file.write_text("SECRET=value")

        is_protected, reason = self.handler.is_protected_file(str(env_file))
        assert is_protected, ".env should be protected"
        assert "exact match" in reason.lower()

    def test_env_backup_allowed(self):
        """Test that .env-backup is NOT blocked (no substring matching)."""
        backup_file = Path(self.workspace) / ".env-backup"
        backup_file.write_text("OLD_SECRET=value")

        is_protected, reason = self.handler.is_protected_file(str(backup_file))
        assert not is_protected, ".env-backup should NOT be protected (not exact match)"

    def test_test_env_allowed(self):
        """Test that test.env is NOT blocked."""
        test_env = Path(self.workspace) / "test.env"
        test_env.write_text("TEST=value")

        is_protected, reason = self.handler.is_protected_file(str(test_env))
        assert not is_protected, "test.env should NOT be protected"

    def test_env_glob_pattern_blocked(self):
        """Test that .env.* patterns are blocked."""
        env_custom = Path(self.workspace) / ".env.custom"
        env_custom.write_text("CUSTOM=value")

        is_protected, reason = self.handler.is_protected_file(str(env_custom))
        assert is_protected, ".env.custom should be protected (glob match)"

    def test_id_rsa_exact_blocked(self):
        """Test that id_rsa is blocked (exact match)."""
        key_file = Path(self.workspace) / "id_rsa"
        key_file.write_text("PRIVATE KEY")

        is_protected, reason = self.handler.is_protected_file(str(key_file))
        assert is_protected, "id_rsa should be protected"

    def test_my_id_rsa_blocked_by_glob(self):
        """Test that my_id_rsa IS blocked by glob pattern."""
        my_key = Path(self.workspace) / "my_id_rsa"
        my_key.write_text("KEY DATA")

        is_protected, reason = self.handler.is_protected_file(str(my_key))
        # This SHOULD be protected because we have a glob pattern *_rsa
        # which is more secure - catches variants like my_id_rsa, backup_id_rsa, etc.
        assert is_protected, "my_id_rsa should be protected by glob pattern *_rsa"
        assert "glob match" in reason.lower()

    def test_pem_extension_blocked(self):
        """Test that .pem extension is blocked."""
        pem_file = Path(self.workspace) / "certificate.pem"
        pem_file.write_text("CERTIFICATE")

        is_protected, reason = self.handler.is_protected_file(str(pem_file))
        assert is_protected, ".pem files should be protected"

    def test_key_extension_blocked(self):
        """Test that .key extension is blocked."""
        key_file = Path(self.workspace) / "private.key"
        key_file.write_text("KEY")

        is_protected, reason = self.handler.is_protected_file(str(key_file))
        assert is_protected, ".key files should be protected"

    def test_credentials_json_exact_blocked(self):
        """Test that credentials.json is blocked (exact match)."""
        creds = Path(self.workspace) / "credentials.json"
        creds.write_text("{}")

        is_protected, reason = self.handler.is_protected_file(str(creds))
        assert is_protected, "credentials.json should be protected"

    def test_test_credentials_json_allowed(self):
        """Test that test_credentials.json is NOT blocked."""
        test_creds = Path(self.workspace) / "test_credentials.json"
        test_creds.write_text("{}")

        is_protected, reason = self.handler.is_protected_file(str(test_creds))
        assert not is_protected, "test_credentials.json should NOT be protected"

    def test_protected_file_read_blocked(self):
        """Test that reading protected files is blocked."""
        env_file = Path(self.workspace) / ".env"
        env_file.write_text("SECRET=value")

        result = self.handler.read_file(str(env_file))
        assert not result.success, "Reading .env should fail"
        assert "protected file" in result.error.lower()

    def test_protected_file_write_blocked(self):
        """Test that writing to protected files is blocked."""
        env_path = str(Path(self.workspace) / ".env")

        success, message = self.handler.write_file(env_path, "SECRET=newvalue")
        assert not success, "Writing to .env should fail"
        assert "protected file" in message.lower()


class TestWorkspaceBoundary:
    """Test workspace boundary enforcement."""

    def setup_method(self):
        """Create nested workspace structure."""
        self.root = tempfile.mkdtemp()
        self.workspace = Path(self.root) / "workspace"
        self.workspace.mkdir()
        self.handler = FileHandler(workspace_root=str(self.workspace))

        # Create files
        (self.workspace / "inside.txt").write_text("inside")
        (Path(self.root) / "outside.txt").write_text("outside")

    def teardown_method(self):
        """Clean up."""
        import shutil
        if Path(self.root).exists():
            shutil.rmtree(self.root)

    def test_workspace_boundary_enforced(self):
        """Test that files outside workspace are inaccessible."""
        outside_path = str(Path(self.root) / "outside.txt")

        result = self.handler.read_file(outside_path)
        assert not result.success, "Should not access files outside workspace"
        assert "outside workspace boundary" in result.error.lower()

    def test_inside_workspace_accessible(self):
        """Test that files inside workspace are accessible."""
        inside_path = str(self.workspace / "inside.txt")

        result = self.handler.read_file(inside_path)
        assert result.success, "Should access files inside workspace"
        assert result.content


class TestAllowProtectedFlag:
    """Test the allow_protected flag functionality."""

    def setup_method(self):
        """Create workspace with protected file."""
        self.workspace = tempfile.mkdtemp()
        self.env_file = Path(self.workspace) / ".env"
        self.env_file.write_text("SECRET=value")

    def teardown_method(self):
        """Clean up."""
        import shutil
        if Path(self.workspace).exists():
            shutil.rmtree(self.workspace)

    def test_protected_blocked_by_default(self):
        """Test that protected files are blocked by default."""
        handler = FileHandler(workspace_root=self.workspace, allow_protected=False)

        result = handler.read_file(str(self.env_file))
        assert not result.success, "Protected files should be blocked by default"

    def test_protected_allowed_with_flag(self):
        """Test that protected files can be accessed with allow_protected=True."""
        handler = FileHandler(workspace_root=self.workspace, allow_protected=True)

        result = handler.read_file(str(self.env_file))
        assert result.success, "Protected files should be accessible with allow_protected=True"


if __name__ == "__main__":
    # Run tests
    print("Running security tests...")
    pytest.main([__file__, "-v", "--tb=short"])
