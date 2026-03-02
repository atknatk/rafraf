# Developer Handoff: Docker Runner (compose up/down/logs/health)

**Issue**: #14
**Branch**: feature/f2/14-docker-runner
**Tarih**: 2026-03-02
**Sonraki Agent**: tester

## Yapilan Degisiklikler

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `apps/agent/agent/runners/base.py` | CREATE | BaseRunner abstract sinifi - tum runner'lar icin ortak arayuz |
| `apps/agent/agent/runners/docker_runner.py` | CREATE | DockerRunner + ProjectEntry + DockerRunnerError |
| `apps/agent/agent/runners/__init__.py` | MODIFY | Runner registry - public API export |
| `apps/agent/pyproject.toml` | MODIFY | types-docker dev dependency eklendi |

## Dogrulama Sonuclari

| Arac | Durum | Detay |
|------|-------|-------|
| ruff check | PASS | Tum kontroller gecti |
| mypy | PASS | Strict mode, 12 dosya kontrol edildi |

## Notlar

- BaseRunner abstract sinifi gelecek runner'lar (shell, playwright, maestro) icin de kullanilabilir
- DockerRunner.execute() metodu 6 aksiyonu destekler: compose_up, compose_down, compose_restart, compose_logs, health_check, container_status
- Docker SDK (blocking) islemleri asyncio.run_in_executor ile thread pool'da calistirilir
- Compose CLI (non-blocking) islemleri asyncio.create_subprocess_exec ile calistirilir
- Izin verilen compose dosyalari konfigurasyondan okunur (guvenlik)
- Timeout handling asyncio.wait_for ile saglanir
- _extract_container_info fonksiyonu Docker SDK bagimliligini azaltmak icin getattr pattern kullanir
