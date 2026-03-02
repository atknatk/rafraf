"""Unit tests for ApprovalService."""

import asyncio

import pytest

from app.schemas.approval import (
    ApprovalCategory,
    ApprovalDecision,
    ApprovalRequestCreate,
    ApprovalStatus,
)
from app.services.approval_service import ApprovalService


@pytest.fixture
def approval_service() -> ApprovalService:
    """Create a fresh ApprovalService for each test."""
    return ApprovalService()


@pytest.fixture
def sample_request() -> ApprovalRequestCreate:
    """Create a sample approval request."""
    return ApprovalRequestCreate(
        session_id="sess-test-001",
        connection_id="conn-test-001",
        tool_name="docker_push",
        action="push",
        description="Docker image'i registry'ye push etmek istiyor musunuz?",
        params={"tag": "latest"},
        category=ApprovalCategory.DEPLOY,
        timeout_seconds=300,
    )


class TestCheckRequiresApproval:
    """Tests for check_requires_approval method."""

    def test_docker_push_requires_approval(self, approval_service: ApprovalService) -> None:
        assert approval_service.check_requires_approval("docker_push") is True

    def test_kubectl_requires_approval(self, approval_service: ApprovalService) -> None:
        assert approval_service.check_requires_approval("kubectl") is True

    def test_git_push_requires_approval(self, approval_service: ApprovalService) -> None:
        assert approval_service.check_requires_approval("git_push") is True

    def test_git_status_no_approval(self, approval_service: ApprovalService) -> None:
        assert approval_service.check_requires_approval("git_status") is False

    def test_docker_ps_no_approval(self, approval_service: ApprovalService) -> None:
        assert approval_service.check_requires_approval("docker_ps") is False

    def test_unknown_tool_no_approval(self, approval_service: ApprovalService) -> None:
        assert approval_service.check_requires_approval("nonexistent_tool") is False


class TestGetApprovalCategory:
    """Tests for get_approval_category method."""

    def test_deploy_category(self, approval_service: ApprovalService) -> None:
        assert approval_service.get_approval_category("docker_push") == ApprovalCategory.DEPLOY

    def test_infrastructure_category(self, approval_service: ApprovalService) -> None:
        assert approval_service.get_approval_category("kubectl") == ApprovalCategory.INFRASTRUCTURE

    def test_write_remote_category(self, approval_service: ApprovalService) -> None:
        assert approval_service.get_approval_category("git_push") == ApprovalCategory.WRITE_REMOTE

    def test_destructive_category(self, approval_service: ApprovalService) -> None:
        assert approval_service.get_approval_category("shell_rm") == ApprovalCategory.DESTRUCTIVE

    def test_none_for_unknown_tool(self, approval_service: ApprovalService) -> None:
        assert approval_service.get_approval_category("unknown") is None


class TestCreateApproval:
    """Tests for create_approval method."""

    async def test_creates_approval_record(
        self,
        approval_service: ApprovalService,
        sample_request: ApprovalRequestCreate,
    ) -> None:
        record = await approval_service.create_approval(sample_request)
        assert record.id is not None
        assert record.session_id == "sess-test-001"
        assert record.tool_name == "docker_push"
        assert record.status == ApprovalStatus.PENDING
        assert record.category == ApprovalCategory.DEPLOY

    async def test_approval_stored_in_pending(
        self,
        approval_service: ApprovalService,
        sample_request: ApprovalRequestCreate,
    ) -> None:
        record = await approval_service.create_approval(sample_request)
        assert approval_service.pending_count == 1
        assert approval_service.get_pending_approval(record.id) is not None

    async def test_timeout_calculated_from_category(
        self,
        approval_service: ApprovalService,
    ) -> None:
        req = ApprovalRequestCreate(
            session_id="sess-test-002",
            connection_id="conn-test-002",
            tool_name="git_push",
            action="push",
            description="Push to remote",
            category=ApprovalCategory.WRITE_REMOTE,
        )
        record = await approval_service.create_approval(req)
        # WRITE_REMOTE has 180 second timeout
        assert record.timeout_seconds == 180

    async def test_unique_ids(
        self,
        approval_service: ApprovalService,
        sample_request: ApprovalRequestCreate,
    ) -> None:
        record1 = await approval_service.create_approval(sample_request)
        # Create a second request with different session
        req2 = ApprovalRequestCreate(
            session_id="sess-test-003",
            connection_id="conn-test-003",
            tool_name="kubectl",
            action="apply",
            description="Apply manifest",
            category=ApprovalCategory.INFRASTRUCTURE,
        )
        record2 = await approval_service.create_approval(req2)
        assert record1.id != record2.id


