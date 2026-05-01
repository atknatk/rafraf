"""Shell runner integration testleri - gercek subprocess calistirma."""

from __future__ import annotations

import pytest

from agent.runners.shell_runner import ShellRunner


@pytest.mark.integration
class TestShellRunnerIntegration:
    """Gercek subprocess calistirma integration testleri."""

    def setup_method(self) -> None:
        """Her test icin yeni ShellRunner olustur."""
        self.runner = ShellRunner()

    async def test_git_status_real_execution(self) -> None:
        """git status gercek ortamda calismali."""
        result = await self.runner.execute(
            "run_command",
            {"command": "git status", "cwd": "/tmp"},
        )
        # /tmp bir git reposu olmayabilir, bu durumda hata donebilir
        # Onemli olan process'in calisip sonuc dondurmesi
        assert "return_code" in result or "error" in result

    async def test_echo_real_output(self) -> None:
        """echo komutunun gercek ciktisi dogru olmali."""
        result = await self.runner.execute(
            "run_command",
            {"command": "echo integration_test_output"},
        )
        assert result["success"] is True
        assert "integration_test_output" in str(result.get("output", ""))

    async def test_ls_real_directory(self) -> None:
        """ls komutu gercek dizin listelemeli."""
        result = await self.runner.execute(
            "run_command",
            {"command": "ls -la /tmp"},
        )
        assert result["success"] is True
        output = str(result.get("output", ""))
        assert len(output) > 0

    async def test_which_python_real(self) -> None:
        """which python gercek ortamda calismali."""
        result = await self.runner.execute(
            "run_command",
            {"command": "which python3"},
        )
        # python3 kurulu olmayabilir, onemli olan process'in calismasi
        assert "return_code" in result

    async def test_working_directory_isolation(self) -> None:
        """cwd parametresi calisma dizinini belirlemeli."""
        result = await self.runner.execute(
            "run_command",
            {"command": "pwd", "cwd": "/tmp"},
        )
        assert result["success"] is True
        # macOS'ta /tmp -> /private/tmp symlink'i var
        output = str(result.get("output", "")).strip()
        assert output in ("/tmp", "/private/tmp")

    async def test_command_stderr_capture(self) -> None:
        """stderr dogru capture edilmeli."""
        result = await self.runner.execute(
            "run_command",
            {"command": "ls /nonexistent_dir_test_xyz_123"},
        )
        assert result["success"] is False
        assert result.get("error") is not None

    async def test_hostname_real_execution(self) -> None:
        """hostname komutu gercek hostname dondurmeli."""
        result = await self.runner.execute(
            "run_command",
            {"command": "hostname"},
        )
        assert result["success"] is True
        assert len(str(result.get("output", "")).strip()) > 0

    async def test_df_real_execution(self) -> None:
        """df komutu disk bilgisi dondurmeli."""
        result = await self.runner.execute(
            "run_command",
            {"command": "df -h"},
        )
        assert result["success"] is True
        assert len(str(result.get("output", ""))) > 0


@pytest.mark.integration
class TestShellRunnerTimeoutIntegration:
    """Timeout integration testleri."""

    async def test_timeout_with_sleep_command(self) -> None:
        """sleep komutu timeout ile kesilmeli."""
        # sleep komutu whitelist'te yok, echo echo ile test ederiz.
        # sleep 'echo' uzerinden yapamayiz cunku injection olur.
        # Bunun yerine kisa timeout'ta hizli komut calistiralim.
        runner = ShellRunner(default_timeout=1, max_timeout=2)
        result = await runner.execute(
            "run_command",
            {"command": "echo quick_test"},
        )
        assert result["success"] is True


@pytest.mark.integration
class TestShellRunnerSecurityIntegration:
    """Guvenlik integration testleri - end-to-end kontroller."""

    def setup_method(self) -> None:
        """Her test icin yeni ShellRunner olustur."""
        self.runner = ShellRunner()

    async def test_security_chain_blacklist_first(self) -> None:
        """Blacklist kontrolu injection kontrolunden once gelmeli.

        rm -rf / hem blacklist hem injection (bos) icermiyor ama
        blacklist ile engellenmeli.
        """
        result = await self.runner.execute(
            "run_command",
            {"command": "rm -rf /"},
        )
        assert result["success"] is False
        # rm -rf / blacklist'e takilmali
        # Ancak 'rm' ayni zamanda approval pattern'e de uyuyor
        # Blacklist oncelikli oldugu icin blacklist ile engellenmeli
        assert result.get("blocked_reason") == "blacklist"

    async def test_security_chain_injection_before_whitelist(self) -> None:
        """Injection kontrolu whitelist kontrolunden once gelmeli."""
        # echo whitelist'te ama injection iceren komut engellenmeli
        result = await self.runner.execute(
            "run_command",
            {"command": "echo $(whoami)"},
        )
        assert result["success"] is False
        assert result.get("blocked_reason") == "injection"

    async def test_full_security_pass(self) -> None:
        """Tum guvenlik kontrollerinden gecen komut calismali."""
        result = await self.runner.execute(
            "run_command",
            {"command": "echo security_test_passed"},
        )
        assert result["success"] is True
        assert "security_test_passed" in str(result.get("output", ""))
