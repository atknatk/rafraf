"""Unit tests for WebSocket message protocol."""

from __future__ import annotations

import json

import pytest

from agent.core.protocol import (
    HeartbeatContent,
    HeartbeatMessage,
    RegisterAckPayload,
    RegisterContent,
    RegisterMessage,
    ResourceMetrics,
    build_heartbeat_message,
    build_register_message,
    parse_register_ack,
    parse_server_message,
)


class TestResourceMetrics:
    """ResourceMetrics model testleri."""

    def test_create_valid(self) -> None:
        """Gecerli metrikler ile olusturulabilir."""
        metrics = ResourceMetrics(
            cpu_usage_percent=45.0,
            memory_usage_percent=60.5,
            disk_usage_percent=30.0,
            disk_free_gb=200.0,
        )
        assert metrics.cpu_usage_percent == 45.0
        assert metrics.memory_usage_percent == 60.5
        assert metrics.disk_usage_percent == 30.0
        assert metrics.disk_free_gb == 200.0

    def test_frozen_model(self) -> None:
        """ResourceMetrics frozen olmali (immutable)."""
        metrics = ResourceMetrics(
            cpu_usage_percent=45.0,
            memory_usage_percent=60.5,
            disk_usage_percent=30.0,
            disk_free_gb=200.0,
        )
        with pytest.raises(Exception):
            metrics.cpu_usage_percent = 99.0  # type: ignore[misc]


class TestRegisterMessage:
    """RegisterMessage model testleri."""

    def test_create_valid(self) -> None:
        """Gecerli register mesaji olusturulabilir."""
        content = RegisterContent(
            host_id="macbook-pro",
            capabilities=["docker", "shell"],
            os_info="Darwin 24.0",
            version="0.1.0",
        )
        msg = RegisterMessage(
            host_id="macbook-pro",
            content=content,
        )
        assert msg.type == "agent_register"
        assert msg.host_id == "macbook-pro"
        assert msg.content.capabilities == ["docker", "shell"]

    def test_frozen(self) -> None:
        """RegisterMessage frozen olmali."""
        content = RegisterContent(
            host_id="test",
            capabilities=[],
            os_info="Test",
            version="0.1.0",
        )
        msg = RegisterMessage(host_id="test", content=content)
        with pytest.raises(Exception):
            msg.host_id = "changed"  # type: ignore[misc]


class TestRegisterAckPayload:
    """RegisterAckPayload model testleri."""

    def test_create_valid(self) -> None:
        """Gecerli register ack payload olusturulabilir."""
        ack = RegisterAckPayload(
            host_id="macbook-pro",
            registered=True,
            server_time="2026-03-02T10:00:00Z",
            heartbeat_interval=30,
        )
        assert ack.registered is True
        assert ack.heartbeat_interval == 30

    def test_frozen(self) -> None:
        """RegisterAckPayload frozen olmali."""
        ack = RegisterAckPayload(
            host_id="test",
            registered=True,
            server_time="2026-03-02T10:00:00Z",
            heartbeat_interval=30,
        )
        with pytest.raises(Exception):
            ack.registered = False  # type: ignore[misc]


class TestHeartbeatMessage:
    """HeartbeatMessage model testleri."""

    def test_create_valid(self, sample_resource_metrics: ResourceMetrics) -> None:
        """Gecerli heartbeat mesaji olusturulabilir."""
        content = HeartbeatContent(
            host_id="macbook-pro",
            status="online",
            uptime_seconds=3600,
            active_tasks=0,
            resources=sample_resource_metrics,
        )
        msg = HeartbeatMessage(
            host_id="macbook-pro",
            content=content,
        )
        assert msg.type == "agent_heartbeat"
        assert msg.content.status == "online"
        assert msg.content.uptime_seconds == 3600


