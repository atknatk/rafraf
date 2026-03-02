# Developer Handoff: Shell Runner (Whitelist/Blacklist Security)

**Issue**: #16
**Branch**: feature/f2/16-shell-runner
**Tarih**: 2026-03-02
**Sonraki Agent**: tester

## Yapilan Degisiklikler

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `agent/security/whitelist.py` | CREATE | Whitelist kontrolcusu - izin verilen komut pattern'leri |
| `agent/security/blacklist.py` | CREATE | Blacklist + approval kontrolcusu |
| `agent/security/sanitizer.py` | CREATE | Injection korunmasi - metacharacter filtreleme |
| `agent/security/__init__.py` | MODIFY | Export'lar guncellendi |
| `agent/runners/shell_runner.py` | CREATE | Guvenlikli shell komut calistirici |
| `agent/runners/__init__.py` | MODIFY | ShellRunner export'u eklendi |

## Dogrulama Sonuclari

| Arac | Durum | Detay |
|------|-------|-------|
| ruff check | PASS | Tum dosyalar temiz |
| mypy | PASS | 5 dosya kontrol edildi, hata yok |

## API Kontrat Uyumu

Bu feature yeni API endpoint gerektirmez. Mevcut agent_command/command_result akisi kullanilir.
Kontrat dogrulama gerekli degil.

## Notlar

- Guvenlik kontrol sirasi: Blacklist -> Injection -> Approval -> Whitelist
- Blacklist en yuksek oncelikli: Blacklist'e eslesen komut asla calistirilmaz
- `shlex.split` ile komut parse edilir, `create_subprocess_exec` ile calistirilir (shell=False)
- Output truncation: stdout max 5000, stderr max 2000 karakter
- Timeout: varsayilan 60sn, max 300sn (5dk)
- Timeout durumunda process terminate + kill sequence
- Pattern'ler compiled regex olarak cache'lenir (performans)
- Tum siniflar varsayilan pattern'ler ile olusturulabilir (zero-config)
- Tum siniflar ozel pattern'ler ile de olusturulabilir (testability)
