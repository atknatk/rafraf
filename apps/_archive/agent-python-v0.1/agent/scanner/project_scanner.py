"""Yerel klasorlerde git projelerini tarar ve ProjectSyncEntry listesi dondurur."""

from __future__ import annotations

import os
from pathlib import Path

from agent.core.protocol import ProjectSyncEntry

# Dosya/klasor isimlerine gore tech stack tespiti
TECH_MARKERS: dict[str, list[str]] = {
    "pyproject.toml": ["Python"],
    "requirements.txt": ["Python"],
    "setup.py": ["Python"],
    "package.json": ["Node.js"],
    "Cargo.toml": ["Rust"],
    "go.mod": ["Go"],
    "Podfile": ["iOS", "Swift"],
    "build.gradle": ["Android", "Kotlin"],
    "build.gradle.kts": ["Android", "Kotlin"],
    "pom.xml": ["Java"],
    "Gemfile": ["Ruby"],
    "mix.exs": ["Elixir"],
    "pubspec.yaml": ["Flutter", "Dart"],
    "CMakeLists.txt": ["C++"],
    "Makefile": ["C/C++"],
}

# Glob pattern ile tespit edilenler
GLOB_MARKERS: dict[str, list[str]] = {
    "*.xcodeproj": ["Swift", "iOS"],
    "*.xcworkspace": ["Swift", "iOS"],
}

# Taramadan hariç tutulacak klasor isimleri
SKIP_DIRS: frozenset[str] = frozenset(
    {
        "node_modules",
        ".git",
        ".svn",
        "__pycache__",
        ".cache",
        "dist",
        "build",
        "target",
        ".build",
        "vendor",
        "Library",
        "Applications",
        "System",
        "Volumes",
    }
)


def _detect_tech_stack(project_path: Path) -> list[str]:
    """Klasordeki marker dosyalara gore tech stack tespit eder."""
    stack: set[str] = set()

    for marker, techs in TECH_MARKERS.items():
        if (project_path / marker).exists():
            stack.update(techs)

    for pattern, techs in GLOB_MARKERS.items():
        if any(project_path.glob(pattern)):
            stack.update(techs)

    return sorted(stack)


def _get_repo_url(project_path: Path) -> str | None:
    """Git config'ten remote origin URL'yi okur."""
    git_config = project_path / ".git" / "config"
    if not git_config.exists():
        return None
    try:
        text = git_config.read_text(encoding="utf-8")
        in_origin = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped == '[remote "origin"]':
                in_origin = True
            elif stripped.startswith("[") and in_origin:
                in_origin = False
            elif in_origin and stripped.startswith("url = "):
                return stripped.split("url = ", 1)[1].strip()
    except OSError:
        pass
    return None


def _scan_recursive(
    path: Path,
    remaining_depth: int,
    entries: list[ProjectSyncEntry],
    seen: set[str],
) -> None:
    """Verilen dizini recursive olarak tarar."""
    path_str = str(path)
    if path_str in seen:
        return

    if (path / ".git").is_dir():
        seen.add(path_str)
        entries.append(
            ProjectSyncEntry(
                name=path.name,
                repository_url=_get_repo_url(path),
                local_path=path_str,
                tech_stack=_detect_tech_stack(path),
                source="agent_scan",
            ),
        )
        return  # Git repo bulununca alt dizinlere girme

    if remaining_depth <= 0:
        return

    try:
        for child in sorted(path.iterdir()):
            if not child.is_dir():
                continue
            if child.name in SKIP_DIRS or child.name.startswith("."):
                continue
            _scan_recursive(child, remaining_depth - 1, entries, seen)
    except PermissionError:
        pass
    except OSError:
        pass


def scan_projects(scan_paths: list[str], max_depth: int) -> list[ProjectSyncEntry]:
    """Verilen kok dizinlerde .git olan klasorleri tarar.

    Args:
        scan_paths: Taranacak kok dizin yollari (~ desteklenir).
        max_depth: Maksimum tarama derinligi.

    Returns:
        Kesfedilen projelerin listesi.
    """
    entries: list[ProjectSyncEntry] = []
    seen: set[str] = set()

    for root_str in scan_paths:
        root = Path(os.path.expanduser(root_str)).resolve()
        if not root.exists() or not root.is_dir():
            continue
        _scan_recursive(root, max_depth, entries, seen)

    return entries
