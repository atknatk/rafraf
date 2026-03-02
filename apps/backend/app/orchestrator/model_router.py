"""Model router - selects the appropriate Claude model based on message complexity.

Implements a multi-tier routing system:
- Haiku: Simple tasks (greetings, short answers, status queries)
- Sonnet: Default / medium complexity tasks
- Opus: Complex tasks (multi-step reasoning, code generation, architecture)

Features:
- Complexity scoring algorithm with weighted signals
- User override mechanism (explicit model request)
- Cost tracking per model tier
- Fallback strategy when a model is unavailable
"""

from __future__ import annotations

import re
from enum import StrEnum

import structlog
from pydantic import BaseModel, ConfigDict

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class ModelTier(StrEnum):
    """Available model tiers ordered by capability."""

    HAIKU = "haiku"
    SONNET = "sonnet"
    OPUS = "opus"


# Model identifiers for each tier
MODEL_HAIKU: str = "claude-haiku-4-5-20251001"
MODEL_SONNET: str = "claude-sonnet-4-5-20250929"
MODEL_OPUS: str = "claude-opus-4-5-20250929"

# Mapping from tier to model identifier
_TIER_TO_MODEL: dict[ModelTier, str] = {
    ModelTier.HAIKU: MODEL_HAIKU,
    ModelTier.SONNET: MODEL_SONNET,
    ModelTier.OPUS: MODEL_OPUS,
}

# Fallback chain: if requested tier is unavailable, try the next one
_FALLBACK_CHAIN: dict[ModelTier, list[ModelTier]] = {
    ModelTier.OPUS: [ModelTier.SONNET, ModelTier.HAIKU],
    ModelTier.SONNET: [ModelTier.HAIKU],
    ModelTier.HAIKU: [ModelTier.SONNET],
}

# ----- Complexity scoring configuration -----

# Threshold scores for tier selection
_HAIKU_THRESHOLD: int = 20
_OPUS_THRESHOLD: int = 70
# Score between HAIKU_THRESHOLD and OPUS_THRESHOLD -> Sonnet

# Keywords and their complexity weights
_KEYWORD_SCORES: dict[str, int] = {
    # High complexity -> Opus territory (15-25 points each)
    "mimari": 25,
    "architecture": 25,
    "tasarla": 20,
    "design": 20,
    "refactor": 20,
    "multi-step": 20,
    "cok adimli": 20,
    "kod yaz": 20,
    "code gen": 20,
    "implement": 18,
    "optimize": 18,
    "karsilastir": 15,
    "analiz et": 15,
    "analyze": 15,
    "debug": 15,
    "detayli acikla": 15,
    "explain in detail": 15,
    "plan olustur": 15,
    "create plan": 15,
    "strateji": 15,
    "strategy": 15,
    # Medium complexity -> Sonnet territory (5-14 points each)
    "review": 12,
    "analiz": 10,
    "neden": 10,
    "plan": 10,
    "oner": 10,
    "test sonuc": 10,
    "detayli": 10,
    "incele": 10,
    "acikla": 8,
    "ozetle": 8,
    "summarize": 8,
    "cevir": 5,
    "translate": 5,
    # Low complexity -> Haiku territory (negative points)
    "merhaba": -15,
    "selam": -15,
    "hello": -15,
    "hi": -10,
    "hey": -10,
    "nasilsin": -10,
    "tesekkur": -10,
    "sagol": -10,
    "tamam": -10,
    "evet": -10,
    "hayir": -10,
    "ok": -8,
}

# Simple keywords that push score down
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
    "ping",
    "version",
]

# Score adjustment for simple keywords
_SIMPLE_KEYWORD_SCORE: int = -10

