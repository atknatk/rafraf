"""GitHub API service - async HTTP client for GitHub REST API v3."""

import asyncio
import json
from datetime import UTC, datetime

import httpx
import structlog

from app.core.config import get_settings
from app.schemas.github import (
    GitHubBranch,
    GitHubCommit,
    GitHubIssue,
    GitHubPullRequest,
    GitHubRepoInfo,
)


def _to_int(value: object, default: int = 0) -> int:
    """Safely convert an object to int.

    Args:
        value: Value to convert.
        default: Default if conversion fails.

    Returns:
        Integer value.
    """
    if isinstance(value, int):
        return value
    if isinstance(value, (str, float)):
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    return default


def _to_str(value: object, default: str = "") -> str:
    """Safely convert an object to str.

    Args:
        value: Value to convert.
        default: Default if value is None.

    Returns:
        String value.
    """
    if value is None:
        return default
    return str(value)


logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# GitHub API base URL
_GITHUB_API_URL = "https://api.github.com"

# Rate limit safety margin - start backoff when this many requests remain
_RATE_LIMIT_THRESHOLD = 100

# Backoff seconds when rate limited
_RATE_LIMIT_BACKOFF: list[float] = [1.0, 2.0, 4.0, 8.0]

# Maximum retries for transient errors
_MAX_RETRIES = 3


class GitHubServiceError(Exception):
    """Raised when GitHub API call fails."""

    def __init__(self, message: str, status_code: int = 0) -> None:
        self.status_code = status_code
        super().__init__(message)


class GitHubRateLimitError(GitHubServiceError):
    """Raised when GitHub API rate limit is exceeded."""

    def __init__(self, reset_at: datetime) -> None:
        self.reset_at = reset_at
        super().__init__(
            f"GitHub API rate limit exceeded. Resets at {reset_at.isoformat()}",
            status_code=403,
        )


