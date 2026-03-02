# Developer Handoff: Maestro Runner (iOS/Android Flow)

**Issue**: #17
**Branch**: feature/f2/17-f2-05-maestro-runner-iosandroid-flow
**Tarih**: 2026-03-02
**Sonraki Agent**: tester (standard pipeline)

## Yapilan Degisiklikler

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `apps/agent/agent/runners/maestro_runner.py` | CREATE | Maestro runner - run_flow, run_all_flows, take_screenshot, list_flows, validate_flow aksiyonlari |
| `apps/agent/agent/runners/__init__.py` | MODIFY | MaestroRunner ve MaestroRunnerError export eklendi |
| `docs/pipeline/f2/f2-05-maestro-runner-iosandroid-flow-developer.handoff.md` | CREATE | Developer handoff dosyasi |

## Implementasyon Detaylari

### MaestroRunner Aksiyonlari

1. **run_flow**: Tek bir YAML flow dosyasini calistirir. Platform (ios/android), flow_file, cwd, timeout, project_slug parametreleri alir. Sonuclari parse eder, screenshot toplar.
2. **run_all_flows**: Bir dizindeki tum .yaml/.yml flow dosyalarini sirayla calistirir. Her flow icin ayri sonuc raporu olusturur.
3. **take_screenshot**: Mevcut simulator/emulator ekraninin screenshot'ini alir. iOS icin `xcrun simctl io booted screenshot`, Android icin `adb exec-out screencap -p` kullanir.
4. **list_flows**: Belirtilen dizindeki flow dosyalarini listeler (isim, yol, boyut).
5. **validate_flow**: Flow dosyasinin gecerliliginii kontrol eder (bos dosya, bilinen Maestro komutlari).

### Guvenlik / Tasarim Kararlari

- BaseRunner'dan turetilmis, `run()` ile zamanlama/loglama otomatik
- Subprocess ile Maestro CLI cagirilir (`maestro test <flow>`)
- Platform bazli device parametresi destegi (--device)
- S3 upload opsiyonel, yoksa lokal dosya yolu dondurulur
- Timeout handling: varsayilan 300sn, max 600sn
- Flow dosyasi uzanti dogrulamasi (.yaml/.yml)
- Maestro output regex ile parse edilir (Passed/Failed sayilari)

## Dogrulama Sonuclari

| Arac | Durum | Detay |
|------|-------|-------|
| ruff check | PASS | Hata yok |
| ruff format | PASS | Formatlanmis |
| mypy | PASS | Strict mode, hata yok |

## API Kontrat Uyumu

Bu feature agent katmaninda olup REST/WS API endpoint icermedigi icin kontrat dogrulamasi uygulanmamistir.

## Notlar

- Maestro CLI'in host makinede yuklu olmasi gerekmektedir
- iOS testleri icin Xcode + iOS Simulator, Android icin ADB gereklidir
- Screenshot toplama Maestro'nun CWD/.maestro/screenshots veya konfigurdeki screenshots_dir'den yapilir
- Sonraki agent (tester) icin: Tum aksiyonlar (run_flow, run_all_flows, take_screenshot, list_flows, validate_flow) icin unit testler yazilmalidir. Mock subprocess, mock S3 uploader ve gecici dosya sistemi kullanilmalidir.
