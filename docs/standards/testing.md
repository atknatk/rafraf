# RafRaf -- Testing Standards

## Coverage Requirements

| Layer   | Target | Tool                             |
|---------|--------|----------------------------------|
| Backend | >= 80% | pytest-cov                       |
| iOS     | >= 70% | Swift Testing + XCTest (UI only) |
| Agent   | >= 80% | pytest-cov                       |

Coverage is enforced in CI. PRs that drop coverage below the threshold are blocked.

## Test Categories

### Unit Tests

- Test a single function or class in isolation.
- No network, database, or filesystem access. Suite should run in < 30 seconds.

### Integration Tests

- Test interaction between two or more modules (e.g., API + DB).
- May use Docker containers (PostgreSQL, Redis) via `docker-compose.dev.yml`.
- Python: `@pytest.mark.integration` ile isaretleyin. CI'da ayri step olarak calistirilir.
- iOS: Dedicated test plan (Xcode).

### End-to-End Tests

- Full flow: iOS app --> Backend --> Agent --> Backend --> iOS app.
- Run via Maestro (mobile) and Playwright (web dashboard, if applicable).
- Triggered manually or nightly in CI.

## Mock Rules

### What to Mock

- External APIs: Claude, GitHub, Deepgram, OpenAI, S3, APNs.
- System clock (`datetime.now`, `Date.now`).

### What NOT to Mock

- Internal modules — test them with real implementations.
- Pydantic models — let validation run.
- Database in integration tests — use a real test database.

## Fake Pattern

For services with side effects, provide a `Fake*` implementation:

```python
# app/services/notification.py
class NotificationService(Protocol):
    async def send(self, device_token: str, payload: dict) -> None: ...

# tests/fakes/fake_notification.py
class FakeNotificationService:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict]] = []

    async def send(self, device_token: str, payload: dict) -> None:
        self.sent.append((device_token, payload))
```

Swift equivalent uses protocol + mock conformance.

## Test File Organisation

### Python

```text
tests/
  conftest.py          # shared fixtures
  unit/                # birim testleri (network/db/fs erisimi YOK)
    test_<module>.py   # mirrors app/<module>.py
  integration/         # entegrasyon testleri (@pytest.mark.integration)
    test_<module>.py
  fakes/               # fake implementations
  fixtures/            # static test data (JSON, YAML)
```

### Swift

```text
RafRafTests/
  Features/
    <Feature>/
      Data/
        <Feature>RepositoryTests.swift
      Domain/
        <Feature>UseCaseTests.swift
      Presentation/
        <Feature>ViewModelTests.swift
  Mocks/
    Mock<Protocol>.swift
  Snapshots/
    <Feature>SnapshotTests.swift   # swift-snapshot-testing
```

## Running Tests

```bash
# Backend
cd apps/backend && pytest --cov=app --cov-report=term-missing

# Agent
cd apps/agent && pytest --cov=agent --cov-report=term-missing

# iOS
xcodebuild test \
  -scheme RafRaf \
  -destination 'platform=iOS Simulator,name=iPhone 16' \
  -enableCodeCoverage YES

# iOS coverage extraction
xcrun xccov view --report --only-targets <result-bundle-path>
```
