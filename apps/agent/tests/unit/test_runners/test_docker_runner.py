"""Unit tests for DockerRunner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.runners.docker_runner import (
    DockerRunner,
    DockerRunnerError,
    ProjectEntry,
    _extract_container_info,
)

# --- Fixtures ---


@pytest.fixture
def tmp_project_dir(tmp_path: Path) -> Path:
    """Gecici proje dizini olusturur ve docker-compose.yml ekler."""
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("version: '3'\nservices:\n  web:\n    image: nginx\n")
    return tmp_path


@pytest.fixture
def project_entry(tmp_project_dir: Path) -> ProjectEntry:
    """Test proje entrysi olusturur."""
    return ProjectEntry(
        slug="test-project",
        path=str(tmp_project_dir),
        docker_compose="docker-compose.yml",
    )


@pytest.fixture
def projects_dict(project_entry: ProjectEntry) -> dict[str, ProjectEntry]:
    """Proje sozlugu olusturur."""
    return {project_entry.slug: project_entry}


@pytest.fixture
def docker_runner(projects_dict: dict[str, ProjectEntry]) -> DockerRunner:
    """Test icin DockerRunner instance'i olusturur."""
    return DockerRunner(
        projects=projects_dict,
        command_timeout=10,
    )


def _make_mock_process(
    returncode: int = 0,
    stdout: bytes = b"success output",
    stderr: bytes = b"",
) -> AsyncMock:
    """Mock asyncio subprocess olusturur."""
    mock_proc = AsyncMock()
    mock_proc.returncode = returncode
    mock_proc.communicate = AsyncMock(return_value=(stdout, stderr))
    return mock_proc


# --- ProjectEntry Tests ---


class TestProjectEntry:
    """ProjectEntry model testleri."""

    def test_create_with_defaults(self) -> None:
        """Varsayilan compose dosya adi ile olusturulur."""
        entry = ProjectEntry(slug="my-app", path="/home/user/my-app")
        assert entry.slug == "my-app"
        assert entry.path == "/home/user/my-app"
        assert entry.docker_compose == "docker-compose.yml"

    def test_create_with_custom_compose(self) -> None:
        """Ozel compose dosya adi ile olusturulur."""
        entry = ProjectEntry(
            slug="my-app",
            path="/home/user/my-app",
            docker_compose="compose.dev.yml",
        )
        assert entry.docker_compose == "compose.dev.yml"


# --- DockerRunner Init Tests ---


class TestDockerRunnerInit:
    """DockerRunner __init__ testleri."""

    def test_tool_name(self, docker_runner: DockerRunner) -> None:
        """tool_name 'docker' dondurur."""
        assert docker_runner.tool_name == "docker"

    def test_default_allowed_compose_files(
        self,
        projects_dict: dict[str, ProjectEntry],
    ) -> None:
        """Varsayilan izin verilen compose dosyalari dogru ayarlanir."""
        runner = DockerRunner(projects=projects_dict)
        assert "docker-compose.yml" in runner._allowed_compose_files
        assert "docker-compose.yaml" in runner._allowed_compose_files
        assert "compose.yml" in runner._allowed_compose_files

    def test_custom_allowed_compose_files(
        self,
        projects_dict: dict[str, ProjectEntry],
    ) -> None:
        """Ozel izin verilen compose dosyalari ayarlanabilir."""
        runner = DockerRunner(
            projects=projects_dict,
            allowed_compose_files=["my-compose.yml"],
        )
        assert runner._allowed_compose_files == {"my-compose.yml"}


# --- _resolve_project Tests ---


class TestResolveProject:
    """DockerRunner._resolve_project testleri."""

    def test_resolve_existing_project(
        self,
        docker_runner: DockerRunner,
        tmp_project_dir: Path,
    ) -> None:
        """Mevcut proje basariyla resolve edilir."""
        path, compose = docker_runner._resolve_project("test-project")
        assert path == str(tmp_project_dir)
        assert compose == "docker-compose.yml"

    def test_resolve_unknown_project_raises_error(
        self,
        docker_runner: DockerRunner,
    ) -> None:
        """Bilinmeyen proje slug'i hata firlatir."""
        with pytest.raises(DockerRunnerError, match="Proje bulunamadi"):
            docker_runner._resolve_project("nonexistent")

    def test_resolve_disallowed_compose_file_raises_error(
        self,
        tmp_project_dir: Path,
    ) -> None:
        """Izin verilmeyen compose dosyasi hata firlatir."""
        entry = ProjectEntry(
            slug="bad-project",
            path=str(tmp_project_dir),
            docker_compose="evil-compose.yml",
        )
        runner = DockerRunner(projects={"bad-project": entry})
        with pytest.raises(DockerRunnerError, match="izin verilmemis"):
            runner._resolve_project("bad-project")

    def test_resolve_missing_compose_file_raises_error(self, tmp_path: Path) -> None:
        """Fiziksel olarak mevcut olmayan compose dosyasi hata firlatir."""
        # docker-compose.yml olusturmadan proje ekle
        entry = ProjectEntry(
            slug="no-file",
            path=str(tmp_path),
            docker_compose="docker-compose.yml",
        )
        runner = DockerRunner(projects={"no-file": entry})
        with pytest.raises(DockerRunnerError, match="Compose dosyasi bulunamadi"):
            runner._resolve_project("no-file")


