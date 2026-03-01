# RafRaf -- Swift / iOS Standards

Applies to: `apps/ios/`

## Runtime

- Swift 6 / iOS 17+ / Xcode 16+ minimum
- SwiftUI-first, UIKit only when SwiftUI cannot achieve the UX.

## Architecture

### Clean Architecture Layers

```text
Presentation  -->  Domain  -->  Data
(Views, VMs)      (Use Cases)   (Repositories, Network)
```

- Views call ViewModels.
- ViewModels call Use Cases / Services.
- Services call Repositories / Network layer.

### Observation

- Use `@Observable` (Observation framework, iOS 17).
- Do **not** use `@ObservableObject` / `@Published` (legacy Combine pattern).

### Dependency Injection

- Factory library ile DI. `DependencyContainer` yerine `Factory` kutuphanesi kullan.
- No singletons except the DI container itself.

## Naming Conventions

### RF* Prefix

All project types use the `RF` prefix to avoid collisions:

| Type       | Pattern              | Example              |
|------------|----------------------|----------------------|
| View       | `RF*View`            | `RFChatView`         |
| ViewModel  | `RF*ViewModel`       | `RFChatViewModel`    |
| Service    | `RF*Service`         | `RFWebSocketService` |
| Model      | `RF*Model`           | `RFProjectModel`     |
| Error      | `RFError`            | `RFError.networkFail`|
| UI Element | `RF*`                | `RFButton`, `RFCard` |

### File Naming

- One primary type per file.
- File name matches the primary type: `RFChatView.swift`.

## Safety Rules

- **No force unwrap** (`!`) except in `#Preview` blocks and tests.
- **No implicitly unwrapped optionals** (`var x: T!`).
- Use `guard let` / `if let` for optional handling.
- Prefer `async throws` over completion handlers.

## Localisation

- All user-facing strings must use `String(localized:)`.
- Key format: `"feature.screen.element"` (e.g., `"chat.input.placeholder"`).

## Previews

- Every View must have a `#Preview` block.
- Preview should use mock data, not live services.

## Concurrency

- Use Swift Concurrency (`async/await`, `Task`, `AsyncStream`).
- Mark `@MainActor` on ViewModels and any UI-mutating code.
- No `DispatchQueue.main.async` — use `@MainActor` instead.

## Testing

- Framework: Swift Testing (`@Test`, `#expect`). XCTest sadece UI testleri icin. Coverage target: >= 70%.
- Mock external dependencies with protocols.
- Snapshot tests for critical UI components (swift-snapshot-testing).
