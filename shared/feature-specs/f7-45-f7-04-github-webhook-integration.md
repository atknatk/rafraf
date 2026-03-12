# Feature: GitHub Webhook Integration

**Issue**: #45
**Faz**: F7
**Katmanlar**: backend
**Pipeline**: full
**Tarih**: 2026-03-13

## Ozet

GitHub webhook entegrasyonunu genisletir: `check_run` event destegi, DB-backed event depolama ile idempotency garantisi, CI basarisizlik bildirimi ve issue update'lerinde hafiza guncelleme. Mevcut in-memory webhook handler'i production-grade hale getirir.

## Degisecek Dosyalar

### Backend (`apps/backend/`)
| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `app/models/webhook_event.py` | CREATE | SQLAlchemy model - webhook event DB tablosu |
| `app/repositories/webhook_event_repository.py` | CREATE | DB erisim katmani - event CRUD |
| `app/services/webhook_event_service.py` | CREATE | Business logic - idempotency, event dispatch |
| `app/api/routes/webhooks.py` | MODIFY | check_run handler, DB entegrasyonu, idempotency |
| `app/schemas/github.py` | MODIFY | Yeni schema'lar (WebhookEventResponse, vb.) |
| `shared/api-contracts/rest/v1/webhooks.json` | MODIFY | check_run event ve events listesi endpoint'i ekleme |

## API Endpoints

### REST
| Method | Path | Request | Response | Aciklama |
|--------|------|---------|----------|----------|
| POST | `/api/v1/webhooks/github` | GitHub webhook payload | `WebhookResponse` | Mevcut - check_run eklenir |
| GET | `/api/v1/webhooks/github/events` | `?limit=20&event_type=check_run` | `GitHubEventsResponse` | Mevcut - DB-backed, filtreleme eklenir |

## Data Model

### PostgreSQL
```sql
CREATE TABLE webhook_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    delivery_id VARCHAR(255) UNIQUE NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    action VARCHAR(100) NOT NULL DEFAULT '',
    repo VARCHAR(255) NOT NULL DEFAULT '',
    sender VARCHAR(255) NOT NULL DEFAULT '',
    summary JSONB NOT NULL DEFAULT '{}',
    processed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_webhook_events_delivery_id ON webhook_events(delivery_id);
CREATE INDEX ix_webhook_events_event_type ON webhook_events(event_type);
CREATE INDEX ix_webhook_events_created_at ON webhook_events(created_at DESC);
```

### Pydantic Models
```python
class WebhookEventCreate(BaseModel):
    delivery_id: str
    event_type: str
    action: str
    repo: str
    sender: str
    summary: dict[str, object]

class WebhookEventResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    delivery_id: str
    event_type: str
    action: str
    repo: str
    sender: str
    summary: dict[str, object]
    processed: bool
    created_at: datetime
```

## Business Rules

1. **Idempotency**: `X-GitHub-Delivery` header ile event benzersizligi kontrol edilir. Ayni delivery_id'li event tekrar islenmez, `200 OK` ile "already processed" donulur.
2. **check_run event**: `conclusion` alani `failure`, `timed_out` veya `cancelled` ise kullaniciya proactive bildirim gonderilir.
3. **DB-backed storage**: Tum webhook event'leri PostgreSQL'e kaydedilir. In-memory ring buffer kaldirilir.
4. **Issue update -> hafiza**: Issue event'lerinde (opened, closed, labeled) mem0 hafiza sistemine ozet kaydedilir.
5. **Background dispatch**: Event isleme background task olarak yapilir, webhook response hizli donulur.

## Test Requirements

### Backend
- [ ] Unit test: webhook signature dogrulama (valid/invalid/missing)
- [ ] Unit test: idempotency (ayni delivery_id ile iki kez gonderme)
- [ ] Unit test: check_run event handler (failure/success/timed_out)
- [ ] Unit test: event DB kaydi ve listeleme
- [ ] Integration test: POST /api/v1/webhooks/github tum event tipleri
- [ ] Integration test: GET /api/v1/webhooks/github/events filtreleme

## Acceptance Criteria

- [ ] Webhook endpoint check_run event tipini destekler
- [ ] HMAC-SHA256 signature dogrulama calisir
- [ ] Ayni event iki kez islenmez (idempotency)
- [ ] Tum event'ler DB'ye kaydedilir
- [ ] CI failure durumunda kullaniciya bildirim gider
- [ ] Issue update'lerinde hafiza guncellenir
- [ ] Unit + integration testler yazildi
- [ ] Coverage >= 80%