# --- execute() Tests ---


class TestDockerRunnerExecute:
    """DockerRunner.execute() metod testleri."""

    async def test_unknown_action_raises_error(
        self,
        docker_runner: DockerRunner,
    ) -> None:
        """Bilinmeyen aksiyon ValueError firlatir."""
        with pytest.raises(ValueError, match="Bilinmeyen Docker aksiyonu"):
            await docker_runner.execute("invalid_action", {"project_slug": "test-project"})

    async def test_missing_project_slug_returns_error(
        self,
        docker_runner: DockerRunner,
    ) -> None:
        """project_slug olmadan hata dondurur."""
        result = await docker_runner.execute("compose_up", {})
        assert result["success"] is False
        assert "project_slug" in str(result.get("error", ""))

    async def test_empty_project_slug_returns_error(
        self,
        docker_runner: DockerRunner,
    ) -> None:
        """Bos project_slug ile hata dondurur."""
        result = await docker_runner.execute("compose_up", {"project_slug": ""})
        assert result["success"] is False

    async def test_nonexistent_project_returns_error(
        self,
        docker_runner: DockerRunner,
    ) -> None:
        """Bulunamayan proje icin DockerRunnerError yakalanir."""
        result = await docker_runner.execute(
            "compose_up",
            {"project_slug": "nonexistent"},
        )
        assert result["success"] is False
        assert "bulunamadi" in str(result.get("error", "")).lower()


# --- compose_up Tests ---


class TestComposeUp:
    """compose_up aksiyon testleri."""

    @patch("asyncio.create_subprocess_exec")
    async def test_compose_up_success(
        self,
        mock_exec: AsyncMock,
        docker_runner: DockerRunner,
    ) -> None:
        """compose_up basariyla calisir."""
        mock_exec.return_value = _make_mock_process(
            returncode=0,
            stdout=b"Container test-web-1  Started\n",
        )

        result = await docker_runner.execute(
            "compose_up",
            {"project_slug": "test-project"},
        )

        assert result["success"] is True
        assert "Started" in str(result.get("output", ""))

        # docker compose -f docker-compose.yml up -d cagirildi
        call_args = mock_exec.call_args
        cmd_parts = call_args[0]
        assert "compose" in cmd_parts
        assert "up" in cmd_parts
        assert "-d" in cmd_parts

    @patch("asyncio.create_subprocess_exec")
    async def test_compose_up_with_services(
        self,
        mock_exec: AsyncMock,
        docker_runner: DockerRunner,
    ) -> None:
        """compose_up belirli servisler ile calisir."""
        mock_exec.return_value = _make_mock_process()

        await docker_runner.execute(
            "compose_up",
            {"project_slug": "test-project", "services": ["web", "db"]},
        )

        call_args = mock_exec.call_args
        cmd_parts = call_args[0]
        assert "web" in cmd_parts
        assert "db" in cmd_parts

    @patch("asyncio.create_subprocess_exec")
    async def test_compose_up_without_detach(
        self,
        mock_exec: AsyncMock,
        docker_runner: DockerRunner,
    ) -> None:
        """compose_up detach=False ile -d eklenmez."""
        mock_exec.return_value = _make_mock_process()

        await docker_runner.execute(
            "compose_up",
            {"project_slug": "test-project", "detach": False},
        )

        call_args = mock_exec.call_args
        cmd_parts = call_args[0]
        assert "-d" not in cmd_parts

    @patch("asyncio.create_subprocess_exec")
    async def test_compose_up_failure(
        self,
        mock_exec: AsyncMock,
        docker_runner: DockerRunner,
    ) -> None:
        """compose_up basarisiz olursa hata dondurur."""
        mock_exec.return_value = _make_mock_process(
            returncode=1,
            stderr=b"Error: service web failed to start",
        )

        result = await docker_runner.execute(
            "compose_up",
            {"project_slug": "test-project"},
        )

        assert result["success"] is False
        assert result.get("error") is not None


