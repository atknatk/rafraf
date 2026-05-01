"""Whitelist mekanizmasi - izin verilen shell komut pattern'leri.

Sadece whitelist'teki pattern'lere eslesen komutlar calistirilabilir.
Pattern'ler docs/08_Host_Agent_Specification.md ile uyumludur.
"""

from __future__ import annotations

import re

import structlog

logger = structlog.get_logger()

# Izin verilen komut pattern'leri (regex)
# docs/08_Host_Agent_Specification.md Bolum 5.5 referans
DEFAULT_WHITELIST_PATTERNS: tuple[str, ...] = (
    # Git (sadece okuma islemleri)
    r"^git\s+(status|log|diff|branch|show|remote|tag)",
    # Dosya okuma
    r"^ls\b",
    r"^cat\b",
    r"^head\b",
    r"^tail\b",
    r"^grep\b",
    r"^find\b",
    r"^wc\b",
    # Docker (sadece okuma islemleri)
    r"^docker\s+(ps|logs|stats|inspect|images)",
    # npm (guvenli islemler)
    r"^npm\s+(test|run\s+lint|run\s+build|run\s+dev|list)",
    r"^npx\b",
    # Python (test ve lint)
    r"^python\s+-m\s+(pytest|pylint|black|mypy)",
    # Node.js
    r"^node\b",
    # curl (sadece GET)
    r"^curl\s+.*--request\s+GET",
    r"^curl\s+-s",
    # Sistem bilgisi (sadece okuma)
    r"^df\b",
    r"^du\b",
    r"^free\b",
    r"^top\s+-bn1",
    r"^ps\b",
    # Ortam bilgisi
    r"^which\b",
    r"^whoami\b",
    r"^uname\b",
    r"^hostname\b",
    # echo (debug ve test icin)
    r"^echo\b",
    # pwd
    r"^pwd\b",
)


class Whitelist:
    """Shell komut whitelist kontrolcusu.

    Verilen komutu whitelist pattern'lerine karsi kontrol eder.
    Sadece eslesen komutlar calistirilabilir.

    Args:
        patterns: Izin verilen regex pattern listesi.
            None ise varsayilan pattern'ler kullanilir.
    """

    def __init__(self, patterns: tuple[str, ...] | None = None) -> None:
        self._patterns = patterns or DEFAULT_WHITELIST_PATTERNS
        self._compiled: list[re.Pattern[str]] = [re.compile(p) for p in self._patterns]

    @property
    def patterns(self) -> tuple[str, ...]:
        """Aktif whitelist pattern'leri."""
        return self._patterns

    def is_allowed(self, command: str) -> bool:
        """Komutun whitelist'te olup olmadigini kontrol eder.

        Args:
            command: Kontrol edilecek shell komutu.

        Returns:
            True eger komut whitelist'teki en az bir pattern'e eslesiyorsa.
        """
        stripped = command.strip()
        if not stripped:
            return False

        return any(pattern.search(stripped) for pattern in self._compiled)

    def find_matching_pattern(self, command: str) -> str | None:
        """Komutun eslestigi whitelist pattern'ini bulur.

        Args:
            command: Kontrol edilecek shell komutu.

        Returns:
            Eslesen pattern string'i veya None.
        """
        stripped = command.strip()
        if not stripped:
            return None

        for i, compiled_pattern in enumerate(self._compiled):
            if compiled_pattern.search(stripped):
                return self._patterns[i]

        return None
