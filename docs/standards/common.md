# RafRaf -- Cross-Layer Standards

## Naming Conventions

### Architecture Layer Prefixes

| Layer       | Prefix / Pattern         | Example                    |
|-------------|--------------------------|----------------------------|
| API         | `router`, `endpoint`     | `health_router`            |
| Service     | `*_service`              | `stt_service`              |
| Model       | PascalCase noun          | `ProjectSession`           |
| Tool        | `*_tool`                 | `github_tool`              |
| Orchestrator| descriptive noun         | `model_router`             |
| Agent       | `*_runner`, `*_handler`  | `docker_runner`            |
| iOS View    | `RF*View`                | `RFChatView`               |
| iOS VM      | `RF*ViewModel`           | `RFChatViewModel`          |
| iOS Service | `RF*Service`             | `RFWebSocketService`       |

### File Naming

- Python: `snake_case.py`
- Swift: `PascalCase.swift`
- YAML/JSON configs: `kebab-case.yaml`

### Branch Naming

```
feature/f<faz>/<issue-no>-<slug>
```

Ornekler:

```
feature/f1/7-ws-handler
feature/f1/42-chat-ekrani-websocket-baglantisi
feature/f2/15-sesli-komut-entegrasyonu
```

**Slug olusturma kurallari**:

- Kucuk harf
- Bosluk -> tire
- Turkce karakter -> ASCII (c->c, g->g, i->i, o->o, s->s, u->u, C->c, G->g, I->i, O->o, S->s, U->u)
- Ozel karakter kaldir
- Max 40 karakter

### Commit Messages

```
<type>(<scope>): <description> [agent:<agent-name>]

- Detail 1
- Detail 2

Refs: #<issue-no>
```

Ornek:

```
feat(backend): add websocket auth handler [agent:developer]

- JWT token validation middleware
- Connection lifecycle management

Refs: #42
```

Scopes: `backend`, `ios`, `agent`, `infra`, `docs`, `shared`.

## Import Order

### Python

1. Standard library
2. Third-party packages
3. Local application imports

Enforced by `ruff` (isort rules).

### Swift

1. Foundation / SwiftUI
2. Third-party frameworks
3. Project modules (RF*)

## Error Handling

### Python

- Use explicit exception types; never bare `except`.
- All public functions must document raised exceptions in docstrings.
- Return structured error payloads over WebSocket (see docs/02).

### Swift

- Prefer `Result<T, Error>` or `async throws`.
- Never force-unwrap (`!`) outside of `#Preview` and tests.
- Map errors to user-facing `RFError` enum.

## Logging

- Python: `structlog` with JSON output in production.
- Swift: `os.Logger` with subsystem `com.rafraf`.
- Always include `request_id` / `session_id` in log context.

## Configuration

- All secrets via environment variables (never committed).
- Feature flags as env vars with sensible defaults.
- YAML for agent-local config; Pydantic Settings for backend.