class TestSubmitDecision:
    """Tests for submit_decision method."""

    async def test_submit_approve_decision(
        self,
        approval_service: ApprovalService,
        sample_request: ApprovalRequestCreate,
    ) -> None:
        record = await approval_service.create_approval(sample_request)

        # Start waiting in a background task
        result_future: asyncio.Future[object] = asyncio.get_running_loop().create_future()

        async def wait_task() -> None:
            result = await approval_service.wait_for_decision(record.id)
            result_future.set_result(result)

        task = asyncio.create_task(wait_task())

        # Give the waiter time to register
        await asyncio.sleep(0.05)

        # Submit approval
        decision = ApprovalDecision(
            approval_id=record.id,
            decision="approved",
            note="Approved by user",
        )
        submitted = await approval_service.submit_decision(decision)
        assert submitted is True

        # Wait for result
        await task
        result = result_future.result()
        assert result.approved is True  # type: ignore[union-attr]
        assert result.decision == "approved"  # type: ignore[union-attr]
        assert result.note == "Approved by user"  # type: ignore[union-attr]

    async def test_submit_reject_decision(
        self,
        approval_service: ApprovalService,
        sample_request: ApprovalRequestCreate,
    ) -> None:
        record = await approval_service.create_approval(sample_request)

        result_future: asyncio.Future[object] = asyncio.get_running_loop().create_future()

        async def wait_task() -> None:
            result = await approval_service.wait_for_decision(record.id)
            result_future.set_result(result)

        task = asyncio.create_task(wait_task())
        await asyncio.sleep(0.05)

        decision = ApprovalDecision(
            approval_id=record.id,
            decision="rejected",
            note="Too risky",
        )
        submitted = await approval_service.submit_decision(decision)
        assert submitted is True

        await task
        result = result_future.result()
        assert result.approved is False  # type: ignore[union-attr]
        assert result.decision == "rejected"  # type: ignore[union-attr]

    async def test_submit_decision_no_waiter(self, approval_service: ApprovalService) -> None:
        decision = ApprovalDecision(
            approval_id="nonexistent-id",
            decision="approved",
        )
        submitted = await approval_service.submit_decision(decision)
        assert submitted is False


class TestWaitForDecision:
    """Tests for wait_for_decision method."""

    async def test_wait_not_found(self, approval_service: ApprovalService) -> None:
        result = await approval_service.wait_for_decision("nonexistent-id")
        assert result.approved is False
        assert result.decision == "not_found"

    async def test_timeout_expires_approval(
        self,
        approval_service: ApprovalService,
    ) -> None:
        from unittest.mock import patch as mock_patch

        # Override CATEGORY_TIMEOUTS so the test timeout is respected
        with mock_patch.dict(
            "app.services.approval_service.CATEGORY_TIMEOUTS",
            {ApprovalCategory.DEPLOY: 1},
        ):
            req = ApprovalRequestCreate(
                session_id="sess-timeout",
                connection_id="conn-timeout",
                tool_name="docker_push",
                action="push",
                description="Push image",
                category=ApprovalCategory.DEPLOY,
                timeout_seconds=1,
            )
            record = await approval_service.create_approval(req)

        # Wait for the timeout (record has timeout_seconds=1)
        result = await approval_service.wait_for_decision(record.id)
        assert result.approved is False
        assert result.decision == "expired"
        assert approval_service.pending_count == 0


