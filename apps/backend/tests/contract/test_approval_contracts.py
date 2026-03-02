"""Contract tests for approval WebSocket messages.

Verifies that the backend approval schemas match shared/api-contracts/ws/approval-messages.json.
"""

import json
from pathlib import Path

import pytest

from app.schemas.approval import ApprovalCategory
from app.schemas.messages import (
    ApprovalResponsePayload,
    MessageType,
    QuestionOptionPayload,
    QuestionPayload,
)

# Path is relative to apps/backend/ since tests run from there
CONTRACT_FILE = Path("../../shared/api-contracts/ws/approval-messages.json")


@pytest.fixture
def approval_contract() -> dict[str, object]:
    """Load the approval messages contract."""
    with open(CONTRACT_FILE) as f:
        return json.load(f)  # type: ignore[no-any-return]


def _find_message(contract: dict[str, object], msg_type: str) -> dict[str, object] | None:
    """Find a message definition in the contract by type."""
    messages = contract.get("messages", [])
    assert isinstance(messages, list)
    for msg in messages:
        assert isinstance(msg, dict)
        if msg.get("type") == msg_type:
            return msg
    return None


class TestQuestionMessageMatchesContract:
    """Verify question message schema matches the contract."""

    def test_question_type_exists_in_enum(self) -> None:
        """MessageType should include 'question'."""
        assert MessageType.QUESTION == "question"

    def test_question_payload_has_approval_id(self) -> None:
        payload = QuestionPayload(
            approval_id="test-id",
            question="Test?",
            options=[QuestionOptionPayload(id="approve", label="OK", style="primary")],
            timeout_seconds=300,
            category="deploy",
        )
        assert payload.approval_id == "test-id"

    def test_question_payload_has_timeout_seconds(self) -> None:
        payload = QuestionPayload(
            approval_id="test-id",
            question="Test?",
            options=[QuestionOptionPayload(id="approve", label="OK", style="primary")],
            timeout_seconds=300,
            category="deploy",
        )
        assert payload.timeout_seconds == 300

    def test_question_payload_has_category(self) -> None:
        payload = QuestionPayload(
            approval_id="test-id",
            question="Test?",
            options=[QuestionOptionPayload(id="approve", label="OK", style="primary")],
            timeout_seconds=300,
            category="deploy",
        )
        assert payload.category == "deploy"

    def test_question_option_has_required_fields(self) -> None:
        opt = QuestionOptionPayload(id="approve", label="Onayla", style="primary")
        assert opt.id == "approve"
        assert opt.label == "Onayla"
        assert opt.style == "primary"

    def test_contract_question_fields_match_schema(
        self, approval_contract: dict[str, object]
    ) -> None:
        """Contract question payload fields should match QuestionPayload."""
        question_msg = _find_message(approval_contract, "question")
        assert question_msg is not None
        payload_schema = question_msg.get("payload")
        assert isinstance(payload_schema, dict)
        props = payload_schema.get("properties", {})
        assert isinstance(props, dict)

        # All required fields in the contract should exist on QuestionPayload
        required = payload_schema.get("required", [])
        assert isinstance(required, list)
        assert "approval_id" in required
        assert "question" in required
        assert "options" in required
        assert "timeout_seconds" in required
        assert "category" in required

    def test_contract_question_direction(
        self, approval_contract: dict[str, object]
    ) -> None:
        """Question messages are server_to_client."""
        question_msg = _find_message(approval_contract, "question")
        assert question_msg is not None
        assert question_msg["direction"] == "server_to_client"


class TestApprovalResponseMatchesContract:
    """Verify approval_response message schema matches the contract."""

    def test_approval_response_type_exists_in_enum(self) -> None:
        """MessageType should include 'approval_response'."""
        assert MessageType.APPROVAL_RESPONSE == "approval_response"

    def test_approval_response_payload_has_approval_id(self) -> None:
        payload = ApprovalResponsePayload(
            approval_id="test-id",
            decision="approved",
        )
        assert payload.approval_id == "test-id"

    def test_approval_response_payload_has_decision(self) -> None:
        payload = ApprovalResponsePayload(
            approval_id="test-id",
            decision="rejected",
        )
        assert payload.decision == "rejected"

    def test_approval_response_optional_note(self) -> None:
        payload = ApprovalResponsePayload(
            approval_id="test-id",
            decision="approved",
            note="Deploy et",
        )
        assert payload.note == "Deploy et"

    def test_contract_approval_response_fields_match(
        self, approval_contract: dict[str, object]
    ) -> None:
        """Contract approval_response fields should match ApprovalResponsePayload."""
        resp_msg = _find_message(approval_contract, "approval_response")
        assert resp_msg is not None
        payload_schema = resp_msg.get("payload")
        assert isinstance(payload_schema, dict)

        required = payload_schema.get("required", [])
        assert isinstance(required, list)
        assert "approval_id" in required
        assert "decision" in required

    def test_contract_approval_response_direction(
        self, approval_contract: dict[str, object]
    ) -> None:
        """approval_response messages are client_to_server."""
        resp_msg = _find_message(approval_contract, "approval_response")
        assert resp_msg is not None
        assert resp_msg["direction"] == "client_to_server"


class TestApprovalCategoryMatchesContract:
    """Verify approval categories match the contract enum values."""

    def test_contract_category_values(
        self, approval_contract: dict[str, object]
    ) -> None:
        """Contract category enum should match ApprovalCategory values."""
        question_msg = _find_message(approval_contract, "question")
        assert question_msg is not None
        payload_schema = question_msg.get("payload")
        assert isinstance(payload_schema, dict)
        props = payload_schema.get("properties", {})
        assert isinstance(props, dict)
        category_prop = props.get("category", {})
        assert isinstance(category_prop, dict)
        contract_enum = category_prop.get("enum", [])
        assert isinstance(contract_enum, list)

        for cat_value in contract_enum:
            assert cat_value in [c.value for c in ApprovalCategory], (
                f"Contract category '{cat_value}' not in ApprovalCategory enum"
            )
