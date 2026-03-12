"""GitHub webhook receiver endpoint."""

from collections import deque
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Header, Request, Response
from pydantic import BaseModel
from starlette import status

from app.api.routes.websocket import manager as ios_manager
from app.core.config import get_settings
from app.schemas.github import WebhookResponse
from app.services.github_service import GitHubService
from app.services.proactive_notification_service import ProactiveNotificationService

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])

# In-memory ring buffer of recent GitHub events (max 100)
_recent_events: deque[dict[str, object]] = deque(maxlen=100)


class GitHubEventSummary(BaseModel):
    """Summary of a recent GitHub webhook event."""

    event: str
    action: str
    repo: str
    summary: dict[str, object]
    received_at: str


class GitHubEventsResponse(BaseModel):
    """Response for recent GitHub events."""

    events: list[GitHubEventSummary]
    total: int


@router.post(
    "/github",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="GitHub webhook event alici",
)
async def github_webhook(
    request: Request,
    response: Response,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
) -> WebhookResponse:
    """Receive and process GitHub webhook events.

    Validates HMAC-SHA256 signature and processes supported event types
    (pull_request, issues, push).

    Args:
        request: FastAPI request object.
        response: FastAPI response object.
        x_hub_signature_256: GitHub webhook signature header.
        x_github_event: GitHub event type header.

    Returns:
        WebhookResponse with processing status.
    """
    settings = get_settings()

    # Read raw body for signature verification
    body = await request.body()

    # Verify webhook signature if secret is configured
    if settings.github_webhook_secret:
        if not x_hub_signature_256:
            await logger.awarning("webhook_missing_signature")
            response.status_code = status.HTTP_401_UNAUTHORIZED
            return WebhookResponse(
                status="error",
                message="Missing X-Hub-Signature-256 header",
            )

        if not GitHubService.verify_webhook_signature(
            body, x_hub_signature_256, settings.github_webhook_secret
        ):
            await logger.awarning("webhook_invalid_signature")
            response.status_code = status.HTTP_401_UNAUTHORIZED
            return WebhookResponse(
                status="error",
                message="Invalid webhook signature",
            )

    # Parse event
    event_type = x_github_event or "unknown"
    payload = await request.json()

    action = ""
    repo = ""
    sender = ""

    if isinstance(payload, dict):
        action = str(payload.get("action", ""))
        repo_data = payload.get("repository", {})
        if isinstance(repo_data, dict):
            repo = str(repo_data.get("full_name", ""))
        sender_data = payload.get("sender", {})
        if isinstance(sender_data, dict):
            sender = str(sender_data.get("login", ""))

    await logger.ainfo(
        "webhook_received",
        event_type=event_type,
        action=action,
        repo=repo,
        sender=sender,
    )

    # Process supported event types
    if event_type == "issues":
        await _handle_issue_event(action, repo, payload)
        return WebhookResponse(
            status="accepted",
            message=f"Issue event processed: {action}",
        )

    if event_type == "pull_request":
        await _handle_pr_event(action, repo, payload)
        return WebhookResponse(
            status="accepted",
            message=f"PR event processed: {action}",
        )

    if event_type == "push":
        await _handle_push_event(repo, payload)
        return WebhookResponse(
            status="accepted",
            message="Push event processed",
        )

    if event_type == "ping":
        await logger.ainfo("webhook_ping_received", repo=repo)
        return WebhookResponse(
            status="accepted",
            message="Pong!",
        )

    # Store and broadcast unknown supported events
    if event_type in ("create", "delete", "release", "workflow_run"):
        event_data: dict[str, object] = {
            "type": "github_event",
            "event": event_type,
            "action": action,
            "repo": repo,
            "summary": {"sender": sender},
        }
        _store_event(event_type, action, repo, {"sender": sender})
        await ios_manager.broadcast_json(event_data)
        return WebhookResponse(
            status="accepted",
            message=f"Event processed: {event_type}/{action}",
        )

    # Unsupported event types
    await logger.ainfo(
        "webhook_ignored",
        event_type=event_type,
        reason="unsupported event type",
    )
    return WebhookResponse(
        status="ignored",
        message=f"Unsupported event type: {event_type}",
    )


