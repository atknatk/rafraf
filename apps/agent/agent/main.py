"""RafRaf Host Agent - Python asyncio daemon entry point."""

import asyncio

import structlog

logger = structlog.get_logger()


async def main() -> None:
    """Agent daemon baslatma noktasi."""
    await logger.ainfo("RafRaf Host Agent baslatiliyor...")


if __name__ == "__main__":
    asyncio.run(main())