# --- compose_down Tests ---


class TestComposeDown:
    """compose_down aksiyon testleri."""

    @patch("asyncio.create_subprocess_exec")
    async def test_compose_down_success(
        self,
        mock_exec: AsyncMock,
        docker_runner: DockerRunner,
    ) -> None:
        """compose_down basariyla calisir."""
        mock_exec.return_value = _make_mock_process(
            stdout=b"Container test-web-1  Stopped\n",
        )

        result = await docker_runner.execute(
            "compose_down",
            {"project_slug": "test-project"},
        )

        assert result["success"] is True

        call_args = mock_exec.call_args
        cmd_parts = call_args[0]
        assert "down" in cmd_parts
        assert "-v" not in cmd_parts

    @patch("asyncio.create_subprocess_exec")
    async def test_compose_down_with_volumes(
        self,
        mock_exec: AsyncMock,
        docker_runner: DockerRunner,
    ) -> None:
        """compose_down remove_volumes=True ile -v ekler."""
        mock_exec.return_value = _make_mock_process()

        await docker_runner.execute(
            "compose_down",
            {"project_slug": "test-project", "remove_volumes": True},
        )

        call_args = mock_exec.call_args
        cmd_parts = call_args[0]
        assert "-v" in cmd_parts


# --- compose_restart Tests ---


class TestComposeRestart:
    """compose_restart aksiyon testleri."""

    @patch("asyncio.create_subprocess_exec")
    async def test_compose_restart_success(
        self,
        mock_exec: AsyncMock,
        docker_runner: DockerRunner,
    ) -> None:
        """compose_restart basariyla calisir."""
        mock_exec.return_value = _make_mock_process(
            stdout=b"Container test-web-1  Restarted\n",
        )

        result = await docker_runner.execute(
            "compose_restart",
            {"project_slug": "test-project"},
        )

        assert result["success"] is True

        call_args = mock_exec.call_args
        cmd_parts = call_args[0]
        assert "restart" in cmd_parts

    @patch("asyncio.create_subprocess_exec")
    async def test_compose_restart_with_services(
        self,
        mock_exec: AsyncMock,
        docker_runner: DockerRunner,
    ) -> None:
        """compose_restart belirli servisler ile calisir."""
        mock_exec.return_value = _make_mock_process()

        await docker_runner.execute(
            "compose_restart",
            {"project_slug": "test-project", "services": ["web"]},
        )

        call_args = mock_exec.call_args
        cmd_parts = call_args[0]
        assert "web" in cmd_parts


# --- compose_logs Tests ---


class TestComposeLogs:
    """compose_logs aksiyon testleri."""

    @patch("asyncio.create_subprocess_exec")
    async def test_compose_logs_default_tail(
        self,
        mock_exec: AsyncMock,
        docker_runner: DockerRunner,
    ) -> None:
        """compose_logs varsayilan tail=100 kullanir."""
        mock_exec.return_value = _make_mock_process(stdout=b"log line 1\nlog line 2\n")

        result = await docker_runner.execute(
            "compose_logs",
            {"project_slug": "test-project"},
        )

        assert result["success"] is True

        call_args = mock_exec.call_args
        cmd_parts = call_args[0]
        assert "--tail=100" in cmd_parts

    @patch("asyncio.create_subprocess_exec")
    async def test_compose_logs_custom_tail(
        self,
        mock_exec: AsyncMock,
        docker_runner: DockerRunner,
    ) -> None:
        """compose_logs ozel tail degeri kullanir."""
        mock_exec.return_value = _make_mock_process()

        await docker_runner.execute(
            "compose_logs",
            {"project_slug": "test-project", "tail": 50},
        )

        call_args = mock_exec.call_args
        cmd_parts = call_args[0]
        assert "--tail=50" in cmd_parts

    @patch("asyncio.create_subprocess_exec")
    async def test_compose_logs_with_since(
        self,
        mock_exec: AsyncMock,
        docker_runner: DockerRunner,
    ) -> None:
        """compose_logs since parametresi ile calisir."""
        mock_exec.return_value = _make_mock_process()

        await docker_runner.execute(
            "compose_logs",
            {"project_slug": "test-project", "since": "1h"},
        )

        call_args = mock_exec.call_args
        cmd_parts = call_args[0]
        assert "--since" in cmd_parts
        assert "1h" in cmd_parts

    @patch("asyncio.create_subprocess_exec")
    async def test_compose_logs_with_service_filter(
        self,
        mock_exec: AsyncMock,
        docker_runner: DockerRunner,
    ) -> None:
        """compose_logs belirli servis filtrelemesi ile calisir."""
        mock_exec.return_value = _make_mock_process()

        await docker_runner.execute(
            "compose_logs",
            {"project_slug": "test-project", "service": "web"},
        )

        call_args = mock_exec.call_args
        cmd_parts = call_args[0]
        assert "web" in cmd_parts

    @patch("asyncio.create_subprocess_exec")
    async def test_compose_logs_invalid_tail_uses_default(
        self,
        mock_exec: AsyncMock,
        docker_runner: DockerRunner,
    ) -> None:
        """compose_logs gecersiz tail degeri icin varsayilani kullanir."""
        mock_exec.return_value = _make_mock_process()

        await docker_runner.execute(
            "compose_logs",
            {"project_slug": "test-project", "tail": -5},
        )

        call_args = mock_exec.call_args
        cmd_parts = call_args[0]
        assert "--tail=100" in cmd_parts