async def _handle_issue_event(
    action: str,
    repo: str,
    payload: dict[str, object],
) -> None:
    """Handle issue webhook events.

    Args:
        action: Webhook action (opened, closed, edited, labeled, etc.).
        repo: Repository full name.
        payload: Full webhook payload.
    """
    issue = payload.get("issue", {})
    issue_number = 0
    issue_title = ""
    issue_url = ""
    sender = ""
    if isinstance(issue, dict):
        issue_number = int(issue.get("number", 0))
        issue_title = str(issue.get("title", ""))
        issue_url = str(issue.get("html_url", ""))
    sender_data = payload.get("sender", {})
    if isinstance(sender_data, dict):
        sender = str(sender_data.get("login", ""))

    await logger.ainfo(
        "webhook_issue_event",
        action=action,
        repo=repo,
        issue_number=issue_number,
        issue_title=issue_title,
    )

    summary: dict[str, object] = {
        "number": issue_number,
        "title": issue_title,
        "url": issue_url,
        "sender": sender,
    }
    _store_event("issues", action, repo, summary)

    # Broadcast to connected iOS clients
    await ios_manager.broadcast_json({
        "type": "github_event",
        "event": "issues",
        "action": action,
        "repo": repo,
        "summary": summary,
    })

    # Create proactive notification
    if action in ("opened", "closed", "reopened"):
        await _create_proactive_notification_for_all_users(
            event_type="issues",
            action=action,
            repo=repo,
            title=f"Issue #{issue_number} {action}",
            body=f"{issue_title} — {repo}",
            source_event=f"github:issues:{repo}:{issue_number}:{action}",
            deep_link=issue_url or None,
            metadata={
                "repo": repo, "event": "issues",
                "action": action, "issue_number": str(issue_number),
            },
        )


async def _handle_pr_event(
    action: str,
    repo: str,
    payload: dict[str, object],
) -> None:
    """Handle pull request webhook events.

    Args:
        action: Webhook action (opened, closed, merged, etc.).
        repo: Repository full name.
        payload: Full webhook payload.
    """
    pr = payload.get("pull_request", {})
    pr_number = 0
    pr_title = ""
    pr_url = ""
    merged = False
    sender = ""
    if isinstance(pr, dict):
        pr_number = int(pr.get("number", 0))
        pr_title = str(pr.get("title", ""))
        pr_url = str(pr.get("html_url", ""))
        merged = bool(pr.get("merged", False))
    sender_data = payload.get("sender", {})
    if isinstance(sender_data, dict):
        sender = str(sender_data.get("login", ""))

    await logger.ainfo(
        "webhook_pr_event",
        action=action,
        repo=repo,
        pr_number=pr_number,
        pr_title=pr_title,
        merged=merged,
    )

    pr_action = "merged" if merged else action
    pr_summary: dict[str, object] = {
        "number": pr_number,
        "title": pr_title,
        "url": pr_url,
        "merged": merged,
        "sender": sender,
    }
    _store_event("pull_request", pr_action, repo, pr_summary)

    # Broadcast to connected iOS clients
    await ios_manager.broadcast_json({
        "type": "github_event",
        "event": "pull_request",
        "action": pr_action,
        "repo": repo,
        "summary": pr_summary,
    })

    # Create proactive notification for PR events
    if action in ("opened", "closed", "merged"):
        await _create_proactive_notification_for_all_users(
            event_type="pull_request",
            action=pr_action,
            repo=repo,
            title=f"PR #{pr_number} {pr_action}",
            body=f"{pr_title} — {repo}",
            source_event=f"github:pull_request:{repo}:{pr_number}:{pr_action}",
            deep_link=pr_url or None,
            metadata={
                "repo": repo, "event": "pull_request",
                "action": pr_action, "pr_number": str(pr_number),
            },
        )


