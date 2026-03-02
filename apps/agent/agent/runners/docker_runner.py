"""Docker Compose runner - compose up/down/restart/logs/health islemleri.

Docker SDK for Python ve Compose v2 CLI uzerinden calisan runner.
Sadece izin verilen compose dosyalari ile calisabilir (guvenlik).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from agent.runners.base import BaseRunner

logger = structlog.get_logger()

# Desteklenen aksiyonlar
_SUPPORTED_ACTIONS: frozenset[str] = frozenset(
    [
        "compose_up",
        "compose_down",
        "compose_restart",
        "compose_logs",
        "health_check",
        "container_status",
    ],
)

# Varsayilan degerler
_DEFAULT_TIMEOUT: int = 120
_DEFAULT_TAIL_LINES: int = 100
_MAX_OUTPUT_CHARS: int = 50_000
_MAX_LOG_CHARS: int = 100_000

_DEFAULT_ALLOWED_COMPOSE_FILES: list[str] = [
    "docker-compose.yml",
    "docker-compose.yaml",
    "docker-compose.dev.yml",
    "docker-compose.dev.yaml",
    "docker-compose.test.yml",
    "docker-compose.test.yaml",
    "compose.yml",
    "compose.yaml",
]


class DockerRunnerError(Exception):
    """Docker runner'a ozel hata sinifi."""


class ProjectEntry:
    """Proje konfigurasyonu.

    Args:
        slug: Proje tanimlayicisi.
        path: Proje dizin yolu.
        docker_compose: Compose dosya adi.
    """

    __slots__ = ("slug", "path", "docker_compose")

    def __init__(
        self,
        slug: str,
        path: str,
        docker_compose: str = "docker-compose.yml",
    ) -> None:
        self.slug = slug
        self.path = path
        self.docker_compose = docker_compose


