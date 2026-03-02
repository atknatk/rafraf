# Developer Handoff: Resource Monitor (CPU, RAM, Disk)

**Issue**: #19
**Branch**: feature/f2/19-f2-07-resource-monitor-cpu-ram-disk
**Tarih**: 2026-03-02
**Sonraki Agent**: tester

## Yapilan Degisiklikler

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `apps/agent/agent/monitoring/resource_monitor.py` | CREATE | ResourceMonitor sinifi - periyodik izleme, esik alarmlari |
| `apps/agent/agent/core/protocol.py` | MODIFY | AlarmLevel, ResourceAlarm, ResourceReportMessage, ResourceAlarmMessage modelleri ve builder fonksiyonlari |
| `apps/agent/agent/core/config.py` | MODIFY | resource_report_interval, alarm_cpu/memory/disk_threshold ayarlari |
| `apps/agent/agent/main.py` | MODIFY | ResourceMonitor entegrasyonu (start/stop, WS callback) |

## Mimari Kararlar

- **ResourceMonitor** sinifi tek sorumluluk: metrik toplama, esik kontrolu, backend'e raporlama
- **SendCallbackType** callback pattern ile WS bagimliligini gevsetme (loose coupling)
- **AlarmLevel** StrEnum ile WARNING/CRITICAL seviyeleri (>95% CRITICAL, >threshold WARNING)
- **Frozen Pydantic modeller**: ResourceAlarm, ResourceReportMessage, ResourceAlarmMessage
- **Config**: Tum esik degerleri ve raporlama araligi AgentConfig uzerinden ayarlanabilir

## Dogrulama Sonuclari

| Arac | Durum | Detay |
|------|-------|-------|
| ruff check | PASS | Tum kontroller gecti |
| mypy | PASS | Strict mode, 21 dosya kontrol edildi |

## API Kontrat Uyumu

- `shared/api-contracts/ws/agent-messages.json` referans alindi
- ResourceMetrics modeli kontrat ile uyumlu (cpu_usage_percent, memory_usage_percent, disk_usage_percent, disk_free_gb)
- resource_report ve resource_alarm yeni mesaj tipleri (kontrat genisletmesi)

## Notlar

- `psutil` blocking cagrilari `asyncio.to_thread` ile sarmalanmis (mevcut metrics.py)
- Monitor durdurulurken `contextlib.suppress` ile CancelledError yutulur
- active_alarms property'si frozenset dondurur (immutability)
- Esik degerleri: CPU >90%, RAM >85%, Disk >90% (issue kabul kriterleri ile uyumlu)
