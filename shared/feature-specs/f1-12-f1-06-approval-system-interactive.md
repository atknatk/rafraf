# Feature: Approval System (Interactive Question Flow)

**Issue**: #12
**Faz**: F1
**Katmanlar**: backend
**Pipeline**: full
**Tarih**: 2026-03-02

## Ozet

Kullanicidan onay gerektiren islemler icin interaktif soru-cevap akisi. AI orchestrator bir tool calistirmadan once onay matrisini kontrol eder; yuksek riskli islemler (deploy, DB migration, dosya silme vb.) icin iOS client'a bir "question" mesaji gonderir ve kullanicinin onay/red cevabini bekler. Timeout durumunda islem otomatik iptal edilir.

## Degisecek Dosyalar

### Backend (`apps/backend/`)
| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `app/services/approval_service.py` | CREATE | Approval is mantigi: olusturma, bekleme, timeout, karar |
| `app/schemas/approval.py` | CREATE | Approval Pydantic request/response modelleri |
| `app/models/approval.py` | CREATE | SQLAlchemy approval_requests modeli |
| `app/repositories/approval_repository.py` | CREATE | Approval DB erisim katmani |
| `app/api/routes/websocket.py` | MODIFY | approval_response mesaj handler ekleme |
| `app/orchestrator/tool_registry.py` | MODIFY | Approval check entegrasyonu |
| `app/schemas/messages.py` | MODIFY | Mevcut — zaten APPROVAL_RESPONSE ve QUESTION type mevcut |
| `app/core/config.py` | MODIFY | approval_timeout_seconds zaten mevcut |

## WebSocket Messages

| Direction | Type | Payload | Aciklama |
|-----------|------|---------|----------|
| server->client | `question` | `QuestionPayload` | Kullaniciya onay sorusu gonder |
| client->server | `approval_response` | `ApprovalResponsePayload` | Kullanici karar cevabi |

## Data Model

### PostgreSQL
```sql
-- approval_requests tablosu (docs/02 de tanimli)
CREATE TABLE approval_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(100) NOT NULL,
    tool_name VARCHAR(50) NOT NULL,
    action VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    params JSONB,
    category VARCHAR(50) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',   -- pending | approved | rejected | expired
    timeout_seconds INT NOT NULL DEFAULT 300,
    timeout_at TIMESTAMPTZ NOT NULL,
    responded_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Pydantic Models
```python
class ApprovalCategory(StrEnum):
    DEPLOY = "deploy"
    DESTRUCTIVE = "destructive"
    INFRASTRUCTURE = "infrastructure"
    WRITE_REMOTE = "write_remote"

class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"

class ApprovalRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    session_id: str
    tool_name: str
    action: str
    description: str
    params: dict[str, object] | None = None
    category: ApprovalCategory
    status: ApprovalStatus = ApprovalStatus.PENDING
    timeout_seconds: int = 300
    timeout_at: str
    created_at: str

class ApprovalDecision(BaseModel):
    model_config = ConfigDict(frozen=True)
    approval_id: str
    decision: str   # "approved" | "rejected"
    note: str | None = None

class ApprovalResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    approved: bool
    approval_id: str
    decision: str
    note: str | None = None
```

## Business Rules

1. Onay matrisi `docs/07_Security_Permissions_Cost_Analysis.md` Bolum 3.2'de tanimli
2. Yuksek riskli islemler: deploy, DB migration, dosya silme, kubectl, aws cli, git push, docker push
3. Dusuk riskli islemler: okuma, analiz, rapor — onay gerektirmez
4. Timeout: varsayilan 300 saniye (5 dakika), kategori bazli ayarlanabilir
5. Timeout durumunda islem otomatik `expired` olur ve Claude'a "timeout" bilgisi doner
6. Bir session'da ayni anda sadece 1 aktif approval olabilir
7. Approval history audit log amacli saklanir
8. Acil durum bypass YOKTUR (guvenlik prensibi)

## Test Requirements

### Backend
- [ ] Unit test: ApprovalService.create_approval — approval olusturma
- [ ] Unit test: ApprovalService.check_requires_approval — matris kontrol
- [ ] Unit test: ApprovalService.process_decision — karar isleme
- [ ] Unit test: ApprovalService.check_timeout — timeout senaryolari
- [ ] Unit test: Approval schema validation testleri
- [ ] Integration test: WebSocket approval_response handler
- [ ] Integration test: Full approval flow (question -> response -> tool execution)

## Acceptance Criteria

- [ ] Approval request olusturma (tool calistirmadan once)
- [ ] Approval matris sistemi (hangi tool onay gerektirir)
- [ ] Timeout mekanizmasi (varsayilan 300sn, expired action)
- [ ] Approval history (audit log)
- [ ] Multi-choice question support (approve/reject/detail options)
- [ ] WebSocket uzerinden iOS'a soru gonderme
- [ ] Unit + integration testler yazildi
- [ ] Coverage >= 80%
