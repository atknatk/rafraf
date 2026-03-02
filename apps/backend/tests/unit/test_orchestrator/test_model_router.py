"""Unit tests for the model router module."""

from app.orchestrator.model_router import (
    MODEL_HAIKU,
    MODEL_SONNET,
    ModelRouterResult,
    select_model,
)


class TestSelectModel:
    """Tests for the select_model function."""

    def test_complex_keyword_returns_sonnet(self) -> None:
        """Complex keywords should select the Sonnet model."""
        result = select_model("Bu kodu analiz et")
        assert result.model == MODEL_SONNET
        assert "complex_keyword" in result.reason

    def test_simple_keyword_returns_haiku(self) -> None:
        """Simple keywords should select the Haiku model."""
        result = select_model("Proje durumunu goster")
        assert result.model == MODEL_HAIKU
        assert "simple_keyword" in result.reason

    def test_default_returns_sonnet(self) -> None:
        """Messages without matching keywords should default to Sonnet."""
        result = select_model("Merhaba, nasilsin?")
        assert result.model == MODEL_SONNET
        assert result.reason == "default_fallback"

    def test_complex_keywords_all_match(self) -> None:
        """All complex keywords should be recognized."""
        complex_keywords = [
            "review", "analiz", "neden", "debug", "plan",
            "oner", "test sonuc", "karsilastir", "detayli",
            "incele", "acikla", "mimari", "refactor", "optimize",
        ]
        for keyword in complex_keywords:
            result = select_model(f"Lutfen {keyword} yap")
            assert result.model == MODEL_SONNET, f"Failed for keyword: {keyword}"

    def test_simple_keywords_all_match(self) -> None:
        """All simple keywords should be recognized."""
        simple_keywords = [
            "durum", "status", "log", "start", "stop",
            "restart", "list", "listele", "kac", "ne zaman",
            "uptime", "saglik", "health",
        ]
        for keyword in simple_keywords:
            result = select_model(f"Proje {keyword}")
            assert result.model == MODEL_HAIKU, f"Failed for keyword: {keyword}"

    def test_case_insensitive(self) -> None:
        """Keyword matching should be case-insensitive."""
        result = select_model("Bu kodu ANALIZ et")
        assert result.model == MODEL_SONNET

    def test_complex_overrides_simple(self) -> None:
        """Complex keywords should take priority over simple keywords."""
        result = select_model("Projenin durumunu detayli analiz et")
        assert result.model == MODEL_SONNET
        assert "complex_keyword" in result.reason

    def test_custom_models(self) -> None:
        """Custom model names should be used when provided."""
        result = select_model(
            "log goster",
            default_model="custom-sonnet",
            simple_model="custom-haiku",
        )
        assert result.model == "custom-haiku"

    def test_returns_model_router_result(self) -> None:
        """Function should return a ModelRouterResult instance."""
        result = select_model("test mesaji")
        assert isinstance(result, ModelRouterResult)

    def test_empty_message_returns_default(self) -> None:
        """Empty message should return default model."""
        result = select_model("")
        assert result.model == MODEL_SONNET
        assert result.reason == "default_fallback"

    def test_result_is_frozen(self) -> None:
        """ModelRouterResult should be immutable (frozen)."""
        result = select_model("test")
        try:
            result.model = "other-model"  # type: ignore[misc]
            was_frozen = False
        except Exception:
            was_frozen = True
        assert was_frozen, "ModelRouterResult should be frozen"
