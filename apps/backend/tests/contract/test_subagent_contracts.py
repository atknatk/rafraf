"""API contract tests for the subagent REST hydration endpoint (V1.x Item 9).

Validates that the backend ``SubagentResponse`` schema matches the
contract in ``shared/api-contracts/rest/v1/subagents.json``. Mirrors the
``test_agent_contracts.py`` pattern + the ``test_approval_contracts.py``
pattern: a real DTO is built and round-tripped through the JSON Schema
``Draft202012Validator`` so a future drive-by edit on either side
(backend Pydantic model OR contract JSON) breaks this test loudly.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.subagents import SubagentResponse
from app.services.subagent_service import _to_response

_REPO_ROOT = Path(__file__).resolve().parents[4]
REST_CONTRACT = _REPO_ROOT / "shared" / "api-contracts" / "rest" / "v1" / "subagents.json"


def _load_contract() -> dict[str, object]:
    with open(REST_CONTRACT) as f:
        return json.load(f)  # type: ignore[no-any-return]


def _subagent_endpoint(contract: dict[str, object]) -> dict[str, object]:
    """Resolve the single GET endpoint declared in the contract."""
    endpoints = contract["endpoints"]
    assert isinstance(endpoints, list)
    assert len(endpoints) == 1, "subagents.json should declare exactly one endpoint today"
    ep = endpoints[0]
    assert isinstance(ep, dict)
    return ep


def _item_schema(contract: dict[str, object]) -> dict[str, object]:
    """Resolve the JSON Schema for one array item in the response."""
    ep = _subagent_endpoint(contract)
    body = ep["responseBody"]
    assert isinstance(body, dict)
    items = body["items"]
    assert isinstance(items, dict)
    return items


# ---------------------------------------------------------------------------
# Endpoint registration
# ---------------------------------------------------------------------------


class TestEndpointRegistration:
    """Verify the route declared in the contract is mounted on the app."""

    def test_subagents_endpoint_registered(self) -> None:
        """GET /api/v1/sessions/{session_id}/subagents should be registered."""
        from app.main import app

        paths_with_methods = {
            (r.path, frozenset(r.methods or [])) for r in app.routes if hasattr(r, "methods")
        }
        assert ("/api/v1/sessions/{session_id}/subagents", frozenset({"GET"})) in paths_with_methods


# ---------------------------------------------------------------------------
# Schema field-set parity (model ↔ contract)
# ---------------------------------------------------------------------------


class TestModelMatchesContract:
    """Pin every contract field to a Pydantic model field (and vice versa)."""

    def test_required_fields_present_on_model(self) -> None:
        """Every ``required`` field in the contract must exist on SubagentResponse."""
        contract = _load_contract()
        item = _item_schema(contract)
        required = item.get("required", [])
        assert isinstance(required, list)

        model_fields = set(SubagentResponse.model_fields.keys())
        for field in required:
            assert field in model_fields, (
                f"Contract requires '{field}' but SubagentResponse does not declare it"
            )

    def test_all_contract_properties_match_model_fields(self) -> None:
        """Every contract property must map 1:1 to a Pydantic field name."""
        contract = _load_contract()
        item = _item_schema(contract)
        props = item.get("properties", {})
        assert isinstance(props, dict)

        model_fields = set(SubagentResponse.model_fields.keys())
        contract_fields = set(props.keys())
        assert contract_fields == model_fields, (
            "Contract / model field-set drift detected. "
            f"Contract-only: {sorted(contract_fields - model_fields)}; "
            f"Model-only: {sorted(model_fields - contract_fields)}"
        )

    def test_id_field_is_string_not_uuid(self) -> None:
        """``id`` MUST be a string (bridge task_id), not the SQL UUID.

        Reviewer-flagged contract bug: iOS keys its in-memory cache by
        ``Subagent.id`` which is the bridge ``task_id``. If the contract
        ever drifts back to UUID, REST hydration will produce duplicate
        rows on the next live WS update. This test pins the contract.
        """
        contract = _load_contract()
        item = _item_schema(contract)
        props = item["properties"]
        assert isinstance(props, dict)
        id_prop = props["id"]
        assert isinstance(id_prop, dict)
        assert id_prop["type"] == "string", "id MUST be string (bridge task_id), not UUID"

        # And the Pydantic field type must agree.
        id_field = SubagentResponse.model_fields["id"]
        # ``annotation`` is the runtime type; ``str`` here, NOT UUID.
        assert id_field.annotation is str

    def test_db_id_is_separate_uuid_field(self) -> None:
        """The SQL primary key must live on a SEPARATE ``db_id`` field."""
        contract = _load_contract()
        item = _item_schema(contract)
        props = item["properties"]
        assert isinstance(props, dict)
        assert "db_id" in props, "Contract must expose db_id as a separate uuid field"
        db_id_prop = props["db_id"]
        assert isinstance(db_id_prop, dict)
        assert db_id_prop["type"] == "string"
        assert db_id_prop["format"] == "uuid"

    def test_summary_key_is_summary_not_output_summary(self) -> None:
        """Reviewer-flagged: iOS decodes ``summary``, not ``output_summary``."""
        contract = _load_contract()
        item = _item_schema(contract)
        props = item["properties"]
        assert isinstance(props, dict)
        assert "summary" in props, "Contract must use 'summary' (not 'output_summary')"
        assert "output_summary" not in props, (
            "'output_summary' would silently lose completion summaries on iOS"
        )
        assert "summary" in SubagentResponse.model_fields
        assert "output_summary" not in SubagentResponse.model_fields

    def test_ios_decoded_fields_all_present(self) -> None:
        """Every field iOS ``SubagentRestDTO`` decodes must exist in the contract.

        The list mirrors
        ``apps/ios/RafRaf/Features/Agent/Data/Repositories/SubagentRepositoryImpl.swift``
        (struct ``SubagentRestDTO``). Snake-cased to match the JSON wire
        names — iOS auto-converts to camelCase via NetworkClient.
        """
        contract = _load_contract()
        item = _item_schema(contract)
        props = item.get("properties", {})
        assert isinstance(props, dict)

        ios_decoded_fields = {
            "id",
            "parent_id",
            "session_id",
            "status",
            "name",
            "description",
            "prompt_preview",
            "subagent_type",
            "isolation",
            "summary",
            "total_tokens",
            "tool_uses",
            "duration_ms",
            "activity",
            "started_at",
            "completed_at",
            "updated_at",
            "progress_percent",
        }

        missing = ios_decoded_fields - set(props.keys())
        assert not missing, (
            f"Contract is missing fields iOS already decodes: {sorted(missing)}. "
            "Adding them later requires a coordinated iOS release; ship them now."
        )


# ---------------------------------------------------------------------------
# Round-trip: built DTO satisfies the JSON Schema
# ---------------------------------------------------------------------------


class _StubSubagent:
    """Minimal stand-in for the ``Subagent`` ORM row.

    Bypasses the SQLAlchemy session/instrumentation so the contract test
    runs without a database. Uses simple attribute storage; mypy is
    relaxed via the type-ignore inside ``_to_response`` since we deliberately
    don't depend on the real ORM here.
    """

    def __init__(
        self,
        *,
        row_id: uuid.UUID,
        bridge_id: uuid.UUID,
        session_id: str,
        task_id: str,
        spawned_at: datetime,
        parent_session_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        prompt_preview: str | None = None,
        subagent_type: str | None = None,
        isolation: str | None = None,
        status: str = "spawned",
        summary: str | None = None,
        total_tokens: int | None = None,
        tool_uses: int | None = None,
        duration_ms: int | None = None,
        updated_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> None:
        # Set the SQL primary-key column on the stub. ``id`` is the actual
        # ORM attribute name; ``row_id`` is the constructor-arg alias used
        # to avoid shadowing the Python builtin ``id`` (ruff A002).
        self.id = row_id
        self.bridge_id = bridge_id
        self.session_id = session_id
        self.task_id = task_id
        self.spawned_at = spawned_at
        self.parent_session_id = parent_session_id
        self.name = name
        self.description = description
        self.prompt_preview = prompt_preview
        self.subagent_type = subagent_type
        self.isolation = isolation
        self.status = status
        self.summary = summary
        self.total_tokens = total_tokens
        self.tool_uses = tool_uses
        self.duration_ms = duration_ms
        self.updated_at = updated_at
        self.completed_at = completed_at


class TestRoundTripAgainstSchema:
    """Build DTOs via ``_to_response`` and validate them with jsonschema."""

    def test_in_flight_row_matches_schema(self) -> None:
        """A spawned (in-flight) row serialises to a contract-valid object."""
        contract = _load_contract()
        item_schema = _item_schema(contract)
        validator = Draft202012Validator(item_schema)

        spawned = datetime.now(tz=UTC)
        row = _StubSubagent(
            row_id=uuid.uuid4(),
            bridge_id=uuid.uuid4(),
            session_id="sess-contract-spawned",
            task_id="task-101",
            spawned_at=spawned,
            name="developer",
            description="implement the thing",
            prompt_preview="Please do...",
            subagent_type="general-purpose",
            isolation="worktree",
            status="spawned",
        )

        dto = _to_response(row)  # type: ignore[arg-type]
        # Pydantic JSON-mode dump produces the wire shape (str timestamps,
        # str UUIDs) — exactly what the JSON Schema expects.
        wire = dto.model_dump(mode="json")

        errors = sorted(validator.iter_errors(wire), key=lambda e: e.path)
        assert not errors, "Schema violations: " + "; ".join(
            f"{list(e.path)}: {e.message}" for e in errors
        )

        # Contract-critical assertions.
        assert wire["id"] == "task-101", "id must carry bridge task_id, not SQL UUID"
        assert wire["db_id"] == str(row.id)
        assert "summary" in wire
        assert "output_summary" not in wire

    def test_terminal_row_matches_schema(self) -> None:
        """A completed row with terminal payload also satisfies the schema."""
        contract = _load_contract()
        item_schema = _item_schema(contract)
        validator = Draft202012Validator(item_schema)

        spawned = datetime.now(tz=UTC)
        completed = spawned + timedelta(seconds=42)
        row = _StubSubagent(
            row_id=uuid.uuid4(),
            bridge_id=uuid.uuid4(),
            session_id="sess-contract-completed",
            task_id="task-202",
            spawned_at=spawned,
            parent_session_id="parent-sess-1",
            status="completed",
            summary="all green",
            total_tokens=12345,
            tool_uses=7,
            duration_ms=42_000,
            completed_at=completed,
            updated_at=completed,
        )

        dto = _to_response(row)  # type: ignore[arg-type]
        wire = dto.model_dump(mode="json")

        errors = sorted(validator.iter_errors(wire), key=lambda e: e.path)
        assert not errors, "Schema violations: " + "; ".join(
            f"{list(e.path)}: {e.message}" for e in errors
        )
        assert wire["summary"] == "all green"
        assert wire["total_tokens"] == 12345
        assert wire["completed_at"] is not None

    def test_unknown_status_is_coerced_to_failed_not_spawned(self) -> None:
        """Reviewer-flagged: silent fallback to 'spawned' masked corruption.

        ``_coerce_status`` now maps unknowns to ``"failed"`` (conservative,
        surfaces anomalies) AND emits ``subagent_status_coerced`` warning.
        Pinning the behaviour here so a drive-by revert breaks loudly.
        """
        import structlog.testing

        row = _StubSubagent(
            row_id=uuid.uuid4(),
            bridge_id=uuid.uuid4(),
            session_id="sess-unknown",
            task_id="task-unknown",
            spawned_at=datetime.now(tz=UTC),
            status="running",  # NOT in the SubagentStatusLiteral enum.
        )

        with structlog.testing.capture_logs() as captured:
            dto = _to_response(row)  # type: ignore[arg-type]

        assert dto.status == "failed", (
            "Unknown statuses must NOT be silently coerced to 'spawned' "
            "(would mask a genuinely-finished or in-flight task as fresh work)."
        )
        coerce_logs = [e for e in captured if e.get("event") == "subagent_status_coerced"]
        assert len(coerce_logs) == 1
        evt = coerce_logs[0]
        assert evt["log_level"] == "warning"
        assert evt["raw_status"] == "running"
        assert evt["coerced_to"] == "failed"
        assert evt["session_id"] == "sess-unknown"
        assert evt["task_id"] == "task-unknown"


# ---------------------------------------------------------------------------
# Smoke: contract loads cleanly + AsyncSession import unused warning silenced
# ---------------------------------------------------------------------------


class TestContractFileShape:
    """The contract JSON itself must be well-formed."""

    def test_contract_has_one_endpoint(self) -> None:
        contract = _load_contract()
        assert "endpoints" in contract
        endpoints = contract["endpoints"]
        assert isinstance(endpoints, list)
        assert len(endpoints) >= 1

    def test_contract_endpoint_path_and_method(self) -> None:
        ep = _subagent_endpoint(_load_contract())
        assert ep["path"] == "/api/v1/sessions/{session_id}/subagents"
        assert ep["method"] == "GET"


# Silence the unused-import warning from AsyncSession (kept for future
# tests that touch the real session). Trivial pin; removed once the import
# is genuinely consumed.
_ = AsyncSession


# Pytest marker so the test runner doesn't accidentally collect a stub
# class as a TestCase. ``pytest.skip`` here is a no-op at collection time.
del pytest