# --- health_check Tests ---


class TestHealthCheck:
    """health_check aksiyon testleri."""

    @patch("asyncio.create_subprocess_exec")
    async def test_health_check_compose_ps_failure(
        self,
        mock_exec: AsyncMock,
        docker_runner: DockerRunner,
    ) -> None:
        """health_check compose ps basarisiz olursa hata dondurur."""
        mock_exec.return_value = _make_mock_process(
            returncode=1,
            stderr=b"Error: daemon not running",
        )

        result = await docker_runner.execute(
            "health_check",
            {"project_slug": "test-project"},
        )

        assert result["success"] is False

    @patch.object(DockerRunner, "_inspect_project_containers")
    @patch("asyncio.create_subprocess_exec")
    async def test_health_check_all_healthy(
        self,
        mock_exec: AsyncMock,
        mock_inspect: MagicMock,
        docker_runner: DockerRunner,
    ) -> None:
        """health_check tum container'lar saglikli ise healthy=True dondurur."""
        mock_exec.return_value = _make_mock_process(stdout=b"[]")
        mock_inspect.return_value = [
            {"name": "web", "status": "running", "health": "healthy"},
            {"name": "db", "status": "running", "health": None},
        ]

        result = await docker_runner.execute(
            "health_check",
            {"project_slug": "test-project"},
        )

        assert result["success"] is True
        assert result["healthy"] is True

    @patch.object(DockerRunner, "_inspect_project_containers")
    @patch("asyncio.create_subprocess_exec")
    async def test_health_check_unhealthy_container(
        self,
        mock_exec: AsyncMock,
        mock_inspect: MagicMock,
        docker_runner: DockerRunner,
    ) -> None:
        """health_check sagliksiz container varsa healthy=False dondurur."""
        mock_exec.return_value = _make_mock_process(stdout=b"[]")
        mock_inspect.return_value = [
            {"name": "web", "status": "running", "health": "unhealthy"},
            {"name": "db", "status": "running", "health": "healthy"},
        ]

        result = await docker_runner.execute(
            "health_check",
            {"project_slug": "test-project"},
        )

        assert result["success"] is True
        assert result["healthy"] is False

    @patch.object(DockerRunner, "_inspect_project_containers")
    @patch("asyncio.create_subprocess_exec")
    async def test_health_check_docker_sdk_error(
        self,
        mock_exec: AsyncMock,
        mock_inspect: MagicMock,
        docker_runner: DockerRunner,
    ) -> None:
        """health_check Docker SDK hatasi dondururse error dondurur."""
        mock_exec.return_value = _make_mock_process(stdout=b"[]")
        mock_inspect.return_value = [{"error": "Docker daemon baglanti hatasi"}]

        result = await docker_runner.execute(
            "health_check",
            {"project_slug": "test-project"},
        )

        assert result["success"] is False


# --- container_status Tests ---


