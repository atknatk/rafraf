# 12 — Action Plan & Tasks

> **Amaç**: Faz 0 (Cleanup) ve Faz 0.5 (Bridge port) için detaylı task listesi. Her task için done criteria + etkilenen dosyalar + test komutu + dependency. Yeni Claude session bu doc'u açıp `T0.1`'den başlayabilir.

**Sürüm:** 1.0
**Tarih:** 2026-05-01
**Önkoşul okuma:** [`10_Production_Pivot_Spec.md`](10_Production_Pivot_Spec.md) v2.0 ve [`11_Bridge_Spec.md`](11_Bridge_Spec.md)

---

## 0. İçindekiler

1. [Konvansiyonlar](#1-konvansiyonlar)
2. [İki paralel iz](#2-iki-paralel-iz)
3. [Faz 0 — Cleanup tasks (cleanup-track)](#3-faz-0--cleanup-tasks-cleanup-track)
4. [Faz 0.5 — Bridge port tasks (bridge-track)](#4-faz-05--bridge-port-tasks-bridge-track)
5. [Senkronizasyon noktaları](#5-senkronizasyon-noktaları)
6. [Faz 1-3 high-level özet](#6-faz-1-3-high-level-özet)

---

## 1. Konvansiyonlar

### Task ID

- `T0.X` → Faz 0 task'ları (cleanup)
- `T0.5.X` → Faz 0.5 task'ları (bridge)
- `T1.X`, `T2.X`, `T3.X` → Faz 1, 2, 3 (high-level özet, detay sonra)

### Task şablonu

```
### TX.Y — <Başlık>

**Track:** cleanup | bridge | sequential
**Süre:** ~N saat
**Dependency:** TX.A, TX.B (varsa)
**Etkilenen dosyalar:**
  - path/to/file1
  - path/to/dir/

**Done criteria:**
- [ ] checkpoint 1
- [ ] checkpoint 2

**Test komutu:**
```
$ <command>
```

**Notlar:** ek bağlam, tuzaklar
```

### Branch + commit konvansiyonu

- Branch: `feature/f0/<task-slug>` (örn. `feature/f0/voice-features-prune`)
- Commit: `<type>(<scope>): <summary> [<task-id>]` örn. `chore(ios): remove voice features [T0.3]`
- Type'lar: `chore` (cleanup), `feat` (yeni), `refactor`, `test`, `docs`, `ci`
- Scope'lar: `ios`, `backend`, `bridge`, `infra`, `docs`

### Sıralama

- **Cleanup track** sıralı: T0.1 → T0.2 → ... → T0.14 (içinde paralelleştirilebilir alt-task'lar var)
- **Bridge track** sıralı: T0.5.1 → T0.5.2 → ...
- İki track **birbirinden bağımsız** (Faz 0 + Faz 0.5 paralel ilerler)
- **Senkron noktası**: Faz 0 + Faz 0.5 done → Faz 1 başlar (§5)

---

## 2. İki paralel iz

```
Hafta 1                    Hafta 2
┌───────────────────────┐  ┌───────────────────┐
│ Faz 0 — cleanup-track │  │ Faz 1 (sequential)│
│ T0.1 → T0.14          │──┐                   │
└───────────────────────┘  │                   │
┌───────────────────────┐  ├──→  Faz 1 başlar  │
│ Faz 0.5 — bridge-track│  │     (T0+T0.5 done)│
│ T0.5.1 → T0.5.13      │──┘                   │
└───────────────────────┘  └───────────────────┘
```

Cleanup-track ve bridge-track aynı repo'da farklı branch'lerde paralel ilerler. Merge'ler `develop` branch'ine.

---

## 3. Faz 0 — Cleanup tasks (cleanup-track)

### T0.1 — Pre-flight: DB dump + branch hazırlığı

**Track:** cleanup
**Süre:** 30 dk
**Dependency:** —
**Etkilenen dosyalar:**
- `~/Code/rafraf-backups/<date>.sql.gz` (yeni)
- `infra/scripts/backup-dev-db.sh` (yoksa yarat)

**Done criteria:**
- [ ] Backend dev DB'sinin dump'ı alındı (`pg_dump`), gzip'lendi, `~/Code/rafraf-backups/`'a kaydedildi
- [ ] Backup boyutu kontrol: en az 100 KB (boş değil)
- [ ] The Abi'ye sorulup teyit alındı: "55 proje gerçek mi test data mı?" (Doc 10 §9.4)
- [ ] Cleanup branch'ı açıldı: `git checkout -b feature/f0/cleanup`

**Test komutu:**
```bash
ls -lh ~/Code/rafraf-backups/
```

**Notlar:** Gerçek data'sa Faz 1'de schema migration plan değişir. Test data'sa fixtures'a düşer.

---

### T0.2 — log/seed cleanup

**Track:** cleanup
**Süre:** 15 dk
**Dependency:** T0.1
**Etkilenen dosyalar:**
- `log.txt` (sil — 32 KB, geçici dev log'u)
- `seed.md` (Vault'a taşı + sil — credentials içeriyor)
- `.gitignore` (`log.txt`, `log2.txt` zaten orada mı kontrol)

**Done criteria:**
- [ ] `seed.md` içeriği 1Password / Mac Keychain'e kaydedildi (creds redacted — see seed.md backup)
- [ ] `seed.md` ve `log.txt` repo'dan silindi
- [ ] `.gitignore`'da `log*.txt` pattern'i var
- [ ] commit: `chore: remove dev log and seed files [T0.2]`

**Test komutu:**
```bash
git ls-files | grep -E "log\.txt|seed\.md" && echo "STILL TRACKED" || echo "OK"
```

---

### T0.3 — iOS Voice features sil (3 feature)

**Track:** cleanup
**Süre:** 1 saat
**Dependency:** T0.2
**Etkilenen dosyalar:**
- `apps/ios/RafRaf/Features/VoiceInput/` (15 Swift dosyası)
- `apps/ios/RafRaf/Features/VoiceOutput/` (18 Swift dosyası)
- `apps/ios/RafRaf/Features/VoiceConversation/` (3 Swift dosyası)
- `apps/ios/RafRaf/Core/Voice/` (varsa, kontrol)
- `apps/ios/project.yml` (Voice referansları)
- `apps/ios/RafRaf/App/` — Voice feature import'ları

**Done criteria:**
- [ ] 3 feature klasörü silindi
- [ ] `Core/Voice/` (varsa) silindi
- [ ] `project.yml`'de Voice referansları kaldırıldı, `xcodegen generate` çalıştı
- [ ] `xcodebuild build -scheme RafRaf` exit 0
- [ ] commit: `chore(ios): remove voice features [T0.3]`

**Test komutu:**
```bash
cd apps/ios && xcodebuild -scheme RafRaf -destination 'generic/platform=iOS' build CODE_SIGN_IDENTITY="" CODE_SIGNING_REQUIRED=NO
```

**Notlar:** Voice DI registrations'ı (Factory) ayrıca temizlenmeli — `Core/DI/`'da `VoiceContainer` veya benzeri varsa kaldır.

---

### T0.4 — iOS Host-agent-bağlı features sil (ScreenshotViewer, FileSharing, Pulse, Monitoring)

**Track:** cleanup
**Süre:** 1.5 saat
**Dependency:** T0.3
**Etkilenen dosyalar:**
- `apps/ios/RafRaf/Features/ScreenshotViewer/` (11 Swift)
- `apps/ios/RafRaf/Features/FileSharing/` (17 Swift)
- `apps/ios/RafRaf/Features/Pulse/` (varsa, kontrol)
- `apps/ios/RafRaf/Features/Monitoring/` (7 Swift)
- `project.yml`

**Done criteria:**
- [ ] 4 feature klasörü silindi
- [ ] `xcodebuild` build temiz
- [ ] commit: `chore(ios): remove host-agent dependent features [T0.4]`

**Test komutu:** aynı T0.3

---

### T0.5 — iOS Project/Tasks/Progress merge & sil

**Track:** cleanup
**Süre:** 3 saat (en uzun iOS task'ı — manuel inceleme)
**Dependency:** T0.4
**Etkilenen dosyalar:**
- `apps/ios/RafRaf/Features/Project/` (21 Swift) → incele, sonra sil
- `apps/ios/RafRaf/Features/Tasks/` (12 Swift) → useful View'lar Agent'a merge
- `apps/ios/RafRaf/Features/Progress/` (12 Swift) → useful View'lar Agent'a merge
- `apps/ios/RafRaf/Features/Agent/Presentation/Components/` (yeni component'lar buraya)

**Done criteria:**
- [ ] Tasks feature'ından `TaskStatus.swift`, `RFToolStatusView.swift` (subagent task display için kullanışlı) Agent feature'a taşındı
- [ ] Progress feature'ından Live Activity ile bağlı View'lar Agent'a taşındı
- [ ] Project feature komple silindi
- [ ] Tasks ve Progress klasörleri silindi
- [ ] `xcodebuild` build temiz
- [ ] commit: `refactor(ios): merge useful views into Agent feature, drop Project [T0.5]`

**Test komutu:** aynı T0.3

**Notlar:** Bu en risk'li task. Acele etmek yerine her View'ı tek tek incele. 296 → ~180 Swift dosya.

---

### T0.6 — iOS TaskStatusContent decode hatası fix

**Track:** cleanup (small fix)
**Süre:** 30 dk
**Dependency:** T0.5
**Etkilenen dosyalar:**
- `apps/ios/RafRaf/Core/Networking/WebSocketMessage.swift` (TaskStatusContent struct, ~satır 130+)

**Done criteria:**
- [ ] `TaskStatusContent` struct'ına `enum CodingKeys: String, CodingKey { case taskId = "task_id"; case status; ... }` eklendi
- [ ] Aynı pattern tüm WebSocketContent struct'larında doğrulandı (snake_case ↔ camelCase)
- [ ] Unit test eklendi (Swift Testing): JSON snake_case → struct decode
- [ ] commit: `fix(ios): TaskStatusContent decode key mismatch [T0.6]`

**Test komutu:**
```bash
cd apps/ios && xcodebuild test -scheme RafRaf -destination 'platform=iOS Simulator,name=iPhone 15'
```

**Notlar:** log.txt'de gözlenen `keyNotFound(taskId)` hatası bu fix'le çözülür. Doc 10 §6.3.1.

---

### T0.7 — Backend Voice ve mem0 services sil

**Track:** cleanup
**Süre:** 1 saat
**Dependency:** T0.6
**Etkilenen dosyalar:**
- `apps/backend/app/services/memory_service.py` (sil, 594 satır)
- `apps/backend/app/services/conversation_memory_service.py` (sil, 508)
- `apps/backend/app/services/personal_memory_service.py` (sil, 418)
- `apps/backend/app/services/project_memory_service.py` (sil, 426)
- `apps/backend/app/main.py` (mem0 ve voice import'ları)
- `apps/backend/pyproject.toml` (`mem0ai` dependency)

**Done criteria:**
- [ ] 4 mem0 service silindi
- [ ] Voice service varsa silindi (`apps/backend/app/services/`'te `voice_*.py` veya `tts_service.py`)
- [ ] `main.py` import'ları temizlendi
- [ ] `pyproject.toml`'dan `mem0ai>=0.1.0` kaldırıldı, `pip install -e .` re-run, lock güncel
- [ ] `pytest` pass (mem0 test'leri silindi)
- [ ] commit: `chore(backend): remove mem0 and voice services [T0.7]`

**Test komutu:**
```bash
cd apps/backend && uv pip install -e . && pytest -x
```

---

### T0.8 — Backend cost/analytics/maestro/pulse sil

**Track:** cleanup
**Süre:** 1 saat
**Dependency:** T0.7
**Etkilenen dosyalar:**
- `apps/backend/app/services/{analytics,cost,cost_alert,maestro,pulse}_service.py` (5 dosya)
- `apps/backend/app/api/routes/{analytics,cost,cost_alerts,memory,personal_memory,conversation_memory,maestro,pulse,monitoring,subscription}.py` (10 route)
- `apps/backend/app/tools/{memory_tool,cost_tool}.py` (2 tool)
- `apps/backend/app/main.py` (import'lar + lifespan)

**Done criteria:**
- [ ] 5 service silindi
- [ ] 10 route silindi
- [ ] 2 tool silindi
- [ ] `main.py` import'ları + router include'ları temizlendi
- [ ] `pytest` pass
- [ ] commit: `chore(backend): remove cost/analytics/maestro/pulse services and routes [T0.8]`

**Test komutu:**
```bash
cd apps/backend && pytest -x && python -c "from app.main import app; print('OK')"
```

---

### T0.9 — Backend host_agent_tool ve model_router sil

**Track:** cleanup
**Süre:** 30 dk
**Dependency:** T0.8
**Etkilenen dosyalar:**
- `apps/backend/app/tools/host_agent_tool.py` (sil)
- `apps/backend/app/orchestrator/model_router.py` (sil)
- `apps/backend/app/main.py` — `_register_host_agent_tool()` fonksiyonu sil + lifespan'daki çağrı
- `claude_code_runner.py` veya `orchestrator/agent.py` — model_router kullanan yerler

**Done criteria:**
- [ ] `host_agent_tool.py` silindi
- [ ] `model_router.py` silindi
- [ ] `_register_host_agent_tool()` ve çağrıları silindi
- [ ] **DİKKAT**: `agent_registry_service.py` **TUT** (Doc 10 v2.0). Faz 1'de iç logic değiştirilecek (host agent → bridge registry), ama dosya silinmez.
- [ ] `pytest` pass
- [ ] commit: `chore(backend): remove host_agent_tool and model_router [T0.9]`

**Test komutu:**
```bash
cd apps/backend && pytest -x && grep -r "host_agent_tool\|model_router" app/ --include="*.py"
# beklenen: hiçbir referans kalmamış (test dosyaları hariç, onlar da bu task'ta sileceğiz)
```

---

### T0.10 — Host agent (apps/agent/) archive

**Track:** cleanup
**Süre:** 30 dk
**Dependency:** T0.9
**Etkilenen dosyalar:**
- `apps/agent/` → `apps/_archive/agent-python-v0.1/` (rename)
- `infra/docker/docker-compose.dev.yml` — agent service block kaldır
- `Makefile` — agent target'ları sil
- `.github/workflows/` — agent CI workflow varsa sil

**Done criteria:**
- [ ] `apps/agent/` arşive taşındı (silinmedi — Bridge port sırasında referans olarak kullanılacak)
- [ ] `apps/_archive/agent-python-v0.1/README.md` eklendi: "Faz 0.5'te apps/rafraf-bridge'e port edildi, kaynak referans olarak korundu"
- [ ] `docker-compose.dev.yml`'de agent service yok
- [ ] `Makefile` agent target'ları yok
- [ ] commit: `chore: archive python host agent (preserved as bridge port reference) [T0.10]`

**Test komutu:**
```bash
docker compose -f infra/docker/docker-compose.dev.yml config | grep -c "agent" || echo "OK"
```

---

### T0.11 — mem0 docker + dependencies cleanup

**Track:** cleanup
**Süre:** 30 dk
**Dependency:** T0.10
**Etkilenen dosyalar:**
- `infra/docker/mem0/` (sil)
- `infra/docker/docker-compose.dev.yml` — mem0 service + volume
- `infra/docker/initdb/` — pgvector init script varsa
- `apps/backend/pyproject.toml` (zaten T0.7'de mem0ai çıkarıldı, bu adım docker side)

**Done criteria:**
- [ ] `infra/docker/mem0/` silindi
- [ ] docker-compose'dan mem0 + pgvector init kaldırıldı
- [ ] `docker compose up` temiz başlıyor (mem0 container yok)
- [ ] commit: `chore(infra): remove mem0 docker setup [T0.11]`

**Test komutu:**
```bash
docker compose -f infra/docker/docker-compose.dev.yml up -d
docker compose ps
docker compose down
```

---

### T0.12 — Alembic migration cleanup

**Track:** cleanup
**Süre:** 1 saat (dikkatli — DB schema değişiyor)
**Dependency:** T0.11 + T0.1 (DB dump şart)
**Etkilenen dosyalar:**
- `apps/backend/alembic/versions/002_add_cost_logs_table.py` (incele — drop migration yaz)
- `apps/backend/alembic/versions/004_add_remaining_tables.py` (mem0 tabloları varsa drop)
- `apps/backend/alembic/versions/008_add_pulse_reports_table.py` (drop)
- `apps/backend/alembic/versions/010_add_agent_dangerously_skip_permissions.py` (host agent kolonları, drop)
- Yeni: `013_drop_legacy_tables.py` (cost_logs, pulse_reports, mem0 tabloları drop)

**Done criteria:**
- [ ] Yeni migration yazıldı: `013_drop_legacy_tables.py` (down: revert işe yarar — schema dump'tan geri yüklenir)
- [ ] `alembic upgrade head` çalışıyor (dev DB'de)
- [ ] `alembic downgrade -1` ve `upgrade head` test edildi (idempotent)
- [ ] commit: `chore(backend): drop legacy tables (cost_logs, pulse_reports, mem0) [T0.12]`

**Test komutu:**
```bash
cd apps/backend && alembic upgrade head && alembic downgrade -1 && alembic upgrade head
```

**Notlar:** Production DB'de bu migration uygulanmadan önce ayrı bir DB dump alınmalı. Faz 3'e kadar production yok.

---

### T0.13 — `.env.example` revize

**Track:** cleanup
**Süre:** 15 dk
**Dependency:** T0.12
**Etkilenen dosyalar:**
- `apps/backend/.env.example` (root düzeyinde de varsa o)
- `.env` (kullanıcının lokal dosyası — sadece info)

**Done criteria:**
- [ ] **SİL**: `DEEPGRAM_API_KEY`, `OPENAI_API_KEY`, `USE_BEDROCK`, `AGENT_API_KEY`
- [ ] **TUT**: `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET_KEY`, `BACKEND_WS_URL`, `APNS_*` (5 var), `GITHUB_TOKEN`, `AWS_*` (S3 backups)
- [ ] **OPSİYONEL TUT**: `ANTHROPIC_API_KEY` (yorum: "fallback only, V1'de subscription kullanır")
- [ ] **EKLE**: `CLAUDE_CODE_ENABLED=true`, `CLAUDE_CODE_BINARY=claude`, `CLAUDE_CODE_PROJECT_DIR`, `CLAUDE_CODE_MODEL=opus`, `CLAUDE_CODE_TIMEOUT_SECONDS=300`, `CLAUDE_CODE_PERMISSION_MODE=acceptEdits`, `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`
- [ ] commit: `chore: trim .env.example to V1 scope [T0.13]`

**Test komutu:** manual review

---

### T0.14 — Docs cleanup (ARCHIVED notu)

**Track:** cleanup
**Süre:** 30 dk
**Dependency:** T0.13
**Etkilenen dosyalar:**
- `docs/03_AI_Agent_Tool_Layer_Specification.md`
- `docs/05_Memory_System_Specification.md`
- `docs/08_Host_Agent_Specification.md`

**Done criteria:**
- [ ] Her doc'un başına eklenecek block:
  ```markdown
  > **⚠️ ARCHIVED — V2'ye ertelendi.** Bu doc RafRaf'ın v0.1 vizyonuna ait;
  > V1'de scope dışı (bkz. [`10_Production_Pivot_Spec.md`](10_Production_Pivot_Spec.md) §5).
  > V2'de güncellenecek.
  ```
- [ ] commit: `docs: mark v0.1 specs as ARCHIVED [T0.14]`

**Test komutu:** —

---

### Faz 0 Sonu — entegrasyon testi

Faz 0 son commit'inden sonra:

```bash
# Build temiz
cd apps/backend && pytest -x
cd ../ios && xcodebuild build -scheme RafRaf

# Repo boyutu
du -sh . | tee /tmp/repo-size-after-faz0.txt
# Beklenen: ~600 MB (823 → -200 MB)

# Hiç eski referans kalmamış
grep -rE "DEEPGRAM|OPENAI_API|mem0ai|host_agent_tool|model_router|VoiceInput|maestro_service" \
     --include="*.py" --include="*.swift" --include="*.toml" --include="*.yml" \
     | grep -v _archive
# beklenen: minimal output (sadece archive/ ve docs/ ARCHIVED notları)
```

**Faz 0 done = bridge-track ile sync noktası (§5).**

---

## 4. Faz 0.5 — Bridge port tasks (bridge-track)

**Branch**: `feature/f0.5/bridge-port` (Faz 0 ile paralel, develop'tan branch)

### T0.5.1 — Repo skeleton + tooling

**Track:** bridge
**Süre:** 1 saat
**Dependency:** T0.10 (apps/agent/ archive done)
**Etkilenen dosyalar:**
- `apps/rafraf-bridge/` (yeni dizin)

**Done criteria:**
- [ ] Klasör yapısı oluşturuldu (Doc 11 §2 listesi)
- [ ] `go.mod` (`module github.com/atknatk/rafraf/apps/rafraf-bridge`, go 1.22+)
- [ ] `cmd/bridge/main.go` minimal: `func main() { fmt.Println("rafraf-bridge", version) }`
- [ ] `Makefile`: `make build`, `make test`, `make lint`, `make pkg`
- [ ] `.golangci.yml` (errcheck, gofmt, govet, ineffassign, staticcheck, unused)
- [ ] `go build ./...` exit 0
- [ ] `golangci-lint run` exit 0 (warnings yok)
- [ ] `README.md` skeleton
- [ ] commit: `feat(bridge): add rafraf-bridge skeleton [T0.5.1]`

**Test komutu:**
```bash
cd apps/rafraf-bridge && make build test lint
```

---

### T0.5.2 — Spike Go bridge'i base import et

**Track:** bridge
**Süre:** 1 saat
**Dependency:** T0.5.1
**Etkilenen dosyalar:**
- `apps/rafraf-bridge/internal/ws/client.go` (spike `bridge/main.go`'dan WSClient struct port)
- `apps/rafraf-bridge/internal/protocol/envelope.go` (spike Envelope struct port)
- `apps/rafraf-bridge/cmd/bridge/main.go` (spike main yapısından adapt)
- `apps/rafraf-bridge/go.sum` (`coder/websocket` v1.8.13, `google/uuid`)

**Done criteria:**
- [ ] `~/Code/claude-teams-spike/bridge/main.go` referans alınarak split:
  - WSClient → `internal/ws/client.go`
  - Envelope → `internal/protocol/envelope.go`
  - Metric'ler → `internal/telemetry/metrics.go`
  - main entry → `cmd/bridge/main.go`
- [ ] `coder/websocket` v1.8.13 + `google/uuid` v1.6 dep
- [ ] Mock control plane'e (spike `mock-control-plane/server.ts`) bağlanma testi: `make build && ./bridge/bridge --soak-secs 30 --emit-alive`
- [ ] commit: `feat(bridge): import spike WS client and envelope structures [T0.5.2]`

---

### T0.5.3 — config package

**Track:** bridge
**Süre:** 2 saat
**Dependency:** T0.5.2
**Etkilenen dosyalar:**
- `apps/rafraf-bridge/internal/config/config.go`
- `apps/rafraf-bridge/internal/config/config_test.go`

**Done criteria:**
- [ ] `Config` struct (Doc 11 §3.1) + nested config'ler
- [ ] `Load(path)` ve `Validate()` fonksiyonları
- [ ] BurntSushi/toml dep
- [ ] Test: valid + invalid + missing path için
- [ ] `~/.config/rafraf-bridge/config.toml` example asset (`go:embed`)
- [ ] commit: `feat(bridge): config package with TOML loading [T0.5.3]`

---

### T0.5.4 — protocol package

**Track:** bridge
**Süre:** 3 saat
**Dependency:** T0.5.3
**Etkilenen dosyalar:**
- `apps/rafraf-bridge/internal/protocol/{envelope,messages,builder}.go`
- `apps/rafraf-bridge/internal/protocol/envelope_test.go`

**Done criteria:**
- [ ] Envelope struct (Doc 11 §3.3'teki Envelope)
- [ ] Inbound: `CommandClaudeRun`, `CommandClaudeAbort` struct'lar
- [ ] Outbound: `EventSession*`, `EventStorage*`, `EventUsageReport`, `EventBridge*` struct'lar (Doc 11 §3.3'te listed)
- [ ] Builder helper'lar (`NewCommand(...)`, `NewEvent(...)` — Python `build_claude_stream_*_message` eşdeğeri)
- [ ] JSON marshal/unmarshal test (RafRaf Pydantic snake_case ile uyumlu)
- [ ] commit: `feat(bridge): protocol envelope and message types [T0.5.4]`

**Test fixture**: `apps/_archive/agent-python-v0.1/agent/core/protocol.py`'nin Python message format'larıyla 1:1 uyum kontrolü.

---

### T0.5.5 — claude.runner package

**Track:** bridge
**Süre:** 4 saat
**Dependency:** T0.5.4
**Etkilenen dosyalar:**
- `apps/rafraf-bridge/internal/claude/runner.go`
- `apps/rafraf-bridge/internal/claude/runner_test.go`

**Done criteria:**
- [ ] `Runner` struct + `Run(ctx, RunRequest, EventSink) error` (Doc 11 §5)
- [ ] Subprocess: `exec.CommandContext("claude", "-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages", "--permission-mode", ...)`
- [ ] Env: `ANTHROPIC_API_KEY` exclude + `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` inject
- [ ] `Abort(sessionID) error` — context cancel + SIGTERM
- [ ] Test: subprocess mock (`ExecCommand` injectable, `cat testdata/01-simple.jsonl`)
- [ ] commit: `feat(bridge): claude.runner subprocess wrapper [T0.5.5]`

---

### T0.5.6 — claude.parser + state package

**Track:** bridge
**Süre:** 4 saat
**Dependency:** T0.5.5
**Etkilenen dosyalar:**
- `apps/rafraf-bridge/internal/claude/parser.go`
- `apps/rafraf-bridge/internal/claude/state.go`
- `apps/rafraf-bridge/internal/claude/parser_test.go`
- `apps/rafraf-bridge/internal/claude/testdata/*.jsonl` (spike'tan kopyala)

**Done criteria:**
- [ ] Parser line-by-line scanner, 16 MiB max line buffer
- [ ] `StreamState` struct (Doc 11 §6) — subagent map, rate limit, cost
- [ ] Event dispatch: 11+ event tipi (system/init, task_started, task_progress, task_notification, hook_started, hook_response, status, assistant, user, stream_event, rate_limit_event, result)
- [ ] Test fixture: spike `~/Code/claude-teams-spike/results/02-agent-teams/run-1.jsonl` → 3 task_started + 3 task_notification doğrulama
- [ ] Test: malformed JSON line → log warning, akış devam
- [ ] commit: `feat(bridge): stream-json parser and state tracking [T0.5.6]`

---

### T0.5.7 — claude.tool_display + alias

**Track:** bridge
**Süre:** 1 saat
**Dependency:** T0.5.6
**Etkilenen dosyalar:**
- `apps/rafraf-bridge/internal/claude/tool_display.go`
- `apps/rafraf-bridge/internal/claude/alias.go`
- `apps/rafraf-bridge/internal/claude/tool_display_test.go`

**Done criteria:**
- [ ] `ToolDisplayNames` map — 25+ tool için Türkçe display name (Doc 11 §6, Python `_TOOL_DISPLAY_NAMES`'tan port)
- [ ] `CanonicalToolName(name) string` — Task → Agent aliasing (Doc 10 §2.10/C)
- [ ] `DisplayName(name) string` — alias + display lookup, MCP fallback ("MCP aracı çalıştırılıyor")
- [ ] Test: 25+ tool input → expected display
- [ ] commit: `feat(bridge): tool display names and Task/Agent aliasing [T0.5.7]`

---

### T0.5.8 — storage.watcher package

**Track:** bridge
**Süre:** 3 saat
**Dependency:** T0.5.7
**Etkilenen dosyalar:**
- `apps/rafraf-bridge/internal/storage/watcher.go`
- `apps/rafraf-bridge/internal/storage/parser.go`
- `apps/rafraf-bridge/internal/storage/watcher_test.go`
- `go.mod` — `fsnotify/fsnotify` dep

**Done criteria:**
- [ ] `Watcher` struct (Doc 11 §7)
- [ ] fsnotify ile `~/.claude/projects/` izleme
- [ ] Tail offset tracking per file (path → byte offset)
- [ ] InterestedTypes filter: ai-title, pr-link, attachment(hook_*)
- [ ] `MaxFileAge` ile eski dosyaları skip (30 gün default)
- [ ] Test: temp dir + fake jsonl → ai-title yazıp event yakalama
- [ ] commit: `feat(bridge): storage watcher for ~/.claude/projects/ [T0.5.8]`

---

### T0.5.9 — statusline.watcher + installer

**Track:** bridge
**Süre:** 3 saat
**Dependency:** T0.5.8
**Etkilenen dosyalar:**
- `apps/rafraf-bridge/internal/statusline/watcher.go`
- `apps/rafraf-bridge/internal/statusline/installer.go`
- `apps/rafraf-bridge/internal/statusline/assets/statusline.py` (embed)
- `apps/rafraf-bridge/internal/statusline/watcher_test.go`

**Done criteria:**
- [ ] `Watcher.Run` — 5s polling, mod time check
- [ ] `EventUsageReport` emission
- [ ] `InstallStatuslineScript(claudeDir)` — `~/.claude/statusline.py` write + `settings.json` merge-safe patch
- [ ] `statusline.py` content [`docs/claude-code-usage-tracking.md`](claude-code-usage-tracking.md)'den embed
- [ ] Test: temp dir + fake usage.json → event yakalama; settings.json patch idempotent
- [ ] commit: `feat(bridge): statusline watcher and installer [T0.5.9]`

---

### T0.5.10 — security.sandbox (opsiyonel V1)

**Track:** bridge
**Süre:** 2 saat (opsiyonel — V1.1'e ertelenebilir)
**Dependency:** T0.5.9
**Etkilenen dosyalar:**
- `apps/rafraf-bridge/internal/security/sandbox.go`
- `apps/rafraf-bridge/internal/security/sandbox_test.go`

**Done criteria:**
- [ ] Shell command whitelist port (Python `apps/_archive/agent-python-v0.1/agent/security/`'den)
- [ ] V1'de sadece **denylist** (write/bash/edit subagent'larda block edilebilir)
- [ ] Test: whitelist match + edge cases
- [ ] commit: `feat(bridge): security sandbox (denylist V1) [T0.5.10]`

**Notlar:** Subagent permission'ı claude CLI tarafında handle ediliyor olabilir; V1 launch sırasında doğrulanır. Eğer claude CLI yeterli ise bu task **skip**.

---

### T0.5.11 — telemetry.metrics

**Track:** bridge
**Süre:** 2 saat
**Dependency:** T0.5.10 veya T0.5.9
**Etkilenen dosyalar:**
- `apps/rafraf-bridge/internal/telemetry/metrics.go`
- `apps/rafraf-bridge/internal/telemetry/logging.go`

**Done criteria:**
- [ ] `expvar` exports (Doc 11 §9 listesi — 20+ metric)
- [ ] `slog` veya `zerolog` structured logging
- [ ] `/debug/vars` endpoint, 127.0.0.1:9090 (config'le aç/kapat)
- [ ] commit: `feat(bridge): telemetry metrics and logging [T0.5.11]`

---

### T0.5.12 — Packaging (launchd plist + brew formula + signed pkg)

**Track:** bridge
**Süre:** 4 saat
**Dependency:** T0.5.11
**Etkilenen dosyalar:**
- `apps/rafraf-bridge/packaging/launchd/com.rafraf.bridge.plist`
- `apps/rafraf-bridge/packaging/homebrew/rafraf-bridge.rb`
- `apps/rafraf-bridge/packaging/pkg/{distribution.xml,scripts/{preinstall,postinstall}.sh,build-pkg.sh}`
- `apps/rafraf-bridge/scripts/install-bridge.sh` (geliştirme için)

**Done criteria:**
- [ ] launchd plist (Doc 11 §11.1)
- [ ] Brew formula (Doc 11 §11.2) — local test: `brew install --build-from-source ./rafraf-bridge.rb`
- [ ] `build-pkg.sh` çalışıyor — `make pkg` ile signed `.pkg` üretiliyor (Apple Developer ID gerekli — VT3X56P4ZL)
- [ ] Notarize step (Apple notary service) test edildi (1 successful round-trip)
- [ ] Install flow test: `.pkg` Mac'e install edildi, launchd ile `bridge` çalışıyor (`launchctl list | grep rafraf`)
- [ ] commit: `feat(bridge): packaging — launchd, brew, signed pkg [T0.5.12]`

---

### T0.5.13 — bridge-ci.yml + end-to-end smoke

**Track:** bridge
**Süre:** 3 saat
**Dependency:** T0.5.12
**Etkilenen dosyalar:**
- `.github/workflows/bridge-ci.yml`
- `apps/rafraf-bridge/integration_test.go`

**Done criteria:**
- [ ] CI workflow: `golangci-lint`, `go test ./...`, `go build` (matrix: arm64 + amd64)
- [ ] Release tag'lerde GitHub Release'e prebuilt binary attach
- [ ] Integration test (`//go:build integration` tag): mock CP'ye bağlan + `cat testdata/02-agent-teams.jsonl` ile claude'u simüle et + 3 subagent event'inin SSE consumer'a aktığını doğrula
- [ ] CI matrix: macos-14 (arm64), ubuntu-latest (cross-compile) — local test sonuçları PR comment olarak ekle
- [ ] **End-to-end smoke** (Faz 0.5 done göstergesi):
  - [ ] `apps/rafraf-bridge/bridge` build (~10-15 MB)
  - [ ] launchd plist ile başlat, log: "connected to ws://localhost:8000"
  - [ ] RafRaf backend dev'inde mock task forward → claude -p subprocess → stream-json events → backend'e döndü
- [ ] commit: `ci(bridge): add bridge-ci workflow and end-to-end test [T0.5.13]`

---

### Faz 0.5 Sonu — Bridge done

```bash
cd apps/rafraf-bridge && make build test lint pkg
ls -lh bridge
# Beklenen: ~10-15 MB statik binary
ls -lh dist/
# Beklenen: rafraf-bridge-0.1.0-arm64.pkg (signed + notarized)
```

**Faz 0.5 done = cleanup-track ile sync noktası (§5).**

---

## 5. Senkronizasyon noktaları

### Sync 1 — Faz 0 + 0.5 done

İki track'in birleşmesi. Sync sonrası Faz 1 başlar. Sync checklist:

- [ ] Faz 0 cleanup-track tüm task'lar done (T0.1-T0.14 ✓)
- [ ] Faz 0.5 bridge-track tüm task'lar done (T0.5.1-T0.5.13 ✓)
- [ ] `develop` branch'i: cleanup-track + bridge-track merge edildi
- [ ] iOS `xcodebuild` temiz
- [ ] Backend `pytest` pass
- [ ] Bridge `go test ./...` pass + `go build` 10-15 MB
- [ ] Manuel smoke: bridge install → backend bağlanıyor → iOS chat ekranı eski Python agent yokken çalışıyor

Sync done → Faz 1 başlangıç.

### Sync 2 — Faz 1 done

Backend `claude_code_runner.py` v2.0 RPC adapter olarak çalışıyor; bridge subagent state tutuyor; iOS subagent tree view görünüyor. Detay Faz 1 task listesi sonra (§6'da high-level).

### Sync 3, 4 — Faz 2, 3 done

Sırasıyla observability + production deploy.

---

## 6. Faz 1-3 high-level özet

Detay task'lar Faz 0 + 0.5 done sonrası yazılır. Şimdi sadece outline:

### Faz 1 — Agent Teams entegrasyonu (1 hafta)

- T1.1 — Backend `claude_code_runner.py` v2.0: subprocess kaldırılır, bridge'e RPC. (Doc 10 §6.1.1)
- T1.2 — `claude_stream_manager` bridge ↔ iOS forwarder (yeni service)
- T1.3 — Backend `agent_registry_service` refactor: host_agent → bridge_registry (entity rename, schema migration)
- T1.4 — Yeni alembic: `014_rename_host_agents_to_bridges.py`
- T1.5 — Backend WS schemas: yeni MessageType + Pydantic payload'lar (Doc 10 §6.4)
- T1.6 — iOS WebSocketMessage.swift: 7 yeni MessageType + Content struct'lar
- T1.7 — iOS Agent feature: subagent tree view (OutlineGroup), subagent.spawned/progress/completed handle
- T1.8 — iOS Home feature: ai-title kullanımı (session list başlık)
- T1.9 — iOS RFUsageGauge component (Doc 10 §2.11): two-ring 5h/7d, threshold renkler
- T1.10 — Bridge subagent state DB projection (Faz 1 sonu) — Postgres `subagents` tablosu
- T1.11 — End-to-end test: iOS → backend → bridge → claude (3 subagent spawn) → tüm event'ler iOS'ta görünüyor

### Faz 2 — Production hardening (1 hafta)

- T2.1 — OpenTelemetry tracing (backend + bridge)
- T2.2 — Prometheus metrics (`/metrics` backend, expvar bridge)
- T2.3 — Health/readiness endpoint'ler
- T2.4 — Rate limit middleware adapt (Anthropic 429 handling)
- T2.5 — Cost tracking: alembic `015_session_cost_tracking.py`, `result.total_cost_usd` projection
- T2.6 — DB backup + restore drill (PITR, RPO 24h, RTO 1h)
- T2.7 — `backend-ci.yml` workflow
- T2.8 — Disaster recovery runbook (`docs/runbooks/disaster-recovery.md`)
- T2.9 — JWT RS256 migration (varsa HS256'dan, Doc 10 §7.4)

### Faz 3 — TestFlight + launch (1 hafta)

- T3.1 — iOS UI polish (Agent UI, Live Activity, Approval sheet)
- T3.2 — Permission flow doğrulama (Spike Test 5 fallback ağacı)
- T3.3 — TestFlight build (staging branch)
- T3.4 — Manuel device test (3 saat smoke, crash-free %99+)
- T3.5 — Backend EKS deploy (Helm chart, ArgoCD app)
- T3.6 — Bridge install: kullanıcıya signed `.pkg` ver
- T3.7 — End-to-end production smoke
- T3.8 — Runbook'lar: `deploy.md`, `secret-rotation.md`, `anthropic-cli-upgrade.md`, `manual-test-checklist.md`

---

**Belge sonu.** Faz 0 başlangıç komutu (Faz 0+0.5 paralel için iki branch açılır):

```bash
cd /Users/atakan/Documents/GitHub/atknatk/rafraf
git checkout develop
git checkout -b feature/f0/cleanup
# Yeni terminal:
git checkout develop
git checkout -b feature/f0.5/bridge-port
```

Sıradaki adım: T0.1 (cleanup-track) ve T0.5.1 (bridge-track) eş zamanlı başlangıç.
