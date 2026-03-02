# Architect Handoff: FastAPI WebSocket Server (iOS Client Connection)

**Issue**: #7
**Faz**: F1
**Tarih**: 2026-03-02
**Sonraki Agent**: developer

## Ozet

iOS istemcilerin FastAPI WebSocket sunucusuna baglanip gercek zamanli JSON mesaj alisverisi yapabilecegi temel WebSocket endpoint'inin tasarimi. JWT token ile kimlik dogrulama, heartbeat mekanizmasi, connection pooling ve cleanup iceren tam bir WebSocket server implementasyonu.

## Feature Spec

-> `shared/feature-specs/f1-7-f1-01-fastapi-websocket-server-ios-client.md`

## API Contracts

-> `shared/api-contracts/ws/websocket-messages.json`

## Katman Dagilimi

| Katman | Oncelik | Tahmini Dosya Sayisi |
|--------|---------|---------------------|
| backend | HIGH | 5 dosya (2 CREATE, 3 MODIFY) |
| ios | N/A | 0 dosya |
| agent | N/A | 0 dosya |

## Dikkat Edilecekler

- **JWT Token Dogrulama**: WebSocket baglanti aninda query parameter olarak gelen token dogrulanmali. Mevcut `app/core/security.py` dosyasindaki `verify_access_token` fonksiyonu kullanilmali.
- **ConnectionManager Genisletme**: Mevcut `app/core/websocket.py` dosyasindaki `ConnectionManager` sinifini genislet. Heartbeat task'i ve session bilgisi ekle.
- **Heartbeat**: Server tarafli ping gondermeli (30 sn aralik), client 10 sn icinde pong donmezse baglanti kapatilmali. asyncio.Task olarak yonetilmeli.
- **Mesaj Formati**: `docs/02_Backend_API_WebSocket_Specification.md` Bolum 3.2'deki Base Message Schema'ya uyumlu olmali.
- **Async Pattern**: Tum handler'lar `async def` olmali. `structlog` ile loglama zorunlu.
- **Close Codes**: 4001 (auth failed), 4008 (invalid token), 1000 (normal close), 1001 (going away)
- **Multi-device**: Ayni kullanici birden fazla cihazdan baglanabilmeli. connection_id = f"{user_id}:{uuid}" formati kullanilmali.

## Dogrulama

- [x] Feature spec yazildi
- [x] API kontratlar olusturuldu
- [x] Dosya sahipligi belirlendi
- [x] Doc referanslari kontrol edildi (02_Backend_API_WebSocket_Specification.md)
