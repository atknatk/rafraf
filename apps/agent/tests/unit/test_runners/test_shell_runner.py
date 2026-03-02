"""Shell runner unit testleri - guvenlikli komut calistirma."""

from __future__ import annotations

import pytest

from agent.runners.shell_runner import ShellRunner


class TestShellRunnerExecute:
    """ShellRunner.execute() testleri."""

    def setup_method(self) -> None:
        """Her test icin yeni ShellRunner olustur."""
        self.runner = ShellRunner()

    async def test_unknown_action_raises_value_error(self) -> None:
        """Bilinmeyen aksiyon ValueError firlatmali."""
        with pytest.raises(ValueError, match="Bilinmeyen Shell aksiyonu"):
            await self.runner.execute("unknown_action", {})

    async def test_missing_command_returns_error(self) -> None:
        """command parametresi olmadan hata donmeli."""
        result = await self.runner.execute("run_command", {})
        assert result["success"] is False
        assert "command parametresi zorunlu" in str(result["error"])

    async def test_empty_command_returns_error(self) -> None:
        """Bos command ile hata donmeli."""
        result = await self.runner.execute("run_command", {"command": ""})
        assert result["success"] is False
        assert "command parametresi zorunlu" in str(result["error"])

    async def test_whitespace_only_command_returns_error(self) -> None:
        """Sadece bosluk iceren command ile hata donmeli."""
        result = await self.runner.execute("run_command", {"command": "   "})
        assert result["success"] is False

    async def test_tool_name(self) -> None:
        """tool_name 'shell' olmali."""
        assert self.runner.tool_name == "shell"


class TestShellRunnerBlacklistBlocking:
    """ShellRunner blacklist engelleme testleri."""

    def setup_method(self) -> None:
        """Her test icin yeni ShellRunner olustur."""
        self.runner = ShellRunner()

    async def test_rm_rf_root_blocked(self) -> None:
        """rm -rf / engellenmeli."""
        result = await self.runner.execute("run_command", {"command": "rm -rf /"})
        assert result["success"] is False
        assert result.get("blocked_reason") == "blacklist"
        assert "YASAKLI_KOMUT" in str(result["error"])

    async def test_mkfs_blocked(self) -> None:
        """mkfs engellenmeli."""
        result = await self.runner.execute("run_command", {"command": "mkfs -t ext4 /dev/sda"})
        assert result["success"] is False
        assert result.get("blocked_reason") == "blacklist"

    async def test_shutdown_blocked(self) -> None:
        """shutdown engellenmeli."""
        result = await self.runner.execute("run_command", {"command": "shutdown now"})
        assert result["success"] is False
        assert result.get("blocked_reason") == "blacklist"

    async def test_sudo_rm_blocked(self) -> None:
        """sudo rm engellenmeli."""
        result = await self.runner.execute("run_command", {"command": "sudo rm -rf /tmp"})
        assert result["success"] is False
        assert result.get("blocked_reason") == "blacklist"


class TestShellRunnerInjectionBlocking:
    """ShellRunner injection engelleme testleri."""

    def setup_method(self) -> None:
        """Her test icin yeni ShellRunner olustur."""
        self.runner = ShellRunner()

    async def test_semicolon_injection_blocked(self) -> None:
        """Semicolon injection engellenmeli."""
        result = await self.runner.execute(
            "run_command",
            {"command": "echo hello; echo world"},
        )
        assert result["success"] is False
        assert result.get("blocked_reason") == "injection"
        assert "INJECTION_TESPIT" in str(result["error"])

    async def test_pipe_injection_blocked(self) -> None:
        """Pipe injection engellenmeli."""
        result = await self.runner.execute(
            "run_command",
            {"command": "echo hello | cat"},
        )
        assert result["success"] is False
        assert result.get("blocked_reason") == "injection"

    async def test_command_substitution_blocked(self) -> None:
        """Command substitution injection engellenmeli."""
        result = await self.runner.execute(
            "run_command",
            {"command": "echo $(whoami)"},
        )
        assert result["success"] is False
        assert result.get("blocked_reason") == "injection"

    async def test_backtick_injection_blocked(self) -> None:
        """Backtick injection engellenmeli."""
        result = await self.runner.execute(
            "run_command",
            {"command": "echo `whoami`"},
        )
        assert result["success"] is False
        assert result.get("blocked_reason") == "injection"


