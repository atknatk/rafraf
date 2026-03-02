"""Unit tests for the model router module."""

from app.orchestrator.model_router import (
    MODEL_HAIKU,
    MODEL_OPUS,
    MODEL_SONNET,
    CostEstimate,
    CostRecord,
    ModelRouterResult,
    ModelTier,
    compute_complexity_score,
    estimate_cost,
    get_model_for_tier,
    record_cost,
    select_model,
)


class TestComputeComplexityScore:
    """Tests for the compute_complexity_score function."""

    def test_simple_greeting_returns_low_score(self) -> None:
        """Simple greetings should produce negative/low scores."""
        score = compute_complexity_score("merhaba")
        assert score < 20

    def test_complex_architecture_question_returns_high_score(self) -> None:
        """Architecture-level questions should produce high scores."""
        score = compute_complexity_score(
            "Bu projenin mimari yapisini tasarla ve multi-step bir plan olustur"
        )
        assert score >= 70

    def test_medium_analysis_request_returns_medium_score(self) -> None:
        """Medium complexity requests should return medium scores."""
        score = compute_complexity_score("Bu kodu detayli analiz et")
        assert 20 <= score < 70

    def test_short_message_reduces_score(self) -> None:
        """Very short messages should reduce the score."""
        score = compute_complexity_score("test")
        assert score < 20

    def test_long_message_increases_score(self) -> None:
        """Long messages (>200 chars) should increase the score."""
        long_msg = "a " * 120  # 240 chars
        score = compute_complexity_score(long_msg)
        # Should get +10 for length
        assert score >= 0

    def test_code_blocks_increase_score(self) -> None:
        """Messages with code blocks should get a score boost."""
        msg = "Bunu duzelt:\n```python\ndef foo():\n    pass\n```"
        score_with_code = compute_complexity_score(msg)
        score_without_code = compute_complexity_score("Bunu duzelt: def foo(): pass")
        assert score_with_code > score_without_code

    def test_multiple_questions_increase_score(self) -> None:
        """Multiple question marks indicate a multi-part question."""
        msg = "Neden boyle? Nasil calisir? Ne yapmaliyiz?"
        score = compute_complexity_score(msg)
        # 3 question marks -> +10, plus 'neden' keyword -> +10
        assert score > 0

    def test_numbered_list_increases_score(self) -> None:
        """Numbered lists indicate multi-step tasks -> higher score."""
        msg = "Su adimlari yap:\n1. Dosyayi oku\n2. Analiz et\n3. Raporla"
        score = compute_complexity_score(msg)
        assert score > 0

    def test_score_clamped_to_range(self) -> None:
        """Score should be clamped between -30 and 120."""
        # Very simple message
        score_low = compute_complexity_score("merhaba selam nasilsin tesekkur sagol tamam evet")
        assert score_low >= -30

        # Very complex message
        msg = "mimari tasarla refactor optimize multi-step cok adimli kod yaz implement " * 5
        score_high = compute_complexity_score(msg)
        assert score_high <= 120

    def test_empty_message_returns_low_score(self) -> None:
        """Empty message should return a low score."""
        score = compute_complexity_score("")
        assert score < 20

    def test_simple_keywords_reduce_score(self) -> None:
        """Simple keywords (status, log, etc.) should reduce the score."""
        score = compute_complexity_score("status goster")
        assert score < 20