async def _handle_push_event(
    repo: str,
    payload: dict[str, object],
) -> None:
    """Handle push webhook events.

    Args:
        repo: Repository full name.
        payload: Full webhook payload.
    """
    ref = str(payload.get("ref", ""))
    commits = payload.get("commits", [])
    commit_count = len(commits) if isinstance(commits, list) else 0
    branch = ref.replace("refs/heads/", "") if ref.startswith("refs/heads/") else ref
    pusher_data = payload.get("pusher", {})
    pusher = str(pusher_data.get("name", "")) if isinstance(pusher_data, dict) else ""

    # Extract head commit info
    head_commit = payload.get("head_commit", {})
    head_message = ""
    if isinstance(head_commit, dict):
        head_message = str(head_commit.get("message", "")).split("\n")[0][:100]

    await logger.ainfo(
        "webhook_push_event",
        repo=repo,
        ref=ref,
        commit_count=commit_count,
    )

    push_summary: dict[str, object] = {
        "branch": branch,
        "commit_count": commit_count,
        "head_message": head_message,
        "pusher": pusher,
    }
    _store_event("push", "push", repo, push_summary)

    # Broadcast to connected iOS clients
    await ios_manager.broadcast_json({
        "type": "github_event",
        "event": "push",
        "action": "push",
        "repo": repo,
        "summary": push_summary,
    })


async def _create_proactive_notification_for_all_users(
    event_type: str,
    action: str,
    repo: str,
    title: str,
    body: str,
    source_event: str,
    deep_link: str | None = None,
    metadata: dict[str, str] | None = None,
) -> None:
    """Create proactive notifications for all active users from a GitHub event.

    Uses a fresh DB session to avoid coupling with the webhook handler.
    """
    try:
        from app.core.database import get_session
        from app.repositories.user_repository import UserRepository

        async for session in get_session():
            user_repo = UserRepository(session)
            users = await user_repo.get_all_active()
            service = ProactiveNotificationService(session)
            for user in users:
                try:
                    notification_resp = await service.create_from_github_event(
                        user_id=user.id,
                        event_type=event_type,
                        action=action,
                        repo=repo,
                        title=title,
                        body=body,
                        source_event=source_event,
                        deep_link=deep_link,
                        metadata=metadata,
                    )
                    # Push via WebSocket
                    unread = await service.get_unread_count(user.id)
                    await ios_manager.broadcast_json({
                        "type": "proactive_notification",
                        "notification": {
                            "id": str(notification_resp.id),
                            "type": notification_resp.type.value,
                            "priority": notification_resp.priority.value,
                            "title": notification_resp.title,
                            "body": notification_resp.body,
                            "source": notification_resp.source,
                            "deep_link": notification_resp.deep_link,
                            "created_at": notification_resp.created_at.isoformat(),
                        },
                        "unread_count": unread.count,
                    })
                except Exception:
                    await logger.aexception(
                        "proactive_notification_create_failed",
                        user_id=str(user.id),
                        event_type=event_type,
                    )
            await session.commit()
    except Exception:
        await logger.aexception(
            "proactive_notification_webhook_handler_failed",
            event_type=event_type,
            action=action,
        )


def _store_event(
    event: str,
    action: str,
    repo: str,
    summary: dict[str, object],
) -> None:
    """Store a webhook event in the in-memory ring buffer."""
    _recent_events.appendleft({
        "event": event,
        "action": action,
        "repo": repo,
        "summary": summary,
        "received_at": datetime.now(UTC).isoformat(),
    })


@router.get(
    "/github/events",
    response_model=GitHubEventsResponse,
    summary="Son GitHub webhook olaylarini listele",
)
async def list_github_events(limit: int = 20) -> GitHubEventsResponse:
    """Return the most recent GitHub webhook events (in-memory, up to 100).

    Args:
        limit: Maximum number of events to return (default 20).

    Returns:
        List of recent GitHub events.
    """
    capped = min(limit, 100)
    events = [GitHubEventSummary(**e) for e in list(_recent_events)[:capped]]
    return GitHubEventsResponse(events=events, total=len(_recent_events))
