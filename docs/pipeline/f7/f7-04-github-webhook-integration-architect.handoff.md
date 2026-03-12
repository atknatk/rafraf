# Architect Handoff: GitHub Webhook Integration

**Issue**: #45
**Faz**: F7
**Tarih**: 2026-03-13
**Sonraki Agent**: developer

## Ozet

GitHub webhook handler'i production-grade hale getirme: check_run event destegi, DB-backed event depolama ile idempotency, CI failure bildirimi ve issue event'lerinde hafiza guncelleme.

## Feature Spec

-> `shared/feature-specs/f7-45-f7-04-github-webhook-integration.md`

## API Contracts

-> `shared/api-contracts/rest/v1/webhooks.json`

## Katman Dagilimi

| Katman | Oncelik | Tahmini Dosya Sayisi |
|--------|---------|---------------------|
| backend | HIGH | 6 dosya |
| ios | N/A | 0 dosya |
| agent | N/A | 0 dosya |

## Dikkat Edilecekler

- Mevcut webhook handler (`app/api/routes/webhooks.py`) zaten temel push/PR/issue event'lerini destekliyor. Genisletilecek, sifirdan yazilmayacak.
- In-memory `_recent_events` deque kaldirilip DB-backed storage kullanilacak.
- `X-GitHub-Delivery` header ile idempotency saglama: ayni delivery_id'ye sahip event tekrar islenmemeli.
- `check_run` event'inde `conclusion` alani kontrol edilmeli: `failure`, `timed_out`, `cancelled` sonuclarinda proactive bildirim olusturulmali.
- Background task ile event isleme yapilmali, webhook response hizli donmeli.
- Mevcut `WebhookResponse` schema'si korunacak, yeni `WebhookEventResponse` schema'si eklenir.
- `GitHubEventsResponse` mevcut olup DB'den cekilecek sekilde guncellenir.
- Alembic migration dosyasi olusturulmali.

## Dogrulama

- [x] Feature spec yazildi
- [x] API kontratlar olusturuldu
- [x] Dosya sahipligi belirlendi
- [x] Doc referanslari kontrol edildi
