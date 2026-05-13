"""Tests for pipeline/sandbox.py — git worktree sandbox manager."""

import os
import time
import shutil
import subprocess
from pathlib import Path

import pytest
from pipeline.sandbox import SandboxManager, SandboxCreateError, _sanitize


class TestSanitize:
    """Test task_id to directory name sanitization."""

    def test_simple_id_unchanged(self):
        assert _sanitize("task-fix-bug") == "task-fix-bug"

    def test_slashes_replaced(self):
        assert _sanitize("task/a/b") == "task_a_b"

    def test_colons_replaced(self):
        assert _sanitize("task:1") == "task_1"

    def test_windows_forbidden_chars(self):
        sanitized = _sanitize('task<with>:"bad|?chars*')
        assert "/" not in sanitized
        assert "\\" not in sanitized
        assert ":" not in sanitized
        assert "<" not in sanitized
        assert ">" not in sanitized
        assert "|" not in sanitized
        assert "?" not in sanitized
        assert "*" not in sanitized


class TestSandboxManager:
    """Test git worktree sandbox lifecycle.

    Requires git and a real git repo (uses the temp project from conftest).
    """

    @pytest.fixture
    def git_repo(self, tmp_path):
        """Create a minimal git repo for sandbox testing."""
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.email", "test@test.com"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.name", "Test"],
            check=True, capture_output=True,
        )
        # Create initial commit so HEAD exists
        (repo / "README.md").write_text("# Test")
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "initial"],
            check=True, capture_output=True,
        )
        return repo

    def test_create_destroy_worktree(self, git_repo, tmp_path):
        """Create sandbox, verify it exists, destroy it, verify gone."""
        ai_dev = tmp_path / "ai-dev"
        ai_dev.mkdir()

        sm = SandboxManager(git_repo, ai_dev)
        sandbox_path = sm.create("test-task")
        assert sandbox_path.exists()
        assert (sandbox_path / ".git").exists()  # worktree has .git file
        assert (sandbox_path / "README.md").exists()

        sm.destroy()
        assert not sandbox_path.exists()

    def test_sync_outputs_copies_files(self, git_repo, tmp_path):
        """Files created in sandbox should be synced to real project."""
        ai_dev = tmp_path / "ai-dev"
        ai_dev.mkdir()

        sm = SandboxManager(git_repo, ai_dev)
        sandbox_path = sm.create("test-sync")

        # Create files in sandbox
        (sandbox_path / "src").mkdir(exist_ok=True)
        (sandbox_path / "src" / "newfile.java").write_text("public class Test {}")
        (sandbox_path / "config.yml").write_text("key: value")

        synced = sm.sync_outputs(["src/newfile.java", "config.yml"])
        assert len(synced) == 2
        assert "src/newfile.java" in synced
        assert "config.yml" in synced
        assert (git_repo / "src" / "newfile.java").exists()
        assert (git_repo / "config.yml").exists()
        assert (git_repo / "src" / "newfile.java").read_text() == "public class Test {}"

        sm.destroy()

    def test_sync_outputs_skips_missing(self, git_repo, tmp_path):
        """Missing files should be skipped gracefully."""
        ai_dev = tmp_path / "ai-dev"
        ai_dev.mkdir()

        sm = SandboxManager(git_repo, ai_dev)
        sm.create("test-missing")

        synced = sm.sync_outputs(["nonexistent.md"])
        assert len(synced) == 0

        sm.destroy()

    def test_cleanup_orphaned_removes_leftovers(self, git_repo, tmp_path):
        """Orphaned sandbox directories should be cleaned up."""
        ai_dev = tmp_path / "ai-dev"
        sandboxes_dir = ai_dev / "sandboxes"
        sandboxes_dir.mkdir(parents=True)

        # Create a fake orphaned directory (not a real worktree)
        orphan = sandboxes_dir / "orphaned-task"
        orphan.mkdir()
        (orphan / "some_file.txt").write_text("orphan data")

        cleaned = SandboxManager.cleanup_orphaned(git_repo, ai_dev)
        assert "orphaned-task" in cleaned
        assert not orphan.exists()

    def test_create_handles_preexisting_sandbox(self, git_repo, tmp_path):
        """Creating a sandbox when one already exists should replace it."""
        ai_dev = tmp_path / "ai-dev"
        ai_dev.mkdir()

        sm1 = SandboxManager(git_repo, ai_dev)
        path1 = sm1.create("test-recreate")
        assert path1.exists()

        # Do NOT destroy, create again (simulates crash recovery)
        sm2 = SandboxManager(git_repo, ai_dev)
        path2 = sm2.create("test-recreate")
        assert path2.exists()
        assert path2 == path1

        sm2.destroy()
        assert not path2.exists()

    def test_detect_extra_modifications(self, git_repo, tmp_path):
        """Should detect files modified outside declared outputs."""
        ai_dev = tmp_path / "ai-dev"
        ai_dev.mkdir()

        sm = SandboxManager(git_repo, ai_dev)
        sm.create("test-extra")

        # Modify a file that was NOT declared as output
        readme = sm._sandbox_path / "README.md"
        readme.write_text("# Modified by goose")

        extra = sm.detect_extra_modifications({"declared_output.java"})
        assert "README.md" in extra

        sm.destroy()

    def test_create_fails_for_nonexistent_repo(self, tmp_path):
        """SandboxCreateError should be raised for non-git directory."""
        non_repo = tmp_path / "not-a-repo"
        non_repo.mkdir()
        ai_dev = tmp_path / "ai-dev"
        ai_dev.mkdir()

        sm = SandboxManager(non_repo, ai_dev)
        with pytest.raises(SandboxCreateError):
            sm.create("test-fail")
