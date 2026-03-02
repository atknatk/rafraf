# Architect Handoff: Shell Runner (Whitelist/Blacklist Security)

**Issue**: #16
**Faz**: F2
**Tarih**: 2026-03-02
**Sonraki Agent**: developer

## Ozet

Guvenli shell komut calistirici. Whitelist/blacklist/approval mekanizmasi ile
sadece izin verilen komutlar calistirilir. Injection korunmasi, timeout handling
ve output capture ozellikleri icerdir. Agent katmaninda calisan BaseRunner alt sinifi.

## Feature Spec

-> `shared/feature-specs/f2-16-shell-runner.md`

## API Contracts

Bu feature yeni API endpoint gerektirmez. Mevcut `agent_command` / `command_result`
WebSocket akisi kullanilir. Yeni API kontrat dosyasi olusturulmadi.

## Katman Dagilimi

| Katman | Oncelik | Tahmini Dosya Sayisi |
|--------|---------|---------------------|
| agent | HIGH | 6 dosya |
| backend | N/A | 0 dosya |
| ios | N/A | 0 dosya |

## Dikkat Edilecekler

- Security pattern'leri `docs/08_Host_Agent_Specification.md` Bolum 5.5 ile uyumlu olmali
- Approval matrisi `docs/07_Security_Permissions_Cost_Analysis.md` Bolum 3.2 ile uyumlu olmali
- BaseRunner abstract sinifini extend etmeli (`agent/runners/base.py`)
- DockerRunner ve PlaywrightRunner ile ayni pattern'leri takip etmeli
- `shell=True` kullanildiginda injection korunmasi KRITIK
- `asyncio.create_subprocess_shell` ile komut calistirma
- Output truncation: stdout max 5000 karakter, stderr max 2000 karakter
- Timeout: varsayilan 60sn, max 300sn (5dk)
- Tum security modulleri (whitelist, blacklist, sanitizer) ayri dosyalarda olmali
- Mevcut `agent/security/__init__.py` dosyasi guncellenmeli

## Dogrulama

- [x] Feature spec yazildi
- [x] API kontratlar guncellenmedi (gerekli degil — yeni endpoint yok)
- [x] Dosya sahipligi belirlendi
- [x] Doc referanslari kontrol edildi (doc 07, doc 08)
