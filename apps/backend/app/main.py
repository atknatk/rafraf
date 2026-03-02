"""RafRaf Backend - FastAPI WebSocket server + AI orchestrator."""

from fastapi import FastAPI

app = FastAPI(
    title="RafRaf Backend",
    description="AI Project Supervisor - Backend API",
    version="0.1.0",
)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Saglik kontrolu endpoint'i."""
    return {"status": "ok"}