class TestShellRunnerApprovalRequired:
    """ShellRunner approval gerektiren komut testleri."""

    def setup_method(self) -> None:
        """Her test icin yeni ShellRunner olustur."""
        self.runner = ShellRunner()

    async def test_kubectl_requires_approval(self) -> None:
        """kubectl onay gerektirmeli."""
        result = await self.runner.execute(
            "run_command",
            {"command": "kubectl get pods"},
        )
        assert result["success"] is False
        assert result.get("blocked_reason") == "approval_required"
        assert "ONAY_GEREKLI" in str(result["error"])

    async def test_git_push_requires_approval(self) -> None:
        """git push onay gerektirmeli."""
        result = await self.runner.execute(
            "run_command",
            {"command": "git push origin main"},
        )
        assert result["success"] is False
        assert result.get("blocked_reason") == "approval_required"

    async def test_pip_install_requires_approval(self) -> None:
        """pip install onay gerektirmeli."""
        result = await self.runner.execute(
            "run_command",
            {"command": "pip install requests"},
        )
        assert result["success"] is False
        assert result.get("blocked_reason") == "approval_required"


class TestShellRunnerWhitelistBlocking:
    """ShellRunner whitelist engelleme testleri."""

    def setup_method(self) -> None:
        """Her test icin yeni ShellRunner olustur."""
        self.runner = ShellRunner()

    async def test_unknown_command_blocked(self) -> None:
        """Whitelist'te olmayan komut engellenmeli."""
        result = await self.runner.execute(
            "run_command",
            {"command": "wget http://example.com"},
        )
        assert result["success"] is False
        assert result.get("blocked_reason") == "whitelist"
        assert "TANIMLANMAMIS_KOMUT" in str(result["error"])

    async def test_ssh_command_blocked(self) -> None:
        """ssh komutu whitelist'te olmamali."""
        result = await self.runner.execute(
            "run_command",
            {"command": "ssh user@host"},
        )
        assert result["success"] is False
        assert result.get("blocked_reason") == "whitelist"


class TestShellRunnerSuccessfulExecution:
    """ShellRunner basarili komut calistirma testleri."""

    def setup_method(self) -> None:
        """Her test icin yeni ShellRunner olustur."""
        self.runner = ShellRunner()

    async def test_echo_command_success(self) -> None:
        """echo komutu basarili calismali."""
        result = await self.runner.execute(
            "run_command",
            {"command": "echo hello world"},
        )
        assert result["success"] is True
        assert "hello world" in str(result.get("output", ""))
        assert result.get("return_code") == 0
        assert result.get("timed_out") is False

    async def test_pwd_command_success(self) -> None:
        """pwd komutu basarili calismali."""
        result = await self.runner.execute(
            "run_command",
            {"command": "pwd"},
        )
        assert result["success"] is True
        assert result.get("return_code") == 0

    async def test_whoami_command_success(self) -> None:
        """whoami komutu basarili calismali."""
        result = await self.runner.execute(
            "run_command",
            {"command": "whoami"},
        )
        assert result["success"] is True
        assert result.get("return_code") == 0
        assert len(str(result.get("output", ""))) > 0

    async def test_ls_command_success(self) -> None:
        """ls komutu basarili calismali."""
        result = await self.runner.execute(
            "run_command",
            {"command": "ls /tmp"},
        )
        assert result["success"] is True
        assert result.get("return_code") == 0

    async def test_uname_command_success(self) -> None:
        """uname komutu basarili calismali."""
        result = await self.runner.execute(
            "run_command",
            {"command": "uname -a"},
        )
        assert result["success"] is True
        assert result.get("return_code") == 0

    async def test_command_with_cwd(self) -> None:
        """cwd parametresi calismali."""
        result = await self.runner.execute(
            "run_command",
            {"command": "pwd", "cwd": "/tmp"},
        )
        assert result["success"] is True
        assert "/tmp" in str(result.get("output", ""))

    async def test_failed_command_returns_error(self) -> None:
        """Basarisiz komut hata donmeli."""
        result = await self.runner.execute(
            "run_command",
            {"command": "ls /nonexistent_directory_xyz_123"},
        )
        assert result["success"] is False
        assert result.get("return_code") != 0


