# Feature: FastAPI WebSocket Server (iOS Client Connection)

**Issue**: #7
**Faz**: F1
**Katmanlar**: backend
**Pipeline**: full
**Tarih**: 2026-03-02

## Ozet

FastAPI WebSocket endpoint olusturarak iOS istemcilerin sunucuya baglanip gercek zamanli mesaj alisverisi yapabilmesini saglar. Bu feature, RafRaf sisteminin temel iletisim katmanini olusturur. Kullanici iOS uygulamasi uzerinden metin ve ses mesajlari gonderebilir, AI cevaplarini gercek zamanli olarak alabilir.

## Degisecek Dosyalar

### Backend (`apps/backend/`)
| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `app/api/routes/websocket.py` | CREATE | WebSocket endpoint ve mesaj handler |
| `app/schemas/messages.py` | CREATE | WebSocket mesaj Pydantic modelleri |
| `app/core/websocket.py` | MODIFY | ConnectionManager genisletme (heartbeat, session tracking) |
| `app/core/config.py` | MODIFY | WebSocket yapilandirma parametreleri ekleme |
| `app/main.py` | MODIFY | WebSocket router'i ekleme |

## API Endpoints

### WebSocket
| Path | Auth | Aciklama |
|------|------|----------|
| `/ws?token={JWT_TOKEN}` | JWT | iOS client WebSocket baglanti endpoint'i |

### WebSocket Messages
| Direction | Type | Payload | Aciklama |
|-----------|------|---------|----------|
| server->client | `connection_ack` | `{user_id, session_id, server_time}` | Baglanti onay mesaji |
| client->server | `text` | `{content, metadata}` | Metin mesaji gonderme |
| client->server | `voice` | `{content, metadata}` | Ses mesaji (STT sonrasi) |
| server->client | `text` | `{content, metadata}` | AI metin cevabi |
| server->client | `error` | `{error_code, message, details}` | Hata mesaji |
| server->client | `progress` | `{task, step, total_steps, percentage}` | Ilerleme bildirimi |
| bidirectional | `ping`/`pong` | `{timestamp}` | Heartbeat mekanizmasi |

## Data Model

### Pydantic Models

```python
class WebSocketMessage(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    type: str
    content: str | dict[str, object]
    metadata: MessageMetadata | None = None
    attachments: list[MessageAttachment] | None = None

class MessageMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)
    timestamp: str
    session_id: str | None = None
    project_id: str | None = None
    message_id: str | None = None
    direction: str

class MessageAttachment(BaseModel):
    model_config = ConfigDict(frozen=True)
    type: str
    url: str
    mime_type: str
    size_bytes: int

class ConnectionAckPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    user_id: str
    session_id: str
    server_time: str

class ErrorPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    error_code: str
    message: str
    details: str | None = None
    suggestion: str | None = None
    recoverable: bool = True

class ProgressPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    task: str
    step: int
    total_steps: int
    percentage: int
    details: str | None = None
```

## Business Rules

1. WebSocket baglantisi JWT token ile dogrulanir. Gecersiz token'da baglanti reddedilir (4008 close code).
2. Baglanti kurulunca `connection_ack` mesaji gonderilir.
3. Heartbeat: Server her 30 saniyede ping gonderir, client 10 saniye icinde pong donmezse baglanti kapatilir.
4. Her mesajin benzersiz `id` alani olmalidir (UUID v4).
5. Mesaj tipi tanimli tipler disindaysa `error` mesaji doner.
6. Baglanti koparsa ConnectionManager'dan otomatik temizlenir.
7. Ayni kullanici birden fazla baglanti kurabilir (multi-device destek).
8. Tum mesajlar JSON formatinda encode/decode edilir.

## Test Requirements

### Backend
- [ ] Unit test: WebSocket mesaj serialization/deserialization
- [ ] Unit test: JWT token dogrulama (gecerli, gecersiz, expired)
- [ ] Unit test: ConnectionManager connect/disconnect/send
- [ ] Integration test: WebSocket baglanti kurma ve mesaj alisverisi
- [ ] Integration test: Heartbeat mekanizmasi
- [ ] Integration test: Gecersiz token ile baglanti reddi
- [ ] Integration test: Reconnect senaryolari

## Acceptance Criteria

- [ ] `/ws` endpoint'i calisiyor
- [ ] iOS client baglanti kurabiliyor (JWT token ile)
- [ ] JSON mesaj encode/decode calisiyor
- [ ] Heartbeat/ping-pong mekanizmasi var
- [ ] Connection pooling ve cleanup
- [ ] Reconnect senaryolari handle ediliyor
- [ ] WebSocket message types tanimli (shared/api-contracts)
- [ ] Unit + integration testler yazildi
- [ ] Coverage >= 80%
