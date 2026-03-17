"""Subscription usage tracking service.

Reads ~/.claude/stats-cache.json and tracks claude -p invocations
to provide subscription usage data for iOS agent detail views.
%80 kullanim esigi gecildiginde push notification gonderir.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import structlog

from app.core.config import get_settings
from app.core.redis import redis_client
from app.schemas.subscription import DailyUsageStats, SubscriptionUsageResponse

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# Redis keys
_CACHE_KEY = "subscription:usage_cache"
_CACHE_TTL = 900  # 15 minutes
_RATE_LIMIT_KEY = "subscription:rate_limited"
_RATE_LIMIT_TTL = 1800  # 30 minutes
_WARNING_SENT_KEY = "subscription:warning_sent"
_LIMIT_SENT_KEY = "subscription:limit_sent"


def _messages_today_key() -> str:
    return f"subscription:messages_today:{date.today().isoformat()}"


def _warning_sent_today_key() -> str:
    return f"{_WARNING_SENT_KEY}:{date.today().isoformat()}"


def _limit_sent_today_key() -> str:
    return f"{_LIMIT_SENT_KEY}:{date.today().isoformat()}"


class SubscriptionUsageService:
    """Tracks Claude Max subscription usage."""

    async def refresh(self) -> SubscriptionUsageResponse:
        """Refresh usage data from stats-cache + auth status and cache in Redis."""
        settings = get_settings()
        now = datetime.now(tz=UTC).isoformat()

        auth_info = await self._run_auth_status()
        stats = self._read_stats_cache()
        today_str = date.today().isoformat()

        # Find today's stats from cache
        today_usage = DailyUsageStats(date=today_str)
        recent: list[DailyUsageStats] = []
        for entry in stats:
            if entry["date"] == today_str:
                today_usage = DailyUsageStats(
                    date=entry["date"],
                    message_count=entry.get("messageCount", 0),
                    session_count=entry.get("sessionCount", 0),
                    tool_call_count=entry.get("toolCallCount", 0),
                )
            recent.append(
                DailyUsageStats(
                    date=entry["date"],
                    message_count=entry.get("messageCount", 0),
                    session_count=entry.get("sessionCount", 0),
                    tool_call_count=entry.get("toolCallCount", 0),
                )
            )

        # Get our own claude -p message counter
        total_today = await self._get_message_count_today()

        # Check rate limit status
        is_rate_limited, reset_at = await self._get_rate_limit_status()

        # Calculate usage percentage against daily limit
        daily_limit = settings.subscription_daily_message_limit
        threshold = settings.subscription_warning_threshold
        total_messages = today_usage.message_count + total_today
        usage_pct = min((total_messages / daily_limit * 100) if daily_limit > 0 else 0.0, 100.0)
        warning_reached = usage_pct >= (threshold * 100) and not is_rate_limited
        limit_exceeded = total_messages >= daily_limit

        response = SubscriptionUsageResponse(
            subscription_type=auth_info.get("subscriptionType") or "api_key",
            email=auth_info.get("email"),
            org_name=auth_info.get("orgName"),
            today_usage=today_usage,
            recent_days=recent[-7:],
            total_messages_today=total_today,
            is_rate_limited=is_rate_limited,
            rate_limit_reset_at=reset_at,
            usage_percent=round(usage_pct, 1),
            daily_message_limit=daily_limit,
            warning_threshold_reached=warning_reached,
            limit_exceeded=limit_exceeded,
            last_fetched_at=now,
        )

        # Cache in Redis
        await redis_client.set_cache(
            _CACHE_KEY,
            response.model_dump_json(),
            ttl=_CACHE_TTL,
        )

        # Send push notifications for threshold breaches
        await self._check_and_notify(usage_pct, threshold, limit_exceeded, total_messages, daily_limit)

        logger.info(
            "subscription_usage_refreshed",
            subscription_type=response.subscription_type,
            today_messages=today_usage.message_count,
            claude_p_messages=total_today,
            is_rate_limited=is_rate_limited,
            usage_percent=round(usage_pct, 1),
            warning_reached=warning_reached,
        )

        return response

    async def get_usage(self) -> SubscriptionUsageResponse:
        """Get cached usage data, refreshing if needed."""
        cached = await redis_client.get_cache(_CACHE_KEY)
        if cached:
            return SubscriptionUsageResponse.model_validate_json(cached)
        return await self.refresh()

    async def record_message(self) -> None:
        """Increment today's claude -p message counter and check threshold."""
        client = await redis_client._get_client()
        key = _messages_today_key()
        new_count = await client.incr(key)
        await client.expire(key, 172800)  # 48h TTL

        # Quick threshold check on every message
        settings = get_settings()
        daily_limit = settings.subscription_daily_message_limit
        threshold = settings.subscription_warning_threshold
        if daily_limit > 0:
            usage_pct = new_count / daily_limit * 100
            limit_exceeded = new_count >= daily_limit
            await self._check_and_notify(
                usage_pct, threshold, limit_exceeded, new_count, daily_limit
            )

    async def record_rate_limit(self, reset_at: str | None = None) -> None:
        """Record a rate limit event."""
        value = json.dumps(
            {
                "detected_at": datetime.now(tz=UTC).isoformat(),
                "reset_at": reset_at,
            }
        )
        await redis_client.set_cache(_RATE_LIMIT_KEY, value, ttl=_RATE_LIMIT_TTL)
        logger.warning(
            "subscription_rate_limit_detected",
            reset_at=reset_at,
        )

    # --- Private helpers ---

    async def _get_message_count_today(self) -> int:
        """Get today's claude -p message count from Redis."""
        raw = await redis_client.get_cache(_messages_today_key())
        if raw is None:
            return 0
        try:
            return int(raw)
        except ValueError:
            return 0

    async def _get_rate_limit_status(self) -> tuple[bool, str | None]:
        """Check if currently rate limited."""
        raw = await redis_client.get_cache(_RATE_LIMIT_KEY)
        if raw is None:
            return False, None
        try:
            data = json.loads(raw)
            return True, data.get("reset_at")
        except (json.JSONDecodeError, TypeError):
            return True, None

    async def _check_and_notify(
        self,
        usage_pct: float,
        threshold: float,
        limit_exceeded: bool,
        total_messages: int,
        daily_limit: int,
    ) -> None:
        """Send push notification when usage crosses warning threshold or limit."""
        try:
            # Check limit exceeded (100%)
            if limit_exceeded:
                already_sent = await redis_client.get_cache(_limit_sent_today_key())
                if not already_sent:
                    await self._send_usage_alert(
                        title="Günlük limit aşıldı",
                        body=f"Bugün {total_messages}/{daily_limit} mesaj kullanıldı. Rate limit riski!",
                        alert_type="limit_exceeded",
                    )
                    await redis_client.set_cache(_limit_sent_today_key(), "1", ttl=86400)
                return

            # Check warning threshold (80%)
            if usage_pct >= threshold * 100:
                already_sent = await redis_client.get_cache(_warning_sent_today_key())
                if not already_sent:
                    pct_display = int(threshold * 100)
                    await self._send_usage_alert(
                        title=f"Kullanım %{pct_display} eşiğini geçti",
                        body=f"Bugün {total_messages}/{daily_limit} mesaj ({usage_pct:.0f}%). Yavaşlamayı düşün.",
                        alert_type="warning_threshold",
                    )
                    await redis_client.set_cache(_warning_sent_today_key(), "1", ttl=86400)
        except Exception:
            logger.warning("usage_alert_notification_failed", exc_info=True)

    async def _send_usage_alert(
        self,
        title: str,
        body: str,
        alert_type: str,
    ) -> None:
        """Send usage alert push notification to all users with active tokens."""
        from app.core.database import async_session_factory
        from app.repositories.device_token_repo import DeviceTokenRepository
        from app.schemas.notifications import NotificationPayload, NotificationType
        from app.services.notification_service import NotificationService

        sent_to = 0
        async with async_session_factory() as session:
            token_repo = DeviceTokenRepository(session)
            user_ids = await token_repo.get_all_user_ids_with_tokens()

            payload = NotificationPayload(
                notification_id=uuid.uuid4(),
                type=NotificationType.info,
                title=title,
                body=body,
                metadata={"alert_type": alert_type, "category": "usage_alert"},
            )

            svc = NotificationService(session)
            for user_id in user_ids:
                await svc.send_notification(user_id=user_id, notification=payload)

            sent_to = len(user_ids)
            await session.commit()

        logger.info(
            "usage_alert_sent",
            alert_type=alert_type,
            title=title,
            user_count=sent_to,
        )

    def _read_stats_cache(self) -> list[dict[str, object]]:
        """Read ~/.claude/stats-cache.json daily activity."""
        stats_path = Path.home() / ".claude" / "stats-cache.json"
        if not stats_path.exists():
            return []
        try:
            data = json.loads(stats_path.read_text(encoding="utf-8"))
            activity: list[dict[str, object]] = data.get("dailyActivity", [])
            return activity
        except (json.JSONDecodeError, OSError):
            logger.warning("stats_cache_read_failed", path=str(stats_path))
            return []

    async def _run_auth_status(self) -> dict[str, str]:
        """Run `claude auth status --json` and parse output."""
        settings = get_settings()
        binary = settings.claude_code_binary

        try:
            # Remove CLAUDECODE env var to avoid nested session check
            import os

            # CLAUDECODE ve ANTHROPIC_API_KEY kaldirilir:
            # CLAUDECODE → nested session hatasini onler
            # ANTHROPIC_API_KEY → API key modunu devre disi birakir, gercek subscriptionType'i gosterir
            env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "ANTHROPIC_API_KEY")}

            proc = await asyncio.create_subprocess_exec(
                binary,
                "auth",
                "status",
                "--json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            if proc.returncode == 0 and stdout:
                result: dict[str, str] = json.loads(stdout.decode("utf-8", errors="replace"))
                return result
        except (TimeoutError, json.JSONDecodeError, FileNotFoundError, OSError):
            logger.warning("claude_auth_status_failed")

        return {"subscriptionType": "unknown"}


# Module-level singleton
subscription_usage_service = SubscriptionUsageService()
