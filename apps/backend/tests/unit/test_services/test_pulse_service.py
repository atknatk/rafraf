"""Unit tests for PulseService."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.pulse_service import PulseService


@pytest.fixture
def mock_db() -> AsyncMock:
    """Provide a mock AsyncSession."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def svc() -> PulseService:
    """PulseService örneği."""
    return PulseService()


class TestGetLatestPulseNoData:
    """get_latest_pulse — boş DB durumu."""

    @pytest.mark.asyncio
    async def test_get_latest_pulse_no_data(
        self, svc: PulseService, mock_db: AsyncMock
    ) -> None:
        """Boş DB'de None döndürmeli."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=result_mock)

        result = await svc.get_latest_pulse(mock_db, project_id=None)

        assert result is None
        mock_db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_latest_pulse_with_project_no_data(
        self, svc: PulseService, mock_db: AsyncMock
    ) -> None:
        """Belirli proje için boş DB → None."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=result_mock)

        project_id = str(uuid.uuid4())
        result = await svc.get_latest_pulse(mock_db, project_id=project_id)

        assert result is None


class TestGeneratePulseBasic:
    """generate_pulse — temel iş akışı."""

    @pytest.mark.asyncio
    async def test_generate_pulse_basic(
        self, svc: PulseService, mock_db: AsyncMock
    ) -> None:
        """Mock DB ve mock AI ile pulse oluşturulabilmeli."""
        # DB execute çağrıları: messages + costs
        messages_result = MagicMock()
        messages_result.scalars.return_value.all.return_value = []
        costs_result = MagicMock()
        costs_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[messages_result, costs_result])

        # refresh mock — PulseReport nesnesini döndür
        def fake_refresh(obj: object) -> None:
            from app.models.pulse_report import PulseReport

            if isinstance(obj, PulseReport):
                obj.id = uuid.uuid4()
                obj.created_at = datetime.now(tz=UTC)
                obj.updated_at = datetime.now(tz=UTC)

        mock_db.refresh = AsyncMock(side_effect=fake_refresh)

        user_id = uuid.uuid4()

        with patch.object(
            svc,
            "_generate_ai_summary",
            new=AsyncMock(
                return_value=("Özet metni", ["A tamamlandı"], ["B devam ediyor"], ["Risk 1"], ["Öneri 1"])
            ),
        ):
            pulse = await svc.generate_pulse(mock_db, project_id=None, user_id=user_id, days=1)

        assert pulse is not None
        assert pulse.total_messages == 0
        assert pulse.summary_text == "Özet metni"
        assert pulse.completed_items == ["A tamamlandı"]
        assert pulse.in_progress_items == ["B devam ediyor"]
        assert pulse.risks == ["Risk 1"]
        assert pulse.suggestions == ["Öneri 1"]
        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_generate_pulse_fallback_on_ai_error(
        self, svc: PulseService, mock_db: AsyncMock
    ) -> None:
        """AI hatası durumunda fallback özet kullanılmalı."""
        messages_result = MagicMock()
        messages_result.scalars.return_value.all.return_value = []
        costs_result = MagicMock()
        costs_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[messages_result, costs_result])

        def fake_refresh(obj: object) -> None:
            from app.models.pulse_report import PulseReport

            if isinstance(obj, PulseReport):
                obj.id = uuid.uuid4()
                obj.created_at = datetime.now(tz=UTC)
                obj.updated_at = datetime.now(tz=UTC)

        mock_db.refresh = AsyncMock(side_effect=fake_refresh)

        # AI başarısız — gerçek fallback kullan
        import anthropic

        with patch.object(
            svc._client.messages,
            "create",
            new=AsyncMock(side_effect=anthropic.APIConnectionError(request=MagicMock())),
        ):
            pulse = await svc.generate_pulse(mock_db, project_id=None, days=1)

        # Fallback özet istatistik tabanlı
        assert pulse.summary_text.startswith("Son periyotta")
        assert pulse.risks == []
        assert pulse.suggestions == []

    def test_next_generation_at_returns_iso_string(self) -> None:
        """next_generation_at ISO formatında string döndürmeli."""
        result = PulseService.next_generation_at()
        # Geçerli ISO parse edilebilmeli
        parsed = datetime.fromisoformat(result)
        assert parsed.hour == 8
        assert parsed.minute == 0
