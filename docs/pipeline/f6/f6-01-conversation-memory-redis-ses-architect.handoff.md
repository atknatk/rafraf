# Architect Handoff: Conversation Memory (Redis, Session Management)

**Issue**: #37
**Faz**: F6
**Tarih**: 2026-03-03
**Sonraki Agent**: developer

## Ozet

Konusma hafizasi sistemi (Layer 1). Redis ile oturum bazli kisa sureli hafiza yonetimi. Session CRUD, mesaj gecmisi, TTL otomatik temizlik, context window yonetimi (token limit) ve session ozet olusturma. Backend-only feature.

## Feature Spec

-> `shared/feature-specs/f6-37-f6-01-conversation-memory-redis-ses.md`

## API Contracts

-> `shared/api-contracts/rest/v1/conversation-memory.json`

## Katman Dagilimi

| Katman | Oncelik | Tahmini Dosya Sayisi |
|--------|---------|---------------------|
| backend | HIGH | 6 dosya (3 CREATE, 3 MODIFY) |
| ios | N/A | 0 dosya |
| agent | N/A | 0 dosya |

## Dikkat Edilecekler

- Mevcut `RedisClient` (`app/core/redis.py`) zaten temel conversation save/get/append/delete islemleri iceriyor. Yeni servis bunlarin uzerine insa etmeli, Redis key yapisini session bazli Hash + List + String olarak genisletmeli.
- Mevcut `MemoryService` (`app/services/memory_service.py`) conversation layer'i icin `save_conversation`, `get_conversation`, `append_message`, `clear_conversation` metodlarini kullaniyor. Yeni `ConversationMemoryService` bunlari genisletecek ve session lifecycle yonetimi ekleyecek. Mevcut MemoryService'teki conversation metodlari yeni servise delege edilebilir.
- Token hesaplama: karakter sayisi / 4 (yaklasik tahmin). Daha sonra tiktoken ile degistirilebilir.
- Session ozeti icin Claude API cagirma. Summarize endpoint'i disaridan cagirilir; servis summary_text parametresi alarak ozeti Redis'e kaydeder. Gercek AI cagrisini orchestrator yapacak (bu issue kapsaminda degil). Simdilik basit bir truncation-based ozet kullanilabilir.
- TTL: 24 saat varsayilan, konfigurasyondan degistirilebilir. Her mesaj eklendiginde TTL refresh edilir.
- `docs/05_Memory_System_Specification.md` Bolum 3 (Conversation Memory) referans alinmali.
- Bagimliliklarin durumu: F3-03 (Memory manager) zaten implement edilmis. Bu feature onu genisletiyor.

## Dogrulama

- [x] Feature spec yazildi
- [x] API kontratlar olusturuldu
- [x] Dosya sahipligi belirlendi
- [x] Doc referanslari kontrol edildi
