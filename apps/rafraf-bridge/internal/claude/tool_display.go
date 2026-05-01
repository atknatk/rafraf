// Package claude — Turkish display strings for Claude tools.
//
// Source of truth merge:
//   - Python apps/agent/agent/runners/claude_runner.py _TOOL_DISPLAY_NAMES
//     (15 baseline entries) — faithful port for behavioural parity with the
//     legacy host agent until T0.10 retires the Python runner.
//   - docs/11_Bridge_Spec.md §6 — V1 spec adding system/init-observed tools
//     (EnterPlanMode, ExitPlanMode, EnterWorktree, ExitWorktree, Cron*,
//     Task*, ScheduleWakeup, Skill, RemoteTrigger, Monitor).
//   - docs/10_Production_Pivot_Spec.md §2.10/A — additional tools surfaced
//     by 1000-sample Mac history mining (TeamCreate, TeamDelete, ToolSearch,
//     PushNotification, LSP).
//
// Tools not present in the map fall through DisplayName's MCP detection
// (mcp__* prefix → generic Turkish label) or, as a last resort, raw
// passthrough so the chat UI can still surface the original identifier.

package claude

import "strings"

// mcpFallback is the Turkish label used when DisplayName receives an MCP
// tool (mcp__server__name) that is not explicitly mapped.
const mcpFallback = "MCP aracı çalıştırılıyor"

// ToolDisplayNames maps canonical tool names to Turkish display strings used
// by the bridge to label tool_use events for the iOS chat UX.
//
// Keep this map sorted by logical grouping (filesystem → shell → search →
// productivity → web → agent → planning → cron/scheduling → teams → misc)
// so future additions are easy to slot into the right neighbourhood.
var ToolDisplayNames = map[string]string{
	// Filesystem & editing.
	"Read":         "Dosya okunuyor",
	"Write":        "Dosya yazılıyor",
	"Edit":         "Dosya düzenleniyor",
	"MultiEdit":    "Çoklu düzenleme",
	"NotebookEdit": "Notebook düzenleniyor",
	// Shell & filesystem discovery.
	"Bash": "Komut çalıştırılıyor",
	"Glob": "Dosya aranıyor",
	"Grep": "İçerik aranıyor",
	"LS":   "Dizin listeleniyor",
	// Productivity / messaging.
	"TodoWrite":       "Görev listesi güncelleniyor",
	"AskUserQuestion": "Kullanıcıya soru soruluyor",
	"SendMessage":     "Mesaj gönderiliyor",
	// Web.
	"WebFetch":  "Web sayfası getiriliyor",
	"WebSearch": "Web araması yapılıyor",
	// Subagents (Agent is the canonical name; Task is aliased — see alias.go).
	"Agent":      "Alt görev çalıştırılıyor",
	"TaskOutput": "Alt görev çıktısı alınıyor",
	"TaskStop":   "Alt görev durduruluyor",
	// Planning & worktree control.
	"EnterPlanMode": "Plan moduna giriliyor",
	"ExitPlanMode":  "Plan modundan çıkılıyor",
	"EnterWorktree": "Worktree'ye giriliyor",
	"ExitWorktree":  "Worktree'den çıkılıyor",
	// Cron / scheduling.
	"CronCreate":     "Zamanlanmış görev oluşturuluyor",
	"CronDelete":     "Zamanlanmış görev siliniyor",
	"CronList":       "Zamanlanmış görevler listeleniyor",
	"ScheduleWakeup": "Uyandırma planlanıyor",
	// Teams (Doc 10 §2.10/A).
	"TeamCreate": "Ekip oluşturuluyor",
	"TeamDelete": "Ekip siliniyor",
	// Misc tooling surfaced by Mac history mining (Doc 10 §2.10/A).
	"Skill":            "Beceri çağırılıyor",
	"RemoteTrigger":    "Uzak tetikleme",
	"Monitor":          "İzleniyor",
	"ToolSearch":       "Araç aranıyor",
	"PushNotification": "Bildirim gönderiliyor",
	"LSP":              "Dil sunucusu çağırılıyor",
}

// DisplayName returns the Turkish display string for a tool. The lookup
// pipeline is:
//
//  1. Alias canonicalization (Task → Agent — ADR-0005).
//  2. ToolDisplayNames lookup on the canonical name.
//  3. MCP fallback when the canonical name starts with the "mcp__" prefix
//     (Anthropic's convention for Model Context Protocol tools).
//  4. Raw passthrough (the canonical name itself) so unknown tools still
//     produce a non-empty label in the iOS chat UX.
//
// The function never panics, never returns the empty string for a non-empty
// input, and is safe to call on uncontrolled input.
func DisplayName(toolName string) string {
	canonical := CanonicalToolName(toolName)
	if name, ok := ToolDisplayNames[canonical]; ok {
		return name
	}
	if strings.HasPrefix(canonical, "mcp__") {
		return mcpFallback
	}
	return canonical
}
