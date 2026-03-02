"""Unit tests for approval schemas."""

import pytest
from pydantic import ValidationError

from app.schemas.approval import (
    APPROVAL_MATRIX,
    CATEGORY_TIMEOUTS,
    ApprovalCategory,
    ApprovalDecision,
    ApprovalRequestCreate,
    ApprovalRequestRecord,
    ApprovalResult,
    ApprovalStatus,
)


class TestApprovalCategory:
    """Tests for ApprovalCategory enum."""

    def test_deploy_value(self) -> None:
        assert ApprovalCategory.DEPLOY == "deploy"

    def test_destructive_value(self) -> None:
        assert ApprovalCategory.DESTRUCTIVE == "destructive"

    def test_infrastructure_value(self) -> None:
        assert ApprovalCategory.INFRASTRUCTURE == "infrastructure"

    def test_write_remote_value(self) -> None:
        assert ApprovalCategory.WRITE_REMOTE == "write_remote"

    def test_all_categories_count(self) -> None:
        assert len(ApprovalCategory) == 4


class TestApprovalStatus:
    """Tests for ApprovalStatus enum."""

    def test_pending_value(self) -> None:
        assert ApprovalStatus.PENDING == "pending"

    def test_approved_value(self) -> None:
        assert ApprovalStatus.APPROVED == "approved"

    def test_rejected_value(self) -> None:
        assert ApprovalStatus.REJECTED == "rejected"

    def test_expired_value(self) -> None:
        assert ApprovalStatus.EXPIRED == "expired"

    def test_all_statuses_count(self) -> None:
        assert len(ApprovalStatus) == 4


class TestApprovalRequestCreate:
    """Tests for ApprovalRequestCreate schema."""

    def test_valid_request_create(self) -> None:
        req = ApprovalRequestCreate(
            session_id="sess-123",
            connection_id="conn-456",
            tool_name="docker_push",
            action="push",
            description="Push image to registry",
            category=ApprovalCategory.DEPLOY,
        )
        assert req.session_id == "sess-123"
        assert req.connection_id == "conn-456"
        assert req.tool_name == "docker_push"
        assert req.action == "push"
        assert req.description == "Push image to registry"
        assert req.category == ApprovalCategory.DEPLOY
        assert req.timeout_seconds == 300

    def test_custom_timeout(self) -> None:
        req = ApprovalRequestCreate(
            session_id="sess-123",
            connection_id="conn-456",
            tool_name="kubectl",
            action="apply",
            description="Apply K8s manifest",
            category=ApprovalCategory.INFRASTRUCTURE,
            timeout_seconds=600,
        )
        assert req.timeout_seconds == 600

    def test_with_params(self) -> None:
        req = ApprovalRequestCreate(
            session_id="sess-123",
            connection_id="conn-456",
            tool_name="shell_rm",
            action="remove",
            description="Delete file",
            params={"path": "/tmp/test.txt"},
            category=ApprovalCategory.DESTRUCTIVE,
        )
        assert req.params == {"path": "/tmp/test.txt"}

    def test_params_default_none(self) -> None:
        req = ApprovalRequestCreate(
            session_id="sess-123",
            connection_id="conn-456",
            tool_name="git_push",
            action="push",
            description="Push to remote",
            category=ApprovalCategory.WRITE_REMOTE,
        )
        assert req.params is None

    def test_is_frozen(self) -> None:
        req = ApprovalRequestCreate(
            session_id="sess-123",
            connection_id="conn-456",
            tool_name="docker_push",
            action="push",
            description="Push image",
            category=ApprovalCategory.DEPLOY,
        )
        with pytest.raises(ValidationError):
            req.session_id = "new-session"  # type: ignore[misc]

    def test_missing_required_field(self) -> None:
        with pytest.raises(ValidationError):
            ApprovalRequestCreate(
                session_id="sess-123",
                connection_id="conn-456",
                tool_name="docker_push",
                # missing action, description, category
            )  # type: ignore[call-arg]


