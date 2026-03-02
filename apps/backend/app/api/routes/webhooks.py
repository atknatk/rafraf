"""GitHub webhook receiver endpoint."""

import structlog
from fastapi import APIRouter, Header, Request, Response
from starlette import status

from app.core.config import get_settings
from app.schemas.github import WebhookResponse
from app.services.github_service import GitHubService

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


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
    if isinstance(issue, dict):
        issue_number = int(issue.get("number", 0))
        issue_title = str(issue.get("title", ""))

    await logger.ainfo(
        "webhook_issue_event",
        action=action,
        repo=repo,
        issue_number=issue_number,
        issue_title=issue_title,
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
    merged = False
    if isinstance(pr, dict):
        pr_number = int(pr.get("number", 0))
        pr_title = str(pr.get("title", ""))
        merged = bool(pr.get("merged", False))

    await logger.ainfo(
        "webhook_pr_event",
        action=action,
        repo=repo,
        pr_number=pr_number,
        pr_title=pr_title,
        merged=merged,
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

    await logger.ainfo(
        "webhook_push_event",
        repo=repo,
        ref=ref,
        commit_count=commit_count,
    )
