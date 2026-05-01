"""Unit tests for MaestroRunner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from agent.runners.maestro_runner import (
    MaestroRunner,
    MaestroRunnerError,
)
from agent.upload.s3_uploader import S3Uploader, UploadResult

# --- Fixtures ---


@pytest.fixture
def mock_s3_uploader() -> AsyncMock:
    """Mock S3Uploader olusturur."""
    uploader = AsyncMock(spec=S3Uploader)
    uploader.upload_bytes = AsyncMock(
        return_value=UploadResult(
            url="https://test-bucket.s3.eu-west-1.amazonaws.com/screenshots/test.png",
            key="screenshots/test.png",
            bucket="test-bucket",
            size_bytes=1024,
            content_type="image/png",
            multipart=False,
        ),
    )
    return uploader


@pytest.fixture
def maestro_runner(mock_s3_uploader: AsyncMock) -> MaestroRunner:
    """Test icin MaestroRunner instance olusturur."""
    return MaestroRunner(
        s3_uploader=mock_s3_uploader,
        default_timeout=60,
        max_timeout=120,
        ios_device="iPhone 16",
        android_device="Pixel_7_API_34",
    )


@pytest.fixture
def maestro_runner_no_s3() -> MaestroRunner:
    """S3 uploader olmadan MaestroRunner olusturur."""
    return MaestroRunner(
        s3_uploader=None,
        default_timeout=60,
        max_timeout=120,
    )


@pytest.fixture
def maestro_runner_no_device() -> MaestroRunner:
    """Device parametresi olmadan MaestroRunner olusturur."""
    return MaestroRunner(
        s3_uploader=None,
        default_timeout=60,
        max_timeout=120,
        ios_device=None,
        android_device=None,
    )


@pytest.fixture
def tmp_flow_file(tmp_path: Path) -> Path:
    """Gecici flow dosyasi olusturur."""
    flow_file = tmp_path / "login_flow.yaml"
    flow_file.write_text(
        "appId: com.example.app\n"
        "---\n"
        "- launchApp\n"
        "- tapOn: Login\n"
        "- inputText: user@test.com\n"
        "- assertVisible: Dashboard\n",
    )
    return flow_file


@pytest.fixture
def tmp_flow_dir(tmp_path: Path) -> Path:
    """Birden fazla flow dosyasi iceren gecici dizin olusturur."""
    flows_dir = tmp_path / "flows"
    flows_dir.mkdir()

    flow1 = flows_dir / "login.yaml"
    flow1.write_text("appId: com.example.app\n- launchApp\n- tapOn: Login\n")

    flow2 = flows_dir / "signup.yml"
    flow2.write_text("appId: com.example.app\n- launchApp\n- tapOn: Signup\n")

    # Non-flow dosya (txt) - atlanmali
    other = flows_dir / "readme.txt"
    other.write_text("Bu dosya flow degil")

    return flows_dir


@pytest.fixture
def tmp_empty_flow(tmp_path: Path) -> Path:
    """Bos flow dosyasi olusturur."""
    flow_file = tmp_path / "empty.yaml"
    flow_file.write_text("")
    return flow_file


@pytest.fixture
def tmp_no_commands_flow(tmp_path: Path) -> Path:
    """Bilinen Maestro komutu olmayan flow dosyasi olusturur."""
    flow_file = tmp_path / "nocommands.yaml"
    flow_file.write_text("name: test\nsteps:\n  - wait: 5\n")
    return flow_file


# --- Yardimci fonksiyonlar ---


def _make_mock_process(
    returncode: int = 0,
    stdout: bytes = b"Passed: 3, Failed: 0",
    stderr: bytes = b"",
) -> AsyncMock:
    """Mock asyncio subprocess olusturur."""
    proc = AsyncMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    return proc


# --- MaestroRunner Init Tests ---


class TestMaestroRunnerInit:
    """MaestroRunner __init__ testleri."""

    def test_tool_name(self, maestro_runner: MaestroRunner) -> None:
        """tool_name 'maestro' dondurur."""
        assert maestro_runner.tool_name == "maestro"

    def test_default_timeout(self) -> None:
        """Varsayilan timeout dogru ayarlanir."""
        runner = MaestroRunner()
        assert runner._default_timeout == 300

    def test_custom_timeout(self) -> None:
        """Ozel timeout ayarlanabilir."""
        runner = MaestroRunner(default_timeout=120)
        assert runner._default_timeout == 120

    def test_default_max_timeout(self) -> None:
        """Varsayilan max timeout dogru ayarlanir."""
        runner = MaestroRunner()
        assert runner._max_timeout == 600

    def test_ios_device_stored(self, maestro_runner: MaestroRunner) -> None:
        """iOS device dogru saklanir."""
        assert maestro_runner._ios_device == "iPhone 16"

    def test_android_device_stored(self, maestro_runner: MaestroRunner) -> None:
        """Android device dogru saklanir."""
        assert maestro_runner._android_device == "Pixel_7_API_34"

    def test_error_class_exists(self) -> None:
        """MaestroRunnerError sinifi mevcut."""
        assert issubclass(MaestroRunnerError, Exception)


# --- execute() Tests ---


class TestMaestroRunnerExecute:
    """MaestroRunner.execute() metod testleri."""

    async def test_unknown_action_raises_error(
        self,
        maestro_runner: MaestroRunner,
    ) -> None:
        """Bilinmeyen aksiyon ValueError firlatir."""
        with pytest.raises(ValueError, match="Bilinmeyen Maestro aksiyonu"):
            await maestro_runner.execute("invalid_action", {})

    async def test_all_supported_actions_dispatched(
        self,
        maestro_runner: MaestroRunner,
    ) -> None:
        """Tum desteklenen aksiyonlar ValueError firlatmaz (parametre hatasi dondurur)."""
        actions = [
            "run_flow",
            "run_all_flows",
            "take_screenshot",
            "list_flows",
            "validate_flow",
        ]
        for action in actions:
            # Parametre eksikse hata dondurur ama ValueError firlatmaz
            result = await maestro_runner.execute(action, {})
            assert result["success"] is False


# --- _validate_platform Tests ---


class TestValidatePlatform:
    """_validate_platform testleri."""

    def test_ios_valid(self, maestro_runner: MaestroRunner) -> None:
        """'ios' gecerli platform."""
        assert maestro_runner._validate_platform("ios") == "ios"

    def test_android_valid(self, maestro_runner: MaestroRunner) -> None:
        """'android' gecerli platform."""
        assert maestro_runner._validate_platform("android") == "android"

    def test_case_insensitive(self, maestro_runner: MaestroRunner) -> None:
        """Platform buyuk/kucuk harf duyarsiz."""
        assert maestro_runner._validate_platform("iOS") == "ios"
        assert maestro_runner._validate_platform("ANDROID") == "android"

    def test_invalid_platform(self, maestro_runner: MaestroRunner) -> None:
        """Gecersiz platform None dondurur."""
        assert maestro_runner._validate_platform("windows") is None

    def test_non_string_platform(self, maestro_runner: MaestroRunner) -> None:
        """String olmayan platform None dondurur."""
        assert maestro_runner._validate_platform(123) is None
        assert maestro_runner._validate_platform(None) is None


# --- _validate_flow_file Tests ---


class TestValidateFlowFile:
    """_validate_flow_file testleri."""

    def test_yaml_extension_valid(self, maestro_runner: MaestroRunner) -> None:
        """.yaml uzantisi gecerli."""
        assert maestro_runner._validate_flow_file("flow.yaml") == "flow.yaml"

    def test_yml_extension_valid(self, maestro_runner: MaestroRunner) -> None:
        """.yml uzantisi gecerli."""
        assert maestro_runner._validate_flow_file("flow.yml") == "flow.yml"

    def test_invalid_extension(self, maestro_runner: MaestroRunner) -> None:
        """Gecersiz uzanti None dondurur."""
        assert maestro_runner._validate_flow_file("flow.txt") is None
        assert maestro_runner._validate_flow_file("flow.json") is None

    def test_empty_string(self, maestro_runner: MaestroRunner) -> None:
        """Bos string None dondurur."""
        assert maestro_runner._validate_flow_file("") is None
        assert maestro_runner._validate_flow_file("  ") is None

    def test_non_string(self, maestro_runner: MaestroRunner) -> None:
        """String olmayan deger None dondurur."""
        assert maestro_runner._validate_flow_file(123) is None
        assert maestro_runner._validate_flow_file(None) is None

    def test_strips_whitespace(self, maestro_runner: MaestroRunner) -> None:
        """Bosluklar temizlenir."""
        assert maestro_runner._validate_flow_file("  flow.yaml  ") == "flow.yaml"


# --- _resolve_timeout Tests ---


class TestResolveTimeout:
    """_resolve_timeout testleri."""

    def test_valid_timeout(self, maestro_runner: MaestroRunner) -> None:
        """Gecerli timeout degeri kullanilir."""
        assert maestro_runner._resolve_timeout(60) == 60

    def test_exceeds_max_timeout(self, maestro_runner: MaestroRunner) -> None:
        """Max timeout asildiginda sinirlama uygulanir."""
        assert maestro_runner._resolve_timeout(999) == 120  # max_timeout=120

    def test_invalid_timeout_uses_default(self, maestro_runner: MaestroRunner) -> None:
        """Gecersiz timeout varsayilana doner."""
        assert maestro_runner._resolve_timeout(-1) == 60  # default_timeout=60
        assert maestro_runner._resolve_timeout(0) == 60
        assert maestro_runner._resolve_timeout("invalid") == 60

    def test_none_timeout_uses_default(self, maestro_runner: MaestroRunner) -> None:
        """None timeout varsayilana doner."""
        assert maestro_runner._resolve_timeout(None) == 60


# --- _build_maestro_cmd Tests ---


class TestBuildMaestroCmd:
    """_build_maestro_cmd testleri."""

    def test_basic_command(self, maestro_runner_no_device: MaestroRunner) -> None:
        """Device olmadan temel komut olusturulur."""
        cmd = maestro_runner_no_device._build_maestro_cmd("flow.yaml", "ios")
        assert cmd == ["maestro", "test", "flow.yaml"]

    def test_ios_with_device(self, maestro_runner: MaestroRunner) -> None:
        """iOS platform icin device parametresi eklenir."""
        cmd = maestro_runner._build_maestro_cmd("flow.yaml", "ios")
        assert cmd == ["maestro", "test", "flow.yaml", "--device", "iPhone 16"]

    def test_android_with_device(self, maestro_runner: MaestroRunner) -> None:
        """Android platform icin device parametresi eklenir."""
        cmd = maestro_runner._build_maestro_cmd("flow.yaml", "android")
        assert cmd == [
            "maestro",
            "test",
            "flow.yaml",
            "--device",
            "Pixel_7_API_34",
        ]


# --- _parse_maestro_output Tests ---


class TestParseMaestroOutput:
    """_parse_maestro_output testleri."""

    def test_parse_passed_and_failed(self, maestro_runner: MaestroRunner) -> None:
        """Passed ve Failed sayilari dogru parse edilir."""
        result = maestro_runner._parse_maestro_output("Passed: 3, Failed: 1")
        assert result["passed_tests"] == 3
        assert result["failed_tests"] == 1
        assert result["total_tests"] == 4

    def test_parse_only_passed(self, maestro_runner: MaestroRunner) -> None:
        """Sadece Passed sayisi parse edilir."""
        result = maestro_runner._parse_maestro_output("Tests passed: 5")
        assert result["passed_tests"] == 5
        assert result["failed_tests"] == 0
        assert result["total_tests"] == 5

    def test_parse_only_failed(self, maestro_runner: MaestroRunner) -> None:
        """Sadece Failed sayisi parse edilir."""
        result = maestro_runner._parse_maestro_output("Failed: 2")
        assert result["passed_tests"] == 0
        assert result["failed_tests"] == 2
        assert result["total_tests"] == 2

    def test_parse_empty_output(self, maestro_runner: MaestroRunner) -> None:
        """Bos cikti sifir dondurur."""
        result = maestro_runner._parse_maestro_output("")
        assert result["passed_tests"] == 0
        assert result["failed_tests"] == 0
        assert result["total_tests"] == 0

    def test_parse_no_match(self, maestro_runner: MaestroRunner) -> None:
        """Hicbir pattern uyusmazsa sifir dondurur."""
        result = maestro_runner._parse_maestro_output("Some random output")
        assert result["total_tests"] == 0


# --- run_flow Tests ---


class TestRunFlow:
    """run_flow aksiyon testleri."""

    async def test_missing_flow_file_returns_error(
        self,
        maestro_runner: MaestroRunner,
    ) -> None:
        """flow_file parametresi olmadan hata dondurur."""
        result = await maestro_runner.execute(
            "run_flow",
            {"platform": "ios"},
        )
        assert result["success"] is False
        assert "flow_file" in str(result.get("error", ""))

    async def test_invalid_flow_file_extension(
        self,
        maestro_runner: MaestroRunner,
    ) -> None:
        """Gecersiz uzantili flow dosyasi reddedilir."""
        result = await maestro_runner.execute(
            "run_flow",
            {"flow_file": "test.txt", "platform": "ios"},
        )
        assert result["success"] is False

    async def test_missing_platform_returns_error(
        self,
        maestro_runner: MaestroRunner,
        tmp_flow_file: Path,
    ) -> None:
        """platform parametresi olmadan hata dondurur."""
        result = await maestro_runner.execute(
            "run_flow",
            {"flow_file": str(tmp_flow_file)},
        )
        assert result["success"] is False
        assert "platform" in str(result.get("error", ""))

    async def test_invalid_platform_returns_error(
        self,
        maestro_runner: MaestroRunner,
        tmp_flow_file: Path,
    ) -> None:
        """Gecersiz platform reddedilir."""
        result = await maestro_runner.execute(
            "run_flow",
            {"flow_file": str(tmp_flow_file), "platform": "windows"},
        )
        assert result["success"] is False

    async def test_flow_file_not_found(
        self,
        maestro_runner: MaestroRunner,
    ) -> None:
        """Mevcut olmayan flow dosyasi hata dondurur."""
        result = await maestro_runner.execute(
            "run_flow",
            {"flow_file": "/nonexistent/flow.yaml", "platform": "ios"},
        )
        assert result["success"] is False
        assert "bulunamadi" in str(result.get("error", ""))

    async def test_run_flow_success(
        self,
        maestro_runner: MaestroRunner,
        tmp_flow_file: Path,
    ) -> None:
        """Flow basariyla calistirilir."""
        mock_proc = _make_mock_process(
            returncode=0,
            stdout=b"Running flow...\nPassed: 3, Failed: 0\nDone.",
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await maestro_runner.execute(
                "run_flow",
                {
                    "flow_file": str(tmp_flow_file),
                    "platform": "ios",
                },
            )

        assert result["success"] is True
        assert result["flow_file"] == str(tmp_flow_file)
        assert result["platform"] == "ios"
        assert result["passed_tests"] == 3
        assert result["failed_tests"] == 0
        assert "duration_ms" in result

    async def test_run_flow_failure(
        self,
        maestro_runner: MaestroRunner,
        tmp_flow_file: Path,
    ) -> None:
        """Flow basarisiz oldugunda sonuc dondurur."""
        mock_proc = _make_mock_process(
            returncode=1,
            stdout=b"Running flow...\nPassed: 1, Failed: 2",
            stderr=b"Flow failed",
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await maestro_runner.execute(
                "run_flow",
                {
                    "flow_file": str(tmp_flow_file),
                    "platform": "android",
                },
            )

        assert result["success"] is False
        assert result["passed_tests"] == 1
        assert result["failed_tests"] == 2

    async def test_run_flow_timeout(
        self,
        maestro_runner: MaestroRunner,
        tmp_flow_file: Path,
    ) -> None:
        """Flow zaman asimi durumunda hata dondurur."""
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=TimeoutError())
        mock_proc.returncode = None

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("asyncio.wait_for", side_effect=TimeoutError()),
        ):
            result = await maestro_runner.execute(
                "run_flow",
                {
                    "flow_file": str(tmp_flow_file),
                    "platform": "ios",
                    "timeout": 5,
                },
            )

        assert result["success"] is False
        assert result.get("timed_out") is True

    async def test_run_flow_maestro_not_found(
        self,
        maestro_runner: MaestroRunner,
        tmp_flow_file: Path,
    ) -> None:
        """Maestro CLI yuklu degilse hata dondurur."""
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("maestro not found"),
        ):
            result = await maestro_runner.execute(
                "run_flow",
                {
                    "flow_file": str(tmp_flow_file),
                    "platform": "ios",
                },
            )

        assert result["success"] is False
        assert "bulunamadi" in str(result.get("error", ""))

    async def test_run_flow_with_cwd(
        self,
        maestro_runner: MaestroRunner,
        tmp_path: Path,
    ) -> None:
        """cwd parametresi ile flow dosyasi calistirilir."""
        flow_file = tmp_path / "test.yaml"
        flow_file.write_text("appId: com.test\n- launchApp\n")

        mock_proc = _make_mock_process(returncode=0, stdout=b"Passed: 1, Failed: 0")

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await maestro_runner.execute(
                "run_flow",
                {
                    "flow_file": "test.yaml",
                    "platform": "ios",
                    "cwd": str(tmp_path),
                },
            )

        assert result["success"] is True

    async def test_run_flow_invalid_cwd_type_ignored(
        self,
        maestro_runner: MaestroRunner,
        tmp_flow_file: Path,
    ) -> None:
        """Gecersiz cwd tipi None'a cevrilir."""
        mock_proc = _make_mock_process(returncode=0, stdout=b"Passed: 1, Failed: 0")

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await maestro_runner.execute(
                "run_flow",
                {
                    "flow_file": str(tmp_flow_file),
                    "platform": "ios",
                    "cwd": 123,
                },
            )

        assert result["success"] is True