class TestContainerStatus:
    """container_status aksiyon testleri."""

    @patch.object(DockerRunner, "_inspect_project_containers")
    @patch("asyncio.create_subprocess_exec")
    async def test_container_status_success(
        self,
        mock_exec: AsyncMock,
        mock_inspect: MagicMock,
        docker_runner: DockerRunner,
    ) -> None:
        """container_status basariyla container bilgilerini dondurur."""
        mock_exec.return_value = _make_mock_process(stdout=b"NAME  STATUS  PORTS\n")
        mock_inspect.return_value = [
            {"name": "web", "status": "running", "health": "healthy"},
            {"name": "db", "status": "running", "health": None},
            {"name": "cache", "status": "exited", "health": None},
        ]

        result = await docker_runner.execute(
            "container_status",
            {"project_slug": "test-project"},
        )

        assert result["success"] is True
        assert result["running_count"] == 2
        assert result["total_count"] == 3

    @patch("asyncio.create_subprocess_exec")
    async def test_container_status_compose_ps_failure(
        self,
        mock_exec: AsyncMock,
        docker_runner: DockerRunner,
    ) -> None:
        """container_status compose ps basarisiz olursa hata dondurur."""
        mock_exec.return_value = _make_mock_process(
            returncode=1,
            stderr=b"Error",
        )

        result = await docker_runner.execute(
            "container_status",
            {"project_slug": "test-project"},
        )

        assert result["success"] is False


# --- Timeout Tests ---


class TestTimeout:
    """Timeout senaryolari."""

    @patch("asyncio.create_subprocess_exec")
    async def test_compose_command_timeout(
        self,
        mock_exec: AsyncMock,
        docker_runner: DockerRunner,
    ) -> None:
        """Timeout durumunda uygun hata dondurur."""
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=TimeoutError)
        mock_exec.return_value = mock_proc

        result = await docker_runner.execute(
            "compose_up",
            {"project_slug": "test-project"},
        )

        assert result["success"] is False
        assert "tamamlanamadi" in str(result.get("error", ""))


# --- _extract_container_info Tests ---


class TestExtractContainerInfo:
    """_extract_container_info fonksiyon testleri."""

    def test_extract_basic_info(self) -> None:
        """Temel container bilgileri dogru cikarilir."""
        mock_container = MagicMock()
        mock_container.name = "test-web-1"
        mock_container.status = "running"
        mock_container.attrs = {
            "Created": "2026-03-02T10:00:00Z",
            "State": {
                "StartedAt": "2026-03-02T10:00:01Z",
                "Health": {"Status": "healthy"},
            },
            "NetworkSettings": {
                "Ports": {
                    "80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}],
                },
            },
        }
        mock_container.image = MagicMock()
        mock_container.image.tags = ["nginx:latest"]

        info = _extract_container_info(mock_container)

        assert info["name"] == "test-web-1"
        assert info["status"] == "running"
        assert info["health"] == "healthy"
        assert info["image"] == "nginx:latest"
        assert "8080->80/tcp" in info["ports"]
        assert info["created_at"] == "2026-03-02T10:00:00Z"
        assert info["started_at"] == "2026-03-02T10:00:01Z"

    def test_extract_container_without_health(self) -> None:
        """Health olmayan container icin health=None dondurur."""
        mock_container = MagicMock()
        mock_container.name = "test-db-1"
        mock_container.status = "running"
        mock_container.attrs = {
            "Created": "2026-03-02T10:00:00Z",
            "State": {"StartedAt": "2026-03-02T10:00:01Z"},
            "NetworkSettings": {"Ports": {}},
        }
        mock_container.image = MagicMock()
        mock_container.image.tags = ["postgres:16"]

        info = _extract_container_info(mock_container)

        assert info["health"] is None

    def test_extract_container_without_ports(self) -> None:
        """Port olmayan container icin bos liste dondurur."""
        mock_container = MagicMock()
        mock_container.name = "test-worker-1"
        mock_container.status = "running"
        mock_container.attrs = {
            "Created": "2026-03-02T10:00:00Z",
            "State": {},
            "NetworkSettings": {"Ports": {}},
        }
        mock_container.image = MagicMock()
        mock_container.image.tags = ["worker:latest"]

        info = _extract_container_info(mock_container)

        assert info["ports"] == []

    def test_extract_exited_container(self) -> None:
        """Duran container icin started_at None dondurur."""
        mock_container = MagicMock()
        mock_container.name = "test-temp-1"
        mock_container.status = "exited"
        mock_container.attrs = {
            "Created": "2026-03-02T10:00:00Z",
            "State": {},
            "NetworkSettings": {"Ports": {}},
        }
        mock_container.image = MagicMock()
        mock_container.image.tags = []
        mock_container.image.id = "sha256:abc123def456"

        info = _extract_container_info(mock_container)

        assert info["status"] == "exited"
        assert info["started_at"] is None
        assert "sha256:abc123def456" in str(info["image"])

    def test_extract_container_null_ports_binding(self) -> None:
        """Port binding None ise sadece port key dondurur."""
        mock_container = MagicMock()
        mock_container.name = "test-app-1"
        mock_container.status = "running"
        mock_container.attrs = {
            "Created": "2026-03-02T10:00:00Z",
            "State": {},
            "NetworkSettings": {
                "Ports": {
                    "3000/tcp": None,
                },
            },
        }
        mock_container.image = MagicMock()
        mock_container.image.tags = ["app:latest"]

        info = _extract_container_info(mock_container)

        assert "3000/tcp" in info["ports"]


