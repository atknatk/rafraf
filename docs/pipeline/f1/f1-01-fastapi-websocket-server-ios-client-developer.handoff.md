# Developer Handoff: FastAPI WebSocket Server (iOS Client Connection)

**Issue**: #7
**Branch**: feature/f1/7-f1-01-fastapi-websocket-server-ios-client
**Tarih**: 2026-03-02
**Sonraki Agent**: tester

## Yapilan Degisiklikler

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `app/schemas/messages.py` | CREATE | WebSocket mesaj Pydantic modelleri (MessageType, WebSocketMessage, ConnectionAckPayload, ErrorPayload, ProgressPayload, PingPongPayload) |
| `app/api/routes/websocket.py` | CREATE | `/ws` WebSocket endpoint, JWT auth, mesaj routing, heartbeat |
| `app/core/websocket.py` | MODIFY | ConnectionManager genisletildi: ConnectionInfo, heartbeat, multi-device, send_to_user |
| `app/core/config.py` | MODIFY | ws_heartbeat_interval ve ws_heartbeat_timeout ayarlari eklendi |
| `app/main.py` | MODIFY | websocket_router eklendi |

## API Kontrat Uyumu

- Referans kontrat: `shared/api-contracts/ws/websocket-messages.json`
- Dogrulanan mesaj tipleri: connection_ack, text, voice, error, progress, ping, pong
- Tum mesaj yapilari kontrat ile uyumlu

## Dogrulama Sonuclari

| Arac | Durum | Detay |
|------|-------|-------|
| ruff check | PASS | Tum kontroller gecti |
| ruff format | PASS | Tum dosyalar formatli |
| mypy | PASS | 23 dosya, 0 hata |

## Notlar

- Text ve voice handler'lari su an echo/acknowledgment gonderir. AI orchestrator entegrasyonu sonraki issue'larda yapilacak.
- Heartbeat server-tarafli ping gonderiyor. Client pong donmezse bir sonraki ping cycle'da baglanti temizlenecek.
- ConnectionManager multi-device destekli: ayni user_id ile birden fazla baglanti kurulabilir. connection_id formati: `{user_id}:{uuid}`.
- WebSocket close code'lari: 4008 (invalid token), 1000 (normal close)
