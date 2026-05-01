# Claude Code Usage Tracking — Reference

> Claude Code CLI'dan 5-saatlik ve 7-gunluk usage yuzdesini cikarmak icin teknik referans. iOS tarafinda usage gostergesi/uyari sistemi yazarken bu dokumana basvur.

## Kaynak

- Claude Code v2.1.80+ statusline JSON'una `rate_limits` alani ekledi.
- Bu alan **sadece statusline script'ine stdin uzerinden** verilir. `-p` (print) modu, `--init-only`, REST API'sinin hicbiri bu yuzdeleri direkt vermez.
- `claude -p --output-format stream-json` ciktisindaki `rate_limit_event.rate_limit_info` yalnizca `status` (allowed/warning/exceeded) ve `resetsAt` icerir — yuzde yoktur.

## Statusline JSON Sekli

Claude Code statusline script'ini her render'da spawn eder ve stdin'e su JSON'i basar (kisaltilmis):

```json
{
  "session_id": "uuid",
  "model": { "id": "claude-opus-4-7[1m]", "display_name": "Opus 4.7 (1M context)" },
  "version": "2.1.126",
  "cost": {
    "total_cost_usd": 0,
    "total_duration_ms": 6696,
    "total_api_duration_ms": 0
  },
  "context_window": {
    "context_window_size": 1000000,
    "current_usage": { "input_tokens": 6, "output_tokens": 4, "cache_creation_input_tokens": 32011, "cache_read_input_tokens": 0 },
    "used_percentage": 3,
    "remaining_percentage": 97
  },
  "rate_limits": {
    "five_hour": { "used_percentage": 90, "resets_at": 1777657800 },
    "seven_day": { "used_percentage": 22, "resets_at": 1778166000 }
  },
  "effort": { "level": "xhigh" },
  "fast_mode": false
}
```

| Alan | Anlam |
|------|-------|
| `rate_limits.five_hour.used_percentage` | Subscription'in 5-saatlik penceresinde harcanmis % (0–100+, overage durumunda 100'u asabilir) |
| `rate_limits.five_hour.resets_at` | Unix timestamp (saniye), pencerenin sifirlanma ani |
| `rate_limits.seven_day.used_percentage` | Haftalik kotanin harcanmis % |
| `rate_limits.seven_day.resets_at` | Haftalik kotanin sifirlanma ani |
| `context_window.used_percentage` | Mevcut konusmanin context window kullanimi (rate limit DEGIL) |
| `cost.total_cost_usd` | Bu session'in calculated API cost'u (subscription'da bilgilendirme amacli) |

## Onemli Tuzaklar

1. **`rate_limits` ilk API call'dan once BOSTUR.** Yeni acilan session'in ilk statusline render'inda alan ya yok ya da bos. Kullanici bir mesaj gonderip model cevap verdikten sonra dolar.
2. **Statusline sadece interactive modda fire eder.** `claude -p`, `claude --init-only`, `claude --bare` statusline'i tetiklemez.
3. **TTY gerekli.** Headless ortamda calistirmak icin `script -q /dev/null` veya `expect` ile pty saglanmali.
4. **API key kullanicilarinda yuzde GELMEZ.** Sadece subscription (Pro/Max/Team/Enterprise) hesaplarinda dolar. `apiKeySource: "anthropic"` durumunda `rate_limits` yoktur.

## Host Agent / Backend Entegrasyonu

iOS app'in RafRaf usage badge'i icin onerilen pipeline:

1. **Host Agent** (Mac/Ubuntu): yerel Claude Code'un statusline'ina bir Python script bagla.
2. Script statusline JSON'unu okur, `rate_limits`'i bir dosyaya yazar (`~/.claude/usage.json`).
3. Host Agent dosyayi watch eder veya periyodik okur, **Backend'e** push eder (yeni mesaj turu: `claude_usage_report`).
4. Backend WebSocket uzerinden iOS client'a forward eder.
5. iOS `RFUsageGauge` componenti ile gosterir (5h ve 7d icin iki ring).

### Tazeleme Stratejisi

`usage.json` sadece aktif session'da render olduginda guncellenir. Up-to-date tutmak icin:

- **Pasif:** Kullanici zaten Claude Code'la calisiyorsa dosya taze kalir.
- **Aktif probe:** 5–10 dakikada bir minimal bir headless oturum acip kapatmak. Maliyet: tek bir `"hi"` cevabi (~%0.1 5h tuketimi). `expect` script'i ile:

```bash
spawn claude --name __usage_probe
expect -timeout 30 "❯"
send "hi\r"
expect -timeout 60 "Opus"
sleep 3
send "\x03"; sleep 1; send "\x03"
expect eof
```

Probe maliyetinden kacinmak istiyorsan: kullanici mevcut session'da ne zaman mesaj gonderirse o zaman push et — gercek zamanli olmasi sart degil, yuzdeler zaten yavas hareket eder.

## Statusline Script (referans implementation)

`~/.claude/statusline.py`:

```python
#!/usr/bin/env python3
import json, os, sys, time

try:
    raw = sys.stdin.read()
    data = json.loads(raw) if raw.strip() else {}
except Exception:
    data = {}

rl = data.get("rate_limits") or {}
fh = (rl.get("five_hour") or {}).get("used_percentage")
sd = (rl.get("seven_day") or {}).get("used_percentage")

with open(os.path.expanduser("~/.claude/usage.json"), "w") as f:
    json.dump({
        "five_hour_pct": fh,
        "seven_day_pct": sd,
        "five_hour_resets_at": (rl.get("five_hour") or {}).get("resets_at"),
        "seven_day_resets_at": (rl.get("seven_day") or {}).get("resets_at"),
        "ts": int(time.time()),
        "raw": rl,
    }, f)

parts = []
model = (data.get("model") or {}).get("display_name")
if model: parts.append(model)
if fh is not None: parts.append(f"5h:{round(fh)}%")
if sd is not None: parts.append(f"7d:{round(sd)}%")
print(" | ".join(parts))
```

`~/.claude/settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "~/.claude/statusline.py"
  }
}
```

## iOS Tarafi (Planlama Notlari)

- DTO: `ClaudeUsageDTO { fiveHourPct: Int, sevenDayPct: Int, fiveHourResetsAt: Date, sevenDayResetsAt: Date }` — `cache_creation_input_tokens` gibi token detaylari iOS'ta gerekmez, sadece yuzdeler.
- Domain entity: `ClaudeUsage` (frozen struct, `Equatable`).
- Use case: `ObserveClaudeUsageUseCase` (WebSocket stream, en son degeri tutar).
- Presentation: `RFUsageGauge` (iki concentric ring: 5h ve 7d, threshold renkleri 0–60% green, 60–85% yellow, 85–100% red).
- Lokalizasyon anahtarlari: `usage.fiveHour.title`, `usage.fiveHour.resetsIn`, `usage.weekly.title`, `usage.weekly.resetsIn`.
- 5h %85+ olunca `RFAlertBanner` ile uyari (kullanici uzun bir tasks queue tetiklemeden once gorsun).

## Referanslar

- [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference)
- [Statusline rate limits announcement (v2.1.80)](https://nyosegawa.com/en/posts/claude-code-statusline-rate-limits/)
- [How do usage and length limits work?](https://support.claude.com/en/articles/11647753-how-do-usage-and-length-limits-work)
- [stream-json event cheatsheet](https://takopi.dev/reference/runners/claude/stream-json-cheatsheet/)

## Degisiklik Gecmisi

- **2026-05-01** — Ilk surum. Empirical olarak v2.1.126'da dogrulandi (Opus 4.7, Max plan).