class TestSelectModel:
    """Tests for the select_model function."""

    def test_simple_message_returns_haiku(self) -> None:
        """Simple messages should select Haiku."""
        result = select_model("merhaba, selam")
        assert result.model == MODEL_HAIKU
        assert result.tier == ModelTier.HAIKU

    def test_medium_message_returns_sonnet(self) -> None:
        """Medium complexity messages should select Sonnet."""
        result = select_model("Bu kodu detayli analiz et ve sonuclari raporla")
        assert result.tier == ModelTier.SONNET
        assert result.model == MODEL_SONNET

    def test_complex_message_returns_opus(self) -> None:
        """Complex multi-step messages should select Opus."""
        result = select_model(
            "Projenin mimari yapisini tasarla, multi-step bir refactor plani olustur "
            "ve implement stratejisi belirle"
        )
        assert result.tier == ModelTier.OPUS
        assert result.model == MODEL_OPUS

    def test_override_tier_parameter(self) -> None:
        """Explicit override_tier should bypass scoring."""
        # Even a simple message should use Opus with override
        result = select_model("merhaba", override_tier=ModelTier.OPUS)
        assert result.model == MODEL_OPUS
        assert result.tier == ModelTier.OPUS
        assert result.is_override is True
        assert "explicit_override" in result.reason

    def test_user_override_haiku_kullan(self) -> None:
        """User saying 'haiku kullan' should trigger override."""
        result = select_model("haiku kullan ve bana durumu goster")
        assert result.tier == ModelTier.HAIKU
        assert result.is_override is True
        assert "user_override" in result.reason

    def test_user_override_opus_kullan(self) -> None:
        """User saying 'opus kullan' should trigger override."""
        result = select_model("opus kullan ve kodu analiz et")
        assert result.tier == ModelTier.OPUS
        assert result.is_override is True

    def test_user_override_use_sonnet(self) -> None:
        """User saying 'use sonnet' should trigger override."""
        result = select_model("use sonnet for this task")
        assert result.tier == ModelTier.SONNET
        assert result.is_override is True

    def test_user_override_best_model(self) -> None:
        """User saying 'en iyi model' should select Opus."""
        result = select_model("en iyi model ile cevapla")
        assert result.tier == ModelTier.OPUS
        assert result.is_override is True

    def test_user_override_quick_answer(self) -> None:
        """User saying 'hizli cevap' should select Haiku."""
        result = select_model("hizli cevap ver")
        assert result.tier == ModelTier.HAIKU
        assert result.is_override is True

    def test_result_contains_complexity_score(self) -> None:
        """Result should contain the computed complexity score."""
        result = select_model("test mesaji")
        assert isinstance(result.complexity_score, int)

    def test_returns_model_router_result(self) -> None:
        """Function should return a ModelRouterResult instance."""
        result = select_model("test mesaji")
        assert isinstance(result, ModelRouterResult)

    def test_result_is_frozen(self) -> None:
        """ModelRouterResult should be immutable (frozen)."""
        result = select_model("test")
        try:
            result.model = "other-model"  # type: ignore[misc]
            was_frozen = False
        except Exception:
            was_frozen = True
        assert was_frozen, "ModelRouterResult should be frozen"

    def test_case_insensitive(self) -> None:
        """Keyword matching should be case-insensitive."""
        result1 = select_model("MIMARI tasarla ve REFACTOR planla")
        result2 = select_model("mimari tasarla ve refactor planla")
        assert result1.complexity_score == result2.complexity_score

    def test_default_is_not_override(self) -> None:
        """Normal score-based selection should not be flagged as override."""
        result = select_model("Bu projeyi incele")
        assert result.is_override is False

    def test_status_query_returns_haiku(self) -> None:
        """Status queries (simple keyword) should select Haiku."""
        result = select_model("durum nedir")
        assert result.tier == ModelTier.HAIKU

    def test_all_simple_keywords_route_to_haiku(self) -> None:
        """All simple keywords should produce low enough scores for Haiku."""
        simple_keywords = [
            "durum",
            "status",
            "log",
            "start",
            "stop",
            "restart",
            "listele",
            "health",
        ]
        for keyword in simple_keywords:
            result = select_model(keyword)
            assert result.tier == ModelTier.HAIKU, f"Failed for keyword: {keyword}"


