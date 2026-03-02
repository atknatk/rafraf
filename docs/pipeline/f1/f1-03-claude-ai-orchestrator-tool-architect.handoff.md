# Architect Handoff: Claude AI Orchestrator + Tool-Calling Loop

**Issue**: #9
**Faz**: F1
**Tarih**: 2026-03-02
**Sonraki Agent**: developer

## Ozet

Claude Agent SDK ile AI reasoning ve tool-calling loop implementasyonu. Backend'in beyin katmanini olusturan ana orkestrator modulu. Kullanicidan gelen mesajlari analiz eder, uygun model'i secer, tool call'lari yonetir ve sonuclari iOS istemcisine iletir.

## Feature Spec

-> `shared/feature-specs/f1-9-f1-03-claude-ai-orchestrator-tool.md`

## API Contracts

-> `shared/api-contracts/ws/orchestrator-messages.json`

## Katman Dagilimi

| Katman | Oncelik | Tahmini Dosya Sayisi |
|--------|---------|---------------------|
| backend | HIGH | 10 dosya |
| ios | N/A | 0 dosya |
| agent | N/A | 0 dosya |

## Dikkat Edilecekler

- Claude Agent SDK (anthropic python SDK) kullanilmali, custom HTTP client degil
- Tool-calling loop max 10 iterasyonda sonlanmali (sonsuz dongu korunmasi)
- Model router basit keyword tabanli olacak (doc 03 referans)
- System prompt docs/03 icerigine uygun olmali
- Onay mekanizmasi WebSocket uzerinden iOS'a soru gondererek calisacak
- `app/api/routes/websocket.py` dosyasindaki placeholder echo handler'lar orchestrator'a yonlendirilmeli
- Mevcut `app/schemas/messages.py` dosyasina yeni MessageType'lar eklenmeli (action_result, question, status, approval_response)
- Streaming partial response icin WebSocket'e iteratif mesaj gonderimi yapilmali
- `app/core/config.py`'ye Claude API model ve max iteration ayarlari eklenmeli
- Bagimliliklari: F1-01 (WebSocket server) — tamamlanmis

## Dogrulama

- [x] Feature spec yazildi
- [x] API kontratlar olusturuldu
- [x] Dosya sahipligi belirlendi
- [x] Doc referanslari kontrol edildi (docs/02, docs/03)