# --- run_all_flows Tests ---


class TestRunAllFlows:
    """run_all_flows aksiyon testleri."""

    async def test_missing_flows_dir_returns_error(
        self,
        maestro_runner: MaestroRunner,
    ) -> None:
        """flows_dir parametresi olmadan hata dondurur."""
        result = await maestro_runner.execute(
            "run_all_flows",
            {"platform": "ios"},
        )
        assert result["success"] is False
        assert "flows_dir" in str(result.get("error", ""))

    async def test_missing_platform_returns_error(
        self,
        maestro_runner: MaestroRunner,
        tmp_flow_dir: Path,
    ) -> None:
        """platform parametresi olmadan hata dondurur."""
        result = await maestro_runner.execute(
            "run_all_flows",
            {"flows_dir": str(tmp_flow_dir)},
        )
        assert result["success"] is False
        assert "platform" in str(result.get("error", ""))

    async def test_nonexistent_dir_returns_error(
        self,
        maestro_runner: MaestroRunner,
    ) -> None:
        """Mevcut olmayan dizin hata dondurur."""
        result = await maestro_runner.execute(
            "run_all_flows",
            {"flows_dir": "/nonexistent/dir", "platform": "ios"},
        )
        assert result["success"] is False
        assert "bulunamadi" in str(result.get("error", ""))

    async def test_empty_dir_returns_error(
        self,
        maestro_runner: MaestroRunner,
        tmp_path: Path,
    ) -> None:
        """Bos dizin (flow yok) hata dondurur."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        result = await maestro_runner.execute(
            "run_all_flows",
            {"flows_dir": str(empty_dir), "platform": "ios"},
        )
        assert result["success"] is False
        assert "bulunamadi" in str(result.get("error", ""))

    async def test_run_all_flows_success(
        self,
        maestro_runner: MaestroRunner,
        tmp_flow_dir: Path,
    ) -> None:
        """Tum flow'lar basariyla calistirilir."""
        mock_proc = _make_mock_process(returncode=0, stdout=b"Passed: 2, Failed: 0")

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await maestro_runner.execute(
                "run_all_flows",
                {
                    "flows_dir": str(tmp_flow_dir),
                    "platform": "ios",
                },
            )

        assert result["success"] is True
        assert result["total_flows"] == 2  # login.yaml + signup.yml (txt atlanir)
        assert result["passed_flows"] == 2
        assert result["failed_flows"] == 0
        assert "duration_ms" in result
        assert "results" in result
        assert len(result["results"]) == 2  # type: ignore[arg-type]

    async def test_run_all_flows_partial_failure(
        self,
        maestro_runner: MaestroRunner,
        tmp_flow_dir: Path,
    ) -> None:
        """Bazi flow'lar basarisiz oldugunda rapor dondurur."""
        call_count = 0

        async def _mock_create_subprocess(
            *_args: object,
            **_kwargs: object,
        ) -> AsyncMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_mock_process(returncode=0, stdout=b"Passed: 1, Failed: 0")
            return _make_mock_process(
                returncode=1,
                stdout=b"Passed: 0, Failed: 1",
                stderr=b"Error",
            )

        with patch("asyncio.create_subprocess_exec", side_effect=_mock_create_subprocess):
            result = await maestro_runner.execute(
                "run_all_flows",
                {
                    "flows_dir": str(tmp_flow_dir),
                    "platform": "ios",
                },
            )

        assert result["success"] is False
        assert result["passed_flows"] == 1
        assert result["failed_flows"] == 1


