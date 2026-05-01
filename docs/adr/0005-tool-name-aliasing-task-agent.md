# ADR-0005 — `Task` ↔ `Agent` tool name aliasing

**Status:** Accepted
**Date:** 2026-05-01
**Owner:** The Abi
**Related:** [`10_Production_Pivot_Spec.md`](../10_Production_Pivot_Spec.md) §2.10/C, [`11_Bridge_Spec.md`](../11_Bridge_Spec.md) §6 (alias.go)

## Context

Spike sırasında (`~/Code/claude-teams-spike/`) gerçek `~/.claude/projects/` 1000-sample tool dağılımı çıkarılırken **iki garip gözlem**:

1. `system/init` event'inin `tools[]` listesi **`Task`** içeriyor, `Agent` içermiyor.
2. Ama `assistant` content'teki `tool_use.name` her zaman **`Agent`**, `Task` ismiyle çağrı 0 kullanım.

Spike empirik veri:

```
=== system/init event'inde listed tools (örnek) ===
["Task","AskUserQuestion","Bash","CronCreate","CronDelete","CronList",
 "Edit","EnterPlanMode","EnterWorktree","ExitPlanMode","ExitWorktree",
 "LSP","Monitor","NotebookEdit","PushNotification","Read","RemoteTrigger",
 "ScheduleWakeup","SendMessage","Skill","TaskOutput","TaskStop",
 "TeamCreate","TeamDelete","TodoWrite","ToolSearch","WebFetch","WebSearch","Write",...]

=== 1000-sample assistant tool_use.name dağılımı ===
938 Agent          ← runtime kullanım
  0 Task           ← yok
```

Yani **Mac'te tool `Task` ismiyle kayıtlı, runtime'da `Agent` ismiyle çağrılıyor**. Bu Anthropic'in `claude` CLI v2.x'teki **internal aliasing**'i — muhtemelen 2.x rename'i sırasında init listesi henüz sync olmadı (bug değil, geçiş etkisi).

Bridge Agent parser bu durumu **bilmek zorunda**. Aksi halde:
- `Task` görürse "bilmediğim tool" diye custom tool olarak gösterir → yanlış UX (kullanıcı subagent spawn'ını görmez).
- Sadece `Agent`'a göre kod yazarsa, gelecekte `Task` ismiyle çağrı gelirse subagent spawn'ı atlanır (kırılganlık).

## Decision

Bridge'in `internal/claude/alias.go` modülü tool name canonicalization yapacak:

```go
package claude

var toolAliases = map[string]string{
    "Task": "Agent", // claude CLI v2.x: init listed Task, runtime Agent
}

func CanonicalToolName(name string) string {
    if alias, ok := toolAliases[name]; ok {
        return alias
    }
    return name
}
```

**Canonical name = `Agent`**. Tüm event handling, display name lookup, state tracking `Agent` ismiyle yapılır. `Task` görürse otomatik canonicalize edilir.

iOS WebSocket message format'ı sadece `Agent` görür — bridge canonicalize edip backend'e gönderir, backend opaque forward eder.

## Consequences

**Pozitif:**
- Future-proof: Anthropic gelecekte `tools[]` listesini sync ederse veya tam tersi yaparsa, alias mapping merkezi tek noktada düzeltilir.
- iOS Agent feature view'ı yalnızca `Agent` ismini bilir — basit kontrat.
- Tool display names (Türkçe) tek ada bağlı: `"Agent": "Alt görev çalıştırılıyor"`. `Task` ayrı entry gerek yok.

**Negatif:**
- Hidden coupling: parser `Task` ismini "geçerli" sayan bir başka yerde olursa (örn. backend bir yerde direkt `Task` literal'ı varsa) inconsistency olur. Tüm parser path'leri `CanonicalToolName()` çağırmaya zorlanmalı.
- Anthropic gelecekte aliasing'i tersine çevirirse (`Agent` → `Task` rename) bu mapping güncellenmeli; CI'da haftalık empirical scan (sample session'lar) ile drift tespit edilebilir.

## Alternatives considered

- **A) `Task` ve `Agent` ayrı handle et**: parser her iki ismi de tanır, iOS'ta iki ayrı UI yolu. **Reddedildi** — iOS UX duplikasyon, gereksiz kompleksite.
- **B) Anthropic'e issue/PR aç**: ekosistem tarafında sync olması daha iyi olurdu, ama bu uzun süreli süreç ve V1 launch'a engel. **Yan adım**: V1.1+ için Anthropic'e bildirim yap (issue tracker), bu arada alias maintain et.
- **C) (Seçildi)** Internal alias map: tek noktada canonicalize, basit, future-proof.

## Implementation notes

Faz 0.5 task T0.5.7 ([`12_Action_Plan_Tasks.md`](../12_Action_Plan_Tasks.md)):

- `internal/claude/alias.go` oluşturulur
- `internal/claude/parser.go` her `tool_use.name` access'ini `CanonicalToolName(...)` üzerinden yapar
- Test: `Task` ismiyle synthetic stream-json fixture → parser `Agent` olarak handle ediyor mu doğrulanır
- Doc 11 §6 (claude.alias) bu pattern'i tarif ediyor

## Monitoring

Bridge'in `expvar` metric'lerine eklenecek: `tool_alias_hits_total{from,to}` counter. Production'da `Task` ismiyle hit gelirse log'lanır — Anthropic'in mevcut davranışını takip için.
