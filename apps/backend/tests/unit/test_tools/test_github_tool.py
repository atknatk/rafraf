"""Unit tests for GitHubTool."""

import json
from unittest.mock import AsyncMock, patch

from app.schemas.github import GitHubCommit, GitHubIssue, GitHubRepoInfo
from app.tools.github_tool import GitHubTool


class TestGetDefinition:
    """Tests for GitHubTool.get_definition."""

    def test_definition_name(self) -> None:
        """get_definition should return tool named github_manager."""
        tool = GitHubTool()
        definition = tool.get_definition()
        assert definition.name == "github_manager"

    def test_definition_has_input_schema(self) -> None:
        """get_definition should have a valid input schema."""
        tool = GitHubTool()
        definition = tool.get_definition()
        assert "properties" in definition.input_schema
        assert "action" in definition.input_schema["properties"]  # type: ignore[operator]
        assert "repo" in definition.input_schema["properties"]  # type: ignore[operator]

    def test_definition_required_fields(self) -> None:
        """get_definition should require action and repo."""
        tool = GitHubTool()
        definition = tool.get_definition()
        assert "required" in definition.input_schema
        assert "action" in definition.input_schema["required"]  # type: ignore[operator]
        assert "repo" in definition.input_schema["required"]  # type: ignore[operator]


class TestRequiresActionApproval:
    """Tests for GitHubTool.requires_action_approval."""

    def test_create_issue_requires_approval(self) -> None:
        """create_issue should require approval."""
        tool = GitHubTool()
        assert tool.requires_action_approval("create_issue") is True

    def test_update_issue_requires_approval(self) -> None:
        """update_issue should require approval."""
        tool = GitHubTool()
        assert tool.requires_action_approval("update_issue") is True

    def test_close_issue_requires_approval(self) -> None:
        """close_issue should require approval."""
        tool = GitHubTool()
        assert tool.requires_action_approval("close_issue") is True

    def test_list_issues_no_approval(self) -> None:
        """list_issues should not require approval."""
        tool = GitHubTool()
        assert tool.requires_action_approval("list_issues") is False

    def test_get_pr_no_approval(self) -> None:
        """get_pr should not require approval."""
        tool = GitHubTool()
        assert tool.requires_action_approval("get_pr") is False

    def test_add_labels_no_approval(self) -> None:
        """add_labels should not require approval."""
        tool = GitHubTool()
        assert tool.requires_action_approval("add_labels") is False


class TestExecute:
    """Tests for GitHubTool.execute."""

    async def test_missing_action_returns_error(self) -> None:
        """execute should return error for missing action."""
        tool = GitHubTool()
        result = await tool.execute({"repo": "owner/repo"})
        parsed = json.loads(result)
        assert "error" in parsed

    async def test_missing_repo_returns_error(self) -> None:
        """execute should return error for missing repo."""
        tool = GitHubTool()
        result = await tool.execute({"action": "list_issues"})
        parsed = json.loads(result)
        assert "error" in parsed

    async def test_unknown_action_returns_error(self) -> None:
        """execute should return error for unknown action."""
        tool = GitHubTool()
        with patch.object(tool._service, "list_issues"):
            result = await tool.execute({"action": "unknown_action", "repo": "owner/repo"})
        parsed = json.loads(result)
        assert "error" in parsed
        assert "Bilinmeyen" in parsed["error"]

    async def test_list_issues_delegates_to_service(self) -> None:
        """execute list_issues should call service.list_issues."""
        tool = GitHubTool()
        mock_issues = [
            GitHubIssue(
                number=1,
                title="Test",
                state="open",
                labels=["bug"],
                assignees=[],
                created_at="2026-01-01",
                updated_at="2026-01-02",
                html_url="https://github.com/o/r/issues/1",
            )
        ]

        with patch.object(
            tool._service, "list_issues", new_callable=AsyncMock, return_value=mock_issues
        ):
            result = await tool.execute(
                {"action": "list_issues", "repo": "owner/repo", "state": "open"}
            )

        parsed = json.loads(result)
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0]["number"] == 1

    async def test_get_issue_requires_issue_number(self) -> None:
        """execute get_issue should require issue_number."""
        tool = GitHubTool()
        result = await tool.execute({"action": "get_issue", "repo": "owner/repo"})
        parsed = json.loads(result)
        assert "error" in parsed

    async def test_list_commits_delegates_to_service(self) -> None:
        """execute list_commits should call service.list_commits."""
        tool = GitHubTool()
        mock_commits = [GitHubCommit(sha="abc", message="Fix", author="dev", date="2026-01-01")]

        with patch.object(
            tool._service, "list_commits", new_callable=AsyncMock, return_value=mock_commits
        ):
            result = await tool.execute(
                {"action": "list_commits", "repo": "owner/repo", "branch": "main"}
            )

        parsed = json.loads(result)
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0]["sha"] == "abc"

    async def test_get_repo_info_delegates_to_service(self) -> None:
        """execute get_repo_info should call service.get_repo_info."""
        tool = GitHubTool()
        mock_info = GitHubRepoInfo(
            full_name="owner/repo",
            default_branch="main",
            open_issues_count=5,
            forks_count=2,
            stargazers_count=10,
            html_url="https://github.com/owner/repo",
        )

        with patch.object(
            tool._service, "get_repo_info", new_callable=AsyncMock, return_value=mock_info
        ):
            result = await tool.execute({"action": "get_repo_info", "repo": "owner/repo"})

        parsed = json.loads(result)
        assert parsed["full_name"] == "owner/repo"
        assert parsed["open_issues_count"] == 5

    async def test_service_error_returns_error_json(self) -> None:
        """execute should return error JSON when service raises."""
        tool = GitHubTool()
        from app.services.github_service import GitHubServiceError

        with patch.object(
            tool._service,
            "list_issues",
            new_callable=AsyncMock,
            side_effect=GitHubServiceError("Not found", status_code=404),
        ):
            result = await tool.execute({"action": "list_issues", "repo": "owner/repo"})

        assert "error" in result
        assert "GitHub API hatasi" in result


class TestToolRegistration:
    """Tests for tool registration flow."""

    def test_register_adds_to_registry(self) -> None:
        """register should add tool to ToolRegistry."""
        from app.orchestrator.tool_registry import ToolRegistry

        tool = GitHubTool()
        registry = ToolRegistry()
        tool.register(registry)

        assert registry.has_tool("github_manager")
        assert registry.tool_count == 1

    def test_registered_handler_is_callable(self) -> None:
        """registered handler should be the execute method."""
        from app.orchestrator.tool_registry import ToolRegistry

        tool = GitHubTool()
        registry = ToolRegistry()
        tool.register(registry)

        handler = registry.get_handler("github_manager")
        assert handler is not None
