"""Base tool interface for cloud tools."""

from abc import ABC, abstractmethod

import structlog

from app.orchestrator.tool_registry import ToolDefinition, ToolRegistry

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class BaseTool(ABC):
    """Abstract base class for all cloud tools.

    Each tool must implement:
    - get_definition(): returns Claude API tool schema
    - execute(): processes tool calls from Claude
    """

    @abstractmethod
    def get_definition(self) -> ToolDefinition:
        """Return the tool definition for Claude API registration.

        Returns:
            ToolDefinition with name, description, input_schema.
        """

    @abstractmethod
    async def execute(self, params: dict[str, object]) -> str:
        """Execute the tool with given parameters.

        Args:
            params: Tool input parameters from Claude.

        Returns:
            String result to send back to Claude.
        """

    def register(self, registry: ToolRegistry) -> None:
        """Register this tool in the given registry.

        Args:
            registry: ToolRegistry to register with.
        """
        definition = self.get_definition()
        registry.register(definition, self.execute)
