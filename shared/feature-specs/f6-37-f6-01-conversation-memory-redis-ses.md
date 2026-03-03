# Feature: Conversation Memory (Redis, Session Management)

**Issue**: #37
**Faz**: F6
**Katmanlar**: backend
**Pipeline**: full
**Tarih**: 2026-03-03

## Ozet

Konusma hafizasi sistemi. Redis ile oturum bazli kisa sureli hafiza yonetimi saglar. Her konusma oturumu Redis'te saklanir, mesajlar eklenir/okunur ve TTL ile otomatik temizlenir. Uzun konusmalarda context window yonetimi (token limit) ve oturum ozeti olusturma destegi saglar. Bu ozellik, AI'nin mevcut konusmadaki baglami korumasini ve "az once soyledigim" gibi referanslari anlamasini saglar.

## Degisecek Dosyalar

### Backend (`apps/backend/`)

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `app/services/conversation_memory_service.py` | CREATE | Conversation memory business logic (session CRUD, mesaj yonetimi, ozet, context window) |
| `app/schemas/conversation_memory.py` | CREATE | Pydantic request/response modelleri (session, mesaj, ozet) |
| `app/api/routes/conversation_memory.py` | CREATE | REST endpoint'leri (session CRUD, mesaj gecmisi, ozet) |
| `app/core/redis.py` | MODIFY | Session metadata, mesaj listesi (RPUSH), TTL refresh, session ozet cache |
| `app/core/config.py` | MODIFY | Conversation memory konfigurasyonu (TTL, max tokens, max messages) |
| `app/main.py` | MODIFY | Yeni router'i dahil et |

## API Endpoints

### REST

| Method | Path | Request | Response | Aciklama |
|--------|------|---------|----------|----------|
| POST | `/api/v1/conversations` | `ConversationCreateRequest` | `ConversationSessionResponse` | Yeni session olustur |
| GET | `/api/v1/conversations/{session_id}` | - | `ConversationSessionResponse` | Session bilgisi getir |
| DELETE | `/api/v1/conversations/{session_id}` | - | 204 | Session sonlandir (ozet olustur, temizle) |
| GET | `/api/v1/conversations/{session_id}/messages` | `?limit=&offset=` | `ConversationMessagesResponse` | Mesaj gecmisi getir |
| POST | `/api/v1/conversations/{session_id}/messages` | `ConversationMessageCreateRequest` | `ConversationMessageResponse` | Mesaj ekle |
| POST | `/api/v1/conversations/{session_id}/summarize` | - | `ConversationSummaryResponse` | Session ozetini olustur |
| GET | `/api/v1/conversations/{session_id}/context` | `?max_tokens=` | `ConversationContextResponse` | Context window icin optimize edilmis mesaj gecmisi |

### WebSocket Messages

Bu feature WS mesaj tipi eklemez. Mevcut WS handler, session_id bazli mesaj alip conversation_memory_service araciligiyla Redis'e kaydeder. Bu entegrasyon gelecek bir WS handler update'inde yapilacaktir.

## Data Model

### Redis Veri Yapilari

Session metadata (Hash):
```
conv:session:{session_id}:meta -> {user_id, project_id, created_at, status, message_count, total_tokens}
```

Mesaj listesi (List - RPUSH):
```
conv:session:{session_id}:messages -> [msg1_json, msg2_json, ...]
```

Session ozeti (String):
```
conv:session:{session_id}:summary -> "ozet metni"
```

Kullanici aktif sessionlari (Set):
```
conv:user:{user_id}:sessions -> {session_id_1, session_id_2, ...}
```

### Pydantic Models

```python
class ConversationMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    role: str  # "user" | "assistant" | "tool" | "system"
    content: str
    timestamp: datetime
    token_count: int
    metadata: dict[str, str] | None = None


class ConversationSession(BaseModel):
    model_config = ConfigDict(frozen=True)

    session_id: str
    user_id: str
    project_id: str | None = None
    status: str  # "active" | "ended" | "summarized"
    message_count: int
    total_tokens: int
    created_at: datetime
    last_activity_at: datetime | None = None
    summary: str | None = None
```

## Business Rules

1. Session olusturulurken user_id zorunlu, project_id opsiyonel
2. Her session'in TTL'i 24 saat (konfigurasyondan degistirilebilir)
3. Her mesaj eklendiginde TTL yenilenir (session aktif kaldikca silimez)
4. Context window esigi: 50,000 token (konfigurasyondan degistirilebilir)
5. Esik asildiginda eski mesajlar ozetlenir ve ozet session'a kaydedilir
6. Session sonlandirildiginda: ozet olusturulur, Redis'teki cache temizlenir (ozet haric)
7. Mesaj listesi RPUSH ile eklenir (siralama korunur), LRANGE ile okunur
8. Token hesaplama: karakter sayisi / 4 (yaklasik tahmin)
9. Session ID formatı: UUID v4
10. 30 dakika inaktivite sonrasi session "stale" olarak isaretlenir (TTL ile otomatik temizlik)

## Test Requirements

### Backend
- [ ] Unit test: ConversationMemoryService.create_session — session olusturma
- [ ] Unit test: ConversationMemoryService.add_message — mesaj ekleme ve token hesaplama
- [ ] Unit test: ConversationMemoryService.get_messages — mesaj gecmisi (limit/offset)
- [ ] Unit test: ConversationMemoryService.get_context_window — context window kesme
- [ ] Unit test: ConversationMemoryService.summarize_session — ozet olusturma
- [ ] Unit test: ConversationMemoryService.end_session — session sonlandirma
- [ ] Unit test: TTL yenileme (her mesaj ekleme sonrasi)
- [ ] Unit test: Token limit asimi durumunda ozet olusturma tetiklenmesi
- [ ] Integration test: Redis ile tam CRUD dongusu
- [ ] Integration test: REST endpoint'ler (session create, message add, get context)
- [ ] Integration test: TTL expiry davranisi

## Acceptance Criteria

- [ ] Redis ile conversation storage calisiyor
- [ ] Session olusturma/sonlandirma calisiyor
- [ ] Mesaj gecmisi kaydetme/okuma calisiyor
- [ ] TTL ile otomatik temizlik calisiyor
- [ ] Context window yonetimi (token limit) calisiyor
- [ ] Session ozeti olusturma (uzun konusmalarda) calisiyor
- [ ] Unit + integration testler yazildi
- [ ] Coverage >= 80%
