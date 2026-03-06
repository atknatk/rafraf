"""Unit tests for git_diff_service."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.services.git_diff_service import get_project_diff


def _init_repo(tmp_path: Path) -> None:
    """Temp dir'de bos bir git repo olusturur."""
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


def _initial_commit(tmp_path: Path, filename: str = "main.py", content: str = "x = 1\n") -> None:
    """Ilk commit'i olusturur."""
    (tmp_path / filename).write_text(content)
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


class TestGetProjectDiffWithChanges:
    """git diff HEAD degisiklik oldugunda payload doner."""

    async def test_get_project_diff_with_changes(self, tmp_path: Path) -> None:
        """Staged degisiklikler varsa CodeDiffPayload doner."""
        _init_repo(tmp_path)
        _initial_commit(tmp_path, "app.py", "x = 1\n")

        # Dosyayi degistir ve stage'e al
        (tmp_path / "app.py").write_text("x = 2\ny = 3\n")
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "."],
            check=True,
            capture_output=True,
        )

        result = await get_project_diff(str(tmp_path))

        assert result is not None
        assert result.files_changed >= 1
        assert result.total_additions >= 1
        assert result.total_deletions >= 1
        assert result.project_path == str(tmp_path)
        assert any(f.file_path == "app.py" for f in result.files)

    async def test_get_project_diff_unstaged_changes(self, tmp_path: Path) -> None:
        """Stage edilmemis degisiklikler de diff'e girer (git diff HEAD)."""
        _init_repo(tmp_path)
        _initial_commit(tmp_path, "mod.py", "a = 1\n")

        # Sadece working tree'yi degistir (stage yok)
        (tmp_path / "mod.py").write_text("a = 1\nb = 2\n")

        result = await get_project_diff(str(tmp_path))

        assert result is not None
        assert result.files_changed >= 1


class TestGetProjectDiffNoChanges:
    """Degisiklik yoksa None doner."""

    async def test_get_project_diff_no_changes(self, tmp_path: Path) -> None:
        """Temiz calisma dizini icin None doner."""
        _init_repo(tmp_path)
        _initial_commit(tmp_path)

        result = await get_project_diff(str(tmp_path))

        assert result is None

    async def test_get_project_diff_empty_repo_no_commit(self, tmp_path: Path) -> None:
        """Hicbir commit olmayan repo icin None doner (git diff HEAD hata verir)."""
        _init_repo(tmp_path)
        # Commit yok — git diff HEAD basarisiz olur

        result = await get_project_diff(str(tmp_path))

        assert result is None


class TestGetProjectDiffInvalidPath:
    """Gecersiz path icin None doner."""

    async def test_get_project_diff_invalid_path(self) -> None:
        """Mevcut olmayan path icin None doner."""
        result = await get_project_diff("/nonexistent/path/that/does/not/exist")

        assert result is None

    async def test_get_project_diff_not_a_git_repo(self, tmp_path: Path) -> None:
        """Git repo olmayan dizin icin None doner."""
        result = await get_project_diff(str(tmp_path))

        assert result is None
