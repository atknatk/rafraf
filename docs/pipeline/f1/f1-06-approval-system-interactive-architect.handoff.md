# Architect Handoff: Approval System (Interactive Question Flow)

**Issue**: #12
**Faz**: F1
**Tarih**: 2026-03-02
**Sonraki Agent**: developer

## Ozet

Kullanicidan onay gerektiren islemler icin interaktif soru-cevap akisi. Tool calistirmadan once onay matrisini kontrol eder, yuksek riskli islemler icin iOS client'a question mesaji gonderir ve kullanicinin cevabini bekler.

## Feature Spec

-> `shared/feature-specs/f1-12-f1-06-approval-system-interactive.md`

## API Contracts

-> `shared/api-contracts/ws/approval-messages.json`

## Katman Dagilimi

| Katman | Oncelik | Tahmini Dosya Sayisi |
|--------|---------|---------------------|
| backend | HIGH | 7 dosya (4 CREATE + 3 MODIFY) |
| ios | N/A | 0 dosya (ilerideki fazda) |
| agent | N/A | 0 dosya |

## Dikkat Edilecekler

- `MessageType` enum'unda `QUESTION` ve `APPROVAL_RESPONSE` zaten tanimli (schemas/messages.py)
- `QuestionPayload`, `QuestionOptionPayload`, `ApprovalResponsePayload` zaten tanimli
- `approval_timeout_seconds` config'de zaten mevcut (300sn varsayilan)
- Onay matrisi `docs/07_Security_Permissions_Cost_Analysis.md` Bolum 3.2'deki tabloya gore
- WebSocket handler'da `approval_response` tipi su an `UNSUPPORTED_CLIENT_MESSAGE` hata veriyor — handler eklenmeli
- `app/orchestrator/tool_registry.py` mevcut — approval check burada entegre edilmeli
- Bir session'da ayni anda en fazla 1 aktif approval olabilir
- Timeout durumunda islem otomatik `expired` olarak isaretlenir

## Dogrulama

- [x] Feature spec yazildi
- [x] API kontratlar olusturuldu
- [x] Dosya sahipligi belirlendi
- [x] Doc referanslari kontrol edildi
