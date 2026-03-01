# RafRaf -- Python Standards (Backend + Agent)

Applies to: `apps/backend/`, `apps/agent/`

## Runtime

- Python >= 3.12
- Async-first (`asyncio`, `async def`, `await`)

## Linting & Formatting

### Ruff

Ruff is the single tool for linting and formatting.

```toml
[tool.ruff]
target-version = "py312"
line-length = 99
```

Enabled rule sets: E, W, F, I, N, UP, B, S, A, C4, DTZ, T20, RUF.

Run: `ruff check . && ruff format --check .`

### MyPy (strict mode)

```toml
[tool.mypy]
python_version = "3.12"
strict = true
disallow_untyped_defs = true
disallow_any_generics = true
```

- No `Any` type in public signatures.
- `pydantic.mypy` plugin zorunlu — `pyproject.toml`'de `plugins = ["pydantic.mypy"]` ekle.

## Pydantic v2

- All data models inherit from `pydantic.BaseModel`.
- Use `model_validator` / `field_validator` (not legacy v1 validators).
- `frozen=True` sadece domain/entity modelleri icin. Request/Response DTO'lari ve Settings siniflari frozen OLMAZ.
- Config via `pydantic-settings` with `.env` loading.

## Async Patterns

- Database: `sqlalchemy[asyncio]` + `asyncpg`.
- HTTP client: `httpx.AsyncClient` — tum HTTP istekleri icin tercih edilen client.
- WebSocket: `fastapi.WebSocket` (backend) / `websockets` (agent).
- Never call blocking I/O from the event loop; use `asyncio.to_thread()` if needed.

## Structured Logging

```python
import structlog

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),  # dev ortaminda
        # structlog.processors.JSONRenderer(),  # production'da
    ],
)

logger = structlog.get_logger()
logger.info("task_started", task_id=task_id, project=project_name)
```

- JSON format in production (`JSONRenderer`), console format in development (`ConsoleRenderer`).
- Always bind contextual fields (`request_id`, `session_id`, `user_id`).

## Docstrings

- All public modules, classes, and functions must have docstrings.
- Use imperative mood: "Return the project by ID." (not "Returns").

## Import Order

Enforced by Ruff (isort):

1. `__future__`
2. Standard library
3. Third-party
4. First-party (`app.*` or `agent.*`)

## Testing

- Framework: `pytest` + `pytest-asyncio`.
- Async tests: `asyncio_mode = "auto"` in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- Test dizin yapisi:

```text
tests/
  unit/            # Birim testleri (network/db/filesystem erisimi YOK)
  integration/     # Entegrasyon testleri (@pytest.mark.integration)
  conftest.py      # Paylasilmis fixture'lar
  fakes/           # Fake implementasyonlari
  fixtures/        # Statik test verisi (JSON, YAML)
```

- Coverage: backend >= 80%, agent >= 80%.
- Mocks: only for external APIs (Claude, GitHub, S3, Deepgram).
- Integration testlerini `@pytest.mark.integration` ile isaretleyin.

## Ortam Kurulumu

```bash
python -m venv .venv && source .venv/bin/activate
```

- Bagimliliklar `pyproject.toml` veya `requirements.txt` ile yonetilir.
- Her uygulamanin (`apps/backend/`, `apps/agent/`) kendi `pyproject.toml` dosyasi vardir.
