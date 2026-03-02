"""Model router - selects the appropriate Claude model based on message complexity."""

import structlog
from pydantic import BaseModel, ConfigDict

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# Keywords that indicate a complex task requiring Sonnet
_COMPLEX_KEYWORDS: list[str] = [
    "review",
    "analiz",
    "neden",
    "debug",
    "plan",
    "oner",
    "test sonuc",
    "karsilastir",
    "detayli",
    "incele",
    "acikla",
    "mimari",
    "refactor",
    "optimize",
]

# Keywords that indicate a simple task suitable for Haiku
_SIMPLE_KEYWORDS: list[str] = [
    "durum",
    "status",
    "log",
    "start",
    "stop",
    "restart",
    "list",
    "listele",
    "kac",
    "ne zaman",
    "uptime",
    "saglik",
    "health",
]

# Default model names
MODEL_SONNET: str = "claude-sonnet-4-5-20250929"
MODEL_HAIKU: str = "claude-haiku-4-5-20251001"


class ModelRouterResult(BaseModel):
    """Result of model selection."""

    model_config = ConfigDict(frozen=True)

    model: str
    reason: str


def select_model(
    message: str,
    *,
    default_model: str = MODEL_SONNET,
    simple_model: str = MODEL_HAIKU,
) -> ModelRouterResult:
    """Select the appropriate model based on message content.

    Uses keyword-based heuristics to determine complexity:
    - Complex keywords -> Sonnet (deeper reasoning)
    - Simple keywords -> Haiku (fast, cheap)
    - Default -> Sonnet (safe fallback)

    Args:
        message: User message text.
        default_model: Model to use for complex/default tasks.
        simple_model: Model to use for simple tasks.

    Returns:
        ModelRouterResult with selected model and reason.
    """
    message_lower = message.lower()

    # Check for complex keywords first (higher priority)
    for keyword in _COMPLEX_KEYWORDS:
        if keyword in message_lower:
            return ModelRouterResult(
                model=default_model,
                reason=f"complex_keyword:{keyword}",
            )

    # Check for simple keywords
    for keyword in _SIMPLE_KEYWORDS:
        if keyword in message_lower:
            return ModelRouterResult(
                model=simple_model,
                reason=f"simple_keyword:{keyword}",
            )

    # Default: use the more capable model
    return ModelRouterResult(
        model=default_model,
        reason="default_fallback",
    )
