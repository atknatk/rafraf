"""Dizin tarama ile git projeleri kesfi."""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

import structlog

from agent.discovery.models import DiscoveredProject

logger = structlog.get_logger()

# Dosya adi -> teknoloji eslestirmesi
_TECH_MARKERS: dict[str, str] = {
    "Package.swift": "Swift",
    "Podfile": "iOS",
    "requirements.txt": "Python",
    "pyproject.toml": "Python",
    "setup.py": "Python",
    "package.json": "Node.js",
    "tsconfig.json": "TypeScript",
    "Cargo.toml": "Rust",
    "go.mod": "Go",
    "pom.xml": "Java",
    "build.gradle": "Kotlin",
    "build.gradle.kts": "Kotlin",
    "Gemfile": "Ruby",
    "docker-compose.yml": "Docker",
    "docker-compose.yaml": "Docker",
    "Dockerfile": "Docker",
}


def _detect_tech_stack(project_path: Path) -> list[str]:
    """Proje dizinindeki marker dosyalara bakarak tech stack tespit eder."""
    detected: set[str] = set()
    try:
        entries = set(os.listdir(project_path))
    except OSError:
        return []

    for marker, tech in _TECH_MARKERS.items():
        if marker in entries:
            detected.add(tech)

    return sorted(detected)


def _get_git_remote_url(project_path: Path) -> str | None:
    """Git remote origin URL'sini dondurur."""
    try:
        result = subprocess.run(
            ["git", "-C", str(project_path), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def _scan_directory(
    base_path: Path,
    max_depth: int,
    current_depth: int = 0,
) -> list[DiscoveredProject]:
    """Dizini recursive tarayarak git projeleri bulur."""
    results: list[DiscoveredProject] = []

    if current_depth > max_depth:
        return results

    if not base_path.is_dir():
        return results

    # Bu dizin bir git repo mu?
    git_dir = base_path / ".git"
    if git_dir.exists():
        name = base_path.name
        remote_url = _get_git_remote_url(base_path)
        tech_stack = _detect_tech_stack(base_path)

        results.append(
            DiscoveredProject(
                name=name,
                repository_url=remote_url,
                local_path=str(base_path),
                tech_stack=tech_stack,
                source="agent_scan",
            ),
        )
        # Git repo bulduktan sonra alt dizinleri tarama (submodule degilse)
        return results

    # Alt dizinleri tara
    try:
        entries = sorted(base_path.iterdir())
    except PermissionError:
        logger.warning("scan_permission_denied", path=str(base_path))
        return results

    for entry in entries:
        if not entry.is_dir():
            continue
        # Gizli dizinleri ve bilinen gereksiz dizinleri atla
        if entry.name.startswith(".") or entry.name in {
            "node_modules",
            "__pycache__",
            ".venv",
            "venv",
            "build",
            "dist",
        }:
            continue
        results.extend(_scan_directory(entry, max_depth, current_depth + 1))

    return results


async def scan_directories(
    scan_paths: list[str],
    max_depth: int = 2,
) -> list[DiscoveredProject]:
    """Konfigure edilen dizinleri tarayarak git projeleri kesfi eder.

    Args:
        scan_paths: Taranacak ust dizin listesi.
        max_depth: Maksimum tarama derinligi.

    Returns:
        Kesfedilen proje listesi.
    """
    all_projects: list[DiscoveredProject] = []

    for scan_path in scan_paths:
        base = Path(scan_path).expanduser()
        if not base.exists():
            logger.warning("scan_path_not_found", path=str(base))
            continue

        # Filesystem islemlerini thread'e tasi
        projects = await asyncio.to_thread(_scan_directory, base, max_depth)
        all_projects.extend(projects)
        logger.info(
            "scan_path_completed",
            path=str(base),
            found=len(projects),
        )

    logger.info("scan_total_completed", total=len(all_projects))
    return all_projects
