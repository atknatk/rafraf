"""Unit tests for GitHubService."""

import hashlib
import hmac
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.github_service import (
    GitHubRateLimitError,
    GitHubService,
    GitHubServiceError,
    _to_int,
    _to_str,
)


class TestToInt:
    """Tests for _to_int helper."""

    def test_int_value(self) -> None:
        assert _to_int(42) == 42

    def test_str_value(self) -> None:
        assert _to_int("10") == 10

    def test_float_value(self) -> None:
        assert _to_int(3.7) == 3

    def test_none_returns_default(self) -> None:
        assert _to_int(None) == 0

    def test_invalid_str_returns_default(self) -> None:
        assert _to_int("abc") == 0

    def test_custom_default(self) -> None:
        assert _to_int(None, default=-1) == -1


class TestToStr:
    """Tests for _to_str helper."""

    def test_str_value(self) -> None:
        assert _to_str("hello") == "hello"

    def test_int_value(self) -> None:
        assert _to_str(42) == "42"

    def test_none_returns_default(self) -> None:
        assert _to_str(None) == ""

    def test_custom_default(self) -> None:
        assert _to_str(None, default="N/A") == "N/A"


class TestVerifyWebhookSignature:
    """Tests for GitHubService.verify_webhook_signature."""

    def test_valid_signature(self) -> None:
        """verify_webhook_signature should return True for valid HMAC."""
        payload = b'{"action":"opened"}'
        secret = "test-secret"
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        signature = f"sha256={expected}"

        assert GitHubService.verify_webhook_signature(payload, signature, secret) is True

    def test_invalid_signature(self) -> None:
        """verify_webhook_signature should return False for invalid HMAC."""
        payload = b'{"action":"opened"}'
        secret = "test-secret"

        assert GitHubService.verify_webhook_signature(payload, "sha256=invalid", secret) is False

    def test_missing_prefix(self) -> None:
        """verify_webhook_signature should return False for missing sha256= prefix."""
        payload = b'{"action":"opened"}'
        secret = "test-secret"
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

        assert GitHubService.verify_webhook_signature(payload, expected, secret) is False


class TestFormatResult:
    """Tests for GitHubService.format_result."""

    def test_format_dict(self) -> None:
        """format_result should serialize dict to JSON."""
        result = GitHubService.format_result({"key": "value"})
        assert '"key": "value"' in result

    def test_format_list(self) -> None:
        """format_result should serialize list to JSON."""
        result = GitHubService.format_result([1, 2, 3])
        assert "[" in result

    def test_format_pydantic_model(self) -> None:
        """format_result should call model_dump on Pydantic models."""
        from app.schemas.github import GitHubBranch

        branch = GitHubBranch(name="main", sha="abc123", protected=True)
        result = GitHubService.format_result(branch)
        assert '"name": "main"' in result
        assert '"protected": true' in result


