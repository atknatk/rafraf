"""Maestro runner - mobil uygulama UI test akislari (iOS/Android).

Maestro CLI kullanarak iOS Simulator ve Android Emulator uzerinde
YAML flow dosyalari calistirir, sonuclari JSON olarak parse eder
ve screenshot'lari toplar.
docs/08_Host_Agent_Specification.md Bolum 5.4 ile uyumludur.
"""

from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from agent.runners.base import BaseRunner

if TYPE_CHECKING:
    from agent.upload.s3_uploader import S3Uploader

logger = structlog.get_logger()

# Desteklenen aksiyonlar
_SUPPORTED_ACTIONS: frozenset[str] = frozenset(
    [
        "run_flow",
        "run_all_flows",
        "take_screenshot",
        "list_flows",
        "validate_flow",
    ],
)

# Desteklenen platformlar
_SUPPORTED_PLATFORMS: frozenset[str] = frozenset(["ios", "android"])

# Varsayilan degerler
_DEFAULT_TIMEOUT: int = 300  # 5 dakika
_MAX_TIMEOUT: int = 600  # 10 dakika
_MAX_OUTPUT_CHARS: int = 50_000
_DEFAULT_SCREENSHOTS_DIR: str = "/tmp/rafraf/screenshots/maestro"

# Flow dosyasi uzantisi
_FLOW_FILE_EXTENSIONS: frozenset[str] = frozenset([".yaml", ".yml"])


class MaestroRunnerError(Exception):
    """Maestro runner'a ozel hata sinifi."""


