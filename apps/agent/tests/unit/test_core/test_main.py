"""Unit tests for agent main module."""

from __future__ import annotations

from agent.main import _configure_structlog


class TestConfigureStructlog:
    """structlog yapilandirma testleri."""

    def test_configure_structlog_runs_without_error(self) -> None:
        """structlog yapilandirmasi hata vermeden calisir."""
        _configure_structlog()

    def test_configure_structlog_idempotent(self) -> None:
        """structlog yapilandirmasi birden fazla kez cagrilabilir."""
        _configure_structlog()
        _configure_structlog()
