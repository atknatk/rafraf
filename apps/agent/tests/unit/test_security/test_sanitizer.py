"""Sanitizer unit testleri - injection pattern tespiti."""

from __future__ import annotations

import pytest

from agent.security.sanitizer import DEFAULT_INJECTION_PATTERNS, Sanitizer


class TestSanitizerHasInjection:
    """Sanitizer.has_injection() testleri."""

    def setup_method(self) -> None:
        """Her test icin yeni Sanitizer olustur."""
        self.sanitizer = Sanitizer()

    # --- Pozitif testler (injection tespit edilmeli) ---

    @pytest.mark.parametrize(
        "command",
        [
            "ls; rm -rf /",  # Semicolon
            "cat file | grep secret",  # Pipe
            "echo hello && rm -rf /",  # AND chain
            "echo hello || rm -rf /",  # OR chain
            "echo `whoami`",  # Backtick
            "echo $(whoami)",  # Dollar paren
            "echo ${HOME}",  # Variable expansion
            "echo test >> /etc/passwd",  # Append redirect
            "cat <(ls)",  # Process substitution
            "diff <(ls /a) >(ls /b)",  # Process substitution
            "cat < /dev/urandom",  # /dev/ input redirect
        ],
    )
    def test_injection_patterns_detected(self, command: str) -> None:
        """Injection pattern'leri tespit edilmeli."""
        assert self.sanitizer.has_injection(command) is True

    def test_newline_injection_detected(self) -> None:
        """Newline injection tespit edilmeli."""
        assert self.sanitizer.has_injection("ls\nrm -rf /") is True
        assert self.sanitizer.has_injection("ls\rrm -rf /") is True

    # --- Negatif testler (temiz komutlar) ---

    @pytest.mark.parametrize(
        "command",
        [
            "git status",
            "ls -la /tmp",
            "cat file.txt",
            "python -m pytest",
            "npm test",
            "docker ps",
            "echo hello world",
            "grep -r pattern .",
            "find . -name '*.py'",
            "whoami",
            "pwd",
        ],
    )
    def test_clean_commands_no_injection(self, command: str) -> None:
        """Temiz komutlarda injection tespit edilmemeli."""
        assert self.sanitizer.has_injection(command) is False

    def test_empty_command_no_injection(self) -> None:
        """Bos komut injection icermemeli."""
        assert self.sanitizer.has_injection("") is False
        assert self.sanitizer.has_injection("   ") is False


class TestSanitizerFindInjectionMatch:
    """Sanitizer.find_injection_match() testleri."""

    def setup_method(self) -> None:
        """Her test icin yeni Sanitizer olustur."""
        self.sanitizer = Sanitizer()

    def test_find_semicolon_injection(self) -> None:
        """Semicolon injection pattern'i bulunmali."""
        pattern = self.sanitizer.find_injection_match("ls; rm /")
        assert pattern is not None

    def test_find_pipe_injection(self) -> None:
        """Pipe injection pattern'i bulunmali."""
        pattern = self.sanitizer.find_injection_match("cat file | grep pass")
        assert pattern is not None

    def test_find_no_match_returns_none(self) -> None:
        """Temiz komut icin None donmeli."""
        assert self.sanitizer.find_injection_match("git status") is None

    def test_empty_command_returns_none(self) -> None:
        """Bos komut icin None donmeli."""
        assert self.sanitizer.find_injection_match("") is None


class TestSanitizerGetAllViolations:
    """Sanitizer.get_all_violations() testleri."""

    def setup_method(self) -> None:
        """Her test icin yeni Sanitizer olustur."""
        self.sanitizer = Sanitizer()

    def test_multiple_violations(self) -> None:
        """Birden fazla violation tespit edilmeli."""
        # Semicolon + pipe
        violations = self.sanitizer.get_all_violations("ls; cat file | grep x")
        assert len(violations) >= 2

    def test_no_violations(self) -> None:
        """Temiz komutta violation olmamali."""
        violations = self.sanitizer.get_all_violations("git status")
        assert violations == []

    def test_empty_command_no_violations(self) -> None:
        """Bos komut icin bos liste donmeli."""
        assert self.sanitizer.get_all_violations("") == []


class TestSanitizerCustomPatterns:
    """Ozel pattern'ler ile Sanitizer testleri."""

    def test_custom_patterns(self) -> None:
        """Ozel pattern'ler calismali."""
        custom = Sanitizer(patterns=(r"INJECT",))
        assert custom.has_injection("INJECT test") is True
        assert custom.has_injection("safe command") is False

    def test_patterns_property(self) -> None:
        """patterns property dogru donmeli."""
        s = Sanitizer()
        assert s.patterns == DEFAULT_INJECTION_PATTERNS