# Override patterns: user explicitly requests a model
_OVERRIDE_PATTERNS: dict[str, ModelTier] = {
    r"\bhaiku\s+kullan\b": ModelTier.HAIKU,
    r"\buse\s+haiku\b": ModelTier.HAIKU,
    r"\bsonnet\s+kullan\b": ModelTier.SONNET,
    r"\buse\s+sonnet\b": ModelTier.SONNET,
    r"\bopus\s+kullan\b": ModelTier.OPUS,
    r"\buse\s+opus\b": ModelTier.OPUS,
    r"\bhizli\s+cevap\b": ModelTier.HAIKU,
    r"\bquick\s+answer\b": ModelTier.HAIKU,
    r"\ben\s+iyi\s+model\b": ModelTier.OPUS,
    r"\bbest\s+model\b": ModelTier.OPUS,
}

# Cost per 1K tokens (approximate USD) for tracking
_COST_PER_1K_INPUT: dict[ModelTier, float] = {
    ModelTier.HAIKU: 0.001,
    ModelTier.SONNET: 0.003,
    ModelTier.OPUS: 0.015,
}

_COST_PER_1K_OUTPUT: dict[ModelTier, float] = {
    ModelTier.HAIKU: 0.005,
    ModelTier.SONNET: 0.015,
    ModelTier.OPUS: 0.075,
}


class ModelRouterResult(BaseModel):
    """Result of model selection with full routing metadata."""

    model_config = ConfigDict(frozen=True)

    model: str
    tier: ModelTier
    reason: str
    complexity_score: int
    is_override: bool = False
    is_fallback: bool = False


class CostEstimate(BaseModel):
    """Estimated cost for a model tier."""

    model_config = ConfigDict(frozen=True)

    tier: ModelTier
    input_cost_per_1k: float
    output_cost_per_1k: float


class CostRecord(BaseModel):
    """Recorded cost for a completed request."""

    model_config = ConfigDict(frozen=True)

    tier: ModelTier
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float


def compute_complexity_score(message: str) -> int:
    """Compute a complexity score for the given message.

    The score is a weighted sum of keyword matches, message length,
    and structural signals (code blocks, question marks, etc.).

    Higher scores indicate more complex messages.

    Args:
        message: User message text.

    Returns:
        Integer complexity score. Typical range: -20 to 100+.
    """
    message_lower = message.lower()
    score = 0

    # 1. Keyword scoring
    for keyword, weight in _KEYWORD_SCORES.items():
        if keyword in message_lower:
            score += weight

    # 2. Simple keyword scoring
    for keyword in _SIMPLE_KEYWORDS:
        if keyword in message_lower:
            score += _SIMPLE_KEYWORD_SCORE

    # 3. Message length signal
    msg_len = len(message)
    if msg_len < 20:
        score -= 10  # Very short -> likely simple
    elif msg_len > 500:
        score += 20  # Very long -> likely very complex
    elif msg_len > 200:
        score += 10  # Long -> likely complex

    # 4. Code block detection (triple backticks)
    code_block_count = message.count("```")
    if code_block_count >= 2:
        score += 15  # Contains code blocks -> complex

    # 5. Multiple question marks -> multi-part question
    question_count = message.count("?")
    if question_count >= 3:
        score += 10
    elif question_count >= 2:
        score += 5

    # 6. Numbered list detection (multi-step task)
    numbered_list_pattern = re.compile(r"^\s*\d+[\.\)]\s+", re.MULTILINE)
    numbered_items = len(numbered_list_pattern.findall(message))
    if numbered_items >= 3:
        score += 15  # Multi-step task
    elif numbered_items >= 2:
        score += 8

    # Clamp score to reasonable range
    return max(-30, min(score, 120))


def _check_override(message: str) -> ModelTier | None:
    """Check if the user explicitly requested a specific model.

    Args:
        message: User message text.

    Returns:
        ModelTier if an override pattern matched, None otherwise.
    """
    message_lower = message.lower()
    for pattern, tier in _OVERRIDE_PATTERNS.items():
        if re.search(pattern, message_lower):
            return tier
    return None


def _tier_from_score(score: int) -> ModelTier:
    """Map a complexity score to a model tier.

    Args:
        score: Complexity score.

    Returns:
        ModelTier based on score thresholds.
    """
    if score < _HAIKU_THRESHOLD:
        return ModelTier.HAIKU
    if score >= _OPUS_THRESHOLD:
        return ModelTier.OPUS
    return ModelTier.SONNET


