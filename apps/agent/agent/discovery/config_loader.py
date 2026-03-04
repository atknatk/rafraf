"""YAML konfigurasyondan proje yukleme."""

from __future__ import annotations

from pathlib import Path

import structlog

from agent.discovery.models import DiscoveredProject

logger = structlog.get_logger()

# YAML format:
# projects:
#   - name: "RafRaf"
#     path: "/Users/me/code/rafraf"
#     repository_url: "https://github.com/atknatk/rafraf"
#     tech_stack: ["Swift", "Python", "FastAPI"]


def load_from_config(config_path: str) -> list[DiscoveredProject]:
    """YAML proje konfigurasyonunu okur ve DiscoveredProject listesi dondurur.

    Args:
        config_path: YAML dosya yolu.

    Returns:
        Konfigurasyon dosyasindan okunan proje listesi.
    """
    path = Path(config_path).expanduser()

    if not path.exists():
        logger.warning("project_config_not_found", path=str(path))
        return []

    try:
        import yaml  # noqa: PLC0415
    except ImportError:
        logger.warning("pyyaml_not_installed", hint="pip install pyyaml")
        return []

    try:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception:
        logger.exception("project_config_parse_error", path=str(path))
        return []

    if not isinstance(data, dict):
        logger.warning("project_config_invalid_format", path=str(path))
        return []

    projects_raw = data.get("projects", [])
    if not isinstance(projects_raw, list):
        return []

    result: list[DiscoveredProject] = []
    for entry in projects_raw:
        if not isinstance(entry, dict):
            continue

        name = entry.get("name", "")
        local_path = entry.get("path", "")
        if not name or not local_path:
            logger.warning("project_config_entry_missing_fields", entry=entry)
            continue

        result.append(
            DiscoveredProject(
                name=str(name),
                repository_url=entry.get("repository_url"),
                local_path=str(local_path),
                tech_stack=entry.get("tech_stack", []),
                source="agent_config",
            ),
        )

    logger.info("project_config_loaded", count=len(result), path=str(path))
    return result