class DockerRunner(BaseRunner):
    """Docker Compose islemlerini calistiran runner.

    Compose up/down/restart, log okuma, health check ve container
    status raporlama islemlerini gerceklestirir.

    Args:
        projects: Proje slug -> ProjectEntry eslestirmesi.
        allowed_compose_files: Izin verilen compose dosya adlari.
        command_timeout: Varsayilan komut timeout suresi (saniye).
    """

    def __init__(
        self,
        projects: dict[str, ProjectEntry],
        allowed_compose_files: list[str] | None = None,
        command_timeout: int = _DEFAULT_TIMEOUT,
    ) -> None:
        self._projects = projects
        self._allowed_compose_files: set[str] = set(
            allowed_compose_files or _DEFAULT_ALLOWED_COMPOSE_FILES,
        )
        self._command_timeout = command_timeout

    @property
    def tool_name(self) -> str:
        """Runner'in destekledigi tool adi."""
        return "docker"

    def _resolve_project(self, project_slug: str) -> tuple[str, str]:
        """Proje slug'indan path ve compose dosyasini cikarir.

        Args:
            project_slug: Proje tanimlayicisi.

        Returns:
            (project_path, compose_file) tuple'i.

        Raises:
            DockerRunnerError: Proje bulunamadi, compose dosyasi izinsiz veya mevcut degil.
        """
        project = self._projects.get(project_slug)
        if project is None:
            msg = f"Proje bulunamadi: {project_slug}"
            raise DockerRunnerError(msg)

        compose_file = project.docker_compose
        project_path = project.path

        # Izin verilen compose dosyasi mi?
        if compose_file not in self._allowed_compose_files:
            msg = (
                f"Compose dosyasi izin verilmemis: {compose_file}. "
                f"Izin verilenler: {sorted(self._allowed_compose_files)}"
            )
            raise DockerRunnerError(msg)

        # Compose dosyasi fiziksel olarak mevcut mu?
        compose_path = Path(project_path) / compose_file
        if not compose_path.is_file():
            msg = f"Compose dosyasi bulunamadi: {compose_path}"
            raise DockerRunnerError(msg)

        return project_path, compose_file

    async def _run_compose_command(
        self,
        project_path: str,
        compose_file: str,
        args: list[str],
        timeout: int | None = None,
    ) -> dict[str, object]:
        """docker compose komutunu async subprocess ile calistirir.

        Args:
            project_path: Proje dizini.
            compose_file: Compose dosya adi.
            args: docker compose sonrasi arguman listesi.
            timeout: Komut timeout suresi (saniye).

        Returns:
            success, output, error anahtarlari iceren dictionary.
        """
        cmd = ["docker", "compose", "-f", compose_file, *args]
        effective_timeout = timeout or self._command_timeout

        await logger.ainfo(
            "Docker compose komutu calistiriliyor",
            cmd=" ".join(cmd),
            cwd=project_path,
            timeout=effective_timeout,
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=project_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=effective_timeout,
            )

            stdout_str = stdout_bytes.decode("utf-8", errors="replace")[:_MAX_OUTPUT_CHARS]
            stderr_str = stderr_bytes.decode("utf-8", errors="replace")[:_MAX_OUTPUT_CHARS]

            return {
                "success": proc.returncode == 0,
                "output": stdout_str,
                "error": stderr_str if proc.returncode != 0 else None,
                "return_code": proc.returncode,
            }

        except TimeoutError:
            await logger.awarning(
                "Docker compose komutu zaman asimi",
                cmd=" ".join(cmd),
                timeout=effective_timeout,
            )
            return {
                "success": False,
                "output": "",
                "error": f"Komut {effective_timeout} saniye icinde tamamlanamadi",
            }

    async def execute(self, action: str, params: dict[str, object]) -> dict[str, object]:
        """Docker aksiyonunu calistirir.

        Args:
            action: Aksiyon adi (compose_up, compose_down, vb.).
            params: Aksiyon parametreleri.

        Returns:
            Sonuc dictionary'si.

        Raises:
            ValueError: Bilinmeyen aksiyon.
        """
        if action not in _SUPPORTED_ACTIONS:
            msg = (
                f"Bilinmeyen Docker aksiyonu: {action}. "
                f"Desteklenenler: {sorted(_SUPPORTED_ACTIONS)}"
            )
            raise ValueError(msg)

        project_slug = params.get("project_slug")
        if not isinstance(project_slug, str) or not project_slug:
            return {
                "success": False,
                "error": "project_slug parametresi zorunlu (string)",
            }

        try:
            return await self._dispatch_action(action, project_slug, params)
        except DockerRunnerError as exc:
            return {
                "success": False,
                "error": str(exc),
            }

    async def _dispatch_action(
        self,
        action: str,
        project_slug: str,
        params: dict[str, object],
    ) -> dict[str, object]:
        """Aksiyonu ilgili metoda yonlendirir."""
        if action == "compose_up":
            return await self._compose_up(project_slug, params)
        if action == "compose_down":
            return await self._compose_down(project_slug, params)
        if action == "compose_restart":
            return await self._compose_restart(project_slug, params)
        if action == "compose_logs":
            return await self._compose_logs(project_slug, params)
        if action == "health_check":
            return await self._health_check(project_slug)
        if action == "container_status":
            return await self._container_status(project_slug)

        msg = f"Beklenmeyen aksiyon: {action}"
        raise ValueError(msg)

    async def _compose_up(
        self,
        project_slug: str,
        params: dict[str, object],
    ) -> dict[str, object]:
        """docker compose up -d calistirir."""
        project_path, compose_file = self._resolve_project(project_slug)

        args: list[str] = ["up"]

        # Detach modu (varsayilan: True)
        detach = params.get("detach", True)
        if detach:
            args.append("-d")

        # Belirli servisler
        services = params.get("services")
        if isinstance(services, list):
            args.extend(str(s) for s in services)

        return await self._run_compose_command(project_path, compose_file, args)

    async def _compose_down(
        self,
        project_slug: str,
        params: dict[str, object],
    ) -> dict[str, object]:
        """docker compose down calistirir."""
        project_path, compose_file = self._resolve_project(project_slug)

        args: list[str] = ["down"]

        # Volume silme opsiyonu
        remove_volumes = params.get("remove_volumes", False)
        if remove_volumes:
            args.append("-v")

        return await self._run_compose_command(project_path, compose_file, args)

    async def _compose_restart(
        self,
        project_slug: str,
        params: dict[str, object],
    ) -> dict[str, object]:
        """docker compose restart calistirir."""
        project_path, compose_file = self._resolve_project(project_slug)

        args: list[str] = ["restart"]

        # Belirli servisler
        services = params.get("services")
        if isinstance(services, list):
            args.extend(str(s) for s in services)

        return await self._run_compose_command(project_path, compose_file, args)

    async def _compose_logs(
        self,
        project_slug: str,
        params: dict[str, object],
    ) -> dict[str, object]:
        """docker compose logs calistirir."""
        project_path, compose_file = self._resolve_project(project_slug)

        # Tail satir sayisi
        tail = params.get("tail", _DEFAULT_TAIL_LINES)
        if not isinstance(tail, int) or tail < 1:
            tail = _DEFAULT_TAIL_LINES

        args: list[str] = ["logs", "--no-color", f"--tail={tail}"]

        # Since parametresi (ornek: "1h", "30m")
        since = params.get("since")
        if isinstance(since, str) and since:
            args.extend(["--since", since])

        # Belirli servis
        service = params.get("service")
        if isinstance(service, str) and service:
            args.append(service)

        result = await self._run_compose_command(project_path, compose_file, args)

        # Log ciktisini sinirlama
        output = result.get("output", "")
        if isinstance(output, str) and len(output) > _MAX_LOG_CHARS:
            result["output"] = output[-_MAX_LOG_CHARS:]
            result["truncated"] = True

        return result

    async def _health_check(self, project_slug: str) -> dict[str, object]:
        """Container'larin saglik durumunu kontrol eder.

        Docker SDK uzerinden container inspect ile health status okur.
        """
        project_path, compose_file = self._resolve_project(project_slug)

        # Calisan container'lari compose ps ile dogrula
        ps_result = await self._run_compose_command(
            project_path,
            compose_file,
            ["ps", "-a", "--format", "json"],
        )

        if not ps_result.get("success"):
            return ps_result

        # Docker SDK ile container health bilgisi al (blocking -> thread pool)
        loop = asyncio.get_running_loop()
        containers_info = await loop.run_in_executor(
            None,
            self._inspect_project_containers,
            project_slug,
        )

        # Hata kontrolu
        if len(containers_info) == 1 and "error" in containers_info[0]:
            return {
                "success": False,
                "error": containers_info[0].get("error", "Bilinmeyen hata"),
            }

        all_healthy = all(
            c.get("health") in ("healthy", None, "")
            for c in containers_info
            if c.get("status") == "running"
        )

        return {
            "success": True,
            "healthy": all_healthy,
            "containers": containers_info,
        }

    def _inspect_project_containers(
        self,
        project_slug: str,
    ) -> list[dict[str, object]]:
        """Docker SDK ile container bilgilerini toplar (senkron).

        Docker SDK blocking oldugu icin run_in_executor ile cagirilmalidir.
        """
        try:
            import docker as docker_lib
        except ImportError:
            return [{"error": "Docker SDK yuklu degil"}]

        try:
            client = docker_lib.from_env()
        except Exception as exc:
            return [{"error": f"Docker daemon'a baglanilamadi: {exc}"}]

        try:
            containers = client.containers.list(
                all=True,
                filters={"label": f"com.docker.compose.project={project_slug}"},
            )
        except Exception as exc:
            return [{"error": f"Container listesi alinamadi: {exc}"}]
        finally:
            client.close()

        containers_info: list[dict[str, object]] = []
        for container in containers:
            info = _extract_container_info(container)
            containers_info.append(info)

        return containers_info

    async def _container_status(self, project_slug: str) -> dict[str, object]:
        """Proje container'larinin durum raporunu dondurur."""
        project_path, compose_file = self._resolve_project(project_slug)

        # compose ps calistir
        result = await self._run_compose_command(
            project_path,
            compose_file,
            ["ps", "-a", "--format", "table {{.Name}}\t{{.Status}}\t{{.Ports}}"],
        )

        if not result.get("success"):
            return result

        # Docker SDK ile detayli bilgi al
        loop = asyncio.get_running_loop()
        containers_info = await loop.run_in_executor(
            None,
            self._inspect_project_containers,
            project_slug,
        )

        # Hata kontrolu
        if len(containers_info) == 1 and "error" in containers_info[0]:
            return {
                "success": False,
                "error": containers_info[0].get("error", "Bilinmeyen hata"),
            }

        running_count = sum(1 for c in containers_info if c.get("status") == "running")
        total_count = len(containers_info)

        return {
            "success": True,
            "containers": containers_info,
            "running_count": running_count,
            "total_count": total_count,
        }