def get_model_for_tier(
    tier: ModelTier,
    *,
    available_models: set[str] | None = None,
) -> tuple[str, bool]:
    """Get the model identifier for a tier with fallback support.

    If the preferred model is not in available_models, walks the
    fallback chain to find an alternative.

    Args:
        tier: Desired model tier.
        available_models: Set of available model identifiers.
            If None, all models are considered available.

    Returns:
        Tuple of (model_identifier, is_fallback).
    """
    preferred = _TIER_TO_MODEL[tier]

    if available_models is None or preferred in available_models:
        return preferred, False

    # Walk the fallback chain
    for fallback_tier in _FALLBACK_CHAIN[tier]:
        fallback_model = _TIER_TO_MODEL[fallback_tier]
        if fallback_model in available_models:
            return fallback_model, True

    # All fallbacks exhausted — return preferred anyway (let API handle error)
    return preferred, False


def select_model(
    message: str,
    *,
    override_tier: ModelTier | None = None,
    available_models: set[str] | None = None,
) -> ModelRouterResult:
    """Select the appropriate Claude model based on message complexity.

    Routing logic (in priority order):
    1. Explicit override_tier parameter
    2. User override pattern in message text
    3. Complexity score-based tier selection

    Args:
        message: User message text.
        override_tier: Force a specific tier (e.g., from user preference).
        available_models: Set of available model IDs for fallback logic.

    Returns:
        ModelRouterResult with selected model, tier, score, and metadata.
    """
    complexity_score = compute_complexity_score(message)

    # Priority 1: Explicit override_tier parameter
    if override_tier is not None:
        model, is_fallback = get_model_for_tier(override_tier, available_models=available_models)
        return ModelRouterResult(
            model=model,
            tier=override_tier,
            reason=f"explicit_override:{override_tier.value}",
            complexity_score=complexity_score,
            is_override=True,
            is_fallback=is_fallback,
        )

    # Priority 2: User override pattern in message
    user_override = _check_override(message)
    if user_override is not None:
        model, is_fallback = get_model_for_tier(user_override, available_models=available_models)
        return ModelRouterResult(
            model=model,
            tier=user_override,
            reason=f"user_override:{user_override.value}",
            complexity_score=complexity_score,
            is_override=True,
            is_fallback=is_fallback,
        )

    # Priority 3: Complexity score-based selection
    tier = _tier_from_score(complexity_score)
    model, is_fallback = get_model_for_tier(tier, available_models=available_models)

    # Determine reason string
    if tier == ModelTier.HAIKU:
        reason = "complexity_score:simple"
    elif tier == ModelTier.OPUS:
        reason = "complexity_score:complex"
    else:
        reason = "complexity_score:medium"

    return ModelRouterResult(
        model=model,
        tier=tier,
        reason=reason,
        complexity_score=complexity_score,
        is_override=False,
        is_fallback=is_fallback,
    )


def estimate_cost(tier: ModelTier) -> CostEstimate:
    """Get estimated cost per 1K tokens for a model tier.

    Args:
        tier: Model tier.

    Returns:
        CostEstimate with input and output costs.
    """
    return CostEstimate(
        tier=tier,
        input_cost_per_1k=_COST_PER_1K_INPUT[tier],
        output_cost_per_1k=_COST_PER_1K_OUTPUT[tier],
    )


def record_cost(
    *,
    tier: ModelTier,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> CostRecord:
    """Record and calculate the cost for a completed request.

    Args:
        tier: Model tier used.
        model: Model identifier used.
        input_tokens: Number of input tokens consumed.
        output_tokens: Number of output tokens consumed.

    Returns:
        CostRecord with calculated estimated cost.
    """
    input_cost = (input_tokens / 1000) * _COST_PER_1K_INPUT[tier]
    output_cost = (output_tokens / 1000) * _COST_PER_1K_OUTPUT[tier]
    total_cost = round(input_cost + output_cost, 6)

    return CostRecord(
        tier=tier,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=total_cost,
    )