# --- take_screenshot Tests ---


class TestTakeScreenshot:
    """take_screenshot aksiyon testleri."""

    async def test_missing_platform_returns_error(
        self,
        maestro_runner: MaestroRunner,
    ) -> None:
        """platform parametresi olmadan hata dondurur."""
        result = await maestro_runner.execute("take_screenshot", {})
        assert result["success"] is False
        assert "platform" in str(result.get("error", ""))

    async def test_ios_screenshot_success(
        self,
        tmp_path: Path,
        mock_s3_uploader: AsyncMock,
    ) -> None:
        """iOS screenshot basariyla alinir."""
        runner = MaestroRunner(
            s3_uploader=mock_s3_uploader,
            screenshots_dir=str(tmp_path),
        )

        mock_proc = _make_mock_process(returncode=0, stdout=b"", stderr=b"")

        async def _mock_create_subprocess(
            *_args: object,
            **_kwargs: object,
        ) -> AsyncMock:
            # Simulate xcrun creating a file
            import time as time_mod

            ts = int(time_mod.time())
            screenshot = tmp_path / f"screenshot_{ts}.png"
            screenshot.write_bytes(b"fake-png-data")
            return mock_proc

        with patch("asyncio.create_subprocess_exec", side_effect=_mock_create_subprocess):
            result = await runner.execute(
                "take_screenshot",
                {"platform": "ios"},
            )

        assert result["success"] is True
        assert result["platform"] == "ios"

    async def test_android_screenshot_success(
        self,
        tmp_path: Path,
    ) -> None:
        """Android screenshot basariyla alinir."""
        runner = MaestroRunner(
            s3_uploader=None,
            screenshots_dir=str(tmp_path),
        )

        mock_proc = _make_mock_process(
            returncode=0,
            stdout=b"fake-android-screenshot-data",
            stderr=b"",
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await runner.execute(
                "take_screenshot",
                {"platform": "android"},
            )

        assert result["success"] is True
        assert result["platform"] == "android"

    async def test_screenshot_tool_not_found(
        self,
        maestro_runner: MaestroRunner,
    ) -> None:
        """Platform araclari yuklu degilse hata dondurur."""
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("xcrun not found"),
        ):
            result = await maestro_runner.execute(
                "take_screenshot",
                {"platform": "ios"},
            )

        assert result["success"] is False
        assert "bulunamadi" in str(result.get("error", ""))

    async def test_screenshot_timeout(
        self,
        maestro_runner: MaestroRunner,
    ) -> None:
        """Screenshot alma zaman asimi."""
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=TimeoutError())

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("asyncio.wait_for", side_effect=TimeoutError()),
        ):
            result = await maestro_runner.execute(
                "take_screenshot",
                {"platform": "ios"},
            )

        assert result["success"] is False
        assert "zaman asimi" in str(result.get("error", ""))

    async def test_screenshot_process_failure(
        self,
        tmp_path: Path,
    ) -> None:
        """Subprocess basarisiz oldugunda hata dondurur."""
        runner = MaestroRunner(screenshots_dir=str(tmp_path))
        mock_proc = _make_mock_process(
            returncode=1,
            stdout=b"",
            stderr=b"No booted device",
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await runner.execute(
                "take_screenshot",
                {"platform": "ios"},
            )

        assert result["success"] is False
        assert "alinamadi" in str(result.get("error", ""))

    async def test_screenshot_os_error(
        self,
        maestro_runner: MaestroRunner,
    ) -> None:
        """OSError durumunda hata dondurur."""
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=OSError("Permission denied"),
        ):
            result = await maestro_runner.execute(
                "take_screenshot",
                {"platform": "ios"},
            )

        assert result["success"] is False
        assert "hatasi" in str(result.get("error", ""))


