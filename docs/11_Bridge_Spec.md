# 11 — `apps/rafraf-bridge/` Spec

> **Amaç**: Mac'te çalışan Go binary'nin (rafraf-bridge) iç tasarımı. EKS'teki backend ile claude CLI arasında köprü; subscription'ı kullanıcının Mac'inden tüketir, stream-json event'leri WS üzerinden backend'e forward eder. Bu doc package-by-package interface kontratını tanımlar — Faz 0.5'in implementation referansı.

**Sürüm:** 1.0
**Tarih:** 2026-05-01
**Sahip:** The Abi
**Geliştirici:** Claude (Opus 4.7)
**Önkoşul okuma:** [`10_Production_Pivot_Spec.md`](10_Production_Pivot_Spec.md) v2.0
**Kaynaklar:**
- Spike Go prototype: `~/Code/claude-teams-spike/bridge/main.go` (276 satır, başlangıç noktası)
- RafRaf Python referans: `apps/_archive/agent-python-v0.1/agent/runners/claude_runner.py` (658 satır, port edilecek logic)

---

## 0. İçindekiler

1. [Genel bakış + mimari yer](#1-genel-bakış--mimari-yer)
2. [Repo yapısı](#2-repo-yapısı)
3. [Package'lar (interface kontratları)](#3-packagelar-interface-kontratları)
4. [Bridge ↔ Backend WS protokolü](#4-bridge--backend-ws-protokolü)
5. [`claude` subprocess wrapper](#5-claude-subprocess-wrapper)
6. [Stream-JSON parser + state](#6-stream-json-parser--state)
7. [Storage watcher (~/.claude/projects/)](#7-storage-watcher-claudeprojects)
8. [Statusline watcher (~/.claude/usage.json)](#8-statusline-watcher-claudeusagejson)
9. [Telemetry + metric kataloğu](#9-telemetry--metric-kataloğu)
10. [Test fixture stratejisi](#10-test-fixture-stratejisi)
11. [Packaging + install flow](#11-packaging--install-flow)
12. [Configuration](#12-configuration)
13. [Açık kararlar](#13-açık-kararlar)

---

## 1. Genel bakış + mimari yer

```
EKS Backend (FastAPI)
   ▲
   │  WSS  /api/v1/agent/ws    (bridge initiates outbound)
   │
   │ envelope: command.* / event.* / ack / error / ping/pong
   │
┌──┴──────────────────────────────────────────────┐
│  rafraf-bridge (Go, Mac launchd)                 │
│  ┌─────────────────────────────────────────┐    │
│  │ cmd/bridge/main.go (entry, flags, daemon)│   │
│  └─────────────────────────────────────────┘    │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐  │
│  │  ws        │ │  protocol  │ │  config    │  │
│  │  client    │ │  envelope  │ │  toml      │  │
│  └────────────┘ └────────────┘ └────────────┘  │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐  │
│  │  claude    │ │  storage   │ │  statusline│  │
│  │  runner    │ │  watcher   │ │  watcher   │  │
│  │  parser    │ │ fsnotify   │ │  poll      │  │
│  │  state     │ │  jsonl     │ │  json      │  │
│  └────────────┘ └────────────┘ └────────────┘  │
│  ┌────────────┐ ┌────────────┐                  │
│  │  security  │ │  telemetry │                  │
│  │  sandbox   │ │  expvar/OTel│                 │
│  └────────────┘ └────────────┘                  │
└──────────────────────┬───────────────────────────┘
                       │ subprocess (exec.CommandContext)
                       ▼
                ┌──────────────┐
                │  claude -p   │  ← subscription bound (~/.claude/credentials)
                │  + Agent Teams│
                └──────────────┘
```

**Tasarım hedefleri:**
- **Tek statik binary** (~10-15 MB), no runtime deps. `go build` çıkışı.
- **Daemon-first**: launchd KeepAlive ile sürekli çalışır, crash'lerden recovery.
- **Stateless**: state Mac dosyalarında (claude credentials) ve EKS Postgres'te. Bridge restart'ta veri kaybı yok.
- **Security minimum**: Mac'te kullanıcı oturumunda çalışır (root değil). Hiçbir secret bridge'te kalıcı saklanmaz; pairing token tek kullanımlık.
- **Test edilebilir**: her package izole testable, real `claude` binary olmadan stream-json fixture ile.
- **Cross-arch**: `GOOS=darwin GOARCH=arm64` (M-series) ve `amd64` (Intel) build matrix.

---

## 2. Repo yapısı

```
apps/rafraf-bridge/
├── cmd/
│   └── bridge/
│       └── main.go                    # entry, flag parsing, signal handling, daemon
├── internal/
│   ├── config/
│   │   ├── config.go                  # AgentConfig (Python'dan port)
│   │   └── config_test.go
│   ├── ws/
│   │   ├── client.go                  # WSClient struct, reconnect, heartbeat
│   │   ├── client_test.go
│   │   └── replay_buffer.go           # local SQLite ring buffer (V1.1+, V1'de in-memory)
│   ├── protocol/
│   │   ├── envelope.go                # Envelope, Type, ID, TS, CorrelationID, Target, Payload
│   │   ├── messages.go                # Type-specific payload struct'lar (command.*, event.*)
│   │   ├── builder.go                 # Build helper'lar (build_claude_stream_*_message Python eşdeğeri)
│   │   └── envelope_test.go
│   ├── claude/
│   │   ├── runner.go                  # Runner.Run(ctx, req, sink) — subprocess execute
│   │   ├── parser.go                  # Parser.Parse(stdout, sink) — line-by-line stream-json
│   │   ├── state.go                   # _StreamState Go karşılığı
│   │   ├── tool_display.go            # 15+ tool için Türkçe display name (Python'dan port)
│   │   ├── alias.go                   # Task ↔ Agent canonical isim
│   │   ├── runner_test.go             # subprocess mock + fixture stream-json
│   │   ├── parser_test.go
│   │   └── testdata/
│   │       ├── 01-simple.jsonl        # spike Test 1 sample
│   │       ├── 02-agent-teams.jsonl   # spike Test 2 sample (3 paralel subagent)
│   │       └── ...
│   ├── storage/
│   │   ├── watcher.go                 # fsnotify on ~/.claude/projects/
│   │   ├── parser.go                  # storage event parser (ai-title, pr-link, attachment.hook_*)
│   │   └── watcher_test.go
│   ├── statusline/
│   │   ├── watcher.go                 # poll ~/.claude/usage.json (5s)
│   │   ├── installer.go               # statusline.py + settings.json patcher
│   │   └── watcher_test.go
│   ├── security/
│   │   ├── sandbox.go                 # opsiyonel: shell whitelist (Python security/'den port)
│   │   └── sandbox_test.go
│   └── telemetry/
│       ├── metrics.go                 # expvar/OTel exporter
│       ├── logging.go                 # zerolog veya slog
│       └── metrics_test.go
├── packaging/
│   ├── launchd/
│   │   └── com.rafraf.bridge.plist
│   ├── homebrew/
│   │   └── rafraf-bridge.rb           # brew formula
│   └── pkg/
│       ├── distribution.xml
│       ├── scripts/
│       │   ├── preinstall.sh
│       │   └── postinstall.sh
│       └── build-pkg.sh               # productbuild + codesign
├── scripts/
│   ├── install-bridge.sh              # geliştirme amaçlı manuel install
│   └── install-statusline.sh          # ~/.claude/statusline.py + settings.json patch
├── go.mod
├── go.sum
├── .golangci.yml
├── Makefile                           # make build, make test, make lint, make pkg
└── README.md
```

---

## 3. Package'lar (interface kontratları)

### 3.1 `internal/config`

```go
package config

type Config struct {
    BackendURL       string `toml:"backend_url"`         // wss://api.rafraf.app/api/v1/agent/ws
    PairingToken     string `toml:"pairing_token"`        // tek kullanımlık (ilk register'da)
    BridgeID         string `toml:"bridge_id"`            // server tarafından atanan UUID
    APITokenPath     string `toml:"api_token_path"`       // ~/.config/rafraf-bridge/token (rotated)

    ClaudeBinary     string `toml:"claude_binary"`        // "claude"
    ProjectDir       string `toml:"project_dir"`          // /Users/.../Code (claude cwd default)
    PermissionMode   string `toml:"permission_mode"`      // "acceptEdits"
    AgentTeams       bool   `toml:"agent_teams"`          // true → CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1

    HeartbeatInterval time.Duration `toml:"heartbeat_interval"` // 15s
    ReconnectInitial  time.Duration `toml:"reconnect_initial"`  // 500ms
    ReconnectMax      time.Duration `toml:"reconnect_max"`      // 30s

    StorageWatcher   StorageWatcherConfig `toml:"storage_watcher"`
    Statusline       StatuslineConfig     `toml:"statusline"`
    Telemetry        TelemetryConfig      `toml:"telemetry"`
}

type StorageWatcherConfig struct {
    Enabled        bool          `toml:"enabled"`
    ProjectsRoot   string        `toml:"projects_root"`   // default ~/.claude/projects
    MaxFileAgeDays int           `toml:"max_file_age_days"` // 30 — eski dosyaları izleme
}

type StatuslineConfig struct {
    Enabled    bool          `toml:"enabled"`
    UsagePath  string        `toml:"usage_path"`       // default ~/.claude/usage.json
    PollEvery  time.Duration `toml:"poll_every"`       // 5s
    StaleAfter time.Duration `toml:"stale_after"`      // 30m
}

func Load(path string) (*Config, error)
func (c *Config) Validate() error
```

Konum: `~/.config/rafraf-bridge/config.toml` (XDG Base Dir).

### 3.2 `internal/ws`

```go
package ws

type Client struct { /* unexported */ }

func New(url string, token string, opts ...Option) *Client

func (c *Client) Run(ctx context.Context) error          // Connect + reconnect loop
func (c *Client) Send(envelope protocol.Envelope) error  // Async send via outbox channel
func (c *Client) OnMessage(handler func(protocol.Envelope)) // Inbound handler
func (c *Client) IsConnected() bool
func (c *Client) Metrics() ClientMetrics

type ClientMetrics struct {
    Connected         atomic.Bool
    ReconnectsTotal   atomic.Int64
    DisconnectsTotal  atomic.Int64
    EventsForwarded   atomic.Int64
    EventsDropped     atomic.Int64  // outbox overflow
    LastPingRoundtrip atomic.Int64  // ms
}
```

**Reconnect algorithm**: exponential backoff `min(initial * 2^attempts, max) + jitter(0, max/2)`.
**Heartbeat**: 15s ping, 30s timeout (3x ping miss → disconnect).
**Auth**: ilk handshake'te Authorization header `Bearer <api_token>`. Token expire'da WS close 401 → bridge yeni token için pairing flow tetikler (manual reauth iOS QR).

### 3.3 `internal/protocol`

```go
package protocol

type Envelope struct {
    Type          string          `json:"type"`           // "command.claude.run", "event.session.assistant", "ack", "error", "ping", "pong"
    ID            string          `json:"id"`             // UUIDv7
    TS            string          `json:"ts"`             // ISO-8601 UTC
    CorrelationID string          `json:"correlation_id,omitempty"`
    Target        string          `json:"target,omitempty"` // "session:abc", "team:xyz"
    Payload       json.RawMessage `json:"payload,omitempty"`
}

// Inbound (backend → bridge)
type CommandClaudeRun struct {
    Prompt         string  `json:"prompt"`
    SessionID      *string `json:"session_id,omitempty"`
    PermissionMode string  `json:"permission_mode,omitempty"` // override config
    AgentTeams     *bool   `json:"agent_teams,omitempty"`     // override config
    ProjectDir     *string `json:"project_dir,omitempty"`     // override
    UserID         string  `json:"user_id"`                    // backend correlation
}

type CommandClaudeAbort struct {
    SessionID string `json:"session_id"`
}

// Outbound (bridge → backend)
type EventSessionInit struct {
    SessionID      string   `json:"session_id"`
    CWD            string   `json:"cwd"`
    Model          string   `json:"model"`
    Tools          []string `json:"tools"`            // system/init.tools[]
    PermissionMode string   `json:"permission_mode"`
    APIKeySource   string   `json:"api_key_source"`   // "none" beklenir
    Version        string   `json:"version"`           // claude_code_version
}

type EventSessionAssistant struct {
    SessionID string          `json:"session_id"`
    Message   json.RawMessage `json:"message"` // raw passthrough — backend Pydantic decode eder
}

type EventSessionUser struct { /* tool_result vs */ }

type EventSessionStream struct {
    SessionID string          `json:"session_id"`
    Delta     json.RawMessage `json:"delta"`
}

type EventSessionTaskStarted struct {
    SessionID    string `json:"session_id"`
    TaskID       string `json:"task_id"`
    Description  string `json:"description"`
    SubagentType string `json:"subagent_type"`
    Isolation    string `json:"isolation"` // "none" | "worktree"
    PromptPreview string `json:"prompt_preview"`
}

type EventSessionTaskNotification struct {
    SessionID  string `json:"session_id"`
    TaskID     string `json:"task_id"`
    Status     string `json:"status"`   // "completed" | "failed"
    Summary    string `json:"summary"`
    TotalTokens int    `json:"total_tokens"`
    ToolUses    int    `json:"tool_uses"`
    DurationMs  int    `json:"duration_ms"`
}

type EventSessionRateLimit struct {
    SessionID      string `json:"session_id"`
    Status         string `json:"status"`           // "allowed" | "warning" | "exceeded"
    RateLimitType  string `json:"rate_limit_type"`  // "five_hour"
    ResetsAt       int64  `json:"resets_at"`
    OverageStatus  string `json:"overage_status"`
    IsUsingOverage bool   `json:"is_using_overage"`
}

type EventSessionResult struct {
    SessionID         string                  `json:"session_id"`
    DurationMs        int                     `json:"duration_ms"`
    NumTurns          int                     `json:"num_turns"`
    Result            string                  `json:"result"`
    StopReason        string                  `json:"stop_reason"`
    TotalCostUSD      float64                 `json:"total_cost_usd"`
    ModelUsage        map[string]ModelUsage   `json:"model_usage"`
    PermissionDenials []json.RawMessage       `json:"permission_denials"`
    TerminalReason    string                  `json:"terminal_reason"`
}

// Storage watcher (~/.claude/projects/)
type EventStorageAITitle struct {
    SessionID string `json:"session_id"`
    Title     string `json:"title"`
}

type EventStoragePRLink struct {
    SessionID    string `json:"session_id"`
    PRNumber     int    `json:"pr_number"`
    PRURL        string `json:"pr_url"`
    PRRepository string `json:"pr_repository"`
    Timestamp    string `json:"timestamp"`
}

// Statusline (~/.claude/usage.json)
type EventUsageReport struct {
    FiveHourPct      int   `json:"five_hour_pct"`
    SevenDayPct      int   `json:"seven_day_pct"`
    FiveHourResetsAt int64 `json:"five_hour_resets_at"`
    SevenDayResetsAt int64 `json:"seven_day_resets_at"`
    ReportedAt       int64 `json:"reported_at"`
}

// Bridge meta
type EventBridgeAlive struct {
    Connected      bool  `json:"connected"`
    UptimeSeconds  int64 `json:"uptime_seconds"`
    BridgeVersion  string `json:"bridge_version"`
    Hostname       string `json:"hostname"`
}

type EventBridgeAuthExpired struct {
    Reason string `json:"reason"` // "claude logged out", "subscription expired"
}
```

**Naming**: snake_case JSON tag (Pydantic ile uyumlu). Go struct'lar PascalCase.

### 3.4 `internal/claude`

Kritik package — 800-1000 satır Go. Spike'taki 276 satırın 4-5 katına çıkar.

```go
package claude

type Runner struct {
    cfg    *config.Config
    logger *slog.Logger
}

type RunRequest struct {
    Prompt         string
    SessionID      string  // empty = new session
    PermissionMode string
    ProjectDir     string  // override
    AgentTeams     bool    // env injection
}

type EventSink interface {
    OnInit(ev protocol.EventSessionInit) error
    OnAssistant(ev protocol.EventSessionAssistant) error
    OnUser(ev protocol.EventSessionUser) error
    OnStream(ev protocol.EventSessionStream) error
    OnTaskStarted(ev protocol.EventSessionTaskStarted) error
    OnTaskProgress(ev protocol.EventSessionTaskProgress) error
    OnTaskNotification(ev protocol.EventSessionTaskNotification) error
    OnRateLimit(ev protocol.EventSessionRateLimit) error
    OnHookStarted(ev protocol.EventSessionHookStarted) error
    OnHookResponse(ev protocol.EventSessionHookResponse) error
    OnResult(ev protocol.EventSessionResult) error
}

func NewRunner(cfg *config.Config) *Runner

func (r *Runner) Run(ctx context.Context, req RunRequest, sink EventSink) error
func (r *Runner) Abort(sessionID string) error  // POST equivalent — claude doesn't have ipc, signal SIGTERM
```

Detay: §5 ve §6.

### 3.5 `internal/storage`

```go
package storage

type Watcher struct { /* ... */ }

type Sink interface {
    OnAITitle(ev protocol.EventStorageAITitle) error
    OnPRLink(ev protocol.EventStoragePRLink) error
    OnHookAttachment(ev protocol.EventStorageHookAttachment) error
}

func NewWatcher(cfg *config.Config) *Watcher

func (w *Watcher) Run(ctx context.Context, sink Sink) error
```

Detay: §7.

### 3.6 `internal/statusline`

```go
package statusline

type Watcher struct { /* ... */ }

func NewWatcher(cfg *config.Config) *Watcher

func (w *Watcher) Run(ctx context.Context, sink func(protocol.EventUsageReport)) error
```

Detay: §8.

---

## 4. Bridge ↔ Backend WS protokolü

### 4.1 Bağlantı kurulumu

```
Bridge starts (launchd):
  1. config.toml load → BackendURL, PairingToken (ilk run) veya APIToken (subsequent)
  2. WSS dial to wss://api.rafraf.app/api/v1/agent/ws
     Header: Authorization: Bearer <token>
              X-Bridge-Version: 0.1.0
              X-Bridge-Hostname: <hostname>
  3. Backend → 101 Switching Protocols (success) veya 401 Unauthorized (token expired)
  4. Bridge sends: {type: "event.bridge.connected", id, ts, payload: {hostname, version}}
  5. Backend acks: {type: "ack", id: <bridge.connected.id>, payload: {bridge_id: "uuid"}}
     - Bridge ID server-assigned (Postgres bridges tablosu)
     - Bridge config'e cache'lenir (tekrar register gerekmez)
```

### 4.2 Komut/event akışı

**Backend → Bridge** (RPC):

```json
{
  "type": "command.claude.run",
  "id": "01HXY...",
  "ts": "2026-05-01T12:00:00Z",
  "payload": {
    "prompt": "implement feature X",
    "session_id": "abc-123",
    "permission_mode": "acceptEdits",
    "agent_teams": true,
    "user_id": "user-xyz"
  }
}
```

**Bridge → Backend** (event akışı, command'a `correlation_id` ile bağlı):

```json
{"type": "ack", "id": "...", "ts": "...", "correlation_id": "01HXY..."}

{"type": "event.session.init", "id": "...", "ts": "...", "correlation_id": "01HXY...",
 "payload": {"session_id": "...", "tools": [...], "permission_mode": "acceptEdits"}}

{"type": "event.session.assistant", "id": "...", "ts": "...", "correlation_id": "01HXY...",
 "payload": {"message": {...raw claude assistant content...}}}

{"type": "event.session.task_started", "id": "...", "correlation_id": "01HXY...",
 "payload": {"task_id": "abc", "description": "...", "isolation": "worktree"}}

...

{"type": "event.session.result", "id": "...", "correlation_id": "01HXY...",
 "payload": {"total_cost_usd": 0.15, "duration_ms": 23000, ...}}
```

### 4.3 Heartbeat

```
every 15s, bridge sends:
  {"type": "ping", "id": "...", "ts": "..."}
backend responds:
  {"type": "pong", "id": "...", "ts": "...", "correlation_id": "<ping.id>"}
```

3x ping miss (45s no pong) → bridge disconnects + reconnect loop.

### 4.4 Error envelope

```json
{
  "type": "error",
  "id": "...",
  "ts": "...",
  "correlation_id": "<original command id>",
  "payload": {
    "code": "claude_subprocess_failed",
    "message": "exit code 1: ...",
    "details": {...}
  }
}
```

Standart error code'lar:
- `claude_binary_not_found` — `claude` PATH'te yok
- `claude_auth_expired` — `claude auth status` loggedIn:false
- `claude_subprocess_failed` — exit non-zero
- `parse_error` — stream-json line malformed
- `subagent_permission_denied` — write/bash blocked, kullanıcı approval gerek

---

## 5. `claude` subprocess wrapper

`internal/claude/runner.go`:

```go
func (r *Runner) Run(ctx context.Context, req RunRequest, sink EventSink) error {
    // 1. Build args
    args := []string{
        "-p",
        "--output-format", "stream-json",
        "--verbose",
        "--include-partial-messages",
    }
    permMode := req.PermissionMode
    if permMode == "" { permMode = r.cfg.PermissionMode }
    args = append(args, "--permission-mode", permMode)
    if req.SessionID != "" {
        args = append(args, "--resume", req.SessionID)
    }
    args = append(args, req.Prompt)

    // 2. cwd
    cwd := req.ProjectDir
    if cwd == "" { cwd = r.cfg.ProjectDir }

    // 3. env (ANTHROPIC_API_KEY exclude + AGENT_TEAMS inject)
    env := filterEnv(os.Environ(), "ANTHROPIC_API_KEY")
    if req.AgentTeams || r.cfg.AgentTeams {
        env = append(env, "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1")
    }

    cmd := exec.CommandContext(ctx, r.cfg.ClaudeBinary, args...)
    cmd.Dir = cwd
    cmd.Env = env

    stdout, err := cmd.StdoutPipe()
    if err != nil { return wrapErr("stdout pipe", err) }
    stderr, err := cmd.StderrPipe()
    if err != nil { return wrapErr("stderr pipe", err) }

    if err := cmd.Start(); err != nil {
        return wrapErr("subprocess start", err)
    }

    // stderr → log (drain in background)
    go drainToLog(r.logger, stderr)

    // stdout → parser
    parser := NewParser(sink, r.logger)
    parseErr := parser.Parse(stdout)

    waitErr := cmd.Wait()

    if parseErr != nil { return parseErr }
    if waitErr != nil { return wrapErr("subprocess wait", waitErr) }
    return nil
}
```

**Abort**: bridge `command.claude.abort` aldığında, runner ctx cancel edilir, `cmd.ProcessState` SIGTERM alır. Subprocess cooperative — claude'un kendi cleanup'ı için ~5s grace, sonra SIGKILL.

**Concurrent runs**: bridge tek anda birden çok run handle eder. Her run kendi context + sink. Map[sessionID]→cancelFunc state'te tutulur (state.go).

**Auth check** (startup'ta):
```go
// On bridge start, check claude auth status
out, _ := exec.Command("claude", "auth", "status").Output()
var status struct { LoggedIn bool `json:"loggedIn"` }
json.Unmarshal(out, &status)
if !status.LoggedIn {
    sink.OnBridgeAuthExpired(...)  // backend'e push, iOS'a notification
}
```

---

## 6. Stream-JSON parser + state

`internal/claude/parser.go`:

```go
type Parser struct {
    sink   EventSink
    logger *slog.Logger
    state  *StreamState
}

func NewParser(sink EventSink, logger *slog.Logger) *Parser

func (p *Parser) Parse(stdout io.Reader) error {
    scanner := bufio.NewScanner(stdout)
    scanner.Buffer(make([]byte, 1<<20), 16<<20) // up to 16 MiB per line
    for scanner.Scan() {
        if err := p.handleLine(scanner.Bytes()); err != nil {
            p.logger.Warn("parse error", "err", err, "line_len", len(scanner.Bytes()))
            // continue — parse error tek satırı bozabilir, akışı kesme
        }
    }
    return scanner.Err()
}
```

`internal/claude/state.go`:

```go
type StreamState struct {
    SessionID         string
    Model             string
    PermissionMode    string
    APIKeySource      string

    ActiveSubagents   map[string]*SubagentState   // task_id → state
    CompletedSubagents []SubagentState

    RateLimitInfo     *RateLimitInfo
    TotalCostUSD      float64
    PermissionDenials []json.RawMessage

    mu sync.Mutex
}

type SubagentState struct {
    TaskID       string
    Description  string
    SubagentType string
    Isolation    string
    Prompt       string
    StartedAt    time.Time
    CompletedAt  *time.Time
    Status       string // "active", "completed", "failed"
    Usage        *SubagentUsage
}
```

`internal/claude/tool_display.go` (Python `_TOOL_DISPLAY_NAMES` dict port):

```go
var ToolDisplayNames = map[string]string{
    "Read":            "Dosya okunuyor",
    "Write":           "Dosya yazılıyor",
    "Edit":            "Dosya düzenleniyor",
    "MultiEdit":       "Çoklu düzenleme",
    "Bash":            "Komut çalıştırılıyor",
    "Glob":            "Dosya aranıyor",
    "Grep":            "İçerik aranıyor",
    "LS":              "Dizin listeleniyor",
    "TodoWrite":       "Görev listesi güncelleniyor",
    "WebFetch":        "Web sayfası getiriliyor",
    "WebSearch":       "Web araması yapılıyor",
    "Agent":           "Alt görev çalıştırılıyor",
    "NotebookEdit":    "Notebook düzenleniyor",
    "AskUserQuestion": "Kullanıcıya soru soruluyor",
    "SendMessage":     "Mesaj gönderiliyor",
    // ekstra (system/init tools[] gözlemlenen):
    "EnterPlanMode": "Plan moduna giriliyor",
    "ExitPlanMode":  "Plan modundan çıkılıyor",
    "EnterWorktree": "Worktree'ye giriliyor",
    "ExitWorktree":  "Worktree'den çıkılıyor",
    "CronCreate":    "Zamanlanmış görev oluşturuluyor",
    "CronDelete":    "Zamanlanmış görev siliniyor",
    "CronList":      "Zamanlanmış görevler listeleniyor",
    "TaskOutput":    "Alt görev çıktısı alınıyor",
    "TaskStop":      "Alt görev durduruluyor",
    "ScheduleWakeup":"Uyandırma planlanıyor",
    "Skill":         "Beceri çağırılıyor",
    "RemoteTrigger": "Uzak tetikleme",
    "Monitor":       "İzleniyor",
}

func DisplayName(toolName string) string {
    canonical := CanonicalToolName(toolName) // alias.go: Task → Agent
    if name, ok := ToolDisplayNames[canonical]; ok {
        return name
    }
    if strings.HasPrefix(canonical, "mcp__") {
        return "MCP aracı çalıştırılıyor"
    }
    return canonical // raw fallback
}
```

`internal/claude/alias.go`:

```go
var toolAliases = map[string]string{
    "Task": "Agent", // claude CLI v2.x: system/init listed Task, runtime tool_use.name = Agent
}

func CanonicalToolName(name string) string {
    if alias, ok := toolAliases[name]; ok {
        return alias
    }
    return name
}
```

---

## 7. Storage watcher (~/.claude/projects/)

`internal/storage/watcher.go`:

```go
type Watcher struct {
    root          string                  // ~/.claude/projects
    fsnotify      *fsnotify.Watcher
    tailOffsets   map[string]int64        // path → byte offset
    interestedTypes map[string]bool        // {"ai-title", "pr-link", "attachment"}
    maxFileAge    time.Duration            // 30 days
    sink          Sink
    mu            sync.Mutex
}

func (w *Watcher) Run(ctx context.Context, sink Sink) error {
    // 1. Initial scan: only files modified in last `maxFileAge`
    err := filepath.Walk(w.root, func(path string, info fs.FileInfo, _ error) error {
        if !strings.HasSuffix(path, ".jsonl") { return nil }
        if time.Since(info.ModTime()) > w.maxFileAge { return nil }
        w.tailOffsets[path] = info.Size() // start from end (only new lines)
        return w.fsnotify.Add(path)
    })
    if err != nil { return err }

    // 2. Watch loop
    for {
        select {
        case <-ctx.Done(): return ctx.Err()
        case event := <-w.fsnotify.Events:
            if event.Op&fsnotify.Write == fsnotify.Write {
                w.tailFile(event.Name)
            }
            if event.Op&fsnotify.Create == fsnotify.Create && strings.HasSuffix(event.Name, ".jsonl") {
                w.fsnotify.Add(event.Name)
                w.tailOffsets[event.Name] = 0
            }
        case err := <-w.fsnotify.Errors:
            w.logger.Warn("fsnotify error", "err", err)
        }
    }
}

func (w *Watcher) tailFile(path string) {
    f, err := os.Open(path)
    if err != nil { return }
    defer f.Close()
    f.Seek(w.tailOffsets[path], io.SeekStart)

    scanner := bufio.NewScanner(f)
    scanner.Buffer(make([]byte, 1<<20), 16<<20)
    for scanner.Scan() {
        line := scanner.Bytes()
        var ev map[string]json.RawMessage
        if err := json.Unmarshal(line, &ev); err != nil { continue }
        var typ string
        json.Unmarshal(ev["type"], &typ)
        if !w.interestedTypes[typ] { continue }
        w.dispatch(typ, line)
    }
    pos, _ := f.Seek(0, io.SeekCurrent)
    w.tailOffsets[path] = pos
}

func (w *Watcher) dispatch(typ string, raw json.RawMessage) {
    switch typ {
    case "ai-title":
        var ev struct {
            SessionID string `json:"sessionId"`
            AITitle   string `json:"aiTitle"`
        }
        if err := json.Unmarshal(raw, &ev); err == nil {
            w.sink.OnAITitle(protocol.EventStorageAITitle{SessionID: ev.SessionID, Title: ev.AITitle})
        }
    case "pr-link":
        // similar
    case "attachment":
        // filter by .attachment.type startsWith "hook_"
    }
}
```

**Optimizasyonlar**:
- `maxFileAge` (30 gün default) ile eski jsonl'ler izlenmez (3.3 GB total, 4474 file → ~%80'i yaşlı, atla)
- Polling fallback yok; fsnotify Mac'te `kqueue` üzerinden çalışır.
- File rotation handling: yeni file create event'i ile ekle.

---

## 8. Statusline watcher (~/.claude/usage.json)

`internal/statusline/watcher.go`:

```go
type Watcher struct {
    path       string         // ~/.claude/usage.json
    pollEvery  time.Duration  // 5s
    staleAfter time.Duration  // 30m
    lastModTime time.Time
    sink       func(protocol.EventUsageReport)
}

func (w *Watcher) Run(ctx context.Context, sink func(protocol.EventUsageReport)) error {
    ticker := time.NewTicker(w.pollEvery)
    defer ticker.Stop()
    for {
        select {
        case <-ctx.Done(): return ctx.Err()
        case <-ticker.C:
            w.poll(sink)
        }
    }
}

func (w *Watcher) poll(sink func(protocol.EventUsageReport)) {
    info, err := os.Stat(w.path)
    if err != nil { return }
    if !info.ModTime().After(w.lastModTime) { return } // unchanged
    w.lastModTime = info.ModTime()

    raw, err := os.ReadFile(w.path)
    if err != nil { return }
    var u struct {
        FiveHourPct      int   `json:"five_hour_pct"`
        SevenDayPct      int   `json:"seven_day_pct"`
        FiveHourResetsAt int64 `json:"five_hour_resets_at"`
        SevenDayResetsAt int64 `json:"seven_day_resets_at"`
        TS               int64 `json:"ts"`
    }
    if err := json.Unmarshal(raw, &u); err != nil { return }

    sink(protocol.EventUsageReport{
        FiveHourPct: u.FiveHourPct,
        SevenDayPct: u.SevenDayPct,
        FiveHourResetsAt: u.FiveHourResetsAt,
        SevenDayResetsAt: u.SevenDayResetsAt,
        ReportedAt: u.TS,
    })
}
```

`internal/statusline/installer.go`:

```go
//go:embed assets/statusline.py
var statuslinePy []byte

func InstallStatuslineScript(claudeDir string) error {
    // 1. Write ~/.claude/statusline.py (overwrite if version changed)
    target := filepath.Join(claudeDir, "statusline.py")
    if err := os.WriteFile(target, statuslinePy, 0755); err != nil { return err }

    // 2. Patch ~/.claude/settings.json
    //    Merge-safe: existing statusLine config korunur, sadece yoksa eklenir
    settingsPath := filepath.Join(claudeDir, "settings.json")
    settings, _ := readJSON(settingsPath)
    if _, hasStatusLine := settings["statusLine"]; !hasStatusLine {
        settings["statusLine"] = map[string]string{
            "type": "command",
            "command": target,
        }
        return writeJSON(settingsPath, settings)
    }
    return nil // user already has custom statusLine; leave alone
}
```

statusline.py içeriği [`docs/claude-code-usage-tracking.md`](claude-code-usage-tracking.md) §statusline implementation'taki Python kod (Go binary'ye `embed.FS` ile gömülür).

---

## 9. Telemetry + metric kataloğu

`internal/telemetry/metrics.go`:

```go
package telemetry

// expvar exports (Go std), V1.1+ OTel SDK ile genişletilebilir
var (
    BridgeUptimeSeconds   = expvar.NewInt("bridge_uptime_seconds")
    BridgeVersion         = expvar.NewString("bridge_version")

    WSConnected           = expvar.NewInt("ws_connected")             // 0/1
    WSReconnectsTotal     = expvar.NewInt("ws_reconnects_total")
    WSDisconnectsTotal    = expvar.NewInt("ws_disconnects_total")
    WSEventsForwardedTotal= expvar.NewInt("ws_events_forwarded_total")
    WSEventsDroppedTotal  = expvar.NewInt("ws_events_dropped_total")  // outbox overflow

    ClaudeSubprocessActive  = expvar.NewInt("claude_subprocess_active")
    ClaudeSubprocessTotal   = expvar.NewInt("claude_subprocess_total")
    ClaudeStreamLinesRead   = expvar.NewInt("claude_stream_lines_read_total")
    ClaudeRateLimitWarnings = expvar.NewInt("claude_rate_limit_warnings_total")
    ClaudeRateLimitExceeded = expvar.NewInt("claude_rate_limit_exceeded_total")
    ClaudeAuthExpired       = expvar.NewInt("claude_auth_expired_total")
    ClaudeTotalCostUSDx1000 = expvar.NewInt("claude_total_cost_usd_x1000") // float'ı int için 1000x

    SubagentSpawnedTotal   = expvar.NewInt("subagent_spawned_total")
    SubagentCompletedTotal = expvar.NewInt("subagent_completed_total")
    SubagentFailedTotal    = expvar.NewInt("subagent_failed_total")

    StorageWatcherEventsTotal = expvar.NewMap("storage_watcher_events_total") // by type
    StorageWatcherLagSeconds  = expvar.NewInt("storage_watcher_lag_seconds")  // gauge

    StatuslineLastReportAge   = expvar.NewInt("statusline_last_report_age_seconds")
    StatuslineFiveHourPct     = expvar.NewInt("statusline_five_hour_pct")
    StatuslineSevenDayPct     = expvar.NewInt("statusline_seven_day_pct")
)
```

`/debug/vars` endpoint expvar'ı dump eder. V2'de OTel `prometheus_client` veya OTLP exporter eklenir.

---

## 10. Test fixture stratejisi

Real `claude` binary olmadan test edebilmek için:

### 10.1 Stream-JSON fixtures

`internal/claude/testdata/`:

- `01-simple.jsonl` — spike Test 1 sample (Hello world cevabı)
- `02-agent-teams.jsonl` — spike Test 2 sample (3 paralel subagent)
- `03-stream-json-tool-read.jsonl` — Read tool kullanımı (~/Code/claude-teams-spike/results/stream-json-samples/02-tool-read.jsonl'den)
- `04-stream-json-tool-write.jsonl` — Write tool
- `05-stream-json-multi-step.jsonl` — multi-turn task
- `06-rate-limit-warning.jsonl` — rate_limit_event with status=warning
- `07-permission-denial.jsonl` — subagent Write blocked
- `08-hook-attachment.jsonl` — storage attachment with hook_success

### 10.2 Parser test pattern

```go
func TestParser_AgentTeams(t *testing.T) {
    f, _ := os.Open("testdata/02-agent-teams.jsonl")
    defer f.Close()

    var spawned, completed atomic.Int32
    sink := &mockSink{
        OnTaskStartedFn:      func(_ protocol.EventSessionTaskStarted) error { spawned.Add(1); return nil },
        OnTaskNotificationFn: func(_ protocol.EventSessionTaskNotification) error { completed.Add(1); return nil },
    }
    p := claude.NewParser(sink, slog.Default())
    if err := p.Parse(f); err != nil { t.Fatal(err) }

    require.Equal(t, int32(3), spawned.Load(),   "expected 3 task_started events")
    require.Equal(t, int32(3), completed.Load(), "expected 3 task_notification events")
}
```

### 10.3 Subprocess mock

Test'te gerçek `claude` çağrılmaz; `Runner` interface'ine `ExecCommand func(ctx, name, args) *exec.Cmd` enjekte edilir. Test'te bu `cat testdata/02-agent-teams.jsonl` ile değiştirilir → subprocess davranışı simüle edilir.

### 10.4 Integration test

`apps/rafraf-bridge/integration_test.go` (build tag `//go:build integration`):

- mock-control-plane spike repo'dan import edilir
- bridge başlatılır, mock CP'ye bağlanır
- mock CP `command.claude.run` gönderir
- `cat testdata/...` ile subprocess simüle edilir
- mock CP'de event'ler doğrulanır

CI'da `go test -tags=integration` ile çalıştırılır.

---

## 11. Packaging + install flow

### 11.1 launchd plist

`packaging/launchd/com.rafraf.bridge.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.rafraf.bridge</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/rafraf-bridge</string>
        <string>--config</string>
        <string>/Users/USERNAME/.config/rafraf-bridge/config.toml</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key>
    <dict><key>SuccessfulExit</key><false/></dict>
    <key>StandardOutPath</key>
    <string>/Users/USERNAME/Library/Logs/rafraf-bridge/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/USERNAME/Library/Logs/rafraf-bridge/stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
```

`USERNAME` postinstall script'inde `${USER}` ile değiştirilir.

### 11.2 Brew formula

`packaging/homebrew/rafraf-bridge.rb`:

```ruby
class RafrafBridge < Formula
  desc "Mac bridge for RafRaf — connects local claude CLI to EKS backend"
  homepage "https://github.com/atknatk/rafraf"
  url "https://github.com/atknatk/rafraf/releases/download/v0.1.0/rafraf-bridge-darwin-arm64.tar.gz"
  sha256 "..."
  version "0.1.0"

  depends_on :macos

  def install
    bin.install "rafraf-bridge"
    (prefix/"Library/LaunchAgents").install "com.rafraf.bridge.plist"
  end

  def post_install
    # Generate config.toml template if missing
    config_dir = Pathname.new("#{ENV["HOME"]}/.config/rafraf-bridge")
    config_dir.mkpath
    config_path = config_dir/"config.toml"
    config_path.write(default_config) unless config_path.exist?
  end

  service do
    run [opt_bin/"rafraf-bridge", "--config", "#{ENV["HOME"]}/.config/rafraf-bridge/config.toml"]
    keep_alive true
    log_path "#{ENV["HOME"]}/Library/Logs/rafraf-bridge/stdout.log"
    error_log_path "#{ENV["HOME"]}/Library/Logs/rafraf-bridge/stderr.log"
  end

  private

  def default_config
    <<~TOML
      backend_url = "wss://api.rafraf.app/api/v1/agent/ws"
      pairing_token = ""  # iOS app QR code'undan kopyala (ilk kurulum)
      claude_binary = "claude"
      project_dir = "#{ENV["HOME"]}/Code"
      permission_mode = "acceptEdits"
      agent_teams = true
    TOML
  end
end
```

Tap: `brew tap atknatk/rafraf` → `brew install rafraf-bridge`.

### 11.3 Signed `.pkg`

`packaging/pkg/build-pkg.sh`:

```bash
#!/bin/bash
# Apple Developer ID ile signed .pkg üret
VERSION=$1
ARCH=${2:-arm64}

# 1. Build binary
GOOS=darwin GOARCH=$ARCH go build -o build/payload/usr/local/bin/rafraf-bridge ./cmd/bridge

# 2. Sign binary
codesign --sign "Developer ID Application: The Abi (VT3X56P4ZL)" \
         --options runtime \
         build/payload/usr/local/bin/rafraf-bridge

# 3. Create payload structure
mkdir -p build/payload/Library/LaunchAgents
cp packaging/launchd/com.rafraf.bridge.plist build/payload/Library/LaunchAgents/

# 4. Build component pkg
pkgbuild --root build/payload \
         --identifier app.rafraf.bridge \
         --version $VERSION \
         --scripts packaging/pkg/scripts \
         build/rafraf-bridge-component.pkg

# 5. Build distribution (final signed)
productbuild --distribution packaging/pkg/distribution.xml \
             --resources packaging/pkg/resources \
             --package-path build \
             --sign "Developer ID Installer: The Abi (VT3X56P4ZL)" \
             dist/rafraf-bridge-${VERSION}-${ARCH}.pkg

# 6. Notarize
xcrun notarytool submit dist/rafraf-bridge-${VERSION}-${ARCH}.pkg \
                       --apple-id "$APPLE_ID" \
                       --team-id "VT3X56P4ZL" \
                       --password "$NOTARY_PASSWORD" \
                       --wait

xcrun stapler staple dist/rafraf-bridge-${VERSION}-${ARCH}.pkg
```

### 11.4 Install flow (kullanıcı perspektifi)

**brew yolu** (geek):

```bash
brew tap atknatk/rafraf
brew install rafraf-bridge
# config.toml düzenle, pairing_token = "..."
brew services start rafraf-bridge
```

**pkg yolu** (TestFlight kullanıcısı için):

1. iOS app onboarding → "Mac setup" adımı
2. Pairing code göster (QR + 6-haneli sayı)
3. Mac'te `rafraf-bridge-0.1.0-arm64.pkg` indir, çift tıkla
4. .pkg installer pairing code'u sorar (postinstall.sh)
5. config.toml otomatik üretilir, launchd auto-start
6. iOS'ta "Bridge bağlandı ✓" gösterir

---

## 12. Configuration

### 12.1 Default config.toml

```toml
backend_url = "wss://api.rafraf.app/api/v1/agent/ws"
pairing_token = ""              # ilk kurulum, sonra api_token_path kullanılır
api_token_path = "~/.config/rafraf-bridge/token"
bridge_id = ""                  # backend tarafından atanır (ilk register sonrası)

claude_binary = "claude"
project_dir = "~/Code"
permission_mode = "acceptEdits"
agent_teams = true

heartbeat_interval = "15s"
reconnect_initial = "500ms"
reconnect_max = "30s"

[storage_watcher]
enabled = true
projects_root = "~/.claude/projects"
max_file_age_days = 30

[statusline]
enabled = true
usage_path = "~/.claude/usage.json"
poll_every = "5s"
stale_after = "30m"

[telemetry]
expvar_enabled = true
expvar_addr = "127.0.0.1:9090"  # /debug/vars
log_level = "info"
log_file = "~/Library/Logs/rafraf-bridge/bridge.log"
```

### 12.2 CLI flags

```
rafraf-bridge --config <path>      # default ~/.config/rafraf-bridge/config.toml
              --version            # print version + exit
              --check              # validate config + claude auth status, exit
              --pair <token>       # one-shot pairing: write token to config and exit
```

---

## 13. Açık kararlar

- **Replay buffer**: V1'de in-memory ring (256 event), V1.1'de SQLite-backed kayıpsız reattach. V1 launch için yeterli mi? Spike'ta drop görüldü ama edge case.
- **Concurrent run limit**: tek anda kaç `claude` subprocess'e izin verelim? Max plan rate limit'e çarpmadık (5 paralel × 80sn = $0.71) ama overlap durumunda concurrency_cap = 4 mantıklı default.
- **stderr drain**: `claude`'un stderr'i log'a basılıyor; debug için gerekli ama gürültülü. Log level config'le ayarlanır mı?
- **Pairing flow**: iOS QR yerine tek 6-haneli sayı + POST `/api/v1/bridges/pair` mı? UX testi gerek.
- **Multi-bridge** (V2 önizleme): bir kullanıcının birden fazla Mac'i olursa? Şimdilik unique constraint `(user_id, hostname)`. V2'de `bridge_label` (kullanıcı verir).
- **`auto-update`** (V1.1+): bridge kendi binary'sini update edebilir mi? Brew yapıyor, .pkg yapmıyor. V1'de manual.
- **Sentry/error tracking**: V1.1+. V1'de structlog → backend'e push.

---

**Belge sonu.** Faz 0.5 task listesi: [`12_Action_Plan_Tasks.md`](12_Action_Plan_Tasks.md) §Faz 0.5.
