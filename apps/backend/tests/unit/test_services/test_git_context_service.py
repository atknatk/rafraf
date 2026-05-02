"""Unit tests for git_context_service."""

from __future__ import annotations

import subprocess
from pathlib import Path

from app.services.git_context_service import build_git_context


class TestBuildGitContextValidRepo:
    """Tests for build_git_context with a valid git repository."""

    async def test_build_git_context_valid_repo(self, tmp_path: Path) -> None:
        """build_git_context should return a non-empty string for a valid git repo."""
        # Initialize a real git repo
        subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.email", "test@test.com"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.name", "Test"],
            check=True,
            capture_output=True,
        )

        # Create a file and commit it
        test_file = tmp_path / "README.md"
        test_file.write_text("# Test Project\n")
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "."],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "feat: initial commit"],
            check=True,
            capture_output=True,
        )

        result = await build_git_context(str(tmp_path))

        assert result != ""
        assert "## Proje Git Durumu" in result
        assert "Son Commitler:" in result
        assert "initial commit" in result

    async def test_build_git_context_with_changes(self, tmp_path: Path) -> None:
        """build_git_context should report uncommitted changes."""
        subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.email", "test@test.com"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.name", "Test"],
            check=True,
            capture_output=True,
        )

        # First commit
        first_file = tmp_path / "main.py"
        first_file.write_text("print('hello')\n")
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "."],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "feat: add main"],
            check=True,
            capture_output=True,
        )

        # Unstaged change
        first_file.write_text("print('hello world')\n")

        result = await build_git_context(str(tmp_path))

        assert result != ""
        assert "Degisiklikler:" in result

    async def test_build_git_context_clean_repo(self, tmp_path: Path) -> None:
        """build_git_context should indicate clean working directory when no changes."""
        subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.email", "test@test.com"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.name", "Test"],
            check=True,
            capture_output=True,
        )

        test_file = tmp_path / "app.py"
        test_file.write_text("pass\n")
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "."],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "chore: initial"],
            check=True,
            capture_output=True,
        )

        result = await build_git_context(str(tmp_path))

        assert result != ""
        assert "Temiz calisma dizini" in result


class TestBuildGitContextNotARepo:
    """Tests for build_git_context with non-git directories."""

    async def test_build_git_context_not_a_repo(self, tmp_path: Path) -> None:
        """build_git_context should return empty string for non-git directory."""
        result = await build_git_context(str(tmp_path))

        assert result == ""

    async def test_build_git_context_nonexistent_path(self) -> None:
        """build_git_context should return empty string for nonexistent path."""
        result = await build_git_context("/nonexistent/path/that/does/not/exist")

        assert result == ""