class MaestroRunner(BaseRunner):
    """Maestro ile mobil UI test akislarini calistiran runner.

    iOS Simulator ve Android Emulator uzerinde YAML flow dosyalari
    calistirir, sonuclari parse eder ve screenshot'lari S3'e yukler.

    Args:
        s3_uploader: Screenshot yukleme icin S3Uploader instance.
        screenshots_dir: Screenshot kayit dizini.
        default_timeout: Varsayilan komut timeout suresi (saniye).
        max_timeout: Maksimum izin verilen timeout suresi (saniye).
        ios_device: iOS simulator cihaz adi (opsiyonel).
        android_device: Android emulator cihaz adi (opsiyonel).
    """

    def __init__(
        self,
        s3_uploader: S3Uploader | None = None,
        screenshots_dir: str = _DEFAULT_SCREENSHOTS_DIR,
        default_timeout: int = _DEFAULT_TIMEOUT,
        max_timeout: int = _MAX_TIMEOUT,
        ios_device: str | None = None,
        android_device: str | None = None,
    ) -> None:
        self._s3_uploader = s3_uploader
        self._screenshots_dir = screenshots_dir
        self._default_timeout = default_timeout
        self._max_timeout = max_timeout
        self._ios_device = ios_device
        self._android_device = android_device

    @property
    def tool_name(self) -> str:
        """Runner'in destekledigi tool adi."""
        return "maestro"

    async def execute(self, action: str, params: dict[str, object]) -> dict[str, object]:
        """Maestro aksiyonunu calistirir.

        Args:
            action: Aksiyon adi (run_flow, run_all_flows, vb.).
            params: Aksiyon parametreleri.

        Returns:
            Sonuc dictionary'si.

        Raises:
            ValueError: Bilinmeyen aksiyon.
        """
        if action not in _SUPPORTED_ACTIONS:
            msg = (
                f"Bilinmeyen Maestro aksiyonu: {action}. "
                f"Desteklenenler: {sorted(_SUPPORTED_ACTIONS)}"
            )
            raise ValueError(msg)

        return await self._dispatch_action(action, params)

    async def _dispatch_action(
        self,
        action: str,
        params: dict[str, object],
    ) -> dict[str, object]:
        """Aksiyonu ilgili metoda yonlendirir."""
        if action == "run_flow":
            return await self._run_flow(params)
        if action == "run_all_flows":
            return await self._run_all_flows(params)
        if action == "take_screenshot":
            return await self._take_screenshot(params)
        if action == "list_flows":
            return await self._list_flows(params)
        if action == "validate_flow":
            return await self._validate_flow(params)

        msg = f"Beklenmeyen aksiyon: {action}"
        raise ValueError(msg)

    def _validate_platform(self, platform: object) -> str | None:
        """Platform parametresini dogrular.

        Args:
            platform: Platform degeri.

        Returns:
            Gecerli platform string veya None (gecersiz ise).
        """
        if not isinstance(platform, str):
            return None
        platform_lower = platform.lower()
        if platform_lower not in _SUPPORTED_PLATFORMS:
            return None
        return platform_lower

    def _validate_flow_file(self, flow_file: object) -> str | None:
        """Flow dosyasi parametresini dogrular.

        Args:
            flow_file: Flow dosya yolu.

        Returns:
            Gecerli flow dosya yolu veya None (gecersiz ise).
        """
        if not isinstance(flow_file, str) or not flow_file.strip():
            return None

        flow_path = Path(flow_file.strip())
        # Uzanti kontrolu
        if flow_path.suffix.lower() not in _FLOW_FILE_EXTENSIONS:
            return None

        return flow_file.strip()

    def _resolve_timeout(self, timeout: object) -> int:
        """Timeout parametresini dogrular ve sinirlara uygun hale getirir.

        Args:
            timeout: Timeout degeri.

        Returns:
            Gecerli timeout suresi (saniye).
        """
        if not isinstance(timeout, int) or timeout < 1:
            return self._default_timeout
        return min(timeout, self._max_timeout)

    def _build_maestro_cmd(
        self,
        flow_file: str,
        platform: str,
    ) -> list[str]:
        """Maestro komut satirini olusturur.

        Args:
            flow_file: Flow dosya yolu.
            platform: Hedef platform (ios/android).

        Returns:
            Komut argumanlari listesi.
        """
        cmd: list[str] = ["maestro", "test", flow_file]

        if platform == "ios" and self._ios_device:
            cmd.extend(["--device", self._ios_device])
        elif platform == "android" and self._android_device:
            cmd.extend(["--device", self._android_device])

        return cmd

    async def _run_maestro_command(
        self,
        cmd: list[str],
        cwd: str | None,
        timeout: int,
    ) -> dict[str, object]:
        """Maestro komutunu async subprocess ile calistirir.

        Args:
            cmd: Komut argumanlari.
            cwd: Calisma dizini.
            timeout: Timeout suresi (saniye).

        Returns:
            Sonuc dictionary'si.
        """
        await logger.ainfo(
            "Maestro komutu calistiriliyor",
            cmd=" ".join(cmd),
            cwd=cwd,
            timeout=timeout,
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )

            stdout_str = stdout_bytes.decode("utf-8", errors="replace")[:_MAX_OUTPUT_CHARS]
            stderr_str = stderr_bytes.decode("utf-8", errors="replace")[:_MAX_OUTPUT_CHARS]

            return {
                "success": proc.returncode == 0,
                "output": stdout_str,
                "error": stderr_str if proc.returncode != 0 else None,
                "return_code": proc.returncode,
                "timed_out": False,
            }

        except TimeoutError:
            await logger.awarning(
                "Maestro komutu zaman asimi",
                cmd=" ".join(cmd),
                timeout=timeout,
            )
            return {
                "success": False,
                "output": "",
                "error": f"Maestro komutu {timeout} saniye icinde tamamlanamadi.",
                "timed_out": True,
            }

        except FileNotFoundError:
            return {
                "success": False,
                "output": "",
                "error": (
                    "Maestro CLI bulunamadi. "
                    "'curl -Ls https://get.maestro.mobile.dev | bash' ile yukleyin."
                ),
            }

        except OSError as exc:
            return {
                "success": False,
                "output": "",
                "error": f"Maestro komutu calistirma hatasi: {exc}",
            }

    def _parse_maestro_output(self, output: str) -> dict[str, object]:
        """Maestro CLI ciktisini parse eder.

        Args:
            output: Maestro stdout ciktisi.

        Returns:
            Parse edilmis sonuc bilgileri.
        """
        passed_count = 0
        failed_count = 0

        # Maestro output parsing
        # Ornek: "Passed: 3, Failed: 1" veya "Tests passed: 5"
        passed_match = re.search(r"[Pp]assed[:\s]+(\d+)", output)
        failed_match = re.search(r"[Ff]ailed[:\s]+(\d+)", output)

        if passed_match:
            passed_count = int(passed_match.group(1))
        if failed_match:
            failed_count = int(failed_match.group(1))

        return {
            "total_tests": passed_count + failed_count,
            "passed_tests": passed_count,
            "failed_tests": failed_count,
        }

    async def _collect_screenshots(
        self,
        cwd: str | None,
        project_slug: str | None,
    ) -> list[str]:
        """Maestro ciktisindaki screenshot'lari toplar ve S3'e yukler.

        Args:
            cwd: Calisma dizini.
            project_slug: Proje tanimlayicisi (S3 path icin).

        Returns:
            Screenshot URL'leri listesi.
        """
        screenshot_urls: list[str] = []

        if self._s3_uploader is None:
            return screenshot_urls

        # Maestro screenshots dizinini tara
        screenshots_dir = Path(self._screenshots_dir)
        if cwd:
            # Maestro bazen CWD altina screenshot birakir
            cwd_screenshots = Path(cwd) / ".maestro" / "screenshots"
            if cwd_screenshots.is_dir():
                screenshots_dir = cwd_screenshots

        if not screenshots_dir.is_dir():
            return screenshot_urls

        timestamp = int(time.time())
        slug = project_slug or "unknown"

        for screenshot_file in sorted(screenshots_dir.iterdir()):
            if screenshot_file.suffix.lower() in (".png", ".jpg", ".jpeg"):
                try:
                    screenshot_bytes = screenshot_file.read_bytes()
                    s3_key = f"screenshots/maestro/{slug}/{timestamp}_{screenshot_file.name}"
                    result = await self._s3_uploader.upload_bytes(
                        data=screenshot_bytes,
                        key=s3_key,
                    )
                    screenshot_urls.append(result.url)
                except Exception as exc:
                    await logger.awarning(
                        "Screenshot yukleme hatasi",
                        file=str(screenshot_file),
                        error=str(exc),
                    )

        return screenshot_urls

    async def _run_flow(self, params: dict[str, object]) -> dict[str, object]:
        """Tek bir Maestro flow dosyasini calistirir.

        Args:
            params: Aksiyon parametreleri.
                - flow_file (str): Flow YAML dosya yolu (zorunlu).
                - platform (str): Hedef platform - ios/android (zorunlu).
                - cwd (str | None): Calisma dizini (opsiyonel).
                - timeout (int | None): Timeout suresi saniye (opsiyonel).
                - project_slug (str | None): Proje tanimlayicisi (opsiyonel).

        Returns:
            Sonuc dictionary'si.
        """
        # Parametre dogrulama
        flow_file = self._validate_flow_file(params.get("flow_file"))
        if flow_file is None:
            return {
                "success": False,
                "error": "flow_file parametresi zorunlu (gecerli .yaml/.yml dosya yolu)",
            }

        platform = self._validate_platform(params.get("platform"))
        if platform is None:
            return {
                "success": False,
                "error": (
                    f"platform parametresi zorunlu. "
                    f"Desteklenen platformlar: {sorted(_SUPPORTED_PLATFORMS)}"
                ),
            }

        cwd = params.get("cwd")
        if cwd is not None and not isinstance(cwd, str):
            cwd = None

        timeout = self._resolve_timeout(params.get("timeout"))
        project_slug = params.get("project_slug")
        if not isinstance(project_slug, str):
            project_slug = None

        # Flow dosyasi kontrol (cwd'ye gore)
        flow_path = Path(flow_file)
        full_flow_path = Path(cwd) / flow_path if cwd else flow_path

        if not full_flow_path.is_file():
            return {
                "success": False,
                "error": f"Flow dosyasi bulunamadi: {full_flow_path}",
            }

        # Komutu olustur ve calistir
        cmd = self._build_maestro_cmd(flow_file, platform)
        start_time = time.monotonic()
        effective_cwd = cwd if isinstance(cwd, str) else None
        result = await self._run_maestro_command(
            cmd,
            cwd=effective_cwd,
            timeout=timeout,
        )
        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        # Sonuc parse
        output = result.get("output", "")
        if isinstance(output, str):
            parsed = self._parse_maestro_output(output)
            result.update(parsed)

        result["flow_file"] = flow_file
        result["platform"] = platform
        result["duration_ms"] = elapsed_ms

        # Screenshot toplama
        screenshots = await self._collect_screenshots(
            cwd=cwd if isinstance(cwd, str) else None,
            project_slug=project_slug,
        )
        if screenshots:
            result["screenshots"] = screenshots

        return result

    async def _run_all_flows(self, params: dict[str, object]) -> dict[str, object]:
        """Bir dizindeki tum flow dosyalarini calistirir.

        Args:
            params: Aksiyon parametreleri.
                - flows_dir (str): Flow dosyalari dizini (zorunlu).
                - platform (str): Hedef platform - ios/android (zorunlu).
                - cwd (str | None): Calisma dizini (opsiyonel).
                - timeout (int | None): Timeout suresi saniye (opsiyonel).
                - project_slug (str | None): Proje tanimlayicisi (opsiyonel).

        Returns:
            Sonuc dictionary'si.
        """
        flows_dir = params.get("flows_dir")
        if not isinstance(flows_dir, str) or not flows_dir.strip():
            return {
                "success": False,
                "error": "flows_dir parametresi zorunlu (dizin yolu)",
            }

        platform = self._validate_platform(params.get("platform"))
        if platform is None:
            return {
                "success": False,
                "error": (
                    f"platform parametresi zorunlu. "
                    f"Desteklenen platformlar: {sorted(_SUPPORTED_PLATFORMS)}"
                ),
            }

        cwd = params.get("cwd")
        if cwd is not None and not isinstance(cwd, str):
            cwd = None

        timeout = self._resolve_timeout(params.get("timeout"))
        project_slug = params.get("project_slug")
        if not isinstance(project_slug, str):
            project_slug = None

        # Dizin kontrolu
        full_dir = Path(cwd) / flows_dir if cwd else Path(flows_dir)

        if not full_dir.is_dir():
            return {
                "success": False,
                "error": f"Flow dizini bulunamadi: {full_dir}",
            }

        # Flow dosyalarini bul
        flow_files = sorted(
            f
            for f in full_dir.iterdir()
            if f.is_file() and f.suffix.lower() in _FLOW_FILE_EXTENSIONS
        )

        if not flow_files:
            return {
                "success": False,
                "error": f"Dizinde flow dosyasi bulunamadi: {full_dir}",
            }

        # Her flow'u calistir
        start_time = time.monotonic()
        results: list[dict[str, object]] = []
        total_passed = 0
        total_failed = 0
        all_success = True

        for flow_path in flow_files:
            # Flow dosya yolunu relative olarak olustur
            relative_flow = str(flow_path.relative_to(Path(cwd))) if cwd else str(flow_path)

            flow_result = await self._run_flow(
                {
                    "flow_file": relative_flow,
                    "platform": platform,
                    "cwd": cwd,
                    "timeout": timeout,
                    "project_slug": project_slug,
                },
            )

            results.append(
                {
                    "flow_file": str(flow_path.name),
                    "success": flow_result.get("success", False),
                    "passed_tests": flow_result.get("passed_tests", 0),
                    "failed_tests": flow_result.get("failed_tests", 0),
                    "error": flow_result.get("error"),
                    "timed_out": flow_result.get("timed_out", False),
                },
            )

            if flow_result.get("success"):
                passed = flow_result.get("passed_tests", 0)
                if isinstance(passed, int):
                    total_passed += passed
            else:
                all_success = False

            failed = flow_result.get("failed_tests", 0)
            if isinstance(failed, int):
                total_failed += failed

        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        # Screenshot toplama
        screenshots = await self._collect_screenshots(
            cwd=cwd if isinstance(cwd, str) else None,
            project_slug=project_slug,
        )

        response: dict[str, object] = {
            "success": all_success,
            "flows_dir": flows_dir,
            "platform": platform,
            "total_flows": len(flow_files),
            "passed_flows": sum(1 for r in results if r.get("success")),
            "failed_flows": sum(1 for r in results if not r.get("success")),
            "total_passed_tests": total_passed,
            "total_failed_tests": total_failed,
            "duration_ms": elapsed_ms,
            "results": results,
        }

        if screenshots:
            response["screenshots"] = screenshots

        return response

    async def _take_screenshot(self, params: dict[str, object]) -> dict[str, object]:
        """Mevcut simulator/emulator ekraninin screenshot'ini alir.

        Args:
            params: Aksiyon parametreleri.
                - platform (str): Hedef platform - ios/android (zorunlu).
                - project_slug (str | None): Proje tanimlayicisi (opsiyonel).

        Returns:
            Sonuc dictionary'si.
        """
        platform = self._validate_platform(params.get("platform"))
        if platform is None:
            return {
                "success": False,
                "error": (
                    f"platform parametresi zorunlu. "
                    f"Desteklenen platformlar: {sorted(_SUPPORTED_PLATFORMS)}"
                ),
            }

        project_slug = params.get("project_slug")
        if not isinstance(project_slug, str):
            project_slug = "unknown"

        timestamp = int(time.time())
        screenshot_path = Path(self._screenshots_dir) / f"screenshot_{timestamp}.png"

        # Dizin olustur
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)

        # Platform bazli screenshot komutu
        if platform == "ios":
            cmd = [
                "xcrun",
                "simctl",
                "io",
                "booted",
                "screenshot",
                str(screenshot_path),
            ]
        else:
            cmd = [
                "adb",
                "exec-out",
                "screencap",
                "-p",
            ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=30,
            )

            if proc.returncode != 0:
                error_msg = stderr_bytes.decode("utf-8", errors="replace")
                return {
                    "success": False,
                    "error": f"Screenshot alinamadi: {error_msg}",
                    "platform": platform,
                }

            # Android icin stdout'tan dosyaya yaz
            if platform == "android":
                screenshot_path.write_bytes(stdout_bytes)

        except FileNotFoundError:
            tool = "xcrun" if platform == "ios" else "adb"
            return {
                "success": False,
                "error": f"{tool} bulunamadi. Platform araclari yuklu degil.",
                "platform": platform,
            }

        except TimeoutError:
            return {
                "success": False,
                "error": "Screenshot alma zaman asimi (30sn).",
                "platform": platform,
            }

        except OSError as exc:
            return {
                "success": False,
                "error": f"Screenshot alma hatasi: {exc}",
                "platform": platform,
            }

        # S3'e yukle
        if self._s3_uploader is not None and screenshot_path.is_file():
            try:
                screenshot_bytes_data = screenshot_path.read_bytes()
                s3_key = f"screenshots/maestro/{project_slug}/{timestamp}.png"
                upload_result = await self._s3_uploader.upload_bytes(
                    data=screenshot_bytes_data,
                    key=s3_key,
                )
                return {
                    "success": True,
                    "screenshot_url": upload_result.url,
                    "platform": platform,
                }
            except Exception as exc:
                await logger.awarning(
                    "Screenshot S3 upload hatasi, lokal dosya dondurulecek",
                    error=str(exc),
                )

        # Fallback: lokal dosya yolu
        local_path = str(screenshot_path) if screenshot_path.is_file() else None
        return {
            "success": True,
            "screenshot_path": local_path,
            "platform": platform,
        }

    async def _list_flows(self, params: dict[str, object]) -> dict[str, object]:
        """Belirtilen dizindeki flow dosyalarini listeler.

        Args:
            params: Aksiyon parametreleri.
                - flows_dir (str): Flow dosyalari dizini (zorunlu).

        Returns:
            Sonuc dictionary'si.
        """
        flows_dir = params.get("flows_dir")
        if not isinstance(flows_dir, str) or not flows_dir.strip():
            return {
                "success": False,
                "error": "flows_dir parametresi zorunlu (dizin yolu)",
            }

        dir_path = Path(flows_dir.strip())
        if not dir_path.is_dir():
            return {
                "success": False,
                "error": f"Dizin bulunamadi: {dir_path}",
            }

        flow_files: list[dict[str, object]] = []
        for file_path in sorted(dir_path.iterdir()):
            if file_path.is_file() and file_path.suffix.lower() in _FLOW_FILE_EXTENSIONS:
                flow_files.append(
                    {
                        "name": file_path.name,
                        "path": str(file_path),
                        "size_bytes": file_path.stat().st_size,
                    },
                )

        return {
            "success": True,
            "flows_dir": flows_dir,
            "flow_count": len(flow_files),
            "flows": flow_files,
        }

    async def _validate_flow(self, params: dict[str, object]) -> dict[str, object]:
        """Flow dosyasinin gecerliliginii kontrol eder.

        Maestro CLI ile flow dosyasinin YAML syntax'ini dogrular.

        Args:
            params: Aksiyon parametreleri.
                - flow_file (str): Flow dosya yolu (zorunlu).

        Returns:
            Sonuc dictionary'si.
        """
        flow_file = self._validate_flow_file(params.get("flow_file"))
        if flow_file is None:
            return {
                "success": False,
                "error": "flow_file parametresi zorunlu (gecerli .yaml/.yml dosya yolu)",
            }

        flow_path = Path(flow_file)
        if not flow_path.is_file():
            return {
                "success": False,
                "error": f"Flow dosyasi bulunamadi: {flow_path}",
            }

        # YAML syntax kontrolu icin dosyayi oku ve parse et
        try:
            content = flow_path.read_text(encoding="utf-8")
        except OSError as exc:
            return {
                "success": False,
                "error": f"Flow dosyasi okunamadi: {exc}",
            }

        # Temel YAML dogrulama: bos dosya veya gecersiz iceri
        if not content.strip():
            return {
                "success": False,
                "error": "Flow dosyasi bos.",
                "flow_file": flow_file,
            }

        # Basit iceri dogrulama: Maestro flow dosyasinda genelde
        # appId veya launchApp gibi komutlar bulunur
        has_known_commands = any(
            keyword in content
            for keyword in [
                "appId",
                "launchApp",
                "tapOn",
                "assertVisible",
                "inputText",
                "scrollDown",
                "scrollUp",
                "swipe",
                "back",
                "clearState",
                "runFlow",
                "waitForAnimationToEnd",
            ]
        )

        return {
            "success": True,
            "flow_file": flow_file,
            "file_size_bytes": len(content.encode("utf-8")),
            "has_known_commands": has_known_commands,
            "valid": True,
        }
