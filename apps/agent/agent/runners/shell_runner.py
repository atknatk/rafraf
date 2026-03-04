"""Shell runner - guvenlikli shell komut calistirici.

Whitelist/blacklist mekanizmasi, injection korunmasi, timeout handling
ve output capture ozellikleri ile guvenli komut calistirma saglar.
docs/08_Host_Agent_Specification.md Bolum 5.5 ile uyumludur.
"""

from __future__ import annotations

import asyncio
import contextlib
import shlex

import structlog

from agent.runners.base import BaseRunner
from agent.security.blacklist import Blacklist
from agent.security.sanitizer import Sanitizer
from agent.security.whitelist import Whitelist

logger = structlog.get_logger()

# Desteklenen aksiyonlar
_SUPPORTED_ACTIONS: frozenset[str] = frozenset(
    [
        "run_command",
    ],
)

# Varsayilan degerler
_DEFAULT_TIMEOUT: int = 60
_MAX_TIMEOUT: int = 300  # 5 dakika
_MAX_STDOUT_CHARS: int = 5_000
_MAX_STDERR_CHARS: int = 2_000


class ShellRunnerError(Exception):
    """Shell runner'a ozel hata sinifi."""


class ShellRunner(BaseRunner):
    """Guvenlikli shell komut calistirici.

    Whitelist/blacklist mekanizmasi, injection korunmasi,
    timeout handling ve output capture ozellikleri saglar.

    Guvenlik kontrol sirasi:
    1. Blacklist kontrolu (ASLA calistirma)
    2. Injection kontrolu (metacharacter filtreleme)
    3. Approval kontrolu (onay gerektirir)
    4. Whitelist kontrolu (izin verilmis mi?)

    Args:
        whitelist: Whitelist kontrolcusu. None ise varsayilan kullanilir.
        blacklist: Blacklist kontrolcusu. None ise varsayilan kullanilir.
        sanitizer: Sanitizer kontrolcusu. None ise varsayilan kullanilir.
        default_timeout: Varsayilan komut timeout suresi (saniye).
        max_timeout: Maksimum izin verilen timeout suresi (saniye).
    """

    def __init__(
        self,
        whitelist: Whitelist | None = None,
        blacklist: Blacklist | None = None,
        sanitizer: Sanitizer | None = None,
        default_timeout: int = _DEFAULT_TIMEOUT,
        max_timeout: int = _MAX_TIMEOUT,
    ) -> None:
        self._whitelist = whitelist or Whitelist()
        self._blacklist = blacklist or Blacklist()
        self._sanitizer = sanitizer or Sanitizer()
        self._default_timeout = default_timeout
        self._max_timeout = max_timeout

    @property
    def tool_name(self) -> str:
        """Runner'in destekledigi tool adi."""
        return "shell"

    async def execute(self, action: str, params: dict[str, object]) -> dict[str, object]:
        """Shell aksiyonunu calistirir.

        Args:
            action: Aksiyon adi (run_command).
            params: Aksiyon parametreleri.
                - command (str): Calistirilacak komut (zorunlu).
                - cwd (str | None): Calisma dizini (opsiyonel).
                - timeout (int | None): Timeout suresi saniye (opsiyonel).

        Returns:
            Sonuc dictionary'si.

        Raises:
            ValueError: Bilinmeyen aksiyon.
        """
        if action not in _SUPPORTED_ACTIONS:
            msg = (
                f"Bilinmeyen Shell aksiyonu: {action}. Desteklenenler: {sorted(_SUPPORTED_ACTIONS)}"
            )
            raise ValueError(msg)

        command = params.get("command")
        if not isinstance(command, str) or not command.strip():
            return {
                "success": False,
                "error": "command parametresi zorunlu (bos olmayan string)",
            }

        cwd = params.get("cwd")
        if cwd is not None and not isinstance(cwd, str):
            cwd = None

        timeout = params.get("timeout")
        if not isinstance(timeout, int) or timeout < 1:
            timeout = self._default_timeout
        # Max timeout sinirlama
        timeout = min(timeout, self._max_timeout)

        return await self._run_command(command=command.strip(), cwd=cwd, timeout=timeout)

    async def _run_command(
        self,
        command: str,
        cwd: str | None,
        timeout: int,
    ) -> dict[str, object]:
        """Guvenlik kontrollerinden gecen komutu calistirir.

        Args:
            command: Calistirilacak shell komutu.
            cwd: Calisma dizini.
            timeout: Timeout suresi (saniye).

        Returns:
            Sonuc dictionary'si.
        """
        # 1. Blacklist kontrolu — ASLA calistirma
        if self._blacklist.is_blacklisted(command):
            matched_pattern = self._blacklist.find_blacklist_match(command)
            await logger.awarning(
                "Blacklist'te yasakli komut engellendi",
                command=command,
                matched_pattern=matched_pattern,
            )
            return {
                "success": False,
                "error": "YASAKLI_KOMUT: Bu komut guvenlik politikasi tarafindan engellendi.",
                "blocked_reason": "blacklist",
                "matched_pattern": matched_pattern,
            }

        # 2. Injection kontrolu — metacharacter filtreleme
        if self._sanitizer.has_injection(command):
            matched_pattern = self._sanitizer.find_injection_match(command)
            await logger.awarning(
                "Injection pattern tespit edildi",
                command=command,
                matched_pattern=matched_pattern,
            )
            return {
                "success": False,
                "error": (
                    "INJECTION_TESPIT: Komut guvenlik acisindan sakincali "
                    "karakter veya pattern iceriyor."
                ),
                "blocked_reason": "injection",
                "matched_pattern": matched_pattern,
            }

        # 3. Approval kontrolu — backend'e sor
        if self._blacklist.requires_approval(command):
            matched_pattern = self._blacklist.find_approval_match(command)
            await logger.ainfo(
                "Onay gerektiren komut tespit edildi",
                command=command,
                matched_pattern=matched_pattern,
            )
            return {
                "success": False,
                "error": "ONAY_GEREKLI: Bu komut calistirilmadan once onay gerektirir.",
                "blocked_reason": "approval_required",
                "command": command,
                "matched_pattern": matched_pattern,
            }

        # 4. Whitelist kontrolu
        if not self._whitelist.is_allowed(command):
            await logger.awarning(
                "Whitelist'te olmayan komut engellendi",
                command=command,
            )
            return {
                "success": False,
                "error": "TANIMLANMAMIS_KOMUT: Komut whitelist'te bulunmuyor.",
                "blocked_reason": "whitelist",
            }

        # 5. Komutu calistir
        return await self._execute_subprocess(command=command, cwd=cwd, timeout=timeout)

    async def _execute_subprocess(
        self,
        command: str,
        cwd: str | None,
        timeout: int,
    ) -> dict[str, object]:
        """Subprocess ile komutu calistirir.

        Komut shlex.split ile token'lara ayrilir ve
        create_subprocess_exec ile calistirilir (shell=False).

        Args:
            command: Calistirilacak komut.
            cwd: Calisma dizini.
            timeout: Timeout suresi (saniye).

        Returns:
            Sonuc dictionary'si.
        """
        try:
            args = shlex.split(command)
        except ValueError as exc:
            return {
                "success": False,
                "error": f"Komut parse edilemedi: {exc}",
            }

        if not args:
            return {
                "success": False,
                "error": "Komut bos.",
            }

        await logger.ainfo(
            "Shell komutu calistiriliyor",
            command=command,
            cwd=cwd,
            timeout=timeout,
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )

            stdout_str = stdout_bytes.decode("utf-8", errors="replace")[-_MAX_STDOUT_CHARS:]
            stderr_str = stderr_bytes.decode("utf-8", errors="replace")[-_MAX_STDERR_CHARS:]

            # grep/diff exit code 1 = eslesme/fark yok, hata degil
            is_success = proc.returncode == 0 or (
                proc.returncode == 1 and args[0] in ("grep", "diff")
            )

            return {
                "success": is_success,
                "output": stdout_str,
                "error": stderr_str if not is_success else None,
                "return_code": proc.returncode,
                "timed_out": False,
            }

        except TimeoutError:
            await logger.awarning(
                "Shell komutu zaman asimi",
                command=command,
                timeout=timeout,
            )
            # Timeout durumunda process'i sonlandir
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=5)
            except (TimeoutError, ProcessLookupError):
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()

            return {
                "success": False,
                "output": "",
                "error": f"Komut {timeout} saniye icinde tamamlanamadi.",
                "timed_out": True,
            }

        except FileNotFoundError:
            return {
                "success": False,
                "error": f"Komut bulunamadi: {args[0]}",
            }

        except PermissionError:
            return {
                "success": False,
                "error": f"Komut calistirma izni yok: {args[0]}",
            }

        except OSError as exc:
            return {
                "success": False,
                "error": f"Komut calistirma hatasi: {exc}",
            }
