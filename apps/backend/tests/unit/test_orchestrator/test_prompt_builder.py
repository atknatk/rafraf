"""Unit tests for the prompt builder module."""

from app.orchestrator.prompt_builder import build_system_prompt, get_base_prompt


class TestBuildSystemPrompt:
    """Tests for the build_system_prompt function."""

    def test_base_prompt_included(self) -> None:
        """System prompt should contain the base prompt."""
        prompt = build_system_prompt()
        assert "AI Proje Yoneticisisin" in prompt
        assert "Supervisor" in prompt

    def test_project_context_added(self) -> None:
        """Project context should be appended when provided."""
        context = "Project X: nextjs, running"
        prompt = build_system_prompt(project_context=context)
        assert context in prompt
        assert "Aktif Projeler" in prompt

    def test_host_status_added(self) -> None:
        """Host status should be appended when provided."""
        status = "macbook-pro: online (CPU: 23%)"
        prompt = build_system_prompt(host_status=status)
        assert status in prompt
        assert "Host Agent Durumlari" in prompt

    def test_recent_history_added(self) -> None:
        """Recent history should be appended when provided."""
        history = "docker_manager compose_up project-x"
        prompt = build_system_prompt(recent_history=history)
        assert history in prompt
        assert "Son Islem Gecmisi" in prompt

    def test_no_context_only_base(self) -> None:
        """Without any context, only the base prompt should be returned."""
        prompt = build_system_prompt()
        base = get_base_prompt()
        assert prompt == base

    def test_all_contexts_combined(self) -> None:
        """All context sections should be included when all provided."""
        prompt = build_system_prompt(
            project_context="project info",
            host_status="host info",
            recent_history="history info",
        )
        assert "project info" in prompt
        assert "host info" in prompt
        assert "history info" in prompt

    def test_approval_rules_in_base(self) -> None:
        """Base prompt should contain approval rules."""
        prompt = get_base_prompt()
        assert "Onay Gerektiren Islemler" in prompt
        assert "kubectl" in prompt
        assert "docker push" in prompt


class TestGetBasePrompt:
    """Tests for the get_base_prompt function."""

    def test_returns_string(self) -> None:
        """get_base_prompt should return a string."""
        prompt = get_base_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_consistent_results(self) -> None:
        """Multiple calls should return the same result."""
        prompt1 = get_base_prompt()
        prompt2 = get_base_prompt()
        assert prompt1 == prompt2
