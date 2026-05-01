# ADR-0003 — Host agent'ı Python'dan Go'ya port et (`apps/rafraf-bridge/`)

**Status:** Accepted
**Date:** 2026-05-01
**Owner:** The Abi
**Supersedes:** RafRaf v0.1'in `apps/agent/` (Python asyncio daemon)
**Related:** [`10_Production_Pivot_Spec.md`](../10_Production_Pivot_Spec.md) §2.0, [`11_Bridge_Spec.md`](../11_Bridge_Spec.md)

## Context

RafRaf v0.1 host agent (`apps/agent/`, Python 3.12 asyncio daemon, 187 dosya, 21 MB) iki rolü birleştiriyor:

1. **claude bridge**: `claude -p` subprocess'lerini Mac'te çalıştırır, stream-json'u backend'e WS forward eder. (`claude_runner.py` 658 satır.)
2. **Multi-runner host**: Docker, Maestro (mobile testing), Playwright (browser), shell — kullanıcının Mac'inde geniş runner'larla test/demo task'ları.

V1 production pivot (Doc 10 v2.0) ile **#2 scope dışına düştü** (mem0/voice/host-agent vizyon kapatıldı). Geriye sadece #1 kalıyor.

Aynı zamanda kullanıcı **"v0.1'i aktiflestirememistim"** dedi. Sebep büyük olasılıkla:
- Python 3.12 + venv + ~30 dependency setup
- `pip install -e .` + launchd plist + Docker/Maestro/Playwright runners' kurulumu
- 13+ dış servis env var (Anthropic, Deepgram, OpenAI, AWS×3, mem0, APNs×4)

V1'in kullanıcı tarafından **aktif kullanılabilmesi** için install adımı **drastically** sadeleşmeli.

## Decision

`apps/agent/` Python implementation'ı **arşivlenir** (`apps/_archive/agent-python-v0.1/`) ve **Go ile port edilir** → `apps/rafraf-bridge/`.

Yeni bridge:
- **Tek statik binary** (~10-15 MB), `go build` çıkışı, no runtime deps.
- **Sadece claude bridge rolü** — Docker/Maestro/Playwright runners YOK.
- Spike'taki Go prototype (`~/Code/claude-teams-spike/bridge/main.go`, 276 satır) çekirdek başlangıç.
- Python `claude_runner.py` (658 satır)'in domain logic'i (15 tool display name, stream-json parsing, subagent state) Go'ya port edilir.
- Distribution: brew tap (`brew install atknatk/rafraf/rafraf-bridge`) veya signed `.pkg` (Apple Developer ID notarized).
- launchd plist ile auto-start.

Detay: [`11_Bridge_Spec.md`](../11_Bridge_Spec.md).

## Consequences

**Pozitif:**

| Boyut | Python (eski) | Go (yeni) |
|---|---|---|
| Install | Python 3.12 + venv + 30 dep + launchd | **Tek binary + launchd plist** |
| Binary | ~50-100 MB (PyInstaller bundle) | **~10-15 MB** |
| Distribution | Karmaşık | **brew tap veya signed .pkg** |
| Cross-arch | Ayrı build | **Tek `GOARCH` build** |
| Code signing | Bundle yapısı tricky | `codesign --sign` direkt |
| Startup | 2-5 sn (Python imports) | **<100 ms** |
| Memory | 80-150 MB | **10-30 MB** |
| Auto-update | pip lock | **binary replacement** |
| AI yazma kolaylığı | Async runtime kompleks | Goroutine + channel pattern temiz |

→ "Aktiflestirememe" sorununun ana sebebi (install karmaşası) çözülür.

**Negatif:**

- ~1 hafta extra dev süresi (Faz 0.5, paralel ile zarar yok ama plan toplamı 4 → 5 hafta).
- 658 satır Python (`claude_runner.py`) port iş; spike base + RafRaf domain merge.
- Test fixture'lar Python'dan Go'ya re-organize gerekir.
- Go ekosisteminde RafRaf'ın kalan Python kodu (FastAPI backend) aynı dilde değil — repo iki dilli (zaten öyle, ama daha belirgin).

**V2'de geri dönüş kolay**: Bridge kavramı Mac-host'lu deploy'a doğal uyumlu. EKS pod'da çalıştırma denenirse subscription auth Mac keychain'de olduğu için ya bridge kalır ya da BYO API key alternatifine geçilir.

## Alternatives considered

- **A) Python agent'ı koruyup küçültmek**: `apps/agent/` 187 → ~14 .py dosyaya prune. Install karmaşası **devam eder** (Python venv + deps). **Reddedildi** — kullanıcının ana ağrı noktası bu.
- **B) Rust ile yazmak**: tek statik binary, Go'dan da hızlı. AI yazımı Go'dan zor (lifetime/ownership), spike'ta Go bridge zaten yazıldı. **Reddedildi** — gereksiz friction.
- **C) Bun executable**: `bun build --compile`. Bun ekosistem yeterince olgun değil daemon için, code signing sorunlu. **Reddedildi**.
- **D) Apple Container System Service** (XPC): macOS-native ama RafRaf'ın V2 multi-OS hedefiyle çakışır (V3'te Linux desteği gerekebilir). **Reddedildi**.

## Migration notes

- `apps/agent/` rename değil, **mv to archive**: `apps/_archive/agent-python-v0.1/`. Geçmiş referans olarak korunur.
- `apps/rafraf-bridge/` yeni Go module — Faz 0.5 task'ları (T0.5.1-T0.5.13).
- WS protocol uyumlu kalır: bridge ↔ backend mesaj envelope'u Python implementation ile aynı (Doc 11 §4); backend tarafı **değişmez** (Faz 1'de `claude_code_runner.py` RPC adapter olarak güncelleniyor ama protocol envelope sabit).

## References

- Spike Go prototype: `~/Code/claude-teams-spike/bridge/main.go`
- Spike notes: `~/Code/claude-teams-spike/notes/07-bridge-stability.md`
- Bridge full spec: [`docs/11_Bridge_Spec.md`](../11_Bridge_Spec.md)
