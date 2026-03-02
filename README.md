# RafRaf - AI Project Supervisor

> AI-driven proje yonetim sistemi - sesli ve metin tabanli arayuz

## Proje Hakkinda

RafRaf, yapay zeka destekli bir proje yonetim sistemidir. Sesli ve metin tabanli arayuz uzerinden projelerinizi yonetmenize olanak tanir. Backend tarafinda FastAPI ve Claude Agent SDK, mobil tarafta SwiftUI ile gelistirilmis iOS uygulamasi ve host makinelerinde calisan Python daemon agent'i ile uctan uca bir deneyim sunar.

## Teknoloji Yigini

| Katman | Teknoloji |
|--------|-----------|
| **Backend** | FastAPI + Python 3.12 + Claude Agent SDK + WebSocket |
| **iOS** | SwiftUI + iOS 17+ + Clean Architecture + Swift 6 |
| **Host Agent** | Python 3.12 + asyncio daemon + Docker/Playwright/Maestro |
| **Veritabani** | PostgreSQL 16 + pgvector + Redis 7 |
| **Hafiza** | mem0 (3 katmanli hafiza sistemi) |
| **Altyapi** | AWS EKS, S3, CloudWatch |
| **Dis Servisler** | Claude API, Deepgram STT, OpenAI TTS, GitHub API |

## Repo Yapisi

```
rafraf/
├── apps/
│   ├── backend/           # FastAPI WebSocket server + AI orchestrator
│   ├── ios/               # SwiftUI iOS uygulamasi (Clean Architecture)
│   └── agent/             # Python host agent daemon
├── shared/
│   ├── api-contracts/     # WebSocket + REST API semalari
│   └── feature-specs/     # Architect feature spesifikasyonlari
├── docs/                  # Sistem spesifikasyonlari (01-08) + standartlar
├── infra/
│   ├── docker/            # Docker compose ve Dockerfile'lar
│   └── k8s/               # Kubernetes konfigurasyonlari
├── scripts/               # Otomasyon betikleri
└── .claude/               # AI agent pipeline konfigurasyonu
```

## Baslangic

### Gereksinimler

- Python 3.12+
- Xcode 16+ (iOS gelistirme icin)
- Docker ve Docker Compose
- PostgreSQL 16
- Redis 7

### Gelistirme Ortami

```bash
# Docker ile gelistirme ortamini baslat
docker compose -f infra/docker/docker-compose.dev.yml up -d

# Backend
cd apps/backend && python -m uvicorn app.main:app --reload

# iOS
cd apps/ios && xcodebuild build -scheme RafRaf

# Host Agent
cd apps/agent && python -m agent.main
```

### Testler

```bash
# Backend testleri
cd apps/backend && python -m pytest --cov=app

# iOS testleri
cd apps/ios && xcodebuild test -scheme RafRaf

# Agent testleri
cd apps/agent && python -m pytest --cov=agent
```

### Lint ve Tip Kontrolu

```bash
# Backend
cd apps/backend && ruff check app/ && mypy app/

# Agent
cd apps/agent && ruff check agent/ && mypy agent/
```

## Ortam Degiskenleri

Asagidaki ortam degiskenlerini `.env` dosyasinda tanimlayin:

| Degisken | Aciklama |
|----------|----------|
| `DATABASE_URL` | PostgreSQL baglanti adresi |
| `REDIS_URL` | Redis baglanti adresi |
| `ANTHROPIC_API_KEY` | Claude API anahtari |
| `DEEPGRAM_API_KEY` | Deepgram STT API anahtari |
| `OPENAI_API_KEY` | OpenAI TTS API anahtari |
| `GITHUB_TOKEN` | GitHub API erisim token'i |
| `AWS_ACCESS_KEY_ID` | AWS erisim anahtari |
| `AWS_SECRET_ACCESS_KEY` | AWS gizli anahtar |
| `AWS_S3_BUCKET` | S3 bucket adi |
| `JWT_SECRET_KEY` | JWT imzalama anahtari |
| `AGENT_API_KEY` | Host Agent kimlik dogrulama anahtari |
| `BACKEND_WS_URL` | Backend WebSocket adresi |

## Dokumantasyon

Detayli sistem spesifikasyonlari `docs/` dizininde bulunur:

1. [Sistem Mimarisi](docs/01_System_Architecture_Overview.md)
2. [Backend API ve WebSocket](docs/02_Backend_API_WebSocket_Specification.md)
3. [AI Agent Tool Katmani](docs/03_AI_Agent_Tool_Layer_Specification.md)
4. [iOS Uygulama](docs/04_iOS_App_Specification.md)
5. [Hafiza Sistemi](docs/05_Memory_System_Specification.md)
6. [Test Stratejisi](docs/06_Testing_Strategy.md)
7. [Guvenlik ve Maliyet](docs/07_Security_Permissions_Cost_Analysis.md)
8. [Host Agent](docs/08_Host_Agent_Specification.md)

## Lisans

Bu proje ozel bir projedir. Tum haklari saklidir.