class TestListIssues:
    """Tests for GitHubService.list_issues."""

    async def test_list_issues_parses_response(self) -> None:
        """list_issues should parse GitHub API response into GitHubIssue list."""
        mock_response = httpx.Response(
            200,
            json=[
                {
                    "number": 1,
                    "title": "Test Issue",
                    "state": "open",
                    "body": "Issue body",
                    "labels": [{"name": "bug"}],
                    "assignees": [{"login": "user1"}],
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-02T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/issues/1",
                }
            ],
            headers={"X-RateLimit-Remaining": "4999"},
        )

        service = GitHubService()
        with patch.object(service, "_get_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get.return_value = mock_client

            issues = await service.list_issues("owner/repo")

        assert len(issues) == 1
        assert issues[0].number == 1
        assert issues[0].title == "Test Issue"
        assert issues[0].labels == ["bug"]
        assert issues[0].assignees == ["user1"]

    async def test_list_issues_skips_pull_requests(self) -> None:
        """list_issues should skip items with pull_request key."""
        mock_response = httpx.Response(
            200,
            json=[
                {
                    "number": 1,
                    "title": "PR",
                    "state": "open",
                    "pull_request": {"url": "..."},
                    "labels": [],
                    "assignees": [],
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-02T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/pull/1",
                },
                {
                    "number": 2,
                    "title": "Real Issue",
                    "state": "open",
                    "labels": [],
                    "assignees": [],
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-02T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/issues/2",
                },
            ],
            headers={"X-RateLimit-Remaining": "4999"},
        )

        service = GitHubService()
        with patch.object(service, "_get_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get.return_value = mock_client

            issues = await service.list_issues("owner/repo")

        assert len(issues) == 1
        assert issues[0].number == 2


class TestGetIssue:
    """Tests for GitHubService.get_issue."""

    async def test_get_issue_parses_response(self) -> None:
        """get_issue should parse single issue response."""
        mock_response = httpx.Response(
            200,
            json={
                "number": 42,
                "title": "Feature request",
                "state": "open",
                "body": "Please add this",
                "labels": [{"name": "enhancement"}, {"name": "priority:high"}],
                "assignees": [],
                "created_at": "2026-03-01T00:00:00Z",
                "updated_at": "2026-03-01T12:00:00Z",
                "html_url": "https://github.com/owner/repo/issues/42",
            },
            headers={"X-RateLimit-Remaining": "4999"},
        )

        service = GitHubService()
        with patch.object(service, "_get_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_get.return_value = mock_client

            issue = await service.get_issue("owner/repo", 42)

        assert issue.number == 42
        assert issue.title == "Feature request"
        assert issue.labels == ["enhancement", "priority:high"]


class TestRateLimitHandling:
    """Tests for rate limit handling."""

    async def test_server_error_retries(self) -> None:
        """_request should retry on 500 errors."""
        error_response = httpx.Response(
            500,
            json={"message": "Internal Server Error"},
            headers={"X-RateLimit-Remaining": "4999"},
        )
        success_response = httpx.Response(
            200,
            json={"status": "ok"},
            headers={"X-RateLimit-Remaining": "4999"},
        )

        service = GitHubService()
        with patch.object(service, "_get_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(
                side_effect=[error_response, success_response]
            )
            mock_get.return_value = mock_client

            result = await service._request("GET", "/test")

        assert result == {"status": "ok"}
        assert mock_client.request.call_count == 2

    async def test_client_error_no_retry(self) -> None:
        """_request should not retry on 4xx client errors."""
        error_response = httpx.Response(
            404,
            text="Not Found",
            headers={"X-RateLimit-Remaining": "4999"},
        )

        service = GitHubService()
        with patch.object(service, "_get_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=error_response)
            mock_get.return_value = mock_client

            with pytest.raises(GitHubServiceError) as exc_info:
                await service._request("GET", "/test")

        assert exc_info.value.status_code == 404
        assert mock_client.request.call_count == 1


class TestListPRs:
    """Tests for GitHubService.list_prs."""

    async def test_list_prs_parses_response(self) -> None:
        """list_prs should parse PR list response."""
        mock_response = httpx.Response(
            200,
            json=[
                {
                    "number": 10,
                    "title": "Fix bug",
                    "state": "open",
                    "body": "Fixes issue",
                    "head": {"ref": "fix/bug"},
                    "base": {"ref": "main"},
                    "html_url": "https://github.com/owner/repo/pull/10",
                    "created_at": "2026-03-01T00:00:00Z",
                    "updated_at": "2026-03-01T12:00:00Z",
                }
            ],
            headers={"X-RateLimit-Remaining": "4999"},
        )

        service = GitHubService()
        with patch.object(service, "_get_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get.return_value = mock_client

            prs = await service.list_prs("owner/repo")

        assert len(prs) == 1
        assert prs[0].number == 10
        assert prs[0].head_branch == "fix/bug"
        assert prs[0].base_branch == "main"


class TestListCommits:
    """Tests for GitHubService.list_commits."""

    async def test_list_commits_parses_response(self) -> None:
        """list_commits should parse commit list response."""
        mock_response = httpx.Response(
            200,
            json=[
                {
                    "sha": "abc123",
                    "commit": {
                        "message": "Fix login",
                        "author": {"name": "Dev", "date": "2026-03-01T10:00:00Z"},
                    },
                    "author": {"login": "developer"},
                }
            ],
            headers={"X-RateLimit-Remaining": "4999"},
        )

        service = GitHubService()
        with patch.object(service, "_get_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get.return_value = mock_client

            commits = await service.list_commits("owner/repo")

        assert len(commits) == 1
        assert commits[0].sha == "abc123"
        assert commits[0].message == "Fix login"
        assert commits[0].author == "developer"


class TestGetRepoInfo:
    """Tests for GitHubService.get_repo_info."""

    async def test_get_repo_info_parses_response(self) -> None:
        """get_repo_info should parse repo info response."""
        mock_response = httpx.Response(
            200,
            json={
                "full_name": "owner/repo",
                "description": "A test repo",
                "default_branch": "main",
                "open_issues_count": 5,
                "forks_count": 2,
                "stargazers_count": 10,
                "language": "Python",
                "html_url": "https://github.com/owner/repo",
            },
            headers={"X-RateLimit-Remaining": "4999"},
        )

        service = GitHubService()
        with patch.object(service, "_get_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_get.return_value = mock_client

            info = await service.get_repo_info("owner/repo")

        assert info.full_name == "owner/repo"
        assert info.open_issues_count == 5
        assert info.language == "Python"
