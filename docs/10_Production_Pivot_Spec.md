# 10 — Production Pivot Spec

> **Bu doküman bir context handoff + action plan dosyasıdır.** Yeni bir Claude session veya yeni bir geliştirici bu doc'u okuduğunda RafRaf'ın bugünkü durumunu, neyin değişeceğini ve production-grade'e nasıl taşınacağını **sıfırdan başka bir kaynağa bakmadan** anlayabilmelidir.

**Sürüm:** 2.0 (mimari major revizyon — host agent → Go bridge port, EKS deploy ana plan)
**Tarih:** 2026-05-01
**Sahip:** The Abi (mr.the.abi@gmail.com)
**Geliştirici:** Claude (Opus 4.7, 1M context)
**Spike kaynağı:** [`~/Code/claude-teams-spike/`](file:///Users/atakan/Code/claude-teams-spike/) (notes/_decision.md)
**Hedef:** RafRaf'ı paralel `claude` agent orkestrasyonuna pivot et + production-grade hâle getir.

**Sürüm geçmişi:**
- 1.0 — İlk yazım
- 1.1 — Review düzeltmeleri: tool aliasing (Task↔Agent), 1000-sample tool dağılımı, system/init tools listesi, RafRaf gerçek path'leri (`WebSocketMessage.swift`, `subprocess_env` line 236), JWT algoritma referansı, cost senaryosu Mac/VPS/EKS ayrı.
- 1.2 — Usage tracking entegrasyonu: yeni §2.11 (statusline JSON pipeline, `~/.claude/usage.json`), `usage.report` WS message tipi, `RFUsageGauge` iOS component planı.
- **2.0 — Mimari major revizyon**:
  - **Backend EKS'te kalır** (kullanıcının mevcut altyapısı). V1 = Mac local önerisi geri alındı.
  - **Host agent SİLİNMEZ** — Python implementasyonu **archive**, yerine `apps/rafraf-bridge/` Go binary olarak **port edilir** (Faz 0.5).
  - **`agent_registry_service.py` TUT** (bridge online/offline tracking için — önceki kararı geri al).
  - **`claude_code_runner.py` rolü değişir**: backend'de subprocess yerine **bridge'e RPC**; subprocess Mac bridge'te.
  - **storage_watcher + statusline pipeline**: backend'de değil, **bridge'te** (Go) — ~/.claude/ Mac'te.
  - Yeni Faz 0.5 eklendi: **Bridge port (Python → Go)**, Faz 0 ile **paralel**. Toplam 4 → 5 hafta.
  - Install kazancı: tek statik Go binary (~10-15 MB), brew tap veya signed `.pkg`. Eski Python venv kurulum karmaşası kalkar — "aktiflestirememistim" sorununun ana sebebi.
  - Yeni docs eşliğinde okunur: [`11_Bridge_Spec.md`](11_Bridge_Spec.md), [`12_Action_Plan_Tasks.md`](12_Action_Plan_Tasks.md), [`adr/0002..0005`](adr/).

---

## 0. İçindekiler

1. [Önsöz: nereden geliyoruz](#1-önsöz-nereden-geliyoruz)
2. [Spike bulguları (özet)](#2-spike-bulguları-özet)
3. [Mevcut RafRaf durumu](#3-mevcut-rafraf-durumu)
4. [Hedef mimari (V1)](#4-hedef-mimari-v1)
5. [Scope reduction — kalanlar / çıkanlar](#5-scope-reduction--kalanlar--çıkanlar)
6. [Mimari değişiklikler (kod düzeyinde)](#6-mimari-değişiklikler-kod-düzeyinde)
7. [Production-grade kriterler](#7-production-grade-kriterler)
8. [Migration / pivot fazları](#8-migration--pivot-fazları)
9. [Açık sorular / kararlar](#9-açık-sorular--kararlar)
10. [Kaynaklar](#10-kaynaklar)

---

## 1. Önsöz: nereden geliyoruz

### Olay sırası

1. **2026-Mart**: RafRaf "AI Project Supervisor" olarak tasarlandı — sesli/yazılı asistanla proje yönetimi. Backend FastAPI, iOS SwiftUI, Mac'te host agent daemon (Docker/Maestro/Playwright/shell runners), mem0 3-katmanlı bellek, voice (Deepgram + OpenAI TTS), 18 iOS feature, 24 backend endpoint.
2. **2026-Apr**: 9 numaralı doc (`09_Hybrid_Claude_Code_Architecture.md`) yazıldı — "her iOS mesajı `claude -p` subprocess ile işlenir, API fallback'tir" mimarisi. `claude_code_runner.py` impl edildi.
3. **2026-Apr-09 (son commit)**: TestFlight CI workflow eklendi, sonra geliştirme durduruldu. Sebep: scope explosion, çok fazla dış servis bağımlılığı (13+ env var: Anthropic, Deepgram, OpenAI, GitHub, AWS×3, mem0, APNs×4), aktif kullanıma geçirilemedi.
4. **2026-May-01 (bugün)**: Bağımsız bir spike çalışması yapıldı (`~/Code/claude-teams-spike/`). 8 test PASS + history mining + Bridge prototype. **Sonuç: GO**, ama RafRaf'ı yenilenen anlayışa göre düzelt.

### Bu doc'un amacı

Spike'ın kanıtladığı şeylerin, RafRaf'ın mevcut kod tabanına nasıl uygulanacağını adım adım yazmak. Bir niyet doc'u değil — eylem planı. Yeni Claude session bu doc'u açıp Faz 0'dan başlayabilir.

---

## 2. Spike bulguları (özet)

Spike `~/Code/claude-teams-spike/` 8 test, 1 history mining, 1 Bridge prototype içerdi. Detay için spike repo'daki `notes/_decision.md` ve test note'ları.

### 2.1 Doğrulanan iki temel iddia

| İddia | Kanıt | Etki |
|---|---|---|
| **Anthropic Ocak 2026'da OpenCode/3rd-party'ın subscription OAuth'unu bloke etti** ([Register](https://www.theregister.com/2026/02/20/anthropic_clarifies_ban_third_party_claude_access/), [Hacker News](https://news.ycombinator.com/item?id=47633396)) | 4 Nisan 2026'da tam enforcement | OpenCode + 3rd-party harness'lar artık subscription kullanamıyor. Sadece **resmî `claude` CLI** subscription destekliyor. RafRaf'ın `claude_code_runner.py` zaten resmî CLI kullanıyor → hâlâ geçerli. |
| **Anthropic Şubat 2026'da Claude Opus 4.6 ile Agent Teams çıkardı** ([Claude Code Docs](https://code.claude.com/docs/en/agent-teams)) | `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` env var, `claude` CLI v2.1.32+ | Lead session **`Agent` tool** ile teammate spawn ediyor; `isolation: "worktree"` ile git worktree built-in; P2P messaging + shared task list. RafRaf bunu **kullanmıyor** — entegre edilecek. |

### 2.2 `claude -p` headless behavior

```bash
claude auth status
# {
#   "loggedIn": true,
#   "authMethod": "claude.ai",       ← OAuth login
#   "apiProvider": "firstParty",
#   "subscriptionType": "max",
#   ...
# }

unset ANTHROPIC_API_KEY
claude -p "merhaba"
# Çalışıyor. apiKeySource: "none" (system/init event'inde) → subscription kullanılıyor.
```

**RafRaf'a etki**: `claude_code_runner.py:236` zaten ANTHROPIC_API_KEY'i subprocess env'inden çıkarıyor:

```python
# apps/backend/app/orchestrator/claude_code_runner.py:236
subprocess_env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
```

Bu pattern aktif → **Backend'in Anthropic API key'i `.env`'de bulundurmasına gerek yok**. Fallback olarak kalabilir, varsayılan kapalı.

### 2.3 Stream-JSON event şeması (genişletilmiş)

`claude -p --output-format stream-json --verbose` çıktısı, RafRaf'ın `claude_code_runner.py`'sinde **kısmen** parse ediliyor. Spike'ta **tüm event tipleri** çıkartıldı:

| Type / Subtype | Açıklama | RafRaf'ta var mı? |
|---|---|---|
| `rate_limit_event` | Her run başında. **Sadece** `status` (allowed/warning/exceeded) + `resetsAt` — **yüzde içermez**. Yüzdeler için statusline JSON'u, bkz. 2.11 | ❌ — eklenecek |
| `system/init` | Session metadata: tools, model, permissionMode, apiKeySource | ⚠️ kısmen |
| `system/task_started` | Subagent (Agent Teams) spawn | ❌ — eklenecek |
| `system/task_progress` | Subagent ilerleme | ❌ — eklenecek |
| `system/task_notification` | Subagent completed (usage stats) | ❌ — eklenecek |
| `system/status` | Session status updates | ⚠️ kısmen |
| `system/hook_started`, `hook_response` | Pre/PostToolUse hook lifecycle | ❌ — eklenecek (V2 yeterli olabilir) |
| `assistant`, `user` | Mesaj turları | ✅ var |
| `stream_event` | Token-level streaming chunks | ✅ var |
| `result` | Final summary (cost, duration, modelUsage, permission_denials) | ⚠️ kısmen — total_cost_usd projeksiyonu yok |

### 2.4 Storage event şeması (yeni)

`~/.claude/projects/<proj>/<session>.jsonl` storage'ı stream-json'dan **farklı**. Spike'ta history mining ile çıkartıldı. RafRaf'ın hiç tanımadığı bir cevher: gerçek-zamanlı stream'de yok ama persistent storage'da var olan event'ler.

| Storage type | Anlam | iOS UX değeri |
|---|---|---|
| `ai-title` | Claude'un session için ürettiği kısa başlık | **Yüksek**: iOS session list'inde session_id yerine title göster |
| `pr-link` | Claude'un açtığı GitHub PR | **Yüksek**: iOS'ta "Bu session bir PR açtı" notification + tıklanabilir link |
| `attachment.type=hook_*` | Pre/PostToolUse hook çıktıları | Orta: V2 |
| `queue-operation` | Kullanıcının queue'ladığı komutlar | Düşük: zaten WebSocket akışında |
| `file-history-snapshot` | Checkpoint dosya state'leri | V2 nice-to-have ("geri al" UX) |
| `permission-mode` | Mode değişiklikleri | Düşük: log için |
| `worktree-state` | Worktree state snapshot'ları | V2 |
| `last-prompt` | Son prompt cache | Düşük |
| `progress` | Progress update | Orta |

### 2.5 `Agent` tool input pattern'ları (gerçek)

Mac'teki 200 sample session'da `Agent` tool 175 kez kullanılmış. Input key kombinasyonları:

```
22 ["description","name","prompt","subagent_type"]
19 ["description","name","prompt","run_in_background","subagent_type"]
 6 ["description","prompt","subagent_type"]
 3 ["description","isolation","name","prompt","subagent_type"]
```

**Önemli**: Gerçek kullanımda **`isolation: "none"` baskın** (197 vs 3 worktree). Yani teammate'ler aynı dizinde çalışıyor (race condition riski). RafRaf V1'de iOS UI default `isolation: "worktree"` zorlamalı — explicit user choice ile `none` opsiyonu.

`subagent_type` değerleri: built-in (`general-purpose`, `Explore`, `Plan`) veya plugin (`<namespace>:<agent>` örn. `dark-factory:holdout-validator`). RafRaf Bridge tool isimlerini opaque tutmalı — namespace istediği gibi gelir.

### 2.6 `--resume`, `--continue`, `--fork-session`

```bash
claude -p --resume <session_id> "..."   # context korunur, num_turns artar
claude -p --continue "..."              # cwd'deki en son session'a dön
claude -p --resume <id> --fork-session  # yeni session_id ile resume (branch)
```

**RafRaf'a etki**: iOS arka plana atılıp dönünce, `--resume` ile session reattach. Backend zaten `claude_code_runner.run(session_id=...)` aldığı için ufak değişiklik.

### 2.7 Git worktree built-in

```bash
claude -w spike-test5 -p "..."   # → .claude/worktrees/spike-test5/ + branch worktree-spike-test5
```

`Agent` tool'da `isolation: "worktree"` aynı mekanizma. **Otomatik cleanup** (subagent task bitince worktree+branch silinir). RafRaf'ın opencode-ensemble pattern'i replikasyonu **gerekmez**. Mevcut RafRaf zaten kendi worktree yönetimini yapmıyor — built-in CLI'ya bırakırız.

### 2.8 Rate limit (Max plan)

5 paralel `claude -p` × 80 saniye burst → toplam **$0.71**, **hiçbiri rate-limit'e çarpmadı** (`status: allowed` her event'te). Max plan V1 başlangıç için fazlasıyla yeterli.

### 2.9 Bridge prototype — RafRaf için ders

Spike'ta minimal Go bridge yazıldı (`~/Code/claude-teams-spike/bridge/main.go`, 276 satır):
- `coder/websocket` v1.8.13 (eski `nhooyr.io/websocket` Mart 2026'da arşivlendi)
- Outbound persistent WS, exponential backoff + jitter, 15s heartbeat
- claude subprocess yönetimi, stream-json line-by-line parse + envelope

**RafRaf'a etki**: RafRaf zaten bu pattern'i Python'da yapıyor (FastAPI WebSocket + claude_code_runner). RafRaf'ın mimarisi spike'tan **daha sade**: ayrı Bridge Agent yok, backend hem WS server hem claude subprocess runner. Bu **good design** — V1'de basit, V2'de remote development için Bridge kavramı eklenir.

### 2.10 Real-world tool distribution (1000 session sample, ~30+ unique tool)

İki ayrı veri seti var; karıştırılmamalı:

#### A) `system/init` event'inde listelenen TÜM destekli tool'lar (kayıtlı, kullanılmasa da)

Spike'ta yakalanan örnek (Mac'in mevcut config'i, MCP'ler dahil):

```json
{"type":"system","subtype":"init","tools":[
  "Task","AskUserQuestion","Bash","CronCreate","CronDelete","CronList",
  "Edit","EnterPlanMode","EnterWorktree","ExitPlanMode","ExitWorktree",
  "LSP","Monitor","NotebookEdit","PushNotification","Read","RemoteTrigger",
  "ScheduleWakeup","SendMessage","Skill","TaskOutput","TaskStop",
  "TeamCreate","TeamDelete","TodoWrite","ToolSearch","WebFetch","WebSearch","Write",
  "mcp__claude_ai_Gmail__authenticate","mcp__claude_ai_Gmail__complete_authentication",
  "mcp__claude_ai_Google_Calendar__authenticate","mcp__claude_ai_Google_Calendar__complete_authentication",
  "mcp__claude_ai_Google_Drive__authenticate","mcp__claude_ai_Google_Drive__complete_authentication",
  "mcp__plugin_figma_figma__authenticate","mcp__plugin_figma_figma__complete_authentication",
  "mcp__plugin_medusa-dev_MedusaDocs__ask_medusa_question"
]}
```

**Built-in core (29)**: `Task`, `AskUserQuestion`, `Bash`, `Edit`, `Read`, `Write`, `TodoWrite`, `Glob` (init'te listelenmemiş ama sık kullanılıyor), `Grep` (yok), `ToolSearch`, `WebFetch`, `WebSearch`, `EnterPlanMode`, `ExitPlanMode`, `EnterWorktree`, `ExitWorktree`, `CronCreate`, `CronDelete`, `CronList`, `TeamCreate`, `TeamDelete`, `SendMessage`, `TaskOutput`, `TaskStop`, `Skill`, `RemoteTrigger`, `Monitor`, `PushNotification`, `NotebookEdit`, `LSP`, `ScheduleWakeup`.

**MCP tool'ları**: kullanıcının kurduğu MCP server'lara göre dinamik. Örn: `mcp__claude_ai_Gmail__*`, `mcp__plugin_figma_figma__*`, `mcp__xcodebuildmcp__*`, `mcp__playwright__*`, `mcp__mobile-mcp__*`, `mcp__firecrawl-mcp__*`, `mcp__plugin_medusa-dev_MedusaDocs__*`, `mcp__sportsbook-php__*`, `mcp__workspace-mcp__*`.

#### B) 1000-sample session'da gerçekten KULLANILAN tool dağılımı

| Tool | Kullanım |
|---|---|
| `Bash` | 17590 |
| `Read` | 9868 |
| `Edit` | 4795 |
| `Grep` | 2569 |
| `Write` | 2352 |
| `TodoWrite` | 1481 |
| `Glob` | 1110 |
| **`Agent`** (subagent spawn) | **938** |
| `ToolSearch` | 551 |
| `mcp__xcodebuildmcp__*` | 200+ (15+ alt-tool: build_run_sim, screenshot, snapshot_ui, vs.) |
| `mcp__workspace-mcp__workspace_api` | 104 |
| `mcp__playwright__*` | 100+ (browser_navigate, browser_take_screenshot, vs.) |
| `ExitPlanMode` / `EnterPlanMode` | 55 / 16 |
| `mcp__firecrawl-mcp__*` | 36+ |
| `ScheduleWakeup` | 40 |
| `AskUserQuestion` | 38 |
| `WebFetch` / `WebSearch` | 29+24 = 53 |
| `RemoteTrigger` | 28 |
| `CronCreate` / `CronDelete` / `CronList` | 24+21+17 = **62** |
| `Monitor` | 18 |
| `Skill` | 14 |
| `SendMessage` | 11 |
| `TaskOutput` / `TaskStop` | 5 / 6 |
| `mcp__plugin_figma_figma__*` | 9+ |
| `mcp__mobile-mcp__*` | 8+ |

#### C) **`Task` ↔ `Agent` aliasing** (kritik)

**Önemli ayrım**:
- `system/init.tools[]` listesinde **`Task`** tool kayıtlı, `Agent` yok.
- Ama assistant content'te `tool_use.name` her zaman **`Agent`**.
- Storage'da 1000-sample'da `Task` ismiyle 0 kullanım, `Agent` ismiyle 938 kullanım.

Yani Mac'te tool **`Task`** ismiyle kayıt, ama runtime'da **`Agent`** olarak görünüyor. Bridge Agent parser **her ikisini de aynı şey olarak handle etmeli** (claude CLI'ın internal aliasing'i bu — muhtemelen 2.x'te rename edildi, init listesi henüz sync olmadı).

```python
# claude_code_runner / WS forwarder pseudocode
TOOL_NAME_ALIASES = {"Task": "Agent"}  # canonical isim Agent

def canonical_tool_name(name: str) -> str:
    return TOOL_NAME_ALIASES.get(name, name)
```

#### D) RafRaf'a etki

- **iOS Chat ekranı tool ismini bilmek zorunda değil** — generic `tool_use` schema yeterli. Top 10'u special-case edip kalanı "custom tool" olarak göster.
- **MCP tool'ları kullanıcının setup'ına bağlı dinamik gelir** — hardcoded liste imkansız (50+ farklı tool).
- **`Task` ↔ `Agent` aliasing**: parser her ikisini de subagent spawn'ı olarak handle etmeli.
- **iOS UX için kritik tool gruplarına özel handling**:
  - **Plan mode** (`EnterPlanMode`, `ExitPlanMode`, 71 toplam): iOS'ta "Planlıyor..." badge / banner.
  - **Cron** (`CronCreate/Delete/List`, 62 toplam): "Bu session bir scheduled task oluşturdu" notification.
  - **Subagent control** (`SendMessage`, `TaskOutput`, `TaskStop`): Agent feature view'ında subagent satırı altında "Mesaj at / Çıktı gör / Durdur" butonları.

---

### 2.11 Usage tracking — statusline JSON pipeline (kritik tamamlayıcı)

Stream-JSON'daki `rate_limit_event` **yüzde değeri vermez** — yalnızca `status: allowed | warning | exceeded` ve `resetsAt`. iOS'ta "5h: %85 dolu" gibi metric göstermek için statusline JSON'u gerekiyor.

**Detay referans**: [`docs/claude-code-usage-tracking.md`](claude-code-usage-tracking.md) — 150 satır, ampirik olarak doğrulanmış (v2.1.126, Opus 4.7, Max plan).

#### Anahtar bulgular

- Claude Code **v2.1.80+** statusline JSON'una `rate_limits` alanı ekledi:
  ```json
  "rate_limits": {
    "five_hour": { "used_percentage": 90, "resets_at": 1777657800 },
    "seven_day": { "used_percentage": 22, "resets_at": 1778166000 }
  }
  ```
- **Sadece interactive mode**'da statusline tetiklenir. `claude -p` (RafRaf'ın subprocess kullanımı), `--init-only`, `--bare` statusline'ı çağırmaz.
- TTY gerekli — headless ortamda `script -q /dev/null` veya `expect` ile pty sağlanmalı.
- API key kullanıcılarında yüzde gelmez — sadece subscription (Pro/Max/Team/Enterprise).

#### Pipeline (V1 Mac local için)

```
~/.claude/statusline.py        ← Mac'te, claude'un her render'ında spawn olur
       │
       │ stdin: statusline JSON (rate_limits dahil)
       ▼
~/.claude/usage.json           ← script tarafından üretilen küçük dosya (5h/7d %)
       │
       │ fsnotify (watchdog)
       ▼
storage_watcher_service        ← veya ayrı usage_watcher_service.py (V1: storage_watcher genişletilebilir)
       │
       │ event.usage.report (yeni WS message)
       ▼
WebSocket → iOS RFUsageGauge (5h ring + 7d ring)
```

#### Tazeleme stratejisi

`usage.json` sadece kullanıcı Claude Code'la **interactive** çalışırken güncellenir (statusline render). RafRaf'ın `claude -p` subprocess çağrıları statusline tetiklemez → o subprocess'lerden geçen kullanım `usage.json`'a yansımaz.

İki yol:

- **Pasif** (V1 önerim): Kullanıcı interactive Claude Code'u zaten her gün açıyor → `usage.json` yeterince taze. Stale kontrolü: 30+ dk eski → "Claude Code'u aç, usage tazelensin" hint.
- **Aktif probe** (V2 nice-to-have): 5–10 dakikada bir headless minimal session açıp kapatmak (`expect` script ile, `~%0.1` 5h tüketimi). V1'de gerek yok.

#### V1 implementation aksiyonları

- Mac'te `~/.claude/statusline.py` deploy edilecek (RafRaf install script veya manuel — §9.x'te karar verilecek).
- `~/.claude/settings.json`'a `statusLine.command` eklenmeli.
- Backend tarafında `storage_watcher_service.py` `INTERESTED_TYPES`'a `usage.json` watch eklenmeli (veya ayrı `usage_watcher_service.py`).
- Yeni WS message: `usage.report` (payload: 5h_pct, 7d_pct, 5h_resets_at, 7d_resets_at).
- iOS DTO + entity + use case + RFUsageGauge component (planlama notları zaten `claude-code-usage-tracking.md` §iOS Tarafi'nda).
- 5h %85+ olunca `RFAlertBanner` ile uyarı.

#### Tuzak: Subscription auth + statusline pipeline kombinasyonu

V1 Mac local deploy senaryosunda backend hem `claude -p` çalıştırıyor hem `~/.claude/usage.json` okuyor — ikisi aynı Mac'te aynı user account'ta. **VPS / EKS** deploy'unda:

- `claude -p` Mac'te subscription gerektirir → backend Mac'te değilse subprocess Mac'e SSH veya Bridge Agent gerekir
- `usage.json` aynı şekilde Mac'te → sync/forward gerekir

Yani **V1 = Mac local** seçimi (§9.1) usage tracking için de mantıklı: tek makinede her şey.

---

## 3. Mevcut RafRaf durumu

### 3.1 Stack (apps/)

| Katman | Teknoloji | Olgunluk |
|---|---|---|
| **Backend** | FastAPI 0.115+, Python 3.12, SQLAlchemy 2.0 async, asyncpg, redis, alembic, anthropic SDK, mem0ai, aioboto3, aioapns | 24 route, 35 service, 7 orchestrator, 7 tool, 9 alembic migration → **olgun** |
| **iOS** | SwiftUI, iOS 17+, Swift 6, Clean Architecture, Factory DI, Nuke | **296 Swift dosyası, 18 feature, 13 RF\* design system component** → **olgun** |
| **Host Agent** | Python asyncio daemon, Docker/Maestro/Playwright/shell runners | Yarım kalmış, log'larda "0 agent online" → **archive edilecek** |

### 3.2 Çalışıyor mu?

`log.txt` (Apr 2) son 30 satır göstergesi:
- iOS WebSocket bağlandı, `chat.stream` mesajları akıyor
- `code.diff` event geldi (7 dosya rapor edildi)
- `task_status: completed` event'i alındı
- Live Activity update + end ediliyor
- **Tek küçük bug**: `TaskStatusContent` decode error — `taskId` key bulunamıyor (snake_case `task_id` ile camelCase mismatch)

Yani **temel akış çalışıyor**, ama production-grade değil:
- Test coverage doğrulanmamış
- Observability eksik
- "Aktiflestirilemedi" sebep: 13+ dış servis bağımlılığı setup'ı zor
- Agent Teams entegre değil
- Stream-JSON parser eksik event tipleri var

### 3.3 Mevcut env (`.env.example` 23 değişken)

```
POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_PORT, DATABASE_URL
REDIS_PORT, REDIS_URL
ANTHROPIC_API_KEY              ← V1'de OPSİYONEL (subscription default)
DEEPGRAM_API_KEY               ← SİL (voice scope dışı)
OPENAI_API_KEY                 ← SİL (voice scope dışı)
GITHUB_TOKEN                   ← TUT (PR tracking)
AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION  ← TUT (S3 backups)
USE_BEDROCK                    ← SİL (sadece subscription)
JWT_SECRET_KEY                 ← TUT
AGENT_API_KEY                  ← SİL (host agent yok)
BACKEND_WS_URL                 ← TUT (iOS config için)
APNS_KEY_PATH, APNS_KEY_ID, APNS_TEAM_ID, APNS_BUNDLE_ID, APNS_USE_SANDBOX  ← TUT
```

**EKLENECEK** (Hibrit doc 09'dan + spike'tan):

```
CLAUDE_CODE_ENABLED=true
CLAUDE_CODE_BINARY=claude
CLAUDE_CODE_PROJECT_DIR=/opt/rafraf
CLAUDE_CODE_MAX_TURNS=30
CLAUDE_CODE_MODEL=opus               # spike'ta opus-4-7[1m] kullanıldı
CLAUDE_CODE_TIMEOUT_SECONDS=300
CLAUDE_CODE_FALLBACK_TO_API=false    # spike'ta subscription yeterli
CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1   # ← yeni
CLAUDE_CODE_INCLUDE_HOOK_EVENTS=false    # V2'de true
CLAUDE_CODE_PERMISSION_MODE=acceptEdits  # default
```

---

## 4. Hedef mimari (V1)

### 4.1 Topoloji (V1 v2.0)

```
                       ┌──────────────┐
                       │  APNs (Apple)│
                       └──────▲───────┘
                              │ push
                              │
   iPhone (SwiftUI) ──HTTPS──▶ ┌──────────────────────┐
   ──WSS──────────────────────▶│  RafRaf Backend       │
                                │  (FastAPI, EKS pod)   │
                                │  ─ Apple Sign In + JWT│
                                │  ─ /sessions /agents  │
                                │  ─ /websocket (iOS WS)│
                                │  ─ /api/v1/agent/ws   │ ← bridge için ayrı WS endpoint
                                │  ─ APNs sender        │
                                │  ─ Postgres + Redis   │
                                │  ─ claude_stream_mgr  │ ← bridge ↔ iOS forwarder
                                └──────────▲───────────┘
                                           │ outbound WSS
                                           │ (bridge initiates)
                                           │
                                ┌──────────┴───────────┐
                                │  rafraf-bridge       │ ← apps/rafraf-bridge/
                                │  (Go, Mac launchd)   │   yeni Go binary, ~10-15 MB
                                │  ─ ws client         │
                                │  ─ claude.runner     │
                                │  ─ claude.parser     │
                                │  ─ claude.state      │
                                │  ─ storage.watcher   │ ← ~/.claude/projects/
                                │  ─ statusline.watcher│ ← ~/.claude/usage.json
                                │  ─ telemetry         │
                                └──────────┬───────────┘
                                           │ subprocess (claude -p)
                                           │
                                ┌──────────▼───────────┐
                                │ claude (Mac)         │
                                │ subscription bound   │
                                │ + Agent Teams flag   │
                                └──────────────────────┘
```

**Anahtar mimari karar (v2.0)**: Backend EKS pod'da, claude CLI Mac'te (subscription bound). Bridge **outbound WSS** ile EKS'e bağlanır (NAT geçişi yok). EKS pod'dan Mac'e direkt bağlantı yok.

**Bridge'in 4 sorumluluğu**:
1. **Backend RPC köprüsü**: `/api/v1/agent/ws` endpoint'inden gelen "claude task çalıştır" komutlarını alır
2. **claude subprocess yöneticisi**: `claude -p --output-format stream-json --verbose ...` çalıştırır
3. **Stream parser + forwarder**: stream-json event'lerini protokol envelope'una çevirip backend'e geri gönderir
4. **Storage + statusline watcher**: `~/.claude/projects/` ve `~/.claude/usage.json` dosyalarını izleyip extra event'leri (ai-title, pr-link, usage report) backend'e push eder

**Spike Bridge prototype** (`~/Code/claude-teams-spike/bridge/main.go`, 276 satır) Faz 0.5'in başlangıç noktası. Mevcut Python `apps/agent/` (claude_runner.py 658 satır + core/connection.py + protocol.py) port edilecek referans.

### 4.2 Akış (V1 v2.0)

```
1. iOS → Backend WS: {type: "user.message", content: "..."}
2. Backend WS handler (websocket.py):
   a. Mesajı conversations tablosuna kaydet
   b. claude_stream_manager.dispatch_to_bridge(user_id, prompt, session_id)
3. claude_stream_manager → bridge WS connection:
   a. Bridge'e RPC envelope: {type: "command.claude.run", payload: {prompt, session_id, permission_mode, agent_teams: true}}
4. Bridge (Go) RPC alır:
   a. claude.runner.Run(prompt, session_id) → exec.CommandContext("claude", "-p", "--output-format", "stream-json", "--verbose", ...)
   b. Subprocess env: CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1, ANTHROPIC_API_KEY excluded
   c. claude.parser line-by-line stdout parse → claude.state günceller (subagents, rate_limit, cost)
   d. Her event'i WS envelope'una çevirip backend'e geri gönderir
5. Bridge (Go) paralel olarak:
   a. storage.watcher → ~/.claude/projects/<proj>/<session>.jsonl tail
   b. statusline.watcher → ~/.claude/usage.json poll
   c. Yakalanan ai-title, pr-link, usage.report event'lerini backend'e push
6. Backend claude_stream_manager:
   a. Bridge'ten gelen event'i RafRaf WS message tipine çevirir (mapping §4.3)
   b. iOS WS'e forward
7. iOS:
   a. chat.stream events (text streaming)
   b. subagent.spawned/progress/completed events (Agent Teams)
   c. session.title event → Home view başlığı güncelle
   d. session.pr_opened event → notification push
   e. usage.report event → RFUsageGauge update
   f. chat.stream_end event → cost + duration göster + Live Activity end
```

### 4.3 Stream-JSON → WS event mapping (iki seviyeli)

İki ayrı WS hattı var:

- **Bridge ↔ Backend**: `/api/v1/agent/ws`, RPC + event envelope (yeni protocol, [`11_Bridge_Spec.md`](11_Bridge_Spec.md) §4)
- **Backend ↔ iOS**: `/api/v1/websocket`, mevcut RafRaf konvansiyonu (`chat.stream`, `chat.stream_end`, `task_status`, `code.diff`)

**Bridge → Backend → iOS akışı**:

claude stream-json → bridge envelope → backend mapping → iOS WS message:

| Stream-JSON `type/subtype` | RafRaf WS message `type` |
|---|---|
| `assistant` (text content) | `chat.stream` |
| `assistant` (tool_use) | `progress` (mevcut) veya `tool.use` (yeni) |
| `user` (tool_result) | `progress` (mevcut) veya `tool.result` (yeni) |
| `stream_event` | `chat.stream` (zaten yapılıyor) |
| `system/init` | `session.init` (yeni) |
| `system/task_started` | `subagent.spawned` (yeni) |
| `system/task_progress` | `subagent.progress` (yeni) |
| `system/task_notification` | `subagent.completed` (yeni) |
| `system/hook_started` | `hook.started` (yeni, V2 yeterli) |
| `rate_limit_event` | `rate_limit.info` (yeni — yalnızca status+resetsAt; yüzdeler için statusline) |
| `result` | `chat.stream_end` (mevcut, ama cost+usage payload eklenmeli) |
| Storage `ai-title` | `session.title` (yeni) |
| Storage `pr-link` | `session.pr_opened` (yeni) |
| Statusline `~/.claude/usage.json` | `usage.report` (yeni — 5h_pct, 7d_pct, resetsAt'lar; bkz. §2.11) |

**Yeni schema'lar `apps/backend/app/schemas/messages.py`'a eklenecek.** iOS tarafı `apps/ios/RafRaf/Core/Networking/`'de WebSocketContent decoder'a bu yeni type'ları ekler.

---

## 5. Scope reduction — kalanlar / çıkanlar

### 5.1 iOS Features (18 → 8 V1)

**TUT** (8 feature):

| Feature | Sebep |
|---|---|
| `Auth` | Apple Sign In + JWT, kritik |
| `Onboarding` | İlk kullanım UX |
| `Home` | Session listesi (ai-title ile zenginleştirilecek) |
| `Chat` | Ana etkileşim ekranı, claude akışı görünür |
| `Agent` | Subagent tree view (Agent Teams için kritik) |
| `Approval` | Tool permission akışı, write/bash için onay |
| `Notifications` | APNs + iOS notification settings |
| `Settings` | Plan, subscription, preferences |

**SİL veya V2'YE ERTELE** (10 feature):

| Feature | Sebep | Karar |
|---|---|---|
| `VoiceInput` | Deepgram dependency, V1 scope dışı | V2 |
| `VoiceOutput` | OpenAI TTS dependency, V1 scope dışı | V2 |
| `VoiceConversation` | Voice composite, V1 scope dışı | V2 |
| `ScreenshotViewer` | Host agent dependency, V1 scope dışı | V2 |
| `FileSharing` | V1 nice-to-have, kompleks UX | V2 |
| `Pulse` | Reports dashboard, V2 feature | V2 |
| `Project` (sayfa) | Standalone project view; Home + Chat yeterli V1'de | V2'de geri gelir |
| `Tasks` | Standalone task view; subagent UI içinde göster | Agent feature içinde merge |
| `Progress` | Progress dashboard; Live Activity yeterli V1 | V2 |
| `Monitoring` | Sistem monitoring; observability backend'de yeter | V2 |

**Klasör aksiyonları**:
- `apps/ios/RafRaf/Features/{Voice*, ScreenshotViewer, FileSharing, Pulse, Project, Monitoring}` → **arşiv branch'e taşı** (ileride geri çağrılabilir), main'den sil
- `Tasks` ve `Progress` feature'larındaki yararlı View'lar `Agent` feature'ı içine merge edilir, ardından klasörler silinir

### 5.2 Backend services (35 → ~18 V1)

**TUT** (V1 zorunlu):

```
auth_service.py
session_service.py
conversation_service.py
approval_service.py
audit_service.py
apns_client.py
live_activity_push_service.py
notification_service.py
orchestrator_service.py
git_context_service.py                ← .claude/projects projection için
git_diff_service.py                   ← code.diff event üretimi için
github_service.py                     ← pr-link / PR webhook için
project_service.py                    ← session.cwd projeksiyonu
proactive_notification_service.py     ← idle session uyarıları
backup_service.py                     ← S3 backup (RDS dump)
s3_service.py                         ← attachment storage
claude_stream_manager.py              ← claude_code_runner ile coupled
```

**YENİ EKLENECEK** (Faz 1):

```
subagent_registry_service.py          ← Agent Teams subagent metadata (in-memory + DB projection)
storage_watcher_service.py            ← ~/.claude/projects/ tail + ~/.claude/usage.json watch (§6.2 + §2.11)
```

`storage_watcher_service` iki kaynak izler:
- `~/.claude/projects/<proj>/<session>.jsonl` → ai-title, pr-link, hook events
- `~/.claude/usage.json` → 5h/7d usage yüzdeleri (statusline.py tarafından yazılan)

İkisi de `event.*` mesajlarına çevrilip WS üzerinden iOS'a forward edilir. Birden fazla servise bölmek yerine tek service iki kaynağı izlemesi daha sade — V1'de.

**SİL / ARCHIVE** (V1 dışı):

```
agent_registry_service.py             ← MEVCUT SERVICE: host agent registry'idir (heartbeat/stale-check),
                                        useCoda'da host agent yok → SİL.
                                        İsim çakışması var: yerine subagent_registry_service.py (yukarıda).
analytics_service.py                  ← V1.1 (basit metric'ler structlog yeterli)
cost_service.py                       ← spike'ta result.total_cost_usd projeksiyonuna basitleşir
cost_alert_service.py                 ← V1.1
maestro_service.py                    ← Host agent ile birlikte gider
memory_service.py                     ← mem0, V2
conversation_memory_service.py        ← mem0, V2
personal_memory_service.py            ← mem0, V2
project_memory_service.py             ← mem0, V2
pulse_service.py                      ← Pulse feature ile birlikte gider
```

**Önemli not — `agent_registry_service` ile çakışma**:

Mevcut `apps/backend/app/services/agent_registry_service.py` üst dosya açıklaması: "Host Agent registry and health monitoring service. Manages agent registration, heartbeat tracking, and stale-agent detection." — bu **host agent**'lar (Mac daemon'ları) için. useCoda'da host agent kavramı yok.

`apps/backend/app/main.py` 5 yerde import ediyor (`from app.services.agent_registry_service import agent_registry`); `apps/backend/app/tools/host_agent_tool.py` da import ediyor. Faz 0'da host_agent_tool ile birlikte komple silinir, ardından Faz 1'de yeni `subagent_registry_service.py` (Agent Teams için) yazılır. Yeni service hiç tutmaz API surface'ını eskiden — temiz başlangıç.

### 5.3 Backend routes (24 → 13 V1)

**TUT**:

```
auth.py, agents.py, agent_ws.py, websocket.py
projects.py, tasks.py, conversations.py
notifications.py, proactive_notifications.py
files.py, backups.py
health.py, webhooks.py
```

**SİL / ARCHIVE**:

```
analytics.py, cost.py, cost_alerts.py
memory.py, personal_memory.py, conversation_memory.py
maestro.py, pulse.py, monitoring.py, subscription.py
```

### 5.4 Backend tools (7 → 3 V1)

LLM'in Claude Agent SDK üzerinden register edip kullandığı tool katmanı. useCoda'da claude CLI'ın **kendi** tool'ları (Bash, Read, Edit, vs.) zaten var — backend tarafı sadece Claude Agent SDK için register edilmiş tool'lar (V1'de minimal kullanım).

**TUT**:

```
base.py               ← Tool taban sınıfı
github_tool.py        ← PR opening (LLM'e izin verilirse)
s3_tool.py            ← backup/attachment
```

**SİL** (mem0 + cost + host agent):

```
memory_tool.py        ← mem0, V2
cost_tool.py          ← cost service ile birlikte
host_agent_tool.py    ← agent_registry_service ile coupled (host agent registry kullanıyor),
                        host agent gidiyor → SİL.
                        useCoda'da claude CLI subprocess olarak doğrudan invoke ediliyor;
                        ayrıca tool katmanına gerek yok.
```

**Sebep**: useCoda'nın çekirdeği `claude_code_runner.py` orchestrator (subprocess). Backend'in Claude Agent SDK için tool register etmesi V1'de yalnızca **`github_tool` (PR opening)** ve **`s3_tool` (attachment)** için anlamlı. Claude'un kendi içsel tool'ları (Bash/Edit/Write/Agent) `claude` CLI tarafında.

### 5.5 Backend orchestrator (7 → 5 V1)

**TUT**:

```
__init__.py
agent.py
claude_code_runner.py  ← BÜYÜK GÜNCELLEME (Agent Teams + yeni event tipleri)
prompt_builder.py
question_bridge.py
tool_registry.py
```

**SİL**:

```
model_router.py        ← Sadece claude (subscription), router gereksiz
```

### 5.6 Apps (host agent kalkıyor)

`apps/agent/` (Python host agent daemon) → **archive branch'e taşı**, main'den sil.

Sebebi: RafRaf'ın orijinal vizyonunda agent kullanıcının Mac'inde Docker/Maestro/Playwright/shell çalıştırıyordu ("AI Project Supervisor" işleri için). useCoda'nın hedefi paralel claude orkestrasyonu — claude CLI bunu kendi başına yapıyor (Bash/Edit/Read tool'ları + Agent Teams). Backend doğrudan `claude -p` subprocess olarak çağırıyor; ayrı Mac daemon **gereksiz**.

V2'de remote development senaryosu için Bridge Agent kavramı geri gelir (spike'ta yazılan Go prototype'a evrilir, ama Python alternatifi de mümkün).

### 5.7 Alembic migrations cleanup

Mevcut 9 migration:
1. ✅ users — TUT
2. ❌ cost_logs — SİL (cost service ile birlikte)
3. ✅ projects — TUT
4. ⚠️ remaining_tables — incele, mem0/voice tablolarını ayır
5. ✅ host_agents/sessions/audit/approval — TUT (host_agents bölümü subagent registry'ye rename)
6. ✅ user_display_name — TUT
7. ✅ project_local_path — TUT
8. ❌ pulse_reports — SİL
9. ⚠️ message_ratings — incele (V1'de kalsın belki)

**Yeni migrations** (V1 için):
10. `010_subagent_registry.py` — Agent Teams subagent metadata
11. `011_session_cost_tracking.py` — `sessions.total_cost_usd`, `sessions.total_tokens`, `sessions.duration_ms`
12. `012_storage_event_cache.py` — ai-title, pr-link projection cache

### 5.8 Dış servis bağımlılığı (13 → 5 V1)

**KALAN** (V1 zorunlu):
- Anthropic Claude (subscription, dolayısıyla **API key bile zorunlu değil**)
- PostgreSQL 16 (RDS veya self-hosted)
- Redis 7 (ElastiCache veya self-hosted)
- Apple APNs (.p8 key)
- AWS S3 (backup/attachment için, opsiyonel olabilir V1'de)

**KALKAN**:
- Deepgram STT (voice scope dışı)
- OpenAI TTS (voice scope dışı)
- AWS Bedrock (subscription yeterli, fallback kapalı)
- mem0 (V2)
- pgvector (mem0 ile birlikte, V2)
- GitHub PAT — **kalır**, ama V1'de optional (PR tracking için)

---

## 6. Mimari değişiklikler (kod düzeyinde, v2.0)

### 6.1 Backend `claude_code_runner.py` rolü tamamen değişiyor

**v1.x** plan: backend subprocess çalıştırıyor (`asyncio.create_subprocess_exec("claude", "-p", ...)`).

**v2.0**: backend EKS pod'da, claude CLI Mac'te. Backend artık **subprocess çalıştırmıyor** — bridge'e RPC ediyor.

#### 6.1.1 Yeni iskelet (backend tarafı)

`apps/backend/app/orchestrator/claude_code_runner.py` baştan yazılır, ama public interface (run/callback'ler) korunur — backend'in geri kalan kodu (`websocket.py`, `claude_stream_manager.py`, `orchestrator_service.py`) az değiştirir.

```python
# apps/backend/app/orchestrator/claude_code_runner.py — v2.0
class ClaudeCodeRunner:
    """RPC adapter: bridge'e komut gönderir, event akışını callback'lere yansıtır.

    Eski v1.x'teki subprocess execution kaldırıldı.
    Subprocess Mac bridge'te (apps/rafraf-bridge/internal/claude/runner.go).
    """

    def __init__(self, agent_registry: AgentRegistryService) -> None:
        self._agents = agent_registry

    async def run(self, *, prompt: str, session_id: str | None = None,
                  bridge_id: str | None = None,
                  on_text_delta: TextDeltaCallback | None = None,
                  on_tool_progress: ToolProgressCallback | None = None,
                  on_question: QuestionCallback | None = None,
                  on_subagent_spawned: SubagentSpawnedCallback | None = None,
                  on_subagent_completed: SubagentCompletedCallback | None = None,
                  on_rate_limit: RateLimitCallback | None = None,
                  on_stream_end: StreamEndCallback | None = None,
                  ) -> ClaudeCodeResult:
        # 1. Hedef bridge'i seç (V1: tek bridge, V2: multi-host)
        bridge = await self._agents.get_active_bridge(user_id, bridge_id)
        # 2. RPC envelope yolla
        rpc_id = uuid4().hex
        await bridge.ws.send_json({
            "type": "command.claude.run",
            "id": rpc_id,
            "ts": now_iso(),
            "payload": {
                "prompt": prompt,
                "session_id": session_id,
                "permission_mode": "acceptEdits",
                "agent_teams": True,
                # ANTHROPIC_API_KEY env exclusion bridge tarafında yapılacak
            },
        })
        # 3. Bridge'ten gelen event'leri korelasyon id ile dinle, callback'lere yansıt
        async for event in self._agents.stream_events(rpc_id):
            await self._dispatch_event(event, callbacks)
        return ClaudeCodeResult(...)
```

#### 6.1.2 Mevcut Python `claude_code_runner.py` (subprocess versiyonu)

Faz 0.5 boyunca **referans olarak korunur** (Bridge port sırasında stream-json parsing logic'i Go'ya kopyalanırken kaynak). Faz 1 sonu ARCHIVED'a taşınır.

#### 6.1.3 Subprocess + stream-json Bridge'te (Go)

Spike'taki Go pattern + RafRaf Python claude_runner.py'nin port edilmiş hali:

```go
// apps/rafraf-bridge/internal/claude/runner.go
type Runner struct {
    Binary       string  // "claude"
    ProjectDir   string  // settings.claude_code_project_dir
    Permissions  string  // "acceptEdits"
}

func (r *Runner) Run(ctx context.Context, req RunRequest, sink EventSink) error {
    cmd := exec.CommandContext(ctx, r.Binary,
        "-p", "--output-format", "stream-json", "--verbose",
        "--include-partial-messages",
        "--permission-mode", r.Permissions,
    )
    if req.SessionID != "" {
        cmd.Args = append(cmd.Args, "--resume", req.SessionID)
    }
    cmd.Args = append(cmd.Args, req.Prompt)
    cmd.Dir = r.ProjectDir

    env := os.Environ()
    env = filterOut(env, "ANTHROPIC_API_KEY")
    env = append(env, "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1")
    cmd.Env = env

    stdout, _ := cmd.StdoutPipe()
    if err := cmd.Start(); err != nil { return err }

    parser := NewParser(sink)
    return parser.Parse(stdout)
}
```

Detay: [`11_Bridge_Spec.md`](11_Bridge_Spec.md) §5 (claude.runner) ve §6 (parser + state).

#### 6.1.2 Yeni stream-json event handler'lar

`_StreamState`'e ekleme:

```python
@dataclass
class _StreamState:
    full_text: str = ""
    delta_index: int = 0
    session_id: str = ""
    model: str = ""
    current_tool_name: str = ""
    current_tool_input_json: str = ""
    is_collecting_tool_input: bool = False
    pending_question: dict[str, object] | None = None
    # YENİ:
    rate_limit_info: dict[str, object] | None = None
    permission_mode: str | None = None
    api_key_source: str | None = None
    active_subagents: dict[str, dict[str, object]] = field(default_factory=dict)  # task_id → metadata
    completed_subagents: list[dict[str, object]] = field(default_factory=list)
    total_cost_usd: float = 0.0
    permission_denials: list[dict[str, object]] = field(default_factory=list)
```

Yeni callback signature'ları:

```python
SubagentSpawnedCallback = Callable[[dict[str, object]], Coroutine[object, object, None]]
SubagentCompletedCallback = Callable[[dict[str, object]], Coroutine[object, object, None]]
RateLimitInfoCallback = Callable[[dict[str, object]], Coroutine[object, object, None]]
SessionInitCallback = Callable[[dict[str, object]], Coroutine[object, object, None]]
ResultCallback = Callable[[ClaudeCodeResult], Coroutine[object, object, None]]  # cost + usage ile
```

`run()` parametre listesine eklenir.

Event dispatch:

```python
async def _dispatch_event(self, event: dict, state: _StreamState) -> None:
    etype = event.get("type")
    subtype = event.get("subtype")

    if etype == "rate_limit_event":
        state.rate_limit_info = event.get("rate_limit_info")
        if self._on_rate_limit:
            await self._on_rate_limit(state.rate_limit_info)

    elif etype == "system" and subtype == "init":
        state.permission_mode = event.get("permissionMode")
        state.api_key_source = event.get("apiKeySource")
        state.session_id = event.get("session_id", "")
        if self._on_session_init:
            await self._on_session_init(event)

    elif etype == "system" and subtype == "task_started":
        task_id = event["task_id"]
        state.active_subagents[task_id] = {
            "task_id": task_id,
            "name": event.get("description"),
            "prompt_preview": event.get("prompt", "")[:200],
            "started_at": datetime.now(UTC).isoformat(),
        }
        if self._on_subagent_spawned:
            await self._on_subagent_spawned(state.active_subagents[task_id])

    elif etype == "system" and subtype == "task_notification":
        task_id = event["task_id"]
        sub = state.active_subagents.pop(task_id, {})
        sub.update({
            "status": event.get("status"),
            "summary": event.get("summary"),
            "usage": event.get("usage", {}),
            "completed_at": datetime.now(UTC).isoformat(),
        })
        state.completed_subagents.append(sub)
        if self._on_subagent_completed:
            await self._on_subagent_completed(sub)

    elif etype == "result":
        state.total_cost_usd = float(event.get("total_cost_usd", 0.0))
        state.permission_denials = event.get("permission_denials", [])
        # ... existing handling
```

#### 6.1.3 Yeni CLI flag'leri

`--include-hook-events`, `--include-partial-messages` opsiyonel destek (config flag ile).

### 6.2 Storage + statusline watcher'lar (v2.0: bridge tarafında)

**v1.x** plan: Python `storage_watcher_service.py` backend'de.

**v2.0**: Mac'te `~/.claude/projects/` ve `~/.claude/usage.json` izlemek backend'in (EKS) yapamayacağı bir iş — dosyalar kullanıcının Mac'inde. Bu yüzden **Bridge tarafına taşındı**:

- `apps/rafraf-bridge/internal/storage/watcher.go` — `~/.claude/projects/` fsnotify
- `apps/rafraf-bridge/internal/statusline/watcher.go` — `~/.claude/usage.json` watch

Detay tasarım: [`11_Bridge_Spec.md`](11_Bridge_Spec.md) §7 (storage) ve §8 (statusline). Aşağıdaki Python referans implementation **archive değeri** taşır — Faz 0.5'te Go'ya port edilirken pattern olarak kullanılır.

<details>
<summary>Eski v1.x Python referans (kullanılmayacak, Go'ya port edilecek)</summary>

`apps/backend/app/services/storage_watcher_service.py` (yeni dosya):

```python
"""Watches ~/.claude/projects/<proj>/<session>.jsonl for storage-only events.

Stream-JSON misses these (they're persisted by claude CLI but not in real-time stream):
  - ai-title (session title generated by Claude)
  - pr-link (GitHub PR opened)
  - attachment.type=hook_* (hook lifecycle)
  - permission-mode (mode changes)

Uses watchdog (filesystem events) + tail-on-write pattern.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import structlog
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = structlog.get_logger()

CLAUDE_PROJECTS_ROOT = Path.home() / ".claude" / "projects"


class StorageEvent(dict[str, Any]):
    """Type alias for clarity."""

    @property
    def event_type(self) -> str:
        return self.get("type", "unknown")

    @property
    def session_id(self) -> str:
        return self.get("sessionId", "")

    @property
    def is_sidechain(self) -> bool:
        return bool(self.get("isSidechain", False))


class StorageWatcher:
    """Tails session jsonl files and yields events of interest."""

    INTERESTED_TYPES = {
        "ai-title",
        "pr-link",
        "attachment",       # filtered by .attachment.type starting with "hook_"
        "permission-mode",
        "worktree-state",
    }

    def __init__(self) -> None:
        self._queue: asyncio.Queue[StorageEvent] = asyncio.Queue()
        self._observer: Observer | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._tail_offsets: dict[Path, int] = {}

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        handler = _Handler(self)
        self._observer = Observer()
        self._observer.schedule(handler, str(CLAUDE_PROJECTS_ROOT), recursive=True)
        self._observer.start()
        await logger.ainfo("storage_watcher_started", root=str(CLAUDE_PROJECTS_ROOT))

    async def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join()

    async def events(self) -> AsyncIterator[StorageEvent]:
        while True:
            event = await self._queue.get()
            yield event

    def _tail_file(self, path: Path) -> None:
        """Read new lines from path since last offset, parse + filter, push to queue."""
        try:
            with path.open() as f:
                f.seek(self._tail_offsets.get(path, 0))
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    etype = ev.get("type")
                    if etype not in self.INTERESTED_TYPES:
                        continue
                    if etype == "attachment":
                        atype = ev.get("attachment", {}).get("type", "")
                        if not atype.startswith("hook_"):
                            continue
                    if self._loop:
                        asyncio.run_coroutine_threadsafe(
                            self._queue.put(StorageEvent(ev)), self._loop
                        )
                self._tail_offsets[path] = f.tell()
        except OSError:
            pass


class _Handler(FileSystemEventHandler):
    def __init__(self, watcher: StorageWatcher) -> None:
        self._watcher = watcher

    def on_modified(self, event: Any) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix != ".jsonl":
            return
        self._watcher._tail_file(path)
```

`pyproject.toml`'a ekle: `watchdog>=4.0.0` (~~v2.0'da kullanılmayacak, Go fsnotify ile~~)

`main.py` lifespan içinde başlat — ~~v2.0'da iptal, bridge tarafında~~.

</details>

**v2.0 yeni akış**:

```
Bridge (Go, Mac)
  ├─ internal/storage/watcher.go   → fsnotify on ~/.claude/projects/
  │  └─ event.session.title (ai-title)
  │  └─ event.session.pr_opened (pr-link)
  │
  └─ internal/statusline/watcher.go → poll ~/.claude/usage.json (5s interval)
     └─ event.usage.report (5h/7d %)
     ↓
   ws.client → backend /api/v1/agent/ws
     ↓
   backend claude_stream_manager → iOS WS forward
```

### 6.3 iOS değişiklikleri

#### 6.3.1 task_status decode hatası fix

`log.txt`'de görülen:

```
[WebSocketContent] TaskStatusContent decode error: keyNotFound(taskId)
```

Backend `task_status` event'inde `task_id` (snake_case) gönderiyor, iOS `TaskStatusContent` struct'ı `taskId` (camelCase) bekliyor — kendi `CodingKeys`'i eksik.

**Doğru dosya**: `apps/ios/RafRaf/Core/Networking/WebSocketMessage.swift` (TaskStatusContent struct'ı bu dosyada tanımlı; satır 90'da kullanılıyor; parent `WebSocketMessage`'ın CodingKeys'i zaten doğru ama TaskStatusContent içeride kendi keys'i eksik).

**Fix**:

```swift
// apps/ios/RafRaf/Core/Networking/WebSocketMessage.swift — TaskStatusContent struct
struct TaskStatusContent: Codable, Sendable {
    let taskId: String
    let status: String
    // ...

    enum CodingKeys: String, CodingKey {
        case taskId = "task_id"     // ← Pydantic snake_case → Swift camelCase
        case status
        // ...
    }
}
```

Aynı pattern tüm WS message Content DTO'larına uygulanmalı (RafRaf konvansiyonu Pydantic snake_case ↔ Swift camelCase). Faz 0 sırasında WebSocketMessage.swift'teki tüm Content struct'larını gözden geçir.

#### 6.3.2 Yeni WS message type'ları

Enum **`apps/ios/RafRaf/Core/Networking/WebSocketMessage.swift`** dosyasında (satır 7'de `enum WebSocketMessageType: String, Codable, Sendable {`). Mevcut enum'a ekleme:

```swift
enum WebSocketMessageType: String, Codable, Sendable {
    // ... existing
    case sessionInit       = "session.init"          // ← yeni
    case subagentSpawned   = "subagent.spawned"      // ← yeni
    case subagentProgress  = "subagent.progress"     // ← yeni
    case subagentCompleted = "subagent.completed"    // ← yeni
    case rateLimitInfo     = "rate_limit.info"       // ← yeni
    case sessionTitle      = "session.title"         // ← yeni (storage)
    case sessionPrOpened   = "session.pr_opened"     // ← yeni (storage)
    case usageReport       = "usage.report"          // ← yeni (statusline, §2.11)
}
```

Aynı dosyada `WebSocketContent` enum'unun `init(from:)` switch'ine bu type'lara karşılık decode case'leri eklenmeli.

#### 6.3.3 Agent feature subagent tree view

`apps/ios/RafRaf/Features/Agent/Presentation/Views/AgentDetailView.swift` (mevcut)'e subagent listesi eklenir. `subagent.spawned` ile lazım, `subagent.completed` ile durumu güncelle. SwiftUI `OutlineGroup` ile lead → subagent ağacı.

#### 6.3.4 Home feature'da ai-title kullanımı

`apps/ios/RafRaf/Features/Home/Presentation/Views/HomeView.swift` (mevcut) — session listesindeki başlık alanı raw session_id veya kullanıcının ilk mesajı yerine, varsa `session.title` (storage'dan gelen `ai-title`).

### 6.4 Schemas (`apps/backend/app/schemas/messages.py`)

Mevcut `MessageType` enum'a:

```python
class MessageType(str, Enum):
    # ... existing
    SESSION_INIT       = "session.init"
    SUBAGENT_SPAWNED   = "subagent.spawned"
    SUBAGENT_PROGRESS  = "subagent.progress"
    SUBAGENT_COMPLETED = "subagent.completed"
    RATE_LIMIT_INFO    = "rate_limit.info"
    SESSION_TITLE      = "session.title"
    SESSION_PR_OPENED  = "session.pr_opened"
```

Yeni Pydantic payload modelleri:

```python
class SubagentSpawnedPayload(BaseModel):
    task_id: str
    name: str
    description: str | None = None
    prompt_preview: str
    subagent_type: str | None = None
    isolation: str | None = None
    started_at: datetime

class SubagentCompletedPayload(BaseModel):
    task_id: str
    status: str  # "completed", "failed"
    summary: str | None = None
    total_tokens: int
    tool_uses: int
    duration_ms: int
    completed_at: datetime

class RateLimitInfoPayload(BaseModel):
    status: str            # "allowed", "limited"
    rate_limit_type: str   # "five_hour"
    resets_at: int         # unix timestamp
    overage_status: str
    is_using_overage: bool

class SessionTitlePayload(BaseModel):
    session_id: UUID
    ai_title: str

class SessionPrOpenedPayload(BaseModel):
    session_id: UUID
    pr_number: int
    pr_url: str
    pr_repository: str

class UsageReportPayload(BaseModel):
    """5-saatlik ve 7-günlük subscription kotalarının yüzdesi.

    Kaynak: ~/.claude/usage.json (Mac'teki statusline.py tarafından yazılır).
    Detay: docs/claude-code-usage-tracking.md, doc 10 §2.11.
    """
    five_hour_pct: int           # 0–100+ (overage durumunda 100'ü aşabilir)
    seven_day_pct: int
    five_hour_resets_at: int     # unix timestamp (saniye)
    seven_day_resets_at: int
    reported_at: int             # usage.json yazılma zamanı (stale detection için)
```

---

## 7. Production-grade kriterler

### 7.1 Test coverage

| Katman | Hedef coverage |
|---|---|
| Backend services (domain logic) | %80+ |
| Backend orchestrator (claude_code_runner) | %90+ (fixture stream-json sample'larıyla) |
| iOS ViewModels (`@Observable`) | %70+ (Swift Testing) |
| iOS DTO mapper'lar | %100 |

**Spike repo'da gerçek `~/.claude/projects/` örnekleri** test fixture olarak kullanılabilir (privacy: kullanıcı içeriği temizlenmeli).

### 7.2 CI/CD

Mevcut `.github/workflows/`:
- `ios-testflight.yml` ✅
- `ios-testflight-staging.yml` ✅ (Apr 2 commit)

**EKLENECEK**:
- `backend-ci.yml` — ruff + mypy strict + pytest + Docker build push
- `agent-ci.yml` — KALDIR (host agent gidiyor)

### 7.3 Observability

| Sinyal | Mevcut | Hedef |
|---|---|---|
| Structured logging | ✅ structlog | Loki ship |
| Tracing | ❌ | OpenTelemetry, Grafana Cloud Tempo |
| Metrics | ❌ | OpenTelemetry, Prometheus remote_write |
| Error tracking | ❌ | Sentry (optional V1.1) |

**Önemli metric'ler** (spike'tan):

Backend:
- `claude_subprocess_count` (gauge)
- `claude_subprocess_duration_seconds` (histogram)
- `claude_rate_limit_hits_total` (counter)
- `claude_total_cost_usd_total` (counter)
- `subagent_spawned_total` (counter)
- `ws_connections_active` (gauge)
- `apns_delivery_success_total` / `apns_delivery_failure_total`

Storage watcher:
- `storage_events_processed_total{type}` (counter)
- `storage_watcher_lag_seconds` (gauge)
- `claude_5h_usage_pct` (gauge) — son rapor edilen 5-saatlik kullanım %
- `claude_7d_usage_pct` (gauge) — son rapor edilen 7-günlük kullanım %
- `claude_usage_report_age_seconds` (gauge) — usage.json son güncellenmesinden bu yana geçen süre (stale detection için)
- `claude_usage_report_total` (counter) — backend'in iOS'a forward ettiği usage.report sayısı

### 7.4 Security

Mevcut RafRaf:
- ✅ JWT — `apps/backend/app/core/security.py` `jwt.encode/decode` `algorithm=settings.jwt_algorithm` config'den okuyor. `Settings` class'ında default değer kontrol edilmeli (HS256 mı RS256 mı). Önerim: **RS256'ya migrate** (asymmetric, key rotation kolay, leaked public key zarar vermez). Migration: yeni RSA key pair üret, `JWT_PUBLIC_KEY` + `JWT_PRIVATE_KEY` env, eski HS256 token'ları grace period ile geçerli tut.
- ✅ bcrypt password hashing
- ✅ Rate limit middleware
- ✅ Request logging middleware
- ✅ Approval service (write/bash için onay)
- ⚠️ Apple Sign In — `apps/backend/app/api/routes/auth.py` doğrula

**EKLENECEK**:
- WAF (production'da, ALB seviyesinde)
- IP allow-list (opsiyonel, sadece The Abi V1)
- KMS encrypted secrets (AWS Secrets Manager)
- IRSA (EKS pod permissions)
- API key rotation runbook

### 7.5 Disaster recovery

| Hedef | Mevcut | Plan |
|---|---|---|
| RPO | ❌ | 24 saat (PITR) |
| RTO | ❌ | 1 saat |
| Backup | ⚠️ S3 backup_service var | Otomatize, restore drill ayda 1 |
| Disaster runbook | ❌ | `docs/runbooks/disaster-recovery.md` |

### 7.6 Multi-AZ

V1 başlangıç: tek AZ (cost), V2'de prod multi-AZ.

### 7.7 Cost target (V1)

Üç deploy senaryosu için ayrı (§9.1'deki seçenekler):

| Kalem | Mac local (önerim) | VPS (Hetzner/DO) | EKS (V2 önizleme) |
|---|---|---|---|
| Compute | $0 | $20-40/ay | $73/ay (EKS control plane) |
| Postgres | $0 (local Docker) | $0 (Docker on VPS) | $25/ay (RDS db.t4g.small) |
| Redis | $0 (local Docker) | $0 (Docker on VPS) | $20/ay (ElastiCache cache.t4g.micro) |
| Load balancer | $0 (Tailscale yeterli) | $0 (nginx) | $22/ay (ALB) |
| Network egress | $0 | ~$5/ay | $30/ay (NAT GW + data transfer) |
| Misc (S3, Route53, ACM, ECR) | ~$5/ay (S3 backup) | ~$5/ay (S3) | ~$10/ay |
| **Infra subtoplam** | **~$5/ay** | **~$30-50/ay** | **~$180/ay** |
| Claude Code subscription Max | $200/ay (mevcut plan) | $200/ay | $200/ay |
| **TOPLAM** | **~$205/ay** | **~$230-250/ay** | **~$380/ay** |

V1 önerim: **Mac local** (~$205/ay), V2'de Bridge Agent kavramı eklenince EKS'e geçiş.

Spike Test 6'da 5 paralel session'da $0.71 tüketildi — Max plan rate-limit'e çarpmadan. V1 öngörüsü: günlük 10-20 session × ortalama $0.50 = aylık $150-300 ek subscription tüketimi (Max plan içinde, ekstra ücret yok). **Yani Max plan'ın token quota'sı V1 için sınırlayıcı değil**.

---

## 8. Migration / pivot fazları

Toplam **5 hafta** RafRaf'ı production-grade hâle getirmek için (v2.0 ile +1 hafta — Faz 0.5 Bridge port).

| Faz | Track | Süre | Bağımlılık |
|---|---|---|---|
| **Faz 0 — Cleanup** | cleanup-track | 1 hafta | — |
| **Faz 0.5 — Bridge port (Python → Go)** | **bridge-track (paralel)** | 1 hafta | — (Faz 0 ile paralel) |
| **Faz 1 — Agent Teams entegrasyonu** | sequential | 1 hafta | Faz 0 + Faz 0.5 done |
| **Faz 2 — Production hardening** | sequential | 1 hafta | Faz 1 done |
| **Faz 3 — TestFlight + launch** | sequential | 1 hafta | Faz 2 done |

**Detay task listesi**: [`12_Action_Plan_Tasks.md`](12_Action_Plan_Tasks.md) — her task için done criteria, etkilenen dosyalar, test komutları, dependency.

**Bridge tasarım detayı**: [`11_Bridge_Spec.md`](11_Bridge_Spec.md) — `apps/rafraf-bridge/` Go module package'ları, interface'ler, packaging.

### Faz 0 — Cleanup (1 hafta)

**Done criteria:**

- [ ] **iOS feature pruning** (10 feature arşivlendi/silindi):
  - [ ] `git checkout -b archive/voice-and-host-agent-features`
  - [ ] Sil: `apps/ios/RafRaf/Features/{VoiceInput,VoiceOutput,VoiceConversation,ScreenshotViewer,FileSharing,Pulse,Project,Monitoring}`
  - [ ] Tasks/Progress yararlı View'larını `Agent/Presentation/Components/`'a merge et, sonra klasörleri sil
  - [ ] `apps/ios/RafRaf.xcodeproj` referanslarını temizle, `xcodegen generate`
  - [ ] iOS build temiz: `xcodebuild build -scheme RafRaf` exit 0
- [ ] **Backend service/route/tool pruning** (v2.0 düzeltme: agent_registry TUT):
  - [ ] Sil: 9 service (mem0×4, voice, cost×2, maestro, pulse), 10 route (analytics, cost×2, memory×3, maestro, pulse, monitoring, subscription), 3 tool (memory_tool, cost_tool, **host_agent_tool**), 1 orchestrator (model_router)
  - [ ] **TUT**: `agent_registry_service.py` (bridge online/offline tracking için yeniden role değişiyor; iç logic Faz 1'de güncellenecek — host agent kaydı yerine bridge kaydı)
  - [ ] `app/main.py` import'ları + lifespan'daki `agent_registry` çağrıları **KALSIN** (Faz 1'de bridge tarafına refactor)
  - [ ] `_register_host_agent_tool()` fonksiyonu sil (main.py'de)
  - [ ] Backend test: `pytest` pass (host_agent_tool test'leri silinir, agent_registry test'leri Faz 1'de güncellenir)
- [ ] **Host agent archive (v2.0 — Bridge port için)**:
  - [ ] `apps/agent/` → `apps/_archive/agent-python-v0.1/` taşınır (referans için, Bridge port sırasında Python claude_runner.py'ye bakılacak)
  - [ ] `infra/docker/docker-compose.dev.yml`'den agent service'ini kaldır
  - [ ] `Makefile` agent target'larını sil
  - [ ] **Yeni**: `apps/rafraf-bridge/` skeleton oluştur (Faz 0.5 ile paralel)
- [ ] **mem0 cleanup**:
  - [ ] `mem0ai` dependency `pyproject.toml`'dan kaldır
  - [ ] `infra/docker/mem0/` arşivle
  - [ ] alembic migration cleanup (mem0 tabloları)
- [ ] **`.env.example` revize**: 23 var → ~12 var (5.8'deki listeye göre)
- [ ] **Docs cleanup**: `docs/03_AI_Agent_Tool_Layer_Specification.md`, `docs/05_Memory_System_Specification.md`, `docs/08_Host_Agent_Specification.md` "ARCHIVED — V2" notu ekle, kalan içerikten referans verme

**Sonuç:** Repo boyutu 823 MB → ~600 MB tahmini. Build temiz.

### Faz 0.5 — Bridge port (Python → Go, 1 hafta, **Faz 0 ile paralel**)

Mevcut Python `apps/agent/` (silmeyiz, archive ettik) referans alınarak `apps/rafraf-bridge/` Go module yazılır. Spike `~/Code/claude-teams-spike/bridge/main.go` (276 satır) çekirdek başlangıç. Detay tasarım: [`11_Bridge_Spec.md`](11_Bridge_Spec.md). Detay task'lar: [`12_Action_Plan_Tasks.md`](12_Action_Plan_Tasks.md) §Faz 0.5.

**Done criteria:**

- [ ] **Skeleton + tooling**:
  - [ ] `apps/rafraf-bridge/cmd/bridge/main.go`, `internal/{config,ws,protocol,claude,storage,statusline,security,telemetry}/`, `packaging/{launchd,homebrew,pkg}/`, `go.mod`
  - [ ] `golangci-lint`, `go test`, `go build` çalışıyor
- [ ] **Çekirdek paketler** (spike'tan + Python port):
  - [ ] `internal/ws/` — `coder/websocket` v1.8.13, outbound persistent + reconnect (jitter+backoff) + 15s heartbeat (spike base genişletilmiş)
  - [ ] `internal/protocol/` — RafRaf WS message envelope (Pydantic snake_case ile uyumlu JSON tag'ler), `build_claude_stream_*_message` builder'larının Go karşılığı
  - [ ] `internal/config/` — `AgentConfig` Python'dan port, `~/.config/rafraf-bridge/config.toml`
  - [ ] `internal/claude/runner.go` — `claude -p --output-format stream-json --verbose --resume <id>` subprocess wrapper. Env injection (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, `ANTHROPIC_API_KEY` exclude).
  - [ ] `internal/claude/parser.go` — stream-json line-by-line parser (Python `_parse_stream` port). 15 tool display name (Türkçe).
  - [ ] `internal/claude/state.go` — `_StreamState` Go karşılığı: subagent_active map, rate_limit_info, total_cost_usd, permission_denials.
- [ ] **Storage + statusline watcher'lar** (Python'da yok, yeni implementation):
  - [ ] `internal/storage/watcher.go` — `~/.claude/projects/` fsnotify, ai-title + pr-link + hook attachment event'leri
  - [ ] `internal/statusline/watcher.go` — `~/.claude/usage.json` watch, 5h/7d usage % event
- [ ] **Telemetry** (asgari V1):
  - [ ] `internal/telemetry/metrics.go` — `expvar` veya OTel SDK, `claude_subprocess_count`, `ws_connected`, `ws_reconnects_total`, `claude_total_cost_usd_total`
- [ ] **Packaging**:
  - [ ] `packaging/launchd/com.rafraf.bridge.plist` (kullanıcı oturum agent)
  - [ ] `packaging/homebrew/rafraf-bridge.rb` (formula, prebuilt binary release)
  - [ ] `packaging/pkg/scripts/{preinstall,postinstall}.sh` (signed `.pkg` için)
  - [ ] `scripts/install-bridge.sh` (geliştirme amaçlı, brew/pkg yokken)
- [ ] **CI workflow** (`.github/workflows/bridge-ci.yml`):
  - [ ] `golangci-lint`, `go test ./...`, `go build` (arm64 + amd64)
  - [ ] Release tag'lerde GitHub Release'e prebuilt binary attach
- [ ] **End-to-end smoke** (Faz 0.5 done göstergesi):
  - [ ] `apps/rafraf-bridge/bridge` build edildi (~10-15 MB statik binary)
  - [ ] Mac'te launchd plist ile başlatıldı, log: "connected to ws://localhost:8000/api/v1/agent/ws"
  - [ ] RafRaf backend dev'inde mock task forward edildi → claude -p subprocess çalıştı → stream-json event'leri WS üzerinden backend'e döndü
  - [ ] iOS Chat ekranı eski Python agent yokken yeni Go bridge ile aynı mesaj akışını gösteriyor (smoke test, manuel)

### Faz 1 — Agent Teams entegrasyonu (1 hafta)

**ÖN KOŞUL**: Faz 0 + Faz 0.5 done. Bridge Go binary çalışıyor, backend Python claude_code_runner subprocess yerine **bridge'e RPC** ediyor.

**Done criteria:**

- [ ] **Backend `claude_code_runner.py` rolü değişimi** (v2.0 major):
  - [ ] Subprocess execute kaldırıldı, yerine WS RPC `bridge.claude.run` mesajı
  - [ ] WS endpoint `/api/v1/agent/ws` (mevcut, route adı agent_ws.py) bridge bağlantısını yönetir; her bridge için register/heartbeat
  - [ ] Bridge'ten gelen stream event'leri `claude_stream_manager` üzerinden iOS WS'e forward
  - [ ] Test fixture: bridge mock'u (spike'tan gerçek stream-json örnekleri) ile pytest coverage %90+
- [ ] **Bridge tarafında Agent Teams** (Go, `apps/rafraf-bridge/internal/claude/`):
  - [ ] `runner.go` env injection: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`
  - [ ] `state.go` Agent Teams state: `active_subagents map[string]SubagentState`, `completed_subagents []SubagentState`
  - [ ] `parser.go` yeni event tipleri dispatch: `system/task_started`, `task_progress`, `task_notification`, `hook_started`, `hook_response`, `rate_limit_event`
  - [ ] Tool name aliasing: `Task` ↔ `Agent` (canonical isim Agent)
  - [ ] Go test fixture: spike `~/Code/claude-teams-spike/results/02-agent-teams/run-1.jsonl`'i `internal/claude/testdata/`'a kopyala
- [ ] **Storage + statusline watcher'lar** (v2.0 düzeltme: backend'de DEĞİL, bridge'te):
  - [ ] **Bridge tarafı** `internal/storage/watcher.go` — `~/.claude/projects/` fsnotify, ai-title + pr-link → WS event olarak backend'e gönder
  - [ ] **Bridge tarafı** `internal/statusline/watcher.go` — `~/.claude/usage.json` watch → `usage.report` WS event
  - [ ] **Backend tarafı** sadece bridge'ten gelen event'leri iOS'a forward eder; kendi watcher'ı yok
- [ ] **Statusline pipeline kurulum** (§2.11, [`claude-code-usage-tracking.md`](claude-code-usage-tracking.md)):
  - [ ] `~/.claude/statusline.py` deploy (`scripts/install-statusline.sh` — Bridge install pkg ile birlikte)
  - [ ] `~/.claude/settings.json`'a `statusLine.command` eklenmesi (merge-safe, mevcut config korunur)
  - [ ] Empirical doğrulama: kullanıcı interactive `claude` aç → `cat ~/.claude/usage.json` → `five_hour_pct` görünüyor
  - [ ] Bridge `statusline/watcher.go` event push ediyor → backend `claude_stream_manager` → iOS RFUsageGauge update
- [ ] **iOS RFUsageGauge component** (§2.11 + [`claude-code-usage-tracking.md`](claude-code-usage-tracking.md) §iOS Tarafi):
  - [ ] `ClaudeUsageDTO` + `ClaudeUsage` entity + `ObserveClaudeUsageUseCase`
  - [ ] `RFUsageGauge` (iki concentric ring, threshold renkleri 0–60% green, 60–85% yellow, 85–100% red)
  - [ ] 5h %85+ → `RFAlertBanner` ile uyarı
  - [ ] Lokalizasyon: `usage.fiveHour.title`, `usage.fiveHour.resetsIn`, `usage.weekly.title`, `usage.weekly.resetsIn`
- [ ] **`subagent_registry_service.py` yeni service** (§5.2):
  - [ ] In-memory subagent state (task_id → metadata)
  - [ ] DB projection (Postgres `subagents` tablosu, migration `010_subagent_registry.py`)
  - [ ] claude_code_runner subagent_spawned/completed callback'lerini bu service'e bağla
- [ ] **WebSocket route güncelleme** (`websocket.py`):
  - [ ] Yeni MessageType'ları handle et
  - [ ] claude_code_runner callback'leri WS push'a bağla
  - [ ] Storage watcher → WS push
- [ ] **Schemas güncelleme** (`schemas/messages.py`):
  - [ ] Yeni Pydantic payload model'leri (§6.4)
- [ ] **iOS WS decoder güncelleme**:
  - [ ] WebSocketMessageType enum'a 7 yeni case
  - [ ] Yeni Content struct'lar (CodingKeys ile snake_case → camelCase)
  - [ ] **TaskStatusContent decode error fix** (§6.3.1)
- [ ] **iOS Agent feature subagent tree** (§6.3.3):
  - [ ] AgentDetailView'a subagent listesi
  - [ ] subagent.spawned/progress/completed handle
- [ ] **iOS Home feature ai-title** (§6.3.4):
  - [ ] HomeView session listesinde varsa ai-title göster
- [ ] E2E test (manuel, terminal'den): iOS WebSocket bağlan → claude task gönder → 3 subagent spawn → her birinin durumu iOS'ta görünüyor

### Faz 2 — Production hardening (1 hafta)

**Done criteria:**

- [ ] **OpenTelemetry tracing**:
  - [ ] FastAPI middleware
  - [ ] `claude_code_runner` span'leri
  - [ ] Grafana Cloud Tempo'ya export
- [ ] **Metrics** (§7.3):
  - [ ] `prometheus_client` veya OTel SDK
  - [ ] §7.3'teki metric listesini emit
  - [ ] `/metrics` endpoint
- [ ] **Health check + readiness**:
  - [ ] `/health` (liveness)
  - [ ] `/ready` (DB + Redis + claude binary)
- [ ] **Rate limit middleware adapt**:
  - [ ] Anthropic 429 yakalandığında client'a `rate_limit.info` push
  - [ ] iOS UI'da "rate limit yakın, X dk sonra reset" göster
- [ ] **Cost tracking**:
  - [ ] Migration `011_session_cost_tracking.py`
  - [ ] `result.total_cost_usd` projeksiyonu sessions tablosuna
  - [ ] Aylık özet endpoint `/sessions/cost-summary`
- [ ] **DB backup + restore drill**:
  - [ ] PITR aktif (RDS) veya cron pg_dump (self-hosted)
  - [ ] Manual restore drill, çıktı: `/health` 200 dön
  - [ ] Runbook: `docs/runbooks/disaster-recovery.md`
- [ ] **CI**:
  - [ ] `.github/workflows/backend-ci.yml` — ruff, mypy strict, pytest, Docker build, push GHCR
  - [ ] `agent-ci.yml` sil (host agent yok)

### Faz 3 — TestFlight & launch (1 hafta)

**Done criteria:**

- [ ] **iOS UI polish**:
  - [ ] Agent feature subagent UI test edildi
  - [ ] Live Activity update test (yeni subagent spawn'da)
  - [ ] Approval sheet UX (Spike #5'in fallback ağacı: write/edit/bash → ask, read/grep → allow)
- [ ] **Permission flow doğrulama**:
  - [ ] Spike Test 2'deki "subagent permission inheritance" gerçek launchd deployment'ta doğrulan
  - [ ] V1 default: lead `--permission-mode acceptEdits`, subagent default permission (denial olursa iOS'ta approval sheet)
- [ ] **TestFlight build**:
  - [ ] iOS build #20001+ staging branch
  - [ ] Manuel device test: The Abi'nin iPhone'unda
  - [ ] Crash-free rate %99+ (3 saat smoke test)
- [ ] **Backend production deploy**:
  - [ ] Docker image build (`apps/backend/Dockerfile`)
  - [ ] Hedef: küçük VPS veya EKS (V1'de tercihe bağlı, useCoda master plan v0.3'te EKS)
  - [ ] DB migrate, Redis bağlantı, APNs key dosyası mount
  - [ ] Secrets: AWS Secrets Manager veya env (V1'de env yeterli)
  - [ ] **Mac'te `claude` CLI yüklü ve login** (subscription gerekli)
- [ ] **End-to-end smoke**:
  - [ ] iOS TestFlight → backend prod → claude -p subprocess → cevap geri
  - [ ] Subagent spawn → tree view → completed
  - [ ] PR opened (gerçek GitHub repo) → iOS notification
- [ ] **Documentation**:
  - [ ] `docs/runbooks/deploy.md`
  - [ ] `docs/runbooks/secret-rotation.md`
  - [ ] `docs/runbooks/anthropic-cli-upgrade.md` (claude CLI haftalık check)

**Toplam: 4 hafta**, RafRaf v1.0 production-grade.

---

## 9. Açık sorular / kararlar

### 9.1 Backend deploy yeri (V1, v2.0 güncellemesi)

**v2.0 KARARI: EKS** (kullanıcının mevcut altyapısı). Mac local önerisi geri alındı.

Sebep: useCoda'nın orijinal master plan'ı zaten EKS demişti; RafRaf'ın production-grade hedefi de EKS uyumlu. Mac local geçici çözümdü; Bridge Agent kavramı (Faz 0.5) Mac'te claude subprocess + EKS'te backend mimarisini doğal hâle getirdi.

| Deploy yeri | claude CLI'a nasıl erişiyor | V1 önerisi |
|---|---|---|
| **EKS pod** | Mac'teki bridge'e outbound WS → bridge claude -p subprocess çalıştırır | ✅ V1 ana plan |
| Mac local | Direkt subprocess (bridge gerek yok) | V1 dev dönemi geçici, prod değil |
| VPS | Bridge ile EKS gibi çalışır, ama EKS zaten kullanılıyor | Anlamsız ara katman |

**V1 production**: EKS pod (Mac bridge ile köprü). Mac dev: docker-compose'la lokal backend + lokal bridge ile aynı pattern test (production'da sadece backend yer değiştirir).

### 9.2 Subscription auth login flow

Backend `claude -p` çağırınca Mac'in Claude Code login durumunu kullanıyor. Eğer:
- Mac'te `claude` login değilse → subprocess fail
- Login expire olursa → subprocess fail
- Backend Linux'ta (VPS) ise → Mac keychain yok → fail

**Aksiyon**: `claude_code_runner` startup'ta `claude auth status` çalıştır, `loggedIn: false` ise iOS'a `event.auth.expired` push, kullanıcıya "Mac'te `claude` login yenile" notification.

### 9.3 RafRaf ismi kalsın mı?

Kullanıcının kararı: **kalsın** (mesajda "rafraf'ı saglamsitacak"). Bundle ID `app.rafraf` da kalır. Domain ayrı bir karar (rafraf.dev / rafraf.app — WHOIS check edilmedi).

### 9.4 Mevcut 55 proje + 9 alembic migration

`log2.txt`'de "Proje listesi alindi: 55 proje" — büyük olasılıkla The Abi'nin gerçek geliştirme projelerinin listesi (RafRaf test sırasında otomatik discovery yapmış olabilir; örn. `apps/agent/agent/discovery/` dizini var, `git_context_service` repo path'lerini tarıyor). Faz 0 cleanup sırasında:
- **Önce**: `pg_dump` al — `infra/scripts/backup-dev-db.sh` (yoksa yaz). Backup `~/Code/rafraf-backups/$(date +%Y-%m-%d).sql.gz`'a düşsün.
- Eğer test data: temizle, fixture olarak `tests/fixtures/projects.sql`
- Eğer gerçek The Abi'nin verisi: koru, Faz 1'de yeni schema'ya migrate (özellikle `projects.local_path` field'ı useCoda'da `sessions.cwd` olarak kullanılacak)

**Aksiyon**: Faz 0 ilk adım = DB dump al + The Abi'ye "55 proje gerçek mi test mi?" sor.

### 9.5 V2'de Bridge Agent

V2 hedef: backend EKS pod'da, Mac'te ayrı Bridge Agent (Go veya Python) outbound WS köprüsü. Spike'taki Go prototype'ı V2'nin başlangıç noktası.

V1 sırasında dikkat: backend ↔ claude_code_runner protokolünü "subprocess" özelinden ayırma. Bridge Agent V2'de gelecek interface aynı kalmalı (yani `ClaudeCodeRunner` interface'i, `process_executor: ClaudeProcessExecutor` strategy ile abstract — V1'de `LocalSubprocessExecutor`, V2'de `BridgeWebSocketExecutor`).

### 9.6 Live Activity edge case'leri

Spike'ta test edilmedi. Bilinen RafRaf davranışı (log.txt'den): Live Activity update + end çalışıyor. Faz 1 sonu manuel test:
- Subagent spawn olunca Live Activity update (kaç subagent aktif)
- Tüm subagent'lar tamamlanınca Live Activity end
- 4KB APNs payload limiti — kaç subagent metadata'sı sığar?

### 9.7 Permission UI scope (V1)

Spike Test 2'de subagent'lar Write blocked oldu. Spike `_decision.md` §6.2 fallback ağacı:
- **Case A**: subagent permission_mode'u `Agent` tool input'undan geçirilebiliyor → V1 dynamic approval
- **Case B**: blocked, OpenCode-tarzı PR yaz → V1 statik denylist (write/bash/edit deny default, kullanıcı toggle ile aç)
- **Case C**: blocked, plugin yaz → V1 statik denylist

Faz 1'de bu test edilmeli (`_dispatch_event` içinde `subagent permission_denial` event yakalama).

### 9.8 Storage watcher'ın CPU/I/O yükü

`~/.claude/projects/` 3.3 GB, 4474 jsonl. Watchdog tüm dizini izlerse CPU artabilir. **Optimizasyon**: sadece son N gün modify edilmiş dosyaları izle, eski'leri ignore et.

### 9.9 Statusline.py deploy yöntemi

[`claude-code-usage-tracking.md`](claude-code-usage-tracking.md) §2.11 ve §statusline implementation: `~/.claude/statusline.py` script Mac'e yazılmalı + `~/.claude/settings.json`'a `statusLine.command` eklenmeli. Üç opsiyon:

- **A — Manuel** (V1 başlangıç): The Abi tek-tıkla bir setup script çalıştırır (`scripts/install-statusline.sh`), o script statusline.py'yi `~/.claude/`'a kopyalar + settings.json'u patch'ler.
- **B — RafRaf init flow**: iOS app'in onboarding'inde "Mac setup" adımı çıkarır, kullanıcıya komut yapıştırır.
- **C — Otomatik** (V2): Bridge Agent kavramı geri geldiğinde, Bridge Agent kendi launchd plist'iyle birlikte statusline'ı da kurar.

V1 önerim: **A**. `scripts/install-statusline.sh` Faz 1'de yazılır, README'de "Subscription usage tracking için bunu çalıştırın" notu.

**Tuzak**: Kullanıcının `~/.claude/settings.json`'unda zaten kendi `statusLine` config'i varsa (doc'taki gibi farklı bir script) overwrite etme — merge / wrap önerisi göster.

### 9.10 Statusline pipeline ile probe stratejisi

[`claude-code-usage-tracking.md`](claude-code-usage-tracking.md) "Tazeleme Stratejisi" — V2'de aktif probe (5–10 dakikada bir headless minimal session) eklenebilir. V1'de pasif yeterli (kullanıcı zaten Claude Code interactive açıyor → usage.json güncel).

V1'de iOS UX'i: usage.json **30+ dakika** eski ise iOS'ta "(usage stale, Claude Code'u açın)" hint. `claude_usage_report_age_seconds` metric bu UX'in sinyali.

---

## 10. Kaynaklar

### 10.1 Spike repo

- [`~/Code/claude-teams-spike/`](file:///Users/atakan/Code/claude-teams-spike/)
  - `notes/_decision.md` — GO kararı + 8 test özeti
  - `notes/00-history-mining.md` — Mac history schema + tool dağılımı
  - `notes/01-subscription.md` — claude -p subscription doğrulaması
  - `notes/02-agent-teams.md` — Agent Teams + 3 paralel subagent
  - `notes/03-stream-json.md` — Tüm event tipleri + Go interface taslakları
  - `notes/04-resume.md` — --resume / --continue
  - `notes/05-worktree.md` — Built-in git worktree
  - `notes/06-rate-limit.md` — Max plan 5 paralel
  - `notes/07-bridge-stability.md` — Mini soak test
  - `notes/08-sse-wrapper.md` — Uçtan uca akış
  - `bridge/main.go` — Go bridge prototype (V2 başlangıcı için)
  - `mock-control-plane/server.ts` — Bun mock CP

### 10.2 Web search bulguları (doğrulandı)

- [Anthropic clarifies ban on third-party tool access to Claude — The Register](https://www.theregister.com/2026/02/20/anthropic_clarifies_ban_third_party_claude_access/)
- [Anthropic Walled Garden: Claude Code Crackdown — paddo.dev](https://paddo.dev/blog/anthropic-walled-garden-crackdown/)
- [Tell HN: Anthropic no longer allowing Claude Code subscriptions to use OpenClaw — Hacker News](https://news.ycombinator.com/item?id=47633396)
- [Orchestrate teams of Claude Code sessions — Claude Code Docs](https://code.claude.com/docs/en/agent-teams)
- [Claude Code Agent Teams: Setup & Usage Guide 2026 — claudefa.st](https://claudefa.st/blog/guide/agents/agent-teams)
- [Collaborating with agents teams in Claude Code — Heeki Park (Medium)](https://heeki.medium.com/collaborating-with-agents-teams-in-claude-code-f64a465f3c11)

### 10.3 RafRaf mevcut docs (referans)

- `docs/01_System_Architecture_Overview.md` — Sistem mimarisi (V1 sonrası güncellenmeli)
- `docs/02_Backend_API_WebSocket_Specification.md` — WS protokol (yeni event'ler eklenecek)
- `docs/03_AI_Agent_Tool_Layer_Specification.md` — **ARCHIVED** (host agent ile birlikte)
- `docs/04_iOS_App_Specification.md` — iOS spec (V1 scope'a göre güncellenmeli)
- `docs/05_Memory_System_Specification.md` — **ARCHIVED V2** (mem0)
- `docs/06_Testing_Strategy.md` — Test stratejisi (geçerli, %80 coverage hedefi)
- `docs/07_Security_Permissions_Cost_Analysis.md` — Güvenlik (geçerli)
- `docs/08_Host_Agent_Specification.md` — **ARCHIVED V2** (host agent)
- `docs/09_Hybrid_Claude_Code_Architecture.md` — claude -p hibrit mimari (claude_code_runner.py kaynağı)
- [`docs/claude-code-usage-tracking.md`](claude-code-usage-tracking.md) — **Statusline JSON pipeline** (§2.11'in detay referansı, ampirik v2.1.126 doğrulanmış)

### 10.4 Yeni eklenmesi planlanan docs

- `docs/runbooks/deploy.md` — Mac local + VPS + EKS deploy adımları
- `docs/runbooks/disaster-recovery.md` — RPO/RTO + restore drill
- `docs/runbooks/secret-rotation.md` — JWT key, APNs key, GitHub PAT rotation
- `docs/runbooks/anthropic-cli-upgrade.md` — Haftalık `claude --version` check + breaking change response
- `docs/runbooks/manual-test-checklist.md` — TestFlight öncesi manuel smoke test (iOS akışları)
- `docs/runbooks/jwt-rs256-migration.md` — HS256 → RS256 geçiş (eğer mevcut HS256 ise)
- `docs/adr/0001-record-architecture-decisions.md`
- `docs/adr/0002-pivot-to-agent-teams.md` — Bu doc'un ADR özeti
- `docs/adr/0003-archive-host-agent.md` — agent_registry_service + host_agent_tool + apps/agent/ archive sebebi
- `docs/adr/0004-archive-mem0-and-voice.md`
- `docs/adr/0005-tool-name-aliasing.md` — Task↔Agent aliasing kararı

---

**Belge sonu.** Yeni Claude session bu doc'u okuyup [§8 Migration fazları](#8-migration--pivot-fazları)'ndan **Faz 0 — Cleanup**'a başlayabilir. Spike repo (`~/Code/claude-teams-spike/`) referans olarak hep yanı başında dursun.
