# ADR-0002 — RafRaf'ı resmî `claude` CLI + Agent Teams üzerine pivot et

**Status:** Accepted
**Date:** 2026-05-01
**Owner:** The Abi
**Supersedes:** RafRaf v0.1'in Anthropic SDK + custom orchestration mimarisi
**Related:** [`10_Production_Pivot_Spec.md`](../10_Production_Pivot_Spec.md), [`09_Hybrid_Claude_Code_Architecture.md`](../09_Hybrid_Claude_Code_Architecture.md), `~/Code/claude-teams-spike/notes/_decision.md`

## Context

İki olay V1 mimari kararını sıfırlattı:

1. **Anthropic Ocak 2026** üçüncü taraf araçların (OpenCode, OpenClaw vs.) Claude subscription OAuth token'larını blokladı. 4 Nisan 2026'da tam enforcement. → **Subscription'a erişim için resmî `claude` CLI binary tek geçerli yol**.
2. **Anthropic Şubat 2026 (Opus 4.6 launch)** `claude` CLI v2.1.32+ ile **Agent Teams** özelliğini çıkardı (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`). Lead → multiple subagents, P2P messaging, shared task list, git worktree built-in (`Agent` tool `isolation: "worktree"`).

RafRaf'ın v0.1 vizyonu (Anthropic SDK + custom orchestrator + opencode-ensemble pattern) bu ikisinden sonra **eskidi**. Spike (`~/Code/claude-teams-spike/`) 8 testle resmî CLI + Agent Teams stack'inin V1 için yeterli olduğunu kanıtladı.

## Decision

V1 backbone:

- **AI provider**: resmî Anthropic `claude` CLI v2.1.32+ (Mac'te), subscription bound.
- **Multi-agent**: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` env var (Mac'te aktif).
- **Subscription model**: Max plan ($200/ay sabit), API key kullanılmıyor (`apiKeySource: "none"` doğrulandı, ANTHROPIC_API_KEY env unset olarak çalışıyor).
- **Programmatic interface**: `claude -p --output-format stream-json --verbose --resume <id> --permission-mode acceptEdits "<prompt>"` — backend'in subprocess olarak çağırdığı (ya da V2.0'da bridge'in çağırdığı) standart komut.
- **Subagent spawn**: lead session'ın `Agent` tool çağrısı, `isolation: "worktree"` parametresi git worktree built-in cleanup ile (`.claude/worktrees/agent-<id>/`).

Bu karar [09_Hybrid_Claude_Code_Architecture.md](../09_Hybrid_Claude_Code_Architecture.md)'in zaten attığı pivot'un **Agent Teams ile genişletilmesi**.

## Consequences

**Pozitif:**
- Token bazlı API maliyeti yok; sabit aylık subscription. Spike'ta 5 paralel × 80sn = $0.71 (rate limit'e çarpmadık).
- opencode-ensemble alpha plugin riskinden kurtulduk; resmî Anthropic Agent Teams.
- `claude` CLI built-in: git worktree management, tool permission flow, subagent lifecycle, stream-json structured output. Bizim re-implementation gerek yok.
- Subscription'ın bridge tarafında bound olması (Mac keychain) kullanıcının control'ünü artırıyor; backend'de secret tutulmuyor.

**Negatif:**
- `claude` CLI Mac'te zorunlu → backend EKS'te ise bridge gerekiyor (bkz. [ADR-0003](0003-rewrite-host-agent-as-go-bridge.md)).
- Anthropic CLI breaking change'leri (2026.4'te `edit/patch` tool metadata değişti) bridge'in adapter pattern'i zorunlu kılıyor.
- Statusline JSON yüzdelerini almak için interactive mode gerekli — `claude -p`'de yok (bkz. [docs/claude-code-usage-tracking.md](../claude-code-usage-tracking.md)).
- Subscription auth expire ederse subprocess fail; "Mac'te `claude` login'i tazele" UX'i gerek.
- V2'de pod'da claude çalıştırma sorunu (subscription Mac keychain'de) — V2 ana mimari sorusu olarak kaldı.

## Alternatives considered

- **A) Anthropic SDK direkt çağırma** (RafRaf v0.1): subscription kullanılamıyor (Ocak crackdown), API key ile token başına ödeme. Cost projeksiyonu Max plan'dan 5-10x yüksek tahmin. **Reddedildi**.
- **B) opencode-ensemble plugin korumak**: alpha + solo maintainer, yeni Agent Teams özelliği zaten resmî olarak çıktı. **Reddedildi** (gereksiz fork+maintenance yükü).
- **C) Bedrock üzerinden API** (USE_BEDROCK env var'ı): subscription anlamı yok, AWS bill. **Reddedildi**.
- **D) Tek custom orchestrator yazmak** (Anthropic SDK üstüne): Agent Teams'in ürettiği lead+teammate+P2P+worktree pattern'ini sıfırdan yazmak ~2 ay. **Reddedildi**.

## References

- [Anthropic clarifies ban on third-party tool access — The Register](https://www.theregister.com/2026/02/20/anthropic_clarifies_ban_third_party_claude_access/)
- [Orchestrate teams of Claude Code sessions — Claude Code Docs](https://code.claude.com/docs/en/agent-teams)
- Spike sonuçları: `~/Code/claude-teams-spike/notes/_decision.md` (8 test PASS)
