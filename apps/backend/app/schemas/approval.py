"""Approval system Pydantic schemas."""

from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class ApprovalCategory(StrEnum):
    """Categories of operations requiring approval."""

    DEPLOY = "deploy"
    DESTRUCTIVE = "destructive"
    INFRASTRUCTURE = "infrastructure"
    WRITE_REMOTE = "write_remote"


class ApprovalStatus(StrEnum):
    """Status of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ApprovalRequestCreate(BaseModel):
    """Data needed to create a new approval request.

    The bridge-correlation block (V1.4) is optional so the legacy
    orchestrator-mediated path keeps working unchanged. Bridge-originated
    requests (``event.session.permission_request``) populate all four
    optional fields so the awaiter can later dispatch a
    ``command.claude.permission.{allow,deny}`` envelope back to the right
    bridge with the right correlation tokens.
    """

    model_config = ConfigDict(frozen=True)

    session_id: str
    connection_id: str
    tool_name: str
    action: str
    description: str
    params: dict[str, object] | None = None
    category: ApprovalCategory
    timeout_seconds: int = 300
    # V1.4 — bridge ``permission_request`` correlation tokens.
    request_id: str | None = None
    bridge_host_id: str | None = None
    rpc_id: str | None = None
    # V1.4-fix MEDIUM #1: explicit bridge-suggested timeout. Was previously
    # synthesised from request_id presence — brittle when callers passed
    # request_id for non-bridge purposes. Now passed explicitly by the
    # runner's _handle_permission_request; legacy callers leave it None.
    bridge_timeout_seconds: int | None = None


class ApprovalRequestRecord(BaseModel):
    """Stored approval request record.

    The bridge-correlation block mirrors :class:`ApprovalRequestCreate`
    so the in-memory record exposes the same routing trio the awaiter
    needs (host_id, rpc_id, request_id) without an extra DB lookup.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    connection_id: str
    tool_name: str
    action: str
    description: str
    params: dict[str, object] | None = None
    category: ApprovalCategory
    status: ApprovalStatus = ApprovalStatus.PENDING
    timeout_seconds: int = 300
    timeout_at: datetime
    created_at: datetime
    responded_at: datetime | None = None
    # V1.4 — bridge correlation tokens (None for legacy in-app rows).
    request_id: str | None = None
    bridge_host_id: str | None = None
    rpc_id: str | None = None
    bridge_timeout_seconds: int | None = None


class ApprovalDecision(BaseModel):
    """User's decision on an approval request."""

    model_config = ConfigDict(frozen=True)

    approval_id: str
    decision: str  # "approved" or "rejected"
    note: str | None = None


class ApprovalResult(BaseModel):
    """Result of an approval flow, returned to the caller."""

    model_config = ConfigDict(frozen=True)

    approved: bool
    approval_id: str
    decision: str
    note: str | None = None


# --- Approval Matrix Configuration ---

# Tools that always require approval (with their category)
APPROVAL_MATRIX: dict[str, ApprovalCategory] = {
    # Deploy operations
    "docker_push": ApprovalCategory.DEPLOY,
    # Destructive operations
    "file_delete": ApprovalCategory.DESTRUCTIVE,
    "s3_delete": ApprovalCategory.DESTRUCTIVE,
    # Infrastructure operations
    "kubectl": ApprovalCategory.INFRASTRUCTURE,
    "aws_cli": ApprovalCategory.INFRASTRUCTURE,
    # Write/remote operations
    "git_push": ApprovalCategory.WRITE_REMOTE,
    "github_create_issue": ApprovalCategory.WRITE_REMOTE,
    "github_close_issue": ApprovalCategory.WRITE_REMOTE,
    "github_comment": ApprovalCategory.WRITE_REMOTE,
    "github_merge_pr": ApprovalCategory.WRITE_REMOTE,
    "npm_publish": ApprovalCategory.WRITE_REMOTE,
    "pip_install": ApprovalCategory.WRITE_REMOTE,
    "shell_rm": ApprovalCategory.DESTRUCTIVE,
    "shell_chmod": ApprovalCategory.INFRASTRUCTURE,
    "shell_chown": ApprovalCategory.INFRASTRUCTURE,
}

# Category-specific timeout overrides (default is 300 seconds)
CATEGORY_TIMEOUTS: dict[ApprovalCategory, int] = {
    ApprovalCategory.DEPLOY: 300,
    ApprovalCategory.DESTRUCTIVE: 300,
    ApprovalCategory.INFRASTRUCTURE: 300,
    ApprovalCategory.WRITE_REMOTE: 180,
}