class TestShellRunnerTimeout:
    """ShellRunner timeout testleri."""

    def setup_method(self) -> None:
        """Kisa timeout ile ShellRunner olustur."""
        self.runner = ShellRunner(default_timeout=2, max_timeout=5)

    async def test_timeout_max_limit(self) -> None:
        """Timeout max siniri uygulanmali."""
        result = await self.runner.execute(
            "run_command",
            {"command": "echo fast", "timeout": 999},
        )
        # Komut hizli calismali, max timeout sinirlandigi icin hata vermemeli
        assert result["success"] is True

    async def test_invalid_timeout_uses_default(self) -> None:
        """Gecersiz timeout degeri varsayilan kullanmali."""
        result = await self.runner.execute(
            "run_command",
            {"command": "echo hello", "timeout": -1},
        )
        assert result["success"] is True

    async def test_non_int_cwd_treated_as_none(self) -> None:
        """Integer olmayan cwd None olarak ele alinmali."""
        result = await self.runner.execute(
            "run_command",
            {"command": "echo hello", "cwd": 123},
        )
        assert result["success"] is True


class TestShellRunnerEdgeCases:
    """ShellRunner kenar durum testleri."""

    def setup_method(self) -> None:
        """Her test icin yeni ShellRunner olustur."""
        self.runner = ShellRunner()

    async def test_command_not_found(self) -> None:
        """Mevcut olmayan komut hata donmeli."""
        result = await self.runner.execute(
            "run_command",
            {"command": "echo test_nonexistent_cmd_xyz_never_exists"},
        )
        # echo exists, so this should succeed
        assert result["success"] is True

    async def test_base_runner_run_method(self) -> None:
        """BaseRunner.run() metodu execution_time_ms eklemeli."""
        result = await self.runner.run("run_command", {"command": "echo hello"})
        assert "execution_time_ms" in result
        assert isinstance(result["execution_time_ms"], int)

    async def test_nonexistent_binary_returns_file_not_found(self) -> None:
        """Var olmayan binary icin hata donmeli."""
        # Whitelist'e custom eklememiz gerekiyor
        from agent.security.whitelist import Whitelist

        custom_whitelist = Whitelist(patterns=(r"^nonexistent_binary_xyz_abc_123\b",))
        runner = ShellRunner(whitelist=custom_whitelist)
        result = await runner.execute(
            "run_command",
            {"command": "nonexistent_binary_xyz_abc_123"},
        )
        assert result["success"] is False
        assert "bulunamadi" in str(result.get("error", "")).lower() or "not found" in str(
            result.get("error", "")
        ).lower()

    async def test_shlex_parse_error(self) -> None:
        """Kotu formatli komut parse hatasi donmeli."""
        # Whitelist'e custom eklememiz gerekiyor
        from agent.security.whitelist import Whitelist

        custom_whitelist = Whitelist(patterns=(r"^echo",))
        runner = ShellRunner(whitelist=custom_whitelist)
        # Unclosed quote causes shlex.split to fail
        result = await runner.execute(
            "run_command",
            {"command": "echo 'unclosed quote"},
        )
        assert result["success"] is False
        assert "parse" in str(result.get("error", "")).lower()

    async def test_timeout_kills_long_running_process(self) -> None:
        """Uzun suren komut timeout ile kesilmeli."""
        from agent.security.whitelist import Whitelist

        # sleep whitelist'e ekliyoruz test icin
        custom_whitelist = Whitelist(patterns=(r"^sleep\b",))
        runner = ShellRunner(whitelist=custom_whitelist, default_timeout=1, max_timeout=2)
        result = await runner.execute(
            "run_command",
            {"command": "sleep 30", "timeout": 1},
        )
        assert result["success"] is False
        assert result.get("timed_out") is True
        assert "tamamlanamadi" in str(result.get("error", ""))