class GitHubService:
    """Async GitHub API client using httpx.

    Handles authentication, rate limiting, and retries for GitHub REST API v3.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._token = settings.github_token
        self._client: httpx.AsyncClient | None = None
        if not self._token:
            logger.warning("github_token_empty", hint="GITHUB_TOKEN env var bos, GitHub API calismaycak")

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the httpx async client.

        Returns:
            Configured httpx.AsyncClient instance.

        Raises:
            GitHubServiceError: If GitHub token is not configured.
        """
        if not self._token:
            raise GitHubServiceError(
                "GITHUB_TOKEN yapilandirilmamis. .env dosyasini kontrol edin.",
                status_code=500,
            )
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=_GITHUB_API_URL,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {self._token}",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
        json_body: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """Make an authenticated GitHub API request with retry and rate limit handling.

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE).
            path: API path (e.g., /repos/owner/repo/issues).
            params: Query parameters.
            json_body: JSON request body.

        Returns:
            Parsed JSON response.

        Raises:
            GitHubServiceError: On API errors.
            GitHubRateLimitError: When rate limited.
        """
        client = await self._get_client()
        last_error: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            try:
                response = await client.request(
                    method,
                    path,
                    params=params,
                    json=json_body,
                )

                # Check rate limit headers
                remaining = response.headers.get("X-RateLimit-Remaining")
                if remaining is not None and int(remaining) < _RATE_LIMIT_THRESHOLD:
                    await logger.awarning(
                        "github_rate_limit_low",
                        remaining=remaining,
                        path=path,
                    )

                # Handle rate limit exceeded
                if response.status_code == 403:
                    reset_ts = response.headers.get("X-RateLimit-Reset")
                    if reset_ts is not None:
                        reset_at = datetime.fromtimestamp(int(reset_ts), tz=UTC)
                        wait_seconds = max((reset_at - datetime.now(tz=UTC)).total_seconds(), 1.0)
                        if wait_seconds <= 60:
                            await logger.awarning(
                                "github_rate_limit_waiting",
                                wait_seconds=wait_seconds,
                                attempt=attempt + 1,
                            )
                            await asyncio.sleep(wait_seconds)
                            continue
                        raise GitHubRateLimitError(reset_at)
                    raise GitHubServiceError(
                        f"GitHub API forbidden: {response.text}",
                        status_code=403,
                    )

                # Handle server errors with retry
                if response.status_code >= 500:
                    backoff = _RATE_LIMIT_BACKOFF[min(attempt, len(_RATE_LIMIT_BACKOFF) - 1)]
                    await logger.awarning(
                        "github_api_server_error",
                        status_code=response.status_code,
                        attempt=attempt + 1,
                        backoff=backoff,
                    )
                    last_error = GitHubServiceError(
                        f"GitHub API server error: {response.status_code}",
                        status_code=response.status_code,
                    )
                    await asyncio.sleep(backoff)
                    continue

                # Handle client errors (non-retryable)
                if response.status_code >= 400:
                    error_body = response.text
                    raise GitHubServiceError(
                        f"GitHub API error {response.status_code}: {error_body}",
                        status_code=response.status_code,
                    )

                # Handle 204 No Content
                if response.status_code == 204:
                    return {"status": "success"}

                result: dict[str, object] = response.json()
                return result

            except httpx.TimeoutException as exc:
                last_error = exc
                backoff = _RATE_LIMIT_BACKOFF[min(attempt, len(_RATE_LIMIT_BACKOFF) - 1)]
                await logger.awarning(
                    "github_api_timeout",
                    attempt=attempt + 1,
                    backoff=backoff,
                    path=path,
                )
                await asyncio.sleep(backoff)

        error_msg = f"GitHub API failed after {_MAX_RETRIES} retries for {method} {path}"
        if last_error is not None:
            error_msg += f": {last_error}"
        raise GitHubServiceError(error_msg)

    async def _request_list(
        self,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
    ) -> list[dict[str, object]]:
        """Make a GET request that returns a list response.

        Args:
            path: API path.
            params: Query parameters.

        Returns:
            List of parsed JSON objects.
        """
        client = await self._get_client()
        last_error: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            try:
                response = await client.get(path, params=params)

                remaining = response.headers.get("X-RateLimit-Remaining")
                if remaining is not None and int(remaining) < _RATE_LIMIT_THRESHOLD:
                    await logger.awarning(
                        "github_rate_limit_low",
                        remaining=remaining,
                        path=path,
                    )

                if response.status_code == 403:
                    reset_ts = response.headers.get("X-RateLimit-Reset")
                    if reset_ts is not None:
                        reset_at = datetime.fromtimestamp(int(reset_ts), tz=UTC)
                        wait_seconds = max((reset_at - datetime.now(tz=UTC)).total_seconds(), 1.0)
                        if wait_seconds <= 60:
                            await asyncio.sleep(wait_seconds)
                            continue
                        raise GitHubRateLimitError(reset_at)
                    raise GitHubServiceError(
                        f"GitHub API forbidden: {response.text}",
                        status_code=403,
                    )

                if response.status_code >= 500:
                    backoff = _RATE_LIMIT_BACKOFF[min(attempt, len(_RATE_LIMIT_BACKOFF) - 1)]
                    last_error = GitHubServiceError(
                        f"GitHub API server error: {response.status_code}",
                        status_code=response.status_code,
                    )
                    await asyncio.sleep(backoff)
                    continue

                if response.status_code >= 400:
                    raise GitHubServiceError(
                        f"GitHub API error {response.status_code}: {response.text}",
                        status_code=response.status_code,
                    )

                result: list[dict[str, object]] = response.json()
                return result

            except httpx.TimeoutException as exc:
                last_error = exc
                backoff = _RATE_LIMIT_BACKOFF[min(attempt, len(_RATE_LIMIT_BACKOFF) - 1)]
                await asyncio.sleep(backoff)

        error_msg = f"GitHub API list failed after {_MAX_RETRIES} retries for {path}"
        if last_error is not None:
            error_msg += f": {last_error}"
        raise GitHubServiceError(error_msg)

    # ── Issue operations ──

    async def list_issues(
        self,
        repo: str,
        *,
        state: str = "open",
        labels: list[str] | None = None,
        page: int = 1,
        per_page: int = 30,
    ) -> list[GitHubIssue]:
        """List issues for a repository.

        Args:
            repo: Repository in owner/repo format.
            state: Issue state filter (open, closed, all).
            labels: Filter by labels.
            page: Page number.
            per_page: Items per page.

        Returns:
            List of GitHubIssue objects.
        """
        params: dict[str, str | int] = {
            "state": state,
            "page": page,
            "per_page": per_page,
        }
        if labels:
            params["labels"] = ",".join(labels)

        data = await self._request_list(f"/repos/{repo}/issues", params=params)

        issues: list[GitHubIssue] = []
        for item in data:
            # Skip pull requests (GitHub API returns PRs in issues endpoint)
            if "pull_request" in item:
                continue
            issue_labels_raw = item.get("labels", [])
            issue_labels: list[str] = []
            if isinstance(issue_labels_raw, list):
                for lbl in issue_labels_raw:
                    if isinstance(lbl, dict):
                        name = lbl.get("name", "")
                        if isinstance(name, str):
                            issue_labels.append(name)

            assignees_raw = item.get("assignees", [])
            assignee_names: list[str] = []
            if isinstance(assignees_raw, list):
                for assignee in assignees_raw:
                    if isinstance(assignee, dict):
                        login = assignee.get("login", "")
                        if isinstance(login, str):
                            assignee_names.append(login)

            issues.append(
                GitHubIssue(
                    number=_to_int(item.get("number", 0)),
                    title=_to_str(item.get("title", "")),
                    state=_to_str(item.get("state", "")),
                    body=_to_str(item.get("body", "")) if item.get("body") else None,
                    labels=issue_labels,
                    assignees=assignee_names,
                    created_at=_to_str(item.get("created_at", "")),
                    updated_at=_to_str(item.get("updated_at", "")),
                    html_url=_to_str(item.get("html_url", "")),
                )
            )
        return issues

    async def get_issue(self, repo: str, issue_number: int) -> GitHubIssue:
        """Get a single issue by number.

        Args:
            repo: Repository in owner/repo format.
            issue_number: Issue number.

        Returns:
            GitHubIssue object.
        """
        data = await self._request("GET", f"/repos/{repo}/issues/{issue_number}")

        issue_labels_raw = data.get("labels", [])
        issue_labels: list[str] = []
        if isinstance(issue_labels_raw, list):
            for lbl in issue_labels_raw:
                if isinstance(lbl, dict):
                    name = lbl.get("name", "")
                    if isinstance(name, str):
                        issue_labels.append(name)

        assignees_raw = data.get("assignees", [])
        assignee_names: list[str] = []
        if isinstance(assignees_raw, list):
            for assignee in assignees_raw:
                if isinstance(assignee, dict):
                    login = assignee.get("login", "")
                    if isinstance(login, str):
                        assignee_names.append(login)

        return GitHubIssue(
            number=_to_int(data.get("number", 0)),
            title=_to_str(data.get("title", "")),
            state=_to_str(data.get("state", "")),
            body=_to_str(data.get("body", "")) if data.get("body") else None,
            labels=issue_labels,
            assignees=assignee_names,
            created_at=_to_str(data.get("created_at", "")),
            updated_at=_to_str(data.get("updated_at", "")),
            html_url=_to_str(data.get("html_url", "")),
        )

    async def create_issue(
        self,
        repo: str,
        title: str,
        *,
        body: str | None = None,
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
    ) -> GitHubIssue:
        """Create a new issue.

        Args:
            repo: Repository in owner/repo format.
            title: Issue title.
            body: Issue body (markdown).
            labels: Labels to add.
            assignees: Users to assign.

        Returns:
            Created GitHubIssue.
        """
        json_body: dict[str, object] = {"title": title}
        if body is not None:
            json_body["body"] = body
        if labels is not None:
            json_body["labels"] = labels
        if assignees is not None:
            json_body["assignees"] = assignees

        data = await self._request("POST", f"/repos/{repo}/issues", json_body=json_body)

        issue_labels_raw = data.get("labels", [])
        issue_labels: list[str] = []
        if isinstance(issue_labels_raw, list):
            for lbl in issue_labels_raw:
                if isinstance(lbl, dict):
                    name = lbl.get("name", "")
                    if isinstance(name, str):
                        issue_labels.append(name)

        assignees_raw = data.get("assignees", [])
        assignee_names: list[str] = []
        if isinstance(assignees_raw, list):
            for a in assignees_raw:
                if isinstance(a, dict):
                    login = a.get("login", "")
                    if isinstance(login, str):
                        assignee_names.append(login)

        return GitHubIssue(
            number=_to_int(data.get("number", 0)),
            title=_to_str(data.get("title", "")),
            state=_to_str(data.get("state", "")),
            body=_to_str(data.get("body", "")) if data.get("body") else None,
            labels=issue_labels,
            assignees=assignee_names,
            created_at=_to_str(data.get("created_at", "")),
            updated_at=_to_str(data.get("updated_at", "")),
            html_url=_to_str(data.get("html_url", "")),
        )

    async def update_issue(
        self,
        repo: str,
        issue_number: int,
        *,
        title: str | None = None,
        body: str | None = None,
        state: str | None = None,
        labels: list[str] | None = None,
    ) -> GitHubIssue:
        """Update an existing issue.

        Args:
            repo: Repository in owner/repo format.
            issue_number: Issue number.
            title: New title (optional).
            body: New body (optional).
            state: New state (open/closed) (optional).
            labels: Replace labels (optional).

        Returns:
            Updated GitHubIssue.
        """
        json_body: dict[str, object] = {}
        if title is not None:
            json_body["title"] = title
        if body is not None:
            json_body["body"] = body
        if state is not None:
            json_body["state"] = state
        if labels is not None:
            json_body["labels"] = labels

        data = await self._request(
            "PATCH",
            f"/repos/{repo}/issues/{issue_number}",
            json_body=json_body,
        )

        issue_labels_raw = data.get("labels", [])
        issue_labels: list[str] = []
        if isinstance(issue_labels_raw, list):
            for lbl in issue_labels_raw:
                if isinstance(lbl, dict):
                    name = lbl.get("name", "")
                    if isinstance(name, str):
                        issue_labels.append(name)

        assignees_raw = data.get("assignees", [])
        assignee_names: list[str] = []
        if isinstance(assignees_raw, list):
            for a in assignees_raw:
                if isinstance(a, dict):
                    login = a.get("login", "")
                    if isinstance(login, str):
                        assignee_names.append(login)

        return GitHubIssue(
            number=_to_int(data.get("number", 0)),
            title=_to_str(data.get("title", "")),
            state=_to_str(data.get("state", "")),
            body=_to_str(data.get("body", "")) if data.get("body") else None,
            labels=issue_labels,
            assignees=assignee_names,
            created_at=_to_str(data.get("created_at", "")),
            updated_at=_to_str(data.get("updated_at", "")),
            html_url=_to_str(data.get("html_url", "")),
        )

    async def close_issue(
        self,
        repo: str,
        issue_number: int,
        *,
        comment: str | None = None,
    ) -> GitHubIssue:
        """Close an issue, optionally adding a comment.

        Args:
            repo: Repository in owner/repo format.
            issue_number: Issue number.
            comment: Optional closing comment.

        Returns:
            Closed GitHubIssue.
        """
        if comment:
            await self._request(
                "POST",
                f"/repos/{repo}/issues/{issue_number}/comments",
                json_body={"body": comment},
            )

        return await self.update_issue(repo, issue_number, state="closed")

    # ── Label operations ──

    async def add_labels(self, repo: str, issue_number: int, labels: list[str]) -> list[str]:
        """Add labels to an issue.

        Args:
            repo: Repository in owner/repo format.
            issue_number: Issue number.
            labels: Labels to add.

        Returns:
            Updated list of label names.
        """
        # POST method for adding labels returns updated labels
        client = await self._get_client()
        response = await client.post(
            f"/repos/{repo}/issues/{issue_number}/labels",
            json={"labels": labels},
        )
        if response.status_code >= 400:
            raise GitHubServiceError(
                f"Failed to add labels: {response.text}",
                status_code=response.status_code,
            )
        result: list[dict[str, object]] = response.json()
        return [_to_str(lbl.get("name", "")) for lbl in result if isinstance(lbl, dict)]

    async def remove_label(self, repo: str, issue_number: int, label: str) -> None:
        """Remove a label from an issue.

        Args:
            repo: Repository in owner/repo format.
            issue_number: Issue number.
            label: Label name to remove.
        """
        await self._request(
            "DELETE",
            f"/repos/{repo}/issues/{issue_number}/labels/{label}",
        )

    # ── PR operations ──

    async def list_prs(
        self,
        repo: str,
        *,
        state: str = "open",
        page: int = 1,
        per_page: int = 30,
    ) -> list[GitHubPullRequest]:
        """List pull requests.

        Args:
            repo: Repository in owner/repo format.
            state: PR state filter (open, closed, all).
            page: Page number.
            per_page: Items per page.

        Returns:
            List of GitHubPullRequest objects.
        """
        params: dict[str, str | int] = {
            "state": state,
            "page": page,
            "per_page": per_page,
        }
        data = await self._request_list(f"/repos/{repo}/pulls", params=params)

        prs: list[GitHubPullRequest] = []
        for item in data:
            head = item.get("head", {})
            base = item.get("base", {})
            head_ref = ""
            base_ref = ""
            if isinstance(head, dict):
                head_ref = _to_str(head.get("ref", ""))
            if isinstance(base, dict):
                base_ref = _to_str(base.get("ref", ""))

            prs.append(
                GitHubPullRequest(
                    number=_to_int(item.get("number", 0)),
                    title=_to_str(item.get("title", "")),
                    state=_to_str(item.get("state", "")),
                    body=_to_str(item.get("body", "")) if item.get("body") else None,
                    head_branch=head_ref,
                    base_branch=base_ref,
                    mergeable=None,
                    additions=0,
                    deletions=0,
                    changed_files=0,
                    html_url=_to_str(item.get("html_url", "")),
                    created_at=_to_str(item.get("created_at", "")),
                    updated_at=_to_str(item.get("updated_at", "")),
                )
            )
        return prs

    async def get_pr(self, repo: str, pr_number: int) -> GitHubPullRequest:
        """Get a single pull request with details.

        Args:
            repo: Repository in owner/repo format.
            pr_number: Pull request number.

        Returns:
            GitHubPullRequest with full details.
        """
        data = await self._request("GET", f"/repos/{repo}/pulls/{pr_number}")

        head = data.get("head", {})
        base = data.get("base", {})
        head_ref = ""
        base_ref = ""
        if isinstance(head, dict):
            head_ref = _to_str(head.get("ref", ""))
        if isinstance(base, dict):
            base_ref = _to_str(base.get("ref", ""))

        mergeable_raw = data.get("mergeable")
        mergeable: bool | None = None
        if isinstance(mergeable_raw, bool):
            mergeable = mergeable_raw

        return GitHubPullRequest(
            number=_to_int(data.get("number", 0)),
            title=_to_str(data.get("title", "")),
            state=_to_str(data.get("state", "")),
            body=_to_str(data.get("body", "")) if data.get("body") else None,
            head_branch=head_ref,
            base_branch=base_ref,
            mergeable=mergeable,
            additions=_to_int(data.get("additions", 0)),
            deletions=_to_int(data.get("deletions", 0)),
            changed_files=_to_int(data.get("changed_files", 0)),
            html_url=_to_str(data.get("html_url", "")),
            created_at=_to_str(data.get("created_at", "")),
            updated_at=_to_str(data.get("updated_at", "")),
        )

    # ── Commit/Branch operations ──

    async def list_commits(
        self,
        repo: str,
        *,
        branch: str | None = None,
        limit: int = 10,
    ) -> list[GitHubCommit]:
        """List recent commits.

        Args:
            repo: Repository in owner/repo format.
            branch: Branch name (optional, defaults to default branch).
            limit: Maximum number of commits.

        Returns:
            List of GitHubCommit objects.
        """
        params: dict[str, str | int] = {"per_page": limit}
        if branch is not None:
            params["sha"] = branch

        data = await self._request_list(f"/repos/{repo}/commits", params=params)

        commits: list[GitHubCommit] = []
        for item in data:
            commit_data = item.get("commit", {})
            author_data: dict[str, object] = {}
            message = ""
            date = ""
            if isinstance(commit_data, dict):
                message = _to_str(commit_data.get("message", ""))
                raw_author = commit_data.get("author", {})
                if isinstance(raw_author, dict):
                    author_data = raw_author
                    date = _to_str(author_data.get("date", ""))

            # Use commit author login or fallback to commit data name
            top_author = item.get("author", {})
            author_login = ""
            if isinstance(top_author, dict):
                author_login = _to_str(top_author.get("login", ""))
            if not author_login:
                author_login = _to_str(author_data.get("name", "unknown"))

            commits.append(
                GitHubCommit(
                    sha=_to_str(item.get("sha", "")),
                    message=message,
                    author=author_login,
                    date=date,
                )
            )
        return commits

    async def list_branches(self, repo: str) -> list[GitHubBranch]:
        """List repository branches.

        Args:
            repo: Repository in owner/repo format.

        Returns:
            List of GitHubBranch objects.
        """
        data = await self._request_list(f"/repos/{repo}/branches", params={"per_page": 100})

        branches: list[GitHubBranch] = []
        for item in data:
            commit_obj = item.get("commit", {})
            sha = ""
            if isinstance(commit_obj, dict):
                sha = _to_str(commit_obj.get("sha", ""))

            protected_raw = item.get("protected", False)
            protected = bool(protected_raw) if isinstance(protected_raw, bool) else False

            branches.append(
                GitHubBranch(
                    name=_to_str(item.get("name", "")),
                    sha=sha,
                    protected=protected,
                )
            )
        return branches

    # ── Repository info ──

    async def get_repo_info(self, repo: str) -> GitHubRepoInfo:
        """Get repository information and statistics.

        Args:
            repo: Repository in owner/repo format.

        Returns:
            GitHubRepoInfo object.
        """
        data = await self._request("GET", f"/repos/{repo}")

        return GitHubRepoInfo(
            full_name=_to_str(data.get("full_name", "")),
            description=_to_str(data.get("description", "")) if data.get("description") else None,
            default_branch=_to_str(data.get("default_branch", "main")),
            open_issues_count=_to_int(data.get("open_issues_count", 0)),
            forks_count=_to_int(data.get("forks_count", 0)),
            stargazers_count=_to_int(data.get("stargazers_count", 0)),
            language=_to_str(data.get("language", "")) if data.get("language") else None,
            html_url=_to_str(data.get("html_url", "")),
        )

    # ── Webhook signature verification ──

    @staticmethod
    def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
        """Verify GitHub webhook HMAC-SHA256 signature.

        Args:
            payload: Raw request body bytes.
            signature: X-Hub-Signature-256 header value.
            secret: Webhook secret.

        Returns:
            True if signature is valid.
        """
        import hashlib
        import hmac

        if not signature.startswith("sha256="):
            return False

        expected = hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(f"sha256={expected}", signature)

    # ── JSON serialization helper ──

    @staticmethod
    def format_result(data: object) -> str:
        """Format result data as JSON string for Claude.

        Args:
            data: Data to serialize (Pydantic model or dict/list).

        Returns:
            JSON string.
        """
        if isinstance(data, list):
            items = [item.model_dump() if hasattr(item, "model_dump") else item for item in data]
            return json.dumps(items, ensure_ascii=False, indent=2)
        if hasattr(data, "model_dump"):
            return json.dumps(
                data.model_dump(),
                ensure_ascii=False,
                indent=2,
            )
        return json.dumps(data, ensure_ascii=False, indent=2)
