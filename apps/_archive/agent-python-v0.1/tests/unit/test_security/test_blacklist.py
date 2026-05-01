"""Blacklist unit testleri - yasakli komut ve onay gerektiren komut pattern'leri."""

from __future__ import annotations

import pytest

from agent.security.blacklist import (
    DEFAULT_APPROVAL_PATTERNS,
    DEFAULT_BLACKLIST_PATTERNS,
    Blacklist,
)


class TestBlacklistIsBlacklisted:
    """Blacklist.is_blacklisted() testleri."""

    def setup_method(self) -> None:
        """Her test icin yeni Blacklist olustur."""
        self.blacklist = Blacklist()

    # --- Pozitif testler (yasakli komutlar) ---

    @pytest.mark.parametrize(
        "command",
        [
            "rm -rf /",
            "rm -rf / --no-preserve-root",
            "rm  -rf   /",
        ],
    )
    def test_rm_rf_root_blacklisted(self, command: str) -> None:
        """rm -rf / her zaman yasakli olmali."""
        assert self.blacklist.is_blacklisted(command) is True

    def test_mkfs_blacklisted(self) -> None:
        """mkfs her zaman yasakli olmali."""
        assert self.blacklist.is_blacklisted("mkfs -t ext4 /dev/sda1") is True

    def test_dd_if_dev_blacklisted(self) -> None:
        """dd if=/dev yasakli olmali."""
        assert self.blacklist.is_blacklisted("dd if=/dev/zero of=/dev/sda") is True

    def test_fork_bomb_blacklisted(self) -> None:
        """Fork bomb yasakli olmali."""
        assert self.blacklist.is_blacklisted(":() { :|:& };:") is True

    def test_dev_sd_redirect_blacklisted(self) -> None:
        """>/dev/sd yasakli olmali."""
        assert self.blacklist.is_blacklisted("echo test > /dev/sda") is True

    @pytest.mark.parametrize(
        "command",
        [
            "shutdown now",
            "shutdown -h now",
            "reboot",
            "halt",
        ],
    )
    def test_system_power_commands_blacklisted(self, command: str) -> None:
        """Sistem kapatma/yeniden baslatma yasakli olmali."""
        assert self.blacklist.is_blacklisted(command) is True

    def test_passwd_blacklisted(self) -> None:
        """passwd yasakli olmali."""
        assert self.blacklist.is_blacklisted("passwd root") is True

    def test_sudo_rm_blacklisted(self) -> None:
        """sudo rm yasakli olmali."""
        assert self.blacklist.is_blacklisted("sudo rm -rf /tmp/test") is True

    # --- Negatif testler (yasakli olmayan komutlar) ---

    @pytest.mark.parametrize(
        "command",
        [
            "git status",
            "ls -la",
            "echo hello",
            "python -m pytest",
            "npm test",
        ],
    )
    def test_safe_commands_not_blacklisted(self, command: str) -> None:
        """Guvenli komutlar blacklist'te olmamali."""
        assert self.blacklist.is_blacklisted(command) is False

    def test_empty_command_not_blacklisted(self) -> None:
        """Bos komut blacklisted olmamali."""
        assert self.blacklist.is_blacklisted("") is False
        assert self.blacklist.is_blacklisted("   ") is False


class TestBlacklistRequiresApproval:
    """Blacklist.requires_approval() testleri."""

    def setup_method(self) -> None:
        """Her test icin yeni Blacklist olustur."""
        self.blacklist = Blacklist()

    @pytest.mark.parametrize(
        "command",
        [
            "kubectl get pods",
            "kubectl apply -f deploy.yaml",
            "aws s3 ls",
            "aws ec2 describe-instances",
            "docker push myimage:latest",
            "git push origin main",
            "npm publish",
            "rm file.txt",
            "rm -r directory/",
            "chmod 755 script.sh",
            "chown user:group file.txt",
            "pip install requests",
            "sudo apt update",
        ],
    )
    def test_approval_required_commands(self, command: str) -> None:
        """Onay gerektiren komutlar dogru tespit edilmeli."""
        assert self.blacklist.requires_approval(command) is True

    @pytest.mark.parametrize(
        "command",
        [
            "git status",
            "ls -la",
            "echo hello",
            "python -m pytest",
            "npm test",
            "docker ps",
        ],
    )
    def test_no_approval_for_safe_commands(self, command: str) -> None:
        """Guvenli komutlar onay gerektirmemeli."""
        assert self.blacklist.requires_approval(command) is False

    def test_empty_command_no_approval(self) -> None:
        """Bos komut onay gerektirmemeli."""
        assert self.blacklist.requires_approval("") is False


class TestBlacklistFindMatch:
    """Blacklist.find_blacklist_match() ve find_approval_match() testleri."""

    def setup_method(self) -> None:
        """Her test icin yeni Blacklist olustur."""
        self.blacklist = Blacklist()

    def test_find_blacklist_match_rm_rf(self) -> None:
        """rm -rf / icin eslesen pattern bulunmali."""
        pattern = self.blacklist.find_blacklist_match("rm -rf /")
        assert pattern is not None
        assert "rm" in pattern

    def test_find_blacklist_match_none(self) -> None:
        """Guvenli komut icin None donmeli."""
        assert self.blacklist.find_blacklist_match("git status") is None

    def test_find_approval_match_kubectl(self) -> None:
        """kubectl icin eslesen approval pattern bulunmali."""
        pattern = self.blacklist.find_approval_match("kubectl get pods")
        assert pattern is not None
        assert "kubectl" in pattern

    def test_find_approval_match_none(self) -> None:
        """Onay gerektirmeyen komut icin None donmeli."""
        assert self.blacklist.find_approval_match("git status") is None

    def test_empty_blacklist_match(self) -> None:
        """Bos komut icin None donmeli."""
        assert self.blacklist.find_blacklist_match("") is None

    def test_empty_approval_match(self) -> None:
        """Bos komut icin None donmeli."""
        assert self.blacklist.find_approval_match("") is None


class TestBlacklistCustomPatterns:
    """Ozel pattern'ler ile Blacklist testleri."""

    def test_custom_blacklist_patterns(self) -> None:
        """Ozel blacklist pattern'leri calismali."""
        custom = Blacklist(blacklist_patterns=(r"^dangerous\b",))
        assert custom.is_blacklisted("dangerous command") is True
        assert custom.is_blacklisted("safe command") is False

    def test_custom_approval_patterns(self) -> None:
        """Ozel approval pattern'leri calismali."""
        custom = Blacklist(approval_patterns=(r"^deploy\b",))
        assert custom.requires_approval("deploy production") is True
        assert custom.requires_approval("test command") is False

    def test_patterns_properties(self) -> None:
        """Pattern property'leri dogru donmeli."""
        bl = Blacklist()
        assert bl.blacklist_patterns == DEFAULT_BLACKLIST_PATTERNS
        assert bl.approval_patterns == DEFAULT_APPROVAL_PATTERNS
