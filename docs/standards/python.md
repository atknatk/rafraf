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
- Use `pydantic.mypy` plugin for model validation.

## Pydantic v2

- All data models inherit from `pydantic.BaseModel`.
- Use `model_validator` / `field_validator` (not legacy v1 validators).
- Config via `pydantic-settings` with `.env` loading.

## Async Patterns

- Database: `sqlalchemy[asyncio]` + `asyncpg`.
- HTTP client: `httpx.AsyncClient`.
- WebSocket: `fastapi.WebSocket` (backend) / `websockets` (agent).
- Never call blocking I/O from the event loop; use `asyncio.to_thread()` if needed.

## Structured Logging

```python
import structlog
logger = structlog.get_logger()

logger.info("task_started", task_id=task_id, project=project_name)
```

- JSON format in production.
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
- Async tests: `asyncio_mode = "auto"` in pyproject.toml.
- Coverage: backend >= 80%, agent >= 80%.
- Mocks: only for external APIs (Claude, GitHub, S3, Deepgram).
