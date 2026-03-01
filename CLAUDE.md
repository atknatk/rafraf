# RafRaf - AI Project Supervisor

> AI-driven proje yonetim sistemi - sesli ve metin tabanli arayuz

## Project Identity

- **Proje**: RafRaf - AI Project Supervisor
- **Katmanlar**: Backend (FastAPI) + iOS (SwiftUI) + Host Agent (Python daemon)
- **Backend**: FastAPI + Python 3.12 + Claude Agent SDK + WebSocket
- **iOS**: SwiftUI + iOS 17+ + Clean Architecture + Swift 6 + Xcode 16+
- **Agent**: Python 3.12 + asyncio daemon + Docker/Playwright/Maestro
- **Database**: PostgreSQL 16 + pgvector + Redis 7
- **Memory**: mem0 (3-katmanli hafiza sistemi)
- **Altyapi**: AWS EKS, S3, CloudWatch
- **Dis Servisler**: Claude API, Deepgram STT, OpenAI TTS, GitHub API

## Repo Yapisi

```
rafraf/
├── apps/backend/          # FastAPI WebSocket server + AI orchestrator
├── apps/ios/              # SwiftUI iOS app (Clean Architecture)
├── apps/agent/            # Python host agent daemon
├── shared/                # API contracts + feature specs
├── docs/                  # System specs (01-08) + standards + pipeline
├── infra/                 # Docker, K8s configs
├── scripts/               # Automation
└── .claude/               # Agent pipeline configuration
```

## Mimari

### Backend (FastAPI)
- Async WebSocket server (iOS client + Host Agent)
- Claude Agent SDK ile AI reasoning + tool calling
- Host-aware tool dispatch (dogru makineye yonlendirme)
- mem0 ile 3-katmanli hafiza (conversation, project, personal)
- PostgreSQL veri, Redis cache/session

### iOS (Clean Architecture)
Uc katmanli mimari, her feature icin:
1. **Data Layer**: DTO'lar, repository implementasyonlari, mapper'lar
2. **Domain Layer**: Model'ler, repository protocol'leri, use case'ler
3. **Presentation Layer**: SwiftUI view'lar, ViewModel'ler, UI state

Design System: `RF*` bilesenler (RFButton, RFCard, vb.) — feature view'larda raw SwiftUI YASAK.

### Host Agent
Mac/Ubuntu uzerinde calisan Python daemon. Backend'e WSS ile baglanir.
Runner'lar: Docker, Playwright, Maestro, Shell (guvenlik filtreleri ile).

## Temel Kurallar (Tum Agent'lar)

1. **`Any` tipi YASAK** — domain/presentation (iOS), service katmanlari (Python) icin type hint zorunlu
2. **Force unwrap YASAK** — `#Preview` ve test bloklari haric
3. **Immutable modeller** — frozen Pydantic domain/entity modelleri (Python), struct (Swift)
4. **Domain layer izolasyonu** (iOS) — data/ veya presentation/'dan import YASAK
5. **RF* bilesen zorunlu** — iOS feature ekranlarinda sadece RF* componentler
6. **Tum iOS stringleri localized** — `String(localized:)`
7. **Her iOS ekranin `#Preview`'u olmali**
8. **Async native** — Python'da `async def`, Swift'te `async/await`
9. **Structured logging** — structlog (Python), os.Logger (Swift)
10. **Guvenlik oncelikli** — onay matrisi (`docs/07_Security_Permissions_Cost_Analysis.md`), shell whitelist/blacklist (`docs/08_Host_Agent_Specification.md`)

## Kodlama Standartlari

### Python (Backend + Agent)
- Ruff linter + formatter
- MyPy strict mode
- Pydantic v2 tum modeller
- SQLAlchemy 2.0+ async (asyncpg)
- Import sirasi: stdlib -> 3rd party -> local
- `any` YASAK, tum fonksiyonlar typed

