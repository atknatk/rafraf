"""Blacklist mekanizmasi - yasakli shell komut pattern'leri.

Blacklist'teki pattern'lere eslesen komutlar ASLA calistirilmaz.
Pattern'ler docs/08_Host_Agent_Specification.md ile uyumludur.
"""

from __future__ import annotations

import re

import structlog

logger = structlog.get_logger()

# Yasakli komut pattern'leri (regex)
# docs/08_Host_Agent_Specification.md Bolum 5.5 referans
DEFAULT_BLACKLIST_PATTERNS: tuple[str, ...] = (
    # Tehlikeli silme islemleri
    r"rm\s+-rf\s+/",
    # Disk formatlama
    r"mkfs\b",
    # Disk silme
    r"dd\s+if=/dev",
    # Fork bomb
    r":\(\)\s*\{",
    # Disk uzerine yazma
    r">\s*/dev/sd",
    # Sistem kapatma
    r"shutdown\b",
    r"reboot\b",
    r"halt\b",
    # Parola degistirme
    r"passwd\b",
    # Sudo ile silme
    r"sudo\s+rm",
)

# Onay gerektiren komut pattern'leri
# docs/07_Security_Permissions_Cost_Analysis.md Bolum 3.2 referans
DEFAULT_APPROVAL_PATTERNS: tuple[str, ...] = (
    r"^kubectl\b",
    r"^aws\b",
    r"^docker\s+push",
    r"^git\s+push",
    r"^npm\s+publish",
    r"^rm\b",
    r"^chmod\b",
    r"^chown\b",
    r"^pip\s+install",
    r"^sudo\b",
)


class Blacklist:
    """Shell komut blacklist kontrolcusu.

    Verilen komutu blacklist ve approval pattern'lerine karsi kontrol eder.
    Blacklist'e eslesen komutlar ASLA calistirilmaz.
    Approval pattern'lerine eslesenlere onay gerektirir.

    Args:
        blacklist_patterns: Yasakli regex pattern listesi.
            None ise varsayilan pattern'ler kullanilir.
        approval_patterns: Onay gerektiren regex pattern listesi.
            None ise varsayilan pattern'ler kullanilir.
    """

    def __init__(
        self,
        blacklist_patterns: tuple[str, ...] | None = None,
        approval_patterns: tuple[str, ...] | None = None,
    ) -> None:
        self._blacklist_patterns = blacklist_patterns or DEFAULT_BLACKLIST_PATTERNS
        self._approval_patterns = approval_patterns or DEFAULT_APPROVAL_PATTERNS
        self._compiled_blacklist: list[re.Pattern[str]] = [
            re.compile(p) for p in self._blacklist_patterns
        ]
        self._compiled_approval: list[re.Pattern[str]] = [
            re.compile(p) for p in self._approval_patterns
        ]

    @property
    def blacklist_patterns(self) -> tuple[str, ...]:
        """Aktif blacklist pattern'leri."""
        return self._blacklist_patterns

    @property
    def approval_patterns(self) -> tuple[str, ...]:
        """Aktif approval pattern'leri."""
        return self._approval_patterns

    def is_blacklisted(self, command: str) -> bool:
        """Komutun blacklist'te olup olmadigini kontrol eder.

        Args:
            command: Kontrol edilecek shell komutu.

        Returns:
            True eger komut blacklist'teki en az bir pattern'e eslesiyorsa.
        """
        stripped = command.strip()
        if not stripped:
            return False

        return any(pattern.search(stripped) for pattern in self._compiled_blacklist)

    def requires_approval(self, command: str) -> bool:
        """Komutun onay gerektirip gerektirmedigini kontrol eder.

        Args:
            command: Kontrol edilecek shell komutu.

        Returns:
            True eger komut approval pattern'lerinden birine eslesiyorsa.
        """
        stripped = command.strip()
        if not stripped:
            return False

        return any(pattern.search(stripped) for pattern in self._compiled_approval)

    def find_blacklist_match(self, command: str) -> str | None:
        """Komutun eslestigi blacklist pattern'ini bulur.

        Args:
            command: Kontrol edilecek shell komutu.

        Returns:
            Eslesen pattern string'i veya None.
        """
        stripped = command.strip()
        if not stripped:
            return None

        for i, compiled_pattern in enumerate(self._compiled_blacklist):
            if compiled_pattern.search(stripped):
                return self._blacklist_patterns[i]

        return None

    def find_approval_match(self, command: str) -> str | None:
        """Komutun eslestigi approval pattern'ini bulur.

        Args:
            command: Kontrol edilecek shell komutu.

        Returns:
            Eslesen pattern string'i veya None.
        """
        stripped = command.strip()
        if not stripped:
            return None

        for i, compiled_pattern in enumerate(self._compiled_approval):
            if compiled_pattern.search(stripped):
                return self._approval_patterns[i]

        return None