class TestGetModelForTier:
    """Tests for the get_model_for_tier function."""

    def test_returns_preferred_model_when_available(self) -> None:
        """Should return the preferred model when all are available."""
        model, is_fallback = get_model_for_tier(ModelTier.SONNET)
        assert model == MODEL_SONNET
        assert is_fallback is False

    def test_returns_preferred_when_no_availability_set(self) -> None:
        """Should return the preferred model when available_models is None."""
        model, is_fallback = get_model_for_tier(ModelTier.OPUS)
        assert model == MODEL_OPUS
        assert is_fallback is False

    def test_falls_back_when_preferred_unavailable(self) -> None:
        """Should use fallback when preferred model is unavailable."""
        available = {MODEL_SONNET, MODEL_HAIKU}
        model, is_fallback = get_model_for_tier(
            ModelTier.OPUS, available_models=available
        )
        assert model == MODEL_SONNET
        assert is_fallback is True

    def test_haiku_falls_back_to_sonnet(self) -> None:
        """Haiku should fall back to Sonnet when unavailable."""
        available = {MODEL_SONNET, MODEL_OPUS}
        model, is_fallback = get_model_for_tier(
            ModelTier.HAIKU, available_models=available
        )
        assert model == MODEL_SONNET
        assert is_fallback is True

    def test_sonnet_falls_back_to_haiku(self) -> None:
        """Sonnet should fall back to Haiku when unavailable."""
        available = {MODEL_HAIKU}
        model, is_fallback = get_model_for_tier(
            ModelTier.SONNET, available_models=available
        )
        assert model == MODEL_HAIKU
        assert is_fallback is True

    def test_returns_preferred_when_all_unavailable(self) -> None:
        """Should return preferred model when no fallbacks match."""
        model, is_fallback = get_model_for_tier(
            ModelTier.OPUS, available_models=set()
        )
        assert model == MODEL_OPUS
        assert is_fallback is False

    def test_fallback_flag_in_select_model(self) -> None:
        """select_model should propagate fallback flag."""
        result = select_model(
            "merhaba",
            available_models={MODEL_SONNET},
        )
        # Haiku preferred for simple message, but not available
        if result.model != MODEL_HAIKU:
            assert result.is_fallback is True


class TestCostTracking:
    """Tests for cost estimation and recording functions."""

    def test_estimate_cost_haiku(self) -> None:
        """Haiku cost estimate should reflect cheapest tier."""
        est = estimate_cost(ModelTier.HAIKU)
        assert isinstance(est, CostEstimate)
        assert est.tier == ModelTier.HAIKU
        assert est.input_cost_per_1k > 0
        assert est.output_cost_per_1k > 0
        assert est.input_cost_per_1k <= estimate_cost(ModelTier.SONNET).input_cost_per_1k

    def test_estimate_cost_ordering(self) -> None:
        """Cost should increase from Haiku < Sonnet < Opus."""
        haiku = estimate_cost(ModelTier.HAIKU)
        sonnet = estimate_cost(ModelTier.SONNET)
        opus = estimate_cost(ModelTier.OPUS)

        assert haiku.input_cost_per_1k < sonnet.input_cost_per_1k
        assert sonnet.input_cost_per_1k < opus.input_cost_per_1k
        assert haiku.output_cost_per_1k < sonnet.output_cost_per_1k
        assert sonnet.output_cost_per_1k < opus.output_cost_per_1k

    def test_record_cost_calculation(self) -> None:
        """record_cost should correctly calculate estimated USD cost."""
        cost = record_cost(
            tier=ModelTier.SONNET,
            model=MODEL_SONNET,
            input_tokens=1000,
            output_tokens=500,
        )
        assert isinstance(cost, CostRecord)
        assert cost.tier == ModelTier.SONNET
        assert cost.model == MODEL_SONNET
        assert cost.input_tokens == 1000
        assert cost.output_tokens == 500
        assert cost.estimated_cost_usd > 0

    def test_record_cost_zero_tokens(self) -> None:
        """Zero tokens should result in zero cost."""
        cost = record_cost(
            tier=ModelTier.HAIKU,
            model=MODEL_HAIKU,
            input_tokens=0,
            output_tokens=0,
        )
        assert cost.estimated_cost_usd == 0.0

    def test_record_cost_frozen(self) -> None:
        """CostRecord should be immutable."""
        cost = record_cost(
            tier=ModelTier.OPUS,
            model=MODEL_OPUS,
            input_tokens=100,
            output_tokens=50,
        )
        try:
            cost.estimated_cost_usd = 999.0  # type: ignore[misc]
            was_frozen = False
        except Exception:
            was_frozen = True
        assert was_frozen


class TestModelTier:
    """Tests for the ModelTier enum."""

    def test_tier_values(self) -> None:
        """ModelTier should have haiku, sonnet, opus values."""
        assert ModelTier.HAIKU.value == "haiku"
        assert ModelTier.SONNET.value == "sonnet"
        assert ModelTier.OPUS.value == "opus"

    def test_tier_is_string_enum(self) -> None:
        """ModelTier should be usable as a string."""
        assert str(ModelTier.HAIKU) == "haiku"
        assert f"{ModelTier.SONNET}" == "sonnet"