### Swift (iOS)
- SwiftLint
- Clean Architecture: Data/ -> Domain/ -> Presentation/
- `@Observable` + `@MainActor` ViewModel pattern
- Factory-based DI (Factory library)
- Factory library ile dependency injection
- URLSession WebSocket (native, 3rd party yok)
- Nuke for async image loading
- iOS 17+ minimum
- Xcode 16+ minimum
- Test framework: Swift Testing (`@Test`, `#expect`), XCTest sadece UI testleri icin

## Git Workflow

- **Branch**: `feature/f<faz>/<issue-no>-<slug>` (ornek: `feature/f1/7-ws-handler`)
- **Commit**: `<type>(<scope>): <aciklama> [agent:<agent-adi>]`
  - Body: detay satirlari
  - Footer: `Refs: #<issue-no>`
- **Types**: feat, fix, refactor, test, docs, infra, chore
- **Scopes**: backend, ios, agent, infra, docs, shared
- **PR -> develop**: Squash merge
- **develop -> main**: Merge commit (releases)

## AI Pipeline

### Agent Rolleri (4 rol)

| Agent | Model | Gorev |
|-------|-------|-------|
| **architect** | Opus | Feature spec + API kontrat + dosya sahipligi |
| **developer** | Opus | Kod implementasyonu (backend/ios/agent) |
| **tester** | Sonnet | Test yazma + CI dogrulama |
| **reviewer** | Opus | Kod review + kalite gate |

### Pipeline Tipleri

| Pipeline | Adimlar | Ne Zaman |
|----------|---------|----------|
| **full** | Architect -> Developer -> Tester -> Reviewer | Major feature |
| **standard** | Developer -> Tester | Medium feature |
| **quick** | Developer | Infra, config, kucuk is |

### Temel Kurallar
- **Worktree izolasyonu**: Her issue kendi git worktree'sinde calisir
- **Auto-merge**: `agent:pipeline` etiketli PR'lar CI gectikten sonra squash merge
- **Source of truth**: GitHub Issues (label + body + state)
- **Durum takibi**: `status:ready`, `status:in-progress`, `status:blocked`, `status:review`, `status:merged`

## Komutlar

```bash
# Backend
cd apps/backend && python -m uvicorn app.main:app --reload
cd apps/backend && python -m pytest --cov=app
cd apps/backend && ruff check app/ && mypy app/

# iOS
cd apps/ios && xcodebuild build -scheme RafRaf
cd apps/ios && xcodebuild test -scheme RafRaf

# Agent
cd apps/agent && python -m agent.main
cd apps/agent && python -m pytest --cov=agent

# Dev ortam
docker compose -f infra/docker/docker-compose.dev.yml up -d
```

## Onemli Dosya Konumlari

- `CLAUDE.md` — Bu dosya
- `docs/01-08 (01_System_Architecture_Overview.md ... 08_Host_Agent_Specification.md)` — Sistem spesifikasyon dokumanlari
- `docs/standards/` — Platform bazli kodlama standartlari
- `docs/pipeline/` — Agent handoff dosyalari
- `shared/api-contracts/` — WebSocket + REST API semalari
- `shared/feature-specs/` — Architect feature spesifikasyonlari
- `scripts/feature-queue.jsonl` — Faz sirali feature kuyrugu
- `.claude/agents/` — Agent tanimlari (4 agent)
- `.claude/skills/` — Pipeline skill'leri (5 skill)

## Gerekli Ortam Degiskenleri

- `DATABASE_URL` — PostgreSQL baglanti adresi
- `REDIS_URL` — Redis baglanti adresi
- `ANTHROPIC_API_KEY` — Claude API anahtari
- `DEEPGRAM_API_KEY` — Deepgram STT API anahtari
- `OPENAI_API_KEY` — OpenAI TTS API anahtari
- `GITHUB_TOKEN` — GitHub API erisim token'i
- `AWS_ACCESS_KEY_ID` — AWS erisim anahtari
- `AWS_SECRET_ACCESS_KEY` — AWS gizli anahtar
- `AWS_S3_BUCKET` — S3 bucket adi
- `JWT_SECRET_KEY` — JWT imzalama anahtari
- `AGENT_API_KEY` — Host Agent kimlik dogrulama anahtari
- `BACKEND_WS_URL` — Backend WebSocket adresi
