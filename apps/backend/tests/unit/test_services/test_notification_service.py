"""Unit tests for NotificationService."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.schemas.notifications import (
    NotificationPayload,
    NotificationSettingsUpdateRequest,
    NotificationType,
)
from app.services.notification_service import NotificationService


@pytest.fixture
def mock_session() -> AsyncMock:
    """Provide a mock AsyncSession."""
    return AsyncMock()


@pytest.fixture
def service(mock_session: AsyncMock) -> NotificationService:
    """Provide a NotificationService with mocked session."""
    return NotificationService(mock_session)


class TestRegisterToken:
    """Tests for NotificationService.register_token."""

    @pytest.mark.asyncio
    async def test_register_token_returns_response(
        self, service: NotificationService
    ) -> None:
        """Should return DeviceTokenRegisterResponse on successful upsert."""
        user_id = uuid4()
        now = datetime.now(tz=timezone.utc)
        mock_device_token = MagicMock()
        mock_device_token.id = uuid4()
        mock_device_token.created_at = now

        with patch.object(
            service._token_repo, "upsert", new_callable=AsyncMock
        ) as mock_upsert:
            mock_upsert.return_value = mock_device_token
            result = await service.register_token(
                user_id=user_id,
                token="apns-token-abc",
                platform="ios",
                app_version="1.0",
            )

        assert result.id == mock_device_token.id
        assert result.registered_at == now
        mock_upsert.assert_called_once_with(
            user_id=user_id,
            token="apns-token-abc",
            platform="ios",
            app_version="1.0",
        )


class TestDeactivateToken:
    """Tests for NotificationService.deactivate_token."""

    @pytest.mark.asyncio
    async def test_deactivate_token_calls_repo(
        self, service: NotificationService
    ) -> None:
        """Should call repository deactivate method."""
        user_id = uuid4()

        with patch.object(
            service._token_repo, "deactivate", new_callable=AsyncMock
        ) as mock_deactivate:
            await service.deactivate_token(
                user_id=user_id,
                token="apns-token-abc",
            )

        mock_deactivate.assert_called_once_with(
            user_id=user_id,
            token="apns-token-abc",
        )


class TestGetSettings:
    """Tests for NotificationService.get_settings."""

    @pytest.mark.asyncio
    async def test_get_settings_returns_current_prefs(
        self, service: NotificationService
    ) -> None:
        """Should return NotificationSettingsResponse with current values."""
        user_id = uuid4()
        mock_settings = MagicMock()
        mock_settings.task_complete_enabled = True
        mock_settings.approval_needed_enabled = False
        mock_settings.error_enabled = True
        mock_settings.info_enabled = True

        with patch.object(
            service._settings_repo, "get_or_create", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = mock_settings
            result = await service.get_settings(user_id=user_id)

        assert result.task_complete_enabled is True
        assert result.approval_needed_enabled is False
        assert result.error_enabled is True
        assert result.info_enabled is True


class TestUpdateSettings:
    """Tests for NotificationService.update_settings."""

    @pytest.mark.asyncio
    async def test_update_settings_partial(
        self, service: NotificationService
    ) -> None:
        """Should partially update notification settings."""
        user_id = uuid4()
        mock_settings = MagicMock()
        mock_settings.task_complete_enabled = False
        mock_settings.approval_needed_enabled = True
        mock_settings.error_enabled = True
        mock_settings.info_enabled = True

        with patch.object(
            service._settings_repo, "update_settings", new_callable=AsyncMock
        ) as mock_update:
            mock_update.return_value = mock_settings
            payload = NotificationSettingsUpdateRequest(
                task_complete_enabled=False,
            )
            result = await service.update_settings(
                user_id=user_id,
                payload=payload,
            )

        assert result.task_complete_enabled is False
        assert result.approval_needed_enabled is True


class TestSendNotification:
    """Tests for NotificationService.send_notification."""

    @pytest.mark.asyncio
    async def test_send_notification_skips_disabled_category(
        self, service: NotificationService
    ) -> None:
        """Should skip sending if category is disabled."""
        user_id = uuid4()
        mock_settings = MagicMock()
        mock_settings.task_complete_enabled = False

        with (
            patch.object(
                service._settings_repo, "get_or_create", new_callable=AsyncMock
            ) as mock_get,
            patch.object(
                service._token_repo, "get_active_tokens", new_callable=AsyncMock
            ) as mock_tokens,
        ):
            mock_get.return_value = mock_settings
            notification = NotificationPayload(
                notification_id=uuid4(),
                type=NotificationType.task_complete,
                title="Done",
                body="Task completed.",
            )
            result = await service.send_notification(user_id, notification)

        assert result is False
        mock_tokens.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_notification_skips_no_tokens(
        self, service: NotificationService
    ) -> None:
        """Should return False when user has no active tokens."""
        user_id = uuid4()
        mock_settings = MagicMock()
        mock_settings.info_enabled = True

        with (
            patch.object(
                service._settings_repo, "get_or_create", new_callable=AsyncMock
            ) as mock_get,
            patch.object(
                service._token_repo,
                "get_active_tokens",
                new_callable=AsyncMock,
            ) as mock_tokens,
        ):
            mock_get.return_value = mock_settings
            mock_tokens.return_value = []
            notification = NotificationPayload(
                notification_id=uuid4(),
                type=NotificationType.info,
                title="Info",
                body="Just info.",
            )
            result = await service.send_notification(user_id, notification)

        assert result is False

    @pytest.mark.asyncio
    async def test_send_notification_dispatches_to_active_tokens(
        self, service: NotificationService
    ) -> None:
        """Should dispatch to all active device tokens."""
        user_id = uuid4()
        mock_settings = MagicMock()
        mock_settings.error_enabled = True
        mock_token = MagicMock()
        mock_token.token = "token-abc-12345678"

        with (
            patch.object(
                service._settings_repo, "get_or_create", new_callable=AsyncMock
            ) as mock_get,
            patch.object(
                service._token_repo,
                "get_active_tokens",
                new_callable=AsyncMock,
            ) as mock_tokens,
        ):
            mock_get.return_value = mock_settings
            mock_tokens.return_value = [mock_token]
            notification = NotificationPayload(
                notification_id=uuid4(),
                type=NotificationType.error,
                title="Error",
                body="Something went wrong.",
            )
            result = await service.send_notification(user_id, notification)

        assert result is True
