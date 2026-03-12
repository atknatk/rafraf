"""GitHub webhook receiver endpoint with DB-backed storage and idempotency."""

from uuid import uuid4

import structlog
from fastapi import APIRouter, Header, Request, Response
from pydantic import BaseModel, ConfigDict
from starlette import status

from app.api.routes.websocket import manager as ios_manager
from app.core.config import get_settings
from app.core.database import async_session_factory
from app.schemas.github import WebhookResponse
from app.services.github_service import GitHubService
from app.services.proactive_notification_service import ProactiveNotificationService
from app.services.webhook_event_service import WebhookEventService

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


class GitHubEventSummary(BaseModel):
    """Summary of a recent GitHub webhook event."""

    model_config = ConfigDict(frozen=True)

    id: str | None = None
    delivery_id: str | None = None
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
    x_github_delivery: str | None = Header(default=None),
) -> WebhookResponse:
    """Receive and process GitHub webhook events.

    Validates HMAC-SHA256 signature, checks idempotency via delivery ID,
    and processes supported event types (pull_request, issues, push, check_run).

    Args:
        request: FastAPI request object.
        response: FastAPI response object.
        x_hub_signature_256: GitHub webhook signature header.
        x_github_event: GitHub event type header.
        x_github_delivery: GitHub delivery ID for idempotency.

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
    delivery_id = x_github_delivery or str(uuid4())
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
        delivery_id=delivery_id,
    )

    # Idempotency check — skip already-processed events
    async with async_session_factory() as session:
        event_service = WebhookEventService(session)

        if await event_service.is_duplicate(delivery_id):
            await logger.ainfo(
                "webhook_duplicate_skipped",
                delivery_id=delivery_id,
                event_type=event_type,
            )
            return WebhookResponse(
                status="accepted",
                message="Event already processed",
            )

        # Process supported event types
        summary: dict[str, object] = {}

        if event_type == "issues":
            summary = await _handle_issue_event(action, repo, payload)
        elif event_type == "pull_request":
            summary = await _handle_pr_event(action, repo, payload)
        elif event_type == "push":
            summary = await _handle_push_event(repo, payload)
        elif event_type == "check_run":
            summary = await _handle_check_run_event(action, repo, payload)
        elif event_type == "ping":
            await logger.ainfo("webhook_ping_received", repo=repo)
            summary = {"repo": repo}
        elif event_type in ("create", "delete", "release", "workflow_run"):
            summary = {"sender": sender}
            event_data: dict[str, object] = {
                "type": "github_event",
                "event": event_type,
                "action": action,
                "repo": repo,
                "summary": summary,
            }
            await ios_manager.broadcast_json(event_data)
        else:
            await logger.ainfo(
                "webhook_ignored",
                event_type=event_type,
                reason="unsupported event type",
            )
            return WebhookResponse(
                status="ignored",
                message=f"Unsupported event type: {event_type}",
            )

        # Persist event to DB
        await event_service.record_event(
            delivery_id=delivery_id,
            event_type=event_type,
            action=action,
            repo=repo,
            sender=sender,
            summary=summary,
        )
        await session.commit()

    message = f"{event_type} event processed"
    if action:
        message = f"{event_type} event processed: {action}"

    return WebhookResponse(
        status="accepted",
        message=message,
    )


async def _handle_issue_event(
    action: str,
    repo: str,
    payload: dict[str, object],
) -> dict[str, object]:
    """Handle issue webhook events.

    Args:
        action: Webhook action (opened, closed, edited, labeled, etc.).
        repo: Repository full name.
        payload: Full webhook payload.

    Returns:
        Event summary dict.
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

    return summary


