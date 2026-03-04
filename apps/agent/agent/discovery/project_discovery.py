"""Config + scanner birlestirici — tum kaynaklardan proje kesfi."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from agent.discovery.config_loader import load_from_config
from agent.discovery.models import DiscoveredProject
from agent.discovery.scanner import scan_directories

if TYPE_CHECKING:
    from agent.core.config import AgentConfig

logger = structlog.get_logger()


class ProjectDiscovery:
    """YAML config ve dizin taramasini birlestirerek tum projeleri kesfeder."""

    def __init__(self, config: AgentConfig) -> None:
        self._config = config

    async def discover_all(self) -> list[DiscoveredProject]:
        """Tum kaynaklardan projeleri toplar ve deduplicate eder.

        Returns:
            Benzersiz (local_path bazinda) proje listesi.
            Config projeleri onceliklidir (ayni path varsa config kazanir).
        """
        config_projects = load_from_config(self._config.project_config_path)
        scanned_projects = await scan_directories(
            self._config.project_scan_paths,
            self._config.project_scan_depth,
        )

        # Deduplicate by local_path — config projeleri oncelikli
        seen_paths: set[str] = set()
        result: list[DiscoveredProject] = []

        for project in config_projects + scanned_projects:
            if project.local_path not in seen_paths:
                seen_paths.add(project.local_path)
                result.append(project)

        logger.info(
            "project_discovery_completed",
            config_count=len(config_projects),
            scan_count=len(scanned_projects),
            total_unique=len(result),
        )
        return result