class TestGetSessionPending:
    """Tests for get_session_pending method."""

    async def test_returns_pending_for_session(
        self,
        approval_service: ApprovalService,
        sample_request: ApprovalRequestCreate,
    ) -> None:
        record = await approval_service.create_approval(sample_request)
        pending = approval_service.get_session_pending("sess-test-001")
        assert pending is not None
        assert pending.id == record.id

    def test_returns_none_for_unknown_session(self, approval_service: ApprovalService) -> None:
        pending = approval_service.get_session_pending("unknown-session")
        assert pending is None


class TestApprovalHistory:
    """Tests for approval history tracking."""

    async def test_approved_added_to_history(
        self,
        approval_service: ApprovalService,
        sample_request: ApprovalRequestCreate,
    ) -> None:
        record = await approval_service.create_approval(sample_request)

        async def wait_and_decide() -> None:
            await asyncio.sleep(0.05)
            decision = ApprovalDecision(approval_id=record.id, decision="approved")
            await approval_service.submit_decision(decision)

        task = asyncio.create_task(wait_and_decide())
        await approval_service.wait_for_decision(record.id)
        await task

        history = approval_service.get_history()
        assert len(history) == 1
        assert history[0].id == record.id
        assert history[0].status == ApprovalStatus.APPROVED

    async def test_expired_added_to_history(
        self,
        approval_service: ApprovalService,
    ) -> None:
        from unittest.mock import patch as mock_patch

        with mock_patch.dict(
            "app.services.approval_service.CATEGORY_TIMEOUTS",
            {ApprovalCategory.INFRASTRUCTURE: 1},
        ):
            req = ApprovalRequestCreate(
                session_id="sess-expire",
                connection_id="conn-expire",
                tool_name="kubectl",
                action="apply",
                description="Apply manifest",
                category=ApprovalCategory.INFRASTRUCTURE,
                timeout_seconds=1,
            )
            record = await approval_service.create_approval(req)
        await approval_service.wait_for_decision(record.id)

        history = approval_service.get_history()
        assert len(history) == 1
        assert history[0].status == ApprovalStatus.EXPIRED

    def test_history_limit(self, approval_service: ApprovalService) -> None:
        history = approval_service.get_history(limit=10)
        assert len(history) == 0


class TestBuildQuestionMessage:
    """Tests for build_question_message method."""

    async def test_builds_valid_question_message(
        self,
        approval_service: ApprovalService,
        sample_request: ApprovalRequestCreate,
    ) -> None:
        record = await approval_service.create_approval(sample_request)
        message = approval_service.build_question_message(record, "sess-test-001")

        assert message["type"] == "question"
        assert "content" in message
        content = message["content"]
        assert isinstance(content, dict)
        assert content["approval_id"] == record.id
        assert content["category"] == "deploy"
        assert content["timeout_seconds"] == record.timeout_seconds
        assert len(content["options"]) == 2

    async def test_question_has_approve_reject_options(
        self,
        approval_service: ApprovalService,
        sample_request: ApprovalRequestCreate,
    ) -> None:
        record = await approval_service.create_approval(sample_request)
        message = approval_service.build_question_message(record, "sess-test-001")

        content = message["content"]
        assert isinstance(content, dict)
        options = content["options"]
        option_ids = [opt["id"] for opt in options]
        assert "approve" in option_ids
        assert "reject" in option_ids

    async def test_question_has_metadata(
        self,
        approval_service: ApprovalService,
        sample_request: ApprovalRequestCreate,
    ) -> None:
        record = await approval_service.create_approval(sample_request)
        message = approval_service.build_question_message(record, "sess-test-001")

        assert "metadata" in message
        metadata = message["metadata"]
        assert isinstance(metadata, dict)
        assert metadata["direction"] == "server_to_client"
        assert metadata["session_id"] == "sess-test-001"