async def _handle_pr_event(
    action: str,
    repo: str,
    payload: dict[str, object],
) -> dict[str, object]:
    """Handle pull request webhook events.

    Args:
        action: Webhook action (opened, closed, merged, etc.).
        repo: Repository full name.
        payload: Full webhook payload.

    Returns:
        Event summary dict.
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

    return pr_summary


async def _handle_push_event(
    repo: str,
    payload: dict[str, object],
) -> dict[str, object]:
    """Handle push webhook events.

    Args:
        repo: Repository full name.
        payload: Full webhook payload.

    Returns:
        Event summary dict.
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

    # Broadcast to connected iOS clients
    await ios_manager.broadcast_json({
        "type": "github_event",
        "event": "push",
        "action": "push",
        "repo": repo,
        "summary": push_summary,
    })

    return push_summary


async def _handle_check_run_event(
    action: str,
    repo: str,
    payload: dict[str, object],
) -> dict[str, object]:
    """Handle check_run webhook events (CI status).

    Sends proactive notifications when CI checks fail, time out, or are cancelled.

    Args:
        action: Webhook action (created, completed, rerequested, etc.).
        repo: Repository full name.
        payload: Full webhook payload.

    Returns:
        Event summary dict.
    """
    check_run = payload.get("check_run", {})
    check_name = ""
    check_status = ""
    conclusion = ""
    check_url = ""
    check_id = 0
    sender = ""

    if isinstance(check_run, dict):
        check_name = str(check_run.get("name", ""))
        check_status = str(check_run.get("status", ""))
        conclusion = str(check_run.get("conclusion", "") or "")
        check_url = str(check_run.get("html_url", ""))
        check_id = int(check_run.get("id", 0))

    sender_data = payload.get("sender", {})
    if isinstance(sender_data, dict):
        sender = str(sender_data.get("login", ""))

    await logger.ainfo(
        "webhook_check_run_event",
        action=action,
        repo=repo,
        check_name=check_name,
        status=check_status,
        conclusion=conclusion,
    )

    check_summary: dict[str, object] = {
        "check_id": check_id,
        "name": check_name,
        "status": check_status,
        "conclusion": conclusion,
        "url": check_url,
        "sender": sender,
    }

    # Broadcast to connected iOS clients
    await ios_manager.broadcast_json({
        "type": "github_event",
        "event": "check_run",
        "action": action,
        "repo": repo,
        "summary": check_summary,
    })

    # Create proactive notification for CI failures
    if action == "completed" and conclusion in ("failure", "timed_out", "cancelled"):
        await _create_proactive_notification_for_all_users(
            event_type="check_run",
            action=conclusion,
            repo=repo,
            title=f"CI {conclusion}: {check_name}",
            body=f"Check run '{check_name}' {conclusion} — {repo}",
            source_event=f"github:check_run:{repo}:{check_id}:{conclusion}",
            deep_link=check_url or None,
            metadata={
                "repo": repo, "event": "check_run",
                "action": conclusion, "check_name": check_name,
                "check_id": str(check_id),
            },
        )

    return check_summary


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


@router.get(
    "/github/events",
    response_model=GitHubEventsResponse,
    summary="Son GitHub webhook olaylarini listele",
)
async def list_github_events(
    limit: int = 20,
    event_type: str | None = None,
) -> GitHubEventsResponse:
    """Return the most recent GitHub webhook events from the database.

    Args:
        limit: Maximum number of events to return (default 20, max 100).
        event_type: Optional filter by event type (push, pull_request, issues, check_run).

    Returns:
        List of recent GitHub events with total count.
    """
    async with async_session_factory() as session:
        event_service = WebhookEventService(session)
        events, total = await event_service.list_events(
            limit=limit,
            event_type=event_type,
        )

        event_summaries = [
            GitHubEventSummary(
                id=str(e.id),
                delivery_id=e.delivery_id,
                event=e.event_type,
                action=e.action,
                repo=e.repo,
                summary=e.summary,
                received_at=e.created_at.isoformat(),
            )
            for e in events
        ]
        return GitHubEventsResponse(events=event_summaries, total=total)