class TestBuildRegisterMessage:
    """build_register_message fonksiyon testleri."""

    def test_returns_valid_json(self) -> None:
        """Gecerli JSON string dondurur."""
        result = build_register_message(
            host_id="test-host",
            capabilities=["docker", "shell"],
            os_info="Darwin 24.0",
            version="0.1.0",
        )
        data = json.loads(result)
        assert data["type"] == "agent_register"
        assert data["host_id"] == "test-host"
        assert data["content"]["capabilities"] == ["docker", "shell"]
        assert data["content"]["os_info"] == "Darwin 24.0"
        assert data["content"]["version"] == "0.1.0"

    def test_empty_capabilities(self) -> None:
        """Bos yetenekler listesi ile calisiyor."""
        result = build_register_message(
            host_id="test",
            capabilities=[],
            os_info="Linux",
            version="0.1.0",
        )
        data = json.loads(result)
        assert data["content"]["capabilities"] == []


class TestBuildHeartbeatMessage:
    """build_heartbeat_message fonksiyon testleri."""

    def test_returns_valid_json(self, sample_resource_metrics: ResourceMetrics) -> None:
        """Gecerli JSON string dondurur."""
        result = build_heartbeat_message(
            host_id="test-host",
            status="online",
            uptime_seconds=120,
            active_tasks=2,
            resources=sample_resource_metrics,
        )
        data = json.loads(result)
        assert data["type"] == "agent_heartbeat"
        assert data["host_id"] == "test-host"
        assert data["content"]["status"] == "online"
        assert data["content"]["uptime_seconds"] == 120
        assert data["content"]["active_tasks"] == 2
        assert data["content"]["resources"]["cpu_usage_percent"] == 25.5

    def test_busy_status(self, sample_resource_metrics: ResourceMetrics) -> None:
        """Busy durum dogru serialize edilir."""
        result = build_heartbeat_message(
            host_id="test",
            status="busy",
            uptime_seconds=60,
            active_tasks=3,
            resources=sample_resource_metrics,
        )
        data = json.loads(result)
        assert data["content"]["status"] == "busy"
        assert data["content"]["active_tasks"] == 3


class TestParseServerMessage:
    """parse_server_message fonksiyon testleri."""

    def test_valid_message(self) -> None:
        """Gecerli mesaj dogru parse edilir."""
        raw = json.dumps({"type": "agent_register_ack", "content": {}})
        data = parse_server_message(raw)
        assert data["type"] == "agent_register_ack"

    def test_invalid_json(self) -> None:
        """Gecersiz JSON ValueError firlatir."""
        with pytest.raises(ValueError, match="Gecersiz JSON"):
            parse_server_message("not-json{")

    def test_missing_type_field(self) -> None:
        """Type alani eksikse ValueError firlatir."""
        raw = json.dumps({"content": "test"})
        with pytest.raises(ValueError, match="'type' alani eksik"):
            parse_server_message(raw)

    def test_preserves_all_fields(self) -> None:
        """Tum alanlar korunur."""
        raw = json.dumps({
            "type": "test",
            "content": {"key": "value"},
            "extra": 42,
        })
        data = parse_server_message(raw)
        assert data["content"]["key"] == "value"
        assert data["extra"] == 42


class TestParseRegisterAck:
    """parse_register_ack fonksiyon testleri."""

    def test_valid_ack(self) -> None:
        """Gecerli register ack parse edilir."""
        data = {
            "type": "agent_register_ack",
            "content": {
                "host_id": "test",
                "registered": True,
                "server_time": "2026-03-02T10:00:00Z",
                "heartbeat_interval": 30,
            },
        }
        ack = parse_register_ack(data)
        assert ack.registered is True
        assert ack.heartbeat_interval == 30

    def test_wrong_type(self) -> None:
        """Yanlis mesaj tipi ValueError firlatir."""
        data = {"type": "agent_heartbeat", "content": {}}
        with pytest.raises(ValueError, match="Beklenen tip"):
            parse_register_ack(data)

    def test_missing_content(self) -> None:
        """Content alani eksikse ValueError firlatir."""
        data = {"type": "agent_register_ack"}
        with pytest.raises(ValueError, match="'content' alani eksik"):
            parse_register_ack(data)

    def test_registration_rejected(self) -> None:
        """Reddedilen kayit dogru parse edilir."""
        data = {
            "type": "agent_register_ack",
            "content": {
                "host_id": "test",
                "registered": False,
                "server_time": "2026-03-02T10:00:00Z",
                "heartbeat_interval": 30,
            },
        }
        ack = parse_register_ack(data)
        assert ack.registered is False
