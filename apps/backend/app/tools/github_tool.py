"""GitHub Manager Tool - Claude AI tool for GitHub operations.

Cloud tool that runs on EKS (no host agent required).
Provides issue CRUD, PR management, commit/branch listing, and label management.
"""

import structlog

from app.orchestrator.tool_registry import ToolDefinition
from app.services.github_service import GitHubService, GitHubServiceError, _to_int
from app.tools.base import BaseTool

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# Tool schema for Claude API
_GITHUB_TOOL_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": [
                "list_issues",
                "get_issue",
                "create_issue",
                "update_issue",
                "close_issue",
                "list_prs",
                "get_pr",
                "list_commits",
                "list_branches",
                "get_repo_info",
                "add_labels",
                "remove_labels",
            ],
            "description": "Yapilacak GitHub islemi",
        },
        "repo": {
            "type": "string",
            "description": "Repository (owner/repo formatinda, ornek: atknatk/rafraf)",
        },
        "issue_number": {
            "type": "integer",
            "description": (
                "Issue numarasi (get_issue, update_issue, "
                "close_issue, add_labels, remove_labels icin)"
            ),
        },
        "pr_number": {
            "type": "integer",
            "description": "Pull request numarasi (get_pr icin)",
        },
        "title": {
            "type": "string",
            "description": "Issue basligi (create_issue, update_issue icin)",
        },
        "body": {
            "type": "string",
            "description": "Issue icerigi (create_issue, update_issue icin)",
        },
        "comment": {
            "type": "string",
            "description": "Kapatma yorumu (close_issue icin)",
        },
        "state": {
            "type": "string",
            "enum": ["open", "closed", "all"],
            "description": "Durum filtresi (list_issues, list_prs, update_issue icin)",
        },
        "labels": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Label listesi (list_issues filtre, create_issue, "
                "update_issue, add_labels, remove_labels icin)"
            ),
        },
        "assignees": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Atanacak kullanicilar (create_issue icin)",
        },
        "branch": {
            "type": "string",
            "description": "Branch adi (list_commits icin)",
        },
        "limit": {
            "type": "integer",
            "description": "Sonuc limiti (list_commits icin, varsayilan: 10)",
            "default": 10,
        },
        "page": {
            "type": "integer",
            "description": "Sayfa numarasi (list_issues, list_prs icin, varsayilan: 1)",
            "default": 1,
        },
        "per_page": {
            "type": "integer",
            "description": "Sayfa basi sonuc (list_issues, list_prs icin, varsayilan: 30)",
            "default": 30,
        },
    },
    "required": ["action", "repo"],
}

# Actions that require user approval
_APPROVAL_ACTIONS = frozenset({"create_issue", "update_issue", "close_issue"})


