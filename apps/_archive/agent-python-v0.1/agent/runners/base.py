"""Base runner abstract sinifi - tum runner'lar bundan turetilir."""

from __future__ import annotations

import abc
import time

import structlog

logger = structlog.get_logger()


class BaseRunner(abc.ABC):
    """Tum runner'larin turetilecegi soyut temel sinif.

    Her runner, belirli bir tool tipine ait aksiyonlari calistirir.
    Ortak islevsellik (loglama, zamanlama) bu sinifta bulunur.
    """

    @property
    @abc.abstractmethod
    def tool_name(self) -> str:
        """Runner'in destekledigi tool adi (ornek: 'docker', 'shell')."""

    @abc.abstractmethod
    async def execute(self, action: str, params: dict[str, object]) -> dict[str, object]:
        """Belirtilen aksiyonu calistirir.

        Args:
            action: Calistirilacak aksiyon adi (ornek: 'compose_up').
            params: Aksiyona ozel parametreler.

        Returns:
            Sonuc dictionary'si. En azindan 'success' anahtari icermeli.

        Raises:
            ValueError: Bilinmeyen aksiyon.
        """

    async def run(self, action: str, params: dict[str, object]) -> dict[str, object]:
        """Aksiyonu calistirir, zamanlama ve loglama ekler.

        Alt siniflar execute() metodunu override eder, run() degil.

        Args:
            action: Calistirilacak aksiyon adi.
            params: Aksiyona ozel parametreler.

        Returns:
            Sonuc dictionary'si. 'execution_time_ms' alani eklenir.
        """
        start_time = time.monotonic()

        await logger.ainfo(
            "Runner aksiyon baslatiliyor",
            tool=self.tool_name,
            action=action,
        )

        try:
            result = await self.execute(action, params)
        except Exception:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            await logger.aexception(
                "Runner aksiyon hatasi",
                tool=self.tool_name,
                action=action,
                elapsed_ms=elapsed_ms,
            )
            raise

        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        result["execution_time_ms"] = elapsed_ms

        await logger.ainfo(
            "Runner aksiyon tamamlandi",
            tool=self.tool_name,
            action=action,
            success=result.get("success"),
            elapsed_ms=elapsed_ms,
        )

        return result
