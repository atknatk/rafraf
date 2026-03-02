"""Shell komut sanitizer - injection korunmasi.

Shell metacharacter filtreleme ile komut enjeksiyon saldirilarini engeller.
"""

from __future__ import annotations

import re

import structlog

logger = structlog.get_logger()

# Shell metacharacter / injection pattern'leri
DEFAULT_INJECTION_PATTERNS: tuple[str, ...] = (
    # Komut zincirleme operatorleri
    r";",
    r"\|",
    r"&&",
    r"\|\|",
    # Backtick command substitution
    r"`",
    # Dollar sign command substitution
    r"\$\(",
    # Variable expansion
    r"\$\{",
    # Output redirection (append)
    r">>",
    # Process substitution
    r"<\(",
    r">\(",
    # Input redirection ile tehlike
    r"<\s*/dev/",
    # Newline injection
    r"\n",
    r"\r",
)


class Sanitizer:
    """Shell komut sanitizer - injection pattern'lerini tespit eder.

    Verilen komuttaki shell metacharacter'leri ve injection
    pattern'lerini kontrol eder.

    Args:
        patterns: Injection regex pattern listesi.
            None ise varsayilan pattern'ler kullanilir.
    """

    def __init__(self, patterns: tuple[str, ...] | None = None) -> None:
        self._patterns = patterns or DEFAULT_INJECTION_PATTERNS
        self._compiled: list[re.Pattern[str]] = [
            re.compile(p) for p in self._patterns
        ]

    @property
    def patterns(self) -> tuple[str, ...]:
        """Aktif injection pattern'leri."""
        return self._patterns

    def has_injection(self, command: str) -> bool:
        """Komutta injection pattern'i olup olmadigini kontrol eder.

        Args:
            command: Kontrol edilecek shell komutu.

        Returns:
            True eger komut injection pattern'lerinden birine eslesiyorsa.
        """
        if not command or not command.strip():
            return False

        return any(pattern.search(command) for pattern in self._compiled)

    def find_injection_match(self, command: str) -> str | None:
        """Komuttaki ilk injection pattern'ini bulur.

        Args:
            command: Kontrol edilecek shell komutu.

        Returns:
            Eslesen pattern string'i veya None.
        """
        if not command or not command.strip():
            return None

        for i, compiled_pattern in enumerate(self._compiled):
            if compiled_pattern.search(command):
                return self._patterns[i]

        return None

    def get_all_violations(self, command: str) -> list[str]:
        """Komuttaki tum injection pattern eslesmelerini dondurur.

        Args:
            command: Kontrol edilecek shell komutu.

        Returns:
            Eslesen pattern string listesi.
        """
        if not command or not command.strip():
            return []

        violations: list[str] = []
        for i, compiled_pattern in enumerate(self._compiled):
            if compiled_pattern.search(command):
                violations.append(self._patterns[i])

        return violations
