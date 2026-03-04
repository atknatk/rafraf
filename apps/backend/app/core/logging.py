"""Structured logging configuration using structlog."""

import logging
import sys
from io import TextIOBase
from pathlib import Path
from typing import IO

import structlog


class TeeFile(TextIOBase):
    """File-like object that writes to multiple targets simultaneously."""

    def __init__(self, *files: IO[str]) -> None:
        self._files = files

    def write(self, data: str) -> int:  # type: ignore[override]
        for f in self._files:
            f.write(data)
            f.flush()
        return len(data)

    def flush(self) -> None:
        for f in self._files:
            f.flush()


def setup_logging(*, debug: bool = False) -> None:
    """Configure structlog for the application."""
    log_level = logging.DEBUG if debug else logging.INFO

    # Log dosyasi olustur
    log_dir = Path(__file__).resolve().parent.parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = (log_dir / "backend.log").open("a")  # noqa: SIM115

    # stdout + dosyaya ayni anda yaz
    tee = TeeFile(sys.stdout, log_file)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            (structlog.dev.ConsoleRenderer() if debug else structlog.processors.JSONRenderer()),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=tee),
        cache_logger_on_first_use=True,
    )