# --- _inspect_project_containers Tests ---


class TestInspectProjectContainers:
    """_inspect_project_containers testleri."""

    def test_inspect_returns_empty_list_for_no_containers(self) -> None:
        """Proje icin container yoksa bos liste dondurur."""
        entry = ProjectEntry(slug="empty-proj", path="/tmp", docker_compose="docker-compose.yml")
        runner = DockerRunner(projects={"empty-proj": entry})

        mock_client = MagicMock()
        mock_client.containers.list.return_value = []
        mock_client.close = MagicMock()

        mock_docker_module = MagicMock()
        mock_docker_module.from_env.return_value = mock_client

        with patch.dict("sys.modules", {"docker": mock_docker_module}):
            result = runner._inspect_project_containers("empty-proj")
            assert result == []

    def test_inspect_docker_daemon_error_returns_error(self) -> None:
        """Docker daemon baglanti hatasi durumunda hata dondurur."""
        entry = ProjectEntry(slug="test", path="/tmp", docker_compose="docker-compose.yml")
        runner = DockerRunner(projects={"test": entry})

        mock_docker_module = MagicMock()
        mock_docker_module.from_env.side_effect = Exception("Docker daemon not available")

        with patch.dict("sys.modules", {"docker": mock_docker_module}):
            result = runner._inspect_project_containers("test")
            assert len(result) == 1
            assert "error" in result[0]
            assert "baglanilamadi" in str(result[0]["error"])


# --- run_compose_command internal Tests ---


class TestRunComposeCommand:
    """_run_compose_command ic metod testleri."""

    @patch("asyncio.create_subprocess_exec")
    async def test_command_builds_correct_args(
        self,
        mock_exec: AsyncMock,
        docker_runner: DockerRunner,
        tmp_project_dir: Path,
    ) -> None:
        """docker compose komutu dogru arguman listesi ile cagirilir."""
        mock_exec.return_value = _make_mock_process()

        await docker_runner._run_compose_command(
            project_path=str(tmp_project_dir),
            compose_file="docker-compose.yml",
            args=["up", "-d"],
        )

        call_args = mock_exec.call_args
        cmd_parts = call_args[0]
        assert cmd_parts[0] == "docker"
        assert cmd_parts[1] == "compose"
        assert cmd_parts[2] == "-f"
        assert cmd_parts[3] == "docker-compose.yml"
        assert cmd_parts[4] == "up"
        assert cmd_parts[5] == "-d"

        # cwd dogru ayarlanmis mi?
        assert call_args[1].get("cwd") == str(tmp_project_dir)

    @patch("asyncio.create_subprocess_exec")
    async def test_command_captures_stdout_stderr(
        self,
        mock_exec: AsyncMock,
        docker_runner: DockerRunner,
        tmp_project_dir: Path,
    ) -> None:
        """stdout ve stderr dogru yakalanir."""
        mock_exec.return_value = _make_mock_process(
            returncode=0,
            stdout=b"output data",
            stderr=b"",
        )

        result = await docker_runner._run_compose_command(
            str(tmp_project_dir),
            "docker-compose.yml",
            ["ps"],
        )

        assert result["output"] == "output data"
        assert result["error"] is None

    @patch("asyncio.create_subprocess_exec")
    async def test_command_returns_error_on_failure(
        self,
        mock_exec: AsyncMock,
        docker_runner: DockerRunner,
        tmp_project_dir: Path,
    ) -> None:
        """Basarisiz komut error alani dondurur."""
        mock_exec.return_value = _make_mock_process(
            returncode=1,
            stdout=b"",
            stderr=b"permission denied",
        )

        result = await docker_runner._run_compose_command(
            str(tmp_project_dir),
            "docker-compose.yml",
            ["up", "-d"],
        )

        assert result["success"] is False
        assert result["error"] == "permission denied"
