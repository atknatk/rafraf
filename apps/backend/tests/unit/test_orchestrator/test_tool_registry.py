"""Unit tests for the tool registry module."""

from app.orchestrator.tool_registry import ToolDefinition, ToolRegistry


async def _dummy_handler(params: dict[str, object]) -> str:
    """Dummy tool handler for testing."""
    return "dummy_result"


async def _another_handler(params: dict[str, object]) -> str:
    """Another dummy tool handler for testing."""
    return "another_result"


def _make_definition(
    name: str = "test_tool",
    *,
    requires_approval: bool = False,
    approval_category: str | None = None,
) -> ToolDefinition:
    """Create a ToolDefinition for testing."""
    return ToolDefinition(
        name=name,
        description=f"Test tool: {name}",
        input_schema={
            "type": "object",
            "properties": {
                "action": {"type": "string"},
            },
        },
        requires_approval=requires_approval,
        approval_category=approval_category,
    )


class TestToolRegistry:
    """Tests for the ToolRegistry class."""

    def test_register_tool(self) -> None:
        """Registering a tool should make it available."""
        registry = ToolRegistry()
        definition = _make_definition("my_tool")
        registry.register(definition, _dummy_handler)

        assert registry.has_tool("my_tool")
        assert registry.tool_count == 1

    def test_unregister_tool(self) -> None:
        """Unregistering a tool should remove it."""
        registry = ToolRegistry()
        definition = _make_definition("my_tool")
        registry.register(definition, _dummy_handler)

        result = registry.unregister("my_tool")
        assert result is True
        assert not registry.has_tool("my_tool")
        assert registry.tool_count == 0

    def test_unregister_nonexistent_tool(self) -> None:
        """Unregistering a nonexistent tool should return False."""
        registry = ToolRegistry()
        result = registry.unregister("nonexistent")
        assert result is False

    def test_get_definition(self) -> None:
        """Getting a definition should return the registered definition."""
        registry = ToolRegistry()
        definition = _make_definition("my_tool")
        registry.register(definition, _dummy_handler)

        retrieved = registry.get_definition("my_tool")
        assert retrieved is not None
        assert retrieved.name == "my_tool"

    def test_get_definition_nonexistent(self) -> None:
        """Getting a nonexistent definition should return None."""
        registry = ToolRegistry()
        assert registry.get_definition("nonexistent") is None

    def test_get_handler(self) -> None:
        """Getting a handler should return the registered handler."""
        registry = ToolRegistry()
        definition = _make_definition("my_tool")
        registry.register(definition, _dummy_handler)

        handler = registry.get_handler("my_tool")
        assert handler is _dummy_handler

    def test_get_handler_nonexistent(self) -> None:
        """Getting a nonexistent handler should return None."""
        registry = ToolRegistry()
        assert registry.get_handler("nonexistent") is None

    def test_has_tool(self) -> None:
        """has_tool should return True for registered tools."""
        registry = ToolRegistry()
        definition = _make_definition("my_tool")
        registry.register(definition, _dummy_handler)

        assert registry.has_tool("my_tool")
        assert not registry.has_tool("other_tool")

    def test_list_tools(self) -> None:
        """list_tools should return all registered definitions."""
        registry = ToolRegistry()
        registry.register(_make_definition("tool_a"), _dummy_handler)
        registry.register(_make_definition("tool_b"), _another_handler)

        tools = registry.list_tools()
        assert len(tools) == 2
        names = {t.name for t in tools}
        assert names == {"tool_a", "tool_b"}

    def test_get_tools_for_api(self) -> None:
        """get_tools_for_api should return dicts in Claude API format."""
        registry = ToolRegistry()
        registry.register(_make_definition("my_tool"), _dummy_handler)

        api_tools = registry.get_tools_for_api()
        assert len(api_tools) == 1
        assert api_tools[0]["name"] == "my_tool"
        assert "description" in api_tools[0]
        assert "input_schema" in api_tools[0]

    def test_requires_approval_false(self) -> None:
        """Non-approval tools should return False."""
        registry = ToolRegistry()
        registry.register(_make_definition("safe_tool"), _dummy_handler)
        assert registry.requires_approval("safe_tool") is False

    def test_requires_approval_true(self) -> None:
        """Approval-required tools should return True."""
        registry = ToolRegistry()
        definition = _make_definition(
            "danger_tool",
            requires_approval=True,
            approval_category="deploy",
        )
        registry.register(definition, _dummy_handler)
        assert registry.requires_approval("danger_tool") is True

    def test_requires_approval_nonexistent(self) -> None:
        """Nonexistent tools should return False for requires_approval."""
        registry = ToolRegistry()
        assert registry.requires_approval("nonexistent") is False

    def test_tool_count(self) -> None:
        """tool_count should track the number of registered tools."""
        registry = ToolRegistry()
        assert registry.tool_count == 0

        registry.register(_make_definition("a"), _dummy_handler)
        assert registry.tool_count == 1

        registry.register(_make_definition("b"), _another_handler)
        assert registry.tool_count == 2

        registry.unregister("a")
        assert registry.tool_count == 1

    def test_register_overwrites_existing(self) -> None:
        """Registering a tool with the same name should overwrite."""
        registry = ToolRegistry()
        registry.register(_make_definition("my_tool"), _dummy_handler)
        registry.register(_make_definition("my_tool"), _another_handler)

        assert registry.tool_count == 1
        assert registry.get_handler("my_tool") is _another_handler

    def test_definition_is_frozen(self) -> None:
        """ToolDefinition should be immutable."""
        definition = _make_definition("frozen_tool")
        try:
            definition.name = "changed"  # type: ignore[misc]
            was_frozen = False
        except Exception:
            was_frozen = True
        assert was_frozen, "ToolDefinition should be frozen"
