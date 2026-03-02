"""Tool registry - manages tool definitions and dispatch for Claude API."""

from collections.abc import Awaitable, Callable

import structlog
from pydantic import BaseModel, ConfigDict

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# Type alias for tool handler functions
ToolHandler = Callable[[dict[str, object]], Awaitable[str]]


class ToolDefinition(BaseModel):
    """Definition of a tool available to Claude."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    input_schema: dict[str, object]
    requires_approval: bool = False
    approval_category: str | None = None


class ToolRegistry:
    """Registry for managing tools available to the AI orchestrator.

    Supports dynamic registration and removal of tools. Each tool
    has a definition (for Claude API) and a handler function (for execution).
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, definition: ToolDefinition, handler: ToolHandler) -> None:
        """Register a tool with its definition and handler.

        Args:
            definition: Tool definition for Claude API.
            handler: Async function to execute when tool is called.
        """
        self._tools[definition.name] = definition
        self._handlers[definition.name] = handler

    def unregister(self, tool_name: str) -> bool:
        """Remove a tool from the registry.

        Args:
            tool_name: Name of the tool to remove.

        Returns:
            True if tool was removed, False if not found.
        """
        if tool_name in self._tools:
            del self._tools[tool_name]
            del self._handlers[tool_name]
            return True
        return False

    def get_definition(self, tool_name: str) -> ToolDefinition | None:
        """Get a tool definition by name.

        Args:
            tool_name: Name of the tool.

        Returns:
            ToolDefinition if found, None otherwise.
        """
        return self._tools.get(tool_name)

    def get_handler(self, tool_name: str) -> ToolHandler | None:
        """Get a tool handler by name.

        Args:
            tool_name: Name of the tool.

        Returns:
            Handler function if found, None otherwise.
        """
        return self._handlers.get(tool_name)

    def has_tool(self, tool_name: str) -> bool:
        """Check if a tool is registered.

        Args:
            tool_name: Name of the tool.

        Returns:
            True if tool is registered.
        """
        return tool_name in self._tools

    def list_tools(self) -> list[ToolDefinition]:
        """Return all registered tool definitions.

        Returns:
            List of all registered ToolDefinitions.
        """
        return list(self._tools.values())

    def get_tools_for_api(self) -> list[dict[str, object]]:
        """Return tool definitions formatted for the Claude API.

        Returns:
            List of dicts in Claude API tool format.
        """
        api_tools: list[dict[str, object]] = []
        for tool in self._tools.values():
            api_tools.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                }
            )
        return api_tools

    def requires_approval(self, tool_name: str) -> bool:
        """Check if a tool requires user approval before execution.

        Args:
            tool_name: Name of the tool.

        Returns:
            True if approval is required.
        """
        tool = self._tools.get(tool_name)
        if tool is None:
            return False
        return tool.requires_approval

    @property
    def tool_count(self) -> int:
        """Return the number of registered tools."""
        return len(self._tools)