class TestApprovalDecision:
    """Tests for ApprovalDecision schema."""

    def test_valid_approve_decision(self) -> None:
        decision = ApprovalDecision(
            approval_id="appr-123",
            decision="approved",
        )
        assert decision.approval_id == "appr-123"
        assert decision.decision == "approved"
        assert decision.note is None

    def test_valid_reject_decision(self) -> None:
        decision = ApprovalDecision(
            approval_id="appr-456",
            decision="rejected",
            note="Too risky",
        )
        assert decision.decision == "rejected"
        assert decision.note == "Too risky"

    def test_is_frozen(self) -> None:
        decision = ApprovalDecision(
            approval_id="appr-123",
            decision="approved",
        )
        with pytest.raises(ValidationError):
            decision.decision = "rejected"  # type: ignore[misc]


class TestApprovalResult:
    """Tests for ApprovalResult schema."""

    def test_approved_result(self) -> None:
        result = ApprovalResult(
            approved=True,
            approval_id="appr-123",
            decision="approved",
        )
        assert result.approved is True
        assert result.decision == "approved"

    def test_rejected_result(self) -> None:
        result = ApprovalResult(
            approved=False,
            approval_id="appr-456",
            decision="rejected",
            note="Not safe",
        )
        assert result.approved is False
        assert result.note == "Not safe"

    def test_expired_result(self) -> None:
        result = ApprovalResult(
            approved=False,
            approval_id="appr-789",
            decision="expired",
            note="Approval request timed out",
        )
        assert result.decision == "expired"

    def test_is_frozen(self) -> None:
        result = ApprovalResult(
            approved=True,
            approval_id="appr-123",
            decision="approved",
        )
        with pytest.raises(ValidationError):
            result.approved = False  # type: ignore[misc]


class TestApprovalRequestRecord:
    """Tests for ApprovalRequestRecord schema."""

    def test_valid_record(self) -> None:
        from datetime import UTC, datetime

        now = datetime.now(tz=UTC)
        record = ApprovalRequestRecord(
            id="rec-123",
            session_id="sess-123",
            connection_id="conn-456",
            tool_name="docker_push",
            action="push",
            description="Push image",
            category=ApprovalCategory.DEPLOY,
            timeout_seconds=300,
            timeout_at=now,
            created_at=now,
        )
        assert record.id == "rec-123"
        assert record.status == ApprovalStatus.PENDING
        assert record.responded_at is None

    def test_auto_generates_id(self) -> None:
        from datetime import UTC, datetime

        now = datetime.now(tz=UTC)
        record = ApprovalRequestRecord(
            session_id="sess-123",
            connection_id="conn-456",
            tool_name="docker_push",
            action="push",
            description="Push image",
            category=ApprovalCategory.DEPLOY,
            timeout_seconds=300,
            timeout_at=now,
            created_at=now,
        )
        assert record.id is not None
        assert len(record.id) > 0


class TestApprovalMatrix:
    """Tests for the approval matrix configuration."""

    def test_docker_push_requires_deploy_approval(self) -> None:
        assert APPROVAL_MATRIX["docker_push"] == ApprovalCategory.DEPLOY

    def test_kubectl_requires_infrastructure_approval(self) -> None:
        assert APPROVAL_MATRIX["kubectl"] == ApprovalCategory.INFRASTRUCTURE

    def test_git_push_requires_write_remote_approval(self) -> None:
        assert APPROVAL_MATRIX["git_push"] == ApprovalCategory.WRITE_REMOTE

    def test_shell_rm_requires_destructive_approval(self) -> None:
        assert APPROVAL_MATRIX["shell_rm"] == ApprovalCategory.DESTRUCTIVE

    def test_non_existent_tool_not_in_matrix(self) -> None:
        assert "git_status" not in APPROVAL_MATRIX
        assert "docker_ps" not in APPROVAL_MATRIX

    def test_matrix_has_expected_tool_count(self) -> None:
        assert len(APPROVAL_MATRIX) >= 10


class TestCategoryTimeouts:
    """Tests for category-specific timeouts."""

    def test_deploy_timeout(self) -> None:
        assert CATEGORY_TIMEOUTS[ApprovalCategory.DEPLOY] == 300

    def test_write_remote_timeout(self) -> None:
        assert CATEGORY_TIMEOUTS[ApprovalCategory.WRITE_REMOTE] == 180

    def test_all_categories_have_timeout(self) -> None:
        for category in ApprovalCategory:
            assert category in CATEGORY_TIMEOUTS