def _extract_container_info(container: object) -> dict[str, object]:
    """Tek bir Docker container'dan bilgi cikarir.

    Args:
        container: docker.models.containers.Container nesnesi.

    Returns:
        Container bilgilerini iceren dictionary.
    """
    # Container attributes (docker SDK Container nesnesi)
    attrs: dict[str, object] = getattr(container, "attrs", {}) or {}
    state: dict[str, object] = attrs.get("State", {})  # type: ignore[assignment]

    # Health status
    health_data = state.get("Health")
    health_status: str | None = None
    if isinstance(health_data, dict):
        raw_status = health_data.get("Status")
        if isinstance(raw_status, str):
            health_status = raw_status

    # Port bilgileri
    network_settings = attrs.get("NetworkSettings", {})
    ports_data: dict[str, object] = {}
    if isinstance(network_settings, dict):
        raw_ports = network_settings.get("Ports", {})
        if isinstance(raw_ports, dict):
            ports_data = raw_ports

    port_list: list[str] = []
    for port_key, bindings in ports_data.items():
        if isinstance(bindings, list):
            for binding in bindings:
                if isinstance(binding, dict):
                    host_port = binding.get("HostPort", "")
                    port_list.append(f"{host_port}->{port_key}")
        else:
            port_list.append(str(port_key))

    # Container name ve status
    container_name: str = getattr(container, "name", "") or ""
    container_status: str = getattr(container, "status", "") or ""

    # Image bilgisi
    image = getattr(container, "image", None)
    image_str = ""
    if image is not None:
        tags = getattr(image, "tags", None)
        if tags and isinstance(tags, list) and len(tags) > 0:
            image_str = str(tags[0])
        else:
            image_str = str(getattr(image, "id", ""))[:20]

    # Zaman bilgileri
    created_at = str(attrs.get("Created", ""))
    started_raw = state.get("StartedAt")
    started_at: str | None = str(started_raw) if started_raw else None

    return {
        "name": container_name,
        "status": container_status,
        "health": health_status,
        "image": image_str,
        "ports": port_list,
        "created_at": created_at,
        "started_at": started_at,
    }