class GitHubTool(BaseTool):
    """GitHub Manager tool for Claude AI.

    Provides GitHub API operations as a Claude tool. Registered with the
    tool registry and called by the AI orchestrator during tool-calling loops.
    """

    def __init__(self) -> None:
        self._service = GitHubService()

    def get_definition(self) -> ToolDefinition:
        """Return the tool definition for Claude API.

        Returns:
            ToolDefinition with github_manager schema.
        """
        return ToolDefinition(
            name="github_manager",
            description=(
                "GitHub islemlerini yonetir. Issue olusturma/okuma/guncelleme/kapatma, "
                "PR listeleme/detay, commit/branch listeleme, label yonetimi. "
                "Issue olusturma/guncelleme/kapatma onay gerektirir."
            ),
            input_schema=_GITHUB_TOOL_SCHEMA,
            requires_approval=False,  # Per-action approval checked in execute
            approval_category="write_remote",
        )

    async def execute(self, params: dict[str, object]) -> str:
        """Execute a GitHub action.

        Args:
            params: Tool input parameters from Claude.

        Returns:
            JSON string result.
        """
        action = str(params.get("action", ""))
        repo = str(params.get("repo", ""))

        if not action or not repo:
            return '{"error": "action ve repo parametreleri zorunludur"}'

        await logger.ainfo(
            "github_tool_execute",
            action=action,
            repo=repo,
        )

        try:
            return await self._dispatch(action, repo, params)
        except GitHubServiceError as exc:
            await logger.aexception(
                "github_tool_error",
                action=action,
                repo=repo,
            )
            return f'{{"error": "GitHub API hatasi: {exc}"}}'
        except Exception as exc:
            await logger.aexception(
                "github_tool_unexpected_error",
                action=action,
                repo=repo,
            )
            return f'{{"error": "Beklenmeyen hata: {exc}"}}'

    async def _dispatch(self, action: str, repo: str, params: dict[str, object]) -> str:
        """Dispatch to the appropriate action handler.

        Args:
            action: Action name.
            repo: Repository.
            params: Full params dict.

        Returns:
            JSON string result.
        """
        if action == "list_issues":
            return await self._list_issues(repo, params)
        if action == "get_issue":
            return await self._get_issue(repo, params)
        if action == "create_issue":
            return await self._create_issue(repo, params)
        if action == "update_issue":
            return await self._update_issue(repo, params)
        if action == "close_issue":
            return await self._close_issue(repo, params)
        if action == "list_prs":
            return await self._list_prs(repo, params)
        if action == "get_pr":
            return await self._get_pr(repo, params)
        if action == "list_commits":
            return await self._list_commits(repo, params)
        if action == "list_branches":
            return await self._list_branches(repo)
        if action == "get_repo_info":
            return await self._get_repo_info(repo)
        if action == "add_labels":
            return await self._add_labels(repo, params)
        if action == "remove_labels":
            return await self._remove_labels(repo, params)
        return f'{{"error": "Bilinmeyen action: {action}"}}'

    def requires_action_approval(self, action: str) -> bool:
        """Check if a specific action requires approval.

        Args:
            action: Action name.

        Returns:
            True if approval is required.
        """
        return action in _APPROVAL_ACTIONS

    async def _list_issues(self, repo: str, params: dict[str, object]) -> str:
        state = str(params.get("state", "open"))
        labels_raw = params.get("labels")
        labels: list[str] | None = None
        if isinstance(labels_raw, list):
            labels = [str(lbl) for lbl in labels_raw]
        page = _to_int(params.get("page", 1))
        per_page = _to_int(params.get("per_page", 30))

        issues = await self._service.list_issues(
            repo, state=state, labels=labels, page=page, per_page=per_page
        )
        return GitHubService.format_result(issues)

    async def _get_issue(self, repo: str, params: dict[str, object]) -> str:
        issue_number = _to_int(params.get("issue_number", 0))
        if not issue_number:
            return '{"error": "issue_number parametresi zorunludur"}'
        issue = await self._service.get_issue(repo, issue_number)
        return GitHubService.format_result(issue)

    async def _create_issue(self, repo: str, params: dict[str, object]) -> str:
        title = str(params.get("title", ""))
        if not title:
            return '{"error": "title parametresi zorunludur"}'
        body = str(params.get("body", "")) if params.get("body") else None
        labels_raw = params.get("labels")
        labels: list[str] | None = None
        if isinstance(labels_raw, list):
            labels = [str(lbl) for lbl in labels_raw]
        assignees_raw = params.get("assignees")
        assignees: list[str] | None = None
        if isinstance(assignees_raw, list):
            assignees = [str(a) for a in assignees_raw]

        issue = await self._service.create_issue(
            repo, title, body=body, labels=labels, assignees=assignees
        )
        return GitHubService.format_result(issue)

    async def _update_issue(self, repo: str, params: dict[str, object]) -> str:
        issue_number = _to_int(params.get("issue_number", 0))
        if not issue_number:
            return '{"error": "issue_number parametresi zorunludur"}'
        title = str(params.get("title", "")) if params.get("title") else None
        body = str(params.get("body", "")) if params.get("body") else None
        state = str(params.get("state", "")) if params.get("state") else None
        labels_raw = params.get("labels")
        labels: list[str] | None = None
        if isinstance(labels_raw, list):
            labels = [str(lbl) for lbl in labels_raw]

        issue = await self._service.update_issue(
            repo, issue_number, title=title, body=body, state=state, labels=labels
        )
        return GitHubService.format_result(issue)

    async def _close_issue(self, repo: str, params: dict[str, object]) -> str:
        issue_number = _to_int(params.get("issue_number", 0))
        if not issue_number:
            return '{"error": "issue_number parametresi zorunludur"}'
        comment = str(params.get("comment", "")) if params.get("comment") else None

        issue = await self._service.close_issue(repo, issue_number, comment=comment)
        return GitHubService.format_result(issue)

    async def _list_prs(self, repo: str, params: dict[str, object]) -> str:
        state = str(params.get("state", "open"))
        page = _to_int(params.get("page", 1))
        per_page = _to_int(params.get("per_page", 30))

        prs = await self._service.list_prs(repo, state=state, page=page, per_page=per_page)
        return GitHubService.format_result(prs)

    async def _get_pr(self, repo: str, params: dict[str, object]) -> str:
        pr_number = _to_int(params.get("pr_number", 0))
        if not pr_number:
            return '{"error": "pr_number parametresi zorunludur"}'
        pr = await self._service.get_pr(repo, pr_number)
        return GitHubService.format_result(pr)

    async def _list_commits(self, repo: str, params: dict[str, object]) -> str:
        branch = str(params.get("branch", "")) if params.get("branch") else None
        limit = _to_int(params.get("limit", 10))

        commits = await self._service.list_commits(repo, branch=branch, limit=limit)
        return GitHubService.format_result(commits)

    async def _list_branches(self, repo: str) -> str:
        branches = await self._service.list_branches(repo)
        return GitHubService.format_result(branches)

    async def _get_repo_info(self, repo: str) -> str:
        info = await self._service.get_repo_info(repo)
        return GitHubService.format_result(info)

    async def _add_labels(self, repo: str, params: dict[str, object]) -> str:
        issue_number = _to_int(params.get("issue_number", 0))
        if not issue_number:
            return '{"error": "issue_number parametresi zorunludur"}'
        labels_raw = params.get("labels")
        if not isinstance(labels_raw, list) or not labels_raw:
            return '{"error": "labels parametresi zorunludur (bos olmayan liste)"}'
        labels = [str(lbl) for lbl in labels_raw]

        result = await self._service.add_labels(repo, issue_number, labels)
        return GitHubService.format_result(result)

    async def _remove_labels(self, repo: str, params: dict[str, object]) -> str:
        issue_number = _to_int(params.get("issue_number", 0))
        if not issue_number:
            return '{"error": "issue_number parametresi zorunludur"}'
        labels_raw = params.get("labels")
        if not isinstance(labels_raw, list) or not labels_raw:
            return '{"error": "labels parametresi zorunludur (bos olmayan liste)"}'

        for label in labels_raw:
            await self._service.remove_label(repo, issue_number, str(label))
        return '{"status": "success", "message": "Label\'lar kaldirildi"}'
