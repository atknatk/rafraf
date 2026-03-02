# Developer Handoff: Model Router (Haiku/Sonnet/Opus Selection)

**Issue**: #11
**Branch**: feature/f1/11-model-router-haiku-sonnet-selection
**Tarih**: 2026-03-02
**Sonraki Agent**: tester

## Yapilan Degisiklikler

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `apps/backend/app/orchestrator/model_router.py` | MODIFY | Complexity scoring algoritması, 3-tier routing (Haiku/Sonnet/Opus), override mekanizmasi, fallback stratejisi, cost tracking eklendi |
| `apps/backend/app/orchestrator/agent.py` | MODIFY | Cost tracking entegrasyonu, routing metadata loglama eklendi |
| `apps/backend/app/core/config.py` | MODIFY | `claude_complex_model` (Opus) config ayari eklendi |
| `apps/backend/tests/unit/test_orchestrator/test_model_router.py` | MODIFY | 41 yeni test: complexity scoring, tier selection, override, fallback, cost tracking |
| `docs/pipeline/f1/model-router-haiku-sonnet-selection-developer.handoff.md` | CREATE | Bu dosya |

## Implementasyon Detaylari

### Complexity Scoring Algoritmasi
- Keyword-based weighted scoring sistemi (her keyword'un agirlik puani var)
- Mesaj uzunlugu sinyali (kisa mesajlar: -10, uzun mesajlar: +10/+20)
- Kod blogu tespiti (triple backtick): +15
- Coklu soru isareti tespiti: +5/+10
- Numarali liste tespiti (multi-step task): +8/+15
- Skor araligu: -30 ile 120 arasi clamp edilir

### 3-Tier Model Routing
- **Haiku** (score < 20): Basit selamlasma, durum sorgulari, kisa cevaplar
- **Sonnet** (20 <= score < 70): Orta karmasiklik, analiz, review, ozet
- **Opus** (score >= 70): Mimari tasarim, multi-step planlama, kod uretimi, refactor

### Override Mekanizmasi
1. **Explicit override_tier parametresi**: Programatik olarak tier belirleme
2. **Kullanici mesaj kaliplari**: "haiku kullan", "opus kullan", "use sonnet", "en iyi model", "hizli cevap" gibi ifadeler

### Fallback Stratejisi
- Opus kullanilamazsa: Sonnet -> Haiku
- Sonnet kullanilamazsa: Haiku
- Haiku kullanilamazsa: Sonnet
- `available_models` parametresi ile runtime'da kullanilabilir modeller belirlenebilir

### Cost Tracking
- Her tier icin 1K token basina input/output maliyet tanimlari
- `estimate_cost()`: Tier icin tahmini maliyet bilgisi
- `record_cost()`: Tamamlanan istek icin hesaplanmis maliyet kaydı
- Agent'da her istek sonrasi cost loglama entegrasyonu

## API Kontrat Uyumu
- Bu feature yeni REST/WS endpoint eklemiyor, mevcut WebSocket akisindaki model secim logigini genisletiyor
- Kontrat dosyalari etkilenmiyor

## Dogrulama Sonuclari

| Arac | Durum | Detay |
|------|-------|-------|
| ruff check | PASS | 0 hata |
| ruff format | PASS | Formatli |
| mypy | PASS | 40 dosya, 0 hata |
| pytest | PASS | 295/307 passed (12 pre-existing auth failures) |

## Notlar

- `ModelRouterResult` artik `tier`, `complexity_score`, `is_override`, `is_fallback` alanlari iceriyor
- Eski `default_model` ve `simple_model` parametreleri kaldirildi, tier-based routing tercih ediliyor
- Pre-existing 12 test failure bcrypt/passlib iliskili, bu PR ile alakasiz
- Tester icin: Tum yeni fonksiyonlar (compute_complexity_score, select_model, get_model_for_tier, estimate_cost, record_cost) test edilmeli