# --- list_flows Tests ---


class TestListFlows:
    """list_flows aksiyon testleri."""

    async def test_missing_flows_dir_returns_error(
        self,
        maestro_runner: MaestroRunner,
    ) -> None:
        """flows_dir parametresi olmadan hata dondurur."""
        result = await maestro_runner.execute("list_flows", {})
        assert result["success"] is False
        assert "flows_dir" in str(result.get("error", ""))

    async def test_nonexistent_dir_returns_error(
        self,
        maestro_runner: MaestroRunner,
    ) -> None:
        """Mevcut olmayan dizin hata dondurur."""
        result = await maestro_runner.execute(
            "list_flows",
            {"flows_dir": "/nonexistent/dir"},
        )
        assert result["success"] is False
        assert "bulunamadi" in str(result.get("error", ""))

    async def test_list_flows_success(
        self,
        maestro_runner: MaestroRunner,
        tmp_flow_dir: Path,
    ) -> None:
        """Flow dosyalari basariyla listelenir."""
        result = await maestro_runner.execute(
            "list_flows",
            {"flows_dir": str(tmp_flow_dir)},
        )

        assert result["success"] is True
        assert result["flow_count"] == 2  # login.yaml + signup.yml
        flows = result["flows"]
        assert isinstance(flows, list)
        assert len(flows) == 2

        flow_names = [f["name"] for f in flows]  # type: ignore[index]
        assert "login.yaml" in flow_names
        assert "signup.yml" in flow_names

    async def test_list_flows_empty_dir(
        self,
        maestro_runner: MaestroRunner,
        tmp_path: Path,
    ) -> None:
        """Bos dizin sifir flow dondurur."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        result = await maestro_runner.execute(
            "list_flows",
            {"flows_dir": str(empty_dir)},
        )

        assert result["success"] is True
        assert result["flow_count"] == 0

    async def test_list_flows_includes_size(
        self,
        maestro_runner: MaestroRunner,
        tmp_flow_dir: Path,
    ) -> None:
        """Flow dosya boyutlari dahil edilir."""
        result = await maestro_runner.execute(
            "list_flows",
            {"flows_dir": str(tmp_flow_dir)},
        )

        assert result["success"] is True
        flows = result["flows"]
        assert isinstance(flows, list)
        for flow in flows:
            assert "size_bytes" in flow  # type: ignore[operator]
            assert isinstance(flow["size_bytes"], int)  # type: ignore[index]

    async def test_list_flows_empty_string(
        self,
        maestro_runner: MaestroRunner,
    ) -> None:
        """Bos string hata dondurur."""
        result = await maestro_runner.execute(
            "list_flows",
            {"flows_dir": ""},
        )
        assert result["success"] is False

    async def test_list_flows_whitespace_string(
        self,
        maestro_runner: MaestroRunner,
    ) -> None:
        """Sadece bosluk iceren string hata dondurur."""
        result = await maestro_runner.execute(
            "list_flows",
            {"flows_dir": "   "},
        )
        assert result["success"] is False


# --- validate_flow Tests ---


class TestValidateFlow:
    """validate_flow aksiyon testleri."""

    async def test_missing_flow_file_returns_error(
        self,
        maestro_runner: MaestroRunner,
    ) -> None:
        """flow_file parametresi olmadan hata dondurur."""
        result = await maestro_runner.execute("validate_flow", {})
        assert result["success"] is False
        assert "flow_file" in str(result.get("error", ""))

    async def test_nonexistent_file_returns_error(
        self,
        maestro_runner: MaestroRunner,
    ) -> None:
        """Mevcut olmayan dosya hata dondurur."""
        result = await maestro_runner.execute(
            "validate_flow",
            {"flow_file": "/nonexistent/flow.yaml"},
        )
        assert result["success"] is False
        assert "bulunamadi" in str(result.get("error", ""))

    async def test_validate_valid_flow(
        self,
        maestro_runner: MaestroRunner,
        tmp_flow_file: Path,
    ) -> None:
        """Gecerli flow dosyasi dogrulanir."""
        result = await maestro_runner.execute(
            "validate_flow",
            {"flow_file": str(tmp_flow_file)},
        )

        assert result["success"] is True
        assert result["valid"] is True
        assert result["has_known_commands"] is True
        assert "file_size_bytes" in result
        assert isinstance(result["file_size_bytes"], int)

    async def test_validate_empty_flow(
        self,
        maestro_runner: MaestroRunner,
        tmp_empty_flow: Path,
    ) -> None:
        """Bos flow dosyasi hata dondurur."""
        result = await maestro_runner.execute(
            "validate_flow",
            {"flow_file": str(tmp_empty_flow)},
        )

        assert result["success"] is False
        assert "bos" in str(result.get("error", "")).lower()

    async def test_validate_flow_no_known_commands(
        self,
        maestro_runner: MaestroRunner,
        tmp_no_commands_flow: Path,
    ) -> None:
        """Bilinen komut icermeyen flow dosyasi dogrulanir ama uyari verir."""
        result = await maestro_runner.execute(
            "validate_flow",
            {"flow_file": str(tmp_no_commands_flow)},
        )

        assert result["success"] is True
        assert result["has_known_commands"] is False

    async def test_validate_invalid_extension(
        self,
        maestro_runner: MaestroRunner,
    ) -> None:
        """Gecersiz uzantili dosya reddedilir."""
        result = await maestro_runner.execute(
            "validate_flow",
            {"flow_file": "flow.txt"},
        )
        assert result["success"] is False


# --- _collect_screenshots Tests ---


class TestCollectScreenshots:
    """_collect_screenshots testleri."""

    async def test_no_s3_uploader_returns_empty(
        self,
        maestro_runner_no_s3: MaestroRunner,
    ) -> None:
        """S3 uploader yoksa bos liste dondurur."""
        result = await maestro_runner_no_s3._collect_screenshots(None, None)
        assert result == []

    async def test_nonexistent_dir_returns_empty(self) -> None:
        """Mevcut olmayan dizin bos liste dondurur."""
        runner = MaestroRunner(
            s3_uploader=AsyncMock(spec=S3Uploader),
            screenshots_dir="/nonexistent/dir",
        )
        result = await runner._collect_screenshots(None, None)
        assert result == []

    async def test_collect_screenshots_from_dir(
        self,
        mock_s3_uploader: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Dizindeki screenshot'lar S3'e yuklenir."""
        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()
        (screenshots_dir / "step1.png").write_bytes(b"png-data-1")
        (screenshots_dir / "step2.jpg").write_bytes(b"jpg-data-2")
        (screenshots_dir / "log.txt").write_text("not a screenshot")

        runner = MaestroRunner(
            s3_uploader=mock_s3_uploader,
            screenshots_dir=str(screenshots_dir),
        )

        result = await runner._collect_screenshots(None, "my-project")
        assert len(result) == 2
        assert mock_s3_uploader.upload_bytes.call_count == 2


# --- BaseRunner integration Tests ---


class TestBaseRunnerIntegration:
    """BaseRunner.run() ile MaestroRunner entegrasyon testleri."""

    async def test_run_adds_execution_time(
        self,
        maestro_runner: MaestroRunner,
        tmp_flow_file: Path,
    ) -> None:
        """BaseRunner.run() execution_time_ms ekler."""
        mock_proc = _make_mock_process(returncode=0, stdout=b"Passed: 1, Failed: 0")

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await maestro_runner.run(
                "run_flow",
                {
                    "flow_file": str(tmp_flow_file),
                    "platform": "ios",
                },
            )

        assert "execution_time_ms" in result
        assert isinstance(result["execution_time_ms"], int)

    async def test_run_unknown_action_raises_error(
        self,
        maestro_runner: MaestroRunner,
    ) -> None:
        """BaseRunner.run() bilinmeyen aksiyonda hata firlatir."""
        with pytest.raises(ValueError, match="Bilinmeyen Maestro aksiyonu"):
            await maestro_runner.run("nonexistent", {})
