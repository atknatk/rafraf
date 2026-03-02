# Architect Handoff: Docker Runner (compose up/down/logs/health)

**Issue**: #14
**Faz**: F2
**Tarih**: 2026-03-02
**Sonraki Agent**: developer

## Ozet

Docker Compose islemlerini calistiran runner implementasyonu. Host Agent uzerinde compose up/down/restart, log okuma, health check ve container status raporlama islemlerini gerceklestirir. Docker SDK for Python ve Compose v2 CLI kullanir. Sadece izin verilen compose dosyalari ile calisabilir.

## Feature Spec

-> `shared/feature-specs/f2-14-docker-runner.md`

## API Contracts

Bu feature sadece agent katmanini etkiler. Yeni REST/WS endpoint eklenmez. Mevcut `agent_command` / `agent_command_result` WS mesaj akisi uzerinden calisir.

## Katman Dagilimi

| Katman | Oncelik | Tahmini Dosya Sayisi |
|--------|---------|---------------------|
| agent | HIGH | 5 dosya |

## Dikkat Edilecekler

- BaseRunner abstract sinifi olusturulmali (gelecek runner'lar icin de kullanilacak)
- Docker SDK (`docker` package) import'u thread pool uzerinden yapilmali (blocking)
- Compose v2 CLI (`docker compose`) async subprocess ile calistirilmali
- Izin verilen compose dosyalari konfigurasyondan okunmali
- Timeout handling: asyncio.wait_for ile
- Resource limitleri (CPU, RAM) config uzerinden yonetilebilir olmali
- Proje path'lerinin fiziksel olarak mevcut olmasi dogrulanmali
- `docs/08_Host_Agent_Specification.md` section 5.2 Docker Runner referans alinmali
- F2-01 (Agent daemon base) #13 tamamlanmis, temel altyapi (config, connection, protocol, monitoring) mevcut

## Dogrulama

- [x] Feature spec yazildi
- [x] API kontratlar kontrol edildi (yeni endpoint/WS mesaji yok, mevcut akis yeterli)
- [x] Dosya sahipligi belirlendi
- [x] Doc referanslari kontrol edildi
