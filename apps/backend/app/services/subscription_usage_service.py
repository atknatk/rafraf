"""Subscription usage tracking service.

Reads ~/.claude/stats-cache.json and tracks claude -p invocations
to provide subscription usage data for iOS agent detail views.
"""

from __future__ import annotations

import asyncio
import json
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


def _messages_today_key() -> str:
    return f"subscription:messages_today:{date.today().isoformat()}"


class SubscriptionUsageService:
    """Tracks Claude Max subscription usage."""

    async def refresh(self) -> SubscriptionUsageResponse:
        """Refresh usage data from stats-cache + auth status and cache in Redis."""
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

        response = SubscriptionUsageResponse(
            subscription_type=auth_info.get("subscriptionType") or "api_key",
            email=auth_info.get("email"),
            org_name=auth_info.get("orgName"),
            today_usage=today_usage,
            recent_days=recent[-7:],
            total_messages_today=total_today,
            is_rate_limited=is_rate_limited,
            rate_limit_reset_at=reset_at,
            last_fetched_at=now,
        )

        # Cache in Redis
        await redis_client.set_cache(
            _CACHE_KEY,
            response.model_dump_json(),
            ttl=_CACHE_TTL,
        )

        logger.info(
            "subscription_usage_refreshed",
            subscription_type=response.subscription_type,
            today_messages=today_usage.message_count,
            claude_p_messages=total_today,
            is_rate_limited=is_rate_limited,
        )

        return response

    async def get_usage(self) -> SubscriptionUsageResponse:
        """Get cached usage data, refreshing if needed."""
        cached = await redis_client.get_cache(_CACHE_KEY)
        if cached:
            return SubscriptionUsageResponse.model_validate_json(cached)
        return await self.refresh()

    async def record_message(self) -> None:
        """Increment today's claude -p message counter."""
        client = await redis_client._get_client()
        key = _messages_today_key()
        await client.incr(key)
        await client.expire(key, 172800)  # 48h TTL

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
